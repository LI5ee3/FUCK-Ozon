import json
import math
from datetime import timedelta, timezone
from decimal import Decimal, InvalidOperation

from . import client
from ..db import transaction


FINANCE_PAGE_SIZE = 1000
FINANCE_PAGE_LIMIT = 200
TOTAL_FIELDS = (
    "accruals_for_sale", "sale_commission", "processing_and_delivery",
    "refunds_and_cancellations", "services_amount", "compensation_amount",
    "money_transfer", "others_amount",
)


def _utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _next_month(value):
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1, day=1,
                             hour=0, minute=0, second=0, microsecond=0)
    return value.replace(month=value.month + 1, day=1,
                         hour=0, minute=0, second=0, microsecond=0)


def _month_ranges(start, end):
    if start > end:
        raise ValueError("Finance 日期范围无效")
    current = start
    while current <= end:
        boundary = _next_month(current)
        yield current, min(end, boundary - timedelta(seconds=1))
        current = boundary


def _decimal_amount(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(f"Finance 返回的 {field} 不是有限数字")
    try:
        number = Decimal(str(value))
        converted = float(number)
    except (InvalidOperation, TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"Finance 返回的 {field} 不是有限数字") from error
    if not number.is_finite() or not math.isfinite(converted):
        raise ValueError(f"Finance 返回的 {field} 不是有限数字")
    return number, converted


def _text(value, default=""):
    return default if value is None else str(value)


def _optional_text(value):
    return None if value is None else str(value)


def _list_field(operation, field):
    value = operation.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Finance 返回的 operation.{field} 不是数组")
    return value


def _map_operation(shop_id, operation, currency, fetched_at):
    if not isinstance(operation, dict):
        raise ValueError("Finance 返回的 operation 不是对象")
    raw_operation_id = operation.get("operation_id")
    operation_id = str(raw_operation_id).strip() if raw_operation_id is not None else ""
    if not operation_id:
        raise ValueError("Finance 返回的 operation 缺少 operation_id")

    amounts = {}
    for field in ("amount", "accruals_for_sale", "sale_commission",
                  "delivery_charge", "return_delivery_charge"):
        amounts[field] = _decimal_amount(operation.get(field), field)
    posting = operation.get("posting")
    if not isinstance(posting, dict):
        posting = {}
    raw_posting_number = posting.get("posting_number")
    posting_number = None
    if raw_posting_number is not None and str(raw_posting_number).strip():
        posting_number = str(raw_posting_number).strip()

    items = []
    for line_no, item in enumerate(_list_field(operation, "items"), 1):
        if not isinstance(item, dict):
            raise ValueError("Finance 返回的 operation.items 成员不是对象")
        items.append((line_no, None if item.get("sku") is None else str(item.get("sku")),
                      _text(item.get("name"))))

    services = []
    for line_no, service in enumerate(_list_field(operation, "services"), 1):
        if not isinstance(service, dict):
            raise ValueError("Finance 返回的 operation.services 成员不是对象")
        _, price = _decimal_amount(service.get("price"), "services.price")
        services.append((line_no, _text(service.get("name")), price))

    return {
        "shop_id": shop_id,
        "operation_id": operation_id,
        "operation_type": _text(operation.get("operation_type")),
        "operation_type_name": _text(operation.get("operation_type_name")),
        "transaction_type": _text(operation.get("type")),
        "operation_date": _text(operation.get("operation_date")),
        "posting_number": posting_number,
        "order_date": _optional_text(posting.get("order_date")),
        "delivery_schema": _text(posting.get("delivery_schema")),
        "warehouse_id": _optional_text(posting.get("warehouse_id")),
        "amount": amounts["amount"][1],
        "accruals_for_sale": amounts["accruals_for_sale"][1],
        "sale_commission": amounts["sale_commission"][1],
        "delivery_charge": amounts["delivery_charge"][1],
        "return_delivery_charge": amounts["return_delivery_charge"][1],
        "currency": currency,
        "payload_json": json.dumps(operation, ensure_ascii=False, separators=(",", ":")),
        "fetched_at": fetched_at,
        "amounts": amounts,
        "items": items,
        "services": services,
    }


def _finance_list_payload(start, end, page):
    return {
        "filter": {
            "date": {"from": _utc(start), "to": _utc(end)},
            "operation_type": [], "posting_number": "", "transaction_type": "all",
        },
        "page": page,
        "page_size": FINANCE_PAGE_SIZE,
    }


def _response_result(body, path):
    if not isinstance(body, dict) or not isinstance(body.get("result"), dict):
        raise RuntimeError(f"{path}: 响应结构无效")
    return body["result"]


def _nonnegative_int(value, field, path):
    if isinstance(value, bool):
        raise RuntimeError(f"{path}: {field} 无效")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise RuntimeError(f"{path}: {field} 无效") from error
    if number < 0 or isinstance(value, float) and number != value:
        raise RuntimeError(f"{path}: {field} 无效")
    return number


def _fetch_finance_transactions(shop_id, start, end):
    path = "/v3/finance/transaction/list"
    operations = []
    page_count = row_count = None
    for page in range(1, FINANCE_PAGE_LIMIT + 1):
        result = _response_result(client._post(shop_id, path, _finance_list_payload(start, end, page)), path)
        current_page_count = _nonnegative_int(result.get("page_count"), "page_count", path)
        current_row_count = _nonnegative_int(result.get("row_count"), "row_count", path)
        if page_count is None:
            page_count, row_count = current_page_count, current_row_count
            if page_count > FINANCE_PAGE_LIMIT:
                raise RuntimeError(f"{path}: 分页超过安全上限")
        elif (current_page_count, current_row_count) != (page_count, row_count):
            raise RuntimeError(f"{path}: 分页元数据不一致")
        batch = result.get("operations")
        if batch is None:
            batch = []
        if not isinstance(batch, list):
            raise RuntimeError(f"{path}: operations 不是数组")
        operations.extend(batch)
        if page >= page_count:
            break
    else:
        raise RuntimeError(f"{path}: 分页超过安全上限")
    if len(operations) != row_count:
        raise RuntimeError(f"{path}: row_count={row_count}，实际取得={len(operations)}")
    return operations, row_count


def fetch_finance_transactions(shop_id, start, end):
    return _fetch_finance_transactions(shop_id, start, end)[0]


def _validate_operations(operations):
    for operation in operations:
        _map_operation(0, operation, "USD", "")


def _totals_payload(start, end):
    return {"date": {"from": _utc(start), "to": _utc(end)},
            "posting_number": "", "transaction_type": "all"}


def fetch_finance_totals(shop_id, start, end):
    path = "/v3/finance/transaction/totals"
    result = _response_result(client._post(shop_id, path, _totals_payload(start, end)), path)
    totals = {}
    for field in TOTAL_FIELDS:
        _, value = _decimal_amount(result.get(field), field)
        totals[field] = value
    return totals


def _reconciliation(operations, row_count, totals):
    local_amount_total = sum((operation["amounts"]["amount"][0] for operation in operations), Decimal("0"))
    remote_component_total = (
        Decimal(str(totals["accruals_for_sale"]))
        - Decimal(str(totals["sale_commission"]))
        - Decimal(str(totals["processing_and_delivery"]))
        - Decimal(str(totals["refunds_and_cancellations"]))
        - Decimal(str(totals["services_amount"]))
        - Decimal(str(totals["compensation_amount"]))
        - Decimal(str(totals["money_transfer"]))
        - Decimal(str(totals["others_amount"]))
    )
    difference = local_amount_total - remote_component_total
    return {
        "api_row_count": row_count,
        "fetched_operation_count": len(operations),
        **totals,
        "local_amount_total": float(local_amount_total),
        "remote_component_total": float(remote_component_total),
        "difference": float(difference),
        "reconciliation_status": "matched" if abs(difference) <= Decimal("0.01") else "mismatch",
    }


def _save_finance_chunk(shop_id, start, end, operations, row_count, totals, fetched_at):
    period_from, period_to = _utc(start), _utc(end)
    with transaction() as db:
        shop = db.execute("SELECT settlement_currency FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not shop:
            raise ValueError("店铺不存在")
        currency = shop[0]
        mapped = [_map_operation(shop_id, operation, currency, fetched_at) for operation in operations]
        for operation in mapped:
            db.execute("""INSERT INTO ozon_finance_transactions(
              shop_id,operation_id,operation_type,operation_type_name,transaction_type,operation_date,
              posting_number,order_date,delivery_schema,warehouse_id,amount,accruals_for_sale,
              sale_commission,delivery_charge,return_delivery_charge,currency,payload_json,fetched_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(shop_id,operation_id) DO UPDATE SET
                operation_type=excluded.operation_type,operation_type_name=excluded.operation_type_name,
                transaction_type=excluded.transaction_type,operation_date=excluded.operation_date,
                posting_number=excluded.posting_number,order_date=excluded.order_date,
                delivery_schema=excluded.delivery_schema,warehouse_id=excluded.warehouse_id,
                amount=excluded.amount,accruals_for_sale=excluded.accruals_for_sale,
                sale_commission=excluded.sale_commission,delivery_charge=excluded.delivery_charge,
                return_delivery_charge=excluded.return_delivery_charge,currency=excluded.currency,
                payload_json=excluded.payload_json,fetched_at=excluded.fetched_at""",
                      (operation["shop_id"], operation["operation_id"], operation["operation_type"],
                       operation["operation_type_name"], operation["transaction_type"], operation["operation_date"],
                       operation["posting_number"], operation["order_date"], operation["delivery_schema"],
                       operation["warehouse_id"], operation["amount"], operation["accruals_for_sale"],
                       operation["sale_commission"], operation["delivery_charge"], operation["return_delivery_charge"],
                       operation["currency"], operation["payload_json"], operation["fetched_at"]))
            db.execute("""DELETE FROM ozon_finance_transaction_items
              WHERE shop_id=? AND operation_id=?""", (shop_id, operation["operation_id"]))
            db.execute("""DELETE FROM ozon_finance_transaction_services
              WHERE shop_id=? AND operation_id=?""", (shop_id, operation["operation_id"]))
            db.executemany("""INSERT INTO ozon_finance_transaction_items(
              shop_id,operation_id,line_no,sku,name) VALUES(?,?,?,?,?)""",
                           [(shop_id, operation["operation_id"], *item) for item in operation["items"]])
            db.executemany("""INSERT INTO ozon_finance_transaction_services(
              shop_id,operation_id,line_no,service_name,price) VALUES(?,?,?,?,?)""",
                           [(shop_id, operation["operation_id"], *service) for service in operation["services"]])

        reconciliation = _reconciliation(mapped, row_count, totals)
        db.execute("""INSERT INTO ozon_finance_reconciliations(
          shop_id,period_from,period_to,api_row_count,fetched_operation_count,accruals_for_sale,
          sale_commission,processing_and_delivery,refunds_and_cancellations,services_amount,
          compensation_amount,money_transfer,others_amount,local_amount_total,remote_component_total,
          difference,reconciliation_status,fetched_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(shop_id,period_from,period_to) DO UPDATE SET
            api_row_count=excluded.api_row_count,fetched_operation_count=excluded.fetched_operation_count,
            accruals_for_sale=excluded.accruals_for_sale,sale_commission=excluded.sale_commission,
            processing_and_delivery=excluded.processing_and_delivery,
            refunds_and_cancellations=excluded.refunds_and_cancellations,services_amount=excluded.services_amount,
            compensation_amount=excluded.compensation_amount,money_transfer=excluded.money_transfer,
            others_amount=excluded.others_amount,local_amount_total=excluded.local_amount_total,
            remote_component_total=excluded.remote_component_total,difference=excluded.difference,
            reconciliation_status=excluded.reconciliation_status,fetched_at=excluded.fetched_at""",
                  (shop_id, period_from, period_to, reconciliation["api_row_count"],
                   reconciliation["fetched_operation_count"], reconciliation["accruals_for_sale"],
                   reconciliation["sale_commission"], reconciliation["processing_and_delivery"],
                   reconciliation["refunds_and_cancellations"], reconciliation["services_amount"],
                   reconciliation["compensation_amount"], reconciliation["money_transfer"],
                   reconciliation["others_amount"], reconciliation["local_amount_total"],
                   reconciliation["remote_component_total"], reconciliation["difference"],
                   reconciliation["reconciliation_status"], fetched_at))


def sync_finance_transactions(shop_id, start, end):
    records = chunks = 0
    for chunk_start, chunk_end in _month_ranges(start, end):
        operations, row_count = _fetch_finance_transactions(shop_id, chunk_start, chunk_end)
        _validate_operations(operations)
        totals = fetch_finance_totals(shop_id, chunk_start, chunk_end)
        _save_finance_chunk(shop_id, chunk_start, chunk_end, operations, row_count, totals, client._stamp())
        records += len(operations)
        chunks += 1
    return {"records": records, "chunks": chunks}
