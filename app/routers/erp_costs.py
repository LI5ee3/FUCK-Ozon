from fastapi import APIRouter, HTTPException

from ..erp_cost_matching import get_erp_cost_coverage, list_erp_cost_issues


router = APIRouter()


@router.get("/api/erp-costs/coverage")
def erp_cost_coverage(shop_id: int):
    try:
        return get_erp_cost_coverage(shop_id)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/api/erp-costs/issues")
def erp_cost_issues(shop_id: int, type: str = "", q: str = "", page: int = 1, size: int = 50):
    try:
        return list_erp_cost_issues(shop_id, issue_type=type, q=q, page=page, size=size)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
