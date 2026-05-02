from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import artifacts, metadata
from .config import deployment_topology
from .provider_responses import extract_normalized_provider_answer, parse_embedded_json_value


LOCK_STALE_SECONDS = 45
JOB_QUEUE_STALE_SECONDS = 60
JOB_RUNNING_STALE_SECONDS = 180
LOOP_QUEUE_LIMIT = 4


@dataclass(frozen=True)
class Paths:
    root: Path
    data: Path
    tasks: Path
    task_states: Path
    checkpoints: Path
    outputs: Path
    sessions: Path
    jobs: Path
    evals: Path
    eval_suites: Path
    eval_arms: Path
    eval_runs: Path
    state: Path
    events: Path
    steps: Path


def project_paths(root: Optional[Path] = None) -> Paths:
    topology = deployment_topology(root)
    base = topology.root
    data = topology.data_root
    evals = data / "evals"
    return Paths(
        root=base,
        data=data,
        tasks=data / "tasks",
        task_states=data / "task_states",
        checkpoints=data / "checkpoints",
        outputs=data / "outputs",
        sessions=data / "sessions",
        jobs=data / "jobs",
        evals=evals,
        eval_suites=evals / "suites",
        eval_arms=evals / "arms",
        eval_runs=evals / "runs",
        state=data / "state.json",
        events=data / "events.jsonl",
        steps=data / "steps.jsonl",
    )


def benchmark_vetting_root(paths: Paths) -> Path:
    return paths.data / "benchmarks" / "vetting"


def benchmark_vetting_runs_dir(paths: Paths) -> Path:
    return benchmark_vetting_root(paths) / "runs"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_text(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    return raw


def read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    raw = read_text(path)
    if raw is None or raw.strip() == "":
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def append_contract_warning(warnings: List[str], message: str) -> None:
    normalized = str(message or "").strip()
    if not normalized or normalized in warnings:
        return
    warnings.append(normalized)


def coerce_int(
    value: Any,
    *,
    default: int = 0,
    minimum: Optional[int] = None,
    allow_none: bool = False,
    warnings: Optional[List[str]] = None,
    label: str = "value",
) -> Optional[int]:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        result: Optional[int] = None if allow_none else default
    else:
        try:
            result = int(value)
        except (TypeError, ValueError):
            result = None if allow_none else default
            if warnings is not None:
                append_contract_warning(
                    warnings,
                    f"{label} had an invalid numeric value ({value!r}); using {result if result is not None else 'none'}.",
                )
    if result is not None and minimum is not None and result < minimum:
        if warnings is not None:
            append_contract_warning(
                warnings,
                f"{label} was below the minimum ({result}); using {minimum}.",
            )
        result = minimum
    return result


def coerce_float(
    value: Any,
    *,
    default: float = 0.0,
    minimum: Optional[float] = None,
    allow_none: bool = False,
    warnings: Optional[List[str]] = None,
    label: str = "value",
) -> Optional[float]:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        result: Optional[float] = None if allow_none else default
    else:
        try:
            result = float(value)
        except (TypeError, ValueError):
            result = None if allow_none else default
            if warnings is not None:
                append_contract_warning(
                    warnings,
                    f"{label} had an invalid numeric value ({value!r}); using {result if result is not None else 'none'}.",
                )
    if result is not None and minimum is not None and result < minimum:
        if warnings is not None:
            append_contract_warning(
                warnings,
                f"{label} was below the minimum ({result}); using {minimum}.",
            )
        result = minimum
    return result


def coerce_int_list(value: Any, *, warnings: Optional[List[str]] = None, label: str = "values") -> List[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        if warnings is not None:
            append_contract_warning(warnings, f"{label} was not a list; dropping invalid values.")
        return []
    coerced: List[int] = []
    dropped = 0
    for item in value:
        parsed = coerce_int(item, allow_none=True)
        if parsed is None:
            dropped += 1
            continue
        coerced.append(parsed)
    if dropped and warnings is not None:
        append_contract_warning(warnings, f"{label} dropped {dropped} invalid entr{'y' if dropped == 1 else 'ies'}.")
    return coerced


def default_loop_state() -> Dict[str, Any]:
    return {
        "status": "idle",
        "jobId": None,
        "mode": "manual",
        "totalRounds": 0,
        "completedRounds": 0,
        "currentRound": 0,
        "delayMs": 0,
        "cancelRequested": False,
        "queuedAt": None,
        "startedAt": None,
        "finishedAt": None,
        "lastHeartbeatAt": None,
        "lastMessage": "Ready.",
        "activeTargets": [],
        "providerTrace": None,
    }


def default_usage_bucket() -> Dict[str, Any]:
    return {
        "calls": 0,
        "webSearchCalls": 0,
        "inputTokens": 0,
        "cachedInputTokens": 0,
        "billableInputTokens": 0,
        "outputTokens": 0,
        "reasoningTokens": 0,
        "totalTokens": 0,
        "modelCostUsd": 0.0,
        "toolCostUsd": 0.0,
        "estimatedCostUsd": 0.0,
        "lastModel": None,
        "lastResponseId": None,
        "lastUpdated": None,
    }


def default_usage_state() -> Dict[str, Any]:
    bucket = default_usage_bucket()
    bucket["byTarget"] = {}
    bucket["byModel"] = {}
    return bucket


def default_state() -> Dict[str, Any]:
    return {
        "activeTask": None,
        "draft": {},
        "commander": None,
        "commanderReview": None,
        "workers": {},
        "directBaseline": None,
        "summary": None,
        "arbiter": None,
        "memoryVersion": 0,
        "usage": default_usage_state(),
        "loop": default_loop_state(),
        "lastUpdated": utc_now(),
    }


def normalize_provider_trace(trace: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(trace, dict):
        return None
    normalized: Dict[str, Any] = {}
    for key, value in trace.items():
        field = str(key or "").strip()
        if not field:
            continue
        if value is None or isinstance(value, (str, int, float, bool)):
            normalized[field] = value
            continue
        if isinstance(value, list):
            normalized[field] = [
                item
                for item in value
                if item is None or isinstance(item, (str, int, float, bool))
            ][:20]
            continue
        if isinstance(value, dict):
            child: Dict[str, Any] = {}
            for child_key, child_value in value.items():
                child_field = str(child_key or "").strip()
                if not child_field:
                    continue
                if child_value is None or isinstance(child_value, (str, int, float, bool)):
                    child[child_field] = child_value
            normalized[field] = child
    return normalized or None


def normalize_usage_bucket(bucket: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = default_usage_bucket()
    current = bucket if isinstance(bucket, dict) else {}
    merged = dict(base)
    for key in base:
        value = current.get(key, base[key])
        if key.endswith("Usd"):
            merged[key] = coerce_float(value, default=0.0) or 0.0
        elif key in {"lastModel", "lastResponseId", "lastUpdated"}:
            merged[key] = value
        else:
            merged[key] = coerce_int(value, default=0) or 0
    return merged


def normalize_usage_state(usage: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    current = usage if isinstance(usage, dict) else {}
    merged = normalize_usage_bucket(current)
    merged["byTarget"] = {
        str(key): normalize_usage_bucket(value if isinstance(value, dict) else {})
        for key, value in (current.get("byTarget") or {}).items()
    } if isinstance(current.get("byTarget"), dict) else {}
    merged["byModel"] = {
        str(key): normalize_usage_bucket(value if isinstance(value, dict) else {})
        for key, value in (current.get("byModel") or {}).items()
    } if isinstance(current.get("byModel"), dict) else {}
    return merged


VALID_LOOP_STATUSES = {"idle", "queued", "running", "completed", "interrupted", "cancelled", "error", "budget_exhausted"}


def normalize_loop_snapshot(loop: Optional[Dict[str, Any]], warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    current = loop if isinstance(loop, dict) else {}
    merged = dict(default_loop_state())
    raw_status = str(current.get("status") or merged["status"]).strip().lower()
    if raw_status not in VALID_LOOP_STATUSES:
        append_contract_warning(warnings or [], f"loop.status {raw_status!r} is invalid; using 'idle'.")
        raw_status = "idle"
    merged["status"] = raw_status
    merged["jobId"] = current.get("jobId")
    merged["mode"] = str(current.get("mode") or merged["mode"]).strip() or merged["mode"]
    merged["totalRounds"] = coerce_int(current.get("totalRounds"), default=0, minimum=0, warnings=warnings, label="loop.totalRounds") or 0
    merged["completedRounds"] = coerce_int(current.get("completedRounds"), default=0, minimum=0, warnings=warnings, label="loop.completedRounds") or 0
    merged["currentRound"] = coerce_int(current.get("currentRound"), default=0, minimum=0, warnings=warnings, label="loop.currentRound") or 0
    merged["delayMs"] = coerce_int(current.get("delayMs"), default=0, minimum=0, warnings=warnings, label="loop.delayMs") or 0
    merged["cancelRequested"] = bool(current.get("cancelRequested") or False)
    merged["queuedAt"] = current.get("queuedAt")
    merged["startedAt"] = current.get("startedAt")
    merged["finishedAt"] = current.get("finishedAt")
    merged["lastHeartbeatAt"] = current.get("lastHeartbeatAt")
    merged["lastMessage"] = str(current.get("lastMessage") or merged["lastMessage"])
    merged["activeTargets"] = [
        str(value).strip()
        for value in (current.get("activeTargets") or [])
        if str(value).strip()
    ][:12] if isinstance(current.get("activeTargets"), list) else []
    merged["providerTrace"] = normalize_provider_trace(current.get("providerTrace"))
    return merged


def normalize_state_contract(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    current = state if isinstance(state, dict) else {}
    warnings: List[str] = []
    normalized = default_state()

    if current.get("activeTask") is not None and not isinstance(current.get("activeTask"), dict):
        append_contract_warning(warnings, "activeTask was not an object; dropping malformed task state.")
    normalized["activeTask"] = current.get("activeTask") if isinstance(current.get("activeTask"), dict) else None

    if current.get("draft") is not None and not isinstance(current.get("draft"), dict):
        append_contract_warning(warnings, "draft was not an object; resetting staged draft state.")
    normalized["draft"] = current.get("draft") if isinstance(current.get("draft"), dict) else {}

    for field in ("commander", "commanderReview", "directBaseline", "summary", "arbiter"):
        value = current.get(field)
        if value is not None and not isinstance(value, dict):
            append_contract_warning(warnings, f"{field} was not an object; dropping malformed state.")
        normalized[field] = value if isinstance(value, dict) else None

    worker_state = current.get("workers")
    if worker_state is not None and not isinstance(worker_state, dict):
        append_contract_warning(warnings, "workers was not an object; clearing malformed worker state.")
        worker_state = {}
    cleaned_workers: Dict[str, Any] = {}
    dropped_workers = 0
    for key, value in (worker_state or {}).items():
        worker_id = str(key).strip()
        if not worker_id:
            dropped_workers += 1
            continue
        if value is None or isinstance(value, dict):
            cleaned_workers[worker_id] = value
            continue
        dropped_workers += 1
    if dropped_workers:
        append_contract_warning(
            warnings,
            f"workers dropped {dropped_workers} malformed entr{'y' if dropped_workers == 1 else 'ies'}.",
        )
    normalized["workers"] = cleaned_workers

    normalized["memoryVersion"] = coerce_int(current.get("memoryVersion"), default=0, minimum=0, warnings=warnings, label="memoryVersion") or 0
    normalized["usage"] = normalize_usage_state(current.get("usage") if isinstance(current.get("usage"), dict) else {})
    if current.get("usage") is not None and not isinstance(current.get("usage"), dict):
        append_contract_warning(warnings, "usage was not an object; resetting usage counters.")
    normalized["loop"] = normalize_loop_snapshot(current.get("loop") if isinstance(current.get("loop"), dict) else {}, warnings)
    if current.get("loop") is not None and not isinstance(current.get("loop"), dict):
        append_contract_warning(warnings, "loop was not an object; resetting loop state.")
    normalized["lastUpdated"] = str(current.get("lastUpdated") or utc_now())
    normalized["contractWarnings"] = warnings[:20]
    return normalized


def read_state(paths: Optional[Paths] = None) -> Dict[str, Any]:
    paths = paths or project_paths()
    if metadata.postgres_enabled(paths.root):
        parsed = metadata.read_state_payload(paths.root, default_state())
    else:
        parsed = read_json_file(paths.state)
    if not isinstance(parsed, dict):
        return normalize_state_contract(default_state())
    return normalize_state_contract(parsed)


def parse_ts(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def default_job(config: Dict[str, Any]) -> Dict[str, Any]:
    warnings: List[str] = []
    dependency_ids = [
        str(value).strip()
        for value in (config.get("dependencyJobIds") or [])
        if str(value).strip()
    ] if isinstance(config.get("dependencyJobIds"), list) else []
    return {
        "jobId": config.get("jobId"),
        "taskId": config.get("taskId"),
        "jobType": str(config.get("jobType") or "loop"),
        "mode": config.get("mode") or "background",
        "status": config.get("status") or "queued",
        "target": config.get("target"),
        "batchId": config.get("batchId"),
        "queuePosition": coerce_int(config.get("queuePosition"), default=0, minimum=0, warnings=warnings, label="queuePosition") or 0,
        "attempt": coerce_int(config.get("attempt"), default=1, minimum=1, warnings=warnings, label="attempt") or 1,
        "resumeOfJobId": config.get("resumeOfJobId"),
        "retryOfJobId": config.get("retryOfJobId"),
        "resumeFromRound": coerce_int(config.get("resumeFromRound"), default=1, minimum=1, warnings=warnings, label="resumeFromRound") or 1,
        "rounds": coerce_int(config.get("rounds"), default=0, warnings=warnings, label="rounds") or 0,
        "delayMs": coerce_int(config.get("delayMs"), default=0, warnings=warnings, label="delayMs") or 0,
        "workerCount": coerce_int(config.get("workerCount"), default=0, minimum=0, warnings=warnings, label="workerCount") or 0,
        "cancelRequested": bool(config.get("cancelRequested") or False),
        "dependencyJobIds": dependency_ids,
        "dependencyMode": str(config.get("dependencyMode") or "all"),
        "partialSummary": bool(config.get("partialSummary") or False),
        "timeoutSeconds": coerce_int(config.get("timeoutSeconds"), default=300, minimum=30, warnings=warnings, label="timeoutSeconds") or 300,
        "queuedAt": config.get("queuedAt"),
        "startedAt": config.get("startedAt"),
        "finishedAt": config.get("finishedAt"),
        "lastHeartbeatAt": config.get("lastHeartbeatAt"),
        "completedRounds": coerce_int(config.get("completedRounds"), default=0, warnings=warnings, label="completedRounds") or 0,
        "currentRound": coerce_int(config.get("currentRound"), default=0, warnings=warnings, label="currentRound") or 0,
        "lastMessage": config.get("lastMessage") or "Queued.",
        "usage": normalize_usage_state(config.get("usage") if isinstance(config.get("usage"), dict) else {}),
        "results": config.get("results") if isinstance(config.get("results"), list) else [],
        "metadata": config.get("metadata") if isinstance(config.get("metadata"), dict) else {},
        "error": config.get("error"),
        "contractWarnings": warnings[:12],
    }


def read_jobs(paths: Optional[Paths] = None) -> List[Dict[str, Any]]:
    paths = paths or project_paths()
    jobs: List[Dict[str, Any]] = []
    if metadata.postgres_enabled(paths.root):
        for parsed in metadata.read_all_job_payloads(paths.root):
            if isinstance(parsed, dict):
                jobs.append(default_job(parsed))
        return jobs
    if not paths.jobs.exists():
        return []
    job_files = sorted(paths.jobs.glob("*.json"), key=lambda item: item.stat().st_mtime)
    for job_file in job_files:
        parsed = read_json_file(job_file)
        if isinstance(parsed, dict):
            jobs.append(default_job(parsed))
    return jobs


def job_status_is_active(status: Optional[str]) -> bool:
    return str(status or "") in {"queued", "running"}


def job_status_is_terminal(status: Optional[str]) -> bool:
    return str(status or "") in {"completed", "cancelled", "error", "budget_exhausted", "interrupted"}


def dispatch_target_label(job: Dict[str, Any]) -> str:
    target = str(job.get("target") or "target").lower()
    if target == "answer_now":
        return "Answer now"
    if target == "direct_baseline":
        return "Single-thread baseline"
    if target == "commander":
        return "Commander"
    if target == "commander_review":
        return "Commander review"
    if target == "summarizer":
        return "Summarizer (partial)" if job.get("partialSummary") else "Summarizer"
    if target == "arbiter":
        return "External arbiter"
    return f"Worker {target.upper()}"


def dispatch_dependency_failure_message(job: Dict[str, Any], jobs_by_id: Dict[str, Dict[str, Any]]) -> Optional[str]:
    for dependency_id in job.get("dependencyJobIds", []):
        dependency = jobs_by_id.get(dependency_id)
        if dependency is None:
            return f"Dependency {dependency_id} is missing."
        status = str(dependency.get("status") or "queued")
        if job_status_is_terminal(status) and status != "completed":
            return f"{dispatch_target_label(dependency)} finished with status {status}."
    return None


def dispatch_dependencies_completed(job: Dict[str, Any], jobs_by_id: Dict[str, Dict[str, Any]]) -> bool:
    for dependency_id in job.get("dependencyJobIds", []):
        dependency = jobs_by_id.get(dependency_id)
        if dependency is None or str(dependency.get("status") or "queued") != "completed":
            return False
    return True


def recover_dispatch_jobs_view(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    jobs = [copy.deepcopy(job) for job in jobs]
    jobs_by_id = {str(job.get("jobId") or ""): job for job in jobs}
    now = datetime.now(timezone.utc).timestamp()
    changed = True
    while changed:
        changed = False
        for job in jobs:
            if str(job.get("jobType") or "loop") != "target":
                continue
            status = str(job.get("status") or "queued")
            if status not in {"queued", "running"}:
                continue
            queue_ts = parse_ts(job.get("queuedAt"))
            heartbeat_ts = parse_ts(job.get("lastHeartbeatAt")) or parse_ts(job.get("startedAt")) or queue_ts
            has_dependencies = bool(job.get("dependencyJobIds"))
            waiting_on_dependencies = (
                status == "queued"
                and has_dependencies
                and dispatch_dependency_failure_message(job, jobs_by_id) is None
                and not dispatch_dependencies_completed(job, jobs_by_id)
            )
            queue_stale = (
                status == "queued"
                and not has_dependencies
                and not waiting_on_dependencies
                and queue_ts is not None
                and (now - queue_ts) > JOB_QUEUE_STALE_SECONDS
            )
            run_stale = status == "running" and heartbeat_ts is not None and (now - heartbeat_ts) > JOB_RUNNING_STALE_SECONDS
            failure = dispatch_dependency_failure_message(job, jobs_by_id)
            if queue_stale or run_stale:
                message = (
                    "Recovered a stale queued dispatch job. It can be retried."
                    if queue_stale
                    else "Recovered a stale running dispatch job. It can be retried."
                )
                job["status"] = "interrupted"
                job["finishedAt"] = utc_now()
                job["lastHeartbeatAt"] = utc_now()
                job["lastMessage"] = message
                job["error"] = message
                changed = True
            elif failure is not None:
                job["status"] = "interrupted"
                job["finishedAt"] = utc_now()
                job["lastHeartbeatAt"] = utc_now()
                job["lastMessage"] = "Dispatch stopped because a dependency failed."
                job["error"] = failure
                changed = True
    return jobs


def current_dispatch_state(state: Dict[str, Any], jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    task_id = str(((state.get("activeTask") or {}) if isinstance(state.get("activeTask"), dict) else {}).get("taskId") or "")
    if not task_id:
        return {
            "status": "idle",
            "activeJobs": [],
            "runningCount": 0,
            "queuedCount": 0,
            "partialCount": 0,
            "lastMessage": "Ready.",
            "providerTrace": None,
        }
    jobs = recover_dispatch_jobs_view(jobs)
    active_jobs = [
        default_job(job)
        for job in jobs
        if str(job.get("jobType") or "loop") == "target"
        and str(job.get("taskId") or "") == task_id
        and job_status_is_active(job.get("status"))
    ]
    if not active_jobs:
        return {
            "status": "idle",
            "activeJobs": [],
            "runningCount": 0,
            "queuedCount": 0,
            "partialCount": 0,
            "lastMessage": "Ready.",
            "providerTrace": None,
        }
    active_jobs.sort(key=lambda job: (0 if str(job.get("status")) == "running" else 1, parse_ts(job.get("queuedAt")) or 0))
    running_count = sum(1 for job in active_jobs if str(job.get("status")) == "running")
    queued_count = len(active_jobs) - running_count
    partial_count = sum(1 for job in active_jobs if job.get("partialSummary"))
    return {
        "status": "running" if running_count > 0 else "queued",
        "activeJobs": [
            {
                "jobId": job.get("jobId"),
                "taskId": job.get("taskId"),
                "target": job.get("target"),
                "targetLabel": dispatch_target_label(job),
                "status": job.get("status"),
                "schedulerState": str((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("schedulerState") or ""),
                "batchId": job.get("batchId"),
                "partialSummary": bool(job.get("partialSummary")),
                "queuedAt": job.get("queuedAt"),
                "startedAt": job.get("startedAt"),
                "lastHeartbeatAt": job.get("lastHeartbeatAt"),
                "lastMessage": job.get("lastMessage"),
                "provider": str((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("provider") or ""),
                "model": str((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("model") or ""),
                "workItemId": str((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("workItemId") or ""),
                "scheduleClass": str((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("scheduleClass") or ""),
                "plannedTarget": bool((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("plannedTarget")),
                "postTarget": bool((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("postTarget")),
                "dependencyJobIds": [
                    str(value).strip()
                    for value in (job.get("dependencyJobIds") or [])
                    if str(value).strip()
                ] if isinstance(job.get("dependencyJobIds"), list) else [],
                "providerTrace": normalize_provider_trace(((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {}).get("providerTrace")),
            }
            for job in active_jobs
        ],
        "runningCount": running_count,
        "queuedCount": queued_count,
        "partialCount": partial_count,
        "lastMessage": active_jobs[0].get("lastMessage") or "Dispatch in progress.",
        "providerTrace": normalize_provider_trace((((active_jobs[0].get("metadata") or {}) if isinstance(active_jobs[0].get("metadata"), dict) else {})).get("providerTrace")),
    }


def build_job_execution_health(job: Dict[str, Any]) -> Dict[str, Any]:
    status = str(job.get("status") or "unknown").strip().lower()
    mode = str(job.get("mode") or "").strip().lower()
    last_message = str(job.get("lastMessage") or "").strip()
    error = str(job.get("error") or "").strip()
    partial = bool(job.get("partialSummary"))
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    scheduler_state = str(metadata.get("schedulerState") or "").strip().lower()
    provider_label = str(metadata.get("provider") or "").strip().lower()
    failure_class = str(metadata.get("failureClass") or "").strip().lower()
    operator_note = str(metadata.get("operatorNote") or "").strip()
    dependency_failures = [
        str(item).strip()
        for item in (metadata.get("dependencyFailures") or [])
        if str(item).strip()
    ] if isinstance(metadata.get("dependencyFailures"), list) else []
    contract_warnings = [
        str(item).strip()
        for item in (job.get("contractWarnings") or [])
        if str(item).strip()
    ] if isinstance(job.get("contractWarnings"), list) else []

    if status in {"queued", "running"}:
        if scheduler_state == "waiting_on_key":
            label_provider = provider_label.upper() if provider_label else "Provider"
            return {
                "tone": "active",
                "label": "Key wait",
                "summary": last_message or f"Queued while waiting for {label_provider} key capacity.",
                "degraded": False,
            }
        if partial and dependency_failures:
            return {
                "tone": "active",
                "label": "Partial-risk",
                "summary": "Running a partial answer while failed lanes remain unresolved: " + ", ".join(dependency_failures) + ".",
                "degraded": True,
            }
        label = "Running" if status == "running" else "Queued"
        summary = last_message or ("Background work is active." if status == "running" else "Background work is queued.")
        return {
            "tone": "active",
            "label": label,
            "summary": summary,
            "degraded": False,
        }

    if status in {"interrupted", "error", "budget_exhausted"}:
        label_map = {
            "interrupted": "Interrupted",
            "error": "Error",
            "budget_exhausted": "Budget stop",
        }
        if failure_class == "provider_error":
            label_map["error"] = "Provider"
        elif failure_class == "output_exhausted":
            label_map["error"] = "Output cap"
        elif failure_class == "dependency_failure":
            label_map["interrupted"] = "Dependency"
        return {
            "tone": "error",
            "label": label_map.get(status, "Error"),
            "summary": last_message or operator_note or error or "This job ended in an explicit failure state.",
            "degraded": True,
        }

    if status == "cancelled":
        return {
            "tone": "warning",
            "label": "Cancelled",
            "summary": last_message or "This job was cancelled before completing.",
            "degraded": True,
        }

    if mode == "mock":
        return {
            "tone": "warning",
            "label": "Fallback",
            "summary": last_message or "This job completed with mock fallback output.",
            "degraded": True,
        }

    if partial:
        return {
            "tone": "warning" if dependency_failures else "recovered",
            "label": "Partial-risk" if dependency_failures else "Partial",
            "summary": (
                "Partial answer generated while failed lanes remained unresolved: " + ", ".join(dependency_failures) + "."
                if dependency_failures
                else (last_message or "This job produced a partial answer from current checkpoints.")
            ),
            "degraded": bool(dependency_failures),
        }

    if error:
        return {
            "tone": "warning",
            "label": "Warning",
            "summary": error,
            "degraded": True,
        }
    if failure_class == "provider_error":
        return {
            "tone": "error",
            "label": "Provider",
            "summary": operator_note or error or "The model provider returned a server-side error.",
            "degraded": True,
        }
    if failure_class == "output_exhausted":
        return {
            "tone": "warning",
            "label": "Output cap",
            "summary": operator_note or error or "Output-token recovery was exhausted for this job.",
            "degraded": True,
        }
    if failure_class == "dependency_failure" or dependency_failures:
        return {
            "tone": "warning",
            "label": "Dependency",
            "summary": operator_note or error or (
                "This job was created while failed lanes remained unresolved: " + ", ".join(dependency_failures) + "."
                if dependency_failures
                else "An upstream dependency failed before this job could complete."
            ),
            "degraded": True,
        }
    if contract_warnings:
        return {
            "tone": "warning",
            "label": "Contract",
            "summary": contract_warnings[0],
            "degraded": True,
        }

    return {
        "tone": "clean",
        "label": "Clean",
        "summary": last_message or "Completed without recorded degradation.",
        "degraded": False,
    }


def coerce_loop_state(state: Dict[str, Any], jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    current = copy.deepcopy(state)
    loop = dict(default_loop_state(), **(current.get("loop") if isinstance(current.get("loop"), dict) else {}))
    status = str(loop.get("status") or "idle")
    if status not in {"queued", "running"}:
        current["loop"] = loop
        return current
    job_id = str(loop.get("jobId") or "").strip()
    if not job_id:
        loop["status"] = "error"
        loop["finishedAt"] = utc_now()
        loop["lastHeartbeatAt"] = utc_now()
        loop["lastMessage"] = "Loop recovery failed: missing background job metadata."
        current["loop"] = loop
        return current
    jobs_by_id = {str(job.get("jobId") or ""): default_job(job) for job in jobs}
    job = jobs_by_id.get(job_id)
    if job is None:
        loop["status"] = "error"
        loop["finishedAt"] = utc_now()
        loop["lastHeartbeatAt"] = utc_now()
        loop["lastMessage"] = "Loop recovery failed: background job record is missing."
        current["loop"] = loop
        return current
    now = datetime.now(timezone.utc).timestamp()
    queue_ts = parse_ts(job.get("queuedAt"))
    heartbeat_ts = parse_ts(job.get("lastHeartbeatAt")) or parse_ts(job.get("startedAt")) or queue_ts
    queue_stale = str(job.get("status") or "") == "queued" and queue_ts is not None and (now - queue_ts) > JOB_QUEUE_STALE_SECONDS
    run_stale = str(job.get("status") or "") == "running" and heartbeat_ts is not None and (now - heartbeat_ts) > JOB_RUNNING_STALE_SECONDS
    if queue_stale or run_stale:
        message = (
            "Recovered a stale queued background loop. It can be resumed or retried."
            if queue_stale
            else "Recovered a stale running background loop. It can be resumed or retried."
        )
        loop.update(
            {
                "status": "interrupted",
                "jobId": job_id,
                "mode": job.get("mode") or loop.get("mode") or "background",
                "totalRounds": int(job.get("rounds") or loop.get("totalRounds") or 0),
                "completedRounds": int(job.get("completedRounds") or loop.get("completedRounds") or 0),
                "currentRound": 0,
                "delayMs": int(job.get("delayMs") or loop.get("delayMs") or 0),
                "cancelRequested": bool(job.get("cancelRequested") or False),
                "queuedAt": job.get("queuedAt") or loop.get("queuedAt"),
                "startedAt": job.get("startedAt") or loop.get("startedAt"),
                "finishedAt": utc_now(),
                "lastHeartbeatAt": utc_now(),
                "lastMessage": message,
                "providerTrace": normalize_provider_trace((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("providerTrace")),
            }
        )
    elif job_status_is_terminal(job.get("status")) or status != str(job.get("status") or status):
        loop.update(
            {
                "status": job.get("status") or status,
                "jobId": job_id,
                "mode": job.get("mode") or loop.get("mode") or "background",
                "totalRounds": int(job.get("rounds") or loop.get("totalRounds") or 0),
                "completedRounds": int(job.get("completedRounds") or loop.get("completedRounds") or 0),
                "currentRound": int(job.get("currentRound") or 0),
                "delayMs": int(job.get("delayMs") or loop.get("delayMs") or 0),
                "cancelRequested": bool(job.get("cancelRequested") or False),
                "queuedAt": job.get("queuedAt") or loop.get("queuedAt"),
                "startedAt": job.get("startedAt") or loop.get("startedAt"),
                "finishedAt": job.get("finishedAt") or loop.get("finishedAt"),
                "lastHeartbeatAt": job.get("lastHeartbeatAt") or loop.get("lastHeartbeatAt"),
                "lastMessage": job.get("lastMessage") or loop.get("lastMessage") or "Ready.",
                "providerTrace": normalize_provider_trace((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("providerTrace"))
                or normalize_provider_trace(loop.get("providerTrace")),
            }
        )
    job_provider_trace = normalize_provider_trace((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("providerTrace"))
    if job_provider_trace and not normalize_provider_trace(loop.get("providerTrace")):
        loop["providerTrace"] = job_provider_trace
    current["loop"] = loop
    return current


def read_state_payload(paths: Optional[Paths] = None) -> Dict[str, Any]:
    paths = paths or project_paths()
    jobs = read_jobs(paths)
    state = coerce_loop_state(read_state(paths), jobs)
    active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    active_task_id = str((active_task or {}).get("taskId") or "").strip()
    if active_task_id:
        task_state = read_task_state_payload(active_task_id, paths)
        if isinstance(task_state, dict):
            for field in ("activeTask", "commander", "commanderReview", "workers", "directBaseline", "summary", "arbiter", "usage", "memoryVersion"):
                state[field] = copy.deepcopy(task_state.get(field))
            scoped_loop = task_state.get("loop") if isinstance(task_state.get("loop"), dict) else None
            if isinstance(scoped_loop, dict):
                global_loop = state.get("loop") if isinstance(state.get("loop"), dict) else {}
                if str(global_loop.get("status") or "idle") == "idle" or str(scoped_loop.get("jobId") or "").strip() == str(global_loop.get("jobId") or "").strip():
                    state["loop"] = copy.deepcopy(scoped_loop)
            state["lastUpdated"] = str(task_state.get("lastUpdated") or state.get("lastUpdated") or utc_now())
    step_report = read_recent_jsonl_report(paths.steps, 400)
    event_report = read_recent_jsonl_report(paths.events, 200)
    state["executionHealth"] = build_execution_health(state, paths, step_report=step_report)
    contract_warnings = [
        str(item).strip()
        for item in (state.get("contractWarnings") or [])
        if str(item).strip()
    ][:20] if isinstance(state.get("contractWarnings"), list) else []
    for warning in list(step_report.get("warnings") or []) + list(event_report.get("warnings") or []):
        append_contract_warning(contract_warnings, warning)
    state["contractWarnings"] = contract_warnings[:20]
    active_task = state.get("activeTask")
    if isinstance(active_task, dict):
        enriched_task = copy.deepcopy(active_task)
        enriched_task["stateWorkers"] = copy.deepcopy(state.get("workers") or {})
        enriched_task["stateCommander"] = copy.deepcopy(state.get("commander"))
        enriched_task["stateCommanderReview"] = copy.deepcopy(state.get("commanderReview"))
        enriched_task["directBaseline"] = copy.deepcopy(state.get("directBaseline"))
        enriched_task["summary"] = copy.deepcopy(state.get("summary"))
        enriched_task["arbiter"] = copy.deepcopy(state.get("arbiter"))
        enriched_task["executionHealth"] = copy.deepcopy(state.get("executionHealth") or {})
        enriched_task["contractWarnings"] = copy.deepcopy(state.get("contractWarnings") or [])
        state["activeTask"] = enriched_task
    state["dispatch"] = current_dispatch_state(state, jobs)
    return state


def read_task_state_payload(task_id: str, paths: Optional[Paths] = None) -> Optional[Dict[str, Any]]:
    paths = paths or project_paths()
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return None
    parsed = read_json_file(paths.task_states / f"{normalized_task_id}.json")
    if not isinstance(parsed, dict):
        return None
    state = coerce_loop_state(
        normalize_state_contract(parsed),
        [
            job
            for job in read_jobs(paths)
            if str((job or {}).get("taskId") or "").strip() == normalized_task_id
        ],
    )
    state["dispatch"] = current_dispatch_state(state, read_jobs(paths))
    return state


def artifact_visibility_policy() -> Dict[str, Any]:
    return {
        "publicThread": "structured_only",
        "reviewSurface": "raw_output_exception",
        "exportSurface": "raw_output_exception",
        "rules": [
            "Home and canonical memory render only normalized structured outputs and adjudicated answers.",
            "Raw model text is a review-only exception and is limited to saved output artifacts plus export bundles.",
            "Carry-forward context, task snapshots, worker checkpoints, and summary state must stay structured.",
            "When raw output is shown in Review, it is for auditability and replay, not as the canonical source of truth.",
        ],
    }


ARTIFACT_PATTERNS = [
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_([A-Z])_step(\d+)_output\.json$", re.I), "worker_output", lambda m: m.group(2), lambda m: int(m.group(3))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_commander_round(\d+)_output\.json$", re.I), "commander_output", lambda m: "commander", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_direct_baseline_round(\d+)_output\.json$", re.I), "direct_baseline_output", lambda m: "direct_baseline", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_commander_review_round(\d+)_output\.json$", re.I), "commander_review_output", lambda m: "commander-review", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_summary_partial_round(\d+)_output\.json$", re.I), "summary_partial_output", lambda m: "summary-partial", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_summary_round(\d+)_output\.json$", re.I), "summary_output", lambda m: "summary", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_([A-Z])_step(\d+)\.json$", re.I), "worker_step", lambda m: m.group(2), lambda m: int(m.group(3))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_commander_round(\d+)\.json$", re.I), "commander_round", lambda m: "commander", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_direct_baseline_round(\d+)\.json$", re.I), "direct_baseline_round", lambda m: "direct_baseline", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_commander_review_round(\d+)\.json$", re.I), "commander_review_round", lambda m: "commander-review", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_summary_partial_round(\d+)\.json$", re.I), "summary_partial_round", lambda m: "summary-partial", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_summary_round(\d+)\.json$", re.I), "summary_round", lambda m: "summary", lambda m: int(m.group(2))),
]


def build_artifact_history_entry(name: str, modified_at: str, size: int, content: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if "_step" not in name and "_round" not in name:
        return None
    warnings: List[str] = []
    entry: Dict[str, Any] = {
        "name": name,
        "modifiedAt": modified_at,
        "size": coerce_int(size, default=0, minimum=0, warnings=warnings, label=f"{name}.size") or 0,
        "kind": "artifact",
        "taskId": None,
        "worker": None,
        "roundOrStep": None,
        "provider": None,
        "providerCapabilities": {},
        "model": None,
        "mode": None,
        "responseId": None,
        "providerTrace": None,
        "requestedMaxOutputTokens": None,
        "effectiveMaxOutputTokens": None,
        "maxOutputTokenAttempts": [],
        "recoveredFromIncomplete": False,
        "rawOutputAvailable": False,
        "contractWarnings": [],
    }
    for pattern, kind, worker_fn, round_fn in ARTIFACT_PATTERNS:
        match = pattern.match(name)
        if match:
            entry["taskId"] = match.group(1)
            entry["worker"] = worker_fn(match)
            entry["kind"] = kind
            entry["roundOrStep"] = round_fn(match)
            break
    if isinstance(content, dict):
        response_meta = content.get("responseMeta") if isinstance(content.get("responseMeta"), dict) else {}
        provider_trace = normalize_provider_trace(response_meta.get("providerTrace"))
        entry["provider"] = content.get("provider")
        entry["providerCapabilities"] = content.get("providerCapabilities") if isinstance(content.get("providerCapabilities"), dict) else {}
        entry["model"] = content.get("model") or content.get("modelUsed")
        entry["mode"] = content.get("mode")
        entry["responseId"] = content.get("responseId") or (provider_trace.get("providerResponseId") if isinstance(provider_trace, dict) else None)
        entry["providerTrace"] = provider_trace
        entry["requestedMaxOutputTokens"] = coerce_int(
            response_meta.get("requestedMaxOutputTokens"),
            allow_none=True,
            warnings=warnings,
            label=f"{name}.responseMeta.requestedMaxOutputTokens",
        )
        entry["effectiveMaxOutputTokens"] = coerce_int(
            response_meta.get("effectiveMaxOutputTokens"),
            allow_none=True,
            warnings=warnings,
            label=f"{name}.responseMeta.effectiveMaxOutputTokens",
        )
        entry["maxOutputTokenAttempts"] = coerce_int_list(
            response_meta.get("maxOutputTokenAttempts"),
            warnings=warnings,
            label=f"{name}.responseMeta.maxOutputTokenAttempts",
        )
        entry["recoveredFromIncomplete"] = bool(response_meta.get("recoveredFromIncomplete"))
        entry["rawOutputAvailable"] = bool(str(content.get("rawOutputText") or "").strip())
    entry["contractWarnings"] = warnings[:12]
    return entry


def read_task_snapshot(task_id: str, paths: Optional[Paths] = None) -> Optional[Dict[str, Any]]:
    paths = paths or project_paths()
    if metadata.postgres_enabled(paths.root):
        return metadata.read_task_payload(paths.root, task_id)
    return read_json_file(paths.tasks / f"{task_id}.json")


def list_session_archives(paths: Optional[Paths] = None, max_items: int = 10) -> List[Dict[str, Any]]:
    paths = paths or project_paths()
    archives: List[Dict[str, Any]] = []
    files = artifacts.list_json_artifacts(paths.root, ["sessions"])
    for file in files[: max(0, max_items)]:
        archive = artifacts.read_json_artifact(paths.root, "sessions", str(file.get("name") or ""))
        if not isinstance(archive, dict):
            continue
        warnings: List[str] = []
        carry_context = str(archive.get("carryContext") or "").strip()
        archived_at = str(archive.get("archivedAt") or archive.get("createdAt") or file.get("modifiedAt") or "").strip() or None
        if archive.get("summaryRound") not in (None, "") and coerce_int(archive.get("summaryRound"), allow_none=True) is None:
            append_contract_warning(warnings, f"{file.get('name') or 'archive'} had an invalid summaryRound value.")
        archives.append(
            {
                "file": str(file.get("name") or ""),
                "createdAt": archive.get("createdAt"),
                "archivedAt": archived_at,
                "taskId": archive.get("taskId"),
                "objective": str(archive.get("objective") or "").strip(),
                "reason": str(archive.get("reason") or "unspecified").strip() or "unspecified",
                "summaryRound": coerce_int(archive.get("summaryRound"), default=0, minimum=0, warnings=warnings, label=f"{file.get('name') or 'archive'}.summaryRound") or 0,
                "carryContextPreview": carry_context[:320],
                "contractWarnings": warnings[:12],
            }
        )
    return archives


def count_session_archives(paths: Optional[Paths] = None) -> int:
    paths = paths or project_paths()
    return sum(1 for entry in artifacts.list_json_artifacts(paths.root, ["sessions"]) if str(entry.get("name") or "").strip())


def build_history_payload(paths: Optional[Paths] = None, max_jobs: int = 12, max_artifacts: int = 30, max_rounds: int = 12, max_sessions: int = 10) -> Dict[str, Any]:
    paths = paths or project_paths()
    state = read_state_payload(paths)
    recovery_warning = None
    loop_message = str(((state.get("loop") or {}) if isinstance(state.get("loop"), dict) else {}).get("lastMessage") or "")
    if "Recovery check deferred:" in loop_message:
        recovery_warning = loop_message

    task_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def load_task(task_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not task_id:
            return None
        if task_id not in task_cache:
            task_cache[task_id] = read_task_snapshot(task_id, paths)
        return task_cache[task_id]

    jobs = sorted(read_jobs(paths), key=lambda job: parse_ts(job.get("queuedAt")) or 0, reverse=True)
    jobs_out: List[Dict[str, Any]] = []
    for job in jobs[:max_jobs]:
        task = load_task(str(job.get("taskId") or ""))
        is_target_job = str(job.get("jobType") or "loop") == "target"
        jobs_out.append(
            {
                "jobId": job.get("jobId"),
                "taskId": job.get("taskId"),
                "jobType": job.get("jobType") or "loop",
                "target": job.get("target"),
                "batchId": job.get("batchId"),
                "partialSummary": bool(job.get("partialSummary")),
                "schedulerState": str((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("schedulerState") or ""),
                "objective": (task or {}).get("objective"),
                "status": job.get("status"),
                "mode": job.get("mode"),
                "workerCount": int(job.get("workerCount") or 0),
                "rounds": int(job.get("rounds") or 0),
                "completedRounds": int(job.get("completedRounds") or 0),
                "resumeFromRound": int(job.get("resumeFromRound") or 1),
                "queuePosition": int(job.get("queuePosition") or 0),
                "attempt": int(job.get("attempt") or 1),
                "resumeOfJobId": job.get("resumeOfJobId"),
                "retryOfJobId": job.get("retryOfJobId"),
                "queuedAt": job.get("queuedAt"),
                "startedAt": job.get("startedAt"),
                "finishedAt": job.get("finishedAt"),
                "lastHeartbeatAt": job.get("lastHeartbeatAt"),
                "lastMessage": job.get("lastMessage"),
                "provider": str((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("provider") or ""),
                "model": str((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("model") or ""),
                "workItemId": str((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("workItemId") or ""),
                "scheduleClass": str((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("scheduleClass") or ""),
                "plannedTarget": bool((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("plannedTarget")),
                "postTarget": bool((((job.get("metadata") or {}) if isinstance(job.get("metadata"), dict) else {})).get("postTarget")),
                "dependencyJobIds": [
                    str(value).strip()
                    for value in (job.get("dependencyJobIds") or [])
                    if str(value).strip()
                ] if isinstance(job.get("dependencyJobIds"), list) else [],
                "totalTokens": int(((job.get("usage") or {}) if isinstance(job.get("usage"), dict) else {}).get("totalTokens") or 0),
                "estimatedCostUsd": float(((job.get("usage") or {}) if isinstance(job.get("usage"), dict) else {}).get("estimatedCostUsd") or 0.0),
                "error": job.get("error"),
                "executionHealth": build_job_execution_health(job),
                "contractWarnings": (job.get("contractWarnings") or [])[:12] if isinstance(job.get("contractWarnings"), list) else [],
                "canResume": (not is_target_job) and str(job.get("status") or "") == "interrupted",
                "canRetry": (not is_target_job) and str(job.get("status") or "") in {"interrupted", "error", "budget_exhausted", "cancelled", "completed"},
                "canCancel": (not is_target_job) and str(job.get("status") or "") in {"queued", "interrupted"},
            }
        )

    artifact_files = artifacts.list_json_artifacts(paths.root, ["checkpoints", "outputs"])

    artifact_entries: List[Dict[str, Any]] = []
    round_groups: Dict[str, Dict[str, Any]] = {}
    for artifact_file in artifact_files:
        content = artifacts.read_json_artifact(paths.root, str(artifact_file.get("category") or ""), str(artifact_file.get("name") or ""))
        entry = build_artifact_history_entry(
            str(artifact_file.get("name") or ""),
            str(artifact_file.get("modifiedAt") or ""),
            int(artifact_file.get("size") or 0),
            content,
        )
        if entry is None:
            continue
        artifact_out = dict(entry)
        artifact_entries.append(artifact_out)
        if (
            entry.get("taskId") is not None
            and entry.get("roundOrStep") is not None
            and str(entry.get("kind") or "") in {"worker_output", "commander_output", "direct_baseline_output", "commander_review_output", "summary_output", "summary_partial_output"}
        ):
            round_key = f"{entry['taskId']}:{int(entry['roundOrStep'])}"
            if round_key not in round_groups:
                task = load_task(str(entry.get("taskId") or ""))
                round_groups[round_key] = {
                    "taskId": entry["taskId"],
                    "objective": (task or {}).get("objective"),
                    "round": int(entry["roundOrStep"]),
                    "capturedAt": entry["modifiedAt"],
                    "commanderArtifact": None,
                    "directBaselineArtifact": None,
                    "commanderReviewArtifact": None,
                    "summaryArtifact": None,
                    "workerArtifacts": [],
                    "_healthArtifacts": [],
                }
            if entry["kind"] == "commander_output":
                round_groups[round_key]["commanderArtifact"] = artifact_out
            elif entry["kind"] == "direct_baseline_output":
                round_groups[round_key]["directBaselineArtifact"] = artifact_out
            elif entry["kind"] == "commander_review_output":
                round_groups[round_key]["commanderReviewArtifact"] = artifact_out
            elif entry["kind"] in {"summary_output", "summary_partial_output"}:
                round_groups[round_key]["summaryArtifact"] = artifact_out
            else:
                round_groups[round_key]["workerArtifacts"].append(artifact_out)
            round_groups[round_key]["_healthArtifacts"].append(artifact_out)
            if entry["modifiedAt"] > round_groups[round_key]["capturedAt"]:
                round_groups[round_key]["capturedAt"] = entry["modifiedAt"]
        if len(artifact_entries) >= max_artifacts:
            break

    rounds = list(round_groups.values())
    rounds.sort(key=lambda item: (str(item.get("capturedAt") or ""), int(item.get("round") or 0)), reverse=True)
    rounds = rounds[:max_rounds]
    for round_entry in rounds:
        round_entry["workerArtifacts"].sort(key=lambda item: str(item.get("worker") or ""))
        round_entry["executionHealth"] = build_round_execution_health(round_entry.get("_healthArtifacts") or [])
        round_entry.pop("_healthArtifacts", None)

    return {
        "jobs": jobs_out,
        "dispatch": state.get("dispatch"),
        "artifacts": artifact_entries,
        "rounds": rounds,
        "sessions": list_session_archives(paths, max_sessions),
        "sessionArchiveCount": count_session_archives(paths),
        "contractWarnings": (state.get("contractWarnings") or [])[:20] if isinstance(state.get("contractWarnings"), list) else [],
        "artifactPolicy": artifact_visibility_policy(),
        "queueLimit": LOOP_QUEUE_LIMIT,
        "recoveryWarning": recovery_warning,
    }


def tail_text_lines(path: Path, limit: int, empty_message: str) -> str:
    raw = read_text(path)
    if raw is None:
        return empty_message
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        return empty_message
    return "\n".join(reversed(lines[-limit:]))


def _count_label(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def read_recent_jsonl_report(path: Path, limit: int = 400) -> Dict[str, Any]:
    raw = read_text(path)
    report: Dict[str, Any] = {
        "entries": [],
        "warnings": [],
        "lineCount": 0,
        "parsedCount": 0,
        "malformedLineCount": 0,
        "nonObjectCount": 0,
    }
    if raw is None:
        return report
    lines = [line for line in raw.splitlines() if line.strip()]
    report["lineCount"] = len(lines)
    selected_lines = lines[-max(0, limit):]
    entries: List[Dict[str, Any]] = []
    malformed = 0
    non_object = 0
    for line in selected_lines:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(parsed, dict):
            non_object += 1
            continue
        entries.append(parsed)
    report["entries"] = entries
    report["parsedCount"] = len(entries)
    report["malformedLineCount"] = malformed
    report["nonObjectCount"] = non_object
    if malformed:
        append_contract_warning(
            report["warnings"],
            f"{path.name} dropped {_count_label(malformed, 'malformed JSONL line', 'malformed JSONL lines')} from the recent telemetry window.",
        )
    if non_object:
        append_contract_warning(
            report["warnings"],
            f"{path.name} dropped {_count_label(non_object, 'non-object telemetry entry', 'non-object telemetry entries')} from the recent telemetry window.",
        )
    return report


def read_recent_jsonl_entries(path: Path, limit: int = 400) -> List[Dict[str, Any]]:
    return list(read_recent_jsonl_report(path, limit).get("entries") or [])


def step_target_id(stage: Any) -> Optional[str]:
    text = str(stage or "").strip().lower()
    if text in {"commander", "commander_review", "summarizer", "direct_baseline"}:
        return text
    match = re.fullmatch(r"worker_([a-z])", text)
    if match:
        return match.group(1).upper()
    return None


def execution_target_label(target_id: str, active_task: Optional[Dict[str, Any]]) -> str:
    normalized = str(target_id or "").strip()
    if normalized == "commander":
        return "Commander"
    if normalized == "direct_baseline":
        return "Direct baseline"
    if normalized == "commander_review":
        return "Commander Review"
    if normalized == "summarizer":
        return "Summarizer"
    workers = active_task.get("workers") if isinstance(active_task, dict) and isinstance(active_task.get("workers"), list) else []
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        if str(worker.get("id") or "").strip().upper() == normalized.upper():
            label = str(worker.get("label") or worker.get("type") or normalized).strip()
            return f"{normalized.upper()} / {label}" if label else normalized.upper()
    return normalized.upper()


def build_execution_health(
    state: Dict[str, Any],
    paths: Paths,
    step_limit: int = 400,
    step_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    task_id = str((active_task or {}).get("taskId") or "").strip()
    base = {
        "degraded": False,
        "issueCount": 0,
        "fallbackCount": 0,
        "recoveredCount": 0,
        "latestIssue": None,
        "targets": {},
    }
    if not task_id:
        return base

    report = step_report if isinstance(step_report, dict) else read_recent_jsonl_report(paths.steps, step_limit)
    latest_issue: Optional[Dict[str, Any]] = None
    latest_issue_ts = ""
    targets: Dict[str, Dict[str, Any]] = {}
    for entry in report.get("entries") or []:
        context = entry.get("context") if isinstance(entry.get("context"), dict) else {}
        if str(context.get("taskId") or "").strip() != task_id:
            continue
        target_id = step_target_id(entry.get("stage"))
        if not target_id:
            continue
        message = str(entry.get("message") or "").strip()
        message_lower = message.lower()
        ts = str(entry.get("ts") or "").strip()
        mode = str(context.get("mode") or "").strip() or None
        recovered = bool(context.get("recoveredFromIncomplete"))
        fallback = "falling back to mock" in message_lower or mode == "mock"
        errored = "failed and was not downgraded to mock" in message_lower or message_lower.startswith("budget stopped")
        degraded = fallback or recovered or errored
        existing = targets.get(target_id)
        target_degraded = bool((existing or {}).get("degraded")) or degraded
        target_fallback = bool((existing or {}).get("usedMockFallback")) or fallback
        target_recovered = bool((existing or {}).get("recoveredFromIncomplete")) or recovered
        target_errored = str((existing or {}).get("status") or "") == "error" or errored
        status = "error" if target_errored else ("degraded" if target_degraded else "completed")
        target_entry = {
            "target": target_id,
            "label": execution_target_label(target_id, active_task),
            "status": status,
            "mode": mode or ((existing or {}).get("mode")),
            "degraded": target_degraded,
            "usedMockFallback": target_fallback,
            "recoveredFromIncomplete": target_recovered,
            "lastError": str(context.get("error") or "").strip() or ((existing or {}).get("lastError")) or None,
            "lastMessage": message or ((existing or {}).get("lastMessage")) or "",
            "updatedAt": ts or ((existing or {}).get("updatedAt")) or None,
        }
        targets[target_id] = target_entry
        if target_degraded and ts >= latest_issue_ts:
            latest_issue_ts = ts
            latest_issue = dict(target_entry)

    fallback_count = sum(1 for target in targets.values() if bool(target.get("usedMockFallback")))
    recovered_count = sum(1 for target in targets.values() if bool(target.get("recoveredFromIncomplete")))
    issue_count = sum(1 for target in targets.values() if bool(target.get("degraded")))
    return {
        "degraded": issue_count > 0,
        "issueCount": issue_count,
        "fallbackCount": fallback_count,
        "recoveredCount": recovered_count,
        "latestIssue": latest_issue,
        "targets": targets,
    }


def build_round_execution_health(artifacts_for_round: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest_issue: Optional[Dict[str, Any]] = None
    latest_issue_ts = ""
    fallback_count = 0
    recovered_count = 0
    issue_count = 0
    targets: Dict[str, Dict[str, Any]] = {}
    for artifact in artifacts_for_round:
        target = str(artifact.get("worker") or "").strip()
        if not target:
            continue
        label = execution_target_label(target, None)
        mode = str(artifact.get("mode") or "").strip() or None
        recovered = bool(artifact.get("recoveredFromIncomplete"))
        fallback = mode == "mock"
        contract_warnings = [
            str(item).strip()
            for item in (artifact.get("contractWarnings") or [])
            if str(item).strip()
        ] if isinstance(artifact.get("contractWarnings"), list) else []
        degraded = fallback or recovered or bool(contract_warnings)
        if fallback:
            fallback_count += 1
        if recovered:
            recovered_count += 1
        if degraded:
            issue_count += 1
        target_entry = {
            "target": target,
            "label": label,
            "status": "degraded" if degraded else "completed",
            "mode": mode,
            "degraded": degraded,
            "usedMockFallback": fallback,
            "recoveredFromIncomplete": recovered,
            "lastError": None,
            "lastMessage": (
                "Used mock fallback for this artifact."
                if fallback
                else (
                    "Recovered after output-token escalation."
                    if recovered
                    else (contract_warnings[0] if contract_warnings else "Completed without degradation.")
                )
            ),
            "updatedAt": str(artifact.get("modifiedAt") or "").strip() or None,
            "contractWarnings": contract_warnings[:12],
        }
        targets[target] = target_entry
        ts = str(artifact.get("modifiedAt") or "").strip()
        if degraded and ts >= latest_issue_ts:
            latest_issue_ts = ts
            latest_issue = dict(target_entry)
    return {
        "degraded": issue_count > 0,
        "issueCount": issue_count,
        "fallbackCount": fallback_count,
        "recoveredCount": recovered_count,
        "latestIssue": latest_issue,
        "targets": targets,
    }


def read_artifact(paths: Optional[Paths], name: str) -> Dict[str, Any]:
    paths = paths or project_paths()
    safe_name = Path(name).name
    if not safe_name.endswith(".json"):
        raise FileNotFoundError("A valid artifact filename is required.")
    location = None
    bucket_name = None
    content: Optional[Dict[str, Any]] = None
    modified_at: Optional[str] = None
    size = 0
    for bucket in ("outputs", "checkpoints"):
        content = artifacts.read_json_artifact(paths.root, bucket, safe_name)
        if isinstance(content, dict):
            bucket_name = bucket
            for entry in artifacts.list_json_artifacts(paths.root, [bucket]):
                if str(entry.get("name") or "") == safe_name:
                    modified_at = str(entry.get("modifiedAt") or "")
                    size = int(entry.get("size") or 0)
                    break
            if not modified_at:
                modified_at = utc_now()
            break
    if content is None or bucket_name is None:
        raise FileNotFoundError("Artifact not found.")
    warnings: List[str] = []
    response_meta = content.get("responseMeta") if isinstance(content.get("responseMeta"), dict) else {}
    provider_trace = normalize_provider_trace(response_meta.get("providerTrace"))
    kind = str(content.get("artifactType") or "").strip() or "artifact"
    if kind == "artifact":
        if re.search(r"_summary_round\d+\.json$", safe_name, re.I):
            kind = "summary_round"
        elif re.search(r"_[A-Z]_step\d+\.json$", safe_name, re.I):
            kind = "worker_step"
    return {
        "name": safe_name,
        "kind": kind,
        "storage": bucket_name,
        "modifiedAt": modified_at,
        "size": coerce_int(size, default=0, minimum=0, warnings=warnings, label=f"{safe_name}.size") or 0,
        "summary": {
            "taskId": content.get("taskId"),
            "target": content.get("target") or content.get("workerId"),
            "label": content.get("label"),
            "mode": content.get("mode"),
            "provider": content.get("provider"),
            "providerCapabilities": content.get("providerCapabilities") if isinstance(content.get("providerCapabilities"), dict) else {},
            "model": content.get("model") or content.get("modelUsed"),
            "step": coerce_int(content.get("step"), allow_none=True, warnings=warnings, label=f"{safe_name}.step"),
            "round": coerce_int(content.get("round"), allow_none=True, warnings=warnings, label=f"{safe_name}.round"),
            "responseId": content.get("responseId") or (provider_trace.get("providerResponseId") if isinstance(provider_trace, dict) else None),
            "providerTrace": provider_trace,
            "requestedMaxOutputTokens": coerce_int(
                response_meta.get("requestedMaxOutputTokens"),
                allow_none=True,
                warnings=warnings,
                label=f"{safe_name}.responseMeta.requestedMaxOutputTokens",
            ),
            "effectiveMaxOutputTokens": coerce_int(
                response_meta.get("effectiveMaxOutputTokens"),
                allow_none=True,
                warnings=warnings,
                label=f"{safe_name}.responseMeta.effectiveMaxOutputTokens",
            ),
            "maxOutputTokenAttempts": coerce_int_list(
                response_meta.get("maxOutputTokenAttempts"),
                warnings=warnings,
                label=f"{safe_name}.responseMeta.maxOutputTokenAttempts",
            ),
            "recoveredFromIncomplete": bool(response_meta.get("recoveredFromIncomplete")),
            "localToolCalls": (response_meta.get("localToolCalls") or [])[:12] if isinstance(response_meta.get("localToolCalls"), list) else [],
            "localFileSources": list(response_meta.get("localFileSources") or []) if isinstance(response_meta.get("localFileSources"), list) else [],
            "githubToolCalls": (response_meta.get("githubToolCalls") or [])[:12] if isinstance(response_meta.get("githubToolCalls"), list) else [],
            "githubSources": list(response_meta.get("githubSources") or []) if isinstance(response_meta.get("githubSources"), list) else [],
            "rawOutputAvailable": bool(str(content.get("rawOutputText") or "").strip()),
            "contractWarnings": warnings[:12],
        },
        "policy": artifact_visibility_policy(),
        "content": content,
    }


def _load_eval_manifest_catalog(directory: Path, id_key: str, title_key: str, extras: callable) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    seen: set[str] = set()
    if not directory.exists():
        return {"items": items, "errors": errors}
    for file_path in sorted(directory.glob("*.json")):
        try:
            manifest = read_json_file(file_path)
            if not isinstance(manifest, dict):
                raise ValueError(f"Manifest is empty or invalid JSON: {file_path.name}")
            manifest_id = str(manifest.get(id_key) or "").strip()
            title = str(manifest.get(title_key) or "").strip()
            if not manifest_id:
                raise ValueError(f"Missing {id_key} in {file_path.name}")
            if not title:
                raise ValueError(f"Missing {title_key} in {file_path.name}")
            if manifest_id in seen:
                raise ValueError(f"Duplicate {id_key} {manifest_id} across manifest files.")
            seen.add(manifest_id)
            item = {id_key: manifest_id, "title": title, "file": file_path.name}
            item.update(extras(manifest))
            items.append(item)
        except Exception as exc:  # noqa: BLE001
            errors.append({"file": file_path.name, "message": str(exc)})
    items.sort(key=lambda item: str(item.get("title") or ""))
    return {"items": items, "errors": errors}


def load_eval_suite_catalog(paths: Optional[Paths] = None) -> Dict[str, Any]:
    paths = paths or project_paths()
    return _load_eval_manifest_catalog(
        paths.eval_suites,
        "suiteId",
        "title",
        lambda manifest: {
            "description": str(manifest.get("description") or "").strip(),
            "caseCount": len(manifest.get("cases") or []) if isinstance(manifest.get("cases"), list) else 0,
            "cases": [
                {
                    "caseId": str(case.get("caseId") or "").strip(),
                    "title": str(case.get("title") or case.get("caseId") or "").strip(),
                }
                for case in (manifest.get("cases") or [])
                if isinstance(case, dict) and str(case.get("caseId") or "").strip()
            ],
        },
    )


def load_eval_arm_catalog(paths: Optional[Paths] = None) -> Dict[str, Any]:
    paths = paths or project_paths()
    return _load_eval_manifest_catalog(
        paths.eval_arms,
        "armId",
        "title",
        lambda manifest: {
            "description": str(manifest.get("description") or "").strip(),
            "type": str(manifest.get("type") or "").strip(),
            "contextMode": ((manifest.get("runtime") or {}) if isinstance(manifest.get("runtime"), dict) else {}).get("contextMode"),
            "directBaselineMode": ((manifest.get("runtime") or {}) if isinstance(manifest.get("runtime"), dict) else {}).get("directBaselineMode"),
            "provider": ((manifest.get("runtime") or {}) if isinstance(manifest.get("runtime"), dict) else {}).get("provider"),
            "model": ((manifest.get("runtime") or {}) if isinstance(manifest.get("runtime"), dict) else {}).get("model"),
            "directProvider": ((manifest.get("runtime") or {}) if isinstance(manifest.get("runtime"), dict) else {}).get("directProvider"),
            "directModel": ((manifest.get("runtime") or {}) if isinstance(manifest.get("runtime"), dict) else {}).get("directModel"),
            "summarizerProvider": ((manifest.get("runtime") or {}) if isinstance(manifest.get("runtime"), dict) else {}).get("summarizerProvider"),
            "summarizerModel": ((manifest.get("runtime") or {}) if isinstance(manifest.get("runtime"), dict) else {}).get("summarizerModel"),
            "reasoningEffort": str((((manifest.get("runtime") or {}) if isinstance(manifest.get("runtime"), dict) else {}).get("reasoningEffort")) or "low"),
            "workerCount": len(manifest.get("workers") or []) if isinstance(manifest.get("workers"), list) else 0,
            "workers": [
                {
                    "id": worker.get("id"),
                    "type": worker.get("type"),
                    "label": worker.get("label"),
                    "model": worker.get("model"),
                }
                for worker in (manifest.get("workers") or [])
                if isinstance(worker, dict)
            ],
        },
    )


def read_eval_run(paths: Optional[Paths], run_id: str) -> Optional[Dict[str, Any]]:
    paths = paths or project_paths()
    if metadata.postgres_enabled(paths.root):
        return metadata.read_eval_run_payload(paths.root, run_id)
    return read_json_file(paths.eval_runs / run_id / "run.json")


def list_eval_runs(paths: Optional[Paths] = None) -> List[Dict[str, Any]]:
    paths = paths or project_paths()
    if metadata.postgres_enabled(paths.root):
        return metadata.read_all_eval_run_payloads(paths.root)
    runs: List[Dict[str, Any]] = []
    if not paths.eval_runs.exists():
        return runs
    files = list(paths.eval_runs.glob("*/run.json"))
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    for run_file in files:
        payload = read_json_file(run_file)
        if isinstance(payload, dict):
            runs.append(payload)
    return runs


def build_eval_run_preview(run: Dict[str, Any]) -> Dict[str, Any]:
    summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
    return {
        "runId": run.get("runId"),
        "suiteId": run.get("suiteId"),
        "canvas": str(run.get("canvas") or "").strip() or None,
        "source": str(run.get("source") or "").strip() or None,
        "taskId": str(run.get("taskId") or "").strip() or None,
        "loopJobId": str(run.get("loopJobId") or "").strip() or None,
        "status": run.get("status") or "unknown",
        "createdAt": run.get("createdAt"),
        "updatedAt": run.get("updatedAt"),
        "startedAt": run.get("startedAt"),
        "completedAt": run.get("completedAt"),
        "replicates": int(run.get("replicates") or 0),
        "loopSweep": [int(value) for value in (run.get("loopSweep") or []) if str(value).strip()] if isinstance(run.get("loopSweep"), list) else [],
        "judgeProvider": run.get("judgeProvider"),
        "judgeModel": run.get("judgeModel"),
        "judgeRuntime": run.get("judgeRuntime") if isinstance(run.get("judgeRuntime"), dict) else None,
        "judgeLearning": run.get("judgeLearning") if isinstance(run.get("judgeLearning"), dict) else None,
        "current": run.get("current") if isinstance(run.get("current"), dict) else None,
        "error": run.get("error"),
        "summary": {
            "caseCount": int(summary.get("caseCount") or 0),
            "variantCount": int(summary.get("variantCount") or 0),
            "errorCount": int(summary.get("errorCount") or 0),
            "totalTokens": int(summary.get("totalTokens") or 0),
            "estimatedCostUsd": float(summary.get("estimatedCostUsd") or 0.0),
            "averageQuality": summary.get("averageQuality") if isinstance(summary.get("averageQuality"), dict) else {},
            "averageAnswerHealth": summary.get("averageAnswerHealth") if isinstance(summary.get("averageAnswerHealth"), dict) else {},
            "averageControl": summary.get("averageControl") if isinstance(summary.get("averageControl"), dict) else {},
            "variants": (summary.get("variants") or [])[:8] if isinstance(summary.get("variants"), list) else [],
        },
    }


def eval_resolve_run_file(paths: Optional[Paths], run_id: str, relative_path: str) -> Optional[Path]:
    paths = paths or project_paths()
    cleaned = str(relative_path or "").replace("/", str(Path("/"))).replace("\\", str(Path("/"))).lstrip("/\\")
    if not cleaned or ".." in Path(cleaned).parts:
        return None
    run_dir = paths.eval_runs / run_id
    if not run_dir.exists():
        return None
    candidate = (run_dir / cleaned).resolve()
    resolved_run_dir = run_dir.resolve()
    try:
        candidate.relative_to(resolved_run_dir)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def build_eval_history_payload(paths: Optional[Paths] = None, selected_run_id: str = "", canvas: str = "") -> Dict[str, Any]:
    paths = paths or project_paths()
    suite_catalog = load_eval_suite_catalog(paths)
    arm_catalog = load_eval_arm_catalog(paths)
    run_payloads = list_eval_runs(paths)
    normalized_canvas = str(canvas or "").strip().lower()
    if normalized_canvas:
        run_payloads = [
            run for run in run_payloads
            if str(run.get("canvas") or "").strip().lower() == normalized_canvas
        ]
    run_payloads.sort(
        key=lambda item: (
            str(item.get("updatedAt") or item.get("createdAt") or ""),
            str(item.get("runId") or ""),
        ),
        reverse=True,
    )
    run_payloads = run_payloads[:16]
    runs: List[Dict[str, Any]] = []
    selected_run: Optional[Dict[str, Any]] = None
    for run in run_payloads:
        runs.append(build_eval_run_preview(run))
        if selected_run_id and str(run.get("runId") or "") == selected_run_id:
            selected_run = run
    if selected_run is None and not selected_run_id and run_payloads:
        latest = run_payloads[0]
        selected_run = latest
        selected_run_id = str(latest.get("runId") or "")
    if isinstance(selected_run, dict):
        artifacts = [entry for entry in (selected_run.get("artifactIndex") or {}).values() if isinstance(entry, dict)] if isinstance(selected_run.get("artifactIndex"), dict) else []
        artifacts.sort(key=lambda item: (str(item.get("modifiedAt") or ""), str(item.get("name") or "")), reverse=True)
        selected_run["artifacts"] = artifacts
    return {
        "suites": suite_catalog["items"],
        "suiteErrors": suite_catalog["errors"],
        "arms": arm_catalog["items"],
        "armErrors": arm_catalog["errors"],
        "canvas": normalized_canvas or None,
        "runs": runs,
        "selectedRunId": selected_run_id or None,
        "selectedRun": selected_run,
    }


def read_eval_artifact(paths: Optional[Paths], run_id: str, artifact_id: str) -> Dict[str, Any]:
    paths = paths or project_paths()
    run = read_eval_run(paths, run_id)
    if not isinstance(run, dict):
        raise FileNotFoundError("Eval run not found.")
    artifact_index = run.get("artifactIndex") if isinstance(run.get("artifactIndex"), dict) else {}
    entry = artifact_index.get(artifact_id) if isinstance(artifact_index, dict) else None
    if not isinstance(entry, dict):
        raise FileNotFoundError("Eval artifact not found.")
    relative_path = str(entry.get("relativePath") or "")
    artifact_file = eval_resolve_run_file(paths, run_id, relative_path)
    if artifact_file is None:
        raise FileNotFoundError("Eval artifact file is missing.")
    content = read_json_file(artifact_file)
    if not isinstance(content, dict):
        raise ValueError("Eval artifact content is invalid.")
    return {
        "artifactId": artifact_id,
        "name": entry.get("name") or artifact_file.name,
        "kind": entry.get("kind") or "artifact",
        "storage": "eval",
        "modifiedAt": entry.get("modifiedAt") or datetime.fromtimestamp(artifact_file.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
        "size": entry.get("size") or artifact_file.stat().st_size,
        "summary": entry.get("summary") if isinstance(entry.get("summary"), dict) else {},
        "policy": artifact_visibility_policy(),
        "content": content,
    }


def default_vetting_rubric_preview() -> Dict[str, Any]:
    return {
        "qualifier": "MSP Live Incident Lead Qualifier",
        "mustDo": [
            "Judge as if hiring a lead MSP incident responder for a live multi-tenant severity-1 event.",
            "Reward tenant separation, evidence preservation, control-plane skepticism, and threshold-based escalation.",
            "Require per-customer incident ownership, an internal major-incident record, and tenant-safe evidence-compatible communication.",
            "Penalize polished answers that create cross-tenant exposure, evidence loss, or blind service disruption.",
        ],
        "hardFailRules": [
            "Cross-tenant customer disclosure or shared customer-facing ticketing is disqualifying.",
            "Missing per-customer incident ownership plus an internal major-incident record/decision log is disqualifying.",
            "Blind trust in the suspected compromised RMM or PSA before preserving evidence is a hard fail.",
            "Blind mass shutdown or destructive cleanup without gates is a hard fail.",
        ],
        "categories": {
            "blastRadiusPerception": "Blast path, tenant-boundary, and control-plane perception.",
            "humanUsability": "MSP operator usability under pressure.",
            "agentExecutability": "Tenant-safe executability.",
            "commsAndIncidentDiscipline": "Comms & incident-record discipline.",
            "tacticalDetail": "Evidence and action detail.",
            "restraintAndCollateral": "Collateral and compliance restraint.",
            "decisionGates": "Decision and escalation gates.",
            "firstHourRealism": "First-hour MSP realism.",
            "overall": "Lead hireability.",
        },
        "awards": {
            "bestFinalAnswer": "The safest, clearest, most hireable incident-lead answer.",
            "bestTacticalDetail": "The answer with the strongest useful extra checks, artifacts, or control-plane cautions.",
        },
    }


def read_score_run(paths: Optional[Paths], run_id: str) -> Dict[str, Any]:
    paths = paths or project_paths()
    target = benchmark_vetting_runs_dir(paths) / f"{run_id}.json"
    payload = read_json_file(target)
    if not isinstance(payload, dict):
        raise FileNotFoundError("Score run not found.")
    return payload


def list_score_runs(paths: Optional[Paths]) -> List[Dict[str, Any]]:
    paths = paths or project_paths()
    runs_dir = benchmark_vetting_runs_dir(paths)
    payloads: List[Dict[str, Any]] = []
    if not runs_dir.exists():
        return payloads
    for path in runs_dir.glob("*.json"):
        payload = read_json_file(path)
        if not isinstance(payload, dict):
            continue
        payloads.append(payload)
    payloads.sort(
        key=lambda item: (
            str(item.get("createdAt") or ""),
            str(item.get("runId") or ""),
        ),
        reverse=True,
    )
    return payloads


def read_project_json_file(paths: Paths, relative_or_absolute_path: str) -> Optional[Dict[str, Any]]:
    raw = str(relative_or_absolute_path or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (paths.root / raw).resolve()
    else:
        candidate = candidate.resolve()
    try:
        candidate.relative_to(paths.root.resolve())
    except ValueError:
        return None
    return read_json_file(candidate)


def read_eval_arm_manifest(paths: Paths, answer_id: str) -> Optional[Dict[str, Any]]:
    target = paths.eval_arms / f"{str(answer_id or '').strip()}.json"
    return read_json_file(target)


def score_overall_value(answer: Dict[str, Any]) -> Optional[float]:
    scores = answer.get("scores") if isinstance(answer.get("scores"), dict) else {}
    value = scores.get("overall") if isinstance(scores, dict) else None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def score_run_judge_provider(run: Dict[str, Any]) -> Optional[str]:
    judge = run.get("judge") if isinstance(run.get("judge"), dict) else {}
    provider = str(judge.get("provider") or run.get("providerFamily") or "").strip()
    return provider or None


def build_scores_run_preview(run: Dict[str, Any]) -> Dict[str, Any]:
    judge = run.get("judge") if isinstance(run.get("judge"), dict) else {}
    answers = run.get("answers") if isinstance(run.get("answers"), list) else []
    answer_providers = sorted(
        {
            str(answer.get("provider") or "").strip()
            for answer in answers
            if isinstance(answer, dict) and str(answer.get("provider") or "").strip()
        }
    )
    return {
        "runId": str(run.get("runId") or "").strip(),
        "createdAt": str(run.get("createdAt") or "").strip(),
        "title": str(((run.get("case") or {}) if isinstance(run.get("case"), dict) else {}).get("title") or "").strip() or "Scored run",
        "judgeSystem": str(run.get("judgeSystem") or "").strip() or "council",
        "providerFamily": str(run.get("providerFamily") or "").strip() or None,
        "judgeProvider": score_run_judge_provider(run),
        "judgeModel": str(judge.get("model") or "").strip() or None,
        "answerProviders": answer_providers,
        "bestFinalAnswer": str(((run.get("bestFinalAnswer") or {}) if isinstance(run.get("bestFinalAnswer"), dict) else {}).get("label") or "").strip() or None,
        "bestTacticalDetail": str(((run.get("bestTacticalDetail") or {}) if isinstance(run.get("bestTacticalDetail"), dict) else {}).get("label") or "").strip() or None,
        "measuredAdvantage": str(((run.get("advantageSummary") or {}) if isinstance(run.get("advantageSummary"), dict) else {}).get("band") or "").strip() or None,
        "answerCount": len(run.get("answers") or []) if isinstance(run.get("answers"), list) else 0,
    }


def extract_meaningful_answer_text(payload: Any) -> str:
    if isinstance(payload, dict):
        output_value = payload.get("output")
        if isinstance(output_value, dict):
            nested = extract_meaningful_answer_text(output_value)
            if nested:
                return nested
        if isinstance(output_value, str) and output_value.strip():
            nested_output = extract_meaningful_answer_text(output_value.strip())
            if nested_output:
                return nested_output
        front_answer = payload.get("frontAnswer")
        if isinstance(front_answer, dict):
            nested = extract_meaningful_answer_text(front_answer)
            if nested:
                return nested
        answer_value = payload.get("answer")
        if isinstance(answer_value, dict):
            nested = extract_meaningful_answer_text(answer_value)
            if nested:
                return nested
        if isinstance(answer_value, str) and answer_value.strip():
            nested_answer = extract_meaningful_answer_text(answer_value.strip())
            if nested_answer:
                return nested_answer
            return answer_value.strip()
        flattened_output = payload.get("flattenedOutputText")
        if isinstance(flattened_output, str) and flattened_output.strip():
            return flattened_output.strip()
        provider = str(payload.get("provider") or "").strip()
        raw_output = payload.get("rawOutputText")
        if isinstance(raw_output, str) and raw_output.strip():
            normalized = extract_normalized_provider_answer(provider, raw_output)
            if normalized:
                return normalized
            decoded_raw = parse_embedded_json_value(raw_output)
            if decoded_raw is not None:
                nested = extract_meaningful_answer_text(decoded_raw)
                if nested:
                    return nested
            return raw_output.strip()
    if isinstance(payload, str):
        raw = payload.strip()
        decoded_raw = parse_embedded_json_value(raw)
        if decoded_raw is not None:
            nested = extract_meaningful_answer_text(decoded_raw)
            if nested:
                return nested
        return raw
    return ""


def extract_canonical_prompt_text(payload: Any) -> str:
    if isinstance(payload, dict):
        input_text = payload.get("inputText")
        if isinstance(input_text, str) and input_text.strip():
            return input_text.strip()
        full_prompt = payload.get("fullPrompt")
        if isinstance(full_prompt, str) and full_prompt.strip():
            full_prompt_text = full_prompt.strip()
            for marker in ("\n\nObjective:", "\n\nPrompt:", "\n\nCandidate answers:"):
                marker_index = full_prompt_text.find(marker)
                if marker_index >= 0:
                    return full_prompt_text[marker_index + 2 :].strip()
            return full_prompt_text
        output_value = payload.get("output")
        if isinstance(output_value, dict):
            nested = extract_canonical_prompt_text(output_value)
            if nested:
                return nested
    return ""


def missing_canonical_prompt_message() -> str:
    return "Canonical provider prompt was not recorded for this run. Rerun on the current runtime to inspect the exact prompt."


def hydrate_score_answer(paths: Paths, answer: Dict[str, Any]) -> Dict[str, Any]:
    hydrated = dict(answer)
    artifact_file = str(answer.get("artifactFile") or "").strip()
    if artifact_file:
        artifact_payload = read_project_json_file(paths, artifact_file)
        if isinstance(artifact_payload, dict):
            hydrated["_artifactPayload"] = artifact_payload
            extracted = extract_meaningful_answer_text(artifact_payload)
            if extracted:
                hydrated["text"] = extracted
            if not str(hydrated.get("provider") or "").strip():
                hydrated["provider"] = str(artifact_payload.get("provider") or "").strip() or hydrated.get("provider")
            if not str(hydrated.get("model") or "").strip():
                hydrated["model"] = str(artifact_payload.get("model") or "").strip() or hydrated.get("model")
    return hydrated


def format_preview_heading(label: str, value: str) -> str:
    normalized_label = str(label or "").strip()
    normalized_value = str(value or "").strip()
    if not normalized_value:
        return ""
    return f"{normalized_label}:\n{normalized_value}"


def format_preview_bullets(values: Any) -> str:
    if isinstance(values, list):
        lines = [f"- {str(item).strip()}" for item in values if str(item or "").strip()]
        return "\n".join(lines) if lines else "- none"
    if isinstance(values, dict):
        lines: List[str] = []
        for key, value in values.items():
            key_label = re.sub(r"(?<!^)([A-Z])", r" \1", str(key or "")).replace("_", " ").strip() or "item"
            if isinstance(value, list):
                rendered = format_preview_bullets(value)
                lines.append(f"- {key_label}:")
                lines.extend([f"  {line}" for line in rendered.splitlines()])
            elif isinstance(value, dict):
                rendered = format_preview_bullets(value)
                lines.append(f"- {key_label}:")
                lines.extend([f"  {line}" for line in rendered.splitlines()])
            else:
                lines.append(f"- {key_label}: {str(value or '').strip() or 'none'}")
        return "\n".join(lines) if lines else "- none"
    normalized = str(values or "").strip()
    return normalized or "none"


def build_shared_question_prompt(case: Dict[str, Any]) -> str:
    return "\n\n".join(
        [
            format_preview_heading("Objective", str(case.get("objective") or "").strip()),
            format_preview_heading("Constraints", format_preview_bullets(case.get("constraints", []))),
            format_preview_heading("Session context", str(case.get("sessionContext", "") or "none").strip() or "none"),
        ]
    ).strip()


def build_direct_answer_prompt_preview(case: Dict[str, Any], runtime_config: Dict[str, Any]) -> str:
    return build_shared_question_prompt(case)


def build_vetting_matrix_judge_prompt_preview(
    case: Dict[str, Any],
    judge_rubric: Any,
    answers: List[Dict[str, Any]],
) -> str:
    instructions = (
        "Blindly evaluate the candidate answers to the same prompt as if vetting a lead MSP incident responder for a live multi-tenant severity-1 event.\n"
        "Use only the judge metric below plus the shared prompt, constraints, and answer texts.\n"
        "Score each answer from 0 to 10 in 0.5-point increments for every listed category.\n"
        "Record hire verdicts, hard-fail flags, and trap findings for each answer.\n"
        "An answer that triggers a hard fail should not win best final answer unless every answer hard-fails.\n"
        "Choose one best final answer and one best tactical detail answer.\n"
        "Return JSON only that matches the schema."
    )
    answer_blocks: List[str] = []
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        answer_blocks.append(
            "\n".join(
                [
                    f"Answer {str(answer.get('id', '')).strip() or '?'}",
                    str(answer.get("text", "")).strip() or "No answer captured.",
                ]
            ).strip()
        )
    input_text = "\n\n".join(
        [
            format_preview_heading("Judge metric", format_preview_bullets(judge_rubric)),
            format_preview_heading("Objective", str(case.get("objective") or "").strip()),
            format_preview_heading("Constraints", format_preview_bullets(case.get("constraints", []))),
            format_preview_heading("Candidate answers", "\n\n".join(answer_blocks) if answer_blocks else "No candidate answers supplied."),
        ]
    ).strip()
    return f"Instructions:\n{instructions}\n\n{input_text}".strip()


def build_direct_lane_prompt(case: Dict[str, Any], arm_manifest: Optional[Dict[str, Any]]) -> str:
    runtime_config = (
        (arm_manifest.get("runtime") if isinstance(arm_manifest, dict) and isinstance(arm_manifest.get("runtime"), dict) else {})
        or {}
    )
    return build_direct_answer_prompt_preview(case, runtime_config)


def build_para_lane_prompt(case: Dict[str, Any], arm_manifest: Optional[Dict[str, Any]]) -> str:
    arm_manifest = arm_manifest if isinstance(arm_manifest, dict) else {}
    arm_bits = "\n".join(
        [
            line
            for line in [
                str(arm_manifest.get("title") or "").strip(),
                str(arm_manifest.get("description") or "").strip(),
            ]
            if line
        ]
    ).strip()
    prompt = build_shared_question_prompt(case)
    if not arm_bits:
        return prompt
    return "\n\n".join([prompt, format_preview_heading("Para path", arm_bits)]).strip()


def build_judge_lane_prompt(run: Dict[str, Any], source_manifest: Optional[Dict[str, Any]]) -> str:
    case = run.get("case") if isinstance(run.get("case"), dict) else {}
    answers = run.get("answers") if isinstance(run.get("answers"), list) else []
    judge_rubric = (
        source_manifest.get("judgeRubric")
        if isinstance(source_manifest, dict) and isinstance(source_manifest.get("judgeRubric"), dict)
        else default_vetting_rubric_preview()
    )
    slotted_answers = []
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        slotted_answers.append(
            {
                "id": str(answer.get("slot") or answer.get("answerId") or "").strip(),
                "text": str(answer.get("text") or "").strip(),
                "costUsd": answer.get("costUsd"),
                "costNote": answer.get("costNote"),
                "familyHint": answer.get("familyHint"),
            }
        )
    return build_vetting_matrix_judge_prompt_preview(case, judge_rubric, slotted_answers)


def build_judge_lane_response(run: Dict[str, Any]) -> str:
    best_final = run.get("bestFinalAnswer") if isinstance(run.get("bestFinalAnswer"), dict) else {}
    best_tactical = run.get("bestTacticalDetail") if isinstance(run.get("bestTacticalDetail"), dict) else {}
    advantage = run.get("advantageSummary") if isinstance(run.get("advantageSummary"), dict) else {}
    answers = run.get("answers") if isinstance(run.get("answers"), list) else []
    score_packets: Dict[str, Any] = {}
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        score_packets[str(answer.get("label") or answer.get("slot") or "").strip() or "answer"] = (
            answer.get("scores") if isinstance(answer.get("scores"), dict) else {}
        )
    lines = [
        f"Best final answer: {str(best_final.get('label') or best_final.get('slot') or 'n/a').strip()}",
        f"Best tactical detail: {str(best_tactical.get('label') or best_tactical.get('slot') or 'n/a').strip()}",
    ]
    hire_verdict = str(best_final.get("hireVerdict") or "").strip()
    if hire_verdict:
        lines.append(f"Hire verdict: {hire_verdict}")
    hard_fail_flags = best_final.get("hardFailFlags") if isinstance(best_final.get("hardFailFlags"), list) else []
    if hard_fail_flags:
        lines.append("Hard fail flags: " + "; ".join([str(item).strip() for item in hard_fail_flags if str(item).strip()]))
    band = str(advantage.get("band") or "").strip()
    if band:
        leader = ((advantage.get("leader") or {}) if isinstance(advantage.get("leader"), dict) else {})
        runner_up = ((advantage.get("runnerUp") or {}) if isinstance(advantage.get("runnerUp"), dict) else {})
        lines.append(
            "Measured advantage: "
            + band
            + " | leader "
            + (str(leader.get("label") or leader.get("slot") or "n/a").strip())
            + " | runner-up "
            + (str(runner_up.get("label") or runner_up.get("slot") or "n/a").strip())
        )
    rationale = str(run.get("rationale") or "").strip()
    if rationale:
        lines.extend(["", "Judge rationale:", rationale])
    return "\n".join([line for line in lines if line is not None]).strip()


def build_scores_judge_trace_text(run: Dict[str, Any], answers: List[Dict[str, Any]]) -> str:
    judge = run.get("judge") if isinstance(run.get("judge"), dict) else {}
    advantage = run.get("advantageSummary") if isinstance(run.get("advantageSummary"), dict) else {}
    ranking = run.get("rankingAnswers") if isinstance(run.get("rankingAnswers"), list) else []
    lines: List[str] = []
    lines.append(f"Judge system: {str(run.get('judgeSystem') or 'council').strip() or 'council'}")
    provider = str(judge.get("provider") or run.get("providerFamily") or "").strip()
    if provider:
        lines.append(f"Judge provider: {provider}")
    model = str(judge.get("model") or "").strip()
    if model:
        lines.append(f"Judge model: {model}")
    response_id = ""
    slot_result = run.get("slotResult") if isinstance(run.get("slotResult"), dict) else {}
    response_id = str(slot_result.get("responseId") or "").strip()
    if not response_id:
        trace = run.get("judgeTrace") if isinstance(run.get("judgeTrace"), dict) else {}
        response_id = str(trace.get("responseId") or "").strip()
    if response_id:
        lines.append(f"Response id: {response_id}")
    source_manifest = str(run.get("sourceManifest") or "").strip()
    if source_manifest:
        lines.append(f"Source manifest: {source_manifest}")
    if answers:
        lines.extend(["", "Blind slot mapping:"])
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            slot = str(answer.get("slot") or "").strip() or "?"
            label = str(answer.get("label") or answer.get("answerId") or "").strip() or "answer"
            lines.append(f"- {slot}: {label}")
    if ranking:
        lines.extend(["", "Ranking:"])
        for index, answer in enumerate(ranking, start=1):
            if not isinstance(answer, dict):
                continue
            label = str(answer.get("label") or answer.get("slot") or "answer").strip()
            hire_verdict = str(answer.get("hireVerdict") or "").strip()
            verdict_suffix = f" | {hire_verdict}" if hire_verdict else ""
            lines.append(f"{index}. {label}{verdict_suffix}")
            hard_fail_flags = answer.get("hardFailFlags") if isinstance(answer.get("hardFailFlags"), list) else []
            if hard_fail_flags:
                lines.append("   hard fails: " + "; ".join([str(item).strip() for item in hard_fail_flags if str(item).strip()]))
    band = str(advantage.get("band") or "").strip()
    if band:
        leader = advantage.get("leader") if isinstance(advantage.get("leader"), dict) else {}
        runner_up = advantage.get("runnerUp") if isinstance(advantage.get("runnerUp"), dict) else {}
        lines.extend(
            [
                "",
                "Measured advantage:",
                f"- band: {band}",
                f"- leader: {str(leader.get('label') or leader.get('slot') or 'n/a').strip()}",
                f"- runner-up: {str(runner_up.get('label') or runner_up.get('slot') or 'n/a').strip()}",
            ]
        )
    markdown = run.get("markdown") if isinstance(run.get("markdown"), dict) else {}
    summary = str(markdown.get("summary") or "").strip()
    if summary:
        lines.extend(["", "Judge summary:", summary])
    score_table = str(markdown.get("scoreTable") or "").strip()
    if score_table:
        lines.extend(["", "Score table:", score_table])
    legend = str(markdown.get("legend") or "").strip()
    if legend:
        lines.extend(["", "Legend:", legend])
    return "\n".join([line for line in lines if line is not None]).strip()


def build_scores_answer_lane(
    paths: Paths,
    case: Dict[str, Any],
    answer: Dict[str, Any],
    arm_manifest: Optional[Dict[str, Any]],
    *,
    lane_key: str,
) -> Dict[str, Any]:
    runtime_config = arm_manifest.get("runtime") if isinstance(arm_manifest, dict) and isinstance(arm_manifest.get("runtime"), dict) else {}
    hydrated_answer = hydrate_score_answer(paths, answer)
    artifact_payload = hydrated_answer.get("_artifactPayload") if isinstance(hydrated_answer.get("_artifactPayload"), dict) else None
    prompt_text = build_shared_question_prompt(case)
    if not prompt_text:
        prompt_text = extract_canonical_prompt_text(artifact_payload)
    if not prompt_text:
        if lane_key == "direct":
            prompt_text = build_direct_lane_prompt(case, arm_manifest)
        else:
            prompt_text = build_shared_question_prompt(case)
    response_text = extract_meaningful_answer_text(artifact_payload) if isinstance(artifact_payload, dict) else ""
    if not response_text:
        response_text = str(hydrated_answer.get("text") or "").strip()
    return {
        "laneKey": lane_key,
        "answerId": str(hydrated_answer.get("answerId") or "").strip() or None,
        "label": str(hydrated_answer.get("label") or "").strip() or lane_key.title(),
        "role": str(hydrated_answer.get("role") or "").strip() or None,
        "provider": str(hydrated_answer.get("provider") or runtime_config.get("provider") or "").strip() or None,
        "model": str(hydrated_answer.get("model") or runtime_config.get("model") or runtime_config.get("summarizerModel") or "").strip() or None,
        "overall": score_overall_value(hydrated_answer),
        "artifactFile": str(hydrated_answer.get("artifactFile") or "").strip() or None,
        "cohort": str(hydrated_answer.get("cohort") or "").strip() or None,
        "elapsedSeconds": hydrated_answer.get("elapsedSeconds"),
        "promptText": prompt_text or missing_canonical_prompt_message(),
        "responseText": response_text or "No response captured.",
    }


def score_answer_is_para_candidate(answer: Dict[str, Any]) -> bool:
    role = str((answer or {}).get("role") or "").strip().lower()
    if role == "direct":
        return False
    return True


def build_scores_run_detail(paths: Paths, run: Dict[str, Any]) -> Dict[str, Any]:
    source_manifest = read_project_json_file(paths, str(run.get("sourceManifest") or ""))
    case = run.get("case") if isinstance(run.get("case"), dict) else {}
    judge = run.get("judge") if isinstance(run.get("judge"), dict) else {}
    judge_trace = run.get("judgeTrace") if isinstance(run.get("judgeTrace"), dict) else {}
    slot_result = run.get("slotResult") if isinstance(run.get("slotResult"), dict) else {}
    answers = [hydrate_score_answer(paths, dict(answer)) for answer in (run.get("answers") or []) if isinstance(answer, dict)]
    answer_providers = sorted(
        {
            str(answer.get("provider") or "").strip()
            for answer in answers
            if isinstance(answer, dict) and str(answer.get("provider") or "").strip()
        }
    )
    para_answers = [answer for answer in answers if score_answer_is_para_candidate(answer)]
    direct_answer = next((answer for answer in answers if str(answer.get("role") or "").strip() == "direct"), None)
    para_lanes = []
    for answer in para_answers:
        arm_manifest = read_eval_arm_manifest(paths, str(answer.get("answerId") or ""))
        para_lanes.append(build_scores_answer_lane(paths, case, answer, arm_manifest, lane_key="para"))
    para_lanes.sort(
        key=lambda item: (
            -float(item.get("overall")) if item.get("overall") is not None else 999.0,
            str(item.get("label") or ""),
        )
    )
    best_final = run.get("bestFinalAnswer") if isinstance(run.get("bestFinalAnswer"), dict) else {}
    default_para_answer_id = None
    if score_answer_is_para_candidate(best_final):
        default_para_answer_id = str(best_final.get("answerId") or "").strip() or None
    if not default_para_answer_id and para_lanes:
        default_para_answer_id = str(para_lanes[0].get("answerId") or "").strip() or None
    direct_lane = None
    if isinstance(direct_answer, dict):
        direct_arm_manifest = read_eval_arm_manifest(paths, str(direct_answer.get("answerId") or ""))
        direct_lane = build_scores_answer_lane(paths, case, direct_answer, direct_arm_manifest, lane_key="direct")
    judge_prompt = (
        str((slot_result.get("fullPrompt") if isinstance(slot_result, dict) else None) or "").strip()
        or str(judge_trace.get("fullPrompt") or "").strip()
        or missing_canonical_prompt_message()
    )
    judge_lane = {
        "laneKey": "judge",
        "label": "Blind judge",
        "provider": score_run_judge_provider(run),
        "model": str(judge.get("model") or "").strip() or None,
        "promptText": judge_prompt,
        "responseText": build_judge_lane_response(run),
    }
    markdown = run.get("markdown") if isinstance(run.get("markdown"), dict) else {}
    return {
        "runId": str(run.get("runId") or "").strip(),
        "createdAt": str(run.get("createdAt") or "").strip(),
        "title": str(case.get("title") or "").strip() or "Scored run",
        "judgeSystem": str(run.get("judgeSystem") or "").strip() or "council",
        "providerFamily": str(run.get("providerFamily") or "").strip() or None,
        "judge": {
            "provider": score_run_judge_provider(run),
            "model": str(judge.get("model") or "").strip() or None,
        },
        "answerProviders": answer_providers,
        "case": case,
        "bestFinalAnswer": best_final,
        "bestTacticalDetail": run.get("bestTacticalDetail") if isinstance(run.get("bestTacticalDetail"), dict) else {},
        "advantageSummary": run.get("advantageSummary") if isinstance(run.get("advantageSummary"), dict) else {},
        "judgeTrace": {
            "responseId": str((slot_result.get("responseId") if isinstance(slot_result, dict) else None) or judge_trace.get("responseId") or "").strip() or None,
            "fullPrompt": judge_prompt,
            "rawResponseText": str(judge_trace.get("rawOutputText") or "").strip() or None,
            "logText": build_scores_judge_trace_text(run, answers),
            "sourceManifest": str(run.get("sourceManifest") or "").strip() or None,
        },
        "markdown": {
            "summary": str(markdown.get("summary") or "").strip(),
            "scoreTable": str(markdown.get("scoreTable") or "").strip(),
            "legend": str(markdown.get("legend") or "").strip(),
        },
        "lanes": {
            "defaultParaAnswerId": default_para_answer_id,
            "paraOptions": para_lanes,
            "direct": direct_lane,
            "judge": judge_lane,
        },
    }


def build_scores_runs_payload(paths: Optional[Paths] = None, selected_run_id: str = "") -> Dict[str, Any]:
    paths = paths or project_paths()
    run_payloads = list_score_runs(paths)
    runs = [build_scores_run_preview(run) for run in run_payloads]
    selected_run: Optional[Dict[str, Any]] = None
    selected_source: Optional[Dict[str, Any]] = None
    for run in run_payloads:
        if selected_run_id and str(run.get("runId") or "") == selected_run_id:
            selected_source = run
            break
    if selected_source is None and run_payloads:
        selected_source = run_payloads[0]
        selected_run_id = str(selected_source.get("runId") or "")
    if isinstance(selected_source, dict):
        selected_run = build_scores_run_detail(paths, selected_source)
    return {
        "runs": runs,
        "selectedRunId": selected_run_id or None,
        "selectedRun": selected_run,
    }
