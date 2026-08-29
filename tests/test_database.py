import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from app import db
from app.db import DEFAULT_DAILY_TEMPLATE
from tests.support import DatabaseTestCase


class DatabaseSchemaTest(DatabaseTestCase):
    def test_empty_database_has_only_current_schema_and_defaults(self):
        with db.connect() as connection:
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
            shops = [tuple(row) for row in connection.execute("SELECT * FROM shops ORDER BY id")]
            settings = tuple(connection.execute("SELECT * FROM notification_settings").fetchone())
            auto = connection.execute("SELECT COUNT(*) FROM shop_auto_sync_settings").fetchone()[0]
            item_pk = [row[1] for row in sorted(
                connection.execute("PRAGMA table_info(order_items)"), key=lambda row: row[5]) if row[5]]
        self.assertIn("idx_auto_sync_once", indexes)
        self.assertEqual(shops, [(1, "店铺1", "USD"), (2, "店铺2", "CNY")])
        self.assertEqual(settings, (1, 0, "09:00", "1,2,3,4,5,6,7", DEFAULT_DAILY_TEMPLATE))
        self.assertEqual(auto, 10)
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
        self.assertEqual(after[0], 6)

    def test_nonempty_old_database_is_rejected(self):
        old_path = Path(self.temp.name) / "old.db"
        connection = sqlite3.connect(old_path)
        connection.execute("CREATE TABLE old_data(value TEXT)")
        connection.commit()
        connection.close()
        db.DB_PATH = old_path
        with self.assertRaisesRegex(RuntimeError, "重建数据库"):
            db.init_db()
        with closing(sqlite3.connect(old_path)) as connection:
            self.assertEqual(connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchone()[0], "old_data")

    def test_v1_database_migrates_without_rebuilding_existing_data(self):
        with db.transaction() as connection:
            connection.execute("""INSERT INTO orders(
              shop_id,posting_number,channel,status_raw,shipped,source)
              VALUES(1,'MIGRATION-1','realFBS','运输中',1,'test')""")
            connection.execute("DROP TABLE ozon_webhook_events")
            connection.execute("PRAGMA user_version=1")

        db.init_db()
        with db.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 6)
            self.assertEqual(connection.execute(
                "SELECT status_raw FROM orders WHERE posting_number='MIGRATION-1'").fetchone()[0], "运输中")
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ozon_webhook_events'").fetchone())
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ad_campaigns'").fetchone())
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ad_campaign_daily'").fetchone())
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ad_sku_daily'").fetchone())
