import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app import db
from app.main import product_rules, save_product_rule
from app.products import clean_product_name, load_product_rules, resolve_product


class Request:
    def __init__(self, value):
        self.value = value

    async def json(self):
        return self.value


class ProductRulesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()
        with db.transaction() as connection:
            self._product(connection, 1, "P-1", "SKU-1", "OFFER-1", "Новый\u00a0平台商品")
            self._product(connection, 2, "P-2", "SKU-1", "OFFER-1", "另一店商品")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _product(connection, shop, posting, sku, offer, name):
        connection.execute("""INSERT INTO orders(shop_id,posting_number,channel,created_at,
          status_raw,shipped,source) VALUES(?,?,'FBP','2026-08-01T00:00:00Z','已签收',1,'api')""",
                           (shop, posting))
        connection.execute("""INSERT INTO order_items(shop_id,channel,posting_number,sku,offer_id,
          product_name_raw,quantity,source) VALUES(?,'FBP',?,?,?,?,1,'api')""",
                           (shop, posting, sku, offer, name))

    def test_name_cleaning_and_sku_only_short_name(self):
        self.assertEqual(clean_product_name("  Новый&#xA0;A Новый\u00a0B  "), "A B")
        with self.assertRaises(HTTPException):
            asyncio.run(save_product_rule(Request({"kind": "short_name", "key_type": "offer_id",
                                                    "key_value": "OFFER-1", "short_name": "错误"})))
        asyncio.run(save_product_rule(Request({"kind": "short_name", "sku": "SKU-1",
                                               "short_name": "中文短名"})))
        asyncio.run(save_product_rule(Request({"kind": "short_name", "sku": "SKU-1",
                                               "short_name": "更新短名"})))
        with db.connect() as connection:
            rules = load_product_rules(connection)
            count = connection.execute("SELECT COUNT(*) FROM product_short_names WHERE key_type='sku'").fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(resolve_product(rules, "SKU-1", "OFFER-1", "Новый\u00a0原名")["display_name"],
                         "更新短名")
        self.assertEqual(resolve_product(rules, "OTHER", "OFFER-1", "Новый\u00a0原名")["display_name"], "原名")

    def test_primary_offer_is_global_identity_but_shops_remain_separate(self):
        with db.transaction() as connection:
            self._product(connection, 1, "P-3", "SKU-2", "OFFER-2", "第二件商品")
        asyncio.run(save_product_rule(Request({"kind": "short_name", "sku": "SKU-1",
                                               "short_name": "统一名称"})))
        asyncio.run(save_product_rule(Request({"kind": "merge", "primary_offer_id": "OFFER-1",
          "primary_sku": "SKU-1", "members": [{"key_type": "offer_id", "key_value": "OFFER-2"}]})))
        with db.connect() as connection:
            rules = load_product_rules(connection)
        resolved = resolve_product(rules, "SKU-1", "OFFER-1", "平台商品")
        self.assertEqual((resolved["identity"], resolved["display_name"]), ("OFFER-1", "统一名称"))
        self.assertEqual(resolve_product(rules, "SKU-2")["identity"], "OFFER-1")
        result = product_rules()
        self.assertEqual(result["summary"], {"short_names": 1, "merges": 1})
        self.assertNotIn("brands", result)
        self.assertNotIn("name", result["groups"][0])

    def test_legacy_offer_short_names_and_groups_migrate_without_silent_loss(self):
        with db.transaction() as connection:
            self._product(connection, 1, "P-U", "SKU-U", "OFFER-U", "唯一")
            self._product(connection, 1, "P-A1", "SKU-A1", "OFFER-A", "歧义一")
            self._product(connection, 1, "P-A2", "SKU-A2", "OFFER-A", "歧义二")
            connection.executemany("INSERT INTO product_short_names VALUES('offer_id',?,?,'now')",
                                   [("OFFER-U", "唯一短名"), ("OFFER-A", "歧义短名")])
            active = connection.execute("INSERT INTO product_groups(name,created_at,updated_at) VALUES('旧组一','now','now')").lastrowid
            connection.executemany("INSERT INTO product_group_members VALUES(?,?,?)", [
                (active, "offer_id", "OFFER-U"), (active, "sku", "SKU-U")])
            pending = connection.execute("INSERT INTO product_groups(name,created_at,updated_at) VALUES('旧组二','now','now')").lastrowid
            connection.executemany("INSERT INTO product_group_members VALUES(?,?,?)", [
                (pending, "offer_id", "OFFER-U2"), (pending, "offer_id", "OFFER-A")])
        db.init_db()
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT short_name FROM product_short_names WHERE key_type='sku' AND key_value='SKU-U'").fetchone()[0], "唯一短名")
            self.assertIsNone(connection.execute("SELECT 1 FROM product_short_names WHERE key_type='sku' AND key_value IN ('SKU-A1','SKU-A2')").fetchone())
            statuses = {row["group_id"]: row["status"] for row in connection.execute("SELECT group_id,status FROM product_group_config")}
            note = connection.execute("SELECT note FROM product_short_name_migrations WHERE key_value='OFFER-A'").fetchone()[0]
        self.assertEqual((statuses[active], statuses[pending]), ("active", "pending"))
        self.assertIn("无法唯一关联", note)


if __name__ == "__main__":
    unittest.main()
