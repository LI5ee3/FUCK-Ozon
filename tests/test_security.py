import asyncio
from http.cookies import SimpleCookie
import unittest
from unittest.mock import patch

from fastapi import HTTPException, Response

from app import db, main
from app.main import protect_api
from app.routers import auth
from app.routers.auth import _client_ip, login, logout, session
from app.security import (clear_login_failures, login_limited, password_hash,
                          password_matches, record_login_failure)
from tests.support import DatabaseTestCase


class SecurityTest(DatabaseTestCase):
    def test_password_hash_and_rate_limit(self):
        salt, digest = password_hash("secret")
        self.assertTrue(password_matches("secret", salt, digest))
        self.assertFalse(password_matches("wrong", salt, digest))
        clear_login_failures("test")
        for _ in range(5):
            record_login_failure("test", 100)
        self.assertTrue(login_limited("test", 101))

    def test_csrf_middleware_protection(self):
        auth.DATA_DIR = db.DATA_DIR
        csrf, token = "csrf", auth._token("csrf")

        async def next_response(_):
            return main.Response(status_code=204)

        async def run(header=False):
            headers = [(b"cookie", f"session={token}".encode())]
            if header:
                headers.append((b"x-csrf-token", csrf.encode()))
            request = main.Request({
                "type": "http", "method": "POST", "path": "/api/shops",
                "raw_path": b"/api/shops", "query_string": b"", "headers": headers,
                "scheme": "http", "server": ("test", 80), "client": ("test", 1),
            })
            return await protect_api(request, next_response)

        self.assertEqual(asyncio.run(run()).status_code, 403)
        self.assertEqual(asyncio.run(run(True)).status_code, 204)

    def test_login_authenticates_with_configured_hash(self):
        salt, digest = password_hash("secret")

        class Request:
            url = type("URL", (), {"scheme": "http"})()
            client = type("Client", (), {"host": "127.0.0.1"})()
            headers = {}

            async def json(self):
                return {"password": "secret"}

        with patch("app.routers.auth._env", return_value={"ADMIN_PASSWORD_SALT": salt, "ADMIN_PASSWORD_HASH": digest}), \
             patch("app.routers.auth._token", return_value="token"):
            self.assertEqual(asyncio.run(login(Request(), Response())), {"ok": True})

    def test_login_rate_limit_uses_only_trusted_forwarded_client_ip(self):
        class Request:
            url = type("URL", (), {"scheme": "https"})()

            def __init__(self, headers, host="127.0.0.1"):
                self.headers = headers
                self.client = type("Client", (), {"host": host})()

            async def json(self):
                return {"password": "wrong"}

        requests = [
            (Request({"CF-Connecting-IP": " 198.51.100.7 "}), "198.51.100.7"),
            (Request({"CF-Connecting-IP": "198.51.100.8"}, "192.0.2.8"), "192.0.2.8"),
            (Request({}, "192.0.2.9"), "192.0.2.9"),
            (Request({"CF-Connecting-IP": "not-an-ip"}), "127.0.0.1"),
            (Request({"X-Forwarded-For": "203.0.113.7"}), "203.0.113.7"),
            (Request({"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}), "127.0.0.1"),
        ]
        self.assertEqual([_client_ip(request) for request, _ in requests], [expected for _, expected in requests])
        with patch("app.routers.auth._env", return_value={"ADMIN_PASSWORD_SALT": "00", "ADMIN_PASSWORD_HASH": "hash"}), \
             patch("app.routers.auth.login_limited", return_value=False), \
             patch("app.routers.auth.password_matches", return_value=False), \
             patch("app.routers.auth.record_login_failure") as record:
            for request, _ in requests:
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(login(request, Response()))
                self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual([call.args[0] for call in record.call_args_list], [expected for _, expected in requests])

        first, second = (expected for _, expected in requests[:2])
        clear_login_failures(first)
        clear_login_failures(second)
        for _ in range(5):
            record_login_failure(first, 100)
        self.assertTrue(login_limited(first, 101))
        self.assertFalse(login_limited(second, 101))
        clear_login_failures(first)
        clear_login_failures(second)

    def test_session_secret_cache_follows_data_dir(self):
        auth.DATA_DIR = db.DATA_DIR
        first = auth._secret()
        self.assertIs(first, auth._secret())
        self.assertEqual((db.DATA_DIR / "session_secret").stat().st_mode & 0o777, 0o600)
        auth.DATA_DIR = db.DATA_DIR / "other"
        self.assertNotEqual(auth._secret(), first)
        auth.DATA_DIR = db.DATA_DIR

    def test_logout_clears_authenticated_session_cookie(self):
        auth.DATA_DIR = db.DATA_DIR
        salt, digest = password_hash("secret")

        class LoginRequest:
            url = type("URL", (), {"scheme": "http"})()
            client = type("Client", (), {"host": "127.0.0.1"})()
            headers = {}

            async def json(self):
                return {"password": "secret"}

        login_response = Response()
        with patch("app.routers.auth._env", return_value={"ADMIN_PASSWORD_SALT": salt, "ADMIN_PASSWORD_HASH": digest}):
            self.assertEqual(asyncio.run(login(LoginRequest(), login_response)), {"ok": True})
        cookie = SimpleCookie()
        cookie.load(login_response.headers["set-cookie"])
        token = cookie["session"].value
        csrf = token.split(".", 2)[1]

        def request(path, method="POST", csrf_header=None, session_cookie=token):
            headers = []
            if session_cookie:
                headers.append((b"cookie", f"session={session_cookie}".encode()))
            if csrf_header is not None:
                headers.append((b"x-csrf-token", csrf_header.encode()))
            return main.Request({
                "type": "http", "method": method, "path": path,
                "raw_path": path.encode(), "query_string": b"", "headers": headers,
                "scheme": "http", "server": ("test", 80), "client": ("test", 1),
            })

        self.assertTrue(session(request("/api/session", "GET"))["authenticated"])

        async def next_response(_):
            return Response(status_code=204)

        allowed = asyncio.run(protect_api(request("/api/logout", csrf_header=csrf), next_response))
        self.assertEqual(allowed.status_code, 204)

        logout_response = Response()
        self.assertEqual(logout(logout_response), {"ok": True})
        deleted_cookie = SimpleCookie()
        deleted_cookie.load(logout_response.headers["set-cookie"])
        self.assertEqual(deleted_cookie["session"].value, "")
        self.assertEqual(deleted_cookie["session"]["path"], "/")
        self.assertEqual(session(request("/api/session", "GET", session_cookie="")), {
            "authenticated": False, "csrf_token": "",
        })

    def test_logout_requires_authentication_and_csrf(self):
        auth.DATA_DIR = db.DATA_DIR
        token = auth._token("csrf")

        def request(csrf_header=None, session_cookie=token):
            headers = []
            if session_cookie:
                headers.append((b"cookie", f"session={session_cookie}".encode()))
            if csrf_header is not None:
                headers.append((b"x-csrf-token", csrf_header.encode()))
            return main.Request({
                "type": "http", "method": "POST", "path": "/api/logout",
                "raw_path": b"/api/logout", "query_string": b"", "headers": headers,
                "scheme": "http", "server": ("test", 80), "client": ("test", 1),
            })

        async def next_response(_):
            return Response(status_code=204)

        self.assertEqual(asyncio.run(protect_api(request(session_cookie=""), next_response)).status_code, 401)
        self.assertEqual(asyncio.run(protect_api(request(), next_response)).status_code, 403)
        self.assertEqual(asyncio.run(protect_api(request("csrf"), next_response)).status_code, 204)
