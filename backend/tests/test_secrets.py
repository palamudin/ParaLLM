from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from backend.app import control, infrastructure
from backend.app.secrets import external_secret_status
from runtime.engine import read_api_key_pool


class _SecretProviderHandler(BaseHTTPRequestHandler):
    response_status = 200
    response_headers = {"Content-Type": "application/json"}
    response_body = json.dumps({"keys": ["sk-one", "sk-two", "sk-one"]}).encode("utf-8")
    expected_token = "test-token"

    def do_GET(self) -> None:  # noqa: N802
        if self.headers.get("Authorization") != f"Bearer {self.expected_token}":
            self.send_response(401)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"unauthorized")
            return
        self.send_response(self.response_status)
        for name, value in self.response_headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(self.response_body)

    def log_message(self, format: str, *args: object) -> None:
        return


class ExternalSecretBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _SecretProviderHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.provider_url = f"http://127.0.0.1:{self.server.server_port}/keys"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)
        self._tmp.cleanup()

    def _env(self) -> dict[str, str]:
        return {
            "LOOP_ROOT": str(self.root),
            "LOOP_SECRET_BACKEND": "external",
            "LOOP_SECRET_PROVIDER_URL": self.provider_url,
            "LOOP_SECRET_PROVIDER_TOKEN": "test-token",
            "LOOP_SECRET_PROVIDER_HEALTHCHECK_URL": self.provider_url,
        }

    def test_control_reads_external_secret_provider_keys(self) -> None:
        with mock.patch.dict("os.environ", self._env(), clear=False):
            keys = control.read_auth_key_pool(self.root)
            status = control.auth_pool_status(self.root)

        self.assertEqual(keys, ["sk-one", "sk-two"])
        self.assertEqual(status["backend"], "external")
        self.assertFalse(status["writable"])
        self.assertEqual(status["keyCount"], 2)

    def test_infrastructure_reports_external_secret_provider_ready(self) -> None:
        with mock.patch.dict("os.environ", self._env(), clear=False):
            status = infrastructure.infrastructure_status(self.root)

        secrets = status["backends"]["secrets"]
        self.assertTrue(secrets["configured"])
        self.assertTrue(secrets["ready"])
        self.assertEqual(secrets["keyCount"], 2)

    def test_runtime_reads_external_secret_provider_keys(self) -> None:
        missing_path = self.root / "missing-auth.txt"
        with mock.patch.dict("os.environ", self._env(), clear=False):
            keys = read_api_key_pool(missing_path)

        self.assertEqual(keys, ["sk-one", "sk-two"])

    def test_external_secret_backend_reads_grouped_provider_payloads(self) -> None:
        previous_body = _SecretProviderHandler.response_body
        _SecretProviderHandler.response_body = json.dumps(
            {
                "providers": {
                    "openai": ["sk-openai"],
                    "anthropic": ["sk-anthropic", "sk-anthropic"],
                }
            }
        ).encode("utf-8")
        try:
            with mock.patch.dict("os.environ", self._env(), clear=False):
                anthropic_status = external_secret_status(self.root, provider="anthropic")
                auth_status = control.auth_pool_status(self.root)
                runtime_keys = read_api_key_pool(self.root / "missing-auth.txt", "anthropic")
        finally:
            _SecretProviderHandler.response_body = previous_body

        self.assertEqual(anthropic_status["keys"], ["sk-anthropic"])
        self.assertEqual(runtime_keys, ["sk-anthropic"])
        self.assertEqual(auth_status["keyCount"], 2)
        self.assertEqual(auth_status["providerGroups"]["openai"]["keyCount"], 1)
        self.assertEqual(auth_status["providerGroups"]["anthropic"]["keyCount"], 1)

    def test_external_secret_status_reports_unreachable_provider(self) -> None:
        env = self._env()
        env["LOOP_SECRET_PROVIDER_URL"] = "http://127.0.0.1:1/keys"
        env["LOOP_SECRET_PROVIDER_HEALTHCHECK_URL"] = "http://127.0.0.1:1/keys"
        with mock.patch.dict("os.environ", env, clear=False):
            status = external_secret_status(self.root, timeout=0.25)

        self.assertFalse(status["ready"])
        self.assertEqual(status["failureMode"], "unreachable")
        self.assertEqual(status["keys"], [])


if __name__ == "__main__":
    unittest.main()
