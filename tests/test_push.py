import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db
from app.dingtalk import daily_message
from app.main import orders, ozon_push, shops
from app.push import PUSH_TYPES, PushAuthError, push_settings, receive_push, retry_pending, save_seller_ids


class Request:
    def __init__(self, payload, content_type="application/json"):
        self.data = json.dumps(payload).encode()
        self.headers = {"content-type": content_type, "content-length": str(len(self.data))}
        self.scope = {"path": "/api/ozon/push/token", "raw_path": b"/api/ozon/push/token"}

    async def body(self):
        return self.data


class PushTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()
        save_seller_ids({"1": "1001", "2": "2002"})
        with db.connect() as connection:
            self.tokens = dict(connection.execute("SELECT id,push_token FROM shops"))

    def tearDown(self):
        self.temp.cleanup()

    def send(self, shop_id, payload):
        return asyncio.run(ozon_push(self.tokens[shop_id], Request(payload)))

    def test_ping_and_all_eight_business_events(self):
        ping = self.send(1, {"message_type": "TYPE_PING", "time": "2026-08-20T00:00:00Z"})
        self.assertEqual(ping["name"], "FUCK Ozon")
        self.assertTrue(ping["version"])
        self.assertTrue(ping["time"].endswith("Z"))

        events = [
            {"message_type": "TYPE_NEW_POSTING", "seller_id": 1001, "posting_number": "F-1",
             "integration_type_flow": "aggregator", "in_process_at": "2026-08-20T03:00:00+03:00",
             "warehouse_id": 10, "products": [{"sku": 1, "offer_id": "A", "quantity": 2}]},
            {"message_type": "TYPE_POSTING_CANCELLED", "seller_id": 1001, "posting_number": "F-1",
             "new_state": "posting_canceled", "changed_state_date": "2026-08-20T02:00:00Z",
             "warehouse_id": 10, "reason": {"id": 1, "message": "Покупатель не забрал заказ"},
             "products": [{"sku": 1, "quantity": 2}], "buyer_comment": "自由文本"},
            {"message_type": "TYPE_STATE_CHANGED", "seller_id": 1001, "posting_number": "F-1",
             "new_state": "delivering", "changed_state_date": "2026-08-20T03:00:00Z", "warehouse_id": 10},
            {"message_type": "TYPE_FBO_POSTING_NEW", "seller_id": 1001, "uuid": "fbo-new",
             "posting_number": "W-1", "order_number": "M-1", "creation_date": "2026-08-20T00:00:00Z",
             "warehouse_id": 20, "products": [{"sku": 2, "offer_id": "B", "quantity": 1}]},
            {"message_type": "TYPE_FBO_POSTING_CANCELLED", "seller_id": 1001, "uuid": "fbo-cancel",
             "posting_number": "W-1", "order_number": "M-1", "new_state": "cancelled",
             "cancel_date": "2026-08-20T04:00:00Z", "reason": {"id": 2, "message": "未知俄语原因"}},
            {"message_type": "TYPE_FBO_POSTING_STATE_CHANGED", "seller_id": 1001, "uuid": "fbo-state",
             "posting_number": "W-1", "order_number": "M-1", "new_state": "delivered",
             "changed_state_date": "2026-08-20T05:00:00Z", "warehouse_id": 20},
            {"message_type": "TYPE_STOCKS_CHANGED", "seller_id": 1001, "items": [{"sku": 3,
             "product_id": 30, "updated_at": "2026-08-20T06:00:00Z",
             "stocks": [{"warehouse_id": 10, "present": 7, "reserved": 2}]}]},
            {"message_type": "TYPE_FBO_STOCKS_CHANGED", "seller_id": 1001,
             "stocks": {"sku": 4, "updated_at": "2026-08-20T07:00:00Z",
                        "new_present": 8, "new_reserved": 1, "old_present": 6, "old_reserved": 0}},
        ]
        with patch("app.ozon._post") as ozon_call:
            for event in events:
                self.assertEqual(self.send(1, event), {"result": True})
        ozon_call.assert_not_called()

        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM webhook_events").fetchone()[0], 9)
            self.assertEqual(connection.execute("SELECT channel FROM orders WHERE posting_number='F-1'").fetchone()[0], "realFBS")
            self.assertEqual(connection.execute("SELECT channel FROM orders WHERE posting_number='W-1'").fetchone()[0], "WHD")
            self.assertEqual(tuple(connection.execute(
                "SELECT shipped,shipped_at,delivered_at FROM orders WHERE posting_number='W-1'").fetchone()),
                (1, "2026-08-20T05:00:00Z", "2026-08-20T05:00:00Z"))
            self.assertEqual(connection.execute("SELECT created_at FROM orders WHERE posting_number='F-1'").fetchone()[0], "2026-08-20T00:00:00Z")
            self.assertEqual(tuple(connection.execute("SELECT present,reserved FROM warehouse_stocks").fetchone()), (7, 2))
            self.assertEqual(tuple(connection.execute("SELECT new_present,new_reserved FROM fbo_stocks").fetchone()), (8, 1))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM finance_records").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM return_records").fetchone()[0], 0)
        script = (Path(__file__).parent.parent / "static/app.js").read_text()
        self.assertIn('timeZone:"Asia/Shanghai"', script)

    def test_tokens_sellers_idempotency_ordering_and_pending_channel(self):
        event = {"message_type": "TYPE_FBO_POSTING_NEW", "seller_id": 1001, "uuid": "same",
                 "posting_number": "W-2", "creation_date": "2026-08-20T00:00:00Z",
                 "products": [{"sku": 5, "offer_id": "KEEP", "name": "保留名称", "quantity": 3}]}
        self.assertEqual(receive_push(self.tokens[1], event), {"result": True})
        self.assertEqual(receive_push(self.tokens[1], event), {"result": True})
        self.assertEqual(receive_push(self.tokens[2], {**event, "seller_id": 2002,
                                                       "posting_number": "W-2-SHOP-2"}), {"result": True})
        newer = {"message_type": "TYPE_FBO_POSTING_STATE_CHANGED", "seller_id": 1001, "uuid": "newer",
                 "posting_number": "W-2", "new_state": "delivered", "changed_state_date": "2026-08-20T10:00:00Z"}
        older = {"message_type": "TYPE_FBO_POSTING_STATE_CHANGED", "seller_id": 1001, "uuid": "older",
                 "posting_number": "W-2", "new_state": "awaiting_packaging", "changed_state_date": "2026-08-20T09:00:00Z"}
        receive_push(self.tokens[1], newer)
        receive_push(self.tokens[1], older)
        receive_push(self.tokens[1], {**event, "uuid": "empty", "products": [{"sku": 5, "quantity": 3}]})
        pending = {"message_type": "TYPE_NEW_POSTING", "seller_id": 1001, "posting_number": "UNKNOWN",
                   "in_process_at": "2026-08-20T00:00:00Z", "products": [{"sku": 6, "quantity": 1}]}
        self.assertEqual(receive_push(self.tokens[1], pending), {"result": True})
        with self.assertRaises(PushAuthError):
            receive_push(self.tokens[1], {**event, "seller_id": 2002, "uuid": "wrong", "posting_number": "BAD"})
        with db.connect() as connection:
            order = connection.execute("SELECT status_raw,channel FROM orders WHERE posting_number='W-2'").fetchone()
            item = connection.execute("SELECT offer_id,product_name_raw,quantity FROM order_items WHERE posting_number='W-2'").fetchone()
            self.assertEqual(tuple(order), ("已签收", "WHD"))
            self.assertEqual(tuple(item), ("KEEP", "保留名称", 3))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM order_status_history WHERE posting_number='W-2'").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT processing_status FROM webhook_events WHERE event_key=(SELECT event_key FROM webhook_events WHERE payload_json LIKE '%UNKNOWN%')").fetchone()[0], "pending_match")
            self.assertIsNone(connection.execute("SELECT posting_number FROM orders WHERE posting_number IN ('UNKNOWN','BAD')").fetchone())
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders WHERE posting_number='W-2'").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders WHERE shop_id=2 AND posting_number='W-2-SHOP-2'").fetchone()[0], 1)
        with db.transaction() as connection:
            connection.execute("""INSERT INTO orders(shop_id,posting_number,channel,status_raw,shipped,source)
              VALUES(1,'UNKNOWN','FBP','',0,'api')""")
        with db.connect() as connection:
            event_id = connection.execute("""SELECT id FROM webhook_events
              WHERE processing_status='pending_match'""").fetchone()[0]
        retry_pending(event_id)
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT processing_status FROM webhook_events WHERE id=?",
                                                (event_id,)).fetchone()[0], "processed")

    def test_cancellation_preserves_manual_data_and_fixed_reason_only(self):
        receive_push(self.tokens[1], {"message_type": "TYPE_FBO_POSTING_NEW", "seller_id": 1001,
                     "uuid": "manual-new", "posting_number": "W-3", "creation_date": "2026-08-19T00:00:00Z",
                     "products": [{"sku": 7, "quantity": 1}]})
        with db.transaction() as connection:
            connection.execute("""INSERT INTO order_manual_data(
              shop_id,posting_number,complaint_number,notes,compensation_amount) VALUES(1,'W-3','C-1','人工备注',12.5)""")
            connection.execute("UPDATE orders SET shipped=1,shipped_at='2026-08-19T00:30:00Z' WHERE posting_number='W-3'")
        cancel = {"message_type": "TYPE_FBO_POSTING_CANCELLED", "seller_id": 1001, "uuid": "manual-cancel",
                  "posting_number": "W-3", "new_state": "cancelled", "cancel_date": "2026-08-19T01:00:00Z",
                  "reason": {"id": 1, "message": "Покупатель не забрал заказ"}, "buyer_comment": "不要发送"}
        receive_push(self.tokens[1], cancel)
        with db.connect() as connection:
            manual = connection.execute("SELECT complaint_number,notes,compensation_amount FROM order_manual_data").fetchone()
            raw_reason = connection.execute("SELECT cancel_reason_raw FROM orders WHERE posting_number='W-3'").fetchone()[0]
        self.assertEqual(tuple(manual), ("C-1", "人工备注", 12.5))
        self.assertEqual(raw_reason, "Покупатель не забрал заказ")
        self.assertEqual(orders(1, q="W-3")["items"][0]["cancel_reason_raw"], "买家未取货")
        message = daily_message("2026-08-19")
        self.assertIn("W-3：买家未取货", message)
        self.assertNotIn("不要发送", message)

        receive_push(self.tokens[1], {"message_type": "TYPE_FBO_POSTING_NEW", "seller_id": 1001,
                     "uuid": "unknown-new", "posting_number": "W-4", "creation_date": "2026-08-19T02:00:00Z"})
        receive_push(self.tokens[1], {"message_type": "TYPE_FBO_POSTING_CANCELLED", "seller_id": 1001,
                     "uuid": "unknown-cancel", "posting_number": "W-4", "new_state": "cancelled",
                     "cancel_date": "2026-08-19T03:00:00Z", "reason": {"id": 99, "message": "未知俄语原因"}})
        self.assertEqual(orders(1, q="W-4")["items"][0]["cancel_reason_raw"], "未知俄语原因")

    def test_webhook_shipping_then_cancellation_stays_active(self):
        receive_push(self.tokens[1], {"message_type": "TYPE_FBO_POSTING_NEW", "seller_id": 1001,
                     "uuid": "ship-new", "posting_number": "W-5", "creation_date": "2026-08-01T00:00:00Z"})
        receive_push(self.tokens[1], {"message_type": "TYPE_FBO_POSTING_STATE_CHANGED", "seller_id": 1001,
                     "uuid": "ship-state", "posting_number": "W-5", "new_state": "delivering",
                     "changed_state_date": "2026-08-19T01:00:00Z"})
        receive_push(self.tokens[1], {"message_type": "TYPE_FBO_POSTING_CANCELLED", "seller_id": 1001,
                     "uuid": "ship-cancel", "posting_number": "W-5", "new_state": "cancelled",
                     "cancel_date": "2026-08-20T02:00:00Z", "reason": {"message": "Покупатель отменил заказ"}})
        with db.connect() as connection:
            row = connection.execute("""SELECT shipped,cancelled_after_ship,shipped_at,status_changed_at
              FROM orders WHERE posting_number='W-5'""").fetchone()
        self.assertEqual(tuple(row), (1, 1, "2026-08-19T01:00:00Z", "2026-08-20T02:00:00Z"))
        self.assertEqual(orders(1, q="W-5")["total"], 1)
        self.assertIn("W-5：买家取消订单", daily_message("2026-08-20"))

    def test_existing_webhook_history_backfills_shipping_times(self):
        receive_push(self.tokens[1], {"message_type": "TYPE_FBO_POSTING_NEW", "seller_id": 1001,
                     "uuid": "backfill-new", "posting_number": "W-6", "creation_date": "2026-08-01T00:00:00Z"})
        receive_push(self.tokens[1], {"message_type": "TYPE_FBO_POSTING_STATE_CHANGED", "seller_id": 1001,
                     "uuid": "backfill-delivered", "posting_number": "W-6", "new_state": "delivered",
                     "changed_state_date": "2026-08-20T05:00:00Z"})
        with db.transaction() as connection:
            connection.execute("UPDATE orders SET shipped=0,shipped_at=NULL,delivered_at=NULL WHERE posting_number='W-6'")
        db.init_db()
        with db.connect() as connection:
            row = connection.execute(
                "SELECT shipped,shipped_at,delivered_at FROM orders WHERE posting_number='W-6'").fetchone()
        self.assertEqual(tuple(row), (1, "2026-08-20T05:00:00Z", "2026-08-20T05:00:00Z"))

    def test_stock_idempotency_and_fbo_object_array_compatibility(self):
        stock = {"message_type": "TYPE_STOCKS_CHANGED", "seller_id": 1001, "items": [{"sku": 8,
                 "product_id": 80, "updated_at": "2026-08-20T00:00:00Z",
                 "stocks": [{"warehouse_id": 11, "present": 2, "reserved": 1}]}]}
        receive_push(self.tokens[1], stock)
        receive_push(self.tokens[1], stock)
        for stocks in (
            {"sku": 9, "updated_at": "2026-08-20T00:00:00Z", "new_present": 3, "new_reserved": 1},
            [{"sku": 10, "updated_at": "2026-08-20T01:00:00Z", "new_present": 4, "new_reserved": 2}],
        ):
            receive_push(self.tokens[1], {"message_type": "TYPE_FBO_STOCKS_CHANGED", "seller_id": 1001,
                         "stocks": stocks})
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM warehouse_stocks").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM fbo_stocks").fetchone()[0], 2)

    def test_admin_settings_hide_tokens_from_normal_shop_api(self):
        self.assertEqual(set(PUSH_TYPES), set(push_settings("https://example.test")[0]["event_types"]))
        self.assertNotIn("push_token", shops()[0])
        settings = push_settings("https://example.test")
        self.assertIn(self.tokens[1], settings[0]["callback_url"])
        self.assertNotEqual(self.tokens[1], self.tokens[2])
        response = asyncio.run(ozon_push(self.tokens[1], Request(
            {"message_type": "TYPE_PING", "time": "2026-08-20T00:00:00Z"}, "text/plain")))
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.media_type, "application/json")

        unsupported = asyncio.run(ozon_push(self.tokens[1], Request(
            {"message_type": "TYPE_ORDER_NEW", "seller_id": 1001})))
        self.assertEqual(unsupported.status_code, 400)
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM webhook_events").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
