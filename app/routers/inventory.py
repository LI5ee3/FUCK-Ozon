from fastapi import APIRouter, HTTPException

from ..inventory import get_stock


router = APIRouter()


def _stock_response(**params):
    try:
        return get_stock(**params)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/api/stock")
def stock(shop_id: int = 0, page: int = 1, size: int = 50, sku: str = "",
          offer_id: str = "", product_name: str = "", sort_by: str = "",
          sort_order: str = "desc", channel: str = "", risk: str = "", q: str = ""):
    return _stock_response(shop_id=shop_id, page=page, size=size, sku=sku, offer_id=offer_id,
                           product_name=product_name, sort_by=sort_by, sort_order=sort_order,
                           channel=channel, risk=risk, q=q)


@router.get("/api/inventory/forecast")
def inventory_forecast(shop_id: int = 0, page: int = 1, size: int = 50, q: str = "", channel: str = "",
                       risk: str = "", sort: str = "", sort_order: str = "desc"):
    return _stock_response(shop_id=shop_id, page=page, size=size, q=q, channel=channel, risk=risk,
                           sort_by=sort, sort_order=sort_order)
