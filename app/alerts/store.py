import json
import sqlite3

from ..db import connect, transaction
from .config import RULE_CATEGORIES, RULE_KEYS, RULE_LABELS
from .freshness import _utc_text


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


def _mark_notification_failed(event_id):
    with transaction() as db:
        db.execute("UPDATE alert_events SET last_notify_error=? WHERE id=?",
                   ("钉钉发送失败", event_id))


def _mark_notification_sent(event_id, now):
    with transaction() as db:
        db.execute("""UPDATE alert_events SET last_notified_at=?,last_notify_error=NULL WHERE id=?""",
                   (_utc_text(now), event_id))


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
