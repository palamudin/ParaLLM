from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qsl

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
    from fastapi.staticfiles import StaticFiles
except ModuleNotFoundError as exc:  # pragma: no cover - helpful runtime error
    raise RuntimeError("Install backend/requirements.txt before running the Python control-plane scaffold.") from exc

from runtime.engine import RuntimeErrorWithCode

from . import config, control, dispatch, evals, infrastructure, jobs, judge_learning, knowledgebase, memory_graph, repo_graph, sessions, settings, storage


async def request_payload(request: Request) -> dict[str, object]:
    content_type = str(request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        body = json.loads((await request.body()).decode("utf-8") or "{}")
        return body if isinstance(body, dict) else {}
    raw = (await request.body()).decode("utf-8", errors="replace")
    return {str(key): value for key, value in parse_qsl(raw, keep_blank_values=True)}


def python_shell_html(root: Path) -> str:
    index_path = root / "index.html"
    return index_path.read_text(encoding="utf-8")


def legacy_shell_html(root: Path) -> str:
    index_path = root / "index_old.html"
    if not index_path.is_file():
        raise FileNotFoundError("index_old.html not found.")
    return index_path.read_text(encoding="utf-8")


def replacement_shell_html(root: Path) -> str:
    replacement_path = root / "replacement-shell.html"
    if not replacement_path.is_file():
        raise FileNotFoundError("replacement-shell.html not found.")
    return replacement_path.read_text(encoding="utf-8")


def repo_webview_html(root: Path) -> str:
    webview_path = root / "webviewindex.html"
    if not webview_path.is_file():
        raise FileNotFoundError("webviewindex.html not found.")
    return webview_path.read_text(encoding="utf-8")


def create_app(root: Path | None = None) -> FastAPI:
    paths = storage.project_paths(root)
    app = FastAPI(
        title="ParaLLM Control Plane",
        version="0.1.0",
        description="Python-first control plane for the ParaLLM shell, reads/writes, jobs, dispatch, evals, and local self-hosted operation.",
    )
    app.mount("/assets", StaticFiles(directory=str(paths.root / "assets")), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def app_shell() -> HTMLResponse:
        return HTMLResponse(python_shell_html(paths.root))

    @app.get("/index.html", response_class=HTMLResponse)
    def app_shell_index() -> HTMLResponse:
        return HTMLResponse(python_shell_html(paths.root))

    @app.get("/index_old.html", response_class=HTMLResponse)
    def legacy_shell_index() -> HTMLResponse:
        try:
            return HTMLResponse(legacy_shell_html(paths.root))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/replacement-shell.html", response_class=HTMLResponse)
    def replacement_shell_index() -> HTMLResponse:
        try:
            return HTMLResponse(replacement_shell_html(paths.root))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/webviewindex.html", response_class=HTMLResponse)
    def repo_webview_shell() -> HTMLResponse:
        try:
            return HTMLResponse(repo_webview_html(paths.root))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/health")
    def health() -> dict[str, object]:
        topology = config.deployment_topology(paths.root)
        infra = infrastructure.infrastructure_status(paths.root)
        return {
            "ok": True,
            "service": "python-control-plane",
            "root": str(paths.root),
            "mode": "scaffold",
            "profile": topology.profile,
            "queueBackend": topology.queue_backend,
            "metadataBackend": topology.metadata_backend,
            "artifactBackend": topology.artifact_backend,
            "secretBackend": topology.secret_backend,
            "runtimeExecutionBackend": topology.runtime_execution_backend,
            "infrastructureReady": bool(infra.get("ready")),
        }

    @app.get("/v1/system/topology")
    def get_topology() -> JSONResponse:
        return JSONResponse(config.deployment_topology(paths.root).as_dict())

    @app.get("/v1/system/infrastructure")
    def get_infrastructure() -> JSONResponse:
        return JSONResponse(infrastructure.infrastructure_status(paths.root))

    @app.get("/v1/repo/graph")
    def get_repo_graph(
        maxNodes: int = 1600,
        maxFiles: int = 5000,
        maxFileBytes: int = 900000,
        includeAmbiguous: bool = False,
    ) -> JSONResponse:
        return JSONResponse(
            repo_graph.build_repo_graph(
                paths.root,
                max_nodes=maxNodes,
                max_files=maxFiles,
                max_file_bytes=maxFileBytes,
                include_ambiguous=includeAmbiguous,
            )
        )

    @app.get("/v1/knowledgebase/graph")
    def get_knowledgebase_graph(
        maxEvents: int = 30,
        maxSteps: int = 30,
        maxArtifacts: int = 24,
        includeRepo: bool = False,
        maxRepoNodes: int = 220,
        maxRepoFiles: int = 2500,
        maxFileBytes: int = 500000,
    ) -> JSONResponse:
        return JSONResponse(
            memory_graph.build_memory_graph(
                paths.root,
                max_events=maxEvents,
                max_steps=maxSteps,
                max_artifacts=maxArtifacts,
                include_repo=includeRepo,
                max_repo_nodes=maxRepoNodes,
                max_repo_files=maxRepoFiles,
                max_file_bytes=maxFileBytes,
            )
        )

    @app.get("/v1/knowledgebase/status")
    def get_knowledgebase_status() -> JSONResponse:
        return JSONResponse(knowledgebase.status(paths.root))

    @app.post("/v1/knowledgebase/retain")
    async def post_knowledgebase_retain(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        return JSONResponse(knowledgebase.retain(paths.root, payload))

    @app.get("/v1/knowledgebase/recall")
    def get_knowledgebase_recall(
        query: str = "",
        bankId: str = "",
        maxRecords: int = 12,
        maxTokens: int = 2048,
        tags: str = "",
        tagsMatch: str = "any",
        types: str = "",
        includeRuntime: bool = True,
        includePersistent: bool = True,
    ) -> JSONResponse:
        return JSONResponse(
            knowledgebase.recall(
                paths.root,
                query=query,
                bank_id=bankId,
                max_records=maxRecords,
                max_tokens=maxTokens,
                tags=knowledgebase.parse_tags(tags),
                tags_match=tagsMatch,
                types=knowledgebase.parse_types(types),
                include_runtime=includeRuntime,
                include_persistent=includePersistent,
            )
        )

    @app.post("/v1/knowledgebase/recall")
    async def post_knowledgebase_recall(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        return JSONResponse(
            knowledgebase.recall(
                paths.root,
                query=str(payload.get("query") or payload.get("prompt") or ""),
                bank_id=str(payload.get("bankId") or payload.get("bank_id") or ""),
                max_records=int(payload.get("maxRecords") or payload.get("max_records") or 12),
                max_tokens=int(payload.get("maxTokens") or payload.get("max_tokens") or 2048),
                tags=knowledgebase.parse_tags(payload.get("tags")),
                tags_match=str(payload.get("tagsMatch") or payload.get("tags_match") or "any"),
                types=knowledgebase.parse_types(payload.get("types")),
                include_runtime=knowledgebase.coerce_bool(payload.get("includeRuntime"), True),
                include_persistent=knowledgebase.coerce_bool(payload.get("includePersistent"), True),
            )
        )

    @app.post("/v1/knowledgebase/reflect")
    async def post_knowledgebase_reflect(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        return JSONResponse(knowledgebase.reflect(paths.root, payload))

    @app.post("/v1/knowledgebase/learn/evals")
    async def post_knowledgebase_learn_evals(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        raw_run_ids = payload.get("runIds") or payload.get("run_ids") or payload.get("runId") or payload.get("run_id") or []
        if isinstance(raw_run_ids, str):
            run_ids = [part.strip() for part in re.split(r"[,\s]+", raw_run_ids) if part.strip()]
        elif isinstance(raw_run_ids, list):
            run_ids = [str(part).strip() for part in raw_run_ids if str(part).strip()]
        else:
            run_ids = []
        return JSONResponse(
            judge_learning.learn_from_eval_runs(
                paths.root,
                run_ids=run_ids,
                latest=int(payload.get("latest") or 1),
                bank_id=str(payload.get("bankId") or payload.get("bank_id") or judge_learning.DEFAULT_LEARNING_BANK_ID),
                dry_run=knowledgebase.coerce_bool(payload.get("dryRun", payload.get("dry_run")), False),
            )
        )

    @app.get("/v1/memory/graph")
    def get_memory_graph_legacy(
        maxEvents: int = 30,
        maxSteps: int = 30,
        maxArtifacts: int = 24,
        includeRepo: bool = False,
        maxRepoNodes: int = 220,
        maxRepoFiles: int = 2500,
        maxFileBytes: int = 500000,
    ) -> JSONResponse:
        return get_knowledgebase_graph(
            maxEvents=maxEvents,
            maxSteps=maxSteps,
            maxArtifacts=maxArtifacts,
            includeRepo=includeRepo,
            maxRepoNodes=maxRepoNodes,
            maxRepoFiles=maxRepoFiles,
            maxFileBytes=maxFileBytes,
        )

    @app.get("/v1/memory/status")
    def get_memory_status_legacy() -> JSONResponse:
        return get_knowledgebase_status()

    @app.post("/v1/memory/retain")
    async def post_memory_retain_legacy(request: Request) -> JSONResponse:
        return await post_knowledgebase_retain(request)

    @app.get("/v1/memory/recall")
    def get_memory_recall_legacy(
        query: str = "",
        bankId: str = "",
        maxRecords: int = 12,
        maxTokens: int = 2048,
        tags: str = "",
        tagsMatch: str = "any",
        types: str = "",
        includeRuntime: bool = True,
        includePersistent: bool = True,
    ) -> JSONResponse:
        return get_knowledgebase_recall(
            query=query,
            bankId=bankId,
            maxRecords=maxRecords,
            maxTokens=maxTokens,
            tags=tags,
            tagsMatch=tagsMatch,
            types=types,
            includeRuntime=includeRuntime,
            includePersistent=includePersistent,
        )

    @app.post("/v1/memory/reflect")
    async def post_memory_reflect_legacy(request: Request) -> JSONResponse:
        return await post_knowledgebase_reflect(request)

    @app.post("/v1/memory/learn/evals")
    async def post_memory_learn_evals_legacy(request: Request) -> JSONResponse:
        return await post_knowledgebase_learn_evals(request)

    @app.get("/v1/auth/status")
    def get_auth_status() -> JSONResponse:
        return JSONResponse(control.auth_pool_status(paths.root))

    @app.post("/v1/auth/keys")
    async def post_auth_keys(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = settings.set_auth_keys(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/auth/mode")
    async def post_auth_mode(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = settings.set_auth_backend_mode(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.get("/v1/providers/status")
    def get_provider_instances_status() -> JSONResponse:
        return JSONResponse(settings.get_provider_instance_status(paths.root))

    @app.post("/v1/providers/instances")
    async def post_provider_instances(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = settings.set_provider_instances(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.get("/v1/state")
    def get_state() -> JSONResponse:
        return JSONResponse(storage.read_state_payload(paths))

    @app.get("/v1/history")
    def get_history() -> JSONResponse:
        return JSONResponse(storage.build_history_payload(paths))

    @app.get("/v1/handoffs/latest")
    def get_latest_handoff() -> JSONResponse:
        packet = storage.read_latest_handoff_packet(paths)
        if packet is None:
            packet = storage.build_handoff_packet(
                paths,
                actor="system",
                reason="live-preview",
                next_action="No saved handoff exists yet. Create one before handing control to another agent.",
            )
        return JSONResponse(packet)

    @app.post("/v1/handoffs")
    async def post_handoff(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        packet = storage.write_handoff_packet(
            paths,
            actor=str(payload.get("actor") or "operator"),
            reason=str(payload.get("reason") or "manual"),
            next_action=str(payload.get("nextAction") or payload.get("next_action") or ""),
        )
        return JSONResponse(packet)

    @app.get("/v1/events")
    def get_events() -> PlainTextResponse:
        return PlainTextResponse(storage.tail_text_lines(paths.events, 100, "No events."), media_type="text/plain; charset=utf-8")

    @app.get("/v1/steps")
    def get_steps() -> PlainTextResponse:
        return PlainTextResponse(storage.tail_text_lines(paths.steps, 150, "No steps."), media_type="text/plain; charset=utf-8")

    @app.get("/v1/artifacts/{name}")
    def get_artifact(name: str) -> JSONResponse:
        try:
            payload = storage.read_artifact(paths, name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.get("/v1/artifact")
    def get_artifact_by_query(name: str = "") -> JSONResponse:
        try:
            payload = storage.read_artifact(paths, name.strip())
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.get("/v1/evals/history")
    def get_eval_history(runId: str = "", canvas: str = "") -> JSONResponse:
        if str(canvas or "").strip().lower() == "live":
            evals.sync_front_live_runs(paths.root)
        return JSONResponse(storage.build_eval_history_payload(paths, selected_run_id=runId.strip(), canvas=canvas.strip()))

    @app.get("/v1/scores/runs")
    def get_scores_runs(runId: str = "") -> JSONResponse:
        return JSONResponse(storage.build_scores_runs_payload(paths, selected_run_id=runId.strip()))

    @app.get("/v1/evals/artifacts/{run_id}/{artifact_id}")
    def get_eval_artifact(run_id: str, artifact_id: str) -> JSONResponse:
        try:
            payload = storage.read_eval_artifact(paths, run_id.strip(), artifact_id.strip())
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.get("/v1/evals/artifact")
    def get_eval_artifact_by_query(runId: str = "", artifactId: str = "") -> JSONResponse:
        try:
            payload = storage.read_eval_artifact(paths, runId.strip(), artifactId.strip())
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.post("/v1/draft")
    async def post_draft(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = control.save_draft(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/tasks")
    async def post_task(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = control.create_task(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/session/reset")
    def post_session_reset() -> JSONResponse:
        try:
            result = sessions.reset_session(paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/session/archives/clear")
    def post_session_archives_clear() -> JSONResponse:
        try:
            result = sessions.clear_session_archives(paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/state/reset")
    def post_state_reset() -> JSONResponse:
        try:
            result = sessions.reset_state(paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/session/replay")
    async def post_session_replay(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = sessions.replay_session(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.get("/v1/session/export")
    def get_session_export(archiveFile: str = "") -> JSONResponse:
        try:
            result = sessions.export_session(archiveFile, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/runtime/apply")
    async def post_runtime_apply(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = settings.apply_runtime_settings(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/workers/update")
    async def post_worker_update(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = settings.update_worker_config(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/workers/add")
    async def post_worker_add(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = settings.add_adversarial_worker(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/workers/remove")
    async def post_worker_remove(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = settings.remove_adversarial_worker(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/runtime/ollama/benchmark")
    async def post_runtime_ollama_benchmark(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = settings.benchmark_ollama_timeouts(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/runtime/ollama/models")
    async def post_runtime_ollama_models(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = settings.check_ollama_models(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/positions/model")
    async def post_position_model(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = settings.set_position_model(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/loops")
    async def post_loop(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = jobs.start_loop(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/loops/cancel")
    def post_cancel_loop() -> JSONResponse:
        try:
            result = jobs.cancel_loop(paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/jobs/manage")
    async def post_manage_job(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = jobs.manage_loop_job(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/targets/background")
    async def post_target_job(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = dispatch.start_target_job(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/rounds")
    async def post_round(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = dispatch.run_round(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/targets/run")
    async def post_run_target(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = dispatch.run_target_sync(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/evals/runs")
    async def post_eval_run(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = evals.start_eval_run(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/front/eval/runs")
    async def post_front_eval_run(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = evals.start_front_eval_run(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/front/live/runs")
    async def post_front_live_run(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = evals.start_front_live_run(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/v1/front/judge/runs")
    async def post_front_judge_run(request: Request) -> JSONResponse:
        payload = await request_payload(request)
        try:
            result = evals.start_front_judge_run(payload, paths.root)
        except RuntimeErrorWithCode as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    return app


app = create_app()
