import statistics
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..db import connect
from .common import (ACTIVE, _duration_hours, _overview_range, _paging,
                     _percentile, _shop_clause, _utc_moment)


router = APIRouter()


@router.get("/api/timeliness")
def timeliness(shop_id: int = 0, page: int = 1, size: int = 30, q: str = "",
               date_from: Annotated[str | None, Query(alias="from")] = None,
               date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    start_date, end_date, utc_start, utc_end = _overview_range(date_from, date_to)
    clause, shop_args = _shop_clause(shop_id)
    page, size = _paging(page, size)
    base_where = f"{ACTIVE} AND o.created_at>=? AND o.created_at<?{clause}"
    base_args = [utc_start, utc_end, *shop_args]
    detail_where, detail_args = base_where, list(base_args)
    if q.strip():
        detail_where += " AND o.posting_number LIKE ?"
        detail_args.append(f"%{q.strip()}%")
    with connect() as db:
        all_rows = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,
          o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at
          FROM orders o JOIN shops s ON s.id=o.shop_id WHERE {base_where}
          ORDER BY o.created_at DESC,o.posting_number DESC""", base_args)]
        through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {base_where}", base_args).fetchone()[0]
        total = db.execute(f"SELECT COUNT(*) FROM orders o WHERE {detail_where}", detail_args).fetchone()[0]
        rows = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,
          o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at
          FROM orders o JOIN shops s ON s.id=o.shop_id WHERE {detail_where}
          ORDER BY o.created_at DESC,o.posting_number DESC LIMIT ? OFFSET ?""",
          [*detail_args, size, (page - 1) * size])]
    ship_values, delivery_values = [], []
    grouped = {}
    for row in all_rows:
        shipped_moment, delivered_moment = _utc_moment(row["shipped_at"]), _utc_moment(row["delivered_at"])
        if row["channel"] in ("FBP", "realFBS") and delivered_moment and delivered_moment == shipped_moment:
            row["delivered_at"] = None
        ship_hours = _duration_hours(row["created_at"], row["shipped_at"])
        delivery_hours = _duration_hours(row["shipped_at"], row["delivered_at"])
        if ship_hours is not None: ship_values.append(ship_hours)
        if delivery_hours is not None: delivery_values.append(delivery_hours)
        group = grouped.setdefault((row["shop_id"], row["channel"]), {
            "shop_id": row["shop_id"], "shop_name": row["shop_name"], "channel": row["channel"],
            "orders": 0, "created": 0, "shipped": 0, "delivered": 0, "ship": [], "delivery": []})
        group["orders"] += 1
        group["created"] += int(_utc_moment(row["created_at"]) is not None)
        group["shipped"] += int(_utc_moment(row["shipped_at"]) is not None)
        group["delivered"] += int(_utc_moment(row["delivered_at"]) is not None)
        if ship_hours is not None: group["ship"].append(ship_hours)
        if delivery_hours is not None: group["delivery"].append(delivery_hours)
    summary = {"orders": len(all_rows), "shipped_orders": sum(_utc_moment(row["shipped_at"]) is not None for row in all_rows),
      "delivered_orders": sum(_utc_moment(row["delivered_at"]) is not None for row in all_rows),
      "ship_samples": len(ship_values), "delivery_samples": len(delivery_values),
      "avg_ship_hours": statistics.fmean(ship_values) if ship_values else None,
      "p50_ship_hours": _percentile(ship_values, .5), "p90_ship_hours": _percentile(ship_values, .9),
      "avg_delivery_hours": statistics.fmean(delivery_values) if delivery_values else None,
      "p50_delivery_hours": _percentile(delivery_values, .5), "p90_delivery_hours": _percentile(delivery_values, .9)}
    groups = []
    for group in grouped.values():
        orders_count = group["orders"]
        groups.append({**{k: v for k, v in group.items() if k not in {"ship", "delivery"}},
          "ship_samples": len(group["ship"]), "delivery_samples": len(group["delivery"]),
          "ship_sample_insufficient": 0 < len(group["ship"]) < 30,
          "delivery_sample_insufficient": 0 < len(group["delivery"]) < 30,
          "avg_ship_hours": statistics.fmean(group["ship"]) if group["ship"] else None,
          "p50_ship_hours": _percentile(group["ship"], .5), "p90_ship_hours": _percentile(group["ship"], .9),
          "avg_delivery_hours": statistics.fmean(group["delivery"]) if group["delivery"] else None,
          "p50_delivery_hours": _percentile(group["delivery"], .5), "p90_delivery_hours": _percentile(group["delivery"], .9),
          "created_completeness": group["created"] / orders_count if orders_count else 0,
          "shipped_completeness": group["shipped"] / orders_count if orders_count else 0,
          "delivered_completeness": group["delivered"] / orders_count if orders_count else 0})
    groups.sort(key=lambda value: (value["shop_id"], {"FBP": 0, "realFBS": 1, "WHD": 2}[value["channel"]]))
    for row in rows:
        shipped_moment, delivered_moment = _utc_moment(row["shipped_at"]), _utc_moment(row["delivered_at"])
        if row["channel"] in ("FBP", "realFBS") and delivered_moment and delivered_moment == shipped_moment:
            row["delivered_at"] = None
        row["ship_hours"] = _duration_hours(row["created_at"], row["shipped_at"])
        row["delivery_hours"] = _duration_hours(row["shipped_at"], row["delivered_at"])
        row["ship_anomaly"] = bool(row["shipped_at"]) and row["ship_hours"] is None
        row["delivery_anomaly"] = bool(row["delivered_at"]) and row["delivery_hours"] is None
    return {"range": {"from": start_date.isoformat(), "to": end_date.isoformat()},
            "summary": summary, "items": rows, "total": total, "page": page, "size": size,
            "groups": groups, "data_through": through}
