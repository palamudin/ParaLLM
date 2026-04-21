from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime.engine import read_api_key_pool


class RuntimeAuthTests(unittest.TestCase):
    def test_read_api_key_pool_uses_env_backend_when_configured(self) -> None:
        missing_path = Path(tempfile.gettempdir()) / "parallm-missing-auth.txt"
        env = {
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_OPENAI_API_KEYS": "sk-one\nsk-two\nsk-one\n",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            keys = read_api_key_pool(missing_path)

        self.assertEqual(keys, ["sk-one", "sk-two"])

    def test_read_api_key_pool_reads_mounted_secret_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "openai_api_keys"
            secret_path.write_text("sk-one\nsk-two\n", encoding="utf-8")
            env = {
                "LOOP_SECRET_BACKEND": "docker_secret",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                keys = read_api_key_pool(secret_path)

        self.assertEqual(keys, ["sk-one", "sk-two"])


if __name__ == "__main__":
    unittest.main()
