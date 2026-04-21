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
    find_node_binary,
    project_root,
    qa_print,
    request_json,
    restart_runtime,
    run_http_checks,
    run_js_checks,
    run_python_checks,
)
from qa_live_check import ensure_auth_available


def load_readme_excerpt(root: Path, max_chars: int = 6000) -> str:
    readme = root / "README.md"
    if not readme.exists():
        raise QAError("README.md is required for the dispatch smoke prompt.")
    text = readme.read_text(encoding="utf-8")
    excerpt = text[:max_chars].strip()
    if not excerpt:
        raise QAError("README.md excerpt was empty.")
    return excerpt


def build_workers(model: str) -> List[Dict[str, Any]]:
    return [
        {
            "id": "A",
            "type": "proponent",
            "label": "Proponent",
            "role": "utility",
            "focus": "strongest constructive architecture path and leverage",
            "temperature": "balanced",
            "model": model,
            "harness": {
                "concision": "tight",
                "instruction": "Argue for the strongest practical path forward without getting dreamy.",
            },
        },
        {
            "id": "B",
            "type": "sceptic",
            "label": "Sceptic",
            "role": "adversarial",
            "focus": "failure modes, overfitting, false confidence, and hidden complexity",
            "temperature": "cool",
            "model": model,
            "harness": {
                "concision": "tight",
                "instruction": "Challenge weak assumptions and force course change only when truly earned.",
            },
        },
        {
            "id": "C",
            "type": "economist",
            "label": "Economist",
            "role": "adversarial",
            "focus": "burn rate, operating cost, token economics, and ROI",
            "temperature": "cool",
            "model": model,
            "harness": {
                "concision": "tight",
                "instruction": "Stress-test whether the plan earns its cost and operational burden.",
            },
        },
        {
            "id": "D",
            "type": "reliability",
            "label": "Reliability",
            "role": "adversarial",
            "focus": "recovery semantics, resumability, state integrity, and production hardening",
            "temperature": "cool",
            "model": model,
            "harness": {
                "concision": "tight",
                "instruction": "Pressure-test reliability, recovery, and publish semantics.",
            },
        },
    ]


def build_objective(readme_excerpt: str) -> str:
    return (
        "Read the README excerpt below as the only repo context. Decide the next 45-day architecture plan to improve "
        "answer quality and robustness without weakening the full-context adversarial thesis. Choose a primary "
        "priority order across these five candidates: separate commander reevaluation pass, GitHub/file tooling, "
        "shared retrieval cache, stronger eval benchmarks, summarizer mini-adversary. Then give a concrete plan, "
        "top risks, and what not to build yet.\n\nREADME excerpt:\n\n"
        + readme_excerpt
    )


def terminal_status(status: Any) -> bool:
    return str(status or "") in {"completed", "cancelled", "error", "budget_exhausted", "interrupted"}


def wait_for_idle_workspace(base_url: str, timeout_seconds: float = 120.0) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_state: Dict[str, Any] | None = None
    while time.time() < deadline:
        last_state = request_json(api_url(base_url, "state"), timeout=20)
        loop = last_state.get("loop") if isinstance(last_state.get("loop"), dict) else {}
        dispatch = last_state.get("dispatch") if isinstance(last_state.get("dispatch"), dict) else {}
        if loop.get("status") not in {"queued", "running"} and dispatch.get("status") == "idle":
            return last_state
        time.sleep(1.0)
    raise QAError(f"Workspace did not become idle within {timeout_seconds:.1f}s: {json.dumps(last_state or {}, indent=2)}")


def wait_for_task_dispatch_terminal(base_url: str, task_id: str, timeout_seconds: float = 180.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        history = request_json(api_url(base_url, "history"), timeout=20)
        active_jobs = [
            job
            for job in history.get("jobs", [])
            if isinstance(job, dict)
            and str(job.get("taskId") or "") == task_id
            and str(job.get("jobType") or "") == "target"
            and not terminal_status(job.get("status"))
        ]
        if not active_jobs:
            return
        time.sleep(2.0)
    raise QAError(f"Dispatch jobs for {task_id} did not settle within {timeout_seconds:.1f}s.")


def parse_step_auth_assignments(root: Path, task_id: str) -> Dict[str, int]:
    steps_path = root / "data" / "steps.jsonl"
    assignments: Dict[str, int] = {}
    if not steps_path.exists():
        return assignments
    with steps_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            context = entry.get("context") if isinstance(entry.get("context"), dict) else {}
            if str(context.get("taskId") or "") != task_id:
                continue
            auth = context.get("auth") if isinstance(context.get("auth"), dict) else {}
            key_slot = int(auth.get("keySlot", 0) or 0)
            if key_slot <= 0:
                continue
            stage = str(entry.get("stage") or "").strip()
            target = str(context.get("target") or stage or "").strip()
            if target:
                assignments[target] = key_slot
    return assignments


def run_dispatch_smoke(
    root: Path,
    base_url: str,
    runtime_url: str,
    model: str,
    summarizer_model: str,
    reasoning_effort: str,
    restart_runtime_first: bool,
) -> Dict[str, Any]:
    if restart_runtime_first:
        restart_runtime(runtime_url)

    wait_for_idle_workspace(base_url, timeout_seconds=120.0)
    readme_excerpt = load_readme_excerpt(root)
    workers = build_workers(model)
    budget_targets = {
        "commander": {"maxTotalTokens": 180000, "maxCostUsd": 15, "maxOutputTokens": 6400},
        "worker": {"maxTotalTokens": 180000, "maxCostUsd": 15, "maxOutputTokens": 5200},
        "summarizer": {"maxTotalTokens": 260000, "maxCostUsd": 20, "maxOutputTokens": 9000},
    }

    task_id = ""
    with PreservedState(root) as preserved:
        try:
            qa_print("Starting fresh dispatch smoke task")
            start = request_json(
                api_url(base_url, "task_start"),
                method="POST",
                form_data={
                    "objective": build_objective(readme_excerpt),
                    "constraints": json.dumps(
                        [
                            "No web browsing.",
                            "Use only the provided README excerpt.",
                            "Be decisive.",
                            "Prefer a concrete 45-day plan over generic caution.",
                            "Only change course if objections materially alter correctness or practicality.",
                        ]
                    ),
                    "sessionContext": "",
                    "workers": json.dumps(workers),
                    "summarizerHarness": json.dumps(
                        {
                            "concision": "balanced",
                            "instruction": "Answer like one lead architect. Only redirect or reverse if the objections genuinely earn it.",
                        }
                    ),
                    "executionMode": "live",
                    "model": model,
                    "summarizerModel": summarizer_model,
                    "reasoningEffort": reasoning_effort,
                    "maxTotalTokens": "0",
                    "maxCostUsd": "0",
                    "maxOutputTokens": "0",
                    "budgetTargets": json.dumps(budget_targets),
                    "researchEnabled": "0",
                    "researchExternalWebAccess": "0",
                    "vettingEnabled": "1",
                    "loopRounds": "1",
                    "loopDelayMs": "0",
                },
                timeout=40,
            )
            task_id = str(start.get("taskId") or "").strip()
            if not task_id:
                raise QAError("Dispatch smoke taskId was missing.")

            round_start = request_json(api_url(base_url, "round_run"), method="POST", form_data={}, timeout=30)
            batch_id = str(round_start.get("batchId") or "").strip()
            if not batch_id:
                raise QAError("Round dispatch batchId was missing.")

            answer_triggered = False
            answer_job_id = ""
            dispatch_non_idle_seen = False
            partial_summary_seen = False
            final_jobs: List[Dict[str, Any]] = []
            deadline = time.time() + 900.0

            while time.time() < deadline:
                time.sleep(2.0)
                state = request_json(api_url(base_url, "state"), timeout=20)
                history = request_json(api_url(base_url, "history"), timeout=20)
                jobs = [
                    job
                    for job in history.get("jobs", [])
                    if isinstance(job, dict) and str(job.get("taskId") or "") == task_id and str(job.get("jobType") or "") == "target"
                ]
                final_jobs = jobs
                if not jobs:
                    continue

                dispatch = state.get("dispatch") if isinstance(state.get("dispatch"), dict) else {}
                active_jobs = dispatch.get("activeJobs") if isinstance(dispatch.get("activeJobs"), list) else []
                if active_jobs:
                    dispatch_non_idle_seen = True

                commander_done = any(str(job.get("target") or "") == "commander" and str(job.get("status") or "") == "completed" for job in jobs)
                non_commander_active = any(
                    str(job.get("target") or "") not in {"commander", "answer_now"} and not terminal_status(job.get("status"))
                    for job in jobs
                )
                if commander_done and non_commander_active and not answer_triggered:
                    answer = request_json(
                        api_url(base_url, "target_background"),
                        method="POST",
                        form_data={"target": "answer_now"},
                        timeout=30,
                    )
                    answer_job_id = str(answer.get("jobId") or "").strip()
                    if not answer_job_id:
                        raise QAError("Answer Now did not return a jobId.")
                    answer_triggered = True

                if answer_job_id and any(str(job.get("jobId") or "") == answer_job_id and terminal_status(job.get("status")) for job in jobs):
                    partial_summary_seen = True

                remaining_main = [
                    job for job in jobs
                    if str(job.get("target") or "") != "answer_now" and not terminal_status(job.get("status"))
                ]
                answer_done = not answer_job_id or any(
                    str(job.get("jobId") or "") == answer_job_id and terminal_status(job.get("status"))
                    for job in jobs
                )
                if not remaining_main and answer_done:
                    break

            if not final_jobs:
                raise QAError("Dispatch smoke never surfaced target jobs in history.")

            if not dispatch_non_idle_seen:
                raise QAError("Dispatch smoke never showed a non-idle dispatch state while target jobs were active.")

            required_targets = {"commander", "A", "B", "C", "D", "commander_review", "summarizer"}
            seen_targets = {str(job.get("target") or "") for job in final_jobs}
            missing_targets = sorted(required_targets - seen_targets)
            if missing_targets:
                raise QAError(f"Dispatch smoke did not create all expected target jobs: {', '.join(missing_targets)}")

            non_completed = [
                f"{job.get('target')}={job.get('status')}"
                for job in final_jobs
                if str(job.get("target") or "") != "answer_now" and str(job.get("status") or "") != "completed"
            ]
            if non_completed:
                raise QAError("Some round target jobs did not complete cleanly: " + ", ".join(non_completed))

            if not answer_triggered:
                raise QAError("Answer Now was never triggered while workers were still active.")

            answer_status = next(
                (str(job.get("status") or "") for job in final_jobs if str(job.get("jobId") or "") == answer_job_id),
                "",
            )
            if answer_status != "completed":
                raise QAError(f"Answer Now job did not complete cleanly: {answer_status or 'missing'}")

            final_state = request_json(api_url(base_url, "state"), timeout=20)
            if str((final_state.get("dispatch") or {}).get("status") or "") != "idle":
                raise QAError("Dispatch state did not return to idle after the smoke.")
            summary = final_state.get("summary")
            if not isinstance(summary, dict):
                raise QAError("Final summary was missing from state after dispatch smoke.")
            front_answer = summary.get("frontAnswer") if isinstance(summary.get("frontAnswer"), dict) else {}
            if not str(front_answer.get("answer") or "").strip():
                raise QAError("Final summary frontAnswer.answer was empty.")

            final_history = request_json(api_url(base_url, "history"), timeout=20)
            artifacts = [artifact for artifact in final_history.get("artifacts", []) if isinstance(artifact, dict) and str(artifact.get("taskId") or "") == task_id]
            partial_artifacts = [artifact for artifact in artifacts if str(artifact.get("kind") or "") == "summary_partial_output"]
            commander_review_artifacts = [
                artifact for artifact in artifacts if str(artifact.get("kind") or "") == "commander_review_output"
            ]
            summary_artifacts = [artifact for artifact in artifacts if str(artifact.get("kind") or "") == "summary_output"]
            if not partial_artifacts:
                raise QAError("Answer Now did not leave a summary_partial_output artifact.")
            if not commander_review_artifacts:
                raise QAError("Commander review did not leave a commander_review_output artifact.")
            if not summary_artifacts:
                raise QAError("Full summarizer did not leave a summary_output artifact.")

            assignments = parse_step_auth_assignments(root, task_id)
            unique_slots = sorted({slot for slot in assignments.values() if slot > 0})
            if len(unique_slots) < 6:
                raise QAError(
                    f"Expected all six key slots to be exercised across the round, but only saw {len(unique_slots)} slot(s): {unique_slots}"
                )

            usage = final_state.get("usage") if isinstance(final_state.get("usage"), dict) else {}
            return {
                "taskId": task_id,
                "batchId": batch_id,
                "answerNowJobId": answer_job_id,
                "dispatchState": final_state.get("dispatch"),
                "summaryRound": summary.get("round"),
                "frontAnswerConfidenceNote": front_answer.get("confidenceNote"),
                "targetJobs": [
                    {
                        "jobId": job.get("jobId"),
                        "target": job.get("target"),
                        "status": job.get("status"),
                        "partialSummary": job.get("partialSummary"),
                        "estimatedCostUsd": job.get("estimatedCostUsd"),
                        "totalTokens": job.get("totalTokens"),
                    }
                    for job in final_jobs
                ],
                "partialArtifacts": [artifact.get("name") for artifact in partial_artifacts],
                "commanderReviewArtifacts": [artifact.get("name") for artifact in commander_review_artifacts],
                "summaryArtifacts": [artifact.get("name") for artifact in summary_artifacts],
                "authAssignments": assignments,
                "uniqueKeySlots": unique_slots,
                "totalTokens": int(usage.get("totalTokens", 0) or 0),
                "estimatedCostUsd": float(usage.get("estimatedCostUsd", 0.0) or 0.0),
                "answerNowCompleted": partial_summary_seen,
            }
        finally:
            if task_id:
                try:
                    wait_for_task_dispatch_terminal(base_url, task_id, timeout_seconds=120.0)
                except QAError as cleanup_error:
                    qa_print(f"Cleanup warning: {cleanup_error}")
                qa_print(f"Cleaning reversible dispatch smoke artifacts for {task_id}")
                preserved.cleanup_task_artifacts(task_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a reusable smoke for async target dispatch plus Answer Now.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base browser URL for the local app.")
    parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL, help="Resident Python runtime URL.")
    parser.add_argument("--model", default="gpt-5-mini", help="Worker model for the dispatch smoke.")
    parser.add_argument("--summarizer-model", default="gpt-5-mini", help="Summarizer model for the dispatch smoke.")
    parser.add_argument("--reasoning-effort", default="high", help="Reasoning effort for the dispatch smoke.")
    parser.add_argument("--skip-prechecks", action="store_true", help="Skip Python/JS/http prechecks and run only the dispatch smoke.")
    parser.add_argument("--no-restart-runtime", action="store_true", help="Do not refresh the resident runtime before the smoke.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()
    node_bin = find_node_binary()

    qa_print(f"Project root: {root}")
    qa_print(f"Worker model: {args.model}")
    qa_print(f"Summarizer model: {args.summarizer_model}")

    try:
        ensure_auth_available(args.base_url)
    except QAError as error:
        message = str(error)
        if message.startswith("SKIP:"):
            qa_print(message)
            return 0
        qa_print(f"FAIL: {message}")
        return 1

    try:
        if not args.skip_prechecks:
            run_python_checks(root)
            run_js_checks(root, node_bin)
            run_http_checks(args.base_url)
        result = run_dispatch_smoke(
            root=root,
            base_url=args.base_url,
            runtime_url=args.runtime_url,
            model=args.model,
            summarizer_model=args.summarizer_model,
            reasoning_effort=args.reasoning_effort,
            restart_runtime_first=not args.no_restart_runtime,
        )
    except QAError as error:
        qa_print(f"FAIL: {error}")
        return 1
    except Exception as error:  # pragma: no cover - defensive in smoke script
        qa_print(f"FAIL: unexpected error: {error}")
        return 1

    qa_print("PASS")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
