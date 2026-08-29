from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from ..db import connect, transaction
from ..ozon.client import BEIJING
from ..ozon.mappings import CANCEL_REASON_ZH
from ..products import load_product_rules, resolve_product
from .common import (_complaint_deadline, _overview_range, _paging,
                     _with_compensation_conversion, _utc_text)


router = APIRouter()


def _compensation_pair(body, amount_key, time_key):
    amount, compensated_at = body.get(amount_key), str(body.get(time_key) or "").strip()
    if (amount in (None, "")) != (not compensated_at):
        raise HTTPException(400, "赔偿金额和赔偿时间必须同时填写")
    if amount in (None, ""):
        return None, None
    try:
        value = Decimal(str(amount))
        if value <= 0:
            raise InvalidOperation
        moment = datetime.fromisoformat(compensated_at.replace("Z", "+00:00"))
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(400, "赔偿金额必须大于0，且赔偿时间必须有效") from error
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BEIJING)
    return str(value), _utc_text(moment)


@router.post("/api/exception-complaints/shipping")
@router.put("/api/exception-complaints/shipping")
async def save_complaint(request: Request):
    body = await request.json()
    shop_id = int(body.get("shop_id") or 0)
    number = str(body.get("complaint_number") or "").strip()
    posting = str(body.get("posting_number") or "").strip()
    complaint_at = str(body.get("complaint_at") or "").strip()
    channel = str(body.get("channel") or "").strip()
    if shop_id not in (1, 2) or not all((number, posting, complaint_at, channel)):
        raise HTTPException(400, "店铺、订单号、投诉编号、投诉时间和渠道均为必填")
    for key in ("resolved", "package_returned"):
        if body.get(key) not in (None, True, False):
            raise HTTPException(400, "是否完结和包裹是否退回只允许未填写、是或否")
    if body.get("not_received_return") not in (None, True, False):
        raise HTTPException(400, "未收到退件只允许未填写、是或否")
    amount = body.get("compensation_amount")
    if amount not in (None, ""):
        try: amount = float(amount)
        except (TypeError, ValueError) as error: raise HTTPException(400, "赔付金额无效") from error
    else:
        amount = None
    platform_amount, platform_at = _compensation_pair(
        body, "platform_compensation_rub", "platform_compensated_at")
    logistics_amount, logistics_at = _compensation_pair(
        body, "logistics_compensation_cny", "logistics_compensated_at")
    now = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        shop = db.execute("SELECT settlement_currency FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not db.execute("SELECT 1 FROM orders WHERE shop_id=? AND posting_number=?", (shop_id, posting)).fetchone():
            raise HTTPException(400, "未找到该店铺订单")
        currency = str(body.get("compensation_currency") or (shop[0] if amount is not None else "")).upper() or None
        exists = db.execute("""SELECT created_at FROM complaints
          WHERE shop_id=? AND complaint_number=? AND posting_number=?""",
                            (shop_id, number, posting)).fetchone()
        db.execute("""INSERT INTO complaints(
          shop_id,complaint_number,posting_number,complaint_at,channel,resolved,package_returned,
          compensation_amount,compensation_currency,notes,not_received_return,warehouse,
          order_process_status,complaint_status,compensation_status,
          platform_compensation_rub,platform_compensated_at,
          logistics_compensation_cny,logistics_compensated_at,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(shop_id,complaint_number,posting_number) DO UPDATE SET
          complaint_at=excluded.complaint_at,channel=excluded.channel,
          resolved=excluded.resolved,package_returned=excluded.package_returned,
          compensation_amount=COALESCE(excluded.compensation_amount,complaints.compensation_amount),
          compensation_currency=COALESCE(excluded.compensation_currency,complaints.compensation_currency),
          notes=excluded.notes,not_received_return=excluded.not_received_return,
          warehouse=excluded.warehouse,order_process_status=excluded.order_process_status,
          complaint_status=excluded.complaint_status,compensation_status=excluded.compensation_status,
          platform_compensation_rub=excluded.platform_compensation_rub,
          platform_compensated_at=excluded.platform_compensated_at,
          logistics_compensation_cny=excluded.logistics_compensation_cny,
          logistics_compensated_at=excluded.logistics_compensated_at,updated_at=excluded.updated_at""",
          (shop_id, number, posting, complaint_at, channel,
           None if body.get("resolved") is None else int(body["resolved"]),
           None if body.get("package_returned") is None else int(body["package_returned"]),
           amount, currency, str(body.get("notes") or ""),
           None if body.get("not_received_return") is None else int(body["not_received_return"]),
           str(body.get("warehouse") or ""), str(body.get("order_process_status") or ""),
           str(body.get("complaint_status") or ""), str(body.get("compensation_status") or ""),
           platform_amount, platform_at,
           logistics_amount, logistics_at, exists[0] if exists else now, now))
    return {"ok": True}


@router.get("/api/exception-complaints/shipping")
def shipping_complaints(shop_id: int = 0, q: str = "", status: str = "", page: int = 1, size: int = 50,
                        date_from: Annotated[str | None, Query(alias="from")] = None,
                        date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    if status not in {"", "unfiled", "open", "closed"}:
        raise HTTPException(400, "投诉状态无效")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    cancelled = "o.status_raw IN ('已取消','cancelled','canceled')"
    where, args = [f"NOT ({cancelled} AND o.shipped=0)", f"(({cancelled} AND o.shipped=1) OR o.data_anomaly=1)",
                   "o.created_at>=?", "o.created_at<?"], [utc_start, utc_end]
    if shop_id:
        where.append("o.shop_id=?"); args.append(shop_id)
    if q.strip():
        pattern = f"%{q.strip()}%"
        where.append("""(o.posting_number LIKE ? OR EXISTS(SELECT 1 FROM order_items i
          WHERE i.shop_id=o.shop_id AND i.posting_number=o.posting_number
            AND (i.sku LIKE ? OR i.offer_id LIKE ?)) OR EXISTS(SELECT 1 FROM complaints c
          WHERE c.shop_id=o.shop_id AND c.posting_number=o.posting_number AND c.complaint_number LIKE ?)
          OR COALESCE(o.tracking_number,'') LIKE ?)""")
        args.extend([pattern] * 5)
    if status == "unfiled":
        where.append("NOT EXISTS(SELECT 1 FROM complaints c WHERE c.shop_id=o.shop_id AND c.posting_number=o.posting_number)")
    elif status == "open":
        where.append("EXISTS(SELECT 1 FROM complaints c WHERE c.shop_id=o.shop_id AND c.posting_number=o.posting_number AND c.resolved IS NOT 1)")
    elif status == "closed":
        where.append("EXISTS(SELECT 1 FROM complaints c WHERE c.shop_id=o.shop_id AND c.posting_number=o.posting_number) AND NOT EXISTS(SELECT 1 FROM complaints c WHERE c.shop_id=o.shop_id AND c.posting_number=o.posting_number AND c.resolved IS NOT 1)")
    sql = " AND ".join(where)
    page, size = _paging(page, size)
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM orders o WHERE {sql}", args).fetchone()[0]
        rows = [dict(row) for row in db.execute(f"""SELECT o.*,s.name shop_name,s.settlement_currency,
          COALESCE(o.tracking_number,'') tracking_number,
          (SELECT MAX(r.occurred_at) FROM return_records r
            WHERE r.shop_id=o.shop_id AND r.posting_number=o.posting_number) fallback_cancelled_at
          FROM orders o JOIN shops s ON s.id=o.shop_id WHERE {sql}
          ORDER BY o.created_at DESC LIMIT ? OFFSET ?""", args + [size, (page - 1) * size])]
        rules = load_product_rules(db)
        items, complaints_by_order = {}, {}
        if rows:
            marks = ",".join("(?,?)" for _ in rows)
            keys = [value for row in rows for value in (row["shop_id"], row["posting_number"])]
            for item in db.execute(f"""SELECT shop_id,posting_number,sku,offer_id,product_name_raw,
              quantity,unit_price,price_currency FROM order_items
              WHERE (shop_id,posting_number) IN ({marks}) ORDER BY shop_id,posting_number,sku""", keys):
                items.setdefault((item["shop_id"], item["posting_number"]), []).append(dict(item))
            for complaint in db.execute(f"""SELECT c.*,s.settlement_currency FROM complaints c
              JOIN shops s ON s.id=c.shop_id WHERE (c.shop_id,c.posting_number) IN ({marks})
              ORDER BY c.shop_id,c.posting_number,c.complaint_at DESC,c.complaint_number""", keys):
                value = _with_compensation_conversion(db, dict(complaint))
                complaints_by_order.setdefault((complaint["shop_id"], complaint["posting_number"]), []).append(value)
        for row in rows:
            row["cancelled_at"] = row["status_changed_at"] or row["fallback_cancelled_at"]
            row.update(_complaint_deadline(row["status_changed_at"], row["fallback_cancelled_at"]))
            row["cancel_reason"] = CANCEL_REASON_ZH.get(row["cancel_reason_raw"], row["cancel_reason_raw"])
            key = row["shop_id"], row["posting_number"]
            row["items"] = items.get(key, [])
            for value in row["items"]:
                value["product_name"] = resolve_product(rules, value["sku"], value["offer_id"],
                                                          value["product_name_raw"])["display_name"]
            row["complaints"] = complaints_by_order.get(key, [])
        through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {sql}", args).fetchone()[0]
    return {"items": rows, "total": total, "page": page, "size": size, "data_through": through}


@router.get("/api/exception-complaints/received")
def received_disputes(shop_id: int = 0, q: str = "", status: str = "", page: int = 1, size: int = 50,
                      date_from: Annotated[str | None, Query(alias="from")] = None,
                      date_to: Annotated[str | None, Query(alias="to")] = None):
    if shop_id not in (0, 1, 2):
        raise HTTPException(400, "未知店铺")
    if status not in {"", "unfiled", "open", "closed"}:
        raise HTTPException(400, "处理状态无效")
    _, _, utc_start, utc_end = _overview_range(date_from, date_to)
    where, args = ["r.created_at>=?", "r.created_at<?"], [utc_start, utc_end]
    if shop_id:
        where.append("r.shop_id=?"); args.append(shop_id)
    if q.strip():
        pattern = f"%{q.strip()}%"
        where.append("(r.sku LIKE ? OR r.offer_id LIKE ? OR r.posting_number LIKE ? OR r.return_number LIKE ?)")
        args.extend([pattern] * 4)
    if status == "unfiled":
        where.append("d.return_number IS NULL")
    elif status == "open":
        where.append("d.return_number IS NOT NULL AND COALESCE(d.process_status,'') NOT IN ('结束','已完结')")
    elif status == "closed":
        where.append("d.process_status IN ('结束','已完结')")
    sql = " AND ".join(where)
    page, size = _paging(page, size)
    with connect() as db:
        join = """FROM rfbs_return_records r JOIN shops s ON s.id=r.shop_id
          LEFT JOIN rfbs_return_disputes d ON d.shop_id=r.shop_id AND d.return_number=r.return_number"""
        total = db.execute(f"SELECT COUNT(*) {join} WHERE {sql}", args).fetchone()[0]
        rows = [dict(row) for row in db.execute(f"""SELECT r.shop_id,s.name shop_name,s.settlement_currency,r.return_number,
          r.created_at,r.posting_number,r.sku,r.offer_id,r.product_name,r.product_amount,r.product_currency,
          r.reason_raw,r.reason_name,r.buyer_comment_raw,d.refund_type,d.refund_amount,d.refund_currency,
          d.platform_compensation_rub,d.platform_compensated_at,
          d.logistics_compensation_cny,d.logistics_compensated_at,d.process_status,d.return_method,
          d.iml_return_number,d.iml_system_sn,d.buyer_tracking_number,d.handling_method,d.video_recorded,
          d.outbound_order_number,d.return_result,d.notes,d.created_at manual_created_at,d.updated_at
          {join} WHERE {sql} ORDER BY r.created_at DESC,r.return_id DESC LIMIT ? OFFSET ?""",
          args + [size, (page - 1) * size])]
        rules = load_product_rules(db)
        for row in rows:
            row.update(_complaint_deadline(row["created_at"]))
            row["product_name"] = resolve_product(rules, row["sku"], row["offer_id"],
                                                   row["product_name"])["display_name"]
            row["reason_name"] = CANCEL_REASON_ZH.get(row["reason_raw"], row["reason_name"] or row["reason_raw"])
            _with_compensation_conversion(db, row)
        through = db.execute(f"SELECT MAX(r.created_at) {join} WHERE {sql}", args).fetchone()[0]
    return {"items": rows, "total": total, "page": page, "size": size, "data_through": through}


@router.post("/api/exception-complaints/received")
@router.put("/api/exception-complaints/received")
async def save_received_dispute(request: Request):
    body = await request.json()
    shop_id = int(body.get("shop_id") or 0)
    return_number = str(body.get("return_number") or "").strip()
    if shop_id not in (1, 2) or not return_number:
        raise HTTPException(400, "店铺和退货申请编号均为必填")
    enums = {
        "refund_type": {"", "部分退款", "全额退款", "多次纠纷"},
        "return_method": {"", "未退货", "IML", "FBO二次销售"},
        "handling_method": {"", "退回", "销毁"},
        "return_result": {"", "退回国内中", "已签收", "已销毁"},
    }
    for key, allowed in enums.items():
        if str(body.get(key) or "") not in allowed:
            raise HTTPException(400, f"{key}取值无效")
    if body.get("video_recorded") not in (None, True, False):
        raise HTTPException(400, "是否拍视频只允许未填写、是或否")
    try:
        refund_amount = None if body.get("refund_amount") in (None, "") else float(body["refund_amount"])
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "退款金额无效") from error
    platform_amount, platform_at = _compensation_pair(
        body, "platform_compensation_rub", "platform_compensated_at")
    logistics_amount, logistics_at = _compensation_pair(
        body, "logistics_compensation_cny", "logistics_compensated_at")
    now = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        shop = db.execute("SELECT settlement_currency FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not db.execute("""SELECT 1 FROM rfbs_return_records
          WHERE shop_id=? AND return_number=?""", (shop_id, return_number)).fetchone():
            raise HTTPException(400, "未找到该店铺退货申请")
        exists = db.execute("""SELECT created_at FROM rfbs_return_disputes
          WHERE shop_id=? AND return_number=?""", (shop_id, return_number)).fetchone()
        refund_currency = str(body.get("refund_currency") or (shop[0] if refund_amount is not None else "")).upper() or None
        if refund_currency not in (None, "USD", "CNY"):
            raise HTTPException(400, "币种只允许USD或CNY")
        db.execute("""INSERT INTO rfbs_return_disputes(
          shop_id,return_number,refund_type,refund_amount,refund_currency,
          platform_compensation_rub,platform_compensated_at,
          logistics_compensation_cny,logistics_compensated_at,
          process_status,return_method,iml_return_number,iml_system_sn,
          buyer_tracking_number,handling_method,video_recorded,outbound_order_number,return_result,notes,
          created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(shop_id,return_number) DO UPDATE SET refund_type=excluded.refund_type,
          refund_amount=excluded.refund_amount,refund_currency=excluded.refund_currency,
          platform_compensation_rub=excluded.platform_compensation_rub,
          platform_compensated_at=excluded.platform_compensated_at,
          logistics_compensation_cny=excluded.logistics_compensation_cny,
          logistics_compensated_at=excluded.logistics_compensated_at,
          process_status=excluded.process_status,return_method=excluded.return_method,
          iml_return_number=excluded.iml_return_number,iml_system_sn=excluded.iml_system_sn,
          buyer_tracking_number=excluded.buyer_tracking_number,handling_method=excluded.handling_method,
          video_recorded=excluded.video_recorded,outbound_order_number=excluded.outbound_order_number,
          return_result=excluded.return_result,notes=excluded.notes,updated_at=excluded.updated_at""",
          (shop_id, return_number, str(body.get("refund_type") or ""), refund_amount,
           refund_currency, platform_amount, platform_at, logistics_amount, logistics_at,
           str(body.get("process_status") or ""), str(body.get("return_method") or ""),
           str(body.get("iml_return_number") or ""), str(body.get("iml_system_sn") or ""),
           str(body.get("buyer_tracking_number") or ""), str(body.get("handling_method") or ""),
           None if body.get("video_recorded") is None else int(body["video_recorded"]),
           str(body.get("outbound_order_number") or ""), str(body.get("return_result") or ""),
           str(body.get("notes") or ""), exists[0] if exists else now, now))
    return {"ok": True}
