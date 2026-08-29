from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..exchange import exchange_rate_status, sync_exchange_rates
from .common import _overview_range


router = APIRouter()


@router.get("/api/exchange-rates")
def get_exchange_rate_status():
    return exchange_rate_status()


@router.post("/api/exchange-rates/sync")
async def sync_exchange_rate_data(request: Request):
    body = await request.json()
    start, end, _, _ = _overview_range(body.get("from"), body.get("to"))
    try:
        return await run_in_threadpool(sync_exchange_rates, start, end)
    except (OSError, ValueError) as error:
        raise HTTPException(502, f"汇率拉取失败：{error}") from error
