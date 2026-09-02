from fastapi import APIRouter, HTTPException

from ..pricing import get_pricing
from ..pricing_strategy import PricingStrategyNotFound, get_pricing_strategy


router = APIRouter()


@router.get("/api/pricing")
def pricing(shop_id: int = 0, q: str = "", channel: str = "FBP", health: str = "",
            target_margin_pct: str = "20", sort_by: str = "", sort_order: str = "desc",
            page: int = 1, size: int = 50):
    try:
        return get_pricing(shop_id, q, channel, health, target_margin_pct,
                           sort_by, sort_order, page, size)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/api/pricing/strategy")
def pricing_strategy(shop_id: int = 0, snapshot_key: str = "", channel: str = "FBP",
                     target_margin_pct: str = "20", history_days: int = 90):
    try:
        return get_pricing_strategy(shop_id, snapshot_key, channel, target_margin_pct, history_days)
    except PricingStrategyNotFound as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
