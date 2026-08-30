import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..ozon.client import _env
from ..ozon.webhooks import process_webhook_event, webhook_validation_error
from .common import _utc_text, read_bounded_json


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


@router.post("/api/webhooks/ozon/{secret}")
async def ozon_webhook(secret: str, request: Request):
    shop_id = _webhook_shop_id(secret)
    payload = await read_bounded_json(request, WEBHOOK_MAX_BODY_BYTES, "Webhook")
    _validate_webhook_seller(shop_id, payload)
    message_type = str(payload.get("message_type") or "").strip()
    if message_type == "TYPE_PING":
        return {"version": "1.0.0", "name": "oPanel", "time": _utc_text(datetime.now(timezone.utc))}
    error = webhook_validation_error(payload)
    if error:
        raise HTTPException(400, error)
    process_webhook_event(shop_id, payload, _utc_text(datetime.now(timezone.utc)))
    return {"result": True}
