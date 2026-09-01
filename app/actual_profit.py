from decimal import Decimal, InvalidOperation

from .db import connect


SHOP_IDS = (0, 1, 2)


def _shop(shop_id):
    if type(shop_id) is not int or shop_id not in SHOP_IDS:
        raise ValueError("未知店铺")


def _decimal(value, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{label}不是有限数字") from error
    if not number.is_finite():
        raise ValueError(f"{label}不是有限数字")
    return number


def _decimal_text(value):
    return format(value, "f")


def _present(value):
    return value is not None and (not isinstance(value, str) or value.strip())


def _pair_marks(rows):
    marks = ",".join("(?,?)" for _ in rows)
    args = [value for row in rows for value in (row["shop_id"], row["posting_number"])]
    return marks, args


def _finance_details(rows, settlement_currency):
    if not rows:
        return {
            "status": "missing", "operation_count": 0, "currency": None,
            "net_amount": None, "net": None, "currency_consistent": False,
        }

    net = sum((_decimal(row["amount"], "Finance amount") for row in rows), Decimal("0"))
    currencies = {row["currency"] for row in rows}
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    return {
        "status": "available", "operation_count": len(rows), "currency": currency,
        "net_amount": _decimal_text(net), "net": net,
        "currency_consistent": len(currencies) == 1 and currency == settlement_currency,
    }


def _rate_details(rows):
    rates = []
    missing = False
    for row in rows:
        value = row["exchange_rate_original"]
        if not _present(value):
            missing = True
            continue
        try:
            rate = _decimal(value, "ERP exchange rate")
        except ValueError:
            missing = True
            continue
        if rate <= 0:
            missing = True
            continue
        rates.append(rate)
    distinct = []
    for rate in rates:
        if rate not in distinct:
            distinct.append(rate)
    return {
        "missing": bool(rows) and missing,
        "mismatch": len(distinct) > 1,
        "rate": distinct[0] if len(distinct) == 1 and not missing else None,
    }


def _erp_details(rows, settlement_currency):
    matched = [row for row in rows
               if row["erp_shop_id"] is not None and row["order_quantity"] == row["erp_quantity"]]
    missing = [row for row in rows if row["erp_shop_id"] is None]
    quantity_mismatch = [row for row in rows
                         if row["erp_shop_id"] is not None and row["order_quantity"] != row["erp_quantity"]]
    offer_mismatch = [row for row in matched
                      if _present(row["order_offer_id"]) and _present(row["erp_offer_id"])
                      and row["order_offer_id"] != row["erp_offer_id"]]
    complete = bool(rows) and not missing and not quantity_mismatch
    rates = _rate_details(matched)
    total_cost = None
    if complete:
        total_cost = sum((_decimal(row["total_cost"], "ERP total cost") for row in matched), Decimal("0"))
    return {
        "status": "complete" if complete else "incomplete",
        "item_count": len(rows), "matched_items": len(matched), "missing_items": len(missing),
        "quantity_mismatch_items": len(quantity_mismatch),
        "offer_id_mismatch_items": len(offer_mismatch),
        "exchange_rate_original": _decimal_text(rates["rate"])
        if complete and rates["rate"] is not None else None,
        "total_cost_cny": _decimal_text(total_cost) if total_cost is not None else None,
        "rate_for_finance": rates["rate"],
        "missing_rate": rates["missing"] if settlement_currency == "USD" else False,
        "rate_mismatch": rates["mismatch"] if settlement_currency == "USD" else False,
    }


def _add_reason(reasons, reason):
    if reason not in reasons:
        reasons.append(reason)


def _profit_row(order, item_rows, finance_rows):
    erp = _erp_details(item_rows, order["settlement_currency"])
    finance = _finance_details(finance_rows, order["settlement_currency"])
    reasons = []
    if not erp["item_count"]:
        _add_reason(reasons, "missing_order_items")
    if erp["missing_items"]:
        _add_reason(reasons, "missing_erp_cost")
    if erp["quantity_mismatch_items"]:
        _add_reason(reasons, "quantity_mismatch")
    if finance["status"] == "missing":
        _add_reason(reasons, "missing_finance")
    if not finance["currency_consistent"] and finance["status"] == "available":
        _add_reason(reasons, "finance_currency_mismatch")
    if erp["missing_rate"]:
        _add_reason(reasons, "missing_exchange_rate")
    if erp["rate_mismatch"]:
        _add_reason(reasons, "exchange_rate_mismatch")

    finance_net_cny = None
    if finance["status"] == "available" and finance["currency_consistent"]:
        if order["settlement_currency"] == "CNY":
            finance_net_cny = finance["net"]
        elif erp["rate_for_finance"] is not None:
            finance_net_cny = finance["net"] * erp["rate_for_finance"]
    finance["net_cny"] = _decimal_text(finance_net_cny) if finance_net_cny is not None else None

    actual_profit = None
    if not reasons:
        actual_profit = finance_net_cny - _decimal(erp["total_cost_cny"], "ERP total cost")

    finance.pop("net")
    finance.pop("currency_consistent")
    erp.pop("rate_for_finance")
    erp.pop("missing_rate")
    erp.pop("rate_mismatch")
    return {
        "shop_id": order["shop_id"], "shop_name": order["shop_name"],
        "posting_number": order["posting_number"], "channel": order["channel"],
        "created_at": order["created_at"], "status_raw": order["status_raw"],
        "finance": finance, "erp_cost": erp,
        "actual_profit_cny": _decimal_text(actual_profit) if actual_profit is not None else None,
        "profit_status": "ready" if not reasons else "incomplete",
        "incomplete_reasons": reasons,
    }


def list_actual_order_profits(shop_id, utc_start, utc_end, q="", page=1, size=50):
    _shop(shop_id)
    q = q.strip() if isinstance(q, str) else ""
    filters = ["o.created_at>=?", "o.created_at<?"]
    args = [utc_start, utc_end]
    if shop_id in (1, 2):
        filters.append("o.shop_id=?")
        args.append(shop_id)
    if q:
        pattern = f"%{q}%"
        filters.append("""(o.posting_number LIKE ? OR EXISTS(
          SELECT 1 FROM order_items x
          WHERE x.shop_id=o.shop_id AND x.posting_number=o.posting_number
            AND (x.sku LIKE ? OR x.offer_id LIKE ?)))""")
        args.extend([pattern] * 3)
    where = " AND ".join(filters)
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM orders o WHERE {where}", args).fetchone()[0]
        orders = [dict(row) for row in db.execute(f"""
          SELECT o.shop_id,s.name shop_name,s.settlement_currency,
            o.posting_number,o.channel,o.created_at,o.status_raw
          FROM orders o JOIN shops s ON s.id=o.shop_id
          WHERE {where}
          ORDER BY o.created_at DESC,o.posting_number DESC LIMIT ? OFFSET ?
        """, args + [size, (page - 1) * size])]
        if not orders:
            return {"items": [], "total": total, "page": page, "size": size}

        marks, pair_args = _pair_marks(orders)
        item_rows = db.execute(f"""
          SELECT i.shop_id,i.posting_number,i.sku,i.offer_id AS order_offer_id,
            i.quantity AS order_quantity,
            e.shop_id AS erp_shop_id,e.offer_id AS erp_offer_id,e.quantity AS erp_quantity,
            e.total_cost,e.exchange_rate_original
          FROM order_items i
          LEFT JOIN erp_order_item_costs e
            ON e.shop_id=i.shop_id
           AND e.erp_order_number=i.posting_number
           AND e.ozon_sku=i.sku
          WHERE (i.shop_id,i.posting_number) IN ({marks})
          ORDER BY i.shop_id,i.posting_number,i.sku
        """, pair_args).fetchall()
        finance_rows = db.execute(f"""
          SELECT t.shop_id,t.posting_number,t.amount,t.currency
          FROM ozon_finance_transactions t
          WHERE NULLIF(trim(t.posting_number),'') IS NOT NULL
            AND (t.shop_id,t.posting_number) IN ({marks})
          ORDER BY t.shop_id,t.posting_number,t.operation_id
        """, pair_args).fetchall()

    items_by_order = {}
    for row in item_rows:
        items_by_order.setdefault((row["shop_id"], row["posting_number"]), []).append(row)
    finance_by_order = {}
    for row in finance_rows:
        finance_by_order.setdefault((row["shop_id"], row["posting_number"]), []).append(row)
    return {
        "items": [_profit_row(
            order,
            items_by_order.get((order["shop_id"], order["posting_number"]), []),
            finance_by_order.get((order["shop_id"], order["posting_number"]), []),
        ) for order in orders],
        "total": total, "page": page, "size": size,
    }
