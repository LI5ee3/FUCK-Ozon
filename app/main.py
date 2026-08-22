import hashlib
import hmac
import json
import secrets
import statistics
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .db import DATA_DIR, connect, init_db, transaction
from .dingtalk import configured as dingtalk_configured, send_sync_failure, send_test, start_scheduler, stop_scheduler
from .importer import CHANNELS, import_csv
from .ozon import (BEIJING, CANCEL_REASON_ZH, RFBS_RETURN_STATUS_ZH,
                   RETURN_STATUS_ZH, STATUS_ZH, _env, default_range, probe_shop, sync_module)
from .security import (clear_login_failures, login_limited, migrate_env_password,
                       password_matches, record_login_failure)

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
ACTIVE = "NOT (o.status_raw='已取消' AND o.shipped=0)"
BUYER_UNCLAIMED_REASONS = (
    "Покупатель не забрал заказ",
    "Покупатель отменил заказ",
    "Покупатель отменил заказ: не устроил срок доставки",
    "Покупатель отказался при вручении: товар не подошел",
    "Покупатель отменил заказ: нашел дешевле",
)
RISK_REASON_ZH = CANCEL_REASON_ZH | {
    "Покупатель отменил заказ: не устроил срок доставки": "买家取消：对配送时间不满意",
}
SYNC_MODULES = {"orders", "returns", "stock"}
_auto_sync_stop = threading.Event()
_auto_sync_thread = None

app = FastAPI(title="FUCK Ozon", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def startup():
    migrate_env_password(ROOT / ".env")
    init_db()
    with transaction() as db:
        db.execute("""UPDATE sync_runs SET status='failed',error='服务重启，任务已中断，请重新拉取',
          finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE status='running'""")
    start_scheduler()
    _start_auto_sync_scheduler()


@app.on_event("shutdown")
def shutdown():
    stop_scheduler()
    _stop_auto_sync_scheduler()


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


@app.middleware("http")
async def protect_api(request: Request, call_next):
    public = {"/api/login", "/api/session"}
    if request.url.path.startswith("/api/") and request.url.path not in public and not _authenticated(request):
        return Response(json.dumps({"detail": "未登录"}, ensure_ascii=False), 401, media_type="application/json")
    if (request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path != "/api/login"
            and request.url.path.startswith("/api/")):
        try:
            _, csrf, _ = request.cookies.get("session", "").split(".", 2)
        except ValueError:
            csrf = ""
        if not csrf or not hmac.compare_digest(csrf, request.headers.get("x-csrf-token", "")):
            return Response(json.dumps({"detail": "CSRF令牌无效"}, ensure_ascii=False), 403,
                            media_type="application/json")
    return await call_next(request)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/session")
def session(request: Request):
    authenticated = _authenticated(request)
    csrf = request.cookies.get("session", "").split(".", 2)[1] if authenticated else ""
    return {"authenticated": authenticated, "csrf_token": csrf}


@app.post("/api/login")
async def login(request: Request, response: Response):
    values = _env()
    salt, expected = values.get("ADMIN_PASSWORD_SALT"), values.get("ADMIN_PASSWORD_HASH")
    if not salt or not expected:
        raise HTTPException(503, "服务器尚未设置管理员密码哈希")
    key = request.client.host if request.client else "unknown"
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


def _dingtalk_settings():
    with connect() as db:
        row = dict(db.execute("SELECT * FROM notification_settings WHERE id=1").fetchone())
        last = db.execute("""SELECT stats_date,status,sent_at,error FROM notification_runs
          WHERE kind='daily' ORDER BY stats_date DESC LIMIT 1""").fetchone()
    row["daily_enabled"] = bool(row["daily_enabled"])
    row["weekdays"] = [int(value) for value in row["weekdays"].split(",") if value]
    row["configured"] = dingtalk_configured()
    row["last_run"] = dict(last) if last else None
    return row


@app.get("/api/dingtalk/settings")
def dingtalk_settings():
    return _dingtalk_settings()


@app.put("/api/dingtalk/settings")
async def update_dingtalk_settings(request: Request):
    body = await request.json()
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
    with transaction() as db:
        db.execute("UPDATE notification_settings SET daily_enabled=?,push_time=?,weekdays=? WHERE id=1",
                   (int(enabled), push_time, ",".join(map(str, weekdays))))
    return _dingtalk_settings()


@app.post("/api/dingtalk/test")
async def test_dingtalk():
    if not dingtalk_configured():
        raise HTTPException(400, "钉钉机器人未配置")
    try:
        await run_in_threadpool(send_test)
    except Exception as error:
        raise HTTPException(502, "测试推送失败") from error
    return {"ok": True}


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
    return start, end, utc_start.isoformat(), utc_end.isoformat()


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


def _gmv_summary(rows, shop_id):
    currency = "USD" if shop_id == 1 else "CNY"
    amount = 0.0
    missing = 0
    for row in rows:
        value = row["amount_original"] if row["amount_original"] is not None else row["item_amount"]
        value_currency = row["amount_currency"] or row["item_currency"] or row["settlement_currency"]
        if value is None or (shop_id == 0 and value_currency != "CNY") or (shop_id and value_currency != currency):
            missing += 1
        else:
            amount += value
    return {"amount": round(amount, 2), "currency": currency if shop_id else "CNY",
            "missing_rate_orders": missing}


RETURN_PENDING_STATUSES = {
    "AwaitingProcessing", "OnSellerApproval", "OnWayToOzon", "CheckingStatus",
    "PassedToPartner", "ApprovedOnPreModerationByOzon", "Approved", "OnWay",
    "UtilizingByOzon", "OnSellerClarificationAfterPartialCompensation",
}


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


def _overview_stock_alerts(db, shop_id):
    records = _latest_snapshots(db, "stock_snapshots", shop_id)
    latest = {}
    for row in records:
        payload = json.loads(row["payload"])
        for value in payload.get("stocks") or []:
            sku = str(value.get("sku") or payload.get("product_id") or "")
            if sku:
                item = latest.setdefault((row["shop_id"], sku), {"present": 0})
                item["present"] += int(value.get("present") or 0)
    if not latest:
        return None, None
    clause, args = _shop_clause(shop_id)
    sales = {(row["shop_id"], row["sku"]): row["pieces"] for row in db.execute(f"""
      SELECT i.shop_id,i.sku,SUM(i.quantity) pieces FROM order_items i
      JOIN orders o USING(shop_id,posting_number)
      WHERE {ACTIVE} AND julianday(o.created_at)>=julianday('now','-30 days'){clause}
      GROUP BY i.shop_id,i.sku""", args)}
    stockouts = sum(item["present"] <= 0 for item in latest.values())
    low_stock = sum(0 < item["present"] / (sales.get(key, 0) / 30) <= 7
                    for key, item in latest.items() if sales.get(key, 0))
    return stockouts, low_stock


def _overview_top_products(db, utc_start, utc_end, shop_id):
    clause, shop_args = _shop_clause(shop_id)
    rows = db.execute(f"""SELECT o.shop_id,o.posting_number,o.status_raw,o.shipped,
      i.sku,i.offer_id,i.product_name_raw,i.quantity,g.id group_id,g.name group_name,
      COALESCE(
        (SELECT short_name FROM product_short_names n WHERE n.key_type='offer_id' AND n.key_value=i.offer_id),
        (SELECT short_name FROM product_short_names n WHERE n.key_type='sku' AND n.key_value=i.sku)) short_name
      FROM orders o JOIN order_items i USING(shop_id,posting_number)
      LEFT JOIN product_groups g ON g.id=COALESCE(
        (SELECT group_id FROM product_group_members m WHERE m.key_type='offer_id' AND m.key_value=i.offer_id),
        (SELECT group_id FROM product_group_members m WHERE m.key_type='sku' AND m.key_value=i.sku))
      WHERE {ACTIVE} AND julianday(o.created_at)>=julianday(?)
        AND julianday(o.created_at)<julianday(?) {clause}""", [utc_start, utc_end] + shop_args)
    products = {}
    for row in rows:
        key = f"group:{row['group_id']}" if row["group_id"] else f"sku:{row['shop_id']}:{row['sku']}"
        item = products.setdefault(key, {"name": row["short_name"] or row["group_name"] or
                                             row["product_name_raw"] or row["sku"],
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
          WHERE {ACTIVE} AND julianday(o.created_at)>=julianday(?)
            AND julianday(o.created_at)<julianday(?) {clause}
          GROUP BY o.shop_id,o.posting_number
          ORDER BY o.created_at
        """, args)]
        complaint_clause, complaint_args = _record_clause(shop_id, "c")
        unresolved_complaints = db.execute(
            f"SELECT COUNT(*) FROM complaints c{complaint_clause}{' AND' if complaint_clause else ' WHERE'} c.resolved IS NOT 1",
            complaint_args).fetchone()[0]
        return_clause, return_args = _record_clause(shop_id, "r")
        placeholders = ",".join("?" for _ in RETURN_PENDING_STATUSES)
        pending_returns = db.execute(
            f"SELECT COUNT(*) FROM rfbs_return_records r{return_clause}{' AND' if return_clause else ' WHERE'} r.status_raw IN ({placeholders})",
            return_args + sorted(RETURN_PENDING_STATUSES)).fetchone()[0]
        stockouts, low_stock = _overview_stock_alerts(db, shop_id)
        top_products = _overview_top_products(db, utc_start, utc_end, shop_id)
    totals = {"orders": len(rows), "pieces": sum(row["pieces"] for row in rows),
              "cancelled_orders": sum(row["status_raw"] == "已取消" and row["shipped"] == 1 for row in rows)}
    totals["cancelled_pieces"] = sum(row["pieces"] for row in rows
                                     if row["status_raw"] == "已取消" and row["shipped"] == 1)
    totals["cancel_rate"] = totals["cancelled_orders"] / totals["orders"] if totals["orders"] else 0
    channels = []
    for channel in ("FBP", "realFBS", "WHD"):
        channel_rows = [row for row in rows if row["channel"] == channel]
        channels.append({"channel": channel, "orders": len(channel_rows),
                         "pieces": sum(row["pieces"] for row in channel_rows),
                         "cancelled_pieces": sum(row["pieces"] for row in channel_rows
                             if row["status_raw"] == "已取消" and row["shipped"] == 1)})
    bucket_dates = []
    cursor = _bucket_start(start, granularity)
    while cursor <= end:
        bucket_dates.append(cursor)
        cursor = _next_bucket(cursor, granularity)
    buckets = []
    for bucket_date in bucket_dates:
        next_date = _next_bucket(bucket_date, granularity)
        bucket_rows = [row for row in rows
                       if _bucket_start(_beijing_date(row["created_at"]), granularity) == bucket_date]
        channel_values = {}
        for channel in ("FBP", "realFBS", "WHD"):
            values = [row for row in bucket_rows if row["channel"] == channel]
            channel_values[channel] = {"orders": len(values), "gmv": _gmv_summary(values, shop_id)}
        buckets.append({"key": bucket_date.isoformat(),
                        "from": max(bucket_date, start).isoformat(),
                        "to": min(next_date - timedelta(days=1), end).isoformat(),
                        "orders": len(bucket_rows), "gmv": _gmv_summary(bucket_rows, shop_id),
                        "channels": channel_values})
    return {"range": {"from": start.isoformat(), "to": end.isoformat()},
            "granularity": granularity, "totals": totals, "channels": channels,
            "buckets": buckets, "gmv": _gmv_summary(rows, shop_id),
            "exceptions": {"unresolved_complaints": unresolved_complaints,
                           "pending_returns": pending_returns, "stockout_skus": stockouts,
                           "low_stock_skus": low_stock,
                           "anomaly_orders": sum(bool(row["data_anomaly"]) for row in rows)},
            "timeliness": _overview_timeliness(rows), "top_products": top_products,
            "data_through": max((row["created_at"] for row in rows), default=None)}


def _translated_order(row):
    order = dict(row)
    order["status_raw"] = STATUS_ZH.get(order["status_raw"], order["status_raw"])
    order["cancel_reason_raw"] = CANCEL_REASON_ZH.get(order["cancel_reason_raw"], order["cancel_reason_raw"])
    return order


@app.get("/api/orders")
def orders(shop_id: int = 0, channel: str = "", q: str = "", page: int = 1, size: int = 30,
           date_from: Annotated[str | None, Query(alias="from")] = None,
           date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    where, args = ["julianday(o.created_at)>=julianday(?)", "julianday(o.created_at)<julianday(?)"], [utc_start, utc_end]
    if shop_id in (1, 2):
        where.append("o.shop_id=?"); args.append(shop_id)
    if channel:
        if channel not in CHANNELS: raise HTTPException(400, "未知渠道")
        where.append("o.channel=?"); args.append(channel)
    if q:
        where.append("(o.posting_number LIKE ? OR EXISTS(SELECT 1 FROM order_items x WHERE x.shop_id=o.shop_id AND x.posting_number=o.posting_number AND (x.sku LIKE ? OR x.offer_id LIKE ? OR x.product_name_raw LIKE ?)))")
        args.extend([f"%{q}%"] * 4)
    page, size = max(page, 1), min(max(size, 1), 100)
    sql_where = " AND ".join(where)
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM orders o WHERE {sql_where}", args).fetchone()[0]
        result = [_translated_order(row) for row in db.execute(f"""
          SELECT o.shop_id,s.name shop_name,o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at,
            o.status_raw,o.cancel_reason_raw,o.shipped,o.data_anomaly,o.amount_original,o.amount_currency
          FROM orders o JOIN shops s ON s.id=o.shop_id
          WHERE {sql_where} ORDER BY o.created_at DESC LIMIT ? OFFSET ?
        """, args + [size, (page - 1) * size])]
        for order in result:
            order["items"] = [dict(row) for row in db.execute(
                """SELECT sku,offer_id,COALESCE(
                  (SELECT short_name FROM product_short_names n WHERE n.key_type='offer_id' AND n.key_value=order_items.offer_id),
                  (SELECT short_name FROM product_short_names n WHERE n.key_type='sku' AND n.key_value=order_items.sku),
                  product_name_raw) product_name_raw,product_name_raw product_name_original,
                  quantity,unit_price,price_currency FROM order_items
                  WHERE shop_id=? AND posting_number=? ORDER BY sku""",
                (order["shop_id"], order["posting_number"]))]
            order["sku_types"] = len(order["items"])
            order["pieces"] = sum(item["quantity"] for item in order["items"])
    return {"items": result, "total": total, "page": page, "size": size}


@app.get("/api/risk")
def risk(shop_id: int = 0, grouped: bool = False,
         date_from: Annotated[str | None, Query(alias="from")] = None,
         date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    start, end, utc_start, utc_end = _overview_range(date_from, date_to)
    clause, args = _shop_clause(shop_id)
    group_join = """LEFT JOIN product_groups g ON g.id=COALESCE(
      (SELECT group_id FROM product_group_members m WHERE m.key_type='offer_id' AND m.key_value=i.offer_id),
      (SELECT group_id FROM product_group_members m WHERE m.key_type='sku' AND m.key_value=i.sku))""" if grouped else ""
    group_key = "CASE WHEN g.id IS NULL THEN 'sku:'||COALESCE(i.sku,'') ELSE 'group:'||g.id END" if grouped else "'sku:'||COALESCE(i.sku,'')"
    group_name = "g.name" if grouped else "NULL"
    unclaimed = ",".join("?" for _ in BUYER_UNCLAIMED_REASONS)
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,s.name shop_name,o.channel,{group_key} item_key,{group_name} group_name,
            GROUP_CONCAT(DISTINCT i.sku) member_skus,
            GROUP_CONCAT(DISTINCT COALESCE(i.sku,'')||' '||COALESCE(i.offer_id,'')||' '||COALESCE(i.product_name_raw,'')) search_text,
            MAX(COALESCE(
            (SELECT short_name FROM product_short_names n WHERE n.key_type='offer_id' AND n.key_value=i.offer_id),
            (SELECT short_name FROM product_short_names n WHERE n.key_type='sku' AND n.key_value=i.sku),
            i.product_name_raw)) product_name,
            SUM(i.quantity) valid_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 THEN i.quantity ELSE 0 END) cancelled_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 AND o.cancel_reason_raw IN ({unclaimed}) THEN i.quantity ELSE 0 END) unclaimed_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 AND o.cancel_reason_raw='Отправление не прошло таможенное оформление' THEN i.quantity ELSE 0 END) customs_pieces
          FROM orders o JOIN shops s ON s.id=o.shop_id JOIN order_items i USING(shop_id,posting_number)
          {group_join} WHERE {ACTIVE} AND julianday(o.created_at)>=julianday(?)
            AND julianday(o.created_at)<julianday(?){clause}
          GROUP BY o.shop_id,o.channel,{group_key},{group_name}
        """, [*BUYER_UNCLAIMED_REASONS, utc_start, utc_end, *args])]

    def stats(values):
        result = {key: sum(int(row[f"{key}_pieces"] or 0) for row in values)
                  for key in ("valid", "cancelled", "unclaimed", "customs")}
        for key in ("cancelled", "unclaimed", "customs"):
            result[f"{key}_rate"] = result[key] / result["valid"] if result["valid"] else None
        return result

    items = []
    for item_key in sorted({(row["shop_id"], row["item_key"]) for row in rows}):
        values = [row for row in rows if (row["shop_id"], row["item_key"]) == item_key]
        skus = sorted({sku for row in values for sku in (row["member_skus"] or "").split(",") if sku})
        items.append({"shop_id": values[0]["shop_id"], "shop_name": values[0]["shop_name"],
                      "item_key": item_key[1], "sku": skus[0] if len(skus) == 1 else "、".join(skus),
                      "group_name": values[0]["group_name"], "member_count": len(skus),
                      "product_name": max((row["product_name"] or "" for row in values), default=""),
                      "search_text": " ".join(row["search_text"] or "" for row in values),
                      "total": stats(values),
                      "channels": {channel: stats([row for row in values if row["channel"] == channel])
                                   if any(row["channel"] == channel for row in values) else None
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
          WHERE o.status_raw='已取消' AND o.shipped=1 AND julianday(o.created_at)>=julianday(?)
            AND julianday(o.created_at)<julianday(?){clause}{extra}
          GROUP BY o.shop_id,o.channel,reason_raw ORDER BY pieces DESC""", [utc_start, utc_end, *args])]
        details = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,o.channel,
          o.posting_number,SUM(i.quantity) pieces FROM orders o JOIN shops s ON s.id=o.shop_id
          JOIN order_items i USING(shop_id,posting_number)
          WHERE o.status_raw='已取消' AND o.shipped=1 AND julianday(o.created_at)>=julianday(?)
            AND julianday(o.created_at)<julianday(?){clause}{extra}
          GROUP BY o.shop_id,o.channel,o.posting_number ORDER BY o.posting_number""",
          [utc_start, utc_end, *args])] if reason else []
    items = []
    for reason_raw in sorted({row["reason_raw"] for row in rows}):
        values = [row for row in rows if row["reason_raw"] == reason_raw]
        items.append({"reason_raw": reason_raw,
                      "reason_name": RISK_REASON_ZH.get(reason_raw, reason_raw),
                      "total": {"orders": sum(row["orders"] for row in values),
                                "pieces": sum(row["pieces"] for row in values)},
                      "channels": {channel: {"orders": sum(row["orders"] for row in values if row["channel"] == channel),
                                             "pieces": sum(row["pieces"] for row in values if row["channel"] == channel)}
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
    base_where = f"{ACTIVE} AND julianday(o.created_at)>=julianday(?) AND julianday(o.created_at)<julianday(?){clause}"
    base_args = [utc_start, utc_end, *shop_args]
    detail_where, detail_args = base_where, list(base_args)
    if q.strip():
        detail_where += " AND o.posting_number LIKE ?"
        detail_args.append(f"%{q.strip()}%")
    with connect() as db:
        all_rows = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,
          o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at
          FROM orders o JOIN shops s ON s.id=o.shop_id WHERE {base_where}
          ORDER BY julianday(o.created_at) DESC,o.posting_number DESC""", base_args)]
        through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {base_where}", base_args).fetchone()[0]
        total = db.execute(f"SELECT COUNT(*) FROM orders o WHERE {detail_where}", detail_args).fetchone()[0]
        rows = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,
          o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at
          FROM orders o JOIN shops s ON s.id=o.shop_id WHERE {detail_where}
          ORDER BY julianday(o.created_at) DESC,o.posting_number DESC LIMIT ? OFFSET ?""",
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


@app.get("/api/complaints")
def complaints(shop_id: int = 0, q: str = "", status: str = "", page: int = 1, size: int = 50,
               date_from: Annotated[str | None, Query(alias="from")] = None,
               date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    if status not in {"", "open", "closed", "unset"}:
        raise HTTPException(400, "完结状态无效")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    where, args = ["julianday(c.complaint_at)>=julianday(?)", "julianday(c.complaint_at)<julianday(?)"], [utc_start, utc_end]
    if shop_id in (1, 2): where.append("c.shop_id=?"); args.append(shop_id)
    if q.strip():
        where.append("(c.posting_number LIKE ? OR c.complaint_number LIKE ?)")
        args += [f"%{q.strip()}%", f"%{q.strip()}%"]
    if status in {"open", "closed", "unset"}:
        where.append("c.resolved IS " + {"open": "0", "closed": "1", "unset": "NULL"}[status])
    page, size = _paging(page, size)
    sql = " AND ".join(where)
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM complaints c WHERE {sql}", args).fetchone()[0]
        items = [dict(row) for row in db.execute(f"""SELECT c.*,s.name shop_name
          FROM complaints c JOIN shops s ON s.id=c.shop_id WHERE {sql}
          ORDER BY c.complaint_at DESC LIMIT ? OFFSET ?""", args + [size, (page-1)*size])]
        through = db.execute(f"SELECT MAX(c.complaint_at) FROM complaints c WHERE {sql}", args).fetchone()[0]
    return {"items": items, "total": total, "page": page, "size": size,
            "data_through": through}


@app.post("/api/complaints")
@app.put("/api/complaints")
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
    amount = body.get("compensation_amount")
    if amount not in (None, ""):
        try: amount = float(amount)
        except ValueError as error: raise HTTPException(400, "赔付金额无效") from error
    else:
        amount = None
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as db:
        shop = db.execute("SELECT settlement_currency FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not db.execute("SELECT 1 FROM orders WHERE shop_id=? AND posting_number=?", (shop_id, posting)).fetchone():
            raise HTTPException(400, "未找到该店铺订单")
        currency = str(body.get("compensation_currency") or (shop[0] if amount is not None else "")).upper() or None
        exists = db.execute("SELECT created_at FROM complaints WHERE shop_id=? AND complaint_number=?",
                            (shop_id, number)).fetchone()
        db.execute("""INSERT INTO complaints VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(shop_id,complaint_number) DO UPDATE SET
          posting_number=excluded.posting_number,complaint_at=excluded.complaint_at,channel=excluded.channel,
          resolved=excluded.resolved,package_returned=excluded.package_returned,
          compensation_amount=excluded.compensation_amount,compensation_currency=excluded.compensation_currency,
          notes=excluded.notes,updated_at=excluded.updated_at""",
          (shop_id, number, posting, complaint_at, channel,
           None if body.get("resolved") is None else int(body["resolved"]),
           None if body.get("package_returned") is None else int(body["package_returned"]),
           amount, currency, str(body.get("notes") or ""), exists[0] if exists else now, now))
        if body.get("resolved") is True:
            db.execute("""INSERT INTO order_after_sales VALUES(?,?,?,?)
              ON CONFLICT(shop_id,posting_number) DO UPDATE SET status='已完结',updated_at=excluded.updated_at""",
                       (shop_id, posting, "已完结", now))
    return {"ok": True}


@app.get("/api/product-rules")
def product_rules():
    with connect() as db:
        short_names = [dict(row) for row in db.execute("SELECT * FROM product_short_names ORDER BY key_type,key_value")]
        groups = [dict(row) for row in db.execute("""SELECT g.id,g.name,m.key_type,m.key_value FROM product_groups g
          LEFT JOIN product_group_members m ON m.group_id=g.id ORDER BY g.id,m.key_type,m.key_value""")]
        brands = [dict(row) for row in db.execute("""SELECT b.*,
          EXISTS(SELECT 1 FROM brand_rules x WHERE x.id<>b.id AND x.enabled=1 AND b.enabled=1
            AND lower(x.keyword)=lower(b.keyword)) conflict FROM brand_rules b ORDER BY priority DESC,id""")]
        products = [dict(row) for row in db.execute("""SELECT sku,offer_id,MAX(product_name_raw) product_name
          FROM order_items GROUP BY sku,offer_id ORDER BY product_name LIMIT 500""")]
    enabled = [row for row in brands if row["enabled"]]
    for product in products:
        haystack = " ".join(str(product.get(key) or "") for key in ("product_name", "sku", "offer_id")).lower()
        product["matched_brand"] = next(
            (row["brand_name"] for row in enabled if row["keyword"].lower() in haystack), None)
    return {"short_names": short_names, "groups": groups, "brands": brands, "products": products,
            "key_note": "真实数据中SKU和货号均存在一对多历史记录，请明确选择匹配键"}


@app.put("/api/product-rules")
async def save_product_rule(request: Request):
    body = await request.json()
    kind = body.get("kind")
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as db:
        if kind == "short_name":
            key_type, key_value = body.get("key_type"), str(body.get("key_value") or "").strip()
            name = str(body.get("short_name") or "").strip()
            if key_type not in {"sku", "offer_id"} or not key_value or not name:
                raise HTTPException(400, "短名称规则不完整")
            db.execute("""INSERT INTO product_short_names VALUES(?,?,?,?)
              ON CONFLICT(key_type,key_value) DO UPDATE SET short_name=excluded.short_name,updated_at=excluded.updated_at""",
                       (key_type, key_value, name, now))
        elif kind == "group":
            name = str(body.get("name") or "").strip()
            members = body.get("members") or []
            if not name or not members: raise HTTPException(400, "合并组名称和成员不能为空")
            group = db.execute("SELECT id FROM product_groups WHERE name=?", (name,)).fetchone()
            group_id = group[0] if group else db.execute(
                "INSERT INTO product_groups(name,created_at,updated_at) VALUES(?,?,?)", (name, now, now)).lastrowid
            db.execute("DELETE FROM product_group_members WHERE group_id=?", (group_id,))
            for member in members:
                if member.get("key_type") not in {"sku", "offer_id"} or not str(member.get("key_value") or "").strip():
                    raise HTTPException(400, "合并组成员无效")
                db.execute("INSERT INTO product_group_members VALUES(?,?,?)",
                           (group_id, member["key_type"], str(member["key_value"]).strip()))
        elif kind == "brand":
            brand, keyword = str(body.get("brand_name") or "").strip(), str(body.get("keyword") or "").strip()
            if not brand or not keyword: raise HTTPException(400, "品牌和关键词不能为空")
            db.execute("INSERT INTO brand_rules(brand_name,keyword,priority,enabled,updated_at) VALUES(?,?,?,?,?)",
                       (brand, keyword, int(body.get("priority") or 0), int(bool(body.get("enabled", True))), now))
        elif kind == "ungroup":
            db.execute("DELETE FROM product_group_members WHERE key_type=? AND key_value=?",
                       (body.get("key_type"), str(body.get("key_value") or "")))
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
    filters, args = ["julianday(r.occurred_at)>=julianday(?)", "julianday(r.occurred_at)<julianday(?)"], [utc_start, utc_end]
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
          CAST(json_extract(r.payload,'$.product.offer_id') AS TEXT) offer_id,
          COALESCE(
            (SELECT short_name FROM product_short_names n WHERE n.key_type='offer_id' AND n.key_value=CAST(json_extract(r.payload,'$.product.offer_id') AS TEXT)),
            (SELECT short_name FROM product_short_names n WHERE n.key_type='sku' AND n.key_value=r.sku)) short_name
          FROM return_records r JOIN shops s ON s.id=r.shop_id{where}
          ORDER BY r.occurred_at DESC LIMIT ? OFFSET ?""", args + [size, (page - 1) * size]).fetchall()
        through = db.execute(f"SELECT MAX(r.occurred_at) FROM return_records r{where}", args).fetchone()[0]
    items = []
    for row in records:
        payload = json.loads(row["payload"])
        product, visual = payload.get("product") or {}, payload.get("visual") or {}
        status = visual.get("status") or {}
        status = status.get("display_name") if isinstance(status, dict) else status
        items.append({"shop_id": row["shop_id"], "shop_name": row["shop_name"],
                      "occurred_at": row["occurred_at"], "posting_number": row["posting_number"],
                      "sku": row["sku"], "offer_id": row["offer_id"],
                      "product_name": row["short_name"] or product.get("name"),
                      "quantity": product.get("quantity"),
                      "reason": CANCEL_REASON_ZH.get(payload.get("return_reason_name"), payload.get("return_reason_name")),
                      "reason_raw": payload.get("return_reason_name"),
                      "status": RETURN_STATUS_ZH.get(status, status),
                      "compensation_status": payload.get("compensation_status") or payload.get("money_return_state_name"),
                      "product_amount": product.get("price") or product.get("amount"),
                      "product_currency": product.get("currency_code") or product.get("currency"),
                      "logistic_return_at": payload.get("logistic_return_at") or payload.get("returned_at"),
                      "buyer_comment_raw": payload.get("buyer_comment") or payload.get("comment"),
                      "type": payload.get("type")})
    return {"summary": {"records": total, "shops": totals}, "items": items, "total": total,
            "page": page, "size": size, "data_through": through}


@app.get("/api/rfbs-returns")
def rfbs_returns(shop_id: int = 0, page: int = 1, size: int = 50, q: str = "",
                 date_from: Annotated[str | None, Query(alias="from")] = None,
                 date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    filters, args = ["julianday(r.created_at)>=julianday(?)", "julianday(r.created_at)<julianday(?)"], [utc_start, utc_end]
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
        rows = db.execute(f"""SELECT r.shop_id,s.name shop_name,r.return_id,
          r.return_number,r.created_at,r.posting_number,r.offer_id,r.sku,r.product_name,
          r.status_raw,r.status_name,r.quantity,r.reason_raw,r.reason_name,
          r.compensation_status,r.product_amount,r.product_currency,r.logistic_return_at,
          r.buyer_comment_raw,r.payload,COALESCE(
            (SELECT short_name FROM product_short_names n WHERE n.key_type='offer_id' AND n.key_value=r.offer_id),
            (SELECT short_name FROM product_short_names n WHERE n.key_type='sku' AND n.key_value=r.sku),
            r.product_name) display_product_name FROM rfbs_return_records r JOIN shops s ON s.id=r.shop_id{where}
          ORDER BY r.created_at DESC,r.return_id DESC LIMIT ? OFFSET ?""",
          args + [size, (page - 1) * size]).fetchall()
        through = db.execute(f"SELECT MAX(r.created_at) FROM rfbs_return_records r{where}", args).fetchone()[0]
    items = []
    for raw in rows:
        item = dict(raw)
        item["product_name"] = item.pop("display_product_name")
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
    return {"summary": {"records": total, "shops": totals}, "items": items, "total": total,
            "page": page, "size": size, "data_through": through}


def _latest_snapshots(db, table, shop_id):
    where, args = _record_clause(shop_id, "r")
    return db.execute(f"""SELECT r.shop_id,s.name shop_name,r.observed_at,r.payload FROM {table} r
      JOIN shops s ON s.id=r.shop_id JOIN (
        SELECT shop_id,MAX(observed_at) observed_at FROM {table} GROUP BY shop_id
      ) latest ON latest.shop_id=r.shop_id AND latest.observed_at=r.observed_at{where}
      ORDER BY r.shop_id,r.record_key""", args).fetchall()


@app.get("/api/stock")
def stock(shop_id: int = 0, page: int = 1, size: int = 50):
    page, size = _paging(page, size)
    with connect() as db:
        records = _latest_snapshots(db, "stock_snapshots", shop_id)
        sales = {(row["shop_id"], row["sku"]): dict(row) for row in db.execute(f"""SELECT i.shop_id,i.sku,
          SUM(CASE WHEN o.created_at>=datetime('now','-7 days') THEN i.quantity ELSE 0 END) sales_7,
          SUM(CASE WHEN o.created_at>=datetime('now','-30 days') THEN i.quantity ELSE 0 END) sales_30
          FROM order_items i JOIN orders o USING(shop_id,posting_number)
          WHERE {ACTIVE.replace('o.', 'o.')}{_shop_clause(shop_id)[0]}
          GROUP BY i.shop_id,i.sku""", _shop_clause(shop_id)[1])}
    items, shops = [], {}
    for row in records:
        payload = json.loads(row["payload"])
        for value in payload.get("stocks") or []:
            items.append({"shop_id": row["shop_id"], "shop_name": row["shop_name"],
              "observed_at": row["observed_at"], "product_id": payload.get("product_id"),
              "offer_id": payload.get("offer_id"), "sku": str(value.get("sku") or payload.get("product_id") or ""),
              "warehouse_id": ",".join(map(str, value.get("warehouse_ids") or [])),
              "present": int(value.get("present") or 0), "reserved": int(value.get("reserved") or 0),
              "types": value.get("type") or value.get("shipment_type") or "", "source": "API快照"})
    channel_names = {"fbp": "FBP", "rfbs": "realFBS", "fbo": "WHD"}
    grouped = {}
    for item in items:
        if item["present"] <= 0 and item["reserved"] <= 0:
            continue
        key = item["shop_id"], item["sku"]
        group = grouped.setdefault(key, {"shop_id": item["shop_id"], "shop_name": item["shop_name"],
          "sku": item["sku"], "offer_id": item.get("offer_id"), "product_id": item.get("product_id"),
          "_channels": {}})
        group["offer_id"] = group["offer_id"] or item.get("offer_id")
        group["product_id"] = group["product_id"] or item.get("product_id")
        channel = channel_names.get(str(item.get("types") or "").lower(), "库存事件")
        source = group["_channels"].setdefault(channel, {}).setdefault(item["source"], {
          "channel": channel, "source": item["source"], "present": 0, "reserved": 0,
          "observed_at": item["observed_at"], "warehouses": set()})
        source["present"] += item["present"]
        source["reserved"] += item["reserved"]
        source["observed_at"] = max(source["observed_at"] or "", item["observed_at"] or "")
        source["warehouses"].update(filter(None, str(item.get("warehouse_id") or "").split(",")))
    cards = []
    channel_order = {"FBP": 0, "realFBS": 1, "WHD": 2, "库存事件": 3}
    for group in grouped.values():
        channels = [max(sources.values(), key=lambda value: value["observed_at"] or "")
                    for sources in group.pop("_channels").values()]
        for channel in channels:
            channel["warehouse_id"] = ", ".join(sorted(channel.pop("warehouses")))
        channels.sort(key=lambda value: channel_order[value["channel"]])
        sold = sales.get((group["shop_id"], group["sku"]), {})
        group["channels"] = channels
        group["present"] = sum(value["present"] for value in channels)
        group["reserved"] = sum(value["reserved"] for value in channels)
        group["sales_7"] = int(sold.get("sales_7") or 0)
        group["sales_30"] = int(sold.get("sales_30") or 0)
        group["days_available"] = round(group["present"] / (group["sales_30"] / 30), 1) if group["sales_30"] else None
        group["observed_at"] = max(value["observed_at"] for value in channels)
        summary = shops.setdefault(group["shop_id"], {"shop_id": group["shop_id"],
          "shop_name": group["shop_name"], "products": 0, "present": 0, "reserved": 0})
        summary["products"] += 1; summary["present"] += group["present"]; summary["reserved"] += group["reserved"]
        cards.append(group)
    cards.sort(key=lambda value: (value["shop_id"], value["sku"]))
    total = len(cards); start = (page - 1) * size
    through = max((item["observed_at"] for item in cards), default=None)
    return {"summary": {"records": total, "shops": list(shops.values())}, "items": cards[start:start + size],
            "total": total, "page": page, "size": size, "data_through": through,
            "formula": "预计可售天数=当前可售库存÷(近30天有效货件数÷30)；无销量时无法估算"}


@app.get("/api/stock/history")
def stock_history(shop_id: int = 0, page: int = 1, size: int = 50):
    where, args = _record_clause(shop_id, "h")
    where += " AND h.source IN ('api','API快照')" if where else " WHERE h.source IN ('api','API快照')"
    page, size = _paging(page, size)
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM stock_history h{where}", args).fetchone()[0]
        items = [dict(row) for row in db.execute(f"""SELECT h.shop_id,s.name shop_name,h.source,
          h.warehouse_id,h.sku,h.present,h.reserved,h.occurred_at FROM stock_history h
          JOIN shops s ON s.id=h.shop_id{where} ORDER BY h.occurred_at DESC LIMIT ? OFFSET ?""",
          args + [size, (page-1)*size])]
    return {"items": items, "total": total, "page": page, "size": size}


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
          SELECT r.*,s.name shop_name FROM sync_runs r JOIN shops s ON s.id=r.shop_id ORDER BY r.id DESC LIMIT 100
        """)]


@app.get("/api/sync/{run_id}")
def sync_run(run_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM sync_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "拉取任务不存在")
    return dict(row)


@app.get("/api/auto-sync-settings")
def auto_sync_settings():
    with connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM shop_auto_sync_settings WHERE module IN ('orders','returns','stock') "
            "ORDER BY shop_id,CASE module WHEN 'orders' THEN 1 WHEN 'returns' THEN 2 ELSE 3 END")]


def save_auto_sync_settings(values):
    if set(values) == SYNC_MODULES:
        values = {str(shop_id): values for shop_id in (1, 2)}
    if set(values) != {"1", "2"} or any(set(values[str(shop_id)]) != SYNC_MODULES for shop_id in (1, 2)):
        raise ValueError("必须分别提交两个店铺的三个模块设置")
    settings = []
    for shop_id in (1, 2):
        for module in ("orders", "returns", "stock"):
            value = values[str(shop_id)][module]
            run_time = str(value.get("run_time") or "")
            if len(run_time) != 5:
                raise ValueError("拉取时间格式无效")
            try:
                datetime.strptime(run_time, "%H:%M")
                range_days = int(value.get("range_days") or 0)
            except (TypeError, ValueError) as error:
                raise ValueError("拉取时间或范围无效") from error
            if not 1 <= range_days <= 365:
                raise ValueError("自动拉取范围必须为 1 至 365 天")
            settings.append((int(bool(value.get("enabled"))), run_time,
                             1 if module == "stock" else range_days, shop_id, module))
    with transaction() as db:
        db.executemany("""UPDATE shop_auto_sync_settings SET enabled=?,run_time=?,range_days=?
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
    if module == "stock":
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
    try:
        for index, (start, end) in enumerate(ranges, 1):
            with transaction() as db:
                db.execute("UPDATE sync_runs SET current_from=?,current_to=? WHERE id=?",
                           (start.isoformat(), end.isoformat(), run_id))
            result = sync_module(module, shop_id, start, end)
            records += int(result.get("records") or 0)
            with transaction() as db:
                db.execute("UPDATE sync_runs SET progress_done=?,records=?,data_through=? WHERE id=?",
                           (index, records, end.isoformat(), run_id))
    except Exception as error:
        message = str(error)[:500]
        with transaction() as db:
            db.execute("""UPDATE sync_runs SET finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'),
              status='failed',error=? WHERE id=?""", (message, run_id))
        try:
            send_sync_failure(shop_id, module, ranges[0][0], ranges[-1][1], message)
        except Exception:
            pass
        return
    with transaction() as db:
        db.execute("""UPDATE sync_runs SET finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'),
          data_through=?,status='success',current_from=NULL,current_to=NULL WHERE id=?""",
                   (ranges[-1][1].isoformat(), run_id))


def _create_sync_job(module, shop_id, start, end, run_source="manual", scheduled_date=None):
    ranges = _sync_ranges(module, start, end)
    with transaction() as db:
        if run_source == "auto" and db.execute("""SELECT 1 FROM sync_runs
          WHERE shop_id=? AND module=? AND scheduled_date=? AND run_source='auto'
          AND status='failed' AND started_at>=strftime('%Y-%m-%dT%H:%M:%SZ','now','-5 minutes')""",
                                                     (shop_id, module, scheduled_date)).fetchone():
            return None
        cursor = db.execute("""INSERT OR IGNORE INTO sync_runs(
          shop_id,module,range_from,range_to,status,progress_total,run_source,scheduled_date)
          VALUES(?,?,?,?, 'running',?,?,?)""",
                            (shop_id, module, start.isoformat(), end.isoformat(), len(ranges),
                             run_source, scheduled_date))
        if cursor.rowcount == 0:
            return None
        run_id = cursor.lastrowid
    threading.Thread(target=_run_sync_job, args=(run_id, module, shop_id, ranges), daemon=True).start()
    return run_id


def run_auto_sync_once(now=None):
    now = now or datetime.now(BEIJING)
    today = now.date().isoformat()
    with connect() as db:
        settings = db.execute("""SELECT * FROM shop_auto_sync_settings
          WHERE enabled=1 AND module IN ('orders','returns','stock') ORDER BY shop_id,rowid""").fetchall()
    started = []
    for setting in settings:
        if now.strftime("%H:%M") < setting["run_time"]:
            continue
        end = now
        start = (now - timedelta(days=setting["range_days"] - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        run_id = _create_sync_job(setting["module"], setting["shop_id"], start, end, "auto", today)
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
            range_clause += " AND julianday(o.created_at)>=julianday(?)"; args.append(utc_start)
        if utc_end:
            range_clause += f" AND julianday(o.created_at){'<' if exclusive_end else '<='}julianday(?)"; args.append(utc_end)
    def lines():
        with connect() as db:
            shops_value = [dict(r) for r in db.execute("SELECT id,name FROM shops ORDER BY id")
                           if shop_id not in (1, 2) or r["id"] == shop_id]
            through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {ACTIVE}{clause}{range_clause}", args).fetchone()[0]
            yield json.dumps({"type":"metadata","shops":shops_value,"timezone":"数据库UTC；显示北京时间",
                              "range":{"from":export_range[0],"to":export_range[1]} if export_range else {"from":None,"to":None},
                              "order_definition":"COUNT DISTINCT posting_number","piece_definition":"SUM quantity",
                              "filter":"剔除状态为已取消且无发货证据的订单","data_through":through}, ensure_ascii=False) + "\n"
            for row in db.execute(f"""
              SELECT o.shop_id,s.name shop,o.posting_number,o.channel,o.created_at,o.status_raw,
                o.cancel_reason_raw,o.amount_original,o.amount_currency
              FROM orders o JOIN shops s ON s.id=o.shop_id
              WHERE {ACTIVE}{clause}{range_clause} ORDER BY o.created_at
            """, args):
                yield json.dumps(_translated_order(row), ensure_ascii=False) + "\n"
    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Content-Disposition":"attachment; filename=orders.jsonl"})


@app.get("/api/export/{module}")
def export_module(module: str, shop_id: int = 0, date_from: str = "", date_to: str = ""):
    if module not in {"risk", "timeliness", "returns", "complaints", "stock", "rules"}:
        raise HTTPException(404, "未知导出模块")
    if shop_id not in (0, 1, 2): raise HTTPException(400, "未知店铺")
    tables = {
        "risk": ("orders o JOIN order_items i USING(shop_id,posting_number)", "o.created_at",
                 "o.shop_id,o.channel,o.posting_number,i.sku,i.offer_id,i.quantity,o.status_raw,o.cancel_reason_raw,COALESCE((SELECT g.name FROM product_group_members m JOIN product_groups g ON g.id=m.group_id WHERE (m.key_type='sku' AND m.key_value=i.sku) OR (m.key_type='offer_id' AND m.key_value=i.offer_id) ORDER BY m.key_type='sku' DESC LIMIT 1),i.sku,i.offer_id) analysis_group"),
        "timeliness": ("orders o", "o.created_at",
                 "o.shop_id,o.channel,o.posting_number,o.created_at,o.shipped_at,o.delivered_at"),
        "returns": ("rfbs_return_records o", "o.created_at",
                 "o.shop_id,o.return_id,o.return_number,o.created_at,o.posting_number,o.sku,o.offer_id,o.product_name,o.status_raw,o.status_name,o.quantity,o.reason_raw,o.reason_name,o.compensation_status,o.product_amount,o.product_currency,o.logistic_return_at,o.buyer_comment_raw"),
        "complaints": ("complaints o", "o.complaint_at",
                 "o.shop_id,o.posting_number,o.complaint_number,o.complaint_at,o.channel,o.resolved,o.package_returned,o.compensation_amount,o.compensation_currency,o.created_at,o.updated_at"),
        "stock": ("stock_history o", "o.occurred_at",
                 "o.shop_id,o.source,o.warehouse_id,o.sku,o.present,o.reserved,o.occurred_at"),
        "rules": ("brand_rules o", "o.updated_at", "o.id,o.brand_name,o.keyword,o.priority,o.enabled,o.updated_at"),
    }
    table, date_column, fields = tables[module]
    where, args = ["1=1"], []
    alias = "o"
    export_range = _export_range(date_from, date_to) if module != "rules" else None
    if shop_id in (1, 2) and module != "rules":
        where.append(f"{alias}.shop_id=?"); args.append(shop_id)
    if export_range:
        _, _, utc_start, utc_end, exclusive_end = export_range
        if utc_start:
            where.append(f"julianday({date_column})>=julianday(?)"); args.append(utc_start)
        if utc_end:
            where.append(f"julianday({date_column}){'<' if exclusive_end else '<='}julianday(?)"); args.append(utc_end)
    if module in {"risk", "timeliness"}:
        where.append(ACTIVE)
    if module == "stock":
        where.append("o.source IN ('api','API快照')")
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
                        legacy_where.append("julianday(occurred_at)>=julianday(?)"); legacy_args.append(utc_start)
                    if utc_end:
                        legacy_where.append(f"julianday(occurred_at){'<' if exclusive_end else '<='}julianday(?)"); legacy_args.append(utc_end)
                for row in db.execute(f"SELECT shop_id,occurred_at,posting_number,sku,payload FROM return_records WHERE {' AND '.join(legacy_where)} ORDER BY occurred_at", legacy_args):
                    value, payload = dict(row), json.loads(row["payload"])
                    product, visual = payload.get("product") or {}, payload.get("visual") or {}
                    status = visual.get("status") or {}
                    value.pop("payload")
                    value.update({"record_type": "取消明细", "quantity": product.get("quantity"),
                                  "product_name": product.get("name"), "reason_raw": payload.get("return_reason_name"),
                                  "status": status.get("display_name") if isinstance(status, dict) else status})
                    yield json.dumps(value, ensure_ascii=False) + "\n"
            if module == "rules":
                for rule_type, query in (
                    ("中文短名称", "SELECT key_type,key_value,short_name,updated_at FROM product_short_names"),
                    ("合并组", "SELECT g.name,m.key_type,m.key_value,g.updated_at FROM product_groups g LEFT JOIN product_group_members m ON m.group_id=g.id"),
                ):
                    for row in db.execute(query):
                        yield json.dumps({"rule_type": rule_type, **dict(row)}, ensure_ascii=False) + "\n"
            for row in db.execute(f"SELECT {fields} FROM {table} WHERE {sql_where} ORDER BY {date_column}", args):
                value = dict(row)
                if module == "returns":
                    value["record_type"] = "退货明细"
                elif module == "rules":
                    value["rule_type"] = "品牌规则"
                yield json.dumps(value, ensure_ascii=False) + "\n"
    return StreamingResponse(lines(), media_type="application/x-ndjson",
      headers={"Content-Disposition": f"attachment; filename={module}.jsonl"})
