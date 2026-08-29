import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DB_PATH = DATA_DIR / os.getenv("DB_NAME", "opanel.db")
DEFAULT_DAILY_TEMPLATE = """{{统计日期}} 取消与退货订单汇总

{{店铺明细}}"""
DEFAULT_ALERT_RULE_CONFIGS = {
    "ad_spend_spike": {
        "baseline_days": 7, "minimum_baseline_days": 4,
        "increase_percent": 50, "minimum_current_spend_rub": 500,
    },
    "ad_drr_high": {"window_days": 3, "threshold_drr": 30, "minimum_spend_rub": 500},
    "ad_clicks_no_orders": {"window_days": 3, "minimum_clicks": 30, "minimum_spend_rub": 300},
    "ad_orders_drop": {
        "baseline_days": 7, "minimum_baseline_days": 4, "drop_percent": 50,
        "minimum_baseline_orders_per_day": 2, "minimum_spend_ratio": .70,
    },
    "inventory_risk": {},
    "sales_drop": {
        "baseline_days": 7, "minimum_baseline_days": 4, "drop_percent": 50,
        "minimum_baseline_units_per_day": 5,
    },
}


@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    for pragma in ("foreign_keys=ON", "busy_timeout=30000", "journal_mode=WAL",
                   "synchronous=NORMAL", "cache_size=-64000", "mmap_size=268435456",
                   "temp_store=MEMORY"):
        db.execute(f"PRAGMA {pragma}")
    try:
        yield db
    finally:
        try:
            db.execute("PRAGMA optimize")
        except sqlite3.Error:
            pass
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
    if old:
        marks = ",".join("?" for _ in old)
        db.execute(f"UPDATE orders SET import_batch_id=NULL WHERE import_batch_id IN ({marks})", old)
        db.execute(f"UPDATE order_items SET import_batch_id=NULL WHERE import_batch_id IN ({marks})", old)
        db.execute(f"DELETE FROM import_batches WHERE id IN ({marks})", old)
