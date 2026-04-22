from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import control, dispatch, queueing, storage
from runtime.engine import RuntimeErrorWithCode

from .test_queueing import FakeRedis


class DispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        control.create_task({"objective": "Exercise the Python dispatch control plane."}, self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _read_state(self) -> dict[str, object]:
        return storage.read_state_payload(storage.project_paths(self.root))

    def _write_state(self, state: dict[str, object]) -> None:
        paths = storage.project_paths(self.root)
        paths.state.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def test_run_round_queues_dependency_batch_and_launches_commander(self) -> None:
        with mock.patch("backend.app.dispatch.launch_dispatch_job_runner") as launcher:
            result = dispatch.run_round({}, self.root)

        self.assertEqual(result["message"], "Round dispatch queued.")
        self.assertTrue(str(result["batchId"]).startswith("batch-"))
        launcher.assert_called_once()

        paths = storage.project_paths(self.root)
        jobs = storage.read_jobs(paths)
        self.assertEqual(len(jobs), 5)

        commander = next(job for job in jobs if job["target"] == "commander")
        workers = [job for job in jobs if str(job["target"]).isalpha() and len(str(job["target"])) == 1]
        commander_review = next(job for job in jobs if job["target"] == "commander_review")
        summarizer = next(job for job in jobs if job["target"] == "summarizer")

        self.assertEqual(len(workers), 2)
        self.assertEqual(launcher.call_args[0][0]["jobId"], commander["jobId"])
        self.assertEqual(commander["dependencyJobIds"], [])
        self.assertTrue(all(job["dependencyJobIds"] == [commander["jobId"]] for job in workers))
        worker_job_ids_by_target = {str(job["target"]): str(job["jobId"]) for job in workers}
        self.assertEqual(
            sorted(commander_review["dependencyJobIds"]),
            sorted(worker_job_ids_by_target.values()),
        )
        self.assertEqual(summarizer["dependencyJobIds"], [commander_review["jobId"]])
        self.assertEqual(
            result["jobIds"],
            [
                commander["jobId"],
                worker_job_ids_by_target["A"],
                worker_job_ids_by_target["B"],
                commander_review["jobId"],
                summarizer["jobId"],
            ],
        )

    def test_start_target_job_requires_commander_before_answer_now(self) -> None:
        with self.assertRaises(RuntimeErrorWithCode) as ctx:
            dispatch.start_target_job({"target": "answer_now"}, self.root)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("commander draft", str(ctx.exception))

    def test_start_target_job_queues_partial_answer_after_commander(self) -> None:
        state = self._read_state()
        state["commander"] = {"round": 1, "answer": "Lead draft present."}
        self._write_state(state)

        with mock.patch("backend.app.dispatch.launch_dispatch_job_runner") as launcher:
            result = dispatch.start_target_job({"target": "answer_now"}, self.root)

        self.assertEqual(result["message"], "Partial answer queued.")
        self.assertTrue(result["partialSummary"])
        launcher.assert_called_once()

        job = storage.read_json_file(storage.project_paths(self.root).jobs / f"{result['jobId']}.json")
        self.assertIsInstance(job, dict)
        self.assertEqual(job["target"], "answer_now")
        self.assertTrue(job["partialSummary"])
        self.assertEqual(job["status"], "running")

    def test_run_target_sync_uses_runtime_path(self) -> None:
        with mock.patch.object(
            dispatch.LoopRuntime,
            "run_target",
            return_value={"output": "Commander completed.", "backend": "python", "exitCode": 0},
        ) as run_target:
            result = dispatch.run_target_sync({"target": "commander"}, self.root)

        self.assertEqual(result["message"], "Executed commander")
        self.assertEqual(result["target"], "commander")
        self.assertEqual(result["output"], "Commander completed.")
        self.assertEqual(result["backend"], "python")
        run_target.assert_called_once()

    def test_run_round_with_redis_ready_queue_launches_commander(self) -> None:
        fake = FakeRedis()
        env = {
            "LOOP_QUEUE_BACKEND": "redis",
            "LOOP_REDIS_URL": "redis://example/0",
        }
        with (
            mock.patch.dict("os.environ", env, clear=False),
            mock.patch("backend.app.queueing._redis_client", return_value=fake),
            mock.patch("backend.app.dispatch.launch_dispatch_job_runner") as launcher,
        ):
            result = dispatch.run_round({}, self.root)

        self.assertEqual(result["message"], "Round dispatch queued.")
        launcher.assert_called_once()
        topology = queueing.deployment_topology(self.root)
        self.assertEqual(fake.lrange(queueing._dispatch_ready_key(topology), 0, -1), [])

    def test_execute_target_job_fault_interrupts_dependent_jobs(self) -> None:
        runtime = dispatch._runtime(self.root)
        state = self._read_state()
        task = state["activeTask"]
        batch = dispatch.create_round_dispatch_jobs(runtime, task, {"roundNumber": 1})

        env = {"LOOP_FAULT_POINTS": "dispatch.execute.before_runtime.commander"}
        with mock.patch.dict("os.environ", env, clear=False):
            with self.assertRaises(RuntimeErrorWithCode) as ctx:
                dispatch.execute_target_job_process(batch["commander"]["jobId"], self.root)

        self.assertIn("dispatch.execute.before_runtime.commander", str(ctx.exception))
        jobs_by_id = {
            str(job["jobId"]): job
            for job in storage.read_jobs(storage.project_paths(self.root))
        }
        self.assertEqual(jobs_by_id[batch["commander"]["jobId"]]["status"], "error")
        self.assertEqual(jobs_by_id[batch["workers"][0]["jobId"]]["status"], "interrupted")
        self.assertEqual(jobs_by_id[batch["workers"][1]["jobId"]]["status"], "interrupted")
        self.assertEqual(jobs_by_id[batch["commanderReview"]["jobId"]]["status"], "interrupted")
        self.assertEqual(jobs_by_id[batch["summarizer"]["jobId"]]["status"], "interrupted")

    def test_execute_target_job_provider_error_gets_explicit_failure_class(self) -> None:
        runtime = dispatch._runtime(self.root)
        state = self._read_state()
        task = state["activeTask"]
        job = dispatch.create_target_job(runtime, task, "commander", {})

        with mock.patch(
            "backend.app.runtime_execution.run_target",
            side_effect=RuntimeErrorWithCode("OpenAI API request failed: HTTP 500 | server_error", 500),
        ):
            with self.assertRaises(RuntimeErrorWithCode):
                dispatch.execute_target_job_process(job["jobId"], self.root)

        history = storage.build_history_payload(storage.project_paths(self.root))
        recorded = next(entry for entry in history["jobs"] if entry["jobId"] == job["jobId"])
        self.assertEqual(recorded["status"], "error")
        self.assertEqual(recorded["executionHealth"]["label"], "Provider")
        self.assertIn("server-side error", recorded["executionHealth"]["summary"].lower())

    def test_execute_target_job_output_exhaustion_gets_explicit_failure_class(self) -> None:
        runtime = dispatch._runtime(self.root)
        state = self._read_state()
        task = state["activeTask"]
        job = dispatch.create_target_job(runtime, task, "commander", {})

        with mock.patch(
            "backend.app.runtime_execution.run_target",
            side_effect=RuntimeErrorWithCode("OpenAI Responses API output remained incomplete after attempts [2800, 5600]", 500),
        ):
            with self.assertRaises(RuntimeErrorWithCode):
                dispatch.execute_target_job_process(job["jobId"], self.root)

        history = storage.build_history_payload(storage.project_paths(self.root))
        recorded = next(entry for entry in history["jobs"] if entry["jobId"] == job["jobId"])
        self.assertEqual(recorded["status"], "error")
        self.assertEqual(recorded["executionHealth"]["label"], "Output cap")
        self.assertIn("output-token", recorded["executionHealth"]["summary"].lower())

    def test_answer_now_records_failed_lane_dependencies_in_partial_job(self) -> None:
        state = self._read_state()
        state["commander"] = {"round": 1, "answer": "Lead draft present."}
        self._write_state(state)
        paths = storage.project_paths(self.root)
        (paths.jobs / "dispatch-worker-a.json").write_text(
            json.dumps(
                storage.default_job(
                    {
                        "jobId": "dispatch-worker-a",
                        "taskId": state["activeTask"]["taskId"],
                        "jobType": "target",
                        "target": "A",
                        "status": "error",
                        "error": "OpenAI API request failed: HTTP 500 | server_error",
                        "metadata": {
                            "failureClass": "provider_error",
                            "operatorNote": "OpenAI API request failed: HTTP 500 | server_error",
                        },
                    }
                ),
                indent=2,
            ),
            encoding="utf-8",
        )

        with mock.patch("backend.app.dispatch.launch_dispatch_job_runner"):
            result = dispatch.start_target_job({"target": "answer_now"}, self.root)

        history = storage.build_history_payload(paths)
        recorded = next(entry for entry in history["jobs"] if entry["jobId"] == result["jobId"])
        self.assertTrue(recorded["partialSummary"])
        self.assertEqual(recorded["executionHealth"]["label"], "Partial-risk")
        self.assertIn("failed lanes remain unresolved", recorded["executionHealth"]["summary"].lower())


if __name__ == "__main__":
    unittest.main()
