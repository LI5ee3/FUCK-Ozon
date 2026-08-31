from datetime import datetime, timezone
import math

from .db import connect
from .ozon import client


PRODUCT_INFO_PATH = "/v3/product/info/list"
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


def _validate_local_sku(shop_id, sku):
    with connect() as db:
        exists = db.execute("""SELECT 1 FROM order_items
          WHERE shop_id=? AND trim(sku)=? LIMIT 1""", (shop_id, sku)).fetchone()
    if not exists:
        raise ProductCommissionInputError(f"店铺{shop_id}下未找到 Ozon SKU {sku}")


def _unavailable(message):
    raise ProductCommissionUnavailable(message)


def _sku_text(value):
    if type(value) not in (str, int):
        return ""
    return str(value).strip()


def _info_item(response, sku):
    if not isinstance(response, dict) or not isinstance(response.get("items"), list):
        _unavailable("Ozon商品响应格式无效")
    items = response["items"]
    if not items or any(not isinstance(item, dict) for item in items):
        _unavailable("Ozon商品响应未返回唯一商品")
    matches = []
    for item in items:
        values = []
        if "sku" in item:
            value = _sku_text(item["sku"])
            if not value:
                _unavailable("Ozon商品响应中的 SKU 无效")
            values.append(value)
        sources = item.get("sources")
        if sources is not None and not isinstance(sources, list):
            _unavailable("Ozon商品响应中的 sources 格式无效")
        for source in sources or []:
            if not isinstance(source, dict) or "sku" not in source:
                _unavailable("Ozon商品响应中的 sources 格式无效")
            value = _sku_text(source["sku"])
            if not value:
                _unavailable("Ozon商品响应中的 SKU 无效")
            values.append(value)
        if sku in values or (len(items) == 1 and "sku" not in item and "sources" not in item):
            matches.append(item)
        elif not values and len(items) > 1:
            _unavailable("Ozon商品响应无法验证请求的 Ozon SKU")
    if len(matches) != 1:
        _unavailable("Ozon商品响应未唯一匹配请求的 Ozon SKU")
    return matches[0]


def _product_id(value):
    if type(value) is int:
        if value <= 0:
            _unavailable("Ozon返回的 product_id 无效")
        return value
    if type(value) is str:
        normalized = value.strip()
        if not normalized.isdigit() or int(normalized) <= 0:
            _unavailable("Ozon返回的 product_id 无效")
        return normalized
    _unavailable("Ozon返回的 product_id 类型无效")


def _product_id_text(value):
    if type(value) is int and value > 0:
        return str(value)
    if type(value) is str and value.strip().isdigit() and int(value.strip()) > 0:
        return str(int(value.strip()))
    return None


def _current_offer_id(value):
    if type(value) is not str or not value.strip():
        _unavailable("Ozon返回的当前 offer_id 无效")
    return value.strip()


def _price_item(response, product_id, offer_id):
    if not isinstance(response, dict) or not isinstance(response.get("items"), list):
        _unavailable("Ozon佣金响应格式无效")
    items = response["items"]
    if not items or any(not isinstance(item, dict) for item in items):
        _unavailable("Ozon佣金响应未返回唯一商品")
    expected_product_id = _product_id_text(product_id)
    if expected_product_id is None:
        _unavailable("Ozon返回的 product_id 无效")
    product_ids = [_product_id_text(item.get("product_id")) for item in items]
    if any(value is None for value in product_ids):
        _unavailable("Ozon佣金响应中的 product_id 无效")
    matches = [item for item, value in zip(items, product_ids) if value == expected_product_id]
    if len(matches) != 1:
        if not matches:
            _unavailable(f"Ozon返回的 product_id 与当前商品不一致（应为 {product_id}）")
        _unavailable("Ozon佣金响应返回多个相同 product_id 商品")
    if _current_offer_id(matches[0].get("offer_id")) != offer_id:
        _unavailable("Ozon佣金响应中的 offer_id 与当前商品不一致")
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


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def get_product_commission(shop_id, sku):
    shop_id = _validate_shop_id(shop_id)
    sku = _validate_sku(sku)
    _validate_local_sku(shop_id, sku)
    try:
        info_response = client._post(shop_id, PRODUCT_INFO_PATH, {"sku": [sku]})
    except Exception as error:
        raise ProductCommissionUnavailable(f"Ozon API请求失败：{error}") from error
    info_item = _info_item(info_response, sku)
    product_id = _product_id(info_item.get("id"))
    offer_id = _current_offer_id(info_item.get("offer_id"))
    payload = {
        "filter": {"product_id": [str(product_id)], "visibility": "ALL"},
        "limit": PRODUCT_PRICES_LIMIT,
    }
    try:
        response = client._post(shop_id, PRODUCT_PRICES_PATH, payload)
    except Exception as error:
        raise ProductCommissionUnavailable(f"Ozon API请求失败：{error}") from error
    item = _price_item(response, product_id, offer_id)
    commissions = item.get("commissions")
    if not isinstance(commissions, dict):
        _unavailable("Ozon佣金字段缺失或格式无效")
    return {
        "shop_id": shop_id,
        "sku": sku,
        "offer_id": offer_id,
        "product_id": product_id,
        "sales_percent_fbp": _percent(commissions, "sales_percent_fbp"),
        "sales_percent_rfbs": _percent(commissions, "sales_percent_rfbs"),
        "fetched_at": _utc_now(),
    }
