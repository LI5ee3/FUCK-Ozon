from .db import connect


ISSUE_TYPES = (
    "missing_erp_cost", "missing_order", "missing_order_item",
    "quantity_mismatch", "offer_id_mismatch",
)
ERP_COST_FIELDS = (
    "erp_order_number", "ozon_sku", "offer_id", "quantity", "unit_cost",
    "exchange_rate_original", "total_cost", "platform_link", "source_batch_id",
    "source_row_no", "raw_payload_json", "imported_at", "updated_at",
)


def _shop(shop_id):
    if type(shop_id) is not int or shop_id not in (1, 2):
        raise ValueError("未知店铺")


def _paging(page, size):
    if type(page) is not int or page < 1:
        raise ValueError("page必须为正整数")
    if type(size) is not int or not 1 <= size <= 100:
        raise ValueError("size必须在1到100之间")
    return page, size


def _present(value):
    return value is not None and (not isinstance(value, str) or value.strip())


def resolve_erp_cost_for_order_item(db, shop_id, posting_number, sku, quantity):
    _shop(shop_id)
    row = db.execute("""
      SELECT i.offer_id AS order_offer_id,
        e.erp_order_number,e.ozon_sku,e.offer_id,e.quantity,e.unit_cost,
        e.exchange_rate_original,e.total_cost,e.platform_link,e.source_batch_id,
        e.source_row_no,e.raw_payload_json,e.imported_at,e.updated_at
      FROM order_items i
      LEFT JOIN erp_order_item_costs e
        ON e.shop_id=i.shop_id
       AND e.erp_order_number=i.posting_number
       AND e.ozon_sku=i.sku
      WHERE i.shop_id=? AND i.posting_number=? AND i.sku=?
    """, (shop_id, posting_number, sku)).fetchone()
    if row is None or row["erp_order_number"] is None:
        return {"status": "missing_erp_cost", "erp_cost": None,
                "order_offer_id": row["order_offer_id"] if row else None,
                "offer_id_mismatch": False}

    erp_cost = {field: row[field] for field in ERP_COST_FIELDS}
    order_offer_id = row["order_offer_id"]
    erp_offer_id = row["offer_id"]
    matched = row["quantity"] == quantity
    offer_id_mismatch = bool(
        matched and _present(order_offer_id) and _present(erp_offer_id)
        and order_offer_id != erp_offer_id
    )
    return {
        "status": "matched" if matched else "quantity_mismatch",
        "erp_cost": erp_cost,
        "order_offer_id": order_offer_id,
        "offer_id_mismatch": offer_id_mismatch,
    }


def get_erp_cost_coverage(shop_id):
    _shop(shop_id)
    with connect() as db:
        order_counts = db.execute("""
          SELECT COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN e.shop_id IS NOT NULL AND i.quantity=e.quantity THEN 1 ELSE 0 END),0) AS matched,
            COALESCE(SUM(CASE WHEN e.shop_id IS NULL THEN 1 ELSE 0 END),0) AS missing_erp_cost,
            COALESCE(SUM(CASE WHEN e.shop_id IS NOT NULL AND i.quantity<>e.quantity THEN 1 ELSE 0 END),0) AS quantity_mismatch
          FROM order_items i
          LEFT JOIN erp_order_item_costs e
            ON e.shop_id=i.shop_id
           AND e.erp_order_number=i.posting_number
           AND e.ozon_sku=i.sku
          WHERE i.shop_id=?
        """, (shop_id,)).fetchone()
        erp_counts = db.execute("""
          SELECT COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN o.shop_id IS NULL THEN 1 ELSE 0 END),0) AS missing_order,
            COALESCE(SUM(CASE WHEN o.shop_id IS NOT NULL AND i.shop_id IS NULL THEN 1 ELSE 0 END),0) AS missing_order_item,
            COALESCE(SUM(CASE WHEN o.shop_id IS NOT NULL AND i.shop_id IS NOT NULL
                              AND e.quantity<>i.quantity THEN 1 ELSE 0 END),0) AS quantity_mismatch,
            COALESCE(SUM(CASE WHEN o.shop_id IS NOT NULL AND i.shop_id IS NOT NULL
                              AND e.quantity=i.quantity THEN 1 ELSE 0 END),0) AS matched
          FROM erp_order_item_costs e
          LEFT JOIN orders o
            ON o.shop_id=e.shop_id AND o.posting_number=e.erp_order_number
          LEFT JOIN order_items i
            ON i.shop_id=e.shop_id AND i.posting_number=e.erp_order_number AND i.sku=e.ozon_sku
          WHERE e.shop_id=?
        """, (shop_id,)).fetchone()
        offer_id_mismatch = db.execute("""
          SELECT COUNT(*)
          FROM erp_order_item_costs e
          JOIN orders o
            ON o.shop_id=e.shop_id AND o.posting_number=e.erp_order_number
          JOIN order_items i
            ON i.shop_id=e.shop_id AND i.posting_number=e.erp_order_number AND i.sku=e.ozon_sku
          WHERE e.shop_id=? AND e.quantity=i.quantity
            AND NULLIF(trim(e.offer_id),'') IS NOT NULL
            AND NULLIF(trim(i.offer_id),'') IS NOT NULL
            AND e.offer_id<>i.offer_id
        """, (shop_id,)).fetchone()[0]

    order_total, order_matched = order_counts["total"], order_counts["matched"]
    return {
        "shop_id": shop_id,
        "order_items": {
            "total": order_total,
            "matched": order_matched,
            "missing_erp_cost": order_counts["missing_erp_cost"],
            "quantity_mismatch": order_counts["quantity_mismatch"],
            "coverage_rate": order_matched / order_total if order_total else None,
        },
        "erp_facts": {
            "total": erp_counts["total"],
            "matched": erp_counts["matched"],
            "missing_order": erp_counts["missing_order"],
            "missing_order_item": erp_counts["missing_order_item"],
            "quantity_mismatch": erp_counts["quantity_mismatch"],
        },
        "diagnostics": {"offer_id_mismatch": offer_id_mismatch},
    }


ISSUE_QUERIES = {
    "missing_erp_cost": {
        "select": """
          SELECT 'missing_erp_cost' AS issue_type, i.shop_id,
            i.posting_number, NULL AS erp_order_number, i.sku,
            i.offer_id AS order_offer_id, NULL AS erp_offer_id,
            i.quantity AS order_quantity, NULL AS erp_quantity,
            NULL AS unit_cost, NULL AS total_cost, NULL AS exchange_rate_original,
            NULL AS source_batch_id, NULL AS source_row_no
        """,
        "from": """
          FROM order_items i
          LEFT JOIN erp_order_item_costs e
            ON e.shop_id=i.shop_id AND e.erp_order_number=i.posting_number AND e.ozon_sku=i.sku
        """,
        "where": "i.shop_id=? AND e.shop_id IS NULL",
    },
    "missing_order": {
        "select": """
          SELECT 'missing_order' AS issue_type, e.shop_id,
            e.erp_order_number AS posting_number, e.erp_order_number, e.ozon_sku AS sku,
            NULL AS order_offer_id, e.offer_id AS erp_offer_id,
            NULL AS order_quantity, e.quantity AS erp_quantity,
            e.unit_cost, e.total_cost, e.exchange_rate_original,
            e.source_batch_id, e.source_row_no
        """,
        "from": """
          FROM erp_order_item_costs e
          LEFT JOIN orders o
            ON o.shop_id=e.shop_id AND o.posting_number=e.erp_order_number
        """,
        "where": "e.shop_id=? AND o.shop_id IS NULL",
    },
    "missing_order_item": {
        "select": """
          SELECT 'missing_order_item' AS issue_type, e.shop_id,
            e.erp_order_number AS posting_number, e.erp_order_number, e.ozon_sku AS sku,
            NULL AS order_offer_id, e.offer_id AS erp_offer_id,
            NULL AS order_quantity, e.quantity AS erp_quantity,
            e.unit_cost, e.total_cost, e.exchange_rate_original,
            e.source_batch_id, e.source_row_no
        """,
        "from": """
          FROM erp_order_item_costs e
          JOIN orders o
            ON o.shop_id=e.shop_id AND o.posting_number=e.erp_order_number
          LEFT JOIN order_items i
            ON i.shop_id=e.shop_id AND i.posting_number=e.erp_order_number AND i.sku=e.ozon_sku
        """,
        "where": "e.shop_id=? AND i.shop_id IS NULL",
    },
    "quantity_mismatch": {
        "select": """
          SELECT 'quantity_mismatch' AS issue_type, e.shop_id,
            e.erp_order_number AS posting_number, e.erp_order_number, e.ozon_sku AS sku,
            i.offer_id AS order_offer_id, e.offer_id AS erp_offer_id,
            i.quantity AS order_quantity, e.quantity AS erp_quantity,
            e.unit_cost, e.total_cost, e.exchange_rate_original,
            e.source_batch_id, e.source_row_no
        """,
        "from": """
          FROM erp_order_item_costs e
          JOIN orders o
            ON o.shop_id=e.shop_id AND o.posting_number=e.erp_order_number
          JOIN order_items i
            ON i.shop_id=e.shop_id AND i.posting_number=e.erp_order_number AND i.sku=e.ozon_sku
        """,
        "where": "e.shop_id=? AND e.quantity<>i.quantity",
    },
    "offer_id_mismatch": {
        "select": """
          SELECT 'offer_id_mismatch' AS issue_type, e.shop_id,
            e.erp_order_number AS posting_number, e.erp_order_number, e.ozon_sku AS sku,
            i.offer_id AS order_offer_id, e.offer_id AS erp_offer_id,
            i.quantity AS order_quantity, e.quantity AS erp_quantity,
            e.unit_cost, e.total_cost, e.exchange_rate_original,
            e.source_batch_id, e.source_row_no
        """,
        "from": """
          FROM erp_order_item_costs e
          JOIN orders o
            ON o.shop_id=e.shop_id AND o.posting_number=e.erp_order_number
          JOIN order_items i
            ON i.shop_id=e.shop_id AND i.posting_number=e.erp_order_number AND i.sku=e.ozon_sku
        """,
        "where": """
          e.shop_id=? AND e.quantity=i.quantity
            AND NULLIF(trim(e.offer_id),'') IS NOT NULL
            AND NULLIF(trim(i.offer_id),'') IS NOT NULL
            AND e.offer_id<>i.offer_id
        """,
    },
}


def _issue_union(issue_type, shop_id):
    types = (issue_type,) if issue_type else ISSUE_TYPES
    parts, args = [], []
    for current_type in types:
        query = ISSUE_QUERIES[current_type]
        parts.append(f"{query['select']} {query['from']} WHERE {query['where']}")
        args.append(shop_id)
    return " UNION ALL ".join(parts), args


def list_erp_cost_issues(shop_id, issue_type="", q="", page=1, size=50):
    _shop(shop_id)
    page, size = _paging(page, size)
    if issue_type and issue_type not in ISSUE_TYPES:
        raise ValueError("未知问题类型")
    query, args = _issue_union(issue_type, shop_id)
    where, search_args = [], []
    q = q.strip() if isinstance(q, str) else ""
    if q:
        pattern = f"%{q}%"
        where.append("(posting_number LIKE ? OR erp_order_number LIKE ? OR sku LIKE ? "
                     "OR erp_offer_id LIKE ? OR order_offer_id LIKE ?)")
        search_args = [pattern] * 5
    where_sql = f" WHERE {' AND '.join(where)}" if where else ""
    with connect() as db:
        total = db.execute(
            f"SELECT COUNT(*) FROM ({query}) AS issues{where_sql}", args + search_args
        ).fetchone()[0]
        rows = db.execute(
            f"""SELECT * FROM ({query}) AS issues{where_sql}
              ORDER BY posting_number,sku,issue_type LIMIT ? OFFSET ?""",
            args + search_args + [size, (page - 1) * size],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "size": size}
