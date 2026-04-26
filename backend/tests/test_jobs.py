from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import control, dispatch, jobs, queueing, storage
from backend.app.config import DeploymentTopology
from runtime.engine import RuntimeErrorWithCode, compile_engine_graph

from .test_queueing import FakeRedis


class LoopJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        control.create_task({"objective": "Exercise the Python loop control plane."}, self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_start_loop_queues_background_job(self) -> None:
        with mock.patch("backend.app.jobs.launch_loop_job_runner") as launcher:
            result = jobs.start_loop({"rounds": "2", "delayMs": "50"}, self.root)

        self.assertEqual(result["message"], "Background loop started.")
        self.assertEqual(result["rounds"], 2)
        self.assertEqual(result["delayMs"], 50)
        launcher.assert_called_once()

        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        self.assertEqual(state["loop"]["status"], "queued")
        self.assertEqual(state["loop"]["jobId"], result["jobId"])

        job = storage.read_json_file(paths.jobs / f"{result['jobId']}.json")
        self.assertIsInstance(job, dict)
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["rounds"], 2)

    def test_start_loop_single_baseline_clamps_rounds_and_worker_count(self) -> None:
        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        task = state["activeTask"]
        task["runtime"]["directBaselineMode"] = "single"
        paths.state.write_text(json.dumps(state, indent=2), encoding="utf-8")
        (paths.tasks / f"{task['taskId']}.json").write_text(json.dumps(task, indent=2), encoding="utf-8")
        (paths.task_states / f"{task['taskId']}.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        with mock.patch("backend.app.jobs.launch_loop_job_runner") as launcher:
            result = jobs.start_loop({"rounds": "4", "delayMs": "25"}, self.root)

        self.assertEqual(result["rounds"], 1)
        launcher.assert_called_once()
        job = storage.read_json_file(paths.jobs / f"{result['jobId']}.json")
        self.assertIsInstance(job, dict)
        self.assertEqual(job["rounds"], 1)
        self.assertEqual(job["workerCount"], 0)

    def test_cancel_loop_cancels_queued_job_before_start(self) -> None:
        with mock.patch("backend.app.jobs.launch_loop_job_runner"):
            queued = jobs.start_loop({"rounds": "2", "delayMs": "0"}, self.root)

        result = jobs.cancel_loop(self.root)
        self.assertEqual(result["message"], "Scheduler reset. Ready to go.")
        self.assertEqual(result["loopsCancelled"], 1)

        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        self.assertEqual(state["loop"]["status"], "idle")

        job = storage.read_json_file(paths.jobs / f"{queued['jobId']}.json")
        self.assertIsInstance(job, dict)
        self.assertEqual(job["status"], "cancelled")

    def test_manage_job_retry_creates_new_background_job(self) -> None:
        paths = storage.project_paths(self.root)
        task_id = storage.read_state_payload(paths)["activeTask"]["taskId"]
        interrupted_job_id = "job-test-interrupted"
        (paths.jobs / f"{interrupted_job_id}.json").write_text(
            json.dumps(
                storage.default_job(
                    {
                        "jobId": interrupted_job_id,
                        "taskId": task_id,
                        "status": "interrupted",
                        "rounds": 3,
                        "delayMs": 100,
                        "completedRounds": 1,
                        "results": [{"round": 1, "targets": []}],
                        "queuedAt": "2026-04-21T12:00:00+00:00",
                        "startedAt": "2026-04-21T12:00:01+00:00",
                        "finishedAt": "2026-04-21T12:00:02+00:00",
                        "lastHeartbeatAt": "2026-04-21T12:00:02+00:00",
                        "lastMessage": "Interrupted for QA.",
                    }
                ),
                indent=2,
            ),
            encoding="utf-8",
        )

        with mock.patch("backend.app.jobs.launch_loop_job_runner") as launcher:
            result = jobs.manage_loop_job({"jobId": interrupted_job_id, "action": "retry"}, self.root)

        self.assertEqual(result["message"], "Loop queued for retry.")
        launcher.assert_called_once()

        new_job = storage.read_json_file(paths.jobs / f"{result['jobId']}.json")
        self.assertIsInstance(new_job, dict)
        self.assertEqual(new_job["retryOfJobId"], interrupted_job_id)
        self.assertEqual(new_job["resumeFromRound"], 1)

    def test_launch_loop_job_runner_passes_topology_env_to_subprocess(self) -> None:
        topology = DeploymentTopology(
            profile="local-single-node",
            root=self.root,
            data_root=self.root / "data",
            auth_file=self.root / "Auth.txt",
            host="127.0.0.1",
            port=8787,
            runtime_host="127.0.0.1",
            runtime_port=8765,
            queue_backend="local_subprocess",
            metadata_backend="json_files",
            artifact_backend="filesystem",
            secret_backend="local_file",
            secret_file=None,
            runtime_execution_backend="embedded_engine_subprocess",
            database_url=None,
            redis_url=None,
            object_store_url=None,
            object_store_bucket=None,
            object_store_healthcheck_url=None,
            object_store_access_key=None,
            object_store_secret_key=None,
            object_store_region="us-east-1",
            runtime_service_url=None,
            secret_provider_url=None,
            secret_provider_healthcheck_url=None,
        )
        with (
            mock.patch("backend.app.jobs.deployment_topology", return_value=topology),
            mock.patch("backend.app.jobs.control.auth_file_path", return_value=self.root / "Auth.txt"),
            mock.patch("backend.app.jobs.subprocess.Popen") as popen,
        ):
            jobs.launch_loop_job_runner({"jobId": "job-test"}, self.root)

        popen.assert_called_once()
        _, kwargs = popen.call_args
        env = kwargs["env"]
        self.assertEqual(env["LOOP_ROOT"], str(self.root))
        self.assertEqual(env["LOOP_AUTH_FILE"], str(self.root / "Auth.txt"))
        self.assertEqual(env["LOOP_SECRET_BACKEND"], "local_file")
        self.assertEqual(env["LOOP_DEPLOYMENT_PROFILE"], "local-single-node")

    def test_update_loop_job_progress_sets_waiting_target_message(self) -> None:
        paths = storage.project_paths(self.root)
        task_id = storage.read_state_payload(paths)["activeTask"]["taskId"]
        job_id = "job-test-progress"
        (paths.jobs / f"{job_id}.json").write_text(
            json.dumps(
                storage.default_job(
                    {
                        "jobId": job_id,
                        "taskId": task_id,
                        "status": "running",
                        "rounds": 2,
                        "currentRound": 1,
                        "queuedAt": "2026-04-21T12:00:00+00:00",
                        "startedAt": "2026-04-21T12:00:01+00:00",
                        "lastHeartbeatAt": "2026-04-21T12:00:02+00:00",
                        "lastMessage": "Running round 1.",
                    }
                ),
                indent=2,
            ),
            encoding="utf-8",
        )
        state = storage.read_state_payload(paths)
        state["loop"] = {
            **storage.default_loop_state(),
            "status": "running",
            "jobId": job_id,
            "mode": "background",
            "totalRounds": 2,
            "currentRound": 1,
            "startedAt": "2026-04-21T12:00:01+00:00",
            "lastHeartbeatAt": "2026-04-21T12:00:02+00:00",
            "lastMessage": "Running round 1.",
        }
        paths.state.write_text(json.dumps(state, indent=2), encoding="utf-8")

        runtime = jobs._runtime(self.root)
        jobs.update_loop_job_progress(runtime, job_id, task_id, 1, 2, "B", waiting=True)

        updated_state = storage.read_state_payload(paths)
        self.assertEqual(updated_state["loop"]["status"], "running")
        self.assertEqual(updated_state["loop"]["currentRound"], 1)
        self.assertIn("Worker B", updated_state["loop"]["lastMessage"])
        self.assertIn("Waiting", updated_state["loop"]["lastMessage"])

        updated_job = storage.read_json_file(paths.jobs / f"{job_id}.json")
        self.assertIsInstance(updated_job, dict)
        self.assertEqual(updated_job["status"], "running")
        self.assertIn("Worker B", updated_job["lastMessage"])

    def test_start_loop_with_redis_queue_backend_claims_and_launches(self) -> None:
        fake = FakeRedis()
        env = {
            "LOOP_QUEUE_BACKEND": "redis",
            "LOOP_REDIS_URL": "redis://example/0",
        }
        with (
            mock.patch.dict("os.environ", env, clear=False),
            mock.patch("backend.app.queueing._redis_client", return_value=fake),
            mock.patch("backend.app.jobs.launch_loop_job_runner") as launcher,
        ):
            result = jobs.start_loop({"rounds": "2", "delayMs": "50"}, self.root)

        self.assertEqual(result["message"], "Background loop started.")
        launcher.assert_called_once()

        paths = storage.project_paths(self.root)
        task_id = storage.read_state_payload(paths)["activeTask"]["taskId"]
        topology = queueing.deployment_topology(self.root)
        self.assertEqual(fake.get(queueing._loop_active_key(topology, task_id)), result["jobId"])
        self.assertEqual(fake.lrange(queueing._loop_queue_key(topology, task_id), 0, -1), [])

    def test_cancel_loop_with_redis_queue_backend_clears_claim(self) -> None:
        fake = FakeRedis()
        env = {
            "LOOP_QUEUE_BACKEND": "redis",
            "LOOP_REDIS_URL": "redis://example/0",
        }
        with (
            mock.patch.dict("os.environ", env, clear=False),
            mock.patch("backend.app.queueing._redis_client", return_value=fake),
            mock.patch("backend.app.jobs.launch_loop_job_runner"),
        ):
            queued = jobs.start_loop({"rounds": "2", "delayMs": "0"}, self.root)
            result = jobs.cancel_loop(self.root)

        self.assertEqual(result["message"], "Scheduler reset. Ready to go.")
        paths = storage.project_paths(self.root)
        task_id = storage.read_state_payload(paths)["activeTask"]["taskId"]
        topology = queueing.deployment_topology(self.root)
        self.assertIsNone(fake.get(queueing._loop_active_key(topology, task_id)))
        self.assertEqual(fake.lrange(queueing._loop_queue_key(topology, task_id), 0, -1), [])

        job = storage.read_json_file(paths.jobs / f"{queued['jobId']}.json")
        self.assertIsInstance(job, dict)
        self.assertEqual(job["status"], "cancelled")

    def test_cancel_loop_resets_scheduler_globally(self) -> None:
        paths = storage.project_paths(self.root)
        runtime = jobs._runtime(self.root)
        primary_state = storage.read_state_payload(paths)
        primary_task = primary_state["activeTask"]
        with runtime.with_lock():
            runtime.initialize_task_state_unlocked(primary_task, primary_state)

        secondary_result = control.create_task({"objective": "Secondary scheduler lane."}, self.root, activate=False)
        secondary_task_id = str(secondary_result["taskId"])
        secondary_task = storage.read_task_snapshot(secondary_task_id, paths)
        self.assertIsInstance(secondary_task, dict)
        with runtime.with_lock():
            runtime.initialize_task_state_unlocked(secondary_task, {"activeTask": secondary_task})

        primary_loop_job = jobs.create_loop_job(runtime, primary_task, 2, 0, "background")
        secondary_loop_job = jobs.create_loop_job(
            runtime,
            secondary_task,
            1,
            0,
            "background",
            {"updateLoopState": False, "lastMessage": "Queued secondary loop."},
        )
        runtime.mutate_job(
            str(secondary_loop_job["jobId"]),
            lambda existing: storage.default_job(
                {
                    **(existing or {}),
                    "status": "running",
                    "startedAt": jobs.utc_now(),
                    "lastHeartbeatAt": jobs.utc_now(),
                    "lastMessage": "Running secondary loop.",
                }
            ),
        )
        with runtime.with_lock():
            with jobs._task_state_context(runtime, secondary_task_id):
                secondary_state = runtime.read_state_unlocked()
                secondary_state["loop"] = {
                    **storage.default_loop_state(),
                    "status": "running",
                    "jobId": secondary_loop_job["jobId"],
                    "mode": "background",
                    "totalRounds": 1,
                    "startedAt": jobs.utc_now(),
                    "lastHeartbeatAt": jobs.utc_now(),
                    "lastMessage": "Running secondary loop.",
                }
                runtime.write_state_unlocked(secondary_state)

        primary_target_job = dispatch.create_target_job(runtime, primary_task, "A", {"lastMessage": "Queued worker A."})
        secondary_target_job = dispatch.create_target_job(runtime, secondary_task, "B", {"lastMessage": "Queued worker B."})
        runtime.mutate_job(
            str(secondary_target_job["jobId"]),
            lambda existing: storage.default_job(
                {
                    **(existing or {}),
                    "status": "running",
                    "startedAt": jobs.utc_now(),
                    "lastHeartbeatAt": jobs.utc_now(),
                    "lastMessage": "Running worker B.",
                }
            ),
        )

        result = jobs.cancel_loop(self.root)

        self.assertEqual(result["message"], "Scheduler reset. Ready to go.")
        self.assertEqual(result["loopsCancelled"], 2)
        self.assertEqual(result["targetsCancelled"], 2)
        self.assertGreaterEqual(result["taskStatesReset"], 2)

        updated_global = storage.read_state_payload(paths)
        self.assertEqual(updated_global["loop"]["status"], "idle")

        updated_secondary = storage.read_task_state_payload(secondary_task_id, paths)
        self.assertIsInstance(updated_secondary, dict)
        self.assertEqual(updated_secondary["loop"]["status"], "idle")

        primary_loop = storage.read_json_file(paths.jobs / f"{primary_loop_job['jobId']}.json")
        secondary_loop = storage.read_json_file(paths.jobs / f"{secondary_loop_job['jobId']}.json")
        primary_target = storage.read_json_file(paths.jobs / f"{primary_target_job['jobId']}.json")
        secondary_target = storage.read_json_file(paths.jobs / f"{secondary_target_job['jobId']}.json")
        for job in (primary_loop, secondary_loop, primary_target, secondary_target):
            self.assertIsInstance(job, dict)
            self.assertEqual(job["status"], "cancelled")
            self.assertTrue(job["cancelRequested"])

    def test_cancel_loop_with_redis_clears_dispatch_ready_queue(self) -> None:
        fake = FakeRedis()
        env = {
            "LOOP_QUEUE_BACKEND": "redis",
            "LOOP_REDIS_URL": "redis://example/0",
        }
        runtime = jobs._runtime(self.root)
        state = storage.read_state_payload(storage.project_paths(self.root))
        task = state["activeTask"]
        loop_job = jobs.create_loop_job(runtime, task, 1, 0, "background")
        dispatch_job = dispatch.create_target_job(runtime, task, "A", {"lastMessage": "Queued worker A."})
        topology = queueing.deployment_topology(self.root)
        fake.set(queueing._loop_active_key(topology, str(task["taskId"])), str(loop_job["jobId"]))
        fake.rpush(queueing._dispatch_ready_key(topology), str(dispatch_job["jobId"]))

        with (
            mock.patch.dict("os.environ", env, clear=False),
            mock.patch("backend.app.queueing._redis_client", return_value=fake),
        ):
            result = jobs.cancel_loop(self.root)

        self.assertEqual(result["dispatchKeysCleared"], 1)
        self.assertIsNone(fake.get(queueing._loop_active_key(topology, str(task["taskId"]))))
        self.assertEqual(fake.lrange(queueing._dispatch_ready_key(topology), 0, -1), [])

    def test_execute_loop_job_fault_sets_explicit_error_state(self) -> None:
        runtime = jobs._runtime(self.root)
        state = storage.read_state_payload(storage.project_paths(self.root))
        task = state["activeTask"]
        job = jobs.create_loop_job(runtime, task, 2, 0, "background")

        env = {"LOOP_FAULT_POINTS": "loop.execute.before_target.commander"}
        with mock.patch.dict("os.environ", env, clear=False):
            with self.assertRaises(RuntimeErrorWithCode) as ctx:
                jobs.execute_loop_job(job["jobId"], self.root)

        self.assertIn("loop.execute.before_target.commander", str(ctx.exception))
        paths = storage.project_paths(self.root)
        updated_state = storage.read_state_payload(paths)
        self.assertEqual(updated_state["loop"]["status"], "error")
        self.assertIn("Loop error:", updated_state["loop"]["lastMessage"])
        self.assertIn("loop.execute.before_target.commander", updated_state["loop"]["lastMessage"])

        updated_job = storage.read_json_file(paths.jobs / f"{job['jobId']}.json")
        self.assertIsInstance(updated_job, dict)
        self.assertEqual(updated_job["status"], "error")
        self.assertIn("loop.execute.before_target.commander", str(updated_job.get("error")))

    def test_execute_loop_job_single_mode_only_runs_direct_baseline(self) -> None:
        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        task = state["activeTask"]
        task["runtime"]["directBaselineMode"] = "single"
        paths.state.write_text(json.dumps(state, indent=2), encoding="utf-8")
        (paths.tasks / f"{task['taskId']}.json").write_text(json.dumps(task, indent=2), encoding="utf-8")

        runtime = jobs._runtime(self.root)
        with runtime.with_lock():
            runtime.initialize_task_state_unlocked(task, state)
        job = jobs.create_loop_job(runtime, task, 4, 0, "background")
        seen_targets: list[str] = []

        def fake_run_target(_runtime, target, _task_id, _payload):
            seen_targets.append(str(target))
            return {"target": target, "output": f"{target} complete", "exitCode": 0}

        with mock.patch("backend.app.jobs.runtime_execution.run_target", side_effect=fake_run_target):
            result = jobs.execute_loop_job(job["jobId"], self.root)

        self.assertEqual(seen_targets, ["direct_baseline"])
        self.assertEqual(result["requestedRounds"], 1)
        self.assertEqual(result["completedRounds"], 1)
        updated_job = storage.read_json_file(paths.jobs / f"{job['jobId']}.json")
        self.assertIsInstance(updated_job, dict)
        self.assertEqual(updated_job["rounds"], 1)
        self.assertEqual(updated_job["workerCount"], 0)

    def test_execute_loop_job_both_mode_runs_parallel_direct_baseline(self) -> None:
        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        task = state["activeTask"]
        task["runtime"]["directBaselineMode"] = "both"
        paths.state.write_text(json.dumps(state, indent=2), encoding="utf-8")
        (paths.tasks / f"{task['taskId']}.json").write_text(json.dumps(task, indent=2), encoding="utf-8")

        runtime = jobs._runtime(self.root)
        with runtime.with_lock():
            runtime.initialize_task_state_unlocked(task, state)
        job = jobs.create_loop_job(runtime, task, 1, 0, "background")
        seen_targets: list[str] = []

        def fake_run_target(_runtime, target, _task_id, _payload):
            seen_targets.append(str(target))
            return {"target": target, "output": f"{target} complete", "exitCode": 0}

        with mock.patch("backend.app.jobs.runtime_execution.run_target", side_effect=fake_run_target):
            with mock.patch("backend.app.jobs._launch_answer_now_sidecar") as launch_answer_now:
                with mock.patch("backend.app.jobs._launch_direct_baseline_sidecar") as launch_direct_baseline:
                    launch_answer_now.return_value = {"jobId": "dispatch-answer-now", "target": "answer_now"}
                    launch_direct_baseline.return_value = {"jobId": "dispatch-direct-baseline", "target": "direct_baseline"}
                    result = jobs.execute_loop_job(job["jobId"], self.root)

        self.assertNotIn("direct_baseline", seen_targets)
        self.assertIn("commander", seen_targets)
        self.assertIn("commander_review", seen_targets)
        self.assertIn("summarizer", seen_targets)
        self.assertIn("A", seen_targets)
        self.assertIn("B", seen_targets)
        launch_answer_now.assert_called_once()
        launch_direct_baseline.assert_called_once()
        self.assertEqual(result["requestedRounds"], 1)
        self.assertTrue(result["results"])
        self.assertNotIn("parallelTargets", result["results"][0])

    def test_execute_loop_job_v2_live_compatible_plan_drives_round_sequence(self) -> None:
        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        task = state["activeTask"]
        task["runtime"]["engineVersion"] = "v2"
        task["runtime"]["engineGraph"]["nodes"]["workers"]["timeoutSeconds"] = 88
        task["runtime"]["engineGraph"]["nodes"]["review"]["timeoutSeconds"] = 144
        task["runtime"]["engineGraph"]["nodes"]["answerNow"]["timeoutSeconds"] = 77
        task["runtime"]["engineGraph"]["nodes"]["judge"]["timeoutSeconds"] = 155
        task["runtime"]["enginePlan"] = compile_engine_graph(
            task["runtime"]["engineGraph"],
            task=task,
            runtime_config=task["runtime"],
        )
        paths.state.write_text(json.dumps(state, indent=2), encoding="utf-8")
        (paths.tasks / f"{task['taskId']}.json").write_text(json.dumps(task, indent=2), encoding="utf-8")

        runtime = jobs._runtime(self.root)
        with runtime.with_lock():
            runtime.initialize_task_state_unlocked(task, state)
        job = jobs.create_loop_job(runtime, task, 1, 0, "background")
        seen_targets: list[str] = []
        seen_options: dict[str, dict[str, object]] = {}

        def fake_run_target(_runtime, target, _task_id, _payload):
            seen_targets.append(str(target))
            seen_options[str(target)] = dict(_payload or {})
            return {"target": target, "output": f"{target} complete", "exitCode": 0}

        with mock.patch("backend.app.jobs.runtime_execution.run_target", side_effect=fake_run_target):
            with mock.patch(
                "backend.app.dispatch.launch_dispatch_job_runner",
                side_effect=lambda job_payload, root_path: dispatch.execute_target_job_process(
                    str(job_payload.get("jobId") or ""),
                    root_path,
                ),
            ):
                with mock.patch("backend.app.jobs._launch_loop_post_target") as launch_post_target:
                    launch_post_target.return_value = {"jobId": "dispatch-arbiter", "target": "arbiter"}
                    result = jobs.execute_loop_job(job["jobId"], self.root)

        self.assertEqual(result["results"][0]["planSource"], "v2-plan")
        self.assertTrue(str(result["results"][0].get("batchId") or "").startswith("batch-"))
        self.assertIn("commander", seen_targets)
        self.assertIn("commander_review", seen_targets)
        self.assertIn("summarizer", seen_targets)
        self.assertIn("A", seen_targets)
        self.assertIn("B", seen_targets)
        self.assertNotIn("workers", seen_targets)
        self.assertIn("answer_now", seen_targets)
        launch_post_target.assert_called_once()
        self.assertEqual(int(seen_options["A"]["timeoutSeconds"]), 88)
        self.assertEqual(int(seen_options["B"]["timeoutSeconds"]), 88)
        self.assertEqual(int(seen_options["commander_review"]["timeoutSeconds"]), 144)
        self.assertEqual(int(seen_options["answer_now"]["timeoutSeconds"]), 77)
        self.assertEqual(int(launch_post_target.call_args.kwargs["timeout_seconds_override"]), 155)
        self.assertEqual(result["results"][0]["postTargets"], ["arbiter"])


if __name__ == "__main__":
    unittest.main()
