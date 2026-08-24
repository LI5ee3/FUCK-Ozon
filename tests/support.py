import hashlib
import tempfile
import unittest
from pathlib import Path

from app import db


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
        db.init_db()

    def tearDown(self):
        db.DATA_DIR, db.DB_PATH = self._db_data_dir, self._db_path
        self.temp.cleanup()


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

    async def json(self):
        return self.value
