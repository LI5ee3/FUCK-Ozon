import hashlib
import json
from datetime import datetime, timezone

from .db import connect, transaction
from .ozon import STATUS_ZH, _env

PUSH_TYPES = (
    "TYPE_PING", "TYPE_NEW_POSTING", "TYPE_POSTING_CANCELLED", "TYPE_STATE_CHANGED",
    "TYPE_FBO_POSTING_NEW", "TYPE_FBO_POSTING_CANCELLED",
    "TYPE_FBO_POSTING_STATE_CHANGED", "TYPE_FBO_STOCKS_CHANGED", "TYPE_STOCKS_CHANGED",
)
FBO_TYPES = {
    "TYPE_FBO_POSTING_NEW", "TYPE_FBO_POSTING_CANCELLED",
    "TYPE_FBO_POSTING_STATE_CHANGED", "TYPE_FBO_STOCKS_CHANGED",
}


class PushRequestError(ValueError):
    pass


class PushAuthError(PushRequestError):
    pass


class PushProcessingError(RuntimeError):
    pass


class PendingMatch(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc(value):
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise PushRequestError(f"无效UTC时间：{value}") from error
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_key(shop_id, message_type, payload):
    seller_id = str(payload.get("seller_id") or "")
    if payload.get("uuid"):
        return f"{seller_id}:{payload['uuid']}"
    business_key = payload.get("posting_number") or payload.get("order_number") or ""
    source = f"{shop_id}|{seller_id}|{message_type}|{business_key}|{_json(payload)}"
    return hashlib.sha256(source.encode()).hexdigest()


def _occurred_at(payload):
    for key in ("time", "changed_state_date", "cancel_date", "creation_date",
                "in_process_at", "shipment_date", "updated_at"):
        if payload.get(key):
            return _utc(payload[key])
    for item in payload.get("items") or []:
        if item.get("updated_at"):
            return _utc(item["updated_at"])
    stocks = payload.get("stocks") or []
    stocks = stocks if isinstance(stocks, list) else [stocks]
    return _utc(stocks[0].get("updated_at")) if stocks and stocks[0].get("updated_at") else None


def _shop(shop_token):
    with connect() as db:
        row = db.execute("SELECT id,name,seller_id FROM shops WHERE push_token=?", (shop_token,)).fetchone()
    if not row:
        raise PushAuthError("回调地址无效")
    return dict(row)


def _channel(db, shop_id, payload, fbo=False):
    if fbo:
        return "WHD"
    posting = str(payload.get("posting_number") or "")
    existing = db.execute("SELECT channel FROM orders WHERE shop_id=? AND posting_number=?",
                          (shop_id, posting)).fetchone() if posting else None
    if existing:
        return existing[0]
    flow = payload.get("integration_type_flow") or payload.get("delivery_schema") or payload.get("channel")
    if flow in ("FBP", "fbp"):
        return "FBP"
    if flow in ("aggregator", "realFBS", "rfbs", "rFBS"):
        return "realFBS"
    raise PendingMatch("无法根据现有规则识别 FBP 或 realFBS 渠道")


def _upsert_products(db, shop_id, posting, channel, products):
    db.execute("UPDATE order_items SET channel=? WHERE shop_id=? AND posting_number=?",
               (channel, shop_id, posting))
    for product in products or []:
        sku = str(product.get("sku") or "").strip()
        quantity = int(product.get("quantity") or 0)
        if not sku or quantity <= 0:
            continue
        db.execute("""INSERT INTO order_items(
          shop_id,channel,posting_number,sku,offer_id,product_name_raw,quantity,source)
          VALUES(?,?,?,?,?,?,?,'push') ON CONFLICT(shop_id,posting_number,sku) DO UPDATE SET
          channel=excluded.channel,offer_id=COALESCE(NULLIF(excluded.offer_id,''),order_items.offer_id),
          product_name_raw=COALESCE(NULLIF(excluded.product_name_raw,''),order_items.product_name_raw),
          quantity=excluded.quantity,source='push'""",
                   (shop_id, channel, posting, sku, product.get("offer_id"), product.get("name") or "", quantity))


def _upsert_order(db, shop_id, seller_id, payload, channel):
    posting = str(payload.get("posting_number") or "").strip()
    if not posting:
        raise PushRequestError("posting_number 不能为空")
    created = _utc(payload.get("in_process_at") or payload.get("creation_date") or payload.get("created_at"))
    shipment = _utc(payload.get("shipment_date"))
    delivery = payload.get("delivery_date") if isinstance(payload.get("delivery_date"), dict) else {}
    delivery_begin = _utc(payload.get("delivery_date_begin") or delivery.get("from"))
    delivery_end = _utc(payload.get("delivery_date_end") or delivery.get("to"))
    db.execute("""INSERT INTO orders(
      shop_id,posting_number,parent_order_no,channel,created_at,status_raw,warehouse_id,seller_id,
      external_uuid,shipment_date,delivery_date_begin,delivery_date_end,source)
      VALUES(?,?,?,?,?,'',?,?,?,?,?,?,'push') ON CONFLICT(shop_id,posting_number) DO UPDATE SET
      parent_order_no=COALESCE(NULLIF(excluded.parent_order_no,''),orders.parent_order_no),
      channel=excluded.channel,created_at=COALESCE(NULLIF(excluded.created_at,''),orders.created_at),
      warehouse_id=COALESCE(NULLIF(excluded.warehouse_id,''),orders.warehouse_id),
      seller_id=COALESCE(NULLIF(excluded.seller_id,''),orders.seller_id),
      external_uuid=COALESCE(NULLIF(excluded.external_uuid,''),orders.external_uuid),
      shipment_date=COALESCE(NULLIF(excluded.shipment_date,''),orders.shipment_date),
      delivery_date_begin=COALESCE(NULLIF(excluded.delivery_date_begin,''),orders.delivery_date_begin),
      delivery_date_end=COALESCE(NULLIF(excluded.delivery_date_end,''),orders.delivery_date_end),source='push'""",
               (shop_id, posting, payload.get("order_number"), channel, created,
                str(payload.get("warehouse_id") or ""), seller_id, payload.get("uuid"), shipment,
                delivery_begin, delivery_end))
    _upsert_products(db, shop_id, posting, channel, payload.get("products"))
    return posting


def _state(db, shop_id, posting, message_type, event_key, raw, occurred_at, payload,
           reason_id=None, reason=None):
    if not raw or not occurred_at:
        raise PushRequestError("状态代码和状态时间不能为空")
    display = STATUS_ZH.get(raw, "已取消" if "cancel" in raw.lower() else raw)
    shipped = int(display in ("运输中", "已签收"))
    delivered = int(display == "已签收")
    db.execute("""INSERT OR IGNORE INTO order_status_history(
      shop_id,posting_number,message_type,event_key,status_raw,status_name,reason_id,reason_message,
      occurred_at,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?)""",
               (shop_id, posting, message_type, event_key, raw, display,
                str(reason_id or "") or None, reason, occurred_at, _json(payload)))
    db.execute("""UPDATE orders SET status_raw=?,status_changed_at=?,
      shipped=CASE WHEN ?=1 THEN 1 ELSE shipped END,
      shipped_at=CASE WHEN ?=1 AND NULLIF(shipped_at,'') IS NULL THEN ? ELSE shipped_at END,
      delivered_at=CASE WHEN ?=1 AND NULLIF(delivered_at,'') IS NULL THEN ? ELSE delivered_at END,
      cancel_reason_raw=CASE WHEN ? IS NULL OR ?='' THEN cancel_reason_raw ELSE ? END,
      cancel_reason_id=CASE WHEN ? IS NULL OR ?='' THEN cancel_reason_id ELSE ? END,
      cancelled_after_ship=CASE WHEN ?=1 THEN CASE WHEN shipped=1 OR NULLIF(shipped_at,'') IS NOT NULL THEN 1 ELSE 0 END
        ELSE cancelled_after_ship END,updated_at=?,source='push'
      WHERE shop_id=? AND posting_number=?
      AND (status_changed_at IS NULL OR status_changed_at='' OR status_changed_at<=?)""",
               (display, occurred_at, shipped, shipped, occurred_at, delivered, occurred_at,
                reason, reason, reason, reason_id, reason_id, reason_id,
                int("cancel" in raw.lower()), _now(),
                shop_id, posting, occurred_at))


def _posting_event(db, shop_id, seller_id, message_type, event_key, payload):
    fbo = message_type in FBO_TYPES
    channel = _channel(db, shop_id, payload, fbo)
    posting = _upsert_order(db, shop_id, seller_id, payload, channel)
    if message_type.endswith("CANCELLED"):
        reason = payload.get("reason") or {}
        reason_text = reason.get("message") if isinstance(reason, dict) else str(reason or "")
        reason_id = reason.get("id") if isinstance(reason, dict) else None
        occurred = _utc(payload.get("changed_state_date") or payload.get("cancel_date"))
        _state(db, shop_id, posting, message_type, event_key,
               payload.get("new_state") or "cancelled", occurred, payload,
               reason_id, reason_text or "原因暂缺")
    elif message_type.endswith("STATE_CHANGED"):
        _state(db, shop_id, posting, message_type, event_key, payload.get("new_state"),
               _utc(payload.get("changed_state_date")), payload)


def _stocks(value):
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def _seller_stocks(db, shop_id, payload):
    for item in payload.get("items") or []:
        sku = str(item.get("sku") or "").strip()
        updated = _utc(item.get("updated_at"))
        if not sku or not updated:
            raise PushRequestError("库存 SKU 和 updated_at 不能为空")
        for stock in _stocks(item.get("stocks")):
            warehouse = str(stock.get("warehouse_id") or "").strip()
            if not warehouse or stock.get("present") is None or stock.get("reserved") is None:
                raise PushRequestError("FBS/rFBS 库存缺少 warehouse_id、present 或 reserved")
            db.execute("""INSERT INTO warehouse_stocks(
              shop_id,warehouse_id,sku,product_id,present,reserved,updated_at,payload_json)
              VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(shop_id,warehouse_id,sku) DO UPDATE SET
              product_id=COALESCE(NULLIF(excluded.product_id,''),warehouse_stocks.product_id),
              present=excluded.present,reserved=excluded.reserved,updated_at=excluded.updated_at,
              payload_json=excluded.payload_json WHERE warehouse_stocks.updated_at<=excluded.updated_at""",
                       (shop_id, warehouse, sku, str(item.get("product_id") or ""),
                        int(stock["present"]), int(stock["reserved"]), updated, _json(item)))
            db.execute("""INSERT OR IGNORE INTO stock_history(
              shop_id,source,warehouse_id,sku,present,reserved,occurred_at,event_key,payload_json)
              VALUES(?,?,?,?,?,?,?,?,?)""",
              (shop_id, "webhook", warehouse, sku, int(stock["present"]), int(stock["reserved"]),
               updated, _event_key(shop_id, "TYPE_STOCKS_CHANGED", payload), _json(item)))


def _fbo_stocks(db, shop_id, payload):
    for stock in _stocks(payload.get("stocks")):
        sku = str(stock.get("sku") or payload.get("sku") or "").strip()
        updated = _utc(stock.get("updated_at") or payload.get("updated_at"))
        if not sku or not updated or stock.get("new_present") is None or stock.get("new_reserved") is None:
            raise PushRequestError("FBO 库存 SKU、时间和新库存不能为空")
        db.execute("""INSERT INTO fbo_stocks(
          shop_id,sku,updated_at,new_present,new_reserved,old_present,old_reserved,payload_json)
          VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(shop_id,sku) DO UPDATE SET
          updated_at=excluded.updated_at,new_present=excluded.new_present,new_reserved=excluded.new_reserved,
          old_present=excluded.old_present,old_reserved=excluded.old_reserved,payload_json=excluded.payload_json
          WHERE fbo_stocks.updated_at<=excluded.updated_at""",
                   (shop_id, sku, updated, int(stock["new_present"]), int(stock["new_reserved"]),
                    stock.get("old_present"), stock.get("old_reserved"), _json(stock)))
        db.execute("""INSERT OR IGNORE INTO stock_history(
          shop_id,source,warehouse_id,sku,present,reserved,occurred_at,event_key,payload_json)
          VALUES(?,?,?,?,?,?,?,?,?)""",
          (shop_id, "webhook_fbo", "", sku, int(stock["new_present"]), int(stock["new_reserved"]),
           updated, _event_key(shop_id, "TYPE_FBO_STOCKS_CHANGED", payload), _json(stock)))


def _process(db, shop_id, seller_id, message_type, event_key, payload):
    if message_type in {"TYPE_NEW_POSTING", "TYPE_POSTING_CANCELLED", "TYPE_STATE_CHANGED",
                        "TYPE_FBO_POSTING_NEW", "TYPE_FBO_POSTING_CANCELLED",
                        "TYPE_FBO_POSTING_STATE_CHANGED"}:
        _posting_event(db, shop_id, seller_id, message_type, event_key, payload)
    elif message_type == "TYPE_STOCKS_CHANGED":
        _seller_stocks(db, shop_id, payload)
    elif message_type == "TYPE_FBO_STOCKS_CHANGED":
        _fbo_stocks(db, shop_id, payload)


def receive_push(shop_token, payload):
    if not isinstance(payload, dict):
        raise PushRequestError("JSON 请求体必须是对象")
    message_type = payload.get("message_type")
    if message_type not in PUSH_TYPES:
        raise PushRequestError("不支持的 message_type")
    shop = _shop(shop_token)
    seller_id = str(payload.get("seller_id") or "")
    if message_type != "TYPE_PING":
        if not shop["seller_id"]:
            raise PushRequestError("店铺尚未配置 seller_id")
        if seller_id != str(shop["seller_id"]):
            raise PushAuthError("seller_id 与回调店铺不匹配")
    event_key = _event_key(shop["id"], message_type, payload)
    received = _now()
    occurred = _occurred_at(payload)
    raw = _json(payload)
    with transaction() as db:
        db.execute("""INSERT INTO webhook_events(
          shop_id,message_type,event_key,occurred_at,received_at,payload_json,processing_status)
          VALUES(?,?,?,?,?,?,'received') ON CONFLICT(shop_id,event_key) DO UPDATE SET
          received_at=excluded.received_at""", (shop["id"], message_type, event_key, occurred, received, raw))
        event = db.execute("SELECT processing_status FROM webhook_events WHERE shop_id=? AND event_key=?",
                           (shop["id"], event_key)).fetchone()
        previous = event[0]
        if message_type == "TYPE_PING":
            db.execute("UPDATE webhook_events SET processing_status='processed',error_message=NULL WHERE shop_id=? AND event_key=?",
                       (shop["id"], event_key))
            return {"version": _env().get("APP_VERSION", "1.0.0"), "name": "FUCK Ozon", "time": received}
        if previous == "processed":
            return {"result": True}
    try:
        with transaction() as db:
            _process(db, shop["id"], seller_id, message_type, event_key, payload)
            db.execute("UPDATE webhook_events SET processing_status='processed',error_message=NULL WHERE shop_id=? AND event_key=?",
                       (shop["id"], event_key))
    except PendingMatch as error:
        with transaction() as db:
            db.execute("UPDATE webhook_events SET processing_status='pending_match',error_message=? WHERE shop_id=? AND event_key=?",
                       (str(error)[:500], shop["id"], event_key))
    except PushRequestError as error:
        with transaction() as db:
            db.execute("UPDATE webhook_events SET processing_status='failed',error_message=? WHERE shop_id=? AND event_key=?",
                       (str(error)[:500], shop["id"], event_key))
        raise
    except Exception as error:
        message = str(error)[:500]
        with transaction() as db:
            db.execute("UPDATE webhook_events SET processing_status='failed',error_message=? WHERE shop_id=? AND event_key=?",
                       (message, shop["id"], event_key))
        raise PushProcessingError(message) from error
    return {"result": True}


def retry_pending(event_id):
    with connect() as db:
        row = db.execute("""SELECT e.*,s.push_token FROM webhook_events e JOIN shops s ON s.id=e.shop_id
          WHERE e.id=? AND e.processing_status='pending_match'""", (event_id,)).fetchone()
    if not row:
        raise PushRequestError("待匹配事件不存在")
    return receive_push(row["push_token"], json.loads(row["payload_json"]))


def push_settings(base_url):
    with connect() as db:
        shops = [dict(row) for row in db.execute("SELECT id,name,seller_id,push_token FROM shops ORDER BY id")]
        events = [dict(row) for row in db.execute("""SELECT shop_id,
          MAX(CASE WHEN message_type='TYPE_PING' AND processing_status='processed' THEN received_at END) last_ping_at,
          MAX(CASE WHEN message_type<>'TYPE_PING' THEN received_at END) last_business_event_at,
          MAX(CASE WHEN processing_status='failed' THEN received_at END) last_failure_at
          FROM webhook_events GROUP BY shop_id""")]
        failures = {row["shop_id"]: dict(row) for row in db.execute("""SELECT e.shop_id,e.error_message FROM webhook_events e
          JOIN (SELECT shop_id,MAX(id) id FROM webhook_events WHERE processing_status='failed' GROUP BY shop_id) x
          ON x.shop_id=e.shop_id AND x.id=e.id""")}
    by_shop = {row["shop_id"]: row for row in events}
    for shop in shops:
        status = by_shop.get(shop["id"], {})
        shop.update(status)
        shop["last_error"] = failures.get(shop["id"], {}).get("error_message")
        shop["callback_url"] = f"{base_url.rstrip('/')}/api/ozon/push/{shop['push_token']}"
        latest_ok = max(filter(None, (shop.get("last_ping_at"), shop.get("last_business_event_at"))), default=None)
        if not shop["seller_id"]:
            shop["connection_status"] = "未配置 seller_id"
        elif shop.get("last_failure_at") and (not latest_ok or shop["last_failure_at"] > latest_ok):
            shop["connection_status"] = "处理异常"
        elif latest_ok:
            shop["connection_status"] = "已连接"
        else:
            shop["connection_status"] = "等待 Ozon 验证"
        shop["event_types"] = PUSH_TYPES
    return shops


def save_seller_ids(values):
    seller_ids = [str(values.get(str(shop_id), "")).strip() for shop_id in (1, 2)]
    if not all(value.isdigit() for value in seller_ids):
        raise PushRequestError("两个店铺的 seller_id 必须是数字")
    if seller_ids[0] == seller_ids[1]:
        raise PushRequestError("两个店铺的 seller_id 不能相同")
    with transaction() as db:
        for shop_id, seller_id in enumerate(seller_ids, 1):
            db.execute("UPDATE shops SET seller_id=? WHERE id=?", (seller_id, shop_id))
