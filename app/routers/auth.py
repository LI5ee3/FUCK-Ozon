import hashlib
import hmac
import ipaddress
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response

from ..db import DATA_DIR
from ..ozon.client import _env
from ..security import (clear_login_failures, login_limited, password_matches,
                        record_login_failure)


router = APIRouter()


def _secret():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "session_secret"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip().encode()


def _token(csrf):
    expires = str(int(time.time()) + 86400)
    value = f"{expires}.{csrf}"
    signature = hmac.new(_secret(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def _authenticated(request):
    try:
        expires, csrf, signature = request.cookies.get("session", "").split(".", 2)
        expected = hmac.new(_secret(), f"{expires}.{csrf}".encode(), hashlib.sha256).hexdigest()
        return int(expires) > time.time() and hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False


@router.get("/api/session")
def session(request: Request):
    authenticated = _authenticated(request)
    csrf = request.cookies.get("session", "").split(".", 2)[1] if authenticated else ""
    return {"authenticated": authenticated, "csrf_token": csrf}


def _client_ip(request):
    headers = {str(key).lower(): value for key, value in request.headers.items()}
    for header in ("cf-connecting-ip", "x-forwarded-for"):
        for value in str(headers.get(header) or "").split(","):
            try:
                return str(ipaddress.ip_address(value.strip()))
            except ValueError:
                continue
    host = request.client.host if request.client else None
    return str(host).strip() if host else "unknown"


@router.post("/api/login")
async def login(request: Request, response: Response):
    values = _env()
    salt, expected = values.get("ADMIN_PASSWORD_SALT"), values.get("ADMIN_PASSWORD_HASH")
    if not salt or not expected:
        raise HTTPException(503, "服务器尚未设置管理员密码哈希")
    key = _client_ip(request)
    if login_limited(key):
        raise HTTPException(429, "登录失败次数过多，请5分钟后重试")
    body = await request.json()
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
    response.delete_cookie("session", path="/", httponly=True, samesite="strict")
    return {"ok": True}
