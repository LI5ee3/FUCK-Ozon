import logging
import threading
from datetime import datetime, timedelta, timezone

from .alerts import evaluate_alerts
from .db import connect, transaction
from .dingtalk import send_sync_failure
from .exchange import MOSCOW, current_exchange_rate_entries, sync_exchange_rates
from .ozon.client import BEIJING
from .ozon.sync import sync_module
from .performance import sync_performance_campaigns, sync_performance_statistics
from .routers.common import _utc_text


logger = logging.getLogger(__name__)


SYNC_MODULES = {"orders", "returns", "stock"}
AD_SYNC_MODULES = {"ad_campaign_daily", "ad_sku_daily"}
AUTO_SYNC_MODULES = SYNC_MODULES | AD_SYNC_MODULES
PERFORMANCE_SYNC_MODULE = "ad_campaigns"
AUTO_SYNC_INTERVALS = {1, 2, 3, 4, 6, 8, 12, 24}
_auto_sync_stop = threading.Event()
_auto_sync_thread = None
_exchange_rate_last_attempt_at = None
_EXCHANGE_RATE_RETRY_COOLDOWN = timedelta(hours=1)


def _trim_sync_runs(db, keep=10, scheduled_slot=None, today=None):
    today = (scheduled_slot or today or datetime.now(BEIJING).date().isoformat())[:10]
    db.execute("""DELETE FROM sync_runs
      WHERE id NOT IN (SELECT id FROM sync_runs ORDER BY id DESC LIMIT ?)
      AND status!='running'
      AND NOT (run_source='auto' AND substr(COALESCE(scheduled_slot,''),1,10)=?)""", (keep, today))


def _run_performance_campaign_sync(shop_id):
    started_at = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        run_id = db.execute("""INSERT INTO sync_runs(
          shop_id,module,status,progress_total,run_source,started_at)
          VALUES(?,?, 'running',1,'manual',?)""",
                            (shop_id, PERFORMANCE_SYNC_MODULE, started_at)).lastrowid
    try:
        result = sync_performance_campaigns(shop_id)
    except Exception as error:
        with transaction() as db:
            db.execute("""UPDATE sync_runs SET finished_at=?,status='failed',error=?
              WHERE id=?""", (_utc_text(datetime.now(timezone.utc)), str(error)[:500], run_id))
            _trim_sync_runs(db)
        raise
    records = int(result.get("inserted_or_updated") or 0)
    finished_at = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        db.execute("""UPDATE sync_runs SET finished_at=?,status='success',progress_done=1,
          records=?,data_through=? WHERE id=?""", (finished_at, records, finished_at, run_id))
        _trim_sync_runs(db)
    result = dict(result)
    result["run_id"] = run_id
    return result


def _evaluate_alerts_after_sync(shop_id, module):
    rule_keys = {
        "orders": ("sales_drop", "inventory_risk"),
        "stock": ("inventory_risk",),
        "ad_campaign_daily": ("ad_spend_spike", "ad_drr_high", "ad_orders_drop"),
        "ad_sku_daily": ("ad_clicks_no_orders",),
        "ad_statistics": ("ad_spend_spike", "ad_drr_high", "ad_orders_drop", "ad_clicks_no_orders"),
    }.get(module)
    if not rule_keys:
        return
    try:
        evaluate_alerts(shop_id, rule_keys=rule_keys)
    except Exception:
        # Alert delivery is best effort; a sync that succeeded must stay successful.
        logger.exception("Alert evaluation failed after sync: shop_id=%s module=%s", shop_id, module)


def _run_performance_statistics_sync(shop_id, start, end, module="all"):
    run_module = "ad_statistics" if module == "all" else module
    started_at = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        run_id = db.execute("""INSERT INTO sync_runs(
          shop_id,module,range_from,range_to,status,progress_total,run_source,started_at)
          VALUES(?,?,?,?, 'running',1,'manual',?)""",
                            (shop_id, run_module, start.isoformat(), end.isoformat(), started_at)).lastrowid
    try:
        result = sync_performance_statistics(shop_id, start.isoformat(), end.isoformat(), module)
    except Exception as error:
        with transaction() as db:
            db.execute("""UPDATE sync_runs SET finished_at=?,status='failed',error=?
              WHERE id=?""", (_utc_text(datetime.now(timezone.utc)), str(error)[:500], run_id))
            _trim_sync_runs(db)
        raise
    records = int(result.get("inserted_or_updated") or 0)
    finished_at = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        db.execute("""UPDATE sync_runs SET finished_at=?,status='success',progress_done=1,
          records=?,data_through=? WHERE id=?""",
                   (finished_at, records, result.get("date_to"), run_id))
        _trim_sync_runs(db)
    _evaluate_alerts_after_sync(shop_id, run_module)
    result = dict(result)
    result["run_id"] = run_id
    return result


def save_auto_sync_settings(values):
    if set(values) == SYNC_MODULES:
        values = {str(shop_id): values for shop_id in (1, 2)}
    if set(values) != {"1", "2"}:
        raise ValueError("必须分别提交两个店铺的自动拉取设置")
    with connect() as db:
        current_ads = {shop_id: {row["module"]: dict(row) for row in db.execute(
            "SELECT * FROM shop_auto_sync_settings WHERE shop_id=? AND module IN ('ad_campaign_daily','ad_sku_daily')",
            (shop_id,))} for shop_id in (1, 2)}
    settings = []
    for shop_id in (1, 2):
        submitted = dict(values[str(shop_id)])
        if set(submitted) == SYNC_MODULES:
            submitted.update({module: {"enabled": row["enabled"], "interval_hours": row["interval_hours"],
                                       "range_days": row["range_days"]}
                              for module, row in current_ads[shop_id].items()})
        if set(submitted) != AUTO_SYNC_MODULES:
            raise ValueError("必须分别提交两个店铺的五个模块设置")
        for module in ("orders", "returns", "stock", "ad_campaign_daily", "ad_sku_daily"):
            value = submitted[module]
            if "run_time" in value:
                raise ValueError("run_time 已停用，请提交 interval_hours")
            try:
                interval_hours = int(value.get("interval_hours"))
                range_days = int(value.get("range_days") or 0)
            except (TypeError, ValueError) as error:
                raise ValueError("拉取频率或范围无效") from error
            if interval_hours not in AUTO_SYNC_INTERVALS:
                raise ValueError("拉取频率只允许 1、2、3、4、6、8、12、24 小时")
            if not 1 <= range_days <= 365:
                raise ValueError("自动拉取范围必须为 1 至 365 天")
            settings.append((int(bool(value.get("enabled"))), interval_hours,
                             1 if module == "stock" else range_days, shop_id, module))
    with transaction() as db:
        db.executemany("""UPDATE shop_auto_sync_settings SET enabled=?,interval_hours=?,range_days=?
          WHERE shop_id=? AND module=?""",
                       settings)


def _sync_ranges(module, start, end):
    if module == "stock" or module in AD_SYNC_MODULES:
        return [(start, end)]
    ranges, current = [], start
    while current <= end:
        next_month = (current.replace(day=1, year=current.year + 1, month=1)
                      if current.month == 12 else current.replace(day=1, month=current.month + 1))
        next_month = next_month.replace(hour=0, minute=0, second=0, microsecond=0)
        chunk_end = min(end, next_month - timedelta(seconds=1))
        ranges.append((current, chunk_end))
        current = next_month
    return ranges


def _run_sync_job(run_id, module, shop_id, ranges):
    records = 0
    with connect() as db:
        run_source = db.execute("SELECT run_source FROM sync_runs WHERE id=?", (run_id,)).fetchone()[0]
    try:
        for index, (start, end) in enumerate(ranges, 1):
            with transaction() as db:
                db.execute("UPDATE sync_runs SET current_from=?,current_to=? WHERE id=?",
                           (_utc_text(start), _utc_text(end), run_id))
            if module in AD_SYNC_MODULES:
                start_date = start.date() if isinstance(start, datetime) else start
                end_date = end.date() if isinstance(end, datetime) else end
                result = sync_performance_statistics(shop_id, start_date.isoformat(), end_date.isoformat(), module)
                records += int(result.get("inserted_or_updated") or 0)
            else:
                result = sync_module(module, shop_id, start, end, include_existing_missing=run_source != "auto")
                records += int(result.get("records") or 0)
            with transaction() as db:
                db.execute("UPDATE sync_runs SET progress_done=?,records=?,data_through=? WHERE id=?",
                           (index, records, _utc_text(end), run_id))
    except Exception as error:
        message = str(error)[:500]
        with transaction() as db:
            db.execute("""UPDATE sync_runs SET finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'),
              status='failed',error=? WHERE id=?""", (message, run_id))
            _trim_sync_runs(db)
        try:
            send_sync_failure(shop_id, module, ranges[0][0], ranges[-1][1], message)
        except Exception:
            pass
        return
    with transaction() as db:
        db.execute("""UPDATE sync_runs SET finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'),
          data_through=?,status='success',current_from=NULL,current_to=NULL WHERE id=?""",
                   (_utc_text(ranges[-1][1]), run_id))
        _trim_sync_runs(db)
    _evaluate_alerts_after_sync(shop_id, module)


def _create_sync_job(module, shop_id, start, end, run_source="manual", scheduled_slot=None, now=None):
    ranges = _sync_ranges(module, start, end)
    with transaction() as db:
        if run_source == "auto":
            cooldown = _utc_text((now or datetime.now(BEIJING)) - timedelta(minutes=5))
            if db.execute("""SELECT 1 FROM sync_runs
              WHERE shop_id=? AND module=? AND scheduled_slot=? AND run_source='auto'
              AND status='failed' AND datetime(COALESCE(finished_at,started_at))>=datetime(?)""",
                          (shop_id, module, scheduled_slot, cooldown)).fetchone():
                return None
        cursor = db.execute("""INSERT OR IGNORE INTO sync_runs(
          shop_id,module,range_from,range_to,status,progress_total,run_source,scheduled_slot)
          VALUES(?,?,?,?, 'running',?,?,?)""",
                            (shop_id, module, _utc_text(start), _utc_text(end), len(ranges),
                             run_source, scheduled_slot))
        if cursor.rowcount == 0:
            return None
        run_id = cursor.lastrowid
        _trim_sync_runs(db, scheduled_slot=scheduled_slot)
    threading.Thread(target=_run_sync_job, args=(run_id, module, shop_id, ranges), daemon=True).start()
    return run_id


def auto_sync_slot(now, interval_hours):
    if now.tzinfo is None:
        now = now.replace(tzinfo=BEIJING)
    now = now.astimezone(BEIJING)
    return now.replace(hour=(now.hour // interval_hours) * interval_hours,
                       minute=0, second=0, microsecond=0)


def run_auto_sync_once(now=None):
    now = now or datetime.now(BEIJING)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BEIJING)
    now = now.astimezone(BEIJING)
    with connect() as db:
        settings = db.execute("""SELECT * FROM shop_auto_sync_settings
          WHERE enabled=1 ORDER BY shop_id,rowid""").fetchall()
    started = []
    for setting in settings:
        slot = auto_sync_slot(now, setting["interval_hours"])
        end = now
        start = (now - timedelta(days=setting["range_days"] - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        run_id = _create_sync_job(setting["module"], setting["shop_id"], start, end,
                                  "auto", slot.isoformat(), now)
        if run_id:
            started.append(run_id)
    return started


def run_exchange_rate_auto_sync_once(now=None):
    global _exchange_rate_last_attempt_at
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    with connect() as db:
        current = current_exchange_rate_entries(db, moment)
    if all(currency in current for currency in ("USD", "CNY")):
        return False

    last_attempt = _exchange_rate_last_attempt_at
    same_moscow_day = last_attempt and last_attempt.astimezone(MOSCOW).date() == moment.astimezone(MOSCOW).date()
    if same_moscow_day and moment - last_attempt < _EXCHANGE_RATE_RETRY_COOLDOWN:
        return False

    _exchange_rate_last_attempt_at = moment
    current_date = moment.astimezone(MOSCOW).date()
    try:
        sync_exchange_rates(current_date, current_date)
    except Exception:
        logger.exception("Ozon 汇率自动同步失败")
        return False
    return True


def _auto_sync_scheduler():
    while not _auto_sync_stop.wait(20):
        try:
            run_auto_sync_once()
        except Exception:
            logger.exception("自动同步调度失败")
        try:
            run_exchange_rate_auto_sync_once()
        except Exception:
            logger.exception("Ozon 汇率自动同步调度失败")


def _start_auto_sync_scheduler():
    global _auto_sync_thread
    if _auto_sync_thread and _auto_sync_thread.is_alive():
        return
    _auto_sync_stop.clear()
    _auto_sync_thread = threading.Thread(target=_auto_sync_scheduler, name="auto-sync-scheduler", daemon=True)
    _auto_sync_thread.start()


def _stop_auto_sync_scheduler():
    _auto_sync_stop.set()
