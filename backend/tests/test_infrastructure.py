from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import config, control, infrastructure, settings
from runtime.engine import RuntimeErrorWithCode


class InfrastructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_env_secret_backend_reads_keys_from_environment(self) -> None:
        env = {
            "LOOP_ROOT": str(self.root),
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_OPENAI_API_KEYS": "sk-one\nsk-two\nsk-one\n",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            keys = control.read_auth_key_pool(self.root)
            status = control.auth_pool_status(self.root)

        self.assertEqual(keys, ["sk-one", "sk-two"])
        self.assertEqual(status["backend"], "env")
        self.assertFalse(status["writable"])
        self.assertEqual(status["keyCount"], 2)

    def test_env_secret_backend_disables_ui_mutation(self) -> None:
        env = {
            "LOOP_ROOT": str(self.root),
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_OPENAI_API_KEYS": "sk-one\n",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            with self.assertRaises(RuntimeErrorWithCode):
                settings.set_auth_keys({"apiKeys": ["sk-two"]}, self.root)

    def test_env_secret_backend_reports_strict_live_failure_when_empty(self) -> None:
        env = {
            "LOOP_ROOT": str(self.root),
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_OPENAI_API_KEYS": "",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            status = control.auth_pool_status(self.root)
            infra = infrastructure.infrastructure_status(self.root)

        self.assertEqual(status["backend"], "env")
        self.assertFalse(status["available"])
        self.assertTrue(status["strictLiveFailure"])
        self.assertEqual(status["failureMode"], "empty")
        self.assertEqual(infra["backends"]["secrets"]["failureMode"], "empty")

    def test_docker_secret_backend_reads_keys_from_mounted_file(self) -> None:
        secret_path = self.root / "secrets" / "openai_api_keys"
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text("sk-one\nsk-two\nsk-one\n", encoding="utf-8")
        env = {
            "LOOP_ROOT": str(self.root),
            "LOOP_SECRET_BACKEND": "docker_secret",
            "LOOP_SECRET_FILE": str(secret_path),
        }
        with mock.patch.dict("os.environ", env, clear=False):
            keys = control.read_auth_key_pool(self.root)
            status = control.auth_pool_status(self.root)
            infra = infrastructure.infrastructure_status(self.root)

        self.assertEqual(keys, ["sk-one", "sk-two"])
        self.assertEqual(status["backend"], "docker_secret")
        self.assertFalse(status["writable"])
        self.assertEqual(status["keyCount"], 2)
        self.assertTrue(infra["backends"]["secrets"]["ready"])

    def test_docker_secret_backend_disables_ui_mutation(self) -> None:
        secret_path = self.root / "secrets" / "openai_api_keys"
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text("sk-one\n", encoding="utf-8")
        env = {
            "LOOP_ROOT": str(self.root),
            "LOOP_SECRET_BACKEND": "docker_secret",
            "LOOP_SECRET_FILE": str(secret_path),
        }
        with mock.patch.dict("os.environ", env, clear=False):
            with self.assertRaises(RuntimeErrorWithCode):
                settings.set_auth_keys({"apiKeys": ["sk-two"]}, self.root)

    def test_local_infrastructure_status_is_ready(self) -> None:
        status = infrastructure.infrastructure_status(self.root)
        self.assertEqual(status["profile"], "local-single-node")
        self.assertTrue(status["backends"]["queue"]["ready"])
        self.assertTrue(status["backends"]["runtimeExecution"]["ready"])

    def test_local_profile_defaults_to_env_secret_backend(self) -> None:
        env = {"LOOP_ROOT": str(self.root)}
        with mock.patch.dict("os.environ", env, clear=True):
            topology = config.deployment_topology(self.root)
        self.assertEqual(topology.secret_backend, "env")

    def test_hosted_profile_defaults_to_docker_secret_backend(self) -> None:
        env = {
            "LOOP_ROOT": str(self.root),
            "LOOP_DEPLOYMENT_PROFILE": "hosted-single-node",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            topology = config.deployment_topology(self.root)
        self.assertEqual(topology.secret_backend, "docker_secret")


if __name__ == "__main__":
    unittest.main()
