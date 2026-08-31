import asyncio
import math
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import db
from app.product_commissions import (PRODUCT_PRICES_PATH, ProductCommissionInputError,
                                     ProductCommissionUnavailable, get_product_commission)
from app.product_costs import list_product_forecast_costs
from app.routers.product_commissions import product_commission
from app.routers.products import save_product_rule
from tests.support import DatabaseTestCase, MockRequest, add_item, add_order


class ProductCommissionTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        with db.transaction() as connection:
            add_order(connection, 1, "P-1", "FBP", "2026-08-01T00:00:00Z", "已签收", 1)
            add_item(connection, 1, "P-1", "FBP", "1936515175", offer_id="OFFER-1", product_name_raw="测试商品")
            add_order(connection, 2, "P-2", "FBP", "2026-08-01T00:00:00Z", "已签收", 1)
            add_item(connection, 2, "P-2", "FBP", "1936515175", offer_id="OFFER-2", product_name_raw="测试商品")

    @staticmethod
    def _response(offer_id="OFFER-1", commissions=None, product_id=123456789):
        return {"items": [{
            "offer_id": offer_id,
            "product_id": product_id,
            "commissions": commissions if commissions is not None else {
                "sales_percent_fbp": 15,
                "sales_percent_rfbs": 12,
            },
        }]}

    def test_resolves_shop_sku_to_local_offer_and_calls_prices_api(self):
        with patch("app.product_commissions.client._post", return_value=self._response()) as post:
            result = get_product_commission(1, " 1936515175 ")
        post.assert_called_once_with(1, PRODUCT_PRICES_PATH, {
            "filter": {"offer_id": ["OFFER-1"], "visibility": "ALL"},
            "limit": 100,
        })
        self.assertEqual(result["offer_id"], "OFFER-1")
        self.assertEqual(result["product_id"], 123456789)
        self.assertEqual(result["sales_percent_fbp"], 15)
        self.assertEqual(result["sales_percent_rfbs"], 12)
        self.assertTrue(result["fetched_at"].endswith("Z"))

    def test_shop_is_part_of_lookup_and_unknown_sku_is_rejected(self):
        with patch("app.product_commissions.client._post", return_value=self._response("OFFER-2")) as post:
            result = get_product_commission(2, "1936515175")
        self.assertEqual(result["offer_id"], "OFFER-2")
        with self.assertRaises(ProductCommissionInputError):
            get_product_commission(1, "UNKNOWN")
        post.assert_called_once()

    def test_invalid_shop_and_missing_local_listing_are_rejected_without_api_call(self):
        with patch("app.product_commissions.client._post") as post:
            for shop_id, sku in ((True, "1936515175"), (3, "1936515175"), (1, ""), (1, "NOPE")):
                with self.subTest(shop_id=shop_id, sku=sku), self.assertRaises(ProductCommissionInputError):
                    get_product_commission(shop_id, sku)
        post.assert_not_called()

    def test_multiple_local_offer_ids_are_not_guessed(self):
        with db.transaction() as connection:
            add_order(connection, 1, "P-3", "FBP", "2026-08-02T00:00:00Z", "已签收", 1)
            add_item(connection, 1, "P-3", "FBP", "1936515175", offer_id="OFFER-OTHER")
        with patch("app.product_commissions.client._post") as post:
            with self.assertRaisesRegex(ProductCommissionInputError, "多个不同 offer_id"):
                get_product_commission(1, "1936515175")
        post.assert_not_called()

    def test_missing_local_offer_id_is_rejected(self):
        with db.transaction() as connection:
            add_order(connection, 1, "P-3", "FBP", "2026-08-02T00:00:00Z", "已签收", 1)
            add_item(connection, 1, "P-3", "FBP", "NO-OFFER", offer_id=None)
        with self.assertRaisesRegex(ProductCommissionInputError, "没有可解析的 offer_id"):
            get_product_commission(1, "NO-OFFER")

    def test_response_must_contain_the_unique_matching_offer(self):
        for response in ({"items": []}, {"items": [self._response("WRONG")["items"][0]]},
                         {"items": [self._response()["items"][0], self._response()["items"][0]]},
                         {"items": [{"offer_id": "OFFER-1", "commissions": []}]}):
            with self.subTest(response=response), patch("app.product_commissions.client._post", return_value=response):
                with self.assertRaises(ProductCommissionUnavailable):
                    get_product_commission(1, "1936515175")
        with patch("app.product_commissions.client._post", return_value={
            "items": [self._response("OTHER")["items"][0], self._response()["items"][0]],
        }):
            self.assertEqual(get_product_commission(1, "1936515175")["offer_id"], "OFFER-1")

    def test_exact_fbp_and_rfbs_fields_are_mapped_without_fallback(self):
        response = self._response(commissions={
            "sales_percent_fbp": 0,
            "sales_percent_rfbs": 12.5,
            "sales_percent_fbs": 99,
            "sales_percent_fbo": 98,
        })
        with patch("app.product_commissions.client._post", return_value=response):
            result = get_product_commission(1, "1936515175")
        self.assertEqual(result["sales_percent_fbp"], 0)
        self.assertEqual(result["sales_percent_rfbs"], 12.5)

        with patch("app.product_commissions.client._post", return_value=self._response(
                commissions={"sales_percent_fbs": 99, "sales_percent_fbo": 98})):
            result = get_product_commission(1, "1936515175")
        self.assertIsNone(result["sales_percent_fbp"])
        self.assertIsNone(result["sales_percent_rfbs"])

    def test_invalid_commission_numbers_are_rejected_and_booleans_are_not_numbers(self):
        for field, value in (("sales_percent_fbp", True), ("sales_percent_fbp", -1),
                             ("sales_percent_fbp", 101), ("sales_percent_fbp", math.nan),
                             ("sales_percent_rfbs", math.inf), ("sales_percent_rfbs", "12")):
            with self.subTest(field=field, value=value), patch(
                "app.product_commissions.client._post",
                return_value=self._response(commissions={field: value}),
            ):
                with self.assertRaises(ProductCommissionUnavailable):
                    get_product_commission(1, "1936515175")

    def test_ozon_errors_are_unavailable_and_router_maps_errors(self):
        with patch("app.product_commissions.client._post", side_effect=RuntimeError("timeout")):
            with self.assertRaisesRegex(ProductCommissionUnavailable, "timeout"):
                get_product_commission(1, "1936515175")
        with patch("app.routers.product_commissions.get_product_commission", side_effect=ProductCommissionInputError("bad")):
            with self.assertRaises(HTTPException) as context:
                product_commission(1, "1936515175")
        self.assertEqual(context.exception.status_code, 400)
        with patch("app.routers.product_commissions.get_product_commission", side_effect=ProductCommissionUnavailable("timeout")):
            with self.assertRaises(HTTPException) as context:
                product_commission(1, "1936515175")
        self.assertEqual(context.exception.status_code, 502)

    def test_canonical_product_listings_preserve_shop_sku_and_offer(self):
        with db.transaction() as connection:
            add_order(connection, 1, "P-A", "FBP", "2026-08-03T00:00:00Z", "已签收", 1)
            add_item(connection, 1, "P-A", "FBP", "SKU-A", offer_id="OFFER-A", product_name_raw="同一商品")
            add_order(connection, 2, "P-B", "FBP", "2026-08-03T00:00:00Z", "已签收", 1)
            add_item(connection, 2, "P-B", "FBP", "SKU-B", offer_id="OFFER-B", product_name_raw="同一商品")
        asyncio.run(save_product_rule(MockRequest({
            "kind": "merge", "primary_offer_id": "OFFER-A", "primary_sku": "SKU-A",
            "members": [{"key_type": "offer_id", "key_value": "OFFER-B"}],
        })))
        result = list_product_forecast_costs("同一商品")
        rows = [row for row in result["items"] if row["product_identity"] == "OFFER-A"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["listings"], [
            {"shop_id": 1, "sku": "SKU-A", "offer_id": "OFFER-A"},
            {"shop_id": 2, "sku": "SKU-B", "offer_id": "OFFER-B"},
        ])
        self.assertTrue(set(rows[0]) - {"listings"} >= {
            "product_identity", "display_name", "ozon_skus", "offer_ids", "forecast_cost", "configured",
        })


if __name__ == "__main__":
    unittest.main()
