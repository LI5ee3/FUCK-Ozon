import json
import tempfile
import unittest
from pathlib import Path

from app import db, importer
from app.main import SYNC_MODULES, app, orders, returns, rfbs_returns, stock, timeliness


class ModuleViewsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()
        with db.transaction() as connection:
            connection.execute("""INSERT INTO orders(shop_id,posting_number,channel,created_at,shipped_at,
              delivered_at,status_raw,shipped,source) VALUES(1,'P-1','FBP','2026-08-01T00:00:00Z',
              '2026-08-01T02:00:00Z','2026-08-02T02:00:00Z','已签收',1,'api')""")
            connection.execute("INSERT INTO return_records VALUES(1,'R-1','2026-08-02T00:00:00Z','P-1','S-1',?,?)",
                               (json.dumps({"product": {"quantity": 1},
                                            "return_reason_name": "Товар поврежден, но упаковка цела",
                                            "visual": {"status": {"display_name": "На складе"}}}),
                                "2026-08-02T00:00:00Z"))
            connection.execute("INSERT INTO stock_snapshots VALUES(1,'S-1','2026-08-03T00:00:00Z',?)",
                               (json.dumps({"offer_id": "O-1", "stocks": [
                                   {"sku": "S-1", "type": "fbp", "present": 2, "reserved": 1}]}),))
            connection.execute("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,posting_number,offer_id,sku,product_name,
              status_raw,status_name,payload,fetched_at) VALUES(
              1,10,'174763409-R14','2026-08-04T00:00:00Z','P-1','O-1','S-1','商品',
              'OnSellerClarification','На уточнении','{}','2026-08-04T00:00:00Z')""")

    def tearDown(self):
        self.temp.cleanup()

    def test_each_view_reads_only_its_module_and_shop(self):
        views = [timeliness, returns, rfbs_returns, stock]
        for view in views:
            self.assertEqual(view(1)["total"], 1, view.__name__)
            self.assertEqual(view(2)["total"], 0, view.__name__)
        item = returns(1)["items"][0]
        self.assertEqual(item["status"], "已到仓库")
        self.assertEqual(item["reason"], "商品损坏但包装完好")
        rfbs_item = rfbs_returns(1)["items"][0]
        self.assertEqual(rfbs_item["return_number"], "174763409-R14")
        self.assertEqual(rfbs_item["status_name"], "确认中")

    def test_removed_modules_are_absent(self):
        with db.connect() as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("analytics_records", tables)
        self.assertNotIn("price_snapshots", tables)
        self.assertIn("exchange_rates", tables)
        for table in ("finance_records", "finance_reports", "order_costs",
                      "exchange_rate_history", "currency_conversions", "webhook_events",
                      "order_status_history", "warehouse_stocks", "fbo_stocks"):
            self.assertNotIn(table, tables)
        paths = {route.path for route in app.routes}
        for path in ("/api/premium", "/api/prices", "/api/finance", "/api/profits"):
            self.assertNotIn(path, paths)
        self.assertIn("/api/exchange-rates", paths)
        self.assertFalse(any(path.startswith("/api/ozon/push") or
                             path.startswith("/api/ozon/pending-events") for path in paths))
        self.assertEqual(SYNC_MODULES, {"orders", "returns", "stock"})
        self.assertFalse(hasattr(importer, "import_costs"))
        self.assertNotIn("/api/logout", paths)
        root = Path(__file__).resolve().parent.parent
        self.assertNotIn("openpyxl", (root / "requirements.txt").read_text().lower())

    def test_exception_order_pages_are_separate_from_complaints(self):
        root = Path(__file__).resolve().parent.parent
        html = (root / "static/index.html").read_text()
        script = (root / "static/app.js").read_text()
        returns_nav = html.index('data-page="returns"')
        complaint_nav = html.index('data-page="complaintPlaceholder"')
        self.assertLess(returns_nav, complaint_nav)
        self.assertIn("<span>异常订单明细</span>", html)
        self.assertIn("<span>异常订单投诉</span>", html)

        returns_page = html.split('<section id="returns"', 1)[1].split(
            '<section id="complaintPlaceholder"', 1)[0]
        self.assertIn("取消明细", returns_page)
        self.assertIn("退货明细", returns_page)
        self.assertNotIn("投诉管理", returns_page)
        self.assertNotIn("returns-complaints", returns_page)

        placeholder = html.split('<section id="complaintPlaceholder"', 1)[1].split(
            "</section>", 1)[0]
        self.assertIn("异常订单投诉功能正在规划中", placeholder)
        self.assertIn("投诉记录方式将在后续版本重新设计", placeholder)
        self.assertNotIn("<form", placeholder)
        self.assertNotIn("<table", placeholder)
        self.assertIn("Promise.all([loadReturns(), loadRfbsReturns()])", script)
        self.assertNotIn("loadComplaints", script)
        self.assertNotIn("data-add-complaint", script)
        self.assertIn('if(page==="complaintPlaceholder") renderDataThrough(null)', script)
        self.assertIn("/api/complaints", {route.path for route in app.routes})

    def test_order_view_translates_status_and_cancellation_reason(self):
        with db.transaction() as connection:
            connection.execute("""UPDATE orders SET status_raw='awaiting_registration',
              cancel_reason_raw='Покупатель отменил заказ: не устроил срок доставки'
              WHERE posting_number='P-1'""")
        item = orders(1)["items"][0]
        self.assertEqual(item["status_raw"], "等待登记")
        self.assertEqual(item["cancel_reason_raw"], "买家取消：配送时效不符合预期")

    def test_stock_groups_channels_by_sku_and_keeps_zero_inventory(self):
        payload = lambda sku, values: json.dumps({"offer_id": f"O-{sku}", "stocks": [
          {"sku": sku, "type": channel, "present": present, "reserved": reserved}
          for channel, present, reserved in values]})
        with db.transaction() as connection:
            connection.execute("DELETE FROM stock_snapshots")
            connection.execute("INSERT INTO stock_snapshots VALUES(1,'A','2026-08-05T00:00:00Z',?)",
                               (payload("S-1", [("fbp", 4, 0), ("rfbs", 2, 1), ("fbo", 3, 0)]),))
            connection.execute("INSERT INTO stock_snapshots VALUES(1,'B','2026-08-05T00:00:00Z',?)",
                               (payload("S-0", [("fbp", 0, 0), ("rfbs", 0, 0)]),))
        data = stock(1)
        self.assertEqual(data["total"], 2)
        item = next(row for row in data["items"] if row["sku"] == "S-1")
        self.assertEqual([row["channel"] for row in item["channels"]],
                         ["FBP", "realFBS", "WHD"])
        self.assertEqual(item["present"], 9)


if __name__ == "__main__":
    unittest.main()
