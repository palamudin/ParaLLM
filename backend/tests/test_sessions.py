from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import control, sessions, storage
from backend.tests.test_artifacts import FakeObjectStore
from runtime.engine import RuntimeErrorWithCode


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        control.create_task({"objective": "Exercise session mutation paths."}, self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_reset_session_archives_and_loads_carry_forward_draft(self) -> None:
        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        state["summary"] = {
            "round": 1,
            "frontAnswer": {"answer": "Ship a bounded pilot."},
            "summarizerOpinion": {"stance": "Proceed conditionally with guardrails."},
            "recommendedNextAction": "Define the pilot boundary.",
        }
        state["usage"]["totalTokens"] = 321
        state["usage"]["estimatedCostUsd"] = 0.1234
        paths.state.write_text(json.dumps(state, indent=2), encoding="utf-8")

        result = sessions.reset_session(self.root)

        self.assertIn("Session reset", result["message"])
        self.assertTrue(result["archiveFile"])
        self.assertIn("Prior objective:", result["carryContext"])
        self.assertIn("Prior adjudicated answer:", result["carryContext"])
        self.assertEqual(result["draft"]["objective"], "")

        next_state = storage.read_state_payload(paths)
        self.assertIsNone(next_state["activeTask"])
        self.assertTrue((paths.sessions / result["archiveFile"]).is_file())

    def test_reset_state_restores_defaults(self) -> None:
        result = sessions.reset_state(self.root)
        self.assertEqual(result["message"], "State reset.")

        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertIsNone(state["activeTask"])
        self.assertEqual(state["loop"]["status"], "idle")

    def test_replay_session_restores_archived_state(self) -> None:
        reset = sessions.reset_session(self.root)
        result = sessions.replay_session({"archiveFile": reset["archiveFile"]}, self.root)

        self.assertEqual(result["message"], "Archived session replayed.")
        self.assertEqual(result["archiveFile"], reset["archiveFile"])

        state = storage.read_state_payload(storage.project_paths(self.root))
        self.assertIsNotNone(state["activeTask"])
        self.assertEqual(state["loop"]["status"], "idle")

    def test_reset_session_fault_before_archive_write_fails_loudly(self) -> None:
        with mock.patch.dict(os.environ, {"LOOP_FAULT_POINTS": "session.reset.before_archive_write"}, clear=False):
            with self.assertRaises(RuntimeErrorWithCode) as ctx:
                sessions.reset_session(self.root)

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("session.reset.before_archive_write", str(ctx.exception))

    def test_replay_session_fault_before_restore_fails_loudly(self) -> None:
        reset = sessions.reset_session(self.root)
        with mock.patch.dict(os.environ, {"LOOP_FAULT_POINTS": "session.replay.before_restore"}, clear=False):
            with self.assertRaises(RuntimeErrorWithCode) as ctx:
                sessions.replay_session({"archiveFile": reset["archiveFile"]}, self.root)

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("session.replay.before_restore", str(ctx.exception))

    def test_export_session_returns_jobs_and_artifacts_for_current_task(self) -> None:
        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        task_id = state["activeTask"]["taskId"]
        (paths.jobs / "job-test.json").write_text(
            json.dumps(
                storage.default_job(
                    {
                        "jobId": "job-test",
                        "taskId": task_id,
                        "status": "completed",
                        "queuedAt": "2026-04-21T12:00:00+00:00",
                        "finishedAt": "2026-04-21T12:00:05+00:00",
                    }
                ),
                indent=2,
            ),
            encoding="utf-8",
        )
        (paths.outputs / f"{task_id}_summary_round001_output.json").write_text(
            json.dumps(
                {
                    "taskId": task_id,
                    "artifactType": "summary_output",
                    "round": 1,
                    "responseMeta": {},
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        bundle = sessions.export_session(root=self.root)

        self.assertEqual(bundle["source"], "current")
        self.assertEqual(len(bundle["jobs"]), 1)
        self.assertEqual(len(bundle["artifacts"]), 1)
        self.assertTrue((paths.data / "exports" / bundle["bundleFile"]).is_file())

    def test_export_session_fault_before_bundle_write_fails_loudly(self) -> None:
        with mock.patch.dict(os.environ, {"LOOP_FAULT_POINTS": "session.export.before_bundle_write"}, clear=False):
            with self.assertRaises(RuntimeErrorWithCode) as ctx:
                sessions.export_session(root=self.root)

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("session.export.before_bundle_write", str(ctx.exception))

    def test_export_session_collects_contract_warnings_for_malformed_artifacts(self) -> None:
        paths = storage.project_paths(self.root)
        state = storage.read_state_payload(paths)
        task_id = state["activeTask"]["taskId"]
        (paths.outputs / f"{task_id}_summary_round001_output.json").write_text(
            json.dumps(
                {
                    "taskId": task_id,
                    "artifactType": "summary_output",
                    "round": "later",
                    "responseMeta": {
                        "requestedMaxOutputTokens": "wide",
                        "effectiveMaxOutputTokens": "wider",
                        "maxOutputTokenAttempts": ["900", "oops"],
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        bundle = sessions.export_session(root=self.root)

        self.assertTrue(bundle["contractWarnings"])
        self.assertTrue(any("artifact" in warning.lower() for warning in bundle["contractWarnings"]))

    def test_session_archive_and_export_bundle_roundtrip_through_object_storage(self) -> None:
        env = {
            "LOOP_ARTIFACT_BACKEND": "object_storage",
            "LOOP_OBJECT_STORE_URL": "http://object-store:9000",
            "LOOP_OBJECT_STORE_BUCKET": "parallm",
            "LOOP_OBJECT_STORE_ACCESS_KEY": "minioadmin",
            "LOOP_OBJECT_STORE_SECRET_KEY": "minioadmin",
        }
        store = FakeObjectStore()
        with mock.patch.dict("os.environ", env, clear=False), mock.patch("backend.app.artifacts._s3_client", return_value=store):
            reset = sessions.reset_session(self.root)
            bundle = sessions.export_session(archive_file=reset["archiveFile"], root=self.root)
            replay = sessions.replay_session({"archiveFile": reset["archiveFile"]}, self.root)
            archives = storage.list_session_archives(storage.project_paths(self.root))
            archive_path_exists = (storage.project_paths(self.root).sessions / reset["archiveFile"]).exists()

        self.assertEqual(bundle["source"], "archive")
        self.assertEqual(replay["message"], "Archived session replayed.")
        self.assertEqual(archives[0]["file"], reset["archiveFile"])
        self.assertFalse(archive_path_exists)


if __name__ == "__main__":
    unittest.main()
