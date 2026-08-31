import asyncio
import unittest

from fastapi import HTTPException

from app import db
from app.migrations import SCHEMA_VERSION, init_db
from app.product_costs import (list_product_forecast_cost_history, list_product_forecast_costs,
                               save_product_forecast_cost)
from app.routers.product_costs import product_cost_history
from app.routers.products import save_product_rule
from tests.support import DatabaseTestCase, MockRequest, add_item, add_order


class ProductForecastCostsTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        with db.transaction() as connection:
            self._add_product(connection, "P-1", "SKU-1", "OFFER-1", "蓝牙追踪器")

    @staticmethod
    def _add_product(connection, posting, sku, offer_id, name):
        add_order(connection, 1, posting, "FBP", "2026-08-01T00:00:00Z", "已签收", 1)
        add_item(connection, 1, posting, "FBP", sku, offer_id=offer_id, product_name_raw=name)

    @staticmethod
    def _payload(**changes):
        payload = {
            "sku": "SKU-1", "offer_id": "OFFER-1", "purchase_cost": 10,
            "purchase_currency": "USD", "weight_grams": 100, "length_cm": 10,
            "width_cm": 5, "height_cm": 3, "packing_cost_cny": 2,
            "other_cost_cny": 1, "note": "初始参数", "change_note": "新报价",
        }
        payload.update(changes)
        return payload

    def test_fresh_schema_has_forecast_tables_and_no_actual_cost_fields(self):
        with db.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            current_columns = {row[1] for row in connection.execute(
                "PRAGMA table_info(product_forecast_costs)")}
            history_columns = {row[1] for row in connection.execute(
                "PRAGMA table_info(product_forecast_cost_history)")}
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("product_forecast_costs", tables)
        self.assertIn("product_forecast_cost_history", tables)
        self.assertIn("product_identity", current_columns)
        self.assertIn("updated_at", current_columns)
        self.assertIn("change_note", history_columns)
        self.assertIn("recorded_at", history_columns)
        self.assertNotIn("effective_from", history_columns)
        self.assertIn("idx_product_forecast_cost_history_identity_time", indexes)

    def test_v7_migration_preserves_existing_orders(self):
        with db.transaction() as connection:
            connection.execute("DROP TABLE product_forecast_cost_history")
            connection.execute("DROP TABLE product_forecast_costs")
            connection.execute("PRAGMA user_version=7")
        init_db()
        with db.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(connection.execute(
                "SELECT status_raw FROM orders WHERE posting_number='P-1'").fetchone()[0], "已签收")
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='product_forecast_costs'").fetchone())

    def test_first_save_writes_current_and_one_complete_history_snapshot(self):
        result = save_product_forecast_cost(self._payload())
        self.assertEqual((result["created"], result["changed"], result["product_identity"]),
                         (True, True, "SKU-1"))
        with db.connect() as connection:
            current = dict(connection.execute("SELECT * FROM product_forecast_costs").fetchone())
            history = [dict(row) for row in connection.execute(
                "SELECT * FROM product_forecast_cost_history")]
        self.assertEqual(current["purchase_cost"], 10)
        self.assertEqual(current["weight_grams"], 100)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["purchase_cost"], 10)
        self.assertEqual(history[0]["height_cm"], 3)
        self.assertEqual(history[0]["change_note"], "新报价")

    def test_purchase_and_other_business_field_changes_create_revisions(self):
        save_product_forecast_cost(self._payload())
        save_product_forecast_cost(self._payload(purchase_cost=12, change_note="供应商涨价"))
        save_product_forecast_cost(self._payload(weight_grams=120, packing_cost_cny=3, change_note="包材调整"))
        with db.connect() as connection:
            current = dict(connection.execute("SELECT * FROM product_forecast_costs").fetchone())
            history = [dict(row) for row in connection.execute(
                "SELECT * FROM product_forecast_cost_history ORDER BY id")]
        self.assertEqual(current["purchase_cost"], 10)
        self.assertEqual(current["weight_grams"], 120)
        self.assertEqual(current["packing_cost_cny"], 3)
        self.assertEqual(len(history), 3)
        self.assertEqual([row["purchase_cost"] for row in history], [10, 12, 10])
        self.assertEqual(history[0]["weight_grams"], 100)
        self.assertEqual(history[1]["change_note"], "供应商涨价")

    def test_identical_normalized_business_data_does_not_create_revision(self):
        save_product_forecast_cost(self._payload(change_note="第一次"))
        result = save_product_forecast_cost(self._payload(
            purchase_cost="10.00", weight_grams="100", change_note="不同备注"))
        with db.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM product_forecast_cost_history").fetchone()[0]
        self.assertFalse(result["changed"])
        self.assertEqual(count, 1)

    def test_zero_cost_is_preserved(self):
        result = save_product_forecast_cost(self._payload(
            purchase_cost=0, packing_cost_cny=0, other_cost_cny=0, change_note="免费样品"))
        self.assertEqual(result["forecast_cost"]["purchase_cost"], 0)
        self.assertEqual(result["forecast_cost"]["packing_cost_cny"], 0)

    def test_invalid_numbers_currency_and_text_are_rejected(self):
        for field, value in (("purchase_cost", -1), ("weight_grams", -1),
                             ("packing_cost_cny", float("nan")), ("other_cost_cny", float("inf")),
                             ("purchase_cost", True), ("purchase_currency", "RUB"),
                             ("note", 1)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                save_product_forecast_cost(self._payload(**{field: value}))
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM product_forecast_costs").fetchone()[0], 0)

    def test_unknown_product_cannot_create_orphan_cost(self):
        with self.assertRaisesRegex(ValueError, "孤立"):
            save_product_forecast_cost(self._payload(sku="UNKNOWN", offer_id="NO-OFFER"))
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM product_forecast_costs").fetchone()[0], 0)

    def test_canonical_merge_shares_one_current_cost_and_history(self):
        with db.transaction() as connection:
            self._add_product(connection, "P-2", "SKU-2", "OFFER-2", "同款追踪器")
        asyncio.run(save_product_rule(MockRequest({
            "kind": "merge", "primary_offer_id": "OFFER-1", "primary_sku": "SKU-1",
            "members": [{"key_type": "offer_id", "key_value": "OFFER-2"}],
        })))
        save_product_forecast_cost(self._payload(purchase_cost=10))
        second = dict(self._payload(sku="SKU-2", offer_id="OFFER-2", purchase_cost=12,
                                    change_note="统一成本"))
        save_product_forecast_cost(second)
        result = list_product_forecast_costs()
        rows = [row for row in result["items"] if row["product_identity"] == "OFFER-1"]
        with db.connect() as connection:
            current_count = connection.execute("SELECT COUNT(*) FROM product_forecast_costs").fetchone()[0]
            history_count = connection.execute("SELECT COUNT(*) FROM product_forecast_cost_history").fetchone()[0]
        self.assertEqual(current_count, 1)
        self.assertEqual(history_count, 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ozon_skus"], ["SKU-1", "SKU-2"])
        self.assertEqual(rows[0]["offer_ids"], ["OFFER-1", "OFFER-2"])
        self.assertEqual(rows[0]["listings"], [
            {"shop_id": 1, "sku": "SKU-1", "offer_id": "OFFER-1", "offer_ids": ["OFFER-1"]},
            {"shop_id": 1, "sku": "SKU-2", "offer_id": "OFFER-2", "offer_ids": ["OFFER-2"]},
        ])
        self.assertEqual(rows[0]["forecast_cost"]["purchase_cost"], 12)

    def test_conflicting_product_rules_are_not_guessed(self):
        with db.transaction() as connection:
            self._add_product(connection, "P-C", "SKU-C", "OFFER-C", "冲突商品")
            now = "2026-08-31T00:00:00Z"
            group_one = connection.execute(
                "INSERT INTO product_groups(name,created_at,updated_at) VALUES(?,?,?)",
                ("merge:C1", now, now)).lastrowid
            group_two = connection.execute(
                "INSERT INTO product_groups(name,created_at,updated_at) VALUES(?,?,?)",
                ("merge:C2", now, now)).lastrowid
            connection.executemany(
                "INSERT INTO product_group_config(group_id,primary_offer_id,primary_sku,status,note) VALUES(?,?,?,'active','')",
                [(group_one, "OFFER-C", "SKU-C"), (group_two, "OFFER-OTHER", "SKU-OTHER")])
            connection.executemany("INSERT INTO product_group_members VALUES(?,?,?)", [
                (group_one, "sku", "SKU-C"), (group_two, "offer_id", "OFFER-C")])
        rows = [row for row in list_product_forecast_costs()["items"] if "SKU-C" in row["ozon_skus"]]
        self.assertTrue(rows[0]["conflict"])
        self.assertIsNone(rows[0]["product_identity"])
        with self.assertRaisesRegex(ValueError, "冲突"):
            save_product_forecast_cost(self._payload(sku="SKU-C", offer_id="OFFER-C"))

    def test_history_is_descending_and_history_route_is_read_only(self):
        save_product_forecast_cost(self._payload(purchase_cost=10))
        save_product_forecast_cost(self._payload(purchase_cost=11, change_note="修正"))
        history = list_product_forecast_cost_history(sku="SKU-1", offer_id="OFFER-1")
        self.assertEqual([row["purchase_cost"] for row in history["items"]], [11, 10])
        routed = product_cost_history(sku="SKU-1", offer_id="OFFER-1")
        self.assertEqual(routed["items"][0]["change_note"], "修正")
        from app.routers.product_costs import router
        history_routes = [route for route in router.routes if route.path.endswith("/history")]
        self.assertEqual(len(history_routes), 1)
        self.assertEqual(history_routes[0].methods, {"GET"})

    def test_search_and_pagination_cover_sku_offer_name_and_boundaries(self):
        with db.transaction() as connection:
            self._add_product(connection, "P-2", "SKU-2", "OFFER-2", "红色收纳盒")
            self._add_product(connection, "P-3", "SKU-3", "OFFER-3", "蓝色灯具")
        self.assertEqual(list_product_forecast_costs("SKU-2")["items"][0]["ozon_skus"], ["SKU-2"])
        self.assertEqual(list_product_forecast_costs("OFFER-3")["items"][0]["offer_ids"], ["OFFER-3"])
        self.assertEqual(list_product_forecast_costs("收纳盒")["items"][0]["display_name"], "红色收纳盒")
        first = list_product_forecast_costs(page=1, size=2)
        second = list_product_forecast_costs(page=2, size=2)
        beyond = list_product_forecast_costs(page=3, size=2)
        self.assertEqual((first["total"], len(first["items"]), len(second["items"]), beyond["items"]),
                         (3, 2, 1, []))


if __name__ == "__main__":
    unittest.main()
