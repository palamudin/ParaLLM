from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import control, metadata, storage
from runtime.engine import LoopRuntime


class FakePostgresStore:
    def __init__(self) -> None:
        self.state: dict[str, str] = {}
        self.jobs: dict[tuple[str, str], str] = {}
        self.tasks: dict[tuple[str, str], str] = {}
        self.eval_runs: dict[tuple[str, str], str] = {}


class FakeCursor:
    def __init__(self, store: FakePostgresStore) -> None:
        self.store = store
        self._rows: list[tuple[str]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, query: str, params=None) -> None:
        sql = " ".join(str(query).split()).lower()
        values = params or ()
        self._rows = []
        if sql.startswith("create table") or sql.startswith("create index"):
            return
        if "insert into parallm_state" in sql:
            project_key, payload = values[0], values[1]
            self.store.state[str(project_key)] = str(payload)
            return
        if "select payload::text from parallm_state" in sql:
            payload = self.store.state.get(str(values[0]))
            self._rows = [(payload,)] if payload is not None else []
            return
        if "insert into parallm_jobs" in sql:
            project_key, job_id, *_rest, payload = values
            self.store.jobs[(str(project_key), str(job_id))] = str(payload)
            return
        if "select payload::text from parallm_jobs where project_key = %s and job_id = %s" in sql:
            payload = self.store.jobs.get((str(values[0]), str(values[1])))
            self._rows = [(payload,)] if payload is not None else []
            return
        if "select payload::text from parallm_jobs" in sql:
            project_key = str(values[0])
            rows = []
            for (candidate_project, _job_id), payload in self.store.jobs.items():
                if candidate_project != project_key:
                    continue
                decoded = json.loads(payload)
                rows.append((str(decoded.get("queuedAt") or ""), str(decoded.get("jobId") or ""), payload))
            rows.sort(key=lambda item: (item[0], item[1]))
            self._rows = [(payload,) for _, _, payload in rows]
            return
        if "insert into parallm_tasks" in sql:
            project_key, task_id, payload = values
            self.store.tasks[(str(project_key), str(task_id))] = str(payload)
            return
        if "select payload::text from parallm_tasks" in sql:
            payload = self.store.tasks.get((str(values[0]), str(values[1])))
            self._rows = [(payload,)] if payload is not None else []
            return
        if "insert into parallm_eval_runs" in sql:
            project_key, run_id, *_rest, payload = values
            self.store.eval_runs[(str(project_key), str(run_id))] = str(payload)
            return
        if "select payload::text from parallm_eval_runs where project_key = %s and run_id = %s" in sql:
            payload = self.store.eval_runs.get((str(values[0]), str(values[1])))
            self._rows = [(payload,)] if payload is not None else []
            return
        if "select payload::text from parallm_eval_runs" in sql:
            project_key = str(values[0])
            rows = []
            for (candidate_project, _run_id), payload in self.store.eval_runs.items():
                if candidate_project != project_key:
                    continue
                decoded = json.loads(payload)
                rows.append((str(decoded.get("updatedAt") or decoded.get("createdAt") or ""), str(decoded.get("runId") or ""), payload))
            rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
            self._rows = [(payload,) for _, _, payload in rows]
            return
        raise AssertionError(f"Unhandled SQL in fake postgres cursor: {query}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConnection:
    def __init__(self, store: FakePostgresStore) -> None:
        self.store = store

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.store)


class PostgresMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = FakePostgresStore()
        self.env = {
            "LOOP_METADATA_BACKEND": "postgres",
            "LOOP_DATABASE_URL": f"postgresql://fake/{self.root.name}",
        }

    def tearDown(self) -> None:
        metadata._SCHEMA_READY.clear()
        self._tmp.cleanup()

    def _connect_patch(self):
        return mock.patch("backend.app.metadata.psycopg.connect", side_effect=lambda *args, **kwargs: FakeConnection(self.store))

    def test_runtime_and_storage_share_postgres_state_jobs_and_tasks(self) -> None:
        runtime = LoopRuntime(self.root)
        state = storage.default_state()
        state["activeTask"] = {"taskId": "t-postgres", "objective": "Shared metadata state."}
        job = storage.default_job(
            {
                "jobId": "job-postgres",
                "taskId": "t-postgres",
                "status": "queued",
                "jobType": "loop",
                "queuedAt": "2026-04-21T12:00:00+00:00",
            }
        )
        task = {"taskId": "t-postgres", "objective": "Persist the task snapshot."}

        with mock.patch.dict("os.environ", self.env, clear=False), self._connect_patch():
            with runtime.with_lock():
                runtime.write_state_unlocked(state)
                runtime.write_job_unlocked(job)
                runtime.write_task_snapshot_unlocked(task)

            paths = storage.project_paths(self.root)
            persisted_state = storage.read_state_payload(paths)
            persisted_jobs = storage.read_jobs(paths)
            persisted_task = storage.read_task_snapshot("t-postgres", paths)

        self.assertEqual(persisted_state["activeTask"]["taskId"], "t-postgres")
        self.assertEqual(len(persisted_jobs), 1)
        self.assertEqual(persisted_jobs[0]["jobId"], "job-postgres")
        self.assertEqual(persisted_task["objective"], "Persist the task snapshot.")
        self.assertFalse((storage.project_paths(self.root).tasks / "t-postgres.json").exists())

    def test_create_task_persists_snapshot_without_task_file_under_postgres(self) -> None:
        with mock.patch.dict("os.environ", self.env, clear=False), self._connect_patch():
            result = control.create_task({"objective": "Postgres-backed task creation."}, self.root)
            paths = storage.project_paths(self.root)
            task = storage.read_task_snapshot(result["taskId"], paths)

        self.assertIsNotNone(task)
        self.assertEqual(task["objective"], "Postgres-backed task creation.")
        self.assertFalse((paths.tasks / f"{result['taskId']}.json").exists())

    def test_eval_runs_persist_in_postgres_without_run_manifest_file(self) -> None:
        run = {
            "runId": "eval-123",
            "suiteId": "suite-a",
            "status": "queued",
            "createdAt": "2026-04-21T12:00:00+00:00",
            "updatedAt": "2026-04-21T12:00:00+00:00",
            "artifactIndex": {},
            "cases": [],
        }

        with mock.patch.dict("os.environ", self.env, clear=False), self._connect_patch():
            metadata.write_eval_run_payload(self.root, run)
            persisted = metadata.read_eval_run_payload(self.root, "eval-123")
            listed = metadata.read_all_eval_run_payloads(self.root)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["suiteId"], "suite-a")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["runId"], "eval-123")
        self.assertFalse((storage.project_paths(self.root).eval_runs / "eval-123" / "run.json").exists())


if __name__ == "__main__":
    unittest.main()
