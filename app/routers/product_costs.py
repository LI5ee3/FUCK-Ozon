from fastapi import APIRouter, HTTPException, Request

from ..product_costs import (list_product_forecast_cost_history, list_product_forecast_costs,
                             save_product_forecast_cost)
from .common import read_bounded_json


router = APIRouter()
JSON_MAX_BODY_BYTES = 64 * 1024


@router.get("/api/product-costs")
def product_costs(q: str = "", page: int = 1, size: int = 50):
    try:
        return list_product_forecast_costs(q, page, size)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.put("/api/product-costs")
async def save_product_costs(request: Request):
    try:
        return save_product_forecast_cost(await read_bounded_json(request, JSON_MAX_BODY_BYTES, "预测成本"))
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/api/product-costs/history")
def product_cost_history(sku: str = "", offer_id: str = "", product_identity: str = "", limit: int = 50):
    try:
        return list_product_forecast_cost_history(sku=sku, offer_id=offer_id,
                                                  product_identity=product_identity, limit=limit)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
