import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..db import connect
from ..ozon.mappings import CANCEL_REASON_ZH
from ..products import load_product_rules, resolve_product
from .common import (_complaint_deadline, _overview_range, _shop_clause, _translated_order,
                     _with_compensation_conversion)


router = APIRouter()
ACTIVE = "NOT (o.status_raw='已取消' AND o.shipped=0)"


def _export_range(date_from="", date_to=""):
    if not date_from and not date_to:
        return None
    if "T" in date_from or "T" in date_to:
        try:
            start = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
            end = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
        except ValueError as error:
            raise HTTPException(400, "日期格式无效") from error
        if start and start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
        if end and end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
        if start and end and start > end:
            raise HTTPException(400, "开始日期不能晚于结束日期")
        return date_from or None, date_to or None, date_from or None, date_to or None, False
    start, end, utc_start, utc_end = _overview_range(date_from or None, date_to or None)
    return start.isoformat(), end.isoformat(), utc_start, utc_end, True


@router.get("/api/export/orders")
def export_orders(shop_id: int = 0, date_from: str = "", date_to: str = ""):
    if shop_id not in (0, 1, 2): raise HTTPException(400, "未知店铺")
    clause, args = _shop_clause(shop_id)
    export_range = _export_range(date_from, date_to)
    range_clause = ""
    if export_range:
        _, _, utc_start, utc_end, exclusive_end = export_range
        if utc_start:
            range_clause += " AND o.created_at>=?"; args.append(utc_start)
        if utc_end:
            range_clause += f" AND o.created_at{'<' if exclusive_end else '<='}?"; args.append(utc_end)
    def lines():
        with connect() as db:
            rules = load_product_rules(db)
            shops_value = [dict(r) for r in db.execute("SELECT id,name FROM shops ORDER BY id")
                           if shop_id not in (1, 2) or r["id"] == shop_id]
            through = db.execute(f"SELECT MAX(o.created_at) FROM orders o WHERE {ACTIVE}{clause}{range_clause}", args).fetchone()[0]
            yield json.dumps({"type":"metadata","shops":shops_value,"timezone":"数据库UTC；显示北京时间",
                              "range":{"from":export_range[0],"to":export_range[1]} if export_range else {"from":None,"to":None},
                              "order_definition":"COUNT DISTINCT posting_number","piece_definition":"SUM quantity",
                              "filter":"剔除状态为已取消且无发货证据的订单","data_through":through}, ensure_ascii=False) + "\n"
            current_key = current = None
            for raw in db.execute(f"""
              SELECT o.shop_id,s.name shop_name,o.posting_number,o.channel,o.created_at,
                o.shipped_at,o.delivered_at,o.status_changed_at,o.status_raw,o.cancel_reason_raw,
                o.shipped,o.data_anomaly,o.amount_original,o.amount_currency,
                i.sku item_sku,i.offer_id item_offer_id,i.product_name_raw item_product_name_raw,
                i.quantity item_quantity,i.unit_price item_unit_price,i.price_currency item_price_currency
              FROM orders o JOIN shops s ON s.id=o.shop_id
              LEFT JOIN order_items i ON i.shop_id=o.shop_id AND i.posting_number=o.posting_number
              WHERE {ACTIVE}{clause}{range_clause} ORDER BY o.created_at
                ,o.shop_id,o.posting_number,i.sku,i.offer_id
            """, args):
                key = raw["shop_id"], raw["posting_number"]
                if key != current_key:
                    if current is not None:
                        current["sku_types"] = len(current["items"])
                        current["pieces"] = sum(int(item["quantity"] or 0) for item in current["items"])
                        yield json.dumps(current, ensure_ascii=False) + "\n"
                    current_key = key
                    current = _translated_order(raw)
                    current["items"] = []
                if raw["item_sku"] is not None:
                    item = {"sku": raw["item_sku"], "offer_id": raw["item_offer_id"],
                            "product_name_raw": raw["item_product_name_raw"],
                            "quantity": raw["item_quantity"], "unit_price": raw["item_unit_price"],
                            "price_currency": raw["item_price_currency"]}
                    resolved = resolve_product(rules, item["sku"], item["offer_id"], item["product_name_raw"])
                    item.update({"product_name": resolved["display_name"],
                                 "analysis_identity": resolved["identity"]})
                    current["items"].append(item)
            if current is not None:
                current["sku_types"] = len(current["items"])
                current["pieces"] = sum(int(item["quantity"] or 0) for item in current["items"])
                yield json.dumps(current, ensure_ascii=False) + "\n"
    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Content-Disposition":"attachment; filename=orders.jsonl"})


@router.get("/api/export/{module}")
def export_module(module: str, shop_id: int = 0, date_from: str = "", date_to: str = ""):
    if module not in {"risk", "returns", "complaints"}:
        raise HTTPException(404, "未知导出模块")
    if shop_id not in (0, 1, 2): raise HTTPException(400, "未知店铺")
    tables = {
        "risk": ("orders o JOIN order_items i USING(shop_id,posting_number)", "o.created_at",
                 "o.shop_id,o.channel,o.posting_number,o.created_at,i.sku,i.offer_id,i.product_name_raw,i.quantity,o.status_raw,o.shipped,o.cancel_reason_raw"),
        "returns": ("rfbs_return_records o LEFT JOIN rfbs_return_disputes d ON d.shop_id=o.shop_id AND d.return_number=o.return_number JOIN shops s ON s.id=o.shop_id", "o.created_at",
                 "o.shop_id,s.name shop_name,o.return_id,o.return_number,o.created_at,o.posting_number,o.sku,o.offer_id,o.product_name,o.status_raw,o.status_name,o.quantity,o.reason_raw,o.reason_name,o.compensation_status,o.product_amount,o.product_currency,o.logistic_return_at,o.buyer_comment_raw,s.settlement_currency,d.refund_type,d.refund_amount,d.refund_currency,d.platform_compensation_rub,d.platform_compensated_at,d.logistics_compensation_cny,d.logistics_compensated_at,d.process_status,d.return_method,d.iml_return_number,d.iml_system_sn,d.buyer_tracking_number,d.handling_method,d.video_recorded,d.outbound_order_number,d.return_result,d.notes,d.created_at manual_created_at,d.updated_at manual_updated_at"),
        "complaints": ("complaints o JOIN shops s ON s.id=o.shop_id JOIN orders x ON x.shop_id=o.shop_id AND x.posting_number=o.posting_number", "o.complaint_at",
                 "o.shop_id,s.name shop_name,o.posting_number,o.complaint_number,o.complaint_at,o.channel,o.resolved,o.package_returned,o.compensation_amount,o.compensation_currency,o.notes,o.not_received_return,o.warehouse,o.order_process_status,o.complaint_status,o.compensation_status,o.platform_compensation_rub,o.platform_compensated_at,o.logistics_compensation_cny,o.logistics_compensated_at,s.settlement_currency,x.status_changed_at,(SELECT MAX(r.occurred_at) FROM return_records r WHERE r.shop_id=o.shop_id AND r.posting_number=o.posting_number) fallback_cancelled_at,o.created_at,o.updated_at"),
    }
    table, date_column, fields = tables[module]
    where, args = ["1=1"], []
    alias = "o"
    export_range = _export_range(date_from, date_to)
    if shop_id in (1, 2):
        where.append(f"{alias}.shop_id=?"); args.append(shop_id)
    if export_range:
        _, _, utc_start, utc_end, exclusive_end = export_range
        if utc_start:
            where.append(f"{date_column}>=?"); args.append(utc_start)
        if utc_end:
            where.append(f"{date_column}{'<' if exclusive_end else '<='}?"); args.append(utc_end)
    if module == "risk":
        where.append(ACTIVE)
    sql_where = " AND ".join(where)

    def lines():
        with connect() as db:
            selected = [dict(row) for row in db.execute("SELECT id,name FROM shops ORDER BY id")
                        if shop_id not in (1, 2) or row["id"] == shop_id]
            through = db.execute(f"SELECT MAX({date_column}) FROM {table} WHERE {sql_where}", args).fetchone()[0]
            metadata = {"type": "metadata", "module": module, "shops": selected,
              "range": {"from": export_range[0], "to": export_range[1]} if export_range else {"from": None, "to": None},
              "timezone": "数据库UTC；页面北京时间", "currencies": "保留记录原始币种，不做跨币种汇总",
              "order_definition": "不同posting_number", "piece_definition": "SUM(quantity)",
              "filter": "统计类导出剔除发货前取消；模块互相隔离", "data_through": through}
            yield json.dumps(metadata, ensure_ascii=False) + "\n"
            if module == "returns":
                legacy_where, legacy_args = ["1=1"], []
                if shop_id in (1, 2):
                    legacy_where.append("shop_id=?"); legacy_args.append(shop_id)
                if export_range:
                    if utc_start:
                        legacy_where.append("occurred_at>=?"); legacy_args.append(utc_start)
                    if utc_end:
                        legacy_where.append(f"occurred_at{'<' if exclusive_end else '<='}?"); legacy_args.append(utc_end)
                for row in db.execute(f"SELECT shop_id,occurred_at,posting_number,sku,payload FROM return_records WHERE {' AND '.join(legacy_where)} ORDER BY occurred_at", legacy_args):
                    value, payload = dict(row), json.loads(row["payload"])
                    product, visual = payload.get("product") or {}, payload.get("visual") or {}
                    status = visual.get("status") or {}
                    value.pop("payload")
                    value.update({"record_type": "取消明细", "quantity": product.get("quantity"),
                                  "offer_id": product.get("offer_id"), "product_name": product.get("name"),
                                  "reason_raw": payload.get("return_reason_name"),
                                  "reason_name": CANCEL_REASON_ZH.get(payload.get("return_reason_name"), payload.get("return_reason_name")),
                                  "status": status.get("display_name") if isinstance(status, dict) else status})
                    value.update(_complaint_deadline(value["occurred_at"]))
                    yield json.dumps(value, ensure_ascii=False) + "\n"
            rules = load_product_rules(db) if module == "risk" else None
            for row in db.execute(f"SELECT {fields} FROM {table} WHERE {sql_where} ORDER BY {date_column}", args):
                value = dict(row)
                if module == "returns":
                    value["record_type"] = "退货明细"
                    value["reason_name"] = CANCEL_REASON_ZH.get(
                        value["reason_raw"], value["reason_name"] or value["reason_raw"])
                    value.update(_complaint_deadline(value["created_at"]))
                    _with_compensation_conversion(db, value)
                elif module == "complaints":
                    value["record_type"] = "发货未收货投诉"
                    value.update(_complaint_deadline(value.pop("status_changed_at"),
                                                      value.pop("fallback_cancelled_at")))
                    _with_compensation_conversion(db, value)
                elif module == "risk":
                    resolved = resolve_product(rules, value["sku"], value["offer_id"], value.pop("product_name_raw"))
                    value["analysis_identity"] = resolved["identity"]
                    value["analysis_product_name"] = resolved["display_name"]
                    value["cancel_reason_name"] = CANCEL_REASON_ZH.get(
                        value["cancel_reason_raw"], value["cancel_reason_raw"])
                yield json.dumps(value, ensure_ascii=False) + "\n"
            if module == "complaints":
                received_where, received_args = ["1=1"], []
                if shop_id in (1, 2):
                    received_where.append("r.shop_id=?"); received_args.append(shop_id)
                if export_range:
                    if utc_start:
                        received_where.append("r.created_at>=?"); received_args.append(utc_start)
                    if utc_end:
                        received_where.append(f"r.created_at{'<' if exclusive_end else '<='}?")
                        received_args.append(utc_end)
                for row in db.execute(f"""SELECT r.shop_id,s.name shop_name,r.posting_number,
                  r.return_number,r.created_at,r.sku,r.offer_id,r.product_name,r.product_amount,
                  r.product_currency,r.reason_raw,r.reason_name,r.buyer_comment_raw,
                  d.refund_type,d.refund_amount,d.refund_currency,d.platform_compensation_rub,
                  d.platform_compensated_at,d.logistics_compensation_cny,d.logistics_compensated_at,
                  d.process_status,d.return_method,d.iml_return_number,d.iml_system_sn,
                  d.buyer_tracking_number,d.handling_method,d.video_recorded,d.outbound_order_number,
                  d.return_result,d.notes,d.created_at manual_created_at,d.updated_at manual_updated_at,
                  s.settlement_currency FROM rfbs_return_disputes d
                  JOIN rfbs_return_records r ON r.shop_id=d.shop_id AND r.return_number=d.return_number
                  JOIN shops s ON s.id=r.shop_id WHERE {' AND '.join(received_where)} ORDER BY r.created_at""",
                  received_args):
                    value = dict(row)
                    value["record_type"] = "已收货纠纷"
                    value["reason_name"] = CANCEL_REASON_ZH.get(
                        value["reason_raw"], value["reason_name"] or value["reason_raw"])
                    value.update(_complaint_deadline(value["created_at"]))
                    _with_compensation_conversion(db, value)
                    yield json.dumps(value, ensure_ascii=False) + "\n"
    return StreamingResponse(lines(), media_type="application/x-ndjson",
      headers={"Content-Disposition": f"attachment; filename={module}.jsonl"})
