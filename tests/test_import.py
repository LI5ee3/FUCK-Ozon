import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db
from app.importer import import_costs, import_csv
from app.ozon import _product_price, sync_module, table_fingerprints

ROOT = Path(__file__).resolve().parent.parent


class ImportRegressionTest(unittest.TestCase):
    def test_api_product_price_shapes(self):
        self.assertEqual(_product_price({"price": "12.50"}, "USD"), (12.5, "USD"))
        self.assertEqual(_product_price({"price": {"amount": "88", "currency": "CNY"}}, "USD"), (88.0, "CNY"))

    def test_stock_sync_changes_only_stock_table(self):
        before = table_fingerprints()
        response = {"items": [{"product_id": 1, "offer_id": "A", "stocks": []}], "has_next": False}
        with patch("app.ozon._post", return_value=response):
            sync_module("stock", 1)
        after = table_fingerprints()
        self.assertEqual({table for table in before if before[table] != after[table]}, {"stock_snapshots"})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()

    def tearDown(self):
        self.temp.cleanup()

    def test_real_samples_match_verified_baseline(self):
        for channel in ("FBP", "realFBS", "WHD"):
            path = ROOT / f"{channel}.csv"
            import_csv(1, channel, path.name, path.read_bytes())
        costs = ROOT / "马帮.xlsx"
        import_costs(1, costs.name, costs.read_bytes())

        with db.connect() as connection:
            active = "NOT (o.status_raw='已取消' AND o.shipped=0)"
            totals = connection.execute(f"""
              SELECT COUNT(DISTINCT o.posting_number),SUM(i.quantity)
              FROM orders o JOIN order_items i USING(shop_id,posting_number) WHERE {active}
            """).fetchone()
            by_channel = {row[0]:(row[1],row[2]) for row in connection.execute(f"""
              SELECT o.channel,COUNT(DISTINCT o.posting_number),SUM(i.quantity)
              FROM orders o JOIN order_items i USING(shop_id,posting_number)
              WHERE {active} GROUP BY o.channel
            """)}
            cost_count, cost_total = connection.execute(
                "SELECT COUNT(*),SUM(cost_cny) FROM order_costs").fetchone()
            matched = connection.execute(
                "SELECT COUNT(*) FROM order_costs c JOIN orders o USING(shop_id,posting_number)").fetchone()[0]

        self.assertEqual(tuple(totals), (3623, 3671))
        self.assertEqual(by_channel, {"FBP": (2690, 2724), "realFBS": (810, 824), "WHD": (123, 123)})
        self.assertEqual((cost_count, matched), (500, 500))
        self.assertAlmostEqual(cost_total, 351164.6576, places=4)


if __name__ == "__main__":
    unittest.main()
