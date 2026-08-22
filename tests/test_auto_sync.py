from datetime import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db
from app.main import run_auto_sync_once, save_auto_sync_settings
from app.ozon import BEIJING


class AutoSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()

    def tearDown(self):
        self.temp.cleanup()

    def test_each_module_settings_and_daily_deduplication(self):
        values = {
            module: {"enabled": module == "orders", "run_time": "08:30", "range_days": 7}
            for module in ("orders", "returns", "stock")
        }
        save_auto_sync_settings(values)
        with db.connect() as connection:
            stock_days = connection.execute(
                "SELECT range_days FROM auto_sync_settings WHERE module='stock'").fetchone()[0]
        self.assertEqual(stock_days, 1)
        self.assertEqual(run_auto_sync_once(datetime(2026, 8, 21, 8, 29, tzinfo=BEIJING)), [])
        with patch("app.main.threading.Thread") as thread:
            first = run_auto_sync_once(datetime(2026, 8, 21, 8, 30, tzinfo=BEIJING))
            second = run_auto_sync_once(datetime(2026, 8, 21, 9, 0, tzinfo=BEIJING))
        self.assertEqual(len(first), 2)
        self.assertEqual(second, [])
        self.assertEqual(thread.call_count, 2)
        with db.connect() as connection:
            rows = connection.execute("""SELECT shop_id,module,run_source,scheduled_date,range_from,range_to
              FROM sync_runs ORDER BY shop_id""").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["module"] == "orders" and row["run_source"] == "auto" for row in rows))
        self.assertTrue(all(row["scheduled_date"] == "2026-08-21" for row in rows))
        self.assertTrue(all(row["range_from"].startswith("2026-08-15T00:00:00") for row in rows))

    def test_invalid_range_is_rejected(self):
        values = {module: {"enabled": False, "run_time": "02:00", "range_days": 1}
                  for module in ("orders", "returns", "stock")}
        values["returns"]["range_days"] = 366
        with self.assertRaisesRegex(ValueError, "1 至 365"):
            save_auto_sync_settings(values)

    def test_failed_auto_sync_retries_after_cooldown(self):
        values = {module: {"enabled": module == "orders", "run_time": "08:30", "range_days": 1}
                  for module in ("orders", "returns", "stock")}
        save_auto_sync_settings(values)
        with db.transaction() as connection:
            connection.execute("""INSERT INTO sync_runs(
              shop_id,module,status,run_source,scheduled_date,started_at)
              VALUES(1,'orders','failed','auto','2026-08-21','2000-01-01T00:00:00Z')""")
        with patch("app.main.threading.Thread") as thread:
            started = run_auto_sync_once(datetime(2026, 8, 21, 9, 0, tzinfo=BEIJING))
        self.assertEqual(len(started), 2)
        self.assertEqual(thread.call_count, 2)


if __name__ == "__main__":
    unittest.main()
