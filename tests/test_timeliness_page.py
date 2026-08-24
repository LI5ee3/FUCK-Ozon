import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import db
from app.main import _months_before, timeliness
from tests.support import DatabaseTestCase


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


if __name__ == "__main__":
    unittest.main()
