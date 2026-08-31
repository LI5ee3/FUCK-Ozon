import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from app import db
from app.migrations import init_db


MODULE_TABLES = {
    "orders": ("orders", "order_items"),
    "returns": ("return_records", "rfbs_return_records"),
    "stock": ("stock_snapshots", "stock_history"),
}


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self._db_data_dir, self._db_path = db.DATA_DIR, db.DB_PATH
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        init_db()

    def tearDown(self):
        db.DATA_DIR, db.DB_PATH = self._db_data_dir, self._db_path
        self.temp.cleanup()


def add_order(connection, shop_id, posting_number, channel, created_at=None,
              status_raw="", shipped=0, source="api", *, shipped_at=None,
              delivered_at=None, tracking_number=None, cancel_reason_raw=None,
              cancel_reason_id=None, data_anomaly=0, amount_original=None,
              amount_currency=None, status_changed_at=None):
    connection.execute("""INSERT INTO orders(
      shop_id,posting_number,channel,created_at,shipped_at,delivered_at,
      tracking_number,status_raw,cancel_reason_raw,cancel_reason_id,shipped,
      data_anomaly,amount_original,amount_currency,status_changed_at,source)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (shop_id, posting_number, channel, created_at, shipped_at, delivered_at,
       tracking_number, status_raw, cancel_reason_raw, cancel_reason_id, shipped,
       data_anomaly, amount_original, amount_currency, status_changed_at, source))


def add_item(connection, shop_id, posting_number, channel, sku, quantity=1,
             *, offer_id=None, product_name_raw="", unit_price=None,
             price_currency=None, source="api"):
    connection.execute("""INSERT INTO order_items(
      shop_id,posting_number,channel,sku,offer_id,product_name_raw,quantity,
      unit_price,price_currency,source) VALUES(?,?,?,?,?,?,?,?,?,?)""",
      (shop_id, posting_number, channel, sku, offer_id, product_name_raw, quantity,
       unit_price, price_currency, source))


def add_stock_snapshot(connection, shop_id, record_key, observed_at, payload):
    connection.execute("INSERT INTO stock_snapshots VALUES(?,?,?,?)",
                       (shop_id, record_key, observed_at,
                        json.dumps(payload, ensure_ascii=False)))


def table_fingerprints():
    result = {}
    with db.connect() as connection:
        for tables in MODULE_TABLES.values():
            for table in tables:
                rows = connection.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall()
                digest = hashlib.sha256("\n".join(
                    "|".join(str(value) for value in row) for row in rows).encode()).hexdigest()
                result[table] = {"rows": len(rows), "sha256": digest}
    return result


class MockRequest:
    def __init__(self, value):
        self.value = value

    headers = {}

    async def stream(self):
        yield json.dumps(self.value).encode()

    async def json(self):
        return self.value
