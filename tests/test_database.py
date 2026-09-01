import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from app import db
from app.db import DEFAULT_DAILY_TEMPLATE
from app.migrations import SCHEMA_VERSION, init_db
from tests.support import DatabaseTestCase


class DatabaseSchemaTest(DatabaseTestCase):
    def test_empty_database_has_only_current_schema_and_defaults(self):
        with db.connect() as connection:
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
            shops = [tuple(row) for row in connection.execute("SELECT * FROM shops ORDER BY id")]
            settings = tuple(connection.execute("SELECT * FROM notification_settings").fetchone())
            auto = connection.execute("SELECT COUNT(*) FROM shop_auto_sync_settings").fetchone()[0]
            finance_setting = connection.execute(
                "SELECT 1 FROM shop_auto_sync_settings WHERE shop_id=1 AND module='finance_transactions'").fetchone()
            finance_columns = [row[1] for row in connection.execute(
                "PRAGMA table_info(ozon_finance_transactions)")]
            exchange_info = {row[1]: row for row in connection.execute("PRAGMA table_info(exchange_rates)")}
            item_pk = [row[1] for row in sorted(
                connection.execute("PRAGMA table_info(order_items)"), key=lambda row: row[5]) if row[5]]
        self.assertIn("idx_auto_sync_once", indexes)
        self.assertIn("idx_sync_one_running", indexes)
        self.assertEqual(shops, [(1, "店铺1", "USD"), (2, "店铺2", "CNY")])
        self.assertEqual(settings, (1, 0, "09:00", "1,2,3,4,5,6,7", DEFAULT_DAILY_TEMPLATE))
        self.assertEqual(auto, 12)
        self.assertIsNotNone(finance_setting)
        self.assertEqual(finance_columns, [
            "shop_id", "operation_id", "operation_type", "operation_type_name", "transaction_type",
            "operation_date", "posting_number", "order_date", "delivery_schema", "warehouse_id",
            "amount", "accruals_for_sale", "sale_commission", "delivery_charge",
            "return_delivery_charge", "currency", "payload_json", "fetched_at",
        ])
        self.assertTrue({"service_penalty_exchange_rate", "sales_exchange_rate"} <= set(exchange_info))
        self.assertEqual(exchange_info["service_penalty_exchange_rate"][3], 1)
        self.assertEqual(exchange_info["sales_exchange_rate"][3], 0)
        self.assertNotIn("base_rate", exchange_info)
        self.assertNotIn("rate_with_adjustment", exchange_info)
        self.assertEqual(item_pk, ["shop_id", "posting_number", "sku"])

    def test_repeated_init_keeps_version_and_schema(self):
        with db.connect() as connection:
            before = (connection.execute("PRAGMA user_version").fetchone()[0],
                      connection.execute("SELECT group_concat(sql,'\n') FROM sqlite_master").fetchone()[0])
        init_db()
        with db.connect() as connection:
            after = (connection.execute("PRAGMA user_version").fetchone()[0],
                      connection.execute("SELECT group_concat(sql,'\n') FROM sqlite_master").fetchone()[0])
        self.assertEqual(before, after)
        self.assertEqual(after[0], SCHEMA_VERSION)

    def test_nonempty_old_database_is_rejected(self):
        old_path = Path(self.temp.name) / "old.db"
        connection = sqlite3.connect(old_path)
        connection.execute("CREATE TABLE old_data(value TEXT)")
        connection.commit()
        connection.close()
        db.DB_PATH = old_path
        with self.assertRaisesRegex(RuntimeError, "重建数据库"):
            init_db()
        with closing(sqlite3.connect(old_path)) as connection:
            self.assertEqual(connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchone()[0], "old_data")

    def test_v1_database_migrates_without_rebuilding_existing_data(self):
        with db.transaction() as connection:
            connection.execute("ALTER TABLE exchange_rates RENAME COLUMN service_penalty_exchange_rate TO base_rate")
            connection.execute("ALTER TABLE exchange_rates RENAME COLUMN sales_exchange_rate TO rate_with_adjustment")
            connection.execute("""INSERT INTO orders(
              shop_id,posting_number,channel,status_raw,shipped,source)
              VALUES(1,'MIGRATION-1','realFBS','运输中',1,'test')""")
            connection.execute("DROP TABLE ozon_webhook_events")
            connection.execute("PRAGMA user_version=1")

        init_db()
        with db.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
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
            for table in ("ozon_finance_transactions", "ozon_finance_transaction_items",
                          "ozon_finance_transaction_services", "ozon_finance_reconciliations"):
                self.assertIsNotNone(connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())

    def test_v10_database_migrates_finance_tables_and_module_without_losing_orders(self):
        with db.transaction() as connection:
            connection.execute("""INSERT INTO orders(
              shop_id,posting_number,channel,status_raw,shipped,source)
              VALUES(1,'V10-ORDER','realFBS','运输中',1,'test')""")
            connection.execute("DELETE FROM shop_auto_sync_settings WHERE module='finance_transactions'")
            connection.execute("DROP TABLE ozon_finance_transaction_items")
            connection.execute("DROP TABLE ozon_finance_transaction_services")
            connection.execute("DROP TABLE ozon_finance_reconciliations")
            connection.execute("DROP TABLE ozon_finance_transactions")
            connection.execute("PRAGMA user_version=10")

        init_db()
        with db.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            order = connection.execute(
                "SELECT posting_number FROM orders WHERE posting_number='V10-ORDER'").fetchone()
            finance_setting = connection.execute("""SELECT enabled,interval_hours,range_days
              FROM shop_auto_sync_settings WHERE shop_id=1 AND module='finance_transactions'""").fetchone()
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ozon_finance_%'")}
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertEqual(order[0], "V10-ORDER")
        self.assertEqual(tuple(finance_setting), (0, 24, 31))
        self.assertEqual(tables, {"ozon_finance_transactions", "ozon_finance_transaction_items",
                                  "ozon_finance_transaction_services", "ozon_finance_reconciliations"})

    def test_v6_migration_keeps_duplicate_running_history_and_adds_unique_index(self):
        with db.transaction() as connection:
            connection.execute("ALTER TABLE exchange_rates RENAME COLUMN service_penalty_exchange_rate TO base_rate")
            connection.execute("ALTER TABLE exchange_rates RENAME COLUMN sales_exchange_rate TO rate_with_adjustment")
            connection.execute("DROP INDEX idx_sync_one_running")
            connection.execute("INSERT INTO sync_runs(shop_id,module,status) VALUES(1,'orders','running')")
            connection.execute("INSERT INTO sync_runs(shop_id,module,status) VALUES(1,'orders','running')")
            connection.execute("PRAGMA user_version=6")
        init_db()
        with db.connect() as connection:
            rows = connection.execute("SELECT status,error FROM sync_runs ORDER BY id").fetchall()
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual([row["status"] for row in rows], ["failed", "running"])
        self.assertIn("数据库升级", rows[0]["error"])
        self.assertEqual(version, SCHEMA_VERSION)

    def test_v8_exchange_rate_migration_preserves_missing_sales_rate(self):
        with db.transaction() as connection:
            connection.execute("ALTER TABLE exchange_rates RENAME COLUMN service_penalty_exchange_rate TO base_rate")
            connection.execute("ALTER TABLE exchange_rates RENAME COLUMN sales_exchange_rate TO rate_with_adjustment")
            connection.execute("""INSERT INTO exchange_rates VALUES(
              'USD','RUB','2026-08-21T21:00:00Z','2026-08-22T21:00:00Z','90',NULL,
              'ozon_xapi','2026-08-22T22:00:00Z')""")
            connection.execute("PRAGMA user_version=8")

        init_db()
        with db.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            columns = {row[1] for row in connection.execute("PRAGMA table_info(exchange_rates)")}
            row = connection.execute("""SELECT service_penalty_exchange_rate,sales_exchange_rate
              FROM exchange_rates WHERE from_currency='USD'""").fetchone()
        self.assertEqual((SCHEMA_VERSION, version), (11, 11))
        self.assertEqual(tuple(row), ("90", None))
        self.assertNotIn("base_rate", columns)
        self.assertNotIn("rate_with_adjustment", columns)

        with db.connect() as connection:
            sales_info = next(row for row in connection.execute("PRAGMA table_info(exchange_rates)")
                              if row[1] == "sales_exchange_rate")
        self.assertEqual(sales_info[3], 0)

    def test_v9_not_null_exchange_rate_migration_rebuilds_nullable_column(self):
        with db.transaction() as connection:
            connection.execute("""CREATE TABLE exchange_rates_v9 (
              from_currency TEXT NOT NULL CHECK(from_currency IN ('USD','CNY')),
              to_currency TEXT NOT NULL CHECK(to_currency='RUB'), valid_from_utc TEXT NOT NULL,
              valid_to_utc TEXT NOT NULL, service_penalty_exchange_rate TEXT NOT NULL,
              sales_exchange_rate TEXT NOT NULL,
              source TEXT NOT NULL DEFAULT 'ozon_xapi' CHECK(source='ozon_xapi'), fetched_at TEXT NOT NULL,
              PRIMARY KEY(from_currency,to_currency,valid_from_utc,valid_to_utc));""")
            connection.execute("""INSERT INTO exchange_rates_v9(
              from_currency,to_currency,valid_from_utc,valid_to_utc,
              service_penalty_exchange_rate,sales_exchange_rate,source,fetched_at)
              SELECT from_currency,to_currency,valid_from_utc,valid_to_utc,
                service_penalty_exchange_rate,sales_exchange_rate,source,fetched_at
              FROM exchange_rates""")
            connection.execute("DROP TABLE exchange_rates")
            connection.execute("ALTER TABLE exchange_rates_v9 RENAME TO exchange_rates")
            connection.execute("""INSERT INTO exchange_rates VALUES(
              'USD','RUB','2026-08-21T21:00:00Z','2026-08-22T21:00:00Z','90','88',
              'ozon_xapi','2026-08-22T22:00:00Z')""")
            connection.execute("PRAGMA user_version=9")

        init_db()
        with db.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            sales_info = next(row for row in connection.execute("PRAGMA table_info(exchange_rates)")
                              if row[1] == "sales_exchange_rate")
            row = connection.execute("""SELECT service_penalty_exchange_rate,sales_exchange_rate
              FROM exchange_rates WHERE from_currency='USD'""").fetchone()
        self.assertEqual((SCHEMA_VERSION, version), (11, 11))
        self.assertEqual(tuple(row), ("90", "88"))
        self.assertEqual(sales_info[3], 0)
