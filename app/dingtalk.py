import base64
import hashlib
import hmac
import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .db import connect, transaction
from .ozon import BEIJING, CANCEL_REASON_ZH, _env

MODULE_NAMES = {"orders": "订单", "returns": "退货", "stock": "库存"}
_stop = threading.Event()
_thread = None


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


def send_test():
    now = datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")
    send_text(f"FUCK Ozon 测试消息\n机器人连接正常\n发送时间：{now}（北京时间）")


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


def daily_message(stats_date):
    with connect() as db:
        shops = db.execute("SELECT id,name FROM shops ORDER BY id").fetchall()
        rows = db.execute("""SELECT o.shop_id,o.channel,o.posting_number,o.cancel_reason_raw
          FROM orders o WHERE o.status_raw='已取消' AND o.shipped=1
          AND date(datetime(o.status_changed_at),'+8 hours')=?
          ORDER BY o.shop_id,CASE o.channel WHEN 'FBP' THEN 1 WHEN 'realFBS' THEN 2 ELSE 3 END,o.posting_number
        """, (stats_date,)).fetchall()
        through = db.execute("""SELECT MAX(data_through) FROM sync_runs
          WHERE module='orders' AND status='success'""").fetchone()[0]
        if not through:
            through = db.execute("SELECT MAX(created_at) FROM orders").fetchone()[0]
    lines = ["昨日取消订单汇总", f"统计日期：{stats_date}（北京时间）", ""]
    for shop in shops:
        own = [row for row in rows if row["shop_id"] == shop["id"]]
        counts = {channel: sum(row["channel"] == channel for row in own)
                  for channel in ("FBP", "realFBS", "WHD")}
        lines.append(f"{shop['name']}：FBP {counts['FBP']}｜realFBS {counts['realFBS']}｜WHD {counts['WHD']}")
        for row in own:
            lines.append(f"{row['posting_number']}：{CANCEL_REASON_ZH.get(row['cancel_reason_raw'], row['cancel_reason_raw'] or '原因暂缺')}")
        lines.append("")
    lines.append(f"数据截止：{_display_time(through)}")
    return "\n".join(lines)


def send_daily(stats_date):
    attempted = datetime.now(timezone.utc).isoformat()
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
          WHERE kind='daily' AND stats_date=?""", (datetime.now(timezone.utc).isoformat(), stats_date))
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
