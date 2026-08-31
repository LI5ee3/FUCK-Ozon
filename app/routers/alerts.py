from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..alerts import (acknowledge_alert, alert_summary, evaluate_alerts, get_alert_rules,
                      list_alert_events, update_alert_rule)
from .common import read_bounded_json


router = APIRouter()
JSON_MAX_BODY_BYTES = 16 * 1024


def _alert_shop_id(value=0):
    if type(value) not in (int, str):
        raise HTTPException(400, "shop_id无效")
    try:
        shop_id = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(400, "shop_id无效") from error
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    return shop_id


@router.get("/api/alerts")
def alerts(shop_id: int = 0, status: str = "open", severity: str = "", rule_key: str = "",
           category: str = "", q: str = "", page: int = 1, size: int = 50):
    try:
        return list_alert_events(_alert_shop_id(shop_id), status, severity, rule_key, q, page, size, category)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/api/alerts/summary")
def alerts_summary(shop_id: int = 0):
    try:
        return alert_summary(_alert_shop_id(shop_id))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/api/alerts/evaluate")
async def alerts_evaluate(request: Request):
    body = await read_bounded_json(request, JSON_MAX_BODY_BYTES, "告警")
    try:
        shop_id = _alert_shop_id((body or {}).get("shop_id", 0))
        return await run_in_threadpool(evaluate_alerts, shop_id)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/api/alerts/{alert_id}/acknowledge")
def alert_acknowledge(alert_id: int):
    try:
        return acknowledge_alert(alert_id)
    except (LookupError, ValueError) as error:
        raise HTTPException(404 if isinstance(error, LookupError) else 400, str(error)) from error


@router.get("/api/alert-rules")
def alert_rules(shop_id: int = 0):
    try:
        return get_alert_rules(_alert_shop_id(shop_id))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.put("/api/alert-rules/{rule_key}")
async def alert_rule_update(rule_key: str, request: Request):
    try:
        return update_alert_rule(rule_key, await read_bounded_json(request, JSON_MAX_BODY_BYTES, "告警"))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
