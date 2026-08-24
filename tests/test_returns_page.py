import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app import db
from app.main import complaints, returns, rfbs_returns


class ReturnsPageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()
        with db.transaction() as connection:
            payload = json.dumps({"product": {"offer_id": "OFFER-42", "name": "Hidden Name", "quantity": 2},
                                  "return_reason_name": "Покупатель отменил заказ"})
            connection.execute("INSERT INTO return_records VALUES(1,'R1','2026-07-31T16:00:00Z','POST-42','SKU-42',?,?)",
                               (payload, "2026-08-01T00:00:00Z"))
            connection.execute("INSERT INTO return_records VALUES(1,'R2','2026-08-02T16:00:00Z','OUTSIDE','OUT',?,?)",
                               (payload, "2026-08-03T00:00:00Z"))
            connection.execute("""INSERT INTO rfbs_return_records(
              shop_id,return_id,return_number,created_at,posting_number,offer_id,sku,product_name,
              status_raw,payload,fetched_at,order_number,quantity,reason_raw,buyer_comment_raw)
              VALUES(1,42,'RET-R42','2026-08-01T01:00:00Z','POST-42','OFFER-42','SKU-42',
              'Hidden Name','OnSellerApproval','{}','2026-08-01T01:00:00Z','MOTHER-42',2,
              'Покупатель отменил заказ','Текст покупателя')""")
            connection.executemany("""INSERT INTO orders(
              shop_id,posting_number,channel,created_at,status_raw,shipped,source)
              VALUES(1,?,'FBP',?,'已签收',1,'api')""", [
                ("POST-42", "2026-08-01T00:00:00Z"),
                ("POST-99", "2026-08-02T00:00:00Z"),
            ])
            connection.executemany("""INSERT INTO complaints(
              shop_id,complaint_number,posting_number,complaint_at,channel,resolved,package_returned,
              compensation_amount,compensation_currency,notes,created_at,updated_at)
              VALUES(1,?,?,?,?,?,?,?,?,?,?,?)""", [
                ("C-OPEN", "POST-42", "2026-08-01T02:00:00Z", "平台", 0, None, None, None, "", "2026-08-01T02:00:00Z", "2026-08-01T02:00:00Z"),
                ("C-UNSET", "POST-99", "2026-08-02T02:00:00Z", "邮件", None, None, None, None, "", "2026-08-02T02:00:00Z", "2026-08-02T02:00:00Z"),
            ])

    def tearDown(self):
        self.temp.cleanup()

    def test_cancel_filters_beijing_range_and_only_authorized_search_fields(self):
        data = returns(1, date_from="2026-08-01", date_to="2026-08-02", q="OFFER-4")
        self.assertEqual((data["total"], data["summary"]["records"]), (1, 1))
        self.assertEqual(data["items"][0]["offer_id"], "OFFER-42")
        self.assertEqual(returns(1, q="Hidden Name")["total"], 0)

    def test_rfbs_search_excludes_mother_order_number_and_response(self):
        for query in ("SKU-4", "OFFER-4", "POST-4", "RET-R4"):
            self.assertEqual(rfbs_returns(1, q=query)["total"], 1)
        self.assertEqual(rfbs_returns(1, q="MOTHER-42")["total"], 0)
        self.assertNotIn("order_number", rfbs_returns(1)["items"][0])

    def test_complaint_filters_combine_and_validate(self):
        data = complaints(1, q="C-UN", status="unset", date_from="2026-08-01", date_to="2026-08-02")
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["complaint_number"], "C-UNSET")
        self.assertEqual(complaints(1, q="邮件")["total"], 0)
        with self.assertRaises(HTTPException):
            complaints(3)
        with self.assertRaises(HTTPException):
            complaints(1, status="other")


if __name__ == "__main__":
    unittest.main()
