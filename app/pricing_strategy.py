from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from . import pricing
from .db import connect
from .ozon.client import BEIJING
from .routers.common import ACTIVE, _utc_moment, _utc_text


class PricingStrategyNotFound(ValueError):
    pass


HISTORY_DAYS = (7, 365)
MARKET_SOURCES = ("ozon", "external", "self_marketplace")
TRACKED_FIELDS = (
    ("effective_price_changed", "effective_price"),
    ("base_price_changed", "base_price"),
    ("marketing_seller_price_changed", "marketing_seller_price"),
    ("min_price_changed", "min_price"),
    ("auto_action_changed", "auto_action_enabled"),
    ("price_index_color_changed", "price_index_color"),
)


def _history_days(value):
    if type(value) is not int or not HISTORY_DAYS[0] <= value <= HISTORY_DAYS[1]:
        raise ValueError("价格历史天数必须在7到365之间")
    return value


def _snapshot_key(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("snapshot_key不能为空")
    return value.strip()


def _rates(entries):
    return {currency: rate for currency, entry in entries.items()
            if (rate := pricing._decimal(entry.get("sales_exchange_rate"))) is not None and rate > 0}


def _history_point(row):
    price = pricing._price_view(row)
    return {
        "observed_at": price["observed_at"],
        "currency": price["currency"],
        "base_price": price["base_price"],
        "marketing_seller_price": price["marketing_seller_price"],
        "effective_price": price["effective_price"],
        "min_price": price["min_price"],
        "price_index_color": pricing._text(row["price_index_color"]) or None,
        "auto_action_enabled": price["auto_action_enabled"],
    }


def _history_state(row):
    point = _history_point(row)
    competitiveness = pricing._competitiveness(row)
    return {
        **point,
        **{f"{source}_reference": {
            "price": competitiveness[source]["min_price"],
            "currency": competitiveness[source]["min_price_currency"],
        } for source in MARKET_SOURCES},
    }


def _historical_identity(row):
    return {
        "offer_id": pricing._text(row["offer_id"]) or None,
        "product_id": pricing._text(row["product_id"]) or None,
    }


def _comparison_value(value):
    if isinstance(value, dict):
        return tuple((key, _comparison_value(value.get(key))) for key in sorted(value))
    if isinstance(value, str):
        decimal = pricing._decimal(value)
        if decimal is not None:
            return ("decimal", decimal)
        return value.upper() if value else value
    return value


def _changed(before, after):
    return _comparison_value(before) != _comparison_value(after)


def _effective_change(before, after):
    before_currency = (before["currency"] or "").upper()
    after_currency = (after["currency"] or "").upper()
    if not before_currency or not after_currency:
        return None, "missing_currency"
    if before_currency != after_currency:
        return None, "currency_mismatch"
    old, new = pricing._decimal(before["effective_price"]), pricing._decimal(after["effective_price"])
    if old is None or new is None or old <= 0:
        return None, "missing_price"
    return pricing._number((new / old - Decimal("1")) * Decimal("100")), "available"


def _price_event(before_row, after_row, point_index):
    before, after = _history_state(before_row), _history_state(after_row)
    before_identity, after_identity = _historical_identity(before_row), _historical_identity(after_row)
    types, changes = [], {}
    for event_type, field in TRACKED_FIELDS:
        if _changed(before[field], after[field]):
            types.append(event_type)
            changes[field] = {"from": before[field], "to": after[field]}
    for source in MARKET_SOURCES:
        field = f"{source}_reference"
        if _changed(before[field], after[field]):
            types.append(f"{source}_reference_changed")
            changes[field] = {"from": before[field], "to": after[field]}
    if _changed(before["currency"], after["currency"]):
        types.append("currency_changed")
        changes["currency"] = {"from": before["currency"], "to": after["currency"]}
    if not types:
        return None
    change_pct, change_status = _effective_change(before, after)
    observed = _utc_moment(after["observed_at"])
    return {
        "observed_at": after["observed_at"],
        "previous_observed_at": before["observed_at"],
        "event_day": observed.astimezone(BEIJING).date().isoformat() if observed else None,
        "before_offer_id": before_identity["offer_id"], "after_offer_id": after_identity["offer_id"],
        "before_product_id": before_identity["product_id"], "after_product_id": after_identity["product_id"],
        "previous_currency": before["currency"], "currency": after["currency"],
        "types": types,
        "changes": changes,
        "effective_price_change_pct": change_pct,
        "price_change_status": change_status,
        "impact": None,
        "_point_index": point_index,
    }


def _market_source(source, competitiveness, settlement_currency, rates):
    value = pricing._decimal(competitiveness[source]["min_price"])
    currency = pricing._text(competitiveness[source]["min_price_currency"]).upper() or None
    result = {
        "price": pricing._decimal_text(value), "currency": currency,
        "converted_price": None, "converted_currency": settlement_currency,
        "status": "missing_price",
    }
    if value is None or value <= 0:
        return result
    if not currency:
        result["status"] = "missing_currency"
        return result
    converted = pricing._convert(value, currency, settlement_currency, rates)
    if converted is None:
        result["status"] = "missing_exchange_rate"
    elif converted > 0:
        result["converted_price"] = pricing._decimal_text(converted)
        result["status"] = "available"
    return result


def _market_reference(competitiveness, settlement_currency, rates):
    sources = {source: _market_source(source, competitiveness, settlement_currency, rates)
               for source in MARKET_SOURCES}
    available = [pricing._decimal(value["converted_price"])
                 for value in sources.values() if value["status"] == "available"]
    available = [value for value in available if value is not None and value > 0]
    warnings = []
    if available and len(available) < len(MARKET_SOURCES):
        warnings.append("partial_market_reference")
    if any(value["status"] == "missing_currency" for value in sources.values()):
        warnings.append("market_reference_currency_missing")
    if any(value["status"] == "missing_exchange_rate" for value in sources.values()):
        warnings.append("market_reference_exchange_rate_missing")
    return sources, (min(available) if available else None), list(dict.fromkeys(warnings))


def _window(rows):
    sales = pricing._sales_view(rows)
    return {
        "days": 7,
        "units": sales["units"],
        "avg_daily_units": sales["units"] / 7,
        "revenue": sales["revenue"],
        "currency": sales["currency"],
        "weighted_avg_price": sales["weighted_avg_price"],
        "sold_price_status": sales["sold_price_status"],
    }


def _pct(new, old):
    return pricing._number((new / old - Decimal("1")) * Decimal("100")) if old is not None and old != 0 else None


def _impact(before_rows, after_rows):
    before, after = _window(before_rows), _window(after_rows)
    before_units, after_units = before["units"], after["units"]
    revenue_comparable = (before["sold_price_status"] == "available"
                          and after["sold_price_status"] == "available"
                          and before["currency"] == after["currency"])
    weighted_comparable = revenue_comparable
    before_revenue = pricing._decimal(before["revenue"])
    after_revenue = pricing._decimal(after["revenue"])
    before_weighted = pricing._decimal(before["weighted_avg_price"])
    after_weighted = pricing._decimal(after["weighted_avg_price"])
    return {
        "status": "available", "before": before, "after": after,
        "units_delta": after_units - before_units,
        "units_change_pct": _pct(Decimal(after_units), Decimal(before_units)),
        "revenue_delta": pricing._decimal_text(after_revenue - before_revenue)
        if revenue_comparable and before_revenue is not None and after_revenue is not None else None,
        "revenue_change_pct": _pct(after_revenue, before_revenue)
        if revenue_comparable and before_revenue is not None and after_revenue is not None else None,
        "weighted_avg_price_change_pct": _pct(after_weighted, before_weighted)
        if weighted_comparable and before_weighted is not None and after_weighted is not None else None,
        "reason": None,
    }


def _sales_rows(db, shop_id, channel, start_day, end_day, *, offer_id=None, sku=None):
    offer_id, sku = pricing._text(offer_id), pricing._text(sku)
    if offer_id:
        match_field, match_value = "i.offer_id", offer_id
    elif sku:
        match_field, match_value = "i.sku", sku
    else:
        return None
    start = _utc_text(datetime.combine(start_day, datetime.min.time(), BEIJING).astimezone(timezone.utc))
    end = _utc_text(datetime.combine(end_day + timedelta(days=1), datetime.min.time(), BEIJING).astimezone(timezone.utc))
    rows = db.execute(f"""SELECT i.quantity,i.unit_price,i.price_currency,o.created_at
      FROM order_items i JOIN orders o USING(shop_id,posting_number)
      WHERE {ACTIVE} AND o.shop_id=? AND o.channel=? AND o.created_at>=? AND o.created_at<?
        AND {match_field}=? ORDER BY o.created_at""",
                      (shop_id, channel, start, end, match_value)).fetchall()
    by_day = {}
    for row in rows:
        observed = _utc_moment(row["created_at"])
        if observed:
            by_day.setdefault(observed.astimezone(BEIJING).date(), []).append(row)
    return by_day


def _attach_impacts(db, events, shop_id, channel, today):
    effective_events = [event for event in events if "effective_price_changed" in event["types"]]
    if not effective_events:
        return
    for event in effective_events:
        if not event["event_day"]:
            event["impact"] = {"status": "unavailable", "before": None, "after": None,
                                "units_delta": None, "units_change_pct": None,
                                "revenue_delta": None, "revenue_change_pct": None,
                                "weighted_avg_price_change_pct": None,
                                "reason": "invalid_event_time"}
            continue
        event_day = date.fromisoformat(event["event_day"])
        if today < event_day + timedelta(days=8):
            event["impact"] = {"status": "pending", "before": None, "after": None,
                                "units_delta": None, "units_change_pct": None,
                                "revenue_delta": None, "revenue_change_pct": None,
                                "weighted_avg_price_change_pct": None,
                                "reason": "after_window_incomplete"}
            continue
        before_offer_id = pricing._text(event.get("before_offer_id"))
        after_offer_id = pricing._text(event.get("after_offer_id"))
        if not before_offer_id or not after_offer_id:
            event["impact"] = {"status": "unavailable", "before": None, "after": None,
                                "units_delta": None, "units_change_pct": None,
                                "revenue_delta": None, "revenue_change_pct": None,
                                "weighted_avg_price_change_pct": None,
                                "reason": "missing_historical_product_match"}
            continue
        before_rows = _sales_rows(
            db, shop_id, channel, event_day - timedelta(days=7), event_day - timedelta(days=1),
            offer_id=before_offer_id,
        ) or {}
        after_rows = _sales_rows(
            db, shop_id, channel, event_day + timedelta(days=1), event_day + timedelta(days=7),
            offer_id=after_offer_id,
        ) or {}
        before = [row for day in (event_day - timedelta(days=offset) for offset in range(7, 0, -1))
                  for row in before_rows.get(day, [])]
        after = [row for day in (event_day + timedelta(days=offset) for offset in range(1, 8))
                 for row in after_rows.get(day, [])]
        event["impact"] = _impact(before, after)


def _strategy(current_item, market_sources, market_reference, market_warnings, settlement_currency, rates):
    economics = current_item["economics"]
    sales = current_item["sales_30"]
    current = pricing._decimal(economics["current_effective_price"])
    break_even = pricing._decimal(economics["break_even_price"])
    target = pricing._decimal(economics["target_margin_price"])
    market = market_reference
    reasons = []
    if current is None or current <= 0:
        reasons.append("missing_current_price")
    if target is None:
        reasons.append("missing_target_margin_price")
    if market is None or market <= 0:
        reasons.append("missing_market_reference")
    if current is not None and break_even is not None and current < break_even:
        reasons.append("current_below_break_even")
    if current is not None and target is not None and current < target:
        reasons.append("current_below_target_margin")
    if current is not None and market is not None and current > market:
        reasons.append("current_above_market_reference")
    if current is not None and target is not None and market is not None and target <= current <= market:
        reasons.append("within_observation_range")
    if target is not None and market is not None and target > market:
        reasons.append("target_margin_above_market")
    missing_core = current is None or current <= 0 or target is None or market is None or market <= 0
    if missing_core:
        signal = "insufficient_data"
    elif target > market:
        signal = "margin_market_conflict"
    elif current < target:
        signal = "raise"
    elif current > market:
        signal = "reduce"
    else:
        signal = "hold"
    if target is None or market is None or market <= 0:
        observation = {"status": "unavailable", "lower": None, "upper": None}
    elif target > market:
        observation = {"status": "conflict", "lower": None, "upper": None}
    else:
        observation = {"status": "available", "lower": pricing._decimal_text(target),
                       "upper": pricing._decimal_text(market)}
    sold = pricing._decimal(sales["weighted_avg_price"])
    sold = pricing._convert(sold, sales["currency"], settlement_currency, rates) if sold is not None else None
    return {
        "status": "available", "signal": signal, "currency": settlement_currency,
        "current_price": pricing._decimal_text(current),
        "break_even_price": pricing._decimal_text(break_even),
        "target_margin_price": pricing._decimal_text(target),
        "sold_price_30": pricing._decimal_text(sold),
        "sold_price_status": sales["sold_price_status"],
        "market_reference_price": pricing._decimal_text(market),
        "observation_range": observation,
        "market_sources": market_sources,
        "reason_codes": list(dict.fromkeys(reasons)),
        "warnings": list(dict.fromkeys(market_warnings)),
    }


def get_pricing_strategy(shop_id, snapshot_key, channel="FBP", target_margin_pct=20,
                         history_days=90, now=None):
    if type(shop_id) is not int or shop_id not in (1, 2):
        raise ValueError("策略详情必须指定店铺1或2")
    snapshot_key = _snapshot_key(snapshot_key)
    channel = pricing._channel(channel)
    target_margin = pricing._target_margin(target_margin_pct)
    history_days = _history_days(history_days)
    moment = pricing._sales_window(now)[0]
    with connect() as db:
        shop = db.execute("SELECT id,name,settlement_currency FROM shops WHERE id=?", (shop_id,)).fetchone()
        through, _ = pricing._latest_price_batch(db, shop_id)
        current_row = db.execute("""SELECT 1 FROM product_price_snapshots
          WHERE shop_id=? AND snapshot_key=? AND observed_at=?""",
                                 (shop_id, snapshot_key, through)).fetchone() if through else None
        if not shop or not current_row:
            raise PricingStrategyNotFound("价格实体不属于当前店铺最新完整价格批次")
        through_moment = _utc_moment(through)
        if not through_moment:
            raise ValueError("当前价格批次时间无效")
        history_from = through_moment - timedelta(days=history_days)
        history_rows = db.execute("""SELECT * FROM product_price_snapshots
          WHERE shop_id=? AND snapshot_key=? AND observed_at>=? AND observed_at<=?
          ORDER BY observed_at ASC""",
                                  (shop_id, snapshot_key, _utc_text(history_from), _utc_text(through_moment))).fetchall()
        exchange_entries = pricing.current_exchange_rate_entries(db, moment.astimezone(timezone.utc))
        rates = _rates(exchange_entries)

    current_response = pricing.get_pricing(
        shop_id, channel=channel, target_margin_pct=target_margin, page=1, size=1, now=moment,
        _snapshot_key=snapshot_key, _price_batch_through=through, _exchange_entries=exchange_entries,
    )
    if not current_response["items"]:
        raise PricingStrategyNotFound("价格实体不属于当前店铺最新完整价格批次")
    current_item = current_response["items"][0]
    settlement_currency = shop["settlement_currency"]
    market_sources, market_reference, market_warnings = _market_reference(
        current_item["competitiveness"], settlement_currency, rates)
    strategy = _strategy(current_item, market_sources, market_reference, market_warnings, settlement_currency, rates)
    events = []
    for index in range(1, len(history_rows)):
        event = _price_event(history_rows[index - 1], history_rows[index], index)
        if event:
            events.append(event)
    with connect() as db:
        _attach_impacts(db, events, shop_id, channel, moment.astimezone(BEIJING).date())
    points = [_history_point(row) for row in history_rows]
    keep = {0, len(points) - 1} if points else set()
    keep.update(event["_point_index"] for event in events
                if "effective_price_changed" in event["types"] or "currency_changed" in event["types"])
    points = [point for index, point in enumerate(points) if index in keep]
    for event in events:
        event.pop("_point_index", None)
    return {
        "as_of": current_response["as_of"], "shop_id": shop_id, "shop_name": shop["name"],
        "snapshot_key": snapshot_key, "reference_channel": channel,
        "target_margin_pct": pricing._number(target_margin), "product": current_item["product"],
        "current": {key: current_item[key] for key in ("price", "sales_30", "economics", "competitiveness", "stock")},
        "strategy": strategy,
        "history": {
            "days": history_days, "from": _utc_text(history_from), "to": _utc_text(through_moment),
            "snapshot_count": len(history_rows),
            "price_change_count": sum("effective_price_changed" in event["types"] for event in events),
            "points": points, "events": events,
        },
    }
