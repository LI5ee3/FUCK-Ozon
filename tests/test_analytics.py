import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import ozon
from app.routers.analytics import (BEIJING, _analytics_range, get_analytics_data,
                                    get_product_queries, get_product_query_details)
from tests.support import DatabaseTestCase


class AnalyticsApiTest(DatabaseTestCase):
    def test_ozon_wrappers_send_verified_payloads(self):
        with patch("app.ozon._post", return_value={}) as post:
            ozon.analytics_data(2, "2026-08-01", "2026-08-07", "123", 50, 10)
            payload = post.call_args.args[2]
            self.assertEqual(post.call_args.args[:2], (2, "/v1/analytics/data"))
            self.assertEqual(payload["filters"], [{"key": "sku", "op": "EQ", "value": "123"}])
            self.assertEqual((payload["limit"], payload["offset"]), (50, 10))

            ozon.product_queries(1, "from", "to", [123])
            self.assertEqual(post.call_args.args[1], "/v1/analytics/product-queries")
            self.assertEqual(post.call_args.args[2]["page"], 0)

            ozon.product_query_details(1, "from", "to", [123])
            self.assertEqual(post.call_args.args[1], "/v1/analytics/product-queries/details")
            self.assertEqual(post.call_args.args[2]["limit_by_sku"], 15)

    def test_default_range_is_latest_available_30_days(self):
        start, end = _analytics_range(now=datetime(2026, 8, 26, 12, tzinfo=BEIJING))
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-07-25", "2026-08-23"))

    @patch("app.routers.analytics.analytics_data")
    def test_traffic_keeps_shop_identity_and_zero_rates(self, request):
        request.side_effect = [
            {"result": {"data": [{"dimensions": [{"id": "101", "name": "A"}],
                                    "metrics": [10, 0, 0, 0, 0, 100]}],
                        "totals": [10, 0, 0, 0, 0, 100]}},
            {"result": {"data": [{"dimensions": [{"id": "202", "name": "B"}],
                                    "metrics": [20, 10, 0, 5, 1, 200]}],
                        "totals": [20, 10, 0, 5, 1, 200]}},
        ]
        data = get_analytics_data(0, "", 1, 50, "2026-08-01", "2026-08-07")
        self.assertEqual({row["shop_id"] for row in data["items"]}, {1, 2})
        self.assertEqual([row["revenue"] for row in data["shops"]], [100, 200])
        self.assertNotIn("revenue", data)
        first = next(row for row in data["items"] if row["shop_id"] == 1)
        self.assertEqual(first["view_rate"], 0)
        self.assertIsNone(first["cart_rate"])
        self.assertIsNone(first["order_rate"])

    @patch("app.routers.analytics.product_query_details")
    @patch("app.routers.analytics.product_queries")
    @patch("app.routers.analytics.analytics_data")
    def test_search_currency_and_details_are_on_demand(self, traffic, products, details):
        traffic.side_effect = [
            {"result": {"data": [{"dimensions": [{"id": "101"}]}]}},
            {"result": {"data": [{"dimensions": [{"id": "202"}]}]}},
        ]
        products.side_effect = [
            {"items": [{"sku": 101, "name": "A", "gmv": 10, "currency": "USD",
                         "unique_search_users": 2}]},
            {"items": [{"sku": 202, "name": "B", "gmv": 20, "currency": "CNY",
                         "unique_search_users": 3}]},
        ]
        data = get_product_queries(0, "", 1, 50, "2026-08-01", "2026-08-07")
        self.assertEqual({row["currency"] for row in data["items"]}, {"USD", "CNY"})
        details.assert_not_called()

        details.return_value = {"queries": [{"sku": 202, "query": "phone", "position": 8,
                                               "unique_search_users": 9, "unique_view_users": 3,
                                               "view_conversion": 12.5, "order_count": 1,
                                               "gmv": 20, "currency": "CNY"}], "total": 1}
        result = get_product_query_details(2, "202", 1, 50, "2026-08-01", "2026-08-07")
        self.assertEqual(result["items"][0]["query"], "phone")
        self.assertEqual(details.call_args.args[4], 0)

    @patch("app.routers.analytics.analytics_data", side_effect=RuntimeError("Ozon analytics unavailable"))
    def test_traffic_failure_is_explicit(self, _request):
        with self.assertRaises(HTTPException) as raised:
            get_analytics_data(1, "", 1, 50, "2026-08-01", "2026-08-07")
        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("unavailable", raised.exception.detail)

    def test_page_loads_details_only_from_click_handler(self):
        view = (Path(__file__).parents[1] / "frontend/src/views/AnalyticsView.vue").read_text()
        self.assertIn("onClick: () => { void loadDetails(row); }", view)
        rows_loader = view[view.index("async function loadProductQueryRows"):view.index("async function loadDetails")]
        self.assertNotIn("getProductQueryDetails", rows_loader)


if __name__ == "__main__":
    unittest.main()
