from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math

from .db import connect, transaction
from .products import clean_product_name, load_product_rules, resolve_product


CURRENCIES = {"USD", "CNY"}
MAX_NOTE_LENGTH = 500
MAX_HISTORY_LIMIT = 100
BUSINESS_FIELDS = (
    "purchase_cost", "purchase_currency", "weight_grams", "length_cm", "width_cm",
    "height_cm", "packing_cost_cny", "other_cost_cny", "note",
)


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _identifier(value, label):
    if value is None:
        return ""
    if type(value) not in (str, int):
        raise ValueError(f"{label}类型无效")
    return str(value).strip()


def _number(value, label, required=False):
    if value is None or (type(value) is str and not value.strip()):
        if required:
            raise ValueError(f"{label}为必填项")
        return None
    if type(value) is bool or type(value) not in (int, float, str, Decimal):
        raise ValueError(f"{label}必须为数字")
    try:
        number = Decimal(str(value).strip())
        if not number.is_finite() or number < 0:
            raise InvalidOperation
        result = float(number)
    except (InvalidOperation, ValueError, OverflowError) as error:
        raise ValueError(f"{label}必须为有限非负数字") from error
    if not math.isfinite(result):
        raise ValueError(f"{label}必须为有限非负数字")
    return 0.0 if result == 0 else result


def _currency(value):
    if type(value) is not str:
        raise ValueError("采购币种必须为 USD 或 CNY")
    value = value.strip().upper()
    if value not in CURRENCIES:
        raise ValueError("采购币种必须为 USD 或 CNY")
    return value


def _note(value, label):
    if value is None:
        return ""
    if type(value) is not str:
        raise ValueError(f"{label}必须为字符串")
    value = value.strip()
    if len(value) > MAX_NOTE_LENGTH:
        raise ValueError(f"{label}不能超过{MAX_NOTE_LENGTH}个字符")
    return value


def normalize_forecast_cost_payload(body):
    if not isinstance(body, dict):
        raise ValueError("预测成本请求必须为对象")
    sku = _identifier(body.get("sku"), "Ozon SKU")
    offer_id = _identifier(body.get("offer_id"), "货号")
    if not sku and not offer_id:
        raise ValueError("必须提供 Ozon SKU 或货号")
    return {
        "sku": sku,
        "offer_id": offer_id,
        "purchase_cost": _number(body.get("purchase_cost"), "采购成本", required=True),
        "purchase_currency": _currency(body.get("purchase_currency")),
        "weight_grams": _number(body.get("weight_grams"), "重量"),
        "length_cm": _number(body.get("length_cm"), "长度"),
        "width_cm": _number(body.get("width_cm"), "宽度"),
        "height_cm": _number(body.get("height_cm"), "高度"),
        "packing_cost_cny": _number(body.get("packing_cost_cny"), "包装成本"),
        "other_cost_cny": _number(body.get("other_cost_cny"), "其他成本"),
        "note": _note(body.get("note"), "备注"),
        "change_note": _note(body.get("change_note"), "变更备注"),
    }


def _page(value, label):
    if type(value) is not int or value < 1:
        raise ValueError(f"{label}必须为正整数")
    return value


def _product_items(db):
    return db.execute("""
      WITH preferred AS (
        SELECT shop_id,sku,offer_id,
          COALESCE(MIN(CASE WHEN source='api' THEN rowid END),MIN(rowid)) item_rowid
        FROM order_items
        WHERE NULLIF(trim(sku),'') IS NOT NULL OR NULLIF(trim(offer_id),'') IS NOT NULL
        GROUP BY shop_id,sku,offer_id)
      SELECT i.shop_id,i.sku,i.offer_id,i.product_name_raw
      FROM preferred p JOIN order_items i ON i.rowid=p.item_rowid
      ORDER BY i.shop_id,i.sku,i.offer_id
    """).fetchall()


def _sku_group_ids_by_sku(rules):
    groups = {}
    for offer_id, sku in rules["names"]:
        group_id = rules["members"].get(("offer_id", offer_id))
        if group_id is not None:
            groups.setdefault(sku, set()).add(group_id)
    return groups


def _resolve_item(rules, sku, offer_id, raw_name, sku_group_ids):
    sku_group = rules["members"].get(("sku", sku))
    offer_group = rules["members"].get(("offer_id", offer_id))
    group_ids = {group_id for group_id in (sku_group, offer_group) if group_id is not None}
    group_ids.update(sku_group_ids.get(sku, ()))
    if len(group_ids) > 1:
        return None, "商品匹配规则存在冲突，无法确定 canonical product identity"
    return resolve_product(rules, sku, offer_id, raw_name), None


def _product_rows(db, rules):
    products = {}
    sku_group_ids = _sku_group_ids_by_sku(rules)
    for item in _product_items(db):
        shop_id = int(item["shop_id"])
        sku = str(item["sku"] or "").strip()
        offer_id = str(item["offer_id"] or "").strip()
        raw_name = item["product_name_raw"] or ""
        resolved, conflict = _resolve_item(rules, sku, offer_id, raw_name, sku_group_ids)
        if conflict:
            key = ("conflict", sku, offer_id)
            row = products.setdefault(key, {
                "product_identity": None,
                "display_name": clean_product_name(raw_name) or "商品匹配冲突",
                "ozon_skus": set(), "offer_ids": set(),
                "listings": set(),
                "sku": sku, "offer_id": offer_id,
                "conflict": True, "conflict_message": conflict,
            })
            row["ozon_skus"].add(sku) if sku else None
            row["offer_ids"].add(offer_id) if offer_id else None
            if sku and offer_id:
                row["listings"].add((shop_id, sku, offer_id))
            continue
        identity = resolved["identity"]
        row = products.setdefault(identity, {
            "product_identity": identity,
            "display_name": resolved["display_name"],
            "ozon_skus": set(), "offer_ids": set(),
            "listings": set(),
            "sku": resolved["primary_sku"] or sku,
            "offer_id": resolved["primary_offer_id"] or offer_id,
            "conflict": False, "conflict_message": None,
        })
        row["ozon_skus"].add(sku) if sku else None
        row["offer_ids"].add(offer_id) if offer_id else None
        if sku and offer_id:
            row["listings"].add((shop_id, sku, offer_id))
    result = []
    for row in products.values():
        row["ozon_skus"] = sorted(row["ozon_skus"])
        row["offer_ids"] = sorted(row["offer_ids"])
        row["listings"] = [
            {"shop_id": shop_id, "sku": sku, "offer_id": offer_id}
            for shop_id, sku, offer_id in sorted(row["listings"])
        ]
        result.append(row)
    return result


def _target_identity(db, rules, sku, offer_id):
    matches = []
    sku_group_ids = _sku_group_ids_by_sku(rules)
    for item in _product_items(db):
        item_sku = str(item["sku"] or "").strip()
        item_offer = str(item["offer_id"] or "").strip()
        if sku and item_sku != sku:
            continue
        if offer_id and item_offer != offer_id:
            continue
        resolved, conflict = _resolve_item(rules, item_sku, item_offer, item["product_name_raw"] or "", sku_group_ids)
        if conflict:
            raise ValueError(conflict)
        matches.append(resolved["identity"])
    identities = sorted(set(matches))
    if not identities:
        raise ValueError("未找到该商品，不能创建孤立预测成本记录")
    if len(identities) > 1:
        raise ValueError("商品标识对应多个 canonical 商品，请同时提供 Ozon SKU 和货号")
    return identities[0]


def _cost_row(db, identity):
    row = db.execute("SELECT * FROM product_forecast_costs WHERE product_identity=?", (identity,)).fetchone()
    return dict(row) if row else None


def list_product_forecast_costs(q="", page=1, size=50):
    page = _page(page, "页码")
    size = _page(size, "每页数量")
    size = min(size, MAX_HISTORY_LIMIT)
    query = str(q or "").strip().casefold()
    with connect() as db:
        rules = load_product_rules(db)
        rows = _product_rows(db, rules)
        costs = {
            row["product_identity"]: dict(row)
            for row in db.execute("SELECT * FROM product_forecast_costs")
        }
    for row in rows:
        cost = costs.get(row["product_identity"]) if not row["conflict"] else None
        row["forecast_cost"] = cost
        row["configured"] = cost is not None
        row["updated_at"] = cost["updated_at"] if cost else None
        haystack = " ".join([
            row["display_name"], row["product_identity"] or "", row["sku"], row["offer_id"],
            *row["ozon_skus"], *row["offer_ids"], row["conflict_message"] or "",
        ]).casefold()
        row["_matches"] = not query or query in haystack
    rows = [row for row in rows if row.pop("_matches")]
    rows.sort(key=lambda row: (row["display_name"].casefold(), row["product_identity"] or row["sku"]))
    total = len(rows)
    offset = (page - 1) * size
    return {"items": rows[offset:offset + size], "total": total, "page": page, "size": size}


def _business_values(values):
    return tuple(values[field] for field in BUSINESS_FIELDS)


def _insert_history(db, identity, values, change_note, recorded_at):
    db.execute("""INSERT INTO product_forecast_cost_history(
      product_identity,purchase_cost,purchase_currency,weight_grams,length_cm,width_cm,height_cm,
      packing_cost_cny,other_cost_cny,note,change_note,recorded_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (identity, *(_business_values(values)), change_note, recorded_at))


def save_product_forecast_cost(body):
    values = normalize_forecast_cost_payload(body)
    with transaction() as db:
        rules = load_product_rules(db)
        identity = _target_identity(db, rules, values["sku"], values["offer_id"])
        current = db.execute("SELECT * FROM product_forecast_costs WHERE product_identity=?", (identity,)).fetchone()
        now = _utc_now()
        if current is None:
            db.execute("""INSERT INTO product_forecast_costs(
              product_identity,purchase_cost,purchase_currency,weight_grams,length_cm,width_cm,height_cm,
              packing_cost_cny,other_cost_cny,note,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (identity, *(_business_values(values)), now, now))
            _insert_history(db, identity, values, values["change_note"], now)
            created, changed = True, True
        elif _business_values(dict(current)) != _business_values(values):
            db.execute("""UPDATE product_forecast_costs SET purchase_cost=?,purchase_currency=?,weight_grams=?,
              length_cm=?,width_cm=?,height_cm=?,packing_cost_cny=?,other_cost_cny=?,note=?,updated_at=?
              WHERE product_identity=?""", (*(_business_values(values)), now, identity))
            _insert_history(db, identity, values, values["change_note"], now)
            created, changed = False, True
        else:
            created, changed = False, False
        cost = _cost_row(db, identity)
    return {"ok": True, "created": created, "changed": changed,
            "product_identity": identity, "forecast_cost": cost}


def _history_identity(db, rules, sku, offer_id, product_identity):
    if sku or offer_id:
        identity = _target_identity(db, rules, sku, offer_id)
        if product_identity and product_identity != identity:
            raise ValueError("商品 identity 与当前商品解析结果不一致")
        return identity
    if not product_identity:
        raise ValueError("必须提供商品 identity、Ozon SKU 或货号")
    if not any(row["product_identity"] == product_identity and not row["conflict"]
               for row in _product_rows(db, rules)):
        raise ValueError("未找到该商品")
    return product_identity


def list_product_forecast_cost_history(*, sku="", offer_id="", product_identity="", limit=50):
    sku = _identifier(sku, "Ozon SKU")
    offer_id = _identifier(offer_id, "货号")
    product_identity = _identifier(product_identity, "商品 identity")
    limit = _page(limit, "历史记录数量")
    limit = min(limit, MAX_HISTORY_LIMIT)
    with connect() as db:
        rules = load_product_rules(db)
        identity = _history_identity(db, rules, sku, offer_id, product_identity)
        rows = [dict(row) for row in db.execute("""SELECT * FROM product_forecast_cost_history
          WHERE product_identity=? ORDER BY recorded_at DESC,id DESC LIMIT ?""", (identity, limit))]
        total = db.execute("SELECT COUNT(*) FROM product_forecast_cost_history WHERE product_identity=?",
                           (identity,)).fetchone()[0]
    return {"product_identity": identity, "items": rows, "total": total, "limit": limit}
