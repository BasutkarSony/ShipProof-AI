"""Tests for the optional shared password protecting the public demo."""
import base64
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import _valid_demo_authorization


class DemoAccessTests(unittest.TestCase):
    def _header(self, username: str, password: str) -> str:
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

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
