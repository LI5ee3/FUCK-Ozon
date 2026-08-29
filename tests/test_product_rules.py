import asyncio
import unittest

from fastapi import HTTPException

from app import db
from app.products import clean_product_name, load_product_rules, resolve_product
from app.routers.products import product_rules, save_product_rule
from tests.support import DatabaseTestCase, MockRequest as Request, add_item, add_order


class ProductRulesTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        with db.transaction() as connection:
            self._product(connection, 1, "P-1", "SKU-1", "OFFER-1", "Новый\u00a0平台商品")
            self._product(connection, 2, "P-2", "SKU-1", "OFFER-1", "另一店商品")

    @staticmethod
    def _product(connection, shop, posting, sku, offer, name):
        add_order(connection, shop, posting, "FBP", "2026-08-01T00:00:00Z", "已签收", 1)
        add_item(connection, shop, posting, "FBP", sku, offer_id=offer,
                 product_name_raw=name)

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
        self.assertEqual(rules["names"][("OFFER-1", "SKU-1")], "平台商品")
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
        group_id = result["groups"][0]["id"]
        asyncio.run(save_product_rule(Request({"kind": "dissolve", "id": group_id})))
        self.assertEqual(product_rules()["groups"], [])
