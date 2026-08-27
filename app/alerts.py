import json
import math
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import DEFAULT_ALERT_RULE_CONFIGS, connect, transaction
from .dingtalk import configured as dingtalk_configured, send_text
from .products import load_product_rules, resolve_product

MOSCOW = ZoneInfo("Europe/Moscow")
BEIJING = ZoneInfo("Asia/Shanghai")
RULE_KEYS = tuple(DEFAULT_ALERT_RULE_CONFIGS)
RULE_LABELS = {
    "ad_spend_spike": "广告花费突增",
    "ad_drr_high": "广告成本率过高",
    "ad_clicks_no_orders": "大量点击无订单",
    "ad_orders_drop": "广告订单下降",
    "inventory_risk": "FBP库存风险",
    "sales_drop": "核心渠道销量下降",
}
RULE_CATEGORIES = {
    "ad_spend_spike": "advertising", "ad_drr_high": "advertising",
    "ad_clicks_no_orders": "advertising", "ad_orders_drop": "advertising",
    "inventory_risk": "inventory", "sales_drop": "sales",
}
RULE_SEVERITIES = {
    "ad_spend_spike": "warning", "ad_drr_high": "warning",
    "ad_clicks_no_orders": "high", "ad_orders_drop": "warning",
    "inventory_risk": "high", "sales_drop": "high",
}
INTEGER_CONFIG_KEYS = {
    "baseline_days", "minimum_baseline_days", "window_days", "minimum_clicks",
}
PERCENT_CONFIG_KEYS = {"increase_percent", "threshold_drr", "drop_percent"}
NON_NEGATIVE_CONFIG_KEYS = {
    "minimum_current_spend_rub", "minimum_spend_rub", "minimum_baseline_orders_per_day",
    "minimum_baseline_units_per_day",
}
_alert_lock = threading.Lock()


def _now_utc(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_text(value):
    return _now_utc(value).isoformat().replace("+00:00", "Z")


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _date_value(value, zone):
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        return value
    else:
        text = str(value or "")
        if not text:
            return None
        if len(text) >= 10 and text[4] == "-" and text[7] == "-" and "T" not in text and " " not in text:
            try:
                return date.fromisoformat(text[:10])
            except ValueError:
                return None
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone).date()


def _moment_value(value):
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
    return _now_utc(moment)


def _fmt(value, digits=2):
    value = _number(value)
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def validate_rule_config(rule_key, config, base=None):
    if rule_key not in DEFAULT_ALERT_RULE_CONFIGS:
        raise ValueError("未知预警规则")
    if not isinstance(config, dict):
        raise ValueError("规则配置必须是对象")
    unknown = set(config) - set(DEFAULT_ALERT_RULE_CONFIGS[rule_key])
    if unknown:
        raise ValueError("规则配置包含未知字段")
    merged = dict(base if base is not None else DEFAULT_ALERT_RULE_CONFIGS[rule_key])
    merged.update(config)
    for key, value in merged.items():
        if isinstance(value, bool) or _number(value) is None:
            raise ValueError("规则配置必须是有限数字")
        number = _number(value)
        if key in INTEGER_CONFIG_KEYS:
            if number != int(number):
                raise ValueError("天数和数量阈值必须是整数")
            if key == "window_days" and not 1 <= number <= 30:
                raise ValueError("统计周期必须为 1 至 30 天")
            if key == "baseline_days" and not 3 <= number <= 30:
                raise ValueError("基准周期必须为 3 至 30 天")
            if key == "minimum_baseline_days" and not 3 <= number <= 30:
                raise ValueError("最少基准天数必须为 3 至 30 天")
            if key == "minimum_clicks" and not 1 <= number <= 100000:
                raise ValueError("最低点击数必须为 1 至 100000")
            merged[key] = int(number)
        elif key in PERCENT_CONFIG_KEYS:
            if not 0 <= number <= 1000 or (key == "threshold_drr" and number <= 0):
                raise ValueError("百分比阈值超出有效范围")
            merged[key] = number
        elif key in NON_NEGATIVE_CONFIG_KEYS:
            if number < 0 or number > 1000000000:
                raise ValueError("金额或销量阈值无效")
            merged[key] = number
        elif key == "minimum_spend_ratio":
            if not 0 <= number <= 2:
                raise ValueError("花费比例必须为 0 至 2")
            merged[key] = number
    if "minimum_baseline_days" in merged and "baseline_days" in merged \
            and merged["minimum_baseline_days"] > merged["baseline_days"]:
        raise ValueError("最少基准天数不能超过基准周期")
    json.dumps(merged, ensure_ascii=False, allow_nan=False)
    return merged


def _rule_row(row):
    try:
        config = json.loads(row["config_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        config = {}
    config = validate_rule_config(row["rule_key"], config)
    return {"shop_id": row["shop_id"], "rule_key": row["rule_key"],
            "enabled": bool(row["enabled"]), "notify_dingtalk": bool(row["notify_dingtalk"]),
            "config": config, "updated_at": row["updated_at"],
            "label": RULE_LABELS[row["rule_key"]], "category": RULE_CATEGORIES[row["rule_key"]]}


def get_alert_rules(shop_id=0):
    if shop_id not in (0, 1, 2):
        raise ValueError("未知店铺")
    with connect() as db:
        shops = (1, 2) if shop_id == 0 else (shop_id,)
        rows = db.execute("SELECT * FROM alert_rules WHERE shop_id IN (1,2) ORDER BY shop_id,rowid").fetchall()
    by_key = {(row["shop_id"], row["rule_key"]): _rule_row(row) for row in rows}
    result = []
    for current_shop in shops:
        for rule_key in RULE_KEYS:
            value = by_key.get((current_shop, rule_key))
            if value is None:
                value = {"shop_id": current_shop, "rule_key": rule_key, "enabled": True,
                         "notify_dingtalk": True, "config": dict(DEFAULT_ALERT_RULE_CONFIGS[rule_key]),
                         "updated_at": None, "label": RULE_LABELS[rule_key],
                         "category": RULE_CATEGORIES[rule_key]}
            result.append(value)
    return result


def update_alert_rule(rule_key, body):
    if rule_key not in DEFAULT_ALERT_RULE_CONFIGS:
        raise ValueError("未知预警规则")
    if not isinstance(body, dict):
        raise ValueError("请求内容无效")
    if set(body) - {"shop_id", "enabled", "notify_dingtalk", "config"}:
        raise ValueError("请求包含未知字段")
    try:
        shop_id = int(body["shop_id"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("shop_id无效") from error
    if shop_id not in (1, 2):
        raise ValueError("未知店铺")
    if not isinstance(body.get("enabled"), bool) or not isinstance(body.get("notify_dingtalk"), bool):
        raise ValueError("enabled和notify_dingtalk必须是布尔值")
    with connect() as db:
        current = db.execute("SELECT * FROM alert_rules WHERE shop_id=? AND rule_key=?", (shop_id, rule_key)).fetchone()
    base = _rule_row(current)["config"] if current else DEFAULT_ALERT_RULE_CONFIGS[rule_key]
    config = validate_rule_config(rule_key, body.get("config"), base)
    with transaction() as db:
        db.execute("""INSERT INTO alert_rules(shop_id,rule_key,enabled,notify_dingtalk,config_json,updated_at)
          VALUES(?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%SZ','now'))
          ON CONFLICT(shop_id,rule_key) DO UPDATE SET enabled=excluded.enabled,
          notify_dingtalk=excluded.notify_dingtalk,config_json=excluded.config_json,updated_at=excluded.updated_at""",
                   (shop_id, rule_key, int(body["enabled"]), int(body["notify_dingtalk"]),
                    json.dumps(config, ensure_ascii=False, allow_nan=False)))
    return next(row for row in get_alert_rules(shop_id) if row["rule_key"] == rule_key)


def _run_coverage(db, shop_id, modules, zone):
    marks = ",".join("?" for _ in modules)
    rows = db.execute(f"""SELECT data_through,range_to FROM sync_runs
      WHERE shop_id=? AND status='success' AND module IN ({marks})""", (shop_id, *modules)).fetchall()
    values = [_date_value(row["data_through"] or row["range_to"], zone) for row in rows]
    return max((value for value in values if value), default=None)


def _has_sync_coverage(db, shop_id, modules, start, end, zone):
    marks = ",".join("?" for _ in modules)
    rows = db.execute(f"""SELECT range_from,range_to,data_through FROM sync_runs
      WHERE shop_id=? AND status='success' AND module IN ({marks})""", (shop_id, *modules)).fetchall()
    intervals = []
    for row in rows:
        range_start = _date_value(row["range_from"], zone)
        range_end = _date_value(row["range_to"] or row["data_through"], zone)
        if range_start and range_end and range_start <= range_end:
            intervals.append((range_start, range_end))
    covered = start
    for range_start, range_end in sorted(intervals):
        if range_end < covered:
            continue
        if range_start > covered:
            break
        covered = range_end + timedelta(days=1)
        if covered > end:
            return True
    return False


def _fresh_ad_data(db, shop_id, table, modules, target):
    latest = db.execute(f"SELECT MAX(stat_date) FROM {table} WHERE shop_id=?", (shop_id,)).fetchone()[0]
    if not latest:
        return False, "暂无广告数据"
    target_rows = db.execute(f"SELECT COUNT(*) FROM {table} WHERE shop_id=? AND stat_date=?",
                             (shop_id, target.isoformat())).fetchone()[0]
    if not target_rows:
        return False, f"目标广告数据缺失，无法判断 {target.isoformat()}"
    coverage = _run_coverage(db, shop_id, modules, MOSCOW)
    if not coverage:
        return False, "广告统计尚未有成功同步记录"
    if str(latest) < target.isoformat() or coverage < target:
        return False, f"最新广告数据为 {latest}，无法判断 {target.isoformat()}"
    return True, ""


def _fresh_orders(db, shop_id, target, baseline_start=None):
    coverage = _run_coverage(db, shop_id, ("orders",), BEIJING)
    if not coverage or coverage < target:
        return False, "订单同步尚未覆盖昨日"
    if baseline_start and not _has_sync_coverage(db, shop_id, ("orders",), baseline_start, target, BEIJING):
        return False, "订单同步尚未覆盖销量基准周期"
    return True, ""


def _fresh_inventory(db, shop_id, now):
    latest = db.execute("SELECT MAX(observed_at) FROM stock_snapshots WHERE shop_id=?", (shop_id,)).fetchone()[0]
    observed = _moment_value(latest)
    if not observed:
        return False, "暂无有效库存快照"
    if _now_utc(now) - observed > timedelta(hours=36):
        return False, "库存快照已过期"
    rows = db.execute("""SELECT finished_at,data_through,range_to FROM sync_runs
      WHERE shop_id=? AND module='stock' AND status='success'""", (shop_id,)).fetchall()
    finished = [_moment_value(row["finished_at"] or row["data_through"] or row["range_to"]) for row in rows]
    finished = [value for value in finished if value]
    if not finished or _now_utc(now) - max(finished) > timedelta(hours=36):
        return False, "库存同步尚未有足够新的成功记录"
    return True, ""


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
        from .main import stock
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


def _record_rule_state(shop_id, rule_key, items, now, resolvable_ids=None):
    current_time = _utc_text(now)
    active_ids = {item["entity_id"] for item in items}
    resolvable_ids = set(active_ids if resolvable_ids is None else resolvable_ids)
    counts = {"triggered": 0, "updated": 0, "resolved": 0}
    pending = []
    with transaction() as db:
        for item in items:
            metrics = json.dumps(item["metrics"], ensure_ascii=False, allow_nan=False)
            row = db.execute("""SELECT id FROM alert_events WHERE shop_id=? AND rule_key=?
              AND entity_type=? AND entity_id=? AND resolved_at IS NULL""",
                             (shop_id, rule_key, item["entity_type"], item["entity_id"])).fetchone()
            if row:
                db.execute("""UPDATE alert_events SET severity=?,title=?,message=?,metric_json=?,last_seen_at=?
                  WHERE id=?""", (item["severity"], item["title"], item["message"], metrics, current_time, row[0]))
                counts["updated"] += 1
            else:
                try:
                    cursor = db.execute("""INSERT INTO alert_events(
                      shop_id,rule_key,entity_type,entity_id,severity,title,message,metric_json,first_seen_at,last_seen_at)
                      VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                       (shop_id, rule_key, item["entity_type"], item["entity_id"], item["severity"],
                                        item["title"], item["message"], metrics, current_time, current_time))
                    pending.append((cursor.lastrowid, item["message"]))
                    counts["triggered"] += 1
                except sqlite3.IntegrityError:
                    existing = db.execute("""SELECT id FROM alert_events WHERE shop_id=? AND rule_key=?
                      AND entity_type=? AND entity_id=? AND resolved_at IS NULL""",
                                          (shop_id, rule_key, item["entity_type"], item["entity_id"])).fetchone()
                    if existing:
                        db.execute("UPDATE alert_events SET last_seen_at=?,message=?,metric_json=? WHERE id=?",
                                   (current_time, item["message"], metrics, existing[0]))
                        counts["updated"] += 1
        open_rows = db.execute("""SELECT id,entity_id FROM alert_events
          WHERE shop_id=? AND rule_key=? AND resolved_at IS NULL""", (shop_id, rule_key)).fetchall()
        for row in open_rows:
            if row["entity_id"] in resolvable_ids and row["entity_id"] not in active_ids:
                db.execute("UPDATE alert_events SET resolved_at=? WHERE id=?", (current_time, row["id"]))
                counts["resolved"] += 1
    return counts, pending


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
                            with transaction() as db:
                                db.execute("UPDATE alert_events SET last_notify_error=? WHERE id=?",
                                           ("钉钉发送失败", event_id))
                            summary["notifications_failed"] += 1
                        else:
                            with transaction() as db:
                                db.execute("""UPDATE alert_events SET last_notified_at=?,last_notify_error=NULL WHERE id=?""",
                                           (_utc_text(now), event_id))
                            summary["notifications_sent"] += 1
    return summary


def list_alert_events(shop_id=0, status="open", severity="", rule_key="", q="", page=1, size=50, category=""):
    if shop_id not in (0, 1, 2):
        raise ValueError("未知店铺")
    if status not in ("open", "resolved", "all"):
        raise ValueError("未知预警状态")
    if severity and severity not in ("critical", "high", "warning"):
        raise ValueError("未知预警等级")
    try:
        page, size = max(int(page), 1), min(max(int(size), 1), 100)
    except (TypeError, ValueError) as error:
        raise ValueError("分页参数无效") from error
    where, args = ["(?=0 OR e.shop_id=?)"], [shop_id, shop_id]
    if status == "open":
        where.append("e.resolved_at IS NULL")
    elif status == "resolved":
        where.append("e.resolved_at IS NOT NULL")
    if severity:
        where.append("e.severity=?"); args.append(severity)
    if rule_key:
        if rule_key not in RULE_KEYS:
            raise ValueError("未知预警规则")
        where.append("e.rule_key=?"); args.append(rule_key)
    if category:
        if category not in {"advertising", "inventory", "sales"}:
            raise ValueError("未知预警类型")
        keys = [key for key in RULE_KEYS if RULE_CATEGORIES[key] == category]
        where.append("e.rule_key IN (" + ",".join("?" for _ in keys) + ")"); args.extend(keys)
    if str(q or "").strip():
        query = f"%{str(q).strip().lower()}%"
        where.append("(lower(e.title) LIKE ? OR lower(e.message) LIKE ? OR lower(e.entity_id) LIKE ?)")
        args.extend((query, query, query))
    clause = " AND ".join(where)
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM alert_events e WHERE {clause}", args).fetchone()[0]
        rows = db.execute(f"""SELECT e.*,s.name shop_name FROM alert_events e JOIN shops s ON s.id=e.shop_id
          WHERE {clause} ORDER BY CASE e.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
          e.last_seen_at DESC,e.id DESC LIMIT ? OFFSET ?""", (*args, size, (page - 1) * size)).fetchall()
    items = []
    for row in rows:
        try:
            metrics = json.loads(row["metric_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            metrics = {}
        item = dict(row)
        item.pop("metric_json", None)
        item["metrics"] = metrics
        item["status"] = "resolved" if item["resolved_at"] else "open"
        item["rule_label"] = RULE_LABELS.get(item["rule_key"], item["rule_key"])
        item["category"] = RULE_CATEGORIES.get(item["rule_key"], "")
        item["object_name"] = metrics.get("campaign_name") or metrics.get("product_name") or item["entity_id"]
        items.append(item)
    return {"items": items, "total": total, "page": page, "size": size}


def alert_summary(shop_id=0):
    if shop_id not in (0, 1, 2):
        raise ValueError("未知店铺")
    with connect() as db:
        rows = db.execute("""SELECT e.rule_key,e.severity FROM alert_events e
          WHERE (?=0 OR e.shop_id=?) AND e.resolved_at IS NULL""", (shop_id, shop_id)).fetchall()
    summary = {"active": len(rows), "critical": 0, "high": 0, "warning": 0,
               "advertising": 0, "inventory": 0, "sales": 0}
    for row in rows:
        summary[row["severity"]] += 1
        summary[RULE_CATEGORIES.get(row["rule_key"], "sales")] += 1
    return summary


def acknowledge_alert(alert_id):
    try:
        alert_id = int(alert_id)
    except (TypeError, ValueError) as error:
        raise ValueError("预警ID无效") from error
    with transaction() as db:
        cursor = db.execute("""UPDATE alert_events SET acknowledged_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
          WHERE id=?""", (alert_id,))
        if cursor.rowcount != 1:
            raise LookupError("预警不存在")
    return {"ok": True, "id": alert_id}
