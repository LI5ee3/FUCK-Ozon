from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from app import db
from app.ozon.finance import TOTAL_FIELDS, fetch_finance_transactions, sync_finance_transactions
from tests.support import DatabaseTestCase


LIST_PATH = "/v3/finance/transaction/list"


def totals(**values):
    return {field: values.get(field, 0) for field in TOTAL_FIELDS}


def operation(operation_id, amount, **values):
    return {
        "operation_id": operation_id,
        "operation_type": values.get("operation_type", "Operation"),
        "operation_type_name": values.get("operation_type_name", "操作"),
        "operation_date": values.get("operation_date", "2026-08-01T00:00:00+03:00"),
        "type": values.get("type", "orders"),
        "amount": amount,
        "accruals_for_sale": values.get("accruals_for_sale", amount),
        "sale_commission": values.get("sale_commission", 0),
        "delivery_charge": values.get("delivery_charge", 0),
        "return_delivery_charge": values.get("return_delivery_charge", 0),
        "posting": values.get("posting", {}),
        "items": values.get("items", []),
        "services": values.get("services", []),
        "future_field": {"kept": True},
    }


class FinanceSyncTest(DatabaseTestCase):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    end = datetime(2026, 8, 2, tzinfo=timezone.utc)

    def test_single_page_saves_finance_fields_and_raw_payload(self):
        first = operation(
            "100", 12.34,
            posting={"posting_number": "P-1", "order_date": "2026-07-31", "delivery_schema": "FBO",
                     "warehouse_id": 42},
            items=[{"sku": "SKU-1", "name": "商品一"}],
            services=[{"name": "物流", "price": -1.25}],
        )
        second = operation("101", -6.46, operation_type="MarketplaceMarketingActionCostOperation")
        requests = []

        def post(shop_id, path, payload):
            requests.append((shop_id, path, payload))
            if path == LIST_PATH:
                return {"result": {"operations": [first, second], "page_count": 1, "row_count": 2}}
            return {"result": totals(accruals_for_sale=5.88)}

        with patch("app.ozon.finance.client._post", side_effect=post):
            result = sync_finance_transactions(1, self.start, self.end)

        self.assertEqual(result, {"records": 2, "chunks": 1})
        self.assertEqual(requests[0][1], LIST_PATH)
        self.assertEqual(requests[1][1], "/v3/finance/transaction/totals")
        self.assertEqual(requests[0][2]["page_size"], 1000)
        with db.connect() as connection:
            rows = connection.execute("""SELECT operation_id,operation_type,transaction_type,operation_date,
              posting_number,order_date,delivery_schema,warehouse_id,amount,currency,payload_json
              FROM ozon_finance_transactions ORDER BY operation_id""").fetchall()
            item = connection.execute("""SELECT sku,name FROM ozon_finance_transaction_items
              WHERE operation_id='100'""").fetchone()
            service = connection.execute("""SELECT service_name,price FROM ozon_finance_transaction_services
              WHERE operation_id='100'""").fetchone()
        self.assertEqual(tuple(rows[0][:10]),
                         ("100", "Operation", "orders", "2026-08-01T00:00:00+03:00", "P-1",
                          "2026-07-31", "FBO", "42", 12.34, "USD"))
        self.assertEqual(tuple(rows[1][:10]),
                         ("101", "MarketplaceMarketingActionCostOperation", "orders",
                          "2026-08-01T00:00:00+03:00", None, None, "", None, -6.46, "USD"))
        self.assertEqual(tuple(item), ("SKU-1", "商品一"))
        self.assertEqual(tuple(service), ("物流", -1.25))
        self.assertTrue(json.loads(rows[0][10])["future_field"]["kept"])

    def test_page_pagination_uses_page_and_validates_row_count(self):
        pages = [[operation("1", 1), operation("2", 2)], [operation("3", 3)]]
        requests = []

        def post(_shop_id, path, payload):
            self.assertEqual(path, LIST_PATH)
            requests.append(payload)
            return {"result": {"operations": pages[payload["page"] - 1], "page_count": 2, "row_count": 3}}

        with patch("app.ozon.finance.client._post", side_effect=post):
            records = fetch_finance_transactions(1, self.start, self.end)
        self.assertEqual([row["operation_id"] for row in records], ["1", "2", "3"])
        self.assertEqual([request["page"] for request in requests], [1, 2])
        self.assertTrue(all(request["page_size"] == 1000 for request in requests))
        self.assertTrue(all("cursor" not in request for request in requests))

    def test_row_count_mismatch_fails_before_totals_or_database_write(self):
        response = {"result": {"operations": [operation("1", 1)], "page_count": 1, "row_count": 2}}
        with patch("app.ozon.finance.client._post", return_value=response) as post:
            with self.assertRaisesRegex(RuntimeError, "row_count"):
                sync_finance_transactions(1, self.start, self.end)
        self.assertEqual(post.call_count, 1)
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ozon_finance_transactions").fetchone()[0], 0)

    def test_empty_page_count_is_a_valid_empty_chunk(self):
        def post(_shop_id, path, _payload):
            if path == LIST_PATH:
                return {"result": {"operations": [], "page_count": 0, "row_count": 0}}
            return {"result": totals()}

        with patch("app.ozon.finance.client._post", side_effect=post):
            result = sync_finance_transactions(1, self.start, self.end)
        self.assertEqual(result["records"], 0)
        with db.connect() as connection:
            row = connection.execute("""SELECT api_row_count,fetched_operation_count,
              local_amount_total,remote_component_total,difference,reconciliation_status
              FROM ozon_finance_reconciliations""").fetchone()
        self.assertEqual(tuple(row), (0, 0, 0.0, 0.0, 0.0, "matched"))

    def test_missing_posting_and_unknown_operation_type_are_saved(self):
        row = operation("marketing-1", -6.46,
                         operation_type="FutureOzonFeeOperation",
                         posting={"posting_number": ""}, items=[], services=[])

        def post(_shop_id, path, _payload):
            if path == LIST_PATH:
                return {"result": {"operations": [row], "page_count": 1, "row_count": 1}}
            return {"result": totals(accruals_for_sale=-6.46)}

        with patch("app.ozon.finance.client._post", side_effect=post):
            sync_finance_transactions(1, self.start, self.end)
        with db.connect() as connection:
            stored = connection.execute("""SELECT operation_type,posting_number,amount
              FROM ozon_finance_transactions WHERE operation_id='marketing-1'""").fetchone()
        self.assertEqual(tuple(stored), ("FutureOzonFeeOperation", None, -6.46))

    def test_upsert_replaces_stale_children_and_is_idempotent(self):
        first = operation("same", 5, items=[{"sku": "A", "name": "A"}],
                          services=[{"name": "A", "price": 1}, {"name": "B", "price": 2}])
        second = operation("same", 7, items=[], services=[{"name": "C", "price": -3}])
        current = [first, second, second]

        def post(_shop_id, path, _payload):
            row = current.pop(0) if path == LIST_PATH else None
            if path == LIST_PATH:
                return {"result": {"operations": [row], "page_count": 1, "row_count": 1}}
            return {"result": totals(accruals_for_sale=(first if len(current) == 2 else second)["amount"])}

        with patch("app.ozon.finance.client._post", side_effect=post):
            sync_finance_transactions(1, self.start, self.end)
            sync_finance_transactions(1, self.start, self.end)
            sync_finance_transactions(1, self.start, self.end)
        with db.connect() as connection:
            transaction_count = connection.execute("SELECT COUNT(*) FROM ozon_finance_transactions").fetchone()[0]
            items = connection.execute("SELECT COUNT(*) FROM ozon_finance_transaction_items").fetchone()[0]
            services = [tuple(row) for row in connection.execute(
                "SELECT service_name,price FROM ozon_finance_transaction_services")]
            amount = connection.execute("SELECT amount FROM ozon_finance_transactions WHERE operation_id='same'").fetchone()[0]
        self.assertEqual((transaction_count, items, services, amount), (1, 0, [("C", -3.0)], 7.0))

    def test_multi_month_range_is_split_before_each_api_call(self):
        requests = []

        def post(_shop_id, path, payload):
            requests.append((path, payload))
            if path == LIST_PATH:
                return {"result": {"operations": [], "page_count": 0, "row_count": 0}}
            return {"result": totals()}

        start = datetime(2026, 7, 15, tzinfo=timezone.utc)
        end = datetime(2026, 10, 10, tzinfo=timezone.utc)
        with patch("app.ozon.finance.client._post", side_effect=post):
            result = sync_finance_transactions(1, start, end)
        list_requests = [payload for path, payload in requests if path == LIST_PATH]
        self.assertEqual((result["chunks"], len(list_requests)), (4, 4))
        for payload in list_requests:
            date_range = payload["filter"]["date"]
            from_value = datetime.fromisoformat(date_range["from"].replace("Z", "+00:00"))
            to_value = datetime.fromisoformat(date_range["to"].replace("Z", "+00:00"))
            self.assertLessEqual(to_value - from_value, timedelta(days=31))
        self.assertEqual(list_requests[0]["filter"]["date"]["from"], "2026-07-15T00:00:00Z")
        self.assertEqual(list_requests[-1]["filter"]["date"]["to"], "2026-10-10T00:00:00Z")

    def test_totals_mismatch_is_saved_without_changing_transaction_amount(self):
        row = operation("mismatch", 10)

        def post(_shop_id, path, _payload):
            if path == LIST_PATH:
                return {"result": {"operations": [row], "page_count": 1, "row_count": 1}}
            return {"result": totals(accruals_for_sale=9)}

        with patch("app.ozon.finance.client._post", side_effect=post):
            sync_finance_transactions(1, self.start, self.end)
        with db.connect() as connection:
            amount = connection.execute("SELECT amount FROM ozon_finance_transactions").fetchone()[0]
            reconciliation = connection.execute("""SELECT local_amount_total,remote_component_total,
              difference,reconciliation_status FROM ozon_finance_reconciliations""").fetchone()
        self.assertEqual(amount, 10.0)
        self.assertEqual(tuple(reconciliation), (10.0, 9.0, 1.0, "mismatch"))

    def test_currency_is_snapshotted_from_shop_at_write_time(self):
        row = operation("currency", 1)

        def post(_shop_id, path, _payload):
            if path == LIST_PATH:
                return {"result": {"operations": [row], "page_count": 1, "row_count": 1}}
            return {"result": totals(accruals_for_sale=1)}

        with patch("app.ozon.finance.client._post", side_effect=post):
            sync_finance_transactions(1, self.start, self.end)
        with db.connect() as connection:
            currency = connection.execute("SELECT currency FROM ozon_finance_transactions").fetchone()[0]
        self.assertEqual(currency, "USD")

    def test_non_finite_amount_is_rejected_without_silent_zero(self):
        row = operation("bad", float("nan"))

        def post(_shop_id, path, _payload):
            if path == LIST_PATH:
                return {"result": {"operations": [row], "page_count": 1, "row_count": 1}}
            return {"result": totals()}

        with patch("app.ozon.finance.client._post", side_effect=post):
            with self.assertRaisesRegex(ValueError, "amount"):
                sync_finance_transactions(1, self.start, self.end)
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ozon_finance_transactions").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
