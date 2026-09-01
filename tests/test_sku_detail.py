import unittest

from fastapi import HTTPException

from app import db
from app.inventory import get_stock
from app.routers.sku_detail import sku_detail
from app.sku_detail import SkuDetailNotFound, _signals, get_sku_detail
from tests.support import DatabaseTestCase, add_item, add_order, add_stock_snapshot


def timestamp(day):
    return f"{day}T12:00:00Z"


def add_finance(connection, shop_id, operation_id, posting_number, amount, currency="CNY"):
    connection.execute("""INSERT INTO ozon_finance_transactions(
      shop_id,operation_id,operation_type,operation_type_name,transaction_type,operation_date,
      posting_number,amount,accruals_for_sale,sale_commission,delivery_charge,
      return_delivery_charge,currency,payload_json,fetched_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (shop_id, operation_id, "Operation", "操作", "orders", "2026-08-02T00:00:00Z",
       posting_number, amount, 0, 0, 0, 0, currency, "{}", "2026-08-02T00:00:00Z"))


def add_erp(connection, shop_id, posting_number, sku, total_cost):
    batch_id = connection.execute("""INSERT INTO erp_cost_import_batches(
      shop_id,filename,row_count,parsed_count,inserted_count,updated_count,unchanged_count,imported_at)
      VALUES(?, 'test.xlsx',1,1,1,0,0,'2026-08-02T00:00:00Z')""", (shop_id,)).lastrowid
    connection.execute("""INSERT INTO erp_order_item_costs(
      shop_id,erp_order_number,ozon_sku,offer_id,quantity,unit_cost,exchange_rate_original,
      total_cost,platform_link,source_batch_id,source_row_no,raw_payload_json,imported_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (shop_id, posting_number, sku, f"ERP-{sku}", 1, total_cost, "1", total_cost, "",
       batch_id, 1, "{}", "2026-08-02T00:00:00Z", "2026-08-02T00:00:00Z"))


class SkuDetailTest(DatabaseTestCase):
    def test_shop_and_sku_are_isolated_and_cancelled_sales_are_excluded(self):
        with db.transaction() as connection:
            add_order(connection, 1, "P-1", "FBP", timestamp("2026-08-01"), "已签收", 1)
            add_item(connection, 1, "P-1", "FBP", "S-A", 2, offer_id="O-A", unit_price=10, price_currency="USD")
            add_order(connection, 1, "P-CANCEL", "FBP", timestamp("2026-08-02"), "已取消", 0)
            add_item(connection, 1, "P-CANCEL", "FBP", "S-A", 5, offer_id="O-A", unit_price=10, price_currency="USD")
            add_order(connection, 1, "P-WHD", "WHD", timestamp("2026-08-03"), "已签收", 1)
            add_item(connection, 1, "P-WHD", "WHD", "S-A", 3, offer_id="O-A", unit_price=10, price_currency="USD")
            add_order(connection, 1, "P-B", "FBP", timestamp("2026-08-01"), "已签收", 1)
            add_item(connection, 1, "P-B", "FBP", "S-B", 99, offer_id="O-B", unit_price=1, price_currency="USD")
            add_order(connection, 2, "P-2", "FBP", timestamp("2026-08-01"), "已签收", 1)
            add_item(connection, 2, "P-2", "FBP", "S-A", 90, offer_id="O-2", unit_price=1, price_currency="CNY")
            add_stock_snapshot(connection, 1, "S-A", timestamp("2026-08-03"), {"offer_id": "O-A", "stocks": [
                {"sku": "S-A", "type": "fbp", "present": 20, "reserved": 2},
                {"sku": "S-A", "type": "rfbs", "present": 5, "reserved": 1},
                {"sku": "S-A", "type": "fbo", "present": 7, "reserved": 0},
            ]})
            connection.execute("""INSERT INTO ad_sku_daily(
              shop_id,stat_date,campaign_id,sku,impressions,clicks,cart_adds,spend_rub,orders,revenue_rub)
              VALUES(1,'2026-08-02','C-1','S-A',100,10,4,20,2,100)""")
            connection.execute("""INSERT INTO ad_sku_daily(
              shop_id,stat_date,campaign_id,sku,impressions,clicks,cart_adds,spend_rub,orders,revenue_rub)
              VALUES(1,'2026-07-31','C-OLD','S-A',900,90,40,200,20,1000)""")

        result = get_sku_detail(1, "S-A", "2026-08-01", "2026-08-03")
        self.assertEqual((result["identity"]["shop_id"], result["identity"]["sku"]), (1, "S-A"))
        self.assertEqual((result["sales"]["summary"]["orders"], result["sales"]["summary"]["units"]), (2, 5))
        self.assertEqual([row["units"] for row in result["sales"]["channels"]], [2, 0, 3])
        self.assertEqual(result["sales"]["summary"]["revenue"], 50.0)
        self.assertEqual(result["advertising"]["summary"]["orders"], 2)
        self.assertEqual(result["advertising"]["summary"]["impressions"], 100)
        self.assertAlmostEqual(result["advertising"]["ad_order_share"], 0.4)
        self.assertEqual(result["inventory"]["fbp_present"], 20)
        expected_inventory = get_stock(1, page=1, size=100, sku="S-A")["items"][0]
        self.assertEqual(result["inventory"]["forecast_daily"], expected_inventory["forecast_daily"])
        self.assertEqual(result["inventory"]["risk_code"], expected_inventory["risk_code"])
        self.assertEqual(len(result["sales"]["trend"]), 3)

    def test_profit_attributes_only_single_sku_orders(self):
        with db.transaction() as connection:
            add_order(connection, 2, "SINGLE", "FBP", timestamp("2026-08-02"), "已签收", 1)
            add_item(connection, 2, "SINGLE", "FBP", "SKU", 1, offer_id="O-S", unit_price=100, price_currency="CNY")
            add_erp(connection, 2, "SINGLE", "SKU", "60")
            add_finance(connection, 2, "FIN-S", "SINGLE", 100)
            add_order(connection, 2, "MULTI", "FBP", timestamp("2026-08-02"), "已签收", 1)
            add_item(connection, 2, "MULTI", "FBP", "SKU", 1, offer_id="O-S", unit_price=100, price_currency="CNY")
            add_item(connection, 2, "MULTI", "FBP", "OTHER", 1, offer_id="O-O", unit_price=50, price_currency="CNY")
            add_erp(connection, 2, "MULTI", "SKU", "60")
            add_erp(connection, 2, "MULTI", "OTHER", "30")
            add_finance(connection, 2, "FIN-M", "MULTI", 200)

        result = get_sku_detail(2, "SKU", "2026-08-01", "2026-08-03")["profit"]
        self.assertEqual((result["attributed_orders"], result["unattributed_multi_sku_orders"], result["units"]), (1, 1, 1))
        self.assertEqual((result["actual_profit_cny"], result["avg_profit_per_unit_cny"]), ("40.0", "40.0"))
        self.assertEqual(result["incomplete_reasons"], {"multi_sku_order": 1})

    def test_after_sales_uses_order_cohort_and_deduplicates_postings(self):
        with db.transaction() as connection:
            add_order(connection, 1, "RETURNED", "FBP", timestamp("2026-08-02"), "已签收", 1)
            add_item(connection, 1, "RETURNED", "FBP", "SKU-R", 1, offer_id="O-R")
            add_order(connection, 1, "HISTORIC", "FBP", timestamp("2026-07-02"), "已签收", 1)
            add_item(connection, 1, "HISTORIC", "FBP", "SKU-R", 1, offer_id="O-R")
            connection.execute("INSERT INTO return_records VALUES(1,'LEGACY-1',?,?,?,?,?)",
                               (timestamp("2026-08-02"), "RETURNED", "SKU-R", "{}", timestamp("2026-08-02")))
            connection.execute("INSERT INTO return_records VALUES(1,'LEGACY-HISTORIC',?,?,?,?,?)",
                               (timestamp("2026-08-02"), "HISTORIC", "SKU-R", "{}", timestamp("2026-08-02")))
            connection.execute("INSERT INTO return_records VALUES(1,'LEGACY-MISSING',?,?,?,?,?)",
                               (timestamp("2026-08-02"), None, "SKU-R", "{}", timestamp("2026-08-02")))
            connection.executemany("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,posting_number,offer_id,sku,product_name,payload,fetched_at)
              VALUES(?,?,?,?,?,?,?,?,?,?)""", [
                (1, 1, "R-1", timestamp("2026-08-02"), "RETURNED", "O-R", "SKU-R", "商品", "{}", timestamp("2026-08-02")),
                (1, 2, "R-2", timestamp("2026-08-02"), "RETURNED", "O-R", "SKU-R", "商品", "{}", timestamp("2026-08-02")),
                (1, 3, "R-H", timestamp("2026-08-02"), "HISTORIC", "O-R", "SKU-R", "商品", "{}", timestamp("2026-08-02")),
            ])
            connection.execute("""INSERT INTO complaints(
              shop_id,complaint_number,posting_number,complaint_at,channel,created_at,updated_at)
              VALUES(1,'CASE-1','RETURNED',?,?,?,?)""",
              (timestamp("2026-08-02"), "Ozon", timestamp("2026-08-02"), timestamp("2026-08-02")))
            connection.execute("""INSERT INTO ad_sku_daily(
              shop_id,stat_date,campaign_id,sku,orders,revenue_rub) VALUES(1,'2026-08-02','C-1','SKU-R',0,0)""")
        result = get_sku_detail(1, "SKU-R", "2026-08-01", "2026-08-03")
        after_sales = result["after_sales"]
        self.assertEqual((after_sales["orders"], after_sales["returns"], after_sales["return_orders"]), (1, 3, 1))
        self.assertEqual(after_sales["return_rate"], 1)
        self.assertEqual(after_sales["complaints"], 1)
        self.assertEqual(result["after_sales"]["complaint_rate"], 1)
        self.assertLessEqual(after_sales["return_orders"], after_sales["orders"])

    def test_after_sales_cohort_includes_future_returns_but_not_period_returns(self):
        with db.transaction() as connection:
            add_order(connection, 1, "FUTURE-RETURN", "FBP", timestamp("2026-08-02"), "已签收", 1)
            add_item(connection, 1, "FUTURE-RETURN", "FBP", "SKU-FUTURE", 1, offer_id="O-F")
            connection.execute("INSERT INTO return_records VALUES(1,'FUTURE-LEGACY',?,?,?,?,?)",
                               (timestamp("2026-09-05"), "FUTURE-RETURN", "SKU-FUTURE", "{}", timestamp("2026-09-05")))
            connection.executemany("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,posting_number,offer_id,sku,product_name,payload,fetched_at)
              VALUES(?,?,?,?,?,?,?,?,?,?)""", [
                (1, 10, "FUTURE-R1", timestamp("2026-09-05"), "FUTURE-RETURN", "O-F", "SKU-FUTURE", "商品", "{}", timestamp("2026-09-05")),
                (1, 11, "FUTURE-R2", timestamp("2026-09-05"), "FUTURE-RETURN", "O-F", "SKU-FUTURE", "商品", "{}", timestamp("2026-09-05")),
            ])

        after_sales = get_sku_detail(1, "SKU-FUTURE", "2026-08-01", "2026-08-31")["after_sales"]
        self.assertEqual((after_sales["orders"], after_sales["returns"], after_sales["return_orders"]), (1, 0, 1))
        self.assertEqual(after_sales["return_rate"], 1)

        with db.transaction() as connection:
            connection.execute("""INSERT INTO ad_sku_daily(
              shop_id,stat_date,campaign_id,sku,orders,revenue_rub) VALUES(1,'2026-08-02','C-2','AD-ONLY',3,30)""")
        result = get_sku_detail(1, "AD-ONLY", "2026-08-01", "2026-08-03")
        self.assertIsNone(result["advertising"]["ad_order_share"])

    def test_replenishment_signals_distinguish_urgent_and_normal_replenishment(self):
        advertising = {"ad_order_share": None, "summary": {"drr": None}}
        profit = {}
        normal = _signals({"risk_code": "replenish", "days_cover": 40,
                           "lead_time_days": 25, "target_cover_days": 60,
                           "recommended_replenishment": 20, "trend": None}, advertising, profit)[0]
        self.assertEqual(normal["severity"], "warning")
        self.assertNotIn("低于", normal["message"])
        self.assertIn("可覆盖采购交期", normal["message"])
        self.assertIn("目标库存", normal["message"])

        urgent = _signals({"risk_code": "urgent_replenishment", "days_cover": 7.8,
                           "lead_time_days": 25, "target_cover_days": 60,
                           "recommended_replenishment": 139, "trend": None}, advertising, profit)[0]
        self.assertEqual(urgent["severity"], "critical")
        self.assertIn("不高于 25 天采购交期", urgent["message"])
        self.assertIn("到货前缺货风险", urgent["message"])

    def test_unknown_sku_is_not_an_empty_success(self):
        with self.assertRaises(SkuDetailNotFound):
            get_sku_detail(1, "DOES-NOT-EXIST", "2026-08-01", "2026-08-03")

    def test_router_rejects_merged_shop_and_maps_missing_sku_to_404(self):
        with self.assertRaises(HTTPException) as error:
            sku_detail("SKU", 0, "2026-08-01", "2026-08-03")
        self.assertEqual(error.exception.status_code, 400)
        with self.assertRaises(HTTPException) as error:
            sku_detail("DOES-NOT-EXIST", 1, "2026-08-01", "2026-08-03")
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
