import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend/src"


class FrontendContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = (FRONTEND / "router/index.ts").read_text()
        cls.client = (FRONTEND / "api/client.ts").read_text()
        cls.ads = (FRONTEND / "api/ads.ts").read_text()
        cls.frontend_text = "\n".join(
            path.read_text() for path in FRONTEND.rglob("*") if path.is_file()
        )

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
        api = (FRONTEND / "api/push-subscriptions.ts").read_text()
        for path in (
            "/api/ozon/notifications/push-types",
            "/api/ozon/notifications/check",
            "/api/ozon/notifications/set",
            "/api/ozon/notifications/list",
            "/api/ozon/notifications/enable",
            "/api/ozon/notifications/delete",
        ):
            self.assertIn(path, api)


if __name__ == "__main__":
    unittest.main()
