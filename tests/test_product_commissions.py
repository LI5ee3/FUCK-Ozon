import asyncio
import math
import unittest
from unittest.mock import call, patch

from fastapi import HTTPException

from app import db
from app.product_commissions import (PRODUCT_INFO_PATH, PRODUCT_PRICES_PATH,
                                     ProductCommissionInputError, ProductCommissionUnavailable,
                                     get_product_commission)
from app.product_costs import list_product_forecast_costs
from app.routers.product_commissions import product_commission
from app.routers.products import save_product_rule
from tests.support import DatabaseTestCase, MockRequest, add_item, add_order


class ProductCommissionTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        with db.transaction() as connection:
            add_order(connection, 1, "P-1", "FBP", "2026-08-01T00:00:00Z", "已签收", 1)
            add_item(connection, 1, "P-1", "FBP", "1936515175", offer_id="OLD-OFFER", product_name_raw="测试商品")
            add_order(connection, 2, "P-2", "FBP", "2026-08-01T00:00:00Z", "已签收", 1)
            add_item(connection, 2, "P-2", "FBP", "1936515175", offer_id="SHOP-2-OFFER", product_name_raw="测试商品")

    @staticmethod
    def _info_response(sku="1936515175", product_id=123456789, offer_id="CURRENT-OFFER", *, include_sku=True):
        item = {"id": product_id, "offer_id": offer_id}
        if include_sku:
            item["sources"] = [{"sku": int(sku) if str(sku).isdigit() else sku}]
        return {"items": [item]}

    @staticmethod
    def _price_response(product_id=123456789, offer_id="CURRENT-OFFER", commissions=None):
        return {"items": [{
            "product_id": product_id,
            "offer_id": offer_id,
            "commissions": commissions if commissions is not None else {
                "sales_percent_fbp": 15,
                "sales_percent_rfbs": 12,
            },
        }]}

    def _post_pair(self, info=None, prices=None):
        return patch(
            "app.product_commissions.client._post",
            side_effect=[
                self._info_response() if info is None else info,
                self._price_response() if prices is None else prices,
            ],
        )

    def test_resolves_shop_sku_through_v3_and_queries_prices_by_product_id(self):
        with self._post_pair() as post:
            result = get_product_commission(1, " 1936515175 ")
        post.assert_has_calls([
            call(1, PRODUCT_INFO_PATH, {"sku": ["1936515175"]}),
            call(1, PRODUCT_PRICES_PATH, {
                "filter": {"product_id": ["123456789"], "visibility": "ALL"},
                "limit": 100,
            }),
        ])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(result["offer_id"], "CURRENT-OFFER")
        self.assertEqual(result["product_id"], 123456789)
        self.assertEqual(result["sales_percent_fbp"], 15)
        self.assertEqual(result["sales_percent_rfbs"], 12)
        self.assertTrue(result["fetched_at"].endswith("Z"))

    def test_shop_is_part_of_local_sku_lookup_and_unknown_sku_is_rejected(self):
        with self._post_pair(
            info=self._info_response(offer_id="SHOP-2-CURRENT"),
            prices=self._price_response(offer_id="SHOP-2-CURRENT"),
        ):
            result = get_product_commission(2, "1936515175")
        self.assertEqual(result["offer_id"], "SHOP-2-CURRENT")
        with patch("app.product_commissions.client._post") as post:
            with self.assertRaises(ProductCommissionInputError):
                get_product_commission(1, "UNKNOWN")
        post.assert_not_called()

    def test_invalid_shop_and_missing_local_sku_are_rejected_without_api_call(self):
        with patch("app.product_commissions.client._post") as post:
            for shop_id, sku in ((True, "1936515175"), (3, "1936515175"), (1, ""), (1, "NOPE")):
                with self.subTest(shop_id=shop_id, sku=sku), self.assertRaises(ProductCommissionInputError):
                    get_product_commission(shop_id, sku)
        post.assert_not_called()

    def test_historical_offer_changes_do_not_create_a_local_conflict(self):
        with db.transaction() as connection:
            add_order(connection, 1, "P-3", "FBP", "2026-08-02T00:00:00Z", "已签收", 1)
            add_item(connection, 1, "P-3", "FBP", "1936515175", offer_id="NEW-OFFER")
        with self._post_pair(
            info=self._info_response(offer_id="NEW-OFFER"),
            prices=self._price_response(offer_id="NEW-OFFER"),
        ) as post:
            result = get_product_commission(1, "1936515175")
        self.assertEqual(result["offer_id"], "NEW-OFFER")
        self.assertEqual(post.call_count, 2)

    def test_local_sku_validation_does_not_require_a_historical_offer(self):
        with db.transaction() as connection:
            add_order(connection, 1, "P-3", "FBP", "2026-08-02T00:00:00Z", "已签收", 1)
            add_item(connection, 1, "P-3", "FBP", "NO-OFFER", offer_id=None)
        with self._post_pair(info=self._info_response(sku="NO-OFFER")):
            result = get_product_commission(1, "NO-OFFER")
        self.assertEqual(result["sku"], "NO-OFFER")

    def test_v3_response_must_uniquely_match_requested_sku(self):
        responses = (
            [],
            {"items": "invalid"},
            {"items": []},
            {"items": [{"id": 1, "offer_id": "CURRENT", "sources": [{"sku": 999}]}]},
            {"items": [self._info_response()["items"][0], self._info_response()["items"][0]]},
            {"items": [{"id": 1, "offer_id": "CURRENT"}, {"id": 2, "offer_id": "OTHER"}]},
            {"items": [{"id": 1, "offer_id": "CURRENT", "sources": "invalid"}]},
        )
        for response in responses:
            with self.subTest(response=response), patch(
                "app.product_commissions.client._post", return_value=response,
            ):
                with self.assertRaises(ProductCommissionUnavailable):
                    get_product_commission(1, "1936515175")

    def test_v3_single_item_without_sku_metadata_is_accepted_after_exact_sku_request(self):
        with self._post_pair(info=self._info_response(include_sku=False)):
            result = get_product_commission(1, "1936515175")
        self.assertEqual(result["product_id"], 123456789)

    def test_v3_product_id_must_be_a_positive_int_or_numeric_string(self):
        for product_id in (True, 0, -1, 1.5, "", "not-a-number", None):
            with self.subTest(product_id=product_id), patch(
                "app.product_commissions.client._post",
                return_value=self._info_response(product_id=product_id),
            ):
                with self.assertRaises(ProductCommissionUnavailable):
                    get_product_commission(1, "1936515175")

    def test_v3_current_offer_id_must_be_a_non_empty_string(self):
        for offer_id in (None, "", "  ", 123, True):
            with self.subTest(offer_id=offer_id), patch(
                "app.product_commissions.client._post",
                return_value=self._info_response(offer_id=offer_id),
            ):
                with self.assertRaises(ProductCommissionUnavailable):
                    get_product_commission(1, "1936515175")

    def test_v5_response_must_match_product_id_once_and_current_offer(self):
        responses = (
            {"items": []},
            {"items": [self._price_response(product_id=999)["items"][0]]},
            {"items": [self._price_response()["items"][0], self._price_response()["items"][0]]},
            self._price_response(offer_id="OLD-OFFER"),
            {"items": [{"product_id": 123456789, "offer_id": "CURRENT-OFFER", "commissions": []}]},
        )
        for response in responses:
            with self.subTest(response=response), self._post_pair(prices=response):
                with self.assertRaises(ProductCommissionUnavailable):
                    get_product_commission(1, "1936515175")

    def test_v3_string_product_id_is_normalized_for_v5_but_preserved_in_response(self):
        with self._post_pair(
            info=self._info_response(product_id="243686911", offer_id="CURRENT-OFFER"),
            prices=self._price_response(product_id="243686911"),
        ) as post:
            result = get_product_commission(1, "1936515175")
        self.assertEqual(result["product_id"], "243686911")
        self.assertEqual(post.call_args_list[1], call(1, PRODUCT_PRICES_PATH, {
            "filter": {"product_id": ["243686911"], "visibility": "ALL"},
            "limit": 100,
        }))

    def test_exact_fbp_and_rfbs_fields_are_mapped_without_fallback(self):
        response = self._price_response(commissions={
            "sales_percent_fbp": 0,
            "sales_percent_rfbs": 12.5,
            "sales_percent_fbs": 99,
            "sales_percent_fbo": 98,
        })
        with self._post_pair(prices=response):
            result = get_product_commission(1, "1936515175")
        self.assertEqual(result["sales_percent_fbp"], 0)
        self.assertEqual(result["sales_percent_rfbs"], 12.5)

        with self._post_pair(prices=self._price_response(commissions={"sales_percent_fbs": 99, "sales_percent_fbo": 98})):
            result = get_product_commission(1, "1936515175")
        self.assertIsNone(result["sales_percent_fbp"])
        self.assertIsNone(result["sales_percent_rfbs"])

    def test_invalid_commission_numbers_are_rejected_and_booleans_are_not_numbers(self):
        for field, value in (("sales_percent_fbp", True), ("sales_percent_fbp", -1),
                             ("sales_percent_fbp", 101), ("sales_percent_fbp", math.nan),
                             ("sales_percent_rfbs", math.inf), ("sales_percent_rfbs", "12")):
            with self.subTest(field=field, value=value), self._post_pair(
                prices=self._price_response(commissions={field: value}),
            ):
                with self.assertRaises(ProductCommissionUnavailable):
                    get_product_commission(1, "1936515175")

    def test_ozon_errors_are_unavailable_and_router_maps_errors(self):
        with patch("app.product_commissions.client._post", side_effect=RuntimeError("timeout")):
            with self.assertRaisesRegex(ProductCommissionUnavailable, "timeout"):
                get_product_commission(1, "1936515175")
        with self._post_pair(prices=RuntimeError("prices timeout")):
            with self.assertRaisesRegex(ProductCommissionUnavailable, "prices timeout"):
                get_product_commission(1, "1936515175")
        with patch("app.routers.product_commissions.get_product_commission", side_effect=ProductCommissionInputError("bad")):
            with self.assertRaises(HTTPException) as context:
                product_commission(1, "1936515175")
        self.assertEqual(context.exception.status_code, 400)
        with patch("app.routers.product_commissions.get_product_commission", side_effect=ProductCommissionUnavailable("timeout")):
            with self.assertRaises(HTTPException) as context:
                product_commission(1, "1936515175")
        self.assertEqual(context.exception.status_code, 502)

    def test_canonical_product_listings_preserve_shop_sku_and_deduplicate_historical_offers(self):
        with db.transaction() as connection:
            add_order(connection, 1, "P-A", "FBP", "2026-08-03T00:00:00Z", "已签收", 1)
            add_item(connection, 1, "P-A", "FBP", "SKU-A", offer_id="OFFER-A", product_name_raw="同一商品")
            add_order(connection, 1, "P-A-OLD", "FBP", "2026-08-03T00:00:00Z", "已签收", 1)
            add_item(connection, 1, "P-A-OLD", "FBP", "SKU-A", offer_id="OFFER-A-OLD", product_name_raw="同一商品")
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
            {"shop_id": 1, "sku": "SKU-A", "offer_id": None, "offer_ids": ["OFFER-A", "OFFER-A-OLD"]},
            {"shop_id": 2, "sku": "SKU-B", "offer_id": "OFFER-B", "offer_ids": ["OFFER-B"]},
        ])
        self.assertTrue(set(rows[0]) - {"listings"} >= {
            "product_identity", "display_name", "ozon_skus", "offer_ids", "forecast_cost", "configured",
        })


if __name__ == "__main__":
    unittest.main()
