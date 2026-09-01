from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..sku_detail import SkuDetailNotFound, get_sku_detail


router = APIRouter()


@router.get("/api/sku-detail/{sku}")
def sku_detail(sku: str, shop_id: int, date_from: Annotated[str | None, Query(alias="from")] = None,
               date_to: Annotated[str | None, Query(alias="to")] = None):
    try:
        return get_sku_detail(shop_id, sku, date_from, date_to)
    except SkuDetailNotFound as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
