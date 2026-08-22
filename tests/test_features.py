import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from app import db
from app import main
from app.main import (complaints, export_module, product_rules, protect_api, risk_reasons,
                      save_complaint, save_product_rule, save_auto_sync_settings, timeliness)
from app.security import (clear_login_failures, login_limited, password_hash, password_matches,
                          record_login_failure)


class Request:
    def __init__(self, value):
        self.value = value

    async def json(self):
        return self.value


class FeatureRegressionTest(unittest.TestCase):
    def setUp(self):
        self.main_data_dir = main.DATA_DIR
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()
        with db.transaction() as connection:
            connection.execute("""INSERT INTO orders(shop_id,posting_number,channel,created_at,shipped_at,
              delivered_at,status_raw,shipped,amount_original,amount_currency,source)
              VALUES(1,'P-1','FBP','2026-08-01T00:00:00Z','2026-08-01T12:00:00Z',
              '2026-08-03T12:00:00Z','已签收',1,100,'USD','api')""")
            connection.execute("""INSERT INTO order_items(
              shop_id,channel,posting_number,sku,offer_id,product_name_raw,quantity,source)
              VALUES(1,'FBP','P-1','S-1','O-1','商品',2,'api')""")

    def tearDown(self):
        main.DATA_DIR = self.main_data_dir
        self.temp.cleanup()

    @staticmethod
    async def response_text(response):
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    def test_complaints_allow_multiple_tristate_and_do_not_change_ozon_status(self):
        base = {"shop_id": 1, "posting_number": "P-1", "complaint_at": "2026-08-04T00:00:00Z",
                "channel": "平台", "resolved": None, "package_returned": False}
        asyncio.run(save_complaint(Request(base | {"complaint_number": "C-1"})))
        asyncio.run(save_complaint(Request(base | {"complaint_number": "C-2", "resolved": True,
                                                   "compensation_amount": 5})))
        result = complaints(1)
        self.assertEqual(result["total"], 2)
        self.assertIsNone(next(x for x in result["items"] if x["complaint_number"] == "C-1")["resolved"])
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT status_raw FROM orders").fetchone()[0], "已签收")
            self.assertEqual(connection.execute("SELECT status FROM order_after_sales").fetchone()[0], "已完结")

    def test_timeliness_percentiles_and_reason_piece_distribution(self):
        group = timeliness(1)["groups"][0]
        self.assertEqual((group["ship_samples"], group["delivery_samples"]), (1, 1))
        self.assertAlmostEqual(group["p50_ship_hours"], 12)
        with db.transaction() as connection:
            connection.execute("""UPDATE orders SET status_raw='已取消',cancel_reason_raw='未知俄语',
              cancelled_after_ship=1 WHERE posting_number='P-1'""")
        reason = risk_reasons(1)["items"][0]
        self.assertEqual((reason["reason_name"], reason["total"]["pieces"]), ("未知俄语", 2))

    def test_timeliness_rejects_historical_fbs_delivery_fallback(self):
        with db.transaction() as connection:
            connection.execute("UPDATE orders SET delivered_at=shipped_at WHERE posting_number='P-1'")
        data = timeliness(1)
        self.assertEqual(data["groups"][0]["delivery_samples"], 0)
        self.assertEqual(data["groups"][0]["delivered_completeness"], 0)
        self.assertIsNone(data["items"][0]["delivered_at"])

    def test_timeliness_handles_samples_completeness_missing_invalid_and_negative_times(self):
        orders = [
          ("V1", "2026-08-01T00:00:00Z", "2026-08-01T01:00:00Z", "2026-08-01T03:00:00Z", "已签收", 1),
          ("V2", "2026-08-01T00:00:00Z", "2026-08-01T02:00:00Z", "2026-08-01T05:00:00Z", "已签收", 1),
          ("V3", "2026-08-01T00:00:00Z", "坏时间", "坏时间", "已签收", 1),
          ("V4", "2026-08-01T00:00:00Z", None, "2026-08-01T08:00:00Z", "已签收", 1),
          ("V5", "2026-08-01T00:00:00Z", "2026-08-01T04:00:00Z", None, "配送中", 1),
          ("V6", "2026-08-01T05:00:00Z", "2026-08-01T04:00:00Z", "2026-08-01T06:00:00Z", "已签收", 1),
          ("V7", "2026-08-01T00:00:00Z", "2026-08-01T03:00:00Z", "2026-08-01T01:00:00Z", "已签收", 1),
          ("C1", "2026-08-01T00:00:00Z", None, None, "已取消", 0),
        ]
        with db.transaction() as connection:
            connection.execute("DELETE FROM order_items")
            connection.execute("DELETE FROM orders")
            connection.executemany("""INSERT INTO orders(shop_id,posting_number,channel,created_at,
              shipped_at,delivered_at,status_raw,shipped,source) VALUES(1,?,'FBP',?,?,?,?,?,'api')""", orders)
            connection.executemany("""INSERT INTO order_items(
              shop_id,channel,posting_number,sku,quantity,source) VALUES(1,'FBP','V1',?,1,'api')""",
              [("SKU-1",), ("SKU-2",)])
        data = timeliness(1)
        group = data["groups"][0]
        self.assertEqual(data["total"], 7)
        self.assertEqual((group["ship_samples"], group["delivery_samples"]), (4, 3))
        self.assertAlmostEqual(group["p50_ship_hours"], 2.5)
        self.assertAlmostEqual(group["avg_ship_hours"], 2.5)
        self.assertAlmostEqual(group["p90_ship_hours"], 3.7)
        self.assertAlmostEqual(group["p50_delivery_hours"], 2)
        self.assertAlmostEqual(group["avg_delivery_hours"], 7 / 3)
        self.assertAlmostEqual(group["p90_delivery_hours"], 2.8)
        self.assertEqual((group["created_completeness"], group["shipped_completeness"],
                          group["delivered_completeness"]), (1, 5 / 7, 5 / 7))
        self.assertTrue(group["ship_sample_insufficient"])
        self.assertTrue(group["delivery_sample_insufficient"])
        rows = {row["posting_number"]: row for row in data["items"]}
        self.assertTrue(rows["V3"]["ship_anomaly"])
        self.assertTrue(rows["V3"]["delivery_anomaly"])
        self.assertIsNone(rows["V4"]["ship_hours"])
        self.assertIsNone(rows["V6"]["ship_hours"])
        self.assertIsNone(rows["V7"]["delivery_hours"])

    def test_password_hash_rate_limit_and_shop_auto_sync_isolation(self):
        salt, digest = password_hash("secret")
        self.assertTrue(password_matches("secret", salt, digest))
        self.assertFalse(password_matches("wrong", salt, digest))
        clear_login_failures("test")
        for _ in range(5):
            record_login_failure("test", 100)
        self.assertTrue(login_limited("test", 101))
        values = {str(shop): {module: {"enabled": shop == 1 and module == "orders",
                  "run_time": "08:00", "range_days": 7}
                  for module in ("orders", "returns", "stock")} for shop in (1, 2)}
        save_auto_sync_settings(values)
        with db.connect() as connection:
            enabled = connection.execute("""SELECT shop_id,module FROM shop_auto_sync_settings
              WHERE enabled=1""").fetchall()
        self.assertEqual([tuple(row) for row in enabled], [(1, "orders")])

    def test_static_contracts_cover_csrf_exports_port_and_dingtalk_scope(self):
        root = Path(__file__).parent.parent
        main = (root / "app/main.py").read_text()
        deploy = (root / "deploy.sh").read_text()
        frontend = (root / "static/app.js").read_text()
        style = (root / "static/style.css").read_text()
        self.assertIn("x-csrf-token", main.lower())
        self.assertIn("/api/export/{module}", main)
        self.assertIn('"X-CSRF-Token":state.csrf', frontend)
        self.assertIn('s.bind(("0.0.0.0",p))', deploy)
        self.assertIn("nav{display:flex;max-width:100%;overflow-x:auto", style)

    def test_product_priority_ungroup_and_module_exports(self):
        asyncio.run(save_product_rule(Request({"kind": "brand", "brand_name": "低", "keyword": "商品", "priority": 1})))
        asyncio.run(save_product_rule(Request({"kind": "brand", "brand_name": "高", "keyword": "商品", "priority": 9})))
        asyncio.run(save_product_rule(Request({"kind": "short_name", "key_type": "sku", "key_value": "S-1", "short_name": "短名"})))
        asyncio.run(save_product_rule(Request({"kind": "group", "name": "组A", "members": [{"key_type": "sku", "key_value": "S-1"}]})))
        rules = product_rules()
        self.assertEqual(rules["products"][0]["matched_brand"], "高")
        self.assertTrue(all(row["conflict"] for row in rules["brands"]))
        risk_export = asyncio.run(self.response_text(export_module("risk")))
        self.assertIn('"analysis_group": "组A"', risk_export)
        asyncio.run(save_product_rule(Request({"kind": "ungroup", "key_type": "sku", "key_value": "S-1"})))
        self.assertIsNone(product_rules()["groups"][0]["key_type"])
        exported = asyncio.run(self.response_text(export_module("rules")))
        self.assertIn('"rule_type": "中文短名称"', exported)
        self.assertIn('"rule_type": "品牌规则"', exported)
        self.assertNotIn("P-1", exported)

    def test_stock_snapshot_backfill_and_real_csrf_middleware(self):
        payload = json.dumps({"product_id": 1, "stocks": [{"sku": "S-1", "warehouse_ids": [7],
                                                            "present": 4, "reserved": 2}]})
        with db.transaction() as connection:
            connection.execute("INSERT INTO stock_snapshots VALUES(1,'K','2026-08-01T00:00:00Z',?)", (payload,))
        db.init_db(); db.init_db()
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0], 1)

        main.DATA_DIR = db.DATA_DIR
        csrf, token = "csrf", main._token("csrf")
        async def next_response(_):
            return main.Response(status_code=204)
        async def run(header=False):
            headers = [(b"cookie", f"session={token}".encode())]
            if header: headers.append((b"x-csrf-token", csrf.encode()))
            request = main.Request({"type": "http", "method": "POST", "path": "/api/shops",
              "raw_path": b"/api/shops", "query_string": b"", "headers": headers,
              "scheme": "http", "server": ("test", 80), "client": ("test", 1)})
            return await protect_api(request, next_response)
        self.assertEqual(asyncio.run(run()).status_code, 403)
        self.assertEqual(asyncio.run(run(True)).status_code, 204)


if __name__ == "__main__":
    unittest.main()
