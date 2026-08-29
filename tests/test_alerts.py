import asyncio
import json
import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException

from app import db
from app.alerts import (acknowledge_alert, alert_summary, evaluate_alerts,
                        get_alert_rules, list_alert_events, update_alert_rule,
                        validate_rule_config)
from app.performance import MOSCOW
from app.routers.alerts import (alert_acknowledge, alert_rule_update, alerts,
                                alerts_evaluate, alerts_summary)
from app.sync_jobs import _run_sync_job
from tests.support import (DatabaseTestCase, MockRequest, add_item, add_order,
                           add_stock_snapshot)

BEIJING = timezone(timedelta(hours=8))


def local_timestamp(day, hour=12):
    return datetime.combine(day, datetime.min.time().replace(hour=hour), BEIJING).astimezone(
        timezone.utc).isoformat().replace("+00:00", "Z")


class AlertTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.now = datetime.now(BEIJING).replace(hour=12, minute=0, second=0, microsecond=0)
        self.target = self.now.astimezone(MOSCOW).date() - timedelta(days=1)

    def sync_run(self, shop_id, module, through=None, finished=None, range_from=None):
        through = through or self.target
        range_from = range_from or (self.target - timedelta(days=7) if module == "orders" else through)
        finished = finished or self.now.astimezone(timezone.utc)
        with db.transaction() as connection:
            connection.execute("""INSERT INTO sync_runs(
              shop_id,module,range_from,range_to,status,finished_at,data_through)
              VALUES(?,?,?,?,?,?,?)""", (shop_id, module, range_from.isoformat(), through.isoformat(),
                                         "success", finished.isoformat().replace("+00:00", "Z"),
                                         through.isoformat()))

    @staticmethod
    def campaign(connection, shop_id, campaign_id="C-1", name="测试 Campaign"):
        connection.execute("INSERT INTO ad_campaigns(shop_id,campaign_id,name,state) VALUES(?,?,?,'RUNNING')",
                           (shop_id, campaign_id, name))

    @staticmethod
    def campaign_daily(connection, shop_id, campaign_id, day, spend=0, revenue=0, clicks=0, orders=0):
        connection.execute("""INSERT INTO ad_campaign_daily(
          shop_id,stat_date,campaign_id,impressions,clicks,cart_adds,spend_rub,orders,revenue_rub)
          VALUES(?,?,?,?,?,?,?,?,?)""", (shop_id, day.isoformat(), campaign_id, 100, clicks, 0,
                                           spend, orders, revenue))

    @staticmethod
    def sku_daily(connection, shop_id, campaign_id, sku, day, clicks=0, spend=0, orders=0, name="测试商品"):
        connection.execute("""INSERT INTO ad_sku_daily(
          shop_id,stat_date,campaign_id,sku,product_name,impressions,clicks,cart_adds,spend_rub,orders,revenue_rub)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (shop_id, day.isoformat(), campaign_id, sku, name, 100,
                                              clicks, 0, spend, orders, spend * 2))

    def sale(self, connection, shop_id, posting, sku, day, quantity=1, channel="FBP"):
        add_order(connection, shop_id, posting, channel, local_timestamp(day), "已签收", 1)
        add_item(connection, shop_id, posting, channel, sku, quantity,
                 offer_id=f"O-{sku}", product_name_raw="测试商品")

    def stock(self, connection, shop_id, sku, present, reserved=0):
        add_stock_snapshot(connection, shop_id, sku, self.now.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"), {"offer_id": f"O-{sku}", "stocks": [
                {"sku": sku, "type": "fbp", "present": present, "reserved": reserved}]})

    def stock_channels(self, connection, shop_id, sku, values):
        add_stock_snapshot(connection, shop_id, sku, self.now.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"), {"offer_id": f"O-{sku}", "stocks": [
                {"sku": sku, "type": channel, "present": present, "reserved": reserved}
                for channel, present, reserved in values]})

    def evaluate(self, shop_id, rule_key, configured=False):
        with patch("app.alerts.evaluation.dingtalk_configured", return_value=configured), \
                patch("app.alerts.evaluation.send_text") as sender:
            result = evaluate_alerts(shop_id, rule_keys=(rule_key,), now=self.now)
        return result, sender

    def test_defaults_and_rule_config_validation(self):
        rules = get_alert_rules(0)
        self.assertEqual(len(rules), 12)
        self.assertEqual({row["rule_key"] for row in rules}, {
            "ad_spend_spike", "ad_drr_high", "ad_clicks_no_orders", "ad_orders_drop",
            "inventory_risk", "sales_drop"})
        with self.assertRaises(ValueError): validate_rule_config("ad_drr_high", {"unknown": 1})
        with self.assertRaises(ValueError): validate_rule_config("ad_drr_high", {"window_days": 31})
        with self.assertRaises(ValueError): validate_rule_config("ad_drr_high", {"threshold_drr": float("nan")})
        with self.assertRaises(ValueError): validate_rule_config("ad_drr_high", {"minimum_spend_rub": -1})
        updated = update_alert_rule("ad_drr_high", {"shop_id": 1, "enabled": False,
                                                       "notify_dingtalk": False,
                                                       "config": {"window_days": 3}})
        self.assertFalse(updated["enabled"])
        self.assertFalse(updated["notify_dingtalk"])
        self.assertEqual(updated["config"]["threshold_drr"], 30)

    def test_ad_spend_spike_threshold_and_deduplication(self):
        with db.transaction() as connection:
            self.campaign(connection, 1)
            for offset in range(1, 8):
                self.campaign_daily(connection, 1, "C-1", self.target - timedelta(days=offset), spend=400)
            self.campaign_daily(connection, 1, "C-1", self.target, spend=700)
        self.sync_run(1, "ad_campaign_daily")
        first, sender = self.evaluate(1, "ad_spend_spike", configured=True)
        second, _ = self.evaluate(1, "ad_spend_spike", configured=True)
        self.assertEqual((first["triggered"], first["notifications_sent"]), (1, 1))
        self.assertEqual((second["triggered"], second["updated"]), (0, 1))
        sender.assert_called_once()
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0], 1)

    def test_ad_spend_spike_small_amount_and_insufficient_baseline_do_not_trigger(self):
        with db.transaction() as connection:
            self.campaign(connection, 1)
            for offset in range(1, 4):
                self.campaign_daily(connection, 1, "C-1", self.target - timedelta(days=offset), spend=400)
            self.campaign_daily(connection, 1, "C-1", self.target, spend=499)
        self.sync_run(1, "ad_campaign_daily")
        result, _ = self.evaluate(1, "ad_spend_spike")
        self.assertEqual(result["triggered"], 0)
        with db.transaction() as connection:
            self.campaign_daily(connection, 1, "C-2", self.target - timedelta(days=4), spend=400)
            self.campaign_daily(connection, 1, "C-2", self.target, spend=700)
        result, _ = self.evaluate(1, "ad_spend_spike")
        self.assertEqual(result["triggered"], 0)

    def test_drr_high_and_zero_revenue_is_not_infinity(self):
        with db.transaction() as connection:
            self.campaign(connection, 1)
            for offset in range(3):
                self.campaign_daily(connection, 1, "C-1", self.target - timedelta(days=offset), spend=200, revenue=100)
        self.sync_run(1, "ad_campaign_daily")
        result, _ = self.evaluate(1, "ad_drr_high")
        self.assertEqual(result["triggered"], 1)
        with db.transaction() as connection:
            connection.execute("UPDATE ad_campaign_daily SET revenue_rub=0 WHERE shop_id=1")
        result, _ = self.evaluate(1, "ad_drr_high")
        self.assertEqual(result["triggered"], 0)
        with db.connect() as connection:
            event = connection.execute("SELECT * FROM alert_events").fetchone()
            self.assertIsNotNone(event["resolved_at"])
            self.assertNotIn("Infinity", event["message"])
            json.dumps(dict(event), allow_nan=False)

    def test_clicks_without_orders_and_shop_isolation(self):
        with db.transaction() as connection:
            for shop_id in (1, 2):
                for offset in range(3):
                    self.sku_daily(connection, shop_id, "C-1", "SAME", self.target - timedelta(days=offset),
                                    clicks=15, spend=100)
        self.sync_run(1, "ad_sku_daily")
        self.sync_run(2, "ad_sku_daily")
        result, _ = self.evaluate(0, "ad_clicks_no_orders")
        self.assertEqual(result["triggered"], 2)
        with db.connect() as connection:
            self.assertEqual({row[0] for row in connection.execute(
                "SELECT shop_id FROM alert_events ORDER BY shop_id")}, {1, 2})
        with db.transaction() as connection:
            connection.execute("UPDATE ad_sku_daily SET clicks=9 WHERE shop_id=1")
        result, _ = self.evaluate(1, "ad_clicks_no_orders")
        self.assertEqual(result["triggered"], 0)

    def test_ad_orders_drop_requires_spend_not_to_drop(self):
        with db.transaction() as connection:
            self.campaign(connection, 1)
            for offset in range(1, 8):
                self.campaign_daily(connection, 1, "C-1", self.target - timedelta(days=offset), spend=100, orders=4)
            self.campaign_daily(connection, 1, "C-1", self.target, spend=100, orders=0)
        self.sync_run(1, "ad_campaign_daily")
        result, _ = self.evaluate(1, "ad_orders_drop")
        self.assertEqual(result["triggered"], 1)
        with db.transaction() as connection:
            connection.execute("UPDATE ad_campaign_daily SET spend_rub=50 WHERE stat_date=?", (self.target.isoformat(),))
        result, _ = self.evaluate(1, "ad_orders_drop")
        self.assertEqual(result["triggered"], 0)

    def test_sales_drop_uses_valid_orders_and_freshness(self):
        with db.transaction() as connection:
            for offset in range(1, 8):
                self.sale(connection, 1, f"P-{offset}", "S-1", self.target - timedelta(days=offset), 10)
        self.sync_run(1, "orders")
        result, _ = self.evaluate(1, "sales_drop")
        self.assertEqual(result["triggered"], 1)
        with db.transaction() as connection:
            connection.execute("DELETE FROM sync_runs WHERE module='orders'")
        result, _ = self.evaluate(1, "sales_drop")
        self.assertEqual(result["triggered"], 0)
        self.assertTrue(any(item["rule_key"] == "sales_drop" for item in result["skipped"]))

    def test_sales_drop_excludes_whd_and_uses_core_channels(self):
        with db.transaction() as connection:
            for offset in range(1, 8):
                self.sale(connection, 1, f"W-BASE-{offset}", "W-ONLY",
                          self.target - timedelta(days=offset), 10, channel="WHD")
                self.sale(connection, 2, f"F-BASE-{offset}", "CORE",
                          self.target - timedelta(days=offset), 10)
                self.sale(connection, 2, f"W-BASE-2-{offset}", "CORE",
                          self.target - timedelta(days=offset), 100, channel="WHD")
            self.sale(connection, 2, "W-CURRENT", "CORE", self.target, 100, channel="WHD")
        self.sync_run(1, "orders")
        self.sync_run(2, "orders")
        whd_only, _ = self.evaluate(1, "sales_drop")
        core_drop, _ = self.evaluate(2, "sales_drop")
        self.assertEqual(whd_only["triggered"], 0)
        self.assertEqual(core_drop["triggered"], 1)
        with db.connect() as connection:
            message = connection.execute(
                "SELECT message FROM alert_events WHERE shop_id=2 AND rule_key='sales_drop'"
            ).fetchone()[0]
        self.assertIn("FBP + realFBS", message)
        self.assertIn("不包含WHD", message)

    def test_sales_drop_skips_when_order_sync_does_not_cover_baseline(self):
        with db.transaction() as connection:
            for offset in range(1, 8):
                self.sale(connection, 1, f"P-{offset}", "S-1", self.target - timedelta(days=offset), 10)
        self.sync_run(1, "orders", through=self.target, range_from=self.target)
        result, _ = self.evaluate(1, "sales_drop")
        self.assertEqual(result["triggered"], 0)
        self.assertEqual(result["skipped"][0]["reason"], "订单同步尚未覆盖销量基准周期")

    def test_low_baseline_sales_does_not_trigger(self):
        with db.transaction() as connection:
            for offset in range(1, 8):
                self.sale(connection, 1, f"P-{offset}", "S-1", self.target - timedelta(days=offset), 1)
        self.sync_run(1, "orders")
        result, _ = self.evaluate(1, "sales_drop")
        self.assertEqual(result["triggered"], 0)

    def test_inventory_uses_existing_forecast_and_only_urgent_states(self):
        with db.transaction() as connection:
            self.sale(connection, 1, "SALE-OUT", "OUT", self.target, 10)
            self.sale(connection, 1, "SALE-URGENT", "URGENT", self.target, 10)
            self.sale(connection, 1, "SALE-SAFE", "SAFE", self.target, 1)
            self.stock(connection, 1, "OUT", 0)
            self.stock(connection, 1, "URGENT", 10)
            self.stock(connection, 1, "SAFE", 1000)
        self.sync_run(1, "stock", finished=self.now.astimezone(timezone.utc))
        result, _ = self.evaluate(1, "inventory_risk")
        self.assertEqual(result["triggered"], 2)
        with db.connect() as connection:
            values = {row["sku"]: row for row in connection.execute(
                "SELECT json_extract(metric_json,'$.sku') sku,severity,message FROM alert_events")}
        self.assertEqual(values["OUT"]["severity"], "critical")
        self.assertEqual(values["URGENT"]["severity"], "high")
        self.assertIn("当前库存无法覆盖25天补货交期。", values["URGENT"]["message"])
        self.assertNotIn("SAFE", values)

    def test_inventory_alert_is_based_on_fbp_stock_only(self):
        with db.transaction() as connection:
            self.sale(connection, 1, "SALE-FBP-OUT", "OUT", self.target, 10)
            self.sale(connection, 1, "SALE-FBP-SAFE", "SAFE", self.target, 10)
            self.stock_channels(connection, 1, "OUT", [
                ("fbp", 0, 0), ("rfbs", 500, 0), ("fbo", 500, 0)])
            self.stock_channels(connection, 1, "SAFE", [
                ("fbp", 1000, 0), ("rfbs", 0, 0), ("fbo", 0, 0)])
        self.sync_run(1, "stock", finished=self.now.astimezone(timezone.utc))
        result, _ = self.evaluate(1, "inventory_risk")
        self.assertEqual(result["triggered"], 1)
        with db.connect() as connection:
            rows = {row["sku"]: row for row in connection.execute(
                "SELECT json_extract(metric_json,'$.sku') sku,severity,message FROM alert_events")}
        self.assertEqual(rows["OUT"]["severity"], "critical")
        self.assertIn("FBP库存预警", rows["OUT"]["message"])
        self.assertIn("FBP有效库存", rows["OUT"]["message"])
        self.assertNotIn("WHD", rows["OUT"]["message"])
        self.assertNotIn("SAFE", rows)

    def test_missing_ad_target_is_skipped_and_not_resolved_as_zero(self):
        with db.transaction() as connection:
            self.campaign(connection, 1)
            for offset in range(1, 8):
                self.campaign_daily(connection, 1, "C-1", self.target - timedelta(days=offset), spend=400)
            self.campaign_daily(connection, 1, "C-1", self.target, spend=700)
        self.sync_run(1, "ad_campaign_daily")
        result, _ = self.evaluate(1, "ad_spend_spike")
        self.assertEqual(result["triggered"], 1)
        with db.transaction() as connection:
            connection.execute("DELETE FROM ad_campaign_daily WHERE stat_date=?", (self.target.isoformat(),))
        result, _ = self.evaluate(1, "ad_spend_spike")
        self.assertEqual(result["triggered"], 0)
        self.assertTrue(result["skipped"])
        with db.connect() as connection:
            self.assertIsNone(connection.execute("SELECT resolved_at FROM alert_events").fetchone()[0])

    def test_missing_campaign_target_does_not_resolve_that_campaign(self):
        with db.transaction() as connection:
            for campaign_id in ("C-1", "C-2"):
                self.campaign(connection, 1, campaign_id)
                for offset in range(1, 8):
                    self.campaign_daily(connection, 1, campaign_id, self.target - timedelta(days=offset), spend=400)
                self.campaign_daily(connection, 1, campaign_id, self.target, spend=700)
        self.sync_run(1, "ad_campaign_daily")
        result, _ = self.evaluate(1, "ad_spend_spike")
        self.assertEqual(result["triggered"], 2)
        with db.transaction() as connection:
            connection.execute("DELETE FROM ad_campaign_daily WHERE campaign_id='C-2' AND stat_date=?",
                               (self.target.isoformat(),))
        result, _ = self.evaluate(1, "ad_spend_spike")
        self.assertEqual(result["resolved"], 0)
        with db.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM alert_events WHERE resolved_at IS NULL").fetchone()[0], 2)

    def test_incident_acknowledge_resolve_and_retrigger(self):
        with db.transaction() as connection:
            self.campaign(connection, 1)
            for offset in range(1, 8):
                self.campaign_daily(connection, 1, "C-1", self.target - timedelta(days=offset), spend=400)
            self.campaign_daily(connection, 1, "C-1", self.target, spend=700)
        self.sync_run(1, "ad_campaign_daily")
        first, sender = self.evaluate(1, "ad_spend_spike", configured=True)
        with db.connect() as connection:
            event_id = connection.execute("SELECT id FROM alert_events").fetchone()[0]
        self.assertEqual(acknowledge_alert(event_id), {"ok": True, "id": event_id})
        with db.transaction() as connection:
            connection.execute("UPDATE ad_campaign_daily SET spend_rub=400 WHERE stat_date=?", (self.target.isoformat(),))
        self.evaluate(1, "ad_spend_spike", configured=True)
        with db.connect() as connection:
            rows = connection.execute("SELECT * FROM alert_events ORDER BY id").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0]["resolved_at"])
        self.assertIsNotNone(rows[0]["acknowledged_at"])
        with db.transaction() as connection:
            connection.execute("UPDATE ad_campaign_daily SET spend_rub=700 WHERE stat_date=?", (self.target.isoformat(),))
        result, _ = self.evaluate(1, "ad_spend_spike", configured=True)
        self.assertEqual(result["triggered"], 1)
        self.assertEqual(sender.call_count, 1)
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0], 2)

    def test_dingtalk_failure_does_not_fail_sync(self):
        with db.transaction() as connection:
            self.campaign(connection, 1)
            for offset in range(1, 8):
                self.campaign_daily(connection, 1, "C-1", self.target - timedelta(days=offset), spend=400)
            self.campaign_daily(connection, 1, "C-1", self.target, spend=700)
        self.sync_run(1, "ad_campaign_daily")
        with patch("app.alerts.evaluation.dingtalk_configured", return_value=True), \
                patch("app.alerts.evaluation.send_text", side_effect=RuntimeError("webhook secret must not leak")):
            result = evaluate_alerts(1, rule_keys=("ad_spend_spike",), now=self.now)
        self.assertEqual((result["triggered"], result["notifications_failed"]), (1, 1))
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT last_notify_error FROM alert_events").fetchone()[0], "钉钉发送失败")
        with db.transaction() as connection:
            run_id = connection.execute("INSERT INTO sync_runs(shop_id,module,status) VALUES(1,'orders','running')").lastrowid
        with patch("app.sync_jobs.sync_module", return_value={"records": 1}), \
                patch("app.sync_jobs.evaluate_alerts", side_effect=RuntimeError("alert failure")):
            _run_sync_job(run_id, "orders", 1, [(self.now - timedelta(days=1), self.now)])
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT status FROM sync_runs WHERE id=?", (run_id,)).fetchone()[0], "success")

    def test_disabled_and_non_notifying_rule_stays_quiet_but_creates_no_event(self):
        update_alert_rule("ad_spend_spike", {"shop_id": 1, "enabled": False,
                                               "notify_dingtalk": True, "config": {}})
        result, sender = self.evaluate(1, "ad_spend_spike", configured=True)
        self.assertEqual(result["triggered"], 0)
        sender.assert_not_called()
        update_alert_rule("ad_spend_spike", {"shop_id": 1, "enabled": True,
                                               "notify_dingtalk": False, "config": {}})
        self.assertEqual(self.evaluate(1, "ad_spend_spike", configured=True)[0]["triggered"], 0)

    def test_alert_api_filters_pagination_summary_and_acknowledge(self):
        with db.transaction() as connection:
            self.campaign(connection, 1)
            for offset in range(1, 8):
                self.campaign_daily(connection, 1, "C-1", self.target - timedelta(days=offset), spend=400)
            self.campaign_daily(connection, 1, "C-1", self.target, spend=700)
        self.sync_run(1, "ad_campaign_daily")
        self.evaluate(1, "ad_spend_spike")
        result = alerts(shop_id=1, status="open", category="advertising", page=1, size=1)
        self.assertEqual((result["total"], len(result["items"])), (1, 1))
        self.assertEqual(alerts_summary(1)["advertising"], 1)
        event_id = result["items"][0]["id"]
        self.assertEqual(alert_acknowledge(event_id)["ok"], True)
        self.assertTrue(alerts(shop_id=1)["items"][0]["acknowledged_at"])
        with self.assertRaises(HTTPException): alerts(shop_id=3)
        with self.assertRaises(HTTPException): alerts(shop_id=1, category="bad")
        with self.assertRaises(HTTPException): asyncio.run(alerts_evaluate(MockRequest({"shop_id": 3})))

    def test_api_rule_update_rejects_invalid_payload(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(alert_rule_update("ad_drr_high", MockRequest({
                "shop_id": 1, "enabled": True, "notify_dingtalk": True,
                "config": {"threshold_drr": float("inf")}})))
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
