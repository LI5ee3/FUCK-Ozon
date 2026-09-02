import json
import unittest
from datetime import date, datetime, time, timezone
from decimal import Decimal

from fastapi import HTTPException

from app import db
from app.pricing_strategy import _market_reference, _strategy, get_pricing_strategy
from app.routers.pricing import pricing_strategy as pricing_strategy_route
from app.ozon.client import BEIJING
from tests.support import DatabaseTestCase, add_item, add_order


NOW = datetime(2026, 9, 2, 12, tzinfo=BEIJING)


def stamp(day):
    return datetime.combine(day, time(12), BEIJING).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def add_snapshot(connection, shop_id, observed_at, snapshot_key, *, price="100", currency="CNY",
                 min_price="80", min_currency=None):
    min_currency = min_currency or currency
    indexes = {
        "ozon_index_data": {"min_price": min_price, "min_price_currency": min_currency},
        "external_index_data": {}, "self_marketplaces_index_data": {},
    }
    values = {
        "shop_id": shop_id, "product_id": snapshot_key, "offer_id": f"O-{snapshot_key}",
        "observed_at": observed_at, "currency": currency, "price": price, "old_price": None,
        "min_price": min_price, "marketing_seller_price": None, "auto_action_enabled": 0,
        "acquiring": "0", "price_index_color": "GREEN", "ozon_min_price": min_price,
        "ozon_price_index": "1", "external_min_price": None, "external_price_index": None,
        "self_marketplace_min_price": None, "self_marketplace_price_index": None,
        "commissions_json": json.dumps({"sales_percent_fbp": 0, "sales_percent_rfbs": 0, "sales_percent_fbo": 0}),
        "marketing_actions_json": None, "price_indexes_json": json.dumps(indexes),
        "payload_json": json.dumps({"name": f"商品 {snapshot_key}"}), "snapshot_key": snapshot_key,
    }
    columns = ",".join(values)
    connection.execute(f"INSERT INTO product_price_snapshots({columns}) VALUES({','.join('?' for _ in values)})",
                       tuple(values.values()))


def add_successful_price_run(connection, shop_id, observed_at):
    connection.execute("INSERT INTO sync_runs(shop_id,module,status,data_through) VALUES(?,'prices','success',?)",
                       (shop_id, observed_at))


def add_sale(connection, shop_id, posting, day, quantity=1, *, offer_id="O-A", price=10, currency="CNY",
             channel="FBP"):
    add_order(connection, shop_id, posting, channel, stamp(day), "已签收", 1)
    add_item(connection, shop_id, posting, channel, f"SKU-{offer_id}", quantity, offer_id=offer_id,
             unit_price=price, price_currency=currency, product_name_raw=offer_id)


def strategy_item(current, target):
    return {
        "economics": {
            "current_effective_price": str(current) if current is not None else None,
            "break_even_price": "50", "target_margin_price": str(target) if target is not None else None,
        },
        "sales_30": {"weighted_avg_price": "78", "currency": "CNY", "sold_price_status": "available"},
    }


class PricingStrategyTest(DatabaseTestCase):
    def test_strategy_signal_order_has_no_arbitrary_tolerance(self):
        cases = (
            ("hold", 75, 69, Decimal("76")),
            ("raise", 60, 69, Decimal("76")),
            ("reduce", 82, 69, Decimal("76")),
            ("margin_market_conflict", 60, 69, Decimal("66")),
            ("insufficient_data", 60, 69, None),
        )
        for signal, current, target, market in cases:
            with self.subTest(signal=signal):
                result = _strategy(strategy_item(current, target), {}, market, [], "CNY", {})
                self.assertEqual(result["signal"], signal)

    def test_market_reference_converts_each_source_before_taking_minimum(self):
        competitiveness = {
            "ozon": {"min_price": "760", "min_price_currency": "RUB"},
            "external": {"min_price": "80", "min_price_currency": "USD"},
            "self_marketplace": {"min_price": "600", "min_price_currency": "CNY"},
        }
        sources, reference, warnings = _market_reference(
            competitiveness, "USD", {"USD": Decimal("10"), "CNY": Decimal("2")})
        self.assertEqual(reference, Decimal("76"))
        self.assertEqual(sources["ozon"]["converted_price"], "76")
        self.assertEqual(sources["self_marketplace"]["converted_price"], "120")
        self.assertEqual(warnings, [])
        competitiveness["external"]["min_price_currency"] = None
        sources, reference, warnings = _market_reference(competitiveness, "USD", {"USD": Decimal("10")})
        self.assertEqual(reference, Decimal("76"))
        self.assertEqual(sources["external"]["status"], "missing_currency")
        self.assertIn("partial_market_reference", warnings)

    def test_history_isolated_by_shop_and_snapshot_key(self):
        current = "2026-09-01T00:00:00Z"
        with db.transaction() as connection:
            add_snapshot(connection, 1, "2026-08-01T00:00:00Z", "A")
            add_snapshot(connection, 1, current, "A")
            add_snapshot(connection, 1, current, "B")
            add_snapshot(connection, 2, current, "A")
            add_successful_price_run(connection, 1, current)
            add_successful_price_run(connection, 2, current)
        result = get_pricing_strategy(1, "A", now=NOW)
        self.assertEqual(result["snapshot_key"], "A")
        self.assertEqual(result["history"]["snapshot_count"], 2)
        self.assertEqual({point["currency"] for point in result["history"]["points"]}, {"CNY"})

    def test_events_skip_repeated_snapshots_and_exclude_event_day_from_impact(self):
        with db.transaction() as connection:
            for observed, price in (
                ("2026-08-18T00:00:00Z", "100"), ("2026-08-19T00:00:00Z", "100"),
                ("2026-08-20T00:00:00Z", "90"), ("2026-08-21T00:00:00Z", "90"),
                ("2026-08-22T00:00:00Z", "95"), ("2026-09-02T00:00:00Z", "95"),
            ):
                add_snapshot(connection, 2, observed, "A", price=price)
            add_successful_price_run(connection, 2, "2026-09-02T00:00:00Z")
            for index in range(7):
                add_sale(connection, 2, f"BEFORE-{index}", date(2026, 8, 13 + index), offer_id="O-A")
            add_sale(connection, 2, "EVENT-DAY", date(2026, 8, 20), 99, offer_id="O-A")
            for index in range(7):
                add_sale(connection, 2, f"AFTER-{index}", date(2026, 8, 21 + index), 2, offer_id="O-A")
        result = get_pricing_strategy(2, "A", now=NOW)
        self.assertEqual(result["history"]["price_change_count"], 2)
        self.assertEqual(len(result["history"]["points"]), 4)
        self.assertEqual([event["event_day"] for event in result["history"]["events"]], ["2026-08-20", "2026-08-22"])
        impact = result["history"]["events"][0]["impact"]
        self.assertEqual(impact["status"], "available")
        self.assertEqual((impact["before"]["units"], impact["after"]["units"]), (7, 14))
        self.assertEqual(impact["units_change_pct"], 100.0)

    def test_recent_event_is_pending_and_currency_mismatch_has_no_fake_change_pct(self):
        with db.transaction() as connection:
            add_snapshot(connection, 2, "2026-08-25T00:00:00Z", "P", price="100")
            add_snapshot(connection, 2, "2026-08-27T00:00:00Z", "P", price="90")
            add_snapshot(connection, 2, "2026-09-02T00:00:00Z", "P", price="90")
            add_snapshot(connection, 2, "2026-08-01T00:00:00Z", "C", price="100", currency="CNY")
            add_snapshot(connection, 2, "2026-08-02T00:00:00Z", "C", price="90", currency="RUB")
            add_snapshot(connection, 2, "2026-09-02T00:00:00Z", "C", price="90", currency="CNY")
            add_successful_price_run(connection, 2, "2026-09-02T00:00:00Z")
        pending = get_pricing_strategy(2, "P", now=NOW)
        impact = pending["history"]["events"][0]["impact"]
        self.assertEqual(impact["status"], "pending")
        self.assertIsNone(impact["after"])
        changed = get_pricing_strategy(2, "C", now=NOW)
        event = changed["history"]["events"][0]
        self.assertEqual(event["price_change_status"], "currency_mismatch")
        self.assertIsNone(event["effective_price_change_pct"])
        json.dumps(changed, allow_nan=False)

    def test_strategy_route_rejects_shop_zero_and_returns_404_for_stale_entity(self):
        with self.assertRaises(HTTPException) as error:
            pricing_strategy_route(shop_id=0, snapshot_key="A")
        self.assertEqual(error.exception.status_code, 400)
        with db.transaction() as connection:
            add_snapshot(connection, 1, "2026-09-01T00:00:00Z", "A")
            add_successful_price_run(connection, 1, "2026-09-02T00:00:00Z")
        with self.assertRaises(HTTPException) as error:
            pricing_strategy_route(shop_id=1, snapshot_key="A")
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
