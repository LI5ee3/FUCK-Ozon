from contextlib import asynccontextmanager
import hmac
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import transaction
from .dingtalk import start_scheduler, stop_scheduler
from .migrations import init_db
from .ozon.webhooks import start_webhook_worker, stop_webhook_worker
from .routers.alerts import router as alerts_router
from .routers.analytics import router as analytics_router
from .routers.auth import _authenticated, router as auth_router
from .routers.complaints import router as complaints_router
from .routers.dashboard import router as dashboard_router
from .routers.dingtalk import router as dingtalk_router
from .routers.exchange import router as exchange_router
from .routers.export import router as export_router
from .routers.imports import router as imports_router
from .routers.inventory import router as inventory_router
from .routers.ozon_notifications import router as ozon_notifications_router
from .routers.ozon_webhooks import router as ozon_webhooks_router
from .routers.orders import router as orders_router
from .routers.performance import router as performance_router
from .routers.products import router as products_router
from .routers.returns import router as returns_router
from .routers.risk import router as risk_router
from .routers.shops import router as shops_router
from .routers.sync import router as sync_router
from .routers.timeliness import router as timeliness_router
from .security import migrate_env_password
from .sync_jobs import _start_auto_sync_scheduler, _stop_auto_sync_scheduler, _trim_sync_runs

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
FRONTEND_PUBLIC_ASSETS = ROOT / "frontend" / "public" / "assets"


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate_env_password(ROOT / ".env")
    init_db()
    with transaction() as db:
        db.execute("""UPDATE sync_runs SET status='failed',error='服务重启，任务已中断，请重新拉取',
          finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE status='running'""")
        _trim_sync_runs(db)
    start_scheduler()
    _start_auto_sync_scheduler()
    start_webhook_worker()
    try:
        yield
    finally:
        stop_webhook_worker()
        stop_scheduler()
        _stop_auto_sync_scheduler()


class ViteStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if (response.status_code in (200, 304)
                and re.fullmatch(r".+-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+", Path(path).name)
                and not (FRONTEND_PUBLIC_ASSETS / path).is_file()):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app = FastAPI(title="oPanel", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/assets", ViteStaticFiles(directory=FRONTEND_ASSETS, check_dir=False), name="frontend-assets")
app.include_router(analytics_router)
app.include_router(auth_router)
app.include_router(ozon_notifications_router)
app.include_router(alerts_router)
app.include_router(sync_router)
app.include_router(export_router)
app.include_router(performance_router)
app.include_router(shops_router)
app.include_router(ozon_webhooks_router)
app.include_router(dingtalk_router)
app.include_router(dashboard_router)
app.include_router(orders_router)
app.include_router(risk_router)
app.include_router(timeliness_router)
app.include_router(complaints_router)
app.include_router(returns_router)
app.include_router(inventory_router)
app.include_router(products_router)
app.include_router(imports_router)
app.include_router(exchange_router)


def _is_ozon_webhook_path(path):
    parts = path.split("/")
    return len(parts) == 5 and parts[:4] == ["", "api", "webhooks", "ozon"] and bool(parts[4])


@app.middleware("http")
async def protect_api(request: Request, call_next):
    # 安全边界必须基于路由匹配所用的 ASGI scope path；request.url.path 会被恶意 Host 头重构污染（CVE-2026-48710）
    path = request.scope["path"]
    public = {"/api/login", "/api/session"}
    webhook = _is_ozon_webhook_path(path)
    if path.startswith("/api/") and path not in public and not webhook and not _authenticated(request):
        return Response(json.dumps({"detail": "未登录"}, ensure_ascii=False), 401, media_type="application/json")
    if (request.method in {"POST", "PUT", "PATCH", "DELETE"} and path != "/api/login" and not webhook
            and path.startswith("/api/")):
        try:
            _, csrf, _ = request.cookies.get("session", "").split(".", 2)
        except ValueError:
            csrf = ""
        if not csrf or not hmac.compare_digest(csrf, request.headers.get("x-csrf-token", "")):
            return Response(json.dumps({"detail": "CSRF令牌无效"}, ensure_ascii=False), 403,
                            media_type="application/json")
    return await call_next(request)


def _frontend_index_response():
    if not FRONTEND_INDEX.is_file():
        return Response("前端构建不存在，请先执行 frontend production build", 503, media_type="text/plain")
    return FileResponse(FRONTEND_INDEX, headers={"Cache-Control": "no-cache"})


@app.get("/")
def index():
    return _frontend_index_response()


@app.get("/{path:path}")
def spa_fallback(path: str):
    if (path == "api" or path.startswith("api/") or
            path == "static" or path.startswith("static/") or
            path == "assets" or path.startswith("assets/")):
        raise HTTPException(404)
    return _frontend_index_response()
