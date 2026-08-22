import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from app import db
from app.main import BEIJING, _overview_range, summary


class OverviewRegressionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()
        orders = [
            (1, "BEFORE", "FBP", "2026-08-09T15:30:00Z", "已签收", 1, 50, "USD"),
            (1, "MULTI", "FBP", "2026-08-09T16:30:00Z", "已签收", 1, 100, "USD"),
            (1, "FALLBACK", "realFBS", "2026-08-12T00:00:00Z", "已签收", 1, None, None),
            (1, "PRE-CANCEL", "WHD", "2026-08-13T00:00:00Z", "已取消", 0, 999, "USD"),
            (1, "POST-CANCEL", "WHD", "2026-08-14T00:00:00Z", "已取消", 1, 30, "USD"),
            (1, "LATER", "FBP", "2026-08-24T00:00:00Z", "已签收", 1, 20, "USD"),
            (2, "CNY", "FBP", "2026-08-11T00:00:00Z", "已签收", 1, 200, "CNY"),
        ]
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO orders(
              shop_id,posting_number,channel,created_at,status_raw,shipped,
              amount_original,amount_currency,source) VALUES(?,?,?,?,?,?,?,?,'api')""", orders)
            items = [
                (1, "FBP", "BEFORE", "B", 1, 50, "USD"),
                (1, "FBP", "MULTI", "M1", 1, 60, "USD"),
                (1, "FBP", "MULTI", "M2", 2, 20, "USD"),
                (1, "realFBS", "FALLBACK", "F1", 2, 10, "USD"),
                (1, "realFBS", "FALLBACK", "F2", 1, 5, "USD"),
                (1, "WHD", "PRE-CANCEL", "PC", 1, 999, "USD"),
                (1, "WHD", "POST-CANCEL", "AC", 1, 30, "USD"),
                (1, "FBP", "LATER", "L", 1, 20, "USD"),
                (2, "FBP", "CNY", "C", 1, 200, "CNY"),
            ]
            connection.executemany("""INSERT INTO order_items(
              shop_id,channel,posting_number,sku,product_name_raw,quantity,unit_price,
              price_currency,source) VALUES(?,?,?,?,'',?,?,?,'api')""", items)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_range_and_validation(self):
        start, end, utc_start, utc_end = _overview_range(
            None, None, datetime(2026, 8, 22, 12, tzinfo=BEIJING))
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-05-22", "2026-08-22"))
        self.assertTrue(utc_start.startswith("2026-05-21T16:00:00"))
        self.assertTrue(utc_end.startswith("2026-08-22T16:00:00"))
        with self.assertRaises(HTTPException):
            summary(1, "2026-08-20", "2026-08-10", "day")

    def test_beijing_boundary_dedup_cancellation_channels_and_gmv(self):
        data = summary(1, "2026-08-10", "2026-08-16", "day")
        self.assertEqual(data["totals"]["orders"], 3)
        self.assertEqual(data["totals"]["pieces"], 7)
        self.assertEqual(data["totals"]["cancelled_orders"], 1)
        self.assertAlmostEqual(data["totals"]["cancel_rate"], 1 / 3)
        self.assertEqual([row["channel"] for row in data["channels"]], ["FBP", "realFBS", "WHD"])
        self.assertEqual([row["orders"] for row in data["channels"]], [1, 1, 1])
        self.assertEqual(len(data["buckets"]), 7)
        self.assertEqual(data["buckets"][0]["orders"], 1)
        self.assertEqual(data["buckets"][1]["orders"], 0)
        self.assertEqual(data["gmv"], {"amount": 155.0, "currency": "USD", "missing_rate_orders": 0})
        self.assertEqual(data["buckets"][0]["gmv"]["amount"], 100)

    def test_week_month_grouping_zero_fill_and_multi_currency(self):
        weekly = summary(0, "2026-08-10", "2026-08-30", "week")
        self.assertEqual([row["key"] for row in weekly["buckets"]],
                         ["2026-08-10", "2026-08-17", "2026-08-24"])
        self.assertEqual([row["orders"] for row in weekly["buckets"]], [4, 0, 1])
        self.assertEqual(weekly["gmv"]["amount"], 200)
        self.assertEqual(weekly["gmv"]["missing_rate_orders"], 4)
        self.assertEqual(weekly["buckets"][0]["channels"]["FBP"]["orders"], 2)
        monthly = summary(2, "2026-07-01", "2026-09-30", "month")
        self.assertEqual([row["key"] for row in monthly["buckets"]],
                         ["2026-07-01", "2026-08-01", "2026-09-01"])
        self.assertEqual([row["orders"] for row in monthly["buckets"]], [0, 1, 0])
        self.assertEqual(monthly["gmv"], {"amount": 200.0, "currency": "CNY", "missing_rate_orders": 0})

    def test_date_picker_chart_accessibility_and_no_sync_side_effect(self):
        root = Path(__file__).parent.parent
        html = (root / "static/index.html").read_text()
        script = (root / "static/app.js").read_text()
        styles = (root / "static/style.css").read_text()
        self.assertIn('id="overviewDateRange"', html)
        self.assertIn('id="syncDateRange"', html)
        self.assertEqual(script.count("function createDateRange"), 1)
        self.assertIn('e.target.closest("[data-range-role]")', script)
        self.assertIn('overviewRange=createDateRange("#overviewDateRange",()=>loadOverview()', script)
        self.assertIn("onpointerover", script)
        self.assertIn("target.onfocus", script)
        self.assertIn("host.onclick", script)
        self.assertIn('tabindex="0"', script)
        self.assertIn(".trend-segment.channel-fbp", styles)
        self.assertIn("[data-theme=dark]", styles)
        overview_loader = script[script.index("async function loadOverview"):script.index("async function loadOrders")]
        self.assertNotIn("/api/sync", overview_loader)

    def test_exceptions_timeliness_and_top_products(self):
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO complaints VALUES(
              1,?,?,?,?,?,?,?,?,?,?,?)""", [
                ("OPEN", "MULTI", "2026-08-10T00:00:00Z", "平台", 0, None, None, None, "", "now", "now"),
                ("DONE", "MULTI", "2026-08-10T00:00:00Z", "平台", 1, None, None, None, "", "now", "now")])
            connection.executemany("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,status_raw,payload,fetched_at) VALUES(1,?,?,?,?,?)""", [
                (1, "R1", "AwaitingProcessing", "{}", "now"),
                (2, "R2", "MoneyReturned", "{}", "now"),
                (3, "R3", "UnmappedStatus", "{}", "now")])
            connection.execute("UPDATE orders SET data_anomaly=1 WHERE posting_number='MULTI'")
            connection.execute("""INSERT INTO stock_snapshots VALUES(
              1,'old','2026-08-19T00:00:00Z',?)""", ('{"product_id":"OLD","stocks":[{"sku":"OLD","present":0}]}',))
            connection.executemany("INSERT INTO stock_snapshots VALUES(1,?,'2026-08-20T00:00:00Z',?)", [
                ("zero", '{"product_id":"ZERO","stocks":[{"sku":"ZERO","present":0}]}'),
                ("low", '{"product_id":"LOW","stocks":[{"sku":"LOW","present":2}]}')])
            connection.execute("""INSERT INTO product_groups(name,created_at,updated_at)
              VALUES('热销组合','now','now')""")
            group_id = connection.execute("SELECT id FROM product_groups WHERE name='热销组合'").fetchone()[0]
            connection.executemany("INSERT INTO product_group_members VALUES(?,'sku',?)",
                                   [(group_id, "TIM-A"), (group_id, "TIM-B")])
            connection.execute("INSERT INTO product_group_members VALUES(?,'offer_id','TIM-MAIN')", (group_id,))
            connection.execute("INSERT INTO product_group_config VALUES(?,'TIM-MAIN','TIM-A','active','')", (group_id,))
            connection.execute("INSERT INTO product_short_names VALUES('sku','TIM-A','热销短名','now')")
            for index in range(30):
                posting = f"TIM-{index}"
                connection.execute("""INSERT INTO orders(shop_id,posting_number,channel,created_at,
                  shipped_at,delivered_at,status_raw,shipped,source) VALUES(1,?,'FBP',
                  '2026-08-10T00:00:00Z','2026-08-11T00:00:00Z','2026-08-13T00:00:00Z','已签收',1,'api')""",
                                   (posting,))
                sku = "TIM-A" if index < 15 else "TIM-B"
                connection.execute("""INSERT INTO order_items(shop_id,channel,posting_number,sku,
                  offer_id,product_name_raw,quantity,source) VALUES(1,'FBP',?,?,?,?,1,'api')""",
                                   (posting, sku, "TIM-MAIN" if sku == "TIM-A" else "TIM-B-O", "原始名称"))
            connection.execute("""INSERT INTO order_items(shop_id,channel,posting_number,sku,
              product_name_raw,quantity,source) VALUES(1,'FBP','MULTI','LOW','低库存商品',30,'api')""")

        data = summary(1, "2026-08-10", "2026-08-16", "week")
        self.assertEqual(data["exceptions"], {"unresolved_complaints": 1, "pending_returns": 1,
                         "stockout_skus": 1, "low_stock_skus": 1, "anomaly_orders": 1})
        fbp = data["timeliness"][0]
        self.assertEqual((fbp["ship_samples"], fbp["delivery_samples"]), (30, 30))
        self.assertEqual((fbp["p50_ship_hours"], fbp["p50_delivery_hours"],
                          fbp["p90_delivery_hours"]), (24, 48, 48))
        self.assertFalse(fbp["ship_sample_insufficient"])
        self.assertEqual(data["top_products"][0]["name"], "热销短名")
        self.assertEqual((data["top_products"][0]["pieces"], data["top_products"][0]["orders"]), (30, 30))

    def test_overview_panels_and_links_are_present(self):
        root = Path(__file__).parent.parent
        html = (root / "static/index.html").read_text()
        script = (root / "static/app.js").read_text()
        styles = (root / "static/style.css").read_text()
        for value in ("overviewExceptions", "overviewTimeliness", "overviewTopProducts"):
            self.assertIn(f'id="{value}"', html)
        self.assertIn('data-overview-page', script)
        self.assertIn('openPage(page)', script)
        self.assertIn('.overview-analysis-grid', styles)
        self.assertIn('@media(max-width:600px)', styles)


if __name__ == "__main__":
    unittest.main()
