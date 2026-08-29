import unittest
from datetime import datetime

from fastapi import HTTPException

from app import db
from app.main import BEIJING, _trend_range, order_trend, summary
from app.routers.common import _overview_range
from tests.support import DatabaseTestCase


class OverviewRegressionTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
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
        self.assertEqual(data["totals"]["cancelled_pieces"], 1)
        self.assertAlmostEqual(data["totals"]["cancel_rate"], 1 / 7)
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

    def test_order_trend_fixed_ranges(self):
        fixed_now = datetime(2026, 8, 23, 12, tzinfo=BEIJING)
        start_d, end_d, _, _ = _trend_range("day", fixed_now)
        self.assertEqual((end_d - start_d).days + 1, 90)
        start_w, end_w, _, _ = _trend_range("week", fixed_now)
        self.assertEqual((end_w - start_w).days + 1, 12 * 7)
        start_m, end_m, _, _ = _trend_range("month", fixed_now)
        self.assertEqual(start_m.isoformat(), "2025-09-01")
        self.assertEqual(end_m.isoformat(), "2026-08-31")

        trend_day = order_trend(1, "day")
        self.assertEqual(len(trend_day["buckets"]), 90)
        trend_week = order_trend(0, "week")
        self.assertEqual(len(trend_week["buckets"]), 12)
        trend_month = order_trend(2, "month")
        self.assertEqual(len(trend_month["buckets"]), 12)

        with self.assertRaises(HTTPException):
            order_trend(99, "day")
        with self.assertRaises(HTTPException):
            order_trend(1, "year")
