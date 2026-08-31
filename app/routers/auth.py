import hashlib
import hmac
import ipaddress
import os
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response

from ..db import DATA_DIR
from ..ozon.client import _env
from ..security import (clear_login_failures, login_limited, password_matches,
                        record_login_failure)
from .common import read_bounded_json


router = APIRouter()
LOGIN_MAX_BODY_BYTES = 8 * 1024
_secret_path = None
_secret_value = None


def _secret():
    global _secret_path, _secret_value
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "session_secret"
    if path == _secret_path:
        return _secret_value
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    path.chmod(0o600)
    _secret_path, _secret_value = path, path.read_text().strip().encode()
    return _secret_value


def _generation():
    try:
        return int((DATA_DIR / "session_generation").read_text().strip())
    except (OSError, ValueError):
        return 0


def _rotate_generation():
    # 单管理员模型：logout 轮换全局 generation 使所有已签发 session 立即失效，并发轮换竞争无害
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "session_generation"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(str(_generation() + 1))
    temporary.chmod(0o600)
    os.replace(temporary, path)


def _token(csrf):
    expires = str(int(time.time()) + 86400)
    value = f"{expires}.{csrf}.{_generation()}"
    signature = hmac.new(_secret(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def _authenticated(request):
    try:
        expires, csrf, generation, signature = request.cookies.get("session", "").split(".", 3)
        expected = hmac.new(_secret(), f"{expires}.{csrf}.{generation}".encode(), hashlib.sha256).hexdigest()
        return (int(expires) > time.time() and generation == str(_generation())
                and hmac.compare_digest(signature, expected))
    except (ValueError, AttributeError, TypeError):
        return False


@router.get("/api/session")
def session(request: Request):
    authenticated = _authenticated(request)
    csrf = request.cookies.get("session", "").split(".", 2)[1] if authenticated else ""
    return {"authenticated": authenticated, "csrf_token": csrf}


def _client_ip(request):
    host = request.client.host if request.client else None
    peer = str(host).strip() if host else "unknown"
    try:
        trusted_proxy = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        trusted_proxy = False
    if not trusted_proxy:
        return peer

    headers = {str(key).lower(): value for key, value in request.headers.items()}
    values = [headers.get("cf-connecting-ip"), headers.get("x-forwarded-for")]
    for index, value in enumerate(values):
        value = str(value or "").strip()
        if not value:
            continue
        try:
            addresses = value.split(",") if index == 1 else [value]
            parsed = [ipaddress.ip_address(address.strip()) for address in addresses]
            return str(parsed[0])
        except ValueError:
            continue
    return peer


@router.post("/api/login")
async def login(request: Request, response: Response):
    values = _env()
    salt, expected = values.get("ADMIN_PASSWORD_SALT"), values.get("ADMIN_PASSWORD_HASH")
    if not salt or not expected:
        raise HTTPException(503, "服务器尚未设置管理员密码哈希")
    key = _client_ip(request)
    if login_limited(key):
        raise HTTPException(429, "登录失败次数过多，请5分钟后重试")
    body = await read_bounded_json(request, LOGIN_MAX_BODY_BYTES, "登录")
    if not password_matches(str(body.get("password", "")), salt, expected):
        record_login_failure(key)
        raise HTTPException(401, "密码错误")
    clear_login_failures(key)
    csrf = secrets.token_urlsafe(24)
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie("session", _token(csrf), httponly=True, secure=secure,
                        samesite="strict", max_age=86400)
    return {"ok": True}


@router.post("/api/logout")
def logout(response: Response):
    _rotate_generation()
    response.delete_cookie("session", path="/", httponly=True, samesite="strict")
    return {"ok": True}
