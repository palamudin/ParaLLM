from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from qa_check import (
    DEFAULT_BASE_URL,
    DEFAULT_RUNTIME_URL,
    PreservedState,
    QAError,
    api_url,
    project_root,
    qa_print,
    request_json,
    restart_runtime,
)
from qa_live_check import ensure_auth_available


def wait_for_idle_workspace(base_url: str, timeout_seconds: float = 180.0) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_state: Dict[str, Any] | None = None
    while time.time() < deadline:
        last_state = request_json(api_url(base_url, "get_state.php"), timeout=30)
        loop = last_state.get("loop") if isinstance(last_state.get("loop"), dict) else {}
        dispatch = last_state.get("dispatch") if isinstance(last_state.get("dispatch"), dict) else {}
        loop_status = str(loop.get("status") or "")
        dispatch_status = str((dispatch or {}).get("status") or "")
        if loop_status in {"idle", "completed"} and not dispatch:
            return last_state
        if loop_status in {"idle", "completed"} and dispatch_status == "idle":
            return last_state
        time.sleep(1.0)
    raise QAError(f"Workspace did not become idle within {timeout_seconds:.1f}s: {json.dumps(last_state or {}, indent=2)}")


def build_workers(model: str) -> List[Dict[str, Any]]:
    return [
        {
            "id": "A",
            "type": "proponent",
            "label": "Proponent",
            "role": "utility",
            "focus": "best path to ship value quickly without losing the plot",
            "temperature": "balanced",
            "model": model,
            "harness": {
                "concision": "tight",
                "instruction": "Drive toward a clear decision and a practical rollout path.",
            },
        },
        {
            "id": "B",
            "type": "sceptic",
            "label": "Sceptic",
            "role": "adversarial",
            "focus": "hidden failure, false confidence, and weak assumptions",
            "temperature": "cool",
            "model": model,
            "harness": {
                "concision": "tight",
                "instruction": "Challenge bad assumptions, but only force reversal when it is truly earned.",
            },
        },
    ]


def live_objective() -> str:
    return (
        "A team wants to let outside users submit public GitHub repositories for automated AI review and suggested patches. "
        "The product head wants a decisive recommendation and a 30-day rollout plan. The system can read local files, read GitHub, "
        "and spawn adversarial lanes if uncertainty of a specific type remains. Make the best call, but only change course when the "
        "pressure truly earns it. The likely blind spot is hostile use and abuse through public repos, secrets, prompts, and generated patches."
    )


def wait_for_task_completion(base_url: str, task_id: str, timeout_seconds: float = 1800.0) -> tuple[Dict[str, Any], Dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    last_state: Dict[str, Any] | None = None
    last_history: Dict[str, Any] | None = None
    while time.time() < deadline:
        time.sleep(4.0)
        last_state = request_json(api_url(base_url, "get_state.php"), timeout=30)
        last_history = request_json(api_url(base_url, "get_history.php"), timeout=30)
        active_task = last_state.get("activeTask") if isinstance(last_state.get("activeTask"), dict) else {}
        if str(active_task.get("taskId") or "") != task_id:
            continue
        loop = last_state.get("loop") if isinstance(last_state.get("loop"), dict) else {}
        dispatch = last_state.get("dispatch") if isinstance(last_state.get("dispatch"), dict) else {}
        loop_status = str(loop.get("status") or "")
        dispatch_status = str((dispatch or {}).get("status") or "")
        if loop_status in {"error", "budget_exhausted", "interrupted"}:
            raise QAError(f"Loop ended in {loop_status}: {loop.get('lastMessage')}")
        if loop_status in {"idle", "completed"} and (not dispatch or dispatch_status == "idle"):
            return last_state, last_history
    raise QAError(f"Timed out waiting for live round-alignment run to finish: {json.dumps(last_state or {}, indent=2)}")


def run_single_alignment_case(root: Path, base_url: str, model: str, reasoning_effort: str) -> Dict[str, Any]:
    wait_for_idle_workspace(base_url)
    workers = build_workers(model)
    budget_targets = {
        "commander": {"maxTotalTokens": 180000, "maxCostUsd": 15, "maxOutputTokens": 4200},
        "worker": {"maxTotalTokens": 180000, "maxCostUsd": 15, "maxOutputTokens": 3200},
        "summarizer": {"maxTotalTokens": 220000, "maxCostUsd": 20, "maxOutputTokens": 6200},
    }
    task_id = ""
    with PreservedState(root) as preserved:
        try:
            start = request_json(
                api_url(base_url, "start_task.php"),
                method="POST",
                form_data={
                    "objective": live_objective(),
                    "constraints": json.dumps(
                        [
                            "No web browsing.",
                            "Be decisive.",
                            "Prefer a concrete 30-day plan over generic caution.",
                            "All lanes should work from the same user objective.",
                            "Only redirect or reverse if objections materially alter correctness or viability.",
                        ]
                    ),
                    "sessionContext": "",
                    "workers": json.dumps(workers),
                    "summarizerHarness": json.dumps(
                        {
                            "concision": "balanced",
                            "instruction": "Package the answer in one lead voice after commander review. Do not narrate the debate.",
                        }
                    ),
                    "executionMode": "live",
                    "model": model,
                    "summarizerModel": model,
                    "reasoningEffort": reasoning_effort,
                    "maxTotalTokens": "0",
                    "maxCostUsd": "0",
                    "maxOutputTokens": "0",
                    "budgetTargets": json.dumps(budget_targets),
                    "researchEnabled": "0",
                    "researchExternalWebAccess": "0",
                    "vettingEnabled": "1",
                    "dynamicSpinupEnabled": "1",
                    "loopRounds": "2",
                    "loopDelayMs": "0",
                },
                timeout=60,
            )
            task_id = str(start.get("taskId") or "").strip()
            if not task_id:
                raise QAError("Task creation did not return a taskId.")

            start_loop = request_json(
                api_url(base_url, "start_loop.php"),
                method="POST",
                form_data={"rounds": "2", "delayMs": "0"},
                timeout=60,
            )
            if not str(start_loop.get("jobId") or "").strip():
                raise QAError("Live alignment loop did not return a jobId.")

            final_state, final_history = wait_for_task_completion(base_url, task_id)
            active_task = final_state.get("activeTask") if isinstance(final_state.get("activeTask"), dict) else {}
            loop = final_state.get("loop") if isinstance(final_state.get("loop"), dict) else {}
            commander = final_state.get("commander") if isinstance(final_state.get("commander"), dict) else {}
            commander_review = final_state.get("commanderReview") if isinstance(final_state.get("commanderReview"), dict) else {}
            summary = final_state.get("summary") if isinstance(final_state.get("summary"), dict) else {}
            usage = final_state.get("usage") if isinstance(final_state.get("usage"), dict) else {}
            workers_final = active_task.get("workers") if isinstance(active_task.get("workers"), list) else []
            spawned_workers = [worker for worker in workers_final if isinstance(worker, dict) and str(worker.get("id") or "") not in {"A", "B"}]

            if str(loop.get("status") or "") not in {"idle", "completed"}:
                raise QAError(f"Expected successful loop completion, found {loop.get('status')}.")
            if int(commander.get("round", 0) or 0) != 2:
                raise QAError(f"Expected commander round 2, found {commander.get('round')}.")
            if int(commander_review.get("round", 0) or 0) != 2:
                raise QAError(f"Expected commander review round 2, found {commander_review.get('round')}.")
            if int(summary.get("round", 0) or 0) != 2:
                raise QAError(f"Expected summary round 2, found {summary.get('round')}.")
            if not str(((summary.get("frontAnswer") or {}).get("answer")) or "").strip():
                raise QAError("Final front answer was empty.")
            if not spawned_workers:
                raise QAError("Expected commander review to spawn at least one next-round worker.")

            spawned = spawned_workers[0]
            if int(spawned.get("activeFromRound", 0) or 0) != 2:
                raise QAError(f"Expected spawned worker to activate from round 2, found {spawned.get('activeFromRound')}.")

            worker_state = final_state.get("workers") if isinstance(final_state.get("workers"), dict) else {}
            spawned_checkpoint = worker_state.get(str(spawned.get("id") or ""))
            if not isinstance(spawned_checkpoint, dict) or int(spawned_checkpoint.get("step", 0) or 0) != 2:
                raise QAError("Spawned worker did not complete round 2 as expected.")

            job_targets = [
                {
                    "target": job.get("target"),
                    "status": job.get("status"),
                    "attempt": job.get("attempt"),
                }
                for job in final_history.get("jobs", [])
                if isinstance(job, dict) and str(job.get("taskId") or "") == task_id
            ]
            artifact_kinds = [
                artifact.get("kind")
                for artifact in final_history.get("artifacts", [])
                if isinstance(artifact, dict) and str(artifact.get("taskId") or "") == task_id
            ]
            if "commander_review_output" not in artifact_kinds:
                raise QAError("Expected commander_review_output artifact in successful live run.")
            if "summary_output" not in artifact_kinds:
                raise QAError("Expected summary_output artifact in successful live run.")

            return {
                "taskId": task_id,
                "spawnedWorker": {
                    "id": spawned.get("id"),
                    "type": spawned.get("type"),
                    "activeFromRound": spawned.get("activeFromRound"),
                    "temperature": spawned.get("temperature"),
                    "instruction": ((spawned.get("harness") or {}).get("instruction")),
                },
                "commanderReview": {
                    "courseDecision": ((commander_review.get("controlAudit") or {}).get("courseDecision")),
                    "dynamicLaneDecision": commander_review.get("dynamicLaneDecision"),
                },
                "summaryAnswer": ((summary.get("frontAnswer") or {}).get("answer")),
                "totalTokens": int(usage.get("totalTokens", 0) or 0),
                "estimatedCostUsd": float(usage.get("estimatedCostUsd", 0.0) or 0.0),
                "jobTargets": job_targets,
                "artifactKinds": artifact_kinds,
            }
        finally:
            if task_id:
                preserved.cleanup_task_artifacts(task_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repeated live 2-round alignment checks for commander-review dynamic spin-up.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base browser URL for the local app.")
    parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL, help="Resident Python runtime URL.")
    parser.add_argument("--model", default="gpt-5-mini", help="Model to use for all lanes in the live check.")
    parser.add_argument("--reasoning-effort", default="medium", help="Reasoning effort for the live check.")
    parser.add_argument("--repeats", type=int, default=4, help="Number of successful live runs required.")
    parser.add_argument("--no-restart-runtime", action="store_true", help="Do not restart the resident runtime before the run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()
    qa_print(f"Project root: {root}")
    qa_print(f"Model: {args.model}")
    qa_print(f"Repeats: {args.repeats}")

    try:
        ensure_auth_available(args.base_url)
        if not args.no_restart_runtime:
            restart_runtime(args.runtime_url)
        wait_for_idle_workspace(args.base_url)
        results = []
        for index in range(max(1, int(args.repeats or 1))):
            qa_print(f"Starting live alignment run {index + 1}/{args.repeats}")
            result = run_single_alignment_case(root, args.base_url, args.model, args.reasoning_effort)
            results.append(result)
            qa_print(
                "Completed run "
                + str(index + 1)
                + f": task={result['taskId']} spawned={result['spawnedWorker']['id']} tokens={result['totalTokens']} cost=${result['estimatedCostUsd']:.6f}"
            )
        print(json.dumps({"status": "ok", "runs": results}, indent=2))
        return 0
    except QAError as error:
        qa_print(f"FAIL: {error}")
        return 1
    except Exception as error:  # pragma: no cover
        qa_print(f"FAIL: unexpected error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
