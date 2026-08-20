import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .db import connect, transaction

API = "https://api-seller.ozon.ru"
BEIJING = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parent.parent
MODULE_TABLES = {
    "orders": ("orders", "order_items", "order_api_records"),
    "finance": ("finance_records",),
    "returns": ("return_records",),
    "premium": ("analytics_records",),
    "stock": ("stock_snapshots",),
    "prices": ("price_snapshots",),
    "questions": ("question_records",),
}
STATUS_ZH = {
    "delivered": "已签收", "delivering": "运输中", "cancelled": "已取消",
    "awaiting_deliver": "等待发运", "awaiting_packaging": "待备货",
}
ANALYTICS_METRICS = [
    "revenue", "ordered_units", "hits_view_search", "hits_view_pdp",
    "hits_tocart_search", "hits_tocart_pdp", "session_view_search",
    "session_view_pdp", "conv_tocart_search", "conv_tocart_pdp",
    "returns", "cancellations", "delivered_units", "position_category",
]
_request_lock = threading.Lock()
_last_request = 0.0


def _env():
    values = dict(os.environ)
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values.setdefault(key.strip(), value.strip())
    return values


def _headers(shop_id):
    values = _env()
    client_id = values.get(f"SHOP_{shop_id}_OZON_CLIENT_ID", "")
    api_key = values.get(f"SHOP_{shop_id}_OZON_API_KEY", "")
    if not client_id or not api_key:
        raise ValueError(f"店铺{shop_id} API凭据未配置")
    return {"Client-Id": client_id, "Api-Key": api_key, "Content-Type": "application/json"}


def _post(shop_id, path, payload):
    global _last_request
    # ponytail: one global limiter is enough for one admin; use per-shop limiters only if sync concurrency matters.
    with _request_lock:
        delay = max(0, 1.05 - (time.monotonic() - _last_request))
        if delay:
            time.sleep(delay)
        for attempt in range(7):
            request = urllib.request.Request(
                API + path, data=json.dumps(payload).encode(), headers=_headers(shop_id), method="POST")
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    _last_request = time.monotonic()
                    return json.load(response)
            except urllib.error.HTTPError as error:
                _last_request = time.monotonic()
                if error.code == 429 and attempt < 6:
                    time.sleep(min(30, 2 ** (attempt + 1)))
                    continue
                try:
                    message = json.loads(error.read()).get("message", "Ozon API请求失败")
                except Exception:
                    message = "Ozon API请求失败"
                raise RuntimeError(f"{path}: HTTP {error.code}: {message}") from error


def default_range():
    end = datetime.now(BEIJING)
    month = end.month - 3
    year = end.year
    if month <= 0:
        month += 12
        year -= 1
    start = end.replace(year=year, month=month, day=min(end.day, monthrange(year, month)[1]),
                        hour=0, minute=0, second=0, microsecond=0)
    return start, end


def _utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _key(record, *fields):
    parts = [str(record.get(field, "")) for field in fields]
    if any(parts):
        return "|".join(parts)
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _cursor_pages(shop_id, path, payload, list_key, request_cursor="cursor", response_cursor="cursor"):
    records, cursor = [], ""
    for _ in range(200):
        request = dict(payload)
        if cursor:
            request[request_cursor] = cursor
        body = _post(shop_id, path, request)
        batch = body.get(list_key) or []
        records.extend(batch)
        if not body.get("has_next") or not batch:
            return records
        cursor = str(body.get(response_cursor) or batch[-1].get("id") or "")
        if not cursor:
            raise RuntimeError(f"{path}: 分页游标缺失")
    raise RuntimeError(f"{path}: 分页超过安全上限")


def _json(record):
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _product_price(product, fallback_currency):
    price = product.get("price")
    if isinstance(price, dict):
        return float(price.get("amount") or 0), price.get("currency") or fallback_currency
    return float(price or 0), fallback_currency


def sync_orders(shop_id, start, end):
    base = {"dir": "ASC", "filter": {"since": _utc(start), "to": _utc(end)},
            "limit": 100, "with": {"analytics_data": True, "financial_data": True}}
    fbs = _cursor_pages(shop_id, "/v4/posting/fbs/list", base, "postings")
    fbo = _cursor_pages(shop_id, "/v3/posting/fbo/list", base, "postings")
    fetched = _stamp()
    with transaction() as db:
        currency = db.execute("SELECT settlement_currency FROM shops WHERE id=?", (shop_id,)).fetchone()[0]
        for posting, channel in [(record, None) for record in fbs] + [(record, "WHD") for record in fbo]:
            if channel is None:
                flow = posting.get("integration_type_flow")
                if flow not in ("FBP", "aggregator"):
                    raise RuntimeError(f"未知 integration_type_flow: {flow!r}")
                channel = "FBP" if flow == "FBP" else "realFBS"
            number = posting["posting_number"]
            status_original = posting.get("status") or ""
            cancellation = posting.get("cancellation") or {}
            cancelled_after = cancellation.get("cancelled_after_ship") if status_original == "cancelled" else None
            shipped = int(bool(cancelled_after) if status_original == "cancelled" else status_original in ("delivered", "delivering"))
            products = posting.get("products") or []
            prices = [_product_price(product, currency) for product in products]
            amount = sum(price[0] * int(product.get("quantity") or 0) for product, price in zip(products, prices))
            amount_currency = prices[0][1] if prices else currency
            created = posting.get("in_process_at") or posting.get("created_at")
            db.execute("""
              INSERT INTO orders(shop_id,posting_number,parent_order_no,channel,created_at,status_raw,
                cancel_reason_raw,shipped,cancelled_after_ship,data_anomaly,amount_original,
                amount_currency,source,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(shop_id,posting_number) DO UPDATE SET
                parent_order_no=COALESCE(NULLIF(excluded.parent_order_no,''),orders.parent_order_no),
                channel=excluded.channel,created_at=COALESCE(NULLIF(excluded.created_at,''),orders.created_at),
                status_raw=COALESCE(NULLIF(excluded.status_raw,''),orders.status_raw),
                cancel_reason_raw=COALESCE(NULLIF(excluded.cancel_reason_raw,''),orders.cancel_reason_raw),
                shipped=CASE WHEN excluded.channel='WHD' AND excluded.status_raw='已取消' AND excluded.cancelled_after_ship IS NULL
                  THEN orders.shipped ELSE excluded.shipped END,
                cancelled_after_ship=COALESCE(excluded.cancelled_after_ship,orders.cancelled_after_ship),
                amount_original=COALESCE(excluded.amount_original,orders.amount_original),
                amount_currency=COALESCE(NULLIF(excluded.amount_currency,''),orders.amount_currency),
                source='api',updated_at=excluded.updated_at
            """, (shop_id, number, posting.get("order_number"), channel, created,
                  STATUS_ZH.get(status_original, status_original), cancellation.get("cancel_reason"),
                  shipped, cancelled_after, 0, amount, amount_currency, "api", fetched))
            for product, price in zip(products, prices):
                sku = str(product.get("sku") or "")
                if not sku:
                    continue
                db.execute("""
                  INSERT INTO order_items(shop_id,channel,posting_number,sku,offer_id,product_name_raw,
                    quantity,unit_price,price_currency,source)
                  VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(shop_id,channel,posting_number,sku) DO UPDATE SET
                    offer_id=COALESCE(NULLIF(excluded.offer_id,''),order_items.offer_id),
                    product_name_raw=COALESCE(NULLIF(excluded.product_name_raw,''),order_items.product_name_raw),
                    quantity=excluded.quantity,unit_price=COALESCE(excluded.unit_price,order_items.unit_price),
                    price_currency=COALESCE(NULLIF(excluded.price_currency,''),order_items.price_currency),source='api'
                """, (shop_id, channel, number, sku, product.get("offer_id"), product.get("name") or "",
                      int(product.get("quantity") or 1), price[0], price[1], "api"))
            db.execute("""
              INSERT INTO order_api_records VALUES(?,?,?,?,?) ON CONFLICT(shop_id,posting_number) DO UPDATE SET
                channel=excluded.channel,payload=excluded.payload,fetched_at=excluded.fetched_at
            """, (shop_id, number, channel, _json(posting), fetched))
    return {"records": len(fbs) + len(fbo), "FBP": sum(p.get("integration_type_flow") == "FBP" for p in fbs),
            "realFBS": sum(p.get("integration_type_flow") == "aggregator" for p in fbs), "WHD": len(fbo)}


def sync_finance(shop_id, start, end):
    records, cursor = [], start
    while cursor < end:
        window_end = min(cursor + timedelta(days=30), end)
        page = 1
        while True:
            payload = {"filter": {"date": {"from": _utc(cursor), "to": _utc(window_end)},
                       "operation_type": [], "posting_number": "", "transaction_type": "all"},
                       "page": page, "page_size": 1000}
            result = _post(shop_id, "/v3/finance/transaction/list", payload).get("result") or {}
            records.extend(result.get("operations") or [])
            if page >= int(result.get("page_count") or 0):
                break
            page += 1
        cursor = window_end
    fetched = _stamp()
    with transaction() as db:
        for record in records:
            db.execute("""INSERT INTO finance_records VALUES(?,?,?,?,?)
              ON CONFLICT(shop_id,record_key) DO UPDATE SET occurred_at=excluded.occurred_at,payload=excluded.payload,fetched_at=excluded.fetched_at
            """, (shop_id, _key(record, "operation_id"), record.get("operation_date"), _json(record), fetched))
    return {"records": len({_key(record, "operation_id") for record in records}), "fetched": len(records)}


def sync_returns(shop_id, start, end):
    payload = {"filter": {"logistic_return_date": {"time_from": _utc(start), "time_to": _utc(end)}}, "limit": 100}
    records = _cursor_pages(shop_id, "/v1/returns/list", payload, "returns", "last_id", "")
    fetched = _stamp()
    with transaction() as db:
        for record in records:
            product, logistic = record.get("product") or {}, record.get("logistic") or {}
            db.execute("""INSERT INTO return_records VALUES(?,?,?,?,?,?,?)
              ON CONFLICT(shop_id,record_key) DO UPDATE SET occurred_at=excluded.occurred_at,posting_number=excluded.posting_number,sku=excluded.sku,payload=excluded.payload,fetched_at=excluded.fetched_at
            """, (shop_id, _key(record, "id"), logistic.get("return_date") or logistic.get("final_moment"),
                  record.get("posting_number"), str(product.get("sku") or ""), _json(record), fetched))
    return {"records": len(records)}


def sync_premium(shop_id, start, end):
    records, offset, limit = [], 0, 1000
    while True:
        payload = {"date_from": start.date().isoformat(), "date_to": end.date().isoformat(),
                   "metrics": ANALYTICS_METRICS, "dimension": ["day", "sku"],
                   "filters": [], "sort": [], "limit": limit, "offset": offset}
        batch = ((_post(shop_id, "/v1/analytics/data", payload).get("result") or {}).get("data") or [])
        records.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    fetched = _stamp()
    with transaction() as db:
        for record in records:
            dimensions = record.get("dimensions") or []
            occurred = next((d.get("id") for d in dimensions if str(d.get("id", "")).startswith("20")), None)
            db.execute("""INSERT INTO analytics_records VALUES(?,?,?,?,?)
              ON CONFLICT(shop_id,record_key) DO UPDATE SET occurred_at=excluded.occurred_at,payload=excluded.payload,fetched_at=excluded.fetched_at
            """, (shop_id, _key(record), occurred, _json(record), fetched))
    return {"records": len(records), "metrics": len(ANALYTICS_METRICS)}


def _sync_snapshot(shop_id, path, table):
    records = _cursor_pages(shop_id, path, {"filter": {"visibility": "ALL"}, "limit": 1000}, "items")
    observed = _stamp()
    with transaction() as db:
        for record in records:
            db.execute(f"INSERT INTO {table} VALUES(?,?,?,?)",
                       (shop_id, _key(record, "product_id", "offer_id"), observed, _json(record)))
    return {"records": len(records), "snapshot_at": observed}


def sync_questions(shop_id, start, end):
    records = _cursor_pages(shop_id, "/v1/question/list", {"filter": {}, "limit": 100},
                            "questions", "last_id", "last_id")
    records = [record for record in records if start <= datetime.fromisoformat(record["published_at"].replace("Z", "+00:00")).astimezone(BEIJING) <= end]
    fetched = _stamp()
    with transaction() as db:
        for record in records:
            db.execute("""INSERT INTO question_records VALUES(?,?,?,?,?)
              ON CONFLICT(shop_id,record_key) DO UPDATE SET occurred_at=excluded.occurred_at,payload=excluded.payload,fetched_at=excluded.fetched_at
            """, (shop_id, _key(record, "id"), record.get("published_at"), _json(record), fetched))
    return {"records": len(records)}


def sync_module(module, shop_id, start=None, end=None):
    start, end = (start, end) if start and end else default_range()
    functions = {"orders": sync_orders, "finance": sync_finance, "returns": sync_returns,
                 "premium": sync_premium, "stock": lambda s, _a, _b: _sync_snapshot(s, "/v4/product/info/stocks", "stock_snapshots"),
                 "prices": lambda s, _a, _b: _sync_snapshot(s, "/v5/product/info/prices", "price_snapshots"),
                 "questions": sync_questions}
    if module not in functions:
        raise ValueError("未知同步模块")
    return functions[module](shop_id, start, end)


def table_fingerprints():
    result = {}
    with connect() as db:
        for tables in MODULE_TABLES.values():
            for table in tables:
                rows = db.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall()
                digest = hashlib.sha256("\n".join("|".join(str(v) for v in row) for row in rows).encode()).hexdigest()
                result[table] = {"rows": len(rows), "sha256": digest}
    return result
