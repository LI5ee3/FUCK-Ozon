from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


MOSCOW = ZoneInfo("Europe/Moscow")
BEIJING = ZoneInfo("Asia/Shanghai")


def _now_utc(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_text(value):
    return _now_utc(value).isoformat().replace("+00:00", "Z")


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
