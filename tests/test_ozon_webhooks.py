import asyncio
import json
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException, Response

from app import db, main
from app.main import WEBHOOK_MAX_BODY_BYTES, ozon_webhook, protect_api, stock
from app.ozon import client, sync, webhooks
from tests.support import DatabaseTestCase, add_item, add_order, add_stock_snapshot


class WebhookRequest:
    def __init__(self, value, headers=None):
        self.raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.headers = {"content-length": str(len(self.raw)), **(headers or {})}

    async def stream(self):
        yield self.raw
        yield b""


ENV = {
    "OZON_WEBHOOK_SECRET_1": "secret-one",
    "OZON_WEBHOOK_SECRET_2": "secret-two",
    "SHOP_1_OZON_CLIENT_ID": "101",
    "SHOP_2_OZON_CLIENT_ID": "202",
}


class OzonWebhookTest(DatabaseTestCase):
    def order(self, posting, channel="realFBS", status="运输中", shipped=1):
        with db.transaction() as connection:
            add_order(connection, 1, posting, channel, status_raw=status, shipped=shipped)

    def test_ping_is_public_and_other_api_is_not(self):
        with patch("app.main._env", return_value=ENV):
            result = asyncio.run(ozon_webhook("secret-one", WebhookRequest({"message_type": "TYPE_PING"})))
        self.assertEqual(result["version"], "1.0.0")
        self.assertEqual(result["name"], "oPanel")
        self.assertTrue(result["time"].endswith("Z"))

        async def next_response(_):
            return Response(status_code=204)

        webhook_request = main.Request({
            "type": "http", "method": "POST", "path": "/api/webhooks/ozon/secret-one",
            "raw_path": b"/api/webhooks/ozon/secret-one", "query_string": b"", "headers": [],
            "scheme": "http", "server": ("test", 80), "client": ("test", 1),
        })
        self.assertEqual(asyncio.run(protect_api(webhook_request, next_response)).status_code, 204)

        request = main.Request({
            "type": "http", "method": "POST", "path": "/api/shops", "raw_path": b"/api/shops",
            "query_string": b"", "headers": [], "scheme": "http", "server": ("test", 80),
            "client": ("test", 1),
        })
        self.assertEqual(asyncio.run(protect_api(request, next_response)).status_code, 401)

    def test_bad_secret_size_and_required_fields_are_rejected(self):
        with patch("app.main._env", return_value=ENV):
            for secret in ("wrong", "secret-one"):
                request = WebhookRequest({"message_type": "TYPE_POSTING_CANCELLED"})
                if secret == "wrong":
                    with self.assertRaisesRegex(HTTPException, "Webhook密钥无效"):
                        asyncio.run(ozon_webhook(secret, request))
                else:
                    with self.assertRaisesRegex(HTTPException, "posting_number"):
                        asyncio.run(ozon_webhook(secret, request))
            request = WebhookRequest(b"{" + b"x" * WEBHOOK_MAX_BODY_BYTES)
            with self.assertRaisesRegex(HTTPException, "请求体过大"):
                asyncio.run(ozon_webhook("secret-one", request))
            with self.assertRaisesRegex(HTTPException, "JSON无效"):
                asyncio.run(ozon_webhook("secret-one", WebhookRequest(b"not-json")))

    def test_seller_id_is_checked(self):
        payload = {"message_type": "TYPE_ORDER_NEW", "order_number": "O-1", "seller_id": 999}
        with patch("app.main._env", return_value=ENV), self.assertRaisesRegex(HTTPException, "店铺身份"):
            asyncio.run(ozon_webhook("secret-one", WebhookRequest(payload)))

    def test_new_posting_is_persisted_then_completed_from_detail(self):
        payload = {"message_type": "TYPE_NEW_POSTING", "posting_number": "P-NEW",
                   "integration_type_flow": "aggregator", "in_process_at": "2026-08-01T01:00:00Z",
                   "uuid": "event-new"}
        row = webhooks.persist_webhook_event(1, payload, "2026-08-01T01:01:00Z")
        detail = {"result": {"posting_number": "P-NEW", "order_number": "O-NEW",
                              "integration_type_flow": "aggregator", "status": "delivering",
                              "in_process_at": "2026-08-01T01:00:00Z", "products": [
                                  {"sku": 11, "offer_id": "A", "name": "商品", "quantity": 2, "price": "3.5"}]}}
        with patch("app.ozon.client._post", return_value=detail) as post:
            webhooks.complete_webhook_posting(1, row["event_key"])
        post.assert_called_once()
        self.assertEqual(post.call_args.args[1], "/v3/posting/fbs/get")
        with db.connect() as connection:
            order = connection.execute("SELECT channel,status_raw,amount_original FROM orders WHERE posting_number='P-NEW'").fetchone()
            item = connection.execute("SELECT sku,product_name_raw,quantity FROM order_items WHERE posting_number='P-NEW'").fetchone()
            applied = connection.execute("SELECT applied_at FROM ozon_webhook_events WHERE event_key='event-new'").fetchone()[0]
        self.assertEqual(tuple(order), ("realFBS", "运输中", 7.0))
        self.assertEqual(tuple(item), ("11", "商品", 2))
        self.assertIsNotNone(applied)

    def test_new_posting_only_wakes_shared_worker_and_stays_idempotent(self):
        payload = {"message_type": "TYPE_NEW_POSTING", "posting_number": "P-PENDING",
                   "in_process_at": "2026-08-01T01:00:00Z", "uuid": "pending-one"}
        with patch("app.ozon.webhooks.threading.Thread") as thread:
            webhooks.process_webhook_event(1, payload)
            duplicate = webhooks.process_webhook_event(1, payload)
        thread.assert_not_called()
        self.assertFalse(duplicate["new"])
        with db.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM ozon_webhook_events WHERE event_key='pending-one'").fetchone()[0], 1)

    def test_pending_worker_continues_after_failure_and_retries(self):
        for posting in ("P-FAIL", "P-NEXT"):
            webhooks.persist_webhook_event(1, {
                "message_type": "TYPE_NEW_POSTING", "posting_number": posting,
                "in_process_at": "2026-08-01T01:00:00Z", "uuid": posting,
            })
        attempts = {"P-FAIL": 0}

        def detail(_shop_id, _path, body):
            posting = body["posting_number"]
            if posting == "P-FAIL" and attempts[posting] == 0:
                attempts[posting] += 1
                raise RuntimeError("temporary")
            return {"result": {"posting_number": posting, "integration_type_flow": "aggregator",
                               "status": "awaiting_packaging", "products": []}}

        with patch("app.ozon.client._post", side_effect=detail):
            webhooks.process_pending_webhook_postings()
            with db.connect() as connection:
                rows = {row["event_key"]: tuple(row)[1:] for row in connection.execute(
                    "SELECT event_key,applied_at,error FROM ozon_webhook_events ORDER BY event_key")}
            self.assertIsNone(rows["P-FAIL"][0])
            self.assertEqual(rows["P-FAIL"][1], "temporary")
            self.assertIsNotNone(rows["P-NEXT"][0])
            webhooks.process_pending_webhook_postings()
        with db.connect() as connection:
            row = connection.execute(
                "SELECT applied_at,error FROM ozon_webhook_events WHERE event_key='P-FAIL'").fetchone()
        self.assertIsNotNone(row["applied_at"])
        self.assertIsNone(row["error"])

    def test_worker_start_processes_pending_from_previous_process(self):
        webhooks.persist_webhook_event(1, {
            "message_type": "TYPE_NEW_POSTING", "posting_number": "P-RESTART",
            "in_process_at": "2026-08-01T01:00:00Z", "uuid": "restart-pending",
        })
        detail = {"result": {"posting_number": "P-RESTART", "integration_type_flow": "aggregator",
                             "status": "awaiting_packaging", "products": []}}
        try:
            with patch("app.ozon.client._post", return_value=detail):
                webhooks.start_webhook_worker()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    with db.connect() as connection:
                        applied = connection.execute(
                            "SELECT applied_at FROM ozon_webhook_events WHERE event_key='restart-pending'").fetchone()[0]
                    if applied:
                        break
                    time.sleep(.01)
        finally:
            webhooks.stop_webhook_worker()
        self.assertIsNotNone(applied)

    def test_service_lifespan_starts_and_stops_webhook_worker(self):
        async def run():
            with patch("app.main.migrate_env_password"), patch("app.main.start_scheduler"), \
                 patch("app.main.stop_scheduler"), patch("app.main._start_auto_sync_scheduler"), \
                 patch("app.main._stop_auto_sync_scheduler"), \
                 patch("app.main.start_webhook_worker") as start, \
                 patch("app.main.stop_webhook_worker") as stop:
                async with main.lifespan(main.app):
                    start.assert_called_once_with()
                stop.assert_called_once_with()

        asyncio.run(run())

    def test_fbs_and_fbo_cancel_fields_and_earliest_time(self):
        self.order("P-CANCEL")
        self.order("W-CANCEL", "WHD")
        fbs = {"message_type": "TYPE_POSTING_CANCELLED", "posting_number": "P-CANCEL",
               "changed_state_date": "2026-08-01T10:00:00Z", "reason": {"id": 79, "message": "fbs"},
               "uuid": "cancel-fbs"}
        fbo = {"message_type": "TYPE_FBO_POSTING_CANCELLED", "posting_number": "W-CANCEL",
               "cancel_date": "2026-08-01T11:00:00Z", "reason": {"id": 80, "message": "fbo"},
               "uuid": "cancel-fbo"}
        webhooks.process_webhook_event(1, fbs, "2026-08-01T12:00:00Z")
        webhooks.process_webhook_event(1, fbo, "2026-08-01T12:00:00Z")
        earlier = dict(fbs, uuid="cancel-fbs-earlier", changed_state_date="2026-08-01T09:00:00Z")
        webhooks.process_webhook_event(1, earlier, "2026-08-01T12:00:00Z")
        with db.connect() as connection:
            rows = connection.execute("""SELECT posting_number,status_raw,status_changed_at,
              cancel_reason_id,cancel_reason_raw FROM orders ORDER BY posting_number""").fetchall()
        self.assertEqual([tuple(row) for row in rows], [
            ("P-CANCEL", "已取消", "2026-08-01T09:00:00Z", "79", "fbs"),
            ("W-CANCEL", "已取消", "2026-08-01T11:00:00Z", "80", "fbo"),
        ])

    def test_state_events_are_time_ordered_and_delivery_is_recorded(self):
        self.order("P-STATE", status="待备货", shipped=0)
        delivered = {"message_type": "TYPE_STATE_CHANGED", "posting_number": "P-STATE",
                     "new_state": "posting_delivered", "changed_state_date": "2026-08-01T10:00:00Z",
                     "uuid": "state-delivered"}
        old = {"message_type": "TYPE_STATE_CHANGED", "posting_number": "P-STATE",
               "new_state": "posting_in_carriage", "changed_state_date": "2026-08-01T09:00:00Z",
               "uuid": "state-old"}
        webhooks.process_webhook_event(1, delivered)
        webhooks.process_webhook_event(1, old)
        with db.connect() as connection:
            row = connection.execute("SELECT status_raw,status_changed_at,shipped,delivered_at FROM orders WHERE posting_number='P-STATE'").fetchone()
        self.assertEqual(tuple(row), ("已签收", "2026-08-01T10:00:00Z", 1, "2026-08-01T10:00:00Z"))

    def test_old_cancellation_does_not_overwrite_newer_state(self):
        with db.transaction() as connection:
            add_order(connection, 1, "P-OLD-CANCEL", "realFBS", status_raw="已签收", shipped=1,
                      status_changed_at="2026-08-01T10:00:00Z", delivered_at="2026-08-01T10:00:00Z")
        webhooks.process_webhook_event(1, {
            "message_type": "TYPE_POSTING_CANCELLED", "posting_number": "P-OLD-CANCEL",
            "changed_state_date": "2026-08-01T09:00:00Z", "uuid": "old-cancel",
        })
        with db.connect() as connection:
            row = connection.execute("""SELECT status_raw,status_changed_at,delivered_at FROM orders
              WHERE posting_number='P-OLD-CANCEL'""").fetchone()
        self.assertEqual(tuple(row), ("已签收", "2026-08-01T10:00:00Z", "2026-08-01T10:00:00Z"))

    def test_event_waits_for_late_order_and_is_reapplied(self):
        payload = {"message_type": "TYPE_POSTING_CANCELLED", "posting_number": "P-LATE",
                   "changed_state_date": "2026-08-01T10:00:00Z", "reason": {"id": 7, "message": "late"},
                   "uuid": "cancel-late"}
        row = webhooks.process_webhook_event(1, payload)
        with db.connect() as connection:
            self.assertIsNone(connection.execute("SELECT applied_at FROM ozon_webhook_events WHERE event_key=?",
                                                 (row["event_key"],)).fetchone()[0])
        detail = {"result": {"posting_number": "P-LATE", "integration_type_flow": "FBP",
                              "status": "awaiting_packaging", "products": []}}
        with patch("app.ozon.client._post", return_value=detail):
            webhooks.complete_webhook_posting(1, row["event_key"])
        with db.connect() as connection:
            result = connection.execute("SELECT channel,status_raw,status_changed_at FROM orders WHERE posting_number='P-LATE'").fetchone()
        self.assertEqual(tuple(result), ("FBP", "已取消", "2026-08-01T10:00:00Z"))

    def test_uuid_and_canonical_payload_hash_are_idempotent(self):
        first = {"message_type": "TYPE_ORDER_NEW", "order_number": "O-1", "uuid": "same"}
        second = {"uuid": "same", "order_number": "O-2", "message_type": "TYPE_ORDER_NEW"}
        webhooks.persist_webhook_event(1, first)
        duplicate = webhooks.persist_webhook_event(1, second)
        self.assertFalse(duplicate["new"])
        left = {"message_type": "TYPE_ORDER_CANCELLED", "order_number": "O-2", "a": {"x": 1, "y": 2}}
        right = {"a": {"y": 2, "x": 1}, "order_number": "O-2", "message_type": "TYPE_ORDER_CANCELLED"}
        self.assertEqual(webhooks.webhook_event_key(left), webhooks.webhook_event_key(right))

    def test_order_events_are_saved_without_changing_orders(self):
        self.order("P-ORDER", status="待备货", shipped=0)
        payload = {"message_type": "TYPE_ORDER_STATE_CHANGED", "posting_number": "P-ORDER",
                   "order_number": "O-ORDER", "new_state": "cancelled"}
        row = webhooks.process_webhook_event(1, payload)
        with db.connect() as connection:
            status = connection.execute("SELECT status_raw FROM orders WHERE posting_number='P-ORDER'").fetchone()[0]
            saved = connection.execute("SELECT order_number,applied_at FROM ozon_webhook_events WHERE event_key=?",
                                       (row["event_key"],)).fetchone()
        self.assertEqual(status, "待备货")
        self.assertEqual(saved[0], "O-ORDER")
        self.assertIsNotNone(saved[1])

    def test_stock_push_sources_and_snapshot_overlay(self):
        fbs = {"message_type": "TYPE_STOCKS_CHANGED", "uuid": "stock-rfbs", "items": [{
            "sku": 11, "updated_at": "2026-08-01T11:00:00Z",
            "stocks": [{"warehouse_id": 1, "present": 9, "reserved": 2}]}]}
        fbo = {"message_type": "TYPE_FBO_STOCKS_CHANGED", "uuid": "stock-fbo", "sku": 12,
               "warehouse_id": 2, "updated_at": "2026-08-01T11:00:00Z",
               "stocks": {"new_present": 8, "new_reserved": 1}}
        webhooks.process_webhook_event(1, fbs)
        webhooks.process_webhook_event(1, fbo)
        with db.transaction() as connection:
            add_order(connection, 1, "STOCK-11", "realFBS", "2026-08-01T00:00:00Z", "运输中", 1)
            add_item(connection, 1, "STOCK-11", "realFBS", "11", offer_id="O-11",
                     product_name_raw="商品11")
            add_stock_snapshot(connection, 1, "base-11", "2026-08-01T10:00:00Z", {
                "offer_id": "O-11", "stocks": [{"sku": "11", "type": "fbp", "present": 4, "reserved": 0},
                                                    {"sku": "11", "type": "rfbs", "present": 3, "reserved": 0}]})
            add_stock_snapshot(connection, 1, "base-old", "2026-08-01T10:00:00Z", {
                "offer_id": "O-13", "stocks": [{"sku": "13", "type": "rfbs", "present": 6, "reserved": 0}]})
            connection.execute("""INSERT INTO stock_history(
              shop_id,source,warehouse_id,sku,present,reserved,occurred_at,event_key,payload_json)
              VALUES(1,'push_rfbs','3','13',99,0,'2026-08-01T09:00:00Z','old-push','{}')""")
        data = stock(1, size=100)
        values = {item["sku"]: item for item in data["items"]}
        self.assertEqual((values["11"]["fbp_present"], values["11"]["channels"][1]["present"]), (4, 9))
        self.assertEqual(values["13"]["channels"][1]["present"], 6)
        with db.connect() as connection:
            sources = {tuple(row) for row in connection.execute(
                "SELECT source,sku,present,reserved FROM stock_history WHERE event_key IN ('stock-rfbs','stock-fbo')")}
        self.assertEqual(sources, {("push_rfbs", "11", 9, 2), ("push_fbo", "12", 8, 1)})

    def test_full_order_sync_does_not_overwrite_push_cancel(self):
        self.order("P-PUSH", status="已取消", shipped=1)
        webhooks.process_webhook_event(1, {"message_type": "TYPE_POSTING_CANCELLED", "posting_number": "P-PUSH",
                                       "changed_state_date": "2026-08-01T10:00:00Z", "uuid": "push-cancel"})
        posting = {"posting_number": "P-PUSH", "integration_type_flow": "aggregator", "status": "delivering",
                   "products": []}
        with patch("app.ozon.client._cursor_pages", side_effect=[[posting], []]):
            sync.sync_orders(1, datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 8, 2, tzinfo=timezone.utc))
        with db.connect() as connection:
            self.assertEqual(tuple(connection.execute(
                "SELECT status_raw,shipped,status_changed_at FROM orders WHERE posting_number='P-PUSH'").fetchone()),
                             ("已取消", 1, "2026-08-01T10:00:00Z"))

    def test_notification_management_uses_current_api_shapes(self):
        with patch("app.ozon.client._post", return_value={}) as post:
            client.notification_set(1, "https://example.test/api/webhooks/ozon/secret", ["TYPE_NEW_POSTING"])
            client.notification_enable(1, 7, True)
            client.notification_delete(1, 7)
        self.assertEqual([call.args[1] for call in post.call_args_list], [
            "/v1/notification/set", "/v1/notification/enable", "/v1/notification/delete"])
        self.assertEqual(post.call_args_list[1].args[2], {"id": 7, "enabled": True})
