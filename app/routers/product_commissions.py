from fastapi import APIRouter, HTTPException

from ..product_commissions import (ProductCommissionInputError, ProductCommissionUnavailable,
                                   get_product_commission)


router = APIRouter()


@router.get("/api/product-commission")
def product_commission(shop_id: int, sku: str):
    try:
        return get_product_commission(shop_id, sku)
    except ProductCommissionInputError as error:
        raise HTTPException(400, str(error)) from error
    except ProductCommissionUnavailable as error:
        raise HTTPException(502, f"Ozon平台佣金获取失败：{str(error)[:300]}") from error
