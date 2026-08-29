from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..db import connect
from ..ozon.analytics import analytics_data, product_queries, product_query_details
from ..ozon.client import BEIJING


router = APIRouter()


def _analytics_range(date_from=None, date_to=None, now=None):
    available_end = (now or datetime.now(BEIJING)).date() - timedelta(days=3)
    if not date_to:
        date_to = available_end.isoformat()
    if not date_from:
        try:
            date_from = (date.fromisoformat(date_to) - timedelta(days=29)).isoformat()
        except (TypeError, ValueError):
            pass
    try:
        end = date.fromisoformat(date_to)
        start = date.fromisoformat(date_from)
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "日期格式必须为 YYYY-MM-DD") from error
    if start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    return start, end


def _analytics_shops(shop_id):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT id,name FROM shops ORDER BY id")
                if not shop_id or row["id"] == shop_id]


def _analytics_sku(sku):
    value = str(sku or "").strip()
    if value and (not value.isdigit() or int(value) <= 0):
        raise HTTPException(400, "SKU必须为正整数")
    return value


def _analytics_row(row, shop):
    values = list(row.get("metrics") or []) + [0] * 6
    dimension = (row.get("dimensions") or [{}])[0]
    return {
        "shop_id": shop["id"], "shop_name": shop["name"],
        "sku": str(dimension.get("id") or ""), "name": dimension.get("name") or "",
        "impressions": values[0], "product_views": values[1], "cart_adds": values[2],
        "unique_visitors": values[3], "ordered_units": values[4], "revenue": values[5],
        "currency": "RUB",
        "view_rate": values[1] / values[0] if values[0] else None,
        "cart_rate": values[2] / values[1] if values[1] else None,
        "order_rate": values[4] / values[2] if values[2] else None,
    }


@router.get("/api/analytics/data")
def get_analytics_data(shop_id: int = 0, sku: str = "", page: int = 1, size: int = 50,
                       date_from: Annotated[str | None, Query(alias="from")] = None,
                       date_to: Annotated[str | None, Query(alias="to")] = None):
    page, size = max(page, 1), min(max(size, 1), 100)
    start, end = _analytics_range(date_from, date_to)
    sku = _analytics_sku(sku)
    shops = _analytics_shops(shop_id)
    items, summaries = [], []
    try:
        for shop in shops:
            result = analytics_data(shop["id"], start.isoformat(), end.isoformat(), sku).get("result") or {}
            rows = [_analytics_row(row, shop) for row in result.get("data") or []]
            items.extend(rows)
            totals = _analytics_row({"dimensions": [{}], "metrics": result.get("totals") or []}, shop)
            totals.pop("sku"); totals.pop("name")
            summaries.append(totals)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error
    items.sort(key=lambda row: (-float(row["impressions"] or 0), row["shop_id"], row["sku"]))
    total, offset = len(items), (page - 1) * size
    return {"shops": summaries, "items": items[offset:offset + size], "total": total,
            "page": page, "size": size, "data_through": end.isoformat()}


@router.get("/api/analytics/product-queries")
def get_product_queries(shop_id: int = 0, sku: str = "", page: int = 1, size: int = 50,
                        date_from: Annotated[str | None, Query(alias="from")] = None,
                        date_to: Annotated[str | None, Query(alias="to")] = None):
    page, size = max(page, 1), min(max(size, 1), 100)
    start, end = _analytics_range(date_from, date_to)
    sku = _analytics_sku(sku)
    shops = _analytics_shops(shop_id)
    date_from_utc, date_to_utc = f"{start.isoformat()}T00:00:00Z", f"{end.isoformat()}T23:59:59Z"
    items = []
    try:
        for shop in shops:
            if sku:
                skus = [int(sku)]
            else:
                source = analytics_data(shop["id"], start.isoformat(), end.isoformat()).get("result") or {}
                skus = [int(row["dimensions"][0]["id"]) for row in source.get("data") or []
                        if row.get("dimensions") and str(row["dimensions"][0].get("id") or "").isdigit()]
            if not skus:
                continue
            # ponytail: Ozon accepts at most 1000 SKUs; keep each request within that ceiling.
            for offset in range(0, len(skus), 1000):
                body = product_queries(shop["id"], date_from_utc, date_to_utc, skus[offset:offset + 1000])
                for row in body.get("items") or []:
                    items.append({"shop_id": shop["id"], "shop_name": shop["name"],
                                  "sku": str(row.get("sku") or ""), "name": row.get("name") or "",
                                  "offer_id": row.get("offer_id") or "", "category": row.get("category") or "",
                                  "position": row.get("position"), "unique_search_users": row.get("unique_search_users"),
                                  "unique_view_users": row.get("unique_view_users"),
                                  "view_conversion": row.get("view_conversion"), "gmv": row.get("gmv"),
                                  "currency": row.get("currency") or ""})
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error
    items.sort(key=lambda row: (-int(row["unique_search_users"] or 0), row["shop_id"], row["sku"]))
    total, offset = len(items), (page - 1) * size
    return {"items": items[offset:offset + size], "total": total, "page": page, "size": size,
            "data_through": end.isoformat()}


@router.get("/api/analytics/product-queries/details")
def get_product_query_details(shop_id: int = 0, sku: str = "", page: int = 1, size: int = 50,
                              date_from: Annotated[str | None, Query(alias="from")] = None,
                              date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (1, 2):
        raise HTTPException(400, "请选择具体店铺")
    page, size = max(page, 1), min(max(size, 1), 100)
    start, end = _analytics_range(date_from, date_to)
    sku = _analytics_sku(sku)
    if not sku:
        raise HTTPException(400, "请选择SKU")
    try:
        body = product_query_details(shop_id, f"{start.isoformat()}T00:00:00Z",
                                     f"{end.isoformat()}T23:59:59Z", [int(sku)], page - 1, size)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error
    with connect() as db:
        shop_name = db.execute("SELECT name FROM shops WHERE id=?", (shop_id,)).fetchone()[0]
    items = [{"shop_id": shop_id, "shop_name": shop_name, "sku": str(row.get("sku") or sku),
              "query": row.get("query") or "", "position": row.get("position"),
              "unique_search_users": row.get("unique_search_users"),
              "unique_view_users": row.get("unique_view_users"),
              "view_conversion": row.get("view_conversion"), "order_count": row.get("order_count"),
              "gmv": row.get("gmv"), "currency": row.get("currency") or ""}
             for row in body.get("queries") or []]
    return {"items": items, "total": int(body.get("total") or len(items)), "page": page,
            "size": size, "data_through": end.isoformat()}
