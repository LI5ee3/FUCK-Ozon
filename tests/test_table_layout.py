import unittest
from pathlib import Path


ROOT = Path(__file__).parent.parent


class TableLayoutTest(unittest.TestCase):
    def test_all_tables_use_left_aligned_fixed_semantic_columns(self):
        styles = (ROOT / "static/style.css").read_text()
        self.assertIn("table-layout:fixed", styles)
        self.assertIn("text-align:left!important", styles)
        self.assertNotIn(".num,.risk-col{text-align:right", styles)
        for selector in ("#overview", "#risk", "#transfer", "#sync", "#timeliness",
                         "#returns-cancel", "#returns-rfbs", "#rules"):
            self.assertIn(f"{selector} table{{min-width:", styles)
            self.assertIn(f"{selector} th:nth-child", styles)

    def test_stock_uses_responsive_sku_cards(self):
        html = (ROOT / "static/index.html").read_text()
        script = (ROOT / "static/app.js").read_text()
        styles = (ROOT / "static/style.css").read_text()
        self.assertIn('id="stockRows" class="stock-grid"', html)
        self.assertIn('class="stock-card"', script)
        self.assertIn('.stock-channel-grid{display:grid;grid-template-columns:repeat(3', styles)


if __name__ == "__main__":
    unittest.main()
