from contextlib import asynccontextmanager
import hashlib
import hmac
import ipaddress
import json
import math
import secrets
import statistics
import threading
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .alerts import (acknowledge_alert, alert_summary, evaluate_alerts, get_alert_rules,
                     list_alert_events, update_alert_rule)
from .db import DATA_DIR, connect, init_db, transaction
from .dingtalk import (configured as dingtalk_configured, next_push_time,
                       send_sync_failure, start_scheduler, stop_scheduler)
from .exchange import (convert_compensation, exchange_rate_status, load_base_rate_periods,
                       rates_for_order, sync_exchange_rates)
from .importer import CHANNELS, import_csv
from .ozon.client import (BEIJING, _env, notification_check, notification_delete,
                          notification_enable, notification_list, notification_set,
                          probe_shop, push_type_list)
from .ozon.mappings import (CANCEL_REASON_ZH, PUSH_EVENT_TYPES, RFBS_RETURN_STATUS_ZH,
                            RETURN_STATUS_ZH, STATUS_ZH)
from .ozon.sync import default_range, sync_module
from .ozon.webhooks import process_webhook_event, webhook_validation_error
from .performance import (PerformanceConfigurationError, list_campaigns,
                           sync_performance_campaigns, sync_performance_statistics)
from .products import clean_product_name, load_product_rules, resolve_product
from .routers.analytics import router as analytics_router
from .security import (clear_login_failures, login_limited, migrate_env_password,
                       password_matches, record_login_failure)

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
ACTIVE = "NOT (o.status_raw='已取消' AND o.shipped=0)"
BUYER_UNCLAIMED_REASONS = (
    "Покупатель не забрал заказ",
    "Покупатель отменил заказ",
    "Покупатель отменил заказ: не устроил срок доставки",
    "Покупатель отказался при вручении: товар не подошел",
    "Покупатель отменил заказ: нашел дешевле",
)
RISK_REASON_ZH = CANCEL_REASON_ZH
SYNC_MODULES = {"orders", "returns", "stock"}
AD_SYNC_MODULES = {"ad_campaign_daily", "ad_sku_daily"}
AUTO_SYNC_MODULES = SYNC_MODULES | AD_SYNC_MODULES
PERFORMANCE_SYNC_MODULE = "ad_campaigns"
AUTO_SYNC_INTERVALS = {1, 2, 3, 4, 6, 8, 12, 24}
FORECAST_WINDOWS = (7, 15, 30)
FORECAST_WEIGHTS = {7: .50, 15: .30, 30: .20}
FORECAST_LEAD_TIME_DAYS = 25
FORECAST_TARGET_COVER_DAYS = 60
FORECAST_OVERSTOCK_DAYS = 90
FORECAST_RISK_LABELS = {
    "out_of_stock": "缺货",
    "urgent_replenishment": "紧急补货",
    "replenish": "需要补货",
    "sufficient": "库存充足",
    "overstock": "库存偏高",
    "no_recent_sales": "无近期销量",
}
FORECAST_RISK_ORDER = {
    "out_of_stock": 0, "urgent_replenishment": 1, "replenish": 2,
    "sufficient": 3, "overstock": 4, "no_recent_sales": 5,
}
_auto_sync_stop = threading.Event()
_auto_sync_thread = None


def _trim_sync_runs(db, keep=10, scheduled_slot=None, today=None):
    today = (scheduled_slot or today or datetime.now(BEIJING).date().isoformat())[:10]
    db.execute("""DELETE FROM sync_runs
      WHERE id NOT IN (SELECT id FROM sync_runs ORDER BY id DESC LIMIT ?)
      AND status!='running'
      AND NOT (run_source='auto' AND substr(COALESCE(scheduled_slot,''),1,10)=?)""", (keep, today))


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
    yield
    stop_scheduler()
    _stop_auto_sync_scheduler()


app = FastAPI(title="oPanel", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS, check_dir=False), name="frontend-assets")
app.include_router(analytics_router)


def _secret():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "session_secret"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip().encode()


def _token(csrf):
    expires = str(int(time.time()) + 86400)
    value = f"{expires}.{csrf}"
    signature = hmac.new(_secret(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def _authenticated(request):
    try:
        expires, csrf, signature = request.cookies.get("session", "").split(".", 2)
        expected = hmac.new(_secret(), f"{expires}.{csrf}".encode(), hashlib.sha256).hexdigest()
        return int(expires) > time.time() and hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False


def _is_ozon_webhook_path(path):
    parts = path.split("/")
    return len(parts) == 5 and parts[:4] == ["", "api", "webhooks", "ozon"] and bool(parts[4])


@app.middleware("http")
async def protect_api(request: Request, call_next):
    public = {"/api/login", "/api/session"}
    webhook = _is_ozon_webhook_path(request.url.path)
    if request.url.path.startswith("/api/") and request.url.path not in public and not webhook and not _authenticated(request):
        return Response(json.dumps({"detail": "未登录"}, ensure_ascii=False), 401, media_type="application/json")
    if (request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path != "/api/login" and not webhook
            and request.url.path.startswith("/api/")):
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


@app.get("/api/session")
def session(request: Request):
    authenticated = _authenticated(request)
    csrf = request.cookies.get("session", "").split(".", 2)[1] if authenticated else ""
    return {"authenticated": authenticated, "csrf_token": csrf}


def _client_ip(request):
    headers = {str(key).lower(): value for key, value in request.headers.items()}
    for header in ("cf-connecting-ip", "x-forwarded-for"):
        for value in str(headers.get(header) or "").split(","):
            try:
                return str(ipaddress.ip_address(value.strip()))
            except ValueError:
                continue
    host = request.client.host if request.client else None
    return str(host).strip() if host else "unknown"


@app.post("/api/login")
async def login(request: Request, response: Response):
    values = _env()
    salt, expected = values.get("ADMIN_PASSWORD_SALT"), values.get("ADMIN_PASSWORD_HASH")
    if not salt or not expected:
        raise HTTPException(503, "服务器尚未设置管理员密码哈希")
    key = _client_ip(request)
    if login_limited(key):
        raise HTTPException(429, "登录失败次数过多，请5分钟后重试")
    body = await request.json()
    if not password_matches(str(body.get("password", "")), salt, expected):
        record_login_failure(key)
        raise HTTPException(401, "密码错误")
    clear_login_failures(key)
    csrf = secrets.token_urlsafe(24)
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie("session", _token(csrf), httponly=True, secure=secure,
                        samesite="strict", max_age=86400)
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("session", path="/", httponly=True, samesite="strict")
    return {"ok": True}


@app.get("/api/shops")
def shops():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT id,name FROM shops ORDER BY id")]


@app.put("/api/shops")
async def update_shops(request: Request):
    body = await request.json()
    names = [str(body.get(str(i), "")).strip() for i in (1, 2)]
    if not all(names):
        raise HTTPException(400, "店铺名称不能为空")
    if names[0] == names[1]:
        raise HTTPException(400, "两个店铺名称不能相同")
    with transaction() as db:
        db.execute("UPDATE shops SET name=? WHERE id=1", (names[0],))
        db.execute("UPDATE shops SET name=? WHERE id=2", (names[1],))
    return {"ok": True}


@app.post("/api/ozon/probe/{shop_id}")
async def ozon_probe(shop_id: int):
    if shop_id not in (1, 2):
        raise HTTPException(404, "店铺不存在")
    try:
        return await run_in_threadpool(probe_shop, shop_id)
    except Exception as error:
        return {"valid": False, "error": str(error)[:200], "roles": [], "permissions": {}}


WEBHOOK_MAX_BODY_BYTES = 1024 * 1024


def _webhook_shop_id(secret):
    values = _env()
    matches = []
    for shop_id in (1, 2):
        expected = str(values.get(f"OZON_WEBHOOK_SECRET_{shop_id}") or "")
        if expected and hmac.compare_digest(str(secret), expected):
            matches.append(shop_id)
    if len(matches) != 1:
        raise HTTPException(403, "Webhook密钥无效")
    return matches[0]


def _validate_webhook_seller(shop_id, payload):
    if "seller_id" not in payload or payload["seller_id"] in (None, ""):
        return
    values = _env()
    expected = values.get(f"SHOP_{shop_id}_OZON_SELLER_ID") or values.get(f"SHOP_{shop_id}_OZON_CLIENT_ID")
    if not expected or str(payload["seller_id"]).strip() != str(expected).strip():
        raise HTTPException(403, "Webhook店铺身份无效")


async def _read_webhook_json(request):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > WEBHOOK_MAX_BODY_BYTES:
                raise HTTPException(413, "Webhook请求体过大")
        except ValueError as error:
            raise HTTPException(400, "Content-Length无效") from error
    chunks, size = [], 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > WEBHOOK_MAX_BODY_BYTES:
                raise HTTPException(413, "Webhook请求体过大")
            chunks.append(chunk)
        raw = b"".join(chunks)
    except AttributeError:
        raw = await request.body()
        if len(raw) > WEBHOOK_MAX_BODY_BYTES:
            raise HTTPException(413, "Webhook请求体过大")
    try:
        payload = json.loads(raw.decode("utf-8"), parse_constant=_invalid_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(400, "Webhook JSON无效") from error
    if not isinstance(payload, dict):
        raise HTTPException(400, "Webhook JSON必须是对象")
    return payload


def _invalid_json_constant(value):
    raise ValueError(f"非法 JSON 常量: {value}")


@app.post("/api/webhooks/ozon/{secret}")
async def ozon_webhook(secret: str, request: Request):
    shop_id = _webhook_shop_id(secret)
    payload = await _read_webhook_json(request)
    _validate_webhook_seller(shop_id, payload)
    message_type = str(payload.get("message_type") or "").strip()
    if message_type == "TYPE_PING":
        return {"version": "1.0.0", "name": "oPanel", "time": _utc_text(datetime.now(timezone.utc))}
    error = webhook_validation_error(payload)
    if error:
        raise HTTPException(400, error)
    process_webhook_event(shop_id, payload, _utc_text(datetime.now(timezone.utc)))
    return {"result": True}


def _admin_shop(body):
    try:
        shop_id = int(body.get("shop_id"))
    except (AttributeError, TypeError, ValueError) as error:
        raise HTTPException(400, "shop_id无效") from error
    if shop_id not in (1, 2):
        raise HTTPException(400, "未知店铺")
    return shop_id


def _performance_shop_id(value):
    text = str(value or "").strip().lower()
    if text in ("1", "shop_1"):
        return 1
    if text in ("2", "shop_2"):
        return 2
    raise HTTPException(400, "请选择有效店铺")


async def _ozon_management_call(function, *args):
    try:
        return await run_in_threadpool(function, *args)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/api/ozon/notifications/push-types")
async def ozon_push_types(shop_id: int):
    if shop_id not in (1, 2):
        raise HTTPException(400, "未知店铺")
    return await _ozon_management_call(push_type_list, shop_id)


@app.post("/api/ozon/notifications/check")
async def ozon_notification_check(request: Request):
    body = await request.json()
    shop_id = _admin_shop(body)
    url = str(body.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "url不能为空")
    return await _ozon_management_call(notification_check, shop_id, url)


@app.post("/api/ozon/notifications/set")
async def ozon_notification_set(request: Request):
    body = await request.json()
    shop_id = _admin_shop(body)
    url = str(body.get("url") or "").strip()
    types = body.get("types") or PUSH_EVENT_TYPES
    if not url or not isinstance(types, (list, tuple)) or not all(isinstance(value, str) and value for value in types):
        raise HTTPException(400, "url或types无效")
    return await _ozon_management_call(notification_set, shop_id, url, types)


@app.post("/api/ozon/notifications/list")
async def ozon_notification_list(request: Request):
    return await _ozon_management_call(notification_list, _admin_shop(await request.json()))


@app.post("/api/ozon/notifications/enable")
async def ozon_notification_enable(request: Request):
    body = await request.json()
    shop_id = _admin_shop(body)
    try:
        notification_id = int(body.get("id"))
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "通知ID无效") from error
    if "enabled" not in body and "enable" not in body:
        raise HTTPException(400, "缺少 enabled")
    return await _ozon_management_call(notification_enable, shop_id, notification_id,
                                       bool(body.get("enabled", body.get("enable"))))


@app.post("/api/ozon/notifications/delete")
async def ozon_notification_delete(request: Request):
    body = await request.json()
    shop_id = _admin_shop(body)
    try:
        notification_id = int(body.get("id"))
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "通知ID无效") from error
    return await _ozon_management_call(notification_delete, shop_id, notification_id)


def _dingtalk_settings():
    with connect() as db:
        row = dict(db.execute("SELECT * FROM notification_settings WHERE id=1").fetchone())
        last = db.execute("""SELECT stats_date,status,attempted_at,sent_at,error FROM notification_runs
          WHERE kind='daily' ORDER BY attempted_at DESC LIMIT 1""").fetchone()
    row["daily_enabled"] = bool(row["daily_enabled"])
    row["weekdays"] = [int(value) for value in row["weekdays"].split(",") if value]
    row["configured"] = dingtalk_configured()
    row["last_run"] = dict(last) if last else None
    row["next_push_at"] = next_push_time(row)
    row.pop("template", None)
    return row


@app.get("/api/dingtalk/settings")
def dingtalk_settings():
    return _dingtalk_settings()


def _alert_shop_id(value=0):
    try:
        shop_id = int(value)
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "shop_id无效") from error
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    return shop_id


@app.get("/api/alerts")
def alerts(shop_id: int = 0, status: str = "open", severity: str = "", rule_key: str = "",
           category: str = "", q: str = "", page: int = 1, size: int = 50):
    try:
        return list_alert_events(_alert_shop_id(shop_id), status, severity, rule_key, q, page, size, category)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.get("/api/alerts/summary")
def alerts_summary(shop_id: int = 0):
    try:
        return alert_summary(_alert_shop_id(shop_id))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/alerts/evaluate")
async def alerts_evaluate(request: Request):
    body = await request.json()
    try:
        shop_id = _alert_shop_id((body or {}).get("shop_id", 0))
        return await run_in_threadpool(evaluate_alerts, shop_id)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.post("/api/alerts/{alert_id}/acknowledge")
def alert_acknowledge(alert_id: int):
    try:
        return acknowledge_alert(alert_id)
    except (LookupError, ValueError) as error:
        raise HTTPException(404 if isinstance(error, LookupError) else 400, str(error)) from error


@app.get("/api/alert-rules")
def alert_rules(shop_id: int = 0):
    try:
        return get_alert_rules(_alert_shop_id(shop_id))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.put("/api/alert-rules/{rule_key}")
async def alert_rule_update(rule_key: str, request: Request):
    try:
        return update_alert_rule(rule_key, await request.json())
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.put("/api/dingtalk/settings")
async def update_dingtalk_settings(request: Request):
    body = await request.json()
    updates, args = [], []
    schedule_keys = {"daily_enabled", "push_time", "weekdays"}
    if schedule_keys & body.keys():
        if not schedule_keys <= body.keys():
            raise HTTPException(400, "请完整提交汇总开关、时间和星期")
        push_time = str(body.get("push_time", "")).strip()
        try:
            push_time = datetime.strptime(push_time, "%H:%M").strftime("%H:%M")
            weekdays = sorted({int(value) for value in body.get("weekdays", [])})
        except (TypeError, ValueError) as error:
            raise HTTPException(400, "钉钉推送时间或星期无效") from error
        if any(value not in range(1, 8) for value in weekdays):
            raise HTTPException(400, "钉钉推送星期无效")
        enabled = bool(body.get("daily_enabled"))
        if enabled and not weekdays:
            raise HTTPException(400, "启用昨日汇总时至少选择一天")
        updates.extend(("daily_enabled=?", "push_time=?", "weekdays=?"))
        args.extend((int(enabled), push_time, ",".join(map(str, weekdays))))
    if not updates:
        raise HTTPException(400, "没有可保存的设置")
    with transaction() as db:
        db.execute(f"UPDATE notification_settings SET {','.join(updates)} WHERE id=1", args)
    return _dingtalk_settings()


def _shop_clause(shop_id):
    return (" AND o.shop_id=?", [shop_id]) if shop_id in (1, 2) else ("", [])


def _record_clause(shop_id, alias="r"):
    return (f" WHERE {alias}.shop_id=?", [shop_id]) if shop_id in (1, 2) else ("", [])


def _paging(page, size):
    return max(page, 1), min(max(size, 1), 100)


def _months_before(value, months=3):
    month = value.month - months - 1
    year, month = value.year + month // 12, month % 12 + 1
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    return date(year, month, min(value.day, (next_month - timedelta(days=1)).day))


def _overview_range(date_from=None, date_to=None, now=None):
    today = (now or datetime.now(BEIJING)).date()
    try:
        end = date.fromisoformat(date_to) if date_to else today
        start = date.fromisoformat(date_from) if date_from else _months_before(end)
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "日期格式必须为 YYYY-MM-DD") from error
    if start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    utc_start = datetime.combine(start, datetime.min.time(), BEIJING).astimezone(timezone.utc)
    utc_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), BEIJING).astimezone(timezone.utc)
    return start, end, utc_start.isoformat().replace("+00:00", "Z"), utc_end.isoformat().replace("+00:00", "Z")


def _compensation_pair(body, amount_key, time_key):
    amount, compensated_at = body.get(amount_key), str(body.get(time_key) or "").strip()
    if (amount in (None, "")) != (not compensated_at):
        raise HTTPException(400, "赔偿金额和赔偿时间必须同时填写")
    if amount in (None, ""):
        return None, None
    try:
        value = Decimal(str(amount))
        if value <= 0:
            raise InvalidOperation
        moment = datetime.fromisoformat(compensated_at.replace("Z", "+00:00"))
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(400, "赔偿金额必须大于0，且赔偿时间必须有效") from error
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BEIJING)
    return str(value), _utc_text(moment)


def _utc_text(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _with_compensation_conversion(db, row):
    target = row.get("settlement_currency")
    for prefix, amount_key, time_key, source in (
        ("platform_compensation", "platform_compensation_rub", "platform_compensated_at", "RUB"),
        ("logistics_compensation", "logistics_compensation_cny", "logistics_compensated_at", "CNY"),
    ):
        result = convert_compensation(db, row.get(amount_key), row.get(time_key), source, target)
        row[f"{prefix}_original_currency"] = source
        row[f"{prefix}_converted_amount"] = result["converted_amount"]
        row[f"{prefix}_converted_currency"] = result["converted_currency"]
        row[f"{prefix}_base_rates"] = result["base_rates"]
        row[f"{prefix}_missing_rate"] = result["missing_rate"]
        moment = _utc_moment(row.get(time_key))
        row[f"{time_key}_beijing"] = moment.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M") if moment else None
    return row


def _bucket_start(value, granularity):
    if granularity == "week":
        return value - timedelta(days=value.weekday())
    if granularity == "month":
        return value.replace(day=1)
    return value


def _next_bucket(value, granularity):
    if granularity == "day":
        return value + timedelta(days=1)
    if granularity == "week":
        return value + timedelta(days=7)
    return date(value.year + (value.month == 12), value.month % 12 + 1, 1)


def _beijing_date(value):
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(BEIJING).date()


def _group_by_bucket_and_channel(rows, granularity):
    grouped = {}
    for row in rows:
        key = _bucket_start(_beijing_date(row["created_at"]), granularity)
        bucket = grouped.setdefault(key, {"rows": [], "channels": {}})
        bucket["rows"].append(row)
        bucket["channels"].setdefault(row["channel"], []).append(row)
    return grouped


def _gmv_summary(rows, shop_id, rate_periods=()):
    currency = "USD" if shop_id == 1 else "CNY"
    amount = Decimal("0")
    missing = 0
    for row in rows:
        value = row["amount_original"] if row["amount_original"] is not None else row["item_amount"]
        value_currency = (row["amount_currency"] or row["item_currency"] or
                          row["settlement_currency"] or "").upper()
        if value is None:
            continue
        value = Decimal(str(value))
        if shop_id:
            if value_currency == currency:
                amount += value
        elif value_currency == "CNY":
            amount += value
        elif value_currency == "USD":
            rates = rates_for_order(rate_periods, row["created_at"])
            if not rates or not rates.get("USD") or not rates.get("CNY"):
                missing += 1
            else:
                amount += value * rates["USD"] / rates["CNY"]
    return {"amount": float(amount.quantize(Decimal("0.01"))), "currency": currency if shop_id else "CNY",
            "missing_rate_orders": missing}


def _overview_timeliness(rows):
    grouped = {channel: {"ship": [], "delivery": []} for channel in ("FBP", "realFBS", "WHD")}
    for row in rows:
        delivered_at = row["delivered_at"]
        if row["channel"] in ("FBP", "realFBS") and delivered_at == row["shipped_at"]:
            delivered_at = None
        ship = _duration_hours(row["created_at"], row["shipped_at"])
        delivery = _duration_hours(row["shipped_at"], delivered_at)
        if ship is not None:
            grouped[row["channel"]]["ship"].append(ship)
        if delivery is not None:
            grouped[row["channel"]]["delivery"].append(delivery)
    return [{"channel": channel,
             "ship_samples": len(values["ship"]),
             "delivery_samples": len(values["delivery"]),
             "p50_ship_hours": _percentile(values["ship"], .5),
             "p50_delivery_hours": _percentile(values["delivery"], .5),
             "p90_delivery_hours": _percentile(values["delivery"], .9),
             "ship_sample_insufficient": len(values["ship"]) < 30,
             "delivery_sample_insufficient": len(values["delivery"]) < 30}
            for channel, values in grouped.items()]


def _overview_top_products(db, utc_start, utc_end, shop_id):
    clause, shop_args = _shop_clause(shop_id)
    rows = db.execute(f"""SELECT o.shop_id,o.posting_number,o.status_raw,o.shipped,
      i.sku,i.offer_id,i.product_name_raw,i.quantity
      FROM orders o JOIN order_items i USING(shop_id,posting_number)
      WHERE {ACTIVE} AND o.created_at>=?
        AND o.created_at<? {clause}""", [utc_start, utc_end] + shop_args)
    rules = load_product_rules(db)
    products = {}
    for row in rows:
        resolved = resolve_product(rules, row["sku"], row["offer_id"], row["product_name_raw"])
        key = row["shop_id"], resolved["identity"]
        item = products.setdefault(key, {"name": resolved["display_name"],
                                         "pieces": 0, "orders": set(), "cancelled": set()})
        item["pieces"] += row["quantity"]
        posting = row["shop_id"], row["posting_number"]
        item["orders"].add(posting)
        if row["status_raw"] == "已取消" and row["shipped"] == 1:
            item["cancelled"].add(posting)
    result = [{"name": item["name"], "pieces": item["pieces"], "orders": len(item["orders"]),
               "cancel_rate": len(item["cancelled"]) / len(item["orders"])}
              for item in products.values()]
    return sorted(result, key=lambda item: (-item["pieces"], -item["orders"], item["name"]))[:5]


@app.get("/api/summary")
def summary(shop_id: int = 0,
            date_from: Annotated[str | None, Query(alias="from")] = None,
            date_to: Annotated[str | None, Query(alias="to")] = None,
            granularity: str = "week"):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    if granularity not in ("day", "week", "month"):
        raise HTTPException(400, "granularity 必须为 day、week 或 month")
    start, end, utc_start, utc_end = _overview_range(date_from, date_to)
    clause, shop_args = _shop_clause(shop_id)
    args = [utc_start, utc_end] + shop_args
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,o.posting_number,o.channel,o.created_at,o.status_raw,o.shipped,
            o.shipped_at,o.delivered_at,o.data_anomaly,
            o.amount_original,o.amount_currency,s.settlement_currency,
            COALESCE(SUM(i.quantity),0) pieces,
            CASE WHEN o.amount_original IS NULL AND COUNT(i.sku)>0
              AND COUNT(i.unit_price)=COUNT(i.sku) AND COUNT(DISTINCT i.price_currency)=1
              THEN SUM(i.unit_price*i.quantity) END item_amount,
            CASE WHEN COUNT(DISTINCT i.price_currency)=1 THEN MIN(i.price_currency) END item_currency
          FROM orders o JOIN shops s ON s.id=o.shop_id
          LEFT JOIN order_items i USING(shop_id,posting_number)
          WHERE {ACTIVE} AND o.created_at>=?
            AND o.created_at<? {clause}
          GROUP BY o.shop_id,o.posting_number
          ORDER BY o.created_at
        """, args)]
        top_products = _overview_top_products(db, utc_start, utc_end, shop_id)
        rate_periods = load_base_rate_periods(db, utc_start, utc_end) if shop_id == 0 else []
    totals = {"orders": 0, "pieces": 0, "cancelled_orders": 0, "cancelled_pieces": 0}
    channels_by_name = {channel: {"channel": channel, "orders": 0, "pieces": 0, "cancelled_pieces": 0}
                        for channel in ("FBP", "realFBS", "WHD")}
    for row in rows:
        totals["orders"] += 1
        totals["pieces"] += row["pieces"]
        cancelled = row["status_raw"] == "已取消" and row["shipped"] == 1
        if cancelled:
            totals["cancelled_orders"] += 1
            totals["cancelled_pieces"] += row["pieces"]
        channel = channels_by_name.get(row["channel"])
        if channel is not None:
            channel["orders"] += 1
            channel["pieces"] += row["pieces"]
            if cancelled:
                channel["cancelled_pieces"] += row["pieces"]
    totals["cancel_rate"] = totals["cancelled_pieces"] / totals["pieces"] if totals["pieces"] else 0
    channels = list(channels_by_name.values())
    bucket_dates = []
    cursor = _bucket_start(start, granularity)
    while cursor <= end:
        bucket_dates.append(cursor)
        cursor = _next_bucket(cursor, granularity)
    grouped_rows = _group_by_bucket_and_channel(rows, granularity)
    buckets = []
    for bucket_date in bucket_dates:
        next_date = _next_bucket(bucket_date, granularity)
        bucket = grouped_rows.get(bucket_date, {"rows": [], "channels": {}})
        bucket_rows = bucket["rows"]
        channel_values = {}
        for channel in ("FBP", "realFBS", "WHD"):
            values = bucket["channels"].get(channel, [])
            channel_values[channel] = {"orders": len(values), "gmv": _gmv_summary(values, shop_id, rate_periods)}
        buckets.append({"key": bucket_date.isoformat(),
                        "from": max(bucket_date, start).isoformat(),
                        "to": min(next_date - timedelta(days=1), end).isoformat(),
                        "orders": len(bucket_rows), "gmv": _gmv_summary(bucket_rows, shop_id, rate_periods),
                        "channels": channel_values})
    return {"range": {"from": start.isoformat(), "to": end.isoformat()},
            "granularity": granularity, "totals": totals, "channels": channels,
            "buckets": buckets, "gmv": _gmv_summary(rows, shop_id, rate_periods),
            "timeliness": _overview_timeliness(rows), "top_products": top_products,
            "data_through": max((row["created_at"] for row in rows), default=None)}


def _trend_range(granularity: str, now: datetime | None = None):
    today = (now or datetime.now(BEIJING)).date()
    if granularity == "day":
        start = today - timedelta(days=89)
        end = today
    elif granularity == "week":
        cur_week = _bucket_start(today, "week")
        start = cur_week - timedelta(weeks=11)
        end = cur_week + timedelta(days=6)
    else:
        cur_month = today.replace(day=1)
        year = cur_month.year
        month = cur_month.month - 11
        if month <= 0:
            year -= 1
            month += 12
        start = date(year, month, 1)
        next_m = _next_bucket(cur_month, "month")
        end = next_m - timedelta(days=1)
    utc_start = datetime.combine(start, datetime.min.time(), BEIJING).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    utc_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), BEIJING).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return start, end, utc_start, utc_end


@app.get("/api/order-trend")
def order_trend(shop_id: int = 0, granularity: str = "day"):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    if granularity not in ("day", "week", "month"):
        raise HTTPException(400, "granularity 必须为 day、week 或 month")
    start, end, utc_start, utc_end = _trend_range(granularity)
    clause, shop_args = _shop_clause(shop_id)
    args = [utc_start, utc_end] + shop_args
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,o.posting_number,o.channel,o.created_at,o.status_raw,o.shipped,
            o.amount_original,o.amount_currency,s.settlement_currency,
            COALESCE(SUM(i.quantity),0) pieces,
            CASE WHEN o.amount_original IS NULL AND COUNT(i.sku)>0
              AND COUNT(i.unit_price)=COUNT(i.sku) AND COUNT(DISTINCT i.price_currency)=1
              THEN SUM(i.unit_price*i.quantity) END item_amount,
            CASE WHEN COUNT(DISTINCT i.price_currency)=1 THEN MIN(i.price_currency) END item_currency
          FROM orders o JOIN shops s ON s.id=o.shop_id
          LEFT JOIN order_items i USING(shop_id,posting_number)
          WHERE {ACTIVE} AND o.created_at>=?
            AND o.created_at<? {clause}
          GROUP BY o.shop_id,o.posting_number
          ORDER BY o.created_at
        """, args)]
        rate_periods = load_base_rate_periods(db, utc_start, utc_end) if shop_id == 0 else []
    bucket_dates = []
    cursor = _bucket_start(start, granularity)
    while cursor <= end:
        bucket_dates.append(cursor)
        cursor = _next_bucket(cursor, granularity)
    grouped_rows = _group_by_bucket_and_channel(rows, granularity)
    buckets = []
    for bucket_date in bucket_dates:
        next_date = _next_bucket(bucket_date, granularity)
        bucket = grouped_rows.get(bucket_date, {"rows": [], "channels": {}})
        bucket_rows = bucket["rows"]
        channel_values = {}
        for channel in ("FBP", "realFBS", "WHD"):
            values = bucket["channels"].get(channel, [])
            channel_values[channel] = {"orders": len(values), "gmv": _gmv_summary(values, shop_id, rate_periods)}
        buckets.append({"key": bucket_date.isoformat(),
                        "from": max(bucket_date, start).isoformat(),
                        "to": min(next_date - timedelta(days=1), end).isoformat(),
                        "orders": len(bucket_rows), "gmv": _gmv_summary(bucket_rows, shop_id, rate_periods),
                        "channels": channel_values})
    return {"granularity": granularity, "from": start.isoformat(), "to": end.isoformat(), "buckets": buckets}


def _translated_order(row):
    order = dict(row)
    order["status_raw"] = STATUS_ZH.get(order["status_raw"], order["status_raw"])
    order["cancel_reason_raw"] = CANCEL_REASON_ZH.get(order["cancel_reason_raw"], order["cancel_reason_raw"])
    return order


@app.get("/api/orders")
def orders(shop_id: int = 0, channel: str = "", q: str = "", page: int = 1, size: int = 30,
           date_from: Annotated[str | None, Query(alias="from")] = None,
           date_to: Annotated[str | None, Query(alias="to")] = None,
           status: str = ""):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    where, args = ["o.created_at>=?", "o.created_at<?"], [utc_start, utc_end]
    if shop_id in (1, 2):
        where.append("o.shop_id=?"); args.append(shop_id)
    if channel:
        if channel not in CHANNELS: raise HTTPException(400, "未知渠道")
        where.append("o.channel=?"); args.append(channel)
    if q:
        where.append("(o.posting_number LIKE ? OR EXISTS(SELECT 1 FROM order_items x WHERE x.shop_id=o.shop_id AND x.posting_number=o.posting_number AND (x.sku LIKE ? OR x.offer_id LIKE ? OR x.product_name_raw LIKE ?)))")
        args.extend([f"%{q}%"] * 4)

    base_where_sql = " AND ".join(where)
    base_args = list(args)

    if status == "pending":
        where.append("o.status_raw IN ('待备货', '等待发运', '待发货', 'awaiting_packaging', 'awaiting_deliver')")
    elif status == "shipping":
        where.append("o.status_raw IN ('运输中', 'delivering', 'driver_pickup')")
    elif status == "delivered":
        where.append("o.status_raw IN ('已签收', 'delivered')")
    elif status == "cancelled":
        where.append("o.status_raw IN ('已取消', 'cancelled')")
    elif status == "cancelled_shipped":
        where.append("o.status_raw IN ('已取消', 'cancelled') AND o.shipped=1")
    elif status == "anomaly":
        where.append("o.data_anomaly=1")

    page, size = max(page, 1), min(max(size, 1), 100)
    sql_where = " AND ".join(where)
    with connect() as db:
        rules = load_product_rules(db)
        total = db.execute(f"SELECT COUNT(*) FROM orders o WHERE {sql_where}", args).fetchone()[0]

        # Calculate status breakdown for chips
        count_rows = db.execute(f"""
          SELECT o.status_raw, o.shipped, o.data_anomaly, COUNT(*) c
          FROM orders o WHERE {base_where_sql}
          GROUP BY o.status_raw, o.shipped, o.data_anomaly
        """, base_args).fetchall()
        status_counts = {"all": 0, "pending": 0, "shipping": 0, "delivered": 0, "cancelled": 0, "cancelled_shipped": 0, "anomaly": 0}
        for r in count_rows:
            raw, shipped, anomaly, cnt = r["status_raw"], r["shipped"], r["data_anomaly"], r["c"]
            status_counts["all"] += cnt
            if anomaly:
                status_counts["anomaly"] += cnt
            if raw in ("待备货", "等待发运", "待发货", "awaiting_packaging", "awaiting_deliver"):
                status_counts["pending"] += cnt
            elif raw in ("运输中", "delivering", "driver_pickup"):
                status_counts["shipping"] += cnt
            elif raw in ("已签收", "delivered"):
                status_counts["delivered"] += cnt
            elif raw in ("已取消", "cancelled"):
                status_counts["cancelled"] += cnt
                if shipped:
                    status_counts["cancelled_shipped"] += cnt

        result = [_translated_order(row) for row in db.execute(f"""
          SELECT o.shop_id,s.name shop_name,o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at,
            o.status_raw,o.cancel_reason_raw,o.shipped,o.data_anomaly,o.amount_original,o.amount_currency
          FROM orders o JOIN shops s ON s.id=o.shop_id
          WHERE {sql_where} ORDER BY o.created_at DESC LIMIT ? OFFSET ?
        """, args + [size, (page - 1) * size])]
        items = {}
        if result:
            marks = ",".join("(?,?)" for _ in result)
            keys = [value for order in result for value in (order["shop_id"], order["posting_number"])]
            for row in db.execute(f"""SELECT shop_id,posting_number,sku,offer_id,product_name_raw,
              product_name_raw product_name_original,quantity,unit_price,price_currency FROM order_items
              WHERE (shop_id,posting_number) IN ({marks}) ORDER BY shop_id,posting_number,sku""", keys):
                items.setdefault((row["shop_id"], row["posting_number"]), []).append(dict(row))
        for order in result:
            order["items"] = items.get((order["shop_id"], order["posting_number"]), [])
            for item in order["items"]:
                item["product_name_raw"] = resolve_product(
                    rules, item["sku"], item["offer_id"], item["product_name_original"])["display_name"]
            order["sku_types"] = len(order["items"])
            order["pieces"] = sum(item["quantity"] for item in order["items"])
    return {"items": result, "total": total, "page": page, "size": size, "status_counts": status_counts}


@app.get("/api/risk")
def risk(shop_id: int = 0, grouped: bool = False,
         date_from: Annotated[str | None, Query(alias="from")] = None,
         date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    start, end, utc_start, utc_end = _overview_range(date_from, date_to)
    clause, args = _shop_clause(shop_id)
    unclaimed = ",".join("?" for _ in BUYER_UNCLAIMED_REASONS)
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,s.name shop_name,o.channel,i.sku,i.offer_id,i.product_name_raw,
            SUM(i.quantity) valid_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 THEN i.quantity ELSE 0 END) cancelled_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 AND o.cancel_reason_raw IN ({unclaimed}) THEN i.quantity ELSE 0 END) unclaimed_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 AND o.cancel_reason_raw='Отправление не прошло таможенное оформление' THEN i.quantity ELSE 0 END) customs_pieces
          FROM orders o JOIN shops s ON s.id=o.shop_id JOIN order_items i USING(shop_id,posting_number)
          WHERE {ACTIVE} AND o.created_at>=?
            AND o.created_at<?{clause}
          GROUP BY o.shop_id,o.channel,i.sku,i.offer_id,i.product_name_raw
        """, [*BUYER_UNCLAIMED_REASONS, utc_start, utc_end, *args])]
        rules = load_product_rules(db)

    for row in rows:
        row["resolved"] = resolve_product(rules, row["sku"], row["offer_id"], row["product_name_raw"])
        row["item_key"] = row["resolved"]["identity"]

    def stats(values):
        result = {key: sum(int(row[f"{key}_pieces"] or 0) for row in values)
                  for key in ("valid", "cancelled", "unclaimed", "customs")}
        for key in ("cancelled", "unclaimed", "customs"):
            result[f"{key}_rate"] = result[key] / result["valid"] if result["valid"] else None
        return result

    grouped = {}
    for row in rows:
        item = grouped.setdefault((row["shop_id"], row["item_key"]), {"rows": [], "channels": {}})
        item["rows"].append(row)
        item["channels"].setdefault(row["channel"], []).append(row)

    items = []
    for item_key in sorted(grouped):
        group = grouped[item_key]
        values = group["rows"]
        skus = sorted({row["sku"] for row in values if row["sku"]})
        offers = sorted({row["offer_id"] for row in values if row["offer_id"]})
        resolved = values[0]["resolved"]
        items.append({"shop_id": values[0]["shop_id"], "shop_name": values[0]["shop_name"],
                      "item_key": item_key[1], "sku": skus[0] if len(skus) == 1 else "、".join(skus),
                      "primary_offer_id": resolved["primary_offer_id"], "member_count": len(skus),
                      "product_name": resolved["display_name"],
                      "search_text": " ".join(skus + offers + [resolved["display_name"]] +
                                                [row["product_name_raw"] or "" for row in values]),
                      "total": stats(values),
                      "channels": {channel: stats(group["channels"][channel])
                                   if channel in group["channels"] else None
                                   for channel in ("FBP", "realFBS", "WHD")}})
    items.sort(key=lambda row: (-row["total"]["cancelled"], -row["total"]["valid"],
                                row["shop_id"], row["item_key"]))
    return {"range": {"from": start.isoformat(), "to": end.isoformat()}, "summary": stats(rows),
            "items": items}


@app.get("/api/risk/reasons")
def risk_reasons(shop_id: int = 0, reason: str = "",
                 date_from: Annotated[str | None, Query(alias="from")] = None,
                 date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    start, end, utc_start, utc_end = _overview_range(date_from, date_to)
    clause, args = _shop_clause(shop_id)
    extra = ""
    if reason:
        extra = " AND COALESCE(NULLIF(o.cancel_reason_raw,''),'原因暂缺')=?"; args.append(reason)
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,o.channel,
          COALESCE(NULLIF(o.cancel_reason_raw,''),'原因暂缺') reason_raw,
          COUNT(DISTINCT o.posting_number) orders,SUM(i.quantity) pieces
          FROM orders o JOIN shops s ON s.id=o.shop_id JOIN order_items i USING(shop_id,posting_number)
          WHERE o.status_raw='已取消' AND o.shipped=1 AND o.created_at>=?
            AND o.created_at<?{clause}{extra}
          GROUP BY o.shop_id,o.channel,reason_raw ORDER BY pieces DESC""", [utc_start, utc_end, *args])]
        details = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,o.channel,
          o.posting_number,SUM(i.quantity) pieces FROM orders o JOIN shops s ON s.id=o.shop_id
          JOIN order_items i USING(shop_id,posting_number)
          WHERE o.status_raw='已取消' AND o.shipped=1 AND o.created_at>=?
            AND o.created_at<?{clause}{extra}
          GROUP BY o.shop_id,o.channel,o.posting_number ORDER BY o.posting_number""",
          [utc_start, utc_end, *args])] if reason else []
    grouped = {}
    for row in rows:
        reason = grouped.setdefault(row["reason_raw"], {"rows": [], "channels": {}})
        reason["rows"].append(row)
        reason["channels"].setdefault(row["channel"], []).append(row)

    items = []
    for reason_raw in sorted(grouped):
        group = grouped[reason_raw]
        values = group["rows"]
        items.append({"reason_raw": reason_raw,
                      "reason_name": RISK_REASON_ZH.get(reason_raw, reason_raw),
                      "total": {"orders": sum(row["orders"] for row in values),
                                "pieces": sum(row["pieces"] for row in values)},
                      "channels": {channel: {"orders": sum(row["orders"] for row in group["channels"].get(channel, [])),
                                             "pieces": sum(row["pieces"] for row in group["channels"].get(channel, []))}
                                   for channel in ("FBP", "realFBS", "WHD")}})
    items.sort(key=lambda row: (-row["total"]["pieces"], row["reason_raw"]))
    return {"range": {"from": start.isoformat(), "to": end.isoformat()},
            "items": items, "details": details}


def _percentile(values, fraction):
    if not values:
        return None
    if fraction == .5:
        return statistics.median(values)
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=10, method="inclusive")[8]


def _utc_moment(value):
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _complaint_deadline(primary_time, fallback_time=None, now=None):
    moment = _utc_moment(primary_time) or _utc_moment(fallback_time)
    if not moment:
        return {"complaint_deadline": None, "complaint_deadline_status": "missing"}
    deadline = moment.astimezone(BEIJING).date() + timedelta(days=30)
    if now is None:
        today = datetime.now(BEIJING).date()
    elif isinstance(now, datetime):
        today = (now if now.tzinfo else now.replace(tzinfo=BEIJING)).astimezone(BEIJING).date()
    else:
        today = now
    days = (deadline - today).days
    status = "overdue" if days < 0 else "due_today" if days == 0 else "due_soon" if days <= 7 else "normal"
    return {"complaint_deadline": deadline.isoformat(), "complaint_deadline_status": status}


def _duration_hours(start, end):
    start, end = _utc_moment(start), _utc_moment(end)
    if not start or not end or end < start:
        return None
    return (end - start).total_seconds() / 3600


@app.get("/api/timeliness")
def timeliness(shop_id: int = 0, page: int = 1, size: int = 30, q: str = "",
               date_from: Annotated[str | None, Query(alias="from")] = None,
               date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    start_date, end_date, utc_start, utc_end = _overview_range(date_from, date_to)
    clause, shop_args = _shop_clause(shop_id)
    page, size = _paging(page, size)
    base_where = f"{ACTIVE} AND o.created_at>=? AND o.created_at<?{clause}"
    base_args = [utc_start, utc_end, *shop_args]
    detail_where, detail_args = base_where, list(base_args)
    if q.strip():
        detail_where += " AND o.posting_number LIKE ?"
        detail_args.append(f"%{q.strip()}%")
    with connect() as db:
        all_rows = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,
          o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at
          FROM orders o JOIN shops s ON s.id=o.shop_id WHERE {base_where}
          ORDER BY o.created_at DESC,o.posting_number DESC""", base_args)]
        through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {base_where}", base_args).fetchone()[0]
        total = db.execute(f"SELECT COUNT(*) FROM orders o WHERE {detail_where}", detail_args).fetchone()[0]
        rows = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,
          o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at
          FROM orders o JOIN shops s ON s.id=o.shop_id WHERE {detail_where}
          ORDER BY o.created_at DESC,o.posting_number DESC LIMIT ? OFFSET ?""",
          [*detail_args, size, (page - 1) * size])]
    ship_values, delivery_values = [], []
    grouped = {}
    for row in all_rows:
        shipped_moment, delivered_moment = _utc_moment(row["shipped_at"]), _utc_moment(row["delivered_at"])
        if row["channel"] in ("FBP", "realFBS") and delivered_moment and delivered_moment == shipped_moment:
            row["delivered_at"] = None
        ship_hours = _duration_hours(row["created_at"], row["shipped_at"])
        delivery_hours = _duration_hours(row["shipped_at"], row["delivered_at"])
        if ship_hours is not None: ship_values.append(ship_hours)
        if delivery_hours is not None: delivery_values.append(delivery_hours)
        group = grouped.setdefault((row["shop_id"], row["channel"]), {
            "shop_id": row["shop_id"], "shop_name": row["shop_name"], "channel": row["channel"],
            "orders": 0, "created": 0, "shipped": 0, "delivered": 0, "ship": [], "delivery": []})
        group["orders"] += 1
        group["created"] += int(_utc_moment(row["created_at"]) is not None)
        group["shipped"] += int(_utc_moment(row["shipped_at"]) is not None)
        group["delivered"] += int(_utc_moment(row["delivered_at"]) is not None)
        if ship_hours is not None: group["ship"].append(ship_hours)
        if delivery_hours is not None: group["delivery"].append(delivery_hours)
    summary = {"orders": len(all_rows), "shipped_orders": sum(_utc_moment(row["shipped_at"]) is not None for row in all_rows),
      "delivered_orders": sum(_utc_moment(row["delivered_at"]) is not None for row in all_rows),
      "ship_samples": len(ship_values), "delivery_samples": len(delivery_values),
      "avg_ship_hours": statistics.fmean(ship_values) if ship_values else None,
      "p50_ship_hours": _percentile(ship_values, .5), "p90_ship_hours": _percentile(ship_values, .9),
      "avg_delivery_hours": statistics.fmean(delivery_values) if delivery_values else None,
      "p50_delivery_hours": _percentile(delivery_values, .5), "p90_delivery_hours": _percentile(delivery_values, .9)}
    groups = []
    for group in grouped.values():
        orders_count = group["orders"]
        groups.append({**{k: v for k, v in group.items() if k not in {"ship", "delivery"}},
          "ship_samples": len(group["ship"]), "delivery_samples": len(group["delivery"]),
          "ship_sample_insufficient": 0 < len(group["ship"]) < 30,
          "delivery_sample_insufficient": 0 < len(group["delivery"]) < 30,
          "avg_ship_hours": statistics.fmean(group["ship"]) if group["ship"] else None,
          "p50_ship_hours": _percentile(group["ship"], .5), "p90_ship_hours": _percentile(group["ship"], .9),
          "avg_delivery_hours": statistics.fmean(group["delivery"]) if group["delivery"] else None,
          "p50_delivery_hours": _percentile(group["delivery"], .5), "p90_delivery_hours": _percentile(group["delivery"], .9),
          "created_completeness": group["created"] / orders_count if orders_count else 0,
          "shipped_completeness": group["shipped"] / orders_count if orders_count else 0,
          "delivered_completeness": group["delivered"] / orders_count if orders_count else 0})
    groups.sort(key=lambda value: (value["shop_id"], {"FBP": 0, "realFBS": 1, "WHD": 2}[value["channel"]]))
    for row in rows:
        shipped_moment, delivered_moment = _utc_moment(row["shipped_at"]), _utc_moment(row["delivered_at"])
        if row["channel"] in ("FBP", "realFBS") and delivered_moment and delivered_moment == shipped_moment:
            row["delivered_at"] = None
        row["ship_hours"] = _duration_hours(row["created_at"], row["shipped_at"])
        row["delivery_hours"] = _duration_hours(row["shipped_at"], row["delivered_at"])
        row["ship_anomaly"] = bool(row["shipped_at"]) and row["ship_hours"] is None
        row["delivery_anomaly"] = bool(row["delivered_at"]) and row["delivery_hours"] is None
    return {"range": {"from": start_date.isoformat(), "to": end_date.isoformat()},
            "summary": summary, "items": rows, "total": total, "page": page, "size": size,
            "groups": groups, "data_through": through}


@app.post("/api/exception-complaints/shipping")
@app.put("/api/exception-complaints/shipping")
async def save_complaint(request: Request):
    body = await request.json()
    shop_id = int(body.get("shop_id") or 0)
    number = str(body.get("complaint_number") or "").strip()
    posting = str(body.get("posting_number") or "").strip()
    complaint_at = str(body.get("complaint_at") or "").strip()
    channel = str(body.get("channel") or "").strip()
    if shop_id not in (1, 2) or not all((number, posting, complaint_at, channel)):
        raise HTTPException(400, "店铺、订单号、投诉编号、投诉时间和渠道均为必填")
    for key in ("resolved", "package_returned"):
        if body.get(key) not in (None, True, False):
            raise HTTPException(400, "是否完结和包裹是否退回只允许未填写、是或否")
    if body.get("not_received_return") not in (None, True, False):
        raise HTTPException(400, "未收到退件只允许未填写、是或否")
    amount = body.get("compensation_amount")
    if amount not in (None, ""):
        try: amount = float(amount)
        except (TypeError, ValueError) as error: raise HTTPException(400, "赔付金额无效") from error
    else:
        amount = None
    platform_amount, platform_at = _compensation_pair(
        body, "platform_compensation_rub", "platform_compensated_at")
    logistics_amount, logistics_at = _compensation_pair(
        body, "logistics_compensation_cny", "logistics_compensated_at")
    now = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        shop = db.execute("SELECT settlement_currency FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not db.execute("SELECT 1 FROM orders WHERE shop_id=? AND posting_number=?", (shop_id, posting)).fetchone():
            raise HTTPException(400, "未找到该店铺订单")
        currency = str(body.get("compensation_currency") or (shop[0] if amount is not None else "")).upper() or None
        exists = db.execute("""SELECT created_at FROM complaints
          WHERE shop_id=? AND complaint_number=? AND posting_number=?""",
                            (shop_id, number, posting)).fetchone()
        db.execute("""INSERT INTO complaints(
          shop_id,complaint_number,posting_number,complaint_at,channel,resolved,package_returned,
          compensation_amount,compensation_currency,notes,not_received_return,warehouse,
          order_process_status,complaint_status,compensation_status,
          platform_compensation_rub,platform_compensated_at,
          logistics_compensation_cny,logistics_compensated_at,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(shop_id,complaint_number,posting_number) DO UPDATE SET
          complaint_at=excluded.complaint_at,channel=excluded.channel,
          resolved=excluded.resolved,package_returned=excluded.package_returned,
          compensation_amount=COALESCE(excluded.compensation_amount,complaints.compensation_amount),
          compensation_currency=COALESCE(excluded.compensation_currency,complaints.compensation_currency),
          notes=excluded.notes,not_received_return=excluded.not_received_return,
          warehouse=excluded.warehouse,order_process_status=excluded.order_process_status,
          complaint_status=excluded.complaint_status,compensation_status=excluded.compensation_status,
          platform_compensation_rub=excluded.platform_compensation_rub,
          platform_compensated_at=excluded.platform_compensated_at,
          logistics_compensation_cny=excluded.logistics_compensation_cny,
          logistics_compensated_at=excluded.logistics_compensated_at,updated_at=excluded.updated_at""",
          (shop_id, number, posting, complaint_at, channel,
           None if body.get("resolved") is None else int(body["resolved"]),
           None if body.get("package_returned") is None else int(body["package_returned"]),
           amount, currency, str(body.get("notes") or ""),
           None if body.get("not_received_return") is None else int(body["not_received_return"]),
           str(body.get("warehouse") or ""), str(body.get("order_process_status") or ""),
           str(body.get("complaint_status") or ""), str(body.get("compensation_status") or ""),
           platform_amount, platform_at,
           logistics_amount, logistics_at, exists[0] if exists else now, now))
    return {"ok": True}


@app.get("/api/exception-complaints/shipping")
def shipping_complaints(shop_id: int = 0, q: str = "", status: str = "", page: int = 1, size: int = 50,
                        date_from: Annotated[str | None, Query(alias="from")] = None,
                        date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    if status not in {"", "unfiled", "open", "closed"}:
        raise HTTPException(400, "投诉状态无效")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    cancelled = "o.status_raw IN ('已取消','cancelled','canceled')"
    where, args = [f"NOT ({cancelled} AND o.shipped=0)", f"(({cancelled} AND o.shipped=1) OR o.data_anomaly=1)",
                   "o.created_at>=?", "o.created_at<?"], [utc_start, utc_end]
    if shop_id:
        where.append("o.shop_id=?"); args.append(shop_id)
    if q.strip():
        pattern = f"%{q.strip()}%"
        where.append("""(o.posting_number LIKE ? OR EXISTS(SELECT 1 FROM order_items i
          WHERE i.shop_id=o.shop_id AND i.posting_number=o.posting_number
            AND (i.sku LIKE ? OR i.offer_id LIKE ?)) OR EXISTS(SELECT 1 FROM complaints c
          WHERE c.shop_id=o.shop_id AND c.posting_number=o.posting_number AND c.complaint_number LIKE ?)
          OR COALESCE(o.tracking_number,'') LIKE ?)""")
        args.extend([pattern] * 5)
    if status == "unfiled":
        where.append("NOT EXISTS(SELECT 1 FROM complaints c WHERE c.shop_id=o.shop_id AND c.posting_number=o.posting_number)")
    elif status == "open":
        where.append("EXISTS(SELECT 1 FROM complaints c WHERE c.shop_id=o.shop_id AND c.posting_number=o.posting_number AND c.resolved IS NOT 1)")
    elif status == "closed":
        where.append("EXISTS(SELECT 1 FROM complaints c WHERE c.shop_id=o.shop_id AND c.posting_number=o.posting_number) AND NOT EXISTS(SELECT 1 FROM complaints c WHERE c.shop_id=o.shop_id AND c.posting_number=o.posting_number AND c.resolved IS NOT 1)")
    sql = " AND ".join(where)
    page, size = _paging(page, size)
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM orders o WHERE {sql}", args).fetchone()[0]
        rows = [dict(row) for row in db.execute(f"""SELECT o.*,s.name shop_name,s.settlement_currency,
          COALESCE(o.tracking_number,'') tracking_number,
          (SELECT MAX(r.occurred_at) FROM return_records r
            WHERE r.shop_id=o.shop_id AND r.posting_number=o.posting_number) fallback_cancelled_at
          FROM orders o JOIN shops s ON s.id=o.shop_id WHERE {sql}
          ORDER BY o.created_at DESC LIMIT ? OFFSET ?""", args + [size, (page - 1) * size])]
        rules = load_product_rules(db)
        items, complaints_by_order = {}, {}
        if rows:
            marks = ",".join("(?,?)" for _ in rows)
            keys = [value for row in rows for value in (row["shop_id"], row["posting_number"])]
            for item in db.execute(f"""SELECT shop_id,posting_number,sku,offer_id,product_name_raw,
              quantity,unit_price,price_currency FROM order_items
              WHERE (shop_id,posting_number) IN ({marks}) ORDER BY shop_id,posting_number,sku""", keys):
                items.setdefault((item["shop_id"], item["posting_number"]), []).append(dict(item))
            for complaint in db.execute(f"""SELECT c.*,s.settlement_currency FROM complaints c
              JOIN shops s ON s.id=c.shop_id WHERE (c.shop_id,c.posting_number) IN ({marks})
              ORDER BY c.shop_id,c.posting_number,c.complaint_at DESC,c.complaint_number""", keys):
                value = _with_compensation_conversion(db, dict(complaint))
                complaints_by_order.setdefault((complaint["shop_id"], complaint["posting_number"]), []).append(value)
        for row in rows:
            row["cancelled_at"] = row["status_changed_at"] or row["fallback_cancelled_at"]
            row.update(_complaint_deadline(row["status_changed_at"], row["fallback_cancelled_at"]))
            row["cancel_reason"] = CANCEL_REASON_ZH.get(row["cancel_reason_raw"], row["cancel_reason_raw"])
            key = row["shop_id"], row["posting_number"]
            row["items"] = items.get(key, [])
            for value in row["items"]:
                value["product_name"] = resolve_product(rules, value["sku"], value["offer_id"],
                                                          value["product_name_raw"])["display_name"]
            row["complaints"] = complaints_by_order.get(key, [])
        through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {sql}", args).fetchone()[0]
    return {"items": rows, "total": total, "page": page, "size": size, "data_through": through}


@app.get("/api/product-rules")
def product_rules(q: str = ""):
    with connect() as db:
        pattern = f"%{q.strip()}%"
        short_names = [dict(row) for row in db.execute("""SELECT key_value sku,short_name,updated_at
          FROM product_short_names WHERE key_type='sku'
            AND (?='' OR key_value LIKE ? OR short_name LIKE ?) ORDER BY key_value""",
          (q.strip(), pattern, pattern))]
        products = [dict(row) for row in db.execute("""SELECT sku,offer_id,MAX(product_name_raw) product_name
          FROM order_items WHERE NULLIF(offer_id,'') IS NOT NULL
          GROUP BY sku,offer_id ORDER BY offer_id,sku LIMIT 1000""")]
        for product in products:
            product["product_name"] = clean_product_name(product["product_name"])
        rules = load_product_rules(db)
        groups = []
        for config in db.execute("""SELECT c.group_id id,c.primary_offer_id,c.primary_sku,c.status,c.note,
            g.updated_at FROM product_group_config c JOIN product_groups g ON g.id=c.group_id
            ORDER BY c.primary_offer_id,c.group_id"""):
            group = dict(config)
            group["members"] = [dict(row) for row in db.execute("""SELECT key_type,key_value
              FROM product_group_members WHERE group_id=? ORDER BY key_type,key_value""", (group["id"],))]
            resolved = resolve_product(rules, group["primary_sku"], group["primary_offer_id"], "")
            group["product_name"] = resolved["display_name"] if group["status"] == "active" else "待管理员确认"
            groups.append(group)
        conflicts = [{"key_type": "merge", "key_value": row["primary_offer_id"] or "待确认商品组",
                       "note": row["note"]} for row in groups if row["status"] != "active"]
        short_name_count = db.execute(
            "SELECT COUNT(*) FROM product_short_names WHERE key_type='sku'").fetchone()[0]
    return {"summary": {"short_names": short_name_count,
                         "merges": sum(row["status"] == "active" for row in groups)},
            "short_names": short_names, "groups": groups, "products": products, "conflicts": conflicts,
            "fixed_rule": "固定规则：自动移除平台产品名称中的“Новый ”前缀"}


@app.put("/api/product-rules")
async def save_product_rule(request: Request):
    body = await request.json()
    kind = body.get("kind")
    now = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        if kind == "short_name":
            key_value = str(body.get("sku") or body.get("key_value") or "").strip()
            name = str(body.get("short_name") or "").strip()
            if body.get("key_type") not in (None, "sku") or not key_value or not name:
                raise HTTPException(400, "短名称规则不完整")
            db.execute("""INSERT INTO product_short_names VALUES('sku',?,?,?)
              ON CONFLICT(key_type,key_value) DO UPDATE SET short_name=excluded.short_name,updated_at=excluded.updated_at""",
                       (key_value, name, now))
        elif kind == "delete_short_name":
            sku = str(body.get("sku") or "").strip()
            if not sku: raise HTTPException(400, "SKU不能为空")
            db.execute("DELETE FROM product_short_names WHERE key_type='sku' AND key_value=?", (sku,))
        elif kind == "merge":
            group_id = int(body.get("id") or 0)
            primary_offer = str(body.get("primary_offer_id") or "").strip()
            members = [(str(row.get("key_type") or ""), str(row.get("key_value") or "").strip())
                       for row in body.get("members") or []]
            if not primary_offer or any(key_type not in {"sku", "offer_id"} or not value
                                        for key_type, value in members):
                raise HTTPException(400, "主货号和合并成员不能为空")
            if len(members) != len(set(members)):
                raise HTTPException(400, "合并成员不能重复")
            members = list(dict.fromkeys([("offer_id", primary_offer), *members]))
            if len(members) < 2: raise HTTPException(400, "请至少添加一个合并成员")
            skus = [row[0] for row in db.execute(
                "SELECT DISTINCT sku FROM order_items WHERE offer_id=? ORDER BY sku", (primary_offer,))]
            if not skus: raise HTTPException(400, "主货号未匹配到现有商品")
            primary_sku = str(body.get("primary_sku") or "").strip()
            if len(skus) > 1 and primary_sku not in skus:
                raise HTTPException(400, "主货号对应多个SKU，请明确选择名称解析SKU")
            primary_sku = primary_sku if primary_sku in skus else skus[0]
            existing = db.execute("SELECT group_id FROM product_group_config WHERE primary_offer_id=? AND group_id<>?",
                                  (primary_offer, group_id)).fetchone()
            if existing: raise HTTPException(400, "该主货号已用于其他合并关系")
            for key_type, value in members:
                owner = db.execute("SELECT group_id FROM product_group_members WHERE key_type=? AND key_value=? AND group_id<>?",
                                   (key_type, value, group_id)).fetchone()
                if owner: raise HTTPException(400, f"{key_type} {value} 已属于其他主货号")
            member_skus = [value for key_type, value in members if key_type == "sku"]
            member_offers = [value for key_type, value in members if key_type == "offer_id"]
            pairs = db.execute(f"""SELECT DISTINCT sku,offer_id FROM order_items WHERE
              sku IN ({','.join('?' for _ in member_skus) or "''"}) OR
              offer_id IN ({','.join('?' for _ in member_offers) or "''"})""",
              [*member_skus, *member_offers]).fetchall()
            for pair in pairs:
                owner = db.execute("""SELECT group_id FROM product_group_members WHERE group_id<>?
                  AND ((key_type='sku' AND key_value=?) OR (key_type='offer_id' AND key_value=?)) LIMIT 1""",
                  (group_id, pair["sku"], pair["offer_id"])).fetchone()
                if owner: raise HTTPException(400, f"商品 {pair['sku']} / {pair['offer_id']} 与其他主货号冲突")
            if group_id:
                if not db.execute("SELECT 1 FROM product_groups WHERE id=?", (group_id,)).fetchone():
                    raise HTTPException(400, "合并关系不存在")
                db.execute("UPDATE product_groups SET name=?,updated_at=? WHERE id=?",
                           (f"merge:{primary_offer}", now, group_id))
                db.execute("DELETE FROM product_group_members WHERE group_id=?", (group_id,))
            else:
                group_id = db.execute("INSERT INTO product_groups(name,created_at,updated_at) VALUES(?,?,?)",
                                      (f"merge:{primary_offer}", now, now)).lastrowid
            db.execute("""INSERT INTO product_group_config VALUES(?,?,?,'active','')
              ON CONFLICT(group_id) DO UPDATE SET primary_offer_id=excluded.primary_offer_id,
              primary_sku=excluded.primary_sku,status='active',note=''""", (group_id, primary_offer, primary_sku))
            db.executemany("INSERT INTO product_group_members VALUES(?,?,?)",
                           [(group_id, key_type, value) for key_type, value in members])
        elif kind == "dissolve":
            db.execute("DELETE FROM product_groups WHERE id=?", (int(body.get("id") or 0),))
        else:
            raise HTTPException(400, "未知规则类型")
    return {"ok": True}


@app.get("/api/returns")
def returns(shop_id: int = 0, page: int = 1, size: int = 50, q: str = "",
            date_from: Annotated[str | None, Query(alias="from")] = None,
            date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    filters, args = ["r.occurred_at>=?", "r.occurred_at<?"], [utc_start, utc_end]
    if shop_id:
        filters.append("r.shop_id=?"); args.append(shop_id)
    if q.strip():
        pattern = f"%{q.strip()}%"
        filters.append("(r.sku LIKE ? OR r.posting_number LIKE ? OR CAST(json_extract(r.payload,'$.product.offer_id') AS TEXT) LIKE ?)")
        args.extend([pattern, pattern, pattern])
    where = " WHERE " + " AND ".join(filters)
    page, size = _paging(page, size)
    with connect() as db:
        totals = [dict(row) for row in db.execute(f"""
          SELECT r.shop_id,s.name shop_name,COUNT(*) records,
            COALESCE(SUM(CAST(json_extract(r.payload,'$.product.quantity') AS INTEGER)),0) quantity
          FROM return_records r JOIN shops s ON s.id=r.shop_id{where}
          GROUP BY r.shop_id ORDER BY r.shop_id
        """, args)]
        total = db.execute(f"SELECT COUNT(*) FROM return_records r{where}", args).fetchone()[0]
        records = db.execute(f"""SELECT r.shop_id,s.name shop_name,r.occurred_at,r.posting_number,r.sku,r.payload,
          o.status_changed_at,
          CAST(json_extract(r.payload,'$.product.offer_id') AS TEXT) offer_id
          FROM return_records r JOIN shops s ON s.id=r.shop_id
          LEFT JOIN orders o ON o.shop_id=r.shop_id AND o.posting_number=r.posting_number{where}
          ORDER BY r.occurred_at DESC LIMIT ? OFFSET ?""", args + [size, (page - 1) * size]).fetchall()
        through = db.execute(f"SELECT MAX(r.occurred_at) FROM return_records r{where}", args).fetchone()[0]
        rules = load_product_rules(db)
    items = []
    for row in records:
        payload = json.loads(row["payload"])
        product, visual = payload.get("product") or {}, payload.get("visual") or {}
        status = visual.get("status") or {}
        status = status.get("display_name") if isinstance(status, dict) else status
        item = {"shop_id": row["shop_id"], "shop_name": row["shop_name"],
                      "occurred_at": row["occurred_at"], "posting_number": row["posting_number"],
                      "sku": row["sku"], "offer_id": row["offer_id"],
                      "product_name": resolve_product(rules, row["sku"], row["offer_id"],
                                                       product.get("name"))["display_name"],
                      "quantity": product.get("quantity"),
                      "reason": CANCEL_REASON_ZH.get(payload.get("return_reason_name"), payload.get("return_reason_name")),
                      "reason_raw": payload.get("return_reason_name"),
                      "status": RETURN_STATUS_ZH.get(status, status),
                      "compensation_status": payload.get("compensation_status") or payload.get("money_return_state_name"),
                      "product_amount": product.get("price") or product.get("amount"),
                      "product_currency": product.get("currency_code") or product.get("currency"),
                      "logistic_return_at": payload.get("logistic_return_at") or payload.get("returned_at"),
                      "buyer_comment_raw": payload.get("buyer_comment") or payload.get("comment"),
                      "type": payload.get("type")}
        item["cancelled_at"] = row["status_changed_at"] or row["occurred_at"]
        item.update(_complaint_deadline(row["status_changed_at"], row["occurred_at"]))
        items.append(item)
    return {"summary": {"records": total, "shops": totals}, "items": items, "total": total,
            "page": page, "size": size, "data_through": through}


@app.get("/api/rfbs-returns")
def rfbs_returns(shop_id: int = 0, page: int = 1, size: int = 50, q: str = "",
                 date_from: Annotated[str | None, Query(alias="from")] = None,
                 date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    filters, args = ["r.created_at>=?", "r.created_at<?"], [utc_start, utc_end]
    if shop_id:
        filters.append("r.shop_id=?"); args.append(shop_id)
    if q.strip():
        pattern = f"%{q.strip()}%"
        filters.append("(r.sku LIKE ? OR r.offer_id LIKE ? OR r.posting_number LIKE ? OR r.return_number LIKE ?)")
        args.extend([pattern] * 4)
    where = " WHERE " + " AND ".join(filters)
    page, size = _paging(page, size)
    with connect() as db:
        totals = [dict(row) for row in db.execute(f"""SELECT r.shop_id,s.name shop_name,COUNT(*) records
          FROM rfbs_return_records r JOIN shops s ON s.id=r.shop_id{where}
          GROUP BY r.shop_id ORDER BY r.shop_id""", args)]
        total = db.execute(f"SELECT COUNT(*) FROM rfbs_return_records r{where}", args).fetchone()[0]
        rows = db.execute(f"""SELECT r.shop_id,s.name shop_name,s.settlement_currency,r.return_id,
          r.return_number,r.created_at,r.posting_number,r.offer_id,r.sku,r.product_name,
          r.status_raw,r.status_name,r.quantity,r.reason_raw,r.reason_name,
          r.compensation_status,r.product_amount,r.product_currency,r.logistic_return_at,
          r.buyer_comment_raw,r.payload,d.refund_amount,d.refund_currency,
          d.platform_compensation_rub,d.platform_compensated_at,
          d.logistics_compensation_cny,d.logistics_compensated_at,d.return_method,d.return_result
          FROM rfbs_return_records r JOIN shops s ON s.id=r.shop_id
          LEFT JOIN rfbs_return_disputes d ON d.shop_id=r.shop_id AND d.return_number=r.return_number{where}
          ORDER BY r.created_at DESC,r.return_id DESC LIMIT ? OFFSET ?""",
          args + [size, (page - 1) * size]).fetchall()
        rows = [_with_compensation_conversion(db, dict(row)) for row in rows]
        through = db.execute(f"SELECT MAX(r.created_at) FROM rfbs_return_records r{where}", args).fetchone()[0]
        rules = load_product_rules(db)
    items = []
    for raw in rows:
        item = dict(raw)
        item["product_name"] = resolve_product(rules, item["sku"], item["offer_id"],
                                               item["product_name"])["display_name"]
        payload = json.loads(item.pop("payload"))
        product, state = payload.get("product") or {}, payload.get("state") or {}
        item["quantity"] = item["quantity"] or payload.get("quantity") or product.get("quantity") or 1
        item["product_amount"] = item["product_amount"] if item["product_amount"] is not None else product.get("price")
        item["product_currency"] = item["product_currency"] or product.get("currency_code")
        item["compensation_status"] = item["compensation_status"] or state.get("money_return_state_name")
        item["reason_name"] = CANCEL_REASON_ZH.get(item["reason_raw"], item["reason_name"] or item["reason_raw"])
        items.append(item)
    for item in items:
        item["status_name"] = RFBS_RETURN_STATUS_ZH.get(item["status_raw"], item["status_name"] or item["status_raw"])
        item.update(_complaint_deadline(item["created_at"]))
    return {"summary": {"records": total, "shops": totals}, "items": items, "total": total,
            "page": page, "size": size, "data_through": through}


@app.get("/api/exception-complaints/received")
def received_disputes(shop_id: int = 0, q: str = "", status: str = "", page: int = 1, size: int = 50,
                      date_from: Annotated[str | None, Query(alias="from")] = None,
                      date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    if status not in {"", "unfiled", "open", "closed"}:
        raise HTTPException(400, "处理状态无效")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    where, args = ["r.created_at>=?", "r.created_at<?"], [utc_start, utc_end]
    if shop_id:
        where.append("r.shop_id=?"); args.append(shop_id)
    if q.strip():
        pattern = f"%{q.strip()}%"
        where.append("(r.sku LIKE ? OR r.offer_id LIKE ? OR r.posting_number LIKE ? OR r.return_number LIKE ?)")
        args.extend([pattern] * 4)
    if status == "unfiled":
        where.append("d.return_number IS NULL")
    elif status == "open":
        where.append("d.return_number IS NOT NULL AND COALESCE(d.process_status,'') NOT IN ('结束','已完结')")
    elif status == "closed":
        where.append("d.process_status IN ('结束','已完结')")
    sql = " AND ".join(where)
    page, size = _paging(page, size)
    with connect() as db:
        join = """FROM rfbs_return_records r JOIN shops s ON s.id=r.shop_id
          LEFT JOIN rfbs_return_disputes d ON d.shop_id=r.shop_id AND d.return_number=r.return_number"""
        total = db.execute(f"SELECT COUNT(*) {join} WHERE {sql}", args).fetchone()[0]
        rows = [dict(row) for row in db.execute(f"""SELECT r.shop_id,s.name shop_name,s.settlement_currency,r.return_number,
          r.created_at,r.posting_number,r.sku,r.offer_id,r.product_name,r.product_amount,r.product_currency,
          r.reason_raw,r.reason_name,r.buyer_comment_raw,d.refund_type,d.refund_amount,d.refund_currency,
          d.platform_compensation_rub,d.platform_compensated_at,
          d.logistics_compensation_cny,d.logistics_compensated_at,d.process_status,d.return_method,
          d.iml_return_number,d.iml_system_sn,d.buyer_tracking_number,d.handling_method,d.video_recorded,
          d.outbound_order_number,d.return_result,d.notes,d.created_at manual_created_at,d.updated_at
          {join} WHERE {sql} ORDER BY r.created_at DESC,r.return_id DESC LIMIT ? OFFSET ?""",
          args + [size, (page - 1) * size])]
        rules = load_product_rules(db)
        for row in rows:
            row.update(_complaint_deadline(row["created_at"]))
            row["product_name"] = resolve_product(rules, row["sku"], row["offer_id"],
                                                   row["product_name"])["display_name"]
            row["reason_name"] = CANCEL_REASON_ZH.get(row["reason_raw"], row["reason_name"] or row["reason_raw"])
            _with_compensation_conversion(db, row)
        through = db.execute(f"SELECT MAX(r.created_at) {join} WHERE {sql}", args).fetchone()[0]
    return {"items": rows, "total": total, "page": page, "size": size, "data_through": through}


@app.post("/api/exception-complaints/received")
@app.put("/api/exception-complaints/received")
async def save_received_dispute(request: Request):
    body = await request.json()
    shop_id = int(body.get("shop_id") or 0)
    return_number = str(body.get("return_number") or "").strip()
    if shop_id not in (1, 2) or not return_number:
        raise HTTPException(400, "店铺和退货申请编号均为必填")
    enums = {
        "refund_type": {"", "部分退款", "全额退款", "多次纠纷"},
        "return_method": {"", "未退货", "IML", "FBO二次销售"},
        "handling_method": {"", "退回", "销毁"},
        "return_result": {"", "退回国内中", "已签收", "已销毁"},
    }
    for key, allowed in enums.items():
        if str(body.get(key) or "") not in allowed:
            raise HTTPException(400, f"{key}取值无效")
    if body.get("video_recorded") not in (None, True, False):
        raise HTTPException(400, "是否拍视频只允许未填写、是或否")
    try:
        refund_amount = None if body.get("refund_amount") in (None, "") else float(body["refund_amount"])
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "退款金额无效") from error
    platform_amount, platform_at = _compensation_pair(
        body, "platform_compensation_rub", "platform_compensated_at")
    logistics_amount, logistics_at = _compensation_pair(
        body, "logistics_compensation_cny", "logistics_compensated_at")
    now = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        shop = db.execute("SELECT settlement_currency FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not db.execute("""SELECT 1 FROM rfbs_return_records
          WHERE shop_id=? AND return_number=?""", (shop_id, return_number)).fetchone():
            raise HTTPException(400, "未找到该店铺退货申请")
        exists = db.execute("""SELECT created_at FROM rfbs_return_disputes
          WHERE shop_id=? AND return_number=?""", (shop_id, return_number)).fetchone()
        refund_currency = str(body.get("refund_currency") or (shop[0] if refund_amount is not None else "")).upper() or None
        if refund_currency not in (None, "USD", "CNY"):
            raise HTTPException(400, "币种只允许USD或CNY")
        db.execute("""INSERT INTO rfbs_return_disputes(
          shop_id,return_number,refund_type,refund_amount,refund_currency,
          platform_compensation_rub,platform_compensated_at,
          logistics_compensation_cny,logistics_compensated_at,
          process_status,return_method,iml_return_number,iml_system_sn,
          buyer_tracking_number,handling_method,video_recorded,outbound_order_number,return_result,notes,
          created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(shop_id,return_number) DO UPDATE SET refund_type=excluded.refund_type,
          refund_amount=excluded.refund_amount,refund_currency=excluded.refund_currency,
          platform_compensation_rub=excluded.platform_compensation_rub,
          platform_compensated_at=excluded.platform_compensated_at,
          logistics_compensation_cny=excluded.logistics_compensation_cny,
          logistics_compensated_at=excluded.logistics_compensated_at,
          process_status=excluded.process_status,return_method=excluded.return_method,
          iml_return_number=excluded.iml_return_number,iml_system_sn=excluded.iml_system_sn,
          buyer_tracking_number=excluded.buyer_tracking_number,handling_method=excluded.handling_method,
          video_recorded=excluded.video_recorded,outbound_order_number=excluded.outbound_order_number,
          return_result=excluded.return_result,notes=excluded.notes,updated_at=excluded.updated_at""",
          (shop_id, return_number, str(body.get("refund_type") or ""), refund_amount,
           refund_currency, platform_amount, platform_at, logistics_amount, logistics_at,
           str(body.get("process_status") or ""), str(body.get("return_method") or ""),
           str(body.get("iml_return_number") or ""), str(body.get("iml_system_sn") or ""),
           str(body.get("buyer_tracking_number") or ""), str(body.get("handling_method") or ""),
           None if body.get("video_recorded") is None else int(body["video_recorded"]),
           str(body.get("outbound_order_number") or ""), str(body.get("return_result") or ""),
           str(body.get("notes") or ""), exists[0] if exists else now, now))
    return {"ok": True}


def _latest_stock_snapshots(db, shop_id):
    where, args = _record_clause(shop_id, "r")
    return db.execute(f"""SELECT r.shop_id,s.name shop_name,r.observed_at,r.payload FROM stock_snapshots r
      JOIN shops s ON s.id=r.shop_id{where}
      ORDER BY r.shop_id,r.record_key""", args).fetchall()


def _stock_quantity(value):
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _forecast_bounds(today, days):
    start = today - timedelta(days=days)
    return (_utc_text(datetime.combine(start, datetime.min.time(), BEIJING)),
            _utc_text(datetime.combine(today, datetime.min.time(), BEIJING)))


def _history_channel(row):
    source = str(row["source"] or "")
    if source == "push_rfbs":
        return "realFBS"
    if source == "push_fbo":
        return "WHD"
    event_key = str(row["event_key"] or "").rsplit(":", 1)[-1].lower()
    return {"fbp": "FBP", "fbs": "realFBS", "rfbs": "realFBS", "fbo": "WHD"}.get(event_key)


def _stock_history_index(history_rows):
    index = {}
    for row in history_rows:
        channel = _history_channel(row)
        moment = _utc_moment(row["occurred_at"])
        if not channel or not moment:
            continue
        key = (row["shop_id"], str(row["sku"] or ""), channel)
        warehouse = str(row["warehouse_id"] or "")
        index.setdefault(key, {}).setdefault(warehouse, []).append(
            (moment, _stock_quantity(row["present"])))
    for series in index.values():
        for values in series.values():
            values.sort(key=lambda value: value[0])
    return index


def _confirmed_stockout_days(history_index, shop_id, sku, channel, sales_end):
    """Return only days whose stock log proves zero stock for the whole day.

    A point-in-time snapshot is not enough.  Each tracked warehouse/source must
    have a zero state at both day boundaries and no positive event in between.
    """
    series = history_index.get((shop_id, sku, channel))
    if not series:
        return None
    confirmed = set()
    for offset in range(30):
        day = sales_end - timedelta(days=offset)
        start = datetime.combine(day, datetime.min.time(), BEIJING).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), datetime.min.time(), BEIJING).astimezone(timezone.utc)
        reliable = True
        for values in series.values():
            before = [value for value in values if value[0] <= start]
            after = [value for value in values if value[0] >= end]
            if not before or not after or before[-1][1] or after[0][1]:
                reliable = False
                break
            if any(value for moment, value in values if start <= moment < end):
                reliable = False
                break
        if reliable:
            confirmed.add(day)
    return confirmed


def _forecast_values(sales, first_sale_at, stockout_days, sales_end):
    first_sale = _utc_moment(first_sale_at)
    first_sale = first_sale.astimezone(BEIJING).date() if first_sale else None
    age_days = max((sales_end - first_sale).days + 1, 0) if first_sale and first_sale <= sales_end else 0
    daily, data_days, in_stock_days = {}, {}, {}
    full_windows = []
    for window in FORECAST_WINDOWS:
        observed_days = min(window, age_days) if age_days else 0
        data_days[window] = observed_days
        if stockout_days is None:
            in_stock_days[window] = None
            denominator = observed_days
        else:
            start = sales_end - timedelta(days=observed_days - 1) if observed_days else sales_end
            counted = sum(start <= day <= sales_end for day in stockout_days)
            in_stock_days[window] = max(observed_days - counted, 0)
            denominator = in_stock_days[window]
        value = float(sales.get(f"sales_{window}") or 0)
        daily[window] = value / denominator if denominator else (0.0 if not value else None)
        if age_days >= window and daily[window] is not None:
            full_windows.append(window)
    if full_windows:
        windows = full_windows
    elif data_days[7] and daily[7] is not None:
        windows = [7]
    elif data_days[15] and daily[15] is not None:
        windows = [15]
    elif data_days[30] and daily[30] is not None:
        windows = [30]
    else:
        windows = []
    weight_total = sum(FORECAST_WEIGHTS[window] for window in windows)
    forecast = (sum(daily[window] * FORECAST_WEIGHTS[window] for window in windows
                    if daily[window] is not None) / weight_total
                if weight_total else 0.0)
    adjusted = bool(stockout_days)
    ratio = daily[7] / daily[30] if daily[7] is not None and daily[30] else None
    trend = "快速增长" if ratio is not None and ratio >= 1.30 else "稳定" if ratio is None or ratio >= .80 else "下降"
    return {"daily": daily, "data_days": data_days, "in_stock_days": in_stock_days,
            "forecast": forecast, "windows": windows, "adjusted": adjusted,
            "stockout_days": len(stockout_days or ()), "trend_7_vs_30": ratio, "trend": trend}


def _forecast_risk(effective_stock, forecast_daily, days_cover, recommended):
    if not forecast_daily:
        return "no_recent_sales"
    if effective_stock <= 0:
        return "out_of_stock"
    if days_cover is not None and days_cover <= FORECAST_LEAD_TIME_DAYS:
        return "urgent_replenishment"
    if recommended > 0:
        return "replenish"
    if days_cover is not None and days_cover > FORECAST_OVERSTOCK_DAYS:
        return "overstock"
    return "sufficient"


@app.get("/api/stock")
def stock(shop_id: int = 0, page: int = 1, size: int = 50, sku: str = "",
          offer_id: str = "", product_name: str = "", sort_by: str = "",
          sort_order: str = "desc", channel: str = "", risk: str = "", q: str = ""):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    channel = {"all": "", "fbp": "FBP", "realfbs": "realFBS", "whd": "WHD"}.get(channel, channel)
    if channel not in ("", "FBP", "realFBS", "WHD"):
        raise HTTPException(400, "未知履约模式")
    reference_channel = channel or "FBP"
    risk = {"需要关注": "attention", "缺货": "out_of_stock", "紧急补货": "urgent_replenishment",
            "需要补货": "replenish", "库存充足": "sufficient", "库存偏高": "overstock",
            "无近期销量": "no_recent_sales"}.get(risk, risk)
    valid_risks = {"", "attention", *FORECAST_RISK_LABELS}
    if risk not in valid_risks:
        raise HTTPException(400, "未知库存风险")
    if sort_by not in ("", "fbp", "realfbs", "whd", "forecast", "replenishment", "days_cover", "risk"):
        raise HTTPException(400, "未知排序字段")
    if sort_order not in ("asc", "desc"):
        raise HTTPException(400, "未知排序方向")
    page, size = _paging(page, size)
    today = datetime.now(BEIJING).date()
    sales_end = today - timedelta(days=1)
    bounds = [_forecast_bounds(today, days) for days in FORECAST_WINDOWS]
    shop_clause, shop_args = _shop_clause(shop_id)
    with connect() as db:
        records = _latest_stock_snapshots(db, shop_id)
        history_rows = db.execute("""SELECT shop_id,source,warehouse_id,sku,present,reserved,occurred_at,event_key
          FROM stock_history WHERE (?=0 OR shop_id=?) ORDER BY shop_id,sku,occurred_at""",
                                 (shop_id, shop_id)).fetchall()
        history_index = _stock_history_index(history_rows)
        sales = {(row["shop_id"], row["sku"]): dict(row) for row in db.execute(f"""SELECT i.shop_id,i.sku,
          SUM(CASE WHEN o.created_at>=? AND o.created_at<? THEN i.quantity ELSE 0 END) sales_7,
          SUM(CASE WHEN o.created_at>=? AND o.created_at<? THEN i.quantity ELSE 0 END) sales_15,
          SUM(CASE WHEN o.created_at>=? AND o.created_at<? THEN i.quantity ELSE 0 END) sales_30,
          MIN(o.created_at) first_sale_at
          FROM order_items i JOIN orders o USING(shop_id,posting_number)
          WHERE {ACTIVE} AND o.channel IN ('FBP','realFBS')
            AND o.created_at<? {shop_clause}
          GROUP BY i.shop_id,i.sku""", [bound for pair in bounds for bound in pair] + [bounds[0][1]] + shop_args)}
        metadata = {}
        for row in db.execute(f"""SELECT i.shop_id,i.sku,i.offer_id,i.product_name_raw,i.source,o.created_at
          FROM order_items i JOIN orders o USING(shop_id,posting_number)
          WHERE 1=1 {shop_clause}
          ORDER BY (i.source='api') DESC,o.created_at DESC""", shop_args):
            item = metadata.setdefault((row["shop_id"], row["sku"]), {"offer_id": "", "product_name_raw": ""})
            item["offer_id"] = item["offer_id"] or row["offer_id"] or ""
            item["product_name_raw"] = item["product_name_raw"] or row["product_name_raw"] or ""
        ad_stats = {(row["shop_id"], str(row["sku"])): {"ad_orders": int(row["ad_orders"] or 0),
                    "product_name": row["product_name"] or "", "has_rows": bool(row["has_rows"])}
                    for row in db.execute("""SELECT shop_id,sku,MAX(NULLIF(product_name,'')) product_name,
                      SUM(CASE WHEN stat_date BETWEEN ? AND ? THEN COALESCE(orders,0) ELSE 0 END) ad_orders,
                      MAX(CASE WHEN stat_date BETWEEN ? AND ? THEN 1 ELSE 0 END) has_rows
                      FROM ad_sku_daily WHERE (?=0 OR shop_id=?) GROUP BY shop_id,sku""",
                                         (bounds[2][0][:10], sales_end.isoformat(), bounds[2][0][:10],
                                          sales_end.isoformat(), shop_id, shop_id))}
        shop_names = {row["id"]: row["name"] for row in db.execute("SELECT id,name FROM shops")}
        rules = load_product_rules(db)
        sales_through = db.execute(f"""SELECT MAX(data_through) FROM sync_runs o
          WHERE module='orders' AND status='success'{shop_clause}""", shop_args).fetchone()[0]
        if not sales_through:
            sales_through = db.execute(f"""SELECT MAX(o.created_at) FROM orders o
              WHERE o.channel IN ('FBP','realFBS'){shop_clause}""", shop_args).fetchone()[0]
    grouped = {}
    channel_names = {"fbp": "FBP", "rfbs": "realFBS", "fbo": "WHD"}
    def empty_group(item_shop, item_sku):
        return {"shop_id": item_shop, "shop_name": shop_names.get(item_shop, f"店铺{item_shop}"),
                "sku": str(item_sku), "offer_id": "", "product_id": None, "_channels": {}}

    for row in records:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            continue
        for value in payload.get("stocks") or []:
            item_sku = str(value.get("sku") or payload.get("product_id") or "")
            channel = channel_names.get(str(value.get("type") or "").lower())
            if not item_sku or not channel:
                continue
            key = row["shop_id"], item_sku
            group = grouped.setdefault(key, empty_group(row["shop_id"], item_sku))
            group["offer_id"] = group["offer_id"] or str(payload.get("offer_id") or "")
            group["product_id"] = group["product_id"] or payload.get("product_id")
            stock_value = group["_channels"].setdefault(channel, {"channel": channel, "source": "api",
              "present": 0, "reserved": 0, "observed_at": row["observed_at"]})
            stock_value["present"] += _stock_quantity(value.get("present"))
            stock_value["reserved"] += _stock_quantity(value.get("reserved"))
            stock_value["observed_at"] = max(stock_value["observed_at"] or "", row["observed_at"] or "")
    push_latest = {}
    for row in history_rows:
        if row["source"] not in ("push_rfbs", "push_fbo"):
            continue
        key = (row["shop_id"], row["source"], row["sku"], row["warehouse_id"] or "")
        previous = push_latest.get(key)
        current_at = _utc_moment(row["occurred_at"])
        previous_at = _utc_moment(previous["occurred_at"]) if previous else None
        if not previous or (current_at and (not previous_at or current_at > previous_at)):
            push_latest[key] = row
    push_groups = {}
    for row in push_latest.values():
        push_groups.setdefault((row["shop_id"], row["source"], row["sku"]), []).append(row)
    for (push_shop, source, item_sku), rows in push_groups.items():
        channel = "realFBS" if source == "push_rfbs" else "WHD"
        key = push_shop, str(item_sku)
        group = grouped.setdefault(key, empty_group(push_shop, item_sku))
        baseline = group["_channels"].get(channel)
        values = list(rows)
        if baseline and _utc_moment(baseline["observed_at"]):
            values = [value for value in values if _utc_moment(value["occurred_at"])
                      and _utc_moment(value["occurred_at"]) > _utc_moment(baseline["observed_at"])]
        if values:
            observed_at = max(value["occurred_at"] for value in values)
            group["_channels"][channel] = {"channel": channel, "source": source,
              "present": sum(_stock_quantity(value["present"]) for value in values),
              "reserved": sum(_stock_quantity(value["reserved"]) for value in values), "observed_at": observed_at}
    for key in sales:
        grouped.setdefault(key, empty_group(key[0], key[1]))
    for key, value in ad_stats.items():
        group = grouped.setdefault(key, empty_group(key[0], key[1]))
        metadata.setdefault(key, {"offer_id": "", "product_name_raw": value["product_name"]})
    cards = []
    for group in grouped.values():
        meta = metadata.get((group["shop_id"], group["sku"]), {})
        group["offer_id"] = group["offer_id"] or meta.get("offer_id") or ""
        raw_name = meta.get("product_name_raw") or ""
        resolved = resolve_product(rules, group["sku"], group["offer_id"], raw_name)
        channels_by_name = group.pop("_channels")
        channels = [channels_by_name.get(channel, {"channel": channel, "source": "api",
                    "present": 0, "reserved": 0, "observed_at": None})
                    for channel in ("FBP", "realFBS", "WHD")]
        for value in channels:
            value["present"] = _stock_quantity(value.get("present"))
            value["reserved"] = _stock_quantity(value.get("reserved"))
            value["effective_stock"] = value["present"]
        sold = sales.get((group["shop_id"], group["sku"]), {})
        group.update({"offer_id": group["offer_id"] or resolved["primary_offer_id"] or "",
                      "product_id": group["product_id"], "product_name_raw": resolved["platform_name"],
                      "short_name": rules["short_names"].get(resolved["primary_sku"] or group["sku"], ""),
                      "display_name": resolved["display_name"], "analysis_identity": resolved["identity"],
                      "group_id": resolved["group_id"], "primary_offer_id": resolved["primary_offer_id"],
                      "offer_members": [group["offer_id"]] if group["offer_id"] else []})
        group["channels"] = channels
        group["present"] = sum(value["present"] for value in channels)
        group["reserved"] = sum(value["reserved"] for value in channels)
        group["sales_7"] = int(sold.get("sales_7") or 0)
        group["sales_15"] = int(sold.get("sales_15") or 0)
        group["sales_30"] = int(sold.get("sales_30") or 0)
        # Replenishment policy:
        # demand = FBP + realFBS sales
        # replenishment stock = FBP only
        # WHD does not participate in demand or replenishment calculations.
        forecast_channel = "FBP"
        base = next(value for value in channels if value["channel"] == forecast_channel)
        stockout_days = _confirmed_stockout_days(history_index, group["shop_id"], group["sku"],
                                                  forecast_channel, sales_end)
        forecast = _forecast_values(sold, sold.get("first_sale_at"), stockout_days, sales_end)
        daily = forecast["forecast"]
        effective_stock = base["effective_stock"]
        days_cover = effective_stock / daily if daily else None
        projected = max(effective_stock - daily * FORECAST_LEAD_TIME_DAYS, 0) if daily else None
        recommended = math.ceil(max(daily * FORECAST_TARGET_COVER_DAYS - projected, 0)) if daily else 0
        risk_code = _forecast_risk(effective_stock, daily, days_cover, recommended)
        ad = ad_stats.get((group["shop_id"], group["sku"]), {})
        ad_orders = ad.get("ad_orders") if ad.get("has_rows") else None
        group.update({
            "current_stock": effective_stock, "reserved_stock": base["reserved"], "effective_stock": effective_stock,
            "forecast_channel": forecast_channel, "sales_data_through": sales_end.isoformat(),
            "daily_7": forecast["daily"][7], "daily_15": forecast["daily"][15], "daily_30": forecast["daily"][30],
            "daily_sales": daily, "forecast_daily": daily, "sales_data_days_7": forecast["data_days"][7],
            "sales_data_days_15": forecast["data_days"][15], "sales_data_days_30": forecast["data_days"][30],
            "in_stock_days_7": forecast["in_stock_days"][7], "in_stock_days_15": forecast["in_stock_days"][15],
            "in_stock_days_30": forecast["in_stock_days"][30], "forecast_windows_used": forecast["windows"],
            "forecast_adjusted_for_stockout": forecast["adjusted"], "confirmed_stockout_days_30": forecast["stockout_days"],
            "trend_7_vs_30": forecast["trend_7_vs_30"], "trend": forecast["trend"],
            "days_cover": days_cover, "current_cover_days": days_cover,
            "days_available": days_cover, "expected_stockout_date":
                (today + timedelta(days=math.ceil(days_cover))).isoformat() if days_cover is not None else None,
            "lead_time_days": FORECAST_LEAD_TIME_DAYS, "inbound_before_arrival": 0,
            "inbound_included": False, "projected_stock_at_arrival": projected,
            "target_cover_days": FORECAST_TARGET_COVER_DAYS, "target_stock_after_arrival":
                daily * FORECAST_TARGET_COVER_DAYS if daily else 0,
            "recommended_replenishment": recommended, "replenishment": recommended,
            "stockout_before_arrival": bool(days_cover is not None and days_cover < FORECAST_LEAD_TIME_DAYS),
            "shortage_days": max(FORECAST_LEAD_TIME_DAYS - days_cover, 0) if days_cover is not None else None,
            "risk_code": risk_code, "risk_status": FORECAST_RISK_LABELS[risk_code],
            "ad_orders_30": ad_orders, "ad_order_share": ad_orders / group["sales_30"]
                if ad_orders is not None and group["sales_30"] else None,
            "fbp_present": channels[0]["present"], "fbp_reserved": channels[0]["reserved"],
            "fbp_effective_stock": channels[0]["effective_stock"], "replenishment_stock_source": "FBP",
        })
        group["observed_at"] = max((value["observed_at"] or "" for value in channels), default="") or None
        filters = ((sku, group["sku"]), (offer_id, " ".join(group["offer_members"])),
                   (product_name, f"{group['product_name_raw']} {group['display_name']}"))
        search_text = f"{group['sku']} {group['offer_id']} {group['product_name_raw']} {group['display_name']}".lower()
        if q.strip() and q.strip().lower() not in search_text:
            continue
        if any(value.strip().lower() not in target.lower() for value, target in filters if value.strip()):
            continue
        if risk == "attention" and risk_code not in {"out_of_stock", "urgent_replenishment", "replenish"}:
            continue
        if risk and risk != "attention" and risk_code != risk:
            continue
        cards.append(group)
    if sort_by:
        sort_values = {
            "fbp": lambda value: value["channels"][0]["present"],
            "realfbs": lambda value: value["channels"][1]["present"],
            "whd": lambda value: value["channels"][2]["present"],
            "forecast": lambda value: value["forecast_daily"],
            "replenishment": lambda value: value["replenishment"],
            "days_cover": lambda value: value["days_cover"],
            "risk": lambda value: -FORECAST_RISK_ORDER[value["risk_code"]],
        }
        cards.sort(key=lambda value: (
            sort_values[sort_by](value) is None,
            (sort_values[sort_by](value) or 0) * (1 if sort_order == "asc" else -1),
            value["shop_id"], value["sku"],
        ))
    else:
        cards.sort(key=lambda value: (FORECAST_RISK_ORDER[value["risk_code"]], value["shop_id"], value["sku"]))
    total = len(cards); start = (page - 1) * size
    through = max((item["observed_at"] for item in cards if item["observed_at"]), default=None)
    summary = {"active_skus": total,
               "fbp_present": sum(item["fbp_present"] for item in cards),
               "fbp_reserved": sum(item["fbp_reserved"] for item in cards),
               "need_replenishment_skus": sum(item["risk_code"] in {"out_of_stock", "urgent_replenishment", "replenish"} for item in cards),
               "replenishment_skus": sum(item["risk_code"] in {"out_of_stock", "urgent_replenishment", "replenish"} for item in cards),
               "stockout_before_arrival_skus": sum(item["stockout_before_arrival"] for item in cards),
               "shortage_skus": sum(item["stockout_before_arrival"] for item in cards),
               "expected_stockout_skus": sum(item["expected_stockout_date"] is not None for item in cards),
               "recommended_replenishment_total": sum(item["recommended_replenishment"] for item in cards),
               "effective_stock": sum(item["effective_stock"] for item in cards),
               "reserved_stock": sum(item["reserved_stock"] for item in cards),
               "forecast_channel": "FBP", "reference_channel": reference_channel,
               "replenishment_stock_source": "FBP", "inbound_included": False}
    return {"summary": summary, "items": cards[start:start + size],
            "total": total, "page": page, "size": size, "data_through": through,
            "sales_through": sales_through,
            "sales_window_end": sales_end.isoformat(), "inventory_business_date": today.isoformat(),
            "formula": "预测日销=FBP+realFBS销量的7/15/30日均销按50%/30%/20%加权；补货库存=FBP；补货=ceil(max(预测日销×60-到货时库存,0))；lead time=25天；未计入在途库存"}


@app.get("/api/inventory/forecast")
def inventory_forecast(shop_id: int = 0, page: int = 1, size: int = 50, q: str = "", channel: str = "",
                       risk: str = "", sort: str = "", sort_order: str = "desc"):
    return stock(shop_id=shop_id, page=page, size=size, q=q, channel=channel, risk=risk,
                 sort_by=sort, sort_order=sort_order)




@app.post("/api/import/{kind}")
async def upload(kind: str, request: Request, shop_id: int):
    if shop_id not in (1, 2): raise HTTPException(400, "请选择店铺")
    if kind not in CHANNELS: raise HTTPException(400, "未知渠道")
    filename = unquote(request.headers.get("x-filename", kind))
    if Path(filename).suffix.lower() != ".csv": raise HTTPException(400, "仅支持CSV文件")
    content = await request.body()
    if len(content) > 50 * 1024 * 1024: raise HTTPException(413, "文件超过50MB")
    try:
        return await run_in_threadpool(import_csv, shop_id, kind, filename, content)
    except (ValueError, UnicodeError) as error:
        raise HTTPException(400, str(error)) from error


@app.get("/api/imports")
def imports():
    with connect() as db:
        return [dict(row) for row in db.execute("""
          SELECT b.*,s.name shop_name FROM import_batches b JOIN shops s ON s.id=b.shop_id
          WHERE b.kind IN ('FBP','realFBS','WHD') ORDER BY b.id DESC LIMIT 10
        """)]


@app.get("/api/sync")
def sync_runs():
    with connect() as db:
        return [dict(row) for row in db.execute("""
          SELECT r.*,s.name shop_name FROM sync_runs r JOIN shops s ON s.id=r.shop_id ORDER BY r.id DESC LIMIT 10
        """)]


@app.get("/api/exchange-rates")
def get_exchange_rate_status():
    return exchange_rate_status()


@app.post("/api/exchange-rates/sync")
async def sync_exchange_rate_data(request: Request):
    body = await request.json()
    start, end, _, _ = _overview_range(body.get("from"), body.get("to"))
    try:
        return await run_in_threadpool(sync_exchange_rates, start, end)
    except (OSError, ValueError) as error:
        raise HTTPException(502, f"汇率拉取失败：{error}") from error


@app.get("/api/sync/{run_id}")
def sync_run(run_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM sync_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "拉取任务不存在")
    return dict(row)


def _run_performance_campaign_sync(shop_id):
    started_at = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        run_id = db.execute("""INSERT INTO sync_runs(
          shop_id,module,status,progress_total,run_source,started_at)
          VALUES(?,?, 'running',1,'manual',?)""",
                            (shop_id, PERFORMANCE_SYNC_MODULE, started_at)).lastrowid
    try:
        result = sync_performance_campaigns(shop_id)
    except Exception as error:
        with transaction() as db:
            db.execute("""UPDATE sync_runs SET finished_at=?,status='failed',error=?
              WHERE id=?""", (_utc_text(datetime.now(timezone.utc)), str(error)[:500], run_id))
            _trim_sync_runs(db)
        raise
    records = int(result.get("inserted_or_updated") or 0)
    finished_at = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        db.execute("""UPDATE sync_runs SET finished_at=?,status='success',progress_done=1,
          records=?,data_through=? WHERE id=?""", (finished_at, records, finished_at, run_id))
        _trim_sync_runs(db)
    result = dict(result)
    result["run_id"] = run_id
    return result


def _evaluate_alerts_after_sync(shop_id, module):
    rule_keys = {
        "orders": ("sales_drop", "inventory_risk"),
        "stock": ("inventory_risk",),
        "ad_campaign_daily": ("ad_spend_spike", "ad_drr_high", "ad_orders_drop"),
        "ad_sku_daily": ("ad_clicks_no_orders",),
        "ad_statistics": ("ad_spend_spike", "ad_drr_high", "ad_orders_drop", "ad_clicks_no_orders"),
    }.get(module)
    if not rule_keys:
        return
    try:
        evaluate_alerts(shop_id, rule_keys=rule_keys)
    except Exception:
        # Alert delivery is best effort; a sync that succeeded must stay successful.
        pass


@app.post("/api/performance/test")
async def performance_test(request: Request):
    shop_id = _performance_shop_id((await request.json()).get("shop_id"))
    try:
        campaigns = await run_in_threadpool(list_campaigns, shop_id)
    except PerformanceConfigurationError as error:
        raise HTTPException(400, str(error)) from error
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error
    return {"success": True, "shop_id": shop_id, "campaign_count": len(campaigns)}


@app.post("/api/performance/campaigns/sync")
async def performance_campaign_sync(request: Request):
    shop_id = _performance_shop_id((await request.json()).get("shop_id"))
    try:
        return await run_in_threadpool(_run_performance_campaign_sync, shop_id)
    except PerformanceConfigurationError as error:
        raise HTTPException(400, str(error)) from error
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.get("/api/performance/campaigns")
def performance_campaigns(shop_id: str = "0"):
    value = str(shop_id or "0").strip().lower()
    selected = 0 if value in ("0", "all") else _performance_shop_id(value)
    with connect() as db:
        if selected:
            rows = db.execute("""SELECT a.*,s.name shop_name FROM ad_campaigns a
              JOIN shops s ON s.id=a.shop_id WHERE a.shop_id=?
              ORDER BY a.campaign_id""", (selected,)).fetchall()
        else:
            rows = db.execute("""SELECT a.*,s.name shop_name FROM ad_campaigns a
              JOIN shops s ON s.id=a.shop_id ORDER BY a.shop_id,a.campaign_id""").fetchall()
    return [dict(row) for row in rows]


def _performance_range(date_from=None, date_to=None):
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    try:
        end = date.fromisoformat(str(date_to)) if date_to else today
        start = date.fromisoformat(str(date_from)) if date_from else end - timedelta(days=6)
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "日期格式必须为 YYYY-MM-DD") from error
    if start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    return start, end


def _performance_filter_shop(value):
    text = str(value or "0").strip().lower()
    return 0 if text in ("", "0", "all") else _performance_shop_id(text)


AD_BASE_FIELDS = ("impressions", "clicks", "cart_adds", "spend_rub", "orders", "revenue_rub")


def _ad_number(value):
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _ad_summary(row):
    values = {field: _ad_number(row.get(field)) for field in AD_BASE_FIELDS}
    values["impressions"] = int(values["impressions"])
    values["clicks"] = int(values["clicks"])
    values["cart_adds"] = int(values["cart_adds"])
    values["orders"] = int(values["orders"])
    values["spend_rub"] = round(values["spend_rub"], 2)
    values["revenue_rub"] = round(values["revenue_rub"], 2)
    values["ctr"] = round(values["clicks"] / values["impressions"] * 100, 4) if values["impressions"] else None
    values["avg_cpc_rub"] = round(values["spend_rub"] / values["clicks"], 4) if values["clicks"] else None
    values["drr"] = round(values["spend_rub"] / values["revenue_rub"] * 100, 4) if values["revenue_rub"] else None
    values["roas"] = round(values["revenue_rub"] / values["spend_rub"], 4) if values["spend_rub"] else None
    return values


def _ad_add(target, row):
    for field in AD_BASE_FIELDS:
        target[field] = target.get(field, 0) + _ad_number(row.get(field))


def _ad_sort(rows, sort, order):
    sort = str(sort or "spend_rub").strip().lower()
    aliases = {"spend": "spend_rub", "revenue": "revenue_rub", "cpc": "avg_cpc_rub",
               "campaigns": "campaign_count"}
    sort = aliases.get(sort, sort)
    allowed = {"name", "sku", "spend_rub", "revenue_rub", "orders", "impressions", "clicks",
               "ctr", "avg_cpc_rub", "drr", "roas", "campaign_count"}
    if sort not in allowed:
        sort = "spend_rub"
    present = [row for row in rows if row.get(sort) is not None]
    missing = [row for row in rows if row.get(sort) is None]
    present.sort(key=lambda row: str(row.get(sort)).lower() if sort in {"name", "sku"} else row.get(sort),
                 reverse=str(order or "desc").lower() == "desc")
    return present + missing


def _date_query_values(date_from, date_to, from_date, to_date):
    return _performance_range(date_from or from_date, date_to or to_date)


@app.get("/api/performance/overview")
def performance_overview(shop_id: str = "0", date_from: str | None = None, date_to: str | None = None,
                         from_date: Annotated[str | None, Query(alias="from")] = None,
                         to_date: Annotated[str | None, Query(alias="to")] = None):
    selected = _performance_filter_shop(shop_id)
    start, end = _date_query_values(date_from, date_to, from_date, to_date)
    with connect() as db:
        rows = [dict(row) for row in db.execute("""
          SELECT d.shop_id,s.name shop_name,d.stat_date,
            SUM(COALESCE(d.impressions,0)) impressions,SUM(COALESCE(d.clicks,0)) clicks,
            SUM(COALESCE(d.cart_adds,0)) cart_adds,SUM(COALESCE(d.spend_rub,0)) spend_rub,
            SUM(COALESCE(d.orders,0)) orders,SUM(COALESCE(d.revenue_rub,0)) revenue_rub
          FROM ad_campaign_daily d JOIN shops s ON s.id=d.shop_id
          WHERE d.stat_date BETWEEN ? AND ? AND (?=0 OR d.shop_id=?)
          GROUP BY d.shop_id,d.stat_date ORDER BY d.stat_date,d.shop_id""",
            (start.isoformat(), end.isoformat(), selected, selected))]
        shop_rows = [dict(row) for row in db.execute("SELECT id,name FROM shops ORDER BY id")]
    by_date, by_shop = {}, {}
    for row in rows:
        by_date.setdefault(row["stat_date"], {})
        _ad_add(by_date[row["stat_date"]], row)
        by_shop.setdefault(row["shop_id"], {"shop_id": row["shop_id"], "shop_name": row["shop_name"]})
        _ad_add(by_shop[row["shop_id"]], row)
    zero = {field: 0 for field in AD_BASE_FIELDS}
    summary_base = dict(zero)
    for row in rows:
        _ad_add(summary_base, row)
    trend = [{"date": current.isoformat(), **_ad_summary(by_date.get(current.isoformat(), zero))}
             for index in range((end - start).days + 1)
             for current in [start + timedelta(days=index)]]
    shops = []
    for shop in shop_rows:
        if selected and shop["id"] != selected:
            continue
        shops.append({"shop_id": shop["id"], "shop_name": shop["name"],
                      **_ad_summary(by_shop.get(shop["id"], zero))})
    summary = _ad_summary(summary_base)
    return {"shop_id": selected, "date_from": start.isoformat(), "date_to": end.isoformat(),
            **summary, "summary": summary, "trend": trend, "shops": shops,
            "data_through": max((row["stat_date"] for row in rows), default=None)}


@app.get("/api/performance/campaign-stats")
def performance_campaign_stats(shop_id: str = "0", state: str = "", sort: str = "spend_rub",
                               order: str = "desc", page: int = 1, size: int = 100,
                               date_from: str | None = None, date_to: str | None = None,
                               from_date: Annotated[str | None, Query(alias="from")] = None,
                               to_date: Annotated[str | None, Query(alias="to")] = None):
    selected = _performance_filter_shop(shop_id)
    start, end = _date_query_values(date_from, date_to, from_date, to_date)
    page, size = _paging(page, size)
    state = "" if str(state or "").lower() in {"", "all"} else str(state).strip()
    with connect() as db:
        rows = [dict(row) for row in db.execute("""
          SELECT c.shop_id,s.name shop_name,c.campaign_id,c.name,c.state,c.payment_type,
            c.adv_object_type,c.placement,c.weekly_budget,
            COALESCE(d.impressions,0) impressions,COALESCE(d.clicks,0) clicks,
            COALESCE(d.cart_adds,0) cart_adds,COALESCE(d.spend_rub,0) spend_rub,
            COALESCE(d.orders,0) orders,COALESCE(d.revenue_rub,0) revenue_rub,d.data_through
          FROM ad_campaigns c JOIN shops s ON s.id=c.shop_id
          LEFT JOIN (
            SELECT shop_id,campaign_id,MAX(stat_date) data_through,
              SUM(COALESCE(impressions,0)) impressions,SUM(COALESCE(clicks,0)) clicks,
              SUM(COALESCE(cart_adds,0)) cart_adds,SUM(COALESCE(spend_rub,0)) spend_rub,
              SUM(COALESCE(orders,0)) orders,SUM(COALESCE(revenue_rub,0)) revenue_rub
            FROM ad_campaign_daily WHERE stat_date BETWEEN ? AND ?
            GROUP BY shop_id,campaign_id
          ) d ON d.shop_id=c.shop_id AND d.campaign_id=c.campaign_id
          WHERE (?=0 OR c.shop_id=?) AND (?='' OR c.state=?)
          ORDER BY c.shop_id,c.campaign_id""",
            (start.isoformat(), end.isoformat(), selected, selected, state, state))]
    items = []
    for row in rows:
        item = {key: row[key] for key in ("shop_id", "shop_name", "campaign_id", "name", "state",
                                           "payment_type", "adv_object_type", "placement", "weekly_budget")}
        item.update(_ad_summary(row))
        item["data_through"] = row["data_through"]
        items.append(item)
    items = _ad_sort(items, sort, order)
    total = len(items)
    offset = (page - 1) * size
    return {"items": items[offset:offset + size], "total": total, "page": page, "size": size,
            "date_from": start.isoformat(), "date_to": end.isoformat(),
            "data_through": max((row["data_through"] for row in items if row["data_through"]), default=None)}


@app.get("/api/performance/sku-stats")
def performance_sku_stats(shop_id: str = "0", q: str = "", sort: str = "spend_rub",
                          order: str = "desc", page: int = 1, size: int = 100,
                          date_from: str | None = None, date_to: str | None = None,
                          from_date: Annotated[str | None, Query(alias="from")] = None,
                          to_date: Annotated[str | None, Query(alias="to")] = None):
    selected = _performance_filter_shop(shop_id)
    start, end = _date_query_values(date_from, date_to, from_date, to_date)
    page, size = _paging(page, size)
    with connect() as db:
        rows = [dict(row) for row in db.execute("""
          SELECT d.shop_id,s.name shop_name,d.sku,
            COALESCE(MAX(NULLIF(d.product_name,'')),MAX(NULLIF(p.product_name,''))) product_name,
            COUNT(DISTINCT d.campaign_id) campaign_count,MAX(d.stat_date) data_through,
            SUM(COALESCE(d.impressions,0)) impressions,SUM(COALESCE(d.clicks,0)) clicks,
            SUM(COALESCE(d.cart_adds,0)) cart_adds,SUM(COALESCE(d.spend_rub,0)) spend_rub,
            SUM(COALESCE(d.orders,0)) orders,SUM(COALESCE(d.revenue_rub,0)) revenue_rub
          FROM ad_sku_daily d JOIN shops s ON s.id=d.shop_id
          LEFT JOIN (
            SELECT shop_id,sku,MAX(NULLIF(product_name_raw,'')) product_name
            FROM order_items GROUP BY shop_id,sku
          ) p ON p.shop_id=d.shop_id AND p.sku=d.sku
          WHERE d.stat_date BETWEEN ? AND ? AND (?=0 OR d.shop_id=?)
          GROUP BY d.shop_id,d.sku ORDER BY d.shop_id,d.sku""",
            (start.isoformat(), end.isoformat(), selected, selected))]
    query = str(q or "").strip().lower()
    items = []
    for row in rows:
        if query and query not in str(row["sku"]).lower() and query not in str(row["product_name"] or "").lower():
            continue
        item = {key: row[key] for key in ("shop_id", "shop_name", "sku", "product_name", "campaign_count", "data_through")}
        item.update(_ad_summary(row))
        items.append(item)
    items = _ad_sort(items, sort, order)
    total = len(items)
    offset = (page - 1) * size
    return {"items": items[offset:offset + size], "total": total, "page": page, "size": size,
            "date_from": start.isoformat(), "date_to": end.isoformat(),
            "data_through": max((row["data_through"] for row in items if row["data_through"]), default=None)}


def _run_performance_statistics_sync(shop_id, start, end, module="all"):
    run_module = "ad_statistics" if module == "all" else module
    started_at = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        run_id = db.execute("""INSERT INTO sync_runs(
          shop_id,module,range_from,range_to,status,progress_total,run_source,started_at)
          VALUES(?,?,?,?, 'running',1,'manual',?)""",
                            (shop_id, run_module, start.isoformat(), end.isoformat(), started_at)).lastrowid
    try:
        result = sync_performance_statistics(shop_id, start.isoformat(), end.isoformat(), module)
    except Exception as error:
        with transaction() as db:
            db.execute("""UPDATE sync_runs SET finished_at=?,status='failed',error=?
              WHERE id=?""", (_utc_text(datetime.now(timezone.utc)), str(error)[:500], run_id))
            _trim_sync_runs(db)
        raise
    records = int(result.get("inserted_or_updated") or 0)
    finished_at = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        db.execute("""UPDATE sync_runs SET finished_at=?,status='success',progress_done=1,
          records=?,data_through=? WHERE id=?""",
                   (finished_at, records, result.get("date_to"), run_id))
        _trim_sync_runs(db)
    _evaluate_alerts_after_sync(shop_id, run_module)
    result = dict(result)
    result["run_id"] = run_id
    return result


@app.post("/api/performance/statistics/sync")
async def performance_statistics_sync(request: Request):
    body = await request.json()
    shop_id = _performance_shop_id(body.get("shop_id"))
    try:
        start, end = _performance_range(body.get("date_from") or body.get("from"),
                                        body.get("date_to") or body.get("to"))
    except HTTPException:
        raise
    module = str(body.get("module") or "all")
    module = {"daily": "ad_campaign_daily", "campaign_daily": "ad_campaign_daily",
              "sku": "ad_sku_daily"}.get(module, module)
    if module not in {"all", "ad_campaign_daily", "ad_sku_daily"}:
        raise HTTPException(400, "未知广告统计模块")
    try:
        return await run_in_threadpool(_run_performance_statistics_sync, shop_id, start, end, module)
    except PerformanceConfigurationError as error:
        raise HTTPException(400, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.get("/api/auto-sync-settings")
def auto_sync_settings():
    with connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM shop_auto_sync_settings ORDER BY shop_id,CASE module "
            "WHEN 'orders' THEN 1 WHEN 'returns' THEN 2 WHEN 'stock' THEN 3 "
            "WHEN 'ad_campaign_daily' THEN 4 ELSE 5 END")]


def save_auto_sync_settings(values):
    if set(values) == SYNC_MODULES:
        values = {str(shop_id): values for shop_id in (1, 2)}
    if set(values) != {"1", "2"}:
        raise ValueError("必须分别提交两个店铺的自动拉取设置")
    with connect() as db:
        current_ads = {shop_id: {row["module"]: dict(row) for row in db.execute(
            "SELECT * FROM shop_auto_sync_settings WHERE shop_id=? AND module IN ('ad_campaign_daily','ad_sku_daily')",
            (shop_id,))} for shop_id in (1, 2)}
    settings = []
    for shop_id in (1, 2):
        submitted = dict(values[str(shop_id)])
        if set(submitted) == SYNC_MODULES:
            submitted.update({module: {"enabled": row["enabled"], "interval_hours": row["interval_hours"],
                                       "range_days": row["range_days"]}
                              for module, row in current_ads[shop_id].items()})
        if set(submitted) != AUTO_SYNC_MODULES:
            raise ValueError("必须分别提交两个店铺的五个模块设置")
        for module in ("orders", "returns", "stock", "ad_campaign_daily", "ad_sku_daily"):
            value = submitted[module]
            if "run_time" in value:
                raise ValueError("run_time 已停用，请提交 interval_hours")
            try:
                interval_hours = int(value.get("interval_hours"))
                range_days = int(value.get("range_days") or 0)
            except (TypeError, ValueError) as error:
                raise ValueError("拉取频率或范围无效") from error
            if interval_hours not in AUTO_SYNC_INTERVALS:
                raise ValueError("拉取频率只允许 1、2、3、4、6、8、12、24 小时")
            if not 1 <= range_days <= 365:
                raise ValueError("自动拉取范围必须为 1 至 365 天")
            settings.append((int(bool(value.get("enabled"))), interval_hours,
                             1 if module == "stock" else range_days, shop_id, module))
    with transaction() as db:
        db.executemany("""UPDATE shop_auto_sync_settings SET enabled=?,interval_hours=?,range_days=?
          WHERE shop_id=? AND module=?""",
                       settings)


@app.put("/api/auto-sync-settings")
async def update_auto_sync_settings(request: Request):
    try:
        save_auto_sync_settings(await request.json())
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"ok": True}


def _sync_ranges(module, start, end):
    if module == "stock" or module in AD_SYNC_MODULES:
        return [(start, end)]
    ranges, current = [], start
    while current <= end:
        next_month = (current.replace(day=1, year=current.year + 1, month=1)
                      if current.month == 12 else current.replace(day=1, month=current.month + 1))
        next_month = next_month.replace(hour=0, minute=0, second=0, microsecond=0)
        chunk_end = min(end, next_month - timedelta(seconds=1))
        ranges.append((current, chunk_end))
        current = next_month
    return ranges


def _run_sync_job(run_id, module, shop_id, ranges):
    records = 0
    with connect() as db:
        run_source = db.execute("SELECT run_source FROM sync_runs WHERE id=?", (run_id,)).fetchone()[0]
    try:
        for index, (start, end) in enumerate(ranges, 1):
            with transaction() as db:
                db.execute("UPDATE sync_runs SET current_from=?,current_to=? WHERE id=?",
                           (_utc_text(start), _utc_text(end), run_id))
            if module in AD_SYNC_MODULES:
                start_date = start.date() if isinstance(start, datetime) else start
                end_date = end.date() if isinstance(end, datetime) else end
                result = sync_performance_statistics(shop_id, start_date.isoformat(), end_date.isoformat(), module)
                records += int(result.get("inserted_or_updated") or 0)
            else:
                result = sync_module(module, shop_id, start, end, include_existing_missing=run_source != "auto")
                records += int(result.get("records") or 0)
            with transaction() as db:
                db.execute("UPDATE sync_runs SET progress_done=?,records=?,data_through=? WHERE id=?",
                           (index, records, _utc_text(end), run_id))
    except Exception as error:
        message = str(error)[:500]
        with transaction() as db:
            db.execute("""UPDATE sync_runs SET finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'),
              status='failed',error=? WHERE id=?""", (message, run_id))
            _trim_sync_runs(db)
        try:
            send_sync_failure(shop_id, module, ranges[0][0], ranges[-1][1], message)
        except Exception:
            pass
        return
    with transaction() as db:
        db.execute("""UPDATE sync_runs SET finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'),
          data_through=?,status='success',current_from=NULL,current_to=NULL WHERE id=?""",
                   (_utc_text(ranges[-1][1]), run_id))
        _trim_sync_runs(db)
    _evaluate_alerts_after_sync(shop_id, module)


def _create_sync_job(module, shop_id, start, end, run_source="manual", scheduled_slot=None, now=None):
    ranges = _sync_ranges(module, start, end)
    with transaction() as db:
        if run_source == "auto":
            if db.execute("SELECT 1 FROM sync_runs WHERE shop_id=? AND module=? AND status='running'",
                          (shop_id, module)).fetchone():
                return None
            cooldown = _utc_text((now or datetime.now(BEIJING)) - timedelta(minutes=5))
            if db.execute("""SELECT 1 FROM sync_runs
              WHERE shop_id=? AND module=? AND scheduled_slot=? AND run_source='auto'
              AND status='failed' AND datetime(COALESCE(finished_at,started_at))>=datetime(?)""",
                          (shop_id, module, scheduled_slot, cooldown)).fetchone():
                return None
        cursor = db.execute("""INSERT OR IGNORE INTO sync_runs(
          shop_id,module,range_from,range_to,status,progress_total,run_source,scheduled_slot)
          VALUES(?,?,?,?, 'running',?,?,?)""",
                            (shop_id, module, _utc_text(start), _utc_text(end), len(ranges),
                             run_source, scheduled_slot))
        if cursor.rowcount == 0:
            return None
        run_id = cursor.lastrowid
        _trim_sync_runs(db, scheduled_slot=scheduled_slot)
    threading.Thread(target=_run_sync_job, args=(run_id, module, shop_id, ranges), daemon=True).start()
    return run_id


def auto_sync_slot(now, interval_hours):
    if now.tzinfo is None:
        now = now.replace(tzinfo=BEIJING)
    now = now.astimezone(BEIJING)
    return now.replace(hour=(now.hour // interval_hours) * interval_hours,
                       minute=0, second=0, microsecond=0)


def run_auto_sync_once(now=None):
    now = now or datetime.now(BEIJING)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BEIJING)
    now = now.astimezone(BEIJING)
    with connect() as db:
        settings = db.execute("""SELECT * FROM shop_auto_sync_settings
          WHERE enabled=1 ORDER BY shop_id,rowid""").fetchall()
    started = []
    for setting in settings:
        slot = auto_sync_slot(now, setting["interval_hours"])
        end = now
        start = (now - timedelta(days=setting["range_days"] - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        run_id = _create_sync_job(setting["module"], setting["shop_id"], start, end,
                                  "auto", slot.isoformat(), now)
        if run_id:
            started.append(run_id)
    return started


def _auto_sync_scheduler():
    while not _auto_sync_stop.wait(20):
        try:
            run_auto_sync_once()
        except Exception:
            pass


def _start_auto_sync_scheduler():
    global _auto_sync_thread
    if _auto_sync_thread and _auto_sync_thread.is_alive():
        return
    _auto_sync_stop.clear()
    _auto_sync_thread = threading.Thread(target=_auto_sync_scheduler, name="auto-sync-scheduler", daemon=True)
    _auto_sync_thread.start()


def _stop_auto_sync_scheduler():
    _auto_sync_stop.set()


@app.post("/api/sync/{module}")
async def sync(module: str, request: Request, shop_id: int):
    if module not in SYNC_MODULES: raise HTTPException(404, "未知模块")
    if shop_id not in (1, 2): raise HTTPException(400, "请选择店铺")
    body = await request.json()
    start, end = default_range()
    try:
        if body.get("from"):
            start = datetime.fromisoformat(body["from"]).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        if body.get("to"):
            end = datetime.fromisoformat(body["to"]).replace(hour=23, minute=59, second=59, tzinfo=ZoneInfo("Asia/Shanghai"))
    except ValueError as error:
        raise HTTPException(400, "日期格式无效") from error
    if start >= end:
        raise HTTPException(400, "开始日期必须早于结束日期")
    run_id = _create_sync_job(module, shop_id, start, end)
    with connect() as db:
        total = db.execute("SELECT progress_total FROM sync_runs WHERE id=?", (run_id,)).fetchone()[0]
    return {"run_id": run_id, "status": "running", "progress_total": total}


def _export_range(date_from="", date_to=""):
    if not date_from and not date_to:
        return None
    if "T" in date_from or "T" in date_to:
        try:
            start = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
            end = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
        except ValueError as error:
            raise HTTPException(400, "日期格式无效") from error
        if start and start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
        if end and end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
        if start and end and start > end:
            raise HTTPException(400, "开始日期不能晚于结束日期")
        return date_from or None, date_to or None, date_from or None, date_to or None, False
    start, end, utc_start, utc_end = _overview_range(date_from or None, date_to or None)
    return start.isoformat(), end.isoformat(), utc_start, utc_end, True


@app.get("/api/export/orders")
def export_orders(shop_id: int = 0, date_from: str = "", date_to: str = ""):
    if shop_id not in (0, 1, 2): raise HTTPException(400, "未知店铺")
    clause, args = _shop_clause(shop_id)
    export_range = _export_range(date_from, date_to)
    range_clause = ""
    if export_range:
        _, _, utc_start, utc_end, exclusive_end = export_range
        if utc_start:
            range_clause += " AND o.created_at>=?"; args.append(utc_start)
        if utc_end:
            range_clause += f" AND o.created_at{'<' if exclusive_end else '<='}?"; args.append(utc_end)
    def lines():
        with connect() as db:
            rules = load_product_rules(db)
            shops_value = [dict(r) for r in db.execute("SELECT id,name FROM shops ORDER BY id")
                           if shop_id not in (1, 2) or r["id"] == shop_id]
            through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {ACTIVE}{clause}{range_clause}", args).fetchone()[0]
            yield json.dumps({"type":"metadata","shops":shops_value,"timezone":"数据库UTC；显示北京时间",
                              "range":{"from":export_range[0],"to":export_range[1]} if export_range else {"from":None,"to":None},
                              "order_definition":"COUNT DISTINCT posting_number","piece_definition":"SUM quantity",
                              "filter":"剔除状态为已取消且无发货证据的订单","data_through":through}, ensure_ascii=False) + "\n"
            for raw in db.execute(f"""
              SELECT o.shop_id,s.name shop_name,o.posting_number,o.channel,o.created_at,
                o.shipped_at,o.delivered_at,o.status_changed_at,o.status_raw,o.cancel_reason_raw,
                o.shipped,o.data_anomaly,o.amount_original,o.amount_currency
              FROM orders o JOIN shops s ON s.id=o.shop_id
              WHERE {ACTIVE}{clause}{range_clause} ORDER BY o.created_at
            """, args):
                value = _translated_order(raw)
                value["items"] = []
                for item_raw in db.execute("""SELECT sku,offer_id,product_name_raw,quantity,
                  unit_price,price_currency FROM order_items WHERE shop_id=? AND posting_number=?
                  ORDER BY sku,offer_id""", (value["shop_id"], value["posting_number"])):
                    item = dict(item_raw)
                    resolved = resolve_product(rules, item["sku"], item["offer_id"], item["product_name_raw"])
                    item.update({"product_name": resolved["display_name"],
                                 "analysis_identity": resolved["identity"]})
                    value["items"].append(item)
                value["sku_types"] = len(value["items"])
                value["pieces"] = sum(int(item["quantity"] or 0) for item in value["items"])
                yield json.dumps(value, ensure_ascii=False) + "\n"
    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Content-Disposition":"attachment; filename=orders.jsonl"})


@app.get("/api/export/{module}")
def export_module(module: str, shop_id: int = 0, date_from: str = "", date_to: str = ""):
    if module not in {"risk", "returns", "complaints"}:
        raise HTTPException(404, "未知导出模块")
    if shop_id not in (0, 1, 2): raise HTTPException(400, "未知店铺")
    tables = {
        "risk": ("orders o JOIN order_items i USING(shop_id,posting_number)", "o.created_at",
                 "o.shop_id,o.channel,o.posting_number,o.created_at,i.sku,i.offer_id,i.product_name_raw,i.quantity,o.status_raw,o.shipped,o.cancel_reason_raw"),
        "returns": ("rfbs_return_records o LEFT JOIN rfbs_return_disputes d ON d.shop_id=o.shop_id AND d.return_number=o.return_number JOIN shops s ON s.id=o.shop_id", "o.created_at",
                 "o.shop_id,s.name shop_name,o.return_id,o.return_number,o.created_at,o.posting_number,o.sku,o.offer_id,o.product_name,o.status_raw,o.status_name,o.quantity,o.reason_raw,o.reason_name,o.compensation_status,o.product_amount,o.product_currency,o.logistic_return_at,o.buyer_comment_raw,s.settlement_currency,d.refund_type,d.refund_amount,d.refund_currency,d.platform_compensation_rub,d.platform_compensated_at,d.logistics_compensation_cny,d.logistics_compensated_at,d.process_status,d.return_method,d.iml_return_number,d.iml_system_sn,d.buyer_tracking_number,d.handling_method,d.video_recorded,d.outbound_order_number,d.return_result,d.notes,d.created_at manual_created_at,d.updated_at manual_updated_at"),
        "complaints": ("complaints o JOIN shops s ON s.id=o.shop_id JOIN orders x ON x.shop_id=o.shop_id AND x.posting_number=o.posting_number", "o.complaint_at",
                 "o.shop_id,s.name shop_name,o.posting_number,o.complaint_number,o.complaint_at,o.channel,o.resolved,o.package_returned,o.compensation_amount,o.compensation_currency,o.notes,o.not_received_return,o.warehouse,o.order_process_status,o.complaint_status,o.compensation_status,o.platform_compensation_rub,o.platform_compensated_at,o.logistics_compensation_cny,o.logistics_compensated_at,s.settlement_currency,x.status_changed_at,(SELECT MAX(r.occurred_at) FROM return_records r WHERE r.shop_id=o.shop_id AND r.posting_number=o.posting_number) fallback_cancelled_at,o.created_at,o.updated_at"),
    }
    table, date_column, fields = tables[module]
    where, args = ["1=1"], []
    alias = "o"
    export_range = _export_range(date_from, date_to)
    if shop_id in (1, 2):
        where.append(f"{alias}.shop_id=?"); args.append(shop_id)
    if export_range:
        _, _, utc_start, utc_end, exclusive_end = export_range
        if utc_start:
            where.append(f"{date_column}>=?"); args.append(utc_start)
        if utc_end:
            where.append(f"{date_column}{'<' if exclusive_end else '<='}?"); args.append(utc_end)
    if module == "risk":
        where.append(ACTIVE)
    sql_where = " AND ".join(where)

    def lines():
        with connect() as db:
            selected = [dict(row) for row in db.execute("SELECT id,name FROM shops ORDER BY id")
                        if shop_id not in (1, 2) or row["id"] == shop_id]
            through = db.execute(f"SELECT MAX({date_column}) FROM {table} WHERE {sql_where}", args).fetchone()[0]
            metadata = {"type": "metadata", "module": module, "shops": selected,
              "range": {"from": export_range[0], "to": export_range[1]} if export_range else {"from": None, "to": None},
              "timezone": "数据库UTC；页面北京时间", "currencies": "保留记录原始币种，不做跨币种汇总",
              "order_definition": "不同posting_number", "piece_definition": "SUM(quantity)",
              "filter": "统计类导出剔除发货前取消；模块互相隔离", "data_through": through}
            yield json.dumps(metadata, ensure_ascii=False) + "\n"
            if module == "returns":
                legacy_where, legacy_args = ["1=1"], []
                if shop_id in (1, 2):
                    legacy_where.append("shop_id=?"); legacy_args.append(shop_id)
                if export_range:
                    if utc_start:
                        legacy_where.append("occurred_at>=?"); legacy_args.append(utc_start)
                    if utc_end:
                        legacy_where.append(f"occurred_at{'<' if exclusive_end else '<='}?"); legacy_args.append(utc_end)
                for row in db.execute(f"SELECT shop_id,occurred_at,posting_number,sku,payload FROM return_records WHERE {' AND '.join(legacy_where)} ORDER BY occurred_at", legacy_args):
                    value, payload = dict(row), json.loads(row["payload"])
                    product, visual = payload.get("product") or {}, payload.get("visual") or {}
                    status = visual.get("status") or {}
                    value.pop("payload")
                    value.update({"record_type": "取消明细", "quantity": product.get("quantity"),
                                  "offer_id": product.get("offer_id"), "product_name": product.get("name"),
                                  "reason_raw": payload.get("return_reason_name"),
                                  "reason_name": CANCEL_REASON_ZH.get(payload.get("return_reason_name"), payload.get("return_reason_name")),
                                  "status": status.get("display_name") if isinstance(status, dict) else status})
                    value.update(_complaint_deadline(value["occurred_at"]))
                    yield json.dumps(value, ensure_ascii=False) + "\n"
            rules = load_product_rules(db) if module == "risk" else None
            for row in db.execute(f"SELECT {fields} FROM {table} WHERE {sql_where} ORDER BY {date_column}", args):
                value = dict(row)
                if module == "returns":
                    value["record_type"] = "退货明细"
                    value["reason_name"] = CANCEL_REASON_ZH.get(
                        value["reason_raw"], value["reason_name"] or value["reason_raw"])
                    value.update(_complaint_deadline(value["created_at"]))
                    _with_compensation_conversion(db, value)
                elif module == "complaints":
                    value["record_type"] = "发货未收货投诉"
                    value.update(_complaint_deadline(value.pop("status_changed_at"),
                                                      value.pop("fallback_cancelled_at")))
                    _with_compensation_conversion(db, value)
                elif module == "risk":
                    resolved = resolve_product(rules, value["sku"], value["offer_id"], value.pop("product_name_raw"))
                    value["analysis_identity"] = resolved["identity"]
                    value["analysis_product_name"] = resolved["display_name"]
                    value["cancel_reason_name"] = CANCEL_REASON_ZH.get(
                        value["cancel_reason_raw"], value["cancel_reason_raw"])
                yield json.dumps(value, ensure_ascii=False) + "\n"
            if module == "complaints":
                received_where, received_args = ["1=1"], []
                if shop_id in (1, 2):
                    received_where.append("r.shop_id=?"); received_args.append(shop_id)
                if export_range:
                    if utc_start:
                        received_where.append("r.created_at>=?"); received_args.append(utc_start)
                    if utc_end:
                        received_where.append(f"r.created_at{'<' if exclusive_end else '<='}?")
                        received_args.append(utc_end)
                for row in db.execute(f"""SELECT r.shop_id,s.name shop_name,r.posting_number,
                  r.return_number,r.created_at,r.sku,r.offer_id,r.product_name,r.product_amount,
                  r.product_currency,r.reason_raw,r.reason_name,r.buyer_comment_raw,
                  d.refund_type,d.refund_amount,d.refund_currency,d.platform_compensation_rub,
                  d.platform_compensated_at,d.logistics_compensation_cny,d.logistics_compensated_at,
                  d.process_status,d.return_method,d.iml_return_number,d.iml_system_sn,
                  d.buyer_tracking_number,d.handling_method,d.video_recorded,d.outbound_order_number,
                  d.return_result,d.notes,d.created_at manual_created_at,d.updated_at manual_updated_at,
                  s.settlement_currency FROM rfbs_return_disputes d
                  JOIN rfbs_return_records r ON r.shop_id=d.shop_id AND r.return_number=d.return_number
                  JOIN shops s ON s.id=r.shop_id WHERE {' AND '.join(received_where)} ORDER BY r.created_at""",
                  received_args):
                    value = dict(row)
                    value["record_type"] = "已收货纠纷"
                    value["reason_name"] = CANCEL_REASON_ZH.get(
                        value["reason_raw"], value["reason_name"] or value["reason_raw"])
                    value.update(_complaint_deadline(value["created_at"]))
                    _with_compensation_conversion(db, value)
                    yield json.dumps(value, ensure_ascii=False) + "\n"
    return StreamingResponse(lines(), media_type="application/x-ndjson",
      headers={"Content-Disposition": f"attachment; filename={module}.jsonl"})


@app.get("/{path:path}")
def spa_fallback(path: str):
    if (path == "api" or path.startswith("api/") or
            path == "static" or path.startswith("static/") or
            path == "assets" or path.startswith("assets/")):
        raise HTTPException(404)
    return _frontend_index_response()
