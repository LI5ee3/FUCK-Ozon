import asyncio
import json
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException

from app import db, performance
from app.main import (performance_campaign_stats, performance_overview, performance_sku_stats,
                      performance_statistics_sync)
from tests.support import DatabaseTestCase, MockRequest


class AdStatisticsTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO ad_campaigns(
              shop_id,campaign_id,name,state) VALUES(?,?,?,?)""", [
                (1, "10", "店铺1 Campaign", "RUNNING"),
                (2, "10", "店铺2 Campaign", "STOPPED"),
            ])

    def test_real_response_parsers_use_rows_and_actual_fields(self):
        campaign = performance.parse_campaign_statistics({"rows": [{
            "id": "10", "title": "Campaign", "objectType": "SKU", "status": "RUNNING",
            "placement": ["NEW_PLACEMENT"], "views": "100", "clicks": "4", "toCart": "2",
            "moneySpent": "12,50", "orders": "1", "ordersMoney": "50,00",
        }]})[0]
        daily = performance.parse_daily_statistics({"rows": [{
            "id": "10", "date": "2026-08-26", "views": "100", "clicks": "4",
            "moneySpent": "12,50", "orders": "1", "ordersMoney": "50,00",
        }]})[0]
        sku = performance.parse_sku_statistics({"rows": [{
            "campaignId": "10", "date": "2026-08-26", "sku": "123", "views": "100",
            "clicks": "4", "toCart": "2", "expense": "12,50", "orders": "1", "sales": "50,00",
        }]})[0]
        self.assertEqual(campaign["placement"], '["NEW_PLACEMENT"]')
        self.assertEqual(daily["impressions"], 100)
        self.assertEqual(daily["spend_rub"], 12.5)
        self.assertEqual(sku["sku"], "123")
        self.assertEqual(sku["revenue_rub"], 50.0)

    def test_stats_request_shapes(self):
        with patch("app.performance.request", return_value={"rows": []}) as requested:
            performance.get_campaign_statistics(1, "2026-08-20", "2026-08-26", ["10", "11"])
            self.assertEqual(requested.call_args.args, (1, "GET", performance.CAMPAIGN_STATS_PATH))
            self.assertEqual(requested.call_args.kwargs["params"]["campaignIds"], ["10", "11"])
            performance.get_sku_statistics(1, "2026-08-26", "2026-08-26", [10])
            self.assertEqual(requested.call_args.args, (1, "POST", performance.SKU_STATS_PATH))
            self.assertEqual(requested.call_args.kwargs["payload"]["dateFrom"], "2026-08-26")

    def test_campaign_daily_sync_upserts_without_duplicates(self):
        row = {"stat_date": "2026-08-20", "campaign_id": "10", "impressions": 10,
               "clicks": 2, "cart_adds": 1, "spend_rub": 3.5, "orders": 1, "revenue_rub": 20}
        updated = dict(row, impressions=12, spend_rub=4.5)
        with patch("app.performance.get_daily_statistics", side_effect=[[row], [updated]]) as fetch:
            first = performance.sync_performance_statistics(1, "2026-08-20", "2026-08-20", "ad_campaign_daily")
            second = performance.sync_performance_statistics(1, "2026-08-20", "2026-08-20", "ad_campaign_daily")
        self.assertEqual((first["fetched"], first["inserted_or_updated"]), (1, 1))
        self.assertEqual((second["fetched"], second["inserted_or_updated"]), (1, 1))
        self.assertEqual(fetch.call_count, 2)
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ad_campaign_daily").fetchone()[0], 1)
            self.assertEqual(tuple(connection.execute(
                "SELECT impressions,spend_rub FROM ad_campaign_daily").fetchone()), (12, 4.5))

    def test_sku_sync_keeps_shops_isolated(self):
        stat_day = datetime.now(performance.MOSCOW).date() - timedelta(days=1)
        rows = lambda shop: [{"stat_date": stat_day.isoformat(), "campaign_id": "10", "sku": "123",
                              "product_name": f"商品{shop}", "impressions": shop, "clicks": 1,
                              "cart_adds": 0, "spend_rub": float(shop), "orders": 0, "revenue_rub": 0}]
        with patch("app.performance.get_sku_statistics", side_effect=lambda shop, *_: rows(shop)):
            performance.sync_performance_statistics(1, stat_day.isoformat(), stat_day.isoformat(), "sku")
            performance.sync_performance_statistics(2, stat_day.isoformat(), stat_day.isoformat(), "sku")
        with db.connect() as connection:
            values = [tuple(row) for row in connection.execute(
                "SELECT shop_id,campaign_id,sku,impressions FROM ad_sku_daily ORDER BY shop_id")]
        self.assertEqual(values, [(1, "10", "123", 1), (2, "10", "123", 2)])

    def test_derived_metrics_return_null_for_zero_denominators(self):
        with db.transaction() as connection:
            connection.execute("""INSERT INTO ad_campaign_daily(
              shop_id,stat_date,campaign_id,impressions,clicks,spend_rub,orders,revenue_rub)
              VALUES(1,'2026-08-20','10',0,0,0,0,0)""")
        result = performance_overview("shop_1", "2026-08-20", "2026-08-20")
        self.assertIsNone(result["ctr"])
        self.assertIsNone(result["avg_cpc_rub"])
        self.assertIsNone(result["drr"])
        self.assertIsNone(result["roas"])

    def test_campaign_and_sku_queries_aggregate_from_sqlite(self):
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO ad_campaign_daily(
              shop_id,stat_date,campaign_id,impressions,clicks,cart_adds,spend_rub,orders,revenue_rub)
              VALUES(?,?,?,?,?,?,?,?,?)""", [
                (1, "2026-08-20", "10", 100, 5, 1, 10, 1, 50),
                (1, "2026-08-21", "10", 200, 5, 2, 20, 1, 100),
            ])
            connection.executemany("""INSERT INTO ad_sku_daily(
              shop_id,stat_date,campaign_id,sku,product_name,impressions,clicks,cart_adds,spend_rub,orders,revenue_rub)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""", [
                (1, "2026-08-20", "10", "123", "测试商品", 100, 5, 1, 10, 1, 50),
                (2, "2026-08-20", "10", "123", "另一商品", 80, 4, 1, 8, 1, 40),
            ])
        campaign = performance_campaign_stats("shop_1", date_from="2026-08-20", date_to="2026-08-21")
        sku = performance_sku_stats("all", date_from="2026-08-20", date_to="2026-08-20")
        self.assertEqual(campaign["items"][0]["spend_rub"], 30.0)
        self.assertEqual(campaign["items"][0]["impressions"], 300)
        self.assertEqual(len(sku["items"]), 2)
        self.assertEqual({row["shop_id"] for row in sku["items"]}, {1, 2})

    def test_overview_all_shops_does_not_merge_skus(self):
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO ad_sku_daily(
              shop_id,stat_date,campaign_id,sku,impressions,clicks,spend_rub,orders,revenue_rub)
              VALUES(?,?,?,?,?,?,?,?,?)""", [
                (1, "2026-08-20", "10", "123", 10, 1, 2, 1, 20),
                (2, "2026-08-20", "10", "123", 20, 2, 3, 1, 30),
            ])
        result = performance_sku_stats("all", date_from="2026-08-20", date_to="2026-08-20")
        self.assertEqual([(row["shop_id"], row["sku"]) for row in result["items"]], [(2, "123"), (1, "123")])

    def test_unknown_placement_is_metadata_not_error(self):
        row = performance.parse_campaign_statistics({"rows": [{"id": "10", "placement": ["FUTURE"]}]})[0]
        self.assertEqual(row["placement"], '["FUTURE"]')

    def test_statistics_sync_route_does_not_return_credentials(self):
        result = {"shop_id": 1, "success": True, "fetched": 1, "inserted_or_updated": 1,
                  "date_from": "2026-08-20", "date_to": "2026-08-20"}
        with patch("app.main.sync_performance_statistics", return_value=result):
            response = asyncio.run(performance_statistics_sync(MockRequest({
                "shop_id": 1, "date_from": "2026-08-20", "date_to": "2026-08-20",
            })))
        text = json.dumps(response)
        self.assertNotIn("client_secret", text)
        self.assertNotIn("access_token", text)
        self.assertEqual(response["inserted_or_updated"], 1)

    def test_statistics_sync_configuration_error_is_clear(self):
        with patch("app.main.sync_performance_statistics",
                   side_effect=performance.PerformanceConfigurationError("Shop 2 尚未配置 Ozon Performance API")):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(performance_statistics_sync(MockRequest({
                    "shop_id": 2, "date_from": "2026-08-20", "date_to": "2026-08-20",
                })))
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("Shop 2 尚未配置", raised.exception.detail)
