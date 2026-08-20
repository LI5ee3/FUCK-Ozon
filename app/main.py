import hashlib
import hmac
import json
import secrets
import threading
import time
from zipfile import BadZipFile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl.utils.exceptions import InvalidFileException
from starlette.concurrency import run_in_threadpool

from .db import DATA_DIR, connect, init_db, transaction
from .dingtalk import configured as dingtalk_configured, send_sync_failure, send_test, start_scheduler, stop_scheduler
from .importer import CHANNELS, import_costs, import_csv
from .ozon import BEIJING, CANCEL_REASON_ZH, FINANCE_OPERATION_ZH, RFBS_RETURN_STATUS_ZH, RETURN_STATUS_ZH, STATUS_ZH, _env, default_range, sync_module
from .push import PushAuthError, PushProcessingError, PushRequestError, push_settings, receive_push, save_seller_ids

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
ACTIVE = "NOT (o.status_raw='已取消' AND o.shipped=0)"
SYNC_MODULES = {"orders", "finance", "returns", "stock"}
_auto_sync_stop = threading.Event()
_auto_sync_thread = None

app = FastAPI(title="FUCK Ozon", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def startup():
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


def _token():
    expires = str(int(time.time()) + 86400)
    signature = hmac.new(_secret(), expires.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}"


def _authenticated(request):
    try:
        expires, signature = request.cookies.get("session", "").split(".", 1)
        expected = hmac.new(_secret(), expires.encode(), hashlib.sha256).hexdigest()
        return int(expires) > time.time() and hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False


@app.middleware("http")
async def protect_api(request: Request, call_next):
    public = {"/api/login", "/api/session"}
    push_callback = request.url.path.startswith("/api/ozon/push/")
    if request.url.path.startswith("/api/") and request.url.path not in public and not push_callback and not _authenticated(request):
        return Response(json.dumps({"detail": "未登录"}, ensure_ascii=False), 401, media_type="application/json")
    return await call_next(request)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/session")
def session(request: Request):
    return {"authenticated": _authenticated(request)}


@app.post("/api/login")
async def login(request: Request, response: Response):
    expected = _env().get("ADMIN_PASSWORD")
    if not expected:
        raise HTTPException(503, "服务器尚未设置 ADMIN_PASSWORD")
    body = await request.json()
    if not hmac.compare_digest(str(body.get("password", "")), expected):
        raise HTTPException(401, "密码错误")
    response.set_cookie("session", _token(), httponly=True, secure=request.url.scheme == "https",
                        samesite="strict", max_age=86400)
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("session")
    return {"ok": True}


@app.get("/api/shops")
def shops():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT id,name,settlement_currency FROM shops ORDER BY id")]


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


def _push_error(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message, "details": ""}}, status_code=status)


@app.post("/api/ozon/push/{shop_token}")
async def ozon_push(shop_token: str, request: Request):
    request.scope["path"] = "/api/ozon/push/[redacted]"
    request.scope["raw_path"] = b"/api/ozon/push/[redacted]"
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        return _push_error(415, "INVALID_CONTENT_TYPE", "Content-Type 必须是 application/json")
    try:
        length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return _push_error(400, "INVALID_REQUEST", "Content-Length 无效")
    if length > 1024 * 1024:
        return _push_error(413, "REQUEST_TOO_LARGE", "请求体超过1MB")
    body = await request.body()
    if len(body) > 1024 * 1024:
        return _push_error(413, "REQUEST_TOO_LARGE", "请求体超过1MB")
    try:
        payload = json.loads(body)
        return await run_in_threadpool(receive_push, shop_token, payload)
    except PushAuthError as error:
        return _push_error(403, "AUTH_FAILED", str(error))
    except (PushRequestError, json.JSONDecodeError) as error:
        return _push_error(400, "INVALID_REQUEST", str(error))
    except PushProcessingError:
        return _push_error(500, "PROCESSING_FAILED", "事件持久化后处理失败")


@app.get("/api/ozon/push-settings")
def ozon_push_settings(request: Request):
    return push_settings(str(request.base_url))


@app.put("/api/ozon/push-settings")
async def update_ozon_push_settings(request: Request):
    try:
        save_seller_ids(await request.json())
    except PushRequestError as error:
        raise HTTPException(400, str(error)) from error
    return push_settings(str(request.base_url))


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
            o.status_raw,o.cancel_reason_raw,o.shipped,o.data_anomaly,o.amount_original,o.amount_currency,c.cost_cny
          FROM orders o JOIN shops s ON s.id=o.shop_id
          LEFT JOIN order_costs c USING(shop_id,posting_number)
          WHERE {sql_where} ORDER BY o.created_at DESC LIMIT ? OFFSET ?
        """, args + [size, (page - 1) * size])]
        for order in result:
            order["items"] = [dict(row) for row in db.execute(
                "SELECT sku,offer_id,product_name_raw,quantity,unit_price,price_currency FROM order_items WHERE shop_id=? AND posting_number=? ORDER BY sku",
                (order["shop_id"], order["posting_number"]))]
    return {"items": result, "total": total, "page": page, "size": size}


@app.get("/api/risk")
def risk(shop_id: int = 0):
    clause, args = _shop_clause(shop_id)
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,s.name shop_name,o.channel,i.sku,MAX(i.product_name_raw) product_name,
            SUM(i.quantity) valid_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 THEN i.quantity ELSE 0 END) cancelled_pieces,
            SUM(CASE WHEN o.cancel_reason_raw='Покупатель не забрал заказ' THEN i.quantity ELSE 0 END) unclaimed_pieces,
            SUM(CASE WHEN o.cancel_reason_raw='Отправление не прошло таможенное оформление' THEN i.quantity ELSE 0 END) customs_pieces
          FROM orders o JOIN shops s ON s.id=o.shop_id JOIN order_items i USING(shop_id,posting_number)
          WHERE {ACTIVE}{clause} GROUP BY o.shop_id,o.channel,i.sku ORDER BY cancelled_pieces DESC,valid_pieces DESC
        """, args)]
    for row in rows:
        for key in ("cancelled", "unclaimed", "customs"):
            row[f"{key}_rate"] = row[f"{key}_pieces"] / row["valid_pieces"] if row["valid_pieces"] else 0
    return rows


@app.get("/api/timeliness")
def timeliness(shop_id: int = 0, page: int = 1, size: int = 30):
    clause, args = _shop_clause(shop_id)
    page, size = _paging(page, size)
    with connect() as db:
        summary = dict(db.execute(f"""
          SELECT COUNT(*) orders,
            SUM(o.shipped_at IS NOT NULL) shipped_orders,
            SUM(o.delivered_at IS NOT NULL) delivered_orders,
            AVG(CASE WHEN o.shipped_at IS NOT NULL AND julianday(o.shipped_at)>=julianday(o.created_at)
              THEN (julianday(o.shipped_at)-julianday(o.created_at))*24 END) avg_ship_hours,
            AVG(CASE WHEN o.delivered_at IS NOT NULL AND o.shipped_at IS NOT NULL
              AND julianday(o.delivered_at)>=julianday(o.shipped_at)
              THEN (julianday(o.delivered_at)-julianday(o.shipped_at))*24 END) avg_delivery_hours
          FROM orders o WHERE {ACTIVE}{clause}
        """, args).fetchone())
        total = summary["orders"]
        rows = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,s.name shop_name,o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at,
            CASE WHEN o.shipped_at IS NOT NULL AND julianday(o.shipped_at)>=julianday(o.created_at)
              THEN (julianday(o.shipped_at)-julianday(o.created_at))*24 END ship_hours,
            CASE WHEN o.delivered_at IS NOT NULL AND o.shipped_at IS NOT NULL
              AND julianday(o.delivered_at)>=julianday(o.shipped_at)
              THEN (julianday(o.delivered_at)-julianday(o.shipped_at))*24 END delivery_hours
          FROM orders o JOIN shops s ON s.id=o.shop_id WHERE {ACTIVE}{clause}
          ORDER BY o.created_at DESC LIMIT ? OFFSET ?
        """, args + [size, (page - 1) * size])]
        through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {ACTIVE}{clause}", args).fetchone()[0]
    return {"summary": summary, "items": rows, "total": total, "page": page, "size": size,
            "data_through": through}


@app.get("/api/finance")
def finance(shop_id: int = 0, page: int = 1, size: int = 50):
    where, args = _record_clause(shop_id)
    page, size = _paging(page, size)
    with connect() as db:
        totals = [dict(row) for row in db.execute(f"""
          SELECT r.shop_id,s.name shop_name,'RUB' currency,COUNT(*) records,
            COALESCE(SUM(CAST(json_extract(r.payload,'$.amount') AS REAL)),0) amount,
            COALESCE(SUM(CAST(json_extract(r.payload,'$.accruals_for_sale') AS REAL)),0) accruals,
            COALESCE(SUM(CAST(json_extract(r.payload,'$.sale_commission') AS REAL)),0) commission
          FROM finance_records r JOIN shops s ON s.id=r.shop_id{where}
          GROUP BY r.shop_id ORDER BY r.shop_id
        """, args)]
        total = db.execute(f"SELECT COUNT(*) FROM finance_records r{where}", args).fetchone()[0]
        records = db.execute(f"""SELECT r.shop_id,s.name shop_name,'RUB' currency,
          r.occurred_at,r.payload FROM finance_records r JOIN shops s ON s.id=r.shop_id{where}
          ORDER BY r.occurred_at DESC LIMIT ? OFFSET ?""", args + [size, (page - 1) * size]).fetchall()
        through = db.execute(f"SELECT MAX(r.occurred_at) FROM finance_records r{where}", args).fetchone()[0]
    items = []
    for row in records:
        payload = json.loads(row["payload"])
        posting = payload.get("posting") or {}
        operation = payload.get("operation_type_name") or payload.get("operation_type")
        items.append({"shop_id": row["shop_id"], "shop_name": row["shop_name"], "currency": row["currency"],
                      "occurred_at": row["occurred_at"], "posting_number": posting.get("posting_number"),
                      "operation_type": FINANCE_OPERATION_ZH.get(operation, operation),
                      "amount": payload.get("amount"), "accruals": payload.get("accruals_for_sale"),
                      "commission": payload.get("sale_commission")})
    return {"summary": {"records": total, "shops": totals}, "items": items, "total": total,
            "page": page, "size": size, "data_through": through}


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
        records = db.execute(f"""SELECT r.shop_id,s.name shop_name,r.occurred_at,r.posting_number,r.sku,r.payload
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
                      "sku": row["sku"], "product_name": product.get("name"),
                      "quantity": product.get("quantity"),
                      "reason": CANCEL_REASON_ZH.get(payload.get("return_reason_name"), payload.get("return_reason_name")),
                      "status": RETURN_STATUS_ZH.get(status, status),
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
        items = [dict(row) for row in db.execute(f"""SELECT r.shop_id,s.name shop_name,r.return_id,
          r.return_number,r.created_at,r.posting_number,r.offer_id,r.sku,r.product_name,
          r.status_raw,r.status_name FROM rfbs_return_records r JOIN shops s ON s.id=r.shop_id{where}
          ORDER BY r.created_at DESC,r.return_id DESC LIMIT ? OFFSET ?""", args + [size, (page - 1) * size])]
        through = db.execute(f"SELECT MAX(r.created_at) FROM rfbs_return_records r{where}", args).fetchone()[0]
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
    items, shops = [], {}
    for row in records:
        payload = json.loads(row["payload"])
        stocks = payload.get("stocks") or []
        present = sum(int(value.get("present") or 0) for value in stocks)
        reserved = sum(int(value.get("reserved") or 0) for value in stocks)
        items.append({"shop_id": row["shop_id"], "shop_name": row["shop_name"],
                      "observed_at": row["observed_at"], "product_id": payload.get("product_id"),
                      "offer_id": payload.get("offer_id"), "present": present, "reserved": reserved,
                      "types": ", ".join(sorted({str(value.get("type") or value.get("shipment_type") or "")
                                                   for value in stocks if value.get("type") or value.get("shipment_type")}))})
        summary = shops.setdefault(row["shop_id"], {"shop_id": row["shop_id"], "shop_name": row["shop_name"],
                                                    "products": 0, "present": 0, "reserved": 0})
        summary["products"] += 1; summary["present"] += present; summary["reserved"] += reserved
    total = len(items); start = (page - 1) * size
    through = max((item["observed_at"] for item in items), default=None)
    return {"summary": {"records": total, "shops": list(shops.values())}, "items": items[start:start + size],
            "total": total, "page": page, "size": size, "data_through": through}


@app.post("/api/import/{kind}")
async def upload(kind: str, request: Request, shop_id: int):
    if shop_id not in (1, 2): raise HTTPException(400, "请选择店铺")
    filename = unquote(request.headers.get("x-filename", kind))
    content = await request.body()
    if len(content) > 50 * 1024 * 1024: raise HTTPException(413, "文件超过50MB")
    try:
        if kind == "mabang":
            return await run_in_threadpool(import_costs, shop_id, filename, content)
        return await run_in_threadpool(import_csv, shop_id, kind, filename, content)
    except (ValueError, UnicodeError, BadZipFile, InvalidFileException) as error:
        raise HTTPException(400, str(error)) from error


@app.get("/api/imports")
def imports():
    with connect() as db:
        return [dict(row) for row in db.execute("""
          SELECT b.*,s.name shop_name FROM import_batches b JOIN shops s ON s.id=b.shop_id ORDER BY b.id DESC LIMIT 50
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
        return [dict(row) for row in db.execute("SELECT * FROM auto_sync_settings ORDER BY rowid")]


def save_auto_sync_settings(values):
    if set(values) != SYNC_MODULES:
        raise ValueError("必须提交订单、财务、退货和库存四个模块的设置")
    settings = []
    for module in ("orders", "finance", "returns", "stock"):
        value = values[module]
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
                         1 if module == "stock" else range_days, module))
    with transaction() as db:
        db.executemany("UPDATE auto_sync_settings SET enabled=?,run_time=?,range_days=? WHERE module=?",
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
        settings = db.execute("SELECT * FROM auto_sync_settings WHERE enabled=1 ORDER BY rowid").fetchall()
    started = []
    for setting in settings:
        if now.strftime("%H:%M") < setting["run_time"]:
            continue
        end = now
        start = (now - timedelta(days=setting["range_days"] - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        for shop_id in (1, 2):
            run_id = _create_sync_job(setting["module"], shop_id, start, end, "auto", today)
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
                o.cancel_reason_raw,o.amount_original,o.amount_currency,c.cost_cny
              FROM orders o JOIN shops s ON s.id=o.shop_id LEFT JOIN order_costs c USING(shop_id,posting_number)
              WHERE {ACTIVE}{clause} ORDER BY o.created_at
            """, args):
                yield json.dumps(_translated_order(row), ensure_ascii=False) + "\n"
    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Content-Disposition":"attachment; filename=orders.jsonl"})
