import os
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
          settlement_currency TEXT NOT NULL CHECK(settlement_currency IN ('USD','CNY'))
        );
        INSERT OR IGNORE INTO shops VALUES (1, '店铺1', 'USD'), (2, '店铺2', 'CNY');

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
          status_raw TEXT NOT NULL DEFAULT '', cancel_reason_raw TEXT,
          shipped INTEGER NOT NULL DEFAULT 0 CHECK(shipped IN (0,1)),
          cancelled_after_ship INTEGER CHECK(cancelled_after_ship IN (0,1)),
          data_anomaly INTEGER NOT NULL DEFAULT 0 CHECK(data_anomaly IN (0,1)),
          amount_original REAL, amount_currency TEXT,
          amount_cny REAL, exchange_rate REAL, exchange_source TEXT, exchange_date TEXT,
          buyer_paid REAL, buyer_currency TEXT,
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
          finished_at TEXT, data_through TEXT, status TEXT NOT NULL, error TEXT
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
        CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(shop_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_items_sku ON order_items(shop_id, sku);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_items_identity ON order_items(shop_id, posting_number, sku);
        """)
