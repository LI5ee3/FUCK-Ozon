import hmac
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..ozon.client import _env
from ..ozon.webhooks import process_webhook_event, webhook_validation_error
from .common import _utc_text


router = APIRouter()
WEBHOOK_MAX_BODY_BYTES = 1024 * 1024


def _webhook_shop_id(secret):
    values = _env()
    matches = []
    for shop_id in (1, 2):
        expected = str(values.get(f"OZON_WEBHOOK_SECRET_{shop_id}") or "")
        if expected and hmac.compare_digest(str(secret), expected):
            matches.append(shop_id)
    if len(matches) != 1:
        raise HTTPException(403, "Webhook密钥无效")
    return matches[0]


def _validate_webhook_seller(shop_id, payload):
    if "seller_id" not in payload or payload["seller_id"] in (None, ""):
        return
    values = _env()
    expected = values.get(f"SHOP_{shop_id}_OZON_SELLER_ID") or values.get(f"SHOP_{shop_id}_OZON_CLIENT_ID")
    if not expected or str(payload["seller_id"]).strip() != str(expected).strip():
        raise HTTPException(403, "Webhook店铺身份无效")


async def _read_webhook_json(request):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > WEBHOOK_MAX_BODY_BYTES:
                raise HTTPException(413, "Webhook请求体过大")
        except ValueError as error:
            raise HTTPException(400, "Content-Length无效") from error
    chunks, size = [], 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > WEBHOOK_MAX_BODY_BYTES:
                raise HTTPException(413, "Webhook请求体过大")
            chunks.append(chunk)
        raw = b"".join(chunks)
    except AttributeError:
        raw = await request.body()
        if len(raw) > WEBHOOK_MAX_BODY_BYTES:
            raise HTTPException(413, "Webhook请求体过大")
    try:
        payload = json.loads(raw.decode("utf-8"), parse_constant=_invalid_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(400, "Webhook JSON无效") from error
    if not isinstance(payload, dict):
        raise HTTPException(400, "Webhook JSON必须是对象")
    return payload


def _invalid_json_constant(value):
    raise ValueError(f"非法 JSON 常量: {value}")


@router.post("/api/webhooks/ozon/{secret}")
async def ozon_webhook(secret: str, request: Request):
    shop_id = _webhook_shop_id(secret)
    payload = await _read_webhook_json(request)
    _validate_webhook_seller(shop_id, payload)
    message_type = str(payload.get("message_type") or "").strip()
    if message_type == "TYPE_PING":
        return {"version": "1.0.0", "name": "oPanel", "time": _utc_text(datetime.now(timezone.utc))}
    error = webhook_validation_error(payload)
    if error:
        raise HTTPException(400, error)
    process_webhook_event(shop_id, payload, _utc_text(datetime.now(timezone.utc)))
    return {"result": True}
