import asyncio
import tempfile
import unittest
from io import BytesIO
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app import db
from app.dingtalk import daily_message, run_scheduled_once, send_sync_failure, send_test, send_text
from app.main import test_dingtalk as test_dingtalk_endpoint


class DingtalkTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()
        with db.transaction() as connection:
            connection.execute("UPDATE shops SET name='一店' WHERE id=1")
            connection.execute("""INSERT INTO orders(shop_id,posting_number,channel,created_at,status_changed_at,status_raw,
              cancel_reason_raw,shipped,source) VALUES(1,'P-1','FBP','2026-08-01T01:00:00Z','2026-08-19T01:00:00Z','已取消',
              'Покупатель не забрал заказ',1,'api')""")
            connection.execute("""INSERT INTO orders(shop_id,posting_number,channel,created_at,status_raw,
              cancel_reason_raw,shipped,source) VALUES(1,'P-2','WHD','2026-08-19T02:00:00Z','已取消',
              '不认识的固定原因',0,'api')""")

    def tearDown(self):
        self.temp.cleanup()

    def test_daily_summary_uses_active_cancellations_and_does_not_repeat(self):
        message = daily_message("2026-08-19")
        self.assertIn("一店：FBP 1｜realFBS 0｜WHD 0", message)
        self.assertIn("P-1：买家未取货", message)
        self.assertNotIn("P-2", message)
        with db.transaction() as connection:
            connection.execute("UPDATE notification_settings SET daily_enabled=1,push_time='09:00' WHERE id=1")
        now = datetime(2026, 8, 20, 9, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("app.dingtalk.configured", return_value=True), patch("app.dingtalk.send_text") as send:
            self.assertTrue(run_scheduled_once(now))
            self.assertFalse(run_scheduled_once(now))
        send.assert_called_once()

    def test_sync_failure_message_hides_secret(self):
        values = {"DINGTALK_WEBHOOK_URL": "https://secret.example/hook", "SHOP_1_OZON_API_KEY": "private-key"}
        moment = datetime(2026, 8, 20, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("app.dingtalk._env", return_value=values), patch("app.dingtalk.send_text") as send:
            send_sync_failure(1, "orders", moment, moment, "request private-key failed")
        content = send.call_args.args[0]
        self.assertIn("同步失败", content)
        self.assertNotIn("private-key", content)

    def test_signed_webhook_adds_timestamp_and_signature(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = BytesIO(b'{"errcode":0}')
        values = {"DINGTALK_WEBHOOK_URL": "https://example.test/hook?access_token=x", "DINGTALK_SECRET": "secret"}
        with patch("app.dingtalk._env", return_value=values), patch("app.dingtalk.urllib.request.urlopen", return_value=response) as open_url:
            send_text("测试")
        query = parse_qs(urlsplit(open_url.call_args.args[0].full_url).query)
        self.assertIn("timestamp", query)
        self.assertIn("sign", query)

    def test_test_message_is_clearly_identified(self):
        with patch("app.dingtalk.send_text") as send:
            send_test()
        content = send.call_args.args[0]
        self.assertIn("FUCK Ozon 测试消息", content)
        self.assertIn("机器人连接正常", content)

    def test_test_endpoint_uses_threadpool(self):
        runner = AsyncMock()
        with patch("app.main.dingtalk_configured", return_value=True), \
             patch("app.main.run_in_threadpool", runner):
            self.assertEqual(asyncio.run(test_dingtalk_endpoint()), {"ok": True})
        runner.assert_awaited_once_with(send_test)


if __name__ == "__main__":
    unittest.main()
