import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import db, ozon
from app.main import (BEIJING, BUYER_UNCLAIMED_REASONS, _analytics_range,
                      _months_before, get_analytics_data, get_product_queries,
                      get_product_query_details, risk, risk_reasons, timeliness)
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

    @patch("app.main.analytics_data")
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

    @patch("app.main.product_query_details")
    @patch("app.main.product_queries")
    @patch("app.main.analytics_data")
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

    @patch("app.main.analytics_data", side_effect=RuntimeError("Ozon analytics unavailable"))
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


class RiskPageTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        orders = [
            (1, "NORMAL", "FBP", "2026-08-09T16:00:00Z", "已签收", None, 1, "SKU-A", 2),
            (1, "CUSTOMS", "realFBS", "2026-08-10T08:00:00Z", "已取消",
             "Отправление не прошло таможенное оформление", 1, "SKU-A", 2),
            (1, "OTHER", "WHD", "2026-08-10T15:59:59Z", "已取消", "Неизвестная причина", 1, "SKU-A", 4),
            (1, "PRE", "FBP", "2026-08-10T05:00:00Z", "已取消", BUYER_UNCLAIMED_REASONS[0], 0, "SKU-A", 9),
            (1, "GROUP-MEMBER", "WHD", "2026-08-10T06:00:00Z", "已签收", None, 1, "SKU-B", 2),
            (1, "BEFORE", "FBP", "2026-08-09T15:59:59Z", "已签收", None, 1, "OUT", 8),
            (1, "AFTER", "FBP", "2026-08-10T16:00:00Z", "已取消", "Неизвестная причина", 1, "OUT", 8),
            (2, "SHOP2", "FBP", "2026-08-10T01:00:00Z", "已签收", None, 1, "SKU-A", 5),
        ]
        orders.extend((1, f"BUYER-{index}", "FBP", f"2026-08-10T0{index}:00:00Z", "已取消",
                       reason, 1, "SKU-A", quantity)
                      for index, (reason, quantity) in enumerate(zip(BUYER_UNCLAIMED_REASONS, (3, 1, 1, 1, 1)), 1))
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO orders(shop_id,posting_number,channel,created_at,
              status_raw,cancel_reason_raw,shipped,source) VALUES(?,?,?,?,?,?,?,'api')""",
              [row[:7] for row in orders])
            connection.executemany("""INSERT INTO order_items(shop_id,channel,posting_number,sku,
              offer_id,product_name_raw,quantity,source) VALUES(?,?,?,?,?,?,?,'api')""",
              [(shop, channel, posting, sku, f"O-{sku}", f"商品 {sku}", quantity)
               for shop, posting, channel, _, _, _, _, sku, quantity in orders])

    def test_matrix_uses_piece_totals_channels_boundaries_and_shop_isolation(self):
        data = risk(1, False, "2026-08-10", "2026-08-10")
        row = next(item for item in data["items"] if item["sku"] == "SKU-A")
        self.assertEqual(len([item for item in data["items"] if item["sku"] == "SKU-A"]), 1)
        self.assertEqual((row["total"]["valid"], row["total"]["cancelled"],
                          row["total"]["unclaimed"], row["total"]["customs"]), (15, 13, 7, 2))
        self.assertAlmostEqual(row["total"]["cancelled_rate"], 13 / 15)
        self.assertEqual((row["channels"]["FBP"]["valid"], row["channels"]["realFBS"]["valid"],
                          row["channels"]["WHD"]["valid"]), (9, 2, 4))
        self.assertIn("O-SKU-A", row["search_text"])
        self.assertIn("商品 SKU-A", row["search_text"])
        self.assertNotIn("OUT", {item["sku"] for item in data["items"]})
        self.assertEqual(risk(2, False, "2026-08-10", "2026-08-10")["items"][0]["total"]["valid"], 5)

    def test_grouping_unclaimed_customs_unknown_reason_and_detail_range(self):
        with db.transaction() as connection:
            group_id = connection.execute("""INSERT INTO product_groups(name,created_at,updated_at)
              VALUES('旧组名','2026-08-10T00:00:00Z','2026-08-10T00:00:00Z')""").lastrowid
            connection.executemany("INSERT INTO product_group_members(group_id,key_type,key_value) VALUES(?,?,?)", [
                (group_id, "sku", "SKU-A"), (group_id, "sku", "SKU-B"),
                (group_id, "offer_id", "O-SKU-A")])
            connection.execute("INSERT INTO product_group_config VALUES(?,'O-SKU-A','SKU-A','active','')",
                               (group_id,))
        grouped = risk(1, False, "2026-08-10", "2026-08-10")
        row = next(item for item in grouped["items"] if item["primary_offer_id"] == "O-SKU-A")
        self.assertEqual((row["member_count"], row["total"]["valid"]), (2, 17))
        reasons = risk_reasons(1, "", "2026-08-10", "2026-08-10")
        raw = {item["reason_raw"]: item for item in reasons["items"]}
        self.assertEqual(raw["Неизвестная причина"]["reason_name"], "Неизвестная причина")
        self.assertEqual(raw["Отправление не прошло таможенное оформление"]["total"]["pieces"], 2)
        for reason in BUYER_UNCLAIMED_REASONS:
            self.assertIn(reason, raw)
        delivery = raw[BUYER_UNCLAIMED_REASONS[2]]
        self.assertEqual(delivery["reason_name"], "买方取消订单：对交货时间不满意")
        details = risk_reasons(1, "Неизвестная причина", "2026-08-10", "2026-08-10")["details"]
        self.assertEqual([item["posting_number"] for item in details], ["OTHER"])

    def test_default_range_validation_and_empty_channel_sample(self):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        data = risk(1)
        self.assertEqual(data["range"], {"from": _months_before(today).isoformat(), "to": today.isoformat()})
        row = next(item for item in risk(1, False, "2026-08-10", "2026-08-10")["items"] if item["sku"] == "SKU-B")
        self.assertIsNone(row["channels"]["FBP"])
        with self.assertRaises(HTTPException):
            risk(1, False, "2026-08-11", "2026-08-10")


class TimelinessPageTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        orders = [
            (1, "S1-ABC-001", "FBP", "2026-08-09T16:00:00Z", "2026-08-09T17:00:00Z", "2026-08-09T20:00:00Z", "已签收", 1),
            (1, "S1-XYZ-002", "realFBS", "2026-08-10T15:59:59Z", "2026-08-10T18:00:00Z", "2026-08-10T18:00:00Z", "已签收", 1),
            (1, "PRE-CANCEL", "FBP", "2026-08-10T01:00:00Z", None, None, "已取消", 0),
            (1, "BEFORE", "FBP", "2026-08-09T15:59:59Z", "2026-08-09T17:00:00Z", None, "已发货", 1),
            (2, "S2-ABC-003", "WHD", "2026-08-10T02:00:00Z", "2026-08-10T04:00:00Z", "2026-08-10T10:00:00Z", "已签收", 1),
        ]
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO orders(shop_id,posting_number,channel,created_at,
              shipped_at,delivered_at,status_raw,shipped,source) VALUES(?,?,?,?,?,?,?,?,'api')""", orders)
            connection.execute("""INSERT INTO order_items(shop_id,channel,posting_number,sku,
              offer_id,product_name_raw,quantity,source) VALUES(1,'realFBS','S1-XYZ-002',
              'MATCH-SKU','MATCH-OFFER','MATCH PRODUCT',1,'api')""")

    def test_beijing_range_shop_and_fallback_delivery(self):
        data = timeliness(0, 1, 30, "", "2026-08-10", "2026-08-10")
        self.assertEqual((data["summary"]["orders"], data["total"]), (3, 3))
        self.assertEqual([(row["shop_id"], row["channel"]) for row in data["groups"]],
                         [(1, "FBP"), (1, "realFBS"), (2, "WHD")])
        fallback = next(row for row in data["items"] if row["posting_number"] == "S1-XYZ-002")
        self.assertIsNone(fallback["delivered_at"])
        self.assertIsNone(fallback["delivery_hours"])
        self.assertNotIn("PRE-CANCEL", {row["posting_number"] for row in data["items"]})

    def test_posting_query_only_changes_details(self):
        base = timeliness(1, 1, 30, "", "2026-08-10", "2026-08-10")
        filtered = timeliness(1, 1, 30, "ABC", "2026-08-10", "2026-08-10")
        exact = timeliness(1, 1, 30, "S1-ABC-001", "2026-08-10", "2026-08-10")
        sku = timeliness(1, 1, 30, "MATCH-SKU", "2026-08-10", "2026-08-10")
        self.assertEqual((filtered["total"], exact["total"], sku["total"]), (1, 1, 0))
        self.assertEqual(filtered["summary"], base["summary"])
        self.assertEqual(filtered["groups"], base["groups"])
        self.assertEqual(filtered["data_through"], base["data_through"])

    def test_default_range_and_validation(self):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        self.assertEqual(timeliness(1)["range"],
                         {"from": _months_before(today).isoformat(), "to": today.isoformat()})
        with self.assertRaises(HTTPException):
            timeliness(1, 1, 30, "", "2026-08-11", "2026-08-10")

    def test_timeliness_handles_samples_completeness_missing_invalid_and_negative_times(self):
        orders = [
          ("V1", "2026-08-01T00:00:00Z", "2026-08-01T01:00:00Z", "2026-08-01T03:00:00Z", "已签收", 1),
          ("V2", "2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z", "2026-08-01T05:00:00Z", "已签收", 1),
          ("V3", "2026-08-01T00:00:00Z", "坏时间", "坏时间", "已签收", 1),
          ("V4", "2026-08-01T00:00:00Z", None, "2026-08-01T08:00:00Z", "已签收", 1),
          ("V5", "2026-08-01T00:00:00Z", "2026-08-01T04:00:00Z", None, "配送中", 1),
          ("V6", "2026-08-01T05:00:00Z", "2026-08-01T04:00:00Z", "2026-08-01T06:00:00Z", "已签收", 1),
          ("V7", "2026-08-01T00:00:00Z", "2026-08-01T03:00:00Z", "2026-08-01T01:00:00Z", "已签收", 1),
          ("C1", "2026-08-01T00:00:00Z", None, None, "已取消", 0),
        ]
        with db.transaction() as connection:
            connection.execute("DELETE FROM order_items")
            connection.execute("DELETE FROM orders")
            connection.executemany("""INSERT INTO orders(shop_id,posting_number,channel,created_at,
              shipped_at,delivered_at,status_raw,shipped,source) VALUES(1,?,'FBP',?,?,?,?,?,'api')""", orders)
            connection.executemany("""INSERT INTO order_items(
              shop_id,channel,posting_number,sku,quantity,source) VALUES(1,'FBP','V1',?,1,'api')""",
              [("SKU-1",), ("SKU-2",)])
        data = timeliness(1)
        group = data["groups"][0]
        self.assertEqual(data["total"], 7)
        self.assertEqual((group["ship_samples"], group["delivery_samples"]), (4, 3))
        self.assertAlmostEqual(group["p50_ship_hours"], 2.5)
        self.assertAlmostEqual(group["avg_ship_hours"], 2.5)
        self.assertAlmostEqual(group["p90_ship_hours"], 3.7)
        self.assertAlmostEqual(group["p50_delivery_hours"], 2)
        self.assertAlmostEqual(group["avg_delivery_hours"], 7 / 3)
        self.assertAlmostEqual(group["p90_delivery_hours"], 2.8)
        self.assertEqual((group["created_completeness"], group["shipped_completeness"],
                          group["delivered_completeness"]), (1, 5 / 7, 5 / 7))
        self.assertTrue(group["ship_sample_insufficient"])
        self.assertTrue(group["delivery_sample_insufficient"])
        rows = {row["posting_number"]: row for row in data["items"]}
        self.assertTrue(rows["V3"]["ship_anomaly"])
        self.assertTrue(rows["V3"]["delivery_anomaly"])
        self.assertIsNone(rows["V4"]["ship_hours"])
        self.assertIsNone(rows["V6"]["ship_hours"])
        self.assertIsNone(rows["V7"]["delivery_hours"])
