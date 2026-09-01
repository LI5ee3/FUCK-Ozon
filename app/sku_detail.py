import math
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from .actual_profit import _decimal_text, _profit_row
from .db import connect
from .inventory import get_stock
from .ozon.client import BEIJING
from .ozon.mappings import CANCEL_REASON_ZH
from .performance import AD_BASE_FIELDS, ad_add, ad_summary
from .products import load_product_rules, resolve_product
from .routers.common import ACTIVE, _overview_range, _utc_moment


CHANNELS = ("FBP", "realFBS", "WHD")
SIGNAL_AD_ORDER_SHARE_THRESHOLD = 0.5
SIGNAL_DRR_THRESHOLD = 30
SIGNAL_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "positive": 3}


class SkuDetailNotFound(ValueError):
    pass


def _period(date_from, date_to):
    today = datetime.now(BEIJING).date()
    if not date_from and not date_to:
        date_to = (today - timedelta(days=1)).isoformat()
        date_from = (today - timedelta(days=30)).isoformat()
    elif not date_from:
        try:
            date_from = (date.fromisoformat(str(date_to)) - timedelta(days=29)).isoformat()
        except (TypeError, ValueError):
            return _overview_range(date_from, date_to)
    elif not date_to:
        date_to = (today - timedelta(days=1)).isoformat()
    return _overview_range(date_from, date_to)


def _local_day(value):
    moment = _utc_moment(value)
    return moment.astimezone(BEIJING).date() if moment else None


def _money(value):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None
    return number if number.is_finite() else None


def _revenue(rows, settlement_currency):
    if not rows:
        return 0.0, settlement_currency, True
    amounts, currencies = [], set()
    for row in rows:
        amount, currency = _money(row["unit_price"]), str(row["price_currency"] or "").upper()
        if amount is None or not currency:
            return None, None, False
        amounts.append(amount * int(row["quantity"] or 0))
        currencies.add(currency)
    if len(currencies) != 1:
        return None, None, False
    try:
        total = sum(amounts, Decimal("0")).quantize(Decimal("0.01"))
    except (InvalidOperation, OverflowError):
        return None, None, False
    try:
        total_float = float(total)
    except (OverflowError, ValueError):
        return None, None, False
    return total_float if math.isfinite(total_float) else None, next(iter(currencies)), math.isfinite(total_float)


def _sales_metrics(rows, settlement_currency):
    revenue, currency, complete = _revenue(rows, settlement_currency)
    return {"orders": len({row["posting_number"] for row in rows}),
            "units": sum(int(row["quantity"] or 0) for row in rows),
            "revenue": revenue, "currency": currency,
            "revenue_complete": complete}


def _sales(rows, start, end, settlement_currency):
    by_day = {}
    for row in rows:
        day = _local_day(row["created_at"])
        if day is not None:
            by_day.setdefault(day, []).append(row)
    selected = [row for day, values in by_day.items() if start <= day <= end for row in values]
    summary = _sales_metrics(selected, settlement_currency)
    period_days = (end - start).days + 1
    summary.update({
        "avg_units_per_day": round(summary["units"] / period_days, 4) if period_days else None,
        "sales_7": sum(int(row["quantity"] or 0) for day, values in by_day.items()
                       if end - timedelta(days=6) <= day <= end for row in values),
        "sales_15": sum(int(row["quantity"] or 0) for day, values in by_day.items()
                        if end - timedelta(days=14) <= day <= end for row in values),
        "sales_30": sum(int(row["quantity"] or 0) for day, values in by_day.items()
                        if end - timedelta(days=29) <= day <= end for row in values),
        "period_days": period_days,
    })
    trend = []
    for offset in range(period_days):
        day = start + timedelta(days=offset)
        metrics = _sales_metrics(by_day.get(day, []), settlement_currency)
        trend.append({"date": day.isoformat(), **metrics})
    return {"status": "available" if selected else "empty", "summary": summary,
            "channels": [{"channel": channel, **_sales_metrics(
                [row for row in selected if row["channel"] == channel], settlement_currency)}
                          for channel in CHANNELS],
            "trend": trend, "data_through": max((row["created_at"] for row in selected), default=None)}


def _advertising(rows, start, end, sales_units):
    zero = {field: 0 for field in AD_BASE_FIELDS}
    total = dict(zero)
    by_day = {}
    campaigns = set()
    for row in rows:
        ad_add(total, row)
        by_day.setdefault(row["stat_date"], {})
        ad_add(by_day[row["stat_date"]], row)
        campaigns.add(str(row["campaign_id"]))
    summary = ad_summary(total)
    summary.update({"campaign_count": len(campaigns), "currency": "RUB"})
    trend = []
    for offset in range((end - start).days + 1):
        day = (start + timedelta(days=offset)).isoformat()
        metrics = ad_summary(by_day.get(day, zero))
        trend.append({"date": day, **metrics})
    share = summary["orders"] / sales_units if sales_units else None
    if share is not None and not math.isfinite(share):
        share = None
    return {"status": "available" if rows else "empty", "summary": summary,
            "trend": trend, "currency": "RUB", "ad_order_share": share,
            "data_through": max((row["stat_date"] for row in rows), default=None)}


def _channel(channel_rows, channel):
    row = next((value for value in channel_rows if value["channel"] == channel), None)
    if row is None:
        return {"channel": channel, "source": None, "present": None, "reserved": None,
                "effective_stock": None, "observed_at": None}
    return {key: row.get(key) for key in ("channel", "source", "present", "reserved",
                                           "effective_stock", "observed_at")}


def _inventory(item):
    if item is None:
        return {"status": "unavailable", "channels": [], "fbp_present": None,
                "fbp_reserved": None, "realfbs_present": None, "realfbs_reserved": None,
                "whd_present": None, "whd_reserved": None, "sales_7": None,
                "sales_15": None, "sales_30": None, "daily_7": None, "daily_15": None,
                "daily_30": None, "forecast_daily": None, "trend": None,
                "trend_7_vs_30": None, "days_cover": None, "expected_stockout_date": None,
                "lead_time_days": 25, "target_cover_days": 60,
                "recommended_replenishment": None, "risk_code": None, "risk_status": None,
                "data_through": None}
    channels = [_channel(item["channels"], channel) for channel in CHANNELS]
    values = {channel: channels[index] for index, channel in enumerate(CHANNELS)}
    return {"status": "available", "channels": channels,
            "fbp_present": values["FBP"]["present"], "fbp_reserved": values["FBP"]["reserved"],
            "realfbs_present": values["realFBS"]["present"], "realfbs_reserved": values["realFBS"]["reserved"],
            "whd_present": values["WHD"]["present"], "whd_reserved": values["WHD"]["reserved"],
            "sales_7": item["sales_7"], "sales_15": item["sales_15"], "sales_30": item["sales_30"],
            "daily_7": item["daily_7"], "daily_15": item["daily_15"],
            "daily_30": item["daily_30"], "forecast_daily": item["forecast_daily"],
            "trend": item["trend"], "trend_7_vs_30": item["trend_7_vs_30"],
            "days_cover": item["days_cover"], "expected_stockout_date": item["expected_stockout_date"],
            "lead_time_days": item["lead_time_days"], "target_cover_days": item["target_cover_days"],
            "recommended_replenishment": item["recommended_replenishment"],
            "risk_code": item["risk_code"], "risk_status": item["risk_status"],
            "projected_stock_at_arrival": item["projected_stock_at_arrival"],
            "inbound_included": item["inbound_included"], "data_through": item["observed_at"]}


def _return_key(source, posting_number, fallback):
    posting = str(posting_number or "").strip()
    return f"posting:{posting}" if posting else f"{source}:{fallback}"


def _cohort_return_postings(db, shop_id, sku, order_rows):
    postings = sorted({str(row["posting_number"]).strip() for row in order_rows
                       if str(row["posting_number"] or "").strip()})
    if not postings:
        return set()
    marks = ",".join("?" for _ in postings)
    args = (shop_id, sku, *postings, shop_id, sku, *postings)
    return {row["posting_number"] for row in db.execute(f"""
      SELECT trim(posting_number) posting_number
      FROM return_records
      WHERE shop_id=? AND sku=? AND NULLIF(trim(posting_number),'') IS NOT NULL
        AND trim(posting_number) IN ({marks})
      UNION
      SELECT trim(posting_number) posting_number
      FROM rfbs_return_records
      WHERE shop_id=? AND sku=? AND NULLIF(trim(posting_number),'') IS NOT NULL
        AND trim(posting_number) IN ({marks})
    """, args)}


def _after_sales(order_rows, period_return_rows, period_rfbs_rows,
                 cohort_return_postings, complaint_rows):
    orders = {str(row["posting_number"]).strip() for row in order_rows}
    cancelled = [row for row in order_rows if row["status_raw"] == "已取消" and row["shipped"] == 0]
    reasons = Counter(CANCEL_REASON_ZH.get(row["cancel_reason_raw"], row["cancel_reason_raw"] or "未提供")
                      for row in cancelled)
    return_keys = {_return_key("return", row["posting_number"], row["record_key"])
                   for row in period_return_rows}
    return_keys.update(_return_key("rfbs", row["posting_number"], row["return_number"])
                       for row in period_rfbs_rows)
    return_orders = {str(posting).strip() for posting in cohort_return_postings
                     if str(posting or "").strip()} & orders
    complaint_keys = {(row["complaint_number"], row["posting_number"]) for row in complaint_rows}
    complaint_orders = {row["posting_number"] for row in complaint_rows}
    order_count = len(orders)
    return {"status": "available" if order_rows or return_keys or complaint_keys else "empty",
            "orders": order_count, "cancelled_before_ship": len(cancelled),
            "cancel_rate": len(cancelled) / order_count if order_count else None,
            "returns": len(return_keys), "return_orders": len(return_orders),
            "return_rate": len(return_orders) / order_count if order_count else None,
            "complaints": len(complaint_keys), "complaint_orders": len(complaint_orders),
            "complaint_rate": len(complaint_orders) / order_count if order_count else None,
            "cancel_reasons": [{"reason": reason, "count": count}
                               for reason, count in sorted(reasons.items(), key=lambda pair: (-pair[1], pair[0]))],
            "completeness": {"return_records": "complete", "rfbs_return_records": "complete",
                             "complaints": "complete"}}


def _profit(db, shop_id, sku, orders):
    if not orders:
        return {"status": "unavailable", "candidate_orders": 0, "attributed_orders": 0,
                "unattributed_multi_sku_orders": 0, "incomplete_orders": 0,
                "actual_profit_cny": None, "avg_profit_per_unit_cny": None, "units": 0,
                "currency": "CNY", "incomplete_reasons": {}}
    marks = ",".join("(?,?)" for _ in orders)
    pair_args = [value for row in orders for value in (row["shop_id"], row["posting_number"])]
    item_rows = db.execute(f"""
      SELECT i.shop_id,i.posting_number,i.sku,i.offer_id AS order_offer_id,
        i.quantity AS order_quantity,
        e.shop_id AS erp_shop_id,e.offer_id AS erp_offer_id,e.quantity AS erp_quantity,
        e.total_cost,e.exchange_rate_original
      FROM order_items i
      LEFT JOIN erp_order_item_costs e
        ON e.shop_id=i.shop_id AND e.erp_order_number=i.posting_number AND e.ozon_sku=i.sku
      WHERE (i.shop_id,i.posting_number) IN ({marks})
      ORDER BY i.shop_id,i.posting_number,i.sku
    """, pair_args).fetchall()
    finance_rows = db.execute(f"""
      SELECT t.shop_id,t.posting_number,t.amount,t.currency
      FROM ozon_finance_transactions t
      WHERE NULLIF(trim(t.posting_number),'') IS NOT NULL
        AND (t.shop_id,t.posting_number) IN ({marks})
      ORDER BY t.shop_id,t.posting_number,t.operation_id
    """, pair_args).fetchall()
    items_by_order, finance_by_order = {}, {}
    for row in item_rows:
        items_by_order.setdefault((row["shop_id"], row["posting_number"]), []).append(row)
    for row in finance_rows:
        finance_by_order.setdefault((row["shop_id"], row["posting_number"]), []).append(row)

    total = Decimal("0")
    attributed_orders = attributed_units = multi_sku = incomplete = 0
    reasons = Counter()
    for order in orders:
        key = (order["shop_id"], order["posting_number"])
        rows = items_by_order.get(key, [])
        if not rows:
            incomplete += 1
            reasons["missing_order_items"] += 1
            continue
        if len({str(row["sku"] or "") for row in rows}) != 1 or str(rows[0]["sku"]) != sku:
            multi_sku += 1
            reasons["multi_sku_order"] += 1
            continue
        try:
            result = _profit_row(order, rows, finance_by_order.get(key, []))
        except ValueError:
            incomplete += 1
            reasons["invalid_profit_data"] += 1
            continue
        if result["actual_profit_cny"] is None:
            incomplete += 1
            reasons.update(result["incomplete_reasons"])
            continue
        attributed_orders += 1
        attributed_units += sum(int(row["order_quantity"] or 0) for row in rows)
        total += _money(result["actual_profit_cny"]) or Decimal("0")
    status = "complete" if not multi_sku and not incomplete else "incomplete"
    return {"status": status, "candidate_orders": len(orders), "attributed_orders": attributed_orders,
            "unattributed_multi_sku_orders": multi_sku, "incomplete_orders": incomplete,
            "actual_profit_cny": _decimal_text(total) if attributed_orders else None,
            "avg_profit_per_unit_cny": _decimal_text(total / attributed_units)
            if attributed_units else None, "units": attributed_units, "currency": "CNY",
            "incomplete_reasons": dict(sorted(reasons.items()))}


def _freshness(db, shop_id, sku, inventory, order_rows):
    orders = db.execute("""SELECT MAX(data_through) FROM sync_runs
      WHERE shop_id=? AND module='orders' AND status='success'""", (shop_id,)).fetchone()[0]
    if not orders:
        orders = max((row["created_at"] for row in order_rows), default=None)
    advertising = db.execute("SELECT MAX(stat_date) FROM ad_sku_daily WHERE shop_id=? AND sku=?",
                             (shop_id, sku)).fetchone()[0]
    finance = db.execute("""SELECT MAX(data_through) FROM sync_runs
      WHERE shop_id=? AND module='finance_transactions' AND status='success'""", (shop_id,)).fetchone()[0]
    if not finance:
        finance = db.execute("""SELECT MAX(t.operation_date) FROM ozon_finance_transactions t
          WHERE t.shop_id=? AND EXISTS(SELECT 1 FROM order_items i
            WHERE i.shop_id=t.shop_id AND i.posting_number=t.posting_number AND i.sku=?)""",
                             (shop_id, sku)).fetchone()[0]
    erp = db.execute("SELECT MAX(updated_at) FROM erp_order_item_costs WHERE shop_id=? AND ozon_sku=?",
                     (shop_id, sku)).fetchone()[0]
    return {"orders": orders, "inventory": inventory.get("data_through"),
            "advertising": advertising, "finance": finance, "erp_cost": erp}


def _signals(inventory, advertising, profit):
    signals = []
    risk = inventory.get("risk_code")
    if risk in {"out_of_stock", "urgent_replenishment", "replenish"}:
        days = inventory.get("days_cover")
        lead = inventory.get("lead_time_days")
        recommended = inventory.get("recommended_replenishment")
        if risk == "out_of_stock":
            message = f"当前 FBP 无可售库存，建议补货 {recommended or 0} 件。"
            severity = "critical"
            title = "FBP 已缺货"
        elif risk == "urgent_replenishment":
            display_days = f"{days:.1f}" if isinstance(days, (int, float)) and math.isfinite(days) else "暂无"
            message = f"当前 FBP 预计可售 {display_days} 天，不高于 {lead} 天采购交期，存在到货前缺货风险，建议补货 {recommended or 0} 件。"
            severity = "critical"
            title = "FBP 到货前缺货风险"
        else:
            display_days = f"{days:.1f}" if isinstance(days, (int, float)) and math.isfinite(days) else "暂无"
            target = inventory.get("target_cover_days")
            message = f"当前 FBP 预计可售 {display_days} 天，可覆盖采购交期，但尚未达到 {target} 天目标库存水平，建议补货 {recommended or 0} 件。"
            severity = "warning"
            title = "FBP 需要补货"
        signals.append({"code": f"inventory_{risk}", "severity": severity, "title": title,
                        "message": message, "metrics": {"days_cover": days,
                        "lead_time_days": lead, "recommended_replenishment": recommended}})
    elif risk == "overstock":
        days = inventory.get("days_cover")
        display_days = f"{days:.1f}" if isinstance(days, (int, float)) and math.isfinite(days) else "暂无"
        signals.append({"code": "inventory_overstock", "severity": "info", "title": "库存覆盖偏高",
                        "message": f"当前 FBP 预计可售 {display_days} 天，库存风险标记为库存偏高。",
                        "metrics": {"days_cover": days, "risk_code": risk}})
    elif risk == "no_recent_sales":
        signals.append({"code": "inventory_no_recent_sales", "severity": "info", "title": "近期无销量",
                        "message": "当前 SKU 没有可用于库存预测的近期销量，暂无法计算可靠的可售天数。",
                        "metrics": {"risk_code": risk, "forecast_daily": inventory.get("forecast_daily")}})
    trend = inventory.get("trend")
    if trend == "快速增长":
        signals.append({"code": "sales_growth", "severity": "positive", "title": "销量增长",
                        "message": "近 7 日销量相对 30 日趋势快速增长。",
                        "metrics": {"trend": trend, "trend_7_vs_30": inventory.get("trend_7_vs_30")}})
    elif trend == "下降":
        signals.append({"code": "sales_decline", "severity": "warning", "title": "销量下滑",
                        "message": "近 7 日销量相对 30 日趋势下降。",
                        "metrics": {"trend": trend, "trend_7_vs_30": inventory.get("trend_7_vs_30")}})
    share = advertising.get("ad_order_share")
    if share is not None and math.isfinite(share) and share >= SIGNAL_AD_ORDER_SHARE_THRESHOLD:
        signals.append({"code": "ad_dependency", "severity": "warning", "title": "广告依赖偏高",
                        "message": f"广告订单约占实际订单商品销量 {share * 100:.1f}%，建议关注自然流量依赖。",
                        "metrics": {"ad_order_share": share,
                                    "threshold": SIGNAL_AD_ORDER_SHARE_THRESHOLD}})
    drr = advertising.get("summary", {}).get("drr")
    if drr is not None and math.isfinite(drr) and drr >= SIGNAL_DRR_THRESHOLD:
        signals.append({"code": "ad_drr_high", "severity": "warning", "title": "广告 DRR 偏高",
                        "message": f"当前广告 DRR 为 {drr:.2f}%，高于 SKU 详情提示阈值。",
                        "metrics": {"drr": drr, "threshold": SIGNAL_DRR_THRESHOLD}})
    excluded = profit.get("unattributed_multi_sku_orders", 0) + profit.get("incomplete_orders", 0)
    if excluded:
        signals.append({"code": "profit_incomplete", "severity": "info", "title": "利润归因不完整",
                        "message": f"有 {excluded} 个订单未进入当前 SKU 的准确利润合计，请查看归因明细。",
                        "metrics": {"unattributed_multi_sku_orders": profit.get("unattributed_multi_sku_orders", 0),
                                    "incomplete_orders": profit.get("incomplete_orders", 0)}})
    signals.sort(key=lambda value: (SIGNAL_SEVERITY_ORDER[value["severity"]], value["code"]))
    return signals[:5]


def get_sku_detail(shop_id, sku, date_from=None, date_to=None):
    if type(shop_id) is not int or shop_id not in (1, 2):
        raise ValueError("请选择具体店铺")
    sku = str(sku or "").strip()
    if not sku:
        raise ValueError("SKU不能为空")
    start, end, utc_start, utc_end = _period(date_from, date_to)
    extended_start = min(start, end - timedelta(days=29))
    _, _, extended_utc_start, _ = _overview_range(extended_start.isoformat(), end.isoformat())
    with connect() as db:
        shop = db.execute("SELECT id,name,settlement_currency FROM shops WHERE id=?", (shop_id,)).fetchone()
        if shop is None:
            raise ValueError("未知店铺")
        rules = load_product_rules(db)
        metadata = {"offer_id": "", "product_name_raw": ""}
        for row in db.execute("""SELECT offer_id,product_name_raw FROM order_items
          WHERE shop_id=? AND sku=? ORDER BY (source='api') DESC,rowid DESC""", (shop_id, sku)):
            metadata["offer_id"] = metadata["offer_id"] or row["offer_id"] or ""
            metadata["product_name_raw"] = metadata["product_name_raw"] or row["product_name_raw"] or ""
        for row in db.execute("""SELECT offer_id,product_name FROM rfbs_return_records
          WHERE shop_id=? AND sku=? ORDER BY created_at DESC,return_id DESC""", (shop_id, sku)):
            metadata["offer_id"] = metadata["offer_id"] or row["offer_id"] or ""
            metadata["product_name_raw"] = metadata["product_name_raw"] or row["product_name"] or ""
        for row in db.execute("""SELECT offer_id,'' product_name_raw FROM erp_order_item_costs
          WHERE shop_id=? AND ozon_sku=? ORDER BY updated_at DESC""", (shop_id, sku)):
            metadata["offer_id"] = metadata["offer_id"] or row["offer_id"] or ""
        source_exists = db.execute("""SELECT EXISTS(
          SELECT 1 FROM order_items WHERE shop_id=? AND sku=?
          UNION ALL SELECT 1 FROM ad_sku_daily WHERE shop_id=? AND sku=?
          UNION ALL SELECT 1 FROM stock_history WHERE shop_id=? AND sku=?
          UNION ALL SELECT 1 FROM return_records WHERE shop_id=? AND sku=?
          UNION ALL SELECT 1 FROM rfbs_return_records WHERE shop_id=? AND sku=?
          UNION ALL SELECT 1 FROM erp_order_item_costs WHERE shop_id=? AND ozon_sku=?)""",
            (shop_id, sku) * 6).fetchone()[0]
        order_rows = [dict(row) for row in db.execute("""
          SELECT o.shop_id,s.name shop_name,s.settlement_currency,o.posting_number,o.channel,
            o.created_at,o.status_raw,o.shipped,o.cancel_reason_raw
          FROM orders o JOIN shops s ON s.id=o.shop_id
          WHERE o.shop_id=? AND o.created_at>=? AND o.created_at<?
            AND EXISTS(SELECT 1 FROM order_items x
              WHERE x.shop_id=o.shop_id AND x.posting_number=o.posting_number AND x.sku=?)
        """, (shop_id, utc_start, utc_end, sku))]
        sales_rows = [dict(row) for row in db.execute(f"""
          SELECT o.posting_number,o.channel,o.created_at,i.quantity,i.unit_price,i.price_currency
          FROM order_items i JOIN orders o USING(shop_id,posting_number)
          WHERE i.shop_id=? AND i.sku=? AND o.created_at>=? AND o.created_at<?
            AND {ACTIVE}
        """, (shop_id, sku, extended_utc_start, utc_end))]
        ad_rows = [dict(row) for row in db.execute("""
          SELECT stat_date,campaign_id,impressions,clicks,cart_adds,spend_rub,orders,revenue_rub
          FROM ad_sku_daily WHERE shop_id=? AND sku=? AND stat_date BETWEEN ? AND ?
          ORDER BY stat_date,campaign_id
        """, (shop_id, sku, start.isoformat(), end.isoformat()))]
        return_rows = [dict(row) for row in db.execute("""
          SELECT record_key,posting_number FROM return_records
          WHERE shop_id=? AND sku=? AND occurred_at>=? AND occurred_at<?
        """, (shop_id, sku, utc_start, utc_end))]
        rfbs_rows = [dict(row) for row in db.execute("""
          SELECT return_number,posting_number FROM rfbs_return_records
          WHERE shop_id=? AND sku=? AND created_at>=? AND created_at<?
        """, (shop_id, sku, utc_start, utc_end))]
        cohort_return_postings = _cohort_return_postings(db, shop_id, sku, order_rows)
        complaint_rows = [dict(row) for row in db.execute("""
          SELECT c.complaint_number,c.posting_number
          FROM complaints c JOIN order_items i
            ON i.shop_id=c.shop_id AND i.posting_number=c.posting_number AND i.sku=?
          JOIN orders o ON o.shop_id=c.shop_id AND o.posting_number=c.posting_number
          WHERE c.shop_id=? AND o.created_at>=? AND o.created_at<?
        """, (sku, shop_id, utc_start, utc_end))]
        profit = _profit(db, shop_id, sku, order_rows)
    stock_response = get_stock(shop_id=shop_id, page=1, size=100, sku=sku, _rules=rules)
    inventory_item = next((row for row in stock_response["items"] if row["sku"] == sku), None)
    if not source_exists and inventory_item is None:
        raise SkuDetailNotFound("未找到该店铺 SKU")
    inventory = _inventory(inventory_item)
    resolved = resolve_product(rules, sku, metadata["offer_id"], metadata["product_name_raw"])
    identity = {"shop_id": shop_id, "shop_name": shop["name"], "sku": sku,
                "offer_id": metadata["offer_id"] or (inventory_item or {}).get("offer_id")
                or resolved["primary_offer_id"] or "",
                "display_name": resolved["display_name"],
                "product_name_raw": metadata["product_name_raw"] or resolved["platform_name"],
                "group_id": resolved["group_id"], "primary_offer_id": resolved["primary_offer_id"]}
    sales = _sales(sales_rows, start, end, shop["settlement_currency"])
    advertising = _advertising(ad_rows, start, end, sales["summary"]["units"])
    after_sales = _after_sales(order_rows, return_rows, rfbs_rows,
                               cohort_return_postings, complaint_rows)
    with connect() as db:
        freshness = _freshness(db, shop_id, sku, inventory, order_rows)
    signals = _signals(inventory, advertising, profit)
    return {"identity": identity, "period": {"from": start.isoformat(), "to": end.isoformat()},
            "sales": sales, "inventory": inventory, "advertising": advertising,
            "after_sales": after_sales, "profit": profit, "signals": signals,
            "freshness": freshness}
