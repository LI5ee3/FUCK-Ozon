import unittest

from app import db
from app.erp_cost_matching import (get_erp_cost_coverage, list_erp_cost_issues,
                                    resolve_erp_cost_for_order_item)
from app.erp_costs import import_erp_costs
from tests.support import DatabaseTestCase, add_item, add_order
from tests.test_erp_costs import row, workbook_bytes


def add_erp_fact(connection, shop_id=1, order="M-001", sku="SKU-1", quantity=1,
                 offer_id="OFFER-1", unit_cost="10", total_cost="10"):
    batch_id = connection.execute("""
      INSERT INTO erp_cost_import_batches(
        shop_id,filename,row_count,parsed_count,inserted_count,updated_count,unchanged_count,imported_at)
      VALUES(?, 'test.xlsx',1,1,1,0,0,'2026-09-01T00:00:00Z')
    """, (shop_id,)).lastrowid
    connection.execute("""
      INSERT INTO erp_order_item_costs(
        shop_id,erp_order_number,ozon_sku,offer_id,quantity,unit_cost,
        exchange_rate_original,total_cost,platform_link,source_batch_id,
        source_row_no,raw_payload_json,imported_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (shop_id, order, sku, offer_id, quantity, unit_cost, "7.2", total_cost,
          "https://www.ozon.ru/product/test-1936515175/", batch_id, 88, "{}",
          "2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z"))


class ErpCostMatchingTest(DatabaseTestCase):
    def test_empty_order_items_have_null_coverage_rate(self):
        coverage = get_erp_cost_coverage(1)

        self.assertEqual(coverage["order_items"]["total"], 0)
        self.assertIsNone(coverage["order_items"]["coverage_rate"])

    def test_exact_key_and_quantity_is_matched(self):
        with db.transaction() as connection:
            add_order(connection, 1, "M-001", "FBP")
            add_item(connection, 1, "M-001", "FBP", "SKU-1", 2, offer_id="OFFER-1")
            add_erp_fact(connection, quantity=2, total_cost="20")

        with db.connect() as connection:
            result = resolve_erp_cost_for_order_item(connection, 1, "M-001", "SKU-1", 2)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["erp_cost"]["unit_cost"], "10")
        self.assertFalse(result["offer_id_mismatch"])
        self.assertEqual(get_erp_cost_coverage(1)["order_items"], {
            "total": 1, "matched": 1, "missing_erp_cost": 0,
            "quantity_mismatch": 0, "coverage_rate": 1.0,
        })

    def test_missing_erp_cost_is_not_a_match(self):
        with db.transaction() as connection:
            add_order(connection, 1, "M-001", "FBP")
            add_item(connection, 1, "M-001", "FBP", "SKU-1", 1)

        with db.connect() as connection:
            result = resolve_erp_cost_for_order_item(connection, 1, "M-001", "SKU-1", 1)
        self.assertEqual(result, {
            "status": "missing_erp_cost", "erp_cost": None,
            "order_offer_id": None, "offer_id_mismatch": False,
        })
        coverage = get_erp_cost_coverage(1)
        self.assertEqual(coverage["order_items"]["missing_erp_cost"], 1)
        self.assertEqual(coverage["order_items"]["coverage_rate"], 0.0)
        self.assertEqual(coverage["erp_facts"]["total"], 0)

    def test_erp_fact_without_order_is_missing_order(self):
        with db.transaction() as connection:
            add_erp_fact(connection)

        coverage = get_erp_cost_coverage(1)
        self.assertEqual(coverage["erp_facts"], {
            "total": 1, "matched": 0, "missing_order": 1,
            "missing_order_item": 0, "quantity_mismatch": 0,
        })
        issue = list_erp_cost_issues(1, issue_type="missing_order")["items"][0]
        self.assertEqual(issue["posting_number"], "M-001")
        self.assertIsNone(issue["order_quantity"])
        self.assertEqual(issue["unit_cost"], "10")

    def test_existing_order_without_sku_is_missing_order_item(self):
        with db.transaction() as connection:
            add_order(connection, 1, "M-001", "FBP")
            add_erp_fact(connection)

        coverage = get_erp_cost_coverage(1)
        self.assertEqual(coverage["erp_facts"]["missing_order_item"], 1)
        self.assertEqual(coverage["erp_facts"]["missing_order"], 0)

    def test_quantity_mismatch_is_not_matched(self):
        with db.transaction() as connection:
            add_order(connection, 1, "M-001", "FBP")
            add_item(connection, 1, "M-001", "FBP", "SKU-1", 1, offer_id="OFFER-1")
            add_erp_fact(connection, quantity=2, total_cost="20")

        with db.connect() as connection:
            result = resolve_erp_cost_for_order_item(connection, 1, "M-001", "SKU-1", 1)
        self.assertEqual(result["status"], "quantity_mismatch")
        coverage = get_erp_cost_coverage(1)
        self.assertEqual(coverage["order_items"]["matched"], 0)
        self.assertEqual(coverage["order_items"]["quantity_mismatch"], 1)
        self.assertEqual(coverage["erp_facts"]["quantity_mismatch"], 1)

    def test_offer_mismatch_is_diagnostic_only(self):
        with db.transaction() as connection:
            add_order(connection, 1, "M-001", "FBP")
            add_item(connection, 1, "M-001", "FBP", "SKU-1", 1, offer_id="ORDER-OFFER")
            add_erp_fact(connection, offer_id="ERP-OFFER")

        with db.connect() as connection:
            result = resolve_erp_cost_for_order_item(connection, 1, "M-001", "SKU-1", 1)
        self.assertEqual(result["status"], "matched")
        self.assertTrue(result["offer_id_mismatch"])
        coverage = get_erp_cost_coverage(1)
        self.assertEqual(coverage["diagnostics"]["offer_id_mismatch"], 1)
        issue = list_erp_cost_issues(1, issue_type="offer_id_mismatch")["items"][0]
        self.assertEqual((issue["order_offer_id"], issue["erp_offer_id"]), ("ORDER-OFFER", "ERP-OFFER"))

    def test_shop_isolation_and_no_offer_fallback(self):
        with db.transaction() as connection:
            add_order(connection, 2, "M-001", "FBP")
            add_item(connection, 2, "M-001", "FBP", "SKU-1", 1, offer_id="OFFER-1")
            add_erp_fact(connection, shop_id=1)
            add_order(connection, 1, "M-002", "FBP")
            add_item(connection, 1, "M-002", "FBP", "SKU-B", 1, offer_id="SAME-OFFER")
            add_erp_fact(connection, order="M-002", sku="SKU-A", offer_id="SAME-OFFER")

        with db.connect() as connection:
            isolated = resolve_erp_cost_for_order_item(connection, 2, "M-001", "SKU-1", 1)
        self.assertEqual(isolated["status"], "missing_erp_cost")
        shop_two = get_erp_cost_coverage(2)
        self.assertEqual(shop_two["order_items"]["missing_erp_cost"], 1)
        self.assertEqual(get_erp_cost_coverage(1)["erp_facts"]["missing_order"], 1)
        fallback = get_erp_cost_coverage(1)
        self.assertEqual(fallback["order_items"]["missing_erp_cost"], 1)
        self.assertEqual(fallback["erp_facts"]["missing_order_item"], 1)

    def test_parent_order_number_does_not_fallback_to_posting_number(self):
        with db.transaction() as connection:
            connection.execute("""INSERT INTO orders(
              shop_id,posting_number,parent_order_no,channel,status_raw,source)
              VALUES(1,'POSTING-1','PARENT-1','FBP','已签收','test')""")
            add_item(connection, 1, "POSTING-1", "FBP", "SKU-1", 1)
            add_erp_fact(connection, order="PARENT-1")

        coverage = get_erp_cost_coverage(1)
        self.assertEqual(coverage["order_items"]["missing_erp_cost"], 1)
        self.assertEqual(coverage["erp_facts"]["missing_order"], 1)

    def test_coverage_summary_has_mutually_exclusive_state_totals(self):
        with db.transaction() as connection:
            add_order(connection, 1, "MATCH-1", "FBP")
            add_item(connection, 1, "MATCH-1", "FBP", "SKU-M", 1)
            add_erp_fact(connection, order="MATCH-1", sku="SKU-M")
            add_order(connection, 1, "MISSING-1", "FBP")
            add_item(connection, 1, "MISSING-1", "FBP", "SKU-X", 1)
            add_order(connection, 1, "MISMATCH-1", "FBP")
            add_item(connection, 1, "MISMATCH-1", "FBP", "SKU-Y", 1)
            add_erp_fact(connection, order="MISMATCH-1", sku="SKU-Y", quantity=2, total_cost="20")
            add_erp_fact(connection, order="ORPHAN-1", sku="SKU-Z")

        coverage = get_erp_cost_coverage(1)
        orders = coverage["order_items"]
        facts = coverage["erp_facts"]
        self.assertEqual(orders["total"], orders["matched"] + orders["missing_erp_cost"] + orders["quantity_mismatch"])
        self.assertEqual(facts["total"], facts["matched"] + facts["missing_order"]
                         + facts["missing_order_item"] + facts["quantity_mismatch"])
        self.assertEqual((orders["total"], orders["matched"], orders["missing_erp_cost"], orders["quantity_mismatch"]),
                         (3, 1, 1, 1))
        self.assertEqual((facts["total"], facts["matched"], facts["missing_order"], facts["missing_order_item"], facts["quantity_mismatch"]),
                         (3, 1, 1, 0, 1))
        issues = list_erp_cost_issues(1)
        self.assertEqual(issues["total"], 3)
        self.assertEqual({item["issue_type"] for item in issues["items"]},
                         {"missing_erp_cost", "missing_order", "quantity_mismatch"})

    def test_issue_search_pagination_and_missing_values_are_null(self):
        with db.transaction() as connection:
            add_order(connection, 1, "MISSING-1", "FBP")
            add_item(connection, 1, "MISSING-1", "FBP", "SKU-1", 1)

        result = list_erp_cost_issues(1, issue_type="missing_erp_cost", q="MISSING", page=1, size=1)
        self.assertEqual((result["total"], result["page"], result["size"], len(result["items"])), (1, 1, 1, 1))
        self.assertIsNone(result["items"][0]["unit_cost"])
        self.assertIsNone(result["items"][0]["source_batch_id"])

    def test_latest_erp_correction_is_visible_without_refresh(self):
        with db.transaction() as connection:
            add_order(connection, 1, "M-001", "FBP")
            add_item(connection, 1, "M-001", "FBP", "1936515175", 2, offer_id="offer-1")
        import_erp_costs(1, "first.xlsx", workbook_bytes([row(cost="1520.6012")]))
        with db.connect() as connection:
            first = resolve_erp_cost_for_order_item(connection, 1, "M-001", "1936515175", 2)
        import_erp_costs(1, "correction.xlsx", workbook_bytes([row(cost="1500.125")]))
        with db.connect() as connection:
            corrected = resolve_erp_cost_for_order_item(connection, 1, "M-001", "1936515175", 2)
        self.assertEqual(first["erp_cost"]["unit_cost"], "1520.6012")
        self.assertEqual(corrected["erp_cost"]["unit_cost"], "1500.125")
        self.assertEqual(corrected["erp_cost"]["total_cost"], "3000.250")


if __name__ == "__main__":
    unittest.main()
