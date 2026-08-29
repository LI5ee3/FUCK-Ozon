PLACEHOLDER = "产品名称暂无"


def clean_product_name(value):
    return str(value or "").replace("Новый&#xA0;", "").replace("Новый\u00a0", "").strip()


def load_product_rules(db):
    short_names = {row["key_value"]: row["short_name"] for row in db.execute(
        "SELECT key_value,short_name FROM product_short_names WHERE key_type='sku'")}
    groups = {row["group_id"]: dict(row) for row in db.execute("""
      SELECT group_id,primary_offer_id,primary_sku FROM product_group_config
      WHERE status='active'""")}
    members = {}
    for row in db.execute("SELECT group_id,key_type,key_value FROM product_group_members"):
        if row["group_id"] in groups:
            members[(row["key_type"], row["key_value"])] = row["group_id"]
    names = {(row["offer_id"], row["sku"]): clean_product_name(row["product_name_raw"])
             for row in db.execute("""WITH preferred AS (
               SELECT offer_id,sku,
                 COALESCE(MIN(CASE WHEN source='api' THEN rowid END),MIN(rowid)) item_rowid
               FROM order_items WHERE NULLIF(offer_id,'') IS NOT NULL GROUP BY offer_id,sku)
             SELECT i.offer_id,i.sku,i.product_name_raw FROM preferred p
             JOIN order_items i ON i.rowid=p.item_rowid""")}
    inferred = {}
    for offer_id, sku in names:
        group_id = members.get(("offer_id", offer_id))
        if group_id:
            inferred.setdefault(sku, set()).add(group_id)
    inferred = {sku: next(iter(group_ids)) for sku, group_ids in inferred.items() if len(group_ids) == 1}
    return {"short_names": short_names, "groups": groups, "members": members,
            "inferred": inferred, "names": names}


def resolve_product(rules, sku="", offer_id="", raw_name=""):
    sku, offer_id = str(sku or ""), str(offer_id or "")
    sku_group = rules["members"].get(("sku", sku))
    offer_group = rules["members"].get(("offer_id", offer_id))
    group_id = (None if sku_group and offer_group and sku_group != offer_group
                else sku_group or offer_group or rules["inferred"].get(sku))
    group = rules["groups"].get(group_id)
    if group:
        primary_offer, primary_sku = group["primary_offer_id"], group["primary_sku"]
        platform_name = rules["names"].get((primary_offer, primary_sku), "")
        return {"identity": primary_offer, "group_id": group_id, "primary_offer_id": primary_offer,
                "primary_sku": primary_sku, "display_name": rules["short_names"].get(primary_sku)
                or platform_name or PLACEHOLDER, "platform_name": platform_name}
    platform_name = clean_product_name(raw_name)
    return {"identity": sku or offer_id, "group_id": None, "primary_offer_id": None,
            "primary_sku": None, "display_name": rules["short_names"].get(sku)
            or platform_name or PLACEHOLDER, "platform_name": platform_name}
