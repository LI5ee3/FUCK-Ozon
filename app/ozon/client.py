import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .mappings import PUSH_EVENT_TYPES

API = "https://api-seller.ozon.ru"
BEIJING = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parent.parent.parent
_request_lock = threading.Lock()
_last_request = 0.0


def _env():
    values = dict(os.environ)
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values.setdefault(key.strip(), value.strip())
    return values


def _headers(shop_id):
    values = _env()
    client_id = values.get(f"SHOP_{shop_id}_OZON_CLIENT_ID", "")
    api_key = values.get(f"SHOP_{shop_id}_OZON_API_KEY", "")
    if not client_id or not api_key:
        raise ValueError(f"店铺{shop_id} API凭据未配置")
    return {"Client-Id": client_id, "Api-Key": api_key, "Content-Type": "application/json"}


def _wait_for_request_slot():
    global _last_request
    with _request_lock:
        now = time.monotonic()
        scheduled = max(now, _last_request + 1.05)
        _last_request = scheduled
    if scheduled > now:
        time.sleep(scheduled - now)


def _post(shop_id, path, payload):
    # ponytail: one global start-rate limiter; network waits must not block unrelated module requests.
    for attempt in range(7):
        _wait_for_request_slot()
        request = urllib.request.Request(
            API + path, data=json.dumps(payload).encode(), headers=_headers(shop_id), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if (error.code == 429 or 500 <= error.code < 600) and attempt < 6:
                delay = min(30, 2 ** (attempt + 1))
                retry_after = error.headers.get("Retry-After") if error.headers else None
                try:
                    if str(retry_after).isdigit():
                        delay = min(30, int(retry_after))
                    elif retry_after:
                        retry_at = parsedate_to_datetime(retry_after)
                        if retry_at.tzinfo is None:
                            retry_at = retry_at.replace(tzinfo=timezone.utc)
                        delay = min(30, max(0, (retry_at - datetime.now(timezone.utc)).total_seconds()))
                except (TypeError, ValueError, OverflowError):
                    pass
                time.sleep(delay)
                continue
            try:
                message = json.loads(error.read()).get("message", "Ozon API请求失败")
            except Exception:
                message = "Ozon API请求失败"
            raise RuntimeError(f"{path}: HTTP {error.code}: {message}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt < 6:
                time.sleep(min(30, 2 ** (attempt + 1)))
                continue
            raise RuntimeError(f"{path}: 网络请求失败: {error}") from error


def _cursor_pages(shop_id, path, payload, list_key, request_cursor="cursor", response_cursor="cursor"):
    records, cursor = [], ""
    for _ in range(200):
        request = dict(payload)
        if cursor:
            request[request_cursor] = cursor
        body = _post(shop_id, path, request)
        container = body.get("result") if isinstance(body.get("result"), dict) else body
        batch = container.get(list_key) or []
        records.extend(batch)
        total = container.get("total")
        if not batch or ("has_next" in container and not container.get("has_next")):
            return records
        if total is not None and len(records) >= int(total):
            return records
        next_cursor = str(container.get(response_cursor) or body.get(response_cursor) or batch[-1].get("id") or "")
        if not next_cursor:
            raise RuntimeError(f"{path}: 分页游标缺失")
        if next_cursor == cursor:
            raise RuntimeError(f"{path}: 分页游标未前进")
        cursor = next_cursor
    raise RuntimeError(f"{path}: 分页超过安全上限")


def _stamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def push_type_list(shop_id):
    return _post(shop_id, "/v1/notification/push-type/list", {})


def notification_check(shop_id, url):
    return _post(shop_id, "/v1/notification/check", {"url": url})


def notification_set(shop_id, url, types=None):
    return _post(shop_id, "/v1/notification/set", {"url": url,
                                                     "types": list(types or PUSH_EVENT_TYPES)})


def notification_list(shop_id):
    return _post(shop_id, "/v1/notification/list", {})


def notification_enable(shop_id, notification_id, enabled):
    return _post(shop_id, "/v1/notification/enable", {"id": int(notification_id), "enabled": bool(enabled)})


def notification_delete(shop_id, notification_id):
    return _post(shop_id, "/v1/notification/delete", {"id": int(notification_id)})


def probe_shop(shop_id):
    roles_response = _post(shop_id, "/v1/roles", {})
    info_response = _post(shop_id, "/v1/seller/info", {})
    roles = roles_response.get("roles") or roles_response.get("result") or []
    role_names = [str(role.get("name") or role.get("role") or role) if isinstance(role, dict) else str(role)
                  for role in roles]
    methods = {method for role in roles if isinstance(role, dict) for method in role.get("methods", [])}
    required = {
        "orders": {"/v4/posting/fbs/list", "/v3/posting/fbo/list"},
        "returns": {"/v1/returns/list", "/v2/returns/rfbs/list", "/v2/returns/rfbs/get"},
        "stock": {"/v4/product/info/stocks"},
    }
    permissions = {module: ("可用" if paths <= methods else "缺少：" + "、".join(sorted(paths - methods)))
                   for module, paths in required.items()}
    info = info_response.get("result") or info_response
    allowed = {"company", "name", "seller_id", "client_id", "inn", "ogrn"}
    return {"valid": True, "identity": {key: value for key, value in info.items() if key in allowed},
            "roles": role_names, "permissions": permissions}
