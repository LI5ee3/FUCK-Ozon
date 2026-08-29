from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..db import connect
from ..importer import CHANNELS
from ..products import load_product_rules, resolve_product
from .common import _overview_range, _translated_order


router = APIRouter()


@router.get("/api/orders")
def orders(shop_id: int = 0, channel: str = "", q: str = "", page: int = 1, size: int = 30,
           date_from: Annotated[str | None, Query(alias="from")] = None,
           date_to: Annotated[str | None, Query(alias="to")] = None,
           status: str = ""):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    where, args = ["o.created_at>=?", "o.created_at<?"], [utc_start, utc_end]
    if shop_id in (1, 2):
        where.append("o.shop_id=?"); args.append(shop_id)
    if channel:
        if channel not in CHANNELS: raise HTTPException(400, "未知渠道")
        where.append("o.channel=?"); args.append(channel)
    if q:
        where.append("(o.posting_number LIKE ? OR EXISTS(SELECT 1 FROM order_items x WHERE x.shop_id=o.shop_id AND x.posting_number=o.posting_number AND (x.sku LIKE ? OR x.offer_id LIKE ? OR x.product_name_raw LIKE ?)))")
        args.extend([f"%{q}%"] * 4)

    base_where_sql = " AND ".join(where)
    base_args = list(args)

    if status == "pending":
        where.append("o.status_raw IN ('待备货', '等待发运', '待发货', 'awaiting_packaging', 'awaiting_deliver')")
    elif status == "shipping":
        where.append("o.status_raw IN ('运输中', 'delivering', 'driver_pickup')")
    elif status == "delivered":
        where.append("o.status_raw IN ('已签收', 'delivered')")
    elif status == "cancelled":
        where.append("o.status_raw IN ('已取消', 'cancelled')")
    elif status == "cancelled_shipped":
        where.append("o.status_raw IN ('已取消', 'cancelled') AND o.shipped=1")
    elif status == "anomaly":
        where.append("o.data_anomaly=1")

    page, size = max(page, 1), min(max(size, 1), 100)
    sql_where = " AND ".join(where)
    with connect() as db:
        rules = load_product_rules(db)
        total = db.execute(f"SELECT COUNT(*) FROM orders o WHERE {sql_where}", args).fetchone()[0]

        # Calculate status breakdown for chips
        count_rows = db.execute(f"""
          SELECT o.status_raw, o.shipped, o.data_anomaly, COUNT(*) c
          FROM orders o WHERE {base_where_sql}
          GROUP BY o.status_raw, o.shipped, o.data_anomaly
        """, base_args).fetchall()
        status_counts = {"all": 0, "pending": 0, "shipping": 0, "delivered": 0, "cancelled": 0, "cancelled_shipped": 0, "anomaly": 0}
        for r in count_rows:
            raw, shipped, anomaly, cnt = r["status_raw"], r["shipped"], r["data_anomaly"], r["c"]
            status_counts["all"] += cnt
            if anomaly:
                status_counts["anomaly"] += cnt
            if raw in ("待备货", "等待发运", "待发货", "awaiting_packaging", "awaiting_deliver"):
                status_counts["pending"] += cnt
            elif raw in ("运输中", "delivering", "driver_pickup"):
                status_counts["shipping"] += cnt
            elif raw in ("已签收", "delivered"):
                status_counts["delivered"] += cnt
            elif raw in ("已取消", "cancelled"):
                status_counts["cancelled"] += cnt
                if shipped:
                    status_counts["cancelled_shipped"] += cnt

        result = [_translated_order(row) for row in db.execute(f"""
          SELECT o.shop_id,s.name shop_name,o.posting_number,o.channel,o.created_at,o.shipped_at,o.delivered_at,
            o.status_raw,o.cancel_reason_raw,o.shipped,o.data_anomaly,o.amount_original,o.amount_currency
          FROM orders o JOIN shops s ON s.id=o.shop_id
          WHERE {sql_where} ORDER BY o.created_at DESC LIMIT ? OFFSET ?
        """, args + [size, (page - 1) * size])]
        items = {}
        if result:
            marks = ",".join("(?,?)" for _ in result)
            keys = [value for order in result for value in (order["shop_id"], order["posting_number"])]
            for row in db.execute(f"""SELECT shop_id,posting_number,sku,offer_id,product_name_raw,
              product_name_raw product_name_original,quantity,unit_price,price_currency FROM order_items
              WHERE (shop_id,posting_number) IN ({marks}) ORDER BY shop_id,posting_number,sku""", keys):
                items.setdefault((row["shop_id"], row["posting_number"]), []).append(dict(row))
        for order in result:
            order["items"] = items.get((order["shop_id"], order["posting_number"]), [])
            for item in order["items"]:
                item["product_name_raw"] = resolve_product(
                    rules, item["sku"], item["offer_id"], item["product_name_original"])["display_name"]
            order["sku_types"] = len(order["items"])
            order["pieces"] = sum(item["quantity"] for item in order["items"])
    return {"items": result, "total": total, "page": page, "size": size, "status_counts": status_counts}
