import threading
from datetime import timedelta

from ..db import connect
from ..dingtalk import configured as dingtalk_configured, send_text
from ..products import load_product_rules, resolve_product
from .config import RULE_KEYS, RULE_LABELS, RULE_SEVERITIES, _number, get_alert_rules
from .freshness import BEIJING, MOSCOW, _fresh_ad_data, _fresh_inventory, _fresh_orders, _now_utc
from .store import _mark_notification_failed, _mark_notification_sent, _record_rule_state


_alert_lock = threading.Lock()


def _fmt(value, digits=2):
    value = _number(value)
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _shop_name(db, shop_id):
    row = db.execute("SELECT name FROM shops WHERE id=?", (shop_id,)).fetchone()
    return row[0] if row else f"店铺{shop_id}"


def _campaign_names(db, shop_id):
    return {str(row["campaign_id"]): row["name"] or str(row["campaign_id"])
            for row in db.execute("SELECT campaign_id,name FROM ad_campaigns WHERE shop_id=?", (shop_id,))}


def _event(rule_key, shop_id, entity_type, entity_id, metrics, message):
    return {"shop_id": shop_id, "rule_key": rule_key, "entity_type": entity_type,
            "entity_id": str(entity_id), "severity": RULE_SEVERITIES[rule_key],
            "title": RULE_LABELS[rule_key], "message": message, "metrics": metrics}


def _campaign_daily(db, shop_id, start, end):
    return db.execute("""SELECT campaign_id,stat_date,spend_rub,revenue_rub,clicks,orders
      FROM ad_campaign_daily WHERE shop_id=? AND stat_date BETWEEN ? AND ?""",
                     (shop_id, start.isoformat(), end.isoformat())).fetchall()


def _valid(value):
    return _number(value) is not None


def _ad_spend_spike(db, shop_id, config, now):
    target = _now_utc(now).astimezone(MOSCOW).date() - timedelta(days=1)
    fresh, reason = _fresh_ad_data(db, shop_id, "ad_campaign_daily", ("ad_campaign_daily", "ad_statistics"), target)
    if not fresh:
        return [], reason, set()
    days = int(config["baseline_days"])
    rows = _campaign_daily(db, shop_id, target - timedelta(days=days), target)
    groups = {}
    for row in rows:
        if _valid(row["spend_rub"]):
            groups.setdefault(str(row["campaign_id"]), {})[row["stat_date"]] = _number(row["spend_rub"])
    names = _campaign_names(db, shop_id)
    result = []
    resolvable_ids = set()
    for campaign_id, values in groups.items():
        current = values.get(target.isoformat())
        baseline = [values.get((target - timedelta(days=offset)).isoformat()) for offset in range(1, days + 1)]
        baseline = [value for value in baseline if value is not None]
        if current is None or len(baseline) < config["minimum_baseline_days"]:
            continue
        resolvable_ids.add(campaign_id)
        average = sum(baseline) / len(baseline)
        if average <= 0 or current < config["minimum_current_spend_rub"] \
                or current < average * (1 + config["increase_percent"] / 100):
            continue
        name = names.get(campaign_id, campaign_id)
        metrics = {"campaign_name": name, "target_date": target.isoformat(), "current_spend_rub": current,
                   "baseline_spend_rub": average, "baseline_days": len(baseline),
                   "increase_percent": (current / average - 1) * 100}
        result.append(_event("ad_spend_spike", shop_id, "campaign", campaign_id, metrics,
                             f"【oPanel 异常预警】\n店铺：{_shop_name(db, shop_id)}\n类型：广告花费突增\n"
                             f"Campaign：{name}\n当前花费：{_fmt(current)} RUB\n过去{len(baseline)}日均值：{_fmt(average)} RUB\n"
                             f"增幅：{_fmt(metrics['increase_percent'], 1)}%\n数据日期：{target.isoformat()}"))
    return result, "", resolvable_ids


def _ad_drr_high(db, shop_id, config, now):
    target = _now_utc(now).astimezone(MOSCOW).date() - timedelta(days=1)
    fresh, reason = _fresh_ad_data(db, shop_id, "ad_campaign_daily", ("ad_campaign_daily", "ad_statistics"), target)
    if not fresh:
        return [], reason, set()
    window = int(config["window_days"])
    start = target - timedelta(days=window - 1)
    rows = _campaign_daily(db, shop_id, start, target)
    groups = {}
    for row in rows:
        if _valid(row["spend_rub"]) and _valid(row["revenue_rub"]):
            value = groups.setdefault(str(row["campaign_id"]), {"dates": set(), "spend": 0, "revenue": 0})
            value["dates"].add(row["stat_date"]); value["spend"] += _number(row["spend_rub"]); value["revenue"] += _number(row["revenue_rub"])
    names = _campaign_names(db, shop_id)
    result = []
    for campaign_id, value in groups.items():
        if len(value["dates"]) < window or value["spend"] < config["minimum_spend_rub"] or value["revenue"] <= 0:
            continue
        drr = value["spend"] / value["revenue"] * 100
        if drr <= config["threshold_drr"]:
            continue
        name = names.get(campaign_id, campaign_id)
        metrics = {"campaign_name": name, "start_date": start.isoformat(), "target_date": target.isoformat(),
                   "window_days": window, "spend_window_rub": value["spend"],
                   "revenue_window_rub": value["revenue"], "spend_3d": value["spend"],
                   "revenue_3d": value["revenue"], "drr": drr,
                   "threshold_drr": config["threshold_drr"]}
        result.append(_event("ad_drr_high", shop_id, "campaign", campaign_id, metrics,
                             f"【oPanel 异常预警】\n店铺：{_shop_name(db, shop_id)}\n类型：广告成本率过高\n"
                             f"Campaign：{name}\n近{window}日花费：{_fmt(value['spend'])} RUB\n近{window}日广告销售：{_fmt(value['revenue'])} RUB\n"
                             f"DRR：{_fmt(drr, 1)}%（阈值 {config['threshold_drr']}%）\n数据日期：{target.isoformat()}"))
    return result, "", {campaign_id for campaign_id, value in groups.items()
                         if len(value["dates"]) >= window}


def _ad_clicks_no_orders(db, shop_id, config, now):
    target = _now_utc(now).astimezone(MOSCOW).date() - timedelta(days=1)
    fresh, reason = _fresh_ad_data(db, shop_id, "ad_sku_daily", ("ad_sku_daily", "ad_statistics"), target)
    if not fresh:
        return [], reason, set()
    window = int(config["window_days"])
    start = target - timedelta(days=window - 1)
    rows = db.execute("""SELECT campaign_id,sku,product_name,stat_date,clicks,spend_rub,orders
      FROM ad_sku_daily WHERE shop_id=? AND stat_date BETWEEN ? AND ?""",
                     (shop_id, start.isoformat(), target.isoformat())).fetchall()
    groups = {}
    for row in rows:
        if not all(_valid(row[key]) for key in ("clicks", "spend_rub", "orders")):
            continue
        key = (str(row["campaign_id"]), str(row["sku"]))
        value = groups.setdefault(key, {"dates": set(), "clicks": 0, "spend": 0, "orders": 0,
                                        "product_name": row["product_name"] or ""})
        value["dates"].add(row["stat_date"]); value["clicks"] += _number(row["clicks"])
        value["spend"] += _number(row["spend_rub"]); value["orders"] += _number(row["orders"])
    names = _campaign_names(db, shop_id)
    product_rules = load_product_rules(db)
    result = []
    for (campaign_id, sku), value in groups.items():
        if len(value["dates"]) < window or value["clicks"] < config["minimum_clicks"] \
                or value["spend"] < config["minimum_spend_rub"] or value["orders"] != 0:
            continue
        campaign_name = names.get(campaign_id, campaign_id)
        product_name = value["product_name"] or resolve_product(product_rules, sku, "", "")["display_name"] or sku
        entity_id = f"{campaign_id}:{sku}"
        metrics = {"campaign_name": campaign_name, "product_name": product_name, "sku": sku,
                   "start_date": start.isoformat(), "target_date": target.isoformat(),
                   "clicks": value["clicks"], "spend_rub": value["spend"], "orders": 0,
                   "minimum_clicks": config["minimum_clicks"], "minimum_spend_rub": config["minimum_spend_rub"]}
        result.append(_event("ad_clicks_no_orders", shop_id, "sku_campaign", entity_id, metrics,
                             f"【oPanel 异常预警】\n店铺：{_shop_name(db, shop_id)}\n类型：大量点击无订单\n"
                             f"Campaign：{campaign_name}\nSKU：{sku}\n近{window}日点击：{_fmt(value['clicks'], 0)}\n"
                             f"近{window}日花费：{_fmt(value['spend'])} RUB\n订单：0\n数据日期：{target.isoformat()}"))
    return result, "", {f"{campaign_id}:{sku}" for (campaign_id, sku), value in groups.items()
                         if len(value["dates"]) >= window}


def _ad_orders_drop(db, shop_id, config, now):
    target = _now_utc(now).astimezone(MOSCOW).date() - timedelta(days=1)
    fresh, reason = _fresh_ad_data(db, shop_id, "ad_campaign_daily", ("ad_campaign_daily", "ad_statistics"), target)
    if not fresh:
        return [], reason, set()
    days = int(config["baseline_days"])
    rows = _campaign_daily(db, shop_id, target - timedelta(days=days), target)
    groups = {}
    for row in rows:
        if not all(_valid(row[key]) for key in ("orders", "spend_rub")):
            continue
        value = groups.setdefault(str(row["campaign_id"]), {})
        value[row["stat_date"]] = (_number(row["orders"]), _number(row["spend_rub"]))
    names = _campaign_names(db, shop_id)
    result = []
    resolvable_ids = set()
    for campaign_id, values in groups.items():
        current = values.get(target.isoformat())
        baseline = [values.get((target - timedelta(days=offset)).isoformat()) for offset in range(1, days + 1)]
        baseline = [value for value in baseline if value is not None]
        if current is None or len(baseline) < config["minimum_baseline_days"]:
            continue
        resolvable_ids.add(campaign_id)
        baseline_orders = sum(value[0] for value in baseline) / len(baseline)
        baseline_spend = sum(value[1] for value in baseline) / len(baseline)
        if baseline_orders < config["minimum_baseline_orders_per_day"] or current[0] > baseline_orders * (1 - config["drop_percent"] / 100):
            continue
        if baseline_spend > 0 and current[1] < baseline_spend * config["minimum_spend_ratio"]:
            continue
        name = names.get(campaign_id, campaign_id)
        drop = (1 - current[0] / baseline_orders) * 100
        metrics = {"campaign_name": name, "target_date": target.isoformat(), "current_orders": current[0],
                   "baseline_orders_per_day": baseline_orders, "current_spend_rub": current[1],
                   "baseline_spend_rub": baseline_spend, "drop_percent": drop}
        result.append(_event("ad_orders_drop", shop_id, "campaign", campaign_id, metrics,
                             f"【oPanel 异常预警】\n店铺：{_shop_name(db, shop_id)}\n类型：广告订单下降\n"
                             f"Campaign：{name}\n当日订单：{_fmt(current[0], 0)}\n前{len(baseline)}日均订单：{_fmt(baseline_orders)}\n"
                             f"下降：{_fmt(drop, 1)}%\n当日花费：{_fmt(current[1])} RUB\n数据日期：{target.isoformat()}"))
    return result, "", resolvable_ids


def _inventory_risk(db, shop_id, config, now):
    fresh, reason = _fresh_inventory(db, shop_id, now)
    if not fresh:
        return [], reason, set()
    try:
        from ..routers.inventory import stock
        rows, page, size = [], 1, 100
        # ponytail: page through the existing forecast endpoint; extract its SQL only if this becomes measurable.
        while True:
            result = stock(shop_id=shop_id, channel="FBP", page=page, size=size)
            rows.extend(result.get("items") or [])
            if page * size >= int(result.get("total") or 0):
                break
            page += 1
    except Exception:
        return [], "库存预测读取失败", set()
    result = []
    for row in rows:
        risk = row.get("risk_code")
        if risk not in {"out_of_stock", "urgent_replenishment"}:
            continue
        sku = str(row.get("sku") or "")
        severity = "critical" if risk == "out_of_stock" else "high"
        metrics = {"sku": sku, "product_name": row.get("display_name") or sku,
                   "effective_stock": row.get("effective_stock"), "forecast_daily": row.get("forecast_daily"),
                   "days_cover": row.get("days_cover"), "expected_stockout_date": row.get("expected_stockout_date"),
                   "recommended_replenishment": row.get("recommended_replenishment"),
                   "stockout_before_arrival": bool(row.get("stockout_before_arrival"))}
        shop = row.get("shop_name") or f"店铺{shop_id}"
        lines = ["【oPanel FBP库存预警】", f"店铺：{shop}", f"商品：{metrics['product_name']}", f"SKU：{sku}",
                 f"FBP有效库存：{_fmt(metrics['effective_stock'], 0)}", f"预测日销（FBP+realFBS需求）：{_fmt(metrics['forecast_daily'])}",
                 f"FBP预计可售：{_fmt(metrics['days_cover'])} 天", f"FBP预计缺货：{metrics['expected_stockout_date'] or '—'}",
                 f"FBP建议补货：{_fmt(metrics['recommended_replenishment'], 0)}",
                 f"当前库存无法覆盖{row['lead_time_days']}天补货交期。" if risk == "urgent_replenishment" else "当前已缺货。"]
        item = _event("inventory_risk", shop_id, "sku", sku, metrics, "\n".join(lines))
        item["severity"] = severity
        result.append(item)
    return result, "", {str(row.get("sku") or "") for row in rows if row.get("sku")}


def _sales_drop(db, shop_id, config, now):
    target = _now_utc(now).astimezone(BEIJING).date() - timedelta(days=1)
    days = int(config["baseline_days"])
    start = target - timedelta(days=days)
    fresh, reason = _fresh_orders(db, shop_id, target, start)
    if not fresh:
        return [], reason, set()
    rows = db.execute("""SELECT date(datetime(o.created_at),'+8 hours') stat_date,
      SUM(i.quantity) units FROM orders o JOIN order_items i USING(shop_id,posting_number)
      WHERE o.shop_id=? AND o.channel IN ('FBP','realFBS')
        AND NOT (o.status_raw='已取消' AND o.shipped=0)
        AND o.created_at>=? AND o.created_at<? GROUP BY stat_date""",
                     (shop_id, f"{start.isoformat()}T00:00:00+08:00",
                      f"{(target + timedelta(days=1)).isoformat()}T00:00:00+08:00")).fetchall()
    by_date = {row["stat_date"]: _number(row["units"]) or 0 for row in rows}
    baseline = [by_date.get((target - timedelta(days=offset)).isoformat(), 0) for offset in range(1, days + 1)]
    baseline_days = len(baseline)
    baseline_units = sum(baseline) / baseline_days if baseline_days else 0
    current = by_date.get(target.isoformat(), 0)
    if baseline_days < config["minimum_baseline_days"] or baseline_units < config["minimum_baseline_units_per_day"] \
            or current > baseline_units * (1 - config["drop_percent"] / 100):
        return [], "", {f"shop:{shop_id}"}
    metrics = {"target_date": target.isoformat(), "current_units": current, "baseline_units_per_day": baseline_units,
               "baseline_days": baseline_days, "drop_percent": (1 - current / baseline_units) * 100}
    return [_event("sales_drop", shop_id, "shop", f"shop:{shop_id}", metrics,
                   f"【oPanel 异常预警】\n店铺：{_shop_name(db, shop_id)}\n类型：核心渠道销量下降\n"
                   f"昨日销量：{_fmt(current, 0)} 件\n前{baseline_days}日均销量：{_fmt(baseline_units)} 件\n"
                   f"下降：{_fmt(metrics['drop_percent'], 1)}%\n统计口径：FBP + realFBS，不包含WHD\n"
                   f"数据日期：{target.isoformat()}")], "", {f"shop:{shop_id}"}


DETECTORS = {
    "ad_spend_spike": _ad_spend_spike,
    "ad_drr_high": _ad_drr_high,
    "ad_clicks_no_orders": _ad_clicks_no_orders,
    "ad_orders_drop": _ad_orders_drop,
    "inventory_risk": _inventory_risk,
    "sales_drop": _sales_drop,
}


def evaluate_alerts(shop_id=0, rule_keys=None, now=None):
    if shop_id not in (0, 1, 2):
        raise ValueError("未知店铺")
    selected_shops = (1, 2) if shop_id == 0 else (shop_id,)
    selected_rules = tuple(rule_keys or RULE_KEYS)
    if any(rule not in RULE_KEYS for rule in selected_rules):
        raise ValueError("未知预警规则")
    now = _now_utc(now)
    summary = {"evaluated": 0, "triggered": 0, "updated": 0, "resolved": 0,
               "notifications_sent": 0, "notifications_failed": 0, "skipped": []}
    with _alert_lock:
        for current_shop in selected_shops:
            rules = {row["rule_key"]: row for row in get_alert_rules(current_shop)}
            for rule_key in selected_rules:
                rule = rules[rule_key]
                if not rule["enabled"]:
                    summary["skipped"].append({"shop_id": current_shop, "rule_key": rule_key, "reason": "规则已停用"})
                    continue
                try:
                    with connect() as db:
                        items, reason, resolvable_ids = DETECTORS[rule_key](
                            db, current_shop, rule["config"], now)
                except Exception:
                    items, reason, resolvable_ids = [], "规则检查失败", set()
                if reason:
                    summary["skipped"].append({"shop_id": current_shop, "rule_key": rule_key, "reason": reason})
                    continue
                summary["evaluated"] += 1
                counts, pending = _record_rule_state(current_shop, rule_key, items, now, resolvable_ids)
                for key in ("triggered", "updated", "resolved"):
                    summary[key] += counts[key]
                if rule["notify_dingtalk"] and pending and dingtalk_configured():
                    for event_id, message in pending:
                        try:
                            send_text(message)
                        except Exception:
                            _mark_notification_failed(event_id)
                            summary["notifications_failed"] += 1
                        else:
                            _mark_notification_sent(event_id, now)
                            summary["notifications_sent"] += 1
    return summary
