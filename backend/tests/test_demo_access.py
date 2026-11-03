"""Tests for the optional shared password protecting the public demo."""
import base64
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starlette.requests import Request
from starlette.responses import Response
from app.main import _valid_demo_authorization, protect_public_demo


class DemoAccessTests(unittest.TestCase):
    def _header(self, username: str, password: str) -> str:
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"


    def _request(self, path="/", headers=None):
        return Request({
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [
                (key.lower().encode("ascii"), value.encode("latin-1"))
                for key, value in (headers or {}).items()
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("parcelproof.test", 443),
        })

    def test_protected_demo_rejects_unauthenticated_page_requests(self):
        async def call_next(_request):
            return Response("unexpected")

        with patch.dict(os.environ, {
            "PARCELPROOF_DEMO_AUTH_REQUIRED": "true",
            "PARCELPROOF_DEMO_USERNAME": "judge",
            "PARCELPROOF_DEMO_PASSWORD": "long-demo-secret",
        }):
            response = __import__("asyncio").run(
                protect_public_demo(self._request("/"), call_next)
            )

        self.assertEqual(response.status_code, 401)
        self.assertIn("Basic", response.headers.get("www-authenticate", ""))

    def test_protected_demo_allows_valid_credentials(self):
        async def call_next(_request):
            return Response("ok", status_code=200)

        header = self._header("judge", "long-demo-secret")
        with patch.dict(os.environ, {
            "PARCELPROOF_DEMO_AUTH_REQUIRED": "true",
            "PARCELPROOF_DEMO_USERNAME": "judge",
            "PARCELPROOF_DEMO_PASSWORD": "long-demo-secret",
        }):
            response = __import__("asyncio").run(
                protect_public_demo(self._request("/", {"Authorization": header}), call_next)
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-frame-options"), "DENY")

    def test_protected_demo_fails_closed_when_secrets_are_missing(self):
        async def call_next(_request):
            return Response("unexpected")

        with patch.dict(os.environ, {
            "PARCELPROOF_DEMO_AUTH_REQUIRED": "true",
            "PARCELPROOF_DEMO_USERNAME": "",
            "PARCELPROOF_DEMO_PASSWORD": "",
        }):
            response = __import__("asyncio").run(
                protect_public_demo(self._request("/"), call_next)
            )

        self.assertEqual(response.status_code, 503)

    def test_render_health_check_is_public_even_when_demo_auth_is_required(self):
        async def call_next(_request):
            return Response("healthy", status_code=200)

        with patch.dict(os.environ, {
            "PARCELPROOF_DEMO_AUTH_REQUIRED": "true",
            "PARCELPROOF_DEMO_USERNAME": "",
            "PARCELPROOF_DEMO_PASSWORD": "",
        }):
            response = __import__("asyncio").run(
                protect_public_demo(self._request("/health"), call_next)
            )

        self.assertEqual(response.status_code, 200)

    def test_accepts_matching_shared_demo_credentials(self):
        with patch.dict(os.environ, {
            "PARCELPROOF_DEMO_USERNAME": "judge",
            "PARCELPROOF_DEMO_PASSWORD": "long-demo-secret",
        }):
            self.assertTrue(
                _valid_demo_authorization(self._header("judge", "long-demo-secret"))
            )

    def test_rejects_wrong_password(self):
        with patch.dict(os.environ, {
            "PARCELPROOF_DEMO_USERNAME": "judge",
            "PARCELPROOF_DEMO_PASSWORD": "long-demo-secret",
        }):
            self.assertFalse(
                _valid_demo_authorization(self._header("judge", "wrong-secret"))
            )

    def test_rejects_wrong_username(self):
        with patch.dict(os.environ, {
            "PARCELPROOF_DEMO_USERNAME": "judge",
            "PARCELPROOF_DEMO_PASSWORD": "long-demo-secret",
        }):
            self.assertFalse(
                _valid_demo_authorization(self._header("someone-else", "long-demo-secret"))
            )

    def test_rejects_malformed_or_non_basic_authorization(self):
        with patch.dict(os.environ, {
            "PARCELPROOF_DEMO_USERNAME": "judge",
            "PARCELPROOF_DEMO_PASSWORD": "long-demo-secret",
        }):
            self.assertFalse(_valid_demo_authorization("Bearer not-a-basic-token"))
            self.assertFalse(_valid_demo_authorization("Basic not-base64"))

    def test_rejects_when_credentials_are_not_configured(self):
        with patch.dict(os.environ, {
            "PARCELPROOF_DEMO_USERNAME": "",
            "PARCELPROOF_DEMO_PASSWORD": "",
        }, clear=False):
            self.assertFalse(_valid_demo_authorization(self._header("judge", "secret")))

    def test_rejects_partial_demo_credential_configuration(self):
        with patch.dict(os.environ, {
            "PARCELPROOF_DEMO_USERNAME": "judge",
            "PARCELPROOF_DEMO_PASSWORD": "",
        }, clear=False):
            self.assertFalse(_valid_demo_authorization(self._header("judge", "secret")))


if __name__ == "__main__":
    unittest.main()
