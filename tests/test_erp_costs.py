import asyncio
import json
import unittest
from io import BytesIO

from openpyxl import Workbook

from app import db
from app.erp_costs import import_erp_costs
from app.routers.imports import upload_erp_costs
from tests.support import DatabaseTestCase


HEADERS = ["订单编号", "平台SKU", "平台SKU数量", "平台SKU单个成本", "汇率(原币)", "平台链接"]


def workbook_bytes(rows, *, extra_column=False):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "成本导出"
    worksheet.append(["马帮 ERP 成本导出"])
    headers = HEADERS + (["新增字段"] if extra_column else [])
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def row(order="M-001", offer="offer-1", quantity=2, cost="1520.6012", rate="7.2",
        link="https://www.ozon.ru/product/test-1936515175/?sku=999#fragment", extra=None):
    values = [order, offer, quantity, cost, rate, link]
    return values + ([extra] if extra is not None else [])


class ErpCostImportTest(DatabaseTestCase):
    def test_imports_xlsx_maps_offer_and_link_sku_with_decimal_precision_and_raw_payload(self):
        result = import_erp_costs(1, "mabang.xlsx", workbook_bytes([row(extra="保留")], extra_column=True))

        self.assertEqual(result, {
            "batch_id": 1, "rows": 1, "parsed": 1, "inserted": 1, "updated": 0, "unchanged": 0,
        })
        with db.connect() as connection:
            saved = connection.execute("""
              SELECT erp_order_number,ozon_sku,offer_id,quantity,unit_cost,
                exchange_rate_original,total_cost,platform_link,source_row_no,raw_payload_json
              FROM erp_order_item_costs
            """).fetchone()
        self.assertEqual(tuple(saved[:9]), (
            "M-001", "1936515175", "offer-1", 2, "1520.6012", "7.2", "3041.2024",
            "https://www.ozon.ru/product/test-1936515175/?sku=999#fragment", 3,
        ))
        self.assertEqual(json.loads(saved[9])["平台SKU"], "offer-1")
        self.assertEqual(json.loads(saved[9])["新增字段"], "保留")

    def test_same_fact_reimport_is_unchanged_and_does_not_duplicate(self):
        content = workbook_bytes([row()])
        import_erp_costs(1, "first.xlsx", content)
        result = import_erp_costs(1, "second.xlsx", content)

        self.assertEqual((result["inserted"], result["updated"], result["unchanged"]), (0, 0, 1))
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM erp_order_item_costs").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM erp_cost_import_batches").fetchone()[0], 2)
            self.assertEqual(connection.execute(
                "SELECT source_batch_id FROM erp_order_item_costs").fetchone()[0], 2)

    def test_only_ozon_root_domain_and_subdomains_supply_ozon_sku(self):
        allowed = [
            "https://www.ozon.ru/product/test-1936515175/",
            "https://ozon.ru/product/test-1936515175/",
            "https://seller.ozon.ru:443/product/test-1936515175/?sku=999#fragment",
            "https://WWW.OZON.RU:8443/product/test-1936515175/",
        ]
        for index, link in enumerate(allowed):
            with self.subTest(link=link):
                order = f"ALLOWED-{index}"
                import_erp_costs(1, f"allowed-{index}.xlsx", workbook_bytes([
                    row(order=order, link=link)
                ]))
                with db.connect() as connection:
                    saved = connection.execute(
                        "SELECT ozon_sku FROM erp_order_item_costs WHERE erp_order_number=?", (order,)
                    ).fetchone()
                self.assertEqual(saved[0], "1936515175")

        rejected = [
            "https://example.com/product/test-1936515175/",
            "https://ozon.ru.example.com/product/test-1936515175/",
            "https://fakeozon.ru/product/test-1936515175/",
        ]
        for index, link in enumerate(rejected):
            with self.subTest(link=link):
                with db.connect() as connection:
                    before = tuple(connection.execute("""
                      SELECT (SELECT COUNT(*) FROM erp_order_item_costs),
                             (SELECT COUNT(*) FROM erp_cost_import_batches)
                    """).fetchone())
                with self.assertRaisesRegex(ValueError, "平台链接无法解析 Ozon SKU"):
                    import_erp_costs(1, f"rejected-{index}.xlsx", workbook_bytes([
                        row(order=f"REJECTED-{index}", link=link)
                    ]))
                with db.connect() as connection:
                    after = tuple(connection.execute("""
                      SELECT (SELECT COUNT(*) FROM erp_order_item_costs),
                             (SELECT COUNT(*) FROM erp_cost_import_batches)
                    """).fetchone())
                self.assertEqual(after, before)

    def test_later_erp_correction_updates_current_fact(self):
        import_erp_costs(1, "first.xlsx", workbook_bytes([row()]))
        result = import_erp_costs(1, "correction.xlsx", workbook_bytes([row(cost="1500.125")]))

        self.assertEqual((result["inserted"], result["updated"], result["unchanged"]), (0, 1, 0))
        with db.connect() as connection:
            saved = connection.execute(
                "SELECT unit_cost,total_cost FROM erp_order_item_costs").fetchone()
        self.assertEqual(tuple(saved), ("1500.125", "3000.250"))

    def test_identical_duplicate_rows_are_imported_once_without_quantity_sum(self):
        result = import_erp_costs(1, "duplicate.xlsx", workbook_bytes([row(), row()]))

        self.assertEqual((result["rows"], result["parsed"], result["inserted"]), (2, 1, 1))
        with db.connect() as connection:
            saved = connection.execute(
                "SELECT COUNT(*),quantity FROM erp_order_item_costs").fetchone()
        self.assertEqual(tuple(saved), (1, 2))

    def test_conflicting_duplicate_rows_fail_with_source_rows_and_rollback(self):
        with self.assertRaisesRegex(ValueError, r"ERP订单 M-001.*1936515175.*第3、4行"):
            import_erp_costs(1, "conflict.xlsx", workbook_bytes([row(), row(cost="1500")]))

        with db.connect() as connection:
            counts = tuple(connection.execute("""
              SELECT (SELECT COUNT(*) FROM erp_order_item_costs),
                     (SELECT COUNT(*) FROM erp_cost_import_batches)
            """).fetchone())
        self.assertEqual(counts, (0, 0))

    def test_invalid_row_prevents_partial_import(self):
        with self.assertRaisesRegex(ValueError, r"第4行：平台链接无法解析 Ozon SKU"):
            import_erp_costs(1, "invalid.xlsx", workbook_bytes([
                row(), row(link="https://www.ozon.ru/product/no-sku/")
            ]))

        with db.connect() as connection:
            counts = tuple(connection.execute("""
              SELECT (SELECT COUNT(*) FROM erp_order_item_costs),
                     (SELECT COUNT(*) FROM erp_cost_import_batches)
            """).fetchone())
        self.assertEqual(counts, (0, 0))

    def test_router_accepts_raw_xlsx_upload_and_keeps_csv_path_separate(self):
        class Request:
            headers = {"x-filename": "mabang.xlsx"}

            async def stream(self):
                yield workbook_bytes([row()])

        result = asyncio.run(upload_erp_costs(Request(), 1))
        self.assertEqual((result["rows"], result["inserted"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
