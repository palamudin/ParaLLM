from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import control, storage
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
        self.assertEqual(status["last4"], "1234")
        self.assertEqual(len(status["masks"]), 2)
        self.assertTrue(status["masks"][0].endswith("1234"))
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
        self.assertEqual(status["last4"], "9999")

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
        self.assertTrue(draft["researchEnabled"])
        self.assertEqual(draft["localFileRoots"], [".", "runtime", "api"])
        self.assertEqual(draft["githubAllowedRepos"], ["palamudin/parallm"])
        self.assertTrue(draft["dynamicSpinupEnabled"])
        self.assertEqual(len(draft["workers"]), 2)
        self.assertEqual(draft["workers"][1]["type"], "security")

        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertEqual(state["draft"]["objective"], "Map the hosted migration")

    def test_create_task_writes_state_snapshot_and_logs(self) -> None:
        result = control.create_task(
            {
                "objective": "Design the first hosted topology",
                "constraints": '["Keep Docker-first", "Do not break evals"]',
                "provider": "ollama",
                "model": "qwen3",
                "summarizerProvider": "openai",
                "summarizerModel": "gpt-5.4-mini",
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
        self.assertEqual(state["activeTask"]["summarizer"]["provider"], "openai")
        self.assertEqual(state["draft"]["objective"], "Design the first hosted topology")
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
