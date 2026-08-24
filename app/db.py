import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "fuck-ozon.db"
LEGACY_DAILY_TEMPLATE = """昨日取消与退货订单汇总
统计日期：{{统计日期}}（北京时间）

{{店铺明细}}

数据截止：{{数据截止}}"""
DEFAULT_DAILY_TEMPLATE = """{{统计日期}} 取消与退货订单汇总

{{店铺明细}}"""


@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-64000")
    db.execute("PRAGMA mmap_size=268435456")
    db.execute("PRAGMA temp_store=MEMORY")
    try:
        yield db
    finally:
        db.close()


@contextmanager
def transaction():
    with connect() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def trim_import_batches(db, keep=10):
    old = [row[0] for row in db.execute(
        "SELECT id FROM import_batches ORDER BY id DESC LIMIT -1 OFFSET ?", (keep,))]
    if not old:
        return
    marks = ",".join("?" for _ in old)
    db.execute(f"UPDATE orders SET import_batch_id=NULL WHERE import_batch_id IN ({marks})", old)
    db.execute(f"UPDATE order_items SET import_batch_id=NULL WHERE import_batch_id IN ({marks})", old)
    db.execute(f"DELETE FROM import_batches WHERE id IN ({marks})", old)


def migrate_product_rules(db):
    for row in db.execute("""SELECT n.key_value,n.short_name FROM product_short_names n
      LEFT JOIN product_short_name_migrations m
        ON m.key_type=n.key_type AND m.key_value=n.key_value
      WHERE n.key_type='offer_id' AND m.key_value IS NULL""").fetchall():
        skus = [value[0] for value in db.execute(
            "SELECT DISTINCT sku FROM order_items WHERE offer_id=? ORDER BY sku", (row["key_value"],))]
        note = "货号无法唯一关联SKU"
        if len(skus) == 1:
            existing = db.execute("SELECT short_name FROM product_short_names WHERE key_type='sku' AND key_value=?",
                                  (skus[0],)).fetchone()
            if not existing:
                db.execute("INSERT INTO product_short_names VALUES('sku',?,?,strftime('%Y-%m-%dT%H:%M:%SZ','now'))",
                           (skus[0], row["short_name"]))
                note = f"已迁移至SKU {skus[0]}"
            elif existing[0] == row["short_name"]:
                note = f"SKU {skus[0]} 已有相同规则"
            else:
                note = f"与SKU {skus[0]}现有短名称冲突"
        db.execute("INSERT INTO product_short_name_migrations VALUES('offer_id',?,0,?)",
                   (row["key_value"], note))

    for row in db.execute("""SELECT g.id FROM product_groups g
      LEFT JOIN product_group_config c ON c.group_id=g.id WHERE c.group_id IS NULL""").fetchall():
        offers = [value[0] for value in db.execute("""SELECT key_value FROM product_group_members
          WHERE group_id=? AND key_type='offer_id' ORDER BY key_value""", (row["id"],))]
        primary_offer = offers[0] if len(offers) == 1 else None
        skus = [value[0] for value in db.execute(
            "SELECT DISTINCT sku FROM order_items WHERE offer_id=? ORDER BY sku", (primary_offer,))] if primary_offer else []
        active = len(skus) == 1
        note = "" if active else ("主货号对应多个SKU，待管理员选择" if len(skus) > 1
                                  else "待设置主货号" if len(offers) != 1 else "主货号未匹配商品")
        db.execute("INSERT INTO product_group_config VALUES(?,?,?,?,?)",
                   (row["id"], primary_offer, skus[0] if active else None,
                    "active" if active else "pending", note))


def init_db():
    with transaction() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS shops (
          id INTEGER PRIMARY KEY CHECK(id IN (1,2)),
          name TEXT NOT NULL UNIQUE CHECK(trim(name) <> ''),
          settlement_currency TEXT NOT NULL CHECK(settlement_currency IN ('USD','CNY'))
        );
        INSERT OR IGNORE INTO shops(id,name,settlement_currency) VALUES (1, '店铺1', 'USD'), (2, '店铺2', 'CNY');

        CREATE TABLE IF NOT EXISTS exchange_rates (
          from_currency TEXT NOT NULL CHECK(from_currency IN ('USD','CNY')),
          to_currency TEXT NOT NULL CHECK(to_currency='RUB'),
          valid_from_utc TEXT NOT NULL,
          valid_to_utc TEXT NOT NULL,
          base_rate TEXT NOT NULL,
          rate_with_adjustment TEXT,
          source TEXT NOT NULL DEFAULT 'ozon_xapi' CHECK(source='ozon_xapi'),
          fetched_at TEXT NOT NULL,
          PRIMARY KEY(from_currency,to_currency,valid_from_utc,valid_to_utc)
        );

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
          buyer_paid REAL, buyer_currency TEXT,
          warehouse_id TEXT, status_changed_at TEXT,
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
        CREATE TABLE IF NOT EXISTS sync_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER NOT NULL REFERENCES shops(id),
          module TEXT NOT NULL, range_from TEXT, range_to TEXT,
          started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          finished_at TEXT, data_through TEXT, status TEXT NOT NULL, error TEXT,
          progress_done INTEGER NOT NULL DEFAULT 0, progress_total INTEGER NOT NULL DEFAULT 1,
          records INTEGER NOT NULL DEFAULT 0, current_from TEXT, current_to TEXT,
          run_source TEXT NOT NULL DEFAULT 'manual', scheduled_date TEXT
        );
        CREATE TABLE IF NOT EXISTS auto_sync_settings (
          module TEXT PRIMARY KEY CHECK(module IN ('orders','returns','stock')),
          enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
          run_time TEXT NOT NULL, range_days INTEGER NOT NULL CHECK(range_days BETWEEN 1 AND 365)
        );
        INSERT OR IGNORE INTO auto_sync_settings VALUES
          ('orders',0,'02:00',3),('returns',0,'04:00',3),('stock',0,'05:00',1);
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
          weekdays TEXT NOT NULL DEFAULT '1,2,3,4,5,6,7',
          template TEXT
        );
        INSERT OR IGNORE INTO notification_settings(id,daily_enabled,push_time,weekdays)
          VALUES(1,0,'09:00','1,2,3,4,5,6,7');
        CREATE TABLE IF NOT EXISTS notification_runs (
          kind TEXT NOT NULL, stats_date TEXT NOT NULL, status TEXT NOT NULL,
          attempted_at TEXT NOT NULL, sent_at TEXT, error TEXT,
          PRIMARY KEY(kind,stats_date)
        );
        CREATE TABLE IF NOT EXISTS order_manual_data (
          shop_id INTEGER NOT NULL, posting_number TEXT NOT NULL,
          complaint_number TEXT, complaint_at TEXT, complaint_channel TEXT,
          resolved INTEGER, package_returned INTEGER, compensation_amount REAL,
          notes TEXT, manual_short_name TEXT, updated_at TEXT,
          PRIMARY KEY(shop_id,posting_number),
          FOREIGN KEY(shop_id,posting_number) REFERENCES orders(shop_id,posting_number)
        );
        CREATE TABLE IF NOT EXISTS complaints (
          shop_id INTEGER NOT NULL REFERENCES shops(id), complaint_number TEXT NOT NULL,
          posting_number TEXT NOT NULL, complaint_at TEXT NOT NULL, channel TEXT NOT NULL,
          resolved INTEGER CHECK(resolved IN (0,1) OR resolved IS NULL),
          package_returned INTEGER CHECK(package_returned IN (0,1) OR package_returned IS NULL),
          compensation_amount REAL, compensation_currency TEXT, notes TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          PRIMARY KEY(shop_id,complaint_number),
          FOREIGN KEY(shop_id,posting_number) REFERENCES orders(shop_id,posting_number)
        );
        CREATE TABLE IF NOT EXISTS order_after_sales (
          shop_id INTEGER NOT NULL, posting_number TEXT NOT NULL, status TEXT NOT NULL DEFAULT '处理中',
          updated_at TEXT NOT NULL, PRIMARY KEY(shop_id,posting_number),
          FOREIGN KEY(shop_id,posting_number) REFERENCES orders(shop_id,posting_number)
        );
        CREATE TABLE IF NOT EXISTS product_short_names (
          key_type TEXT NOT NULL CHECK(key_type IN ('sku','offer_id')), key_value TEXT NOT NULL,
          short_name TEXT NOT NULL CHECK(trim(short_name)<>''), updated_at TEXT NOT NULL,
          PRIMARY KEY(key_type,key_value)
        );
        CREATE TABLE IF NOT EXISTS product_groups (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE CHECK(trim(name)<>''),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_group_members (
          group_id INTEGER NOT NULL REFERENCES product_groups(id) ON DELETE CASCADE,
          key_type TEXT NOT NULL CHECK(key_type IN ('sku','offer_id')), key_value TEXT NOT NULL,
          PRIMARY KEY(key_type,key_value), UNIQUE(group_id,key_type,key_value)
        );
        CREATE TABLE IF NOT EXISTS product_short_name_migrations (
          key_type TEXT NOT NULL, key_value TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
          note TEXT NOT NULL DEFAULT '', PRIMARY KEY(key_type,key_value)
        );
        CREATE TABLE IF NOT EXISTS product_group_config (
          group_id INTEGER PRIMARY KEY REFERENCES product_groups(id) ON DELETE CASCADE,
          primary_offer_id TEXT, primary_sku TEXT, status TEXT NOT NULL DEFAULT 'pending',
          note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS brand_rules (
          id INTEGER PRIMARY KEY AUTOINCREMENT, brand_name TEXT NOT NULL CHECK(trim(brand_name)<>''),
          keyword TEXT NOT NULL CHECK(trim(keyword)<>''), priority INTEGER NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shop_auto_sync_settings (
          shop_id INTEGER NOT NULL REFERENCES shops(id),
          module TEXT NOT NULL CHECK(module IN ('orders','returns','stock')),
          enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)), run_time TEXT NOT NULL,
          range_days INTEGER NOT NULL CHECK(range_days BETWEEN 1 AND 365),
          PRIMARY KEY(shop_id,module)
        );
        INSERT OR IGNORE INTO shop_auto_sync_settings(shop_id,module,enabled,run_time,range_days)
          SELECT s.id,a.module,a.enabled,a.run_time,a.range_days FROM shops s CROSS JOIN auto_sync_settings a
          WHERE a.module IN ('orders','returns','stock');
        CREATE TABLE IF NOT EXISTS stock_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER NOT NULL REFERENCES shops(id),
          source TEXT NOT NULL, warehouse_id TEXT, sku TEXT NOT NULL, present INTEGER NOT NULL,
          reserved INTEGER NOT NULL, occurred_at TEXT NOT NULL, event_key TEXT,
          payload_json TEXT NOT NULL, UNIQUE(shop_id,source,event_key,warehouse_id,sku)
        );
        CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(shop_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_orders_perf ON orders(shop_id, created_at, status_raw, channel, shipped);
        CREATE INDEX IF NOT EXISTS idx_orders_cancelled ON orders(shop_id, status_raw, shipped, created_at);
        CREATE INDEX IF NOT EXISTS idx_items_sku ON order_items(shop_id, sku);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_items_identity ON order_items(shop_id, posting_number, sku);
        CREATE INDEX IF NOT EXISTS idx_complaints_order ON complaints(shop_id,posting_number);
        CREATE INDEX IF NOT EXISTS idx_stock_history_time ON stock_history(shop_id,occurred_at);
        """)
        order_columns = {row[1] for row in db.execute("PRAGMA table_info(orders)")}
        for name in ("cancel_reason_id", "warehouse_id", "status_changed_at"):
            if name not in order_columns:
                db.execute(f"ALTER TABLE orders ADD COLUMN {name} TEXT")
        notification_columns = {row[1] for row in db.execute("PRAGMA table_info(notification_settings)")}
        if "template" not in notification_columns:
            db.execute("ALTER TABLE notification_settings ADD COLUMN template TEXT")
        db.execute("UPDATE notification_settings SET template=? WHERE template IS NULL OR trim(template)=''",
                   (DEFAULT_DAILY_TEMPLATE,))
        db.execute("UPDATE notification_settings SET template=? WHERE template=?",
                   (DEFAULT_DAILY_TEMPLATE, LEGACY_DAILY_TEMPLATE))
        return_columns = {row[1] for row in db.execute("PRAGMA table_info(rfbs_return_records)")}
        for name, definition in (
            ("order_number", "TEXT"), ("quantity", "INTEGER"), ("reason_raw", "TEXT"),
            ("reason_name", "TEXT"), ("compensation_status", "TEXT"), ("product_amount", "REAL"),
            ("product_currency", "TEXT"), ("logistic_return_at", "TEXT"), ("buyer_comment_raw", "TEXT"),
        ):
            if name not in return_columns:
                db.execute(f"ALTER TABLE rfbs_return_records ADD COLUMN {name} {definition}")
        db.execute("""UPDATE orders SET cancelled_after_ship=1
          WHERE status_raw='已取消' AND shipped=1 AND COALESCE(cancelled_after_ship,0)=0""")
        sync_columns = {row[1] for row in db.execute("PRAGMA table_info(sync_runs)")}
        for name, definition in (
            ("progress_done", "INTEGER NOT NULL DEFAULT 0"),
            ("progress_total", "INTEGER NOT NULL DEFAULT 1"),
            ("records", "INTEGER NOT NULL DEFAULT 0"),
            ("current_from", "TEXT"),
            ("current_to", "TEXT"),
            ("run_source", "TEXT NOT NULL DEFAULT 'manual'"),
            ("scheduled_date", "TEXT"),
        ):
            if name not in sync_columns:
                db.execute(f"ALTER TABLE sync_runs ADD COLUMN {name} {definition}")
        db.execute("""UPDATE sync_runs SET progress_done=progress_total
          WHERE status='success' AND progress_done=0""")
        db.execute("DROP INDEX IF EXISTS idx_auto_sync_once")
        db.execute("""CREATE UNIQUE INDEX idx_auto_sync_once
          ON sync_runs(shop_id,module,scheduled_date)
          WHERE run_source='auto' AND status IN ('running','success')""")
        db.execute("""INSERT OR IGNORE INTO complaints(
          shop_id,complaint_number,posting_number,complaint_at,channel,resolved,package_returned,
          compensation_amount,compensation_currency,notes,created_at,updated_at)
          SELECT m.shop_id,m.complaint_number,m.posting_number,COALESCE(m.complaint_at,m.updated_at),
          COALESCE(m.complaint_channel,'历史迁移'),m.resolved,m.package_returned,m.compensation_amount,
          CASE WHEN m.compensation_amount IS NOT NULL THEN s.settlement_currency END,m.notes,
          COALESCE(m.updated_at,strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          COALESCE(m.updated_at,strftime('%Y-%m-%dT%H:%M:%SZ','now'))
          FROM order_manual_data m JOIN shops s ON s.id=m.shop_id
          WHERE NULLIF(trim(m.complaint_number),'') IS NOT NULL""")
        db.execute("""INSERT OR IGNORE INTO stock_history(
          shop_id,source,warehouse_id,sku,present,reserved,occurred_at,event_key,payload_json)
          SELECT s.shop_id,'API快照',COALESCE(json_extract(v.value,'$.warehouse_ids'),''),
            CAST(COALESCE(json_extract(v.value,'$.sku'),json_extract(s.payload,'$.product_id')) AS TEXT),
            COALESCE(json_extract(v.value,'$.present'),0),COALESCE(json_extract(v.value,'$.reserved'),0),
            s.observed_at,s.record_key||':'||s.observed_at,s.payload
          FROM stock_snapshots s,json_each(s.payload,'$.stocks') v
          WHERE json_valid(s.payload)""")
        migrate_product_rules(db)
        trim_import_batches(db)
