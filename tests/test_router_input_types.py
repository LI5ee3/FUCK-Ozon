import asyncio
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app import db
from app.routers import alerts, dingtalk, ozon_notifications as notifications
from tests.support import DatabaseTestCase, MockRequest


INVALID_IDS = (True, False, [], {}, 1.0, None, "abc")
INVALID_BOOLEANS = ("true", "false", 1, 0, [], {}, None)


class RouterInputTypesTest(DatabaseTestCase):
    def test_alert_shop_helper_and_evaluate_reject_invalid_types(self):
        for value in (*INVALID_IDS, 3):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException) as raised:
                    alerts._alert_shop_id(value)
                self.assertEqual(raised.exception.status_code, 400)
                with patch("app.routers.alerts.evaluate_alerts") as evaluate:
                    with self.assertRaises(HTTPException) as raised:
                        asyncio.run(alerts.alerts_evaluate(MockRequest({"shop_id": value})))
                    self.assertEqual(raised.exception.status_code, 400)
                    evaluate.assert_not_called()
        self.assertEqual(alerts._alert_shop_id(), 0)
        for value in (0, 1, 2, "0", "1", "2"):
            with self.subTest(valid=value):
                self.assertEqual(alerts._alert_shop_id(value), int(value))
                with patch("app.routers.alerts.evaluate_alerts", return_value={"evaluated": 1}) as evaluate:
                    result = asyncio.run(alerts.alerts_evaluate(MockRequest({"shop_id": value})))
                self.assertEqual(result, {"evaluated": 1})
                evaluate.assert_called_once_with(int(value))

    def test_notification_shop_types_are_checked_before_management_call(self):
        endpoints = (
            (notifications.ozon_notification_check, notifications.notification_check,
             {"url": "https://example.test/hook"}, ("https://example.test/hook",)),
            (notifications.ozon_notification_set, notifications.notification_set,
             {"url": "https://example.test/hook", "types": ["TYPE_NEW_POSTING"]},
             ("https://example.test/hook", ["TYPE_NEW_POSTING"])),
            (notifications.ozon_notification_list, notifications.notification_list, {}, ()),
        )
        for value in (*INVALID_IDS, 0, 3):
            with self.subTest(helper=value):
                with self.assertRaises(HTTPException) as raised:
                    notifications._admin_shop({"shop_id": value})
                self.assertEqual(raised.exception.status_code, 400)
            for endpoint, _, payload, _ in endpoints:
                with self.subTest(endpoint=endpoint.__name__, value=value):
                    with patch("app.routers.ozon_notifications._ozon_management_call", new_callable=AsyncMock) as call:
                        with self.assertRaises(HTTPException) as raised:
                            asyncio.run(endpoint(MockRequest({**payload, "shop_id": value})))
                        self.assertEqual(raised.exception.status_code, 400)
                        call.assert_not_called()
        for value in (1, 2, "1", "2"):
            self.assertEqual(notifications._admin_shop({"shop_id": value}), int(value))
            for endpoint, function, payload, args in endpoints:
                with self.subTest(endpoint=endpoint.__name__, valid=value):
                    with patch("app.routers.ozon_notifications._ozon_management_call", new_callable=AsyncMock,
                               return_value={"result": "ok"}) as call:
                        result = asyncio.run(endpoint(MockRequest({**payload, "shop_id": value})))
                    self.assertEqual(result, {"result": "ok"})
                    call.assert_awaited_once_with(function, int(value), *args)

    def test_notification_ids_reject_invalid_types_before_management_call(self):
        for endpoint, function, args in (
            (notifications.ozon_notification_enable, notifications.notification_enable, (True,)),
            (notifications.ozon_notification_delete, notifications.notification_delete, ()),
        ):
            for value in INVALID_IDS:
                with self.subTest(endpoint=endpoint.__name__, value=value):
                    with patch("app.routers.ozon_notifications._ozon_management_call", new_callable=AsyncMock) as call:
                        with self.assertRaises(HTTPException) as raised:
                            asyncio.run(endpoint(MockRequest({"shop_id": 1, "id": value, "enabled": True})))
                        self.assertEqual(raised.exception.status_code, 400)
                        call.assert_not_called()
            for value in (0, 7, "7"):
                with self.subTest(endpoint=endpoint.__name__, valid=value):
                    with patch("app.routers.ozon_notifications._ozon_management_call", new_callable=AsyncMock,
                               return_value={"result": "ok"}) as call:
                        result = asyncio.run(endpoint(MockRequest({"shop_id": 1, "id": value, "enabled": True})))
                    self.assertEqual(result, {"result": "ok"})
                    call.assert_awaited_once_with(function, 1, int(value), *args)

    def test_notification_enabled_aliases_require_booleans(self):
        for key in ("enabled", "enable"):
            for value in INVALID_BOOLEANS:
                with self.subTest(key=key, value=value):
                    with patch("app.routers.ozon_notifications._ozon_management_call", new_callable=AsyncMock) as call:
                        with self.assertRaises(HTTPException) as raised:
                            asyncio.run(notifications.ozon_notification_enable(
                                MockRequest({"shop_id": 1, "id": 7, key: value})))
                        self.assertEqual(raised.exception.status_code, 400)
                        call.assert_not_called()
            for value in (True, False):
                with self.subTest(key=key, valid=value):
                    with patch("app.routers.ozon_notifications._ozon_management_call", new_callable=AsyncMock) as call:
                        asyncio.run(notifications.ozon_notification_enable(
                            MockRequest({"shop_id": 1, "id": 7, key: value})))
                    call.assert_awaited_once_with(notifications.notification_enable, 1, 7, value)
        with patch("app.routers.ozon_notifications._ozon_management_call", new_callable=AsyncMock) as call:
            asyncio.run(notifications.ozon_notification_enable(
                MockRequest({"shop_id": 1, "id": 7, "enabled": False, "enable": True})))
        call.assert_awaited_once_with(notifications.notification_enable, 1, 7, False)

    def test_invalid_dingtalk_settings_never_open_transaction_or_change_database(self):
        with db.connect() as connection:
            before = dict(connection.execute("SELECT * FROM notification_settings WHERE id=1").fetchone())
        for key, values in (
            ("daily_enabled", INVALID_BOOLEANS),
            ("weekdays", ("123", 1, {}, None, [True], [False], ["1"], [1.0], [0], [8], [])),
        ):
            for value in values:
                payload = {"daily_enabled": True, "push_time": "09:00", "weekdays": [1, 2, 7], key: value}
                with self.subTest(key=key, value=value):
                    with patch("app.routers.dingtalk.transaction", wraps=db.transaction) as transaction:
                        with self.assertRaises(HTTPException) as raised:
                            asyncio.run(dingtalk.update_dingtalk_settings(MockRequest(payload)))
                        self.assertEqual(raised.exception.status_code, 400)
                        transaction.assert_not_called()
                    with db.connect() as connection:
                        after = dict(connection.execute("SELECT * FROM notification_settings WHERE id=1").fetchone())
                    self.assertEqual(after, before)

    def test_valid_dingtalk_settings_keep_sort_dedup_and_empty_disabled_behavior(self):
        for enabled, weekdays, stored in (
            (True, [1], "1"), (True, [1, 2, 3], "1,2,3"),
            (True, [1, 2, 7], "1,2,7"), (True, [7, 1, 7], "1,7"), (False, [], ""),
        ):
            with self.subTest(enabled=enabled, weekdays=weekdays):
                result = asyncio.run(dingtalk.update_dingtalk_settings(MockRequest(
                    {"daily_enabled": enabled, "push_time": "09:00", "weekdays": weekdays})))
                self.assertIs(result["daily_enabled"], enabled)
                self.assertEqual(result["weekdays"], sorted(set(weekdays)))
                self.assertEqual(result["push_time"], "09:00")
                with db.connect() as connection:
                    row = connection.execute(
                        "SELECT daily_enabled,push_time,weekdays FROM notification_settings WHERE id=1").fetchone()
                self.assertEqual(tuple(row), (int(enabled), "09:00", stored))
