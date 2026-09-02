from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.engine import (
    RuntimeErrorWithCode,
    compile_engine_graph,
    default_judge_model_for_provider,
    default_ollama_timeout_profile,
    default_target_timeout_config,
    default_timeout_mode,
    normalize_ollama_base_url,
    normalize_ollama_timeout_profile,
    normalize_provider_id,
    normalize_reasoning_effort,
    normalize_target_timeout_config,
    normalize_timeout_mode,
    target_timeout_seconds,
)
from runtime.eval_runner import validate_arm_manifest, validate_suite_manifest
from runtime.provider_torso import (
    default_provider_id as contract_default_provider_id,
    model_source_for_auth_route,
    provider_default_auth_route,
    provider_default_model,
    resolve_auth_route,
)

from . import background, control, jobs, metadata, storage
from .config import deployment_topology


def ensure_eval_paths(paths: storage.Paths) -> None:
    for path in [paths.evals, paths.eval_suites, paths.eval_arms, paths.eval_runs]:
        path.mkdir(parents=True, exist_ok=True)


def read_manifest_by_id(directory: Path, manifest_id: str, id_key: str) -> Optional[Dict[str, Any]]:
    candidate = directory / f"{manifest_id}.json"
    payload = storage.read_json_file(candidate)
    if isinstance(payload, dict) and str(payload.get(id_key) or "").strip() == manifest_id:
        return payload
    for file_path in sorted(directory.glob("*.json")):
        payload = storage.read_json_file(file_path)
        if isinstance(payload, dict) and str(payload.get(id_key) or "").strip() == manifest_id:
            return payload
    return None


def _subprocess_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "cwd": str(Path(__file__).resolve().parents[2]),
        "env": os.environ.copy(),
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    return kwargs


def write_eval_run(paths: storage.Paths, run: Dict[str, Any]) -> Dict[str, Any]:
    ensure_eval_paths(paths)
    run_id = str(run.get("runId") or "").strip()
    if not run_id:
        raise ValueError("Eval runId is required.")
    run_dir = paths.eval_runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run["updatedAt"] = storage.utc_now()
    if metadata.postgres_enabled(paths.root):
        metadata.write_eval_run_payload(paths.root, run)
    else:
        (run_dir / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    return run


def launch_eval_runner(run_id: str, root: Optional[Path] = None) -> Optional[str]:
    repo_root = Path(root).resolve() if root else Path(__file__).resolve().parents[2]
    if deployment_topology(repo_root).queue_backend == "in_process":
        from runtime.eval_runner import execute_run

        return background.submit("eval", str(run_id or "eval-run"), repo_root, execute_run, repo_root, str(run_id))
    command = [sys.executable, str(repo_root / "runtime" / "eval_runner.py"), f"--root={repo_root}", f"--run-id={run_id}"]
    subprocess.Popen(command, **_subprocess_kwargs())  # noqa: S603,S607
    return None


def _new_run_id(prefix: str) -> str:
    stamp = storage.utc_now().replace("-", "").replace(":", "").replace("+00:00", "z").replace("T", "-")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:6]}"


def _parse_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _parse_float(value: Any, default: float, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _infer_judge_learning_bank_id(arms: List[Dict[str, Any]], fallback: str = "msp-knowledgebase") -> str:
    candidates: List[str] = []
    for arm in arms:
        runtime_config = arm.get("runtime") if isinstance(arm.get("runtime"), dict) else {}
        knowledgebase_config = runtime_config.get("knowledgebase") if isinstance(runtime_config.get("knowledgebase"), dict) else {}
        bank_id = str(knowledgebase_config.get("bankId") or "").strip()
        if (
            bool(knowledgebase_config.get("enabled", True))
            and bool(knowledgebase_config.get("includePersistent", True))
            and bank_id
            and bank_id not in candidates
        ):
            candidates.append(bank_id)
    return candidates[0] if candidates else fallback


def _judge_learning_config(payload: Dict[str, Any], arms: List[Dict[str, Any]], *, default_enabled: bool = False) -> Dict[str, Any]:
    raw = payload.get("judgeLearning") if isinstance(payload.get("judgeLearning"), dict) else {}
    enabled_value = raw.get("enabled")
    if enabled_value is None:
        enabled_value = payload.get("judgeLearningEnabled")
    bank_id = str(raw.get("bankId") or raw.get("bank_id") or payload.get("judgeLearningBankId") or "").strip()
    return {
        "enabled": _parse_bool(enabled_value, default_enabled),
        "bankId": bank_id or _infer_judge_learning_bank_id(arms),
        "dryRun": _parse_bool(raw.get("dryRun", raw.get("dry_run", payload.get("judgeLearningDryRun"))), False),
        "writeMode": "knowledgebase",
        "source": "judge_scores",
    }


def _load_suite(paths: storage.Paths, suite_id: str) -> Dict[str, Any]:
    manifest = read_manifest_by_id(paths.eval_suites, suite_id, "suiteId")
    if not isinstance(manifest, dict):
        raise RuntimeErrorWithCode(f"Unknown suiteId: {suite_id}", 404)
    return validate_suite_manifest(manifest, paths.eval_suites / f"{suite_id}.json")


def _load_arm(paths: storage.Paths, arm_id: str) -> Dict[str, Any]:
    manifest = read_manifest_by_id(paths.eval_arms, arm_id, "armId")
    if not isinstance(manifest, dict):
        raise RuntimeErrorWithCode(f"Unknown armId: {arm_id}", 404)
    return validate_arm_manifest(manifest, paths.eval_arms / f"{arm_id}.json")


def _subset_suite_case(suite: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    if not case_id:
        return suite
    cases = [case for case in suite.get("cases", []) if str(case.get("caseId") or "") == case_id]
    if not cases:
        raise RuntimeErrorWithCode(f"Case {case_id} was not found in suite {suite.get('suiteId')}.", 404)
    return {
        **suite,
        "suiteId": f"{suite['suiteId']}--{case_id}",
        "title": f"{suite['title']} | {cases[0]['title']}",
        "cases": cases,
    }


def _combine_suites(suites: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not suites:
        raise RuntimeErrorWithCode("Judge needs at least one suite.", 400)
    title_bits = [str(suite.get("title") or suite.get("suiteId") or "").strip() for suite in suites]
    combined_cases: List[Dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for suite in suites:
        suite_id = str(suite.get("suiteId") or "").strip()
        for case in suite.get("cases", []):
            if not isinstance(case, dict):
                continue
            base_case_id = str(case.get("caseId") or "").strip()
            next_case = dict(case)
            next_case_id = base_case_id
            if next_case_id in seen_case_ids:
                next_case_id = f"{suite_id}-{base_case_id}"
            next_case["caseId"] = next_case_id
            seen_case_ids.add(next_case_id)
            combined_cases.append(next_case)
    return {
        "suiteId": f"judge-{uuid.uuid4().hex[:8]}",
        "title": "Judge suite | " + " + ".join([bit for bit in title_bits if bit][:3]),
        "description": "Composite judge suite launched from the front canvas.",
        "judgeRubric": suites[0].get("judgeRubric", {}),
        "cases": combined_cases,
    }


def _front_runtime_budget(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "maxCostUsd": _parse_float(payload.get("maxCostUsd"), 5.0, 0.0),
        "maxTotalTokens": 0,
    }


def _front_runtime_research(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": _parse_bool(payload.get("researchEnabled"), False),
        "externalWebAccess": _parse_bool(payload.get("researchExternalWebAccess"), True),
        "domains": _parse_list(payload.get("researchDomains")),
    }


def _front_runtime_vetting(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"enabled": _parse_bool(payload.get("vettingEnabled"), True)}


def _front_runtime_loop(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rounds": _parse_int(payload.get("loopRounds"), 1, 1),
        "delayMs": _parse_int(payload.get("loopDelayMs"), 0, 0),
    }


def _front_runtime_timeouts(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("targetTimeouts")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _front_ollama_timeout_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("ollamaTimeoutProfile")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return normalize_ollama_timeout_profile(raw if isinstance(raw, dict) else default_ollama_timeout_profile())


def _front_judge_runtime(
    payload: Dict[str, Any],
    selection: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    selected = selection or _front_lane_selection(payload, "judge", judge=True)
    provider = selected["provider"]
    timeout_mode = normalize_timeout_mode(payload.get("timeoutMode"), default_timeout_mode())
    manual = normalize_target_timeout_config(_front_runtime_timeouts(payload))
    ollama_profile = _front_ollama_timeout_profile(payload)
    effective = default_target_timeout_config()
    if timeout_mode == "user":
        effective = manual
    elif provider == "ollama" and timeout_mode == "auto" and str(ollama_profile.get("status") or "") == "ready":
        effective = normalize_target_timeout_config(ollama_profile.get("targetTimeouts"))
    return {
        "provider": provider,
        "authRoute": selected["authRoute"],
        "modelSource": selected["modelSource"],
        "codexNoTimeout": _parse_bool(payload.get("codexNoTimeout"), False),
        "codexSubagentsEnabled": _parse_bool(payload.get("codexSubagentsEnabled"), False),
        "ollamaBaseUrl": normalize_ollama_base_url(payload.get("ollamaBaseUrl")),
        "requestTimeoutSeconds": target_timeout_seconds(effective, "arbiter"),
        "timeoutMode": timeout_mode,
        "targetTimeouts": effective,
        "ollamaTimeoutProfile": ollama_profile,
    }


def _front_summarizer_harness(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("summarizerHarness")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _front_direct_harness(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("directHarness")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _front_worker_list(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("workers")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    return raw if isinstance(raw, list) else []


def _front_lane_selection(
    payload: Dict[str, Any],
    role: str,
    *,
    fallback_provider: Optional[str] = None,
    fallback_model: Optional[str] = None,
    fallback_model_source: Optional[str] = None,
    judge: bool = False,
) -> Dict[str, str]:
    prefix = "" if role == "worker" else role
    provider_key = "provider" if not prefix else f"{prefix}Provider"
    model_key = "model" if not prefix else f"{prefix}Model"
    source_key = "modelSource" if not prefix else f"{prefix}ModelSource"
    route_key = "authRoute" if not prefix else f"{prefix}AuthRoute"
    provider_fallback = normalize_provider_id(
        fallback_provider,
        contract_default_provider_id(judge=judge),
    )
    provider = normalize_provider_id(payload.get(provider_key), provider_fallback)
    requested_model = payload.get(model_key)
    default_route = provider_default_auth_route(provider, judge=judge)
    route_candidate = payload.get(route_key) or payload.get(source_key)
    if (
        not str(route_candidate or "").strip()
        and fallback_model_source
        and provider == provider_fallback
    ):
        route_candidate = fallback_model_source
    if (
        not str(requested_model or "").strip()
        and fallback_model
        and provider == provider_fallback
    ):
        requested_model = fallback_model
    auth_route = resolve_auth_route(
        provider,
        route_candidate,
        model=requested_model,
        judge=judge,
    )
    model_source = model_source_for_auth_route(auth_route)
    default_model = provider_default_model(provider, auth_route=auth_route, judge=judge)
    if (
        not str(requested_model or "").strip()
        and fallback_model
        and provider == provider_fallback
        and model_source == str(fallback_model_source or model_source)
    ):
        requested_model = fallback_model
    model = control.normalize_sourced_model_id(
        requested_model,
        default_model,
        provider,
        model_source,
    )
    return {
        "provider": provider,
        "model": model,
        "authRoute": auth_route,
        "modelSource": model_source,
    }


def _build_front_eval_arm(payload: Dict[str, Any]) -> Dict[str, Any]:
    worker = _front_lane_selection(payload, "worker")
    summarizer = _front_lane_selection(
        payload,
        "summarizer",
        fallback_provider=worker["provider"],
        fallback_model=worker["model"],
        fallback_model_source=worker["modelSource"],
    )
    direct = _front_lane_selection(
        payload,
        "direct",
        fallback_provider=worker["provider"],
        fallback_model=worker["model"],
        fallback_model_source=worker["modelSource"],
    )
    requested_execution_mode = str(payload.get("executionMode") or "live").strip().lower() or "live"
    if requested_execution_mode != "live":
        raise RuntimeErrorWithCode("Front evals only support live execution. Configure a real provider/key before starting the run.", 400)
    execution_mode = "live"
    engine_version = "v2"
    engine_graph = payload.get("engineGraph") if isinstance(payload.get("engineGraph"), dict) else None
    worker_list = _front_worker_list(payload)
    legacy_reasoning_effort = normalize_reasoning_effort(payload.get("reasoningEffort"), "low")
    worker_reasoning_effort = normalize_reasoning_effort(
        payload.get("workerReasoningEffort"),
        legacy_reasoning_effort,
    )
    summarizer_reasoning_effort = normalize_reasoning_effort(
        payload.get("summarizerReasoningEffort"),
        legacy_reasoning_effort,
    )
    runtime_payload = {
        "provider": worker["provider"],
        "model": worker["model"],
        "authRoute": worker["authRoute"],
        "modelSource": worker["modelSource"],
        "summarizerProvider": summarizer["provider"],
        "summarizerModel": summarizer["model"],
        "summarizerAuthRoute": summarizer["authRoute"],
        "summarizerModelSource": summarizer["modelSource"],
        "directProvider": direct["provider"],
        "directModel": direct["model"],
        "directAuthRoute": direct["authRoute"],
        "directModelSource": direct["modelSource"],
    }
    return {
        "armId": f"front-eval-{uuid.uuid4().hex[:8]}",
        "title": str(payload.get("title") or "Current setup vs single-thread baseline").strip() or "Current setup vs single-thread baseline",
        "description": "Front canvas compare run using the current staged worker/summarizer setup against a direct baseline.",
        "type": "steered",
        "runtime": {
            "executionMode": execution_mode,
            "engineVersion": engine_version,
            "engineGraph": engine_graph,
            "enginePlan": compile_engine_graph(engine_graph, task={"workers": worker_list, "runtime": runtime_payload}, runtime_config=runtime_payload),
            "contextMode": str(payload.get("contextMode") or "weighted").strip() or "weighted",
            "directBaselineMode": "both",
            "provider": worker["provider"],
            "model": worker["model"],
            "authRoute": worker["authRoute"],
            "modelSource": worker["modelSource"],
            "directProvider": direct["provider"],
            "directModel": direct["model"],
            "directAuthRoute": direct["authRoute"],
            "directModelSource": direct["modelSource"],
            "ollamaBaseUrl": payload.get("ollamaBaseUrl"),
            "summarizerProvider": summarizer["provider"],
            "summarizerModel": summarizer["model"],
            "summarizerAuthRoute": summarizer["authRoute"],
            "summarizerModelSource": summarizer["modelSource"],
            "summarizerHarness": _front_summarizer_harness(payload),
            "directHarness": _front_direct_harness(payload),
            "reasoningEffort": worker_reasoning_effort,
            "workerReasoningEffort": worker_reasoning_effort,
            "summarizerReasoningEffort": summarizer_reasoning_effort,
            "codexNoTimeout": _parse_bool(payload.get("codexNoTimeout"), False),
            "codexSubagentsEnabled": _parse_bool(payload.get("codexSubagentsEnabled"), False),
            "budget": _front_runtime_budget(payload),
            "research": _front_runtime_research(payload),
            "vetting": _front_runtime_vetting(payload),
            "preferredLoop": _front_runtime_loop(payload),
            "targetTimeouts": _front_runtime_timeouts(payload),
            "requireLive": True,
        },
        "workers": worker_list,
    }


def _build_front_live_task_payload(payload: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    task_payload = dict(payload)
    task_payload["frontMode"] = "live"
    task_payload["liveRunId"] = run_id
    return task_payload


def _build_front_live_run(paths: storage.Paths, run_id: str, task: Dict[str, Any], loop_job_id: Optional[str]) -> Dict[str, Any]:
    runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
    workers = task.get("workers") if isinstance(task.get("workers"), list) else []
    return {
        "runId": run_id,
        "suiteId": f"live-{task.get('taskId')}",
        "armIds": [],
        "replicates": 1,
        "loopSweep": [max(1, int(((task.get("preferredLoop") or {}) if isinstance(task.get("preferredLoop"), dict) else {}).get("rounds") or 1))],
        "judgeModel": None,
        "status": "queued",
        "createdAt": storage.utc_now(),
        "updatedAt": storage.utc_now(),
        "source": "front",
        "canvas": "live",
        "taskId": str(task.get("taskId") or ""),
        "loopJobId": str(loop_job_id or "").strip() or None,
        "launcher": {
            "kind": "front-live",
            "label": str(task.get("objective") or "Live run").strip()[:120] or "Live run",
        },
        "live": {
            "objective": str(task.get("objective") or "").strip(),
            "engineVersion": "v2",
            "engineGraph": runtime.get("engineGraph") if isinstance(runtime.get("engineGraph"), dict) else None,
            "enginePlan": runtime.get("enginePlan") if isinstance(runtime.get("enginePlan"), dict) else None,
            "provider": str(runtime.get("provider") or ""),
            "model": str(runtime.get("model") or ""),
            "modelSource": str(runtime.get("modelSource") or ""),
            "summarizerProvider": str((task.get("summarizer") or {}).get("provider") or ""),
            "summarizerModel": str((task.get("summarizer") or {}).get("model") or ""),
            "summarizerModelSource": str((task.get("summarizer") or {}).get("modelSource") or ""),
            "workerCount": len(workers),
            "workers": [
                {
                    "id": worker.get("id"),
                    "type": worker.get("type"),
                    "label": worker.get("label"),
                    "model": worker.get("model"),
                }
                for worker in workers
                if isinstance(worker, dict)
            ],
        },
        "summary": {
            "caseCount": 1,
            "variantCount": 1,
            "errorCount": 0,
            "totalTokens": 0,
            "estimatedCostUsd": 0.0,
            "averageQuality": {},
            "averageAnswerHealth": {},
            "averageControl": {},
            "variants": [],
        },
    }


def sync_front_live_run(run_id: str, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    paths = storage.project_paths(root)
    run = storage.read_eval_run(paths, run_id)
    if not isinstance(run, dict):
        return None
    if str(run.get("canvas") or "").strip().lower() != "live":
        return run

    task_id = str(run.get("taskId") or "").strip()
    task_state = storage.read_task_state_payload(task_id, paths)
    state = task_state if isinstance(task_state, dict) else storage.read_state_payload(paths)
    active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    task = active_task if isinstance(active_task, dict) and str(active_task.get("taskId") or "") == task_id else storage.read_task_snapshot(task_id, paths)
    jobs_payload = storage.read_jobs(paths)
    loop_jobs = [
        storage.default_job(job)
        for job in jobs_payload
        if str((job or {}).get("jobType") or "loop") == "loop"
        and str((job or {}).get("taskId") or "") == task_id
    ]
    loop_jobs.sort(key=lambda item: (storage.parse_ts(item.get("queuedAt")) or 0, str(item.get("jobId") or "")), reverse=True)

    loop_job_id = str(run.get("loopJobId") or "").strip()
    loop_job = next((job for job in loop_jobs if str(job.get("jobId") or "") == loop_job_id), None)
    if loop_job is None and loop_jobs:
        loop_job = loop_jobs[0]
        loop_job_id = str(loop_job.get("jobId") or "").strip()

    active_loop = (state.get("loop") if isinstance(state.get("loop"), dict) else {}) if isinstance(active_task, dict) and str(active_task.get("taskId") or "") == task_id else {}
    active_loop_status = str(active_loop.get("status") or "").strip().lower() if isinstance(active_loop, dict) else ""
    loop_job_status = str((loop_job or {}).get("status") or "").strip().lower()
    if active_loop_status in {"queued", "running"}:
        loop_status = active_loop_status
    elif loop_job_status:
        loop_status = loop_job_status
    else:
        loop_status = active_loop_status or str(run.get("status") or "queued")
    created_at = str(run.get("createdAt") or storage.utc_now())
    state_usage = storage.normalize_usage_state((state.get("usage") if isinstance(active_task, dict) and str(active_task.get("taskId") or "") == task_id else {}) or {})
    job_usage = storage.normalize_usage_state((((loop_job or {}).get("usage")) if isinstance((loop_job or {}).get("usage"), dict) else {}) or {})
    usage = state_usage
    if int(usage.get("totalTokens") or 0) <= 0 and float(usage.get("estimatedCostUsd") or 0.0) <= 0.0:
        usage = job_usage
    current = None
    if loop_status in {"queued", "running"}:
        current_round = 0
        if isinstance(active_loop, dict):
            current_round = max(0, int(active_loop.get("currentRound") or 0))
        current = {
            "taskId": task_id,
            "loopJobId": loop_job_id or None,
            "round": current_round or max(0, int((loop_job or {}).get("currentRound") or 0)),
            "status": loop_status,
            "message": str((active_loop.get("lastMessage") if isinstance(active_loop, dict) else None) or (loop_job or {}).get("lastMessage") or "").strip() or None,
        }

    live = run.get("live") if isinstance(run.get("live"), dict) else {}
    if isinstance(task, dict):
        runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        workers = task.get("workers") if isinstance(task.get("workers"), list) else []
        live = {
            **live,
            "objective": str(task.get("objective") or live.get("objective") or "").strip(),
            "engineVersion": "v2",
            "engineGraph": runtime.get("engineGraph") if isinstance(runtime.get("engineGraph"), dict) else live.get("engineGraph"),
            "enginePlan": runtime.get("enginePlan") if isinstance(runtime.get("enginePlan"), dict) else live.get("enginePlan"),
            "provider": str(runtime.get("provider") or live.get("provider") or ""),
            "model": str(runtime.get("model") or live.get("model") or ""),
            "summarizerProvider": str((task.get("summarizer") or {}).get("provider") or live.get("summarizerProvider") or ""),
            "summarizerModel": str((task.get("summarizer") or {}).get("model") or live.get("summarizerModel") or ""),
            "workerCount": len(workers),
            "workers": [
                {
                    "id": worker.get("id"),
                    "type": worker.get("type"),
                    "label": worker.get("label"),
                    "model": worker.get("model"),
                }
                for worker in workers
                if isinstance(worker, dict)
            ],
        }

    updated_run = {
        **run,
        "taskId": task_id or run.get("taskId"),
        "loopJobId": loop_job_id or run.get("loopJobId"),
        "status": loop_status,
        "updatedAt": storage.utc_now(),
        "startedAt": str((loop_job or {}).get("startedAt") or run.get("startedAt") or "").strip() or None,
        "completedAt": str((loop_job or {}).get("finishedAt") or run.get("completedAt") or "").strip() or None,
        "current": current,
        "live": live,
        "summary": {
            "caseCount": 1,
            "variantCount": 1,
            "errorCount": 1 if loop_status in {"error", "budget_exhausted", "interrupted"} else 0,
            "totalTokens": int(usage.get("totalTokens") or 0),
            "estimatedCostUsd": float(usage.get("estimatedCostUsd") or 0.0),
            "averageQuality": {},
            "averageAnswerHealth": {},
            "averageControl": {},
            "variants": [],
        },
    }
    if not str(updated_run.get("createdAt") or "").strip():
        updated_run["createdAt"] = created_at
    write_eval_run(paths, updated_run)
    return updated_run


def sync_front_live_runs(root: Optional[Path] = None) -> None:
    paths = storage.project_paths(root)
    for run in storage.list_eval_runs(paths):
        if str(run.get("canvas") or "").strip().lower() != "live":
            continue
        run_id = str(run.get("runId") or "").strip()
        if run_id:
            sync_front_live_run(run_id, paths.root)


def _base_run_payload(
    run_id: str,
    suite: Dict[str, Any],
    arm_ids: List[str],
    judge_provider: str,
    judge_model: str,
    canvas: str,
    judge_runtime: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_judge_provider = normalize_provider_id(
        judge_provider,
        contract_default_provider_id(judge=True),
    )
    return {
        "runId": run_id,
        "suiteId": str(suite.get("suiteId") or "").strip(),
        "armIds": arm_ids,
        "replicates": 1,
        "loopSweep": [1],
        "judgeProvider": normalized_judge_provider,
        "judgeModel": str(
            judge_model or default_judge_model_for_provider(normalized_judge_provider)
        ).strip() or default_judge_model_for_provider(normalized_judge_provider),
        "judgeRuntime": dict(judge_runtime or {}),
        "status": "queued",
        "createdAt": storage.utc_now(),
        "updatedAt": storage.utc_now(),
        "source": "front",
        "canvas": canvas,
    }


def start_front_eval_run(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    paths = storage.project_paths(root)
    ensure_eval_paths(paths)
    suite_id = str(payload.get("suiteId") or "").strip()
    if not suite_id:
        raise RuntimeErrorWithCode("Eval needs a suite selection.", 400)
    case_id = str(payload.get("caseId") or "").strip()
    suite = _subset_suite_case(_load_suite(paths, suite_id), case_id)
    arm = validate_arm_manifest(_build_front_eval_arm(payload), paths.root / "front-eval")
    judge = _front_lane_selection(payload, "judge", judge=True)
    run_id = _new_run_id("eval")
    run = _base_run_payload(
        run_id,
        suite,
        [arm["armId"]],
        judge["provider"],
        judge["model"],
        "eval",
        _front_judge_runtime(payload, judge),
    )
    run["loopSweep"] = [max(1, int(arm["runtime"]["preferredLoop"]["rounds"]))]
    run["inlineSuite"] = suite
    run["inlineArms"] = {arm["armId"]: arm}
    run["selectedCaseId"] = case_id or (suite.get("cases") or [{}])[0].get("caseId")
    run["launcher"] = {"kind": "front-eval", "label": arm["title"]}
    run["judgeLearning"] = _judge_learning_config(payload, [arm], default_enabled=False)
    write_eval_run(paths, run)
    launch_eval_runner(run_id, paths.root)
    return {"message": "Front eval queued.", "runId": run_id, "run": storage.build_eval_run_preview(run)}


def start_front_live_run(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    paths = storage.project_paths(root)
    ensure_eval_paths(paths)
    run_id = _new_run_id("live")
    task_payload = _build_front_live_task_payload(payload, run_id)
    current_state = storage.read_state_payload(paths)
    loop_status = str((((current_state.get("loop") or {}) if isinstance(current_state.get("loop"), dict) else {})).get("status") or "idle")
    activate = loop_status not in {"queued", "running"}
    task_result = control.create_task(task_payload, paths.root, activate=activate)
    task_id = str(task_result.get("taskId") or "").strip()
    task = storage.read_task_snapshot(task_id, paths)
    if not isinstance(task, dict):
        active_task = current_state.get("activeTask") if isinstance(current_state.get("activeTask"), dict) else None
        if isinstance(active_task, dict) and str(active_task.get("taskId") or "") == task_id:
            task = active_task
    if not isinstance(task, dict):
        raise RuntimeErrorWithCode("Live task snapshot was not written.", 500)
    loop_result = jobs.start_loop_for_task(
        task_id,
        {
            "rounds": _parse_int(payload.get("loopRounds"), 1, 1),
            "delayMs": _parse_int(payload.get("loopDelayMs"), 0, 0),
        },
        paths.root,
    )
    run = _build_front_live_run(paths, run_id, task, str(loop_result.get("jobId") or "").strip() or None)
    write_eval_run(paths, run)
    synced = sync_front_live_run(run_id, paths.root) or run
    return {
        "message": "Front live queued.",
        "taskId": task_id,
        "jobId": loop_result.get("jobId"),
        "runId": run_id,
        "run": storage.build_eval_run_preview(synced),
    }


def start_front_judge_run(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    paths = storage.project_paths(root)
    ensure_eval_paths(paths)
    suite_ids = _parse_list(payload.get("suiteIds"))
    if not suite_ids:
        raise RuntimeErrorWithCode("Judge needs at least one selected suite.", 400)
    arm_ids = _parse_list(payload.get("armIds"))
    if not arm_ids:
        raise RuntimeErrorWithCode("Judge needs at least one selected arm.", 400)
    suites = [_load_suite(paths, suite_id) for suite_id in suite_ids]
    arms = [_load_arm(paths, arm_id) for arm_id in arm_ids]
    suite = validate_suite_manifest(_combine_suites(suites), paths.root / "front-judge")
    judge = _front_lane_selection(payload, "judge", judge=True)
    run_id = _new_run_id("judge")
    run = _base_run_payload(
        run_id,
        suite,
        [arm["armId"] for arm in arms],
        judge["provider"],
        judge["model"],
        "judge",
        _front_judge_runtime(payload, judge),
    )
    run["replicates"] = _parse_int(payload.get("replicates"), 1, 1)
    run["loopSweep"] = [
        _parse_int(value, 1, 1)
        for value in _parse_list(payload.get("loopSweep"))
        if _parse_int(value, 1, 1) > 0
    ] or [1]
    run["inlineSuite"] = suite
    run["inlineArms"] = {arm["armId"]: arm for arm in arms}
    run["judgeLearning"] = _judge_learning_config(payload, arms, default_enabled=True)
    run["launcher"] = {
        "kind": "front-judge",
        "suiteIds": suite_ids,
        "armIds": [arm["armId"] for arm in arms],
    }
    write_eval_run(paths, run)
    launch_eval_runner(run_id, paths.root)
    return {"message": "Front judge queued.", "runId": run_id, "run": storage.build_eval_run_preview(run)}


def start_eval_run(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    raise RuntimeErrorWithCode(
        "Legacy batch eval launch has moved to Home. Set Front mode to Eval and run from the main composer.",
        410,
    )
