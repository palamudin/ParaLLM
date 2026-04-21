from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app import control, settings, storage


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        control.create_task({"objective": "Exercise the Python settings control plane."}, self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_set_auth_keys_supports_append_replace_remove_and_clear(self) -> None:
        appended = settings.set_auth_keys({"appendKey": "sk-one-1111"}, self.root)
        self.assertEqual(appended["keyCount"], 1)

        replaced = settings.set_auth_keys({"replaceIndex": 0, "apiKey": "sk-two-2222"}, self.root)
        self.assertEqual(replaced["last4"], "2222")
        self.assertEqual(control.read_auth_key_pool(self.root), ["sk-two-2222"])

        settings.set_auth_keys({"appendKey": "sk-three-3333"}, self.root)
        removed = settings.set_auth_keys({"removeIndex": 0}, self.root)
        self.assertEqual(removed["keyCount"], 1)
        self.assertEqual(control.read_auth_key_pool(self.root), ["sk-three-3333"])

        cleared = settings.set_auth_keys({"clear": 1}, self.root)
        self.assertFalse(cleared["hasKey"])
        self.assertEqual(control.read_auth_key_pool(self.root), [])

    def test_apply_runtime_settings_updates_task_snapshot_and_draft(self) -> None:
        result = settings.apply_runtime_settings(
            {
                "model": "gpt-5.4-mini",
                "summarizerModel": "gpt-5.4",
                "reasoningEffort": "high",
                "maxCostUsd": 19,
                "maxTotalTokens": 456000,
                "maxOutputTokens": 2400,
                "loopRounds": 5,
                "loopDelayMs": 250,
                "researchEnabled": 1,
                "localFilesEnabled": 1,
                "localFileRoots": ".,runtime",
                "githubToolsEnabled": 1,
                "githubAllowedRepos": "palamudin/ParaLLM",
                "dynamicSpinupEnabled": 1,
                "vettingEnabled": 0,
            },
            self.root,
        )

        self.assertEqual(result["workerModel"], "gpt-5.4-mini")
        self.assertEqual(result["summarizerModel"], "gpt-5.4")
        self.assertEqual(result["preferredLoop"]["rounds"], 5)

        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertEqual(state["activeTask"]["runtime"]["model"], "gpt-5.4-mini")
        self.assertEqual(state["activeTask"]["summarizer"]["model"], "gpt-5.4")
        self.assertTrue(all(worker["model"] == "gpt-5.4-mini" for worker in state["activeTask"]["workers"]))
        self.assertEqual(state["draft"]["summarizerModel"], "gpt-5.4")
        self.assertTrue(state["draft"]["githubToolsEnabled"])

    def test_update_worker_config_mutates_draft_only(self) -> None:
        result = settings.update_worker_config(
            {"workerId": "B", "type": "security", "temperature": "hot", "model": "gpt-5.4-mini"},
            self.root,
        )

        worker = result["worker"]
        self.assertEqual(worker["id"], "B")
        self.assertEqual(worker["type"], "security")
        self.assertEqual(worker["temperature"], "hot")
        self.assertEqual(worker["model"], "gpt-5.4-mini")

        state = storage.read_state_payload(storage.project_paths(self.root))
        draft_worker = next(item for item in state["draft"]["workers"] if item["id"] == "B")
        active_worker = next(item for item in state["activeTask"]["workers"] if item["id"] == "B")
        self.assertEqual(draft_worker["type"], "security")
        self.assertNotEqual(active_worker["type"], "security")

    def test_add_adversarial_worker_appends_next_slot_to_draft(self) -> None:
        result = settings.add_adversarial_worker({"type": "reliability"}, self.root)

        self.assertEqual(result["worker"]["id"], "C")
        self.assertEqual(result["worker"]["type"], "reliability")

        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertEqual([worker["id"] for worker in state["draft"]["workers"][:3]], ["A", "B", "C"])

    def test_set_position_model_updates_active_task_position(self) -> None:
        summarizer = settings.set_position_model({"positionId": "summarizer", "model": "gpt-5.4"}, self.root)
        worker = settings.set_position_model({"positionId": "A", "model": "gpt-5.4-mini"}, self.root)

        self.assertEqual(summarizer["model"], "gpt-5.4")
        self.assertEqual(worker["model"], "gpt-5.4-mini")

        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertEqual(state["activeTask"]["summarizer"]["model"], "gpt-5.4")
        self.assertEqual(next(item for item in state["activeTask"]["workers"] if item["id"] == "A")["model"], "gpt-5.4-mini")


if __name__ == "__main__":
    unittest.main()
