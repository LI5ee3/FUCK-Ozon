import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SyncPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "static" / "index.html").read_text()
        cls.script = (ROOT / "static" / "app.js").read_text()
        cls.style = (ROOT / "static" / "style.css").read_text()

    def test_three_sections_and_independent_manual_actions(self):
        for title in ("手动拉取", "自动拉取设置", "拉取记录"):
            self.assertIn(title, self.html)
        self.assertNotIn('data-module="all"', self.html + self.script)
        self.assertIn('data-module="${key}"', self.script)
        self.assertIn('api(`/api/sync/${module}?shop_id=${state.shop}`', self.script)
        self.assertIn('button.textContent="拉取中…"', self.script)
        self.assertIn('if(page==="sync") return Promise.all([loadSync(),loadAutoSync()])', self.script)

    def test_auto_settings_time_and_stock_contract(self):
        self.assertIn("[1,2].map(shop=>", self.script)
        self.assertIn("Object.keys(syncNames).map(module=>", self.script)
        self.assertIn('type="time" step="60"', self.script)
        self.assertIn("每天拉取时间", self.script)
        self.assertIn('class="settings-switch"', self.script)
        self.assertIn('class="snapshot-tag">实时库存', self.script)
        self.assertNotIn('<span>启用</span>', self.script)
        self.assertIn('type="submit">保存</button>', self.html)
        self.assertIn('range_days:module==="stock"?1:', self.script)
        self.assertIn('row.querySelectorAll("[data-auto-setting]").forEach(input=>input.disabled=!enabled)', self.script)

    def test_records_and_responsive_accessibility(self):
        for text in ("自动", "手动", "进行中", "成功", "失败", "r.error||'—'"):
            self.assertIn(text, self.script)
        for attribute in ('role="progressbar"', 'aria-valuemin="0"', 'aria-valuemax="100"', 'aria-valuenow="${percent}"'):
            self.assertIn(attribute, self.script)
        self.assertIn("data-label=\"店铺\"", self.script)
        self.assertIn("最近 10 条任务及实时进度", self.html)
        self.assertIn("ORDER BY r.id DESC LIMIT 10", (ROOT / "app" / "main.py").read_text())
        self.assertIn("@media(max-width:1100px)", self.style)
        self.assertIn("@media(max-width:700px)", self.style)
        self.assertIn(".sync-record-table td:before", self.style)
        self.assertIn("var(--panel)", self.style)
        self.assertIn("[data-theme=dark] .auto-time-wrap", self.style)


if __name__ == "__main__":
    unittest.main()
