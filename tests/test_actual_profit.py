from decimal import Decimal
import unittest

from app import db
from app.actual_profit import list_actual_order_profits
from app.erp_costs import import_erp_costs
from app.routers.actual_profit import actual_order_profits
from tests.support import DatabaseTestCase, add_item, add_order
from tests.test_erp_costs import row, workbook_bytes


def add_finance(connection, shop_id, operation_id, amount, posting_number,
                currency=None, operation_date="2026-04-10T00:00:00Z",
                **components):
    currency = currency or ("USD" if shop_id == 1 else "CNY")
    connection.execute("""INSERT INTO ozon_finance_transactions(
      shop_id,operation_id,operation_type,operation_type_name,transaction_type,operation_date,
      posting_number,order_date,delivery_schema,warehouse_id,amount,accruals_for_sale,
      sale_commission,delivery_charge,return_delivery_charge,currency,payload_json,fetched_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (shop_id, operation_id, "Operation", "操作", "orders", operation_date,
       posting_number, None, "", None, amount,
       components.get("accruals_for_sale", 999), components.get("sale_commission", -888),
       components.get("delivery_charge", -777), components.get("return_delivery_charge", -666),
       currency, "{}", "2026-09-01T00:00:00Z"))


def add_erp_fact(connection, shop_id, order, sku, quantity=1, offer_id="ERP-OFFER",
                 total_cost="60", exchange_rate="1"):
    batch_id = connection.execute("""INSERT INTO erp_cost_import_batches(
      shop_id,filename,row_count,parsed_count,inserted_count,updated_count,unchanged_count,imported_at)
      VALUES(?, 'test.xlsx',1,1,1,0,0,'2026-09-01T00:00:00Z')""", (shop_id,)).lastrowid
    connection.execute("""INSERT INTO erp_order_item_costs(
      shop_id,erp_order_number,ozon_sku,offer_id,quantity,unit_cost,
      exchange_rate_original,total_cost,platform_link,source_batch_id,
      source_row_no,raw_payload_json,imported_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (shop_id, order, sku, offer_id, quantity, total_cost, exchange_rate, total_cost,
       "https://www.ozon.ru/product/test-1936515175/", batch_id, 1, "{}",
       "2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z"))


def decimal(value):
    return Decimal(str(value))


class ActualProfitTest(DatabaseTestCase):
    start = "2026-04-01T00:00:00Z"
    end = "2026-05-01T00:00:00Z"

    def profits(self, shop_id=1, q="", page=1, size=50):
        return list_actual_order_profits(shop_id, self.start, self.end, q, page, size)

    def test_shop_two_cny_profit(self):
        with db.transaction() as connection:
            add_order(connection, 2, "CNY-1", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 2, "CNY-1", "FBP", "SKU-1")
            add_erp_fact(connection, 2, "CNY-1", "SKU-1", total_cost="60")
            add_finance(connection, 2, "cny-1", 100, "CNY-1")

        result = actual_order_profits(2, page=1, size=50, date_from="2026-04-01", date_to="2026-04-30")
        item = result["items"][0]
        self.assertEqual((item["finance"]["currency"], item["erp_cost"]["status"], item["profit_status"]),
                         ("CNY", "complete", "ready"))
        self.assertEqual((decimal(item["finance"]["net_cny"]), decimal(item["erp_cost"]["total_cost_cny"]),
                          decimal(item["actual_profit_cny"])), (Decimal("100"), Decimal("60"), Decimal("40")))

    def test_shop_one_usd_uses_erp_rate_for_cny(self):
        with db.transaction() as connection:
            add_order(connection, 1, "USD-1", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 1, "USD-1", "FBP", "SKU-1")
            add_erp_fact(connection, 1, "USD-1", "SKU-1", total_cost="500", exchange_rate="6.75")
            add_finance(connection, 1, "usd-1", 100, "USD-1")

        item = self.profits(1)["items"][0]
        self.assertEqual((decimal(item["finance"]["net_cny"]), decimal(item["actual_profit_cny"])),
                         (Decimal("675.00"), Decimal("175.00")))

    def test_finance_net_sums_amount_only(self):
        with db.transaction() as connection:
            add_order(connection, 2, "AMOUNT-1", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 2, "AMOUNT-1", "FBP", "SKU-1")
            add_erp_fact(connection, 2, "AMOUNT-1", "SKU-1", total_cost="60")
            add_finance(connection, 2, "amount-1", 100, "AMOUNT-1", accruals_for_sale=9999,
                        sale_commission=-321, delivery_charge=456)
            add_finance(connection, 2, "amount-2", -10, "AMOUNT-1", accruals_for_sale=-9999)
            add_finance(connection, 2, "amount-3", -20, "AMOUNT-1", delivery_charge=7777)

        item = self.profits(2)["items"][0]
        self.assertEqual(decimal(item["finance"]["net_amount"]), Decimal("70"))
        self.assertEqual(decimal(item["actual_profit_cny"]), Decimal("10"))

    def test_late_finance_operation_is_included_for_old_order(self):
        with db.transaction() as connection:
            add_order(connection, 2, "LATE-1", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 2, "LATE-1", "FBP", "SKU-1")
            add_erp_fact(connection, 2, "LATE-1", "SKU-1", total_cost="10")
            add_finance(connection, 2, "late-1", 100, "LATE-1", operation_date="2026-04-10T00:00:00Z")
            add_finance(connection, 2, "late-2", -20, "LATE-1", operation_date="2026-05-20T00:00:00Z")

        item = self.profits(2)["items"][0]
        self.assertEqual(decimal(item["finance"]["net_amount"]), Decimal("80"))

    def test_missing_erp_cost_blocks_profit(self):
        with db.transaction() as connection:
            add_order(connection, 2, "NO-ERP", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 2, "NO-ERP", "FBP", "SKU-1")
            add_finance(connection, 2, "no-erp", 100, "NO-ERP")

        item = self.profits(2)["items"][0]
        self.assertIsNone(item["actual_profit_cny"])
        self.assertEqual(item["incomplete_reasons"], ["missing_erp_cost"])
        self.assertIsNone(item["erp_cost"]["total_cost_cny"])

    def test_quantity_mismatch_blocks_profit(self):
        with db.transaction() as connection:
            add_order(connection, 2, "QTY-1", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 2, "QTY-1", "FBP", "SKU-1", 1)
            add_erp_fact(connection, 2, "QTY-1", "SKU-1", quantity=2, total_cost="120")
            add_finance(connection, 2, "qty-1", 100, "QTY-1")

        item = self.profits(2)["items"][0]
        self.assertIsNone(item["actual_profit_cny"])
        self.assertEqual(item["incomplete_reasons"], ["quantity_mismatch"])

    def test_missing_finance_is_distinct_from_zero_net(self):
        with db.transaction() as connection:
            add_order(connection, 2, "NO-FINANCE", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 2, "NO-FINANCE", "FBP", "SKU-1")
            add_erp_fact(connection, 2, "NO-FINANCE", "SKU-1", total_cost="60")

        item = self.profits(2)["items"][0]
        self.assertEqual(item["finance"]["status"], "missing")
        self.assertIsNone(item["finance"]["net_amount"])
        self.assertIsNone(item["actual_profit_cny"])
        self.assertEqual(item["incomplete_reasons"], ["missing_finance"])

    def test_zero_finance_net_is_available_and_can_make_negative_profit(self):
        with db.transaction() as connection:
            add_order(connection, 2, "ZERO-1", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 2, "ZERO-1", "FBP", "SKU-1")
            add_erp_fact(connection, 2, "ZERO-1", "SKU-1", total_cost="60")
            add_finance(connection, 2, "zero-1", 100, "ZERO-1")
            add_finance(connection, 2, "zero-2", -100, "ZERO-1")

        item = self.profits(2)["items"][0]
        self.assertEqual((item["finance"]["status"], decimal(item["finance"]["net_cny"]),
                          decimal(item["actual_profit_cny"])), ("available", Decimal("0"), Decimal("-60")))

    def test_shop_one_missing_exchange_rate_blocks_profit(self):
        with db.transaction() as connection:
            add_order(connection, 1, "NO-RATE", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 1, "NO-RATE", "FBP", "SKU-1")
            add_erp_fact(connection, 1, "NO-RATE", "SKU-1", total_cost="60", exchange_rate=None)
            add_finance(connection, 1, "no-rate", 100, "NO-RATE")

        item = self.profits(1)["items"][0]
        self.assertIsNone(item["actual_profit_cny"])
        self.assertIsNone(item["finance"]["net_cny"])
        self.assertEqual(item["incomplete_reasons"], ["missing_exchange_rate"])

    def test_shop_one_exchange_rate_mismatch_blocks_profit(self):
        with db.transaction() as connection:
            add_order(connection, 1, "RATE-MISMATCH", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 1, "RATE-MISMATCH", "FBP", "SKU-A")
            add_item(connection, 1, "RATE-MISMATCH", "FBP", "SKU-B")
            add_erp_fact(connection, 1, "RATE-MISMATCH", "SKU-A", total_cost="10", exchange_rate="6.75")
            add_erp_fact(connection, 1, "RATE-MISMATCH", "SKU-B", total_cost="20", exchange_rate="6.80")
            add_finance(connection, 1, "rate-mismatch", 100, "RATE-MISMATCH")

        item = self.profits(1)["items"][0]
        self.assertIsNone(item["actual_profit_cny"])
        self.assertIsNone(item["erp_cost"]["exchange_rate_original"])
        self.assertEqual(item["incomplete_reasons"], ["exchange_rate_mismatch"])

    def test_offer_id_mismatch_does_not_block_profit(self):
        with db.transaction() as connection:
            add_order(connection, 2, "OFFER-MISMATCH", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 2, "OFFER-MISMATCH", "FBP", "SKU-1", offer_id="ORDER-OFFER")
            add_erp_fact(connection, 2, "OFFER-MISMATCH", "SKU-1", offer_id="ERP-OFFER", total_cost="60")
            add_finance(connection, 2, "offer-mismatch", 100, "OFFER-MISMATCH")

        item = self.profits(2)["items"][0]
        self.assertEqual((item["profit_status"], item["erp_cost"]["offer_id_mismatch_items"],
                          decimal(item["actual_profit_cny"])), ("ready", 1, Decimal("40")))

    def test_latest_erp_correction_changes_profit_without_snapshot(self):
        with db.transaction() as connection:
            add_order(connection, 1, "CORRECT-1", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 1, "CORRECT-1", "FBP", "1936515175", 2, offer_id="offer-1")
            add_finance(connection, 1, "correct-1", 100, "CORRECT-1")
        import_erp_costs(1, "first.xlsx", workbook_bytes([
            row(order="CORRECT-1", quantity=2, cost="30", rate="6.75")
        ]))
        first = self.profits(1)["items"][0]
        import_erp_costs(1, "correction.xlsx", workbook_bytes([
            row(order="CORRECT-1", quantity=2, cost="24", rate="6.75")
        ]))
        corrected = self.profits(1)["items"][0]
        self.assertEqual((decimal(first["erp_cost"]["total_cost_cny"]), decimal(first["actual_profit_cny"])),
                         (Decimal("60"), Decimal("615")))
        self.assertEqual((decimal(corrected["erp_cost"]["total_cost_cny"]), decimal(corrected["actual_profit_cny"])),
                         (Decimal("48"), Decimal("627")))

    def test_blank_posting_finance_is_not_assigned_to_order(self):
        with db.transaction() as connection:
            add_order(connection, 2, "NO-BLANK", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 2, "NO-BLANK", "FBP", "SKU-1")
            add_erp_fact(connection, 2, "NO-BLANK", "SKU-1", total_cost="60")
            add_finance(connection, 2, "blank", 100000, None)
            add_finance(connection, 2, "blank-space", 100000, " ")

        item = self.profits(2)["items"][0]
        self.assertEqual(item["finance"]["status"], "missing")
        self.assertEqual(item["incomplete_reasons"], ["missing_finance"])

    def test_finance_currency_mismatch_blocks_profit(self):
        with db.transaction() as connection:
            add_order(connection, 1, "BAD-CURRENCY", "FBP", "2026-04-10T00:00:00Z")
            add_item(connection, 1, "BAD-CURRENCY", "FBP", "SKU-1")
            add_erp_fact(connection, 1, "BAD-CURRENCY", "SKU-1", total_cost="60", exchange_rate="6.75")
            add_finance(connection, 1, "bad-currency", 100, "BAD-CURRENCY", currency="CNY")

        item = self.profits(1)["items"][0]
        self.assertEqual(item["finance"]["currency"], "CNY")
        self.assertIsNone(item["actual_profit_cny"])
        self.assertEqual(item["incomplete_reasons"], ["finance_currency_mismatch"])

    def test_order_without_items_is_incomplete(self):
        with db.transaction() as connection:
            add_order(connection, 2, "NO-ITEMS", "FBP", "2026-04-10T00:00:00Z")
            add_finance(connection, 2, "no-items", 100, "NO-ITEMS")

        item = self.profits(2)["items"][0]
        self.assertIsNone(item["actual_profit_cny"])
        self.assertEqual(item["incomplete_reasons"], ["missing_order_items"])


if __name__ == "__main__":
    unittest.main()
