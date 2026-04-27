from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from runtime.engine import LoopRuntime, RuntimeErrorWithCode, normalize_front_answer, summarizer_config, utc_now
from runtime.eval_runner import (
    answer_similarity_metrics,
    build_answer_telemetry,
    run_answer_health_judge,
    run_comparison_judge,
    run_control_judge,
    run_quality_judge,
)


ARBITER_RUBRIC = {
    "mustDo": [
        "Answer in a single assistant voice.",
        "Give a decisive operator recommendation, not just a menu of options.",
        "Keep the answer factual, methodical, and sequenced.",
        "Preserve uncertainty where facts are incomplete instead of pretending certainty.",
        "Protect safety, responsibility, and escalation boundaries.",
    ],
    "qualitySignals": [
        "Separates immediate action from later cleanup.",
        "Uses assumptions carefully and labels risk when evidence is weak.",
        "Keeps the answer explorable and professionally structured.",
        "Improves real operator judgment instead of adding empty verbosity.",
    ],
}


def current_answer_fingerprint(task: Dict[str, Any], summary: Dict[str, Any], direct_baseline: Dict[str, Any]) -> str:
    seed = "||".join(
        [
            str(task.get("taskId") or ""),
            str(summary.get("round") or 0),
            str(summary.get("mergedAt") or ""),
            str(direct_baseline.get("capturedAt") or ""),
            str((normalize_front_answer(summary.get("frontAnswer"), summary) or {}).get("answer") or ""),
            str(((direct_baseline.get("answer") or {}) if isinstance(direct_baseline.get("answer"), dict) else {}).get("answer") or ""),
        ]
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _build_case(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "caseId": str(task.get("taskId") or "front-eval"),
        "title": str(task.get("objective") or "Front compare").strip()[:120] or "Front compare",
        "objective": str(task.get("objective") or "").strip(),
        "constraints": list(task.get("constraints") or []) if isinstance(task.get("constraints"), list) else [],
        "gold": {},
    }


def _judge_provider() -> str:
    return "openai"


def _judge_model() -> str:
    return "gpt-5.4"


def run_current_task_arbiter(runtime: LoopRuntime, task_id: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options = options if isinstance(options, dict) else {}
    state = runtime.read_state()
    task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    if not isinstance(task, dict):
        raise RuntimeErrorWithCode("No active task.", 400)
    if task_id and str(task.get("taskId") or "") != str(task_id):
        raise RuntimeErrorWithCode("Requested task does not match the active task.", 409)

    summary = state.get("summary") if isinstance(state.get("summary"), dict) else None
    direct_baseline = state.get("directBaseline") if isinstance(state.get("directBaseline"), dict) else None
    if not isinstance(summary, dict):
        raise RuntimeErrorWithCode("Arbiter needs a completed pressurized answer first.", 409)
    if not isinstance(direct_baseline, dict):
        raise RuntimeErrorWithCode("Arbiter needs the single-thread baseline first.", 409)

    fingerprint = current_answer_fingerprint(task, summary, direct_baseline)
    existing = state.get("arbiter") if isinstance(state.get("arbiter"), dict) else None
    if isinstance(existing, dict) and str(existing.get("fingerprint") or "") == fingerprint and not bool(options.get("force", False)):
        raise RuntimeErrorWithCode("Arbiter score already exists for the current answer pair.", 409)

    case = _build_case(task)
    pressurized_answer = str(normalize_front_answer(summary.get("frontAnswer"), summary).get("answer") or "").strip()
    baseline_answer = str(((direct_baseline.get("answer") or {}) if isinstance(direct_baseline.get("answer"), dict) else {}).get("answer") or "").strip()
    if not pressurized_answer:
        raise RuntimeErrorWithCode("Arbiter needs a completed pressurized front answer.", 409)
    if not baseline_answer:
        raise RuntimeErrorWithCode("Arbiter needs a completed single-thread baseline answer.", 409)

    judge_provider = _judge_provider()
    judge_model = _judge_model()
    round_number = max(1, int(summary.get("round") or 1))
    auth_assignments = runtime.provider_auth_assignments(judge_provider, "arbiter", task, round_number=round_number, salt="arbiter")
    auth_assignment = auth_assignments[0] if auth_assignments else None
    api_key = runtime.provider_live_api_key(judge_provider, auth_assignments)
    auth_meta = runtime.live_auth_meta(judge_provider, auth_assignment)

    summary_config = summarizer_config(task)
    pressurized_telemetry = build_answer_telemetry(
        pressurized_answer,
        summary.get("responseMeta") if isinstance(summary.get("responseMeta"), dict) else {},
        provider=str(summary_config.get("provider") or (task.get("runtime") or {}).get("provider") or ""),
        model=str(summary_config.get("model") or (task.get("runtime") or {}).get("model") or ""),
    )
    baseline_telemetry = build_answer_telemetry(
        baseline_answer,
        direct_baseline.get("responseMeta") if isinstance(direct_baseline.get("responseMeta"), dict) else {},
        provider=str(direct_baseline.get("provider") or ((task.get("runtime") or {}) if isinstance(task.get("runtime"), dict) else {}).get("directProvider") or ""),
        model=str(direct_baseline.get("model") or ((task.get("runtime") or {}) if isinstance(task.get("runtime"), dict) else {}).get("directModel") or ""),
    )
    quality = run_quality_judge(runtime, judge_provider, api_key, judge_model, case, ARBITER_RUBRIC, pressurized_answer, {})
    answer_health = run_answer_health_judge(runtime, judge_provider, api_key, judge_model, case, pressurized_answer, pressurized_telemetry, {})
    control = run_control_judge(runtime, judge_provider, api_key, judge_model, case, summary, {})
    baseline_quality = run_quality_judge(runtime, judge_provider, api_key, judge_model, case, ARBITER_RUBRIC, baseline_answer, {})
    baseline_answer_health = run_answer_health_judge(runtime, judge_provider, api_key, judge_model, case, baseline_answer, baseline_telemetry, {})
    similarity = answer_similarity_metrics(pressurized_answer, baseline_answer)
    comparison = run_comparison_judge(
        runtime,
        judge_provider,
        api_key,
        judge_model,
        case,
        ARBITER_RUBRIC,
        pressurized_answer,
        baseline_answer,
        quality,
        answer_health,
        baseline_quality,
        baseline_answer_health,
        similarity,
        {},
    )

    arbiter_payload = {
        "taskId": str(task.get("taskId") or ""),
        "round": round_number,
        "fingerprint": fingerprint,
        "scoredAt": utc_now(),
        "judge": {
            "provider": judge_provider,
            "model": judge_model,
            "auth": auth_meta,
            "live": bool(api_key),
        },
        "quality": quality,
        "answerHealth": answer_health,
        "control": control,
        "baselineQuality": baseline_quality,
        "baselineAnswerHealth": baseline_answer_health,
        "similarity": similarity,
        "comparison": comparison,
        "pressurized": {
            "answer": pressurized_answer,
            "telemetry": pressurized_telemetry,
        },
        "baseline": {
            "answer": baseline_answer,
            "telemetry": baseline_telemetry,
        },
    }

    runtime.mutate_state(lambda current: {**current, "arbiter": arbiter_payload})
    _, history_output = runtime.write_output_artifact(
        f"{task['taskId']}_arbiter_output.json",
        f"{task['taskId']}_arbiter_round{round_number:03d}_output.json",
        {
            "taskId": str(task.get("taskId") or ""),
            "artifactType": "arbiter_output",
            "target": "arbiter",
            "label": "External arbiter",
            "capturedAt": arbiter_payload["scoredAt"],
            "output": arbiter_payload,
        },
    )
    runtime.append_event(
        "arbiter_scored",
        {
            "taskId": task["taskId"],
            "round": round_number,
            "verdict": comparison.get("verdict"),
            "judgeModel": judge_model,
        },
    )
    runtime.append_step(
        "arbiter",
        "External arbiter scored the current compare pair.",
        {
            "taskId": task["taskId"],
            "round": round_number,
            "verdict": comparison.get("verdict"),
            "decisionRelation": comparison.get("decisionRelation"),
            "differentiation": ((comparison.get("scores") or {}) if isinstance(comparison.get("scores"), dict) else {}).get("overallDifferentiation"),
            "judgeModel": judge_model,
            "outputFile": history_output.name,
            "auth": auth_meta,
        },
    )
    return {
        "target": "arbiter",
        "output": "Arbiter score written.",
        "exitCode": 0,
        "backend": "python",
    }
