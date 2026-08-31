from datetime import datetime, timezone
import math

from .db import connect
from .ozon import client


PRODUCT_PRICES_PATH = "/v5/product/info/prices"
PRODUCT_PRICES_LIMIT = 100


class ProductCommissionInputError(ValueError):
    pass


class ProductCommissionUnavailable(RuntimeError):
    pass


def _validate_shop_id(value):
    if type(value) is not int or value not in (1, 2):
        raise ProductCommissionInputError("未知店铺")
    return value


def _validate_sku(value):
    if type(value) not in (str, int):
        raise ProductCommissionInputError("Ozon SKU类型无效")
    sku = str(value).strip()
    if not sku:
        raise ProductCommissionInputError("Ozon SKU不能为空")
    return sku


def _local_offer_id(shop_id, sku):
    with connect() as db:
        exists = db.execute("""SELECT 1 FROM order_items
          WHERE shop_id=? AND trim(sku)=? LIMIT 1""", (shop_id, sku)).fetchone()
        if not exists:
            raise ProductCommissionInputError(f"店铺{shop_id}下未找到 Ozon SKU {sku}")
        rows = db.execute("""SELECT DISTINCT trim(offer_id) offer_id
          FROM order_items
          WHERE shop_id=? AND trim(sku)=? AND NULLIF(trim(offer_id),'') IS NOT NULL
          ORDER BY offer_id""", (shop_id, sku)).fetchall()
    offer_ids = [row["offer_id"] for row in rows]
    if not offer_ids:
        raise ProductCommissionInputError(f"店铺{shop_id}的 Ozon SKU {sku} 没有可解析的 offer_id")
    if len(offer_ids) > 1:
        raise ProductCommissionInputError(
            f"店铺{shop_id}的 Ozon SKU {sku} 对应多个不同 offer_id，无法安全查询平台佣金")
    return offer_ids[0]


def _unavailable(message):
    raise ProductCommissionUnavailable(message)


def _price_item(response, offer_id):
    if not isinstance(response, dict) or not isinstance(response.get("items"), list):
        _unavailable("Ozon佣金响应格式无效")
    items = response["items"]
    if not items or any(not isinstance(item, dict) for item in items):
        _unavailable("Ozon佣金响应未返回唯一商品")
    matches = [item for item in items if item.get("offer_id") == offer_id]
    if len(matches) != 1:
        if not matches:
            _unavailable(f"Ozon返回的 offer_id 与本地商品不一致（应为 {offer_id}）")
        _unavailable("Ozon佣金响应返回多个相同 offer_id 商品")
    return matches[0]


def _percent(commissions, field):
    if field not in commissions or commissions[field] is None:
        return None
    value = commissions[field]
    if type(value) not in (int, float):
        _unavailable(f"Ozon返回的 {field} 不是合法百分比")
    try:
        normalized = float(value)
    except (OverflowError, ValueError):
        _unavailable(f"Ozon返回的 {field} 不是合法百分比")
    if not math.isfinite(normalized) or not 0 <= normalized <= 100:
        _unavailable(f"Ozon返回的 {field} 不是合法百分比")
    return normalized


def _product_id(value):
    if value is None:
        return None
    if type(value) not in (int, str):
        _unavailable("Ozon返回的 product_id 类型无效")
    return value


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def get_product_commission(shop_id, sku):
    shop_id = _validate_shop_id(shop_id)
    sku = _validate_sku(sku)
    offer_id = _local_offer_id(shop_id, sku)
    payload = {
        "filter": {"offer_id": [offer_id], "visibility": "ALL"},
        "limit": PRODUCT_PRICES_LIMIT,
    }
    try:
        response = client._post(shop_id, PRODUCT_PRICES_PATH, payload)
    except Exception as error:
        raise ProductCommissionUnavailable(f"Ozon API请求失败：{error}") from error
    item = _price_item(response, offer_id)
    commissions = item.get("commissions")
    if not isinstance(commissions, dict):
        _unavailable("Ozon佣金字段缺失或格式无效")
    return {
        "shop_id": shop_id,
        "sku": sku,
        "offer_id": offer_id,
        "product_id": _product_id(item.get("product_id")),
        "sales_percent_fbp": _percent(commissions, "sales_percent_fbp"),
        "sales_percent_rfbs": _percent(commissions, "sales_percent_rfbs"),
        "fetched_at": _utc_now(),
    }
