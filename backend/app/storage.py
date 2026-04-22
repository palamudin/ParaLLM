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


LOCK_STALE_SECONDS = 45
JOB_QUEUE_STALE_SECONDS = 60
JOB_RUNNING_STALE_SECONDS = 180
LOOP_QUEUE_LIMIT = 4


@dataclass(frozen=True)
class Paths:
    root: Path
    data: Path
    tasks: Path
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
        "summary": None,
        "memoryVersion": 0,
        "usage": default_usage_state(),
        "loop": default_loop_state(),
        "lastUpdated": utc_now(),
    }


def normalize_usage_bucket(bucket: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = default_usage_bucket()
    current = bucket if isinstance(bucket, dict) else {}
    merged = dict(base)
    for key in base:
        value = current.get(key, base[key])
        if key.endswith("Usd"):
            merged[key] = float(value or 0.0)
        elif key in {"lastModel", "lastResponseId", "lastUpdated"}:
            merged[key] = value
        else:
            merged[key] = int(value or 0)
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


def read_state(paths: Optional[Paths] = None) -> Dict[str, Any]:
    paths = paths or project_paths()
    if metadata.postgres_enabled(paths.root):
        parsed = metadata.read_state_payload(paths.root, default_state())
    else:
        parsed = read_json_file(paths.state)
    if not isinstance(parsed, dict):
        return default_state()
    parsed.setdefault("loop", default_loop_state())
    parsed["usage"] = normalize_usage_state(parsed.get("usage") if isinstance(parsed.get("usage"), dict) else {})
    return parsed


def parse_ts(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def default_job(config: Dict[str, Any]) -> Dict[str, Any]:
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
        "queuePosition": max(0, int(config.get("queuePosition") or 0)),
        "attempt": max(1, int(config.get("attempt") or 1)),
        "resumeOfJobId": config.get("resumeOfJobId"),
        "retryOfJobId": config.get("retryOfJobId"),
        "resumeFromRound": max(1, int(config.get("resumeFromRound") or 1)),
        "rounds": int(config.get("rounds") or 0),
        "delayMs": int(config.get("delayMs") or 0),
        "workerCount": max(0, int(config.get("workerCount") or 0)),
        "cancelRequested": bool(config.get("cancelRequested") or False),
        "dependencyJobIds": dependency_ids,
        "dependencyMode": str(config.get("dependencyMode") or "all"),
        "partialSummary": bool(config.get("partialSummary") or False),
        "timeoutSeconds": max(30, int(config.get("timeoutSeconds") or 300)),
        "queuedAt": config.get("queuedAt"),
        "startedAt": config.get("startedAt"),
        "finishedAt": config.get("finishedAt"),
        "lastHeartbeatAt": config.get("lastHeartbeatAt"),
        "completedRounds": int(config.get("completedRounds") or 0),
        "currentRound": int(config.get("currentRound") or 0),
        "lastMessage": config.get("lastMessage") or "Queued.",
        "usage": normalize_usage_state(config.get("usage") if isinstance(config.get("usage"), dict) else {}),
        "results": config.get("results") if isinstance(config.get("results"), list) else [],
        "metadata": config.get("metadata") if isinstance(config.get("metadata"), dict) else {},
        "error": config.get("error"),
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
    if target == "commander":
        return "Commander"
    if target == "commander_review":
        return "Commander review"
    if target == "summarizer":
        return "Summarizer (partial)" if job.get("partialSummary") else "Summarizer"
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
                "target": job.get("target"),
                "targetLabel": dispatch_target_label(job),
                "status": job.get("status"),
                "batchId": job.get("batchId"),
                "partialSummary": bool(job.get("partialSummary")),
                "queuedAt": job.get("queuedAt"),
                "startedAt": job.get("startedAt"),
                "lastHeartbeatAt": job.get("lastHeartbeatAt"),
                "lastMessage": job.get("lastMessage"),
            }
            for job in active_jobs
        ],
        "runningCount": running_count,
        "queuedCount": queued_count,
        "partialCount": partial_count,
        "lastMessage": active_jobs[0].get("lastMessage") or "Dispatch in progress.",
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
            }
        )
    current["loop"] = loop
    return current


def read_state_payload(paths: Optional[Paths] = None) -> Dict[str, Any]:
    paths = paths or project_paths()
    jobs = read_jobs(paths)
    state = coerce_loop_state(read_state(paths), jobs)
    state["executionHealth"] = build_execution_health(state, paths)
    active_task = state.get("activeTask")
    if isinstance(active_task, dict):
        enriched_task = copy.deepcopy(active_task)
        enriched_task["stateWorkers"] = copy.deepcopy(state.get("workers") or {})
        enriched_task["stateCommander"] = copy.deepcopy(state.get("commander"))
        enriched_task["stateCommanderReview"] = copy.deepcopy(state.get("commanderReview"))
        enriched_task["summary"] = copy.deepcopy(state.get("summary"))
        enriched_task["executionHealth"] = copy.deepcopy(state.get("executionHealth") or {})
        state["activeTask"] = enriched_task
    state["dispatch"] = current_dispatch_state(state, jobs)
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
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_commander_review_round(\d+)_output\.json$", re.I), "commander_review_output", lambda m: "commander-review", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_summary_partial_round(\d+)_output\.json$", re.I), "summary_partial_output", lambda m: "summary-partial", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_summary_round(\d+)_output\.json$", re.I), "summary_output", lambda m: "summary", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_([A-Z])_step(\d+)\.json$", re.I), "worker_step", lambda m: m.group(2), lambda m: int(m.group(3))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_commander_round(\d+)\.json$", re.I), "commander_round", lambda m: "commander", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_commander_review_round(\d+)\.json$", re.I), "commander_review_round", lambda m: "commander-review", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_summary_partial_round(\d+)\.json$", re.I), "summary_partial_round", lambda m: "summary-partial", lambda m: int(m.group(2))),
    (re.compile(r"^(t-\d{8}-\d{6}-[a-f0-9]+)_summary_round(\d+)\.json$", re.I), "summary_round", lambda m: "summary", lambda m: int(m.group(2))),
]


def build_artifact_history_entry(name: str, modified_at: str, size: int, content: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if "_step" not in name and "_round" not in name:
        return None
    entry: Dict[str, Any] = {
        "name": name,
        "modifiedAt": modified_at,
        "size": int(size or 0),
        "kind": "artifact",
        "taskId": None,
        "worker": None,
        "roundOrStep": None,
        "model": None,
        "mode": None,
        "responseId": None,
        "requestedMaxOutputTokens": None,
        "effectiveMaxOutputTokens": None,
        "maxOutputTokenAttempts": [],
        "recoveredFromIncomplete": False,
        "rawOutputAvailable": False,
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
        entry["model"] = content.get("model") or content.get("modelUsed")
        entry["mode"] = content.get("mode")
        entry["responseId"] = content.get("responseId")
        entry["requestedMaxOutputTokens"] = int(response_meta.get("requestedMaxOutputTokens") or 0) or None
        entry["effectiveMaxOutputTokens"] = int(response_meta.get("effectiveMaxOutputTokens") or 0) or None
        entry["maxOutputTokenAttempts"] = [int(value) for value in (response_meta.get("maxOutputTokenAttempts") or []) if str(value).strip()]
        entry["recoveredFromIncomplete"] = bool(response_meta.get("recoveredFromIncomplete"))
        entry["rawOutputAvailable"] = bool(str(content.get("rawOutputText") or "").strip())
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
        carry_context = str(archive.get("carryContext") or "").strip()
        archives.append(
            {
                "file": str(file.get("name") or ""),
                "createdAt": archive.get("createdAt"),
                "taskId": archive.get("taskId"),
                "objective": archive.get("objective"),
                "summaryRound": int(archive.get("summaryRound") or 0),
                "carryContextPreview": carry_context[:320],
            }
        )
    return archives


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
                "totalTokens": int(((job.get("usage") or {}) if isinstance(job.get("usage"), dict) else {}).get("totalTokens") or 0),
                "estimatedCostUsd": float(((job.get("usage") or {}) if isinstance(job.get("usage"), dict) else {}).get("estimatedCostUsd") or 0.0),
                "error": job.get("error"),
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
            and str(entry.get("kind") or "") in {"worker_output", "commander_output", "commander_review_output", "summary_output", "summary_partial_output"}
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
                    "commanderReviewArtifact": None,
                    "summaryArtifact": None,
                    "workerArtifacts": [],
                }
            if entry["kind"] == "commander_output":
                round_groups[round_key]["commanderArtifact"] = artifact_out
            elif entry["kind"] == "commander_review_output":
                round_groups[round_key]["commanderReviewArtifact"] = artifact_out
            elif entry["kind"] in {"summary_output", "summary_partial_output"}:
                round_groups[round_key]["summaryArtifact"] = artifact_out
            else:
                round_groups[round_key]["workerArtifacts"].append(artifact_out)
            if entry["modifiedAt"] > round_groups[round_key]["capturedAt"]:
                round_groups[round_key]["capturedAt"] = entry["modifiedAt"]
        if len(artifact_entries) >= max_artifacts:
            break

    rounds = list(round_groups.values())
    rounds.sort(key=lambda item: (str(item.get("capturedAt") or ""), int(item.get("round") or 0)), reverse=True)
    rounds = rounds[:max_rounds]
    for round_entry in rounds:
        round_entry["workerArtifacts"].sort(key=lambda item: str(item.get("worker") or ""))

    return {
        "jobs": jobs_out,
        "dispatch": state.get("dispatch"),
        "artifacts": artifact_entries,
        "rounds": rounds,
        "sessions": list_session_archives(paths, max_sessions),
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


def read_recent_jsonl_entries(path: Path, limit: int = 400) -> List[Dict[str, Any]]:
    raw = read_text(path)
    if raw is None:
        return []
    lines = [line for line in raw.splitlines() if line.strip()]
    entries: List[Dict[str, Any]] = []
    for line in lines[-max(0, limit):]:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    return entries


def step_target_id(stage: Any) -> Optional[str]:
    text = str(stage or "").strip().lower()
    if text in {"commander", "commander_review", "summarizer"}:
        return text
    match = re.fullmatch(r"worker_([a-z])", text)
    if match:
        return match.group(1).upper()
    return None


def execution_target_label(target_id: str, active_task: Optional[Dict[str, Any]]) -> str:
    normalized = str(target_id or "").strip()
    if normalized == "commander":
        return "Commander"
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


def build_execution_health(state: Dict[str, Any], paths: Paths, step_limit: int = 400) -> Dict[str, Any]:
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

    latest_issue: Optional[Dict[str, Any]] = None
    latest_issue_ts = ""
    targets: Dict[str, Dict[str, Any]] = {}
    for entry in read_recent_jsonl_entries(paths.steps, step_limit):
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
        status = "error" if errored else ("degraded" if degraded else "completed")
        target_entry = {
            "target": target_id,
            "label": execution_target_label(target_id, active_task),
            "status": status,
            "mode": mode,
            "degraded": degraded,
            "usedMockFallback": fallback,
            "recoveredFromIncomplete": recovered,
            "lastError": str(context.get("error") or "").strip() or None,
            "lastMessage": message,
            "updatedAt": ts or None,
        }
        targets[target_id] = target_entry
        if degraded and ts >= latest_issue_ts:
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
    response_meta = content.get("responseMeta") if isinstance(content.get("responseMeta"), dict) else {}
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
        "size": size,
        "summary": {
            "taskId": content.get("taskId"),
            "target": content.get("target") or content.get("workerId"),
            "label": content.get("label"),
            "mode": content.get("mode"),
            "model": content.get("model") or content.get("modelUsed"),
            "step": content.get("step"),
            "round": content.get("round"),
            "responseId": content.get("responseId"),
            "requestedMaxOutputTokens": int(response_meta.get("requestedMaxOutputTokens") or 0) or None,
            "effectiveMaxOutputTokens": int(response_meta.get("effectiveMaxOutputTokens") or 0) or None,
            "maxOutputTokenAttempts": [int(value) for value in (response_meta.get("maxOutputTokenAttempts") or []) if str(value).strip()],
            "recoveredFromIncomplete": bool(response_meta.get("recoveredFromIncomplete")),
            "localToolCalls": (response_meta.get("localToolCalls") or [])[:12] if isinstance(response_meta.get("localToolCalls"), list) else [],
            "localFileSources": list(response_meta.get("localFileSources") or []) if isinstance(response_meta.get("localFileSources"), list) else [],
            "githubToolCalls": (response_meta.get("githubToolCalls") or [])[:12] if isinstance(response_meta.get("githubToolCalls"), list) else [],
            "githubSources": list(response_meta.get("githubSources") or []) if isinstance(response_meta.get("githubSources"), list) else [],
            "rawOutputAvailable": bool(str(content.get("rawOutputText") or "").strip()),
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
            "model": ((manifest.get("runtime") or {}) if isinstance(manifest.get("runtime"), dict) else {}).get("model"),
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
        "status": run.get("status") or "unknown",
        "createdAt": run.get("createdAt"),
        "updatedAt": run.get("updatedAt"),
        "startedAt": run.get("startedAt"),
        "completedAt": run.get("completedAt"),
        "replicates": int(run.get("replicates") or 0),
        "loopSweep": [int(value) for value in (run.get("loopSweep") or []) if str(value).strip()] if isinstance(run.get("loopSweep"), list) else [],
        "judgeModel": run.get("judgeModel"),
        "current": run.get("current") if isinstance(run.get("current"), dict) else None,
        "error": run.get("error"),
        "summary": {
            "caseCount": int(summary.get("caseCount") or 0),
            "variantCount": int(summary.get("variantCount") or 0),
            "errorCount": int(summary.get("errorCount") or 0),
            "totalTokens": int(summary.get("totalTokens") or 0),
            "estimatedCostUsd": float(summary.get("estimatedCostUsd") or 0.0),
            "averageQuality": summary.get("averageQuality") if isinstance(summary.get("averageQuality"), dict) else {},
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


def build_eval_history_payload(paths: Optional[Paths] = None, selected_run_id: str = "") -> Dict[str, Any]:
    paths = paths or project_paths()
    suite_catalog = load_eval_suite_catalog(paths)
    arm_catalog = load_eval_arm_catalog(paths)
    run_payloads = list_eval_runs(paths)
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
