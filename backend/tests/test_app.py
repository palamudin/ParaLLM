from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock
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
        self.assertIn("/index_old.html", paths)
        self.assertIn("/replacement-shell.html", paths)
        self.assertIn("/webviewindex.html", paths)
        self.assertIn("/health", paths)
        self.assertIn("/v1/system/topology", paths)
        self.assertIn("/v1/system/infrastructure", paths)
        self.assertIn("/v1/repo/graph", paths)
        self.assertIn("/v1/knowledgebase/graph", paths)
        self.assertIn("/v1/knowledgebase/status", paths)
        self.assertIn("/v1/knowledgebase/retain", paths)
        self.assertIn("/v1/knowledgebase/recall", paths)
        self.assertIn("/v1/knowledgebase/reflect", paths)
        self.assertIn("/v1/knowledgebase/learn/evals", paths)
        self.assertIn("/v1/memory/graph", paths)
        self.assertIn("/v1/memory/status", paths)
        self.assertIn("/v1/memory/retain", paths)
        self.assertIn("/v1/memory/recall", paths)
        self.assertIn("/v1/memory/reflect", paths)
        self.assertIn("/v1/memory/learn/evals", paths)
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
        self.assertIn("/v1/scores/runs", paths)
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

    def test_root_serves_replacement_shell_defaults(self) -> None:
        client = TestClient(create_app())
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("assets/replacement-shell.js", response.text)
        self.assertIn("Run contract", response.text)
        self.assertIn('id="previewRunThread"', response.text)
        self.assertIn('class="igs-chat-canvas"', response.text)
        self.assertIn('id="previewLaneGrid"', response.text)
        self.assertIn('id="previewStepLog"', response.text)
        self.assertIn("Math2Code", response.text)
        self.assertNotIn("Live answer viewport", response.text)
        self.assertIn('href="/index_old.html"', response.text)
        self.assertNotIn('id="headerApiMode"', response.text)

    def test_home_panels_expose_collapse_controls_except_chat_viewport(self) -> None:
        client = TestClient(create_app())
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="previewHomeCollapsedPills"', response.text)
        for panel in ("contract", "lanes", "trace", "supporting", "math2code"):
            self.assertIn(f'data-home-panel="{panel}"', response.text)
            self.assertIn(f'data-home-collapse-toggle="{panel}"', response.text)
        self.assertIn('data-home-panel="chat"', response.text)
        self.assertNotIn('data-home-collapse-toggle="chat"', response.text)

    def test_home_composer_uses_tool_menu_and_arrow_send_control(self) -> None:
        client = TestClient(create_app())
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="previewComposerToolMenuToggle"', response.text)
        self.assertIn('id="previewComposerToolMenu"', response.text)
        self.assertIn('id="previewComposerFileInput"', response.text)
        self.assertIn('data-composer-tool-action="upload"', response.text)
        self.assertIn('data-composer-tool-action="web-search"', response.text)
        self.assertIn('data-composer-tool-action="memory"', response.text)
        self.assertIn('class="igs-send-icon"', response.text)
        self.assertIn('aria-label="Send prompt"', response.text)
        self.assertNotIn('>Send</button>', response.text)

    def test_run_contract_drawer_uses_pill_controls_and_summary_chips(self) -> None:
        client = TestClient(create_app())
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('class="igs-control-bay"', response.text)
        self.assertIn('class="igs-control-pack igs-control-pack-routing"', response.text)
        self.assertIn('class="igs-control-stack igs-runtime-stack"', response.text)
        self.assertIn('class="igs-control-pack igs-control-pack-models"', response.text)
        self.assertIn('class="igs-control-pack igs-control-pack-execution"', response.text)
        self.assertIn('class="igs-control-tile', response.text)
        self.assertIn('class="igs-control-tile igs-control-tile-provider"', response.text)
        self.assertIn('data-contract-control-tile="Worker provider"', response.text)
        self.assertIn('class="igs-provider-led"', response.text)
        self.assertNotIn('igs-control-glyph', response.text)
        self.assertNotIn('igs-control-led', response.text)
        self.assertIn('data-contract-control-tile="Runtime mode"', response.text)
        self.assertIn('class="igs-contract-telemetry"', response.text)
        self.assertIn('data-contract-pill-select="Worker default model"', response.text)
        self.assertIn('class="igs-native-pill-select"', response.text)
        self.assertIn('class="igs-summary-pill-grid"', response.text)
        self.assertIn('class="igs-summary-pill"', response.text)

    def test_run_contract_uses_toggles_for_modes_and_boolean_controls(self) -> None:
        client = TestClient(create_app())
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('data-select-cycle="previewRuntimeMode"', response.text)
        self.assertIn('data-cycle-values="live,eval,judge"', response.text)
        self.assertIn('data-cycle-press-levels="none,half,full"', response.text)
        self.assertIn('data-select-cycle="previewContextMode"', response.text)
        self.assertIn('data-cycle-values="weighted,full"', response.text)
        self.assertIn('data-select-cycle="previewDirectBaselineMode"', response.text)
        self.assertIn('data-cycle-values="off,single,both"', response.text)
        self.assertIn('data-press-level="none"', response.text)
        for control_id in ("previewVettingEnabled", "previewResearchMode", "previewMemoryMode"):
            self.assertIn(f'data-select-toggle="{control_id}"', response.text)
            self.assertIn(f'data-toggle-target="{control_id}"', response.text)
        self.assertIn('data-state-tooltip-delay="100"', response.text)
        self.assertNotIn('data-state-tooltip-delay="2000"', response.text)
        self.assertIn('data-state-label="', response.text)
        self.assertIn('class="igs-control-tile igs-state-tile', response.text)
        self.assertIn('class="igs-state-text"', response.text)
        self.assertNotIn('igs-state-segment', response.text)
        self.assertNotIn('class="igs-state-button', response.text)
        self.assertNotIn('data-contract-pill-select="Runtime mode"', response.text)
        self.assertNotIn('data-contract-pill-select="Worker context"', response.text)
        self.assertNotIn('data-contract-pill-select="Single-thread baseline"', response.text)
        self.assertNotIn('data-contract-pill-select="Summarizer vetting"', response.text)
        self.assertNotIn('data-contract-pill-select="Research"', response.text)
        self.assertNotIn('data-contract-pill-select="Fractal memory"', response.text)
        self.assertNotIn('igs-toggle-switch-track', response.text)

    def test_run_contract_controls_use_intrinsic_visual_widths(self) -> None:
        root = Path(__file__).resolve().parents[2]
        css = (root / "assets" / "replacement-shell.css").read_text(encoding="utf-8")
        js = (root / "assets" / "replacement-shell.js").read_text(encoding="utf-8")

        self.assertIn("flex: 0 1 auto;", css)
        self.assertIn("width: fit-content;", css)
        self.assertIn("--pill-control-width", css)
        self.assertIn(".igs-state-tile::after", css)
        self.assertIn("transition-delay: 100ms;", css)
        self.assertIn(".igs-control-stack", css)
        self.assertIn(".igs-control-pack {", css)
        self.assertIn("background: transparent;", css)
        self.assertIn(".igs-home-contract .igs-control-tile::before,", css)
        self.assertIn(".igs-home-contract .igs-control-tile:not(.igs-state-tile)::after", css)
        self.assertIn("display: none;", css)
        self.assertIn(".igs-home-contract .igs-control-tile:active", css)
        self.assertIn("transform: translateY(2px) scale(0.986);", css)
        self.assertIn("translate: 0 2px;", css)
        self.assertIn("scale: 0.986;", css)
        self.assertIn("rgba(255, 255, 255, 0.055)", css)
        self.assertIn("color-mix(in srgb, var(--control-accent, var(--rs-accent)) 8%, #070d15)", css)
        self.assertIn("0 0 18px color-mix(in srgb, var(--control-accent, var(--rs-accent)) 34%, transparent)", css)
        self.assertIn("text-shadow: 0 0 9px color-mix(in srgb, var(--control-accent, var(--rs-accent)) 46%, transparent)", css)
        self.assertIn('.igs-state-tile[data-press-level="half"]', css)
        self.assertIn('transform: translateY(1px) scale(0.993);', css)
        self.assertIn("translate: 0 1px;", css)
        self.assertIn("scale: 0.993;", css)
        self.assertIn('.igs-state-tile[data-press-level="full"]', css)
        self.assertIn(".igs-state-tile[data-state-tone=\"both\"]", css)
        self.assertIn("--control-accent: #4ea1ff;", css)
        self.assertIn(".igs-home-contract .igs-control-tile-provider:hover", css)
        self.assertIn("cursor: default;", css)
        self.assertIn(".igs-home-contract .igs-control-tile-provider .igs-segment-btn", css)
        self.assertIn('html[data-bs-theme="light"] .igs-home-contract', css)
        self.assertIn('html[data-bs-theme="light"] .igs-home-contract .igs-control-bay', css)
        self.assertIn('html[data-bs-theme="light"] .igs-home-contract .igs-control-tile', css)
        self.assertIn('html[data-bs-theme="light"] .igs-home-contract .igs-control-tile-provider', css)
        self.assertIn('html[data-bs-theme="light"] .igs-send-button', css)
        self.assertIn('html[data-bs-theme="light"] .igs-send-button.is-answer-now', css)
        self.assertIn(".igs-control-pack-execution .igs-control-tile", css)
        self.assertIn("font-size: 0.68rem;", css)
        self.assertIn("pressLevelForCycleButton", js)
        self.assertIn('button.dataset.pressLevel = pressLevel;', js)
        self.assertIn('button.setAttribute("aria-pressed", pressLevel === "half" ? "mixed" : active ? "true" : "false");', js)
        self.assertIn("syncContractPillIntrinsicWidth", js)
        self.assertIn("contractSelectOptionMeasureLabel", js)
        self.assertIn("syncSelectToggleButtons", js)
        self.assertIn("syncSelectCycleButtons", js)
        self.assertIn("frontEvalRuns", js)
        self.assertIn("frontJudgeRuns", js)

    def test_debug_view_exposes_old_shell_operations(self) -> None:
        client = TestClient(create_app())
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        for control_id in (
            "debugRefreshState",
            "debugResetSession",
            "debugClearSessionArchives",
            "debugRunRound",
            "debugRunLoop",
            "debugSummarize",
            "debugCancelLoop",
            "debugResetState",
            "debugTargetControls",
            "debugExportCurrentSession",
            "debugJobHistory",
            "debugRoundHistory",
            "debugSessionArchives",
            "debugStepLog",
            "debugEventLog",
        ):
            self.assertIn(f'id="{control_id}"', response.text)

    def test_legacy_shell_route_serves_old_shell(self) -> None:
        client = TestClient(create_app())
        response = client.get("/index_old.html")

        self.assertEqual(response.status_code, 200)
        self.assertIn("assets/app.js", response.text)
        self.assertIn("assets/vendor/jquery/jquery-3.7.1.min.js", response.text)
        self.assertIn('class="workspace-pill-row"', response.text)
        self.assertIn('id="headerTaskId"', response.text)

    def test_replacement_shell_route_serves_preview_shell(self) -> None:
        client = TestClient(create_app())
        response = client.get("/replacement-shell.html")

        self.assertEqual(response.status_code, 200)
        self.assertIn("assets/replacement-shell.js", response.text)
        self.assertIn("Run contract", response.text)
        self.assertIn('id="previewRunThread"', response.text)
        self.assertIn('class="igs-chat-canvas"', response.text)
        self.assertIn('id="previewLaneGrid"', response.text)
        self.assertIn('id="previewStepLog"', response.text)
        self.assertNotIn("Live answer viewport", response.text)
        self.assertIn("Open legacy shell", response.text)
        self.assertIn('href="/index_old.html"', response.text)

    def test_knowledgebase_graph_route_returns_ai_readable_nodes(self) -> None:
        (self.root / "index.html").write_text("<html></html>", encoding="utf-8")
        (self.root / "replacement-shell.html").write_text("<html></html>", encoding="utf-8")
        (self.root / "webviewindex.html").write_text("<html></html>", encoding="utf-8")
        (self.paths.eval_suites / "msp-demo.json").write_text(
            json.dumps(
                {
                    "suiteId": "msp-demo",
                    "title": "MSP Demo",
                    "cases": [{"caseId": "rmm-demo", "title": "RMM Demo", "sessionContext": "MSP RMM incident"}],
                }
            ),
            encoding="utf-8",
        )
        self.paths.steps.write_text(
            json.dumps({"ts": "2026-05-01T00:00:00+00:00", "stage": "session", "message": "Started."}) + "\n",
            encoding="utf-8",
        )
        self.paths.events.write_text(
            json.dumps({"ts": "2026-05-01T00:00:01+00:00", "type": "demo", "payload": {"ok": True}}) + "\n",
            encoding="utf-8",
        )

        client = TestClient(create_app(self.root))
        response = client.get("/v1/knowledgebase/graph")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schemaVersion"], "fractal-memory-highway/v0")
        self.assertIn("objective", payload["nodes"])
        self.assertIn("native_memory_layer", payload["nodes"])
        self.assertFalse(payload["meta"]["memoryStatus"]["coreDependency"])
        self.assertIn("eval_subjects", payload["nodes"])
        self.assertTrue(any(lane.get("id") == "memory" for lane in payload["lanes"]))
        self.assertTrue(any(lane.get("id") == "judge_msp" for lane in payload["lanes"]))

    def test_knowledgebase_status_reports_optional_fallback_layer(self) -> None:
        (self.root / "index.html").write_text("<html></html>", encoding="utf-8")
        (self.root / "replacement-shell.html").write_text("<html></html>", encoding="utf-8")
        (self.root / "webviewindex.html").write_text("<html></html>", encoding="utf-8")
        self.paths.steps.write_text(
            json.dumps({"ts": "2026-05-01T00:00:00+00:00", "stage": "qa", "message": "Fallback is readable."}) + "\n",
            encoding="utf-8",
        )

        client = TestClient(create_app(self.root))
        response = client.get("/v1/knowledgebase/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["available"])
        self.assertFalse(payload["coreDependency"])
        self.assertEqual(payload["storage"]["backend"], "local_jsonl")
        self.assertTrue(payload["fallback"]["available"])
        self.assertTrue(any(adapter["id"] == "runtime_fallback" for adapter in payload["adapters"]))

    def test_knowledgebase_retain_recall_and_reflect_are_local_and_ai_readable(self) -> None:
        (self.root / "index.html").write_text("<html></html>", encoding="utf-8")
        (self.root / "replacement-shell.html").write_text("<html></html>", encoding="utf-8")
        (self.root / "webviewindex.html").write_text("<html></html>", encoding="utf-8")
        client = TestClient(create_app(self.root))

        retain_response = client.post(
            "/v1/knowledgebase/retain",
            json={
                "bankId": "client-acme",
                "content": "Acme firewall rollback requires a change ticket and preserved audit evidence.",
                "tags": ["client:acme", "runbook"],
                "metadata": {"source": "unit-test"},
            },
        )
        self.assertEqual(retain_response.status_code, 200)
        self.assertEqual(retain_response.json()["stored"], 1)

        recall_response = client.get(
            "/v1/knowledgebase/recall",
            params={
                "bankId": "client-acme",
                "query": "firewall rollback audit evidence",
                "includeRuntime": "false",
            },
        )
        self.assertEqual(recall_response.status_code, 200)
        recall_payload = recall_response.json()
        self.assertEqual(recall_payload["bankId"], "client-acme")
        self.assertEqual(recall_payload["resultCount"], 1)
        self.assertIn("firewall rollback", recall_payload["hits"][0]["text"])
        self.assertIn("contextText", recall_payload["aiPacket"])
        self.assertFalse(recall_payload["aiPacket"]["coreDependency"])

        reflect_response = client.post(
            "/v1/knowledgebase/reflect",
            json={"bankId": "client-acme", "query": "What protects the Acme firewall rollback?"},
        )
        self.assertEqual(reflect_response.status_code, 200)
        reflect_payload = reflect_response.json()
        self.assertIn("Native knowledgebase reflection", reflect_payload["text"])
        self.assertIn("recommendedNextCheck", reflect_payload["structuredOutput"])

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
            with mock.patch("backend.app.jobs.launch_loop_job_runner"):
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

    def test_scores_runs_route_returns_scored_runs(self) -> None:
        bench_root = self.paths.data / "benchmarks" / "vetting"
        runs_dir = bench_root / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = bench_root / "demo-manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "title": "Demo scored run",
                    "judgeSystem": "provider_owned",
                    "judgeProvider": "anthropic",
                    "judgeModel": "claude-opus-4-7",
                    "providerFamily": "anthropic",
                    "objective": "Contain the blast path.",
                    "constraints": ["Use decision gates."],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (self.paths.eval_arms / "direct-demo.json").write_text(
            json.dumps({"armId": "direct-demo", "runtime": {"provider": "anthropic", "model": "claude-opus-4-7"}}, indent=2),
            encoding="utf-8",
        )
        (self.paths.eval_arms / "para-demo.json").write_text(
            json.dumps({"armId": "para-demo", "runtime": {"provider": "anthropic", "model": "claude-sonnet-4-6", "summarizerModel": "claude-opus-4-7"}}, indent=2),
            encoding="utf-8",
        )
        (runs_dir / "vet-demo.json").write_text(
            json.dumps(
                {
                    "runId": "vet-demo",
                    "createdAt": "2026-04-27T16:10:28+00:00",
                    "sourceManifest": str(manifest_path),
                    "judge": {"provider": "anthropic", "model": "claude-opus-4-7"},
                    "judgeSystem": "provider_owned",
                    "providerFamily": "anthropic",
                    "case": {"title": "Demo scored run", "objective": "Contain the blast path.", "constraints": ["Use decision gates."], "gold": {}},
                    "answers": [
                        {"slot": "A", "answerId": "direct-demo", "label": "Direct Demo", "role": "direct", "provider": "anthropic", "text": "Direct answer text.", "scores": {"overall": 8.0}},
                        {"slot": "B", "answerId": "para-demo", "label": "Para Demo", "role": "parallm", "provider": "anthropic", "text": "Para answer text.", "scores": {"overall": 9.0}},
                    ],
                    "bestFinalAnswer": {"slot": "B", "answerId": "para-demo", "label": "Para Demo", "role": "parallm"},
                    "bestTacticalDetail": {"slot": "B", "answerId": "para-demo", "label": "Para Demo", "role": "parallm"},
                    "advantageSummary": {"band": "clear", "leader": {"slot": "B", "label": "Para Demo"}, "runnerUp": {"slot": "A", "label": "Direct Demo"}},
                    "markdown": {"summary": "- Best final answer: Para Demo", "scoreTable": "| Area | A | B |"},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        previous = os.environ.get("LOOP_DATA_ROOT")
        os.environ["LOOP_DATA_ROOT"] = str(self.paths.data)
        try:
            client = TestClient(create_app())
            response = client.get("/v1/scores/runs", params={"runId": "vet-demo"})
        finally:
            if previous is None:
                os.environ.pop("LOOP_DATA_ROOT", None)
            else:
                os.environ["LOOP_DATA_ROOT"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["runs"][0]["runId"], "vet-demo")
        self.assertEqual(payload["selectedRun"]["judge"]["provider"], "anthropic")

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
