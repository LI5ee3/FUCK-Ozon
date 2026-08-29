import json
import threading
import urllib.error
from email.message import Message
from datetime import datetime, timezone
from unittest.mock import patch

from app import db
from app.importer import import_csv
from app.ozon import client
from app.ozon.client import _cursor_pages, _post
from app.ozon.sync import (_product_price, _sync_stock_snapshot, sync_module,
                           sync_orders, sync_returns)
from tests.support import DatabaseTestCase, table_fingerprints


class OzonSyncTest(DatabaseTestCase):
    def test_api_product_price_shapes(self):
        self.assertEqual(_product_price({"price": "12.50"}, "USD"), (12.5, "USD"))
        self.assertEqual(_product_price({"price": {"amount": "88", "currency": "CNY"}}, "USD"), (88.0, "CNY"))

    def test_stock_sync_changes_only_stock_table(self):
        before = table_fingerprints()
        response = {"items": [{"product_id": 1, "offer_id": "A", "stocks": []}], "has_next": False}
        with patch("app.ozon.client._post", return_value=response):
            sync_module("stock", 1)
        after = table_fingerprints()
        self.assertEqual({table for table in before if before[table] != after[table]}, {"stock_snapshots"})

    def test_network_errors_are_retried(self):
        with patch("app.ozon.client.urllib.request.urlopen", side_effect=urllib.error.URLError("temporary")) as request, \
             patch("app.ozon.client.time.sleep"):
            with self.assertRaises(RuntimeError):
                _post(1, "/test", {})
        self.assertEqual(request.call_count, 7)

    def test_retry_after_precedes_backoff_and_is_capped(self):
        for value in ("120", "Thu, 31 Dec 2099 23:59:59 GMT"):
            with self.subTest(value=value):
                headers = Message()
                headers["Retry-After"] = value
                error = urllib.error.HTTPError("https://example.test", 429, "rate limited", headers, None)
                with patch("app.ozon.client.urllib.request.urlopen", side_effect=error), \
                     patch("app.ozon.client._wait_for_request_slot"), \
                     patch("app.ozon.client.time.sleep") as sleep:
                    with self.assertRaises(RuntimeError):
                        _post(1, "/test", {})
                error.close()
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [30] * 6)

    def test_invalid_retry_after_uses_exponential_backoff(self):
        headers = Message()
        headers["Retry-After"] = "invalid"
        error = urllib.error.HTTPError("https://example.test", 503, "unavailable", headers, None)
        with patch("app.ozon.client.urllib.request.urlopen", side_effect=error), \
             patch("app.ozon.client._wait_for_request_slot"), \
             patch("app.ozon.client.time.sleep") as sleep:
            with self.assertRaises(RuntimeError):
                _post(1, "/test", {})
        error.close()
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4, 8, 16, 30, 30])

    def test_cursor_pages_supports_total_without_has_next(self):
        pages = [
            {"items": [{"id": 1}], "cursor": "next", "total": 2},
            {"items": [{"id": 2}], "cursor": "done", "total": 2},
        ]
        with patch("app.ozon.client._post", side_effect=pages) as post:
            records = _cursor_pages(1, "/stocks", {"limit": 1}, "items")
        self.assertEqual([row["id"] for row in records], [1, 2])
        self.assertEqual(post.call_args_list[1].args[2]["cursor"], "next")

    def test_cursor_pages_stops_when_cursor_does_not_advance(self):
        page = {"items": [{"id": 1}], "cursor": "stuck", "has_next": True}
        with patch("app.ozon.client._post", return_value=page) as post:
            with self.assertRaisesRegex(RuntimeError, "分页游标未前进"):
                _cursor_pages(1, "/stocks", {"limit": 1}, "items")
        self.assertEqual(post.call_count, 2)

    def test_returns_cursor_uses_last_return_id(self):
        pages = [
            {"returns": [{"id": "100"}, {"id": "101"}], "has_next": True},
            {"returns": [{"id": "102"}], "has_next": False},
        ]
        with patch("app.ozon.client._post", side_effect=pages) as post:
            records = _cursor_pages(1, "/v1/returns/list", {"limit": 100}, "returns", "last_id", "")
        self.assertEqual([row["id"] for row in records], ["100", "101", "102"])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[1].args[2]["last_id"], "101")

    def test_network_wait_does_not_hold_rate_limit_lock(self):
        entered, release = threading.Event(), threading.Event()

        class Response:
            def __enter__(self):
                entered.set(); release.wait(1); return self
            def __exit__(self, *_):
                return False

        client._last_request = 0
        with patch("app.ozon.client.urllib.request.urlopen", return_value=Response()), \
             patch("app.ozon.client.json.load", return_value={}):
            thread = threading.Thread(target=_post, args=(1, "/test", {}))
            thread.start(); self.assertTrue(entered.wait(1))
            acquired = client._request_lock.acquire(timeout=.1)
            if acquired:
                client._request_lock.release()
            release.set(); thread.join(1)
        self.assertTrue(acquired)

    def test_return_sources_stay_separate_and_rfbs_is_idempotent(self):
        cancellation = {"id": 1, "posting_number": "C-1", "product": {"sku": 1}, "logistic": {}}
        requests = [
            {"return_id": 9, "return_number": "174763409-R14", "posting_number": "P-0",
             "created_at": "2026-08-03T00:00:00Z", "product": {"offer_id": "O", "sku": 0, "name": "商品0"},
             "state": {"state": "returned", "state_name": "已退货"}},
            {"return_id": 10, "return_number": "55765650-R10", "posting_number": "P-1",
             "created_at": "2026-08-01T00:00:00Z", "product": {"offer_id": "A", "sku": 1, "name": "商品A"},
             "state": {"state": "approved", "state_name": "已批准"}},
            {"return_id": 11, "return_number": "55765650-R11", "posting_number": "P-1",
             "created_at": "2026-08-02T00:00:00Z", "product": {"offer_id": "B", "sku": 2, "name": "商品B"},
             "state": {"state": "new", "state_name": "新申请"}},
            {"return_id": 12, "return_number": "", "posting_number": "P-2", "product": {"sku": 3}},
        ]

        def response(_shop, path, payload):
            if path == "/v1/returns/list":
                return {"returns": [cancellation], "has_next": False}
            if path == "/v2/returns/rfbs/list":
                return {"returns": requests}
            return {"return_reason": {"id": payload["return_id"], "name": "不应该使用中文"}}

        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        end = datetime(2026, 8, 3, tzinfo=timezone.utc)
        with patch("app.ozon.client._post", side_effect=response) as post:
            sync_returns(1, start, end)
            sync_returns(1, start, end)
        with db.connect() as connection:
            cancellations = connection.execute("SELECT COUNT(*) FROM return_records").fetchone()[0]
            saved = connection.execute("SELECT return_number,posting_number FROM rfbs_return_records ORDER BY return_id").fetchall()
        self.assertEqual(cancellations, 1)
        self.assertEqual([tuple(row) for row in saved], [
            ("174763409-R14", "P-0"), ("55765650-R10", "P-1"), ("55765650-R11", "P-1")
        ])
        self.assertEqual(sum(call.args[1] == "/v2/returns/rfbs/get" for call in post.call_args_list), 3)

    def test_rfbs_reason_batches_are_saved_and_resume_after_failure(self):
        rows = [(1, value, f"R-{value}", "2026-08-01T00:00:00Z", "{}", "2026-08-01T00:00:00Z")
                for value in range(1, 27)]
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,payload,fetched_at) VALUES(?,?,?,?,?,?)""", rows)

        def first(_shop, path, payload):
            if path in ("/v1/returns/list", "/v2/returns/rfbs/list"):
                return {"returns": [], "has_next": False}
            if payload["return_id"] == 26:
                raise RuntimeError("temporary")
            return {"returns": {"return_reason": {
                "id": payload["return_id"], "name": "商品或原厂包装已损坏"}}}

        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, tzinfo=timezone.utc)
        with patch("app.ozon.client._post", side_effect=first):
            with self.assertRaisesRegex(RuntimeError, "temporary"):
                sync_returns(1, start, end)
        with db.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM rfbs_return_records WHERE detail_fetched_at IS NOT NULL").fetchone()[0], 25)

        called = []
        def retry(_shop, path, payload):
            if path in ("/v1/returns/list", "/v2/returns/rfbs/list"):
                return {"returns": [], "has_next": False}
            called.append(payload["return_id"])
            return {"return_reason": {"id": 99, "name": "未收录原因"}}

        with patch("app.ozon.client._post", side_effect=retry):
            sync_returns(1, start, end)
        self.assertEqual(called, [26])
        with db.connect() as connection:
            reason, payload, completed = connection.execute(
                "SELECT reason_raw,payload,detail_fetched_at FROM rfbs_return_records WHERE return_id=26").fetchone()
        self.assertEqual(reason, "未收录原因")
        self.assertEqual(json.loads(payload)["return_reason"]["id"], 99)
        self.assertIsNotNone(completed)

    def test_rfbs_list_cannot_clear_existing_detail_reason(self):
        detail = {"return_reason": {"id": 7, "name": "原有俄语原因"}}
        with db.transaction() as connection:
            connection.execute("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,posting_number,payload,fetched_at,
              reason_raw,reason_name,detail_fetched_at)
              VALUES(1,7,'R-7','2026-08-01T00:00:00Z','P-7',?,'2026-08-01T00:00:00Z',?,?,
                '2026-08-01T00:00:00Z')""",
              (json.dumps(detail, ensure_ascii=False), "原有俄语原因", "原有俄语原因"))
        summary = {"return_id": 7, "return_number": "R-7", "created_at": "2026-08-01T00:00:00Z",
                   "posting_number": "P-7", "product": {}, "state": {}}

        def response(_shop, path, _payload):
            if path == "/v1/returns/list":
                return {"returns": [], "has_next": False}
            if path == "/v2/returns/rfbs/list":
                return {"returns": [summary], "has_next": False}
            self.fail("已有原因不应再次请求详情")

        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, tzinfo=timezone.utc)
        with patch("app.ozon.client._post", side_effect=response):
            sync_returns(1, start, end)
        with db.connect() as connection:
            reason, stored = connection.execute(
                "SELECT reason_raw,payload FROM rfbs_return_records WHERE return_id=7").fetchone()
        self.assertEqual(reason, "原有俄语原因")
        self.assertEqual(json.loads(stored)["return_reason"]["id"], 7)

    def test_reasonless_detail_is_completed_saved_and_not_requested_again(self):
        summary = {"return_id": 8, "return_number": "R-8", "created_at": "2026-08-01T00:00:00Z",
                   "posting_number": "P-8", "product": {}, "state": {}}

        def response(_shop, path, _payload):
            if path == "/v1/returns/list":
                return {"returns": [], "has_next": False}
            if path == "/v2/returns/rfbs/list":
                return {"returns": [summary], "has_next": False}
            return {"returns": {"return_reason": {}}, "detail_marker": "saved"}

        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, tzinfo=timezone.utc)
        with patch("app.ozon.client._post", side_effect=response) as post:
            sync_returns(1, start, end)
            sync_returns(1, start, end)
        self.assertEqual(sum(call.args[1] == "/v2/returns/rfbs/get"
                             for call in post.call_args_list), 1)
        with db.connect() as connection:
            reason, payload, completed = connection.execute("""SELECT reason_raw,payload,detail_fetched_at
              FROM rfbs_return_records WHERE return_id=8""").fetchone()
        self.assertIsNone(reason)
        self.assertEqual(json.loads(payload)["detail_marker"], "saved")
        self.assertIsNotNone(completed)

    def test_automatic_return_sync_only_fetches_details_for_new_records(self):
        with db.transaction() as connection:
            connection.execute("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,payload,fetched_at)
              VALUES(1,1,'OLD-R1','2026-08-01T00:00:00Z','{}','2026-08-01T00:00:00Z')""")
        new_record = {"return_id": 2, "return_number": "NEW-R2", "created_at": "2026-08-01T00:00:00Z",
                      "product": {}, "state": {}}
        details = []

        def response(_shop, path, payload):
            if path == "/v1/returns/list":
                return {"returns": [], "has_next": False}
            if path == "/v2/returns/rfbs/list":
                return {"returns": [new_record], "has_next": False}
            details.append(payload["return_id"])
            return {"return_reason": {"id": 2, "name": "Новая причина"}}

        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, tzinfo=timezone.utc)
        before = table_fingerprints()
        with patch("app.ozon.client._post", side_effect=response):
            sync_returns(1, start, end, include_existing_missing=False)
        after = table_fingerprints()
        self.assertEqual(details, [2])
        for table in set(before) - {"return_records", "rfbs_return_records"}:
            self.assertEqual(before[table], after[table], table)
        with db.connect() as connection:
            old_reason, old_completed = connection.execute("""SELECT reason_raw,detail_fetched_at
              FROM rfbs_return_records WHERE return_id=1""").fetchone()
            new_completed = connection.execute("""SELECT detail_fetched_at
              FROM rfbs_return_records WHERE return_id=2""").fetchone()[0]
        self.assertIsNone(old_reason)
        self.assertIsNone(old_completed)
        self.assertIsNotNone(new_completed)

    def test_return_permission_probe_includes_rfbs_detail(self):
        methods = ["/v1/returns/list", "/v2/returns/rfbs/list", "/v2/returns/rfbs/get"]
        with patch("app.ozon.client._post", side_effect=[{"roles": [{"name": "Admin", "methods": methods}]},
                                                   {"result": {"name": "Shop"}}]) as post:
            result = client.probe_shop(1)
        self.assertEqual(result["permissions"]["returns"], "可用")
        self.assertEqual([call.args[1] for call in post.call_args_list], ["/v1/roles", "/v1/seller/info"])

    def test_order_sync_saves_shipping_time_and_tracking_number(self):
        content = ("订单号;发货号码;状态;SKU;数量;已创建;已转移配送\n"
                   "M-2;P-2;已签收;SKU-2;1;2026-08-01T00:00:00Z;2026-08-01T03:00:00Z\n").encode()
        import_csv(1, "FBP", "shipping.csv", content)
        postings = [
            {"posting_number": "P-1", "integration_type_flow": "FBP", "status": "delivering",
             "tracking_number": "TRACK-1",
             "in_process_at": "2026-08-01T00:00:00Z", "delivering_date": "2026-08-01T02:00:00Z", "products": []},
            {"posting_number": "P-2", "integration_type_flow": "FBP", "status": "delivering",
             "in_process_at": "2026-08-01T00:00:00Z", "delivering_date": None, "products": []},
            {"posting_number": "P-3", "integration_type_flow": "FBP", "status": "delivered",
             "in_process_at": "2026-08-01T00:00:00Z", "delivering_date": "2026-08-01T04:00:00Z", "products": []},
        ]
        fbo = [{"posting_number": "W-1", "status": "delivered",
                "created_at": "2026-08-01T00:00:00Z", "fact_delivery_date": "2026-08-02T00:00:00Z",
                "products": []}]
        moment = datetime(2026, 8, 1, tzinfo=timezone.utc)
        with db.transaction() as connection:
            connection.execute("""INSERT INTO orders(shop_id,posting_number,channel,created_at,shipped_at,
              delivered_at,status_raw,shipped,source) VALUES(1,'P-3','FBP','2026-08-01T00:00:00Z',
              '2026-08-01T04:00:00Z','2026-08-01T04:00:00Z','已签收',1,'api')""")
        with patch("app.ozon.client._cursor_pages", side_effect=[postings, fbo]), \
             patch("app.ozon.client._post") as detail:
            sync_orders(1, moment, moment)
        detail.assert_not_called()
        with db.connect() as connection:
            times = dict(connection.execute("SELECT posting_number,shipped_at FROM orders WHERE posting_number IN ('P-1','P-2')"))
            delivered = connection.execute(
                "SELECT delivered_at FROM orders WHERE posting_number='W-1'").fetchone()[0]
            fbs_delivered = connection.execute(
                "SELECT delivered_at FROM orders WHERE posting_number='P-3'").fetchone()[0]
            tracking = connection.execute(
                "SELECT tracking_number FROM orders WHERE posting_number='P-1'").fetchone()[0]
        self.assertEqual(times, {"P-1": "2026-08-01T02:00:00Z", "P-2": "2026-08-01T03:00:00Z"})
        self.assertEqual(delivered, "2026-08-02T00:00:00Z")
        self.assertIsNone(fbs_delivered)
        self.assertEqual(tracking, "TRACK-1")

    def test_api_duplicate_sku_rows_are_aggregated_idempotently(self):
        posting = {"posting_number": "P-API", "integration_type_flow": "FBP", "status": "delivering",
                   "products": [{"sku": "A", "offer_id": "OA", "name": "商品A", "quantity": 1, "price": "10"},
                                {"sku": "A", "offer_id": "OA", "name": "商品A", "quantity": 2, "price": "20"},
                                {"sku": "B", "offer_id": "OB", "name": "商品B", "quantity": 1, "price": "3"}]}
        with patch("app.ozon.client._cursor_pages", side_effect=[[posting], [], [posting], []]):
            sync_orders(1, datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 8, 2, tzinfo=timezone.utc))
            sync_orders(1, datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 8, 2, tzinfo=timezone.utc))
        with db.connect() as connection:
            items = connection.execute("""SELECT sku,quantity FROM order_items
              WHERE shop_id=1 AND posting_number='P-API' ORDER BY sku""").fetchall()
            amount = connection.execute("""SELECT amount_original FROM orders
              WHERE shop_id=1 AND posting_number='P-API'""").fetchone()[0]
        self.assertEqual([tuple(row) for row in items], [("A", 3), ("B", 1)])
        self.assertEqual(amount, 53.0)

    def test_api_stock_history_keeps_each_observation_and_latest_snapshot(self):
        record = {"product_id": 1, "offer_id": "O-1",
                  "stocks": [{"sku": "S-1", "type": "fbs", "present": 10, "reserved": 0}]}
        responses = [
            {**record, "stocks": [{**record["stocks"][0], "present": 10}]},
            {**record, "stocks": [{**record["stocks"][0], "present": 0}]},
            {**record, "stocks": [{**record["stocks"][0], "present": 20}]},
            {**record, "stocks": [{**record["stocks"][0], "present": 20}]},
        ]
        with patch("app.ozon.client._cursor_pages", side_effect=([response] for response in responses)), \
             patch("app.ozon.client._stamp", side_effect=["2026-08-01T00:00:00Z", "2026-08-02T00:00:00Z",
                                                     "2026-08-03T00:00:00Z", "2026-08-03T00:00:00Z"]):
            for _ in responses:
                _sync_stock_snapshot(1)
        with db.connect() as connection:
            snapshot = connection.execute("""SELECT observed_at,payload FROM stock_snapshots
              WHERE shop_id=1 AND record_key='1'""").fetchone()
            history = connection.execute("""SELECT source,occurred_at,present,event_key FROM stock_history
              WHERE shop_id=1 AND sku='S-1' ORDER BY occurred_at""").fetchall()
        self.assertEqual(snapshot[0], "2026-08-03T00:00:00Z")
        self.assertEqual(json.loads(snapshot[1])["stocks"][0]["present"], 20)
        self.assertEqual([(row[0], row[1], row[2]) for row in history], [
            ("api", "2026-08-01T00:00:00Z", 10),
            ("api", "2026-08-02T00:00:00Z", 0),
            ("api", "2026-08-03T00:00:00Z", 20),
        ])
        self.assertTrue(all(row[3].endswith(":fbs") for row in history))
