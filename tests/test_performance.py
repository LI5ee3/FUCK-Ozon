import asyncio
import json
import time
import unittest
import urllib.error
from io import BytesIO
from unittest.mock import patch

from fastapi import HTTPException

from app import db, ozon, performance
from app.main import performance_campaign_sync, performance_campaigns, performance_test
from tests.support import DatabaseTestCase, MockRequest


ENV = {
    "SHOP_1_OZON_PERF_CLIENT_ID": "one@advertising.performance.ozon.ru",
    "SHOP_1_OZON_PERF_CLIENT_SECRET": "secret-one",
    "SHOP_2_OZON_PERF_CLIENT_ID": "two@advertising.performance.ozon.ru",
    "SHOP_2_OZON_PERF_CLIENT_SECRET": "secret-two",
}


class JsonResponse:
    def __init__(self, value):
        self.body = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


def http_error(status, value):
    return urllib.error.HTTPError("https://api-performance.ozon.ru", status, "error", {},
                                  BytesIO(json.dumps(value).encode()))


class PerformanceClientTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        performance._token_cache.clear()

    def tearDown(self):
        performance._token_cache.clear()
        super().tearDown()

    def test_missing_configuration_is_explicit(self):
        with patch("app.performance._env", return_value={}):
            with self.assertRaisesRegex(performance.PerformanceConfigurationError,
                                        "Shop 1 尚未配置 Ozon Performance API"):
                performance.get_token(1)

    def test_token_request_uses_performance_credentials(self):
        with patch("app.performance._env", return_value=ENV), \
             patch("app.performance.urllib.request.urlopen",
                   return_value=JsonResponse({"access_token": "token-one", "expires_in": 1800,
                                              "token_type": "Bearer"})) as opened:
            self.assertEqual(performance.get_token(1), "token-one")
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, performance.BASE_URL + performance.TOKEN_PATH)
        self.assertEqual(json.loads(request.data)["grant_type"], "client_credentials")
        self.assertEqual(json.loads(request.data)["client_id"], ENV["SHOP_1_OZON_PERF_CLIENT_ID"])

    def test_token_cache_avoids_repeated_token_requests(self):
        with patch("app.performance._env", return_value=ENV), \
             patch("app.performance.urllib.request.urlopen",
                   return_value=JsonResponse({"access_token": "cached", "expires_in": 1800})) as opened:
            self.assertEqual((performance.get_token(1), performance.get_token(1)), ("cached", "cached"))
        self.assertEqual(opened.call_count, 1)

    def test_expired_token_is_refreshed(self):
        performance._token_cache[1] = {"access_token": "expired", "expires_at": time.time() - 1}
        with patch("app.performance._env", return_value=ENV), \
             patch("app.performance.urllib.request.urlopen",
                   return_value=JsonResponse({"access_token": "fresh", "expires_in": 1800})) as opened:
            self.assertEqual(performance.get_token(1), "fresh")
        self.assertEqual(opened.call_count, 1)

    def test_401_refreshes_once_and_retries(self):
        responses = [
            JsonResponse({"access_token": "old", "expires_in": 1800}),
            http_error(401, {"message": "expired"}),
            JsonResponse({"access_token": "new", "expires_in": 1800}),
            JsonResponse({"list": [{"id": "10", "title": "Campaign"}]}),
        ]
        with patch("app.performance._env", return_value=ENV), \
             patch("app.performance.urllib.request.urlopen", side_effect=responses) as opened:
            self.assertEqual(performance.list_campaigns(1)[0]["id"], "10")
        self.assertEqual(opened.call_count, 4)
        self.assertEqual(opened.call_args_list[1].args[0].get_header("Authorization"), "Bearer old")
        self.assertEqual(opened.call_args_list[3].args[0].get_header("Authorization"), "Bearer new")

    def test_campaign_response_is_parsed(self):
        with patch("app.performance.request", return_value={"list": [{"id": "10"}]}) as request:
            self.assertEqual(performance.list_campaigns(2), [{"id": "10"}])
        request.assert_called_once_with(2, "GET", performance.CAMPAIGN_PATH)

    def test_campaign_upsert_and_shop_isolation(self):
        shop_one = [{"id": "10", "title": "旧名称", "state": "CAMPAIGN_STATE_RUNNING",
                     "paymentType": "CPC", "weeklyBudget": "1500000",
                     "placement": ["PLACEMENT_TOP"],
                     "createdAt": "2026-08-01T00:00:00Z"}]
        shop_one_updated = [{"id": "10", "title": "新名称", "state": "CAMPAIGN_STATE_STOPPED",
                             "paymentType": "CPC", "weeklyBudget": "2500000",
                             "placement": ["PLACEMENT_TOP"]}]
        shop_two = [{"id": "10", "title": "店铺2名称", "state": "CAMPAIGN_STATE_RUNNING"}]
        with patch("app.performance._env", return_value=ENV), \
             patch("app.performance.list_campaigns",
                   side_effect=[shop_one, shop_one_updated, shop_two]):
            self.assertEqual(performance.sync_performance_campaigns(1)["inserted_or_updated"], 1)
            self.assertEqual(performance.sync_performance_campaigns(1)["inserted_or_updated"], 1)
            self.assertEqual(performance.sync_performance_campaigns(2)["inserted_or_updated"], 1)
        with db.connect() as connection:
            rows = connection.execute("""SELECT shop_id,campaign_id,name,state,placement,weekly_budget
              FROM ad_campaigns ORDER BY shop_id""").fetchall()
        self.assertEqual([tuple(row) for row in rows], [
            (1, "10", "新名称", "CAMPAIGN_STATE_STOPPED", '["PLACEMENT_TOP"]', 2.5),
            (2, "10", "店铺2名称", "CAMPAIGN_STATE_RUNNING", None, None),
        ])

    def test_sync_route_records_result_without_secrets(self):
        result = {"shop_id": 1, "success": True, "fetched": 2, "inserted_or_updated": 2}
        with patch("app.main.sync_performance_campaigns", return_value=result):
            response = asyncio.run(performance_campaign_sync(MockRequest({"shop_id": "shop_1"})))
        self.assertEqual(response["inserted_or_updated"], 2)
        with db.connect() as connection:
            row = connection.execute("SELECT module,status,records FROM sync_runs").fetchone()
        self.assertEqual(tuple(row), ("ad_campaigns", "success", 2))
        self.assertNotIn("client_secret", json.dumps(response))
        self.assertNotIn("access_token", json.dumps(response))

    def test_missing_configuration_route_returns_clear_error(self):
        with patch("app.main.list_campaigns",
                   side_effect=performance.PerformanceConfigurationError(
                       "Shop 1 尚未配置 Ozon Performance API")):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(performance_test(MockRequest({"shop_id": 1})))
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("Shop 1 尚未配置 Ozon Performance API", raised.exception.detail)

    def test_campaign_query_returns_persisted_rows_by_shop(self):
        with db.transaction() as connection:
            connection.execute("""INSERT INTO ad_campaigns(
              shop_id,campaign_id,name,state,synced_at) VALUES(1,'1','One','RUNNING','2026-08-01T00:00:00Z')""")
            connection.execute("""INSERT INTO ad_campaigns(
              shop_id,campaign_id,name,state,synced_at) VALUES(2,'1','Two','RUNNING','2026-08-01T00:00:00Z')""")
        self.assertEqual([row["name"] for row in performance_campaigns("shop_1")], ["One"])
        self.assertEqual([row["name"] for row in performance_campaigns("shop_2")], ["Two"])

    def test_performance_failure_does_not_change_seller_client(self):
        with patch("app.performance._env", return_value={}):
            with self.assertRaises(performance.PerformanceConfigurationError):
                performance.get_token(1)
        with patch("app.ozon._post", return_value={"ok": True}) as seller_request:
            self.assertEqual(ozon._post(1, "/v1/roles", {}), {"ok": True})
        seller_request.assert_called_once_with(1, "/v1/roles", {})
        self.assertNotEqual(performance.BASE_URL, ozon.API)

    def test_error_text_redacts_performance_secret(self):
        secret = ENV["SHOP_1_OZON_PERF_CLIENT_SECRET"]
        with patch("app.performance._env", return_value=ENV), \
             patch("app.performance.urllib.request.urlopen",
                   side_effect=http_error(500, {"message": secret})):
            with self.assertRaises(performance.PerformanceAPIError) as raised:
                performance.get_token(1)
        self.assertNotIn(secret, str(raised.exception))
