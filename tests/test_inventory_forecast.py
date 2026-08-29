import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException

from app import db
from app.ozon.client import BEIJING
from app.routers.inventory import (_confirmed_stockout_days, _forecast_risk,
                                    _forecast_values, _stock_history_index, inventory_forecast, stock)
from tests.support import DatabaseTestCase, add_item, add_order, add_stock_snapshot


def local_timestamp(value, hour=12):
    return datetime.combine(value, datetime.min.time().replace(hour=hour), BEIJING).astimezone(
        timezone.utc).isoformat().replace("+00:00", "Z")


class InventoryForecastTest(DatabaseTestCase):
    def add_sale(self, connection, shop_id, posting, channel, sku, quantity, day,
                 status="已签收", shipped=1, offer_id=None, name="商品"):
        add_order(connection, shop_id, posting, channel, local_timestamp(day), status, shipped)
        add_item(connection, shop_id, posting, channel, sku, quantity,
                 offer_id=offer_id or f"O-{sku}", product_name_raw=name)

    @staticmethod
    def add_snapshot(connection, shop_id, sku, values, observed=None, offer_id=None):
        payload = {"offer_id": offer_id or f"O-{sku}", "stocks": [
            {"sku": sku, "type": channel, "present": present, "reserved": reserved}
            for channel, present, reserved in values]}
        add_stock_snapshot(connection, shop_id, sku, local_timestamp(observed or date.today()), payload)

    def test_weighted_forecast_matches_hand_calculation(self):
        end = date(2026, 8, 26)
        result = _forecast_values({"sales_7": 10, "sales_15": 23, "sales_30": 40},
                                  local_timestamp(end - timedelta(days=30)), None, end)
        expected = (10 / 7 * .5) + (23 / 15 * .3) + (40 / 30 * .2)
        self.assertAlmostEqual(result["daily"][7], 10 / 7)
        self.assertAlmostEqual(result["daily"][15], 23 / 15)
        self.assertAlmostEqual(result["daily"][30], 40 / 30)
        self.assertAlmostEqual(result["forecast"], expected)

    def test_short_history_renormalizes_weights_and_zero_sales_is_safe(self):
        end = date(2026, 8, 26)
        fifteen = _forecast_values({"sales_7": 7, "sales_15": 15, "sales_30": 30},
                                   local_timestamp(end - timedelta(days=14)), None, end)
        expected = ((7 / 7) * .5 + (15 / 15) * .3) / .8
        self.assertEqual(fifteen["windows"], [7, 15])
        self.assertAlmostEqual(fifteen["forecast"], expected)
        seven = _forecast_values({"sales_7": 4, "sales_15": 4, "sales_30": 4},
                                 local_timestamp(end - timedelta(days=3)), None, end)
        self.assertEqual(seven["windows"], [7])
        self.assertEqual(seven["forecast"], 1)
        empty = _forecast_values({"sales_7": 0, "sales_15": 0, "sales_30": 0}, None, None, end)
        self.assertEqual(empty["forecast"], 0)
        self.assertEqual(empty["trend"], "稳定")

    def test_stockout_correction_requires_full_day_evidence(self):
        end = date(2026, 8, 26)
        zero_day = end - timedelta(days=1)
        rows = [
            {"shop_id": 1, "source": "api", "warehouse_id": "", "sku": "S-1", "present": 0,
             "reserved": 0, "occurred_at": local_timestamp(zero_day, 0), "event_key": "p:fbp"},
            {"shop_id": 1, "source": "api", "warehouse_id": "", "sku": "S-1", "present": 0,
             "reserved": 0, "occurred_at": local_timestamp(zero_day + timedelta(days=1), 0), "event_key": "p:fbp"},
        ]
        confirmed = _confirmed_stockout_days(_stock_history_index(rows), 1, "S-1", "FBP", end)
        self.assertIn(zero_day, confirmed)
        adjusted = _forecast_values({"sales_7": 10, "sales_15": 10, "sales_30": 10},
                                    local_timestamp(end - timedelta(days=30)), confirmed, end)
        self.assertEqual(adjusted["in_stock_days"][7], 6)
        self.assertTrue(adjusted["adjusted"])
        self.assertAlmostEqual(adjusted["daily"][7], 10 / 6)
        incomplete = rows[:1] + [{**rows[1], "occurred_at": local_timestamp(zero_day, 18), "present": 5}]
        self.assertNotIn(zero_day, _confirmed_stockout_days(_stock_history_index(incomplete), 1, "S-1", "FBP", end))
        ordinary = _forecast_values({"sales_7": 10, "sales_15": 10, "sales_30": 10}, None, None, end)
        self.assertIsNone(ordinary["in_stock_days"][7])
        self.assertFalse(ordinary["adjusted"])

    def test_replenishment_formula_and_zero_divisors(self):
        end = date(2026, 8, 26)
        result = _forecast_values({"sales_7": 10, "sales_15": 10, "sales_30": 10},
                                  local_timestamp(end - timedelta(days=30)), None, end)
        daily = result["forecast"]
        effective = 10
        projected = max(effective - daily * 25, 0)
        recommended = max(daily * 60 - projected, 0)
        self.assertGreaterEqual(recommended, 0)
        self.assertEqual(_forecast_risk(0, daily, 0, 1), "out_of_stock")
        self.assertEqual(_forecast_risk(1, daily, 1, 1), "urgent_replenishment")
        self.assertEqual(_forecast_risk(1000, daily, 200, 0), "overstock")
        self.assertEqual(_forecast_risk(10, 0, None, 0), "no_recent_sales")

    def test_replenishment_policy_uses_25_60_and_strict_90_day_boundaries(self):
        today = datetime.now(BEIJING).date()
        sales_end = today - timedelta(days=1)
        stocks = {"POLICY-LEAD": (24, 1), "POLICY-ARRIVAL": (26, 1), "POLICY-89": (89, 1), "POLICY-90": (90, 1),
                  "POLICY-90.01": (9001, 100), "POLICY-120": (120, 1)}
        with db.transaction() as connection:
            for sku, (present, quantity) in stocks.items():
                for offset in range(30):
                    self.add_sale(connection, 1, f"{sku}-{offset}", "FBP", sku, quantity,
                                  sales_end - timedelta(days=offset))
                self.add_snapshot(connection, 1, sku, [("fbp", present, 0)], today)
        items = {item["sku"]: item for item in stock(1, size=100, sku="POLICY")["items"]}
        lead = items["POLICY-LEAD"]
        self.assertEqual((lead["forecast_daily"], lead["lead_time_days"], lead["target_cover_days"]), (1, 25, 60))
        self.assertEqual((lead["projected_stock_at_arrival"], lead["target_stock_after_arrival"],
                          lead["recommended_replenishment"]), (0, 60, 60))
        self.assertTrue(lead["stockout_before_arrival"])
        arrival = items["POLICY-ARRIVAL"]
        self.assertEqual((arrival["projected_stock_at_arrival"], arrival["recommended_replenishment"],
                          arrival["risk_code"]), (1, 59, "replenish"))
        self.assertEqual(items["POLICY-89"]["risk_code"], "sufficient")
        self.assertEqual(items["POLICY-90"]["risk_code"], "sufficient")
        self.assertAlmostEqual(items["POLICY-90.01"]["days_cover"], 90.01)
        self.assertEqual(items["POLICY-90.01"]["risk_code"], "overstock")
        self.assertEqual(items["POLICY-120"]["risk_code"], "overstock")
        self.assertTrue(all(item["recommended_replenishment"] >= 0 for item in items.values()))

    def test_declining_example_does_not_get_raised_by_the_forecast(self):
        end = date(2026, 8, 26)
        result = _forecast_values({"sales_7": 10, "sales_15": 15, "sales_30": 56},
                                  local_timestamp(end - timedelta(days=30)), None, end)
        self.assertLess(result["forecast"], result["daily"][30])
        self.assertEqual(result["trend"], "下降")
        daily = result["forecast"]
        self.assertEqual(max(daily * 60 - max(200 - daily * 25, 0), 0), 0)

    def test_endpoint_uses_complete_natural_days_and_stock_semantics(self):
        today = datetime.now(BEIJING).date()
        yesterday = today - timedelta(days=1)
        with db.transaction() as connection:
            self.add_sale(connection, 1, "Y", "FBP", "S-1", 10, yesterday,
                          offer_id="O-1", name="一号商品")
            self.add_sale(connection, 1, "T", "FBP", "S-1", 99, today,
                          offer_id="O-1", name="一号商品")
            self.add_sale(connection, 1, "W", "WHD", "S-1", 77, yesterday,
                          offer_id="O-1", name="一号商品")
            self.add_snapshot(connection, 1, "S-1", [("fbp", 10, 7), ("rfbs", 100, 0), ("fbo", 50, 0)], today)
        item = {row["sku"]: row for row in stock(1, size=100)["items"]}["S-1"]
        self.assertEqual(item["sales_7"], 10)
        self.assertEqual(item["current_stock"], 10)
        self.assertEqual(item["reserved_stock"], 7)
        self.assertEqual(item["effective_stock"], 10)
        self.assertEqual(item["forecast_channel"], "FBP")
        self.assertEqual(item["channels"][1]["present"], 100)

    def test_forecast_always_uses_core_sales_and_fbp_stock(self):
        today = datetime.now(BEIJING).date()
        with db.transaction() as connection:
            day = today - timedelta(days=1)
            self.add_sale(connection, 1, "FBP-SALE", "FBP", "SKU", 10, day)
            self.add_sale(connection, 1, "RFBS-SALE", "realFBS", "SKU", 10, day)
            self.add_sale(connection, 1, "WHD-SALE", "WHD", "SKU", 100, day)
            self.add_snapshot(connection, 1, "SKU", [("fbp", 10, 0), ("rfbs", 100, 0), ("fbo", 100, 0)], today)
        views = [stock(1, size=100, sku="SKU", channel=channel)["items"][0]
                 for channel in ("", "FBP", "realFBS", "WHD")]
        self.assertTrue(all(view["sales_7"] == 20 for view in views))
        self.assertTrue(all(view["forecast_daily"] == 20 for view in views))
        self.assertTrue(all(view["current_stock"] == 10 for view in views))
        self.assertTrue(all(view["effective_stock"] == 10 for view in views))
        self.assertTrue(all(view["forecast_channel"] == "FBP" for view in views))
        self.assertTrue(all(view["replenishment_stock_source"] == "FBP" for view in views))
        for field in ("days_cover", "expected_stockout_date", "projected_stock_at_arrival",
                      "recommended_replenishment", "risk_code"):
            self.assertTrue(all(view[field] == views[0][field] for view in views), field)
        self.assertEqual(views[0]["channels"][1]["present"], 100)
        self.assertEqual(views[0]["channels"][2]["present"], 100)

    def test_fbp_is_the_only_replenishment_stock_and_risk_base(self):
        today = datetime.now(BEIJING).date()
        day = today - timedelta(days=1)
        with db.transaction() as connection:
            for sku, quantity in (("OUT", 10), ("SAFE", 10)):
                self.add_sale(connection, 1, f"FBP-{sku}", "FBP", sku, quantity, day)
                self.add_snapshot(connection, 1, sku, (
                    [("fbp", 0, 0), ("rfbs", 500, 0), ("fbo", 500, 0)]
                    if sku == "OUT" else
                    [("fbp", 1000, 0), ("rfbs", 0, 0), ("fbo", 0, 0)]
                ), today)
        out = stock(1, size=100, sku="OUT", channel="WHD")["items"][0]
        safe = stock(1, size=100, sku="SAFE", channel="realFBS")["items"][0]
        self.assertEqual((out["current_stock"], out["effective_stock"], out["risk_code"]),
                         (0, 0, "out_of_stock"))
        self.assertEqual((safe["current_stock"], safe["effective_stock"]), (1000, 1000))
        self.assertNotEqual(safe["risk_code"], "out_of_stock")
        self.assertEqual(out["channels"][1]["present"], 500)
        self.assertEqual(out["channels"][2]["present"], 500)

    def test_shop_isolation_and_ad_orders_are_not_added_to_sales(self):
        today = datetime.now(BEIJING).date()
        with db.transaction() as connection:
            self.add_sale(connection, 1, "ONE", "FBP", "SAME", 10, today - timedelta(days=1))
            self.add_sale(connection, 2, "TWO", "FBP", "SAME", 20, today - timedelta(days=1))
            self.add_snapshot(connection, 1, "SAME", [("fbp", 10, 0)], today)
            self.add_snapshot(connection, 2, "SAME", [("fbp", 20, 0)], today)
            connection.execute("""INSERT INTO ad_sku_daily(shop_id,stat_date,campaign_id,sku,orders)
              VALUES(?,?,?,?,?)""", (1, (today - timedelta(days=1)).isoformat(), "C", "SAME", 99))
        one = stock(1, size=100, sku="SAME")["items"][0]
        two = stock(2, size=100, sku="SAME")["items"][0]
        self.assertEqual((one["sales_7"], two["sales_7"]), (10, 20))
        self.assertEqual(one["ad_orders_30"], 99)
        self.assertAlmostEqual(one["ad_order_share"], 9.9)
        self.assertNotEqual(one["forecast_daily"], two["forecast_daily"])

    def test_risk_filter_sort_alias_and_json_has_no_non_finite_numbers(self):
        today = datetime.now(BEIJING).date()
        with db.transaction() as connection:
            self.add_sale(connection, 1, "A", "FBP", "A", 10, today - timedelta(days=1))
            self.add_sale(connection, 1, "B", "FBP", "B", 1, today - timedelta(days=1))
            self.add_snapshot(connection, 1, "A", [("fbp", 0, 0)], today)
            self.add_snapshot(connection, 1, "B", [("fbp", 1000, 0)], today)
        attention = stock(1, size=100, risk="attention")
        self.assertTrue(all(row["risk_code"] in {"out_of_stock", "urgent_replenishment", "replenish"}
                            for row in attention["items"]))
        self.assertEqual(stock(1, size=1, sort_by="risk")["items"][0]["risk_code"], "out_of_stock")
        json.dumps(stock(1, size=100), allow_nan=False)
        self.assertEqual(inventory_forecast(1, size=1, q="A")["items"][0]["sku"], "A")

    def test_product_group_is_display_only_for_forecast_rows(self):
        today = datetime.now(BEIJING).date()
        with db.transaction() as connection:
            self.add_sale(connection, 1, "GA", "FBP", "GA", 5, today - timedelta(days=30),
                          offer_id="GO-A", name="同组商品")
            self.add_sale(connection, 1, "GB", "FBP", "GB", 5, today - timedelta(days=30),
                          offer_id="GO-B", name="同组商品")
            self.add_snapshot(connection, 1, "GA", [("fbp", 3, 0)], today, "GO-A")
            self.add_snapshot(connection, 1, "GB", [("fbp", 30, 0)], today, "GO-B")
            group_id = connection.execute(
                "INSERT INTO product_groups(name,created_at,updated_at) VALUES(?,?,?)",
                ("merge:test", "now", "now")).lastrowid
            connection.execute("INSERT INTO product_group_config VALUES(?,?,?,'active','')",
                               (group_id, "GO-A", "GA"))
            connection.executemany("INSERT INTO product_group_members VALUES(?,?,?)",
                                   [(group_id, "sku", "GA"), (group_id, "sku", "GB")])
        rows = {row["sku"]: row for row in stock(1, size=100, sku="G") ["items"]}
        self.assertEqual(set(rows), {"GA", "GB"})
        self.assertEqual(rows["GA"]["current_stock"], 3)
        self.assertEqual(rows["GB"]["current_stock"], 30)

    def test_invalid_forecast_filters_are_rejected(self):
        with self.assertRaises(HTTPException):
            stock(1, channel="other")
        with self.assertRaises(HTTPException):
            stock(1, risk="other")

    def test_inventory_policy_remains_backend_owned(self):
        root = Path(__file__).parents[1]
        backend = (root / "app/routers/inventory.py").read_text()
        inventory = (root / "frontend/src/features/inventory/InventoryView.vue").read_text()
        self.assertIn("FORECAST_LEAD_TIME_DAYS = 25", backend)
        self.assertIn("FORECAST_TARGET_COVER_DAYS = 60", backend)
        self.assertIn("FORECAST_OVERSTOCK_DAYS = 90", backend)
        self.assertIn('"inbound_included": False', backend)
        self.assertIn("demand = FBP + realFBS sales", backend)
        self.assertIn("replenishment stock = FBP only", backend)
        self.assertIn("row.lead_time_days", inventory)
        self.assertIn("row.target_cover_days", inventory)
        self.assertNotIn("FORECAST_LEAD_TIME_DAYS", inventory)


if __name__ == "__main__":
    unittest.main()
