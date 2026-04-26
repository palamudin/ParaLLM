from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import evals, jobs, storage
from runtime.engine import RuntimeErrorWithCode


class EvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "data" / "evals" / "suites").mkdir(parents=True, exist_ok=True)
        (self.root / "data" / "evals" / "arms").mkdir(parents=True, exist_ok=True)
        (self.root / "data" / "evals" / "suites" / "suite-a.json").write_text(
            """
{
  "suiteId": "suite-a",
  "title": "Suite A",
  "description": "test",
  "judgeRubric": {},
  "cases": [
    {
      "caseId": "case-a",
      "title": "Case A",
      "objective": "Handle the incident.",
      "constraints": ["Be careful."]
    }
  ]
}
""".strip(),
            encoding="utf-8",
        )
        (self.root / "data" / "evals" / "arms" / "compare-mini-full.json").write_text(
            """
{
  "armId": "compare-mini-full",
  "title": "Compare Mini",
  "description": "test arm",
  "type": "steered",
  "runtime": {
    "executionMode": "live",
    "contextMode": "full",
    "directBaselineMode": "both",
    "provider": "openai",
    "model": "gpt-5-mini",
    "directProvider": "openai",
    "directModel": "gpt-5-mini",
    "summarizerProvider": "openai",
    "summarizerModel": "gpt-5-mini",
    "reasoningEffort": "medium",
    "budget": {"maxCostUsd": 10, "maxTotalTokens": 0, "maxOutputTokens": 0},
    "research": {"enabled": false, "externalWebAccess": true, "domains": []},
    "vetting": {"enabled": true},
    "preferredLoop": {"rounds": 1, "delayMs": 0}
  },
  "workers": [
    {"id": "A", "type": "proponent", "label": "Proponent", "role": "utility", "focus": "benefits", "temperature": "balanced", "model": "gpt-5-mini"}
  ]
}
""".strip(),
            encoding="utf-8",
        )
        (self.root / "data" / "evals" / "arms" / "direct-gpt54.json").write_text(
            """
{
  "armId": "direct-gpt54",
  "title": "Direct 5.4",
  "description": "direct arm",
  "type": "direct",
  "runtime": {
    "executionMode": "live",
    "provider": "openai",
    "model": "gpt-5.4",
    "directProvider": "openai",
    "directModel": "gpt-5.4",
    "summarizerProvider": "openai",
    "summarizerModel": "gpt-5.4",
    "reasoningEffort": "high",
    "budget": {"maxCostUsd": 10, "maxTotalTokens": 0, "maxOutputTokens": 0},
    "research": {"enabled": false, "externalWebAccess": true, "domains": []},
    "vetting": {"enabled": true},
    "preferredLoop": {"rounds": 1, "delayMs": 0}
  }
}
""".strip(),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_start_eval_run_redirects_to_front_eval_mode(self) -> None:
        with self.assertRaises(RuntimeErrorWithCode) as ctx:
            evals.start_eval_run({"suiteId": "suite-a", "armIds": ["arm-a"]}, self.root)

        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("Front mode to Eval", str(ctx.exception))

    def test_start_front_eval_run_builds_inline_run(self) -> None:
        payload = {
            "suiteId": "suite-a",
            "caseId": "case-a",
            "executionMode": "live",
            "provider": "openai",
            "model": "gpt-5-mini",
            "summarizerProvider": "openai",
            "summarizerModel": "gpt-5-mini",
            "engineVersion": "v2",
            "directProvider": "openai",
            "directModel": "gpt-5-mini",
            "contextMode": "full",
            "reasoningEffort": "medium",
            "loopRounds": 1,
            "maxCostUsd": 4,
            "workers": [
                {"id": "A", "type": "proponent", "label": "Proponent", "role": "utility", "focus": "benefits", "temperature": "balanced", "model": "gpt-5-mini"}
            ],
        }
        with mock.patch.object(evals, "launch_eval_runner") as launch_runner:
            result = evals.start_front_eval_run(payload, self.root)

        self.assertEqual(result["run"]["canvas"], "eval")
        self.assertEqual(result["run"]["suiteId"], "suite-a--case-a")
        self.assertEqual(result["run"]["replicates"], 1)
        self.assertTrue((self.root / "data" / "evals" / "runs" / result["runId"] / "run.json").is_file())
        launch_runner.assert_called_once()

    def test_start_front_judge_run_builds_composite_suite(self) -> None:
        payload = {
            "suiteIds": ["suite-a"],
            "armIds": ["compare-mini-full", "direct-gpt54"],
            "judgeModel": "gpt-5.4",
            "replicates": 1,
            "loopSweep": [1],
        }
        with mock.patch.object(evals, "launch_eval_runner") as launch_runner:
            result = evals.start_front_judge_run(payload, self.root)

        self.assertEqual(result["run"]["canvas"], "judge")
        self.assertEqual(result["run"]["judgeModel"], "gpt-5.4")
        self.assertTrue((self.root / "data" / "evals" / "runs" / result["runId"] / "run.json").is_file())
        launch_runner.assert_called_once()

    def test_start_front_live_run_creates_live_run_record(self) -> None:
        payload = {
            "objective": "Run the live scheduler through the main lane.",
            "provider": "openai",
            "model": "gpt-5-mini",
            "summarizerProvider": "openai",
            "summarizerModel": "gpt-5-mini",
            "engineVersion": "v2",
            "loopRounds": 2,
            "loopDelayMs": 0,
            "workers": [
                {"id": "A", "type": "proponent", "label": "Proponent", "role": "utility", "focus": "benefits", "temperature": "balanced", "model": "gpt-5-mini"}
            ],
        }
        with mock.patch("backend.app.jobs.launch_loop_job_runner") as launcher:
            result = evals.start_front_live_run(payload, self.root)

        self.assertEqual(result["run"]["canvas"], "live")
        self.assertTrue(str(result["runId"]).startswith("live-"))
        self.assertTrue((self.root / "data" / "evals" / "runs" / result["runId"] / "run.json").is_file())
        self.assertEqual(result["run"]["status"], "queued")
        self.assertEqual(result["run"]["summary"]["caseCount"], 1)
        stored_run = storage.read_eval_run(storage.project_paths(self.root), str(result["runId"]))
        self.assertEqual(stored_run["live"]["engineVersion"], "v2")
        launcher.assert_called_once()

    def test_sync_front_live_run_tracks_loop_completion(self) -> None:
        payload = {
            "objective": "Complete one live lane run.",
            "provider": "openai",
            "model": "gpt-5-mini",
            "summarizerProvider": "openai",
            "summarizerModel": "gpt-5-mini",
            "loopRounds": 1,
            "loopDelayMs": 0,
        }
        with mock.patch("backend.app.jobs.launch_loop_job_runner"):
            result = evals.start_front_live_run(payload, self.root)

        run_id = str(result["runId"])
        task_id = str(result["taskId"])
        loop_job_id = str(result["jobId"])
        runtime = jobs._runtime(self.root)

        with runtime.with_lock():
            state = runtime.read_state_unlocked()
            state["usage"] = {
                **storage.default_usage_state(),
                "totalTokens": 4321,
                "estimatedCostUsd": 0.123,
            }
            state["loop"] = {
                **storage.default_loop_state(),
                "status": "completed",
                "jobId": loop_job_id,
                "completedRounds": 1,
                "currentRound": 0,
                "lastMessage": "Completed 1 round(s).",
                "finishedAt": storage.utc_now(),
            }
            runtime.write_state_unlocked(state)
            job = runtime.read_job_unlocked(loop_job_id)
            runtime.write_job_unlocked(
                storage.default_job(
                    {
                        **(job or {}),
                        "jobId": loop_job_id,
                        "taskId": task_id,
                        "status": "completed",
                        "startedAt": storage.utc_now(),
                        "finishedAt": storage.utc_now(),
                        "usage": state["usage"],
                        "lastMessage": "Completed 1 round(s).",
                    }
                )
            )

        synced = evals.sync_front_live_run(run_id, self.root)
        self.assertIsInstance(synced, dict)
        self.assertEqual(synced["status"], "completed")
        self.assertEqual(int((synced.get("summary") or {}).get("totalTokens") or 0), 4321)
        self.assertAlmostEqual(float((synced.get("summary") or {}).get("estimatedCostUsd") or 0.0), 0.123, places=6)

    def test_sync_front_live_run_prefers_task_scoped_state(self) -> None:
        payload = {
            "objective": "Use task-scoped live state.",
            "provider": "openai",
            "model": "gpt-5-mini",
            "summarizerProvider": "openai",
            "summarizerModel": "gpt-5-mini",
            "loopRounds": 1,
            "loopDelayMs": 0,
        }
        with mock.patch("backend.app.jobs.launch_loop_job_runner"):
            result = evals.start_front_live_run(payload, self.root)

        run_id = str(result["runId"])
        task_id = str(result["taskId"])
        loop_job_id = str(result["jobId"])
        runtime = jobs._runtime(self.root)
        task = storage.read_task_snapshot(task_id, storage.project_paths(self.root))
        self.assertIsInstance(task, dict)

        with runtime.with_lock():
            runtime.initialize_task_state_unlocked(
                task,
                {
                    **storage.default_state(),
                    "activeTask": task,
                    "usage": {
                        **storage.default_usage_state(),
                        "totalTokens": 9876,
                        "estimatedCostUsd": 0.456,
                    },
                    "loop": {
                        **storage.default_loop_state(),
                        "status": "completed",
                        "jobId": loop_job_id,
                        "completedRounds": 1,
                        "lastMessage": "Scoped loop completed.",
                        "finishedAt": storage.utc_now(),
                    },
                },
            )
            global_state = runtime.read_state_unlocked()
            global_state["activeTask"] = None
            global_state["usage"] = {
                **storage.default_usage_state(),
                "totalTokens": 12,
                "estimatedCostUsd": 0.001,
            }
            global_state["loop"] = storage.default_loop_state()
            runtime.write_state_unlocked(global_state)
            job = runtime.read_job_unlocked(loop_job_id)
            runtime.write_job_unlocked(
                storage.default_job(
                    {
                        **(job or {}),
                        "jobId": loop_job_id,
                        "taskId": task_id,
                        "status": "completed",
                        "finishedAt": storage.utc_now(),
                        "usage": {
                            **storage.default_usage_state(),
                            "totalTokens": 111,
                            "estimatedCostUsd": 0.222,
                        },
                    }
                )
            )

        synced = evals.sync_front_live_run(run_id, self.root)
        self.assertIsInstance(synced, dict)
        self.assertEqual(synced["status"], "completed")
        self.assertEqual(int((synced.get("summary") or {}).get("totalTokens") or 0), 9876)
        self.assertAlmostEqual(float((synced.get("summary") or {}).get("estimatedCostUsd") or 0.0), 0.456, places=6)

    def test_start_front_live_run_can_queue_while_another_live_run_exists(self) -> None:
        payload = {
            "objective": "Queue a live run.",
            "provider": "openai",
            "model": "gpt-5-mini",
            "summarizerProvider": "openai",
            "summarizerModel": "gpt-5-mini",
            "loopRounds": 1,
            "loopDelayMs": 0,
        }
        with mock.patch("backend.app.jobs.launch_loop_job_runner"):
            first = evals.start_front_live_run(payload, self.root)
            second = evals.start_front_live_run({**payload, "objective": "Queue a second live run."}, self.root)

        self.assertNotEqual(str(first["taskId"]), str(second["taskId"]))
        self.assertNotEqual(str(first["runId"]), str(second["runId"]))


if __name__ == "__main__":
    unittest.main()
