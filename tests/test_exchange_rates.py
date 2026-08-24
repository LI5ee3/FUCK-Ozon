import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app import db
from app.exchange import split_period, sync_exchange_rates, utc_period
from app.main import _gmv_summary, order_trend, summary


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        return self.payload


class ExchangeRateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DATA_DIR = Path(self.temp.name)
        db.DB_PATH = db.DATA_DIR / "test.db"
        db.init_db()
        self.requests = []

    def tearDown(self):
        self.temp.cleanup()

    def opener(self, request, timeout=0):
        query = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(query["fromCurrencyIds"], ["USD", "CNY"])
        self.assertEqual((query["toCurrencyId"], query["marketplaceId"]), (["RUB"], ["1"]))
        start = datetime.fromisoformat(query["fromDate"][0].replace("Z", "+00:00"))
        end = datetime.fromisoformat(query["toDate"][0].replace("Z", "+00:00"))
        self.requests.append((start, end, timeout, dict(request.header_items())))
        items = []
        cursor = start
        while cursor < end:
            next_cursor = cursor + timedelta(days=1)
            for currency, rate in (("USD", 90.123456789), ("CNY", 12.345678901)):
                items.append({"fromCurrencyId": currency, "toCurrencyId": "RUB",
                              "fromDate": cursor.isoformat().replace("+00:00", "Z"),
                              "toDate": next_cursor.isoformat().replace("+00:00", "Z"),
                              "exchangeRate": {"rate": rate, "rateWithAdjustment": 9999.0}})
            cursor = next_cursor
        return _Response({"items": items})

    def test_moscow_boundaries_chunking_precision_and_idempotency(self):
        start, end = utc_period(date(2026, 1, 1), date(2026, 3, 10))
        self.assertEqual(start.isoformat(), "2025-12-31T21:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-03-10T21:00:00+00:00")
        chunks = list(split_period(start, end))
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0][1], chunks[1][0])
        self.assertTrue(all((right - left).days <= 60 for left, right in chunks))

        result = sync_exchange_rates(date(2026, 1, 1), date(2026, 3, 10), self.opener)
        self.assertEqual(result["segments"], 2)
        self.assertEqual(self.requests[0][1], self.requests[1][0])
        with db.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0]
            row = connection.execute("SELECT * FROM exchange_rates WHERE from_currency='USD' LIMIT 1").fetchone()
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)
        self.assertEqual(count, 69 * 2)
        self.assertEqual(row["base_rate"], "90.123456789")
        self.assertEqual(row["rate_with_adjustment"], "9999.0")
        self.assertFalse(any(key.lower() in ("client-id", "api-key", "cookie")
                             for key in self.requests[0][3]))
        sync_exchange_rates(date(2026, 1, 1), date(2026, 3, 10), self.opener)
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0], count)
        with self.assertRaises(OSError):
            sync_exchange_rates(date(2026, 1, 1), date(2026, 1, 2),
                                lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM exchange_rates").fetchone()[0], count)

    def test_combined_gmv_uses_base_rate_and_recovers_when_pair_is_completed(self):
        with db.transaction() as connection:
            connection.execute("""INSERT INTO exchange_rates VALUES(
              'USD','RUB','2026-08-21T21:00:00Z','2026-08-22T21:00:00Z','90','9000',
              'ozon_xapi','2026-08-22T22:00:00Z')""")
            connection.executemany("""INSERT INTO orders(
              shop_id,posting_number,channel,created_at,status_raw,shipped,
              amount_original,amount_currency,source) VALUES(?,?,?,?,?,?,?,?,'api')""", [
                (1, "USD-1", "FBP", "2026-08-21T21:00:00Z", "已签收", 1, 100, "USD"),
                (2, "CNY-1", "realFBS", "2026-08-22T00:00:00Z", "已签收", 1, 200, "CNY")])

        combined = summary(0, "2026-08-22", "2026-08-22", "day")
        self.assertEqual(combined["gmv"], {"amount": 200.0, "currency": "CNY", "missing_rate_orders": 1})
        self.assertEqual(summary(1, "2026-08-22", "2026-08-22", "day")["gmv"]["amount"], 100)
        self.assertEqual(summary(2, "2026-08-22", "2026-08-22", "day")["gmv"]["amount"], 200)

        with db.transaction() as connection:
            connection.execute("""INSERT INTO exchange_rates VALUES(
              'CNY','RUB','2026-08-21T21:00:00Z','2026-08-22T21:00:00Z','12','1',
              'ozon_xapi','2026-08-22T22:01:00Z')""")
        combined = summary(0, "2026-08-22", "2026-08-22", "day")
        self.assertEqual(combined["gmv"], {"amount": 950.0, "currency": "CNY", "missing_rate_orders": 0})
        self.assertEqual(combined["buckets"][0]["gmv"], combined["gmv"])
        self.assertEqual(combined["buckets"][0]["channels"]["FBP"]["gmv"]["amount"], 750)
        trend_bucket = next(row for row in order_trend(0, "day")["buckets"] if row["key"] == "2026-08-22")
        self.assertEqual(trend_bucket["gmv"], combined["gmv"])

        boundary = [{"amount_original": 1, "item_amount": None, "amount_currency": "USD",
                     "item_currency": None, "settlement_currency": "USD",
                     "created_at": "2026-08-22T21:00:00Z"}]
        self.assertEqual(_gmv_summary(boundary, 0, [
            (datetime(2026, 8, 21, 21, tzinfo=timezone.utc),
             datetime(2026, 8, 22, 21, tzinfo=timezone.utc), {"USD": 90, "CNY": 12})
        ])["missing_rate_orders"], 1)


if __name__ == "__main__":
    unittest.main()
