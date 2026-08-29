import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from starlette.routing import Mount

from app import main


ROOT = Path(__file__).resolve().parents[1]


class VueProductionTest(unittest.TestCase):
    def test_fastapi_uses_vue_dist_and_only_vue_assets_mount(self):
        self.assertEqual(main.FRONTEND_DIST, ROOT / "frontend/dist")
        mounts = {route.path: route for route in main.app.routes if isinstance(route, Mount)}
        self.assertNotIn("/static", mounts)
        self.assertIn("/assets", mounts)
        self.assertEqual(mounts["/assets"].name, "frontend-assets")

    def test_only_hashed_vite_assets_are_immutable(self):
        with tempfile.TemporaryDirectory() as temp:
            assets = Path(temp) / "dist/assets"
            public = Path(temp) / "public/assets"
            assets.mkdir(parents=True)
            public.mkdir(parents=True)
            (assets / "index-Ab12_cd3.js").write_text("js")
            (assets / "logo.svg").write_text("logo")
            (public / "logo.svg").write_text("logo")
            static = main.ViteStaticFiles(directory=assets)
            scope = {"type": "http", "method": "GET", "headers": []}
            with patch.object(main, "FRONTEND_PUBLIC_ASSETS", public):
                hashed = asyncio.run(static.get_response("index-Ab12_cd3.js", scope))
                unhashed = asyncio.run(static.get_response("logo.svg", scope))
        self.assertEqual(hashed.headers["cache-control"], "public, max-age=31536000, immutable")
        self.assertNotIn("cache-control", unhashed.headers)

    def test_root_and_fallback_serve_index_with_no_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            index = Path(temp) / "index.html"
            index.write_text('<div id="app"></div>', encoding="utf-8")
            with patch.object(main, "FRONTEND_INDEX", index):
                response = main.index()
                fallback = main.spa_fallback("orders")
            self.assertIsInstance(response, FileResponse)
            self.assertEqual(Path(response.path), index)
            self.assertEqual(response.headers["cache-control"], "no-cache")
            self.assertIsInstance(fallback, FileResponse)
            self.assertEqual(Path(fallback.path), index)

    def test_missing_index_is_explicit_503_without_path_leak(self):
        missing = Path(tempfile.gettempdir()) / "opanel-phase19-missing-index.html"
        with patch.object(main, "FRONTEND_INDEX", missing):
            response = main.index()
        self.assertIsInstance(response, Response)
        self.assertEqual(response.status_code, 503)
        self.assertIn("前端构建不存在", response.body.decode())
        self.assertNotIn(str(missing), response.body.decode())

    def test_catch_all_is_last_and_never_handles_reserved_namespaces(self):
        fallback_indices = [
            index for index, route in enumerate(main.app.routes)
            if route.path == "/{path:path}"
        ]
        self.assertEqual(len(fallback_indices), 1)
        fallback_index = fallback_indices[0]
        self.assertEqual(fallback_index, len(main.app.routes) - 1)
        self.assertLess(
            max(index for index, route in enumerate(main.app.routes)
                if route.path.startswith("/api")),
            fallback_index,
        )
        for path in ("api/does-not-exist", "static/missing.js", "assets/missing.js"):
            with self.assertRaises(HTTPException) as error:
                main.spa_fallback(path)
            self.assertEqual(error.exception.status_code, 404)

    def test_production_scripts_and_gitignore_use_staged_dist(self):
        build = (ROOT / "scripts/build-frontend.sh").read_text()
        test = (ROOT / "scripts/test.sh").read_text()
        node_check = (ROOT / "scripts/check-node.sh").read_text()
        update = (ROOT / "scripts/update.sh").read_text()
        ignored = (ROOT / ".gitignore").read_text()
        self.assertIn("npm ci", test)
        self.assertIn('"$ROOT/scripts/check-node.sh"', test)
        self.assertIn('"$ROOT/scripts/check-node.sh"', build)
        self.assertIn("major === 22 && minor >= 18", node_check)
        self.assertIn("major === 24 && minor >= 11", node_check)
        self.assertIn("major >= 25", node_check)
        self.assertLess(test.index("check-node.sh"), test.index("npm ci"))
        self.assertLess(build.index("check-node.sh"), build.index("npm run build"))
        self.assertIn("--outDir dist.next", build)
        self.assertNotIn("npm ci", build)
        self.assertIn("build-frontend.sh", update)
        self.assertIn("status='running'", update)
        deploy = update[update.index('git -C "$ROOT" pull --ff-only'):]
        self.assertLess(deploy.index('scripts/test.sh'), deploy.index('scripts/stop.sh'))
        self.assertLess(deploy.index('scripts/build-frontend.sh'), deploy.index('scripts/stop.sh'))
        for path in ("frontend/dist.next/", "frontend/dist.previous/", "frontend/dist.failed/"):
            self.assertIn(path, ignored)

    def test_production_asset_checks_follow_public_assets_directory(self):
        public_assets = sorted(
            path.name for path in (ROOT / "frontend/public/assets").iterdir() if path.is_file()
        )
        self.assertEqual(public_assets, ["TABLER_ICONS_LICENSE", "logo.svg"])
        build = (ROOT / "scripts/build-frontend.sh").read_text()
        verify = (ROOT / "scripts/verify-frontend.sh").read_text()
        self.assertIn('for source in "$FRONTEND/public/assets"/*; do', build)
        self.assertIn('for source in "$ROOT/frontend/public/assets"/*; do', verify)
        self.assertNotIn("morphicons.js", build)
        self.assertNotIn('/assets/morphicons.js', verify)

    def test_core_route_styles_follow_lazy_views(self):
        global_style = "\n".join(
            (ROOT / "frontend/src/styles" / name).read_text()
            for name in ("tokens.css", "base.css", "layout.css", "components.css")
        )
        for view_name, css_name, prefix, css_import in (
            ("features/dashboard/DashboardView.vue", "features/dashboard/dashboard.css", "dashboard", 'import "./dashboard.css";'),
            ("features/orders/OrdersView.vue", "features/orders/orders.css", "orders", 'import "./orders.css";'),
            ("features/analytics/AnalyticsView.vue", "styles/analytics.css", "analytics", 'import "../../styles/analytics.css";'),
            ("features/complaints/ComplaintsView.vue", "features/complaints/complaints.css", "complaints", 'import "./complaints.css";'),
        ):
            view = (ROOT / "frontend/src" / view_name).read_text()
            css = ROOT / "frontend/src" / css_name
            self.assertIn(css_import, view)
            self.assertTrue(css.is_file())
            self.assertRegex(css.read_text(), rf"(?m)^\.{prefix}-")
            self.assertNotRegex(global_style, rf"(?m)^\.{prefix}(?:-|\s|\{{|,)")

        for view_name in ("ComplaintsView.vue", "ReturnsView.vue", "RiskView.vue", "TimelinessView.vue"):
            feature = view_name.removesuffix("View.vue").lower()
            self.assertIn('import "../../styles/analytics.css";', (ROOT / "frontend/src/features" / feature / view_name).read_text())


if __name__ == "__main__":
    unittest.main()
