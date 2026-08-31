import base64
import hashlib
import hmac
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .db import connect, transaction
from .ozon.client import BEIJING, _env
from .ozon.mappings import CANCEL_REASON_ZH

MODULE_NAMES = {"orders": "订单", "returns": "退货", "stock": "库存"}
_stop = threading.Event()
_thread = None
ALLOWED_TEMPLATE_VARIABLES = {"统计日期", "取消总数", "退货总数", "店铺明细", "数据截止"}
REQUIRED_TEMPLATE_VARIABLES = {"统计日期", "店铺明细"}
TEMPLATE_LIMIT = 5000


def configured():
    return bool(_env().get("DINGTALK_WEBHOOK_URL"))


def _safe_error(error):
    text = str(error).replace("\n", " ")
    for key, value in _env().items():
        if value and ("KEY" in key or "SECRET" in key or "WEBHOOK" in key):
            text = text.replace(value, "[已隐藏]")
    return text[:500]


def send_text(content):
    values = _env()
    url = values.get("DINGTALK_WEBHOOK_URL", "").strip()
    if not url:
        raise RuntimeError("DINGTALK_WEBHOOK_URL 未配置")
    secret = values.get("DINGTALK_SECRET", "").strip()
    if secret:
        timestamp = str(round(time.time() * 1000))
        digest = hmac.new(secret.encode(), f"{timestamp}\n{secret}".encode(), hashlib.sha256).digest()
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query += [("timestamp", timestamp), ("sign", base64.b64encode(digest).decode())]
        url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                                      urllib.parse.urlencode(query), parsed.fragment))
    request = urllib.request.Request(url, json.dumps({"msgtype": "text", "text": {"content": content}},
                                                     ensure_ascii=False).encode(),
                                     {"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.load(response)
    if result.get("errcode") != 0:
        raise RuntimeError(result.get("errmsg") or "钉钉机器人发送失败")


def validate_template(template):
    template = str(template or "")
    if not template.strip():
        raise ValueError("消息模板不能为空")
    if len(template) > TEMPLATE_LIMIT:
        raise ValueError(f"消息模板不能超过 {TEMPLATE_LIMIT} 个字符")
    found = re.findall(r"\{\{([^{}]+)\}\}", template)
    variables = set(found)
    unknown = variables - ALLOWED_TEMPLATE_VARIABLES
    if unknown or template.count("{{") != len(found) or template.count("}}") != len(found):
        raise ValueError("消息模板包含未知变量")
    missing = REQUIRED_TEMPLATE_VARIABLES - variables
    if missing:
        raise ValueError("消息模板缺少必填变量：" + "、".join(sorted(missing)))
    return template


def render_template(template, values):
    rendered = validate_template(template)
    for name in ALLOWED_TEMPLATE_VARIABLES:
        rendered = rendered.replace("{{" + name + "}}", str(values[name]))
    return rendered


def send_sync_failure(shop_id, module, start, end, error):
    if not configured():
        return
    with connect() as db:
        shop = db.execute("SELECT name FROM shops WHERE id=?", (shop_id,)).fetchone()[0]
    now = datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")
    message = (f"同步失败\n店铺：{shop}\n模块：{MODULE_NAMES.get(module, module)}\n"
               f"拉取范围：{start.astimezone(BEIJING):%Y-%m-%d %H:%M} 至 {end.astimezone(BEIJING):%Y-%m-%d %H:%M}\n"
               f"失败时间：{now}（北京时间）\n错误：{_safe_error(error)[:200]}")
    send_text(message)


def _display_time(value):
    if not value:
        return "暂无"
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M")


def _reason(value):
    return CANCEL_REASON_ZH.get(value, value or "原因暂缺")


def _cutoff(db, module, fallback_sql):
    value = db.execute("""SELECT data_through FROM sync_runs
      WHERE module=? AND status='success' AND data_through IS NOT NULL
      ORDER BY id DESC LIMIT 1""", (module,)).fetchone()
    return value[0] if value else db.execute(fallback_sql).fetchone()[0]


def daily_values(stats_date):
    with connect() as db:
        shops = db.execute("SELECT id,name FROM shops ORDER BY id").fetchall()
        # CSV exports lack cancellation timestamps: count these cancelled orders by creation day.
        # API orders continue to use only the actual status-change day.
        cancellations = db.execute("""SELECT o.shop_id,o.channel,o.posting_number,o.cancel_reason_raw
          FROM orders o WHERE o.status_raw='已取消' AND o.shipped=1
          AND date(datetime(COALESCE(o.status_changed_at, CASE WHEN o.source='csv' THEN o.created_at END)),'+8 hours')=?
        """, (stats_date,)).fetchall()
        legacy = db.execute("""SELECT r.shop_id,r.record_key,r.posting_number,r.payload,o.channel
          FROM return_records r LEFT JOIN orders o
          ON o.shop_id=r.shop_id AND o.posting_number=r.posting_number
          WHERE date(datetime(r.occurred_at),'+8 hours')=?""", (stats_date,)).fetchall()
        rfbs = db.execute("""SELECT r.shop_id,r.return_number,r.posting_number,r.reason_raw,r.reason_name,
          COALESCE(o.channel,'realFBS') channel FROM rfbs_return_records r LEFT JOIN orders o
          ON o.shop_id=r.shop_id AND o.posting_number=r.posting_number
          WHERE date(datetime(r.created_at),'+8 hours')=?""", (stats_date,)).fetchall()
        order_through = _cutoff(db, "orders", "SELECT MAX(COALESCE(status_changed_at,created_at)) FROM orders")
        return_through = _cutoff(db, "returns", """SELECT MAX(value) FROM (
          SELECT MAX(occurred_at) value FROM return_records UNION ALL
          SELECT MAX(created_at) value FROM rfbs_return_records)""")

    cancel_by_shop = {shop["id"]: {} for shop in shops}
    for row in cancellations:
        if row["channel"] not in ("FBP", "realFBS", "WHD"):
            continue
        cancel_by_shop[row["shop_id"]][row["posting_number"]] = {
            "channel": row["channel"], "reasons": {_reason(row["cancel_reason_raw"])} }
    returns_by_shop = {shop["id"]: {} for shop in shops}
    for row in legacy:
        payload = json.loads(row["payload"])
        identity = row["posting_number"] or row["record_key"]
        item = returns_by_shop[row["shop_id"]].setdefault(identity, {"channel": row["channel"], "reasons": set()})
        if row["channel"] in ("FBP", "realFBS", "WHD"):
            item["channel"] = row["channel"]
        item["reasons"].add(_reason(payload.get("return_reason_name")))
    for row in rfbs:
        identity = row["posting_number"] or row["return_number"]
        item = returns_by_shop[row["shop_id"]].setdefault(identity, {"channel": row["channel"], "reasons": set()})
        item["reasons"].add(_reason(row["reason_raw"] or row["reason_name"]))

    channel_order = {"FBP": 0, "realFBS": 1, "WHD": 2, None: 3}
    lines = []
    for shop in shops:
        own_cancel, own_return = cancel_by_shop[shop["id"]], returns_by_shop[shop["id"]]
        cancel_counts = {channel: sum(item["channel"] == channel for item in own_cancel.values()) for channel in ("FBP", "realFBS", "WHD")}
        return_counts = {channel: sum(item["channel"] == channel for item in own_return.values()) for channel in ("FBP", "realFBS", "WHD")}
        lines += [f"{shop['name']}：",
                  f"取消：FBP {cancel_counts['FBP']}｜realFBS {cancel_counts['realFBS']}｜WHD {cancel_counts['WHD']}",
                  f"退货：FBP {return_counts['FBP']}｜realFBS {return_counts['realFBS']}｜WHD {return_counts['WHD']}", "", "取消订单"]
        ordered = sorted(own_cancel.items(), key=lambda pair: (channel_order.get(pair[1]["channel"], 3), pair[0]))
        lines += [f"{identity}：{' / '.join(sorted(item['reasons']))}" for identity, item in ordered] or ["无"]
        lines.append("")
        lines.append("退货订单")
        ordered = sorted(own_return.items(), key=lambda pair: (channel_order.get(pair[1]["channel"], 3), pair[0]))
        lines += [f"{identity}：{' / '.join(sorted(item['reasons']))}" for identity, item in ordered] or ["无"]
        lines.append("")
    return {"统计日期": stats_date,
            "取消总数": sum(len(items) for items in cancel_by_shop.values()),
            "退货总数": sum(len(items) for items in returns_by_shop.values()),
            "店铺明细": "\n".join(lines).rstrip(),
            "数据截止": f"订单 {_display_time(order_through)}｜退货 {_display_time(return_through)}"}


def daily_message(stats_date, template=None):
    if template is None:
        with connect() as db:
            template = db.execute("SELECT template FROM notification_settings WHERE id=1").fetchone()[0]
    return render_template(template, daily_values(stats_date))


def send_daily(stats_date):
    attempted = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with transaction() as db:
        previous = db.execute("SELECT status,attempted_at FROM notification_runs WHERE kind='daily' AND stats_date=?",
                              (stats_date,)).fetchone()
        if previous and previous["status"] == "success":
            return False
        if previous and datetime.fromisoformat(previous["attempted_at"]) > datetime.now(timezone.utc) - timedelta(minutes=5):
            return False
        db.execute("""INSERT INTO notification_runs(kind,stats_date,status,attempted_at) VALUES('daily',?,'sending',?)
          ON CONFLICT(kind,stats_date) DO UPDATE SET status='sending',attempted_at=excluded.attempted_at,error=NULL""",
                   (stats_date, attempted))
    try:
        send_text(daily_message(stats_date))
    except Exception as error:
        with transaction() as db:
            db.execute("UPDATE notification_runs SET status='failed',error=? WHERE kind='daily' AND stats_date=?",
                       (_safe_error(error), stats_date))
        raise
    with transaction() as db:
        db.execute("""UPDATE notification_runs SET status='success',sent_at=?,error=NULL
          WHERE kind='daily' AND stats_date=?""",
          (datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), stats_date))
    return True


def run_scheduled_once(now=None):
    now = now or datetime.now(BEIJING)
    with connect() as db:
        settings = db.execute("SELECT * FROM notification_settings WHERE id=1").fetchone()
    if not settings["daily_enabled"] or not configured():
        return False
    if now.isoweekday() not in {int(value) for value in settings["weekdays"].split(",") if value}:
        return False
    if now.strftime("%H:%M") < settings["push_time"]:
        return False
    return send_daily((now.date() - timedelta(days=1)).isoformat())


def next_push_time(settings, now=None):
    if not settings["daily_enabled"]:
        return None
    now = now or datetime.now(BEIJING)
    raw_weekdays = settings["weekdays"]
    weekdays = ({int(value) for value in raw_weekdays} if isinstance(raw_weekdays, list)
                else {int(value) for value in raw_weekdays.split(",") if value})
    hour, minute = map(int, settings["push_time"].split(":"))
    for offset in range(8):
        candidate = (now + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate.isoweekday() in weekdays and candidate > now:
            return candidate.isoformat()
    return None


def _scheduler():
    while not _stop.wait(20):
        try:
            run_scheduled_once()
        except Exception:
            pass


def start_scheduler():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_scheduler, name="dingtalk-scheduler", daemon=True)
    _thread.start()


def stop_scheduler():
    _stop.set()
