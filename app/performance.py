import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from .db import connect, transaction
from .ozon import _env

BASE_URL = "https://api-performance.ozon.ru"
TOKEN_PATH = "/api/client/token"
CAMPAIGN_PATH = "/api/client/campaign"
CAMPAIGN_STATS_PATH = "/api/client/statistics/campaign/product/json"
DAILY_STATS_PATH = "/api/client/statistics/daily/json"
SKU_STATS_PATH = "/api/client/statistics/products/sku"
HTTP_TIMEOUT = 30
TOKEN_REFRESH_MARGIN = 60
STAT_CAMPAIGN_BATCH_SIZE = 10
_token_cache = {}
_token_lock = threading.Lock()
MOSCOW = ZoneInfo("Europe/Moscow")


class PerformanceConfigurationError(ValueError):
    pass


class PerformanceAPIError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def _shop_id(shop):
    try:
        shop = int(shop)
    except (TypeError, ValueError) as error:
        raise ValueError("未知店铺") from error
    if shop not in (1, 2):
        raise ValueError("未知店铺")
    return shop


def _credentials(shop):
    shop = _shop_id(shop)
    values = _env()
    client_id = str(values.get(f"SHOP_{shop}_OZON_PERF_CLIENT_ID") or "").strip()
    client_secret = str(values.get(f"SHOP_{shop}_OZON_PERF_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise PerformanceConfigurationError(f"Shop {shop} 尚未配置 Ozon Performance API")
    return shop, client_id, client_secret


def _redact(value, secrets=()):
    text = str(value or "").replace("\n", " ")
    for secret in secrets:
        if secret:
            text = text.replace(str(secret), "[已隐藏]")
    return text[:500]


def _response_json(response, path):
    try:
        return json.load(response)
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError) as error:
        raise PerformanceAPIError(f"Performance API {path}: 响应不是有效 JSON") from error


def _error_message(error, secrets=()):
    try:
        raw = error.read()
        body = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(body, dict):
            for key in ("message", "error", "error_description", "detail"):
                value = body.get(key)
                if value not in (None, ""):
                    return _redact(value, secrets)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        pass
    finally:
        error.close()
    return _redact(getattr(error, "reason", "Ozon Performance API 请求失败"), secrets)


def _request_json(url, method, path, payload=None, headers=None, secrets=()):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return _response_json(response, path)
    except urllib.error.HTTPError as error:
        message = _error_message(error, secrets)
        raise PerformanceAPIError(f"Performance API {path}: HTTP {error.code}: {message}", error.code) from error
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        raise PerformanceAPIError(f"Performance API {path}: 网络请求失败：{_redact(error, secrets)}") from error


def _build_url(path, params=None):
    path = "/" + str(path).lstrip("/")
    query = urllib.parse.urlencode(params or {}, doseq=True)
    return BASE_URL + path + (f"?{query}" if query else "")


def _fetch_token(client_id, client_secret):
    body = _request_json(
        BASE_URL + TOKEN_PATH,
        "POST",
        TOKEN_PATH,
        {"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
        {"Accept": "application/json", "Content-Type": "application/json"},
        (client_secret,),
    )
    token = body.get("access_token") if isinstance(body, dict) else None
    if not token:
        raise PerformanceAPIError(f"Performance API {TOKEN_PATH}: token 响应缺少 access_token")
    try:
        expires_in = int(body.get("expires_in", 0))
    except (TypeError, ValueError) as error:
        raise PerformanceAPIError(f"Performance API {TOKEN_PATH}: expires_in 无效") from error
    return {"access_token": str(token), "token_type": str(body.get("token_type") or "Bearer"),
            "expires_in": max(0, expires_in)}


def get_token(shop, force=False):
    shop, client_id, client_secret = _credentials(shop)
    now = time.time()
    with _token_lock:
        cached = _token_cache.get(shop)
        if not force and cached and cached["expires_at"] - TOKEN_REFRESH_MARGIN > now:
            return cached["access_token"]
        # ponytail: one global token lock; use per-shop locks only if token traffic becomes contended.
        cached = _fetch_token(client_id, client_secret)
        cached["expires_at"] = now + cached.pop("expires_in")
        _token_cache[shop] = cached
        return cached["access_token"]


def _invalidate_token(shop, token):
    with _token_lock:
        if _token_cache.get(shop, {}).get("access_token") == token:
            _token_cache.pop(shop, None)


def request(shop, method, path, *, payload=None, params=None):
    shop, _, client_secret = _credentials(shop)
    path = "/" + str(path).lstrip("/")
    token = get_token(shop)
    for attempt in range(2):
        try:
            return _request_json(
                _build_url(path, params), method, path, payload,
                {"Accept": "application/json", "Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
                (client_secret, token),
            )
        except PerformanceAPIError as error:
            if error.status_code != 401 or attempt:
                raise
            _invalidate_token(shop, token)
            token = get_token(shop, force=True)


def list_campaigns(shop):
    response = request(shop, "GET", CAMPAIGN_PATH)
    container = response
    if isinstance(response, dict) and isinstance(response.get("result"), (dict, list)):
        container = response["result"]
    if isinstance(container, dict):
        campaigns = container.get("list")
        if campaigns is None:
            campaigns = container.get("campaigns", container.get("items"))
    else:
        campaigns = container
    if not isinstance(campaigns, list):
        raise PerformanceAPIError(f"Performance API {CAMPAIGN_PATH}: 响应缺少 Campaign 列表")
    return campaigns


def _stat_rows(response, path):
    rows = response.get("rows") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        raise PerformanceAPIError(f"Performance API {path}: 响应缺少 rows 列表")
    return rows


def _number(value):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = value.replace(" ", "").replace(",", ".")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _integer(value):
    value = _number(value)
    return int(value) if value is not None else None


def _stat_date(value, path):
    value = str(value or "")[:10]
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise PerformanceAPIError(f"Performance API {path}: 统计日期无效") from error
    return value


def _stat_id(record, *keys):
    value = _value(record, *keys)
    return str(value) if value not in (None, "") else None


def parse_campaign_statistics(response):
    rows = _stat_rows(response, CAMPAIGN_STATS_PATH)
    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            raise PerformanceAPIError(f"Performance API {CAMPAIGN_STATS_PATH}: Campaign 统计行格式无效")
        campaign_id = _stat_id(row, "id", "campaignId", "campaign_id")
        if not campaign_id:
            raise PerformanceAPIError(f"Performance API {CAMPAIGN_STATS_PATH}: 统计行缺少 campaign id")
        parsed.append({
            "campaign_id": campaign_id,
            "name": _text_value(_value(row, "title", "name")) or "",
            "status": _text_value(_value(row, "status", "state")) or "",
            "adv_object_type": _text_value(_value(row, "objectType", "advObjectType")),
            "placement": _text_value(_value(row, "placement")),
            "impressions": _integer(_value(row, "views", "impressions")),
            "clicks": _integer(_value(row, "clicks")),
            "cart_adds": _integer(_value(row, "toCart", "cartAdds", "cart_adds")),
            "spend_rub": _number(_value(row, "moneySpent", "expense", "spend")),
            "orders": _integer(_value(row, "orders")),
            "revenue_rub": _number(_value(row, "ordersMoney", "sales", "revenue")),
        })
    return parsed


def parse_daily_statistics(response):
    rows = _stat_rows(response, DAILY_STATS_PATH)
    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            raise PerformanceAPIError(f"Performance API {DAILY_STATS_PATH}: 日统计行格式无效")
        campaign_id = _stat_id(row, "id", "campaignId", "campaign_id")
        if not campaign_id:
            raise PerformanceAPIError(f"Performance API {DAILY_STATS_PATH}: 统计行缺少 campaign id")
        parsed.append({
            "stat_date": _stat_date(_value(row, "date", "statDate", "stat_date"), DAILY_STATS_PATH),
            "campaign_id": campaign_id,
            "impressions": _integer(_value(row, "views", "impressions")),
            "clicks": _integer(_value(row, "clicks")),
            "cart_adds": _integer(_value(row, "toCart", "cartAdds", "cart_adds")),
            "spend_rub": _number(_value(row, "moneySpent", "expense", "spend")),
            "orders": _integer(_value(row, "orders")),
            "revenue_rub": _number(_value(row, "ordersMoney", "sales", "revenue")),
        })
    return parsed


def parse_sku_statistics(response):
    rows = _stat_rows(response, SKU_STATS_PATH)
    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            raise PerformanceAPIError(f"Performance API {SKU_STATS_PATH}: SKU 统计行格式无效")
        campaign_id = _stat_id(row, "campaignId", "campaign_id", "id")
        sku = _stat_id(row, "sku", "SKU")
        if not campaign_id or not sku:
            raise PerformanceAPIError(f"Performance API {SKU_STATS_PATH}: 统计行缺少 campaign id 或 SKU")
        parsed.append({
            "stat_date": _stat_date(_value(row, "date", "statDate", "stat_date"), SKU_STATS_PATH),
            "campaign_id": campaign_id,
            "sku": sku,
            "product_name": _text_value(_value(row, "productName", "product_name", "title", "name")),
            "impressions": _integer(_value(row, "views", "impressions")),
            "clicks": _integer(_value(row, "clicks")),
            "cart_adds": _integer(_value(row, "toCart", "cartAdds", "cart_adds")),
            "spend_rub": _number(_value(row, "expense", "moneySpent", "spend")),
            "orders": _integer(_value(row, "orders")),
            "revenue_rub": _number(_value(row, "sales", "ordersMoney", "revenue")),
        })
    return parsed


def _stat_params(date_from, date_to, campaign_ids=None):
    params = {"dateFrom": date_from, "dateTo": date_to}
    if campaign_ids:
        params["campaignIds"] = [str(value) for value in campaign_ids]
    return params


def get_campaign_statistics(shop, date_from, date_to, campaign_ids=None):
    response = request(shop, "GET", CAMPAIGN_STATS_PATH,
                       params=_stat_params(date_from, date_to, campaign_ids))
    return parse_campaign_statistics(response)


def get_daily_statistics(shop, date_from, date_to, campaign_ids=None):
    response = request(shop, "GET", DAILY_STATS_PATH,
                       params=_stat_params(date_from, date_to, campaign_ids))
    return parse_daily_statistics(response)


def get_sku_statistics(shop, date_from, date_to, campaign_ids):
    if not campaign_ids:
        return []
    response = request(shop, "POST", SKU_STATS_PATH, payload={
        "campaignIds": [str(value) for value in campaign_ids],
        "dateFrom": date_from,
        "dateTo": date_to,
    })
    return parse_sku_statistics(response)


def _date_range(date_from, date_to):
    try:
        start = date.fromisoformat(str(date_from))
        end = date.fromisoformat(str(date_to))
    except (TypeError, ValueError) as error:
        raise ValueError("日期格式必须为 YYYY-MM-DD") from error
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    return start, end


def _date_chunks(start, end, days=30):
    current = start
    while current <= end:
        chunk_end = min(end, current + timedelta(days=days - 1))
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def _batches(values, size=STAT_CAMPAIGN_BATCH_SIZE):
    return [values[index:index + size] for index in range(0, len(values), size)]


def _campaign_ids(shop):
    with connect() as db:
        values = [str(row[0]) for row in db.execute(
            "SELECT campaign_id FROM ad_campaigns WHERE shop_id=? ORDER BY campaign_id", (shop,))]
    if values:
        return values
    sync_performance_campaigns(shop)
    with connect() as db:
        return [str(row[0]) for row in db.execute(
            "SELECT campaign_id FROM ad_campaigns WHERE shop_id=? ORDER BY campaign_id", (shop,))]


def _unique_rows(rows, *keys):
    unique = {}
    for row in rows:
        unique[tuple(row.get(key) for key in keys)] = row
    return list(unique.values())


def _upsert_campaign_daily(shop, rows):
    rows = _unique_rows(rows, "stat_date", "campaign_id")
    if not rows:
        return 0
    synced_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    values = [(shop, row["stat_date"], row["campaign_id"], row.get("impressions"), row.get("clicks"),
               row.get("cart_adds"), row.get("spend_rub"), row.get("orders"), row.get("revenue_rub"), synced_at)
              for row in rows]
    with transaction() as db:
        db.executemany("""INSERT INTO ad_campaign_daily(
          shop_id,stat_date,campaign_id,impressions,clicks,cart_adds,spend_rub,orders,revenue_rub,synced_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(shop_id,stat_date,campaign_id) DO UPDATE SET
            impressions=excluded.impressions,clicks=excluded.clicks,cart_adds=excluded.cart_adds,
            spend_rub=excluded.spend_rub,orders=excluded.orders,revenue_rub=excluded.revenue_rub,
            synced_at=excluded.synced_at""", values)
    return len(rows)


def _upsert_sku_daily(shop, rows):
    rows = _unique_rows(rows, "stat_date", "campaign_id", "sku")
    if not rows:
        return 0
    synced_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    values = [(shop, row["stat_date"], row["campaign_id"], row["sku"], row.get("product_name"),
               row.get("impressions"), row.get("clicks"), row.get("cart_adds"), row.get("spend_rub"),
               row.get("orders"), row.get("revenue_rub"), synced_at) for row in rows]
    with transaction() as db:
        db.executemany("""INSERT INTO ad_sku_daily(
          shop_id,stat_date,campaign_id,sku,product_name,impressions,clicks,cart_adds,
          spend_rub,orders,revenue_rub,synced_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(shop_id,stat_date,campaign_id,sku) DO UPDATE SET
            product_name=excluded.product_name,impressions=excluded.impressions,clicks=excluded.clicks,
            cart_adds=excluded.cart_adds,spend_rub=excluded.spend_rub,orders=excluded.orders,
            revenue_rub=excluded.revenue_rub,synced_at=excluded.synced_at""", values)
    return len(rows)


def sync_performance_statistics(shop, date_from, date_to, module="all"):
    shop = _shop_id(shop)
    start, end = _date_range(date_from, date_to)
    module = str(module or "all")
    aliases = {"daily": "ad_campaign_daily", "campaign_daily": "ad_campaign_daily",
               "sku": "ad_sku_daily"}
    module = aliases.get(module, module)
    if module not in {"all", "ad_campaign_daily", "ad_sku_daily"}:
        raise ValueError("未知广告统计模块")

    campaign_ids = _campaign_ids(shop)
    daily_fetched = daily_saved = 0
    if module in {"all", "ad_campaign_daily"}:
        for chunk_start, chunk_end in _date_chunks(start, end):
            batches = _batches(campaign_ids) if campaign_ids else [None]
            for ids in batches:
                rows = get_daily_statistics(shop, chunk_start.isoformat(), chunk_end.isoformat(), ids)
                daily_fetched += len(rows)
                daily_saved += _upsert_campaign_daily(shop, rows)

    sku_fetched = sku_saved = 0
    sku_dates = []
    today = datetime.now(MOSCOW).date()
    sku_allowed = {today - timedelta(days=1), today}
    if module in {"all", "ad_sku_daily"}:
        sku_dates = [value for value in (start + timedelta(days=index)
                     for index in range((end - start).days + 1)) if value in sku_allowed]
        for stat_day in sku_dates:
            for ids in _batches(campaign_ids):
                rows = get_sku_statistics(shop, stat_day.isoformat(), stat_day.isoformat(), ids)
                sku_fetched += len(rows)
                sku_saved += _upsert_sku_daily(shop, rows)

    skipped = []
    if module in {"all", "ad_sku_daily"}:
        skipped = [(start + timedelta(days=index)).isoformat()
                   for index in range((end - start).days + 1) if start + timedelta(days=index) not in sku_allowed]
    return {
        "shop_id": shop, "success": True, "date_from": start.isoformat(), "date_to": end.isoformat(),
        "fetched": daily_fetched + sku_fetched,
        "inserted_or_updated": daily_saved + sku_saved,
        "campaign_daily": {"fetched": daily_fetched, "inserted_or_updated": daily_saved},
        "sku": {"fetched": sku_fetched, "inserted_or_updated": sku_saved, "dates": [d.isoformat() for d in sku_dates]},
        "sku_skipped_dates": skipped,
    }


def _value(record, *keys):
    for key in keys:
        if record.get(key) not in (None, ""):
            return record[key]
    return None


def _weekly_budget(value):
    if value in (None, ""):
        return None
    try:
        return float(value) / 1_000_000
    except (TypeError, ValueError):
        return None


def _text_value(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _campaign_row(shop_id, campaign):
    if not isinstance(campaign, dict):
        raise PerformanceAPIError(f"Performance API {CAMPAIGN_PATH}: Campaign 数据格式无效")
    campaign_id = _value(campaign, "id", "campaign_id")
    if campaign_id in (None, ""):
        raise PerformanceAPIError(f"Performance API {CAMPAIGN_PATH}: Campaign 缺少 id")
    return (
        shop_id,
        str(campaign_id),
        _text_value(_value(campaign, "title", "name")) or "",
        _text_value(_value(campaign, "state", "status")) or "",
        _text_value(_value(campaign, "paymentType", "payment_type")),
        _text_value(_value(campaign, "advObjectType", "adv_object_type", "campaign_type")),
        _text_value(_value(campaign, "placement")),
        _weekly_budget(_value(campaign, "weeklyBudget", "weekly_budget")),
        _text_value(_value(campaign, "createdAt", "created_at")),
        _text_value(_value(campaign, "updatedAt", "updated_at")),
    )


def sync_performance_campaigns(shop):
    shop, _, _ = _credentials(shop)
    campaigns = list_campaigns(shop)
    synced_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rows = [_campaign_row(shop, campaign) + (synced_at,) for campaign in campaigns]
    with transaction() as db:
        db.executemany("""INSERT INTO ad_campaigns(
          shop_id,campaign_id,name,state,payment_type,adv_object_type,placement,
          weekly_budget,created_at,updated_at,synced_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(shop_id,campaign_id) DO UPDATE SET
            name=excluded.name,state=excluded.state,payment_type=excluded.payment_type,
            adv_object_type=excluded.adv_object_type,placement=excluded.placement,
            weekly_budget=excluded.weekly_budget,created_at=excluded.created_at,
            updated_at=excluded.updated_at,synced_at=excluded.synced_at""", rows)
    return {"shop_id": shop, "success": True, "fetched": len(rows),
            "inserted_or_updated": len(rows)}
