import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app import db
from app.importer import import_csv
from app.main import _export_range, export_module, export_orders


ROOT = Path(__file__).resolve().parent.parent


async def rows(response):
    return [json.loads(line) async for line in response.body_iterator]


class TransferPageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()

    def tearDown(self):
        self.temp.cleanup()

    def test_export_range_uses_beijing_day_and_rejects_reverse_dates(self):
        value = _export_range("2026-08-01", "2026-08-01")
        self.assertEqual(value[2:5], ("2026-07-31T16:00:00+00:00", "2026-08-01T16:00:00+00:00", True))
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

    def test_rules_ignore_dates_and_page_hides_format_names(self):
        with db.transaction() as connection:
            connection.execute("INSERT INTO brand_rules(brand_name,keyword,priority,enabled,updated_at) VALUES('A','a',1,1,'2020-01-01T00:00:00Z')")
            connection.execute("INSERT INTO product_short_names VALUES('sku','SKU-A','短名','2026-08-01T00:00:00Z')")
            group_id = connection.execute("INSERT INTO product_groups(name,created_at,updated_at) VALUES('旧名','now','now')").lastrowid
            connection.executemany("INSERT INTO product_group_members VALUES(?,?,?)", [
                (group_id, "sku", "SKU-A"), (group_id, "offer_id", "O-A")])
            connection.execute("INSERT INTO product_group_config VALUES(?,'O-A','SKU-A','active','')", (group_id,))
        exported = asyncio.run(rows(export_module("rules", date_from="2026-08-01", date_to="2026-08-01")))
        self.assertEqual({row.get("rule_type") for row in exported[1:]}, {"中文短名称", "主货号合并"})
        self.assertNotIn("旧名", json.dumps(exported, ensure_ascii=False))
        self.assertNotIn("品牌规则", json.dumps(exported, ensure_ascii=False))

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
