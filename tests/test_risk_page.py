import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import db
from app.main import BUYER_UNCLAIMED_REASONS, _months_before, risk, risk_reasons
from tests.support import DatabaseTestCase


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


if __name__ == "__main__":
    unittest.main()
