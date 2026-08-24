import json
import os
import threading
import time
import urllib.error
import urllib.request
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .db import connect, transaction

API = "https://api-seller.ozon.ru"
BEIJING = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parent.parent
STATUS_ZH = {
    "delivered": "已签收", "delivering": "运输中", "cancelled": "已取消",
    "awaiting_deliver": "等待发运", "awaiting_packaging": "待备货",
    "awaiting_registration": "等待登记",
}
RETURN_STATUS_ZH = {
    "На складе": "在仓库中",
    "Едет на склад": "正在运往仓库",
    "Списали товар": "我们已核销商品",
    "Ожидает отправки": "等待发货",
}
RFBS_RETURN_STATUS_ZH = {
    "Rejected": "由您拒绝",
    "PartialCompensationReturnedByOzon": "已向买家赔偿",
    "Cancelled": "由买家取消",
    "ReleasedByProvider": "已由合作伙伴发送",
    "RejectedByOzon": "由Ozon拒绝了",
    "CancelledDisputeNotOpen": "已拒绝。未提出争议",
    "CancelledDisputeNotOpenOnPostModeration": "已拒绝。未提出争议",
    "UtilizedByOzon": "已由Ozon销毁",
    "ArrivedAtWarehouse": "在仓库中",
    "PartialCompensationReturned": "您已退还部分金额",
    "MoneyReturned": "已退款",
    "AwaitingProcessing": "等待决定",
    "OnSellerApproval": "待卖家审核",
    "OnSellerClarification": "确认中",
    "OnWayToOzon": "在途中",
    "UtilizedByProvider": "已由合作伙伴销毁",
    "ApprovedOnPreModerationByOzon": "已由Ozon批准",
    "CheckingStatus": "正在确认状态",
    "PassedToPartner": "已转交给合作伙伴",
    "Approved": "由您认可",
    "OnWay": "在途中",
    "UtilizingByOzon": "正在由Ozon进行销毁",
    "CrmRejected": "由Ozon拒绝了",
    "OnSellerClarificationAfterPartialCompensation": "确认中",
    "Solved": "已说明",
    "WriteOff": "我们已核销商品",
    "ReceivedBySeller": "已收货",
}
CANCEL_REASON_ZH = {
    "Покупатель отказался при вручении: товар не подошел": "买家在交货时拒收：商品不合适",
    "Отправление не прошло таможенное оформление": "货件未通过清关",
    "Не удалось доставить заказ": "未能配送订单",
    "Покупатель не забрал заказ": "买家没取货",
    "Покупатель отменил заказ: нашел дешевле": "买家取消了订单：找到了更便宜的商品",
    "Покупатель отменил заказ": "买家取消了订单",
    "Заказ утерян при доставке": "订单在配送过程中丢失",
    "Покупатель не предоставил паспортные данные": "买家没提供护照信息",
    "Товар закончился на складе": "仓库缺货",
    "Покупатель отменил заказ: не устроил срок доставки": "买方取消订单：对交货时间不满意",
    "Покупатель отказался при вручении: в заказе не тот товар": "买家在交货时拒收：订单中的商品有误",
    "Покупатель отказался при вручении: недоволен качеством товара": "买家拒绝取货：对商品质量不满意",
    "Вы отменили заказ": "您已取消订单",
    "Покупатель отменил заказ: перенос сроков доставки": "买家取消了订单： 推迟配送期间",
    "Покупатель отменил заказ по вашей просьбе": "买家应您的要求取消了订单",
    "Покупатель отказался при вручении: неполная комплектация": "买家在交货时拒收：商品不齐全",
    "Товар не работает / брак": "商品无法使用 / 存在缺陷",
    "Покупатель получил не те товары": "买家收到错误的商品",
    "Покупатель передумал": "买家改变主意",
    "Упаковка и товар повреждены": "包装和商品均损坏",
    "Товар в неполной комплектации": "商品不齐全",
    "Товар поврежден, но упаковка цела": "商品损坏，但包装完好无损",
    "Товар или заводскую упаковку повредили": "商品或原厂包装已损坏",
    "Товар использовали до меня": "我收到前商品已被使用",
    "Есть внешние дефекты или следы использования": "有外部缺陷或使用痕迹",
    "Привезли не тот товар": "配送了错误的商品",
    "Нет части товара или комплекта": "商品或套装部件缺失",
    "Нет части товара/комплекта": "商品/套件缺失部分",
    "Не работает, плохо работает": "无法使用，使用效果差",
    "Подделка": "假货",
    "Товар сломался при использовании": "商品在使用过程中坏了",
    "Не подошёл товар": "商品不合适",
    "Товар не подошёл": "商品不合适",
    "Не работает или работает плохо": "不可用或无法正常工作",
    "Покупатель попросил вас отменить заказ": "买家已要求您取消订单",
    "Вы не отгрузили заказ вовремя": "您没有按时发送商品",
    "Не соответствует требованиям перевозчика": "不符合承运商的要求",
    "Не удалось зарегистрировать отправление в службе доставки": "未能通过送货服务登记货件",
    "Вы нарушили правила перевозки опасных товаров": "您违反了危险品运输规则",
    "Трек-номер не отслеживается": "追踪号码无法追踪",
    "Покупатель не оплатил пошлину": "买家未缴纳关税",
    "Покупатель не оплатил заказ вовремя": "买方未按时支付订单",
    "Не удалось обработать заказ": "未能处理订单",
    "У товаров неправильная этикетка": "商品标签错误",
    "Проверка товара на соответствие описанию в карточке": "检查商品是否与商品卡片中的描述相符",
    "Отменили заказ по вашей просьбе": "已根据您的要求取消订单",
    "В заказе есть запрещённые к перевозке товары": "订单中有禁止运输的商品",
}
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


def _wait_for_request_slot():
    global _last_request
    with _request_lock:
        now = time.monotonic()
        scheduled = max(now, _last_request + 1.05)
        _last_request = scheduled
    if scheduled > now:
        time.sleep(scheduled - now)


def _post(shop_id, path, payload):
    # ponytail: one global start-rate limiter; network waits must not block unrelated module requests.
    for attempt in range(7):
        _wait_for_request_slot()
        request = urllib.request.Request(
            API + path, data=json.dumps(payload).encode(), headers=_headers(shop_id), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if (error.code == 429 or 500 <= error.code < 600) and attempt < 6:
                time.sleep(min(30, 2 ** (attempt + 1)))
                continue
            try:
                message = json.loads(error.read()).get("message", "Ozon API请求失败")
            except Exception:
                message = "Ozon API请求失败"
            raise RuntimeError(f"{path}: HTTP {error.code}: {message}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt < 6:
                time.sleep(min(30, 2 ** (attempt + 1)))
                continue
            raise RuntimeError(f"{path}: 网络请求失败: {error}") from error


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
        container = body.get("result") if isinstance(body.get("result"), dict) else body
        batch = container.get(list_key) or []
        records.extend(batch)
        total = container.get("total")
        if not batch or ("has_next" in container and not container.get("has_next")):
            return records
        if total is not None and len(records) >= int(total):
            return records
        cursor = str(container.get(response_cursor) or body.get(response_cursor) or batch[-1].get("id") or "")
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
    with connect() as db:
        delivered = {row[0] for row in db.execute(
            "SELECT posting_number FROM orders WHERE shop_id=? AND NULLIF(delivered_at,'') IS NOT NULL", (shop_id,))}
    for posting in fbo:
        if (posting.get("status") == "delivered" and posting["posting_number"] not in delivered
                and not posting.get("fact_delivery_date")):
            detail = _post(shop_id, "/v2/posting/fbo/get", {
                "posting_number": posting["posting_number"],
                "with": {"analytics_data": False, "financial_data": False}}).get("result") or {}
            posting["fact_delivery_date"] = detail.get("fact_delivery_date")
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
            shipped_at = posting.get("delivering_date")
            delivered_at = posting.get("fact_delivery_date")
            db.execute("""
              INSERT INTO orders(shop_id,posting_number,parent_order_no,channel,created_at,shipped_at,delivered_at,tracking_number,status_raw,
                cancel_reason_raw,shipped,cancelled_after_ship,data_anomaly,amount_original,
                amount_currency,source,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(shop_id,posting_number) DO UPDATE SET
                parent_order_no=COALESCE(NULLIF(excluded.parent_order_no,''),orders.parent_order_no),
                channel=excluded.channel,created_at=COALESCE(NULLIF(excluded.created_at,''),orders.created_at),
                shipped_at=COALESCE(NULLIF(excluded.shipped_at,''),orders.shipped_at),
                delivered_at=CASE WHEN NULLIF(excluded.delivered_at,'') IS NOT NULL THEN excluded.delivered_at
                  WHEN excluded.channel IN ('FBP','realFBS') AND orders.delivered_at=orders.shipped_at THEN NULL
                  ELSE orders.delivered_at END,
                tracking_number=COALESCE(NULLIF(excluded.tracking_number,''),orders.tracking_number),
                status_raw=COALESCE(NULLIF(excluded.status_raw,''),orders.status_raw),
                cancel_reason_raw=COALESCE(NULLIF(excluded.cancel_reason_raw,''),orders.cancel_reason_raw),
                shipped=CASE WHEN excluded.channel='WHD' AND excluded.status_raw='已取消' AND excluded.cancelled_after_ship IS NULL
                  THEN orders.shipped ELSE excluded.shipped END,
                cancelled_after_ship=COALESCE(excluded.cancelled_after_ship,orders.cancelled_after_ship),
                amount_original=COALESCE(excluded.amount_original,orders.amount_original),
                amount_currency=COALESCE(NULLIF(excluded.amount_currency,''),orders.amount_currency),
                source='api',updated_at=excluded.updated_at
            """, (shop_id, number, posting.get("order_number"), channel, created, shipped_at, delivered_at,
                  posting.get("tracking_number"),
                  STATUS_ZH.get(status_original, status_original), cancellation.get("cancel_reason"),
                  shipped, cancelled_after, 0, amount, amount_currency, "api", fetched))
            db.execute("UPDATE order_items SET channel=? WHERE shop_id=? AND posting_number=?",
                       (channel, shop_id, number))
            for product, price in zip(products, prices):
                sku = str(product.get("sku") or "")
                if not sku:
                    continue
                db.execute("""
                  INSERT INTO order_items(shop_id,channel,posting_number,sku,offer_id,product_name_raw,
                    quantity,unit_price,price_currency,source)
                  VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(shop_id,posting_number,sku) DO UPDATE SET
                    channel=excluded.channel,offer_id=COALESCE(NULLIF(excluded.offer_id,''),order_items.offer_id),
                    product_name_raw=COALESCE(NULLIF(excluded.product_name_raw,''),order_items.product_name_raw),
                    quantity=excluded.quantity,unit_price=COALESCE(excluded.unit_price,order_items.unit_price),
                    price_currency=COALESCE(NULLIF(excluded.price_currency,''),order_items.price_currency),source='api'
                """, (shop_id, channel, number, sku, product.get("offer_id"), product.get("name") or "",
                      int(product.get("quantity") or 1), price[0], price[1], "api"))
    return {"records": len(fbs) + len(fbo), "FBP": sum(p.get("integration_type_flow") == "FBP" for p in fbs),
            "realFBS": sum(p.get("integration_type_flow") == "aggregator" for p in fbs), "WHD": len(fbo)}


def _rfbs_return_pages(shop_id, start, end):
    base = {"filter": {"created_at": {"from": _utc(start), "to": _utc(end)}}, "limit": 100}
    records, last_id = [], 0
    for _ in range(200):
        body = _post(shop_id, "/v2/returns/rfbs/list", {**base, "last_id": last_id})
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
            body = _post(shop_id, "/v2/returns/rfbs/get", {"return_id": return_id})
            detail = body.get("result") if isinstance(body.get("result"), dict) else body
            detail = detail.get("return") if isinstance(detail.get("return"), dict) else detail
            detail = detail.get("returns") if isinstance(detail.get("returns"), dict) else detail
            reason = detail.get("return_reason") or {}
            reason_name = str(reason.get("name") or "").strip() if isinstance(reason, dict) else ""
            stamp = _stamp()
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
    records = _cursor_pages(shop_id, "/v1/returns/list", payload, "returns", "last_id", "")
    rfbs_records = _rfbs_return_pages(shop_id, start, end)
    fetched = _stamp()
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
    records = _cursor_pages(shop_id, "/v4/product/info/stocks",
                            {"filter": {"visibility": "ALL"}, "limit": 1000}, "items")
    observed = _stamp()
    with transaction() as db:
        for record in records:
            record_key = str(record.get("product_id") or record.get("offer_id") or _key(record))
            db.execute("""INSERT INTO stock_snapshots VALUES(?,?,?,?)
              ON CONFLICT(shop_id,record_key) DO UPDATE SET
                observed_at=excluded.observed_at,payload=excluded.payload""",
                       (shop_id, record_key, observed, _json(record)))
            for value in record.get("stocks") or []:
                db.execute("""INSERT OR IGNORE INTO stock_history(
                  shop_id,source,warehouse_id,sku,present,reserved,occurred_at,event_key,payload_json)
                  VALUES(?,?,?,?,?,?,?,?,?)""",
                  (shop_id, "api", ",".join(map(str, value.get("warehouse_ids") or [])),
                   str(value.get("sku") or record.get("product_id") or ""),
                   int(value.get("present") or 0), int(value.get("reserved") or 0), observed,
                   record_key + ":" + str(value.get("type") or ""), _json(record)))
    return {"records": len(records), "snapshot_at": observed}


def sync_module(module, shop_id, start=None, end=None, include_existing_missing=True):
    start, end = (start, end) if start and end else default_range()
    functions = {"orders": sync_orders,
                 "returns": lambda s, a, b: sync_returns(s, a, b, include_existing_missing),
                 "stock": lambda s, _a, _b: _sync_stock_snapshot(s)}
    if module not in functions:
        raise ValueError("未知同步模块")
    return functions[module](shop_id, start, end)


def probe_shop(shop_id):
    roles_response = _post(shop_id, "/v1/roles", {})
    info_response = _post(shop_id, "/v1/seller/info", {})
    roles = roles_response.get("roles") or roles_response.get("result") or []
    role_names = [str(role.get("name") or role.get("role") or role) if isinstance(role, dict) else str(role)
                  for role in roles]
    methods = {method for role in roles if isinstance(role, dict) for method in role.get("methods", [])}
    required = {
        "orders": {"/v4/posting/fbs/list", "/v3/posting/fbo/list"},
        "returns": {"/v1/returns/list", "/v2/returns/rfbs/list", "/v2/returns/rfbs/get"},
        "stock": {"/v4/product/info/stocks"},
    }
    permissions = {module: ("可用" if paths <= methods else "缺少：" + "、".join(sorted(paths - methods)))
                   for module, paths in required.items()}
    info = info_response.get("result") or info_response
    allowed = {"company", "name", "seller_id", "client_id", "inn", "ogrn"}
    return {"valid": True, "identity": {key: value for key, value in info.items() if key in allowed},
            "roles": role_names, "permissions": permissions}
