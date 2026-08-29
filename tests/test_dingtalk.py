import asyncio
import json
import unittest
from datetime import datetime
from io import BytesIO
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app import db
from app.db import DEFAULT_DAILY_TEMPLATE
from app.dingtalk import (daily_message, render_template, run_scheduled_once,
                          send_sync_failure, send_text, validate_template)
from app.routers.dingtalk import dingtalk_settings, update_dingtalk_settings
from tests.support import DatabaseTestCase, MockRequest as Request


class DingtalkTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        with db.transaction() as connection:
            connection.execute("UPDATE shops SET name='一店' WHERE id=1")
            connection.execute("UPDATE shops SET name='二店' WHERE id=2")
            connection.executemany("""INSERT INTO orders(shop_id,posting_number,channel,created_at,status_changed_at,
              status_raw,cancel_reason_raw,shipped,source) VALUES(?,?,?,?,?,?,?,?,'api')""", [
                (1,"C-1","FBP","2026-08-18T01:00:00Z","2026-08-19T01:00:00Z","已取消","Покупатель не забрал заказ",1),
                (1,"PRE-1","WHD","2026-08-18T02:00:00Z","2026-08-19T02:00:00Z","已取消","不认识的固定原因",0),
                (1,"R-1","WHD","2026-08-18T03:00:00Z",None,"已签收",None,1),
                (2,"RF-1","FBP","2026-08-18T04:00:00Z",None,"已签收",None,1),
            ])
            known = json.dumps({"return_reason_name":"Товар поврежден, но упаковка цела","buyer_comment":"不应出现的买家文本"})
            unknown = json.dumps({"return_reason_name":"未收录退货原因","comment":"另一段买家文本"})
            connection.executemany("INSERT INTO return_records VALUES(1,?,?,?,?,?,?)", [
                ("L-1","2026-08-19T03:00:00Z","R-1","S-1",known,"2026-08-19T04:00:00Z"),
                ("L-2","2026-08-19T04:00:00Z","R-1","S-2",unknown,"2026-08-19T04:00:00Z"),
                ("L-3","2026-08-19T05:00:00Z",None,"S-3",unknown,"2026-08-19T05:00:00Z")])
            connection.executemany("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,posting_number,sku,product_name,status_raw,
              payload,fetched_at,reason_raw,reason_name,buyer_comment_raw) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
                (2,1,"RET-1","2026-08-19T06:00:00Z","RF-1","S-4","商品","Approved","{}","2026-08-19T06:00:00Z","Покупатель передумал",None,"私密买家说明"),
                (2,2,"RET-2","2026-08-19T07:00:00Z","RF-1","S-5","商品","Approved","{}","2026-08-19T07:00:00Z","未知俄语原因",None,None),
                (2,3,"RET-3","2026-08-19T08:00:00Z",None,"S-6","商品","Approved","{}","2026-08-19T08:00:00Z",None,None,None)])
            connection.executemany("INSERT INTO sync_runs(shop_id,module,status,data_through) VALUES(?,?,'success',?)", [
                (1,"orders","2026-08-19T09:00:00Z"),(1,"returns","2026-08-19T10:00:00Z")])

    def test_template_is_backend_only(self):
        custom = DEFAULT_DAILY_TEMPLATE + "\n取消 {{取消总数}}，退货 {{退货总数}}"
        with self.assertRaises(HTTPException):
            asyncio.run(update_dingtalk_settings(Request({"template":custom})))
        settings = dingtalk_settings()
        self.assertNotIn("template", settings); self.assertNotIn("default_template", settings)
        for invalid in ("", "{{未知变量}} {{统计日期}} {{店铺明细}}", "{{统计日期}}"):
            with self.assertRaises(ValueError): validate_template(invalid)
        values = {"统计日期":"D","取消总数":1,"退货总数":2,"店铺明细":"S","数据截止":"T"}
        self.assertNotIn("{{", render_template(custom, values))

    def test_daily_summary_combines_events_deduplicates_and_hides_free_text(self):
        message = daily_message("2026-08-19")
        self.assertTrue(message.startswith("2026-08-19 取消与退货订单汇总"))
        self.assertIn("一店：\n取消：FBP 1｜realFBS 0｜WHD 0\n退货：FBP 0｜realFBS 0｜WHD 1", message)
        self.assertIn("二店：\n取消：FBP 0｜realFBS 0｜WHD 0\n退货：FBP 1｜realFBS 1｜WHD 0", message)
        self.assertEqual(message.count("R-1："),1); self.assertEqual(message.count("RF-1："),1)
        self.assertIn("商品损坏，但包装完好无损 / 未收录退货原因",message)
        self.assertIn("未知俄语原因",message); self.assertNotIn("PRE-1",message)
        self.assertNotIn("不应出现的买家文本",message); self.assertNotIn("私密买家说明",message)
        self.assertNotIn("数据截止：",message)

    def test_daily_schedule_does_not_repeat_and_validates_weekdays(self):
        with db.transaction() as connection: connection.execute("UPDATE notification_settings SET daily_enabled=1,push_time='09:00' WHERE id=1")
        now = datetime(2026,8,20,9,1,tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("app.dingtalk.configured",return_value=True), patch("app.dingtalk.send_text") as send:
            self.assertTrue(run_scheduled_once(now)); self.assertFalse(run_scheduled_once(now))
        send.assert_called_once()
        with self.assertRaises(HTTPException):
            asyncio.run(update_dingtalk_settings(Request({"daily_enabled":True,"push_time":"09:00","weekdays":[]})))

    def test_sync_failure_hides_secret_and_ignores_template(self):
        values={"DINGTALK_WEBHOOK_URL":"https://secret.example/hook","SHOP_1_OZON_API_KEY":"private-key"}
        moment=datetime(2026,8,20,tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("app.dingtalk._env",return_value=values),patch("app.dingtalk.send_text") as send:
            send_sync_failure(1,"orders",moment,moment,"request private-key failed")
        content=send.call_args.args[0]
        self.assertIn("同步失败",content); self.assertNotIn("private-key",content); self.assertNotIn("昨日取消与退货订单汇总",content)

    def test_signed_webhook_adds_timestamp_and_signature(self):
        response=unittest.mock.MagicMock(); response.__enter__.return_value=BytesIO(b'{"errcode":0}')
        values={"DINGTALK_WEBHOOK_URL":"https://example.test/hook?access_token=x","DINGTALK_SECRET":"secret"}
        with patch("app.dingtalk._env",return_value=values),patch("app.dingtalk.urllib.request.urlopen",return_value=response) as open_url: send_text("测试")
        query=parse_qs(urlsplit(open_url.call_args.args[0].full_url).query); self.assertIn("timestamp",query); self.assertIn("sign",query)
