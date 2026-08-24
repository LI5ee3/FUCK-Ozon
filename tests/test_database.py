import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db
from app.db import DEFAULT_DAILY_TEMPLATE
from app.ozon import _sync_stock_snapshot
from tests.support import DatabaseTestCase


REMOVED = {
    "order_api_records", "order_manual_data", "product_short_name_migrations",
    "finance_records", "finance_reports", "order_after_sales", "order_costs",
    "order_status_history", "warehouse_stocks", "webhook_events", "fbo_stocks",
    "currency_conversions", "exchange_rate_history", "brand_rules", "question_records",
    "analytics_records", "price_snapshots",
}


class DatabaseSchemaTest(DatabaseTestCase):
    def test_empty_database_has_only_current_schema_and_defaults(self):
        with db.connect() as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
            shops = [tuple(row) for row in connection.execute("SELECT * FROM shops ORDER BY id")]
            settings = tuple(connection.execute("SELECT * FROM notification_settings").fetchone())
            auto = connection.execute("SELECT COUNT(*) FROM shop_auto_sync_settings").fetchone()[0]
            item_pk = [row[1] for row in sorted(
                connection.execute("PRAGMA table_info(order_items)"), key=lambda row: row[5]) if row[5]]
        self.assertFalse(tables & REMOVED)
        self.assertNotIn("idx_orders_perf", indexes)
        self.assertNotIn("idx_items_identity", indexes)
        self.assertIn("idx_auto_sync_once", indexes)
        self.assertEqual(shops, [(1, "店铺1", "USD"), (2, "店铺2", "CNY")])
        self.assertEqual(settings, (1, 0, "09:00", "1,2,3,4,5,6,7", DEFAULT_DAILY_TEMPLATE))
        self.assertEqual(auto, 6)
        self.assertEqual(item_pk, ["shop_id", "posting_number", "sku"])

    def test_repeated_init_keeps_version_and_schema(self):
        with db.connect() as connection:
            before = (connection.execute("PRAGMA user_version").fetchone()[0],
                      connection.execute("SELECT group_concat(sql,'\n') FROM sqlite_master").fetchone()[0])
        db.init_db()
        with db.connect() as connection:
            after = (connection.execute("PRAGMA user_version").fetchone()[0],
                     connection.execute("SELECT group_concat(sql,'\n') FROM sqlite_master").fetchone()[0])
        self.assertEqual(before, after)
        self.assertEqual(after[0], 1)

    def test_nonempty_old_database_is_rejected(self):
        old_path = Path(self.temp.name) / "old.db"
        connection = sqlite3.connect(old_path)
        connection.execute("CREATE TABLE old_data(value TEXT)")
        connection.commit()
        connection.close()
        db.DB_PATH = old_path
        with self.assertRaisesRegex(RuntimeError, "重建数据库"):
            db.init_db()
        with sqlite3.connect(old_path) as connection:
            self.assertEqual(connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchone()[0], "old_data")

    def test_stock_sync_upserts_current_snapshot(self):
        with patch("app.ozon._cursor_pages", side_effect=[
            [{"product_id": 1, "stocks": []}], [{"product_id": 1, "offer_id": "NEW", "stocks": []}]
        ]):
            _sync_stock_snapshot(1)
            _sync_stock_snapshot(1)
        with db.connect() as connection:
            count, payload = connection.execute(
                "SELECT COUNT(*),payload FROM stock_snapshots WHERE shop_id=1 AND record_key='1'").fetchone()
        self.assertEqual(count, 1)
        self.assertIn('"offer_id":"NEW"', payload)


if __name__ == "__main__":
    unittest.main()
