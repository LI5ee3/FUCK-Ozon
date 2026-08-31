import asyncio
from http.cookies import SimpleCookie
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException, Response
from fastapi.responses import FileResponse

import starlette

from app import db, main, security
from app.main import protect_api
from app.routers import auth
from app.routers.auth import LOGIN_MAX_BODY_BYTES, _client_ip, login, logout, session
from app.security import (clear_login_failures, login_limited, password_hash,
                          password_matches, record_login_failure)
from tests.support import DatabaseTestCase


class StreamingBodyRequest:
    """带 stream() 的登录请求桩：read_bounded_json 通过流式读取限制 body 大小。"""

    url = type("URL", (), {"scheme": "http"})()
    client = type("Client", (), {"host": "127.0.0.1"})()

    def __init__(self, chunks, headers=None):
        self.headers = headers or {}
        self._chunks = chunks
        self.consumed = []

    async def stream(self):
        for chunk in self._chunks:
            self.consumed.append(chunk)
            yield chunk


def body_request(raw=b"", headers=None):
    return StreamingBodyRequest([raw], headers)


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

    def test_malicious_host_header_cannot_bypass_auth_and_csrf(self):
        auth.DATA_DIR = db.DATA_DIR
        token = auth._token("csrf")

        async def next_response(_):
            return Response(status_code=204)

        def request(path, method="GET", headers=()):
            return main.Request({
                "type": "http", "method": method, "path": path,
                "raw_path": path.encode(), "query_string": b"", "headers": list(headers),
                "scheme": "http", "server": ("test", 80), "client": ("test", 1),
            })

        normal = [(b"host", b"localhost")]
        malicious = [(b"host", b"example.com/abc?bar=")]
        self.assertEqual(asyncio.run(protect_api(request("/api/shops", headers=normal), next_response)).status_code, 401)
        self.assertEqual(asyncio.run(protect_api(request("/api/shops", headers=malicious), next_response)).status_code, 401)
        self.assertEqual(asyncio.run(protect_api(request("/api/shops", "PUT", malicious), next_response)).status_code, 401)

        with db.connect() as connection:
            before = connection.execute("SELECT id,name FROM shops ORDER BY id").fetchall()
        authenticated = [(b"cookie", f"session={token}".encode())] + malicious
        response = asyncio.run(protect_api(request("/api/shops", "PUT", authenticated), next_response))
        self.assertEqual(response.status_code, 403)
        with db.connect() as connection:
            after = connection.execute("SELECT id,name FROM shops ORDER BY id").fetchall()
        self.assertEqual(before, after)

        webhook = asyncio.run(
            protect_api(request("/api/webhooks/ozon/secret-one", "POST", malicious), next_response))
        self.assertEqual(webhook.status_code, 204)

    def test_login_authenticates_with_configured_hash(self):
        salt, digest = password_hash("secret")
        with patch("app.routers.auth._env", return_value={"ADMIN_PASSWORD_SALT": salt, "ADMIN_PASSWORD_HASH": digest}), \
             patch("app.routers.auth._token", return_value="token"):
            self.assertEqual(asyncio.run(login(body_request(b'{"password": "secret"}'), Response())), {"ok": True})

    def test_login_rate_limit_uses_only_trusted_forwarded_client_ip(self):
        class Request:
            url = type("URL", (), {"scheme": "https"})()

            def __init__(self, headers, host="127.0.0.1"):
                self.headers = headers
                self.client = type("Client", (), {"host": host})()

            async def stream(self):
                yield b'{"password": "wrong"}'

        requests = [
            (Request({"X-Forwarded-For": "8.8.8.8"}, "198.51.100.20"), "198.51.100.20"),
            (Request({"CF-Connecting-IP": "8.8.8.8"}, "198.51.100.20"), "198.51.100.20"),
            (Request({}, "192.0.2.9"), "192.0.2.9"),
            (Request({"X-Forwarded-For": "203.0.113.10"}), "203.0.113.10"),
            (Request({"X-Forwarded-For": "8.8.8.8, 203.0.113.10"}), "203.0.113.10"),
            (Request({"X-Forwarded-For": "1.1.1.1, 8.8.8.8, 203.0.113.10"}), "203.0.113.10"),
            (Request({"X-Forwarded-For": "garbage, 203.0.113.10"}), "203.0.113.10"),
            (Request({"X-Forwarded-For": "1.2.3.4, garbage"}), "127.0.0.1"),
            (Request({"X-Forwarded-For": "1.2.3.4, "}), "127.0.0.1"),
            (Request({"X-Forwarded-For": "garbage"}), "127.0.0.1"),
            (Request({"CF-Connecting-IP": "198.51.100.7"}), "127.0.0.1"),
            (Request({"CF-Connecting-IP": "198.51.100.7", "X-Forwarded-For": "8.8.8.8, 203.0.113.10"}), "203.0.113.10"),
            (Request({"X-Forwarded-For": "2001:0db8:0000::10"}, "::1"), "2001:db8::10"),
            (Request({"X-Forwarded-For": "2001:db8::99, 2001:0db8:0000::10"}, "::1"), "2001:db8::10"),
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

        first, second = "198.51.100.20", "203.0.113.10"
        clear_login_failures(first)
        clear_login_failures(second)
        for _ in range(5):
            record_login_failure(first, 100)
        self.assertTrue(login_limited(first, 101))
        self.assertFalse(login_limited(second, 101))
        clear_login_failures(first)
        clear_login_failures(second)

    def test_spoofed_forwarding_prefixes_share_the_real_client_rate_limit(self):
        real_ip = "203.0.113.10"
        salt, digest = password_hash("secret")
        with patch.dict(security._failures, {}, clear=True), \
                patch("app.routers.auth._env", return_value={"ADMIN_PASSWORD_SALT": salt, "ADMIN_PASSWORD_HASH": digest}):
            for index, prefix in enumerate(("1.1.1.1", "8.8.8.8", "9.9.9.9", "garbage", "2001:db8::99", "4.4.4.4")):
                request = body_request(b'{"password":"wrong"}', {
                    "X-Forwarded-For": f"{prefix}, {real_ip}", "CF-Connecting-IP": prefix,
                })
                with self.subTest(prefix=prefix):
                    with self.assertRaises(HTTPException) as raised:
                        asyncio.run(login(request, Response()))
                    self.assertEqual(raised.exception.status_code, 401 if index < 5 else 429)
            self.assertEqual(set(security._failures), {real_ip})
            self.assertEqual(len(security._failures[real_ip]), 5)

    def test_login_rejects_malformed_and_non_object_json(self):
        salt, digest = password_hash("secret")
        with patch("app.routers.auth._env", return_value={"ADMIN_PASSWORD_SALT": salt, "ADMIN_PASSWORD_HASH": digest}), \
             patch("app.routers.auth.password_matches") as matches:
            with self.assertRaisesRegex(HTTPException, "JSON无效"):
                asyncio.run(login(body_request(b"not-json"), Response()))
            with self.assertRaisesRegex(HTTPException, "必须是对象"):
                asyncio.run(login(body_request(b'["password"]'), Response()))
            with self.assertRaisesRegex(HTTPException, "Content-Length无效"):
                asyncio.run(login(body_request(b'{"password":"x"}', {"content-length": "abc"}), Response()))
        matches.assert_not_called()

    def test_login_rejects_oversized_body_before_password_check(self):
        salt, digest = password_hash("secret")
        with patch("app.routers.auth._env", return_value={"ADMIN_PASSWORD_SALT": salt, "ADMIN_PASSWORD_HASH": digest}), \
             patch("app.routers.auth.password_matches") as matches, \
             patch("app.routers.auth.record_login_failure") as record:
            with self.assertRaisesRegex(HTTPException, "请求体过大"):
                asyncio.run(login(
                    body_request(b'{"password":"x"}', {"content-length": str(LOGIN_MAX_BODY_BYTES + 1)}), Response()))
            request = StreamingBodyRequest([b"x" * (LOGIN_MAX_BODY_BYTES + 1), b"tail"])
            with self.assertRaisesRegex(HTTPException, "请求体过大"):
                asyncio.run(login(request, Response()))
            self.assertEqual(request.consumed, [b"x" * (LOGIN_MAX_BODY_BYTES + 1)])
        matches.assert_not_called()
        record.assert_not_called()

    def test_starlette_multi_range_exhaustion_is_fixed(self):
        version = tuple(int(part) for part in re.findall(r"\d+", starlette.__version__)[:3])
        self.assertGreaterEqual(version, (0, 49, 1), "Starlette 需包含 CVE-2025-62727 multi-Range 修复")

        async def serve(header_value):
            messages = []

            async def receive():
                return {"type": "http.request"}

            async def send(message):
                messages.append(message)

            scope = {"type": "http", "method": "GET", "headers": [(b"range", header_value.encode())]}
            await FileResponse(Path(temp) / "asset.js")(scope, receive, send)
            return messages[0]["status"], b"".join(message.get("body", b"") for message in messages)

        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "asset.js").write_bytes(b"0123456789" * 10)
            many = "bytes=" + ", ".join(f"{offset}-{offset + 1}" for offset in range(0, 1000, 2))
            status, body = asyncio.run(serve(many))
            self.assertEqual(status, 200)
            self.assertEqual(body, b"0123456789" * 10)
            status, body = asyncio.run(serve("bytes=0-4"))
            self.assertEqual(status, 206)
            self.assertEqual(body, b"01234")

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

            async def stream(self):
                yield b'{"password": "secret"}'

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
        self.assertEqual(auth._generation(), 1)
        self.assertEqual(session(request("/api/session", "GET")), {
            "authenticated": False, "csrf_token": "",
        })
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
