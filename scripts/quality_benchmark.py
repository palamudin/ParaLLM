from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

from qa_check import (
    DEFAULT_BASE_URL,
    DEFAULT_RUNTIME_URL,
    PreservedState,
    QAError,
    api_url,
    find_node_binary,
    find_php_binary,
    project_root,
    qa_print,
    request_json,
    require_text,
    restart_runtime,
    run_http_checks,
    run_js_checks,
    run_php_checks,
    run_python_checks,
)


SCORE_FIELDS = [
    "decisiveness",
    "tradeoffHandling",
    "objectionAbsorption",
    "actionability",
    "singleVoice",
    "overall",
]

CONTROL_SCORE_FIELDS = [
    "leadControl",
    "adversarialDiscipline",
    "selfCheckQuality",
    "nonFunnelIntegration",
    "overallControl",
]


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    title: str
    objective: str
    constraints: List[str]


CORE_CASES: Dict[str, BenchmarkCase] = {
    "sensitive-feature-launch": BenchmarkCase(
        case_id="sensitive-feature-launch",
        title="Sensitive AI Feature Launch",
        objective=(
            "You are advising a 12-person B2B SaaS. The team wants to ship AI-generated summaries for recorded customer "
            "support calls within 6 weeks. Calls can contain personal data, refund promises, and contract-sensitive details. "
            "The CEO wants a clear ship / no-ship recommendation plus the smallest rollout plan that would still be responsible."
        ),
        constraints=[
            "Answer in a single assistant voice.",
            "Give a decisive recommendation, not just a list of pros and cons.",
            "Absorb the strongest objections into the recommendation.",
            "Keep the answer concise but actionable.",
        ],
    ),
    "billing-replatform": BenchmarkCase(
        case_id="billing-replatform",
        title="Billing Replatform Before Peak Season",
        objective=(
            "A SaaS company wants to replace cron-based billing jobs with an event-driven queue system one month before its "
            "holiday traffic spike. The CTO wants a direct go / no-go call and the safest path forward."
        ),
        constraints=[
            "Give a direct recommendation with conditions.",
            "Do not hide behind generic caution.",
            "Explain the most important tradeoff and the concrete next step.",
        ],
    ),
}


def resolve_cases(case_arg: str) -> List[BenchmarkCase]:
    case_arg = (case_arg or "sensitive-feature-launch").strip().lower()
    if case_arg == "core":
        return list(CORE_CASES.values())
    if case_arg not in CORE_CASES:
        valid = ", ".join(sorted(CORE_CASES.keys()) + ["core"])
        raise QAError(f"Unknown benchmark case '{case_arg}'. Use one of: {valid}")
    return [CORE_CASES[case_arg]]


def parse_loop_sweep(raw: str | None, default_rounds: int) -> List[int]:
    if not raw:
        return [max(1, int(default_rounds or 1))]
    values: List[int] = []
    for chunk in raw.split(","):
        text = chunk.strip()
        if not text:
            continue
        try:
            value = int(text)
        except ValueError as error:
            raise QAError(f"Invalid loop count '{text}' in --loop-sweep.") from error
        if value < 1:
            raise QAError("Loop counts in --loop-sweep must be at least 1.")
        if value not in values:
            values.append(value)
    if not values:
        raise QAError("--loop-sweep did not contain any valid loop counts.")
    return values


def normalize_worker_list(model: str) -> List[Dict[str, Any]]:
    return [
        {
            "id": "A",
            "type": "proponent",
            "label": "Proponent",
            "role": "utility",
            "focus": "benefits, feasibility, leverage, momentum, practical execution",
            "temperature": "balanced",
            "model": model,
        },
        {
            "id": "B",
            "type": "sceptic",
            "label": "Sceptic",
            "role": "adversarial",
            "focus": "failure modes, downside, hidden coupling, consequences, externalities",
            "temperature": "cool",
            "model": model,
        },
        {
            "id": "C",
            "type": "security",
            "label": "Security",
            "role": "adversarial",
            "focus": "security abuse, privacy leakage, hostile actors, contractual exposure",
            "temperature": "hot",
            "model": model,
        },
    ]


def load_runtime(root: Path):
    runtime_path = root / "runtime"
    if str(runtime_path) not in sys.path:
        sys.path.insert(0, str(runtime_path))
    from engine import LoopRuntime  # type: ignore

    runtime = LoopRuntime(root)
    runtime.ensure_data_paths()
    return runtime


def direct_answer_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "stance", "confidenceNote"],
        "properties": {
            "answer": {"type": "string"},
            "stance": {"type": "string"},
            "confidenceNote": {"type": "string"},
        },
    }


def blind_judge_schema() -> Dict[str, Any]:
    score_block = {
        "type": "object",
        "additionalProperties": False,
        "required": SCORE_FIELDS,
        "properties": {field: {"type": "integer"} for field in SCORE_FIELDS},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "answerAScores",
            "answerBScores",
            "winner",
            "improvementVerdict",
            "significantImprovement",
            "strongestWinningAdvantage",
            "strongestWinningWeakness",
            "rationale",
        ],
        "properties": {
            "answerAScores": score_block,
            "answerBScores": score_block,
            "winner": {"type": "string"},
            "improvementVerdict": {"type": "string"},
            "significantImprovement": {"type": "boolean"},
            "strongestWinningAdvantage": {"type": "string"},
            "strongestWinningWeakness": {"type": "string"},
            "rationale": {"type": "string"},
        },
    }


def control_judge_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "scores",
            "verdict",
            "strongestControlStrength",
            "strongestControlWeakness",
            "rationale",
        ],
        "properties": {
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": CONTROL_SCORE_FIELDS,
                "properties": {field: {"type": "integer"} for field in CONTROL_SCORE_FIELDS},
            },
            "verdict": {"type": "string"},
            "strongestControlStrength": {"type": "string"},
            "strongestControlWeakness": {"type": "string"},
            "rationale": {"type": "string"},
        },
    }


def choose_answer_slots(case_id: str, trial_number: int) -> Dict[str, str]:
    seed = hashlib.sha256(f"{case_id}:{trial_number}".encode("utf-8")).digest()[0]
    if seed % 2 == 0:
        return {"answerA": "baseline", "answerB": "steered"}
    return {"answerA": "steered", "answerB": "baseline"}


def mean_or_zero(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def average_score_block(blocks: List[Dict[str, int]]) -> Dict[str, float]:
    if not blocks:
        return {field: 0.0 for field in SCORE_FIELDS}
    return {field: round(mean_or_zero([float(block[field]) for block in blocks]), 2) for field in SCORE_FIELDS}


def average_control_score_block(blocks: List[Dict[str, int]]) -> Dict[str, float]:
    if not blocks:
        return {field: 0.0 for field in CONTROL_SCORE_FIELDS}
    return {field: round(mean_or_zero([float(block[field]) for block in blocks]), 2) for field in CONTROL_SCORE_FIELDS}


def summarize_trial_set(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
    baseline_wins = 0
    steered_wins = 0
    ties = 0
    significant_steered_improvements = 0
    significant_baseline_improvements = 0
    baseline_blocks: List[Dict[str, int]] = []
    steered_blocks: List[Dict[str, int]] = []
    deltas: Dict[str, List[float]] = {field: [] for field in SCORE_FIELDS}

    for trial in trials:
        judge = trial.get("judge") if isinstance(trial.get("judge"), dict) else {}
        winner = str(judge.get("winner") or "").strip().lower()
        significant = bool(judge.get("significantImprovement"))
        baseline_scores = judge.get("baselineScores")
        steered_scores = judge.get("steeredScores")
        if isinstance(baseline_scores, dict):
            baseline_blocks.append({field: int(baseline_scores.get(field, 0) or 0) for field in SCORE_FIELDS})
        if isinstance(steered_scores, dict):
            steered_blocks.append({field: int(steered_scores.get(field, 0) or 0) for field in SCORE_FIELDS})
        score_delta = judge.get("scoreDelta") if isinstance(judge.get("scoreDelta"), dict) else {}
        for field in SCORE_FIELDS:
            deltas[field].append(float(score_delta.get(field, 0.0) or 0.0))

        if winner == "steered":
            steered_wins += 1
            if significant:
                significant_steered_improvements += 1
        elif winner == "baseline":
            baseline_wins += 1
            if significant:
                significant_baseline_improvements += 1
        else:
            ties += 1

    mean_delta = {field: round(mean_or_zero(deltas[field]), 2) for field in SCORE_FIELDS}
    verdict = "mixed"
    if steered_wins > baseline_wins and mean_delta["overall"] >= 0.5:
        verdict = "steered_advantage"
    elif baseline_wins > steered_wins and mean_delta["overall"] <= -0.5:
        verdict = "baseline_advantage"

    return {
        "trials": len(trials),
        "steeredWins": steered_wins,
        "baselineWins": baseline_wins,
        "ties": ties,
        "significantSteeredImprovements": significant_steered_improvements,
        "significantBaselineImprovements": significant_baseline_improvements,
        "averageBaselineScores": average_score_block(baseline_blocks),
        "averageSteeredScores": average_score_block(steered_blocks),
        "averageScoreDelta": mean_delta,
        "verdict": verdict,
    }


def summarize_control_trial_set(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
    blocks: List[Dict[str, int]] = []
    for trial in trials:
        control_judge = trial.get("controlJudge") if isinstance(trial.get("controlJudge"), dict) else {}
        scores = control_judge.get("scores")
        if isinstance(scores, dict):
            blocks.append({field: int(scores.get(field, 0) or 0) for field in CONTROL_SCORE_FIELDS})

    averages = average_control_score_block(blocks)
    overall = averages.get("overallControl", 0.0)
    lead_control = averages.get("leadControl", 0.0)
    verdict = "weak_control"
    if overall >= 8.0 and lead_control >= 8.0:
        verdict = "strong_control"
    elif overall >= 6.0:
        verdict = "developing_control"

    return {
        "trials": len(blocks),
        "averageControlScores": averages,
        "verdict": verdict,
    }


def run_direct_baseline(
    runtime: Any,
    api_key: str,
    case: BenchmarkCase,
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
) -> Dict[str, Any]:
    instructions = (
        "Answer the user directly as one assistant.\n"
        "Give a decisive but conditional recommendation.\n"
        "Do not narrate any hidden process.\n"
        "Do not turn the reply into a pros-and-cons list.\n"
        "Absorb tradeoffs into the recommendation itself.\n"
        "Keep the answer to at most 3 short paragraphs.\n"
        "Return JSON only that matches the schema."
    )
    input_text = (
        f"Objective:\n{case.objective}\n\n"
        f"Constraints:\n{json.dumps(case.constraints, ensure_ascii=False, indent=2)}\n\n"
        "Produce the strongest direct answer you can without any hidden multi-lane steering."
    )
    result = runtime.invoke_openai_json(
        api_key=api_key,
        model=model,
        reasoning_effort=reasoning_effort,
        instructions=instructions,
        input_text=input_text,
        schema_name="benchmark_direct_answer",
        schema=direct_answer_schema(),
        max_output_tokens=max_output_tokens,
        target_kind="generic",
    )
    return {
        "answer": result.parsed,
        "model": model,
        "reasoningEffort": reasoning_effort,
        "responseId": result.response_id,
        "attempts": result.attempts,
        "recoveredFromIncomplete": result.recovered_from_incomplete,
    }


def run_steered_case(
    base_url: str,
    case: BenchmarkCase,
    worker_model: str,
    summarizer_model: str,
    reasoning_effort: str,
    max_cost_usd: float,
    max_total_tokens: int,
    max_output_tokens: int,
    loop_rounds: int,
    require_live: bool,
) -> Dict[str, Any]:
    workers = normalize_worker_list(worker_model)
    start = request_json(
        api_url(base_url, "start_task.php"),
        method="POST",
        form_data={
            "objective": case.objective,
            "constraints": json.dumps(case.constraints),
            "sessionContext": "",
            "workers": json.dumps(workers),
            "executionMode": "live",
            "model": worker_model,
            "summarizerModel": summarizer_model,
            "reasoningEffort": reasoning_effort,
            "maxTotalTokens": str(max_total_tokens),
            "maxCostUsd": f"{max_cost_usd:.4f}",
            "maxOutputTokens": str(max_output_tokens),
            "researchEnabled": "0",
            "researchExternalWebAccess": "1",
            "researchDomains": "[]",
            "vettingEnabled": "1",
            "loopRounds": str(loop_rounds),
            "loopDelayMs": "0",
        },
        timeout=30,
    )
    task_id = require_text(start.get("taskId"), "steered taskId")

    for round_number in range(1, max(1, loop_rounds) + 1):
        qa_print(f"Running steered round {round_number} for {case.case_id}")
        for target in ("A", "B", "C", "summarizer"):
            request_json(
                api_url(base_url, "run_target.php"),
                method="POST",
                form_data={"target": target},
                timeout=300,
            )

    state = request_json(api_url(base_url, "get_state.php"), timeout=20)
    summary = state.get("summary")
    if not isinstance(summary, dict):
        raise QAError("Steered summary was missing from state.")
    front_answer = summary.get("frontAnswer")
    if not isinstance(front_answer, dict):
        raise QAError("Steered frontAnswer was missing.")
    summarizer_opinion = summary.get("summarizerOpinion")
    if not isinstance(summarizer_opinion, dict):
        raise QAError("Steered summarizerOpinion was missing.")
    control_audit = summary.get("controlAudit")
    if not isinstance(control_audit, dict):
        raise QAError("Steered controlAudit was missing.")

    artifact_name = f"{task_id}_summary_round{max(1, loop_rounds):03d}_output.json"
    artifact = request_json(
        api_url(base_url, "get_artifact.php") + "?name=" + quote(artifact_name),
        timeout=20,
    )
    artifact_output = artifact.get("content", {}).get("output")
    if not isinstance(artifact_output, dict):
        raise QAError("Steered summary artifact output was missing.")

    usage = state.get("usage") if isinstance(state.get("usage"), dict) else {}
    total_tokens = int(usage.get("totalTokens", 0) or 0)
    worker_modes: Dict[str, str] = {}
    for worker_id in ("A", "B", "C"):
        worker_artifact_name = f"{task_id}_{worker_id}_step{max(1, loop_rounds):03d}_output.json"
        worker_artifact = request_json(
            api_url(base_url, "get_artifact.php") + f"?name={quote(worker_artifact_name)}",
            timeout=20,
        )
        worker_mode = str(worker_artifact.get("content", {}).get("mode") or "").strip().lower()
        worker_modes[worker_id] = worker_mode or "unknown"

    summary_mode = str(artifact.get("content", {}).get("mode") or "").strip().lower()
    live_validation_error = ""
    if require_live:
        non_live_workers = [worker_id for worker_id, mode in worker_modes.items() if mode != "live"]
        if non_live_workers or summary_mode != "live" or total_tokens <= 0:
            live_validation_error = (
                "Invalid steer benchmark: the steered path fell back from live execution. "
                f"workerModes={worker_modes}, summaryMode={summary_mode or 'unknown'}, totalTokens={total_tokens}. "
                "Increase output caps, reduce loop depth, or tune prompts before trusting this comparison."
            )

    return {
        "taskId": task_id,
        "summary": summary,
        "artifact": artifact_name,
        "artifactOutput": artifact_output,
        "artifactMeta": artifact.get("summary", {}),
        "usage": usage,
        "workerModes": worker_modes,
        "summaryMode": summary_mode or "unknown",
        "liveValidationError": live_validation_error,
    }


def remap_blind_judgment(slot_map: Dict[str, str], blind_judgment: Dict[str, Any]) -> Dict[str, Any]:
    reverse_map = {value: key for key, value in slot_map.items()}
    baseline_slot = reverse_map["baseline"]
    steered_slot = reverse_map["steered"]
    baseline_scores = blind_judgment.get(f"{baseline_slot}Scores")
    steered_scores = blind_judgment.get(f"{steered_slot}Scores")

    if not isinstance(baseline_scores, dict) or not isinstance(steered_scores, dict):
        raise QAError("Blind judge response did not include both score blocks.")

    winner_lookup = {
        "answera": slot_map["answerA"],
        "answerb": slot_map["answerB"],
        "tie": "tie",
        "equal": "tie",
    }
    raw_winner = str(blind_judgment.get("winner") or "").strip().lower()
    winner = winner_lookup.get(raw_winner, "tie")

    baseline_scores_int = {field: int(baseline_scores.get(field, 0) or 0) for field in SCORE_FIELDS}
    steered_scores_int = {field: int(steered_scores.get(field, 0) or 0) for field in SCORE_FIELDS}
    score_delta = {field: steered_scores_int[field] - baseline_scores_int[field] for field in SCORE_FIELDS}

    return {
        "baselineScores": baseline_scores_int,
        "steeredScores": steered_scores_int,
        "winner": winner,
        "improvementVerdict": str(blind_judgment.get("improvementVerdict") or "").strip(),
        "significantImprovement": bool(blind_judgment.get("significantImprovement")),
        "strongestWinningAdvantage": str(blind_judgment.get("strongestWinningAdvantage") or "").strip(),
        "strongestWinningWeakness": str(blind_judgment.get("strongestWinningWeakness") or "").strip(),
        "rationale": str(blind_judgment.get("rationale") or "").strip(),
        "scoreDelta": score_delta,
    }


def run_blind_judge(
    runtime: Any,
    api_key: str,
    case: BenchmarkCase,
    judge_model: str,
    baseline: Dict[str, Any],
    steered: Dict[str, Any],
    trial_number: int,
) -> Dict[str, Any]:
    slot_map = choose_answer_slots(case.case_id, trial_number)
    answers = {
        "baseline": baseline["answer"]["answer"],
        "steered": steered["summary"]["frontAnswer"]["answer"],
    }
    answer_a = answers[slot_map["answerA"]]
    answer_b = answers[slot_map["answerB"]]

    instructions = (
        "You are grading two anonymous candidate answers to the same user request.\n"
        "Do not assume either answer used a better process.\n"
        "Score both answers from 1 to 10 on each criterion.\n"
        "Prefer answers that are decisive, absorb objections into the recommendation, stay single-voice, and give concrete next steps.\n"
        "Do not reward verbosity.\n"
        "If one answer is only longer but not better, say so.\n"
        "winner must be exactly one of: answerA, answerB, tie.\n"
        "Return JSON only that matches the schema."
    )
    input_text = (
        f"Benchmark case: {case.title}\n\n"
        f"Objective:\n{case.objective}\n\n"
        f"Constraints:\n{json.dumps(case.constraints, ensure_ascii=False, indent=2)}\n\n"
        f"Answer A:\n{answer_a}\n\n"
        f"Answer B:\n{answer_b}\n"
    )
    result = runtime.invoke_openai_json(
        api_key=api_key,
        model=judge_model,
        reasoning_effort="high",
        instructions=instructions,
        input_text=input_text,
        schema_name="benchmark_blind_comparison_judge",
        schema=blind_judge_schema(),
        max_output_tokens=1800,
        target_kind="generic",
    )
    return {
        "slotMap": slot_map,
        "blindJudgment": result.parsed,
        "responseId": result.response_id,
        "attempts": result.attempts,
        **remap_blind_judgment(slot_map, result.parsed),
    }


def run_control_judge(
    runtime: Any,
    api_key: str,
    case: BenchmarkCase,
    judge_model: str,
    steered: Dict[str, Any],
) -> Dict[str, Any]:
    summary = steered["summary"]
    front_answer = summary.get("frontAnswer", {})
    opinion = summary.get("summarizerOpinion", {})
    control_audit = summary.get("controlAudit", {})

    instructions = (
        "You are grading whether a lead assistant thread stayed in control of adversarial pressure.\n"
        "Reward answers where the lead direction is clear, adversarial objections are selectively integrated, rejected pressure is actually rejected, and the final answer is checked against the user's real request.\n"
        "Penalize funnel-like behavior where adversarial content is merely forwarded, averaged, or allowed to steer the answer blindly.\n"
        "Score from 1 to 10 on each control criterion.\n"
        "Return JSON only that matches the schema."
    )
    input_text = (
        f"Benchmark case: {case.title}\n\n"
        f"Objective:\n{case.objective}\n\n"
        f"Constraints:\n{json.dumps(case.constraints, ensure_ascii=False, indent=2)}\n\n"
        f"Public answer:\n{front_answer.get('answer', '')}\n\n"
        f"Lead direction:\n{front_answer.get('leadDirection', '')}\n\n"
        f"Absorbed adversarial pressure:\n{front_answer.get('adversarialPressure', '')}\n\n"
        f"Current stance:\n{opinion.get('stance', '')}\n\n"
        f"Integration mode:\n{opinion.get('integrationMode', '')}\n\n"
        f"Lead draft before pressure:\n{control_audit.get('leadDraft', '')}\n\n"
        f"Control question:\n{control_audit.get('integrationQuestion', '')}\n\n"
        f"Accepted adversarial points:\n{json.dumps(control_audit.get('acceptedAdversarialPoints', []), ensure_ascii=False, indent=2)}\n\n"
        f"Rejected adversarial points:\n{json.dumps(control_audit.get('rejectedAdversarialPoints', []), ensure_ascii=False, indent=2)}\n\n"
        f"Held-out concerns:\n{json.dumps(control_audit.get('heldOutConcerns', []), ensure_ascii=False, indent=2)}\n\n"
        f"Pre-release self-check:\n{control_audit.get('selfCheck', '')}\n"
    )
    result = runtime.invoke_openai_json(
        api_key=api_key,
        model=judge_model,
        reasoning_effort="high",
        instructions=instructions,
        input_text=input_text,
        schema_name="benchmark_control_judge",
        schema=control_judge_schema(),
        max_output_tokens=1400,
        target_kind="generic",
    )
    parsed = result.parsed
    scores = parsed.get("scores")
    if not isinstance(scores, dict):
        raise QAError("Control judge response did not include score output.")
    return {
        "scores": {field: int(scores.get(field, 0) or 0) for field in CONTROL_SCORE_FIELDS},
        "verdict": str(parsed.get("verdict") or "").strip(),
        "strongestControlStrength": str(parsed.get("strongestControlStrength") or "").strip(),
        "strongestControlWeakness": str(parsed.get("strongestControlWeakness") or "").strip(),
        "rationale": str(parsed.get("rationale") or "").strip(),
        "responseId": result.response_id,
        "attempts": result.attempts,
    }


def benchmark_output_path(root: Path, timestamp: str) -> Path:
    path = root / "data" / "benchmarks"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"benchmark-{timestamp}.json"


def execute_suite(
    root: Path,
    preserved: PreservedState,
    runtime: Any,
    api_key: str,
    args: argparse.Namespace,
    cases: List[BenchmarkCase],
    loop_rounds: int,
) -> Tuple[Dict[str, Any], List[str]]:
    task_ids_to_cleanup: List[str] = []
    suite: Dict[str, Any] = {
        "loopRounds": loop_rounds,
        "cases": [],
    }

    for case in cases:
        qa_print(f"Benchmarking {case.case_id} with {args.repeats} trial(s) at {loop_rounds} loop(s)")
        trials: List[Dict[str, Any]] = []
        for trial_number in range(1, args.repeats + 1):
            qa_print(f"Trial {trial_number}/{args.repeats} for {case.case_id}")
            request_json(api_url(args.base_url, "reset_state.php"), method="POST", timeout=20)

            baseline = run_direct_baseline(
                runtime=runtime,
                api_key=api_key,
                case=case,
                model=args.baseline_model,
                reasoning_effort=args.reasoning_effort,
                max_output_tokens=args.max_output_tokens,
            )
            steered = run_steered_case(
                base_url=args.base_url,
                case=case,
                worker_model=args.worker_model,
                summarizer_model=args.summarizer_model,
                reasoning_effort=args.reasoning_effort,
                max_cost_usd=args.max_cost_usd,
                max_total_tokens=args.max_total_tokens,
                max_output_tokens=args.max_output_tokens,
                loop_rounds=loop_rounds,
                require_live=not args.allow_mock_fallback,
            )
            task_ids_to_cleanup.append(steered["taskId"])
            if steered["liveValidationError"]:
                raise QAError(steered["liveValidationError"])

            judge = run_blind_judge(
                runtime=runtime,
                api_key=api_key,
                case=case,
                judge_model=args.judge_model,
                baseline=baseline,
                steered=steered,
                trial_number=trial_number,
            )
            control_judge = run_control_judge(
                runtime=runtime,
                api_key=api_key,
                case=case,
                judge_model=args.judge_model,
                steered=steered,
            )

            trial_entry = {
                "trial": trial_number,
                "baseline": baseline,
                "steered": {
                    "taskId": steered["taskId"],
                    "artifact": steered["artifact"],
                    "frontAnswer": steered["summary"]["frontAnswer"],
                    "summarizerOpinion": steered["summary"]["summarizerOpinion"],
                    "controlAudit": steered["summary"]["controlAudit"],
                    "workerModes": steered["workerModes"],
                    "summaryMode": steered["summaryMode"],
                    "usage": steered["usage"],
                },
                "judge": judge,
                "controlJudge": control_judge,
            }
            trials.append(trial_entry)
            qa_print(
                f"Trial {trial_number} result: winner={judge['winner']} overallDelta={judge['scoreDelta']['overall']:+d} control={control_judge['scores']['overallControl']}/10"
            )

            if not args.keep_artifacts:
                preserved.cleanup_task_artifacts(steered["taskId"])

        case_summary = summarize_trial_set(trials)
        control_summary = summarize_control_trial_set(trials)
        suite["cases"].append(
            {
                "caseId": case.case_id,
                "title": case.title,
                "objective": case.objective,
                "constraints": case.constraints,
                "trials": trials,
                "aggregate": case_summary,
                "controlAggregate": control_summary,
            }
        )
        qa_print(
            f"Case summary for {case.case_id}: avgOverallDelta={case_summary['averageScoreDelta']['overall']:+.2f} avgControl={control_summary['averageControlScores']['overallControl']:.2f}"
        )

    all_trials = [
        trial
        for case_entry in suite["cases"]
        for trial in case_entry.get("trials", [])
        if isinstance(trial, dict)
    ]
    suite["summary"] = summarize_trial_set(all_trials)
    suite["controlSummary"] = summarize_control_trial_set(all_trials)
    return suite, task_ids_to_cleanup


def build_loop_sweep_comparison(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    comparison: List[Dict[str, Any]] = []
    for run in runs:
        if str(run.get("status") or "") == "error":
            comparison.append(
                {
                    "loopRounds": int(run.get("loopRounds", 0) or 0),
                    "status": "error",
                    "error": str(run.get("error") or ""),
                }
            )
            continue
        summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
        control_summary = run.get("controlSummary") if isinstance(run.get("controlSummary"), dict) else {}
        comparison.append(
            {
                "loopRounds": int(run.get("loopRounds", 0) or 0),
                "status": "ok",
                "trials": int(summary.get("trials", 0) or 0),
                "verdict": str(summary.get("verdict") or ""),
                "averageSteeredOverall": float(summary.get("averageSteeredScores", {}).get("overall", 0.0) or 0.0),
                "averageOverallDelta": float(summary.get("averageScoreDelta", {}).get("overall", 0.0) or 0.0),
                "averageControlOverall": float(control_summary.get("averageControlScores", {}).get("overallControl", 0.0) or 0.0),
                "averageLeadControl": float(control_summary.get("averageControlScores", {}).get("leadControl", 0.0) or 0.0),
                "controlVerdict": str(control_summary.get("verdict") or ""),
            }
        )
    return comparison


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare direct baseline answers against steered loop answers and judge the delta."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base browser URL for the local app.")
    parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL, help="Resident Python runtime URL.")
    parser.add_argument(
        "--case",
        default="sensitive-feature-launch",
        help="Benchmark case id or 'core' to run the built-in suite.",
    )
    parser.add_argument("--baseline-model", default="gpt-5.4", help="Model used for the direct baseline answer.")
    parser.add_argument("--worker-model", default="gpt-5-mini", help="Model used for steered worker lanes.")
    parser.add_argument("--summarizer-model", default="gpt-5.4", help="Model used for the steered summarizer.")
    parser.add_argument("--judge-model", default="gpt-5.4", help="Model used to grade baseline vs steered output.")
    parser.add_argument("--reasoning-effort", default="medium", help="Reasoning effort for baseline and steered summarizer.")
    parser.add_argument("--loop-rounds", type=int, default=1, help="Number of steered rounds to run.")
    parser.add_argument("--loop-sweep", default="", help="Comma-separated loop counts to benchmark, for example 1,2,3.")
    parser.add_argument("--repeats", type=int, default=1, help="How many benchmark trials to run per case.")
    parser.add_argument("--max-cost-usd", type=float, default=4.00, help="Budget cap for each steered run.")
    parser.add_argument("--max-total-tokens", type=int, default=120000, help="Token cap for each steered run.")
    parser.add_argument("--max-output-tokens", type=int, default=2800, help="Requested max output tokens per call.")
    parser.add_argument("--skip-prechecks", action="store_true", help="Skip Python/PHP/JS/http prechecks and run only the benchmark.")
    parser.add_argument("--no-restart-runtime", action="store_true", help="Do not refresh the resident runtime before the benchmark.")
    parser.add_argument("--keep-artifacts", action="store_true", help="Keep generated task artifacts instead of cleaning them up.")
    parser.add_argument(
        "--allow-mock-fallback",
        action="store_true",
        help="Permit mock-fallback steered runs instead of failing the benchmark as invalid.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repeats < 1:
        qa_print("FAIL: --repeats must be at least 1.")
        return 1

    root = project_root()
    runtime = load_runtime(root)
    api_key = runtime.get_api_key()
    if not api_key:
        qa_print("FAIL: no API key is stored locally, so the benchmark cannot run.")
        return 1

    cases = resolve_cases(args.case)
    loop_values = parse_loop_sweep(args.loop_sweep, args.loop_rounds)

    if not args.skip_prechecks:
        run_python_checks(root)
        run_php_checks(root, find_php_binary(root))
        run_js_checks(root, find_node_binary())
        run_http_checks(args.base_url)

    if not args.no_restart_runtime:
        restart_runtime(args.runtime_url)

    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    report: Dict[str, Any] = {
        "generatedAt": timestamp,
        "config": {
            "baselineModel": args.baseline_model,
            "workerModel": args.worker_model,
            "summarizerModel": args.summarizer_model,
            "judgeModel": args.judge_model,
            "reasoningEffort": args.reasoning_effort,
            "loopRounds": args.loop_rounds,
            "loopSweep": loop_values,
            "repeats": args.repeats,
            "maxCostUsdPerSteeredRun": args.max_cost_usd,
            "maxTotalTokensPerSteeredRun": args.max_total_tokens,
            "maxOutputTokens": args.max_output_tokens,
            "keepArtifacts": bool(args.keep_artifacts),
            "allowMockFallback": bool(args.allow_mock_fallback),
        },
    }

    task_ids_to_cleanup: List[str] = []
    with PreservedState(root) as preserved:
        try:
            runs: List[Dict[str, Any]] = []
            for loop_rounds in loop_values:
                try:
                    run_report, run_task_ids = execute_suite(
                        root=root,
                        preserved=preserved,
                        runtime=runtime,
                        api_key=api_key,
                        args=args,
                        cases=cases,
                        loop_rounds=loop_rounds,
                    )
                    run_report["status"] = "ok"
                    runs.append(run_report)
                    task_ids_to_cleanup.extend(run_task_ids)
                except QAError as error:
                    qa_print(f"Loop sweep entry {loop_rounds} failed: {error}")
                    runs.append(
                        {
                            "loopRounds": loop_rounds,
                            "status": "error",
                            "error": str(error),
                        }
                    )

            if len(runs) == 1:
                report.update(runs[0])
            else:
                report["runs"] = runs
                report["loopSweepComparison"] = build_loop_sweep_comparison(runs)
        finally:
            request_json(api_url(args.base_url, "reset_state.php"), method="POST", timeout=20)
            if not args.keep_artifacts:
                for task_id in task_ids_to_cleanup:
                    if task_id:
                        preserved.cleanup_task_artifacts(task_id)

    output_path = benchmark_output_path(root, timestamp)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    qa_print("PASS")
    qa_print(f"Saved benchmark report to {output_path}")

    if "runs" in report:
        print(
            json.dumps(
                {
                    "loopSweepComparison": report.get("loopSweepComparison", []),
                    "savedReport": str(output_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "summary": report.get("summary", {}),
                    "controlSummary": report.get("controlSummary", {}),
                    "savedReport": str(output_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
