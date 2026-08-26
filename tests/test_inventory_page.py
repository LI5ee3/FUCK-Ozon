import unittest
from datetime import datetime, timedelta, timezone

from app import db
from app.main import stock
from tests.support import (DatabaseTestCase, add_item, add_order,
                           add_stock_snapshot)


class InventoryPageTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        now = datetime.now(timezone.utc)
        with db.transaction() as connection:
            connection.execute("UPDATE shops SET name='一店' WHERE id=1")
            connection.execute("UPDATE shops SET name='二店' WHERE id=2")
            self._order(connection, 1, "R7", "realFBS", "S-R", "O-R", "原始手表", 14, now - timedelta(days=1))
            self._order(connection, 1, "R15", "realFBS", "S-R", "O-R", "原始手表", 16, now - timedelta(days=10))
            self._order(connection, 1, "R30", "realFBS", "S-R", "O-R", "原始手表", 30, now - timedelta(days=20))
            self._order(connection, 1, "WHD", "WHD", "S-W", "O-W", "仓库商品", 50, now - timedelta(days=1))
            self._order(connection, 1, "CANCEL", "FBP", "S-C", "O-C", "取消商品", 9,
                        now - timedelta(days=1), status="已取消", shipped=0)
            self._order(connection, 1, "M-F", "FBP", "S-M", "O-M", "混合商品", 10, now - timedelta(days=1))
            self._order(connection, 1, "M-R", "realFBS", "S-M", "O-M", "混合商品", 4, now - timedelta(days=8))
            self._order(connection, 1, "M-W", "WHD", "S-M", "O-M", "混合商品", 100, now - timedelta(days=1))
            self._order(connection, 2, "OTHER", "FBP", "S-M", "O-2", "另一店商品", 3, now - timedelta(days=1))
            connection.execute("INSERT INTO product_short_names VALUES('sku','S-R','SKU短名','now')")
            self._snapshot(connection, 1, "S-R", "O-R", [("rfbs", 5, 1)], now)
            self._snapshot(connection, 1, "S-W", "O-W", [("fbo", 20, 0)], now)
            self._snapshot(connection, 1, "S-C", "O-C", [("fbp", 0, 0)], now)
            self._snapshot(connection, 1, "S-M", "O-M", [("fbp", 10, 2), ("rfbs", 500, 0), ("fbo", 800, 0)], now)
            self._snapshot(connection, 2, "S-M", "O-2", [("fbp", 30, 0)], now)

    @staticmethod
    def _order(connection, shop, posting, channel, sku, offer, name, quantity, created,
               status="已签收", shipped=1):
        add_order(connection, shop, posting, channel, created.isoformat(), status, shipped)
        add_item(connection, shop, posting, channel, sku, quantity,
                 offer_id=offer, product_name_raw=name)

    @staticmethod
    def _snapshot(connection, shop, sku, offer, values, observed):
        payload = {"offer_id": offer, "stocks": [
            {"sku": sku, "type": channel, "present": present, "reserved": reserved}
            for channel, present, reserved in values]}
        add_stock_snapshot(connection, shop, sku, observed.isoformat(), payload)

    def test_sales_windows_channels_forecast_and_shop_isolation(self):
        data = stock(1, size=100)
        items = {item["sku"]: item for item in data["items"]}
        real_only = items["S-R"]
        self.assertEqual((real_only["sales_7"], real_only["sales_15"], real_only["sales_30"]),
                         (14, 30, 60))
        self.assertEqual(real_only["daily_sales"], 2)
        self.assertEqual((real_only["fbp_present"], real_only["days_available"],
                          real_only["replenishment"]), (0, 0, 120))
        self.assertEqual(real_only["risk_status"], "FBP无库存，建议备货")
        self.assertEqual(real_only["display_name"], "SKU短名")
        self.assertEqual(items["S-W"]["daily_sales"], 0)
        self.assertIsNone(items["S-W"]["replenishment"])
        self.assertEqual(items["S-C"]["daily_sales"], 0)
        mixed = items["S-M"]
        self.assertEqual((mixed["sales_7"], mixed["sales_15"], mixed["sales_30"]), (10, 14, 14))
        self.assertEqual(mixed["fbp_present"], 10)
        self.assertNotEqual(mixed["replenishment"], 0)
        self.assertEqual([item["shop_id"] for item in data["items"]], [1] * len(data["items"]))
        self.assertEqual(stock(2, size=100)["items"][0]["shop_name"], "二店")

    def test_filters_are_independent_and_run_before_paging(self):
        self.assertEqual(stock(1, size=1, sku="S-R")["total"], 1)
        self.assertEqual(stock(1, size=1, offer_id="O-R")["items"][0]["sku"], "S-R")
        self.assertEqual(stock(1, product_name="原始手表")["total"], 1)
        self.assertEqual(stock(1, product_name="SKU短名")["total"], 1)
        self.assertEqual(stock(1, product_name="货号短名")["total"], 0)
        self.assertEqual(stock(1, sku="S-R", offer_id="O-W")["total"], 0)

    def test_replenishment_rounds_up_and_all_risk_states(self):
        now = datetime.now(timezone.utc)
        with db.transaction() as connection:
            for sku, stock_value, quantity in (("LOW", 1, 1), ("WARN", 150, 30), ("SAFE", 100, 1)):
                self._order(connection, 1, f"P-{sku}", "FBP", sku, f"O-{sku}", sku, quantity,
                            now - timedelta(days=1))
                self._snapshot(connection, 1, sku, f"O-{sku}", [("fbp", stock_value, 0)], now)
        items = {item["sku"]: item for item in stock(1, size=100)["items"]}
        self.assertEqual(items["LOW"]["risk_status"], "预计到货前缺货")
        self.assertEqual(items["WARN"]["risk_status"], "建议FBP备货")
        self.assertEqual(items["SAFE"]["risk_status"], "暂不需要FBP备货")
        self.assertIsInstance(items["LOW"]["replenishment"], int)

    def test_numeric_sorting_happens_before_paging(self):
        self.assertEqual(stock(1, size=1, sort_by="fbp")["items"][0]["sku"], "S-M")
        self.assertEqual(stock(1, size=1, sort_by="realfbs")["items"][0]["sku"], "S-M")
        self.assertEqual(stock(1, size=1, sort_by="whd")["items"][0]["sku"], "S-M")
        self.assertEqual(stock(1, size=1, sort_by="forecast")["items"][0]["sku"], "S-R")
        self.assertEqual(stock(1, size=1, sort_by="replenishment")["items"][0]["sku"], "S-R")
        self.assertEqual(stock(1, size=1, sort_by="fbp", sort_order="asc")["items"][0]["fbp_present"], 0)
