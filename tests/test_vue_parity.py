import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend/src"
ROUTES = (
    ("overview", "/", "DashboardView.vue"),
    ("orders", "/orders", "OrdersView.vue"),
    ("analytics", "/analytics", "AnalyticsView.vue"),
    ("advertising", "/ads", "AdsView.vue"),
    ("ad-campaigns", "/ads/campaigns", "AdCampaignsView.vue"),
    ("ad-skus", "/ads/skus", "AdSkusView.vue"),
    ("timeliness", "/timeliness", "TimelinessView.vue"),
    ("risk", "/risk", "RiskView.vue"),
    ("returns", "/returns", "ReturnsView.vue"),
    ("alerts", "/alerts", "AlertsView.vue"),
    ("complaints", "/complaints", "ComplaintsView.vue"),
    ("inventory", "/inventory", "InventoryView.vue"),
    ("profit", "/profit", "ProfitView.vue"),
    ("transfer", "/transfer", "TransferView.vue"),
    ("sync", "/sync", "SyncView.vue"),
    ("rules", "/rules", "RulesView.vue"),
    ("push-subscriptions", "/push-subscriptions", "PushSubscriptionsView.vue"),
    ("dingtalk", "/dingtalk", "DingTalkView.vue"),
    ("settings", "/settings", "SettingsView.vue"),
)


class VueParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = (FRONTEND / "router/index.ts").read_text()
        cls.navigation = (FRONTEND / "router/navigation.ts").read_text()
        cls.client = (FRONTEND / "api/client.ts").read_text()
        cls.inventory = (FRONTEND / "views/InventoryView.vue").read_text()
        cls.ads = (FRONTEND / "api/ads.ts").read_text()
        cls.frontend_text = "\n".join(path.read_text() for path in (FRONTEND / "views").glob("*.vue"))

    def test_all_nineteen_routes_have_real_views(self):
        self.assertEqual(len(ROUTES), 19)
        for name, path, view in ROUTES:
            route_source = self.navigation if name != "settings" else self.router
            self.assertIn(path if name != "settings" else 'path: "settings"', route_source)
            self.assertIn(f'import("../views/{view}")', self.router)
        self.assertNotIn("PlaceholderView", self.router)

    def test_all_frontend_network_requests_use_authenticated_client(self):
        for path in (FRONTEND / "api").glob("*.ts"):
            if path.name != "client.ts":
                self.assertNotRegex(path.read_text(), r"\bfetch\s*\(")
        self.assertIn('credentials: "include"', self.client)
        self.assertIn('headers.set("X-CSRF-Token", csrfToken)', self.client)
        self.assertIn("UNAUTHORIZED_EVENT", self.client)

    def test_legacy_sensitive_api_contracts_are_preserved(self):
        self.assertIn("/api/performance/overview", self.ads)
        self.assertIn("/api/performance/campaign-stats", self.ads)
        self.assertIn("/api/performance/sku-stats", self.ads)
        self.assertNotIn("/api/analytics/data", (FRONTEND / "views/AdsView.vue").read_text())
        for module, endpoint in (
            ("risk.ts", "/api/risk"),
            ("returns.ts", "/api/returns"),
            ("complaints.ts", "/api/exception-complaints/shipping"),
            ("dingtalk.ts", "/api/dingtalk/settings"),
        ):
            self.assertIn(endpoint, (FRONTEND / "api" / module).read_text())
        self.assertEqual(
            re.search(r'export type ExportModule = ([^;]+);', (FRONTEND / "api/transfer.ts").read_text()).group(1),
            '"orders" | "risk" | "returns" | "complaints"',
        )

    def test_inventory_policy_remains_backend_owned(self):
        backend = (ROOT / "app/main.py").read_text()
        self.assertIn("FORECAST_LEAD_TIME_DAYS = 25", backend)
        self.assertIn("FORECAST_TARGET_COVER_DAYS = 60", backend)
        self.assertIn("FORECAST_OVERSTOCK_DAYS = 90", backend)
        self.assertIn('"inbound_included": False', backend)
        self.assertIn("demand = FBP + realFBS sales", backend)
        self.assertIn("replenishment stock = FBP only", backend)
        self.assertIn("row.lead_time_days", self.inventory)
        self.assertIn("row.target_cover_days", self.inventory)
        self.assertNotIn("FORECAST_LEAD_TIME_DAYS", self.inventory)

    def test_frontend_does_not_contain_server_credentials(self):
        for secret_name in (
            "ADMIN_PASSWORD",
            "SHOP_1_OZON_API_KEY",
            "SHOP_2_OZON_API_KEY",
            "DINGTALK_SECRET",
            "OZON_WEBHOOK_SECRET",
        ):
            self.assertNotIn(secret_name, self.frontend_text)


if __name__ == "__main__":
    unittest.main()
