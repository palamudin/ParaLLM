from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import control, settings, storage
from backend.app.secrets import write_auth_backend_mode_override
from runtime.engine import RuntimeErrorWithCode


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        control.create_task({"objective": "Exercise the Python settings control plane."}, self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_set_auth_keys_supports_append_replace_remove_and_clear(self) -> None:
        with mock.patch.dict("os.environ", {"LOOP_SECRET_BACKEND": "local_file"}, clear=False):
            appended = settings.set_auth_keys({"appendKey": "sk-one-1111"}, self.root)
            self.assertEqual(appended["keyCount"], 1)
            self.assertEqual(appended["providerGroups"]["openai"]["keyCount"], 1)

            replaced = settings.set_auth_keys({"replaceIndex": 0, "apiKey": "sk-two-2222"}, self.root)
            self.assertEqual(replaced["providerGroups"]["openai"]["last4"], "2222")
            self.assertEqual(control.read_auth_key_pool(self.root), ["sk-two-2222"])

            settings.set_auth_keys({"appendKey": "sk-three-3333"}, self.root)
            removed = settings.set_auth_keys({"removeIndex": 0}, self.root)
            self.assertEqual(removed["keyCount"], 1)
            self.assertEqual(control.read_auth_key_pool(self.root), ["sk-three-3333"])

            cleared = settings.set_auth_keys({"clear": 1}, self.root)
            self.assertFalse(cleared["hasKey"])
            self.assertEqual(control.read_auth_key_pool(self.root), [])

    def test_set_auth_keys_keeps_provider_pools_isolated(self) -> None:
        with mock.patch.dict("os.environ", {"LOOP_SECRET_BACKEND": "local_file"}, clear=False):
            settings.set_auth_keys({"provider": "openai", "appendKey": "sk-openai-1111"}, self.root)
            status = settings.set_auth_keys({"provider": "anthropic", "appendKey": "sk-anthropic-2222"}, self.root)

            self.assertEqual(control.read_auth_key_pool(self.root, "openai"), ["sk-openai-1111"])
            self.assertEqual(control.read_auth_key_pool(self.root, "anthropic"), ["sk-anthropic-2222"])
            self.assertEqual(status["providerGroups"]["openai"]["keyCount"], 1)
            self.assertEqual(status["providerGroups"]["anthropic"]["keyCount"], 1)

            settings.set_auth_keys({"provider": "anthropic", "clear": 1}, self.root)
            self.assertEqual(control.read_auth_key_pool(self.root, "openai"), ["sk-openai-1111"])
            self.assertEqual(control.read_auth_key_pool(self.root, "anthropic"), [])

    def test_set_auth_keys_migrates_provider_group_into_shared_auth_file(self) -> None:
        (self.root / "Auth.anthropic.txt").write_text("sk-legacy-1111\n", encoding="utf-8")

        with mock.patch.dict("os.environ", {"LOOP_SECRET_BACKEND": "local_file"}, clear=False):
            settings.set_auth_keys({"provider": "anthropic", "appendKey": "sk-anthropic-2222"}, self.root)
            shared_after_write = (self.root / "Auth.txt").read_text(encoding="utf-8")
            settings.set_auth_keys({"provider": "anthropic", "clear": 1}, self.root)

        self.assertIn("ant:sk-anthropic-2222", shared_after_write)
        self.assertEqual(control.read_auth_key_pool(self.root, "anthropic"), [])
        self.assertFalse((self.root / "Auth.anthropic.txt").exists())
        self.assertNotIn("ant:", (self.root / "Auth.txt").read_text(encoding="utf-8"))

    def test_set_auth_backend_mode_changes_only_target_provider_group(self) -> None:
        env = {
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_OPENAI_API_KEYS": "sk-env-openai\n",
            "LOOP_ANTHROPIC_API_KEYS": "sk-env-anthropic\n",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            result = settings.set_auth_backend_mode({"provider": "openai", "mode": "local"}, self.root)

        self.assertEqual(result["providerGroups"]["openai"]["selectedMode"], "local")
        self.assertEqual(result["providerGroups"]["openai"]["effectiveBackend"], "local_file")
        self.assertEqual(result["providerGroups"]["anthropic"]["selectedMode"], "env")

    def test_set_auth_backend_mode_supports_db_backed_provider_group(self) -> None:
        env = {
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_SECRET_PROVIDER_URL": "https://secrets.example.invalid/provider",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            result = settings.set_auth_backend_mode({"provider": "openai", "mode": "db"}, self.root)

        self.assertEqual(result["providerGroups"]["openai"]["selectedMode"], "db")
        self.assertEqual(result["providerGroups"]["openai"]["effectiveBackend"], "external")

    def test_set_auth_keys_refuses_mutation_for_safe_provider_group(self) -> None:
        env = {
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_OPENAI_API_KEYS": "sk-env-openai\n",
        }
        write_auth_backend_mode_override(self.root, "anthropic", "env")
        with mock.patch.dict("os.environ", env, clear=False):
            with self.assertRaises(RuntimeErrorWithCode):
                settings.set_auth_keys({"provider": "anthropic", "appendKey": "sk-anthropic-2222"}, self.root)

    def test_apply_runtime_settings_updates_task_snapshot_and_draft(self) -> None:
        result = settings.apply_runtime_settings(
            {
                "provider": "ollama",
                "model": "qwen3",
                "summarizerProvider": "openai",
                "summarizerModel": "gpt-5.4-mini",
                "frontMode": "eval",
                "engineVersion": "v2",
                "contextMode": "full",
                "directBaselineMode": "both",
                "directProvider": "anthropic",
                "directModel": "claude-sonnet-4-20250514",
                "ollamaBaseUrl": "http://192.168.0.26:11434",
                "targetTimeouts": {"commander": 100, "workerDefault": 120, "workers": {"A": 80}, "commanderReview": 230, "summarizer": 245},
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

        self.assertEqual(result["provider"], "ollama")
        self.assertEqual(result["workerModel"], "qwen3")
        self.assertEqual(result["summarizerProvider"], "openai")
        self.assertEqual(result["summarizerModel"], "gpt-5.4-mini")
        self.assertEqual(result["frontMode"], "eval")
        self.assertEqual(result["engineVersion"], "v2")
        self.assertEqual(result["contextMode"], "full")
        self.assertEqual(result["directBaselineMode"], "both")
        self.assertEqual(result["directProvider"], "anthropic")
        self.assertEqual(result["directModel"], "claude-sonnet-4-20250514")
        self.assertEqual(result["ollamaBaseUrl"], "http://192.168.0.26:11434")
        self.assertEqual(result["targetTimeouts"]["commander"], 100)
        self.assertEqual(result["targetTimeouts"]["workerDefault"], 120)
        self.assertEqual(result["targetTimeouts"]["workers"]["A"], 80)
        self.assertEqual(result["preferredLoop"]["rounds"], 5)

        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertEqual(state["activeTask"]["runtime"]["provider"], "ollama")
        self.assertEqual(state["activeTask"]["runtime"]["model"], "qwen3")
        self.assertEqual(state["activeTask"]["runtime"]["frontMode"], "eval")
        self.assertEqual(state["activeTask"]["runtime"]["engineVersion"], "v2")
        self.assertEqual(state["activeTask"]["runtime"]["contextMode"], "full")
        self.assertEqual(state["activeTask"]["runtime"]["directBaselineMode"], "both")
        self.assertEqual(state["activeTask"]["runtime"]["directProvider"], "anthropic")
        self.assertEqual(state["activeTask"]["runtime"]["directModel"], "claude-sonnet-4-20250514")
        self.assertEqual(state["activeTask"]["runtime"]["ollamaBaseUrl"], "http://192.168.0.26:11434")
        self.assertEqual(state["activeTask"]["runtime"]["targetTimeouts"]["commander"], 100)
        self.assertEqual(state["activeTask"]["runtime"]["targetTimeouts"]["workerDefault"], 120)
        self.assertEqual(state["activeTask"]["runtime"]["targetTimeouts"]["workers"]["A"], 80)
        self.assertEqual(state["activeTask"]["summarizer"]["provider"], "openai")
        self.assertEqual(state["activeTask"]["summarizer"]["model"], "gpt-5.4-mini")
        self.assertTrue(all(worker["model"] == "qwen3" for worker in state["activeTask"]["workers"]))
        self.assertEqual(state["draft"]["provider"], "ollama")
        self.assertEqual(state["draft"]["summarizerProvider"], "openai")
        self.assertEqual(state["draft"]["summarizerModel"], "gpt-5.4-mini")
        self.assertEqual(state["draft"]["frontMode"], "eval")
        self.assertEqual(state["draft"]["engineVersion"], "v2")
        self.assertEqual(state["draft"]["contextMode"], "full")
        self.assertEqual(state["draft"]["directBaselineMode"], "both")
        self.assertEqual(state["draft"]["directProvider"], "anthropic")
        self.assertEqual(state["draft"]["directModel"], "claude-sonnet-4-20250514")
        self.assertEqual(state["draft"]["ollamaBaseUrl"], "http://192.168.0.26:11434")
        self.assertEqual(state["draft"]["targetTimeouts"]["commander"], 100)
        self.assertEqual(state["draft"]["targetTimeouts"]["workerDefault"], 120)
        self.assertEqual(state["draft"]["targetTimeouts"]["workers"]["A"], 80)
        self.assertFalse(state["activeTask"]["runtime"]["research"]["enabled"])
        self.assertTrue(state["activeTask"]["runtime"]["localFiles"]["enabled"])
        self.assertTrue(state["activeTask"]["runtime"]["githubTools"]["enabled"])
        self.assertFalse(state["draft"]["researchEnabled"])
        self.assertTrue(state["draft"]["localFilesEnabled"])
        self.assertTrue(state["draft"]["githubToolsEnabled"])

        scoped = storage.read_task_state_payload(state["activeTask"]["taskId"], storage.project_paths(self.root))
        self.assertIsNotNone(scoped)
        self.assertEqual(scoped["activeTask"]["runtime"]["frontMode"], "eval")
        self.assertEqual(scoped["activeTask"]["runtime"]["engineVersion"], "v2")
        self.assertEqual(scoped["activeTask"]["runtime"]["directBaselineMode"], "both")
        self.assertEqual(scoped["activeTask"]["runtime"]["targetTimeouts"]["workers"]["A"], 80)
        self.assertEqual(scoped["draft"]["provider"], "ollama")
        self.assertEqual(scoped["draft"]["summarizerProvider"], "openai")

    def test_apply_runtime_settings_clears_stale_arbiter_score(self) -> None:
        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        state["arbiter"] = {"taskId": state["activeTask"]["taskId"], "comparison": {"verdict": "pressurized_advantage"}}
        paths.state.write_text(json.dumps(state, indent=2), encoding="utf-8")

        settings.apply_runtime_settings({"frontMode": "eval"}, self.root)

        refreshed = storage.read_state_payload(paths)
        self.assertIsNone(refreshed["arbiter"])

    def test_apply_runtime_settings_preserves_staged_draft_worker_roster(self) -> None:
        settings.add_adversarial_worker({"type": "reliability"}, self.root)
        settings.update_worker_config({"workerId": "B", "type": "security", "temperature": "hot"}, self.root)

        result = settings.apply_runtime_settings(
            {
                "provider": "ollama",
                "model": "qwen3",
                "summarizerProvider": "openai",
                "summarizerModel": "gpt-5.4-mini",
                "contextMode": "full",
                "ollamaBaseUrl": "http://192.168.0.26:11434/api",
            },
            self.root,
        )

        self.assertEqual(result["provider"], "ollama")
        state = storage.read_state_payload(storage.project_paths(self.root))

        self.assertEqual([worker["id"] for worker in state["activeTask"]["workers"]], ["A", "B"])
        self.assertEqual([worker["id"] for worker in state["draft"]["workers"]], ["A", "B", "C"])
        self.assertEqual(state["draft"]["provider"], "ollama")
        self.assertEqual(state["draft"]["model"], "qwen3")
        self.assertEqual(state["draft"]["contextMode"], "full")
        self.assertEqual(state["draft"]["ollamaBaseUrl"], "http://192.168.0.26:11434/api")
        self.assertEqual(next(worker for worker in state["draft"]["workers"] if worker["id"] == "B")["type"], "security")
        self.assertEqual(next(worker for worker in state["draft"]["workers"] if worker["id"] == "B")["temperature"], "hot")

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

        scoped = storage.read_task_state_payload(state["activeTask"]["taskId"], storage.project_paths(self.root))
        self.assertIsNotNone(scoped)
        scoped_draft_worker = next(item for item in scoped["draft"]["workers"] if item["id"] == "B")
        self.assertEqual(scoped_draft_worker["type"], "security")
        scoped_active_worker = next(item for item in scoped["activeTask"]["workers"] if item["id"] == "B")
        self.assertNotEqual(scoped_active_worker["type"], "security")

    def test_add_adversarial_worker_appends_next_slot_to_draft(self) -> None:
        result = settings.add_adversarial_worker({"type": "reliability"}, self.root)

        self.assertEqual(result["worker"]["id"], "C")
        self.assertEqual(result["worker"]["type"], "reliability")

        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertEqual([worker["id"] for worker in state["draft"]["workers"][:3]], ["A", "B", "C"])

    def test_add_adversarial_worker_uses_staged_draft_for_next_slot(self) -> None:
        first = settings.add_adversarial_worker({"type": "reliability"}, self.root)
        second = settings.add_adversarial_worker({"type": "security"}, self.root)

        self.assertEqual(first["worker"]["id"], "C")
        self.assertEqual(second["worker"]["id"], "D")

        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertEqual([worker["id"] for worker in state["draft"]["workers"][:4]], ["A", "B", "C", "D"])
        self.assertEqual(next(worker for worker in state["draft"]["workers"] if worker["id"] == "D")["type"], "security")

    def test_remove_adversarial_worker_drops_last_staged_slot_only(self) -> None:
        settings.add_adversarial_worker({"type": "reliability"}, self.root)
        settings.add_adversarial_worker({"type": "security"}, self.root)

        result = settings.remove_adversarial_worker({}, self.root)

        self.assertEqual(result["worker"]["id"], "D")
        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertEqual([worker["id"] for worker in state["draft"]["workers"][:3]], ["A", "B", "C"])
        self.assertEqual([worker["id"] for worker in state["activeTask"]["workers"]], ["A", "B"])

    def test_remove_adversarial_worker_updates_active_task_when_lane_is_live(self) -> None:
        settings.add_adversarial_worker({"type": "reliability"}, self.root)

        runtime = settings._runtime(self.root)

        def mutate(current):
            next_state = dict(current)
            active_task = dict(next_state["activeTask"])
            draft = control.normalize_draft_state(current.get("draft") if isinstance(current.get("draft"), dict) else {})
            active_task["workers"] = settings.task_workers({"runtime": active_task.get("runtime") or {}, "workers": draft["workers"]})
            next_state["activeTask"] = active_task
            return next_state

        runtime.mutate_state(mutate)

        result = settings.remove_adversarial_worker({}, self.root)

        self.assertEqual(result["worker"]["id"], "C")
        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertEqual([worker["id"] for worker in state["draft"]["workers"]], ["A", "B"])
        self.assertEqual([worker["id"] for worker in state["activeTask"]["workers"]], ["A", "B"])

    def test_remove_adversarial_worker_keeps_two_lane_floor(self) -> None:
        with self.assertRaises(RuntimeErrorWithCode):
            settings.remove_adversarial_worker({}, self.root)

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
