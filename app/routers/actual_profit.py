from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..actual_profit import list_actual_order_profits
from .common import _overview_range, _paging


router = APIRouter()


@router.get("/api/profit/actual/orders")
def actual_order_profits(shop_id: int = 0, q: str = "", page: int = 1, size: int = 50,
                         date_from: Annotated[str | None, Query(alias="from")] = None,
                         date_to: Annotated[str | None, Query(alias="to")] = None):
    if type(shop_id) is not int or shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    page, size = _paging(page, size)
    try:
        return list_actual_order_profits(shop_id, utc_start, utc_end, q, page, size)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
