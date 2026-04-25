from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.engine import (
    LoopRuntime,
    RuntimeErrorWithCode,
    normalize_direct_baseline_mode,
    target_timeout_seconds,
    task_workers,
)

from . import control, faults, metadata, queueing, runtime_execution, storage
from .config import deployment_topology


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clamp_loop_rounds(value: Any) -> int:
    rounds = int(value or 1)
    return max(1, min(12, rounds))


def clamp_loop_delay_ms(value: Any) -> int:
    delay_ms = int(value or 0)
    return max(0, min(10000, delay_ms))


def _runtime(root: Optional[Path] = None) -> LoopRuntime:
    return LoopRuntime(Path(root).resolve() if root else Path(__file__).resolve().parents[2])


def current_loop_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return dict(storage.default_loop_state(), **(state.get("loop") if isinstance(state.get("loop"), dict) else {}))


def set_loop_state(state: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    next_state = dict(state)
    loop = current_loop_state(state)
    loop.update(patch)
    next_state["loop"] = loop
    return next_state


def loop_is_active(state: Dict[str, Any]) -> bool:
    return str(current_loop_state(state).get("status") or "idle") in {"queued", "running"}


def read_job(paths: storage.Paths, job_id: str) -> Optional[Dict[str, Any]]:
    if metadata.postgres_enabled(paths.root):
        return metadata.read_job_payload(paths.root, job_id)
    return storage.read_json_file(paths.jobs / f"{job_id}.json")


def job_status_can_resume(status: Optional[str]) -> bool:
    return str(status or "") == "interrupted"


def job_status_can_retry(status: Optional[str]) -> bool:
    return str(status or "") in {"interrupted", "error", "budget_exhausted", "cancelled", "completed"}


def job_resume_round(job: Dict[str, Any]) -> int:
    return max(1, int(job.get("completedRounds") or 0) + 1)


def _active_job_count(paths: storage.Paths, task_id: Optional[str], job_type: str, include_partial: bool = True) -> int:
    count = 0
    for job in storage.read_jobs(paths):
        if str(job.get("jobType") or "loop") != job_type:
            continue
        if str(job.get("status") or "") not in {"queued", "running"}:
            continue
        if task_id is not None and str(job.get("taskId") or "") != task_id:
            continue
        if not include_partial and bool(job.get("partialSummary")):
            continue
        count += 1
    return count


def _ordered_queued_background_jobs(
    paths: storage.Paths,
    task_id: Optional[str],
    job_type: str = "loop",
    exclude_job_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for job in storage.read_jobs(paths):
        if str(job.get("jobType") or "loop") != job_type:
            continue
        if str(job.get("status") or "") != "queued":
            continue
        if task_id is not None and str(job.get("taskId") or "") != task_id:
            continue
        if exclude_job_id and str(job.get("jobId") or "") == exclude_job_id:
            continue
        candidates.append(storage.default_job(job))
    candidates.sort(key=lambda job: (int(job.get("queuePosition") or 0), storage.parse_ts(job.get("queuedAt")) or 0))
    return candidates


def _next_background_queue_position(paths: storage.Paths, task_id: Optional[str], job_type: str = "loop") -> int:
    position = 0
    for job in storage.read_jobs(paths):
        if str(job.get("jobType") or "loop") != job_type:
            continue
        if str(job.get("status") or "") not in {"queued", "running"}:
            continue
        if task_id is not None and str(job.get("taskId") or "") != task_id:
            continue
        position = max(position, int(job.get("queuePosition") or 0))
    return position + 1


def _find_next_queued_background_job(paths: storage.Paths, task_id: Optional[str], exclude_job_id: Optional[str] = None, job_type: str = "loop") -> Optional[Dict[str, Any]]:
    candidates = _ordered_queued_background_jobs(paths, task_id, job_type, exclude_job_id)
    if not candidates:
        return None
    return candidates[0]


def _sync_loop_queue(root: Path, task_id: str, active_job_id: Optional[str] = None, exclude_job_id: Optional[str] = None) -> List[Dict[str, Any]]:
    paths = storage.project_paths(root)
    queued_jobs = _ordered_queued_background_jobs(paths, task_id, "loop", exclude_job_id)
    queueing.sync_loop_queue(root, task_id, [str(job.get("jobId") or "") for job in queued_jobs], active_job_id=active_job_id)
    return queued_jobs


def _cancel_queued_background_jobs_unlocked(runtime: LoopRuntime, task_id: str, exclude_job_id: Optional[str], message: str) -> int:
    cancelled = 0
    for job in storage.read_jobs(storage.project_paths(runtime.root)):
        if str(job.get("jobType") or "loop") != "loop":
            continue
        if str(job.get("status") or "") != "queued":
            continue
        if str(job.get("taskId") or "") != task_id:
            continue
        if exclude_job_id and str(job.get("jobId") or "") == exclude_job_id:
            continue
        runtime.write_job_unlocked(
            storage.default_job(
                {
                    **job,
                    "status": "cancelled",
                    "cancelRequested": True,
                    "finishedAt": utc_now(),
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": message,
                    "error": None,
                }
            )
        )
        cancelled += 1
    state = runtime.read_state_unlocked()
    active_job_id = queueing.current_loop_claim(runtime.root, task_id) if queueing.redis_enabled(runtime.root) else (str(current_loop_state(state).get("jobId") or "").strip() or None)
    _sync_loop_queue(runtime.root, task_id, active_job_id=active_job_id, exclude_job_id=exclude_job_id if active_job_id == exclude_job_id else None)
    return cancelled


def _new_loop_job_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    entropy = os.urandom(8).hex()[:6]
    return f"job-{stamp}-{entropy}"


def _find_active_target_dispatch(runtime: LoopRuntime, task_id: str, target: str) -> Optional[Dict[str, Any]]:
    from . import dispatch

    normalized_target = str(target or "").strip().lower()
    for job in dispatch.active_target_jobs(storage.project_paths(runtime.root), task_id, include_partial=True):
        if str(job.get("target") or "").strip().lower() == normalized_target:
            return job
    return None


def _launch_loop_sidecar(
    runtime: LoopRuntime,
    task: Dict[str, Any],
    target: str,
    *,
    round_number: int,
    loop_job_id: str,
    timeout_target: Optional[str] = None,
    last_message: str,
    launched_message: str,
    partial_summary: bool = False,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from . import dispatch

    task_id = str(task.get("taskId") or "").strip()
    existing = _find_active_target_dispatch(runtime, task_id, target)
    if isinstance(existing, dict):
        runtime.append_step(
            "dispatch",
            "Reused active loop sidecar dispatch.",
            {
                "taskId": task_id,
                "jobId": existing.get("jobId"),
                "target": target,
                "round": round_number,
                "loopJobId": loop_job_id,
            },
        )
        return existing

    task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
    timeout_seconds = target_timeout_seconds(task_runtime.get("targetTimeouts"), timeout_target or target)
    job = dispatch.create_target_job(
        runtime,
        task,
        target,
        {
            "partialSummary": partial_summary,
            "timeoutSeconds": timeout_seconds,
            "lastMessage": last_message,
            "metadata": {
                "trigger": "loop-sidecar",
                "round": round_number,
                "loopJobId": loop_job_id,
                "sidecar": True,
                **(extra_metadata or {}),
            },
        },
    )
    try:
        dispatch.launch_dispatch_job_runner(job, runtime.root)
    except Exception as exc:  # noqa: BLE001
        runtime.mutate_job(
            str(job.get("jobId") or ""),
            lambda existing: storage.default_job(
                {
                    **(existing or {}),
                    "status": "error",
                    "finishedAt": utc_now(),
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": "Loop-sidecar launch failed.",
                    "error": str(exc),
                }
            ),
        )
        raise
    runtime.append_step(
        "dispatch",
        launched_message,
        {
            "taskId": task_id,
            "jobId": job.get("jobId"),
            "target": target,
            "round": round_number,
            "loopJobId": loop_job_id,
            "timeoutSeconds": timeout_seconds,
            "partialSummary": partial_summary,
        },
    )
    return job


def create_loop_job(
    runtime: LoopRuntime,
    task: Dict[str, Any],
    rounds: int,
    delay_ms: int,
    mode: str = "background",
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    overrides = overrides or {}
    job_id = _new_loop_job_id()
    queued_at = utc_now()
    queue_position = max(0, int(overrides.get("queuePosition") or 0))
    update_loop_state = bool(overrides.get("updateLoopState", True))
    worker_count = overrides.get("workerCount")
    if worker_count is None:
        runtime_config = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        direct_baseline_mode = normalize_direct_baseline_mode(runtime_config.get("directBaselineMode"))
        resolved_worker_count = 0 if direct_baseline_mode == "single" else len(task_workers(task))
    else:
        resolved_worker_count = max(0, int(worker_count))
    queued_message = str(
        overrides.get("lastMessage")
        or ("Queued behind another background loop." if queue_position > 0 else "Queued background loop.")
    )
    job = storage.default_job(
        {
            "jobId": job_id,
            "taskId": task["taskId"],
            "mode": mode,
            "status": "queued",
            "queuePosition": queue_position,
            "attempt": max(1, int(overrides.get("attempt") or 1)),
            "resumeOfJobId": overrides.get("resumeOfJobId"),
            "retryOfJobId": overrides.get("retryOfJobId"),
            "resumeFromRound": max(1, int(overrides.get("resumeFromRound") or 1)),
            "rounds": rounds,
            "delayMs": delay_ms,
            "workerCount": resolved_worker_count,
            "usage": overrides.get("usage") if isinstance(overrides.get("usage"), dict) else storage.default_usage_state(),
            "queuedAt": queued_at,
            "lastMessage": queued_message,
            "results": overrides.get("results") if isinstance(overrides.get("results"), list) else [],
            "completedRounds": int(overrides.get("completedRounds") or 0),
            "error": overrides.get("error"),
        }
    )

    with runtime.with_lock():
        runtime.write_job_unlocked(job)
        if update_loop_state:
            state = runtime.read_state_unlocked()
            state = set_loop_state(
                state,
                {
                    "status": "queued",
                    "jobId": job_id,
                    "mode": mode,
                    "totalRounds": rounds,
                    "completedRounds": int(overrides.get("completedRounds") or 0),
                    "currentRound": 0,
                    "delayMs": delay_ms,
                    "cancelRequested": False,
                    "queuedAt": queued_at,
                    "startedAt": None,
                    "finishedAt": None,
                    "lastHeartbeatAt": None,
                    "lastMessage": queued_message,
                },
            )
            runtime.write_state_unlocked(state)

    runtime.append_step(
        "autoloop",
        "Background loop queued." if queue_position == 0 else "Background loop queued behind another job.",
        {
            "taskId": task["taskId"],
            "jobId": job_id,
            "rounds": rounds,
            "delayMs": delay_ms,
            "queuePosition": queue_position,
            "resumeOfJobId": job.get("resumeOfJobId"),
            "retryOfJobId": job.get("retryOfJobId"),
            "resumeFromRound": job.get("resumeFromRound"),
        },
    )
    return job


def _launch_answer_now_sidecar(
    runtime: LoopRuntime,
    task: Dict[str, Any],
    round_number: int,
    loop_job_id: str,
) -> Optional[Dict[str, Any]]:
    return _launch_loop_sidecar(
        runtime,
        task,
        "answer_now",
        round_number=round_number,
        loop_job_id=loop_job_id,
        timeout_target="answer_now",
        last_message="Queued partial summary from current checkpoints.",
        launched_message="Loop launched Answer Now as a non-blocking sidecar.",
        partial_summary=True,
    )


def _launch_direct_baseline_sidecar(
    runtime: LoopRuntime,
    task: Dict[str, Any],
    round_number: int,
    loop_job_id: str,
) -> Optional[Dict[str, Any]]:
    return _launch_loop_sidecar(
        runtime,
        task,
        "direct_baseline",
        round_number=round_number,
        loop_job_id=loop_job_id,
        timeout_target="direct_baseline",
        last_message="Queued single-thread baseline from the current prompt.",
        launched_message="Loop launched the single-thread baseline as a non-blocking sidecar.",
    )


def _subprocess_kwargs(env_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    env = os.environ.copy()
    if env_overrides:
        for key, value in env_overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
    kwargs: Dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "cwd": str(Path(__file__).resolve().parents[2]),
        "env": env,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    return kwargs


def launch_loop_job_runner(job: Dict[str, Any], root: Optional[Path] = None) -> None:
    repo_root = Path(root).resolve() if root else Path(__file__).resolve().parents[2]
    auth_path = control.auth_file_path(repo_root)
    topology = deployment_topology(repo_root)
    env_overrides: Dict[str, str] = {
        "LOOP_ROOT": str(repo_root),
        "LOOP_DEPLOYMENT_PROFILE": topology.profile,
        "LOOP_QUEUE_BACKEND": topology.queue_backend,
        "LOOP_METADATA_BACKEND": topology.metadata_backend,
        "LOOP_ARTIFACT_BACKEND": topology.artifact_backend,
        "LOOP_SECRET_BACKEND": topology.secret_backend,
        "LOOP_RUNTIME_EXECUTION_BACKEND": topology.runtime_execution_backend,
        "LOOP_HOST": topology.host,
        "LOOP_PORT": str(topology.port),
        "LOOP_RUNTIME_HOST": topology.runtime_host,
        "LOOP_RUNTIME_PORT": str(topology.runtime_port),
        "LOOP_AUTH_FILE": str(auth_path),
    }
    optional_overrides = {
        "LOOP_SECRET_FILE": str(topology.secret_file) if topology.secret_file else None,
        "LOOP_RUNTIME_SERVICE_URL": topology.runtime_service_url,
        "LOOP_DATABASE_URL": topology.database_url,
        "LOOP_REDIS_URL": topology.redis_url,
        "LOOP_OBJECT_STORE_URL": topology.object_store_url,
        "LOOP_OBJECT_STORE_BUCKET": topology.object_store_bucket,
        "LOOP_OBJECT_STORE_HEALTHCHECK_URL": topology.object_store_healthcheck_url,
        "LOOP_OBJECT_STORE_ACCESS_KEY": topology.object_store_access_key,
        "LOOP_OBJECT_STORE_SECRET_KEY": topology.object_store_secret_key,
        "LOOP_OBJECT_STORE_REGION": topology.object_store_region,
        "LOOP_SECRET_PROVIDER_URL": topology.secret_provider_url,
        "LOOP_SECRET_PROVIDER_HEALTHCHECK_URL": topology.secret_provider_healthcheck_url,
    }
    for key, value in optional_overrides.items():
        if value is not None:
            env_overrides[key] = value
        else:
            env_overrides[key] = None
    command = [
        sys.executable,
        "-m",
        "backend.workers.loop_job",
        f"--root={repo_root}",
        f"--job-id={job['jobId']}",
        f"--auth-path={auth_path}",
    ]
    subprocess.Popen(command, **_subprocess_kwargs(env_overrides))  # noqa: S603,S607


def _usage_snapshot(runtime: LoopRuntime) -> Dict[str, Any]:
    state = runtime.read_state()
    usage = state.get("usage") if isinstance(state.get("usage"), dict) else {}
    return storage.normalize_usage_state(usage)


def loop_target_label(target: str) -> str:
    normalized = str(target or "").strip().lower()
    if normalized == "workers":
        return "Workers"
    if normalized == "commander":
        return "Commander"
    if normalized == "direct_baseline":
        return "Direct baseline"
    if normalized == "commander_review":
        return "Commander Review"
    if normalized == "summarizer":
        return "Summarizer"
    if normalized == "answer_now":
        return "Partial summarizer"
    if normalized == "arbiter":
        return "External arbiter"
    if len(normalized) == 1 and normalized.isalpha():
        return f"Worker {normalized.upper()}"
    return normalized or "Target"


def update_loop_job_progress(
    runtime: LoopRuntime,
    job_id: str,
    task_id: str,
    round_number: int,
    rounds: int,
    target: str,
    waiting: bool = False,
    active_targets: Optional[List[str]] = None,
) -> None:
    target_label = loop_target_label(target)
    normalized_active_targets = [
        str(value).strip()
        for value in (active_targets or [target])
        if str(value).strip()
    ][:12]
    loop_message = (
        f"Waiting on {target_label} during round {round_number} of {rounds}."
        if waiting
        else f"Running {target_label} during round {round_number} of {rounds}."
    )
    job_message = (
        f"Waiting on {target_label}."
        if waiting
        else f"Running {target_label}."
    )
    with runtime.with_lock():
        state = runtime.read_state_unlocked()
        active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
        if isinstance(active_task, dict) and str(active_task.get("taskId") or "") == task_id:
            state = set_loop_state(
                state,
                {
                    "status": "running",
                    "jobId": job_id,
                    "mode": "background",
                    "totalRounds": rounds,
                    "currentRound": round_number,
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": loop_message,
                    "activeTargets": normalized_active_targets,
                },
            )
            runtime.write_state_unlocked(state)
        existing_job = runtime.read_job_unlocked(job_id) or {"jobId": job_id, "taskId": task_id}
        metadata = dict(existing_job.get("metadata") or {}) if isinstance(existing_job.get("metadata"), dict) else {}
        metadata["activeTargets"] = normalized_active_targets
        runtime.write_job_unlocked(
            storage.default_job(
                {
                    **existing_job,
                    "status": str(existing_job.get("status") or "running"),
                    "currentRound": round_number,
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": job_message,
                    "metadata": metadata,
                }
            )
        )


def start_loop_target_heartbeat(
    runtime: LoopRuntime,
    job_id: str,
    task_id: str,
    round_number: int,
    rounds: int,
    target: str,
    interval_seconds: float = 10.0,
    active_targets: Optional[List[str]] = None,
) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()

    def keepalive() -> None:
        while not stop_event.wait(interval_seconds):
            try:
                update_loop_job_progress(runtime, job_id, task_id, round_number, rounds, target, waiting=True, active_targets=active_targets)
            except Exception:
                return

    thread = threading.Thread(
        target=keepalive,
        name=f"loop-heartbeat-{job_id}-{target}",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def _promote_next_queued_loop_job(runtime: LoopRuntime, task_id: Optional[str], finished_job_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not task_id:
        return None
    next_job: Optional[Dict[str, Any]] = None
    with runtime.with_lock():
        state = runtime.read_state_unlocked()
        active_task_id = str(((state.get("activeTask") or {}) if isinstance(state.get("activeTask"), dict) else {}).get("taskId") or "")
        if active_task_id != task_id:
            return None
        current_active_job_id = queueing.current_loop_claim(runtime.root, task_id) if queueing.redis_enabled(runtime.root) else (str(current_loop_state(state).get("jobId") or "").strip() or None)
        if finished_job_id:
            queueing.release_loop_claim(runtime.root, task_id, finished_job_id)
            if current_active_job_id == finished_job_id:
                current_active_job_id = None
        queued_jobs = _sync_loop_queue(runtime.root, task_id, active_job_id=current_active_job_id, exclude_job_id=finished_job_id if not queueing.redis_enabled(runtime.root) else None)
        if queueing.redis_enabled(runtime.root):
            next_job_id = queueing.claim_next_loop_job_id(
                runtime.root,
                task_id,
                [str(job.get("jobId") or "") for job in queued_jobs],
                active_job_id=current_active_job_id,
            )
            if not next_job_id:
                return None
            next_job_raw = runtime.read_job_unlocked(next_job_id)
            if not isinstance(next_job_raw, dict):
                queueing.release_loop_claim(runtime.root, task_id, next_job_id)
                return None
            next_job = storage.default_job(next_job_raw)
        else:
            next_job = _find_next_queued_background_job(storage.project_paths(runtime.root), task_id, finished_job_id)
            if next_job is None:
                return None
        next_job = runtime.write_job_unlocked(
            storage.default_job(
                {
                    **next_job,
                    "status": "queued",
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": "Queued background loop.",
                }
            )
        )
        state = set_loop_state(
            state,
            {
                "status": "queued",
                "jobId": next_job["jobId"],
                "mode": next_job.get("mode") or "background",
                "totalRounds": int(next_job.get("rounds") or 0),
                "completedRounds": int(next_job.get("completedRounds") or 0),
                "currentRound": 0,
                "delayMs": int(next_job.get("delayMs") or 0),
                "cancelRequested": False,
                "queuedAt": next_job.get("queuedAt") or utc_now(),
                "startedAt": None,
                "finishedAt": None,
                "lastHeartbeatAt": None,
                "lastMessage": "Queued background loop.",
            },
        )
        runtime.write_state_unlocked(state)
    if next_job is None:
        return None
    launch_loop_job_runner(next_job, runtime.root)
    runtime.append_step(
        "autoloop",
        "Background loop process launched.",
        {
            "taskId": next_job.get("taskId"),
            "jobId": next_job["jobId"],
            "rounds": next_job.get("rounds"),
            "delayMs": next_job.get("delayMs"),
            "queuePosition": next_job.get("queuePosition"),
        },
    )
    return next_job


def execute_loop_job(job_id: str, root: Optional[Path] = None, auth_path: Optional[Path] = None) -> Dict[str, Any]:
    runtime = LoopRuntime(Path(root).resolve() if root else Path(__file__).resolve().parents[2], auth_path=auth_path)
    runtime.ensure_data_paths()
    with runtime.with_lock():
        job = runtime.read_job_unlocked(job_id)
    if not isinstance(job, dict):
        raise RuntimeErrorWithCode(f"Job not found: {job_id}", 404)

    if str(job.get("status") or "queued") == "cancelled":
        runtime.append_step(
            "autoloop",
            "Background runner exited because the job was already cancelled.",
            {"taskId": job.get("taskId"), "jobId": job_id},
        )
        return {"message": "Loop was already cancelled.", "completedRounds": int(job.get("completedRounds") or 0), "results": job.get("results") or []}

    rounds = clamp_loop_rounds(job.get("rounds"))
    delay_ms = clamp_loop_delay_ms(job.get("delayMs"))
    task_id = str(job.get("taskId") or "").strip()
    start_round = max(1, min(rounds, int(job.get("resumeFromRound") or 1)))
    results = list(job.get("results") or [])
    completed_rounds = max(0, int(job.get("completedRounds") or 0))
    cancelled = False
    snapshot = runtime.read_state()
    active_task_snapshot = snapshot.get("activeTask") if isinstance(snapshot.get("activeTask"), dict) else None
    direct_baseline_mode = normalize_direct_baseline_mode(
        (((active_task_snapshot or {}).get("runtime") or {}) if isinstance((active_task_snapshot or {}).get("runtime"), dict) else {}).get("directBaselineMode")
    )
    direct_baseline_existing = isinstance(snapshot.get("directBaseline"), dict)
    direct_baseline_sidecar_attempted = direct_baseline_existing

    if direct_baseline_mode == "single":
        rounds = 1
        start_round = 1

    with runtime.with_lock():
        state = runtime.read_state_unlocked()
        active_task_id = str(((state.get("activeTask") or {}) if isinstance(state.get("activeTask"), dict) else {}).get("taskId") or "")
        if active_task_id != task_id:
            raise RuntimeErrorWithCode("No active task.", 400)
        state = set_loop_state(
            state,
            {
                "status": "running",
                "jobId": job_id,
                "mode": "background",
                "totalRounds": rounds,
                "completedRounds": completed_rounds,
                "delayMs": delay_ms,
                "startedAt": current_loop_state(state).get("startedAt") or utc_now(),
                "finishedAt": None,
                "lastHeartbeatAt": utc_now(),
                "lastMessage": f"Preparing round {start_round}.",
            },
        )
        runtime.write_state_unlocked(state)
        runtime.write_job_unlocked(
            storage.default_job(
                {
                    **job,
                    "status": "running",
                    "rounds": rounds,
                    "delayMs": delay_ms,
                    "completedRounds": completed_rounds,
                    "startedAt": current_loop_state(state).get("startedAt"),
                    "finishedAt": None,
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": f"Preparing round {start_round}.",
                }
            )
        )

    runtime.append_step(
        "autoloop",
        "Background loop runner claimed job.",
        {"taskId": task_id, "jobId": job_id, "mode": "background", "rounds": rounds, "delayMs": delay_ms},
    )

    def _execute_loop_target(
        target: str,
        round_number: int,
        *,
        isolated: bool = False,
        options: Optional[Dict[str, Any]] = None,
        active_targets: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        update_loop_job_progress(runtime, job_id, task_id, round_number, rounds, target, waiting=False, active_targets=active_targets)
        heartbeat_stop, heartbeat_thread = start_loop_target_heartbeat(
            runtime,
            job_id,
            task_id,
            round_number,
            rounds,
            target,
            active_targets=active_targets,
        )
        try:
            faults.maybe_raise_fault(
                "loop.execute.before_target",
                f"loop.execute.before_target.{target.lower()}",
            )
            target_runtime = LoopRuntime(runtime.root, auth_path=runtime.auth_path) if isolated else runtime
            target_result = runtime_execution.run_target(target_runtime, target, task_id, dict(options or {}))
            faults.maybe_raise_fault(
                "loop.execute.after_target",
                f"loop.execute.after_target.{target.lower()}",
            )
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1.0)
        usage_snapshot = _usage_snapshot(runtime)
        with runtime.with_lock():
            state = runtime.read_state_unlocked()
            state = set_loop_state(state, {"lastHeartbeatAt": utc_now()})
            runtime.write_state_unlocked(state)
            existing_job = runtime.read_job_unlocked(job_id) or job
            runtime.write_job_unlocked(
                storage.default_job(
                    {
                        **existing_job,
                        "status": str(existing_job.get("status") or "running"),
                        "currentRound": round_number,
                        "lastHeartbeatAt": utc_now(),
                        "usage": usage_snapshot,
                    }
                )
            )
        runtime.append_step(
            "autoloop",
            "Autonomous target completed.",
            {
                "taskId": task_id,
                "jobId": job_id,
                "round": round_number,
                "target": target,
                "exitCode": target_result.get("exitCode"),
                "outputPreview": target_result.get("output"),
            },
        )
        return target_result

    def _execute_parallel_targets(
        targets: List[str],
        round_number: int,
        *,
        auxiliary_targets: Optional[List[str]] = None,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        auxiliary = {str(item).strip().lower() for item in (auxiliary_targets or []) if str(item).strip()}
        slots: List[Dict[str, Any]] = [
            {"target": str(target).strip(), "result": None, "error": None}
            for target in targets
            if str(target).strip()
        ]
        if not slots:
            return [], []

        runtime.append_step(
            "autoloop",
            "Starting parallel lane fan-out.",
            {
                "taskId": task_id,
                "jobId": job_id,
                "round": round_number,
                "targets": [slot["target"] for slot in slots],
                "auxiliaryTargets": sorted(auxiliary),
            },
        )
        active_parallel_targets = [slot["target"] for slot in slots]
        update_loop_job_progress(
            runtime,
            job_id,
            task_id,
            round_number,
            rounds,
            "workers",
            waiting=False,
            active_targets=active_parallel_targets,
        )

        def _run_slot(slot: Dict[str, Any]) -> None:
            try:
                slot["result"] = _execute_loop_target(
                    slot["target"],
                    round_number,
                    isolated=True,
                    active_targets=active_parallel_targets,
                )
            except Exception as exc:  # noqa: BLE001
                slot["error"] = exc

        threads: List[threading.Thread] = []
        for slot in slots:
            thread = threading.Thread(
                target=_run_slot,
                args=(slot,),
                name=f"loop-target-{job_id}-{slot['target']}",
                daemon=True,
            )
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()

        primary_results: List[Dict[str, Any]] = []
        auxiliary_results: List[Dict[str, Any]] = []
        primary_errors: List[Exception] = []
        for slot in slots:
            target_name = str(slot["target"] or "").strip()
            normalized_target = target_name.lower()
            error = slot.get("error")
            if error is not None:
                if normalized_target in auxiliary:
                    runtime.append_step(
                        "error",
                        "Parallel auxiliary target failed while the main loop continued.",
                        {
                            "taskId": task_id,
                            "jobId": job_id,
                            "round": round_number,
                            "target": target_name,
                            "error": str(error),
                        },
                    )
                    continue
                primary_errors.append(error)
                continue
            result = slot.get("result")
            if isinstance(result, dict):
                if normalized_target in auxiliary:
                    auxiliary_results.append(result)
                else:
                    primary_results.append(result)
        if primary_errors:
            raise primary_errors[0]
        return primary_results, auxiliary_results

    try:
        for round_number in range(start_round, rounds + 1):
            snapshot = runtime.read_state()
            active_task = snapshot.get("activeTask") if isinstance(snapshot.get("activeTask"), dict) else None
            if not isinstance(active_task, dict) or str(active_task.get("taskId") or "") != task_id:
                raise RuntimeErrorWithCode("No active task.", 400)
            if bool(current_loop_state(snapshot).get("cancelRequested")):
                cancelled = True
                break

            with runtime.with_lock():
                state = runtime.read_state_unlocked()
                active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
                if not isinstance(active_task, dict) or str(active_task.get("taskId") or "") != task_id:
                    raise RuntimeErrorWithCode("No active task.", 400)
                state = set_loop_state(
                    state,
                    {
                        "status": "running",
                        "currentRound": round_number,
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": f"Running round {round_number} of {rounds}.",
                    },
                )
                runtime.write_state_unlocked(state)
                existing_job = runtime.read_job_unlocked(job_id) or job
                runtime.write_job_unlocked(
                    storage.default_job(
                        {
                            **existing_job,
                            "status": "running",
                            "currentRound": round_number,
                            "lastHeartbeatAt": utc_now(),
                            "lastMessage": f"Running round {round_number}.",
                        }
                    )
                )

            runtime.append_step(
                "autoloop",
                "Starting autonomous round.",
                {"taskId": task_id, "jobId": job_id, "round": round_number, "totalRounds": rounds},
            )

            round_workers = [] if direct_baseline_mode == "single" else task_workers(active_task, round_number)
            if direct_baseline_mode == "both" and not direct_baseline_sidecar_attempted:
                direct_baseline_sidecar_attempted = True
                try:
                    _launch_direct_baseline_sidecar(runtime, active_task, round_number, job_id)
                except Exception as exc:  # noqa: BLE001
                    runtime.append_step(
                        "error",
                        "Failed to launch non-blocking direct baseline sidecar; the main loop continued.",
                        {
                            "taskId": task_id,
                            "jobId": job_id,
                            "round": round_number,
                            "target": "direct_baseline",
                            "error": str(exc),
                        },
                    )
            if direct_baseline_mode == "single":
                if direct_baseline_existing:
                    sequence: List[str] = []
                    runtime.append_step(
                        "direct_baseline",
                        "Reused the existing direct baseline for single-answer mode.",
                        {"taskId": task_id, "jobId": job_id, "round": round_number},
                    )
                else:
                    sequence = ["direct_baseline"]
            else:
                sequence = ["commander", "commander_review", "summarizer"]
            round_result: Dict[str, Any] = {"round": round_number, "targets": []}

            for target in sequence:
                if target == "commander_review" and round_workers:
                    try:
                        _launch_answer_now_sidecar(runtime, active_task, round_number, job_id)
                    except Exception as exc:  # noqa: BLE001
                        runtime.append_step(
                            "error",
                            "Failed to launch non-blocking Answer Now sidecar; the main loop continued.",
                            {
                                "taskId": task_id,
                                "jobId": job_id,
                                "round": round_number,
                                "target": "answer_now",
                                "error": str(exc),
                            },
                        )
                    parallel_results, auxiliary_results = _execute_parallel_targets(
                        [*[str(worker["id"]) for worker in round_workers]],
                        round_number,
                    )
                    round_result["targets"].extend(parallel_results)
                    if auxiliary_results:
                        round_result.setdefault("parallelTargets", [])
                        round_result["parallelTargets"].extend(auxiliary_results)
                target_result = _execute_loop_target(target, round_number)
                round_result["targets"].append(target_result)

            results.append(round_result)
            completed_rounds = round_number
            usage_snapshot = _usage_snapshot(runtime)
            with runtime.with_lock():
                state = runtime.read_state_unlocked()
                state = set_loop_state(
                    state,
                    {
                        "status": "running",
                        "completedRounds": round_number,
                        "currentRound": 0,
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": f"Completed round {round_number} of {rounds}.",
                        "activeTargets": [],
                    },
                )
                runtime.write_state_unlocked(state)
                existing_job = runtime.read_job_unlocked(job_id) or job
                existing_results = list(existing_job.get("results") or [])
                existing_results.append(round_result)
                runtime.write_job_unlocked(
                    storage.default_job(
                        {
                            **existing_job,
                            "status": "running",
                            "completedRounds": round_number,
                            "currentRound": 0,
                            "lastHeartbeatAt": utc_now(),
                            "lastMessage": f"Completed round {round_number}.",
                            "results": existing_results,
                            "usage": usage_snapshot,
                        }
                    )
                )

            runtime.append_step(
                "autoloop",
                "Autonomous round completed.",
                {"taskId": task_id, "jobId": job_id, "round": round_number, "totalRounds": rounds},
            )

            if round_number >= rounds or delay_ms <= 0:
                continue

            remaining_ms = delay_ms
            while remaining_ms > 0:
                time.sleep(min(250, remaining_ms) / 1000.0)
                remaining_ms -= 250
                snapshot = runtime.read_state()
                active_task = snapshot.get("activeTask") if isinstance(snapshot.get("activeTask"), dict) else None
                if not isinstance(active_task, dict) or str(active_task.get("taskId") or "") != task_id:
                    raise RuntimeErrorWithCode("No active task.", 400)
                if bool(current_loop_state(snapshot).get("cancelRequested")):
                    cancelled = True
                    break
            if cancelled:
                break

        final_status = "cancelled" if cancelled else "completed"
        final_message = f"Cancelled after {completed_rounds} completed round(s)." if cancelled else f"Completed {completed_rounds} round(s)."
        usage_snapshot = _usage_snapshot(runtime)
        with runtime.with_lock():
            state = runtime.read_state_unlocked()
            active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
            if isinstance(active_task, dict) and str(active_task.get("taskId") or "") == task_id:
                state = set_loop_state(
                    state,
                    {
                        "status": final_status,
                        "jobId": job_id,
                        "mode": "background",
                        "totalRounds": rounds,
                        "completedRounds": completed_rounds,
                        "currentRound": 0,
                        "delayMs": delay_ms,
                        "finishedAt": utc_now(),
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": final_message,
                        "activeTargets": [],
                    },
                )
                runtime.write_state_unlocked(state)
            existing_job = runtime.read_job_unlocked(job_id) or job
            metadata = dict(existing_job.get("metadata") or {}) if isinstance(existing_job.get("metadata"), dict) else {}
            metadata["activeTargets"] = []
            runtime.write_job_unlocked(
                storage.default_job(
                    {
                        **existing_job,
                        "status": final_status,
                        "completedRounds": completed_rounds,
                        "currentRound": 0,
                        "finishedAt": utc_now(),
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": final_message,
                        "results": results,
                        "usage": usage_snapshot,
                        "metadata": metadata,
                    }
                )
            )

        runtime.append_step(
            "autoloop",
            "Autonomous loop cancelled." if cancelled else "Autonomous loop completed.",
            {
                "taskId": task_id,
                "jobId": job_id,
                "completedRounds": completed_rounds,
                "requestedRounds": rounds,
            },
        )
        _promote_next_queued_loop_job(runtime, task_id, job_id)
        return {
            "message": "Loop cancelled." if cancelled else "Loop completed.",
            "completedRounds": completed_rounds,
            "requestedRounds": rounds,
            "cancelled": cancelled,
            "results": results,
        }
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        final_status = "budget_exhausted" if message.startswith("Budget limit reached:") else "error"
        final_message = message if final_status == "budget_exhausted" else f"Loop error: {message}"
        usage_snapshot = _usage_snapshot(runtime)
        with runtime.with_lock():
            state = runtime.read_state_unlocked()
            active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
            if isinstance(active_task, dict) and str(active_task.get("taskId") or "") == task_id:
                state = set_loop_state(
                    state,
                    {
                        "status": final_status,
                        "jobId": job_id,
                        "mode": "background",
                        "totalRounds": rounds,
                        "completedRounds": completed_rounds,
                        "currentRound": 0,
                        "delayMs": delay_ms,
                        "finishedAt": utc_now(),
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": final_message,
                        "activeTargets": [],
                    },
                )
                runtime.write_state_unlocked(state)
            existing_job = runtime.read_job_unlocked(job_id) or job
            metadata = dict(existing_job.get("metadata") or {}) if isinstance(existing_job.get("metadata"), dict) else {}
            metadata["activeTargets"] = []
            runtime.write_job_unlocked(
                storage.default_job(
                    {
                        **existing_job,
                        "status": final_status,
                        "completedRounds": completed_rounds,
                        "currentRound": 0,
                        "finishedAt": utc_now(),
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": final_message,
                        "results": results,
                        "usage": usage_snapshot,
                        "error": message,
                        "metadata": metadata,
                    }
                )
            )
        runtime.append_step(
            "budget" if final_status == "budget_exhausted" else "error",
            "Autonomous loop stopped at the configured budget limit." if final_status == "budget_exhausted" else "Autonomous loop failed.",
            {
                "taskId": task_id,
                "jobId": job_id,
                "completedRounds": completed_rounds,
                "status": final_status,
                "error": message,
            },
        )
        _promote_next_queued_loop_job(runtime, task_id, job_id)
        raise


def start_loop(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    paths = storage.project_paths(runtime.root)
    state = storage.read_state_payload(paths)
    if not isinstance(state.get("activeTask"), dict):
        raise RuntimeErrorWithCode("No active task. Start one first.", 400)
    if _active_job_count(paths, str(state["activeTask"].get("taskId") or ""), "target", include_partial=True) > 0:
        raise RuntimeErrorWithCode("Target dispatch jobs are still running. Wait for them to finish before starting the autonomous loop.", 409)

    task = state["activeTask"]
    task_id = str(task.get("taskId") or "")
    if _active_job_count(paths, task_id, "loop") >= storage.LOOP_QUEUE_LIMIT:
        raise RuntimeErrorWithCode("Background loop queue is full. Cancel or finish an existing queued job first.", 409)

    rounds = clamp_loop_rounds(payload.get("rounds", 3))
    delay_ms = clamp_loop_delay_ms(payload.get("delayMs", 1000))
    runtime_config = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
    direct_baseline_mode = normalize_direct_baseline_mode(runtime_config.get("directBaselineMode"))
    effective_rounds = 1 if direct_baseline_mode == "single" else rounds
    effective_worker_count = 0 if direct_baseline_mode == "single" else len(task_workers(task))
    had_active_loop = loop_is_active(state)
    queue_position = _next_background_queue_position(paths, task_id, "loop") if had_active_loop else 0
    job = create_loop_job(
        runtime,
        task,
        effective_rounds,
        delay_ms,
        "background",
        {
            "queuePosition": queue_position,
            "updateLoopState": not had_active_loop,
            "lastMessage": "Queued behind another background loop." if queue_position > 0 else "Queued background loop.",
            "workerCount": effective_worker_count,
        },
    )
    try:
        started = False
        if queueing.redis_enabled(runtime.root):
            active_job_id = queueing.current_loop_claim(runtime.root, task_id)
            _sync_loop_queue(runtime.root, task_id, active_job_id=active_job_id)
            if not had_active_loop:
                promoted = _promote_next_queued_loop_job(runtime, task_id, None)
                started = bool(promoted and str(promoted.get("jobId") or "") == str(job.get("jobId") or ""))
        elif queue_position == 0 and not had_active_loop:
            launch_loop_job_runner(job, runtime.root)
            started = True
        return {
            "message": "Background loop queued." if queue_position > 0 or not started else "Background loop started.",
            "jobId": job["jobId"],
            "rounds": effective_rounds,
            "delayMs": delay_ms,
            "queuePosition": queue_position,
        }
    except Exception as exc:  # noqa: BLE001
        with runtime.with_lock():
            state = runtime.read_state_unlocked()
            state = set_loop_state(state, {"status": "error", "lastMessage": "Background launch failed."})
            runtime.write_state_unlocked(state)
            runtime.write_job_unlocked(
                storage.default_job(
                    {
                        **job,
                        "status": "error",
                        "finishedAt": utc_now(),
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": "Background launch failed.",
                        "error": str(exc),
                    }
                )
            )
        queueing.release_loop_claim(runtime.root, task_id, str(job.get("jobId") or ""))
        _sync_loop_queue(runtime.root, task_id)
        runtime.append_step("error", "Failed to launch background loop.", {"taskId": task_id, "jobId": job["jobId"], "error": str(exc)})
        raise RuntimeErrorWithCode(str(exc), 500) from exc


def cancel_loop(root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    paths = storage.project_paths(runtime.root)
    state = storage.read_state_payload(paths)
    if not loop_is_active(state):
        raise RuntimeErrorWithCode("No autonomous loop is currently running.", 400)

    loop = current_loop_state(state)
    task_id = str(((state.get("activeTask") or {}) if isinstance(state.get("activeTask"), dict) else {}).get("taskId") or "")
    job_id = str(loop.get("jobId") or "").strip() or None

    queued_cancel_result: Optional[Dict[str, Any]] = None
    with runtime.with_lock():
        state_unlocked = runtime.read_state_unlocked()
        if str(loop.get("status") or "idle") == "queued":
            cancelled_queued_jobs = _cancel_queued_background_jobs_unlocked(runtime, task_id, job_id, "Cancelled before the queued loop could start.")
            state_unlocked = set_loop_state(
                state_unlocked,
                {
                    "status": "cancelled",
                    "cancelRequested": True,
                    "finishedAt": utc_now(),
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": "Cancelled before the background loop started.",
                },
            )
            runtime.write_state_unlocked(state_unlocked)
            if job_id:
                existing = runtime.read_job_unlocked(job_id) or {"jobId": job_id, "taskId": task_id}
                runtime.write_job_unlocked(
                    storage.default_job(
                        {
                            **existing,
                            "status": "cancelled",
                            "cancelRequested": True,
                            "finishedAt": utc_now(),
                            "lastHeartbeatAt": utc_now(),
                            "lastMessage": "Cancelled before start.",
                        }
                    )
                )
                queueing.release_loop_claim(runtime.root, task_id, job_id)
                _sync_loop_queue(runtime.root, task_id)
            queued_cancel_result = {"message": "Queued loop cancelled before start.", "queuedJobsCancelled": cancelled_queued_jobs}
        else:
            cancelled_queued_jobs = _cancel_queued_background_jobs_unlocked(runtime, task_id, job_id, "Cancelled because the active loop was stopped.")
            state_unlocked = set_loop_state(
                state_unlocked,
                {
                    "cancelRequested": True,
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": "Cancellation requested. The loop will stop after the current round.",
                },
            )
            runtime.write_state_unlocked(state_unlocked)
            if job_id:
                existing = runtime.read_job_unlocked(job_id) or {"jobId": job_id, "taskId": task_id}
                runtime.write_job_unlocked(
                    storage.default_job(
                        {
                            **existing,
                            "cancelRequested": True,
                            "lastHeartbeatAt": utc_now(),
                            "lastMessage": "Cancellation requested.",
                        }
                    )
                )
    if queued_cancel_result is not None:
        runtime.append_step(
            "autoloop",
            "Queued background loop cancelled before start.",
            {"taskId": task_id, "jobId": job_id, "queuedJobsCancelled": queued_cancel_result["queuedJobsCancelled"]},
        )
        return queued_cancel_result

    runtime.append_step(
        "autoloop",
        "Cancellation requested for the autonomous loop.",
        {
            "taskId": task_id,
            "jobId": job_id,
            "completedRounds": current_loop_state(storage.read_state_payload(paths)).get("completedRounds"),
            "queuedJobsCancelled": cancelled_queued_jobs,
        },
    )
    return {"message": "Cancellation requested.", "queuedJobsCancelled": cancelled_queued_jobs}


def manage_loop_job(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    paths = storage.project_paths(runtime.root)
    job_id = str(payload.get("jobId") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    if not job_id:
        raise RuntimeErrorWithCode("A jobId is required.", 400)
    if action not in {"resume", "retry", "cancel"}:
        raise RuntimeErrorWithCode("A valid action is required.", 400)

    state = storage.read_state_payload(paths)
    job = read_job(paths, job_id)
    if not isinstance(job, dict):
        raise RuntimeErrorWithCode("Job not found.", 404)
    task_id = str(job.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeErrorWithCode("Job is missing task metadata.", 409)

    if action == "cancel":
        if str(job.get("status") or "") == "queued" and str(current_loop_state(state).get("jobId") or "") == job_id:
            with runtime.with_lock():
                cancelled_queued_jobs = _cancel_queued_background_jobs_unlocked(runtime, task_id, job_id, "Cancelled before the queued loop could start.")
                current = runtime.read_state_unlocked()
                current = set_loop_state(
                    current,
                    {
                        "status": "cancelled",
                        "cancelRequested": True,
                        "finishedAt": utc_now(),
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": "Cancelled before the background loop started.",
                    },
                )
                runtime.write_state_unlocked(current)
                runtime.write_job_unlocked(
                    storage.default_job(
                        {
                            **job,
                            "status": "cancelled",
                            "cancelRequested": True,
                            "finishedAt": utc_now(),
                            "lastHeartbeatAt": utc_now(),
                            "lastMessage": "Cancelled before start.",
                        }
                    )
                )
            runtime.append_step(
                "autoloop",
                "Queued background loop cancelled from Review before start.",
                {"taskId": task_id, "jobId": job_id, "queuedJobsCancelled": cancelled_queued_jobs},
            )
            return {"message": "Queued loop cancelled before start.", "queuedJobsCancelled": cancelled_queued_jobs}

        if str(job.get("status") or "") not in {"queued", "interrupted"}:
            raise RuntimeErrorWithCode("Only queued or interrupted jobs can be cancelled here.", 409)
        updated = runtime.mutate_job(
            job_id,
            lambda existing: storage.default_job(
                {
                    **(existing or {}),
                    "status": "cancelled",
                    "cancelRequested": True,
                    "finishedAt": utc_now(),
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": "Cancelled from Review.",
                }
            ),
        )
        state_snapshot = storage.read_state_payload(paths)
        active_job_id = str(current_loop_state(state_snapshot).get("jobId") or "").strip() or None
        _sync_loop_queue(runtime.root, task_id, active_job_id=active_job_id)
        runtime.append_step(
            "autoloop",
            "Cancelled a queued or interrupted background job from Review.",
            {"taskId": task_id, "jobId": job_id, "previousStatus": job.get("status")},
        )
        return {"message": "Job cancelled.", "job": updated}

    if loop_is_active(state):
        raise RuntimeErrorWithCode("Cancel or finish the active loop before resuming or retrying another job.", 409)
    if action == "resume" and not job_status_can_resume(job.get("status")):
        raise RuntimeErrorWithCode("Only interrupted jobs can be resumed.", 409)
    if action == "retry" and not job_status_can_retry(job.get("status")):
        raise RuntimeErrorWithCode("This job cannot be retried.", 409)

    resume_from_round = 1
    seed_results: List[Dict[str, Any]] = []
    seed_completed_rounds = 0
    resume_source_job_id: Optional[str] = None
    retry_source_job_id: Optional[str] = None

    if action == "resume":
        resume_from_round = job_resume_round(job)
        if resume_from_round > int(job.get("rounds") or 0):
            raise RuntimeErrorWithCode("This interrupted job has no remaining rounds to resume. Retry it instead.", 409)
        seed_completed_rounds = max(0, int(job.get("completedRounds") or 0))
        seed_results = list(job.get("results") or [])
        resume_source_job_id = job_id
        active_task_id = str(((state.get("activeTask") or {}) if isinstance(state.get("activeTask"), dict) else {}).get("taskId") or "")
        if seed_completed_rounds > 0 and active_task_id != task_id:
            raise RuntimeErrorWithCode("Resume needs the interrupted task still loaded in state. Replay that session first or use Retry to restart from round 1.", 409)

    task_snapshot = storage.read_task_snapshot(task_id, paths)
    if not isinstance(task_snapshot, dict):
        raise RuntimeErrorWithCode("Task snapshot is missing, so this job cannot be restored.", 404)

    active_task_id = str(((state.get("activeTask") or {}) if isinstance(state.get("activeTask"), dict) else {}).get("taskId") or "")
    should_restore_snapshot = action == "retry" or seed_completed_rounds == 0 or active_task_id != task_id

    with runtime.with_lock():
        current = runtime.read_state_unlocked()
        if should_restore_snapshot:
            current["activeTask"] = task_snapshot
            current["draft"] = control.build_draft_from_task(task_snapshot)
            current["commander"] = None
            current["commanderReview"] = None
            current["workers"] = control._empty_worker_state_map(task_workers(task_snapshot))
            current["summary"] = None
            current["arbiter"] = None
            current["memoryVersion"] = int(current.get("memoryVersion") or 0) + 1
            current["usage"] = storage.default_usage_state()
            current["loop"] = storage.default_loop_state()
            runtime.write_state_unlocked(current)
            seed_completed_rounds = 0
            seed_results = []
            resume_from_round = 1
            if action == "resume":
                retry_source_job_id = job_id
                resume_source_job_id = None
            else:
                retry_source_job_id = job_id
        else:
            current["loop"] = storage.default_loop_state()
            runtime.write_state_unlocked(current)

    new_job = create_loop_job(
        runtime,
        task_snapshot,
        clamp_loop_rounds(job.get("rounds") or 1),
        clamp_loop_delay_ms(job.get("delayMs") or 0),
        "background",
        {
            "attempt": max(1, int(job.get("attempt") or 1)) + 1,
            "resumeOfJobId": resume_source_job_id,
            "retryOfJobId": retry_source_job_id,
            "resumeFromRound": resume_from_round,
            "results": seed_results,
            "completedRounds": seed_completed_rounds,
            "lastMessage": "Queued resumed background loop." if action == "resume" else "Queued retried background loop.",
        },
    )
    try:
        if queueing.redis_enabled(runtime.root):
            _sync_loop_queue(runtime.root, task_id)
            promoted = _promote_next_queued_loop_job(runtime, task_id, None)
            if promoted is None:
                raise RuntimeError("Redis queue did not promote the resumed loop job.")
        else:
            launch_loop_job_runner(new_job, runtime.root)
    except Exception as exc:  # noqa: BLE001
        with runtime.with_lock():
            current = runtime.read_state_unlocked()
            current["loop"] = storage.default_loop_state()
            current["loop"]["lastMessage"] = "Background launch failed."
            runtime.write_state_unlocked(current)
            runtime.write_job_unlocked(
                storage.default_job(
                    {
                        **new_job,
                        "status": "error",
                        "finishedAt": utc_now(),
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": "Background launch failed.",
                        "error": str(exc),
                    }
                )
            )
        queueing.release_loop_claim(runtime.root, task_id, str(new_job.get("jobId") or ""))
        _sync_loop_queue(runtime.root, task_id)
        raise RuntimeErrorWithCode(str(exc), 500) from exc

    runtime.append_step(
        "autoloop",
        "Queued a resumed background loop." if action == "resume" else "Queued a retried background loop.",
        {"taskId": task_id, "sourceJobId": job_id, "jobId": new_job["jobId"], "resumeFromRound": resume_from_round},
    )
    return {
        "message": "Interrupted loop resumed." if action == "resume" else "Loop queued for retry.",
        "jobId": new_job["jobId"],
        "resumeFromRound": resume_from_round,
    }
