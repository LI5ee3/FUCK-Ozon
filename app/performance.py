import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .db import transaction
from .ozon import _env

BASE_URL = "https://api-performance.ozon.ru"
TOKEN_PATH = "/api/client/token"
CAMPAIGN_PATH = "/api/client/campaign"
HTTP_TIMEOUT = 30
TOKEN_REFRESH_MARGIN = 60
_token_cache = {}
_token_lock = threading.Lock()


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


def _campaign_row(shop_id, campaign):
    if not isinstance(campaign, dict):
        raise PerformanceAPIError(f"Performance API {CAMPAIGN_PATH}: Campaign 数据格式无效")
    campaign_id = _value(campaign, "id", "campaign_id")
    if campaign_id in (None, ""):
        raise PerformanceAPIError(f"Performance API {CAMPAIGN_PATH}: Campaign 缺少 id")
    return (
        shop_id,
        str(campaign_id),
        str(_value(campaign, "title", "name") or ""),
        str(_value(campaign, "state", "status") or ""),
        _value(campaign, "paymentType", "payment_type"),
        _value(campaign, "advObjectType", "adv_object_type", "campaign_type"),
        _value(campaign, "placement"),
        _weekly_budget(_value(campaign, "weeklyBudget", "weekly_budget")),
        _value(campaign, "createdAt", "created_at"),
        _value(campaign, "updatedAt", "updated_at"),
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
