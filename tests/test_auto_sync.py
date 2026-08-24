from datetime import datetime
import unittest
from unittest.mock import patch

from app import db
from app.main import auto_sync_slot, run_auto_sync_once, save_auto_sync_settings
from app.ozon import BEIJING
from tests.support import DatabaseTestCase


MODULES = ("orders", "returns", "stock")


def settings(enabled=(), interval=6, days=7):
    return {str(shop): {module: {
        "enabled": (shop, module) in enabled,
        "interval_hours": interval,
        "range_days": days,
    } for module in MODULES} for shop in (1, 2)}


class AutoSyncTest(DatabaseTestCase):
    def test_beijing_hour_slots(self):
        at_1025 = datetime(2026, 8, 24, 10, 25, tzinfo=BEIJING)
        self.assertEqual(auto_sync_slot(at_1025, 1).isoformat(), "2026-08-24T10:00:00+08:00")
        self.assertEqual(auto_sync_slot(at_1025, 6).isoformat(), "2026-08-24T06:00:00+08:00")
        self.assertEqual(auto_sync_slot(
            datetime(2026, 8, 24, 12, 1, tzinfo=BEIJING), 6).hour, 12)

    def test_same_slot_deduplicates_and_new_slot_runs(self):
        save_auto_sync_settings(settings({(1, "orders")}, interval=6))
        with patch("app.main.threading.Thread") as thread:
            first = run_auto_sync_once(datetime(2026, 8, 24, 10, 25, tzinfo=BEIJING))
            duplicate = run_auto_sync_once(datetime(2026, 8, 24, 10, 55, tzinfo=BEIJING))
            with db.transaction() as connection:
                connection.execute("UPDATE sync_runs SET status='success' WHERE id=?", (first[0],))
            next_slot = run_auto_sync_once(datetime(2026, 8, 24, 12, 1, tzinfo=BEIJING))
        self.assertEqual((len(first), duplicate, len(next_slot)), (1, [], 1))
        self.assertEqual(thread.call_count, 2)
        with db.connect() as connection:
            slots = [row[0] for row in connection.execute(
                "SELECT scheduled_slot FROM sync_runs ORDER BY id")]
        self.assertEqual(slots, ["2026-08-24T06:00:00+08:00", "2026-08-24T12:00:00+08:00"])

    def test_running_job_blocks_only_same_shop_and_module(self):
        save_auto_sync_settings(settings({(1, "orders"), (1, "returns"), (2, "orders")}))
        with db.transaction() as connection:
            connection.execute("""INSERT INTO sync_runs(
              shop_id,module,status,run_source,scheduled_slot,started_at)
              VALUES(1,'orders','running','auto','2026-08-24T00:00:00+08:00','2026-08-24T00:00:00Z')""")
        with patch("app.main.threading.Thread") as thread:
            started = run_auto_sync_once(datetime(2026, 8, 24, 10, 25, tzinfo=BEIJING))
        self.assertEqual(len(started), 2)
        self.assertEqual(thread.call_count, 2)
        with db.connect() as connection:
            pairs = {tuple(row) for row in connection.execute(
                "SELECT shop_id,module FROM sync_runs WHERE id IN (?,?)", started)}
        self.assertEqual(pairs, {(1, "returns"), (2, "orders")})

    def test_failed_slot_retries_only_after_five_minutes(self):
        save_auto_sync_settings(settings({(1, "orders")}))
        with db.transaction() as connection:
            connection.execute("""INSERT INTO sync_runs(
              shop_id,module,status,run_source,scheduled_slot,started_at,finished_at)
              VALUES(1,'orders','failed','auto','2026-08-24T06:00:00+08:00',
                     '2026-08-24T02:00:00Z','2026-08-24T02:01:00Z')""")
        with patch("app.main.threading.Thread") as thread:
            cooling = run_auto_sync_once(datetime(2026, 8, 24, 10, 4, tzinfo=BEIJING))
            retried = run_auto_sync_once(datetime(2026, 8, 24, 10, 7, tzinfo=BEIJING))
        self.assertEqual(cooling, [])
        self.assertEqual(len(retried), 1)
        self.assertEqual(thread.call_count, 1)

    def test_settings_validation_and_stock_range(self):
        save_auto_sync_settings(settings(interval=6, days=7))
        with db.connect() as connection:
            rows = connection.execute("""SELECT module,interval_hours,range_days
              FROM shop_auto_sync_settings WHERE shop_id=1 ORDER BY module""").fetchall()
        self.assertEqual({row["module"]: (row["interval_hours"], row["range_days"])
                          for row in rows},
                         {"orders": (6, 7), "returns": (6, 7), "stock": (6, 1)})
        for invalid in (0, 5, 7, 25):
            with self.assertRaisesRegex(ValueError, "只允许"):
                save_auto_sync_settings(settings(interval=invalid))
        obsolete = settings()
        obsolete["1"]["orders"]["run_time"] = "08:30"
        with self.assertRaisesRegex(ValueError, "已停用"):
            save_auto_sync_settings(obsolete)
        values = settings()
        values["1"]["returns"]["range_days"] = 366
        with self.assertRaisesRegex(ValueError, "1 至 365"):
            save_auto_sync_settings(values)

if __name__ == "__main__":
    unittest.main()
