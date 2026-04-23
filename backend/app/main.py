from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qsl

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
    from fastapi.staticfiles import StaticFiles
except ModuleNotFoundError as exc:  # pragma: no cover - helpful runtime error
    raise RuntimeError("Install backend/requirements.txt before running the Python control-plane scaffold.") from exc

from runtime.engine import RuntimeErrorWithCode

from . import config, control, dispatch, evals, infrastructure, jobs, sessions, settings, storage


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

    @app.get("/v1/state")
    def get_state() -> JSONResponse:
        return JSONResponse(storage.read_state_payload(paths))

    @app.get("/v1/history")
    def get_history() -> JSONResponse:
        return JSONResponse(storage.build_history_payload(paths))

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
    def get_eval_history(runId: str = "") -> JSONResponse:
        return JSONResponse(storage.build_eval_history_payload(paths, selected_run_id=runId.strip()))

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

    return app


app = create_app()
