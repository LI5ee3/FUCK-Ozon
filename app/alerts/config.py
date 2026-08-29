import json
import math

from ..db import DEFAULT_ALERT_RULE_CONFIGS, connect, transaction


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


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


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
