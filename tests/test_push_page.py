import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
VIEW = (ROOT / "frontend/src/views/PushSubscriptionsView.vue").read_text()
API = (ROOT / "frontend/src/api/push-subscriptions.ts").read_text()
NAVIGATION = (ROOT / "frontend/src/router/navigation.ts").read_text()
ROUTER = (ROOT / "frontend/src/router/index.ts").read_text()


class PushSubscriptionsPageTest(unittest.TestCase):
    def test_navigation_uses_chinese_name_and_order(self):
        self.assertIn('label: "推送订阅管理"', NAVIGATION)
        self.assertNotIn("Ozon Push Webhook", VIEW)
        self.assertLess(NAVIGATION.index('name: "rules"'), NAVIGATION.index('name: "push-subscriptions"'))
        self.assertLess(NAVIGATION.index('name: "push-subscriptions"'), NAVIGATION.index('name: "dingtalk"'))

    def test_page_container_and_title_are_registered(self):
        self.assertIn('<section class="push-view">', VIEW)
        self.assertIn('<div class="push-shop-grid">', VIEW)
        self.assertIn('"push-subscriptions": () => import("../views/PushSubscriptionsView.vue")', ROUTER)
        self.assertIn('icon: "zap"', NAVIGATION)

    def test_existing_notification_apis_are_used(self):
        for path in (
            "/api/ozon/notifications/push-types",
            "/api/ozon/notifications/check",
            "/api/ozon/notifications/set",
            "/api/ozon/notifications/list",
            "/api/ozon/notifications/enable",
            "/api/ozon/notifications/delete",
        ):
            self.assertIn(path, API)

    def test_vue_sources_do_not_contain_env_secrets(self):
        source = VIEW + API
        self.assertNotIn("OZON_WEBHOOK_SECRET_", source)
        self.assertNotIn("SHOP_1_OZON_API_KEY", source)
        self.assertNotIn("SHOP_2_OZON_API_KEY", source)
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                key, separator, value = line.partition("=")
                if separator and key.startswith("OZON_WEBHOOK_SECRET_") and value.strip():
                    self.assertNotIn(value.strip(), source)


if __name__ == "__main__":
    unittest.main()
