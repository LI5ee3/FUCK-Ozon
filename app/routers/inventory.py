import json
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from ..db import connect
from ..ozon.client import BEIJING
from ..products import load_product_rules, resolve_product
from .common import ACTIVE, _paging, _shop_clause, _utc_moment, _utc_text


router = APIRouter()
FORECAST_WINDOWS = (7, 15, 30)
FORECAST_WEIGHTS = {7: .50, 15: .30, 30: .20}
FORECAST_LEAD_TIME_DAYS = 25
FORECAST_TARGET_COVER_DAYS = 60
FORECAST_OVERSTOCK_DAYS = 90
FORECAST_RISK_LABELS = {
    "out_of_stock": "缺货",
    "urgent_replenishment": "紧急补货",
    "replenish": "需要补货",
    "sufficient": "库存充足",
    "overstock": "库存偏高",
    "no_recent_sales": "无近期销量",
}
FORECAST_RISK_ORDER = {
    "out_of_stock": 0, "urgent_replenishment": 1, "replenish": 2,
    "sufficient": 3, "overstock": 4, "no_recent_sales": 5,
}


def _record_clause(shop_id, alias="r"):
    return (f" WHERE {alias}.shop_id=?", [shop_id]) if shop_id in (1, 2) else ("", [])


def _latest_stock_snapshots(db, shop_id):
    where, args = _record_clause(shop_id, "r")
    return db.execute(f"""SELECT r.shop_id,s.name shop_name,r.observed_at,r.payload FROM stock_snapshots r
      JOIN shops s ON s.id=r.shop_id{where}
      ORDER BY r.shop_id,r.record_key""", args).fetchall()


def _stock_quantity(value):
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _forecast_bounds(today, days):
    start = today - timedelta(days=days)
    return (_utc_text(datetime.combine(start, datetime.min.time(), BEIJING)),
            _utc_text(datetime.combine(today, datetime.min.time(), BEIJING)))


def _history_channel(row):
    source = str(row["source"] or "")
    if source == "push_rfbs":
        return "realFBS"
    if source == "push_fbo":
        return "WHD"
    event_key = str(row["event_key"] or "").rsplit(":", 1)[-1].lower()
    return {"fbp": "FBP", "fbs": "realFBS", "rfbs": "realFBS", "fbo": "WHD"}.get(event_key)


def _stock_history_index(history_rows):
    index = {}
    for row in history_rows:
        channel = _history_channel(row)
        moment = _utc_moment(row["occurred_at"])
        if not channel or not moment:
            continue
        key = (row["shop_id"], str(row["sku"] or ""), channel)
        warehouse = str(row["warehouse_id"] or "")
        index.setdefault(key, {}).setdefault(warehouse, []).append(
            (moment, _stock_quantity(row["present"])))
    for series in index.values():
        for values in series.values():
            values.sort(key=lambda value: value[0])
    return index


def _confirmed_stockout_days(history_index, shop_id, sku, channel, sales_end):
    """Return only days whose stock log proves zero stock for the whole day.

    A point-in-time snapshot is not enough.  Each tracked warehouse/source must
    have a zero state at both day boundaries and no positive event in between.
    """
    series = history_index.get((shop_id, sku, channel))
    if not series:
        return None
    confirmed = set()
    for offset in range(30):
        day = sales_end - timedelta(days=offset)
        start = datetime.combine(day, datetime.min.time(), BEIJING).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), datetime.min.time(), BEIJING).astimezone(timezone.utc)
        reliable = True
        for values in series.values():
            before = [value for value in values if value[0] <= start]
            after = [value for value in values if value[0] >= end]
            if not before or not after or before[-1][1] or after[0][1]:
                reliable = False
                break
            if any(value for moment, value in values if start <= moment < end):
                reliable = False
                break
        if reliable:
            confirmed.add(day)
    return confirmed


def _forecast_values(sales, first_sale_at, stockout_days, sales_end):
    first_sale = _utc_moment(first_sale_at)
    first_sale = first_sale.astimezone(BEIJING).date() if first_sale else None
    age_days = max((sales_end - first_sale).days + 1, 0) if first_sale and first_sale <= sales_end else 0
    daily, data_days, in_stock_days = {}, {}, {}
    full_windows = []
    for window in FORECAST_WINDOWS:
        observed_days = min(window, age_days) if age_days else 0
        data_days[window] = observed_days
        if stockout_days is None:
            in_stock_days[window] = None
            denominator = observed_days
        else:
            start = sales_end - timedelta(days=observed_days - 1) if observed_days else sales_end
            counted = sum(start <= day <= sales_end for day in stockout_days)
            in_stock_days[window] = max(observed_days - counted, 0)
            denominator = in_stock_days[window]
        value = float(sales.get(f"sales_{window}") or 0)
        daily[window] = value / denominator if denominator else (0.0 if not value else None)
        if age_days >= window and daily[window] is not None:
            full_windows.append(window)
    if full_windows:
        windows = full_windows
    elif data_days[7] and daily[7] is not None:
        windows = [7]
    elif data_days[15] and daily[15] is not None:
        windows = [15]
    elif data_days[30] and daily[30] is not None:
        windows = [30]
    else:
        windows = []
    weight_total = sum(FORECAST_WEIGHTS[window] for window in windows)
    forecast = (sum(daily[window] * FORECAST_WEIGHTS[window] for window in windows
                    if daily[window] is not None) / weight_total
                if weight_total else 0.0)
    adjusted = bool(stockout_days)
    ratio = daily[7] / daily[30] if daily[7] is not None and daily[30] else None
    trend = "快速增长" if ratio is not None and ratio >= 1.30 else "稳定" if ratio is None or ratio >= .80 else "下降"
    return {"daily": daily, "data_days": data_days, "in_stock_days": in_stock_days,
            "forecast": forecast, "windows": windows, "adjusted": adjusted,
            "stockout_days": len(stockout_days or ()), "trend_7_vs_30": ratio, "trend": trend}


def _forecast_risk(effective_stock, forecast_daily, days_cover, recommended):
    if not forecast_daily:
        return "no_recent_sales"
    if effective_stock <= 0:
        return "out_of_stock"
    if days_cover is not None and days_cover <= FORECAST_LEAD_TIME_DAYS:
        return "urgent_replenishment"
    if recommended > 0:
        return "replenish"
    if days_cover is not None and days_cover > FORECAST_OVERSTOCK_DAYS:
        return "overstock"
    return "sufficient"


@router.get("/api/stock")
def stock(shop_id: int = 0, page: int = 1, size: int = 50, sku: str = "",
          offer_id: str = "", product_name: str = "", sort_by: str = "",
          sort_order: str = "desc", channel: str = "", risk: str = "", q: str = ""):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    channel = {"all": "", "fbp": "FBP", "realfbs": "realFBS", "whd": "WHD"}.get(channel, channel)
    if channel not in ("", "FBP", "realFBS", "WHD"):
        raise HTTPException(400, "未知履约模式")
    reference_channel = channel or "FBP"
    risk = {"需要关注": "attention", "缺货": "out_of_stock", "紧急补货": "urgent_replenishment",
            "需要补货": "replenish", "库存充足": "sufficient", "库存偏高": "overstock",
            "无近期销量": "no_recent_sales"}.get(risk, risk)
    valid_risks = {"", "attention", *FORECAST_RISK_LABELS}
    if risk not in valid_risks:
        raise HTTPException(400, "未知库存风险")
    if sort_by not in ("", "fbp", "realfbs", "whd", "forecast", "replenishment", "days_cover", "risk"):
        raise HTTPException(400, "未知排序字段")
    if sort_order not in ("asc", "desc"):
        raise HTTPException(400, "未知排序方向")
    page, size = _paging(page, size)
    today = datetime.now(BEIJING).date()
    sales_end = today - timedelta(days=1)
    bounds = [_forecast_bounds(today, days) for days in FORECAST_WINDOWS]
    shop_clause, shop_args = _shop_clause(shop_id)
    with connect() as db:
        records = _latest_stock_snapshots(db, shop_id)
        history_rows = db.execute("""SELECT shop_id,source,warehouse_id,sku,present,reserved,occurred_at,event_key
          FROM stock_history WHERE (?=0 OR shop_id=?) ORDER BY shop_id,sku,occurred_at""",
                                 (shop_id, shop_id)).fetchall()
        history_index = _stock_history_index(history_rows)
        sales = {(row["shop_id"], row["sku"]): dict(row) for row in db.execute(f"""SELECT i.shop_id,i.sku,
          SUM(CASE WHEN o.created_at>=? AND o.created_at<? THEN i.quantity ELSE 0 END) sales_7,
          SUM(CASE WHEN o.created_at>=? AND o.created_at<? THEN i.quantity ELSE 0 END) sales_15,
          SUM(CASE WHEN o.created_at>=? AND o.created_at<? THEN i.quantity ELSE 0 END) sales_30,
          MIN(o.created_at) first_sale_at
          FROM order_items i JOIN orders o USING(shop_id,posting_number)
          WHERE {ACTIVE} AND o.channel IN ('FBP','realFBS')
            AND o.created_at<? {shop_clause}
          GROUP BY i.shop_id,i.sku""", [bound for pair in bounds for bound in pair] + [bounds[0][1]] + shop_args)}
        metadata = {}
        for row in db.execute(f"""SELECT i.shop_id,i.sku,i.offer_id,i.product_name_raw,i.source,o.created_at
          FROM order_items i JOIN orders o USING(shop_id,posting_number)
          WHERE 1=1 {shop_clause}
          ORDER BY (i.source='api') DESC,o.created_at DESC""", shop_args):
            item = metadata.setdefault((row["shop_id"], row["sku"]), {"offer_id": "", "product_name_raw": ""})
            item["offer_id"] = item["offer_id"] or row["offer_id"] or ""
            item["product_name_raw"] = item["product_name_raw"] or row["product_name_raw"] or ""
        ad_stats = {(row["shop_id"], str(row["sku"])): {"ad_orders": int(row["ad_orders"] or 0),
                    "product_name": row["product_name"] or "", "has_rows": bool(row["has_rows"])}
                    for row in db.execute("""SELECT shop_id,sku,MAX(NULLIF(product_name,'')) product_name,
                      SUM(CASE WHEN stat_date BETWEEN ? AND ? THEN COALESCE(orders,0) ELSE 0 END) ad_orders,
                      MAX(CASE WHEN stat_date BETWEEN ? AND ? THEN 1 ELSE 0 END) has_rows
                      FROM ad_sku_daily WHERE (?=0 OR shop_id=?) GROUP BY shop_id,sku""",
                                         (bounds[2][0][:10], sales_end.isoformat(), bounds[2][0][:10],
                                          sales_end.isoformat(), shop_id, shop_id))}
        shop_names = {row["id"]: row["name"] for row in db.execute("SELECT id,name FROM shops")}
        rules = load_product_rules(db)
        sales_through = db.execute(f"""SELECT MAX(data_through) FROM sync_runs o
          WHERE module='orders' AND status='success'{shop_clause}""", shop_args).fetchone()[0]
        if not sales_through:
            sales_through = db.execute(f"""SELECT MAX(o.created_at) FROM orders o
              WHERE o.channel IN ('FBP','realFBS'){shop_clause}""", shop_args).fetchone()[0]
    grouped = {}
    channel_names = {"fbp": "FBP", "rfbs": "realFBS", "fbo": "WHD"}

    def empty_group(item_shop, item_sku):
        return {"shop_id": item_shop, "shop_name": shop_names.get(item_shop, f"店铺{item_shop}"),
                "sku": str(item_sku), "offer_id": "", "product_id": None, "_channels": {}}

    for row in records:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            continue
        for value in payload.get("stocks") or []:
            item_sku = str(value.get("sku") or payload.get("product_id") or "")
            channel = channel_names.get(str(value.get("type") or "").lower())
            if not item_sku or not channel:
                continue
            key = row["shop_id"], item_sku
            group = grouped.setdefault(key, empty_group(row["shop_id"], item_sku))
            group["offer_id"] = group["offer_id"] or str(payload.get("offer_id") or "")
            group["product_id"] = group["product_id"] or payload.get("product_id")
            stock_value = group["_channels"].setdefault(channel, {"channel": channel, "source": "api",
              "present": 0, "reserved": 0, "observed_at": row["observed_at"]})
            stock_value["present"] += _stock_quantity(value.get("present"))
            stock_value["reserved"] += _stock_quantity(value.get("reserved"))
            stock_value["observed_at"] = max(stock_value["observed_at"] or "", row["observed_at"] or "")
    push_latest = {}
    for row in history_rows:
        if row["source"] not in ("push_rfbs", "push_fbo"):
            continue
        key = (row["shop_id"], row["source"], row["sku"], row["warehouse_id"] or "")
        previous = push_latest.get(key)
        current_at = _utc_moment(row["occurred_at"])
        previous_at = _utc_moment(previous["occurred_at"]) if previous else None
        if not previous or (current_at and (not previous_at or current_at > previous_at)):
            push_latest[key] = row
    push_groups = {}
    for row in push_latest.values():
        push_groups.setdefault((row["shop_id"], row["source"], row["sku"]), []).append(row)
    for (push_shop, source, item_sku), rows in push_groups.items():
        channel = "realFBS" if source == "push_rfbs" else "WHD"
        key = push_shop, str(item_sku)
        group = grouped.setdefault(key, empty_group(push_shop, item_sku))
        baseline = group["_channels"].get(channel)
        values = list(rows)
        if baseline and _utc_moment(baseline["observed_at"]):
            values = [value for value in values if _utc_moment(value["occurred_at"])
                      and _utc_moment(value["occurred_at"]) > _utc_moment(baseline["observed_at"])]
        if values:
            observed_at = max(value["occurred_at"] for value in values)
            group["_channels"][channel] = {"channel": channel, "source": source,
              "present": sum(_stock_quantity(value["present"]) for value in values),
              "reserved": sum(_stock_quantity(value["reserved"]) for value in values), "observed_at": observed_at}
    for key in sales:
        grouped.setdefault(key, empty_group(key[0], key[1]))
    for key, value in ad_stats.items():
        group = grouped.setdefault(key, empty_group(key[0], key[1]))
        metadata.setdefault(key, {"offer_id": "", "product_name_raw": value["product_name"]})
    cards = []
    for group in grouped.values():
        meta = metadata.get((group["shop_id"], group["sku"]), {})
        group["offer_id"] = group["offer_id"] or meta.get("offer_id") or ""
        raw_name = meta.get("product_name_raw") or ""
        resolved = resolve_product(rules, group["sku"], group["offer_id"], raw_name)
        channels_by_name = group.pop("_channels")
        channels = [channels_by_name.get(channel, {"channel": channel, "source": "api",
                    "present": 0, "reserved": 0, "observed_at": None})
                    for channel in ("FBP", "realFBS", "WHD")]
        for value in channels:
            value["present"] = _stock_quantity(value.get("present"))
            value["reserved"] = _stock_quantity(value.get("reserved"))
            value["effective_stock"] = value["present"]
        sold = sales.get((group["shop_id"], group["sku"]), {})
        group.update({"offer_id": group["offer_id"] or resolved["primary_offer_id"] or "",
                      "product_id": group["product_id"], "product_name_raw": resolved["platform_name"],
                      "short_name": rules["short_names"].get(resolved["primary_sku"] or group["sku"], ""),
                      "display_name": resolved["display_name"], "analysis_identity": resolved["identity"],
                      "group_id": resolved["group_id"], "primary_offer_id": resolved["primary_offer_id"],
                      "offer_members": [group["offer_id"]] if group["offer_id"] else []})
        group["channels"] = channels
        group["present"] = sum(value["present"] for value in channels)
        group["reserved"] = sum(value["reserved"] for value in channels)
        group["sales_7"] = int(sold.get("sales_7") or 0)
        group["sales_15"] = int(sold.get("sales_15") or 0)
        group["sales_30"] = int(sold.get("sales_30") or 0)
        # Replenishment policy:
        # demand = FBP + realFBS sales
        # replenishment stock = FBP only
        # WHD does not participate in demand or replenishment calculations.
        forecast_channel = "FBP"
        base = next(value for value in channels if value["channel"] == forecast_channel)
        stockout_days = _confirmed_stockout_days(history_index, group["shop_id"], group["sku"],
                                                  forecast_channel, sales_end)
        forecast = _forecast_values(sold, sold.get("first_sale_at"), stockout_days, sales_end)
        daily = forecast["forecast"]
        effective_stock = base["effective_stock"]
        days_cover = effective_stock / daily if daily else None
        projected = max(effective_stock - daily * FORECAST_LEAD_TIME_DAYS, 0) if daily else None
        recommended = math.ceil(max(daily * FORECAST_TARGET_COVER_DAYS - projected, 0)) if daily else 0
        risk_code = _forecast_risk(effective_stock, daily, days_cover, recommended)
        ad = ad_stats.get((group["shop_id"], group["sku"]), {})
        ad_orders = ad.get("ad_orders") if ad.get("has_rows") else None
        group.update({
            "current_stock": effective_stock, "reserved_stock": base["reserved"], "effective_stock": effective_stock,
            "forecast_channel": forecast_channel, "sales_data_through": sales_end.isoformat(),
            "daily_7": forecast["daily"][7], "daily_15": forecast["daily"][15], "daily_30": forecast["daily"][30],
            "daily_sales": daily, "forecast_daily": daily, "sales_data_days_7": forecast["data_days"][7],
            "sales_data_days_15": forecast["data_days"][15], "sales_data_days_30": forecast["data_days"][30],
            "in_stock_days_7": forecast["in_stock_days"][7], "in_stock_days_15": forecast["in_stock_days"][15],
            "in_stock_days_30": forecast["in_stock_days"][30], "forecast_windows_used": forecast["windows"],
            "forecast_adjusted_for_stockout": forecast["adjusted"], "confirmed_stockout_days_30": forecast["stockout_days"],
            "trend_7_vs_30": forecast["trend_7_vs_30"], "trend": forecast["trend"],
            "days_cover": days_cover, "current_cover_days": days_cover,
            "days_available": days_cover, "expected_stockout_date":
                (today + timedelta(days=math.ceil(days_cover))).isoformat() if days_cover is not None else None,
            "lead_time_days": FORECAST_LEAD_TIME_DAYS, "inbound_before_arrival": 0,
            "inbound_included": False, "projected_stock_at_arrival": projected,
            "target_cover_days": FORECAST_TARGET_COVER_DAYS, "target_stock_after_arrival":
                daily * FORECAST_TARGET_COVER_DAYS if daily else 0,
            "recommended_replenishment": recommended, "replenishment": recommended,
            "stockout_before_arrival": bool(days_cover is not None and days_cover < FORECAST_LEAD_TIME_DAYS),
            "shortage_days": max(FORECAST_LEAD_TIME_DAYS - days_cover, 0) if days_cover is not None else None,
            "risk_code": risk_code, "risk_status": FORECAST_RISK_LABELS[risk_code],
            "ad_orders_30": ad_orders, "ad_order_share": ad_orders / group["sales_30"]
                if ad_orders is not None and group["sales_30"] else None,
            "fbp_present": channels[0]["present"], "fbp_reserved": channels[0]["reserved"],
            "fbp_effective_stock": channels[0]["effective_stock"], "replenishment_stock_source": "FBP",
        })
        group["observed_at"] = max((value["observed_at"] or "" for value in channels), default="") or None
        filters = ((sku, group["sku"]), (offer_id, " ".join(group["offer_members"])),
                   (product_name, f"{group['product_name_raw']} {group['display_name']}"))
        search_text = f"{group['sku']} {group['offer_id']} {group['product_name_raw']} {group['display_name']}".lower()
        if q.strip() and q.strip().lower() not in search_text:
            continue
        if any(value.strip().lower() not in target.lower() for value, target in filters if value.strip()):
            continue
        if risk == "attention" and risk_code not in {"out_of_stock", "urgent_replenishment", "replenish"}:
            continue
        if risk and risk != "attention" and risk_code != risk:
            continue
        cards.append(group)
    if sort_by:
        sort_values = {
            "fbp": lambda value: value["channels"][0]["present"],
            "realfbs": lambda value: value["channels"][1]["present"],
            "whd": lambda value: value["channels"][2]["present"],
            "forecast": lambda value: value["forecast_daily"],
            "replenishment": lambda value: value["replenishment"],
            "days_cover": lambda value: value["days_cover"],
            "risk": lambda value: -FORECAST_RISK_ORDER[value["risk_code"]],
        }
        cards.sort(key=lambda value: (
            sort_values[sort_by](value) is None,
            (sort_values[sort_by](value) or 0) * (1 if sort_order == "asc" else -1),
            value["shop_id"], value["sku"],
        ))
    else:
        cards.sort(key=lambda value: (FORECAST_RISK_ORDER[value["risk_code"]], value["shop_id"], value["sku"]))
    total = len(cards); start = (page - 1) * size
    through = max((item["observed_at"] for item in cards if item["observed_at"]), default=None)
    summary = {"active_skus": total,
               "fbp_present": sum(item["fbp_present"] for item in cards),
               "fbp_reserved": sum(item["fbp_reserved"] for item in cards),
               "need_replenishment_skus": sum(item["risk_code"] in {"out_of_stock", "urgent_replenishment", "replenish"} for item in cards),
               "replenishment_skus": sum(item["risk_code"] in {"out_of_stock", "urgent_replenishment", "replenish"} for item in cards),
               "stockout_before_arrival_skus": sum(item["stockout_before_arrival"] for item in cards),
               "shortage_skus": sum(item["stockout_before_arrival"] for item in cards),
               "expected_stockout_skus": sum(item["expected_stockout_date"] is not None for item in cards),
               "recommended_replenishment_total": sum(item["recommended_replenishment"] for item in cards),
               "effective_stock": sum(item["effective_stock"] for item in cards),
               "reserved_stock": sum(item["reserved_stock"] for item in cards),
               "forecast_channel": "FBP", "reference_channel": reference_channel,
               "replenishment_stock_source": "FBP", "inbound_included": False}
    return {"summary": summary, "items": cards[start:start + size],
            "total": total, "page": page, "size": size, "data_through": through,
            "sales_through": sales_through,
            "sales_window_end": sales_end.isoformat(), "inventory_business_date": today.isoformat(),
            "formula": "预测日销=FBP+realFBS销量的7/15/30日均销按50%/30%/20%加权；补货库存=FBP；补货=ceil(max(预测日销×60-到货时库存,0))；lead time=25天；未计入在途库存"}


@router.get("/api/inventory/forecast")
def inventory_forecast(shop_id: int = 0, page: int = 1, size: int = 50, q: str = "", channel: str = "",
                       risk: str = "", sort: str = "", sort_order: str = "desc"):
    return stock(shop_id=shop_id, page=page, size=size, q=q, channel=channel, risk=risk,
                 sort_by=sort, sort_order=sort_order)
