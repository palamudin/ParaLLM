from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import control, storage
from backend.app.secrets import write_auth_backend_mode_override
from runtime.engine import RuntimeErrorWithCode


class ControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_auth_pool_status_dedupes_and_masks(self) -> None:
        auth_path = self.root / "Auth.txt"
        auth_path.write_text("sk-one-1234\nsk-two-5678\nsk-one-1234\n", encoding="utf-8")

        with mock.patch.dict("os.environ", {"LOOP_SECRET_BACKEND": "local_file"}, clear=False):
            status = control.auth_pool_status(self.root)

        self.assertTrue(status["hasKey"])
        self.assertEqual(status["keyCount"], 2)
        self.assertIn("openai", status["providerGroups"])
        self.assertEqual(status["providerGroups"]["openai"]["last4"], "1234")
        self.assertEqual(len(status["providerGroups"]["openai"]["masks"]), 2)
        self.assertTrue(status["providerGroups"]["openai"]["masks"][0].endswith("1234"))
        self.assertEqual(status["providerGroups"]["anthropic"]["keyCount"], 0)
        self.assertTrue(status["deprecated"])
        self.assertFalse(status["preferred"])
        self.assertEqual(status["recommendedBackend"], "env")

    def test_auth_pool_status_honors_loop_auth_file_override(self) -> None:
        auth_path = self.root / "secrets" / "Auth.txt"
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text("sk-env-9999\n", encoding="utf-8")
        previous = os.environ.get("LOOP_AUTH_FILE")
        os.environ["LOOP_AUTH_FILE"] = str(auth_path)
        previous_backend = os.environ.get("LOOP_SECRET_BACKEND")
        os.environ["LOOP_SECRET_BACKEND"] = "local_file"
        try:
            status = control.auth_pool_status(self.root)
        finally:
            if previous is None:
                os.environ.pop("LOOP_AUTH_FILE", None)
            else:
                os.environ["LOOP_AUTH_FILE"] = previous
            if previous_backend is None:
                os.environ.pop("LOOP_SECRET_BACKEND", None)
            else:
                os.environ["LOOP_SECRET_BACKEND"] = previous_backend

        self.assertTrue(status["hasKey"])
        self.assertEqual(status["providerGroups"]["openai"]["last4"], "9999")

    def test_auth_pool_status_keeps_provider_groups_isolated(self) -> None:
        (self.root / "Auth.txt").write_text("sk-openai-1111\n", encoding="utf-8")
        (self.root / "Auth.anthropic.txt").write_text("sk-anthropic-2222\n", encoding="utf-8")

        with mock.patch.dict(
            "os.environ",
            {"LOOP_SECRET_BACKEND": "local_file", "LOOP_AUTH_FILE": str(self.root / "Auth.txt")},
            clear=False,
        ):
            status = control.auth_pool_status(self.root)
            self.assertEqual(status["keyCount"], 2)
            self.assertEqual(control.read_auth_key_pool(self.root, "openai"), ["sk-openai-1111"])
            self.assertEqual(control.read_auth_key_pool(self.root, "anthropic"), ["sk-anthropic-2222"])
            self.assertEqual(status["providerGroups"]["openai"]["keyCount"], 1)
            self.assertEqual(status["providerGroups"]["anthropic"]["keyCount"], 1)
            self.assertEqual(status["providerGroups"]["openai"]["last4"], "1111")
            self.assertEqual(status["providerGroups"]["anthropic"]["last4"], "2222")
            self.assertIn("isolated", status["isolationNote"].lower())

    def test_auth_pool_status_reads_prefixed_shared_auth_file_groups(self) -> None:
        (self.root / "Auth.txt").write_text(
            "openai:sk-openai-1111\nant:sk-anthropic-2222\nxai:sk-xai-3333\nmin:sk-minimax-4444\n",
            encoding="utf-8",
        )

        with mock.patch.dict("os.environ", {"LOOP_SECRET_BACKEND": "local_file"}, clear=False):
            status = control.auth_pool_status(self.root)
            self.assertEqual(control.read_auth_key_pool(self.root, "openai"), ["sk-openai-1111"])
            self.assertEqual(control.read_auth_key_pool(self.root, "anthropic"), ["sk-anthropic-2222"])
            self.assertEqual(control.read_auth_key_pool(self.root, "xai"), ["sk-xai-3333"])
            self.assertEqual(control.read_auth_key_pool(self.root, "minimax"), ["sk-minimax-4444"])
            self.assertEqual(status["providerGroups"]["anthropic"]["selectedMode"], "local")
            self.assertEqual(status["providerGroups"]["anthropic"]["effectiveBackend"], "local_file")

    def test_auth_pool_status_respects_provider_local_override_under_safe_backend(self) -> None:
        (self.root / "Auth.txt").write_text("openai:sk-local-1111\n", encoding="utf-8")
        write_auth_backend_mode_override(self.root, "openai", "local")
        env = {
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_OPENAI_API_KEYS": "sk-env-9999\n",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            status = control.auth_pool_status(self.root)

        self.assertEqual(control.read_auth_key_pool(self.root, "openai"), ["sk-local-1111"])
        self.assertEqual(status["providerGroups"]["openai"]["selectedMode"], "local")
        self.assertEqual(status["providerGroups"]["openai"]["effectiveBackend"], "local_file")

    def test_auth_file_path_honors_docker_secret_backend(self) -> None:
        secret_path = self.root / "secrets" / "openai_api_keys"
        previous_backend = os.environ.get("LOOP_SECRET_BACKEND")
        previous_secret_file = os.environ.get("LOOP_SECRET_FILE")
        os.environ["LOOP_SECRET_BACKEND"] = "docker_secret"
        os.environ["LOOP_SECRET_FILE"] = str(secret_path)
        try:
            resolved = control.auth_file_path(self.root)
        finally:
            if previous_backend is None:
                os.environ.pop("LOOP_SECRET_BACKEND", None)
            else:
                os.environ["LOOP_SECRET_BACKEND"] = previous_backend
            if previous_secret_file is None:
                os.environ.pop("LOOP_SECRET_FILE", None)
            else:
                os.environ["LOOP_SECRET_FILE"] = previous_secret_file

        self.assertEqual(resolved, secret_path)

    def test_save_draft_persists_normalized_draft(self) -> None:
        result = control.save_draft(
            {
                "objective": "Map the hosted migration",
                "constraints": '["No downtime", "Keep backward compatibility"]',
                "provider": "ollama",
                "model": "qwen3-coder",
                "summarizerProvider": "openai",
                "summarizerModel": "gpt-5.4-mini",
                "frontMode": "eval",
                "contextMode": "full",
                "directBaselineMode": "both",
                "directProvider": "anthropic",
                "directModel": "claude-sonnet-4-20250514",
                "ollamaBaseUrl": "http://192.168.0.26:11434",
                "targetTimeouts": '{"commander":95,"workerDefault":110,"workers":{"A":75},"commanderReview":205,"summarizer":215}',
                "researchEnabled": "1",
                "localFilesEnabled": "1",
                "localFileRoots": ".,runtime, api",
                "githubToolsEnabled": "1",
                "githubAllowedRepos": "palamudin/ParaLLM",
                "dynamicSpinupEnabled": "1",
                "workers": '[{"id":"A","type":"proponent"},{"id":"B","type":"security"}]',
                "summarizerHarness": '{"concision":"expansive","instruction":"Explain tradeoffs."}',
                "loopRounds": "4",
                "loopDelayMs": "750",
            },
            self.root,
        )

        self.assertEqual(result["message"], "Draft saved.")
        draft = result["draft"]
        self.assertEqual(draft["objective"], "Map the hosted migration")
        self.assertEqual(draft["provider"], "ollama")
        self.assertEqual(draft["constraints"], ["No downtime", "Keep backward compatibility"])
        self.assertEqual(draft["model"], "qwen3-coder")
        self.assertEqual(draft["summarizerProvider"], "openai")
        self.assertEqual(draft["frontMode"], "eval")
        self.assertEqual(draft["contextMode"], "full")
        self.assertEqual(draft["directBaselineMode"], "both")
        self.assertEqual(draft["directProvider"], "anthropic")
        self.assertEqual(draft["directModel"], "claude-sonnet-4-20250514")
        self.assertEqual(draft["ollamaBaseUrl"], "http://192.168.0.26:11434")
        self.assertEqual(draft["targetTimeouts"]["commander"], 95)
        self.assertEqual(draft["targetTimeouts"]["workerDefault"], 110)
        self.assertEqual(draft["targetTimeouts"]["workers"]["A"], 75)
        self.assertEqual(draft["targetTimeouts"]["commanderReview"], 205)
        self.assertFalse(draft["researchEnabled"])
        self.assertTrue(draft["localFilesEnabled"])
        self.assertTrue(draft["githubToolsEnabled"])
        self.assertEqual(draft["localFileRoots"], [".", "runtime", "api"])
        self.assertEqual(draft["githubAllowedRepos"], ["palamudin/parallm"])
        self.assertTrue(draft["dynamicSpinupEnabled"])
        self.assertEqual(len(draft["workers"]), 2)
        self.assertEqual(draft["workers"][1]["type"], "security")

        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertEqual(state["draft"]["objective"], "Map the hosted migration")

    def test_default_draft_budget_is_cost_only(self) -> None:
        draft = control.default_draft_state()

        self.assertEqual(draft["maxTotalTokens"], 0)
        self.assertEqual(draft["maxOutputTokens"], 0)
        self.assertEqual(draft["budgetTargets"]["commander"]["maxTotalTokens"], 0)
        self.assertEqual(draft["budgetTargets"]["worker"]["maxTotalTokens"], 0)
        self.assertEqual(draft["budgetTargets"]["summarizer"]["maxTotalTokens"], 0)

    def test_create_task_writes_state_snapshot_and_logs(self) -> None:
        result = control.create_task(
            {
                "objective": "Design the first hosted topology",
                "constraints": '["Keep Docker-first", "Do not break evals"]',
                "provider": "ollama",
                "model": "qwen3",
                "summarizerProvider": "openai",
                "summarizerModel": "gpt-5.4-mini",
                "frontMode": "eval",
                "contextMode": "full",
                "directBaselineMode": "both",
                "directProvider": "anthropic",
                "directModel": "claude-sonnet-4-20250514",
                "ollamaBaseUrl": "http://192.168.0.26:11434/api",
                "targetTimeouts": '{"commander":105,"workerDefault":125,"workers":{"B":90},"commanderReview":225,"summarizer":245}',
                "reasoningEffort": "medium",
                "loopRounds": "2",
                "loopDelayMs": "500",
                "workers": '[{"id":"A","type":"proponent"},{"id":"B","type":"reliability"}]',
                "summarizerHarness": '{"concision":"balanced","instruction":"Prefer concrete rollout advice."}',
            },
            self.root,
        )

        self.assertEqual(result["message"], "Task created.")
        task_id = result["taskId"]
        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)

        self.assertEqual(state["activeTask"]["taskId"], task_id)
        self.assertEqual(state["activeTask"]["runtime"]["provider"], "ollama")
        self.assertEqual(state["activeTask"]["runtime"]["model"], "qwen3")
        self.assertEqual(state["activeTask"]["runtime"]["frontMode"], "eval")
        self.assertEqual(state["activeTask"]["runtime"]["contextMode"], "full")
        self.assertEqual(state["activeTask"]["runtime"]["directBaselineMode"], "both")
        self.assertEqual(state["activeTask"]["runtime"]["directProvider"], "anthropic")
        self.assertEqual(state["activeTask"]["runtime"]["directModel"], "claude-sonnet-4-20250514")
        self.assertEqual(state["activeTask"]["runtime"]["ollamaBaseUrl"], "http://192.168.0.26:11434/api")
        self.assertEqual(state["activeTask"]["runtime"]["targetTimeouts"]["commander"], 105)
        self.assertEqual(state["activeTask"]["runtime"]["targetTimeouts"]["workerDefault"], 125)
        self.assertEqual(state["activeTask"]["runtime"]["targetTimeouts"]["workers"]["B"], 90)
        self.assertEqual(state["activeTask"]["summarizer"]["provider"], "openai")
        self.assertEqual(state["draft"]["objective"], "Design the first hosted topology")
        self.assertIsNone(state["arbiter"])
        self.assertIn("A", state["workers"])
        self.assertIn("B", state["workers"])
        self.assertTrue((paths.tasks / f"{task_id}.json").is_file())
        self.assertIn("task_started", paths.events.read_text(encoding="utf-8"))
        self.assertIn("Created a new task and reset worker memory.", paths.steps.read_text(encoding="utf-8"))

    def test_create_task_defaults_worker_models_to_provider_family(self) -> None:
        result = control.create_task(
            {
                "objective": "Exercise provider-aware default workers.",
                "provider": "ollama",
                "model": "qwen3:1.7b",
                "summarizerProvider": "ollama",
                "summarizerModel": "qwen3:1.7b",
            },
            self.root,
        )

        task = storage.read_json_file(storage.project_paths(self.root).tasks / f"{result['taskId']}.json")
        self.assertIsInstance(task, dict)
        workers = task.get("workers")
        self.assertIsInstance(workers, list)
        self.assertEqual([worker.get("model") for worker in workers], ["qwen3:1.7b", "qwen3:1.7b"])

    def test_create_task_rejects_active_loop(self) -> None:
        runtime_paths = storage.project_paths(self.root)
        state = storage.default_state()
        state["loop"]["jobId"] = "job-1"
        state["loop"]["status"] = "running"
        runtime_paths.data.mkdir(parents=True, exist_ok=True)
        runtime_paths.state.write_text(json.dumps(state), encoding="utf-8")
        runtime_paths.jobs.mkdir(parents=True, exist_ok=True)
        (runtime_paths.jobs / "job-1.json").write_text(
            json.dumps(
                {
                    "jobId": "job-1",
                    "jobType": "loop",
                    "status": "running",
                    "queuedAt": "2026-04-21T12:00:00+00:00",
                    "startedAt": "2026-04-21T12:00:01+00:00",
                    "lastHeartbeatAt": "2099-04-21T12:00:05+00:00",
                    "lastMessage": "Loop in progress.",
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(RuntimeErrorWithCode) as ctx:
            control.create_task({"objective": "Should fail"}, self.root)

        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
