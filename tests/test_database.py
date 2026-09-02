import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from app import db
from app.db import DEFAULT_DAILY_TEMPLATE
from app.migrations import SCHEMA_VERSION, _create_product_forecast_costs, init_db
from tests.support import DatabaseTestCase


class DatabaseSchemaTest(DatabaseTestCase):
    def test_empty_database_has_only_current_schema_and_defaults(self):
        with db.connect() as connection:
            schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
            shops = [tuple(row) for row in connection.execute("SELECT * FROM shops ORDER BY id")]
            settings = tuple(connection.execute("SELECT * FROM notification_settings").fetchone())
            auto = connection.execute("SELECT COUNT(*) FROM shop_auto_sync_settings").fetchone()[0]
            finance_setting = connection.execute(
                "SELECT 1 FROM shop_auto_sync_settings WHERE shop_id=1 AND module='finance_transactions'").fetchone()
            price_settings = {tuple(row) for row in connection.execute(
                "SELECT shop_id,enabled,interval_hours,range_days FROM shop_auto_sync_settings WHERE module='prices'"
            )}
            finance_columns = [row[1] for row in connection.execute(
                "PRAGMA table_info(ozon_finance_transactions)")]
            price_columns = [row[1] for row in connection.execute(
                "PRAGMA table_info(product_price_snapshots)")]
            exchange_info = {row[1]: row for row in connection.execute("PRAGMA table_info(exchange_rates)")}
            item_pk = [row[1] for row in sorted(
                connection.execute("PRAGMA table_info(order_items)"), key=lambda row: row[5]) if row[5]]
        self.assertEqual(SCHEMA_VERSION, 14)
        self.assertEqual(schema_version, SCHEMA_VERSION)
        self.assertNotIn("product_forecast_costs", tables)
        self.assertNotIn("product_forecast_cost_history", tables)
        self.assertNotIn("idx_product_forecast_cost_history_identity_time", indexes)
        self.assertIn("idx_auto_sync_once", indexes)
        self.assertIn("idx_sync_one_running", indexes)
        self.assertIn("product_price_snapshots", tables)
        self.assertIn("idx_product_price_snapshots_product_time", indexes)
        self.assertIn("idx_product_price_snapshots_offer_time", indexes)
        self.assertEqual(price_columns, [
            "shop_id", "product_id", "offer_id", "observed_at", "currency", "price", "old_price",
            "min_price", "marketing_seller_price", "auto_action_enabled", "acquiring", "price_index_color",
            "ozon_min_price", "ozon_price_index", "external_min_price", "external_price_index",
            "self_marketplace_min_price", "self_marketplace_price_index", "commissions_json",
            "marketing_actions_json", "price_indexes_json", "payload_json", "snapshot_key",
        ])
        self.assertEqual(shops, [(1, "店铺1", "USD"), (2, "店铺2", "CNY")])
        self.assertEqual(settings, (1, 0, "09:00", "1,2,3,4,5,6,7", DEFAULT_DAILY_TEMPLATE))
        self.assertEqual(auto, 14)
        self.assertIsNotNone(finance_setting)
        self.assertEqual(price_settings, {(1, 0, 24, 1), (2, 0, 24, 1)})
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

    def test_empty_database_has_erp_cost_fact_tables(self):
        with db.connect() as connection:
            batch_columns = [row[1] for row in connection.execute(
                "PRAGMA table_info(erp_cost_import_batches)")]
            cost_columns = [row[1] for row in connection.execute(
                "PRAGMA table_info(erp_order_item_costs)")]
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_erp_%'")}
        self.assertEqual(batch_columns, [
            "id", "shop_id", "filename", "row_count", "parsed_count", "inserted_count",
            "updated_count", "unchanged_count", "imported_at",
        ])
        self.assertEqual(cost_columns, [
            "shop_id", "erp_order_number", "ozon_sku", "offer_id", "quantity", "unit_cost",
            "exchange_rate_original", "total_cost", "platform_link", "source_batch_id",
            "source_row_no", "raw_payload_json", "imported_at", "updated_at",
        ])
        self.assertEqual(indexes, {
            "idx_erp_order_item_costs_order", "idx_erp_order_item_costs_sku",
            "idx_erp_order_item_costs_offer",
        })

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
            connection.execute("DELETE FROM shop_auto_sync_settings WHERE module='prices'")
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
            connection.execute("DELETE FROM shop_auto_sync_settings WHERE module='prices'")
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

    def test_v7_database_migrates_forecast_tables_then_removes_them(self):
        with db.transaction() as connection:
            connection.execute("DELETE FROM shop_auto_sync_settings WHERE module='prices'")
            connection.execute("ALTER TABLE exchange_rates RENAME COLUMN service_penalty_exchange_rate TO base_rate")
            connection.execute("ALTER TABLE exchange_rates RENAME COLUMN sales_exchange_rate TO rate_with_adjustment")
            connection.execute("""INSERT INTO orders(
              shop_id,posting_number,channel,status_raw,shipped,source)
              VALUES(1,'V7-ORDER','realFBS','运输中',1,'test')""")
            connection.execute("PRAGMA user_version=7")

        init_db()
        with db.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
            order = connection.execute(
                "SELECT status_raw FROM orders WHERE posting_number='V7-ORDER'").fetchone()
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertEqual(order[0], "运输中")
        self.assertNotIn("product_forecast_costs", tables)
        self.assertNotIn("product_forecast_cost_history", tables)
        self.assertNotIn("idx_product_forecast_cost_history_identity_time", indexes)

    def test_v11_database_migrates_erp_cost_tables_without_losing_existing_facts(self):
        with db.transaction() as connection:
            _create_product_forecast_costs(connection)
            connection.execute("""INSERT INTO orders(
              shop_id,posting_number,channel,status_raw,shipped,source)
              VALUES(1,'V11-ORDER','realFBS','运输中',1,'test')""")
            connection.execute("""INSERT INTO order_items(
              shop_id,channel,posting_number,sku,quantity,source)
              VALUES(1,'realFBS','V11-ORDER','V11-SKU',2,'test')""")
            connection.execute("""INSERT INTO ozon_finance_transactions(
              shop_id,operation_id,operation_type,operation_date,amount,
              accruals_for_sale,sale_commission,delivery_charge,return_delivery_charge,
              currency,payload_json,fetched_at)
              VALUES(1,'V11-OP','Operation','2026-08-31',10,10,0,0,0,'USD','{}','2026-08-31T00:00:00Z')""")
            connection.execute("""INSERT INTO product_forecast_costs(
              product_identity,purchase_cost,purchase_currency,created_at,updated_at)
              VALUES('V11-PRODUCT',10,'USD','2026-08-31T00:00:00Z','2026-08-31T00:00:00Z')""")
            connection.execute("DROP TABLE erp_order_item_costs")
            connection.execute("DROP TABLE erp_cost_import_batches")
            connection.execute("PRAGMA user_version=11")

        init_db()
        with db.connect() as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            counts = tuple(connection.execute("""
              SELECT (SELECT COUNT(*) FROM orders), (SELECT COUNT(*) FROM order_items),
                     (SELECT COUNT(*) FROM ozon_finance_transactions)
            """).fetchone())
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertTrue({"erp_cost_import_batches", "erp_order_item_costs"} <= tables)
        self.assertNotIn("product_forecast_costs", tables)
        self.assertNotIn("product_forecast_cost_history", tables)
        self.assertEqual(counts, (1, 1, 1))

    def test_v12_database_migration_removes_only_forecast_tables(self):
        with db.transaction() as connection:
            _create_product_forecast_costs(connection)
            connection.execute("""INSERT INTO product_forecast_costs(
              product_identity,purchase_cost,purchase_currency,created_at,updated_at)
              VALUES('V12-PRODUCT',10,'USD','2026-08-31T00:00:00Z','2026-08-31T00:00:00Z')""")
            connection.execute("""INSERT INTO product_forecast_cost_history(
              product_identity,purchase_cost,purchase_currency,recorded_at)
              VALUES('V12-PRODUCT',10,'USD','2026-08-31T00:00:00Z')""")
            connection.execute("""INSERT INTO orders(
              shop_id,posting_number,channel,status_raw,shipped,source)
              VALUES(1,'V12-ORDER','realFBS','运输中',1,'test')""")
            connection.execute("""INSERT INTO order_items(
              shop_id,channel,posting_number,sku,quantity,source)
              VALUES(1,'realFBS','V12-ORDER','V12-SKU',1,'test')""")
            connection.execute("""INSERT INTO ozon_finance_transactions(
              shop_id,operation_id,operation_type,operation_date,amount,
              accruals_for_sale,sale_commission,delivery_charge,return_delivery_charge,
              currency,payload_json,fetched_at)
              VALUES(1,'V12-OP','Operation','2026-08-31',10,10,0,0,0,'USD','{}','2026-08-31T00:00:00Z')""")
            batch_id = connection.execute("""INSERT INTO erp_cost_import_batches(
              shop_id,filename,row_count,parsed_count,inserted_count,updated_count,
              unchanged_count,imported_at)
              VALUES(1,'v12.xlsx',1,1,1,0,0,'2026-08-31T00:00:00Z')""").lastrowid
            connection.execute("""INSERT INTO erp_order_item_costs(
              shop_id,erp_order_number,ozon_sku,quantity,unit_cost,total_cost,
              source_batch_id,source_row_no,raw_payload_json,imported_at,updated_at)
              VALUES(1,'V12-ERP','V12-SKU',1,'10','10',?,?, '{}',
                     '2026-08-31T00:00:00Z','2026-08-31T00:00:00Z')""", (batch_id, 2))
            connection.execute("PRAGMA user_version=12")

        init_db()
        with db.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
            counts = tuple(connection.execute("""
              SELECT (SELECT COUNT(*) FROM orders WHERE posting_number='V12-ORDER'),
                     (SELECT COUNT(*) FROM order_items WHERE posting_number='V12-ORDER'),
                     (SELECT COUNT(*) FROM ozon_finance_transactions WHERE operation_id='V12-OP'),
                     (SELECT COUNT(*) FROM erp_cost_import_batches WHERE filename='v12.xlsx'),
                     (SELECT COUNT(*) FROM erp_order_item_costs WHERE erp_order_number='V12-ERP')
            """).fetchone())
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertNotIn("product_forecast_costs", tables)
        self.assertNotIn("product_forecast_cost_history", tables)
        self.assertNotIn("idx_product_forecast_cost_history_identity_time", indexes)
        self.assertTrue({"erp_cost_import_batches", "erp_order_item_costs",
                         "ozon_finance_transactions"} <= tables)
        self.assertEqual(counts, (1, 1, 1, 1, 1))

    def test_v13_database_migration_adds_price_snapshots_and_preserves_settings(self):
        with db.transaction() as connection:
            connection.execute("""UPDATE shop_auto_sync_settings
              SET enabled=1,interval_hours=6,range_days=9
              WHERE shop_id=1 AND module='orders'""")
            connection.execute("ALTER TABLE shop_auto_sync_settings RENAME TO shop_auto_sync_settings_v13_test")
            connection.execute("""CREATE TABLE shop_auto_sync_settings (
              shop_id INTEGER NOT NULL REFERENCES shops(id),
              module TEXT NOT NULL CHECK(module IN (
                'orders','returns','stock','ad_campaign_daily','ad_sku_daily','finance_transactions')),
              enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
              interval_hours INTEGER NOT NULL DEFAULT 24 CHECK(interval_hours IN (1,2,3,4,6,8,12,24)),
              range_days INTEGER NOT NULL CHECK(range_days BETWEEN 1 AND 365), PRIMARY KEY(shop_id,module))""")
            connection.execute("""INSERT INTO shop_auto_sync_settings(shop_id,module,enabled,interval_hours,range_days)
              SELECT shop_id,module,enabled,interval_hours,range_days
              FROM shop_auto_sync_settings_v13_test WHERE module!='prices'""")
            connection.execute("DROP TABLE shop_auto_sync_settings_v13_test")
            connection.execute("DROP TABLE product_price_snapshots")
            connection.execute("PRAGMA user_version=13")

        init_db()
        with db.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            prices = [tuple(row) for row in connection.execute(
                "SELECT shop_id,enabled,interval_hours,range_days FROM shop_auto_sync_settings WHERE module='prices'"
            )]
            orders = tuple(connection.execute(
                "SELECT enabled,interval_hours,range_days FROM shop_auto_sync_settings "
                "WHERE shop_id=1 AND module='orders'"
            ).fetchone())
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_product_price_snapshots_%'"
            )}
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='product_price_snapshots'"
            ).fetchone()
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertEqual(orders, (1, 6, 9))
        self.assertEqual(prices, [(1, 0, 24, 1), (2, 0, 24, 1)])
        self.assertEqual(indexes, {
            "idx_product_price_snapshots_product_time", "idx_product_price_snapshots_offer_time",
        })
        self.assertIsNotNone(table)

    def test_v6_migration_keeps_duplicate_running_history_and_adds_unique_index(self):
        with db.transaction() as connection:
            connection.execute("DELETE FROM shop_auto_sync_settings WHERE module='prices'")
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
            connection.execute("DELETE FROM shop_auto_sync_settings WHERE module='prices'")
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
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            indexes = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertEqual(tuple(row), ("90", None))
        self.assertNotIn("base_rate", columns)
        self.assertNotIn("rate_with_adjustment", columns)
        self.assertNotIn("product_forecast_costs", tables)
        self.assertNotIn("product_forecast_cost_history", tables)
        self.assertNotIn("idx_product_forecast_cost_history_identity_time", indexes)

        with db.connect() as connection:
            sales_info = next(row for row in connection.execute("PRAGMA table_info(exchange_rates)")
                              if row[1] == "sales_exchange_rate")
        self.assertEqual(sales_info[3], 0)

    def test_v9_not_null_exchange_rate_migration_rebuilds_nullable_column(self):
        with db.transaction() as connection:
            connection.execute("DELETE FROM shop_auto_sync_settings WHERE module='prices'")
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
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertEqual(tuple(row), ("90", "88"))
        self.assertEqual(sales_info[3], 0)
