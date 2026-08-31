from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..db import connect, transaction
from ..product_costs import forecast_cost_identities_for_rule_change, rekey_product_forecast_cost
from ..products import clean_product_name, load_product_rules, resolve_product
from .common import _utc_text, read_bounded_json


router = APIRouter()
JSON_MAX_BODY_BYTES = 256 * 1024


@router.get("/api/product-rules")
def product_rules(q: str = ""):
    with connect() as db:
        pattern = f"%{q.strip()}%"
        short_names = [dict(row) for row in db.execute("""SELECT key_value sku,short_name,updated_at
          FROM product_short_names WHERE key_type='sku'
            AND (?='' OR key_value LIKE ? OR short_name LIKE ?) ORDER BY key_value""",
          (q.strip(), pattern, pattern))]
        products = [dict(row) for row in db.execute("""SELECT sku,offer_id,MAX(product_name_raw) product_name
          FROM order_items WHERE NULLIF(offer_id,'') IS NOT NULL
          GROUP BY sku,offer_id ORDER BY offer_id,sku LIMIT 1000""")]
        for product in products:
            product["product_name"] = clean_product_name(product["product_name"])
        rules = load_product_rules(db)
        groups = []
        for config in db.execute("""SELECT c.group_id id,c.primary_offer_id,c.primary_sku,c.status,c.note,
            g.updated_at FROM product_group_config c JOIN product_groups g ON g.id=c.group_id
            ORDER BY c.primary_offer_id,c.group_id"""):
            group = dict(config)
            group["members"] = [dict(row) for row in db.execute("""SELECT key_type,key_value
              FROM product_group_members WHERE group_id=? ORDER BY key_type,key_value""", (group["id"],))]
            resolved = resolve_product(rules, group["primary_sku"], group["primary_offer_id"], "")
            group["product_name"] = resolved["display_name"] if group["status"] == "active" else "待管理员确认"
            groups.append(group)
        conflicts = [{"key_type": "merge", "key_value": row["primary_offer_id"] or "待确认商品组",
                       "note": row["note"]} for row in groups if row["status"] != "active"]
        short_name_count = db.execute(
            "SELECT COUNT(*) FROM product_short_names WHERE key_type='sku'").fetchone()[0]
    return {"summary": {"short_names": short_name_count,
                         "merges": sum(row["status"] == "active" for row in groups)},
            "short_names": short_names, "groups": groups, "products": products, "conflicts": conflicts,
            "fixed_rule": "固定规则：自动移除平台产品名称中的“Новый ”前缀"}


@router.put("/api/product-rules")
async def save_product_rule(request: Request):
    body = await read_bounded_json(request, JSON_MAX_BODY_BYTES, "商品规则")
    kind = body.get("kind")
    group_id = 0
    if kind in ("merge", "dissolve"):
        value = body.get("id")
        try:
            if value is not None and type(value) not in (int, str):
                raise ValueError("invalid ID type")
            group_id = int(value or 0)
        except (TypeError, ValueError) as error:
            raise HTTPException(400, "合并关系ID无效") from error
    now = _utc_text(datetime.now(timezone.utc))
    with transaction() as db:
        if kind == "short_name":
            key_value = str(body.get("sku") or body.get("key_value") or "").strip()
            name = str(body.get("short_name") or "").strip()
            if body.get("key_type") not in (None, "sku") or not key_value or not name:
                raise HTTPException(400, "短名称规则不完整")
            db.execute("""INSERT INTO product_short_names VALUES('sku',?,?,?)
              ON CONFLICT(key_type,key_value) DO UPDATE SET short_name=excluded.short_name,updated_at=excluded.updated_at""",
                       (key_value, name, now))
        elif kind == "delete_short_name":
            sku = str(body.get("sku") or "").strip()
            if not sku: raise HTTPException(400, "SKU不能为空")
            db.execute("DELETE FROM product_short_names WHERE key_type='sku' AND key_value=?", (sku,))
        elif kind == "merge":
            primary_offer = str(body.get("primary_offer_id") or "").strip()
            members = [(str(row.get("key_type") or ""), str(row.get("key_value") or "").strip())
                       for row in body.get("members") or []]
            if not primary_offer or any(key_type not in {"sku", "offer_id"} or not value
                                        for key_type, value in members):
                raise HTTPException(400, "主货号和合并成员不能为空")
            if len(members) != len(set(members)):
                raise HTTPException(400, "合并成员不能重复")
            members = list(dict.fromkeys([("offer_id", primary_offer), *members]))
            if len(members) < 2: raise HTTPException(400, "请至少添加一个合并成员")
            skus = [row[0] for row in db.execute(
                "SELECT DISTINCT sku FROM order_items WHERE offer_id=? ORDER BY sku", (primary_offer,))]
            if not skus: raise HTTPException(400, "主货号未匹配到现有商品")
            primary_sku = str(body.get("primary_sku") or "").strip()
            if len(skus) > 1 and primary_sku not in skus:
                raise HTTPException(400, "主货号对应多个SKU，请明确选择名称解析SKU")
            primary_sku = primary_sku if primary_sku in skus else skus[0]
            existing = db.execute("SELECT group_id FROM product_group_config WHERE primary_offer_id=? AND group_id<>?",
                                  (primary_offer, group_id)).fetchone()
            if existing: raise HTTPException(400, "该主货号已用于其他合并关系")
            for key_type, value in members:
                owner = db.execute("SELECT group_id FROM product_group_members WHERE key_type=? AND key_value=? AND group_id<>?",
                                   (key_type, value, group_id)).fetchone()
                if owner: raise HTTPException(400, f"{key_type} {value} 已属于其他主货号")
            member_skus = [value for key_type, value in members if key_type == "sku"]
            member_offers = [value for key_type, value in members if key_type == "offer_id"]
            pairs = db.execute(f"""SELECT DISTINCT sku,offer_id FROM order_items WHERE
              sku IN ({','.join('?' for _ in member_skus) or "''"}) OR
              offer_id IN ({','.join('?' for _ in member_offers) or "''"})""",
              [*member_skus, *member_offers]).fetchall()
            for pair in pairs:
                owner = db.execute("""SELECT group_id FROM product_group_members WHERE group_id<>?
                  AND ((key_type='sku' AND key_value=?) OR (key_type='offer_id' AND key_value=?)) LIMIT 1""",
                  (group_id, pair["sku"], pair["offer_id"])).fetchone()
                if owner: raise HTTPException(400, f"商品 {pair['sku']} / {pair['offer_id']} 与其他主货号冲突")
            try:
                rules = load_product_rules(db)
                old_identities = forecast_cost_identities_for_rule_change(db, rules, members, group_id)
                rekey_product_forecast_cost(db, old_identities, primary_offer)
            except ValueError as error:
                raise HTTPException(400, str(error)) from error
            if group_id:
                if not db.execute("SELECT 1 FROM product_groups WHERE id=?", (group_id,)).fetchone():
                    raise HTTPException(400, "合并关系不存在")
                db.execute("UPDATE product_groups SET name=?,updated_at=? WHERE id=?",
                           (f"merge:{primary_offer}", now, group_id))
                db.execute("DELETE FROM product_group_members WHERE group_id=?", (group_id,))
            else:
                group_id = db.execute("INSERT INTO product_groups(name,created_at,updated_at) VALUES(?,?,?)",
                                      (f"merge:{primary_offer}", now, now)).lastrowid
            db.execute("""INSERT INTO product_group_config VALUES(?,?,?,'active','')
              ON CONFLICT(group_id) DO UPDATE SET primary_offer_id=excluded.primary_offer_id,
              primary_sku=excluded.primary_sku,status='active',note=''""", (group_id, primary_offer, primary_sku))
            db.executemany("INSERT INTO product_group_members VALUES(?,?,?)",
                           [(group_id, key_type, value) for key_type, value in members])
        elif kind == "dissolve":
            group = db.execute("SELECT primary_offer_id,primary_sku FROM product_group_config WHERE group_id=?",
                               (group_id,)).fetchone()
            if group and group["primary_offer_id"] and group["primary_sku"]:
                try:
                    rekey_product_forecast_cost(db, {group["primary_offer_id"]}, group["primary_sku"])
                except ValueError as error:
                    raise HTTPException(400, str(error)) from error
            db.execute("DELETE FROM product_groups WHERE id=?", (group_id,))
        else:
            raise HTTPException(400, "未知规则类型")
    return {"ok": True}
