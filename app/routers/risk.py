from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..db import connect
from ..ozon.mappings import CANCEL_REASON_ZH
from ..products import load_product_rules, resolve_product
from .common import ACTIVE, _overview_range, _shop_clause


router = APIRouter()
BUYER_UNCLAIMED_REASONS = (
    "Покупатель не забрал заказ",
    "Покупатель отменил заказ",
    "Покупатель отменил заказ: не устроил срок доставки",
    "Покупатель отказался при вручении: товар не подошел",
    "Покупатель отменил заказ: нашел дешевле",
)
RISK_REASON_ZH = CANCEL_REASON_ZH


@router.get("/api/risk")
def risk(shop_id: int = 0, grouped: bool = False,
         date_from: Annotated[str | None, Query(alias="from")] = None,
         date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    start, end, utc_start, utc_end = _overview_range(date_from, date_to)
    clause, args = _shop_clause(shop_id)
    unclaimed = ",".join("?" for _ in BUYER_UNCLAIMED_REASONS)
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,s.name shop_name,o.channel,i.sku,i.offer_id,i.product_name_raw,
            SUM(i.quantity) valid_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 THEN i.quantity ELSE 0 END) cancelled_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 AND o.cancel_reason_raw IN ({unclaimed}) THEN i.quantity ELSE 0 END) unclaimed_pieces,
            SUM(CASE WHEN o.status_raw='已取消' AND o.shipped=1 AND o.cancel_reason_raw='Отправление не прошло таможенное оформление' THEN i.quantity ELSE 0 END) customs_pieces
          FROM orders o JOIN shops s ON s.id=o.shop_id JOIN order_items i USING(shop_id,posting_number)
          WHERE {ACTIVE} AND o.created_at>=?
            AND o.created_at<?{clause}
          GROUP BY o.shop_id,o.channel,i.sku,i.offer_id,i.product_name_raw
        """, [*BUYER_UNCLAIMED_REASONS, utc_start, utc_end, *args])]
        rules = load_product_rules(db)

    for row in rows:
        row["resolved"] = resolve_product(rules, row["sku"], row["offer_id"], row["product_name_raw"])
        row["item_key"] = row["resolved"]["identity"]

    def stats(values):
        result = {key: sum(int(row[f"{key}_pieces"] or 0) for row in values)
                  for key in ("valid", "cancelled", "unclaimed", "customs")}
        for key in ("cancelled", "unclaimed", "customs"):
            result[f"{key}_rate"] = result[key] / result["valid"] if result["valid"] else None
        return result

    grouped = {}
    for row in rows:
        item = grouped.setdefault((row["shop_id"], row["item_key"]), {"rows": [], "channels": {}})
        item["rows"].append(row)
        item["channels"].setdefault(row["channel"], []).append(row)

    items = []
    for item_key in sorted(grouped):
        group = grouped[item_key]
        values = group["rows"]
        skus = sorted({row["sku"] for row in values if row["sku"]})
        offers = sorted({row["offer_id"] for row in values if row["offer_id"]})
        resolved = values[0]["resolved"]
        items.append({"shop_id": values[0]["shop_id"], "shop_name": values[0]["shop_name"],
                      "item_key": item_key[1], "sku": skus[0] if len(skus) == 1 else "、".join(skus),
                      "primary_offer_id": resolved["primary_offer_id"], "member_count": len(skus),
                      "product_name": resolved["display_name"],
                      "search_text": " ".join(skus + offers + [resolved["display_name"]] +
                                                [row["product_name_raw"] or "" for row in values]),
                      "total": stats(values),
                      "channels": {channel: stats(group["channels"][channel])
                                   if channel in group["channels"] else None
                                   for channel in ("FBP", "realFBS", "WHD")}})
    items.sort(key=lambda row: (-row["total"]["cancelled"], -row["total"]["valid"],
                                row["shop_id"], row["item_key"]))
    return {"range": {"from": start.isoformat(), "to": end.isoformat()}, "summary": stats(rows),
            "items": items}


@router.get("/api/risk/reasons")
def risk_reasons(shop_id: int = 0, reason: str = "",
                 date_from: Annotated[str | None, Query(alias="from")] = None,
                 date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    start, end, utc_start, utc_end = _overview_range(date_from, date_to)
    clause, args = _shop_clause(shop_id)
    extra = ""
    if reason:
        extra = " AND COALESCE(NULLIF(o.cancel_reason_raw,''),'原因暂缺')=?"; args.append(reason)
    with connect() as db:
        rows = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,o.channel,
          COALESCE(NULLIF(o.cancel_reason_raw,''),'原因暂缺') reason_raw,
          COUNT(DISTINCT o.posting_number) orders,SUM(i.quantity) pieces
          FROM orders o JOIN shops s ON s.id=o.shop_id JOIN order_items i USING(shop_id,posting_number)
          WHERE o.status_raw='已取消' AND o.shipped=1 AND o.created_at>=?
            AND o.created_at<?{clause}{extra}
          GROUP BY o.shop_id,o.channel,reason_raw ORDER BY pieces DESC""", [utc_start, utc_end, *args])]
        details = [dict(row) for row in db.execute(f"""SELECT o.shop_id,s.name shop_name,o.channel,
          o.posting_number,SUM(i.quantity) pieces FROM orders o JOIN shops s ON s.id=o.shop_id
          JOIN order_items i USING(shop_id,posting_number)
          WHERE o.status_raw='已取消' AND o.shipped=1 AND o.created_at>=?
            AND o.created_at<?{clause}{extra}
          GROUP BY o.shop_id,o.channel,o.posting_number ORDER BY o.posting_number""",
          [utc_start, utc_end, *args])] if reason else []
    grouped = {}
    for row in rows:
        reason = grouped.setdefault(row["reason_raw"], {"rows": [], "channels": {}})
        reason["rows"].append(row)
        reason["channels"].setdefault(row["channel"], []).append(row)

    items = []
    for reason_raw in sorted(grouped):
        group = grouped[reason_raw]
        values = group["rows"]
        items.append({"reason_raw": reason_raw,
                      "reason_name": RISK_REASON_ZH.get(reason_raw, reason_raw),
                      "total": {"orders": sum(row["orders"] for row in values),
                                "pieces": sum(row["pieces"] for row in values)},
                      "channels": {channel: {"orders": sum(row["orders"] for row in group["channels"].get(channel, [])),
                                             "pieces": sum(row["pieces"] for row in group["channels"].get(channel, []))}
                                   for channel in ("FBP", "realFBS", "WHD")}})
    items.sort(key=lambda row: (-row["total"]["pieces"], row["reason_raw"]))
    return {"range": {"from": start.isoformat(), "to": end.isoformat()},
            "items": items, "details": details}
