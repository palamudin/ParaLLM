from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import storage


class StorageReadModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.paths = storage.project_paths(self.root)
        for directory in (
            self.paths.data,
            self.paths.tasks,
            self.paths.checkpoints,
            self.paths.outputs,
            self.paths.sessions,
            self.paths.jobs,
            self.paths.eval_suites,
            self.paths.eval_arms,
            self.paths.eval_runs,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_read_state_payload_defaults_to_idle(self) -> None:
        payload = storage.read_state_payload(self.paths)

        self.assertIsNone(payload["activeTask"])
        self.assertEqual(payload["loop"]["status"], "idle")
        self.assertEqual(payload["dispatch"]["status"], "idle")
        self.assertEqual(payload["dispatch"]["activeJobs"], [])

    def test_read_state_payload_enriches_active_task_runtime_mirrors(self) -> None:
        self.write_json(
            self.paths.state,
            {
                "activeTask": {
                    "taskId": "t-1",
                    "objective": "Stress test the runtime contract.",
                },
                "workers": {
                    "A": {"round": 1, "label": "Proponent"},
                },
                "commander": {
                    "round": 1,
                    "leadDraft": {"position": "Ship with guardrails."},
                },
                "commanderReview": {
                    "round": 1,
                    "courseDecision": "maintain",
                },
                "summary": {
                    "round": 1,
                    "frontAnswer": {"answer": "Proceed carefully."},
                },
            },
        )

        payload = storage.read_state_payload(self.paths)

        self.assertEqual(payload["activeTask"]["stateWorkers"]["A"]["label"], "Proponent")
        self.assertEqual(payload["activeTask"]["stateCommander"]["round"], 1)
        self.assertEqual(payload["activeTask"]["stateCommanderReview"]["courseDecision"], "maintain")
        self.assertEqual(payload["activeTask"]["summary"]["frontAnswer"]["answer"], "Proceed carefully.")
        self.assertNotIn("stateWorkers", self.read_json(self.paths.state)["activeTask"])

    def test_read_state_payload_surfaces_execution_health_from_recent_steps(self) -> None:
        self.write_json(
            self.paths.state,
            {
                "activeTask": {
                    "taskId": "t-health-1",
                    "objective": "Show degraded state clearly.",
                    "workers": [{"id": "A", "label": "Proponent"}],
                },
            },
        )
        self.paths.steps.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "ts": "2026-04-21T12:00:00+00:00",
                            "stage": "commander",
                            "message": "Commander drafted the lead answer for this round.",
                            "context": {
                                "taskId": "t-health-1",
                                "mode": "live",
                                "recoveredFromIncomplete": True,
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "ts": "2026-04-21T12:01:00+00:00",
                            "stage": "worker_A",
                            "message": "Live API call failed; falling back to mock.",
                            "context": {
                                "taskId": "t-health-1",
                                "workerId": "A",
                                "model": "gpt-5-mini",
                                "error": "OpenAI API request failed: HTTP 500",
                            },
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        payload = storage.read_state_payload(self.paths)

        self.assertTrue(payload["executionHealth"]["degraded"])
        self.assertEqual(payload["executionHealth"]["fallbackCount"], 1)
        self.assertEqual(payload["executionHealth"]["recoveredCount"], 1)
        self.assertEqual(payload["executionHealth"]["latestIssue"]["target"], "A")
        self.assertTrue(payload["activeTask"]["executionHealth"]["degraded"])
        self.assertTrue(payload["activeTask"]["executionHealth"]["targets"]["commander"]["recoveredFromIncomplete"])

    def test_read_state_payload_keeps_degraded_target_after_later_clean_step(self) -> None:
        self.write_json(
            self.paths.state,
            {
                "activeTask": {
                    "taskId": "t-health-sticky",
                    "objective": "Do not lose degraded lane state.",
                    "workers": [{"id": "A", "label": "Proponent"}],
                },
            },
        )
        self.paths.steps.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "ts": "2026-04-21T12:00:00+00:00",
                            "stage": "worker_A",
                            "message": "Live API call failed; falling back to mock.",
                            "context": {
                                "taskId": "t-health-sticky",
                                "workerId": "A",
                                "mode": "mock",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "ts": "2026-04-21T12:00:10+00:00",
                            "stage": "worker_A",
                            "message": "Worker A checkpoint saved.",
                            "context": {
                                "taskId": "t-health-sticky",
                                "workerId": "A",
                                "mode": "live",
                            },
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        payload = storage.read_state_payload(self.paths)

        self.assertTrue(payload["executionHealth"]["degraded"])
        self.assertEqual(payload["executionHealth"]["fallbackCount"], 1)
        self.assertEqual(payload["executionHealth"]["targets"]["A"]["status"], "degraded")
        self.assertTrue(payload["executionHealth"]["targets"]["A"]["usedMockFallback"])

    def test_read_state_payload_surfaces_telemetry_contract_warnings(self) -> None:
        self.write_json(
            self.paths.state,
            {
                "activeTask": {
                    "taskId": "t-health-telemetry",
                    "objective": "Surface malformed telemetry safely.",
                },
            },
        )
        self.paths.steps.write_text('{"ts":"2026-04-21T12:00:00+00:00","stage":"commander","context":{"taskId":"t-health-telemetry"}}\nnot-json\n["bad"]\n', encoding="utf-8")
        self.paths.events.write_text('{"ts":"2026-04-21T12:00:00+00:00","type":"task_started"}\nnull\n', encoding="utf-8")

        payload = storage.read_state_payload(self.paths)

        self.assertTrue(payload["contractWarnings"])
        joined = " ".join(payload["contractWarnings"])
        self.assertIn("steps.jsonl dropped 1 malformed JSONL line", joined)
        self.assertIn("steps.jsonl dropped 1 non-object telemetry entry", joined)
        self.assertIn("events.jsonl dropped 1 non-object telemetry entry", joined)
        self.assertEqual(payload["activeTask"]["contractWarnings"], payload["contractWarnings"])

    def test_read_state_payload_surfaces_contract_warnings_for_malformed_state(self) -> None:
        self.write_json(
            self.paths.state,
            {
                "activeTask": {"taskId": "t-state-contract", "objective": "Keep the shell stable."},
                "commander": ["bad"],
                "workers": {"A": {"label": "Proponent"}, "B": "bad"},
                "memoryVersion": "many",
                "loop": {
                    "status": "flying",
                    "totalRounds": "several",
                    "completedRounds": "half",
                    "delayMs": "slow",
                },
                "usage": "expensive",
            },
        )

        payload = storage.read_state_payload(self.paths)

        self.assertIsNone(payload["commander"])
        self.assertEqual(set(payload["workers"].keys()), {"A"})
        self.assertEqual(payload["memoryVersion"], 0)
        self.assertEqual(payload["loop"]["status"], "idle")
        self.assertEqual(payload["loop"]["delayMs"], 0)
        self.assertTrue(payload["contractWarnings"])
        self.assertEqual(payload["activeTask"]["contractWarnings"], payload["contractWarnings"])

    def test_project_paths_honors_loop_data_root_override(self) -> None:
        override = self.root / "shared-data"
        previous = os.environ.get("LOOP_DATA_ROOT")
        os.environ["LOOP_DATA_ROOT"] = str(override)
        try:
            paths = storage.project_paths(self.root)
        finally:
            if previous is None:
                os.environ.pop("LOOP_DATA_ROOT", None)
            else:
                os.environ["LOOP_DATA_ROOT"] = previous

        self.assertEqual(paths.data, override.resolve())
        self.assertEqual(paths.state, (override / "state.json").resolve())

    def test_build_history_payload_surfaces_artifacts_and_sessions(self) -> None:
        task_id = "t-20260421-120000-deadbe"
        self.write_json(
            self.paths.tasks / f"{task_id}.json",
            {
                "taskId": task_id,
                "objective": "Review the deployment plan.",
            },
        )
        self.write_json(
            self.paths.outputs / f"{task_id}_summary_round001_output.json",
            {
                "taskId": task_id,
                "artifactType": "summary_output",
                "target": "summarizer",
                "label": "Summarizer",
                "mode": "live",
                "model": "gpt-5-mini",
                "round": 1,
                "responseMeta": {
                    "requestedMaxOutputTokens": 1200,
                    "effectiveMaxOutputTokens": 2400,
                },
            },
        )
        self.write_json(
            self.paths.sessions / "session-1.json",
            {
                "createdAt": "2026-04-21T12:00:00+00:00",
                "taskId": task_id,
                "objective": "Review the deployment plan.",
                "summaryRound": 1,
                "carryContext": "Carry this forward.",
            },
        )

        payload = storage.build_history_payload(self.paths)

        self.assertTrue(payload["artifacts"])
        self.assertEqual(payload["artifacts"][0]["kind"], "summary_output")
        self.assertEqual(payload["artifacts"][0]["taskId"], task_id)
        self.assertEqual(payload["artifacts"][0]["effectiveMaxOutputTokens"], 2400)
        self.assertTrue(payload["sessions"])
        self.assertEqual(payload["sessions"][0]["taskId"], task_id)

    def test_build_history_payload_surfaces_top_level_contract_warnings(self) -> None:
        self.write_json(
            self.paths.state,
            {
                "activeTask": {
                    "taskId": "t-history-telemetry",
                    "objective": "Carry telemetry warnings into Review.",
                },
            },
        )
        self.paths.steps.write_text('{"ts":"2026-04-21T12:00:00+00:00","stage":"commander","context":{"taskId":"t-history-telemetry"}}\nnot-json\n', encoding="utf-8")

        payload = storage.build_history_payload(self.paths)

        self.assertTrue(payload["contractWarnings"])
        self.assertIn("steps.jsonl dropped 1 malformed JSONL line", payload["contractWarnings"][0])

    def test_build_history_payload_surfaces_session_contract_warnings(self) -> None:
        task_id = "t-20260421-120250-archive"
        self.write_json(
            self.paths.sessions / "session-bad.json",
            {
                "createdAt": "2026-04-21T12:00:00+00:00",
                "taskId": task_id,
                "objective": "Archive safely.",
                "summaryRound": "latest",
                "carryContext": "Carry this forward.",
            },
        )

        payload = storage.build_history_payload(self.paths)
        session = payload["sessions"][0]

        self.assertEqual(session["summaryRound"], 0)
        self.assertTrue(session["contractWarnings"])
        self.assertIn("invalid summaryRound", session["contractWarnings"][0])

    def test_build_history_payload_surfaces_round_execution_health(self) -> None:
        task_id = "t-20260421-120500-beaded"
        self.write_json(
            self.paths.tasks / f"{task_id}.json",
            {
                "taskId": task_id,
                "objective": "Make degraded rounds legible.",
            },
        )
        self.write_json(
            self.paths.outputs / f"{task_id}_A_step001_output.json",
            {
                "taskId": task_id,
                "artifactType": "worker_output",
                "workerId": "A",
                "label": "Proponent",
                "mode": "mock",
                "model": "gpt-5-mini",
                "step": 1,
                "responseMeta": {
                    "requestedMaxOutputTokens": 900,
                    "effectiveMaxOutputTokens": 900,
                },
            },
        )
        self.write_json(
            self.paths.outputs / f"{task_id}_summary_round001_output.json",
            {
                "taskId": task_id,
                "artifactType": "summary_output",
                "target": "summarizer",
                "label": "Summarizer",
                "mode": "live",
                "model": "gpt-5-mini",
                "round": 1,
                "responseMeta": {
                    "requestedMaxOutputTokens": 1200,
                    "effectiveMaxOutputTokens": 2400,
                    "recoveredFromIncomplete": True,
                },
            },
        )

        payload = storage.build_history_payload(self.paths)
        round_entry = payload["rounds"][0]

        self.assertTrue(round_entry["executionHealth"]["degraded"])
        self.assertEqual(round_entry["executionHealth"]["fallbackCount"], 1)
        self.assertEqual(round_entry["executionHealth"]["recoveredCount"], 1)
        self.assertEqual(round_entry["executionHealth"]["issueCount"], 2)
        self.assertEqual(round_entry["executionHealth"]["targets"]["A"]["status"], "degraded")

    def test_build_history_payload_surfaces_job_execution_health(self) -> None:
        task_id = "t-20260421-121000-jobsafe"
        self.write_json(
            self.paths.tasks / f"{task_id}.json",
            {
                "taskId": task_id,
                "objective": "Show job health at a glance.",
            },
        )
        self.write_json(
            self.paths.jobs / "job-loop.json",
            {
                "jobId": "job-loop",
                "taskId": task_id,
                "jobType": "loop",
                "status": "interrupted",
                "rounds": 2,
                "completedRounds": 1,
                "queuedAt": "2026-04-21T12:00:00+00:00",
                "startedAt": "2026-04-21T12:01:00+00:00",
                "finishedAt": "2026-04-21T12:02:00+00:00",
                "lastMessage": "Recovered a stale running background loop. It can be retried.",
                "error": "Recovered a stale running background loop. It can be retried.",
            },
        )
        self.write_json(
            self.paths.jobs / "job-target.json",
            {
                "jobId": "job-target",
                "taskId": task_id,
                "jobType": "target",
                "target": "answer_now",
                "status": "completed",
                "mode": "live",
                "partialSummary": True,
                "queuedAt": "2026-04-21T12:03:00+00:00",
                "startedAt": "2026-04-21T12:03:01+00:00",
                "finishedAt": "2026-04-21T12:03:30+00:00",
                "lastMessage": "Partial answer generated from current checkpoints.",
            },
        )

        payload = storage.build_history_payload(self.paths)
        jobs = {entry["jobId"]: entry for entry in payload["jobs"]}

        self.assertEqual(jobs["job-loop"]["executionHealth"]["tone"], "error")
        self.assertTrue(jobs["job-loop"]["executionHealth"]["degraded"])
        self.assertEqual(jobs["job-target"]["executionHealth"]["tone"], "recovered")
        self.assertFalse(jobs["job-target"]["executionHealth"]["degraded"])

    def test_build_history_payload_coerces_malformed_job_fields_into_contract_warnings(self) -> None:
        task_id = "t-20260421-121500-contract"
        self.write_json(
            self.paths.tasks / f"{task_id}.json",
            {
                "taskId": task_id,
                "objective": "Show malformed job payloads safely.",
            },
        )
        self.write_json(
            self.paths.jobs / "job-malformed.json",
            {
                "jobId": "job-malformed",
                "taskId": task_id,
                "jobType": "loop",
                "status": "completed",
                "queuePosition": "front",
                "attempt": "retry",
                "resumeFromRound": "later",
                "rounds": "two",
                "workerCount": "many",
                "timeoutSeconds": "soon",
                "usage": {
                    "totalTokens": "lots",
                    "estimatedCostUsd": "pricey",
                },
                "lastMessage": "Completed with malformed metadata.",
            },
        )

        payload = storage.build_history_payload(self.paths)
        job = next(entry for entry in payload["jobs"] if entry["jobId"] == "job-malformed")

        self.assertEqual(job["queuePosition"], 0)
        self.assertEqual(job["attempt"], 1)
        self.assertEqual(job["rounds"], 0)
        self.assertEqual(job["totalTokens"], 0)
        self.assertEqual(job["estimatedCostUsd"], 0.0)
        self.assertTrue(job["contractWarnings"])
        self.assertEqual(job["executionHealth"]["tone"], "warning")
        self.assertTrue(job["executionHealth"]["degraded"])

    def test_read_artifact_returns_summary_and_content(self) -> None:
        artifact_name = "t-20260421-120000-deadbe_A_step001_output.json"
        self.write_json(
            self.paths.outputs / artifact_name,
            {
                "taskId": "t-20260421-120000-deadbe",
                "artifactType": "worker_output",
                "workerId": "A",
                "label": "Proponent",
                "mode": "live",
                "model": "gpt-5-mini",
                "step": 1,
                "responseId": "resp_123",
                "responseMeta": {
                    "requestedMaxOutputTokens": 900,
                    "effectiveMaxOutputTokens": 1800,
                    "maxOutputTokenAttempts": [900, 1800],
                    "recoveredFromIncomplete": True,
                },
                "rawOutputText": "Raw lane output.",
            },
        )

        payload = storage.read_artifact(self.paths, artifact_name)

        self.assertEqual(payload["name"], artifact_name)
        self.assertEqual(payload["storage"], "outputs")
        self.assertEqual(payload["summary"]["target"], "A")
        self.assertEqual(payload["summary"]["requestedMaxOutputTokens"], 900)
        self.assertEqual(payload["summary"]["effectiveMaxOutputTokens"], 1800)
        self.assertTrue(payload["summary"]["recoveredFromIncomplete"])
        self.assertEqual(payload["content"]["label"], "Proponent")

    def test_read_artifact_surfaces_contract_warnings_for_malformed_response_meta(self) -> None:
        artifact_name = "t-20260421-120100-deadbe_A_step001_output.json"
        self.write_json(
            self.paths.outputs / artifact_name,
            {
                "taskId": "t-20260421-120100-deadbe",
                "artifactType": "worker_output",
                "workerId": "A",
                "label": "Proponent",
                "mode": "live",
                "model": "gpt-5-mini",
                "step": "first",
                "responseMeta": {
                    "requestedMaxOutputTokens": "wide-open",
                    "effectiveMaxOutputTokens": "wider",
                    "maxOutputTokenAttempts": ["900", "oops", None],
                },
                "rawOutputText": "Raw lane output.",
            },
        )

        payload = storage.read_artifact(self.paths, artifact_name)

        self.assertIsNone(payload["summary"]["step"])
        self.assertIsNone(payload["summary"]["requestedMaxOutputTokens"])
        self.assertIsNone(payload["summary"]["effectiveMaxOutputTokens"])
        self.assertEqual(payload["summary"]["maxOutputTokenAttempts"], [900])
        self.assertTrue(payload["summary"]["contractWarnings"])

    def test_eval_history_and_artifact_reads_work_from_isolated_run_store(self) -> None:
        run_id = "run-1"
        run_dir = self.paths.eval_runs / run_id
        artifact_relative = "cases/case-1/arm-1/replicate-1/summary.json"
        self.write_json(
            self.paths.eval_suites / "suite.json",
            {
                "suiteId": "suite-1",
                "title": "Core Suite",
                "description": "Local eval suite",
                "cases": [{"caseId": "case-1"}],
            },
        )
        self.write_json(
            self.paths.eval_arms / "arm.json",
            {
                "armId": "arm-1",
                "title": "Steered",
                "description": "Steered answer",
                "type": "steered",
                "runtime": {
                    "model": "gpt-5-mini",
                    "summarizerModel": "gpt-5-mini",
                    "reasoningEffort": "medium",
                },
                "workers": [{"id": "A", "type": "proponent", "label": "Proponent", "model": "gpt-5-mini"}],
            },
        )
        self.write_json(
            run_dir / "run.json",
            {
                "runId": run_id,
                "suiteId": "suite-1",
                "status": "completed",
                "createdAt": "2026-04-21T12:00:00+00:00",
                "summary": {
                    "caseCount": 1,
                    "variantCount": 1,
                    "estimatedCostUsd": 0.01,
                },
                "artifactIndex": {
                    "summary-1": {
                        "name": "summary.json",
                        "kind": "summary_output",
                        "relativePath": artifact_relative,
                        "summary": {"taskId": "t-1"},
                    }
                },
            },
        )
        self.write_json(
            run_dir / artifact_relative,
            {
                "taskId": "t-1",
                "frontAnswer": {"answer": "Ship the thing."},
            },
        )

        history = storage.build_eval_history_payload(self.paths)
        artifact = storage.read_eval_artifact(self.paths, run_id, "summary-1")

        self.assertEqual(history["suites"][0]["suiteId"], "suite-1")
        self.assertEqual(history["arms"][0]["armId"], "arm-1")
        self.assertEqual(history["selectedRunId"], run_id)
        self.assertEqual(history["selectedRun"]["runId"], run_id)
        self.assertEqual(artifact["artifactId"], "summary-1")
        self.assertEqual(artifact["content"]["frontAnswer"]["answer"], "Ship the thing.")

    def test_recover_dispatch_jobs_view_interrupts_stale_and_dependency_failed_jobs(self) -> None:
        jobs = [
            storage.default_job(
                {
                    "jobId": "dispatch-commander",
                    "jobType": "target",
                    "taskId": "t-1",
                    "target": "commander",
                    "status": "error",
                    "queuedAt": "2026-04-21T12:00:00+00:00",
                }
            ),
            storage.default_job(
                {
                    "jobId": "dispatch-worker-a",
                    "jobType": "target",
                    "taskId": "t-1",
                    "target": "A",
                    "status": "queued",
                    "dependencyJobIds": ["dispatch-commander"],
                    "queuedAt": "2026-04-21T12:00:01+00:00",
                }
            ),
            storage.default_job(
                {
                    "jobId": "dispatch-worker-b",
                    "jobType": "target",
                    "taskId": "t-1",
                    "target": "B",
                    "status": "running",
                    "queuedAt": "2026-04-21T12:00:00+00:00",
                    "startedAt": "2026-04-21T12:00:00+00:00",
                    "lastHeartbeatAt": "2026-04-21T12:00:00+00:00",
                }
            ),
        ]

        with mock.patch("backend.app.storage.datetime") as fake_datetime:
            from datetime import datetime, timezone

            fake_now = datetime(2026, 4, 21, 12, 10, 0, tzinfo=timezone.utc)
            fake_datetime.now.return_value = fake_now
            fake_datetime.fromisoformat.side_effect = datetime.fromisoformat
            fake_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            recovered = storage.recover_dispatch_jobs_view(jobs)

        recovered_by_id = {str(job["jobId"]): job for job in recovered}
        self.assertEqual(recovered_by_id["dispatch-worker-a"]["status"], "interrupted")
        self.assertIn("dependency failed", recovered_by_id["dispatch-worker-a"]["lastMessage"].lower())
        self.assertEqual(recovered_by_id["dispatch-worker-b"]["status"], "interrupted")
        self.assertIn("stale running dispatch job", recovered_by_id["dispatch-worker-b"]["lastMessage"].lower())

    def test_coerce_loop_state_marks_stale_running_job_interrupted(self) -> None:
        state = storage.default_state()
        state["loop"] = {
            **storage.default_loop_state(),
            "status": "running",
            "jobId": "job-loop",
            "mode": "background",
            "totalRounds": 2,
            "completedRounds": 0,
            "currentRound": 1,
            "queuedAt": "2026-04-21T12:00:00+00:00",
            "startedAt": "2026-04-21T12:00:00+00:00",
            "lastHeartbeatAt": "2026-04-21T12:00:00+00:00",
            "lastMessage": "Running round 1.",
        }
        jobs = [
            storage.default_job(
                {
                    "jobId": "job-loop",
                    "taskId": "t-1",
                    "status": "running",
                    "mode": "background",
                    "rounds": 2,
                    "completedRounds": 0,
                    "currentRound": 1,
                    "delayMs": 0,
                    "queuedAt": "2026-04-21T12:00:00+00:00",
                    "startedAt": "2026-04-21T12:00:00+00:00",
                    "lastHeartbeatAt": "2026-04-21T12:00:00+00:00",
                    "lastMessage": "Running round 1.",
                }
            )
        ]

        with mock.patch("backend.app.storage.datetime") as fake_datetime:
            from datetime import datetime, timezone

            fake_now = datetime(2026, 4, 21, 12, 10, 0, tzinfo=timezone.utc)
            fake_datetime.now.return_value = fake_now
            fake_datetime.fromisoformat.side_effect = datetime.fromisoformat
            fake_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            coerced = storage.coerce_loop_state(state, jobs)

        self.assertEqual(coerced["loop"]["status"], "interrupted")
        self.assertIn("stale running background loop", coerced["loop"]["lastMessage"].lower())


if __name__ == "__main__":
    unittest.main()
