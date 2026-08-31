from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..db import connect
from ..exchange import load_base_rate_periods, rates_for_order
from ..ozon.client import BEIJING
from ..products import load_product_rules, resolve_product
from .common import ACTIVE, _duration_hours, _overview_range, _percentile, _shop_clause


router = APIRouter()


def _bucket_start(value, granularity):
    if granularity == "week":
        return value - timedelta(days=value.weekday())
    if granularity == "month":
        return value.replace(day=1)
    return value


def _next_bucket(value, granularity):
    if granularity == "day":
        return value + timedelta(days=1)
    if granularity == "week":
        return value + timedelta(days=7)
    return date(value.year + (value.month == 12), value.month % 12 + 1, 1)


def _beijing_date(value):
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(BEIJING).date()


def _group_by_bucket_and_channel(rows, granularity):
    grouped = {}
    for row in rows:
        key = _bucket_start(_beijing_date(row["created_at"]), granularity)
        bucket = grouped.setdefault(key, {"rows": [], "channels": {}})
        bucket["rows"].append(row)
        bucket["channels"].setdefault(row["channel"], []).append(row)
    return grouped


def _gmv_summary(rows, shop_id, rate_periods=()):
    currency = "USD" if shop_id == 1 else "CNY"
    amount = Decimal("0")
    missing = 0
    for row in rows:
        value = row["amount_original"] if row["amount_original"] is not None else row["item_amount"]
        value_currency = (row["amount_currency"] or row["item_currency"] or
                          row["settlement_currency"] or "").upper()
        if value is None:
            continue
        value = Decimal(str(value))
        if shop_id:
            if value_currency == currency:
                amount += value
        elif value_currency == "CNY":
            amount += value
        elif value_currency == "USD":
            rates = rates_for_order(rate_periods, row["created_at"])
            if not rates or not rates.get("USD") or not rates.get("CNY"):
                missing += 1
            else:
                amount += value * rates["USD"] / rates["CNY"]
    return {"amount": float(amount.quantize(Decimal("0.01"))), "currency": currency if shop_id else "CNY",
            "missing_rate_orders": missing}


def _overview_timeliness(rows):
    grouped = {channel: {"ship": [], "delivery": []} for channel in ("FBP", "realFBS", "WHD")}
    for row in rows:
        delivered_at = row["delivered_at"]
        if row["channel"] in ("FBP", "realFBS") and delivered_at == row["shipped_at"]:
            delivered_at = None
        ship = _duration_hours(row["created_at"], row["shipped_at"])
        delivery = _duration_hours(row["shipped_at"], delivered_at)
        if ship is not None:
            grouped[row["channel"]]["ship"].append(ship)
        if delivery is not None:
            grouped[row["channel"]]["delivery"].append(delivery)
    return [{"channel": channel,
             "ship_samples": len(values["ship"]),
             "delivery_samples": len(values["delivery"]),
             "p50_ship_hours": _percentile(values["ship"], .5),
             "p50_delivery_hours": _percentile(values["delivery"], .5),
             "p90_delivery_hours": _percentile(values["delivery"], .9),
             "ship_sample_insufficient": len(values["ship"]) < 30,
             "delivery_sample_insufficient": len(values["delivery"]) < 30}
            for channel, values in grouped.items()]


def _overview_top_products(db, utc_start, utc_end, shop_id):
    clause, shop_args = _shop_clause(shop_id)
    rows = db.execute(f"""SELECT o.shop_id,o.posting_number,o.status_raw,o.shipped,
      i.sku,i.offer_id,i.product_name_raw,i.quantity
      FROM orders o JOIN order_items i USING(shop_id,posting_number)
      WHERE {ACTIVE} AND o.created_at>=?
        AND o.created_at<? {clause}""", [utc_start, utc_end] + shop_args)
    rules = load_product_rules(db)
    products = {}
    for row in rows:
        resolved = resolve_product(rules, row["sku"], row["offer_id"], row["product_name_raw"])
        key = row["shop_id"], resolved["identity"]
        item = products.setdefault(key, {"name": resolved["display_name"],
                                         "pieces": 0, "orders": set(), "cancelled": set()})
        item["pieces"] += row["quantity"]
        posting = row["shop_id"], row["posting_number"]
        item["orders"].add(posting)
        if row["status_raw"] == "已取消" and row["shipped"] == 1:
            item["cancelled"].add(posting)
    result = [{"name": item["name"], "pieces": item["pieces"], "orders": len(item["orders"]),
               "cancel_rate": len(item["cancelled"]) / len(item["orders"])}
              for item in products.values()]
    return sorted(result, key=lambda item: (-item["pieces"], -item["orders"], item["name"]))[:5]


@router.get("/api/summary")
def summary(shop_id: int = 0,
            date_from: Annotated[str | None, Query(alias="from")] = None,
            date_to: Annotated[str | None, Query(alias="to")] = None,
            granularity: str = "week"):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    if granularity not in ("day", "week", "month"):
        raise HTTPException(400, "granularity 必须为 day、week 或 month")
    start, end, utc_start, utc_end = _overview_range(date_from, date_to, max_days=3660)
    clause, shop_args = _shop_clause(shop_id)
    args = [utc_start, utc_end] + shop_args
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,o.posting_number,o.channel,o.created_at,o.status_raw,o.shipped,
            o.shipped_at,o.delivered_at,o.data_anomaly,
            o.amount_original,o.amount_currency,s.settlement_currency,
            COALESCE(SUM(i.quantity),0) pieces,
            CASE WHEN o.amount_original IS NULL AND COUNT(i.sku)>0
              AND COUNT(i.unit_price)=COUNT(i.sku) AND COUNT(DISTINCT i.price_currency)=1
              THEN SUM(i.unit_price*i.quantity) END item_amount,
            CASE WHEN COUNT(DISTINCT i.price_currency)=1 THEN MIN(i.price_currency) END item_currency
          FROM orders o JOIN shops s ON s.id=o.shop_id
          LEFT JOIN order_items i USING(shop_id,posting_number)
          WHERE {ACTIVE} AND o.created_at>=?
            AND o.created_at<? {clause}
          GROUP BY o.shop_id,o.posting_number
          ORDER BY o.created_at
        """, args)]
        top_products = _overview_top_products(db, utc_start, utc_end, shop_id)
        rate_periods = load_base_rate_periods(db, utc_start, utc_end) if shop_id == 0 else []
    totals = {"orders": 0, "pieces": 0, "cancelled_orders": 0, "cancelled_pieces": 0}
    channels_by_name = {channel: {"channel": channel, "orders": 0, "pieces": 0, "cancelled_pieces": 0}
                        for channel in ("FBP", "realFBS", "WHD")}
    for row in rows:
        totals["orders"] += 1
        totals["pieces"] += row["pieces"]
        cancelled = row["status_raw"] == "已取消" and row["shipped"] == 1
        if cancelled:
            totals["cancelled_orders"] += 1
            totals["cancelled_pieces"] += row["pieces"]
        channel = channels_by_name.get(row["channel"])
        if channel is not None:
            channel["orders"] += 1
            channel["pieces"] += row["pieces"]
            if cancelled:
                channel["cancelled_pieces"] += row["pieces"]
    totals["cancel_rate"] = totals["cancelled_pieces"] / totals["pieces"] if totals["pieces"] else 0
    channels = list(channels_by_name.values())
    bucket_dates = []
    cursor = _bucket_start(start, granularity)
    while cursor <= end:
        bucket_dates.append(cursor)
        cursor = _next_bucket(cursor, granularity)
    grouped_rows = _group_by_bucket_and_channel(rows, granularity)
    buckets = []
    for bucket_date in bucket_dates:
        next_date = _next_bucket(bucket_date, granularity)
        bucket = grouped_rows.get(bucket_date, {"rows": [], "channels": {}})
        bucket_rows = bucket["rows"]
        channel_values = {}
        for channel in ("FBP", "realFBS", "WHD"):
            values = bucket["channels"].get(channel, [])
            channel_values[channel] = {"orders": len(values), "gmv": _gmv_summary(values, shop_id, rate_periods)}
        buckets.append({"key": bucket_date.isoformat(),
                        "from": max(bucket_date, start).isoformat(),
                        "to": min(next_date - timedelta(days=1), end).isoformat(),
                        "orders": len(bucket_rows), "gmv": _gmv_summary(bucket_rows, shop_id, rate_periods),
                        "channels": channel_values})
    return {"range": {"from": start.isoformat(), "to": end.isoformat()},
            "granularity": granularity, "totals": totals, "channels": channels,
            "buckets": buckets, "gmv": _gmv_summary(rows, shop_id, rate_periods),
            "timeliness": _overview_timeliness(rows), "top_products": top_products,
            "data_through": max((row["created_at"] for row in rows), default=None)}


def _trend_range(granularity: str, now: datetime | None = None):
    today = (now or datetime.now(BEIJING)).date()
    if granularity == "day":
        start = today - timedelta(days=89)
        end = today
    elif granularity == "week":
        cur_week = _bucket_start(today, "week")
        start = cur_week - timedelta(weeks=11)
        end = cur_week + timedelta(days=6)
    else:
        cur_month = today.replace(day=1)
        year = cur_month.year
        month = cur_month.month - 11
        if month <= 0:
            year -= 1
            month += 12
        start = date(year, month, 1)
        next_m = _next_bucket(cur_month, "month")
        end = next_m - timedelta(days=1)
    utc_start = datetime.combine(start, datetime.min.time(), BEIJING).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    utc_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), BEIJING).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return start, end, utc_start, utc_end


@router.get("/api/order-trend")
def order_trend(shop_id: int = 0, granularity: str = "day"):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    if granularity not in ("day", "week", "month"):
        raise HTTPException(400, "granularity 必须为 day、week 或 month")
    start, end, utc_start, utc_end = _trend_range(granularity)
    clause, shop_args = _shop_clause(shop_id)
    args = [utc_start, utc_end] + shop_args
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,o.posting_number,o.channel,o.created_at,o.status_raw,o.shipped,
            o.amount_original,o.amount_currency,s.settlement_currency,
            COALESCE(SUM(i.quantity),0) pieces,
            CASE WHEN o.amount_original IS NULL AND COUNT(i.sku)>0
              AND COUNT(i.unit_price)=COUNT(i.sku) AND COUNT(DISTINCT i.price_currency)=1
              THEN SUM(i.unit_price*i.quantity) END item_amount,
            CASE WHEN COUNT(DISTINCT i.price_currency)=1 THEN MIN(i.price_currency) END item_currency
          FROM orders o JOIN shops s ON s.id=o.shop_id
          LEFT JOIN order_items i USING(shop_id,posting_number)
          WHERE {ACTIVE} AND o.created_at>=?
            AND o.created_at<? {clause}
          GROUP BY o.shop_id,o.posting_number
          ORDER BY o.created_at
        """, args)]
        rate_periods = load_base_rate_periods(db, utc_start, utc_end) if shop_id == 0 else []
    bucket_dates = []
    cursor = _bucket_start(start, granularity)
    while cursor <= end:
        bucket_dates.append(cursor)
        cursor = _next_bucket(cursor, granularity)
    grouped_rows = _group_by_bucket_and_channel(rows, granularity)
    buckets = []
    for bucket_date in bucket_dates:
        next_date = _next_bucket(bucket_date, granularity)
        bucket = grouped_rows.get(bucket_date, {"rows": [], "channels": {}})
        bucket_rows = bucket["rows"]
        channel_values = {}
        for channel in ("FBP", "realFBS", "WHD"):
            values = bucket["channels"].get(channel, [])
            channel_values[channel] = {"orders": len(values), "gmv": _gmv_summary(values, shop_id, rate_periods)}
        buckets.append({"key": bucket_date.isoformat(),
                        "from": max(bucket_date, start).isoformat(),
                        "to": min(next_date - timedelta(days=1), end).isoformat(),
                        "orders": len(bucket_rows), "gmv": _gmv_summary(bucket_rows, shop_id, rate_periods),
                        "channels": channel_values})
    return {"granularity": granularity, "from": start.isoformat(), "to": end.isoformat(), "buckets": buckets}
