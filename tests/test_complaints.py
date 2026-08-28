import asyncio
import json
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import db
from app.main import (_complaint_deadline, export_module, received_disputes, returns,
                      rfbs_returns, save_complaint, save_received_dispute,
                      shipping_complaints)
from tests.support import DatabaseTestCase, MockRequest as Request


class ComplaintsTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO orders(
              shop_id,posting_number,channel,created_at,shipped_at,status_changed_at,status_raw,
              shipped,data_anomaly,amount_original,amount_currency,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", [
                (1, "P-1", "FBP", "2026-08-01T00:00:00Z", "2026-08-02T00:00:00Z",
                 "2026-08-03T00:00:00Z", "已取消", 1, 0, 10, "USD", "api"),
                (1, "P-2", "realFBS", "2026-08-02T00:00:00Z", "2026-08-02T12:00:00Z",
                 "2026-08-03T00:00:00Z", "已取消", 1, 0, 20, "USD", "api"),
                (1, "PRE", "FBP", "2026-08-02T00:00:00Z", None,
                 "2026-08-02T01:00:00Z", "已取消", 0, 0, 30, "USD", "api"),
                (2, "ANOM", "WHD", "2026-08-03T00:00:00Z", None, None,
                 "处理中", 0, 1, 40, "CNY", "api"),
            ])
            connection.executemany("""INSERT INTO order_items(
              shop_id,channel,posting_number,sku,offer_id,product_name_raw,quantity,source)
              VALUES(?,?,?,?,?,?,?,?)""", [
                (1, "FBP", "P-1", "SKU-1", "OFFER-1", "Product 1", 1, "api"),
                (1, "realFBS", "P-2", "SKU-2", "OFFER-2", "Product 2", 2, "api"),
                (1, "FBP", "PRE", "SKU-P", "OFFER-P", "Pre", 1, "api"),
                (2, "WHD", "ANOM", "SKU-A", "OFFER-A", "Anomaly", 1, "api"),
            ])
            connection.execute("UPDATE orders SET tracking_number='TRACK-P1' WHERE posting_number='P-1'")
            connection.executemany("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,posting_number,offer_id,sku,product_name,
              status_raw,payload,fetched_at,product_amount,product_currency,reason_raw) VALUES(
              ?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
                (1, 1, "RET-1", "2026-08-04T00:00:00Z", "P-1", "OFFER-1", "SKU-1",
                 "Product 1", "Open", "{}", "2026-08-04T00:00:00Z", 10, "USD", "Reason 1"),
                (1, 2, "RET-2", "2026-08-05T00:00:00Z", "P-1", "OFFER-1", "SKU-1",
                 "Product 1", "Open", "{}", "2026-08-05T00:00:00Z", 10, "USD", "Reason 2"),
                (2, 3, "RET-3", "2026-08-06T00:00:00Z", "ANOM", "OFFER-A", "SKU-A",
                 "Anomaly", "Open", "{}", "2026-08-06T00:00:00Z", 40, "CNY", "Reason 3"),
            ])

    def save_shipping(self, posting, number, resolved=None):
        asyncio.run(save_complaint(Request({
            "shop_id": 1, "posting_number": posting, "complaint_number": number,
            "complaint_at": "2026-08-07T00:00:00Z", "channel": "Ozon",
            "resolved": resolved, "package_returned": None,
        })))

    def test_complaint_number_can_link_orders_and_order_can_have_many_complaints(self):
        self.save_shipping("P-1", "CASE-1")
        self.save_shipping("P-2", "CASE-1")
        self.save_shipping("P-1", "CASE-2", True)
        with db.connect() as connection:
            rows = connection.execute("""SELECT complaint_number,posting_number FROM complaints
              ORDER BY complaint_number,posting_number""").fetchall()
            self.assertEqual([tuple(row) for row in rows],
                             [("CASE-1", "P-1"), ("CASE-1", "P-2"), ("CASE-2", "P-1")])
            self.assertEqual(connection.execute("""SELECT resolved FROM complaints
              WHERE shop_id=1 AND posting_number='P-1' AND complaint_number='CASE-2'""").fetchone()[0], 1)

    def test_shipping_candidates_exclude_pre_ship_cancel_and_combine_filters(self):
        self.save_shipping("P-1", "CASE-1")
        data = shipping_complaints(1, q="OFFER-1", status="open",
                                   date_from="2026-08-01", date_to="2026-08-03")
        self.assertEqual([row["posting_number"] for row in data["items"]], ["P-1"])
        self.assertEqual(shipping_complaints(1, q="PRE")["total"], 0)
        self.assertEqual(shipping_complaints(2, status="unfiled")["items"][0]["posting_number"], "ANOM")
        tracked = shipping_complaints(1, q="TRACK-P1")
        self.assertEqual((tracked["total"], tracked["items"][0]["tracking_number"]), (1, "TRACK-P1"))

    def test_fixed_deadline_uses_beijing_date_plus_thirty_days_and_all_statuses(self):
        beijing = ZoneInfo("Asia/Shanghai")
        self.assertEqual(_complaint_deadline("2026-08-19T15:50:00Z", now=date(2026, 8, 24)), {
            "complaint_deadline": "2026-09-18", "complaint_deadline_status": "normal"})
        self.assertEqual(_complaint_deadline("2026-08-19T16:10:00Z", now=date(2026, 8, 24))[
            "complaint_deadline"], "2026-09-19")
        base = "2026-08-01T00:00:00Z"
        expected = ((date(2026, 8, 20), "normal"), (date(2026, 8, 24), "due_soon"),
                    (date(2026, 8, 31), "due_today"), (date(2026, 9, 1), "overdue"))
        for today, status in expected:
            self.assertEqual(_complaint_deadline(base, now=today)["complaint_deadline_status"], status)
        self.assertEqual(_complaint_deadline(base, now=datetime(2026, 8, 24, tzinfo=beijing))[
            "complaint_deadline_status"], "due_soon")
        self.assertEqual(_complaint_deadline(None), {
            "complaint_deadline": None, "complaint_deadline_status": "missing"})

    def test_four_endpoints_share_fixed_deadline_and_client_cannot_override_it(self):
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO return_records(
              shop_id,record_key,occurred_at,posting_number,sku,payload,fetched_at)
              VALUES(?,?,?,?,?,?,?)""", [
                (1, "R-P1", "2026-08-10T00:00:00Z", "P-1", "SKU-1",
                 '{"product":{"name":"Product 1","quantity":1,"offer_id":"OFFER-1"}}',
                 "2026-08-10T00:00:00Z"),
                (2, "R-ANOM", "2026-08-08T16:10:00Z", "ANOM", "SKU-A",
                 '{"product":{"name":"Anomaly","quantity":1,"offer_id":"OFFER-A"}}',
                 "2026-08-08T16:10:00Z"),
            ])
        cancel_detail = returns(1, q="P-1")["items"][0]
        shipping = shipping_complaints(1, q="P-1")["items"][0]
        fallback = shipping_complaints(2, q="ANOM")["items"][0]
        return_detail = rfbs_returns(1, q="RET-1")["items"][0]
        received = received_disputes(1, q="RET-1")["items"][0]
        self.assertEqual(cancel_detail["cancelled_at"], "2026-08-03T00:00:00Z")
        self.assertEqual(cancel_detail["complaint_deadline"], "2026-09-02")
        self.assertEqual(shipping["complaint_deadline"], cancel_detail["complaint_deadline"])
        self.assertEqual(fallback["complaint_deadline"], "2026-09-08")
        self.assertEqual(return_detail["complaint_deadline"], "2026-09-03")
        self.assertEqual(received["complaint_deadline"], return_detail["complaint_deadline"])
        self.assertEqual(rfbs_returns(1, q="RET-2")["items"][0]["complaint_deadline"], "2026-09-04")
        for item in (cancel_detail, shipping, fallback, return_detail, received):
            self.assertIn(item["complaint_deadline_status"],
                          {"normal", "due_soon", "due_today", "overdue", "missing"})

        asyncio.run(save_complaint(Request({
            "shop_id": 1, "posting_number": "P-1", "complaint_number": "CASE-DEADLINE",
            "complaint_at": "2026-08-30T00:00:00Z", "channel": "Ozon",
            "complaint_deadline": "2099-01-01",
        })))
        self.assertEqual(shipping_complaints(1, q="CASE-DEADLINE")["items"][0][
            "complaint_deadline"], "2026-09-02")
        with db.connect() as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(complaints)")}
        self.assertNotIn("complaint_deadline", columns)

    def test_returns_keep_separate_applications_and_manual_data_survives_platform_update(self):
        asyncio.run(save_received_dispute(Request({
            "shop_id": 1, "return_number": "RET-1", "refund_type": "部分退款",
            "refund_amount": 3.5, "refund_currency": "USD",
            "platform_compensation_rub": 900, "platform_compensated_at": "2026-08-22T08:00",
            "logistics_compensation_cny": 120, "logistics_compensated_at": "2026-08-22T08:00",
            "return_method": "IML",
            "return_result": "已签收", "notes": "manual",
        })))
        asyncio.run(save_received_dispute(Request({"shop_id": 1, "return_number": "RET-2"})))
        with db.transaction() as connection:
            connection.execute("""UPDATE rfbs_return_records SET status_raw='Closed',payload='{}'
              WHERE shop_id=1 AND return_number='RET-1'""")
        rows = received_disputes(1, q="P-1")["items"]
        self.assertEqual({row["return_number"] for row in rows}, {"RET-1", "RET-2"})
        item = next(row for row in rows if row["return_number"] == "RET-1")
        self.assertEqual((item["refund_amount"], item["return_method"], item["return_result"], item["notes"]),
                         (3.5, "IML", "已签收", "manual"))
        self.assertEqual((item["platform_compensation_rub"], item["logistics_compensation_cny"]),
                         ("900", "120"))
        return_item = next(row for row in rfbs_returns(1)["items"] if row["return_number"] == "RET-1")
        self.assertEqual((return_item["refund_amount"], return_item["return_method"],
                          return_item["return_result"]), (3.5, "IML", "已签收"))

    def test_compensation_conversion_pair_validation_and_dynamic_rate_recovery(self):
        body = {"shop_id": 1, "return_number": "RET-1",
                "refund_amount": 65.94, "refund_currency": "USD",
                "platform_compensation_rub": 5158, "platform_compensated_at": "2026-08-22T08:00",
                "logistics_compensation_cny": 1000, "logistics_compensated_at": "2026-08-22T08:00"}
        asyncio.run(save_received_dispute(Request(body)))
        missing = received_disputes(1, q="RET-1")["items"][0]
        self.assertEqual(missing["refund_amount"], 65.94)
        self.assertTrue(missing["platform_compensation_missing_rate"])
        self.assertTrue(missing["logistics_compensation_missing_rate"])
        self.assertIsNone(missing["platform_compensation_converted_amount"])
        with db.connect() as connection:
            stored = connection.execute("""SELECT platform_compensated_at,logistics_compensated_at
              FROM rfbs_return_disputes WHERE shop_id=1 AND return_number='RET-1'""").fetchone()
        self.assertEqual(tuple(stored), ("2026-08-22T00:00:00Z", "2026-08-22T00:00:00Z"))

        with db.transaction() as connection:
            connection.executemany("""INSERT INTO exchange_rates VALUES(
              ?,'RUB','2026-08-21T21:00:00Z','2026-08-22T21:00:00Z',?,'9999','ozon_xapi','2026-08-22T22:00:00Z')""", [
                ("USD", "80"), ("CNY", "10.666666666666666666")])
        converted = received_disputes(1, q="RET-1")["items"][0]
        self.assertEqual(converted["platform_compensation_converted_amount"], "64.48")
        self.assertEqual(converted["logistics_compensation_converted_amount"], "133.33")
        self.assertFalse(converted["platform_compensation_missing_rate"])
        self.assertEqual(converted["platform_compensation_original_currency"], "RUB")
        self.assertEqual(converted["logistics_compensation_original_currency"], "CNY")

        for invalid in (
            {"platform_compensation_rub": 1}, {"platform_compensated_at": "2026-08-22T08:00"},
            {"logistics_compensation_cny": 0, "logistics_compensated_at": "2026-08-22T08:00"},
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(save_received_dispute(Request({"shop_id": 1, "return_number": "RET-2", **invalid})))
            self.assertEqual(raised.exception.status_code, 400)

    def test_cny_shop_logistics_needs_no_rate_and_shipping_fields_are_independent(self):
        asyncio.run(save_received_dispute(Request({
            "shop_id": 2, "return_number": "RET-3", "refund_amount": 8, "refund_currency": "CNY",
            "logistics_compensation_cny": 100, "logistics_compensated_at": "2026-08-22T08:00",
        })))
        item = received_disputes(2, q="RET-3")["items"][0]
        self.assertEqual(item["logistics_compensation_converted_amount"], "100.00")
        self.assertFalse(item["logistics_compensation_missing_rate"])
        self.assertEqual((item["refund_amount"], item["platform_compensation_rub"],
                          item["logistics_compensation_cny"]), (8, None, "100"))

        asyncio.run(save_complaint(Request({
            "shop_id": 1, "posting_number": "P-1", "complaint_number": "CASE-COMP",
            "complaint_at": "2026-08-22T00:00:00Z", "channel": "Ozon",
            "platform_compensation_rub": 800, "platform_compensated_at": "2026-08-22T08:00",
            "logistics_compensation_cny": 80, "logistics_compensated_at": "2026-08-22T08:00",
        })))
        complaint = shipping_complaints(1, q="CASE-COMP")["items"][0]["complaints"][0]
        self.assertEqual((complaint["platform_compensation_rub"], complaint["logistics_compensation_cny"]),
                         ("800", "80"))

    def test_compensation_fields_are_exported(self):
        asyncio.run(save_received_dispute(Request({
            "shop_id": 1, "return_number": "RET-1",
            "platform_compensation_rub": 90, "platform_compensated_at": "2026-08-04T08:00",
        })))

        async def rows(module):
            return [json.loads(line) async for line in export_module(
                module, 1, "2026-08-01", "2026-08-31").body_iterator]

        item = next(row for row in asyncio.run(rows("returns")) if row.get("return_number") == "RET-1")
        self.assertEqual(item["platform_compensation_rub"], "90")
        self.assertEqual(item["platform_compensation_original_currency"], "RUB")

        complaint_rows = asyncio.run(rows("complaints"))
        received = next(row for row in complaint_rows if row.get("return_number") == "RET-1")
        self.assertEqual(received["record_type"], "已收货纠纷")
        self.assertEqual(received["platform_compensation_rub"], "90")
        self.assertIn("complaint_deadline", received)

    def test_shop_currency_defaults_and_received_filters(self):
        for shop_id, number in ((1, "RET-1"), (2, "RET-3")):
            asyncio.run(save_received_dispute(Request({
                "shop_id": shop_id, "return_number": number, "refund_amount": 2,
                "process_status": "处理中",
            })))
        self.assertEqual(received_disputes(1, q="SKU-1", status="open")["items"][0]["refund_currency"], "USD")
        self.assertEqual(received_disputes(2, q="RET-3", status="open")["items"][0]["refund_currency"], "CNY")
        self.assertEqual(received_disputes(1, q="Reason 1")["total"], 0)
