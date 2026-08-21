from datetime import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import db
from app.main import _run_sync_job, _sync_ranges


class SyncProgressTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()

    def tearDown(self):
        self.temp.cleanup()

    def create_run(self, total):
        with db.transaction() as connection:
            return connection.execute("""INSERT INTO sync_runs(
              shop_id,module,range_from,range_to,status,progress_total)
              VALUES(1,'orders','','','running',?)""", (total,)).lastrowid

    def test_month_ranges_and_success_progress(self):
        timezone = ZoneInfo("Asia/Shanghai")
        ranges = _sync_ranges("orders", datetime(2026, 1, 31, 15, 30, tzinfo=timezone),
                              datetime(2026, 3, 2, 23, 59, 59, tzinfo=timezone))
        self.assertEqual([(start.date().isoformat(), end.date().isoformat()) for start, end in ranges],
                         [("2026-01-31", "2026-01-31"), ("2026-02-01", "2026-02-28"),
                          ("2026-03-01", "2026-03-02")])
        self.assertEqual(ranges[1][0].strftime("%Y-%m-%d %H:%M:%S"), "2026-02-01 00:00:00")
        run_id = self.create_run(len(ranges))
        with patch("app.main.sync_module", return_value={"records": 4}):
            _run_sync_job(run_id, "orders", 1, ranges)
        with db.connect() as connection:
            row = connection.execute("SELECT status,progress_done,progress_total,records FROM sync_runs").fetchone()
        self.assertEqual(tuple(row), ("success", 3, 3, 12))

    def test_failure_stops_remaining_ranges_and_stock_is_one_step(self):
        timezone = ZoneInfo("Asia/Shanghai")
        start, end = datetime(2026, 1, 1, tzinfo=timezone), datetime(2026, 3, 31, tzinfo=timezone)
        ranges = _sync_ranges("orders", start, end)
        self.assertEqual(len(_sync_ranges("stock", start, end)), 1)
        run_id = self.create_run(len(ranges))
        with patch("app.main.sync_module", side_effect=({"records": 2}, RuntimeError("第二段失败"))) as sync_call, \
             patch("app.main.send_sync_failure"):
            _run_sync_job(run_id, "orders", 1, ranges)
        with db.connect() as connection:
            row = connection.execute("SELECT status,progress_done,progress_total,records,error FROM sync_runs").fetchone()
        self.assertEqual(sync_call.call_count, 2)
        self.assertEqual(tuple(row), ("failed", 1, 3, 2, "第二段失败"))


if __name__ == "__main__":
    unittest.main()
