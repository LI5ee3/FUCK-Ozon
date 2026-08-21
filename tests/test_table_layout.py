import unittest
from pathlib import Path


ROOT = Path(__file__).parent.parent


class TableLayoutTest(unittest.TestCase):
    def test_all_tables_use_left_aligned_fixed_semantic_columns(self):
        styles = (ROOT / "static/style.css").read_text()
        self.assertIn("table-layout:fixed", styles)
        self.assertIn("text-align:left!important", styles)
        self.assertNotIn(".num,.risk-col{text-align:right", styles)
        for selector in ("#overview", "#risk", "#transfer", "#sync", "#timeliness", "#finance",
                         "#returns-cancel", "#returns-rfbs", "#stock", "#rules"):
            self.assertIn(f"{selector} table{{min-width:", styles)
            self.assertIn(f"{selector} th:nth-child", styles)


if __name__ == "__main__":
    unittest.main()
