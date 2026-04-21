from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import control, jobs, queueing, storage

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


if __name__ == "__main__":
    unittest.main()
