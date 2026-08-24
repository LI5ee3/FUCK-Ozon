import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .db import connect, transaction


ENDPOINT = "https://xapi.ozon.ru/exchange-rates/sellers/exchange-rate/by-period"
MOSCOW = ZoneInfo("Europe/Moscow")
SOURCE = "ozon_xapi"


def utc_period(date_from: date, date_to: date):
    if date_from > date_to:
        raise ValueError("开始日期不能晚于结束日期")
    start = datetime.combine(date_from, datetime.min.time(), MOSCOW).astimezone(timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), MOSCOW).astimezone(timezone.utc)
    return start, end


def split_period(start: datetime, end: datetime):
    while start < end:
        next_start = min(start + timedelta(days=60), end)
        yield start, next_start
        start = next_start


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _request_json(start, end, opener=None):
    params = [("fromCurrencyIds", "USD"), ("fromCurrencyIds", "CNY"),
              ("toCurrencyId", "RUB"), ("marketplaceId", "1"),
              ("fromDate", _iso(start)), ("toDate", _iso(end))]
    request = Request(f"{ENDPOINT}?{urlencode(params)}", headers={"Accept": "application/json"})
    with (opener or urlopen)(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"), parse_float=Decimal)


def _rate_items(value, inherited=None):
    inherited = dict(inherited or {})
    if isinstance(value, dict):
        for key in ("fromDate", "toDate", "fromCurrency", "fromCurrencyId",
                    "fromCurrencyCode", "toCurrency", "toCurrencyId", "toCurrencyCode"):
            if key in value:
                inherited[key] = value[key]
        if isinstance(value.get("exchangeRate"), dict):
            yield {**inherited, **value}
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _rate_items(child, inherited)
    elif isinstance(value, list):
        for child in value:
            yield from _rate_items(child, inherited)


def _currency(item, prefix):
    value = (item.get(f"{prefix}CurrencyId") or item.get(f"{prefix}CurrencyCode")
             or item.get(f"{prefix}Currency"))
    if isinstance(value, dict):
        value = value.get("id") or value.get("code")
    return str(value or "").upper()


def _rows(payload, fetched_at):
    rows = []
    for item in _rate_items(payload):
        exchange = item["exchangeRate"]
        from_currency, to_currency = _currency(item, "from"), _currency(item, "to")
        if from_currency not in ("USD", "CNY") or to_currency != "RUB":
            continue
        try:
            base_rate = Decimal(str(exchange["rate"]))
            adjustment = exchange.get("rateWithAdjustment")
            if base_rate <= 0:
                raise ValueError
        except (KeyError, InvalidOperation, ValueError) as error:
            raise ValueError("汇率接口返回了无效的基础汇率") from error
        valid_from, valid_to = item.get("fromDate"), item.get("toDate")
        if not valid_from or not valid_to:
            raise ValueError("汇率接口未返回有效时间区间")
        rows.append((from_currency, to_currency, str(valid_from), str(valid_to), str(base_rate),
                     None if adjustment is None else str(Decimal(str(adjustment))), SOURCE, fetched_at))
    return rows


def sync_exchange_rates(date_from: date, date_to: date, opener=None):
    start, end = utc_period(date_from, date_to)
    fetched_at = _iso(datetime.now(timezone.utc))
    written = segments = 0
    for segment_start, segment_end in split_period(start, end):
        rows = _rows(_request_json(segment_start, segment_end, opener), fetched_at)
        with transaction() as db:
            db.executemany("""INSERT INTO exchange_rates(
              from_currency,to_currency,valid_from_utc,valid_to_utc,base_rate,
              rate_with_adjustment,source,fetched_at) VALUES(?,?,?,?,?,?,?,?)
              ON CONFLICT(from_currency,to_currency,valid_from_utc,valid_to_utc) DO UPDATE SET
              base_rate=excluded.base_rate,rate_with_adjustment=excluded.rate_with_adjustment,
              source=excluded.source,fetched_at=excluded.fetched_at""", rows)
        written += len(rows)
        segments += 1
    return {"records": written, "segments": segments, "data_through": _iso(end)}


def _parse_utc(value):
    moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def load_base_rate_periods(db, start_utc, end_utc):
    grouped = {}
    rows = db.execute("""SELECT from_currency,valid_from_utc,valid_to_utc,base_rate
      FROM exchange_rates WHERE source=? AND valid_to_utc>?
      AND valid_from_utc<?
      ORDER BY valid_from_utc""", (SOURCE, start_utc, end_utc))
    for row in rows:
        key = (_parse_utc(row["valid_from_utc"]), _parse_utc(row["valid_to_utc"]))
        grouped.setdefault(key, {})[row["from_currency"]] = Decimal(row["base_rate"])
    return [(start, end, rates) for (start, end), rates in sorted(grouped.items())]


def rates_for_order(periods, created_at):
    try:
        moment = _parse_utc(created_at)
    except (TypeError, ValueError):
        return None
    return next((rates for start, end, rates in periods if start <= moment < end), None)


def convert_compensation(db, amount, compensated_at, source_currency, target_currency):
    result = {"converted_amount": None, "converted_currency": target_currency,
              "base_rates": {}, "missing_rate": False}
    if amount in (None, "") or not compensated_at:
        return result
    value = Decimal(str(amount))
    if source_currency == target_currency:
        result["converted_amount"] = str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        return result
    moment = _parse_utc(compensated_at)
    periods = load_base_rate_periods(db, _iso(moment), _iso(moment + timedelta(seconds=1)))
    rates = rates_for_order(periods, moment)
    required = {target_currency} if source_currency == "RUB" else {"CNY", "USD"}
    if not rates or any(currency not in rates for currency in required):
        result["missing_rate"] = True
        return result
    if source_currency == "RUB":
        converted = value / rates[target_currency]
    else:
        converted = value * rates["CNY"] / rates["USD"]
    result["converted_amount"] = str(converted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    result["base_rates"] = {f"{currency}_RUB": str(rates[currency]) for currency in sorted(required)}
    return result


def exchange_rate_status():
    with connect() as db:
        summary = db.execute("SELECT MAX(fetched_at),MAX(valid_to_utc) FROM exchange_rates").fetchone()
        latest = {}
        for currency in ("USD", "CNY"):
            row = db.execute("""SELECT base_rate,valid_from_utc,valid_to_utc FROM exchange_rates
              WHERE from_currency=? AND to_currency='RUB' AND source=?
              ORDER BY valid_to_utc DESC LIMIT 1""", (currency, SOURCE)).fetchone()
            latest[currency] = dict(row) if row else None
    return {"source": SOURCE, "last_success_at": summary[0], "data_through": summary[1], "rates": latest}
