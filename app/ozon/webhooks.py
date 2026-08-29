import hashlib
import json
import threading
from datetime import datetime

from . import client
from ..db import connect, transaction
from .mappings import (PUSH_CANCEL_TYPES, PUSH_ORDER_TYPES, PUSH_POSTING_TYPES,
                       PUSH_STATE_TYPES, PUSH_STATUS_ZH, PUSH_STOCK_TYPES)


def _canonical_json(record):
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def webhook_event_key(payload):
    value = str(payload.get("uuid") or "").strip()
    if value:
        return value
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _cancel_time(payload, message_type):
    fields = ("cancel_date", "changed_state_date", "changed_at", "cancelled_at") \
        if message_type in {"TYPE_FBO_POSTING_CANCELLED", "TYPE_FBO_POSTING_STATE_CHANGED"} else \
        ("changed_state_date", "changed_at", "cancelled_at", "cancel_date")
    for field in fields:
        stamp = client._timestamp(payload.get(field))
        if stamp:
            return stamp
    return None


def _cancel_reason(payload):
    reason = payload.get("reason") if isinstance(payload.get("reason"), dict) else {}
    reason_id = reason.get("id") if reason.get("id") not in (None, "") else payload.get("cancel_reason_id")
    reason_raw = reason.get("message") or payload.get("cancel_reason")
    return (str(reason_id) if reason_id not in (None, "") else None,
            str(reason_raw).strip() if reason_raw not in (None, "") else None)


def _state_time(payload):
    for field in ("changed_state_date", "changed_at"):
        stamp = client._timestamp(payload.get(field))
        if stamp:
            return stamp
    return None


def _event_occurred_at(payload, message_type, received_at):
    candidates = []
    if message_type in PUSH_CANCEL_TYPES:
        candidates.append(_cancel_time(payload, message_type))
    elif message_type in PUSH_STATE_TYPES:
        candidates.append(_state_time(payload))
    elif message_type in PUSH_STOCK_TYPES:
        candidates.extend(client._timestamp(payload.get(field)) for field in ("updated_at", "time"))
        for item in payload.get("items") or []:
            if isinstance(item, dict):
                candidates.append(client._timestamp(item.get("updated_at")))
                stocks = item.get("stocks")
                if isinstance(stocks, dict):
                    candidates.append(client._timestamp(stocks.get("updated_at")))
                elif isinstance(stocks, list):
                    candidates.extend(client._timestamp(stock.get("updated_at")) for stock in stocks
                                      if isinstance(stock, dict))
        stocks = payload.get("stocks")
        if isinstance(stocks, dict):
            candidates.append(client._timestamp(stocks.get("updated_at")))
    else:
        candidates.extend(client._timestamp(payload.get(field)) for field in (
            "in_process_at", "created_at", "changed_at", "updated_at", "time"))
    candidates = [value for value in candidates if value]
    if candidates:
        return max(candidates, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
    return received_at


def _posting_number(payload):
    return str(payload.get("posting_number") or "").strip() or None


def _order_number(payload):
    value = payload.get("order_number") or payload.get("order_id")
    return str(value).strip() if value not in (None, "") else None


def _stock_entries(payload, message_type):
    if message_type == "TYPE_FBO_STOCKS_CHANGED" and isinstance(payload.get("stocks"), dict):
        return [(payload, payload.get("stocks"))]
    if message_type == "TYPE_STOCKS_CHANGED" and any(
            payload.get(field) is not None for field in ("present", "reserved", "warehouse_id")):
        return [(payload, payload)]
    entries = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        stocks = item.get("stocks")
        if isinstance(stocks, dict):
            stocks = [stocks]
        elif not isinstance(stocks, list) and any(
                item.get(field) is not None for field in ("present", "reserved", "warehouse_id")):
            stocks = [item]
        for stock in stocks or []:
            if isinstance(stock, dict):
                entries.append((item, stock))
    return entries


def webhook_validation_error(payload):
    if not isinstance(payload, dict):
        return "Webhook JSON必须是对象"
    message_type = str(payload.get("message_type") or "").strip()
    if not message_type:
        return "缺少 message_type"
    if message_type in PUSH_POSTING_TYPES and not _posting_number(payload):
        return "缺少 posting_number"
    if message_type in PUSH_ORDER_TYPES and not (_posting_number(payload) or _order_number(payload)):
        return "缺少 order_number 或 posting_number"
    if message_type in PUSH_CANCEL_TYPES and not _cancel_time(payload, message_type):
        return "取消事件缺少有效官方时间"
    if message_type in PUSH_STATE_TYPES:
        if not str(payload.get("new_state") or "").strip():
            return "状态事件缺少 new_state"
        if not _state_time(payload):
            return "状态事件缺少有效官方时间"
    if message_type == "TYPE_STOCKS_CHANGED":
        entries = _stock_entries(payload, message_type)
        if not entries:
            return "库存事件缺少 items/stocks"
        for item, stock in entries:
            if not str(item.get("sku") or item.get("product_id") or "").strip():
                return "库存事件缺少 sku"
            if item.get("warehouse_id") in (None, "") and stock.get("warehouse_id") in (None, ""):
                return "库存事件缺少 warehouse_id"
            if not (client._timestamp(item.get("updated_at")) or client._timestamp(payload.get("updated_at"))):
                return "库存事件缺少有效 updated_at"
            if stock.get("present") is None or stock.get("reserved") is None:
                return "库存事件缺少 present/reserved"
    if message_type == "TYPE_FBO_STOCKS_CHANGED":
        entries = _stock_entries(payload, message_type)
        if not entries:
            return "FBO库存事件缺少 sku/stocks"
        for item, stock in entries:
            if not str(item.get("sku") or item.get("product_id") or "").strip():
                return "FBO库存事件缺少 sku"
            if not (client._timestamp(item.get("updated_at")) or client._timestamp(payload.get("updated_at"))
                    or client._timestamp(stock.get("updated_at"))):
                return "FBO库存事件缺少有效官方时间"
            if ((stock.get("new_present") if "new_present" in stock else stock.get("present")) is None
                    or (stock.get("new_reserved") if "new_reserved" in stock else stock.get("reserved")) is None):
                return "FBO库存事件缺少 new_present/new_reserved"
    return None


def persist_webhook_event(shop_id, payload, received_at=None):
    received_at = client._timestamp(received_at) or client._stamp()
    message_type = str(payload.get("message_type") or "").strip()
    event_key = webhook_event_key(payload)
    payload_json = _canonical_json(payload)
    occurred_at = _event_occurred_at(payload, message_type, received_at)
    with transaction() as db:
        cursor = db.execute("""INSERT OR IGNORE INTO ozon_webhook_events(
          event_key,shop_id,message_type,posting_number,order_number,occurred_at,payload_json,received_at)
          VALUES(?,?,?,?,?,?,?,?)""",
          (event_key, shop_id, message_type, _posting_number(payload), _order_number(payload),
           occurred_at, payload_json, received_at))
        row = db.execute("""SELECT event_key,shop_id,message_type,posting_number,order_number,
          occurred_at,payload_json,received_at,applied_at,error FROM ozon_webhook_events
          WHERE shop_id=? AND event_key=?""", (shop_id, event_key)).fetchone()
    result = dict(row)
    result["new"] = cursor.rowcount == 1
    return result


def _mark_webhook_event(db, row, error=None):
    db.execute("""UPDATE ozon_webhook_events SET applied_at=COALESCE(applied_at,?),error=?
      WHERE shop_id=? AND event_key=?""", (client._stamp(), error, row["shop_id"], row["event_key"]))


def _push_cancellation(db, shop_id, posting_number):
    rows = db.execute("""SELECT message_type,payload_json FROM ozon_webhook_events
      WHERE shop_id=? AND posting_number=? AND message_type IN
      ('TYPE_POSTING_CANCELLED','TYPE_FBO_POSTING_CANCELLED','TYPE_STATE_CHANGED',
       'TYPE_FBO_POSTING_STATE_CHANGED')""",
                      (shop_id, posting_number)).fetchall()
    cancellations = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        message_type = row["message_type"]
        if message_type in PUSH_STATE_TYPES and str(payload.get("new_state") or "").lower() not in (
                "posting_canceled", "posting_cancelled", "cancelled", "canceled"):
            continue
        stamp = _cancel_time(payload, message_type)
        if stamp:
            reason_id, reason_raw = _cancel_reason(payload)
            cancellations.append((stamp, reason_id, reason_raw))
    if not cancellations:
        return None
    cancellations.sort(key=lambda value: value[0])
    occurred_at = cancellations[0][0]
    reason_id = next((value[1] for value in cancellations if value[1] not in (None, "")), None)
    reason_raw = next((value[2] for value in cancellations if value[2]), None)
    return {"occurred_at": occurred_at, "reason_id": reason_id, "reason_raw": reason_raw}


def _apply_cancellation(db, row):
    order = db.execute("SELECT * FROM orders WHERE shop_id=? AND posting_number=?",
                       (row["shop_id"], row["posting_number"])).fetchone()
    if not order:
        return False
    payload = json.loads(row["payload_json"])
    cancellation = _push_cancellation(db, row["shop_id"], row["posting_number"])
    if not cancellation:
        cancellation = {"occurred_at": _cancel_time(payload, row["message_type"]),
                        "reason_id": None, "reason_raw": None}
    current_at = client._timestamp(order["status_changed_at"])
    if (order["status_raw"] not in ("已取消", "cancelled", "canceled") and current_at
            and datetime.fromisoformat(cancellation["occurred_at"].replace("Z", "+00:00"))
            <= datetime.fromisoformat(current_at.replace("Z", "+00:00"))):
        return True
    reason_id, reason_raw = _cancel_reason(payload)
    db.execute("""UPDATE orders SET status_raw='已取消',status_changed_at=?,
      cancel_reason_id=COALESCE(?,cancel_reason_id),cancel_reason_raw=COALESCE(?,cancel_reason_raw),
      updated_at=? WHERE shop_id=? AND posting_number=?""",
      (cancellation["occurred_at"], cancellation["reason_id"] or reason_id,
       cancellation["reason_raw"] or reason_raw, client._stamp(), row["shop_id"], row["posting_number"]))
    return True


def _apply_state_change(db, row):
    order = db.execute("SELECT * FROM orders WHERE shop_id=? AND posting_number=?",
                       (row["shop_id"], row["posting_number"])).fetchone()
    if not order:
        return False
    payload = json.loads(row["payload_json"])
    new_state = str(payload.get("new_state") or "").strip().lower()
    status_raw = PUSH_STATUS_ZH.get(new_state)
    if not status_raw and new_state.startswith("posting_on_way_"):
        status_raw = "运输中"
    if not status_raw:
        return True
    if status_raw == "已取消":
        return _apply_cancellation(db, row)
    if order["status_raw"] == "已取消":
        return True
    changed_at = _state_time(payload)
    current_at = client._timestamp(order["status_changed_at"])
    if current_at and datetime.fromisoformat(changed_at.replace("Z", "+00:00")) <= datetime.fromisoformat(current_at.replace("Z", "+00:00")):
        return True
    shipped = int(status_raw in ("运输中", "已签收"))
    delivered_at = changed_at if status_raw == "已签收" and not order["delivered_at"] else order["delivered_at"]
    db.execute("""UPDATE orders SET status_raw=?,status_changed_at=?,shipped=?,delivered_at=?,updated_at=?
      WHERE shop_id=? AND posting_number=?""",
      (status_raw, changed_at, shipped, delivered_at, client._stamp(), row["shop_id"], row["posting_number"]))
    return True


def _apply_stock_change(db, row):
    payload = json.loads(row["payload_json"])
    message_type = row["message_type"]
    for item, stock in _stock_entries(payload, message_type):
        sku = str(item.get("sku") or item.get("product_id") or "").strip()
        warehouse_id = item.get("warehouse_id")
        if warehouse_id in (None, ""):
            warehouse_id = stock.get("warehouse_id") or payload.get("warehouse_id") or ""
        present = stock.get("new_present") if message_type == "TYPE_FBO_STOCKS_CHANGED" else stock.get("present")
        reserved = stock.get("new_reserved") if message_type == "TYPE_FBO_STOCKS_CHANGED" else stock.get("reserved")
        if present is None:
            present = stock.get("present")
        if reserved is None:
            reserved = stock.get("reserved")
        stamp = (client._timestamp(item.get("updated_at")) or client._timestamp(stock.get("updated_at"))
                 or client._timestamp(payload.get("updated_at")) or row["occurred_at"])
        db.execute("""INSERT INTO stock_history(
          shop_id,source,warehouse_id,sku,present,reserved,occurred_at,event_key,payload_json)
          VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(shop_id,source,event_key,warehouse_id,sku) DO UPDATE SET
            present=excluded.present,reserved=excluded.reserved,occurred_at=excluded.occurred_at,
            payload_json=excluded.payload_json""",
          (row["shop_id"], "push_fbo" if message_type == "TYPE_FBO_STOCKS_CHANGED" else "push_rfbs",
           str(warehouse_id), sku, int(present), int(reserved), stamp, row["event_key"], row["payload_json"]))
    return True


def _apply_webhook_event(db, row):
    message_type = row["message_type"]
    if message_type in PUSH_CANCEL_TYPES:
        return _apply_cancellation(db, row)
    if message_type in PUSH_STATE_TYPES:
        return _apply_state_change(db, row)
    if message_type in PUSH_STOCK_TYPES:
        return _apply_stock_change(db, row)
    return True


def _apply_pending_webhook_events(db, shop_id, posting_number):
    rows = db.execute("""SELECT * FROM ozon_webhook_events
      WHERE shop_id=? AND posting_number=? AND applied_at IS NULL
      ORDER BY occurred_at IS NULL,occurred_at,received_at,event_key""",
                      (shop_id, posting_number)).fetchall()
    for row in rows:
        try:
            if _apply_webhook_event(db, row):
                _mark_webhook_event(db, row)
        except Exception as error:
            db.execute("UPDATE ozon_webhook_events SET error=? WHERE shop_id=? AND event_key=?",
                       (str(error)[:500], shop_id, row["event_key"]))


def _channel_hint(payload):
    flow = str(payload.get("integration_type_flow") or payload.get("tpl_integration_type") or "")
    if flow == "FBP":
        return "FBP"
    if flow.lower() in ("aggregator", "realfbs", "rfbs"):
        return "realFBS"
    return None


def complete_webhook_posting(shop_id, event_key):
    with connect() as db:
        row = db.execute("SELECT * FROM ozon_webhook_events WHERE shop_id=? AND event_key=?",
                         (shop_id, event_key)).fetchone()
    if not row or row["applied_at"]:
        return None
    payload = json.loads(row["payload_json"])
    is_fbo = row["message_type"] == "TYPE_FBO_POSTING_NEW"
    path = "/v2/posting/fbo/get" if is_fbo else "/v3/posting/fbs/get"
    try:
        response = client._post(shop_id, path, {"posting_number": row["posting_number"],
                                                 "with": {"analytics_data": True, "financial_data": True}})
        detail = response.get("result") if isinstance(response.get("result"), dict) else response
        if not isinstance(detail, dict):
            raise ValueError(f"{path}: 详情响应不是对象")
        detail = dict(detail)
        detail.setdefault("posting_number", row["posting_number"])
        from .sync import _save_order
        with transaction() as db:
            _save_order(db, shop_id, detail, "WHD" if is_fbo else _channel_hint(payload), "api")
        return detail
    except Exception as error:
        with transaction() as db:
            db.execute("UPDATE ozon_webhook_events SET error=? WHERE shop_id=? AND event_key=?",
                       (str(error)[:500], shop_id, event_key))
        raise


def _complete_webhook_posting_async(shop_id, event_key):
    try:
        complete_webhook_posting(shop_id, event_key)
    except Exception:
        pass


def process_webhook_event(shop_id, payload, received_at=None):
    row = persist_webhook_event(shop_id, payload, received_at)
    if row["message_type"] in {"TYPE_NEW_POSTING", "TYPE_FBO_POSTING_NEW"}:
        if not row["applied_at"]:
            threading.Thread(target=_complete_webhook_posting_async,
                             args=(shop_id, row["event_key"]), daemon=True).start()
        return row
    if not row["applied_at"]:
        with transaction() as db:
            current = db.execute("SELECT * FROM ozon_webhook_events WHERE shop_id=? AND event_key=?",
                                 (shop_id, row["event_key"])).fetchone()
            try:
                if current and _apply_webhook_event(db, current):
                    _mark_webhook_event(db, current)
            except Exception as error:
                db.execute("UPDATE ozon_webhook_events SET error=? WHERE shop_id=? AND event_key=?",
                           (str(error)[:500], shop_id, row["event_key"]))
    return row
