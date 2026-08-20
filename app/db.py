import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "fuck-ozon.db"


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA journal_mode=WAL")
    return db


@contextmanager
def transaction():
    db = connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    with transaction() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS shops (
          id INTEGER PRIMARY KEY CHECK(id IN (1,2)),
          name TEXT NOT NULL UNIQUE CHECK(trim(name) <> ''),
          settlement_currency TEXT NOT NULL CHECK(settlement_currency IN ('USD','CNY')),
          seller_id TEXT, push_token TEXT
        );
        INSERT OR IGNORE INTO shops(id,name,settlement_currency) VALUES (1, '店铺1', 'USD'), (2, '店铺2', 'CNY');

        CREATE TABLE IF NOT EXISTS import_batches (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          shop_id INTEGER NOT NULL REFERENCES shops(id),
          kind TEXT NOT NULL, filename TEXT NOT NULL,
          imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          row_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS orders (
          shop_id INTEGER NOT NULL REFERENCES shops(id),
          posting_number TEXT NOT NULL,
          parent_order_no TEXT,
          channel TEXT NOT NULL CHECK(channel IN ('FBP','realFBS','WHD')),
          created_at TEXT, shipped_at TEXT, delivered_at TEXT,
          status_raw TEXT NOT NULL DEFAULT '', cancel_reason_raw TEXT, cancel_reason_id TEXT,
          shipped INTEGER NOT NULL DEFAULT 0 CHECK(shipped IN (0,1)),
          cancelled_after_ship INTEGER CHECK(cancelled_after_ship IN (0,1)),
          data_anomaly INTEGER NOT NULL DEFAULT 0 CHECK(data_anomaly IN (0,1)),
          amount_original REAL, amount_currency TEXT,
          amount_cny REAL, exchange_rate REAL, exchange_source TEXT, exchange_date TEXT,
          buyer_paid REAL, buyer_currency TEXT,
          warehouse_id TEXT, seller_id TEXT, external_uuid TEXT, shipment_date TEXT,
          delivery_date_begin TEXT, delivery_date_end TEXT, status_changed_at TEXT,
          source TEXT NOT NULL, import_batch_id INTEGER REFERENCES import_batches(id),
          updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          PRIMARY KEY(shop_id, posting_number)
        );
        CREATE TABLE IF NOT EXISTS order_items (
          shop_id INTEGER NOT NULL, channel TEXT NOT NULL, posting_number TEXT NOT NULL,
          sku TEXT NOT NULL, offer_id TEXT, product_name_raw TEXT NOT NULL DEFAULT '',
          quantity INTEGER NOT NULL CHECK(quantity > 0),
          unit_price REAL, price_currency TEXT,
          buyer_paid REAL, buyer_currency TEXT,
          source TEXT NOT NULL, import_batch_id INTEGER REFERENCES import_batches(id),
          PRIMARY KEY(shop_id, channel, posting_number, sku),
          FOREIGN KEY(shop_id, posting_number) REFERENCES orders(shop_id, posting_number)
        );
        CREATE TABLE IF NOT EXISTS order_costs (
          shop_id INTEGER NOT NULL REFERENCES shops(id), posting_number TEXT NOT NULL,
          cost_cny REAL NOT NULL, source_rate REAL, source TEXT NOT NULL,
          import_batch_id INTEGER REFERENCES import_batches(id),
          PRIMARY KEY(shop_id, posting_number)
        );
        CREATE TABLE IF NOT EXISTS sync_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER NOT NULL REFERENCES shops(id),
          module TEXT NOT NULL, range_from TEXT, range_to TEXT,
          started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          finished_at TEXT, data_through TEXT, status TEXT NOT NULL, error TEXT,
          progress_done INTEGER NOT NULL DEFAULT 0, progress_total INTEGER NOT NULL DEFAULT 1,
          records INTEGER NOT NULL DEFAULT 0, current_from TEXT, current_to TEXT
        );
        CREATE TABLE IF NOT EXISTS order_api_records (
          shop_id INTEGER NOT NULL REFERENCES shops(id), posting_number TEXT NOT NULL,
          channel TEXT NOT NULL, payload TEXT NOT NULL, fetched_at TEXT NOT NULL,
          PRIMARY KEY(shop_id,posting_number)
        );
        UPDATE orders SET shipped_at=(
          SELECT json_extract(r.payload,'$.delivering_date') FROM order_api_records r
          WHERE r.shop_id=orders.shop_id AND r.posting_number=orders.posting_number
        ) WHERE (shipped_at IS NULL OR shipped_at='') AND EXISTS (
          SELECT 1 FROM order_api_records r WHERE r.shop_id=orders.shop_id
          AND r.posting_number=orders.posting_number
          AND NULLIF(json_extract(r.payload,'$.delivering_date'),'') IS NOT NULL
        );
        CREATE TABLE IF NOT EXISTS finance_records (
          shop_id INTEGER NOT NULL REFERENCES shops(id), record_key TEXT NOT NULL,
          occurred_at TEXT, payload TEXT NOT NULL, fetched_at TEXT NOT NULL,
          PRIMARY KEY(shop_id,record_key)
        );
        CREATE TABLE IF NOT EXISTS return_records (
          shop_id INTEGER NOT NULL REFERENCES shops(id), record_key TEXT NOT NULL,
          occurred_at TEXT, posting_number TEXT, sku TEXT, payload TEXT NOT NULL, fetched_at TEXT NOT NULL,
          PRIMARY KEY(shop_id,record_key)
        );
        CREATE TABLE IF NOT EXISTS rfbs_return_records (
          shop_id INTEGER NOT NULL REFERENCES shops(id), return_id INTEGER NOT NULL,
          return_number TEXT NOT NULL CHECK(trim(return_number) <> ''), created_at TEXT,
          posting_number TEXT, offer_id TEXT, sku TEXT, product_name TEXT,
          status_raw TEXT, status_name TEXT, payload TEXT NOT NULL, fetched_at TEXT NOT NULL,
          PRIMARY KEY(shop_id,return_id)
        );
        CREATE TABLE IF NOT EXISTS stock_snapshots (
          shop_id INTEGER NOT NULL REFERENCES shops(id), record_key TEXT NOT NULL,
          observed_at TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY(shop_id,record_key,observed_at)
        );
        DROP TABLE IF EXISTS question_records;
        DROP TABLE IF EXISTS analytics_records;
        DROP TABLE IF EXISTS price_snapshots;
        DELETE FROM sync_runs WHERE module IN ('questions','premium','prices');
        CREATE TABLE IF NOT EXISTS notification_settings (
          id INTEGER PRIMARY KEY CHECK(id=1),
          daily_enabled INTEGER NOT NULL DEFAULT 0 CHECK(daily_enabled IN (0,1)),
          push_time TEXT NOT NULL DEFAULT '09:00',
          weekdays TEXT NOT NULL DEFAULT '1,2,3,4,5,6,7'
        );
        INSERT OR IGNORE INTO notification_settings VALUES(1,0,'09:00','1,2,3,4,5,6,7');
        CREATE TABLE IF NOT EXISTS notification_runs (
          kind TEXT NOT NULL, stats_date TEXT NOT NULL, status TEXT NOT NULL,
          attempted_at TEXT NOT NULL, sent_at TEXT, error TEXT,
          PRIMARY KEY(kind,stats_date)
        );
        CREATE TABLE IF NOT EXISTS webhook_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          shop_id INTEGER NOT NULL REFERENCES shops(id), message_type TEXT NOT NULL,
          event_key TEXT NOT NULL, occurred_at TEXT, received_at TEXT NOT NULL,
          payload_json TEXT NOT NULL, processing_status TEXT NOT NULL, error_message TEXT,
          UNIQUE(shop_id,event_key)
        );
        CREATE TABLE IF NOT EXISTS order_status_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          shop_id INTEGER NOT NULL, posting_number TEXT NOT NULL, message_type TEXT NOT NULL,
          event_key TEXT NOT NULL, status_raw TEXT NOT NULL, status_name TEXT NOT NULL,
          reason_id TEXT, reason_message TEXT, occurred_at TEXT NOT NULL, payload_json TEXT NOT NULL,
          UNIQUE(shop_id,event_key),
          FOREIGN KEY(shop_id,posting_number) REFERENCES orders(shop_id,posting_number)
        );
        CREATE TABLE IF NOT EXISTS order_manual_data (
          shop_id INTEGER NOT NULL, posting_number TEXT NOT NULL,
          complaint_number TEXT, complaint_at TEXT, complaint_channel TEXT,
          resolved INTEGER, package_returned INTEGER, compensation_amount REAL,
          notes TEXT, manual_short_name TEXT, updated_at TEXT,
          PRIMARY KEY(shop_id,posting_number),
          FOREIGN KEY(shop_id,posting_number) REFERENCES orders(shop_id,posting_number)
        );
        CREATE TABLE IF NOT EXISTS warehouse_stocks (
          shop_id INTEGER NOT NULL REFERENCES shops(id), warehouse_id TEXT NOT NULL,
          sku TEXT NOT NULL, product_id TEXT, present INTEGER NOT NULL, reserved INTEGER NOT NULL,
          updated_at TEXT NOT NULL, payload_json TEXT NOT NULL,
          PRIMARY KEY(shop_id,warehouse_id,sku)
        );
        CREATE TABLE IF NOT EXISTS fbo_stocks (
          shop_id INTEGER NOT NULL REFERENCES shops(id), sku TEXT NOT NULL,
          updated_at TEXT NOT NULL, new_present INTEGER NOT NULL, new_reserved INTEGER NOT NULL,
          old_present INTEGER, old_reserved INTEGER, payload_json TEXT NOT NULL,
          PRIMARY KEY(shop_id,sku)
        );
        CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(shop_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_items_sku ON order_items(shop_id, sku);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_items_identity ON order_items(shop_id, posting_number, sku);
        """)
        shop_columns = {row[1] for row in db.execute("PRAGMA table_info(shops)")}
        for name in ("seller_id", "push_token"):
            if name not in shop_columns:
                db.execute(f"ALTER TABLE shops ADD COLUMN {name} TEXT")
        order_columns = {row[1] for row in db.execute("PRAGMA table_info(orders)")}
        for name in ("cancel_reason_id", "warehouse_id", "seller_id", "external_uuid", "shipment_date",
                     "delivery_date_begin", "delivery_date_end", "status_changed_at"):
            if name not in order_columns:
                db.execute(f"ALTER TABLE orders ADD COLUMN {name} TEXT")
        history_columns = {row[1] for row in db.execute("PRAGMA table_info(order_status_history)")}
        for name in ("reason_id", "reason_message"):
            if name not in history_columns:
                db.execute(f"ALTER TABLE order_status_history ADD COLUMN {name} TEXT")
        sync_columns = {row[1] for row in db.execute("PRAGMA table_info(sync_runs)")}
        for name, definition in (
            ("progress_done", "INTEGER NOT NULL DEFAULT 0"),
            ("progress_total", "INTEGER NOT NULL DEFAULT 1"),
            ("records", "INTEGER NOT NULL DEFAULT 0"),
            ("current_from", "TEXT"),
            ("current_to", "TEXT"),
        ):
            if name not in sync_columns:
                db.execute(f"ALTER TABLE sync_runs ADD COLUMN {name} {definition}")
        db.execute("""UPDATE sync_runs SET progress_done=progress_total
          WHERE status='success' AND progress_done=0""")
        for shop_id in (1, 2):
            db.execute("UPDATE shops SET push_token=? WHERE id=? AND COALESCE(push_token,'')=''",
                       (secrets.token_urlsafe(32), shop_id))
