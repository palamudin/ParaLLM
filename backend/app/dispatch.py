from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.engine import LoopRuntime, RuntimeErrorWithCode, task_workers

from . import control, faults, jobs, queueing, runtime_execution, storage


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _runtime(root: Optional[Path] = None) -> LoopRuntime:
    return LoopRuntime(Path(root).resolve() if root else Path(__file__).resolve().parents[2])


def commander_checkpoint_from_state(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    checkpoint = state.get("commander")
    return checkpoint if isinstance(checkpoint, dict) else None


def commander_review_checkpoint_from_state(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    checkpoint = state.get("commanderReview")
    return checkpoint if isinstance(checkpoint, dict) else None


def summary_round_from_state(state: Dict[str, Any]) -> int:
    summary = state.get("summary") if isinstance(state.get("summary"), dict) else {}
    return max(0, int(summary.get("round") or 0))


def commander_round_from_state(state: Dict[str, Any]) -> int:
    commander = commander_checkpoint_from_state(state)
    return max(0, int((commander or {}).get("round") or 0))


def commander_review_round_from_state(state: Dict[str, Any]) -> int:
    review = commander_review_checkpoint_from_state(state)
    return max(0, int((review or {}).get("round") or 0))


def latest_worker_round(worker_state: Dict[str, Any]) -> int:
    latest = 0
    for checkpoint in worker_state.values():
        if not isinstance(checkpoint, dict):
            continue
        latest = max(latest, int(checkpoint.get("step") or 0))
    return latest


def find_task_worker(task: Optional[Dict[str, Any]], worker_id: str) -> Optional[Dict[str, Any]]:
    if not isinstance(task, dict):
        return None
    for worker in task_workers(task):
        if str(worker.get("id") or "").upper() == worker_id.upper():
            return worker
    return None


def available_targets(task: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(task, dict):
        return ["commander", "commander_review", "summarizer", "answer_now"]
    targets = [str(worker["id"]) for worker in task_workers(task)]
    targets.insert(0, "commander")
    targets.extend(["commander_review", "summarizer", "answer_now"])
    seen: Dict[str, bool] = {}
    ordered: List[str] = []
    for target in targets:
        if target not in seen:
            seen[target] = True
            ordered.append(target)
    return ordered


def is_valid_target(target: str, task: Optional[Dict[str, Any]]) -> bool:
    return target in available_targets(task)


def missing_worker_checkpoints(task: Optional[Dict[str, Any]], worker_state: Dict[str, Any], round_number: int) -> List[str]:
    if not isinstance(task, dict):
        return []
    missing: List[str] = []
    for worker in task_workers(task, round_number):
        worker_id = str(worker.get("id") or "").strip()
        if not worker_id:
            continue
        checkpoint = worker_state.get(worker_id)
        if not isinstance(checkpoint, dict) or int(checkpoint.get("step") or 0) != round_number:
            missing.append(worker_id)
    return missing


def target_dispatch_preflight(target: str, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    worker_state = state.get("workers") if isinstance(state.get("workers"), dict) else {}
    commander_round = commander_round_from_state(state)
    commander_review_round = commander_review_round_from_state(state)
    summary_round = summary_round_from_state(state)

    if target == "commander":
        open_round = max(commander_round, commander_review_round, latest_worker_round(worker_state))
        if open_round > summary_round:
            return {
                "code": 409,
                "message": f"Commander already drafted round {open_round}. Finish the current worker/summarizer pass before drafting the next round.",
            }
        return None

    if len(target) == 1 and target.isalpha() and target.isupper():
        worker = find_task_worker(task, target)
        if worker is None:
            return {"code": 404, "message": f"Unknown worker target {target}."}
        activation_round = max(1, int(worker.get("activeFromRound") or 1))
        next_round = 1
        checkpoint = worker_state.get(target)
        if isinstance(checkpoint, dict):
            next_round = int(checkpoint.get("step") or 0) + 1
        if next_round < activation_round:
            next_round = activation_round
        if commander_round <= 0:
            return {"code": 409, "message": "Commander is not ready yet. Run commander first."}
        if commander_round != next_round:
            return {
                "code": 409,
                "message": f"Worker {target} expects commander round {next_round}, but the active commander draft is round {commander_round}.",
            }

    if target == "commander_review":
        if commander_round <= 0:
            return {"code": 409, "message": "Commander review is not ready yet. Run commander first."}
        if commander_review_round == commander_round:
            return {
                "code": 409,
                "message": f"Commander review already exists for commander round {commander_round}. Run summarizer or start the next round.",
            }
        missing = missing_worker_checkpoints(task, worker_state, commander_round)
        if missing:
            return {
                "code": 409,
                "message": f"Commander review is not ready yet. Run worker checkpoint(s) first: {', '.join(missing)}.",
                "missingWorkers": missing,
            }

    if target == "summarizer":
        if commander_round <= 0:
            return {"code": 409, "message": "Summarizer is not ready yet. Run commander first."}
        if commander_review_round != commander_round:
            return {"code": 409, "message": "Commander review is not ready yet. Run commander review first."}
        missing = missing_worker_checkpoints(task, worker_state, commander_round)
        if missing:
            return {
                "code": 409,
                "message": f"Summarizer is not ready yet. Run worker checkpoint(s) first: {', '.join(missing)}.",
                "missingWorkers": missing,
            }
        if summary_round >= commander_round:
            return {
                "code": 409,
                "message": f"Summarizer already exists for round {summary_round}. Start the next round instead.",
            }

    return None


def active_target_jobs(paths: storage.Paths, task_id: Optional[str] = None, include_partial: bool = True) -> List[Dict[str, Any]]:
    jobs_out: List[Dict[str, Any]] = []
    for job in storage.read_jobs(paths):
        if str(job.get("jobType") or "loop") != "target":
            continue
        if str(job.get("status") or "") not in {"queued", "running"}:
            continue
        if task_id is not None and str(job.get("taskId") or "") != task_id:
            continue
        if not include_partial and bool(job.get("partialSummary")):
            continue
        jobs_out.append(storage.default_job(job))
    jobs_out.sort(key=lambda job: (0 if str(job.get("status") or "") == "running" else 1, storage.parse_ts(job.get("queuedAt")) or 0))
    return jobs_out


def active_target_job_count(paths: storage.Paths, task_id: Optional[str] = None, include_partial: bool = True) -> int:
    return len(active_target_jobs(paths, task_id, include_partial))


def dispatch_target_label(job: Dict[str, Any]) -> str:
    target = str(job.get("target") or "target").lower()
    if target == "answer_now":
        return "Answer now"
    if target == "commander":
        return "Commander"
    if target == "commander_review":
        return "Commander review"
    if target == "summarizer":
        return "Summarizer (partial)" if bool(job.get("partialSummary")) else "Summarizer"
    return f"Worker {target.upper()}"


def classify_dispatch_failure(message: str) -> Dict[str, str]:
    normalized = str(message or "").strip()
    lowered = normalized.lower()
    if "http 500" in lowered or "server_error" in lowered or "provider error" in lowered:
        return {
            "failureClass": "provider_error",
            "lastMessage": "Dispatch failed because the model provider returned a server-side error.",
            "operatorNote": normalized or "The provider returned a server-side error.",
        }
    if "max_output_tokens" in lowered or "output remained incomplete after attempts" in lowered or "model response incomplete" in lowered:
        return {
            "failureClass": "output_exhausted",
            "lastMessage": "Dispatch failed after output-token recovery was exhausted.",
            "operatorNote": normalized or "The model stayed incomplete after output-token escalation.",
        }
    if "finished with status" in lowered or "dependency failed" in lowered:
        return {
            "failureClass": "dependency_failure",
            "lastMessage": "Dispatch stopped because an upstream dependency failed.",
            "operatorNote": normalized or "An upstream dependency failed before this dispatch could run.",
        }
    if lowered.startswith("budget limit reached:"):
        return {
            "failureClass": "budget_exhausted",
            "lastMessage": "Dispatch stopped because the task budget was exhausted.",
            "operatorNote": normalized,
        }
    return {
        "failureClass": "runtime_error",
        "lastMessage": "Dispatch failed.",
        "operatorNote": normalized or "The runtime reported a dispatch failure.",
    }


def failed_target_dependency_labels(paths: storage.Paths, task_id: str) -> List[str]:
    labels: List[str] = []
    for job in storage.read_jobs(paths):
        current = storage.default_job(job)
        if str(current.get("jobType") or "loop") != "target":
            continue
        if str(current.get("taskId") or "") != task_id:
            continue
        if str(current.get("status") or "") not in {"error", "interrupted", "budget_exhausted"}:
            continue
        label = dispatch_target_label(current)
        if label not in labels:
            labels.append(label)
    return labels


def dispatch_dependency_ids(job: Dict[str, Any]) -> List[str]:
    return [str(value).strip() for value in (job.get("dependencyJobIds") or []) if str(value).strip()]


def read_dispatch_job_unlocked(runtime: LoopRuntime, job_id: str) -> Optional[Dict[str, Any]]:
    job = runtime.read_job_unlocked(job_id)
    return storage.default_job(job) if isinstance(job, dict) else None


def dispatch_dependency_failure_message_unlocked(runtime: LoopRuntime, job: Dict[str, Any]) -> Optional[str]:
    for dependency_id in dispatch_dependency_ids(job):
        dependency = read_dispatch_job_unlocked(runtime, dependency_id)
        if dependency is None:
            return f"Dependency {dependency_id} is missing."
        status = str(dependency.get("status") or "queued")
        if status in {"completed", "cancelled", "error", "budget_exhausted", "interrupted"} and status != "completed":
            return f"{dispatch_target_label(dependency)} finished with status {status}."
    return None


def dispatch_dependencies_completed_unlocked(runtime: LoopRuntime, job: Dict[str, Any]) -> bool:
    for dependency_id in dispatch_dependency_ids(job):
        dependency = read_dispatch_job_unlocked(runtime, dependency_id)
        if dependency is None or str(dependency.get("status") or "queued") != "completed":
            return False
    return True


def dispatch_job_is_launchable_unlocked(runtime: LoopRuntime, job: Dict[str, Any]) -> bool:
    if str(job.get("jobType") or "loop") != "target":
        return False
    if str(job.get("status") or "queued") != "queued":
        return False
    if bool(job.get("cancelRequested")):
        return False
    return dispatch_dependencies_completed_unlocked(runtime, job)


def interrupt_unrunnable_dispatch_jobs_unlocked(runtime: LoopRuntime, task_id: Optional[str] = None, batch_id: Optional[str] = None) -> int:
    changed = 0
    while True:
        pass_changed = 0
        for job in storage.read_jobs(storage.project_paths(runtime.root)):
            job = storage.default_job(job)
            if str(job.get("jobType") or "loop") != "target":
                continue
            if str(job.get("status") or "") != "queued":
                continue
            if task_id is not None and str(job.get("taskId") or "") != task_id:
                continue
            if batch_id is not None and str(job.get("batchId") or "") != batch_id:
                continue
            failure = dispatch_dependency_failure_message_unlocked(runtime, job)
            if failure is None:
                continue
            runtime.write_job_unlocked(
                storage.default_job(
                    {
                        **job,
                        "status": "interrupted",
                        "finishedAt": utc_now(),
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": "Dispatch stopped because a dependency failed.",
                        "error": failure,
                        "metadata": {
                            **(job.get("metadata") if isinstance(job.get("metadata"), dict) else {}),
                            "failureClass": "dependency_failure",
                            "operatorNote": failure,
                        },
                    }
                )
            )
            pass_changed += 1
        changed += pass_changed
        if pass_changed == 0:
            break
    return changed


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


def launch_dispatch_job_runner(job: Dict[str, Any], root: Optional[Path] = None) -> None:
    repo_root = Path(root).resolve() if root else Path(__file__).resolve().parents[2]
    auth_path = control.auth_file_path(repo_root)
    command = [
        sys.executable,
        "-m",
        "backend.workers.dispatch_job",
        f"--root={repo_root}",
        f"--job-id={job['jobId']}",
        f"--auth-path={auth_path}",
    ]
    subprocess.Popen(command, **_subprocess_kwargs())  # noqa: S603,S607


def create_target_job(runtime: LoopRuntime, task: Dict[str, Any], target: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    overrides = overrides or {}
    job_id = "dispatch-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(8).hex()[:6]
    dependency_ids = [str(value).strip() for value in (overrides.get("dependencyJobIds") or []) if str(value).strip()]
    job = storage.default_job(
        {
            "jobId": job_id,
            "taskId": task["taskId"],
            "jobType": "target",
            "mode": "background",
            "status": "queued",
            "target": target,
            "batchId": overrides.get("batchId"),
            "queuePosition": 0,
            "attempt": max(1, int(overrides.get("attempt") or 1)),
            "rounds": 0,
            "delayMs": 0,
            "workerCount": max(0, int(overrides.get("workerCount") or len(task_workers(task)))),
            "dependencyJobIds": dependency_ids,
            "partialSummary": bool(overrides.get("partialSummary") or False),
            "timeoutSeconds": max(30, int(overrides.get("timeoutSeconds") or 1800)),
            "queuedAt": utc_now(),
            "lastMessage": str(overrides.get("lastMessage") or ("Waiting for dependencies." if dependency_ids else "Queued target dispatch.")),
            "metadata": overrides.get("metadata") if isinstance(overrides.get("metadata"), dict) else {},
        }
    )
    with runtime.with_lock():
        runtime.write_job_unlocked(job)
    runtime.append_step(
        "dispatch",
        "Queued background target dispatch.",
        {
            "taskId": task["taskId"],
            "jobId": job_id,
            "target": target,
            "partialSummary": bool(job.get("partialSummary")),
            "dependencyJobIds": dependency_ids,
            "batchId": job.get("batchId"),
        },
    )
    return job


def create_round_dispatch_jobs(runtime: LoopRuntime, task: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    overrides = overrides or {}
    round_number = max(1, int(overrides.get("roundNumber") or 1))
    round_workers = task_workers(task, round_number)
    batch_id = "batch-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(8).hex()[:6]
    commander_job = create_target_job(
        runtime,
        task,
        "commander",
        {
            "batchId": batch_id,
            "timeoutSeconds": overrides.get("timeoutSeconds", 1800),
            "workerCount": len(round_workers),
            "lastMessage": "Queued commander dispatch.",
            "metadata": {"trigger": "round"},
        },
    )
    worker_jobs: List[Dict[str, Any]] = []
    for worker in round_workers:
        worker_jobs.append(
            create_target_job(
                runtime,
                task,
                str(worker["id"]),
                {
                    "batchId": batch_id,
                    "dependencyJobIds": [commander_job["jobId"]],
                    "timeoutSeconds": overrides.get("timeoutSeconds", 1800),
                    "workerCount": len(round_workers),
                    "lastMessage": "Waiting for commander.",
                    "metadata": {"trigger": "round"},
                },
            )
        )
    commander_review_job = create_target_job(
        runtime,
        task,
        "commander_review",
        {
            "batchId": batch_id,
            "dependencyJobIds": [str(job["jobId"]) for job in worker_jobs],
            "timeoutSeconds": overrides.get("timeoutSeconds", 1800),
            "workerCount": len(round_workers),
            "lastMessage": "Waiting for workers." if worker_jobs else "Waiting for commander.",
            "metadata": {"trigger": "round"},
        },
    )
    summarizer_job = create_target_job(
        runtime,
        task,
        "summarizer",
        {
            "batchId": batch_id,
            "dependencyJobIds": [commander_review_job["jobId"]],
            "timeoutSeconds": overrides.get("timeoutSeconds", 1800),
            "workerCount": len(round_workers),
            "lastMessage": "Waiting for commander review.",
            "metadata": {"trigger": "round"},
        },
    )
    return {
        "batchId": batch_id,
        "commander": commander_job,
        "workers": worker_jobs,
        "commanderReview": commander_review_job,
        "summarizer": summarizer_job,
    }


def promote_ready_dispatch_jobs(runtime: LoopRuntime, task_id: Optional[str] = None, batch_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with runtime.with_lock():
        interrupt_unrunnable_dispatch_jobs_unlocked(runtime, task_id, batch_id)
        launchable: List[Dict[str, Any]] = []
        for job in storage.read_jobs(storage.project_paths(runtime.root)):
            job = storage.default_job(job)
            if str(job.get("jobType") or "loop") != "target":
                continue
            if task_id is not None and str(job.get("taskId") or "") != task_id:
                continue
            if batch_id is not None and str(job.get("batchId") or "") != batch_id:
                continue
            if not dispatch_job_is_launchable_unlocked(runtime, job):
                continue
            launchable.append(
                runtime.write_job_unlocked(
                    storage.default_job(
                        {
                            **job,
                            "status": "running",
                            "startedAt": job.get("startedAt") or utc_now(),
                            "lastHeartbeatAt": utc_now(),
                            "lastMessage": "Launching target dispatch.",
                        }
                    )
                )
            )
    jobs_to_launch = list(launchable)
    if queueing.redis_enabled(runtime.root):
        queueing.enqueue_dispatch_launches(runtime.root, [str(job.get("jobId") or "") for job in launchable])
        jobs_to_launch = []
        for job_id in queueing.drain_dispatch_launches(runtime.root):
            current = runtime.read_job_unlocked(job_id)
            if not isinstance(current, dict):
                continue
            current_job = storage.default_job(current)
            if str(current_job.get("jobType") or "loop") != "target":
                continue
            if str(current_job.get("status") or "") != "running":
                continue
            jobs_to_launch.append(current_job)

    launched: List[Dict[str, Any]] = []
    for job in jobs_to_launch:
        try:
            launch_dispatch_job_runner(job, runtime.root)
            runtime.append_step(
                "dispatch",
                "Background target dispatch launched.",
                {
                    "taskId": job.get("taskId"),
                    "jobId": job.get("jobId"),
                    "target": job.get("target"),
                    "partialSummary": bool(job.get("partialSummary")),
                    "batchId": job.get("batchId"),
                },
            )
            launched.append(job)
        except Exception as exc:  # noqa: BLE001
            runtime.mutate_job(
                str(job.get("jobId") or ""),
                lambda existing: storage.default_job(
                    {
                        **(existing or {}),
                        "status": "error",
                        "finishedAt": utc_now(),
                        "lastHeartbeatAt": utc_now(),
                        "lastMessage": "Dispatch launch failed.",
                        "error": str(exc),
                    }
                ),
            )
            runtime.append_step(
                "error",
                "Failed to launch a background target dispatch.",
                {"taskId": job.get("taskId"), "jobId": job.get("jobId"), "target": job.get("target"), "error": str(exc)},
            )
    return launched


def execute_target_job_process(job_id: str, root: Optional[Path] = None, auth_path: Optional[Path] = None) -> Dict[str, Any]:
    runtime = LoopRuntime(Path(root).resolve() if root else Path(__file__).resolve().parents[2], auth_path=auth_path)
    runtime.ensure_data_paths()
    with runtime.with_lock():
        job = runtime.read_job_unlocked(job_id)
    if not isinstance(job, dict):
        raise RuntimeErrorWithCode(f"Job not found: {job_id}", 404)
    if str(job.get("jobType") or "loop") != "target":
        raise RuntimeErrorWithCode(f"Job is not a target dispatch: {job_id}", 409)
    if str(job.get("status") or "queued") == "cancelled":
        runtime.append_step(
            "dispatch",
            "Background dispatch runner exited because the job was already cancelled.",
            {"taskId": job.get("taskId"), "jobId": job_id, "target": job.get("target")},
        )
        return {"message": "Target dispatch was already cancelled.", "target": job.get("target")}

    target = str(job.get("target") or "").strip()
    task_id = str(job.get("taskId") or "").strip()
    timeout_seconds = max(30, int(job.get("timeoutSeconds") or 1800))
    options: Dict[str, Any] = {"partialSummary": bool(job.get("partialSummary"))}
    dispatch_label = dispatch_target_label({"target": target, "partialSummary": options["partialSummary"]})
    options["dispatchJobId"] = job_id
    options["dispatchHeartbeatMessage"] = f"Waiting on {dispatch_label} response..."
    if not job_id or not target or not task_id:
        raise RuntimeErrorWithCode("Target job metadata is incomplete.", 500)

    runtime.mutate_job(
        job_id,
        lambda existing: storage.default_job(
            {
                **(existing or {}),
                "status": "running",
                "startedAt": utc_now(),
                "finishedAt": None,
                "lastHeartbeatAt": utc_now(),
                "lastMessage": f"Running {dispatch_label}.",
                "error": None,
            }
        ),
    )
    runtime.append_step("dispatch", "Background target runner claimed job.", {"taskId": task_id, "jobId": job_id, "target": target, "options": options})

    try:
        task = storage.read_task_snapshot(task_id, storage.project_paths(runtime.root))
        if not isinstance(task, dict):
            raise RuntimeErrorWithCode("Task snapshot is missing.", 404)
        faults.maybe_raise_fault(
            "dispatch.execute.before_runtime",
            f"dispatch.execute.before_runtime.{target.lower()}",
        )
        result = runtime_execution.run_target(runtime, target, task_id, options)
        faults.maybe_raise_fault(
            "dispatch.execute.after_runtime",
            f"dispatch.execute.after_runtime.{target.lower()}",
        )
        usage_snapshot = storage.normalize_usage_state((runtime.read_state().get("usage") or {}))
        updated_job = runtime.mutate_job(
            job_id,
            lambda existing: storage.default_job(
                {
                    **(existing or {}),
                    "status": "completed",
                    "finishedAt": utc_now(),
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": f"Completed {dispatch_target_label(existing or {})}.",
                    "usage": usage_snapshot,
                    "results": [result],
                    "error": None,
                }
            ),
        )
        runtime.append_step(
            "dispatch",
            "Background target dispatch completed.",
            {"taskId": task_id, "jobId": job_id, "target": target, "outputPreview": result.get("output", ""), "exitCode": result.get("exitCode", 0)},
        )
        promote_ready_dispatch_jobs(runtime, task_id, str((updated_job or {}).get("batchId") or ""))
        return result
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        final_status = "budget_exhausted" if message.startswith("Budget limit reached:") else "error"
        failure = classify_dispatch_failure(message)
        updated_job = runtime.mutate_job(
            job_id,
            lambda existing: storage.default_job(
                {
                    **(existing or {}),
                    "status": final_status,
                    "finishedAt": utc_now(),
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": failure["lastMessage"],
                    "error": message,
                    "metadata": {
                        **((existing or {}).get("metadata") if isinstance((existing or {}).get("metadata"), dict) else {}),
                        "failureClass": failure["failureClass"],
                        "operatorNote": failure["operatorNote"],
                    },
                }
            ),
        )
        runtime.append_step(
            "budget" if final_status == "budget_exhausted" else "error",
            "Background target dispatch failed.",
            {"taskId": task_id, "jobId": job_id, "target": target, "error": message},
        )
        with runtime.with_lock():
            interrupt_unrunnable_dispatch_jobs_unlocked(runtime, task_id, str((updated_job or {}).get("batchId") or ""))
        promote_ready_dispatch_jobs(runtime, task_id, str((updated_job or {}).get("batchId") or ""))
        raise


def start_target_job(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    paths = storage.project_paths(runtime.root)
    state = storage.read_state_payload(paths)
    task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    target = str(payload.get("target") or "").strip()

    if not isinstance(task, dict):
        raise RuntimeErrorWithCode("No active task. Start one first.", 400)
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("The autonomous loop is running. Cancel it before background target dispatch.", 409)
    if not is_valid_target(target, task):
        raise RuntimeErrorWithCode("Invalid target.", 400)

    task_id = str(task.get("taskId") or "")
    dispatch_active = active_target_job_count(paths, task_id, include_partial=False)
    if target != "answer_now" and dispatch_active > 0:
        raise RuntimeErrorWithCode("Another background target dispatch is already active. Wait for it to finish or use Answer Now from current checkpoints.", 409)

    if target != "answer_now":
        preflight = target_dispatch_preflight(target, state)
        if preflight is not None:
            runtime.append_step(
                "dispatch",
                "Background target blocked by preflight check.",
                {"target": target, "message": preflight["message"], "missingWorkers": preflight.get("missingWorkers", [])},
            )
            raise RuntimeErrorWithCode(str(preflight["message"]), int(preflight.get("code", 409)))

    if target == "answer_now" and commander_round_from_state(state) <= 0:
        raise RuntimeErrorWithCode("Answer Now needs a commander draft first.", 409)

    dependency_failures = failed_target_dependency_labels(paths, task_id) if target == "answer_now" else []
    last_message = (
        "Queued partial summary from current checkpoints despite failed lanes: " + ", ".join(dependency_failures) + "."
        if dependency_failures
        else ("Queued partial summary from current checkpoints." if target == "answer_now" else "Queued target dispatch.")
    )

    job = create_target_job(
        runtime,
        task,
        target,
        {
            "partialSummary": target == "answer_now",
            "timeoutSeconds": 1800,
            "lastMessage": last_message,
            "metadata": {
                "trigger": "answer-now" if target == "answer_now" else "manual",
                "dependencyFailures": dependency_failures,
                "dependencyFailureCount": len(dependency_failures),
            },
        },
    )
    try:
        promote_ready_dispatch_jobs(runtime, task_id, str(job.get("batchId") or ""))
        return {
            "message": "Partial answer queued." if target == "answer_now" else f"Background dispatch queued for {target}.",
            "jobId": job["jobId"],
            "target": target,
            "partialSummary": target == "answer_now",
        }
    except Exception as exc:  # noqa: BLE001
        runtime.mutate_job(
            str(job["jobId"]),
            lambda existing: storage.default_job(
                {
                    **(existing or {}),
                    "status": "error",
                    "finishedAt": utc_now(),
                    "lastHeartbeatAt": utc_now(),
                    "lastMessage": "Background launch failed.",
                    "error": str(exc),
                }
            ),
        )
        raise RuntimeErrorWithCode(str(exc), 500) from exc


def run_round(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    paths = storage.project_paths(runtime.root)
    state = storage.read_state_payload(paths)
    task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    if not isinstance(task, dict):
        raise RuntimeErrorWithCode("No active task. Start one first.", 400)
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("The autonomous loop is already active.", 409)
    if active_target_job_count(paths, str(task.get("taskId") or ""), include_partial=False) > 0:
        raise RuntimeErrorWithCode("A background target dispatch is already running. Wait for it to finish or use Answer Now from current checkpoints.", 409)

    batch: Optional[Dict[str, Any]] = None
    try:
        next_round = max(1, summary_round_from_state(state) + 1)
        batch = create_round_dispatch_jobs(runtime, task, {"timeoutSeconds": 1800, "roundNumber": next_round})
        promote_ready_dispatch_jobs(runtime, str(task.get("taskId") or ""), batch["batchId"])
        return {
            "message": "Round dispatch queued.",
            "batchId": batch["batchId"],
            "jobIds": [batch["commander"]["jobId"], *[str(job["jobId"]) for job in batch["workers"]], batch["commanderReview"]["jobId"], batch["summarizer"]["jobId"]],
        }
    except Exception as exc:  # noqa: BLE001
        if isinstance(batch, dict):
            for job in [batch["commander"], *batch["workers"], batch["commanderReview"], batch["summarizer"]]:
                runtime.mutate_job(
                    str(job.get("jobId") or ""),
                    lambda existing, message=str(exc): storage.default_job(
                        {
                            **(existing or {}),
                            "status": "error",
                            "finishedAt": utc_now(),
                            "lastHeartbeatAt": utc_now(),
                            "lastMessage": "Round dispatch launch failed.",
                            "error": message,
                        }
                    ),
                )
        runtime.append_step("error", "Round dispatch failed to queue.", {"error": str(exc)})
        raise RuntimeErrorWithCode(str(exc), 500) from exc


def run_target_sync(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    paths = storage.project_paths(runtime.root)
    state = storage.read_state_payload(paths)
    task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    target = str(payload.get("target") or "").strip()
    if not isinstance(task, dict):
        raise RuntimeErrorWithCode("No active task. Start one first.", 400)
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("The autonomous loop is running. Cancel it before manual dispatch.", 409)
    if active_target_job_count(paths, str(task.get("taskId") or ""), include_partial=True) > 0:
        raise RuntimeErrorWithCode("A background target dispatch is already running. Wait for it to finish or use the queued answer path.", 409)
    if not is_valid_target(target, task):
        raise RuntimeErrorWithCode("Invalid target.", 400)
    preflight = target_dispatch_preflight(target, state)
    if preflight is not None:
        runtime.append_step(
            "dispatch",
            "Manual runtime target blocked by preflight check.",
            {"target": target, "message": preflight["message"], "missingWorkers": preflight.get("missingWorkers", [])},
        )
        raise RuntimeErrorWithCode(str(preflight["message"]), int(preflight.get("code", 409)))
    try:
        runtime.append_step("dispatch", "Dispatching runtime target.", {"target": target})
        result = runtime_execution.run_target(runtime, target, str(task.get("taskId") or ""), {})
        runtime.append_step(
            "dispatch",
            "Runtime target completed.",
            {"target": target, "outputPreview": result.get("output"), "exitCode": result.get("exitCode"), "backend": result.get("backend", "python")},
        )
        return {"message": f"Executed {target}", "target": target, "output": result.get("output"), "backend": result.get("backend", "python")}
    except RuntimeErrorWithCode:
        raise
    except Exception as exc:  # noqa: BLE001
        runtime.append_step("error", "Runtime target failed.", {"target": target, "error": str(exc)})
        message = str(exc)
        status_code = 409 if message.startswith("Budget limit reached:") else 500
        raise RuntimeErrorWithCode(message, status_code) from exc
