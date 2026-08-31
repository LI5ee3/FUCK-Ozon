import asyncio
import csv
import importlib
import inspect
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app import db, security
from app.alerts import evaluate_alerts
from app.alerts.evaluation import _event, _sales_drop
from app.dingtalk import daily_values
from app.importer import import_csv
from app.inventory import get_stock
from app.ozon.client import BEIJING
from app.ozon import webhooks
from app.routers import auth, dashboard, imports, products, sync
from tests.support import DatabaseTestCase, add_item, add_order, add_stock_snapshot


class BodyRequest:
    def __init__(self, chunks, headers=None):
        self.chunks = chunks
        self.headers = headers or {}
        self.consumed = 0

    async def body(self):
        return b"".join(self.chunks)

    async def json(self):
        return json.loads(await self.body())

    async def stream(self):
        for chunk in self.chunks:
            self.consumed += 1
            yield chunk


def utc(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


class RobustnessTest(DatabaseTestCase):
    def test_json_object_endpoints_share_request_validation(self):
        modules = ('sync', 'alerts', 'dingtalk', 'shops', 'exchange', 'products',
                   'product_costs', 'ozon_notifications', 'complaints', 'performance')
        tested = set()
        for name in modules:
            module = importlib.import_module('app.routers.' + name)
            for route in module.router.routes:
                endpoint = route.endpoint
                if endpoint in tested or 'request' not in inspect.signature(endpoint).parameters:
                    continue
                if not route.methods.intersection({'POST', 'PUT'}):
                    continue
                tested.add(endpoint)
                limit = getattr(module, 'JSON_MAX_BODY_BYTES', 64 * 1024)
                for raw, status in [(b'{', 400), (b'', 400), (b'[]', 400), (b'null', 400),
                                    (b'"text"', 400), (b'1', 400), (b'x' * (limit + 1), 413)]:
                    with self.subTest(endpoint=endpoint.__name__, raw=raw[:10], status=status):
                        request = BodyRequest([raw, b'ignored'] if status == 413 else [raw])
                        values = {'request': request, 'shop_id': 1, 'module': 'orders', 'rule_key': 'sales_drop'}
                        kwargs = {key: values[key] for key in inspect.signature(endpoint).parameters if key in values}
                        with self.assertRaises(HTTPException) as raised:
                            asyncio.run(endpoint(**kwargs))
                        self.assertEqual(raised.exception.status_code, status)
                        if status == 413:
                            self.assertEqual(request.consumed, 1)
        self.assertEqual(len(tested), 19)

    def test_invalid_product_id_and_sync_date_are_400(self):
        for kind in ('merge', 'dissolve'):
            for value in ('abc', [], {}, True, 1.5):
                with self.subTest(kind=kind, value=value), self.assertRaises(HTTPException) as raised:
                    asyncio.run(products.save_product_rule(BodyRequest([json.dumps({'kind': kind, 'id': value}).encode()])))
                self.assertEqual(raised.exception.status_code, 400)
        for field in ('from', 'to'):
            for value in (123, [], {}, False, 'bad-date'):
                with self.subTest(field=field, value=value), self.assertRaises(HTTPException) as raised:
                    asyncio.run(sync.sync('orders', BodyRequest([json.dumps({field: value}).encode()]), 1))
                self.assertEqual(raised.exception.status_code, 400)

    def test_router_integer_overflow_is_a_client_error(self):
        cases = [
            ('alerts', 'alerts_evaluate', b'{"shop_id":1e309}'),
            ('ozon_notifications', 'ozon_notification_list', b'{"shop_id":1e309}'),
            ('ozon_notifications', 'ozon_notification_enable', b'{"shop_id":1,"id":1e309,"enabled":true}'),
            ('ozon_notifications', 'ozon_notification_delete', b'{"shop_id":1,"id":1e309}'),
            ('dingtalk', 'update_dingtalk_settings',
             b'{"daily_enabled":true,"push_time":"12:00","weekdays":[1e309]}'),
        ]
        for module, function, raw in cases:
            with self.subTest(function=function):
                endpoint = getattr(importlib.import_module('app.routers.' + module), function)
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(endpoint(BodyRequest([raw])))
                self.assertEqual(raised.exception.status_code, 400)

    def test_snapshot_stock_channel_aliases(self):
        with db.transaction() as connection:
            for kind in ('fbs', 'rfbs', 'fbp', 'fbo'):
                add_stock_snapshot(connection, 1, kind, '2026-08-31T00:00:00Z',
                                   {'stocks': [{'sku': kind, 'type': kind, 'present': 17, 'reserved': 3}]})
        rows = {row['sku']: row for row in get_stock(1)['items']}
        for kind, prefix in [('fbs', 'realFBS'), ('rfbs', 'realFBS'), ('fbp', 'FBP'), ('fbo', 'WHD')]:
            with self.subTest(kind=kind):
                channel = next(value for value in rows[kind]['channels'] if value['channel'] == prefix)
                self.assertEqual(channel['present'], 17)
                self.assertEqual(channel['reserved'], 3)

    def test_sales_drop_beijing_day_boundaries(self):
        now = datetime(2026, 8, 31, 12, tzinfo=BEIJING)
        start = now.date() - timedelta(days=2)
        with db.transaction() as connection:
            for offset, quantity in [(-1, 1000), (0, 10), (1, 2), (2, 1000)]:
                for index, (hour, minute) in enumerate([(0, 0), (0, 1), (7, 59), (8, 0), (23, 59)]):
                    moment = datetime.combine(start + timedelta(days=offset), datetime.min.time(), BEIJING).replace(hour=hour, minute=minute)
                    posting = f'{offset}-{index}'
                    add_order(connection, 1, posting, 'FBP', utc(moment))
                    add_item(connection, 1, posting, 'FBP', 'SKU', quantity)
        config = {'baseline_days': 1, 'minimum_baseline_days': 1, 'minimum_baseline_units_per_day': 40, 'drop_percent': 50}
        with db.connect() as connection, patch('app.alerts.evaluation._fresh_orders', return_value=(True, '')):
            events, reason, _ = _sales_drop(connection, 1, config, now)
        self.assertEqual(reason, '')
        self.assertEqual(len(events), 1)  # Old UTC-text comparison drops 30 baseline units and misses this alert.
        metrics = events[0]['metrics']
        self.assertEqual(metrics['baseline_units_per_day'], 50)
        self.assertEqual(metrics['current_units'], 10)
        self.assertEqual(metrics['drop_percent'], 80)

    def test_detector_failure_is_logged_and_does_not_resolve(self):
        event = _event('sales_drop', 1, 'shop', 'shop:1', {}, 'existing alert')
        with patch('app.alerts.evaluation.DETECTORS', {'sales_drop': lambda *args: ([event], '', {'shop:1'})}), \
                patch('app.alerts.evaluation.dingtalk_configured', return_value=False):
            evaluate_alerts(1, ('sales_drop',))
        with patch('app.alerts.evaluation.DETECTORS', {'sales_drop': lambda *args: (_ for _ in ()).throw(RuntimeError('broken'))}), \
                patch('app.alerts.evaluation._record_rule_state') as record, \
                self.assertLogs('app.alerts.evaluation', level='ERROR') as logs:
            result = evaluate_alerts(1, ('sales_drop',))
        self.assertEqual(result['resolved'], 0)
        self.assertEqual(result['skipped'][0]['reason'], '规则检查失败')
        record.assert_not_called()
        with db.connect() as connection:
            self.assertIsNone(connection.execute("SELECT resolved_at FROM alert_events").fetchone()[0])
        self.assertIn('shop_id=1', logs.output[0])
        self.assertIn('rule_key=sales_drop', logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)

    def test_sync_alert_failure_logs_context(self):
        from app.sync_jobs import _evaluate_alerts_after_sync
        with patch('app.sync_jobs.evaluate_alerts', side_effect=RuntimeError('broken')), \
                self.assertLogs('app.sync_jobs', level='ERROR') as logs:
            _evaluate_alerts_after_sync(1, 'orders')
        self.assertIn('shop_id=1', logs.output[0])
        self.assertIn('module=orders', logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)

    def test_rate_limit_prunes_expired_keys_without_creating_empty_ones(self):
        with patch.dict(security._failures, {}, clear=True):
            for index in range(1000):
                security.record_login_failure(str(index), 100)
            self.assertFalse(security.login_limited('new', 401))
            self.assertEqual(len(security._failures), 0)
            for index in range(5):
                self.assertFalse(security.login_limited('active', 500))
                security.record_login_failure('active', 500)
            self.assertTrue(security.login_limited('active', 800))
            self.assertFalse(security.login_limited('active', 801))
            self.assertNotIn('active', security._failures)

    def test_malformed_session_is_unauthenticated(self):
        with patch.object(auth, '_secret', return_value=b'secret'), patch.object(auth, '_generation', return_value=0):
            for value in ('', 'broken', '9999999999.csrf.0.中文', '9999999999.csrf.0.é', 'nan.csrf.0.signature'):
                with self.subTest(value=value):
                    self.assertFalse(auth.session(SimpleNamespace(cookies={'session': value}))['authenticated'])

    def test_csv_stream_limit_parser_error_and_normal_import(self):
        header = {'x-filename': 'orders.csv'}
        request = BodyRequest([b'x' * (1024 * 1024)] * 51 + [b'tail'], header)
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(imports.upload('FBP', request, 1))
        self.assertEqual(raised.exception.status_code, 413)
        self.assertEqual(request.consumed, 51)
        # csv's field-size limit raises csv.Error, even with the normal permissive dialect.
        malformed = b'"' + b'x' * (csv.field_size_limit() + 1)
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(imports.upload('FBP', BodyRequest([malformed], header), 1))
        self.assertEqual(raised.exception.status_code, 400)
        content = '订单号;发货号码;状态;SKU;数量\nM;P;已签收;SKU;2\n'.encode()
        self.assertEqual(asyncio.run(imports.upload('FBP', BodyRequest([content], header), 1))['rows'], 1)

    def test_summary_date_span_limit(self):
        start = datetime(2016, 1, 1).date()
        for granularity in ('day', 'week', 'month'):
            result = dashboard.summary(date_from=start.isoformat(), date_to=(start + timedelta(days=3659)).isoformat(), granularity=granularity)
            self.assertIsInstance(result, dict)
            with self.assertRaises(HTTPException) as raised:
                dashboard.summary(date_from=start.isoformat(), date_to=(start + timedelta(days=3660)).isoformat(), granularity=granularity)
            self.assertEqual(raised.exception.status_code, 400)
        with self.assertRaises(HTTPException) as raised:
            dashboard.summary(date_from='0001-01-01', date_to='2026-08-31', granularity='day')
        self.assertEqual(raised.exception.status_code, 400)

    def test_ad_orders_use_same_beijing_thirty_days_as_sales(self):
        for now in (datetime(2026, 3, 1, 0, 1, tzinfo=BEIJING), datetime(2026, 8, 31, 23, 59, tzinfo=BEIJING)):
            with self.subTest(now=now), db.transaction() as connection:
                connection.execute('DELETE FROM ad_sku_daily')
                connection.execute('DELETE FROM order_items')
                connection.execute('DELETE FROM orders')
                for offset, quantity in [(-31, 100), (-30, 2), (-1, 3), (0, 100)]:
                    day = now.date() + timedelta(days=offset)
                    connection.execute('INSERT INTO ad_sku_daily(shop_id,stat_date,campaign_id,sku,orders) VALUES(1,?,\'C\',\'SKU\',?)', (day.isoformat(), quantity))
                    add_order(connection, 1, str(offset), 'FBP', utc(datetime.combine(day, datetime.min.time(), BEIJING)))
                    add_item(connection, 1, str(offset), 'FBP', 'SKU', quantity)
            with patch('app.inventory.datetime') as clock:
                clock.now.return_value = now
                clock.combine = datetime.combine
                clock.min = datetime.min
                row = get_stock(1)['items'][0]
            self.assertEqual(row['sales_30'], 5)
            self.assertEqual(row['ad_orders_30'], 5)
            self.assertEqual(row['ad_order_share'], 1)

    def test_csv_cancellation_fallback_preserves_api_dates(self):
        content = ('订单号;发货号码;状态;SKU;数量;已创建;已转移配送\n'
                   'M;CSV;已取消;SKU;1;2026-08-29T16:01:00Z;2026-08-30T01:00:00Z\n').encode()
        import_csv(1, 'FBP', 'orders.csv', content)
        with db.transaction() as connection:
            add_order(connection, 1, 'API', 'FBP', '2026-08-29T16:01:00Z', '已取消', 1,
                      status_changed_at='2026-08-30T16:00:00Z')
            add_order(connection, 1, 'API-UNKNOWN', 'FBP', '2026-08-29T16:01:00Z', '已取消', 1)
            self.assertIsNone(connection.execute("SELECT status_changed_at FROM orders WHERE posting_number='CSV'").fetchone()[0])
        self.assertEqual(daily_values('2026-08-29')['取消总数'], 0)
        self.assertEqual(daily_values('2026-08-30')['取消总数'], 1)
        self.assertEqual(daily_values('2026-08-31')['取消总数'], 1)

    def test_webhook_retry_window_keeps_terminal_error_and_frees_worker(self):
        payload = {'message_type': 'TYPE_NEW_POSTING', 'posting_number': 'POISON', 'uuid': 'poison'}
        webhooks.persist_webhook_event(1, payload)
        with patch('app.ozon.client._post', side_effect=RuntimeError('poison failure')) as post:
            webhooks.process_pending_webhook_postings()
            webhooks.process_pending_webhook_postings()
            self.assertEqual(post.call_count, 2)
            with db.transaction() as connection:
                connection.execute('UPDATE ozon_webhook_events SET received_at=?',
                                   (utc(datetime.now(timezone.utc) - timedelta(hours=25)),))
            with self.assertLogs('app.ozon.webhooks', level='ERROR'):
                webhooks.process_pending_webhook_postings()
            # Duplicate delivery and a fresh worker pass cannot restart an exhausted event.
            webhooks.persist_webhook_event(1, payload)
            self.assertEqual(webhooks.process_pending_webhook_postings(), 0)
            self.assertEqual(post.call_count, 2)
        with db.connect() as connection:
            row = connection.execute('SELECT applied_at,error FROM ozon_webhook_events').fetchone()
        self.assertIsNone(row['applied_at'])
        self.assertIn('poison failure', row['error'])
        self.assertIn('24', row['error'])
