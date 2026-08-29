import json
import unittest

from app import db
from app.routers.returns import returns, rfbs_returns
from tests.support import DatabaseTestCase


class ReturnsTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
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
            connection.execute("""INSERT INTO orders(
              shop_id,posting_number,channel,created_at,status_raw,shipped,source)
              VALUES(1,'POST-42','FBP','2026-08-01T00:00:00Z','已签收',1,'api')""")

    def test_cancel_filters_beijing_range_and_only_authorized_search_fields(self):
        data = returns(1, date_from="2026-08-01", date_to="2026-08-02", q="OFFER-4")
        self.assertEqual((data["total"], data["summary"]["records"]), (1, 1))
        self.assertEqual(data["items"][0]["offer_id"], "OFFER-42")
        self.assertEqual(returns(1, q="Hidden Name")["total"], 0)

    def test_rfbs_search_excludes_mother_order_number_and_response(self):
        for query in ("SKU-4", "OFFER-4", "POST-4", "RET-R4"):
            with self.subTest(query=query):
                self.assertEqual(rfbs_returns(1, q=query)["total"], 1)
        self.assertEqual(rfbs_returns(1, q="MOTHER-42")["total"], 0)
        self.assertNotIn("order_number", rfbs_returns(1)["items"][0])

    def test_rfbs_reason_translation_fallback_and_buyer_text_stays_original(self):
        with db.transaction() as connection:
            connection.execute("""UPDATE rfbs_return_records
              SET reason_raw='Товар не подошёл',reason_name='Товар не подошёл' WHERE return_id=42""")
        item = rfbs_returns(1)["items"][0]
        self.assertEqual(item["reason_name"], "商品不合适")
        self.assertEqual(item["buyer_comment_raw"], "Текст покупателя")
        with db.transaction() as connection:
            connection.execute("""UPDATE rfbs_return_records
              SET reason_raw='Неизвестная причина',reason_name='Неизвестная причина' WHERE return_id=42""")
        self.assertEqual(rfbs_returns(1)["items"][0]["reason_name"], "Неизвестная причина")


if __name__ == "__main__":
    unittest.main()
