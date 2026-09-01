import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend/src"


class FrontendContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = (FRONTEND / "app/router/index.ts").read_text()
        cls.client = (FRONTEND / "shared/api/client.ts").read_text()
        cls.ads = (FRONTEND / "features/advertising/api.ts").read_text()
        cls.frontend_text = "\n".join(
            path.read_text() for path in FRONTEND.rglob("*") if path.is_file()
        )

    def test_all_frontend_network_requests_use_authenticated_client(self):
        api_files = [FRONTEND / "shared/api/shops.ts", FRONTEND / "app/auth/api.ts"]
        api_files.extend((FRONTEND / "features").glob("*/api.ts"))
        for path in api_files:
            self.assertNotRegex(path.read_text(), r"\bfetch\s*\(")
        self.assertIn('credentials: "include"', self.client)
        self.assertIn('headers.set("X-CSRF-Token", csrfToken)', self.client)
        self.assertIn("UNAUTHORIZED_EVENT", self.client)

    def test_legacy_sensitive_api_contracts_are_preserved(self):
        self.assertIn("/api/performance/overview", self.ads)
        self.assertIn("/api/performance/campaign-stats", self.ads)
        self.assertIn("/api/performance/sku-stats", self.ads)
        self.assertNotIn("/api/analytics/data", (FRONTEND / "features/advertising/AdsView.vue").read_text())
        for path, endpoint in (
            ("features/risk/api.ts", "/api/risk"),
            ("features/returns/api.ts", "/api/returns"),
            ("features/complaints/api.ts", "/api/exception-complaints/shipping"),
            ("features/dingtalk/api.ts", "/api/dingtalk/settings"),
        ):
            self.assertIn(endpoint, (FRONTEND / path).read_text())
        self.assertEqual(
            re.search(r'export type ExportModule = ([^;]+);', (FRONTEND / "features/transfer/api.ts").read_text()).group(1),
            '"orders" | "risk" | "returns" | "complaints"',
        )

    def test_frontend_does_not_contain_server_credentials(self):
        for secret_name in (
            "ADMIN_PASSWORD",
            "SHOP_1_OZON_API_KEY",
            "SHOP_2_OZON_API_KEY",
            "DINGTALK_SECRET",
            "OZON_WEBHOOK_SECRET",
        ):
            self.assertNotIn(secret_name, self.frontend_text)
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                key, separator, value = line.partition("=")
                if separator and key.startswith("OZON_WEBHOOK_SECRET_") and value.strip():
                    self.assertNotIn(value.strip(), self.frontend_text)

    def test_notification_api_contracts_are_preserved(self):
        api = (FRONTEND / "features/push-subscriptions/api.ts").read_text()
        for path in (
            "/api/ozon/notifications/push-types",
            "/api/ozon/notifications/check",
            "/api/ozon/notifications/set",
            "/api/ozon/notifications/list",
            "/api/ozon/notifications/enable",
            "/api/ozon/notifications/delete",
        ):
            self.assertIn(path, api)

    def test_sku_detail_route_and_links_preserve_shop_context(self):
        detail = (FRONTEND / "features/sku-detail/SkuDetailView.vue").read_text()
        api = (FRONTEND / "features/sku-detail/api.ts").read_text()
        self.assertIn('path: "sku/:sku"', self.router)
        self.assertIn('name: "sku-detail"', self.router)
        self.assertNotIn('name: "sku-detail"', (FRONTEND / "app/router/navigation.ts").read_text())
        self.assertIn("/api/sku-detail/", api)
        self.assertIn("/api/analytics/data", api)
        self.assertIn("getSkuTraffic", detail)
        self.assertIn("trafficError", detail)
        for relative in (
            "features/inventory/InventoryView.vue",
            "features/advertising/AdSkusView.vue",
            "features/analytics/AnalyticsView.vue",
            "features/orders/OrdersView.vue",
            "features/orders/components/OrderDetailPanel.vue",
        ):
            source = (FRONTEND / relative).read_text()
            self.assertRegex(source, r"name:\s*['\"]sku-detail['\"]", relative)
            self.assertIn("shop_id: String(", source, relative)

    def test_sku_detail_bugfix_contracts(self):
        detail = (FRONTEND / "features/sku-detail/SkuDetailView.vue").read_text()
        orders = (FRONTEND / "features/orders/OrdersView.vue").read_text()
        after_sales = (FRONTEND / "features/sku-detail/components/AfterSalesPanel.vue").read_text()
        ads_chart = (FRONTEND / "features/advertising/components/AdsTrendChart.vue").read_text()
        ads_panel = (FRONTEND / "features/sku-detail/components/AdvertisingPanel.vue").read_text()
        self.assertIn("const availableTo = shiftDays(beijingToday(), -3);", detail)
        self.assertIn("function analyticsRequestFor", detail)
        self.assertIn("if (!request)", detail)
        self.assertIn("return null;", detail)
        self.assertNotIn('if (value === "2") return 2;\n  return 1;', detail)
        self.assertIn('renderCopyButton(value, "点击复制 SKU", "orders-copy-icon", true)', orders)
        self.assertIn('icon: "copy"', orders)
        self.assertIn("退货率 / 投诉率均以当前周期创建且包含该 SKU 的订单为分母", after_sales)
        self.assertNotIn("showOrders", ads_chart)
        self.assertNotIn("show-orders", ads_panel)


if __name__ == "__main__":
    unittest.main()
