from . import client


def analytics_data(shop_id, date_from, date_to, sku="", limit=1000, offset=0):
    filters = [{"key": "sku", "op": "EQ", "value": str(sku)}] if sku else []
    return client._post(shop_id, "/v1/analytics/data", {
        "date_from": date_from, "date_to": date_to, "dimension": ["sku"],
        "metrics": ["hits_view_search", "hits_view_pdp", "hits_tocart",
                    "session_view_pdp", "ordered_units", "revenue"],
        "filters": filters, "sort": [{"key": "hits_view_search", "order": "DESC"}],
        "limit": limit, "offset": offset,
    })


def product_queries(shop_id, date_from, date_to, skus, page=0, page_size=1000):
    return client._post(shop_id, "/v1/analytics/product-queries", {
        "date_from": date_from, "date_to": date_to, "page": page, "page_size": page_size,
        "skus": skus, "sort_by": "BY_SEARCHES", "sort_dir": "DESCENDING",
    })


def product_query_details(shop_id, date_from, date_to, skus, page=0, page_size=100):
    return client._post(shop_id, "/v1/analytics/product-queries/details", {
        "date_from": date_from, "date_to": date_to, "limit_by_sku": 15,
        "page": page, "page_size": page_size, "skus": skus,
        "sort_by": "BY_SEARCHES", "sort_dir": "DESCENDING",
    })
