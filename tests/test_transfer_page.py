import asyncio
import json
import unittest

from fastapi import HTTPException

from app import db
from app.importer import import_csv
from app.main import _export_range, export_module, export_orders
from tests.support import DatabaseTestCase


async def rows(response):
    return [json.loads(line) async for line in response.body_iterator]


class TransferPageTest(DatabaseTestCase):
    def test_export_range_uses_beijing_day_and_rejects_reverse_dates(self):
        value = _export_range("2026-08-01", "2026-08-01")
        self.assertEqual(value[2:5], ("2026-07-31T16:00:00Z", "2026-08-01T16:00:00Z", True))
        with self.assertRaises(HTTPException):
            _export_range("2026-08-02", "2026-08-01")

    def test_order_export_filters_dates_and_keeps_full_export_compatibility(self):
        with db.transaction() as connection:
            connection.executemany("""INSERT INTO orders(
              shop_id,posting_number,channel,created_at,status_raw,shipped,source)
              VALUES(1,?,'FBP',?,'已签收',1,'api')""", [
                ("BEFORE", "2026-07-31T15:59:59Z"),
                ("START", "2026-07-31T16:00:00Z"),
                ("END", "2026-08-01T15:59:59Z"),
                ("AFTER", "2026-08-01T16:00:00Z"),
            ])
        filtered = asyncio.run(rows(export_orders(1, "2026-08-01", "2026-08-01")))
        full = asyncio.run(rows(export_orders(1)))
        self.assertEqual([row["posting_number"] for row in filtered[1:]], ["START", "END"])
        self.assertEqual(len(full[1:]), 4)
        response = export_orders(1)
        self.assertEqual(response.media_type, "application/x-ndjson")
        self.assertIn("orders.jsonl", response.headers["content-disposition"])

    def test_order_and_risk_exports_include_current_product_fields(self):
        with db.transaction() as connection:
            connection.execute("""INSERT INTO orders(
              shop_id,posting_number,channel,created_at,shipped_at,delivered_at,status_raw,
              shipped,data_anomaly,amount_original,amount_currency,source)
              VALUES(1,'CURRENT','FBP','2026-08-01T00:00:00Z','2026-08-01T01:00:00Z',
                '2026-08-02T00:00:00Z','已签收',1,0,12,'USD','api')""")
            connection.execute("""INSERT INTO order_items(
              shop_id,posting_number,channel,sku,offer_id,product_name_raw,quantity,unit_price,price_currency,source)
              VALUES(1,'CURRENT','FBP','SKU-1','OFFER-1','Product',2,6,'USD','api')""")
        order = asyncio.run(rows(export_orders(1, "2026-08-01", "2026-08-01")))[1]
        risk = asyncio.run(rows(export_module("risk", 1, "2026-08-01", "2026-08-01")))[1]
        self.assertEqual((order["pieces"], order["sku_types"], order["items"][0]["offer_id"]),
                         (2, 1, "OFFER-1"))
        self.assertEqual((order["shipped_at"], order["delivered_at"]),
                         ("2026-08-01T01:00:00Z", "2026-08-02T00:00:00Z"))
        self.assertEqual((risk["analysis_identity"], risk["analysis_product_name"]),
                         ("SKU-1", "Product"))

    def test_returns_export_filters_cancel_and_application_dates_separately(self):
        payload = json.dumps({"product": {"quantity": 1}})
        with db.transaction() as connection:
            connection.executemany("INSERT INTO return_records VALUES(1,?,?,?,?,?,?)", [
                ("C-IN", "2026-08-01T00:00:00Z", "POST-IN", "SKU", payload, "now"),
                ("C-OUT", "2026-08-02T16:00:00Z", "POST-OUT", "SKU", payload, "now"),
            ])
            connection.executemany("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,posting_number,payload,fetched_at)
              VALUES(1,?,?,?,?,?,?)""", [
                (1, "RET-IN", "2026-08-01T01:00:00Z", "POST-IN", "{}", "now"),
                (2, "RET-OUT", "2026-08-02T16:00:00Z", "POST-OUT", "{}", "now"),
            ])
        exported = asyncio.run(rows(export_module("returns", 1, "2026-08-01", "2026-08-01")))
        self.assertEqual([(row["record_type"], row["posting_number"]) for row in exported[1:]],
                         [("取消明细", "POST-IN"), ("退货明细", "POST-IN")])

    def test_import_history_keeps_only_latest_ten_without_removing_orders(self):
        header = "订单号;发货号码;状态;SKU;数量;已创建\n"
        for index in range(12):
            content = header + f"M-{index};P-{index};已签收;SKU-{index};1;2026-08-01T00:00:00Z\n"
            import_csv(1, "FBP", f"{index}.csv", content.encode())
        with db.connect() as connection:
            batches = connection.execute("SELECT id FROM import_batches ORDER BY id").fetchall()
            orders = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            detached = connection.execute("SELECT COUNT(*) FROM orders WHERE import_batch_id IS NULL").fetchone()[0]
        self.assertEqual(len(batches), 10)
        self.assertEqual((orders, detached), (12, 2))


if __name__ == "__main__":
    unittest.main()
