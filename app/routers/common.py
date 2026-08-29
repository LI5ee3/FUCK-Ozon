import statistics
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

from ..exchange import convert_compensation
from ..ozon.client import BEIJING
from ..ozon.mappings import CANCEL_REASON_ZH, STATUS_ZH


ACTIVE = "NOT (o.status_raw='已取消' AND o.shipped=0)"


def _paging(page, size):
    return max(page, 1), min(max(size, 1), 100)


def _shop_clause(shop_id):
    return (" AND o.shop_id=?", [shop_id]) if shop_id in (1, 2) else ("", [])


def _months_before(value, months=3):
    month = value.month - months - 1
    year, month = value.year + month // 12, month % 12 + 1
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    return date(year, month, min(value.day, (next_month - timedelta(days=1)).day))


def _overview_range(date_from=None, date_to=None, now=None):
    today = (now or datetime.now(BEIJING)).date()
    try:
        end = date.fromisoformat(date_to) if date_to else today
        start = date.fromisoformat(date_from) if date_from else _months_before(end)
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "日期格式必须为 YYYY-MM-DD") from error
    if start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    utc_start = datetime.combine(start, datetime.min.time(), BEIJING).astimezone(timezone.utc)
    utc_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), BEIJING).astimezone(timezone.utc)
    return start, end, utc_start.isoformat().replace("+00:00", "Z"), utc_end.isoformat().replace("+00:00", "Z")


def _utc_text(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_moment(value):
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _percentile(values, fraction):
    if not values:
        return None
    if fraction == .5:
        return statistics.median(values)
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=10, method="inclusive")[8]


def _duration_hours(start, end):
    start, end = _utc_moment(start), _utc_moment(end)
    if not start or not end or end < start:
        return None
    return (end - start).total_seconds() / 3600


def _complaint_deadline(primary_time, fallback_time=None, now=None):
    moment = _utc_moment(primary_time) or _utc_moment(fallback_time)
    if not moment:
        return {"complaint_deadline": None, "complaint_deadline_status": "missing"}
    deadline = moment.astimezone(BEIJING).date() + timedelta(days=30)
    if now is None:
        today = datetime.now(BEIJING).date()
    elif isinstance(now, datetime):
        today = (now if now.tzinfo else now.replace(tzinfo=BEIJING)).astimezone(BEIJING).date()
    else:
        today = now
    days = (deadline - today).days
    status = "overdue" if days < 0 else "due_today" if days == 0 else "due_soon" if days <= 7 else "normal"
    return {"complaint_deadline": deadline.isoformat(), "complaint_deadline_status": status}


def _translated_order(row):
    order = dict(row)
    order["status_raw"] = STATUS_ZH.get(order["status_raw"], order["status_raw"])
    order["cancel_reason_raw"] = CANCEL_REASON_ZH.get(order["cancel_reason_raw"], order["cancel_reason_raw"])
    return order


def _with_compensation_conversion(db, row):
    target = row.get("settlement_currency")
    for prefix, amount_key, time_key, source in (
        ("platform_compensation", "platform_compensation_rub", "platform_compensated_at", "RUB"),
        ("logistics_compensation", "logistics_compensation_cny", "logistics_compensated_at", "CNY"),
    ):
        result = convert_compensation(db, row.get(amount_key), row.get(time_key), source, target)
        row[f"{prefix}_original_currency"] = source
        row[f"{prefix}_converted_amount"] = result["converted_amount"]
        row[f"{prefix}_converted_currency"] = result["converted_currency"]
        row[f"{prefix}_base_rates"] = result["base_rates"]
        row[f"{prefix}_missing_rate"] = result["missing_rate"]
        moment = _utc_moment(row.get(time_key))
        row[f"{time_key}_beijing"] = moment.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M") if moment else None
    return row
