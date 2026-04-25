from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import control, jobs, queueing, storage
from backend.app.config import DeploymentTopology
from runtime.engine import RuntimeErrorWithCode

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
        self.assertEqual(result["message"], "Queued loop cancelled before start.")

        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        self.assertEqual(state["loop"]["status"], "cancelled")

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

        self.assertEqual(result["message"], "Queued loop cancelled before start.")
        paths = storage.project_paths(self.root)
        task_id = storage.read_state_payload(paths)["activeTask"]["taskId"]
        topology = queueing.deployment_topology(self.root)
        self.assertIsNone(fake.get(queueing._loop_active_key(topology, task_id)))
        self.assertEqual(fake.lrange(queueing._loop_queue_key(topology, task_id), 0, -1), [])

        job = storage.read_json_file(paths.jobs / f"{queued['jobId']}.json")
        self.assertIsInstance(job, dict)
        self.assertEqual(job["status"], "cancelled")

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


if __name__ == "__main__":
    unittest.main()
