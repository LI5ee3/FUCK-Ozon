import asyncio
import json
import tempfile
import threading
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app import db, ozon
from app.importer import _shipping, import_csv
from app.main import export_module, export_orders, login, upload
from app.ozon import (_cursor_pages, _post, _product_price, sync_module, sync_orders,
                      sync_returns, table_fingerprints)

ROOT = Path(__file__).resolve().parent.parent


class ImportRegressionTest(unittest.TestCase):
    def test_api_product_price_shapes(self):
        self.assertEqual(_product_price({"price": "12.50"}, "USD"), (12.5, "USD"))
        self.assertEqual(_product_price({"price": {"amount": "88", "currency": "CNY"}}, "USD"), (88.0, "CNY"))

    def test_shipping_anomaly_detects_conflicting_evidence(self):
        self.assertEqual(_shipping({"状态": "已签收"})[:3], (1, None, 1))
        self.assertEqual(_shipping({"状态": "已取消", "已转移配送": "2026-08-01T00:00:00Z"})[:3],
                         (1, 1, 1))

    def test_stock_sync_changes_only_stock_table(self):
        before = table_fingerprints()
        response = {"items": [{"product_id": 1, "offer_id": "A", "stocks": []}], "has_next": False}
        with patch("app.ozon._post", return_value=response):
            sync_module("stock", 1)
        after = table_fingerprints()
        self.assertEqual({table for table in before if before[table] != after[table]}, {"stock_snapshots"})

    def test_network_errors_are_retried(self):
        with patch("app.ozon.urllib.request.urlopen", side_effect=urllib.error.URLError("temporary")) as request, \
             patch("app.ozon.time.sleep"):
            with self.assertRaises(RuntimeError):
                _post(1, "/test", {})
        self.assertEqual(request.call_count, 7)

    def test_cursor_pages_supports_total_without_has_next(self):
        pages = [
            {"items": [{"id": 1}], "cursor": "next", "total": 2},
            {"items": [{"id": 2}], "cursor": "done", "total": 2},
        ]
        with patch("app.ozon._post", side_effect=pages) as post:
            records = _cursor_pages(1, "/stocks", {"limit": 1}, "items")
        self.assertEqual([row["id"] for row in records], [1, 2])
        self.assertEqual(post.call_args_list[1].args[2]["cursor"], "next")

    def test_network_wait_does_not_hold_rate_limit_lock(self):
        entered, release = threading.Event(), threading.Event()

        class Response:
            def __enter__(self):
                entered.set(); release.wait(1); return self
            def __exit__(self, *_):
                return False

        ozon._last_request = 0
        with patch("app.ozon.urllib.request.urlopen", return_value=Response()), \
             patch("app.ozon.json.load", return_value={}):
            thread = threading.Thread(target=_post, args=(1, "/test", {}))
            thread.start(); self.assertTrue(entered.wait(1))
            acquired = ozon._request_lock.acquire(timeout=.1)
            if acquired:
                ozon._request_lock.release()
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
        with patch("app.ozon._post", side_effect=response) as post:
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
            return {"result": {"return": {"return_reason": {
                "id": payload["return_id"], "name": "商品或原厂包装已损坏"}}}}

        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, tzinfo=timezone.utc)
        with patch("app.ozon._post", side_effect=first):
            with self.assertRaisesRegex(RuntimeError, "temporary"):
                sync_returns(1, start, end)
        with db.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM rfbs_return_records WHERE reason_raw IS NOT NULL").fetchone()[0], 25)

        called = []
        def retry(_shop, path, payload):
            if path in ("/v1/returns/list", "/v2/returns/rfbs/list"):
                return {"returns": [], "has_next": False}
            called.append(payload["return_id"])
            return {"return_reason": {"id": 99, "name": "未收录原因"}}

        with patch("app.ozon._post", side_effect=retry):
            sync_returns(1, start, end)
        self.assertEqual(called, [26])
        with db.connect() as connection:
            reason, payload = connection.execute(
                "SELECT reason_raw,payload FROM rfbs_return_records WHERE return_id=26").fetchone()
        self.assertEqual(reason, "未收录原因")
        self.assertEqual(json.loads(payload)["return_reason"]["id"], 99)

    def test_rfbs_list_cannot_clear_existing_detail_reason(self):
        detail = {"return_reason": {"id": 7, "name": "原有俄语原因"}}
        with db.transaction() as connection:
            connection.execute("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,posting_number,payload,fetched_at,reason_raw,reason_name)
              VALUES(1,7,'R-7','2026-08-01T00:00:00Z','P-7',?,'2026-08-01T00:00:00Z',?,?)""",
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
        with patch("app.ozon._post", side_effect=response):
            sync_returns(1, start, end)
        with db.connect() as connection:
            reason, stored = connection.execute(
                "SELECT reason_raw,payload FROM rfbs_return_records WHERE return_id=7").fetchone()
        self.assertEqual(reason, "原有俄语原因")
        self.assertEqual(json.loads(stored)["return_reason"]["id"], 7)

    def test_rfbs_reason_translations_are_exact(self):
        expected = {
            "Товар или заводскую упаковку повредили": "商品或原厂包装已损坏",
            "Товар использовали до меня": "我收到前商品已被使用",
            "Есть внешние дефекты или следы использования": "有外部缺陷或使用痕迹",
            "Привезли не тот товар": "配送了错误的商品",
            "Нет части товара или комплекта": "商品或套装部件缺失",
            "Нет части товара/комплекта": "商品/套件缺失部分",
            "Не работает, плохо работает": "无法使用，使用效果差",
            "Подделка": "假货",
            "Товар сломался при использовании": "商品在使用过程中坏了",
            "Не подошёл товар": "商品不合适",
            "Товар не подошёл": "商品不合适",
            "Не работает или работает плохо": "不可用或无法正常工作",
        }
        self.assertEqual({reason: ozon.CANCEL_REASON_ZH.get(reason) for reason in expected}, expected)

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
        with patch("app.ozon._post", side_effect=response):
            sync_returns(1, start, end, include_existing_missing=False)
        after = table_fingerprints()
        self.assertEqual(details, [2])
        for table in set(before) - {"return_records", "rfbs_return_records"}:
            self.assertEqual(before[table], after[table], table)
        with db.connect() as connection:
            self.assertIsNone(connection.execute(
                "SELECT reason_raw FROM rfbs_return_records WHERE return_id=1").fetchone()[0])

    def test_return_permission_probe_includes_rfbs_detail(self):
        methods = ["/v1/returns/list", "/v2/returns/rfbs/list", "/v2/returns/rfbs/get"]
        with patch("app.ozon._post", side_effect=[{"roles": [{"name": "Admin", "methods": methods}]},
                                                   {"result": {"name": "Shop"}}]) as post:
            result = ozon.probe_shop(1)
        self.assertEqual(result["permissions"]["returns"], "可用")
        self.assertEqual([call.args[1] for call in post.call_args_list], ["/v1/roles", "/v1/seller/info"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()

    def tearDown(self):
        self.temp.cleanup()

    def test_real_samples_match_verified_baseline(self):
        for channel in ("FBP", "realFBS", "WHD"):
            path = ROOT / f"{channel}.csv"
            if not path.exists():
                self.skipTest(f"跳过基准样本测试：本地未提供可选样例数据 {path.name}")
            import_csv(1, channel, path.name, path.read_bytes())
        with db.connect() as connection:
            active = "NOT (o.status_raw='已取消' AND o.shipped=0)"
            totals = connection.execute(f"""
              SELECT COUNT(DISTINCT o.posting_number),SUM(i.quantity)
              FROM orders o JOIN order_items i USING(shop_id,posting_number) WHERE {active}
            """).fetchone()
            by_channel = {row[0]:(row[1],row[2]) for row in connection.execute(f"""
              SELECT o.channel,COUNT(DISTINCT o.posting_number),SUM(i.quantity)
              FROM orders o JOIN order_items i USING(shop_id,posting_number)
              WHERE {active} GROUP BY o.channel
            """)}

        self.assertEqual(tuple(totals), (3623, 3671))
        self.assertEqual(by_channel, {"FBP": (2690, 2724), "realFBS": (810, 824), "WHD": (123, 123)})

    def test_channel_change_keeps_one_item_row(self):
        content = ("订单号;发货号码;状态;SKU;数量;已创建\n"
                   "M-1;P-1;已签收;SKU-1;2;2026-08-01T00:00:00Z\n").encode()
        import_csv(1, "FBP", "first.csv", content)
        import_csv(1, "realFBS", "second.csv", content)
        with db.connect() as connection:
            rows = connection.execute(
                "SELECT channel,quantity FROM order_items WHERE shop_id=1 AND posting_number='P-1'").fetchall()
        self.assertEqual([tuple(row) for row in rows], [("realFBS", 2)])

    def test_csv_cannot_replace_api_channel(self):
        with db.transaction() as connection:
            connection.execute("""INSERT INTO orders(
              shop_id,posting_number,channel,status_raw,source) VALUES(1,'P-1','realFBS','已签收','api')""")
            connection.execute("""INSERT INTO order_items(
              shop_id,channel,posting_number,sku,quantity,source) VALUES(1,'realFBS','P-1','SKU-1',2,'api')""")
        content = ("订单号;发货号码;状态;SKU;数量;已创建\n"
                   "M-1;P-1;已签收;SKU-1;2;2026-08-01T00:00:00Z\n").encode()
        import_csv(1, "FBP", "wrong-channel.csv", content)
        with db.connect() as connection:
            channels = connection.execute("""SELECT o.channel,i.channel FROM orders o
              JOIN order_items i USING(shop_id,posting_number) WHERE o.posting_number='P-1'""").fetchone()
        self.assertEqual(tuple(channels), ("realFBS", "realFBS"))

    def test_order_sync_saves_actual_shipping_time_and_backfills_existing_rows(self):
        content = ("订单号;发货号码;状态;SKU;数量;已创建;已转移配送\n"
                   "M-2;P-2;已签收;SKU-2;1;2026-08-01T00:00:00Z;2026-08-01T03:00:00Z\n").encode()
        import_csv(1, "FBP", "shipping.csv", content)
        postings = [
            {"posting_number": "P-1", "integration_type_flow": "FBP", "status": "delivering",
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
        with patch("app.ozon._cursor_pages", side_effect=[postings, fbo]), \
             patch("app.ozon._post") as detail:
            sync_orders(1, moment, moment)
        detail.assert_not_called()
        with db.connect() as connection:
            times = dict(connection.execute("SELECT posting_number,shipped_at FROM orders WHERE posting_number IN ('P-1','P-2')"))
            delivered = connection.execute(
                "SELECT delivered_at FROM orders WHERE posting_number='W-1'").fetchone()[0]
            fbs_delivered = connection.execute(
                "SELECT delivered_at FROM orders WHERE posting_number='P-3'").fetchone()[0]
            connection.execute("UPDATE orders SET shipped_at=NULL WHERE posting_number='P-1'")
            connection.commit()
        self.assertEqual(times, {"P-1": "2026-08-01T02:00:00Z", "P-2": "2026-08-01T03:00:00Z"})
        self.assertEqual(delivered, "2026-08-02T00:00:00Z")
        self.assertIsNone(fbs_delivered)
        db.init_db()
        with db.connect() as connection:
            backfilled = connection.execute("SELECT shipped_at FROM orders WHERE posting_number='P-1'").fetchone()[0]
        self.assertEqual(backfilled, "2026-08-01T02:00:00Z")

    def test_duplicate_sku_rows_are_aggregated_idempotently(self):
        content = ("订单号;发货号码;状态;SKU;数量;已创建\n"
                   "M-1;P-1;已签收;SKU-1;1;2026-08-01T00:00:00Z\n"
                   "M-1;P-1;已签收;SKU-1;3;2026-08-01T00:00:00Z\n").encode()
        import_csv(1, "FBP", "duplicate.csv", content)
        import_csv(1, "FBP", "duplicate.csv", content)
        with db.connect() as connection:
            quantity = connection.execute(
                "SELECT quantity FROM order_items WHERE shop_id=1 AND posting_number='P-1' AND sku='SKU-1'").fetchone()[0]
        self.assertEqual(quantity, 4)

    def test_export_excludes_cancelled_before_shipping(self):
        header = "订单号;发货号码;状态;SKU;数量;已创建\n"
        import_csv(1, "FBP", "active.csv", (header + "M-1;P-1;已签收;SKU-1;1;2026-08-01T00:00:00Z\n").encode())
        import_csv(1, "FBP", "cancelled.csv", (header + "M-2;P-2;已取消;SKU-2;1;2026-08-02T00:00:00Z\n").encode())

        async def collect():
            return [json.loads(line) async for line in export_orders(1).body_iterator]

        rows = asyncio.run(collect())
        self.assertEqual([row.get("posting_number") for row in rows[1:]], ["P-1"])

    def test_timeliness_export_filters_pre_ship_cancellations_and_accepts_iso_end(self):
        header = "订单号;发货号码;状态;SKU;数量;已创建\n"
        content = (header
                   + "M-1;P-1;已签收;SKU-1;1;2026-08-01T12:00:00Z\n"
                   + "M-2;P-2;已取消;SKU-2;1;2026-08-01T11:00:00Z\n"
                   + "M-3;P-3;已签收;SKU-3;1;2026-08-01T12:00:00.500Z\n")
        import_csv(1, "FBP", "timeliness.csv", content.encode())
        with db.transaction() as connection:
            connection.execute(
                "UPDATE orders SET created_at='2026-08-01T12:00:00.500Z' WHERE posting_number='P-3'")

        async def collect(date_to):
            return [json.loads(line) async for line in export_module(
                "timeliness", 1, date_to=date_to).body_iterator]

        exact = asyncio.run(collect("2026-08-01T12:00:00Z"))
        whole_day = asyncio.run(collect("2026-08-01"))
        self.assertEqual([row.get("posting_number") for row in exact[1:]], ["P-1"])
        self.assertEqual(sorted(row.get("posting_number") for row in whole_day[1:]), ["P-1", "P-3"])

    def test_login_can_use_dotenv_values(self):
        from app.security import password_hash
        salt, digest = password_hash("secret")
        class Request:
            url = type("URL", (), {"scheme": "http"})()
            client = type("Client", (), {"host": "127.0.0.1"})()
            headers = {}

            async def json(self):
                return {"password": "secret"}

        from fastapi import Response
        with patch("app.main._env", return_value={"ADMIN_PASSWORD_SALT": salt, "ADMIN_PASSWORD_HASH": digest}), \
             patch("app.main._token", return_value="token"):
            self.assertEqual(asyncio.run(login(Request(), Response())), {"ok": True})

    def test_upload_uses_threadpool(self):
        class Request:
            headers = {"x-filename": "orders.csv"}

            async def body(self):
                return ("订单号;发货号码;状态;SKU;数量\n"
                        "M-1;P-1;已签收;SKU-1;1\n").encode()

        runner = AsyncMock(return_value={"rows": 1})
        with patch("app.main.run_in_threadpool", runner):
            result = asyncio.run(upload("FBP", Request(), 1))
        self.assertEqual(result, {"rows": 1})
        runner.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()
