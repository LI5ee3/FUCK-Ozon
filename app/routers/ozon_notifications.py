from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..ozon.client import (notification_check, notification_delete, notification_enable,
                           notification_list, notification_set, push_type_list)
from ..ozon.mappings import PUSH_EVENT_TYPES
from .common import read_bounded_json


router = APIRouter()
JSON_MAX_BODY_BYTES = 16 * 1024


def _admin_shop(body):
    try:
        if type(body.get("shop_id")) not in (int, str):
            raise HTTPException(400, "shop_id无效")
        shop_id = int(body.get("shop_id"))
    except (AttributeError, TypeError, ValueError, OverflowError) as error:
        raise HTTPException(400, "shop_id无效") from error
    if shop_id not in (1, 2):
        raise HTTPException(400, "未知店铺")
    return shop_id


def _notification_id(value):
    if type(value) not in (int, str):
        raise HTTPException(400, "通知ID无效")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(400, "通知ID无效") from error


async def _ozon_management_call(function, *args):
    try:
        return await run_in_threadpool(function, *args)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/api/ozon/notifications/push-types")
async def ozon_push_types(shop_id: int):
    if shop_id not in (1, 2):
        raise HTTPException(400, "未知店铺")
    return await _ozon_management_call(push_type_list, shop_id)


@router.post("/api/ozon/notifications/check")
async def ozon_notification_check(request: Request):
    body = await read_bounded_json(request, JSON_MAX_BODY_BYTES, "通知订阅")
    shop_id = _admin_shop(body)
    url = str(body.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "url不能为空")
    return await _ozon_management_call(notification_check, shop_id, url)


@router.post("/api/ozon/notifications/set")
async def ozon_notification_set(request: Request):
    body = await read_bounded_json(request, JSON_MAX_BODY_BYTES, "通知订阅")
    shop_id = _admin_shop(body)
    url = str(body.get("url") or "").strip()
    types = body.get("types") or PUSH_EVENT_TYPES
    if not url or not isinstance(types, (list, tuple)) or not all(isinstance(value, str) and value for value in types):
        raise HTTPException(400, "url或types无效")
    return await _ozon_management_call(notification_set, shop_id, url, types)


@router.post("/api/ozon/notifications/list")
async def ozon_notification_list(request: Request):
    return await _ozon_management_call(notification_list, _admin_shop(await read_bounded_json(request, JSON_MAX_BODY_BYTES, "通知订阅")))


@router.post("/api/ozon/notifications/enable")
async def ozon_notification_enable(request: Request):
    body = await read_bounded_json(request, JSON_MAX_BODY_BYTES, "通知订阅")
    shop_id = _admin_shop(body)
    notification_id = _notification_id(body.get("id"))
    if "enabled" not in body and "enable" not in body:
        raise HTTPException(400, "缺少 enabled")
    enabled = body.get("enabled", body.get("enable"))
    if type(enabled) is not bool:
        raise HTTPException(400, "enabled必须是布尔值")
    return await _ozon_management_call(notification_enable, shop_id, notification_id, enabled)


@router.post("/api/ozon/notifications/delete")
async def ozon_notification_delete(request: Request):
    body = await read_bounded_json(request, JSON_MAX_BODY_BYTES, "通知订阅")
    shop_id = _admin_shop(body)
    notification_id = _notification_id(body.get("id"))
    return await _ozon_management_call(notification_delete, shop_id, notification_id)
