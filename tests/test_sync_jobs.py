from datetime import datetime
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import db
from app.main import (_run_sync_job, _sync_ranges, _trim_sync_runs,
                      auto_sync_slot, run_auto_sync_once,
                      save_auto_sync_settings)
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
        cases = (
            (datetime(2026, 8, 24, 10, 25, tzinfo=BEIJING), 1, "2026-08-24T10:00:00+08:00"),
            (datetime(2026, 8, 24, 10, 25, tzinfo=BEIJING), 6, "2026-08-24T06:00:00+08:00"),
            (datetime(2026, 8, 24, 12, 1, tzinfo=BEIJING), 6, "2026-08-24T12:00:00+08:00"),
        )
        for now, interval, expected in cases:
            with self.subTest(now=now, interval=interval):
                self.assertEqual(auto_sync_slot(now, interval).isoformat(), expected)

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
                         {"orders": (6, 7), "returns": (6, 7), "stock": (6, 1),
                          "ad_campaign_daily": (24, 7), "ad_sku_daily": (24, 7)})
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


class SyncProgressTest(DatabaseTestCase):
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

    def test_ad_sync_job_uses_performance_statistics_and_one_step(self):
        timezone = ZoneInfo("Asia/Shanghai")
        start = datetime(2026, 8, 1, tzinfo=timezone)
        end = datetime(2026, 8, 7, 23, 59, 59, tzinfo=timezone)
        ranges = _sync_ranges("ad_campaign_daily", start, end)
        with db.transaction() as connection:
            run_id = connection.execute("""INSERT INTO sync_runs(
              shop_id,module,range_from,range_to,status,progress_total)
              VALUES(1,'ad_campaign_daily','','','running',?)""", (len(ranges),)).lastrowid
        with patch("app.main.sync_performance_statistics", return_value={"inserted_or_updated": 3}) as sync_call:
            _run_sync_job(run_id, "ad_campaign_daily", 1, ranges)
        self.assertEqual(sync_call.call_args.args, (1, "2026-08-01", "2026-08-07", "ad_campaign_daily"))
        with db.connect() as connection:
            row = connection.execute("SELECT status,progress_done,progress_total,records FROM sync_runs").fetchone()
        self.assertEqual(tuple(row), ("success", 1, 1, 3))

    def test_old_sync_logs_are_deleted_without_touching_pulled_data(self):
        with db.transaction() as connection:
            connection.execute("""INSERT INTO stock_snapshots
              (shop_id,record_key,observed_at,payload) VALUES(1,'stock','2026-08-22T00:00:00Z','{}')""")
            for _ in range(12):
                connection.execute("""INSERT INTO sync_runs(
                  shop_id,module,status,finished_at) VALUES(1,'stock','success','2026-08-22T00:00:00Z')""")
            _trim_sync_runs(connection, today="2026-08-23")
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sync_runs").fetchone()[0], 10)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM stock_snapshots").fetchone()[0], 1)
