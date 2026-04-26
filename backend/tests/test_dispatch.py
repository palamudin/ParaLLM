from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import control, dispatch, queueing, storage
from runtime.engine import RuntimeErrorWithCode, compile_engine_graph

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
        active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
        task_id = str((active_task or {}).get("taskId") or "").strip()
        if task_id:
            task_state_path = paths.task_states / f"{task_id}.json"
            task_state_path.parent.mkdir(parents=True, exist_ok=True)
            task_state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

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

    def test_arbiter_preflight_uses_existing_score_without_crashing(self) -> None:
        state = self._read_state()
        state["summary"] = {
            "round": 1,
            "mergedAt": "2026-04-24T00:00:00+00:00",
            "frontAnswer": {"answer": "Pressurized answer."},
        }
        state["directBaseline"] = {
            "capturedAt": "2026-04-24T00:00:01+00:00",
            "answer": {"answer": "Baseline answer."},
        }
        fingerprint = dispatch.arbiter.current_answer_fingerprint(state["activeTask"], state["summary"], state["directBaseline"])
        state["arbiter"] = {"fingerprint": fingerprint}

        result = dispatch.target_dispatch_preflight("arbiter", state)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["code"], 409)
        self.assertIn("already scored", result["message"])

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

    def test_create_round_dispatch_jobs_v2_supported_includes_answer_now_sidecar(self) -> None:
        state = self._read_state()
        task = state["activeTask"]
        task["runtime"]["engineVersion"] = "v2"
        self._write_state(state)

        runtime = dispatch._runtime(self.root)
        batch = dispatch.create_round_dispatch_jobs(runtime, task, {"roundNumber": 1})

        self.assertEqual(batch["planSource"], "v2-plan")
        self.assertEqual(len(batch["jobs"]), 6)
        self.assertEqual(len(batch["sidecars"]), 1)
        answer_now = batch["sidecars"][0]
        self.assertEqual(answer_now["target"], "answer_now")
        self.assertTrue(answer_now["partialSummary"])
        self.assertEqual(answer_now["dependencyJobIds"], [batch["commanderReview"]["jobId"]])
        self.assertEqual(batch["summarizer"]["dependencyJobIds"], [batch["commanderReview"]["jobId"]])

    def test_create_round_dispatch_jobs_v2_supported_uses_work_item_timeout_overrides(self) -> None:
        state = self._read_state()
        task = state["activeTask"]
        task["runtime"]["engineVersion"] = "v2"
        graph = task["runtime"]["engineGraph"]
        graph["nodes"]["workers"]["timeoutSeconds"] = 91
        graph["nodes"]["answerNow"]["timeoutSeconds"] = 73
        graph["nodes"]["final"]["timeoutSeconds"] = 141
        task["runtime"]["enginePlan"] = compile_engine_graph(
            graph,
            task=task,
            runtime_config=task["runtime"],
        )
        self._write_state(state)

        runtime = dispatch._runtime(self.root)
        batch = dispatch.create_round_dispatch_jobs(runtime, task, {"roundNumber": 1})

        self.assertTrue(batch["workers"])
        self.assertTrue(all(int(job["timeoutSeconds"]) == 91 for job in batch["workers"]))
        self.assertEqual(int(batch["sidecars"][0]["timeoutSeconds"]), 73)
        self.assertEqual(int(batch["summarizer"]["timeoutSeconds"]), 141)

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

    def test_execute_target_job_process_drops_late_completion_after_cancel(self) -> None:
        runtime = dispatch._runtime(self.root)
        state = self._read_state()
        task = state["activeTask"]
        job = dispatch.create_target_job(runtime, task, "commander", {})

        def fake_run_target(_runtime, _target, _task_id, _options):
            runtime.mutate_job(
                str(job["jobId"]),
                lambda existing: storage.default_job(
                    {
                        **(existing or {}),
                        "status": "cancelled",
                        "cancelRequested": True,
                        "lastHeartbeatAt": dispatch.utc_now(),
                        "lastMessage": "Cancelled externally.",
                    }
                ),
            )
            return {"target": "commander", "output": "late completion", "exitCode": 0}

        with mock.patch("backend.app.runtime_execution.run_target", side_effect=fake_run_target):
            result = dispatch.execute_target_job_process(job["jobId"], self.root)

        self.assertTrue(result["cancelled"])
        recorded = storage.read_json_file(storage.project_paths(self.root).jobs / f"{job['jobId']}.json")
        self.assertIsInstance(recorded, dict)
        self.assertEqual(recorded["status"], "cancelled")
        self.assertTrue(recorded["cancelRequested"])

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

    def test_promote_ready_dispatch_jobs_waits_on_provider_key_capacity(self) -> None:
        runtime = dispatch._runtime(self.root)
        state = self._read_state()
        task = state["activeTask"]
        dispatch.create_target_job(runtime, task, "A", {"lastMessage": "Queued worker A."})
        dispatch.create_target_job(runtime, task, "B", {"lastMessage": "Queued worker B."})

        def fake_auth_state(provider: str) -> dict[str, object]:
            if str(provider).lower() == "openai":
                return {"keys": ["sk-openai-1"]}
            return {"keys": []}

        with (
            mock.patch.object(dispatch.LoopRuntime, "load_api_key_pool_state", side_effect=fake_auth_state),
            mock.patch("backend.app.dispatch.launch_dispatch_job_runner") as launcher,
        ):
            launched = dispatch.promote_ready_dispatch_jobs(runtime)

        self.assertEqual(len(launched), 1)
        launcher.assert_called_once()

        jobs = {str(job["jobId"]): job for job in storage.read_jobs(storage.project_paths(self.root))}
        statuses = {str(job["status"]) for job in jobs.values()}
        self.assertIn("running", statuses)
        self.assertIn("queued", statuses)
        waiting_job = next(job for job in jobs.values() if str(job["status"]) == "queued")
        self.assertEqual(waiting_job["metadata"]["schedulerState"], "waiting_on_key")
        self.assertIn("key capacity", str(waiting_job.get("lastMessage") or "").lower())

        history = storage.build_history_payload(storage.project_paths(self.root))
        recorded = next(entry for entry in history["jobs"] if entry["jobId"] == waiting_job["jobId"])
        self.assertEqual(recorded["executionHealth"]["label"], "Key wait")

        running_job = next(job for job in jobs.values() if str(job["status"]) == "running")
        runtime.mutate_job(
            str(running_job["jobId"]),
            lambda existing: storage.default_job(
                {
                    **(existing or {}),
                    "status": "completed",
                    "finishedAt": dispatch.utc_now(),
                    "lastHeartbeatAt": dispatch.utc_now(),
                    "lastMessage": "Completed worker dispatch.",
                }
            ),
        )

        with (
            mock.patch.object(dispatch.LoopRuntime, "load_api_key_pool_state", side_effect=fake_auth_state),
            mock.patch("backend.app.dispatch.launch_dispatch_job_runner") as launcher,
        ):
            launched_second = dispatch.promote_ready_dispatch_jobs(runtime)

        self.assertEqual(len(launched_second), 1)
        launcher.assert_called_once()
        jobs_after = {str(job["jobId"]): job for job in storage.read_jobs(storage.project_paths(self.root))}
        self.assertEqual(jobs_after[str(waiting_job["jobId"])]["status"], "running")

    def test_promote_ready_dispatch_jobs_launches_multiple_providers_in_parallel(self) -> None:
        other_root_dir = tempfile.TemporaryDirectory()
        try:
            other_root = Path(other_root_dir.name)
            control.create_task(
                {
                    "objective": "Exercise mixed-provider scheduler dispatch.",
                    "provider": "ollama",
                    "model": "qwen3.5:9b",
                    "summarizerProvider": "openai",
                    "summarizerModel": "gpt-5-mini",
                },
                other_root,
            )
            runtime = dispatch._runtime(other_root)
            state = storage.read_state_payload(storage.project_paths(other_root))
            task = state["activeTask"]
            commander_job = dispatch.create_target_job(runtime, task, "commander", {"lastMessage": "Queued commander."})
            worker_job = dispatch.create_target_job(runtime, task, "A", {"lastMessage": "Queued worker A."})

            def fake_auth_state(provider: str) -> dict[str, object]:
                if str(provider).lower() == "openai":
                    return {"keys": ["sk-openai-1"]}
                return {"keys": []}

            with (
                mock.patch.object(dispatch.LoopRuntime, "load_api_key_pool_state", side_effect=fake_auth_state),
                mock.patch("backend.app.dispatch.launch_dispatch_job_runner") as launcher,
            ):
                launched = dispatch.promote_ready_dispatch_jobs(runtime)

            self.assertEqual(len(launched), 2)
            self.assertEqual(launcher.call_count, 2)
            jobs = {str(job["jobId"]): job for job in storage.read_jobs(storage.project_paths(other_root))}
            self.assertEqual(jobs[str(commander_job["jobId"])]["status"], "running")
            self.assertEqual(jobs[str(worker_job["jobId"])]["status"], "running")
        finally:
            other_root_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
