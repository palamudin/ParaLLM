from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app import storage


class AppRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.paths = storage.project_paths(self.root)
        for directory in (
            self.root / "assets",
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

    def test_expected_routes_are_registered(self) -> None:
        app = create_app()
        paths = {route.path for route in app.routes}

        self.assertIn("/", paths)
        self.assertIn("/index.html", paths)
        self.assertIn("/health", paths)
        self.assertIn("/v1/system/topology", paths)
        self.assertIn("/v1/system/infrastructure", paths)
        self.assertIn("/v1/auth/status", paths)
        self.assertIn("/v1/auth/keys", paths)
        self.assertIn("/v1/state", paths)
        self.assertIn("/v1/state/reset", paths)
        self.assertIn("/v1/history", paths)
        self.assertIn("/v1/events", paths)
        self.assertIn("/v1/steps", paths)
        self.assertIn("/v1/artifacts/{name}", paths)
        self.assertIn("/v1/artifact", paths)
        self.assertIn("/v1/evals/history", paths)
        self.assertIn("/v1/evals/runs", paths)
        self.assertIn("/v1/front/live/runs", paths)
        self.assertIn("/v1/front/eval/runs", paths)
        self.assertIn("/v1/front/judge/runs", paths)
        self.assertIn("/v1/evals/artifact", paths)
        self.assertIn("/v1/evals/artifacts/{run_id}/{artifact_id}", paths)
        self.assertIn("/v1/draft", paths)
        self.assertIn("/v1/tasks", paths)
        self.assertIn("/v1/session/reset", paths)
        self.assertIn("/v1/session/archives/clear", paths)
        self.assertIn("/v1/session/replay", paths)
        self.assertIn("/v1/session/export", paths)
        self.assertIn("/v1/runtime/apply", paths)
        self.assertIn("/v1/workers/update", paths)
        self.assertIn("/v1/workers/add", paths)
        self.assertIn("/v1/positions/model", paths)
        self.assertIn("/v1/loops", paths)
        self.assertIn("/v1/loops/cancel", paths)
        self.assertIn("/v1/jobs/manage", paths)
        self.assertIn("/v1/targets/background", paths)
        self.assertIn("/v1/rounds", paths)
        self.assertIn("/v1/targets/run", paths)

    def test_root_serves_python_shell_defaults(self) -> None:
        client = TestClient(create_app())
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("assets/app.js", response.text)
        self.assertIn("assets/vendor/jquery/jquery-3.7.1.min.js", response.text)
        self.assertIn('class="workspace-pill-row"', response.text)
        self.assertIn('id="headerTaskId"', response.text)
        self.assertNotIn('id="headerApiMode"', response.text)

    def test_topology_endpoint_reports_local_single_node_defaults(self) -> None:
        client = TestClient(create_app())
        response = client.get("/v1/system/topology")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["profile"], "local-single-node")
        self.assertEqual(payload["queueBackend"], "local_subprocess")
        self.assertEqual(payload["metadataBackend"], "json_files")
        self.assertEqual(payload["artifactBackend"], "filesystem")
        self.assertEqual(payload["secretBackend"], "env")
        self.assertEqual(payload["runtimeExecutionBackend"], "embedded_engine_subprocess")

    def test_infrastructure_endpoint_reports_local_defaults_ready(self) -> None:
        client = TestClient(create_app())
        response = client.get("/v1/system/infrastructure")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["profile"], "local-single-node")
        self.assertIn("backends", payload)
        self.assertEqual(payload["backends"]["queue"]["backend"], "local_subprocess")
        self.assertEqual(payload["backends"]["metadata"]["backend"], "json_files")
        self.assertEqual(payload["backends"]["artifacts"]["backend"], "filesystem")

    def test_eval_runs_endpoint_returns_gone_message(self) -> None:
        client = TestClient(create_app())
        response = client.post(
            "/v1/evals/runs",
            json={"suiteId": "legacy-suite", "armIds": ["legacy-arm"]},
        )

        self.assertEqual(response.status_code, 410)
        self.assertIn("Front mode to Eval", str(response.json().get("detail") or ""))

    def test_front_live_run_route_creates_live_run(self) -> None:
        previous = os.environ.get("LOOP_DATA_ROOT")
        os.environ["LOOP_DATA_ROOT"] = str(self.paths.data)
        try:
            client = TestClient(create_app(self.root))
            with unittest.mock.patch("backend.app.jobs.launch_loop_job_runner"):
                response = client.post(
                    "/v1/front/live/runs",
                    json={
                        "objective": "Route-level live run smoke.",
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "summarizerProvider": "openai",
                        "summarizerModel": "gpt-5-mini",
                        "loopRounds": 1,
                        "loopDelayMs": 0,
                    },
                )
        finally:
            if previous is None:
                os.environ.pop("LOOP_DATA_ROOT", None)
            else:
                os.environ["LOOP_DATA_ROOT"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(str(payload.get("runId") or "").startswith("live-"))
        self.assertEqual(((payload.get("run") or {}) if isinstance(payload.get("run"), dict) else {}).get("canvas"), "live")

    def test_state_route_enriches_active_task_runtime_mirrors(self) -> None:
        self.paths.state.write_text(
            json.dumps(
                {
                    "activeTask": {
                        "taskId": "t-route-1",
                        "objective": "Validate live state shape.",
                    },
                    "workers": {"A": {"label": "Proponent", "step": 1}},
                    "commander": {"round": 1, "leadDirection": "Ship with guardrails."},
                    "commanderReview": {"round": 1, "courseDecision": "maintain"},
                    "summary": {"round": 1, "frontAnswer": {"answer": "Proceed carefully."}},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        self.paths.steps.write_text(
            json.dumps(
                {
                    "ts": "2026-04-21T12:00:00+00:00",
                    "stage": "commander",
                    "message": "Commander drafted the lead answer for this round.",
                    "context": {
                        "taskId": "t-route-1",
                        "mode": "live",
                        "recoveredFromIncomplete": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        previous = os.environ.get("LOOP_DATA_ROOT")
        os.environ["LOOP_DATA_ROOT"] = str(self.paths.data)
        try:
            client = TestClient(create_app())
            response = client.get("/v1/state")
        finally:
            if previous is None:
                os.environ.pop("LOOP_DATA_ROOT", None)
            else:
                os.environ["LOOP_DATA_ROOT"] = previous

        self.assertEqual(response.status_code, 200)
        active_task = response.json()["activeTask"]
        self.assertEqual(active_task["stateWorkers"]["A"]["label"], "Proponent")
        self.assertEqual(active_task["stateCommander"]["round"], 1)
        self.assertEqual(active_task["stateCommanderReview"]["courseDecision"], "maintain")
        self.assertEqual(active_task["summary"]["frontAnswer"]["answer"], "Proceed carefully.")
        self.assertTrue(active_task["executionHealth"]["degraded"])
        self.assertTrue(response.json()["executionHealth"]["targets"]["commander"]["recoveredFromIncomplete"])

    def test_state_route_surfaces_contract_warnings(self) -> None:
        self.paths.state.write_text(
            json.dumps(
                {
                    "activeTask": {"taskId": "t-route-contract", "objective": "Keep warnings visible."},
                    "workers": {"A": {"label": "Proponent"}, "B": "bad"},
                    "summary": ["bad"],
                    "loop": {"status": "hovering"},
                    "memoryVersion": "lots",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        previous = os.environ.get("LOOP_DATA_ROOT")
        os.environ["LOOP_DATA_ROOT"] = str(self.paths.data)
        try:
            client = TestClient(create_app())
            response = client.get("/v1/state")
        finally:
            if previous is None:
                os.environ.pop("LOOP_DATA_ROOT", None)
            else:
                os.environ["LOOP_DATA_ROOT"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["contractWarnings"])
        self.assertEqual(payload["activeTask"]["contractWarnings"], payload["contractWarnings"])
        self.assertEqual(payload["loop"]["status"], "idle")

    def test_history_route_surfaces_top_level_contract_warnings(self) -> None:
        self.paths.state.write_text(
            json.dumps(
                {
                    "activeTask": {"taskId": "t-route-history-contract", "objective": "Keep telemetry warnings visible."},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        self.paths.steps.write_text('{"ts":"2026-04-21T12:00:00+00:00","stage":"commander","context":{"taskId":"t-route-history-contract"}}\nnot-json\n', encoding="utf-8")
        previous = os.environ.get("LOOP_DATA_ROOT")
        os.environ["LOOP_DATA_ROOT"] = str(self.paths.data)
        try:
            client = TestClient(create_app())
            response = client.get("/v1/history")
        finally:
            if previous is None:
                os.environ.pop("LOOP_DATA_ROOT", None)
            else:
                os.environ["LOOP_DATA_ROOT"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["contractWarnings"])
        self.assertIn("steps.jsonl dropped 1 malformed JSONL line", payload["contractWarnings"][0])

    def test_session_archive_clear_route_reports_deleted_count(self) -> None:
        self.paths.sessions.mkdir(parents=True, exist_ok=True)
        (self.paths.sessions / "session-test.json").write_text(
            json.dumps({"taskId": "t-archive", "createdAt": "2026-04-25T00:00:00+00:00"}, indent=2),
            encoding="utf-8",
        )
        previous = os.environ.get("LOOP_DATA_ROOT")
        os.environ["LOOP_DATA_ROOT"] = str(self.paths.data)
        try:
            client = TestClient(create_app())
            response = client.post("/v1/session/archives/clear")
        finally:
            if previous is None:
                os.environ.pop("LOOP_DATA_ROOT", None)
            else:
                os.environ["LOOP_DATA_ROOT"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deleted"], 1)
        self.assertFalse((self.paths.sessions / "session-test.json").exists())


if __name__ == "__main__":
    unittest.main()
