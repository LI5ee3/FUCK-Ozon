import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES = (
    ("overview", "/"),
    ("orders", "/orders"),
    ("analytics", "/analytics"),
    ("advertising", "/ads"),
    ("ad-campaigns", "/ads/campaigns"),
    ("ad-skus", "/ads/skus"),
    ("timeliness", "/timeliness"),
    ("risk", "/risk"),
    ("returns", "/returns"),
    ("alerts", "/alerts"),
    ("complaints", "/complaints"),
    ("inventory", "/inventory"),
    ("product-costs", "/product-costs"),
    ("profit", "/profit"),
    ("transfer", "/transfer"),
    ("sync", "/sync"),
    ("rules", "/rules"),
    ("push-subscriptions", "/push-subscriptions"),
    ("dingtalk", "/dingtalk"),
)


class VueShellTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = (ROOT / "frontend/src/app/router/index.ts").read_text()
        cls.navigation = (ROOT / "frontend/src/app/router/navigation.ts").read_text()
        cls.app = (ROOT / "frontend/src/App.vue").read_text()
        cls.auth = (ROOT / "frontend/src/app/auth/api.ts").read_text()
        cls.client = (ROOT / "frontend/src/shared/api/client.ts").read_text()
        cls.layout = (ROOT / "frontend/src/app/layouts/AppLayout.vue").read_text()

    def test_navigation_routes_have_real_lazy_views(self):
        mapping = self.router.split("const pageRoutes", 1)[0]
        self.assertEqual(
            re.findall(r'^    label: "([^"]+)"', self.navigation, re.MULTILINE),
            ["业务概览", "广告管理", "履约与异常", "供应链与数据", "系统配置"],
        )
        for name, path in ROUTES:
            self.assertRegex(self.navigation, rf'\{{ name: "{re.escape(name)}".*path: "{re.escape(path)}"')
            self.assertIsNotNone(
                re.search(
                    rf'^\s*"?{re.escape(name)}"?\s*:\s*\(\) => import\("\.\./\.\./features/[^"\n]+\.vue"\),$',
                    mapping,
                    re.MULTILINE,
                )
            )

    def test_router_fails_fast_without_placeholder(self):
        self.assertNotIn("PlaceholderView", self.router)
        self.assertIn("function componentFor(name: string)", self.router)
        self.assertIn("throw new Error(`Missing migrated Vue view: ${name}`)", self.router)
        self.assertIn('{ path: "/:pathMatch(.*)*", redirect: "/" }', self.router)
        self.assertIn("createWebHistory(import.meta.env.BASE_URL)", self.router)

    def test_settings_and_auth_shell_contracts(self):
        self.assertIn('name: "settings"', self.router)
        self.assertIn('component: () => import("../../features/settings/SettingsView.vue")', self.router)
        self.assertIn('v-else-if="!authenticated"', self.app)
        self.assertIn("<RouterView v-else />", self.app)
        self.assertIn("void restoreSession()", self.app)
        self.assertEqual(
            ["/api/session", "/api/login", "/api/logout"],
            re.findall(r'"(/api/(?:session|login|logout))"', self.auth),
        )
        self.assertIn("setCsrfToken(\"\")", self.client)
        self.assertIn("UNAUTHORIZED_EVENT", self.client)
        self.assertIn("LOGOUT_EVENT", self.layout)
        self.assertIn("route.name !== 'profit'", self.layout)
        self.assertIn("navigate('/settings')", self.layout)
        self.assertIn("管理员", self.layout)

    def test_placeholder_file_and_styles_are_gone(self):
        self.assertFalse((ROOT / "frontend/src/features/PlaceholderView.vue").exists())
        style = "\n".join(path.read_text() for path in (ROOT / "frontend/src/styles").glob("*.css"))
        self.assertNotRegex(style, r"\.placeholder-(?:view|card|body|mark|copy|note|status)")


if __name__ == "__main__":
    unittest.main()
