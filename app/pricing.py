import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .db import connect
from .exchange import current_exchange_rate_entries
from .inventory import _stock_quantity
from .ozon.client import BEIJING
from .products import load_product_rules, resolve_product
from .routers.common import ACTIVE, _utc_moment, _utc_text


CHANNELS = ("FBP", "realFBS", "WHD")
SORT_FIELDS = {
    "current_price", "sold_price_30", "price_vs_30d", "projected_margin",
    "break_even_price", "target_margin_price", "sales_30", "effective_stock", "price_index",
}
HEALTH_FLAGS = {"", "incomplete", "loss", "low_margin", "price_red", "price_yellow", "no_price_index", "healthy"}
HEALTH_PRIORITY = (
    "incomplete", "loss", "low_margin", "price_red", "price_yellow", "no_price_index", "healthy",
)
COMMISSION_FIELDS = {
    "FBP": "sales_percent_fbp",
    "realFBS": "sales_percent_rfbs",
    "WHD": "sales_percent_fbo",
}
STOCK_TYPES = {"fbp": "FBP", "fbs": "realFBS", "rfbs": "realFBS", "fbo": "WHD", "whd": "WHD"}


def _decimal(value):
    if value is None or value == "" or isinstance(value, bool) or isinstance(value, (dict, list)):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None
    return number if number.is_finite() else None


def _decimal_text(value):
    return format(value, "f") if value is not None and value.is_finite() else None


def _number(value):
    if value is None or not value.is_finite():
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _text(value):
    if value is None:
        return ""
    value = str(value).strip()
    return value


def _shop_ids(shop_id):
    if type(shop_id) is not int or shop_id not in (0, 1, 2):
        raise ValueError("未知店铺")
    return (1, 2) if shop_id == 0 else (shop_id,)


def _channel(value):
    if not isinstance(value, str):
        raise ValueError("未知履约模式")
    aliases = {"fbp": "FBP", "realfbs": "realFBS", "rfbs": "realFBS", "whd": "WHD"}
    result = aliases.get(value.strip().lower())
    if result not in CHANNELS:
        raise ValueError("未知履约模式")
    return result


def _health_filter(value):
    if not isinstance(value, str) or value not in HEALTH_FLAGS:
        raise ValueError("未知价格健康状态")
    return value


def _target_margin(value):
    if type(value) is bool:
        raise ValueError("目标基础毛利率必须为有限数字")
    result = _decimal(value)
    if result is None or result < 0 or result > 80:
        raise ValueError("目标基础毛利率必须在0到80之间")
    return result


def _sales_window(now=None):
    if now is None:
        moment = datetime.now(BEIJING)
    elif isinstance(now, datetime):
        moment = now if now.tzinfo else now.replace(tzinfo=BEIJING)
        moment = moment.astimezone(BEIJING)
    else:
        raise ValueError("分析时间无效")
    today = moment.date()
    start_day, end_day = today - timedelta(days=30), today - timedelta(days=1)
    start = datetime.combine(start_day, datetime.min.time(), BEIJING).astimezone(timezone.utc)
    end = datetime.combine(today, datetime.min.time(), BEIJING).astimezone(timezone.utc)
    return moment, start_day, end_day, _utc_text(start), _utc_text(end)


def _marks(values):
    return ",".join("?" for _ in values)


def _safe_stock_quantity(value):
    try:
        return _stock_quantity(value)
    except (OverflowError, TypeError, ValueError):
        return 0


def _latest_price_batch(db, shop_id):
    row = db.execute("""SELECT data_through FROM sync_runs
      WHERE shop_id=? AND module='prices' AND status='success'
        AND NULLIF(trim(data_through),'') IS NOT NULL
      ORDER BY data_through DESC,id DESC LIMIT 1""", (shop_id,)).fetchone()
    if row:
        return row[0], "sync_run"
    row = db.execute("SELECT MAX(observed_at) FROM product_price_snapshots WHERE shop_id=?", (shop_id,)).fetchone()
    return (row[0], "snapshot") if row and row[0] else (None, "none")


def _json_dict(value):
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _freshness_key(value):
    moment = _utc_moment(value)
    return (moment or datetime.min.replace(tzinfo=timezone.utc), _text(value))


def _stock_index(rows):
    index = {}
    for row in rows:
        payload = _json_dict(row["payload"])
        if not payload:
            continue
        product_id = _text(payload.get("product_id")) or None
        offer_id = _text(payload.get("offer_id")) or None
        channels = {}
        sku_values = set()
        for raw in payload.get("stocks") or []:
            if not isinstance(raw, dict):
                continue
            channel = STOCK_TYPES.get(_text(raw.get("type")).lower())
            if not channel:
                continue
            sku = _text(raw.get("sku"))
            if sku:
                sku_values.add(sku)
            value = channels.setdefault(channel, {"present": 0, "reserved": 0})
            value["present"] += _safe_stock_quantity(raw.get("present"))
            value["reserved"] += _safe_stock_quantity(raw.get("reserved"))
        candidate = {
            "record_key": _text(row["record_key"]), "observed_at": row["observed_at"],
            "product_id": product_id, "offer_id": offer_id,
            "channels": channels, "sku_values": sku_values,
        }
        keys = [("product_id", product_id), ("offer_id", offer_id)]
        keys.extend(("sku", sku) for sku in sku_values)
        for key_type, key_value in keys:
            if key_value:
                index.setdefault((row["shop_id"], key_type, key_value), []).append(candidate)
    return index


def _stock_view(index, shop_id, product_id, offer_id, sku, channel):
    for key_type, key_value in (("offer_id", offer_id), ("product_id", product_id), ("sku", sku)):
        if not key_value:
            continue
        candidates = index.get((shop_id, key_type, key_value))
        if not candidates:
            continue
        unique = {candidate["record_key"]: candidate for candidate in candidates}
        candidate = max(unique.values(), key=lambda value: _freshness_key(value["observed_at"]))
        value = candidate["channels"].get(channel, {"present": 0, "reserved": 0})
        present, reserved = value["present"], value["reserved"]
        return {
            "present": present, "reserved": reserved,
            "effective_stock": max(present - reserved, 0), "observed_at": candidate["observed_at"],
        }
    return {"present": None, "reserved": None, "effective_stock": None, "observed_at": None}


def _add_mapping(mapping, key, sku):
    if key[-1] and sku:
        mapping.setdefault(key, set()).add(sku)


def _sku_maps(order_rows, erp_rows, stock_index, rules):
    offers, products = {}, {}
    for row in order_rows:
        shop_id, sku, offer_id = row["shop_id"], _text(row["sku"]), _text(row["offer_id"])
        if sku and offer_id:
            offers.setdefault((shop_id, offer_id), set()).add(sku)
    for row in erp_rows:
        if row["order_quantity"] != row["erp_quantity"]:
            continue
        order_offer, erp_offer = _text(row["order_offer_id"]), _text(row["offer_id"])
        if order_offer and erp_offer and order_offer != erp_offer:
            continue
        sku, offer_id = _text(row["ozon_sku"]), erp_offer or order_offer
        if sku and offer_id:
            offers.setdefault((row["shop_id"], offer_id), set()).add(sku)
    for (shop_id, key_type, key_value), candidates in stock_index.items():
        if key_type not in ("product_id", "offer_id"):
            continue
        for candidate in candidates:
            for sku in candidate["sku_values"]:
                _add_mapping(products if key_type == "product_id" else offers,
                             (shop_id, key_value), sku)
    explicit = {}
    for (key_type, key_value), group_id in rules.get("members", {}).items():
        if key_type != "offer_id":
            continue
        group = rules.get("groups", {}).get(group_id) or {}
        primary_sku = _text(group.get("primary_sku"))
        if primary_sku:
            explicit[key_value] = primary_sku
    return offers, products, explicit


def _resolve_sku(shop_id, product_id, offer_id, maps):
    offers, products, explicit = maps
    if offer_id and offer_id in explicit:
        return explicit[offer_id], "resolved"
    candidates = set(offers.get((shop_id, offer_id), ())) if offer_id else set()
    if not candidates and product_id:
        candidates = set(products.get((shop_id, product_id), ()))
    if len(candidates) == 1:
        return next(iter(candidates)), "resolved"
    if len(candidates) > 1:
        return None, "ambiguous"
    return None, "unavailable"


def _price_view(row):
    values = {field: _decimal(row[field]) for field in ("price", "old_price", "min_price", "marketing_seller_price")}
    effective = values["marketing_seller_price"] if values["marketing_seller_price"] is not None and values["marketing_seller_price"] > 0 else values["price"]
    return {
        "observed_at": row["observed_at"], "currency": _text(row["currency"]) or None,
        "base_price": _decimal_text(values["price"]),
        "marketing_seller_price": _decimal_text(values["marketing_seller_price"]),
        "effective_price": _decimal_text(effective), "old_price": _decimal_text(values["old_price"]),
        "min_price": _decimal_text(values["min_price"]),
        "auto_action_enabled": None if row["auto_action_enabled"] is None else bool(row["auto_action_enabled"]),
        "_effective": effective,
    }


def _sales_view(rows):
    rows = rows or []
    if not rows:
        return {"units": 0, "revenue": None, "currency": None, "weighted_avg_price": None,
                "sold_price_status": "no_sales"}
    units = sum(int(row["quantity"] or 0) for row in rows)
    if any(not _text(row["price_currency"]) for row in rows):
        return {"units": units, "revenue": None, "currency": None, "weighted_avg_price": None,
                "sold_price_status": "missing_currency"}
    currencies = {_text(row["price_currency"]).upper() for row in rows}
    if len(currencies) > 1:
        return {"units": units, "revenue": None, "currency": None, "weighted_avg_price": None,
                "sold_price_status": "currency_mismatch"}
    currency = next(iter(currencies), None)
    amounts = []
    for row in rows:
        unit_price = _decimal(row["unit_price"])
        if unit_price is None or not currency or unit_price < 0:
            return {"units": units, "revenue": None, "currency": currency, "weighted_avg_price": None,
                    "sold_price_status": "missing_price"}
        amounts.append((unit_price, int(row["quantity"] or 0)))
    revenue = sum((price * quantity for price, quantity in amounts), Decimal("0"))
    weighted = revenue / units if units else None
    return {"units": units, "revenue": _decimal_text(revenue), "currency": currency,
            "weighted_avg_price": _decimal_text(weighted), "sold_price_status": "available" if weighted is not None else "missing_price"}


def _convert(amount, source, target, rates):
    if amount is None or not source or not target:
        return None
    source, target = source.upper(), target.upper()
    if source == target:
        return amount
    if source == "RUB":
        rate = rates.get(target)
        return amount / rate if rate else None
    if target == "RUB":
        rate = rates.get(source)
        return amount * rate if rate else None
    source_rate, target_rate = rates.get(source), rates.get(target)
    return amount * source_rate / target_rate if source_rate and target_rate else None


def _commission(commissions_json, channel):
    commissions = _json_dict(commissions_json)
    field = COMMISSION_FIELDS[channel]
    value = _decimal(commissions.get(field)) if commissions else None
    return (value if value is not None and value >= 0 else None), field


def _competitiveness(row):
    raw = _json_dict(row["price_indexes_json"]) or {}
    names = {
        "ozon": ("ozon_index_data", "ozon_min_price", "ozon_price_index"),
        "external": ("external_index_data", "external_min_price", "external_price_index"),
        "self_marketplace": ("self_marketplaces_index_data", "self_marketplace_min_price", "self_marketplace_price_index"),
    }
    result = {"color_index": _text(row["price_index_color"]) or None}
    for name, (raw_key, min_key, index_key) in names.items():
        details = raw.get(raw_key) if isinstance(raw.get(raw_key), dict) else {}
        min_value = _decimal(row[min_key])
        index_value = _decimal(row[index_key])
        currency = details.get("min_price_currency") or details.get("min_price_currency_code")
        if currency is None:
            currency = details.get("currency_code") or details.get("currency")
        result[name] = {
            "min_price": _decimal_text(min_value),
            "min_price_currency": _text(currency) or None,
            "index": _decimal_text(index_value),
        }
    return result


def _has_price_index(competitiveness):
    color = (competitiveness.get("color_index") or "").upper()
    if color == "WITHOUT_INDEX":
        return False
    if color:
        return True
    return any(value.get("index") is not None for key, value in competitiveness.items() if key != "color_index")


def _economics(price, settlement_currency, cost, sku_status, commission, commission_field,
               acquiring_raw, rates, sold_price_status, target_margin):
    reasons = []
    if sku_status == "ambiguous":
        reasons.append("ambiguous_sku")
    elif sku_status == "unavailable":
        reasons.append("missing_sku_mapping")
    if cost["status"] != "available":
        reasons.append("missing_erp_cost")
    if price["_effective"] is None or price["_effective"] <= 0:
        reasons.append("missing_current_price")
    if commission is None:
        reasons.append("missing_commission")
    if acquiring_raw is None or acquiring_raw < 0:
        reasons.append("missing_acquiring")
    current = _convert(price["_effective"], price["currency"], settlement_currency, rates)
    unit_cost = _convert(_decimal(cost["unit_cost_cny"]), "CNY", settlement_currency, rates)
    acquiring = _convert(acquiring_raw, price["currency"], settlement_currency, rates)
    if (price["_effective"] is not None and current is None) or (cost["status"] == "available" and unit_cost is None) or (acquiring_raw is not None and acquiring is None):
        reasons.append("missing_exchange_rate")
    if sold_price_status in {"currency_mismatch", "missing_currency"}:
        reasons.append(sold_price_status)
    deduped = list(dict.fromkeys(reasons))
    projected = margin = acquiring_rate = break_even = target_price = None
    if current is not None and current > 0 and unit_cost is not None and commission is not None and acquiring is not None:
        acquiring_rate_decimal = acquiring / current
        acquiring_rate = _number(acquiring_rate_decimal)
        projected_decimal = current - current * commission / Decimal("100") - acquiring - unit_cost
        margin_decimal = projected_decimal / current * Decimal("100")
        projected, margin = _decimal_text(projected_decimal), _number(margin_decimal)
        denominator = Decimal("1") - commission / Decimal("100") - acquiring_rate_decimal
        if denominator > 0:
            break_even = _decimal_text(unit_cost / denominator)
        else:
            deduped.append("break_even_denominator_non_positive")
        target_denominator = denominator - target_margin / Decimal("100")
        if target_denominator > 0:
            target_price = _decimal_text(unit_cost / target_denominator)
        else:
            deduped.append("target_margin_denominator_non_positive")
    return {
        "status": "complete" if not deduped else "incomplete", "currency": settlement_currency,
        "current_effective_price": _decimal_text(current), "unit_cost": _decimal_text(unit_cost),
        "sales_commission_pct": _number(commission), "sales_commission_field": commission_field,
        "acquiring_amount": _decimal_text(acquiring), "acquiring_rate": acquiring_rate,
        "projected_base_profit": projected, "projected_base_margin_pct": margin,
        "break_even_price": break_even, "target_margin_price": target_price,
        "incomplete_reasons": list(dict.fromkeys(deduped)),
        "acquiring_rate_assumption": "保本价和目标毛利价测算假设收单手续费比例保持当前水平",
    }


def _health_flags(economics, competitiveness, target_margin):
    flags = []
    if economics["status"] == "incomplete":
        flags.append("incomplete")
    profit = _decimal(economics["projected_base_profit"])
    margin = economics["projected_base_margin_pct"]
    if profit is not None and profit < 0:
        flags.append("loss")
    elif margin is not None and margin < _number(target_margin):
        flags.append("low_margin")
    color = (competitiveness.get("color_index") or "").upper()
    if color == "RED":
        flags.append("price_red")
    elif color == "YELLOW":
        flags.append("price_yellow")
    if not _has_price_index(competitiveness):
        flags.append("no_price_index")
    if (economics["status"] == "complete" and margin is not None and margin >= _number(target_margin)
            and color not in {"RED", "YELLOW"}):
        flags.append("healthy")
    ordered = [flag for flag in HEALTH_PRIORITY if flag in flags]
    return ordered, ordered[0]


def _sort_value(row, field, rates):
    if field == "current_price":
        return _convert(_decimal(row["price"]["effective_price"]), row["price"]["currency"], "CNY", rates)
    if field == "sold_price_30":
        sales = row["sales_30"]
        return _convert(_decimal(sales["weighted_avg_price"]), sales["currency"], "CNY", rates)
    if field == "break_even_price":
        economics = row["economics"]
        return _convert(_decimal(economics["break_even_price"]), economics["currency"], "CNY", rates)
    if field == "target_margin_price":
        economics = row["economics"]
        return _convert(_decimal(economics["target_margin_price"]), economics["currency"], "CNY", rates)
    if field == "sales_30":
        return Decimal(row["sales_30"]["units"])
    if field == "effective_stock":
        value = row["stock"]["effective_stock"]
        return Decimal(value) if value is not None else None
    if field == "price_index":
        return _decimal(row["competitiveness"]["ozon"]["index"])
    if field == "price_vs_30d":
        return Decimal(str(row["sales_30"]["price_vs_30d_pct"])) if row["sales_30"]["price_vs_30d_pct"] is not None else None
    if field == "projected_margin":
        value = row["economics"]["projected_base_margin_pct"]
        return Decimal(str(value)) if value is not None else None
    return None


def _freshness(db, shop_ids, price_batches, price_rows, exchange_entries):
    shops = {}
    rows_by_shop = {shop_id: [] for shop_id in shop_ids}
    for row in price_rows:
        rows_by_shop[row["shop_id"]].append(row)
    for shop_id in shop_ids:
        through, source = price_batches[shop_id]
        shops[str(shop_id)] = {"status": "available" if rows_by_shop[shop_id] else "missing",
                               "data_through": through, "source": source}
    price_values = [value[0] for value in price_batches.values() if value[0]]
    marks = _marks(shop_ids)
    order_through = db.execute(f"""SELECT MAX(data_through) FROM sync_runs
      WHERE module='orders' AND status='success' AND shop_id IN ({marks})""", shop_ids).fetchone()[0]
    if not order_through:
        order_through = db.execute(f"SELECT MAX(created_at) FROM orders WHERE shop_id IN ({marks})", shop_ids).fetchone()[0]
    stock_through = db.execute(f"SELECT MAX(observed_at) FROM stock_snapshots WHERE shop_id IN ({marks})", shop_ids).fetchone()[0]
    erp_through = db.execute(f"SELECT MAX(updated_at) FROM erp_order_item_costs WHERE shop_id IN ({marks})", shop_ids).fetchone()[0]
    exchange_status = "available" if exchange_entries else "missing"
    has_price = any(rows_by_shop.values())
    return {
        "prices": {"status": "available" if has_price else "missing",
                   "data_through": max(price_values, key=_freshness_key) if price_values else None,
                   "shops": shops},
        "orders": {"status": "available" if order_through else "missing", "data_through": order_through},
        "stock": {"status": "available" if stock_through else "missing", "observed_at": stock_through},
        "erp_cost": {"status": "available" if erp_through else "missing", "updated_at": erp_through},
        "exchange_rate": {"status": exchange_status,
                          "currencies": sorted(exchange_entries),
                          "sales_exchange_rates": {currency: entry.get("sales_exchange_rate")
                                                    for currency, entry in exchange_entries.items()}},
    }


def get_pricing(shop_id=0, q="", channel="FBP", health="", target_margin_pct=20,
                sort_by="", sort_order="desc", page=1, size=50, now=None, _snapshot_key=None):
    shop_ids = _shop_ids(shop_id)
    channel = _channel(channel)
    health = _health_filter(health)
    target_margin = _target_margin(target_margin_pct)
    if sort_by not in ("", *SORT_FIELDS):
        raise ValueError("未知价格分析排序字段")
    if sort_order not in ("asc", "desc"):
        raise ValueError("未知排序方向")
    if type(page) is not int or page < 1 or type(size) is not int or not 1 <= size <= 100:
        raise ValueError("分页参数无效")
    moment, start_day, end_day, utc_start, utc_end = _sales_window(now)
    search = _text(q).lower()
    marks = _marks(shop_ids)
    with connect() as db:
        shop_rows = {row["id"]: dict(row) for row in db.execute(
            f"SELECT id,name,settlement_currency FROM shops WHERE id IN ({marks}) ORDER BY id", shop_ids)}
        rules = load_product_rules(db)
        price_batches = {shop: _latest_price_batch(db, shop) for shop in shop_ids}
        price_rows = []
        for current_shop in shop_ids:
            through = price_batches[current_shop][0]
            if not through:
                continue
            price_rows.extend(db.execute(
                "SELECT * FROM product_price_snapshots WHERE shop_id=? AND observed_at=? ORDER BY snapshot_key",
                (current_shop, through)).fetchall())
        order_mapping_rows = db.execute(f"""SELECT shop_id,sku,offer_id FROM order_items
          WHERE shop_id IN ({marks}) AND NULLIF(trim(offer_id),'') IS NOT NULL""", shop_ids).fetchall()
        erp_rows = db.execute(f"""SELECT e.shop_id,e.erp_order_number,e.ozon_sku,e.offer_id,e.quantity AS erp_quantity,
            e.unit_cost,e.source_batch_id,e.source_row_no,e.imported_at,e.updated_at,
            i.offer_id AS order_offer_id,i.quantity AS order_quantity
          FROM erp_order_item_costs e
          JOIN orders o ON o.shop_id=e.shop_id AND o.posting_number=e.erp_order_number
          JOIN order_items i ON i.shop_id=e.shop_id AND i.posting_number=e.erp_order_number AND i.sku=e.ozon_sku
          WHERE e.shop_id IN ({marks})""", shop_ids).fetchall()
        stock_rows = db.execute(f"SELECT shop_id,record_key,observed_at,payload FROM stock_snapshots WHERE shop_id IN ({marks})", shop_ids).fetchall()
        stock_index = _stock_index(stock_rows)
        sku_maps = _sku_maps(order_mapping_rows, erp_rows, stock_index, rules)
        sales_rows = db.execute(f"""SELECT i.shop_id,i.offer_id,i.sku,i.quantity,i.unit_price,i.price_currency,
            o.channel,o.created_at
          FROM order_items i JOIN orders o USING(shop_id,posting_number)
          WHERE {ACTIVE} AND o.created_at>=? AND o.created_at<? AND o.channel=?
            AND o.shop_id IN ({marks})
          ORDER BY o.created_at,i.sku""", [utc_start, utc_end, channel, *shop_ids]).fetchall()
        sales_by_offer, sales_by_sku = {}, {}
        for row in sales_rows:
            if _text(row["offer_id"]):
                sales_by_offer.setdefault((row["shop_id"], _text(row["offer_id"])), []).append(row)
            if _text(row["sku"]):
                sales_by_sku.setdefault((row["shop_id"], _text(row["sku"])), []).append(row)
        erp_by_sku = {}
        for row in erp_rows:
            if row["order_quantity"] != row["erp_quantity"]:
                continue
            order_offer, erp_offer = _text(row["order_offer_id"]), _text(row["offer_id"])
            if order_offer and erp_offer and order_offer != erp_offer:
                continue
            unit_cost = _decimal(row["unit_cost"])
            if unit_cost is None or unit_cost < 0:
                continue
            erp_by_sku.setdefault((row["shop_id"], _text(row["ozon_sku"])), []).append(row)
        for values in erp_by_sku.values():
            values.sort(key=lambda row: (_text(row["updated_at"]), _text(row["imported_at"]),
                                         int(row["source_batch_id"] or 0), int(row["source_row_no"] or 0)), reverse=True)
        exchange_entries = current_exchange_rate_entries(db, moment.astimezone(timezone.utc))
        rates = {currency: _decimal(entry.get("sales_exchange_rate"))
                 for currency, entry in exchange_entries.items()}
        rates = {currency: rate for currency, rate in rates.items() if rate is not None and rate > 0}
        freshness = _freshness(db, shop_ids, price_batches, price_rows, exchange_entries)

    rows = []
    for raw in price_rows:
        if _snapshot_key is not None and raw["snapshot_key"] != _snapshot_key:
            continue
        shop = shop_rows.get(raw["shop_id"], {})
        product_id = _text(raw["product_id"]) or None
        offer_id = _text(raw["offer_id"]) or None
        payload = _json_dict(raw["payload_json"]) or {}
        raw_name = _text(payload.get("name") or payload.get("product_name") or payload.get("title"))
        sku, sku_status = _resolve_sku(raw["shop_id"], product_id, offer_id, sku_maps)
        resolved = resolve_product(rules, sku or "", offer_id or "", raw_name)
        product = {
            "product_identity": resolved["identity"], "product_id": product_id, "offer_id": offer_id,
            "sku": sku, "display_name": resolved["display_name"], "group_id": resolved["group_id"],
            "primary_offer_id": resolved["primary_offer_id"],
        }
        price = _price_view(raw)
        sales_rows_for_item = sales_by_offer.get((raw["shop_id"], offer_id), []) if offer_id else sales_by_sku.get((raw["shop_id"], sku), [])
        sales = _sales_view(sales_rows_for_item)
        if sales["weighted_avg_price"] is not None:
            current = _convert(price["_effective"], price["currency"], shop["settlement_currency"], rates)
            sold = _convert(_decimal(sales["weighted_avg_price"]), sales["currency"], shop["settlement_currency"], rates)
            sales["price_vs_30d_pct"] = _number((current / sold - Decimal("1")) * Decimal("100")) if current is not None and sold and sold > 0 else None
        else:
            sales["price_vs_30d_pct"] = None
        cost = {"status": "unavailable", "sku": sku, "unit_cost_cny": None, "source_order": None, "updated_at": None}
        if sku:
            for candidate in erp_by_sku.get((raw["shop_id"], sku), []):
                candidate_offer = _text(candidate["offer_id"]) or _text(candidate["order_offer_id"])
                if offer_id and candidate_offer and candidate_offer != offer_id:
                    continue
                cost = {"status": "available", "sku": sku, "unit_cost_cny": _decimal_text(_decimal(candidate["unit_cost"])),
                        "source_order": candidate["erp_order_number"], "updated_at": candidate["updated_at"]}
                break
        commission, commission_field = _commission(raw["commissions_json"], channel)
        acquiring = _decimal(raw["acquiring"])
        economics = _economics(price, shop["settlement_currency"], cost, sku_status, commission,
                               commission_field, acquiring, rates, sales["sold_price_status"], target_margin)
        competitiveness = _competitiveness(raw)
        stock = _stock_view(stock_index, raw["shop_id"], product_id, offer_id, sku, channel)
        flags, primary = _health_flags(economics, competitiveness, target_margin)
        searchable = " ".join(_text(product.get(field)) for field in ("display_name", "sku", "offer_id", "product_id")).lower()
        if search and search not in searchable:
            continue
        rows.append({
            "row_key": f"{raw['shop_id']}:{raw['snapshot_key']}", "shop_id": raw["shop_id"],
            "snapshot_key": raw["snapshot_key"], "shop_name": shop["name"], "product": product,
            "price": {key: value for key, value in price.items() if not key.startswith("_")},
            "sales_30": sales, "cost_basis": cost, "economics": economics,
            "competitiveness": competitiveness, "stock": stock,
            "health_flags": flags, "primary_health": primary,
        })

    summary = {
        "products": len(rows), "economics_ready": sum(row["economics"]["status"] == "complete" for row in rows),
        "loss": sum("loss" in row["health_flags"] for row in rows),
        "low_margin": sum("low_margin" in row["health_flags"] for row in rows),
        "price_red": sum("price_red" in row["health_flags"] for row in rows),
        "price_yellow": sum("price_yellow" in row["health_flags"] for row in rows),
        "incomplete": sum("incomplete" in row["health_flags"] for row in rows),
        "no_price_index": sum("no_price_index" in row["health_flags"] for row in rows),
    }
    if health:
        rows = [row for row in rows if health in row["health_flags"]]
    if sort_by:
        valued = [(row, _sort_value(row, sort_by, rates)) for row in rows]
        present = [(row, value) for row, value in valued if value is not None]
        missing = [row for row, value in valued if value is None]
        present.sort(key=lambda item: item[1], reverse=sort_order == "desc")
        rows = [row for row, _value in present] + missing
    else:
        rows.sort(key=lambda row: (row["shop_id"], row["row_key"]))
    total = len(rows)
    start = (page - 1) * size
    return {
        "as_of": _utc_text(moment.astimezone(timezone.utc)),
        "sales_window": {"from": start_day.isoformat(), "to": end_day.isoformat(), "days": 30},
        "reference_channel": channel, "target_margin_pct": _number(target_margin),
        "freshness": freshness, "summary": summary,
        "items": rows[start:start + size], "total": total, "page": page, "size": size,
    }
