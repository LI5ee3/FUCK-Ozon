import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "static" / "index.html").read_text()
SCRIPT = (ROOT / "static" / "app.js").read_text()


class PushSubscriptionsPageTest(unittest.TestCase):
    def test_navigation_uses_chinese_name_and_order(self):
        self.assertIn('data-page="pushSubscriptions"', INDEX)
        self.assertIn("<span>推送订阅管理</span>", INDEX)
        self.assertNotIn("Ozon Push Webhook", INDEX)
        self.assertLess(INDEX.index('data-page="rules"'), INDEX.index('data-page="pushSubscriptions"'))
        self.assertLess(INDEX.index('data-page="pushSubscriptions"'), INDEX.index('data-page="dingtalk"'))

    def test_page_container_and_title_are_registered(self):
        self.assertIn('<section id="pushSubscriptions" class="page">', INDEX)
        self.assertIn('<div id="pushShopGrid" class="push-shop-grid"></div>', INDEX)
        self.assertIn('pushSubscriptions:"推送订阅管理"', SCRIPT)
        self.assertIn('if(page==="pushSubscriptions") return loadPushSubscriptions()', SCRIPT)
        self.assertIn('pushSubscriptions:"zap"', SCRIPT)

    def test_existing_notification_apis_are_used(self):
        for path in (
            "/api/ozon/notifications/push-types",
            "/api/ozon/notifications/check",
            "/api/ozon/notifications/set",
            "/api/ozon/notifications/list",
            "/api/ozon/notifications/enable",
            "/api/ozon/notifications/delete",
        ):
            self.assertIn(path, SCRIPT)

    def test_static_sources_do_not_contain_env_secrets(self):
        source = INDEX + SCRIPT
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
