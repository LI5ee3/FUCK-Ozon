import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from app import db
from app.importer import _shipping, import_csv
from app.main import upload
from app.routers.export import export_orders
from tests.support import DatabaseTestCase


class ImportTest(DatabaseTestCase):
    def test_shipping_anomaly_detects_conflicting_evidence(self):
        self.assertEqual(_shipping({"状态": "已签收"})[:3], (1, None, 1))
        self.assertEqual(_shipping({"状态": "已取消", "已转移配送": "2026-08-01T00:00:00Z"})[:3],
                         (1, 1, 1))

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
