import hashlib
import json
from calendar import monthrange
from datetime import datetime, timezone

from . import client
from ..db import connect, transaction
from .mappings import PUSH_STATUS_ZH, STATUS_ZH


def _utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def default_range():
    end = datetime.now(client.BEIJING)
    month = end.month - 3
    year = end.year
    if month <= 0:
        month += 12
        year -= 1
    start = end.replace(year=year, month=month, day=min(end.day, monthrange(year, month)[1]),
                        hour=0, minute=0, second=0, microsecond=0)
    return start, end


def _key(record, *fields):
    parts = [str(record.get(field, "")) for field in fields]
    if any(parts):
        return "|".join(parts)
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _json(record):
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _product_price(product, fallback_currency):
    price = product.get("price")
    if isinstance(price, dict):
        return float(price.get("amount") or 0), price.get("currency") or fallback_currency
    return float(price or 0), fallback_currency


def _channel_for_posting(posting, hint=None):
    if hint in ("FBP", "realFBS", "WHD"):
        return hint
    flow = str(posting.get("integration_type_flow") or posting.get("tpl_integration_type") or "")
    if flow == "FBP":
        return "FBP"
    if flow.lower() in ("aggregator", "realfbs", "rfbs"):
        return "realFBS"
    if flow.lower() in ("fbo", "whd"):
        return "WHD"
    raise RuntimeError(f"未知 integration_type_flow: {flow!r}")


def _save_order(db, shop_id, posting, channel=None, source="api", updated_at=None):
    posting = dict(posting or {})
    number = str(posting.get("posting_number") or "").strip()
    if not number:
        raise ValueError("货件详情缺少 posting_number")
    channel = _channel_for_posting(posting, channel)
    currency = db.execute("SELECT settlement_currency FROM shops WHERE id=?", (shop_id,)).fetchone()[0]
    status_original = str(posting.get("status") or "")
    status_raw = STATUS_ZH.get(status_original, PUSH_STATUS_ZH.get(status_original, status_original))
    cancellation = posting.get("cancellation") or {}
    if not isinstance(cancellation, dict):
        cancellation = {}
    cancelled_after = cancellation.get("cancelled_after_ship") if status_original in ("cancelled", "canceled") else None
    shipped = int(bool(cancelled_after) if status_raw == "已取消" else status_raw in ("运输中", "已签收"))
    products = posting.get("products") or []
    prices = [_product_price(product, currency) for product in products]
    amount = sum(price[0] * int(product.get("quantity") or 0)
                 for product, price in zip(products, prices))
    amount_currency = prices[0][1] if prices else currency
    created = posting.get("in_process_at") or posting.get("created_at")
    shipped_at = posting.get("delivering_date")
    delivered_at = posting.get("fact_delivery_date")
    status_changed_at = client._timestamp(posting.get("status_changed_at") or posting.get("last_changed_status_date"))
    reason_id = cancellation.get("cancel_reason_id") or posting.get("cancel_reason_id")
    reason_raw = cancellation.get("cancel_reason") or posting.get("cancel_reason")
    existing = db.execute("SELECT * FROM orders WHERE shop_id=? AND posting_number=?",
                          (shop_id, number)).fetchone()
    from .webhooks import _apply_pending_webhook_events, _push_cancellation
    push_cancel = _push_cancellation(db, shop_id, number)
    if push_cancel:
        status_raw = "已取消"
        status_changed_at = push_cancel["occurred_at"]
        reason_id = push_cancel["reason_id"] or reason_id
        reason_raw = push_cancel["reason_raw"] or reason_raw
        if existing:
            shipped = existing["shipped"]
        if existing and cancelled_after is None:
            cancelled_after = existing["cancelled_after_ship"]
    preserve_shipped = (push_cancel or
                        (channel == "WHD" and status_raw == "已取消" and cancelled_after is None))
    if preserve_shipped and existing:
        shipped = existing["shipped"]
    fetched = updated_at or client._stamp()
    db.execute("""
      INSERT INTO orders(shop_id,posting_number,parent_order_no,channel,created_at,shipped_at,delivered_at,tracking_number,status_raw,
        cancel_reason_raw,cancel_reason_id,shipped,cancelled_after_ship,data_anomaly,amount_original,
        amount_currency,warehouse_id,status_changed_at,source,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(shop_id,posting_number) DO UPDATE SET
        parent_order_no=COALESCE(NULLIF(excluded.parent_order_no,''),orders.parent_order_no),
        channel=excluded.channel,created_at=COALESCE(NULLIF(excluded.created_at,''),orders.created_at),
        shipped_at=COALESCE(NULLIF(excluded.shipped_at,''),orders.shipped_at),
        delivered_at=CASE WHEN NULLIF(excluded.delivered_at,'') IS NOT NULL THEN excluded.delivered_at
          WHEN excluded.channel IN ('FBP','realFBS') AND orders.delivered_at=orders.shipped_at THEN NULL
          ELSE orders.delivered_at END,
        tracking_number=COALESCE(NULLIF(excluded.tracking_number,''),orders.tracking_number),
        status_raw=COALESCE(NULLIF(excluded.status_raw,''),orders.status_raw),
        cancel_reason_raw=COALESCE(NULLIF(excluded.cancel_reason_raw,''),orders.cancel_reason_raw),
        cancel_reason_id=COALESCE(NULLIF(excluded.cancel_reason_id,''),orders.cancel_reason_id),
        shipped=excluded.shipped,
        cancelled_after_ship=COALESCE(excluded.cancelled_after_ship,orders.cancelled_after_ship),
        amount_original=COALESCE(excluded.amount_original,orders.amount_original),
        amount_currency=COALESCE(NULLIF(excluded.amount_currency,''),orders.amount_currency),
        warehouse_id=COALESCE(NULLIF(excluded.warehouse_id,''),orders.warehouse_id),
        status_changed_at=COALESCE(NULLIF(excluded.status_changed_at,''),orders.status_changed_at),
        source=excluded.source,updated_at=excluded.updated_at
    """, (shop_id, number, posting.get("order_number"), channel, created, shipped_at, delivered_at,
          posting.get("tracking_number"), status_raw, reason_raw, str(reason_id or ""), shipped,
          cancelled_after, 0, amount, amount_currency, str(posting.get("warehouse_id") or ""),
          status_changed_at, source, fetched))
    db.execute("UPDATE order_items SET channel=? WHERE shop_id=? AND posting_number=?",
               (channel, shop_id, number))
    products_by_sku = {}
    for product, price in zip(products, prices):
        sku = str(product.get("sku") or "")
        if not sku:
            continue
        item = products_by_sku.setdefault(sku, [dict(product), price, 0])
        item[0]["offer_id"] = product.get("offer_id") or item[0].get("offer_id")
        item[0]["name"] = product.get("name") or item[0].get("name")
        item[1] = price
        item[2] += int(product.get("quantity") or 1)
    for sku, (product, price, quantity) in products_by_sku.items():
        db.execute("""
          INSERT INTO order_items(shop_id,channel,posting_number,sku,offer_id,product_name_raw,
            quantity,unit_price,price_currency,source)
          VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(shop_id,posting_number,sku) DO UPDATE SET
            channel=excluded.channel,offer_id=COALESCE(NULLIF(excluded.offer_id,''),order_items.offer_id),
            product_name_raw=COALESCE(NULLIF(excluded.product_name_raw,''),order_items.product_name_raw),
            quantity=excluded.quantity,unit_price=COALESCE(excluded.unit_price,order_items.unit_price),
            price_currency=COALESCE(NULLIF(excluded.price_currency,''),order_items.price_currency),source=excluded.source
        """, (shop_id, channel, number, sku, product.get("offer_id"), product.get("name") or "",
              quantity, price[0], price[1], source))
    _apply_pending_webhook_events(db, shop_id, number)
    return channel


def sync_orders(shop_id, start, end):
    base = {"dir": "ASC", "filter": {"since": _utc(start), "to": _utc(end)},
            "limit": 100, "with": {"analytics_data": True, "financial_data": True}}
    fbs = client._cursor_pages(shop_id, "/v4/posting/fbs/list", base, "postings")
    fbo = client._cursor_pages(shop_id, "/v3/posting/fbo/list", base, "postings")
    with connect() as db:
        delivered = {row[0] for row in db.execute(
            "SELECT posting_number FROM orders WHERE shop_id=? AND NULLIF(delivered_at,'') IS NOT NULL", (shop_id,))}
    for posting in fbo:
        if (posting.get("status") == "delivered" and posting["posting_number"] not in delivered
                and not posting.get("fact_delivery_date")):
            detail = client._post(shop_id, "/v2/posting/fbo/get", {
                "posting_number": posting["posting_number"],
                "with": {"analytics_data": False, "financial_data": False}}).get("result") or {}
            posting["fact_delivery_date"] = detail.get("fact_delivery_date")
    fetched = client._stamp()
    with transaction() as db:
        for posting, channel in [(record, None) for record in fbs] + [(record, "WHD") for record in fbo]:
            _save_order(db, shop_id, posting, channel, "api", fetched)
    return {"records": len(fbs) + len(fbo), "FBP": sum(p.get("integration_type_flow") == "FBP" for p in fbs),
            "realFBS": sum(p.get("integration_type_flow") == "aggregator" for p in fbs), "WHD": len(fbo)}


def _rfbs_return_pages(shop_id, start, end):
    base = {"filter": {"created_at": {"from": _utc(start), "to": _utc(end)}}, "limit": 100}
    records, last_id = [], 0
    for _ in range(200):
        body = client._post(shop_id, "/v2/returns/rfbs/list", {**base, "last_id": last_id})
        batch = body.get("returns") or []
        if isinstance(batch, dict):
            batch = [batch]
        records.extend(batch)
        if not batch or body.get("has_next") is False or ("has_next" not in body and len(batch) < base["limit"]):
            return records
        next_id = body.get("last_id") or batch[-1].get("return_id")
        if next_id in (None, "") or str(next_id) == str(last_id):
            raise RuntimeError("/v2/returns/rfbs/list: 分页游标缺失或未前进")
        last_id = next_id
    raise RuntimeError("/v2/returns/rfbs/list: 分页超过安全上限")


def _rfbs_return_reason_details(shop_id, start, end, new_ids=(), include_existing=True):
    new_ids = tuple(dict.fromkeys(new_ids))
    id_clause = f"return_id IN ({','.join('?' for _ in new_ids)})" if new_ids else "0"
    scope = (f"((created_at>=? AND created_at<=?) OR {id_clause})"
             if include_existing else f"({id_clause})")
    args = ((shop_id, _utc(start), _utc(end), *new_ids) if include_existing else (shop_id, *new_ids))
    with connect() as db:
        return_ids = [row[0] for row in db.execute(f"""
          SELECT return_id FROM rfbs_return_records
          WHERE shop_id=? AND detail_fetched_at IS NULL
            AND {scope}
          ORDER BY created_at,return_id
        """, args)]
    saved = 0
    for offset in range(0, len(return_ids), 25):
        updates = []
        for return_id in return_ids[offset:offset + 25]:
            body = client._post(shop_id, "/v2/returns/rfbs/get", {"return_id": return_id})
            detail = body.get("result") if isinstance(body.get("result"), dict) else body
            detail = detail.get("return") if isinstance(detail.get("return"), dict) else detail
            detail = detail.get("returns") if isinstance(detail.get("returns"), dict) else detail
            reason = detail.get("return_reason") or {}
            reason_name = str(reason.get("name") or "").strip() if isinstance(reason, dict) else ""
            stamp = client._stamp()
            updates.append((reason_name or None, reason_name or None, _json(body), stamp, stamp,
                            shop_id, return_id))
        with transaction() as db:
            db.executemany("""UPDATE rfbs_return_records
              SET reason_raw=COALESCE(?,reason_raw),reason_name=COALESCE(?,reason_name),
                payload=?,detail_fetched_at=?,fetched_at=?
              WHERE shop_id=? AND return_id=? AND detail_fetched_at IS NULL
            """, updates)
        saved += len(updates)
    return saved


def sync_returns(shop_id, start, end, include_existing_missing=True):
    payload = {"filter": {"logistic_return_date": {"time_from": _utc(start), "time_to": _utc(end)}}, "limit": 100}
    records = client._cursor_pages(shop_id, "/v1/returns/list", payload, "returns", "last_id", "")
    rfbs_records = _rfbs_return_pages(shop_id, start, end)
    fetched = client._stamp()
    with transaction() as db:
        existing_ids = {row[0] for row in db.execute(
            "SELECT return_id FROM rfbs_return_records WHERE shop_id=?", (shop_id,))}
        for record in records:
            product, logistic = record.get("product") or {}, record.get("logistic") or {}
            db.execute("""INSERT INTO return_records VALUES(?,?,?,?,?,?,?)
              ON CONFLICT(shop_id,record_key) DO UPDATE SET occurred_at=excluded.occurred_at,posting_number=excluded.posting_number,sku=excluded.sku,payload=excluded.payload,fetched_at=excluded.fetched_at
            """, (shop_id, _key(record, "id"), logistic.get("return_date") or logistic.get("final_moment"),
                  record.get("posting_number"), str(product.get("sku") or ""), _json(record), fetched))
        saved, new_ids = 0, []
        for record in rfbs_records:
            return_number = str(record.get("return_number") or "").strip()
            if not return_number:
                continue
            return_id = record.get("return_id")
            if return_id in (None, ""):
                raise RuntimeError("/v2/returns/rfbs/list: 退货申请缺少 return_id")
            product, state = record.get("product") or {}, record.get("state") or {}
            status_raw = state.get("state") or state.get("group_state") or ""
            status_name = state.get("state_name") or state.get("money_return_state_name") or status_raw
            amount = product.get("price") or {}
            if not isinstance(amount, dict):
                amount = {"price": amount}
            logistic = record.get("logistic") or {}
            comment = record.get("client_comment") or record.get("comment") or record.get("buyer_comment")
            db.execute("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,posting_number,offer_id,sku,product_name,
              status_raw,status_name,payload,fetched_at,order_number,quantity,reason_raw,reason_name,
              compensation_status,product_amount,product_currency,logistic_return_at,buyer_comment_raw,
              detail_fetched_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(shop_id,return_id) DO UPDATE SET
                return_number=excluded.return_number,created_at=excluded.created_at,
                posting_number=excluded.posting_number,offer_id=excluded.offer_id,sku=excluded.sku,
                product_name=excluded.product_name,status_raw=excluded.status_raw,
                status_name=excluded.status_name,
                payload=CASE WHEN rfbs_return_records.detail_fetched_at IS NOT NULL
                  THEN rfbs_return_records.payload ELSE excluded.payload END,
                fetched_at=excluded.fetched_at,order_number=excluded.order_number,quantity=excluded.quantity,
                reason_raw=rfbs_return_records.reason_raw,reason_name=rfbs_return_records.reason_name,
                compensation_status=excluded.compensation_status,
                product_amount=excluded.product_amount,product_currency=excluded.product_currency,
                logistic_return_at=excluded.logistic_return_at,buyer_comment_raw=excluded.buyer_comment_raw
            """, (shop_id, return_id, return_number, record.get("created_at"), record.get("posting_number"),
                  product.get("offer_id"), str(product.get("sku") or ""), product.get("name") or "",
                  status_raw, status_name, _json(record), fetched, record.get("order_number"),
                  int(record.get("quantity") or product.get("quantity") or 1),
                  None, None,
                  state.get("money_return_state_name") or state.get("money_return_state"),
                  amount.get("price") or amount.get("amount"),
                  amount.get("currency_code") or amount.get("currency"),
                  logistic.get("return_date") or logistic.get("arrived_at"), comment, None))
            if return_id not in existing_ids:
                new_ids.append(return_id)
            saved += 1
    _rfbs_return_reason_details(shop_id, start, end, new_ids, include_existing_missing)
    return {"records": len(records) + saved, "cancellations": len(records), "return_requests": saved}


def _sync_stock_snapshot(shop_id):
    records = client._cursor_pages(shop_id, "/v4/product/info/stocks",
                                   {"filter": {"visibility": "ALL"}, "limit": 1000}, "items")
    observed = client._stamp()
    with transaction() as db:
        for record in records:
            record_key = str(record.get("product_id") or record.get("offer_id") or _key(record))
            db.execute("""INSERT INTO stock_snapshots VALUES(?,?,?,?)
              ON CONFLICT(shop_id,record_key) DO UPDATE SET
                observed_at=excluded.observed_at,payload=excluded.payload""",
                       (shop_id, record_key, observed, _json(record)))
            for value in record.get("stocks") or []:
                stock_type = str(value.get("type") or "")
                db.execute("""INSERT OR IGNORE INTO stock_history(
                  shop_id,source,warehouse_id,sku,present,reserved,occurred_at,event_key,payload_json)
                  VALUES(?,?,?,?,?,?,?,?,?)""",
                  (shop_id, "api", ",".join(map(str, value.get("warehouse_ids") or [])),
                   str(value.get("sku") or record.get("product_id") or ""),
                   int(value.get("present") or 0), int(value.get("reserved") or 0), observed,
                   record_key + ":" + observed + ":" + stock_type, _json(record)))
    return {"records": len(records), "snapshot_at": observed}


def sync_module(module, shop_id, start=None, end=None, include_existing_missing=True):
    start, end = (start, end) if start and end else default_range()
    functions = {"orders": sync_orders,
                 "returns": lambda s, a, b: sync_returns(s, a, b, include_existing_missing),
                 "stock": lambda s, _a, _b: _sync_stock_snapshot(s)}
    if module not in functions:
        raise ValueError("未知同步模块")
    return functions[module](shop_id, start, end)
