import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app import db
from app.pricing import get_pricing
from app.ozon.client import BEIJING
from tests.support import DatabaseTestCase, add_item, add_order, add_stock_snapshot


NOW = datetime(2026, 9, 2, 12, tzinfo=BEIJING)


def stamp(day):
    return datetime.combine(day, time(12), BEIJING).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def add_price(connection, shop_id, observed_at, product_id, offer_id, *, price="100", marketing=None,
              currency="RUB", acquiring="0", commission=0, color="GREEN"):
    index = {
        "color_index": color,
        "ozon_index_data": {"min_price": price, "min_price_currency": currency, "price_index_value": "1"},
        "external_index_data": {}, "self_marketplaces_index_data": {},
    }
    values = {
        "shop_id": shop_id, "product_id": str(product_id), "offer_id": offer_id,
        "observed_at": observed_at, "currency": currency, "price": price, "old_price": None,
        "min_price": price, "marketing_seller_price": marketing, "auto_action_enabled": 0,
        "acquiring": acquiring, "price_index_color": color, "ozon_min_price": price,
        "ozon_price_index": "1", "external_min_price": None, "external_price_index": None,
        "self_marketplace_min_price": None, "self_marketplace_price_index": None,
        "commissions_json": json.dumps({"sales_percent_fbp": commission, "sales_percent_rfbs": commission + 1,
                                          "sales_percent_fbo": commission + 2}),
        "marketing_actions_json": None, "price_indexes_json": json.dumps(index),
        "payload_json": json.dumps({"product_id": product_id, "offer_id": offer_id, "name": offer_id}),
        "snapshot_key": f"product_id:{product_id}",
    }
    columns = ",".join(values)
    connection.execute(f"INSERT INTO product_price_snapshots({columns}) VALUES({','.join('?' for _ in values)})",
                       tuple(values.values()))


def add_successful_price_run(connection, shop_id, observed_at):
    connection.execute("""INSERT INTO sync_runs(shop_id,module,status,data_through)
      VALUES(?,'prices','success',?)""", (shop_id, observed_at))


def add_erp(connection, shop_id, order_number, sku, *, offer_id, quantity=1, unit_cost="10",
            batch_id=None, updated_at="2026-08-31T00:00:00Z"):
    if batch_id is None:
        batch_id = connection.execute("""INSERT INTO erp_cost_import_batches(
          shop_id,filename,row_count,parsed_count,inserted_count,updated_count,unchanged_count,imported_at)
          VALUES(?, 'test.xlsx',1,1,1,0,0,?)""", (shop_id, updated_at)).lastrowid
    connection.execute("""INSERT INTO erp_order_item_costs(
      shop_id,erp_order_number,ozon_sku,offer_id,quantity,unit_cost,total_cost,
      source_batch_id,source_row_no,raw_payload_json,imported_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (shop_id, order_number, sku, offer_id, quantity,
      unit_cost, str(Decimal(unit_cost) * quantity), batch_id, 1, "{}", updated_at, updated_at))


def add_sale(connection, shop_id, posting, channel, sku, offer_id, quantity, unit_price, currency, day):
    add_order(connection, shop_id, posting, channel, stamp(day), "已签收", 1)
    add_item(connection, shop_id, posting, channel, sku, quantity, offer_id=offer_id,
             unit_price=unit_price, price_currency=currency, product_name_raw=offer_id)


class PricingTest(DatabaseTestCase):
    def rates(self):
        return {"USD": {"sales_exchange_rate": "10"}, "CNY": {"sales_exchange_rate": "2"}}

    def test_latest_complete_price_batch_drops_missing_products_and_isolated_per_shop(self):
        with db.transaction() as connection:
            add_price(connection, 1, "2026-08-31T00:00:00Z", 1, "A")
            add_price(connection, 1, "2026-08-31T00:00:00Z", 2, "B")
            add_price(connection, 1, "2026-09-01T00:00:00Z", 1, "A")
            add_price(connection, 2, "2026-08-30T00:00:00Z", 3, "C")
            add_price(connection, 2, "2026-08-31T00:00:00Z", 3, "C")
            add_successful_price_run(connection, 1, "2026-09-01T00:00:00Z")
            add_successful_price_run(connection, 2, "2026-08-31T00:00:00Z")
        result = get_pricing(now=NOW, size=100)
        self.assertEqual([(item["shop_id"], item["product"]["offer_id"]) for item in result["items"]],
                         [(1, "A"), (2, "C")])
        self.assertEqual([item["snapshot_key"] for item in result["items"]],
                         ["product_id:1", "product_id:3"])

    def test_offer_sku_mapping_isolated_by_shop_and_does_not_guess_from_other_shop(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_price(connection, 1, observed, 71, "SAME-OFFER")
            add_price(connection, 1, observed, 73, "ONLY-SHOP2")
            add_price(connection, 2, observed, 72, "SAME-OFFER")
            add_price(connection, 2, observed, 74, "ONLY-SHOP2")
            add_successful_price_run(connection, 1, observed)
            add_successful_price_run(connection, 2, observed)
            add_order(connection, 1, "MAP-1", "FBP", stamp(date(2026, 8, 31)), "已签收", 1)
            add_item(connection, 1, "MAP-1", "FBP", "SKU-A", offer_id="SAME-OFFER")
            add_order(connection, 2, "MAP-2", "FBP", stamp(date(2026, 8, 31)), "已签收", 1)
            add_item(connection, 2, "MAP-2", "FBP", "SKU-B", offer_id="SAME-OFFER")
            add_order(connection, 2, "MAP-ONLY-2", "FBP", stamp(date(2026, 8, 31)), "已签收", 1)
            add_item(connection, 2, "MAP-ONLY-2", "FBP", "SKU-B-ONLY", offer_id="ONLY-SHOP2")
        result = get_pricing(0, now=NOW, size=100)
        items = {(item["shop_id"], item["product"]["offer_id"]): item for item in result["items"]}
        self.assertEqual(items[(1, "SAME-OFFER")]["product"]["sku"], "SKU-A")
        self.assertEqual(items[(2, "SAME-OFFER")]["product"]["sku"], "SKU-B")
        self.assertIsNone(items[(1, "ONLY-SHOP2")]["product"]["sku"])
        self.assertIn("missing_sku_mapping", items[(1, "ONLY-SHOP2")]["economics"]["incomplete_reasons"])

    def test_weighted_sales_and_reference_channel(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_price(connection, 2, observed, 10, "O-10", currency="CNY")
            add_successful_price_run(connection, 2, observed)
            day = date(2026, 8, 31)
            add_sale(connection, 2, "FBP-1", "FBP", "S-10", "O-10", 1, 100, "CNY", day)
            add_sale(connection, 2, "FBP-2", "FBP", "S-10", "O-10", 3, 200, "CNY", day)
            add_sale(connection, 2, "RFBS-1", "realFBS", "S-10", "O-10", 5, 300, "CNY", day)
        fbp = get_pricing(2, channel="FBP", now=NOW, size=100)["items"][0]
        real_fbs = get_pricing(2, channel="realFBS", now=NOW, size=100)["items"][0]
        self.assertEqual((fbp["sales_30"]["units"], fbp["sales_30"]["weighted_avg_price"]), (4, "175.0"))
        self.assertEqual(fbp["economics"]["sales_commission_field"], "sales_percent_fbp")
        self.assertEqual(real_fbs["sales_30"]["units"], 5)
        self.assertEqual(real_fbs["sales_30"]["weighted_avg_price"], "300.0")
        self.assertEqual(real_fbs["economics"]["sales_commission_field"], "sales_percent_rfbs")
        whd = get_pricing(2, channel="WHD", now=NOW, size=100)["items"][0]
        self.assertEqual(whd["economics"]["sales_commission_field"], "sales_percent_fbo")

    def test_erp_uses_latest_reliable_unit_cost_and_rejects_quantity_or_offer_mismatch(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_price(connection, 2, observed, 20, "O-20", currency="CNY")
            add_price(connection, 2, observed, 21, "O-QTY", currency="CNY")
            add_price(connection, 2, observed, 22, "O-OFFER", currency="CNY")
            add_successful_price_run(connection, 2, observed)
            add_sale(connection, 2, "P-OLD", "FBP", "S-20", "O-20", 1, 100, "CNY", date(2026, 8, 20))
            add_sale(connection, 2, "P-NEW", "FBP", "S-20", "O-20", 1, 100, "CNY", date(2026, 8, 21))
            add_sale(connection, 2, "P-QTY", "FBP", "S-QTY", "O-QTY", 1, 100, "CNY", date(2026, 8, 22))
            add_sale(connection, 2, "P-OFFER", "FBP", "S-OFFER", "O-OFFER", 1, 100, "CNY", date(2026, 8, 23))
            add_erp(connection, 2, "P-OLD", "S-20", offer_id="O-20", unit_cost="30", updated_at="2026-08-20T00:00:00Z")
            add_erp(connection, 2, "P-NEW", "S-20", offer_id="O-20", unit_cost="20", updated_at="2026-08-31T00:00:00Z")
            add_erp(connection, 2, "P-QTY", "S-QTY", offer_id="O-QTY", quantity=2, unit_cost="1")
            add_erp(connection, 2, "P-OFFER", "S-OFFER", offer_id="WRONG", unit_cost="1")
        with patch("app.pricing.current_exchange_rate_entries", return_value=self.rates()):
            result = get_pricing(2, now=NOW, size=100)
        items = {item["product"]["offer_id"]: item for item in result["items"]}
        self.assertEqual(items["O-20"]["cost_basis"]["unit_cost_cny"], "20")
        self.assertEqual(items["O-QTY"]["cost_basis"]["status"], "unavailable")
        self.assertEqual(items["O-OFFER"]["cost_basis"]["status"], "unavailable")

    def test_currency_conversion_and_base_economics(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_price(connection, 1, observed, 30, "O-30", price="100", marketing="80", acquiring="5", commission=10)
            add_successful_price_run(connection, 1, observed)
            add_sale(connection, 1, "P-30", "FBP", "S-30", "O-30", 1, 80, "RUB", date(2026, 8, 31))
            add_erp(connection, 1, "P-30", "S-30", offer_id="O-30", unit_cost="4")
        with patch("app.pricing.current_exchange_rate_entries", return_value=self.rates()):
            item = get_pricing(1, now=NOW, size=100)["items"][0]
        economics = item["economics"]
        self.assertEqual(item["price"]["effective_price"], "80")
        self.assertEqual(economics["current_effective_price"], "8")
        self.assertEqual(economics["unit_cost"], "0.8")
        self.assertEqual(economics["acquiring_amount"], "0.5")
        self.assertEqual(economics["projected_base_profit"], "5.9")
        self.assertEqual(economics["break_even_price"], "0.9552238805970149253731343284")
        self.assertEqual(economics["target_margin_price"], "1.254901960784313725490196078")

    def test_currency_mismatch_keeps_item_but_marks_sold_price_incomplete(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_price(connection, 2, observed, 40, "O-40", currency="CNY")
            add_successful_price_run(connection, 2, observed)
            add_sale(connection, 2, "P-CNY", "FBP", "S-40", "O-40", 1, 10, "CNY", date(2026, 8, 30))
            add_sale(connection, 2, "P-RUB", "FBP", "S-40", "O-40", 1, 10, "RUB", date(2026, 8, 31))
        item = get_pricing(2, now=NOW, size=100)["items"][0]
        self.assertEqual(item["sales_30"]["sold_price_status"], "currency_mismatch")
        self.assertIsNone(item["sales_30"]["weighted_avg_price"])
        self.assertIn("currency_mismatch", item["economics"]["incomplete_reasons"])

    def test_missing_currency_keeps_units_but_marks_sales_and_economics_incomplete(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_price(connection, 2, observed, 41, "O-41", currency="CNY", price="100", commission=0)
            add_successful_price_run(connection, 2, observed)
            add_sale(connection, 2, "P-41-CNY", "FBP", "S-41", "O-41", 1, 100, "CNY", date(2026, 8, 30))
            add_sale(connection, 2, "P-41-NONE", "FBP", "S-41", "O-41", 1, 200, None, date(2026, 8, 31))
            add_erp(connection, 2, "P-41-CNY", "S-41", offer_id="O-41", unit_cost="20")
            add_erp(connection, 2, "P-41-NONE", "S-41", offer_id="O-41", unit_cost="20",
                    updated_at="2026-09-01T00:00:00Z")
        item = get_pricing(2, now=NOW, size=100)["items"][0]
        self.assertEqual(item["sales_30"], {
            "units": 2, "revenue": None, "currency": None, "weighted_avg_price": None,
            "sold_price_status": "missing_currency", "price_vs_30d_pct": None,
        })
        self.assertEqual(item["economics"]["status"], "incomplete")
        self.assertIn("missing_currency", item["economics"]["incomplete_reasons"])
        self.assertEqual(item["economics"]["projected_base_profit"], "80")

    def test_current_price_sort_converts_shop_currencies_to_cny_and_keeps_missing_last(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_price(connection, 1, observed, 81, "USD-10", currency="USD", price="10")
            add_price(connection, 2, observed, 82, "CNY-40", currency="CNY", price="40")
            add_successful_price_run(connection, 1, observed)
            add_successful_price_run(connection, 2, observed)
        with patch("app.pricing.current_exchange_rate_entries", return_value=self.rates()):
            ascending = get_pricing(0, sort_by="current_price", sort_order="asc", now=NOW, size=100)
            descending = get_pricing(0, sort_by="current_price", sort_order="desc", now=NOW, size=100)
        self.assertEqual([item["product"]["offer_id"] for item in ascending["items"]], ["CNY-40", "USD-10"])
        self.assertEqual([item["product"]["offer_id"] for item in descending["items"]], ["USD-10", "CNY-40"])
        with patch("app.pricing.current_exchange_rate_entries", return_value={"USD": {"sales_exchange_rate": "10"}}):
            missing_rate = get_pricing(0, sort_by="current_price", sort_order="asc", now=NOW, size=100)
        self.assertEqual([item["product"]["offer_id"] for item in missing_rate["items"]], ["CNY-40", "USD-10"])

    def test_stock_uses_current_channel_snapshot_and_does_not_guess_ambiguous_sku(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_price(connection, 2, observed, 45, "O-45", currency="CNY")
            add_successful_price_run(connection, 2, observed)
            add_stock_snapshot(connection, 2, "45", observed, {
                "product_id": 45, "offer_id": "O-45", "stocks": [
                    {"type": "fbs", "sku": "S-45", "present": 4, "reserved": 7},
                    {"type": "fbo", "sku": "S-45", "present": 9, "reserved": 1},
                ],
            })
            add_price(connection, 2, observed, 46, "O-AMB", currency="CNY")
            add_order(connection, 2, "AMB-1", "FBP", stamp(date(2026, 8, 31)), "已签收", 1)
            add_item(connection, 2, "AMB-1", "FBP", "S-1", offer_id="O-AMB")
            add_order(connection, 2, "AMB-2", "FBP", stamp(date(2026, 8, 31)), "已签收", 1)
            add_item(connection, 2, "AMB-2", "FBP", "S-2", offer_id="O-AMB")
        result = get_pricing(2, channel="realFBS", now=NOW, size=100)
        items = {item["product"]["offer_id"]: item for item in result["items"]}
        self.assertEqual(items["O-45"]["stock"]["effective_stock"], 0)
        self.assertEqual(items["O-45"]["stock"]["present"], 4)
        self.assertEqual(items["O-45"]["competitiveness"]["ozon"]["min_price_currency"], "CNY")
        whd = get_pricing(2, channel="WHD", now=NOW, size=100)["items"][0]
        self.assertEqual(whd["stock"], {"present": 9, "reserved": 1, "effective_stock": 8, "observed_at": observed})
        self.assertIsNone(items["O-AMB"]["product"]["sku"])
        self.assertIn("ambiguous_sku", items["O-AMB"]["economics"]["incomplete_reasons"])

    def test_missing_commission_and_exchange_rate_are_incomplete(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_price(connection, 1, observed, 47, "O-47", currency="EUR", acquiring="1")
            add_successful_price_run(connection, 1, observed)
            add_sale(connection, 1, "P-47", "FBP", "S-47", "O-47", 1, 10, "EUR", date(2026, 8, 31))
            add_erp(connection, 1, "P-47", "S-47", offer_id="O-47", unit_cost="2")
            connection.execute("UPDATE product_price_snapshots SET commissions_json=NULL WHERE offer_id='O-47'")
        item = get_pricing(1, now=NOW, size=100)["items"][0]
        self.assertEqual(item["economics"]["status"], "incomplete")
        self.assertIn("missing_commission", item["economics"]["incomplete_reasons"])
        self.assertIn("missing_exchange_rate", item["economics"]["incomplete_reasons"])

    def test_health_summary_and_filter_are_based_on_unfiltered_rows(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            for index, (offer, cost, color) in enumerate((("LOSS", "20", "GREEN"), ("LOW", "9", "GREEN"),
                                                           ("RED", "1", "RED"), ("GOOD", "1", "GREEN")), 1):
                sku = f"S-{offer}"
                posting = f"P-{offer}"
                add_price(connection, 2, observed, 50 + index, offer, currency="CNY", price="10", commission=0, color=color)
                add_successful_price_run(connection, 2, observed) if index == 1 else None
                add_sale(connection, 2, posting, "FBP", sku, offer, 1, 10, "CNY", date(2026, 8, 31))
                add_erp(connection, 2, posting, sku, offer_id=offer, unit_cost=cost)
            add_price(connection, 2, observed, 55, "INCOMPLETE", currency="CNY", price="10", commission=0)
        # One successful run is enough for the whole batch; add_price rows share its timestamp.
        result = get_pricing(2, now=NOW, target_margin_pct=20, size=100)
        flags = {item["product"]["offer_id"]: item["health_flags"] for item in result["items"]}
        self.assertIn("loss", flags["LOSS"])
        self.assertIn("low_margin", flags["LOW"])
        self.assertIn("price_red", flags["RED"])
        self.assertIn("healthy", flags["GOOD"])
        self.assertIn("incomplete", flags["INCOMPLETE"])
        self.assertEqual(result["summary"]["products"], 5)
        self.assertEqual(get_pricing(2, health="loss", now=NOW, size=100)["summary"], result["summary"])
        self.assertEqual(get_pricing(2, health="loss", now=NOW, size=100)["total"], 1)

    def test_schema_stays_v14_and_bad_json_does_not_break_response(self):
        observed = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_price(connection, 2, observed, 60, "O-60", currency="CNY")
            add_successful_price_run(connection, 2, observed)
            connection.execute("UPDATE product_price_snapshots SET commissions_json=?,price_indexes_json=?",
                               ("{bad", "{bad"))
        result = get_pricing(2, now=NOW, size=100)
        self.assertEqual(result["items"][0]["economics"]["status"], "incomplete")
        json.dumps(result, allow_nan=False)
        with db.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 14)
