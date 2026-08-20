import hashlib
import hmac
import json
import os
import secrets
import time
from zipfile import BadZipFile
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl.utils.exceptions import InvalidFileException
from starlette.concurrency import run_in_threadpool

from .db import DATA_DIR, connect, init_db, transaction
from .importer import CHANNELS, import_costs, import_csv
from .ozon import default_range, sync_module

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
ACTIVE = "NOT (o.status_raw='已取消' AND o.shipped=0)"
SYNC_MODULES = {"orders", "finance", "returns", "premium", "stock", "prices", "questions"}

app = FastAPI(title="FUCK Ozon", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def startup():
    init_db()


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
    if request.url.path.startswith("/api/") and request.url.path not in public and not _authenticated(request):
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
    expected = os.getenv("ADMIN_PASSWORD")
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
        return [dict(row) for row in db.execute("SELECT * FROM shops ORDER BY id")]


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


def _shop_clause(shop_id):
    return (" AND o.shop_id=?", [shop_id]) if shop_id in (1, 2) else ("", [])


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
        result = [dict(row) for row in db.execute(f"""
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


@app.post("/api/import/{kind}")
async def upload(kind: str, request: Request, shop_id: int):
    if shop_id not in (1, 2): raise HTTPException(400, "请选择店铺")
    filename = unquote(request.headers.get("x-filename", kind))
    content = await request.body()
    if len(content) > 50 * 1024 * 1024: raise HTTPException(413, "文件超过50MB")
    try:
        return import_costs(shop_id, filename, content) if kind == "mabang" else import_csv(shop_id, kind, filename, content)
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
    with transaction() as db:
        run_id = db.execute("""
          INSERT INTO sync_runs(shop_id,module,range_from,range_to,status) VALUES(?,?,?,?, 'running')
        """, (shop_id, module, start.isoformat(), end.isoformat())).lastrowid
    try:
        result = await run_in_threadpool(sync_module, module, shop_id, start, end)
    except Exception as error:
        message = str(error)[:500]
        with transaction() as db:
            db.execute("""UPDATE sync_runs SET finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'),status='failed',error=? WHERE id=?""",
                       (message, run_id))
        raise HTTPException(502, message) from error
    with transaction() as db:
        db.execute("""UPDATE sync_runs SET finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'),
          data_through=?,status='success' WHERE id=?""", (end.isoformat(), run_id))
    return {"run_id": run_id, **result}


@app.get("/api/export/orders")
def export_orders(shop_id: int = 0):
    clause, args = _shop_clause(shop_id)
    def lines():
        with connect() as db:
            shops_value = [dict(r) for r in db.execute("SELECT id,name FROM shops ORDER BY id")]
            through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE 1=1{clause}", args).fetchone()[0]
            yield json.dumps({"type":"metadata","shops":shops_value,"timezone":"数据库UTC；显示北京时间",
                              "order_definition":"COUNT DISTINCT posting_number","piece_definition":"SUM quantity",
                              "filter":"剔除状态为已取消且无发货证据的订单","data_through":through}, ensure_ascii=False) + "\n"
            for row in db.execute(f"""
              SELECT o.shop_id,s.name shop,o.posting_number,o.channel,o.created_at,o.status_raw,
                o.cancel_reason_raw,o.amount_original,o.amount_currency,c.cost_cny
              FROM orders o JOIN shops s ON s.id=o.shop_id LEFT JOIN order_costs c USING(shop_id,posting_number)
              WHERE 1=1{clause} ORDER BY o.created_at
            """, args):
                yield json.dumps(dict(row), ensure_ascii=False) + "\n"
    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Content-Disposition":"attachment; filename=orders.jsonl"})
