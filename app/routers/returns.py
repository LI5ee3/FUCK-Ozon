import json
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..db import connect
from ..ozon.mappings import CANCEL_REASON_ZH, RFBS_RETURN_STATUS_ZH, RETURN_STATUS_ZH
from ..products import load_product_rules, resolve_product
from .common import _complaint_deadline, _overview_range, _paging, _with_compensation_conversion


router = APIRouter()


@router.get("/api/returns")
def returns(shop_id: int = 0, page: int = 1, size: int = 50, q: str = "",
            date_from: Annotated[str | None, Query(alias="from")] = None,
            date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    filters, args = ["r.occurred_at>=?", "r.occurred_at<?"], [utc_start, utc_end]
    if shop_id:
        filters.append("r.shop_id=?"); args.append(shop_id)
    if q.strip():
        pattern = f"%{q.strip()}%"
        filters.append("(r.sku LIKE ? OR r.posting_number LIKE ? OR CAST(json_extract(r.payload,'$.product.offer_id') AS TEXT) LIKE ?)")
        args.extend([pattern, pattern, pattern])
    where = " WHERE " + " AND ".join(filters)
    page, size = _paging(page, size)
    with connect() as db:
        totals = [dict(row) for row in db.execute(f"""
          SELECT r.shop_id,s.name shop_name,COUNT(*) records,
            COALESCE(SUM(CAST(json_extract(r.payload,'$.product.quantity') AS INTEGER)),0) quantity
          FROM return_records r JOIN shops s ON s.id=r.shop_id{where}
          GROUP BY r.shop_id ORDER BY r.shop_id
        """, args)]
        total = db.execute(f"SELECT COUNT(*) FROM return_records r{where}", args).fetchone()[0]
        records = db.execute(f"""SELECT r.shop_id,s.name shop_name,r.occurred_at,r.posting_number,r.sku,r.payload,
          o.status_changed_at,
          CAST(json_extract(r.payload,'$.product.offer_id') AS TEXT) offer_id
          FROM return_records r JOIN shops s ON s.id=r.shop_id
          LEFT JOIN orders o ON o.shop_id=r.shop_id AND o.posting_number=r.posting_number{where}
          ORDER BY r.occurred_at DESC LIMIT ? OFFSET ?""", args + [size, (page - 1) * size]).fetchall()
        through = db.execute(f"SELECT MAX(r.occurred_at) FROM return_records r{where}", args).fetchone()[0]
        rules = load_product_rules(db)
    items = []
    for row in records:
        payload = json.loads(row["payload"])
        product, visual = payload.get("product") or {}, payload.get("visual") or {}
        status = visual.get("status") or {}
        status = status.get("display_name") if isinstance(status, dict) else status
        item = {"shop_id": row["shop_id"], "shop_name": row["shop_name"],
                      "occurred_at": row["occurred_at"], "posting_number": row["posting_number"],
                      "sku": row["sku"], "offer_id": row["offer_id"],
                      "product_name": resolve_product(rules, row["sku"], row["offer_id"],
                                                       product.get("name"))["display_name"],
                      "quantity": product.get("quantity"),
                      "reason": CANCEL_REASON_ZH.get(payload.get("return_reason_name"), payload.get("return_reason_name")),
                      "reason_raw": payload.get("return_reason_name"),
                      "status": RETURN_STATUS_ZH.get(status, status),
                      "compensation_status": payload.get("compensation_status") or payload.get("money_return_state_name"),
                      "product_amount": product.get("price") or product.get("amount"),
                      "product_currency": product.get("currency_code") or product.get("currency"),
                      "logistic_return_at": payload.get("logistic_return_at") or payload.get("returned_at"),
                      "buyer_comment_raw": payload.get("buyer_comment") or payload.get("comment"),
                      "type": payload.get("type")}
        item["cancelled_at"] = row["status_changed_at"] or row["occurred_at"]
        item.update(_complaint_deadline(row["status_changed_at"], row["occurred_at"]))
        items.append(item)
    return {"summary": {"records": total, "shops": totals}, "items": items, "total": total,
            "page": page, "size": size, "data_through": through}


@router.get("/api/rfbs-returns")
def rfbs_returns(shop_id: int = 0, page: int = 1, size: int = 50, q: str = "",
                 date_from: Annotated[str | None, Query(alias="from")] = None,
                 date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    filters, args = ["r.created_at>=?", "r.created_at<?"], [utc_start, utc_end]
    if shop_id:
        filters.append("r.shop_id=?"); args.append(shop_id)
    if q.strip():
        pattern = f"%{q.strip()}%"
        filters.append("(r.sku LIKE ? OR r.offer_id LIKE ? OR r.posting_number LIKE ? OR r.return_number LIKE ?)")
        args.extend([pattern] * 4)
    where = " WHERE " + " AND ".join(filters)
    page, size = _paging(page, size)
    with connect() as db:
        totals = [dict(row) for row in db.execute(f"""SELECT r.shop_id,s.name shop_name,COUNT(*) records
          FROM rfbs_return_records r JOIN shops s ON s.id=r.shop_id{where}
          GROUP BY r.shop_id ORDER BY r.shop_id""", args)]
        total = db.execute(f"SELECT COUNT(*) FROM rfbs_return_records r{where}", args).fetchone()[0]
        rows = db.execute(f"""SELECT r.shop_id,s.name shop_name,s.settlement_currency,r.return_id,
          r.return_number,r.created_at,r.posting_number,r.offer_id,r.sku,r.product_name,
          r.status_raw,r.status_name,r.quantity,r.reason_raw,r.reason_name,
          r.compensation_status,r.product_amount,r.product_currency,r.logistic_return_at,
          r.buyer_comment_raw,r.payload,d.refund_amount,d.refund_currency,
          d.platform_compensation_rub,d.platform_compensated_at,
          d.logistics_compensation_cny,d.logistics_compensated_at,d.return_method,d.return_result
          FROM rfbs_return_records r JOIN shops s ON s.id=r.shop_id
          LEFT JOIN rfbs_return_disputes d ON d.shop_id=r.shop_id AND d.return_number=r.return_number{where}
          ORDER BY r.created_at DESC,r.return_id DESC LIMIT ? OFFSET ?""",
          args + [size, (page - 1) * size]).fetchall()
        rows = [_with_compensation_conversion(db, dict(row)) for row in rows]
        through = db.execute(f"SELECT MAX(r.created_at) FROM rfbs_return_records r{where}", args).fetchone()[0]
        rules = load_product_rules(db)
    items = []
    for raw in rows:
        item = dict(raw)
        item["product_name"] = resolve_product(rules, item["sku"], item["offer_id"],
                                               item["product_name"])["display_name"]
        payload = json.loads(item.pop("payload"))
        product, state = payload.get("product") or {}, payload.get("state") or {}
        item["quantity"] = item["quantity"] or payload.get("quantity") or product.get("quantity") or 1
        item["product_amount"] = item["product_amount"] if item["product_amount"] is not None else product.get("price")
        item["product_currency"] = item["product_currency"] or product.get("currency_code")
        item["compensation_status"] = item["compensation_status"] or state.get("money_return_state_name")
        item["reason_name"] = CANCEL_REASON_ZH.get(item["reason_raw"], item["reason_name"] or item["reason_raw"])
        items.append(item)
    for item in items:
        item["status_name"] = RFBS_RETURN_STATUS_ZH.get(item["status_raw"], item["status_name"] or item["status_raw"])
        item.update(_complaint_deadline(item["created_at"]))
    return {"summary": {"records": total, "shops": totals}, "items": items, "total": total,
            "page": page, "size": size, "data_through": through}
