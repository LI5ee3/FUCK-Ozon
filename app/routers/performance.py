import math
import sqlite3
from datetime import date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from ..db import connect
from ..performance import PerformanceConfigurationError, list_campaigns
from ..sync_jobs import _run_performance_campaign_sync, _run_performance_statistics_sync
from .common import _paging


router = APIRouter()


def _performance_shop_id(value):
    text = str(value or "").strip().lower()
    if text in ("1", "shop_1"):
        return 1
    if text in ("2", "shop_2"):
        return 2
    raise HTTPException(400, "请选择有效店铺")
@router.post("/api/performance/test")
async def performance_test(request: Request):
    shop_id = _performance_shop_id((await request.json()).get("shop_id"))
    try:
        campaigns = await run_in_threadpool(list_campaigns, shop_id)
    except PerformanceConfigurationError as error:
        raise HTTPException(400, str(error)) from error
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error
    return {"success": True, "shop_id": shop_id, "campaign_count": len(campaigns)}


@router.post("/api/performance/campaigns/sync")
async def performance_campaign_sync(request: Request):
    shop_id = _performance_shop_id((await request.json()).get("shop_id"))
    try:
        return await run_in_threadpool(_run_performance_campaign_sync, shop_id)
    except sqlite3.IntegrityError as error:
        raise HTTPException(409, "该店铺的同模块拉取任务正在运行") from error
    except PerformanceConfigurationError as error:
        raise HTTPException(400, str(error)) from error
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.get("/api/performance/campaigns")
def performance_campaigns(shop_id: str = "0"):
    value = str(shop_id or "0").strip().lower()
    selected = 0 if value in ("0", "all") else _performance_shop_id(value)
    with connect() as db:
        if selected:
            rows = db.execute("""SELECT a.*,s.name shop_name FROM ad_campaigns a
              JOIN shops s ON s.id=a.shop_id WHERE a.shop_id=?
              ORDER BY a.campaign_id""", (selected,)).fetchall()
        else:
            rows = db.execute("""SELECT a.*,s.name shop_name FROM ad_campaigns a
              JOIN shops s ON s.id=a.shop_id ORDER BY a.shop_id,a.campaign_id""").fetchall()
    return [dict(row) for row in rows]


def _performance_range(date_from=None, date_to=None):
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    try:
        end = date.fromisoformat(str(date_to)) if date_to else today
        start = date.fromisoformat(str(date_from)) if date_from else end - timedelta(days=6)
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "日期格式必须为 YYYY-MM-DD") from error
    if start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    return start, end


def _performance_filter_shop(value):
    text = str(value or "0").strip().lower()
    return 0 if text in ("", "0", "all") else _performance_shop_id(text)


AD_BASE_FIELDS = ("impressions", "clicks", "cart_adds", "spend_rub", "orders", "revenue_rub")


def _ad_number(value):
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _ad_summary(row):
    values = {field: _ad_number(row.get(field)) for field in AD_BASE_FIELDS}
    values["impressions"] = int(values["impressions"])
    values["clicks"] = int(values["clicks"])
    values["cart_adds"] = int(values["cart_adds"])
    values["orders"] = int(values["orders"])
    values["spend_rub"] = round(values["spend_rub"], 2)
    values["revenue_rub"] = round(values["revenue_rub"], 2)
    values["ctr"] = round(values["clicks"] / values["impressions"] * 100, 4) if values["impressions"] else None
    values["avg_cpc_rub"] = round(values["spend_rub"] / values["clicks"], 4) if values["clicks"] else None
    values["drr"] = round(values["spend_rub"] / values["revenue_rub"] * 100, 4) if values["revenue_rub"] else None
    values["roas"] = round(values["revenue_rub"] / values["spend_rub"], 4) if values["spend_rub"] else None
    return values


def _ad_add(target, row):
    for field in AD_BASE_FIELDS:
        target[field] = target.get(field, 0) + _ad_number(row.get(field))


def _ad_sort(rows, sort, order):
    sort = str(sort or "spend_rub").strip().lower()
    aliases = {"spend": "spend_rub", "revenue": "revenue_rub", "cpc": "avg_cpc_rub",
               "campaigns": "campaign_count"}
    sort = aliases.get(sort, sort)
    allowed = {"name", "sku", "spend_rub", "revenue_rub", "orders", "impressions", "clicks",
               "ctr", "avg_cpc_rub", "drr", "roas", "campaign_count"}
    if sort not in allowed:
        sort = "spend_rub"
    present = [row for row in rows if row.get(sort) is not None]
    missing = [row for row in rows if row.get(sort) is None]
    present.sort(key=lambda row: str(row.get(sort)).lower() if sort in {"name", "sku"} else row.get(sort),
                 reverse=str(order or "desc").lower() == "desc")
    return present + missing


def _date_query_values(date_from, date_to, from_date, to_date):
    return _performance_range(date_from or from_date, date_to or to_date)


@router.get("/api/performance/overview")
def performance_overview(shop_id: str = "0", date_from: str | None = None, date_to: str | None = None,
                         from_date: Annotated[str | None, Query(alias="from")] = None,
                         to_date: Annotated[str | None, Query(alias="to")] = None):
    selected = _performance_filter_shop(shop_id)
    start, end = _date_query_values(date_from, date_to, from_date, to_date)
    with connect() as db:
        rows = [dict(row) for row in db.execute("""
          SELECT d.shop_id,s.name shop_name,d.stat_date,
            SUM(COALESCE(d.impressions,0)) impressions,SUM(COALESCE(d.clicks,0)) clicks,
            SUM(COALESCE(d.cart_adds,0)) cart_adds,SUM(COALESCE(d.spend_rub,0)) spend_rub,
            SUM(COALESCE(d.orders,0)) orders,SUM(COALESCE(d.revenue_rub,0)) revenue_rub
          FROM ad_campaign_daily d JOIN shops s ON s.id=d.shop_id
          WHERE d.stat_date BETWEEN ? AND ? AND (?=0 OR d.shop_id=?)
          GROUP BY d.shop_id,d.stat_date ORDER BY d.stat_date,d.shop_id""",
            (start.isoformat(), end.isoformat(), selected, selected))]
        shop_rows = [dict(row) for row in db.execute("SELECT id,name FROM shops ORDER BY id")]
    by_date, by_shop = {}, {}
    for row in rows:
        by_date.setdefault(row["stat_date"], {})
        _ad_add(by_date[row["stat_date"]], row)
        by_shop.setdefault(row["shop_id"], {"shop_id": row["shop_id"], "shop_name": row["shop_name"]})
        _ad_add(by_shop[row["shop_id"]], row)
    zero = {field: 0 for field in AD_BASE_FIELDS}
    summary_base = dict(zero)
    for row in rows:
        _ad_add(summary_base, row)
    trend = [{"date": current.isoformat(), **_ad_summary(by_date.get(current.isoformat(), zero))}
             for index in range((end - start).days + 1)
             for current in [start + timedelta(days=index)]]
    shops = []
    for shop in shop_rows:
        if selected and shop["id"] != selected:
            continue
        shops.append({"shop_id": shop["id"], "shop_name": shop["name"],
                      **_ad_summary(by_shop.get(shop["id"], zero))})
    summary = _ad_summary(summary_base)
    return {"shop_id": selected, "date_from": start.isoformat(), "date_to": end.isoformat(),
            **summary, "summary": summary, "trend": trend, "shops": shops,
            "data_through": max((row["stat_date"] for row in rows), default=None)}


@router.get("/api/performance/campaign-stats")
def performance_campaign_stats(shop_id: str = "0", state: str = "", sort: str = "spend_rub",
                               order: str = "desc", page: int = 1, size: int = 100,
                               date_from: str | None = None, date_to: str | None = None,
                               from_date: Annotated[str | None, Query(alias="from")] = None,
                               to_date: Annotated[str | None, Query(alias="to")] = None):
    selected = _performance_filter_shop(shop_id)
    start, end = _date_query_values(date_from, date_to, from_date, to_date)
    page, size = _paging(page, size)
    state = "" if str(state or "").lower() in {"", "all"} else str(state).strip()
    with connect() as db:
        rows = [dict(row) for row in db.execute("""
          SELECT c.shop_id,s.name shop_name,c.campaign_id,c.name,c.state,c.payment_type,
            c.adv_object_type,c.placement,c.weekly_budget,
            COALESCE(d.impressions,0) impressions,COALESCE(d.clicks,0) clicks,
            COALESCE(d.cart_adds,0) cart_adds,COALESCE(d.spend_rub,0) spend_rub,
            COALESCE(d.orders,0) orders,COALESCE(d.revenue_rub,0) revenue_rub,d.data_through
          FROM ad_campaigns c JOIN shops s ON s.id=c.shop_id
          LEFT JOIN (
            SELECT shop_id,campaign_id,MAX(stat_date) data_through,
              SUM(COALESCE(impressions,0)) impressions,SUM(COALESCE(clicks,0)) clicks,
              SUM(COALESCE(cart_adds,0)) cart_adds,SUM(COALESCE(spend_rub,0)) spend_rub,
              SUM(COALESCE(orders,0)) orders,SUM(COALESCE(revenue_rub,0)) revenue_rub
            FROM ad_campaign_daily WHERE stat_date BETWEEN ? AND ?
            GROUP BY shop_id,campaign_id
          ) d ON d.shop_id=c.shop_id AND d.campaign_id=c.campaign_id
          WHERE (?=0 OR c.shop_id=?) AND (?='' OR c.state=?)
          ORDER BY c.shop_id,c.campaign_id""",
            (start.isoformat(), end.isoformat(), selected, selected, state, state))]
    items = []
    for row in rows:
        item = {key: row[key] for key in ("shop_id", "shop_name", "campaign_id", "name", "state",
                                           "payment_type", "adv_object_type", "placement", "weekly_budget")}
        item.update(_ad_summary(row))
        item["data_through"] = row["data_through"]
        items.append(item)
    items = _ad_sort(items, sort, order)
    total = len(items)
    offset = (page - 1) * size
    return {"items": items[offset:offset + size], "total": total, "page": page, "size": size,
            "date_from": start.isoformat(), "date_to": end.isoformat(),
            "data_through": max((row["data_through"] for row in items if row["data_through"]), default=None)}


@router.get("/api/performance/sku-stats")
def performance_sku_stats(shop_id: str = "0", q: str = "", sort: str = "spend_rub",
                          order: str = "desc", page: int = 1, size: int = 100,
                          date_from: str | None = None, date_to: str | None = None,
                          from_date: Annotated[str | None, Query(alias="from")] = None,
                          to_date: Annotated[str | None, Query(alias="to")] = None):
    selected = _performance_filter_shop(shop_id)
    start, end = _date_query_values(date_from, date_to, from_date, to_date)
    page, size = _paging(page, size)
    with connect() as db:
        rows = [dict(row) for row in db.execute("""
          SELECT d.shop_id,s.name shop_name,d.sku,
            COALESCE(MAX(NULLIF(d.product_name,'')),MAX(NULLIF(p.product_name,''))) product_name,
            COUNT(DISTINCT d.campaign_id) campaign_count,MAX(d.stat_date) data_through,
            SUM(COALESCE(d.impressions,0)) impressions,SUM(COALESCE(d.clicks,0)) clicks,
            SUM(COALESCE(d.cart_adds,0)) cart_adds,SUM(COALESCE(d.spend_rub,0)) spend_rub,
            SUM(COALESCE(d.orders,0)) orders,SUM(COALESCE(d.revenue_rub,0)) revenue_rub
          FROM ad_sku_daily d JOIN shops s ON s.id=d.shop_id
          LEFT JOIN (
            SELECT shop_id,sku,MAX(NULLIF(product_name_raw,'')) product_name
            FROM order_items GROUP BY shop_id,sku
          ) p ON p.shop_id=d.shop_id AND p.sku=d.sku
          WHERE d.stat_date BETWEEN ? AND ? AND (?=0 OR d.shop_id=?)
          GROUP BY d.shop_id,d.sku ORDER BY d.shop_id,d.sku""",
            (start.isoformat(), end.isoformat(), selected, selected))]
    query = str(q or "").strip().lower()
    items = []
    for row in rows:
        if query and query not in str(row["sku"]).lower() and query not in str(row["product_name"] or "").lower():
            continue
        item = {key: row[key] for key in ("shop_id", "shop_name", "sku", "product_name", "campaign_count", "data_through")}
        item.update(_ad_summary(row))
        items.append(item)
    items = _ad_sort(items, sort, order)
    total = len(items)
    offset = (page - 1) * size
    return {"items": items[offset:offset + size], "total": total, "page": page, "size": size,
            "date_from": start.isoformat(), "date_to": end.isoformat(),
            "data_through": max((row["data_through"] for row in items if row["data_through"]), default=None)}



@router.post("/api/performance/statistics/sync")
async def performance_statistics_sync(request: Request):
    body = await request.json()
    shop_id = _performance_shop_id(body.get("shop_id"))
    try:
        start, end = _performance_range(body.get("date_from") or body.get("from"),
                                        body.get("date_to") or body.get("to"))
    except HTTPException:
        raise
    module = str(body.get("module") or "all")
    module = {"daily": "ad_campaign_daily", "campaign_daily": "ad_campaign_daily",
              "sku": "ad_sku_daily"}.get(module, module)
    if module not in {"all", "ad_campaign_daily", "ad_sku_daily"}:
        raise HTTPException(400, "未知广告统计模块")
    try:
        return await run_in_threadpool(_run_performance_statistics_sync, shop_id, start, end, module)
    except sqlite3.IntegrityError as error:
        raise HTTPException(409, "该店铺的同模块拉取任务正在运行") from error
    except PerformanceConfigurationError as error:
        raise HTTPException(400, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error
