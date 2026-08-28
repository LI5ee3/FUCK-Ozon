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
    def test_fastapi_uses_vue_dist_and_keeps_legacy_mount(self):
        self.assertEqual(main.FRONTEND_DIST, ROOT / "frontend/dist")
        mounts = {route.path: route for route in main.app.routes if isinstance(route, Mount)}
        self.assertIn("/static", mounts)
        self.assertIn("/assets", mounts)
        self.assertEqual(mounts["/assets"].name, "frontend-assets")

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
        update = (ROOT / "scripts/update.sh").read_text()
        ignored = (ROOT / ".gitignore").read_text()
        self.assertIn("npm ci", build)
        self.assertIn("--outDir dist.next", build)
        self.assertNotIn("npm install", build)
        self.assertIn("build-frontend.sh", update)
        self.assertIn("status='running'", update)
        for path in ("frontend/dist.next/", "frontend/dist.previous/", "frontend/dist.failed/"):
            self.assertIn(path, ignored)


if __name__ == "__main__":
    unittest.main()
