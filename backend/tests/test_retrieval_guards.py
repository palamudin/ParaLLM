from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.engine import LoopRuntime, RuntimeErrorWithCode


class RetrievalGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "backend" / "app").mkdir(parents=True, exist_ok=True)
        (self.root / "backend" / "app" / "control.py").write_text("print('ok')\n", encoding="utf-8")
        (self.root / "secrets").mkdir(parents=True, exist_ok=True)
        (self.root / "secrets" / "openai_api_keys").write_text("sk-test\n", encoding="utf-8")
        (self.root / "Auth.txt").write_text("sk-test\n", encoding="utf-8")
        self.runtime = LoopRuntime(self.root)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_local_read_file_blocks_secret_shaped_paths(self) -> None:
        with self.assertRaises(RuntimeErrorWithCode):
            self.runtime.execute_local_file_tool_call(
                "local_read_file",
                {"path": "Auth.txt"},
                {"enabled": True, "roots": ["."]},
            )

    def test_local_list_dir_filters_secret_entries(self) -> None:
        result, audit = self.runtime.execute_local_file_tool_call(
            "local_list_dir",
            {"path": ".", "max_entries": 20},
            {"enabled": True, "roots": ["."]},
        )
        returned_paths = {str(entry.get("path", "")) for entry in result["entries"]}
        self.assertNotIn("Auth.txt", returned_paths)
        self.assertNotIn("secrets", returned_paths)
        self.assertGreaterEqual(int(result["filteredSensitiveEntries"]), 2)
        self.assertEqual(result["filteredSensitiveEntries"], audit["filteredSensitiveEntries"])

    def test_local_search_text_skips_secret_files(self) -> None:
        result, audit = self.runtime.execute_local_file_tool_call(
            "local_search_text",
            {"path": ".", "pattern": "sk-test", "max_matches": 10},
            {"enabled": True, "roots": ["."]},
        )
        self.assertEqual(result["matches"], [])
        self.assertGreaterEqual(int(result["filteredSensitiveFiles"]), 2)
        self.assertEqual(result["filteredSensitiveFiles"], audit["filteredSensitiveFiles"])

    def test_github_read_file_blocks_secret_shaped_paths(self) -> None:
        with self.assertRaises(RuntimeErrorWithCode):
            self.runtime.execute_github_tool_call(
                "github_read_file",
                {"repo": "openai/openai-cookbook", "path": ".env"},
                {"enabled": True, "repos": ["openai/openai-cookbook"]},
            )

    def test_github_list_paths_filters_secret_entries(self) -> None:
        def fake_github_request_json(url: str):
            return [
                {
                    "name": "README.md",
                    "path": "README.md",
                    "type": "file",
                    "size": 128,
                    "html_url": "https://github.com/openai/openai-cookbook/blob/main/README.md",
                },
                {
                    "name": ".env",
                    "path": ".env",
                    "type": "file",
                    "size": 32,
                    "html_url": "https://github.com/openai/openai-cookbook/blob/main/.env",
                },
                {
                    "name": "openai_api_keys",
                    "path": "secrets/openai_api_keys",
                    "type": "file",
                    "size": 64,
                    "html_url": "https://github.com/openai/openai-cookbook/blob/main/secrets/openai_api_keys",
                },
            ]

        original = self.runtime.github_request_json
        self.runtime.github_request_json = fake_github_request_json
        try:
            result, audit = self.runtime.execute_github_tool_call(
                "github_list_paths",
                {"repo": "openai/openai-cookbook", "ref": "main"},
                {"enabled": True, "repos": ["openai/openai-cookbook"]},
            )
        finally:
            self.runtime.github_request_json = original

        returned_paths = {str(entry.get("path", "")) for entry in result["entries"]}
        self.assertEqual(returned_paths, {"README.md"})
        self.assertEqual(int(result["filteredSensitiveEntries"]), 2)
        self.assertEqual(result["filteredSensitiveEntries"], audit["filteredSensitiveEntries"])


if __name__ == "__main__":
    unittest.main()
