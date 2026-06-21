import os
import sys
import unittest
from unittest import mock

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api.main as main

_TEST_KEY = "test-key"


class TestApiAuth(unittest.TestCase):
    """Auth gating on protected endpoints.

    Regression: a request with a missing or empty credential must return 401,
    not crash with 500 (HTTPBearer(auto_error=False) yields None).
    """

    def setUp(self) -> None:
        self.client = TestClient(main.app, raise_server_exceptions=False)
        patcher = mock.patch("lib.auth._get_api_key", return_value=_TEST_KEY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_credential_returns_401(self) -> None:
        self.assertEqual(self.client.get("/projects").status_code, 401)

    def test_empty_bearer_returns_401(self) -> None:
        r = self.client.get("/projects", headers={"Authorization": "Bearer "})
        self.assertEqual(r.status_code, 401)

    def test_wrong_key_returns_401(self) -> None:
        r = self.client.get("/projects", headers={"Authorization": "Bearer wrong"})
        self.assertEqual(r.status_code, 401)

    def test_valid_key_returns_200(self) -> None:
        r = self.client.get("/projects", headers={"Authorization": f"Bearer {_TEST_KEY}"})
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_reconcile_requires_auth(self) -> None:
        self.assertEqual(self.client.post("/reconcile").status_code, 401)


if __name__ == "__main__":
    unittest.main()
