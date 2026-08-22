import hashlib
import hmac
import json
import secrets
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response
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


@app.get("/api/summary")
def summary(shop_id: int = 0):
    clause, args = _shop_clause(shop_id)
    with connect() as db:
        totals = dict(db.execute(f"""
          SELECT COUNT(DISTINCT o.posting_number) orders,
            COALESCE(SUM(i.quantity),0) pieces,
            COUNT(DISTINCT CASE WHEN o.status_raw='已取消' AND o.shipped=1 THEN o.posting_number END) cancelled_orders,
            COALESCE(SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 THEN i.quantity ELSE 0 END),0) cancelled_pieces
          FROM orders o JOIN order_items i USING(shop_id,posting_number)
          WHERE {ACTIVE}{clause}
        """, args).fetchone())
        by_channel = [dict(row) for row in db.execute(f"""
          SELECT o.channel, COUNT(DISTINCT o.posting_number) orders, SUM(i.quantity) pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 THEN i.quantity ELSE 0 END) cancelled_pieces
          FROM orders o JOIN order_items i USING(shop_id,posting_number)
          WHERE {ACTIVE}{clause} GROUP BY o.channel ORDER BY CASE o.channel WHEN 'FBP' THEN 1 WHEN 'realFBS' THEN 2 ELSE 3 END
        """, args)]
        through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE 1=1{clause}", args).fetchone()[0]
    totals["cancel_rate"] = totals["cancelled_pieces"] / totals["pieces"] if totals["pieces"] else 0
    return {"totals": totals, "channels": by_channel, "data_through": through}


def _translated_order(row):
    order = dict(row)
    order["status_raw"] = STATUS_ZH.get(order["status_raw"], order["status_raw"])
    order["cancel_reason_raw"] = CANCEL_REASON_ZH.get(order["cancel_reason_raw"], order["cancel_reason_raw"])
    return order


@app.get("/api/orders")
def orders(shop_id: int = 0, channel: str = "", q: str = "", page: int = 1, size: int = 30):
    where, args = ["1=1"], []
    if shop_id in (1, 2):
        where.append("o.shop_id=?"); args.append(shop_id)
    if channel:
        if channel not in CHANNELS: raise HTTPException(400, "未知渠道")
        where.append("o.channel=?"); args.append(channel)
    if q:
        where.append("(o.posting_number LIKE ? OR EXISTS(SELECT 1 FROM order_items x WHERE x.shop_id=o.shop_id AND x.posting_number=o.posting_number AND (x.sku LIKE ? OR x.product_name_raw LIKE ?)))")
        args.extend([f"%{q}%"] * 3)
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
    return {"items": result, "total": total, "page": page, "size": size}


@app.get("/api/risk")
def risk(shop_id: int = 0, grouped: bool = False):
    clause, args = _shop_clause(shop_id)
    group_join = """LEFT JOIN product_groups g ON g.id=COALESCE(
      (SELECT group_id FROM product_group_members m WHERE m.key_type='offer_id' AND m.key_value=i.offer_id),
      (SELECT group_id FROM product_group_members m WHERE m.key_type='sku' AND m.key_value=i.sku))""" if grouped else ""
    sku_value = "COALESCE(g.name,i.sku)" if grouped else "i.sku"
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,s.name shop_name,o.channel,{sku_value} sku,MAX(COALESCE(
            (SELECT short_name FROM product_short_names n WHERE n.key_type='offer_id' AND n.key_value=i.offer_id),
            (SELECT short_name FROM product_short_names n WHERE n.key_type='sku' AND n.key_value=i.sku),
            i.product_name_raw)) product_name,
            SUM(i.quantity) valid_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 THEN i.quantity ELSE 0 END) cancelled_pieces,
            SUM(CASE WHEN o.cancel_reason_raw='Покупатель не забрал заказ' THEN i.quantity ELSE 0 END) unclaimed_pieces,
            SUM(CASE WHEN o.cancel_reason_raw='Отправление не прошло таможенное оформление' THEN i.quantity ELSE 0 END) customs_pieces
          FROM orders o JOIN shops s ON s.id=o.shop_id JOIN order_items i USING(shop_id,posting_number)
          {group_join} WHERE {ACTIVE}{clause} GROUP BY o.shop_id,o.channel,{sku_value}
          ORDER BY cancelled_pieces DESC,valid_pieces DESC
        """, args)]
    for row in rows:
        for key in ("cancelled", "unclaimed", "customs"):
            row[f"{key}_rate"] = row[f"{key}_pieces"] / row["valid_pieces"] if row["valid_pieces"] else 0
    return rows


@app.get("/api/risk/reasons")
def risk_reasons(shop_id: int = 0, reason: str = ""):
    clause, args = _shop_clause(shop_id)
    extra = ""
    if reason:
        extra = " AND o.cancel_reason_raw=?"; args.append(reason)
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,o.channel,
          COALESCE(NULLIF(o.cancel_reason_raw,''),'原因暂缺') reason_raw,
          COUNT(DISTINCT o.posting_number) orders,SUM(i.quantity) pieces
          FROM orders o JOIN shops s ON s.id=o.shop_id JOIN order_items i USING(shop_id,posting_number)
          WHERE o.status_raw='已取消' AND o.shipped=1{clause}{extra}
          GROUP BY o.shop_id,o.channel,reason_raw ORDER BY pieces DESC""", args)]
        details = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,o.channel,
          o.posting_number,SUM(i.quantity) pieces FROM orders o JOIN shops s ON s.id=o.shop_id
          JOIN order_items i USING(shop_id,posting_number)
          WHERE o.status_raw='已取消' AND o.shipped=1{clause}{extra}
          GROUP BY o.shop_id,o.channel,o.posting_number ORDER BY o.posting_number""", args)] if reason else []
    for row in rows:
        row["reason_name"] = CANCEL_REASON_ZH.get(row["reason_raw"], row["reason_raw"])
    return {"items": rows, "details": details}


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
def timeliness(shop_id: int = 0, page: int = 1, size: int = 30):
    clause, args = _shop_clause(shop_id)
    page, size = _paging(page, size)
    with connect() as db:
        all_rows = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,
          o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at
          FROM orders o JOIN shops s ON s.id=o.shop_id WHERE {ACTIVE}{clause}
          ORDER BY julianday(o.created_at) DESC,o.posting_number DESC""", args)]
        through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {ACTIVE}{clause}", args).fetchone()[0]
    ship_values, delivery_values = [], []
    grouped = {}
    for row in all_rows:
        if row["channel"] in ("FBP", "realFBS") and row["delivered_at"] == row["shipped_at"]:
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
    start = (page - 1) * size
    rows = all_rows[start:start + size]
    for row in rows:
        row["ship_hours"] = _duration_hours(row["created_at"], row["shipped_at"])
        row["delivery_hours"] = _duration_hours(row["shipped_at"], row["delivered_at"])
    return {"summary": summary, "items": rows, "total": len(all_rows), "page": page, "size": size,
            "groups": groups, "data_through": through}


@app.get("/api/complaints")
def complaints(shop_id: int = 0, q: str = "", status: str = "", page: int = 1, size: int = 50):
    where, args = ["1=1"], []
    if shop_id in (1, 2): where.append("c.shop_id=?"); args.append(shop_id)
    if q:
        where.append("(c.posting_number LIKE ? OR c.complaint_number LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    if status in {"open", "closed", "unset"}:
        where.append("c.resolved IS " + {"open": "0", "closed": "1", "unset": "NULL"}[status])
    page, size = _paging(page, size)
    sql = " AND ".join(where)
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM complaints c WHERE {sql}", args).fetchone()[0]
        items = [dict(row) for row in db.execute(f"""SELECT c.*,s.name shop_name
          FROM complaints c JOIN shops s ON s.id=c.shop_id WHERE {sql}
          ORDER BY c.complaint_at DESC LIMIT ? OFFSET ?""", args + [size, (page-1)*size])]
    return {"items": items, "total": total, "page": page, "size": size,
            "data_through": max((row["complaint_at"] for row in items), default=None)}


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
def returns(shop_id: int = 0, page: int = 1, size: int = 50):
    where, args = _record_clause(shop_id)
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
          (SELECT short_name FROM product_short_names n WHERE n.key_type='sku' AND n.key_value=r.sku) short_name
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
                      "sku": row["sku"], "product_name": row["short_name"] or product.get("name"),
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
def rfbs_returns(shop_id: int = 0, page: int = 1, size: int = 50):
    where, args = _record_clause(shop_id)
    page, size = _paging(page, size)
    with connect() as db:
        totals = [dict(row) for row in db.execute(f"""SELECT r.shop_id,s.name shop_name,COUNT(*) records
          FROM rfbs_return_records r JOIN shops s ON s.id=r.shop_id{where}
          GROUP BY r.shop_id ORDER BY r.shop_id""", args)]
        total = db.execute(f"SELECT COUNT(*) FROM rfbs_return_records r{where}", args).fetchone()[0]
        rows = db.execute(f"""SELECT r.shop_id,s.name shop_name,r.return_id,
          r.return_number,r.created_at,r.posting_number,r.offer_id,r.sku,r.product_name,
          r.status_raw,r.status_name,r.order_number,r.quantity,r.reason_raw,r.reason_name,
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
        item["order_number"] = item["order_number"] or payload.get("order_number")
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
    filename = unquote(request.headers.get("x-filename", kind))
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
          WHERE b.kind IN ('FBP','realFBS','WHD') ORDER BY b.id DESC LIMIT 50
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


@app.get("/api/export/orders")
def export_orders(shop_id: int = 0):
    clause, args = _shop_clause(shop_id)
    def lines():
        with connect() as db:
            shops_value = [dict(r) for r in db.execute("SELECT id,name FROM shops ORDER BY id")]
            through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {ACTIVE}{clause}", args).fetchone()[0]
            yield json.dumps({"type":"metadata","shops":shops_value,"timezone":"数据库UTC；显示北京时间",
                              "order_definition":"COUNT DISTINCT posting_number","piece_definition":"SUM quantity",
                              "filter":"剔除状态为已取消且无发货证据的订单","data_through":through}, ensure_ascii=False) + "\n"
            for row in db.execute(f"""
              SELECT o.shop_id,s.name shop,o.posting_number,o.channel,o.created_at,o.status_raw,
                o.cancel_reason_raw,o.amount_original,o.amount_currency
              FROM orders o JOIN shops s ON s.id=o.shop_id
              WHERE {ACTIVE}{clause} ORDER BY o.created_at
            """, args):
                yield json.dumps(_translated_order(row), ensure_ascii=False) + "\n"
    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Content-Disposition":"attachment; filename=orders.jsonl"})


@app.get("/api/export/{module}")
def export_module(module: str, shop_id: int = 0, date_from: str = "", date_to: str = ""):
    if module not in {"risk", "timeliness", "returns", "complaints", "stock", "rules"}:
        raise HTTPException(404, "未知导出模块")
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
    if shop_id in (1, 2) and module != "rules":
        where.append(f"{alias}.shop_id=?"); args.append(shop_id)
    if date_from:
        where.append(f"julianday({date_column})>=julianday(?)"); args.append(date_from)
    if date_to:
        where.append(f"julianday({date_column})<=julianday(?)")
        args.append(date_to if "T" in date_to else date_to + "T23:59:59.999999Z")
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
              "range": {"from": date_from or None, "to": date_to or None},
              "timezone": "数据库UTC；页面北京时间", "currencies": "保留记录原始币种，不做跨币种汇总",
              "order_definition": "不同posting_number", "piece_definition": "SUM(quantity)",
              "filter": "统计类导出剔除发货前取消；模块互相隔离", "data_through": through}
            yield json.dumps(metadata, ensure_ascii=False) + "\n"
            if module == "returns":
                legacy_where, legacy_args = ["1=1"], []
                if shop_id in (1, 2):
                    legacy_where.append("shop_id=?"); legacy_args.append(shop_id)
                if date_from:
                    legacy_where.append("julianday(occurred_at)>=julianday(?)"); legacy_args.append(date_from)
                if date_to:
                    legacy_where.append("julianday(occurred_at)<=julianday(?)")
                    legacy_args.append(date_to if "T" in date_to else date_to + "T23:59:59.999999Z")
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
