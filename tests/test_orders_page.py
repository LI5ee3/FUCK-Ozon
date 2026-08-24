import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app import db
from app.main import orders


class OrdersPageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO orders(shop_id,posting_number,channel,created_at,
              status_raw,cancel_reason_raw,shipped,amount_original,amount_currency,source)
              VALUES(?,?,?,?,?,?,?,?,?,'api')""", [
                (1, "BEFORE", "FBP", "2026-08-09T15:59:59Z", "已签收", None, 1, 10, "USD"),
                (1, "MULTI", "FBP", "2026-08-09T16:00:00Z", "已取消", "Покупатель отменил заказ", 0, 30, "USD"),
                (1, "FALLBACK", "realFBS", "2026-08-10T15:59:59Z", "awaiting_registration", "Неизвестная причина", 1, 20, "USD"),
                (1, "AFTER", "FBP", "2026-08-10T16:00:00Z", "已签收", None, 1, 40, "USD"),
                (2, "OTHER", "FBP", "2026-08-10T00:00:00Z", "已签收", None, 1, 50, "CNY")])
            connection.executemany("""INSERT INTO order_items(shop_id,channel,posting_number,sku,
              offer_id,product_name_raw,quantity,unit_price,price_currency,source)
              VALUES(?,?,?,?,?,?,?,?,?,'api')""", [
                (1, "FBP", "BEFORE", "OLD", "OLD-OFFER", "旧商品", 1, 10, "USD"),
                (1, "FBP", "MULTI", "SKU-A", "OFFER-X", "商品甲", 1, 10, "USD"),
                (1, "FBP", "MULTI", "SKU-B", "OFFER-Y", "商品乙", 2, 10, "USD"),
                (1, "realFBS", "FALLBACK", "SKU-C", "OTHER-OFFER", "俄语回退商品", 1, 20, "USD"),
                (1, "FBP", "AFTER", "NEW", "NEW-OFFER", "新商品", 1, 40, "USD"),
                (2, "FBP", "OTHER", "SHOP2", "SHOP2-OFFER", "二店商品", 1, 50, "CNY")])

    def tearDown(self):
        self.temp.cleanup()

    def test_beijing_range_combines_shop_channel_offer_and_keeps_pre_cancel(self):
        data = orders(1, "FBP", "OFFER-X", 1, 30, "2026-08-10", "2026-08-10")
        self.assertEqual(data["total"], 1)
        order = data["items"][0]
        self.assertEqual(order["posting_number"], "MULTI")
        self.assertEqual((order["sku_types"], order["pieces"]), (2, 3))
        self.assertEqual(order["status_raw"], "已取消")
        self.assertEqual(order["cancel_reason_raw"], "买家取消订单")
        self.assertFalse(order["shipped"])

    def test_end_boundary_translation_fallback_and_validation(self):
        data = orders(1, "realFBS", "俄语回退", 1, 30, "2026-08-10", "2026-08-10")
        self.assertEqual([row["posting_number"] for row in data["items"]], ["FALLBACK"])
        self.assertEqual(data["items"][0]["status_raw"], "等待登记")
        self.assertEqual(data["items"][0]["cancel_reason_raw"], "Неизвестная причина")
        self.assertEqual(orders(1, "FBP", "", 1, 30, "2026-08-10", "2026-08-10")["total"], 1)
        with self.assertRaises(HTTPException):
            orders(1, "FBP", "", 1, 30, "2026-08-11", "2026-08-10")
        with self.assertRaises(HTTPException):
            orders(1, "UNKNOWN", "", 1, 30, "2026-08-10", "2026-08-10")


    def test_status_filtering_and_counts(self):
        data = orders(1, "", "", 1, 30, "2026-08-10", "2026-08-10")
        self.assertEqual(data["total"], 2)
        self.assertIn("status_counts", data)
        self.assertEqual(data["status_counts"]["cancelled"], 1)

        cancelled = orders(1, "", "", 1, 30, "2026-08-10", "2026-08-10", status="cancelled")
        self.assertEqual(cancelled["total"], 1)
        self.assertEqual(cancelled["items"][0]["posting_number"], "MULTI")


if __name__ == "__main__":
    unittest.main()
