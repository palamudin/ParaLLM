from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.engine import RuntimeErrorWithCode, compile_engine_graph
from runtime.eval_runner import validate_arm_manifest, validate_suite_manifest

from . import control, jobs, metadata, storage


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


def launch_eval_runner(run_id: str, root: Optional[Path] = None) -> None:
    repo_root = Path(root).resolve() if root else Path(__file__).resolve().parents[2]
    command = [sys.executable, str(repo_root / "runtime" / "eval_runner.py"), f"--root={repo_root}", f"--run-id={run_id}"]
    subprocess.Popen(command, **_subprocess_kwargs())  # noqa: S603,S607


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
        "maxOutputTokens": 0,
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


def _front_summarizer_harness(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("summarizerHarness")
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


def _build_front_eval_arm(payload: Dict[str, Any]) -> Dict[str, Any]:
    provider = str(payload.get("provider") or "openai").strip() or "openai"
    model = str(payload.get("model") or "").strip()
    summarizer_provider = str(payload.get("summarizerProvider") or provider).strip() or provider
    summarizer_model = str(payload.get("summarizerModel") or model).strip() or model
    direct_provider = str(payload.get("directProvider") or provider).strip() or provider
    direct_model = str(payload.get("directModel") or model).strip() or model
    execution_mode = str(payload.get("executionMode") or "live").strip() or "live"
    engine_version = str(payload.get("engineVersion") or "v1").strip() or "v1"
    engine_graph = payload.get("engineGraph") if isinstance(payload.get("engineGraph"), dict) else None
    worker_list = _front_worker_list(payload)
    runtime_payload = {
        "provider": provider,
        "model": model,
        "summarizerProvider": summarizer_provider,
        "summarizerModel": summarizer_model,
        "directProvider": direct_provider,
        "directModel": direct_model,
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
            "provider": provider,
            "model": model,
            "directProvider": direct_provider,
            "directModel": direct_model,
            "ollamaBaseUrl": payload.get("ollamaBaseUrl"),
            "summarizerProvider": summarizer_provider,
            "summarizerModel": summarizer_model,
            "summarizerHarness": _front_summarizer_harness(payload),
            "reasoningEffort": str(payload.get("reasoningEffort") or "low").strip() or "low",
            "budget": _front_runtime_budget(payload),
            "research": _front_runtime_research(payload),
            "vetting": _front_runtime_vetting(payload),
            "preferredLoop": _front_runtime_loop(payload),
            "targetTimeouts": _front_runtime_timeouts(payload),
            "requireLive": execution_mode == "live",
            "allowMockFallback": execution_mode != "live",
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
            "engineVersion": str(runtime.get("engineVersion") or "v1"),
            "engineGraph": runtime.get("engineGraph") if isinstance(runtime.get("engineGraph"), dict) else None,
            "enginePlan": runtime.get("enginePlan") if isinstance(runtime.get("enginePlan"), dict) else None,
            "provider": str(runtime.get("provider") or ""),
            "model": str(runtime.get("model") or ""),
            "summarizerProvider": str((task.get("summarizer") or {}).get("provider") or ""),
            "summarizerModel": str((task.get("summarizer") or {}).get("model") or ""),
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
    loop_status = str((active_loop.get("status") if isinstance(active_loop, dict) else None) or (loop_job or {}).get("status") or run.get("status") or "queued")
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
            "engineVersion": str(runtime.get("engineVersion") or live.get("engineVersion") or "v1"),
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


def _base_run_payload(run_id: str, suite: Dict[str, Any], arm_ids: List[str], judge_model: str, canvas: str) -> Dict[str, Any]:
    return {
        "runId": run_id,
        "suiteId": str(suite.get("suiteId") or "").strip(),
        "armIds": arm_ids,
        "replicates": 1,
        "loopSweep": [1],
        "judgeModel": str(judge_model or "gpt-5.4").strip() or "gpt-5.4",
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
    run_id = _new_run_id("eval")
    run = _base_run_payload(run_id, suite, [arm["armId"]], str(payload.get("judgeModel") or "gpt-5.4"), "eval")
    run["loopSweep"] = [max(1, int(arm["runtime"]["preferredLoop"]["rounds"]))]
    run["inlineSuite"] = suite
    run["inlineArms"] = {arm["armId"]: arm}
    run["selectedCaseId"] = case_id or (suite.get("cases") or [{}])[0].get("caseId")
    run["launcher"] = {"kind": "front-eval", "label": arm["title"]}
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
    run_id = _new_run_id("judge")
    run = _base_run_payload(run_id, suite, [arm["armId"] for arm in arms], str(payload.get("judgeModel") or "gpt-5.4"), "judge")
    run["replicates"] = _parse_int(payload.get("replicates"), 1, 1)
    run["loopSweep"] = [
        _parse_int(value, 1, 1)
        for value in _parse_list(payload.get("loopSweep"))
        if _parse_int(value, 1, 1) > 0
    ] or [1]
    run["inlineSuite"] = suite
    run["inlineArms"] = {arm["armId"]: arm for arm in arms}
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
