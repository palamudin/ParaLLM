from __future__ import annotations

import argparse
import hashlib
import json
import re
import traceback
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine import (
    LoopRuntime,
    RuntimeErrorWithCode,
    auth_assignment_meta,
    coerce_bool,
    default_budget_config,
    default_loop_state,
    default_research_config,
    default_state,
    default_usage_state,
    default_vetting_config,
    normalize_budget_config,
    normalize_model_id,
    normalize_research_config,
    normalize_string_array_preserve_items,
    normalize_usage_state,
    normalize_vetting_config,
    task_workers,
    utc_now,
)


QUALITY_SCORE_FIELDS = [
    "decisiveness",
    "tradeoffHandling",
    "objectionAbsorption",
    "actionability",
    "singleVoice",
    "overallQuality",
]

CONTROL_SCORE_FIELDS = [
    "leadControl",
    "adversarialDiscipline",
    "selfCheckQuality",
    "nonFunnelIntegration",
    "overallControl",
]


class EvalError(RuntimeError):
    pass


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise EvalError(f"Missing JSON file: {path}")
    raw = path.read_text(encoding="utf-8").lstrip("\ufeff")
    if not raw.strip():
        raise EvalError(f"Empty JSON file: {path}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise EvalError(f"Invalid JSON in {path.name}: {error}") from error
    if not isinstance(payload, dict):
        raise EvalError(f"Expected an object in {path.name}.")
    return payload


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def sanitize_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip())
    return cleaned.strip("-") or "item"


def build_task_id(seed: str) -> str:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()[:6]
    return f"t-{sanitize_id(seed)[:32]}-{digest}"


def count_paragraphs(text: str) -> int:
    parts = [part.strip() for part in re.split(r"\n\s*\n", str(text or "").strip()) if part.strip()]
    return len(parts) if parts else (1 if str(text or "").strip() else 0)


def truncate_text(value: Any, max_length: int = 200) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 3)].rstrip() + "..."


def mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def average_score_blocks(blocks: List[Dict[str, Any]], fields: List[str]) -> Dict[str, float]:
    if not blocks:
        return {field: 0.0 for field in fields}
    return {
        field: round(mean([float(block.get(field, 0.0) or 0.0) for block in blocks]), 2)
        for field in fields
    }


def normalize_loop_preferences(config: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    payload = config if isinstance(config, dict) else {}
    rounds = int(payload.get("rounds", 1) or 1)
    delay_ms = int(payload.get("delayMs", 0) or 0)
    return {
        "rounds": max(1, min(12, rounds)),
        "delayMs": max(0, min(10000, delay_ms)),
    }


def response_meta_from_openai(runtime: LoopRuntime, response: Optional[Dict[str, Any]], call_meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not response:
        return None
    return {
        "status": str(response.get("status", "completed")),
        "usageDelta": runtime.get_response_usage_delta(response, call_meta.get("model", "")) or {},
        "webSearchQueries": normalize_string_array_preserve_items(runtime.get_response_web_search_queries(response)),
        "webSearchSources": normalize_string_array_preserve_items(runtime.get_response_web_search_sources(response)),
        "urlCitations": normalize_string_array_preserve_items(runtime.get_response_url_citations(response)),
        "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", 0) or 0),
        "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", 0) or 0),
        "maxOutputTokenAttempts": [int(value or 0) for value in call_meta.get("attempts", []) if int(value or 0) > 0],
        "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
    }


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


def quality_judge_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["scores", "verdict", "strongestStrength", "strongestWeakness", "rationale"],
        "properties": {
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": QUALITY_SCORE_FIELDS,
                "properties": {field: {"type": "integer"} for field in QUALITY_SCORE_FIELDS},
            },
            "verdict": {"type": "string"},
            "strongestStrength": {"type": "string"},
            "strongestWeakness": {"type": "string"},
            "rationale": {"type": "string"},
        },
    }


def control_judge_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["scores", "verdict", "strongestControlStrength", "strongestControlWeakness", "rationale"],
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


def validate_suite_manifest(payload: Dict[str, Any], source: Path) -> Dict[str, Any]:
    suite_id = sanitize_id(str(payload.get("suiteId", "")).strip())
    if not suite_id:
        raise EvalError(f"Missing suiteId in {source.name}")
    title = str(payload.get("title", "")).strip()
    if not title:
        raise EvalError(f"Suite {suite_id} is missing title.")
    description = str(payload.get("description", "")).strip()
    judge_rubric = payload.get("judgeRubric") if isinstance(payload.get("judgeRubric"), (dict, list, str)) else {}
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise EvalError(f"Suite {suite_id} must include at least one case.")
    cases: List[Dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict):
            raise EvalError(f"Suite {suite_id} case #{index} must be an object.")
        case_id = sanitize_id(str(raw_case.get("caseId", "")).strip())
        if not case_id:
            raise EvalError(f"Suite {suite_id} has a case without caseId.")
        if case_id in seen_case_ids:
            raise EvalError(f"Suite {suite_id} contains duplicate caseId {case_id}.")
        seen_case_ids.add(case_id)
        title_value = str(raw_case.get("title", "")).strip()
        objective = str(raw_case.get("objective", "")).strip()
        if not title_value or not objective:
            raise EvalError(f"Suite {suite_id} case {case_id} is missing title or objective.")
        constraints = [str(item).strip() for item in raw_case.get("constraints", []) if str(item).strip()] if isinstance(raw_case.get("constraints"), list) else []
        checks = raw_case.get("checks") if isinstance(raw_case.get("checks"), dict) else {}
        cases.append(
            {
                "caseId": case_id,
                "title": title_value,
                "objective": objective,
                "constraints": constraints,
                "sessionContext": str(raw_case.get("sessionContext", "")).strip(),
                "checks": deepcopy(checks),
                "gold": deepcopy(raw_case.get("gold")) if isinstance(raw_case.get("gold"), (dict, list, str)) else {},
            }
        )
    return {
        "suiteId": suite_id,
        "title": title,
        "description": description,
        "judgeRubric": deepcopy(judge_rubric),
        "cases": cases,
    }


def validate_arm_manifest(payload: Dict[str, Any], source: Path) -> Dict[str, Any]:
    arm_id = sanitize_id(str(payload.get("armId", "")).strip())
    if not arm_id:
        raise EvalError(f"Missing armId in {source.name}")
    title = str(payload.get("title", "")).strip()
    if not title:
        raise EvalError(f"Arm {arm_id} is missing title.")
    arm_type = str(payload.get("type", "")).strip().lower()
    if arm_type not in {"direct", "steered"}:
        raise EvalError(f"Arm {arm_id} must use type 'direct' or 'steered'.")

    runtime_payload = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
    model = normalize_model_id(str(runtime_payload.get("model", "")).strip(), "gpt-5-mini")
    summarizer_model = normalize_model_id(str(runtime_payload.get("summarizerModel", "")).strip(), model)
    reasoning_effort = str(runtime_payload.get("reasoningEffort", "low")).strip().lower()
    if reasoning_effort not in {"none", "low", "medium", "high", "xhigh"}:
        reasoning_effort = "low"
    execution_mode = str(runtime_payload.get("executionMode", "live")).strip().lower()
    if execution_mode not in {"live", "mock"}:
        execution_mode = "live"
    budget = normalize_budget_config(runtime_payload.get("budget") if isinstance(runtime_payload.get("budget"), dict) else {})
    research = normalize_research_config(runtime_payload.get("research") if isinstance(runtime_payload.get("research"), dict) else {})
    vetting = normalize_vetting_config(runtime_payload.get("vetting") if isinstance(runtime_payload.get("vetting"), dict) else {})
    preferred_loop = normalize_loop_preferences(runtime_payload.get("preferredLoop") if isinstance(runtime_payload.get("preferredLoop"), dict) else {})
    workers = payload.get("workers") if isinstance(payload.get("workers"), list) else []
    normalized_workers = task_workers({"runtime": {"model": model}, "workers": workers}) if workers else []
    if arm_type == "steered" and not normalized_workers:
        raise EvalError(f"Steered arm {arm_id} must include at least one worker.")
    return {
        "armId": arm_id,
        "title": title,
        "description": str(payload.get("description", "")).strip(),
        "type": arm_type,
        "runtime": {
            "executionMode": execution_mode,
            "model": model,
            "summarizerModel": summarizer_model,
            "reasoningEffort": reasoning_effort,
            "budget": budget,
            "research": research,
            "vetting": vetting,
            "preferredLoop": preferred_loop,
            "requireLive": coerce_bool(runtime_payload.get("requireLive"), execution_mode == "live"),
            "allowMockFallback": coerce_bool(runtime_payload.get("allowMockFallback"), execution_mode == "mock"),
        },
        "workers": normalized_workers,
    }


def variant_id_for_arm(arm: Dict[str, Any], loop_rounds: int) -> str:
    if arm["type"] == "direct":
        return arm["armId"]
    return f"{arm['armId']}--loops-{int(loop_rounds)}"


def build_eval_task(case: Dict[str, Any], arm: Dict[str, Any], loop_rounds: int, seed: str) -> Dict[str, Any]:
    task_id = build_task_id(seed)
    runtime_config = arm["runtime"]
    return {
        "taskId": task_id,
        "objective": case["objective"],
        "constraints": list(case.get("constraints", [])),
        "sessionContext": str(case.get("sessionContext", "")).strip(),
        "createdAt": utc_now(),
        "runtime": {
            "executionMode": runtime_config["executionMode"],
            "model": runtime_config["model"],
            "reasoningEffort": runtime_config["reasoningEffort"],
            "budget": deepcopy(runtime_config["budget"]),
            "research": deepcopy(runtime_config["research"]),
            "vetting": deepcopy(runtime_config["vetting"]),
            "pricingSource": None,
            "pricingCheckedAt": None,
        },
        "summarizer": {
            "id": "summarizer",
            "label": "Summarizer",
            "model": runtime_config["summarizerModel"],
        },
        "syncPolicy": {
            "mode": "checkpoint",
            "shareOnBlocker": True,
            "shareEverySteps": 3,
        },
        "preferredLoop": {
            "rounds": int(loop_rounds),
            "delayMs": int(runtime_config["preferredLoop"]["delayMs"]),
        },
        "workers": deepcopy(arm["workers"]),
    }


def initialize_steered_workspace(runtime: LoopRuntime, task: Dict[str, Any]) -> None:
    runtime.ensure_data_paths()
    state = default_state()
    state["activeTask"] = task
    state["draft"] = {}
    state["workers"] = {worker["id"]: None for worker in task_workers(task)}
    state["summary"] = None
    state["memoryVersion"] = 1
    state["usage"] = default_usage_state()
    state["loop"] = default_loop_state()
    runtime.write_state(state)
    write_json(runtime.tasks_path / f"{task['taskId']}.json", task)


def build_mock_direct_answer(case: Dict[str, Any]) -> Dict[str, Any]:
    title = case.get("title", "the case")
    objective = case.get("objective", "")
    if "billing" in objective.lower() or "holiday" in objective.lower():
        answer = (
            "My recommendation is no-go on a full billing replatform right before peak traffic. The safer path is a staged dual-run or a narrower cutover that proves the queue path without putting revenue collection at risk.\n\n"
            "The next step is to keep the current cron system as the source of truth for peak season and run the new event path in shadow mode with explicit rollback gates."
        )
        stance = "Hold the full cutover and de-risk it through a staged path."
    else:
        answer = (
            "My recommendation is a conditional ship, not a blind launch. Move forward only with a tightly bounded rollout that keeps sensitive outputs behind review and makes privacy or contract-sensitive failures visible fast.\n\n"
            "The next step is to launch to a small internal or design-partner cohort with manual review, clear escalation rules, and a narrow scope."
        )
        stance = "Ship only through a constrained rollout with strong guardrails."
    return {
        "answer": answer,
        "stance": stance,
        "confidenceNote": f"Mock direct answer for {title}; useful for eval plumbing, not factual confidence.",
    }


def run_direct_answer(
    runtime: LoopRuntime,
    auth_assignment: Optional[Dict[str, Any]],
    case: Dict[str, Any],
    arm: Dict[str, Any],
) -> Dict[str, Any]:
    api_key = str(auth_assignment.get("apiKey")) if isinstance(auth_assignment, dict) else None
    auth_meta = auth_assignment_meta(auth_assignment)
    runtime_config = arm["runtime"]
    model = runtime_config["model"]
    reasoning_effort = runtime_config["reasoningEffort"]
    requested_max_output = int(runtime_config["budget"]["maxOutputTokens"])
    instructions = (
        "Answer the user directly as one assistant.\n"
        "Give a decisive but conditional recommendation.\n"
        "Do not narrate hidden process.\n"
        "Absorb tradeoffs into the recommendation itself.\n"
        "Keep the answer concise and actionable.\n"
        "Return JSON only that matches the schema."
    )
    input_text = (
        f"Objective:\n{case['objective']}\n\n"
        f"Constraints:\n{json.dumps(case.get('constraints', []), ensure_ascii=False, indent=2)}\n\n"
        f"Session context:\n{case.get('sessionContext', '') or 'none'}\n"
    )
    if runtime_config["executionMode"] == "live" and api_key:
        try:
            result = runtime.invoke_openai_json(
                api_key=api_key,
                model=model,
                reasoning_effort=reasoning_effort,
                instructions=instructions,
                input_text=input_text,
                schema_name="eval_direct_answer",
                schema=direct_answer_schema(),
                max_output_tokens=requested_max_output,
                target_kind="generic",
            )
            usage = runtime.get_response_usage_delta(result.response, model) or default_usage_state()
            return {
                "mode": "live",
                "model": model,
                "answer": result.parsed,
                "usage": normalize_usage_state(usage),
                "responseId": result.response_id,
                "rawOutputText": result.output_text,
                "responseMeta": {
                    "status": str(result.response.get("status", "completed")),
                    "usageDelta": runtime.get_response_usage_delta(result.response, model) or {},
                    "webSearchQueries": result.web_search_queries,
                    "webSearchSources": result.web_search_sources,
                    "urlCitations": result.url_citations,
                    "requestedMaxOutputTokens": result.requested_max_output_tokens,
                    "effectiveMaxOutputTokens": result.effective_max_output_tokens,
                    "maxOutputTokenAttempts": result.attempts,
                    "recoveredFromIncomplete": result.recovered_from_incomplete,
                },
                "authMeta": auth_meta,
            }
        except RuntimeErrorWithCode:
            if not runtime_config["allowMockFallback"]:
                raise
    return {
        "mode": "mock",
        "model": model,
        "answer": build_mock_direct_answer(case),
        "usage": default_usage_state(),
        "responseId": None,
        "rawOutputText": None,
        "responseMeta": None,
        "authMeta": auth_meta,
    }


def run_steered_answer(
    project_root: Path,
    auth_path: Path,
    case: Dict[str, Any],
    arm: Dict[str, Any],
    loop_rounds: int,
    replicate_dir: Path,
    seed: str,
) -> Dict[str, Any]:
    workspace_root = replicate_dir / "workspace"
    runtime = LoopRuntime(workspace_root, auth_path=auth_path)
    task = build_eval_task(case, arm, loop_rounds, seed)
    initialize_steered_workspace(runtime, task)
    worker_ids = [worker["id"] for worker in task_workers(task)]
    for _round in range(1, max(1, loop_rounds) + 1):
        runtime.run_target("commander", task["taskId"])
        for worker_id in worker_ids:
            runtime.run_target(worker_id, task["taskId"])
        runtime.run_target("summarizer", task["taskId"])
    state = runtime.read_state()
    summary = state.get("summary")
    if not isinstance(summary, dict):
        raise EvalError("Steered run finished without a summary.")
    usage = normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
    outputs_root = workspace_root / "data"
    return {
        "mode": "live" if str(summary.get("frontAnswer", {}).get("confidenceNote", "")).strip() and usage.get("totalTokens", 0) else "mock",
        "taskId": task["taskId"],
        "summary": summary,
        "usage": usage,
        "state": state,
        "workspaceRoot": workspace_root,
        "outputsRoot": outputs_root,
    }


def quality_judge_live(
    runtime: LoopRuntime,
    api_key: str,
    judge_model: str,
    case: Dict[str, Any],
    judge_rubric: Any,
    public_answer: str,
) -> Dict[str, Any]:
    instructions = (
        "You are grading one candidate assistant answer to a benchmark prompt.\n"
        "Score from 1 to 10 on each quality dimension.\n"
        "Reward decisiveness, tradeoff handling, objection absorption, actionability, and a clean single assistant voice.\n"
        "Use the hidden rubric and gold notes as guidance, but do not require exact wording.\n"
        "Return JSON only that matches the schema."
    )
    input_text = (
        f"Objective:\n{case['objective']}\n\n"
        f"Constraints:\n{json.dumps(case.get('constraints', []), ensure_ascii=False, indent=2)}\n\n"
        f"Hidden rubric:\n{json.dumps(judge_rubric, ensure_ascii=False, indent=2)}\n\n"
        f"Hidden gold guidance:\n{json.dumps(case.get('gold', {}), ensure_ascii=False, indent=2)}\n\n"
        f"Candidate answer:\n{public_answer}\n"
    )
    result = runtime.invoke_openai_json(
        api_key=api_key,
        model=judge_model,
        reasoning_effort="high",
        instructions=instructions,
        input_text=input_text,
        schema_name="eval_quality_judge",
        schema=quality_judge_schema(),
        max_output_tokens=1400,
        target_kind="generic",
    )
    parsed = result.parsed
    scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
    return {
        "mode": "live",
        "scores": {field: int(scores.get(field, 0) or 0) for field in QUALITY_SCORE_FIELDS},
        "verdict": str(parsed.get("verdict", "")).strip(),
        "strongestStrength": str(parsed.get("strongestStrength", "")).strip(),
        "strongestWeakness": str(parsed.get("strongestWeakness", "")).strip(),
        "rationale": str(parsed.get("rationale", "")).strip(),
        "responseId": result.response_id,
    }


def heuristic_quality_judge(public_answer: str) -> Dict[str, Any]:
    text = str(public_answer or "").strip()
    lowered = text.lower()
    paragraphs = count_paragraphs(text)
    has_recommendation = any(token in lowered for token in ["recommend", "no-go", "go ", "ship", "hold", "should"])
    has_tradeoff = any(token in lowered for token in ["tradeoff", "but", "however", "while", "risk"])
    has_conditions = any(token in lowered for token in ["only if", "unless", "with guardrails", "conditional", "only through"])
    has_next_step = any(token in lowered for token in ["next step", "first", "start", "launch", "rollout", "shadow mode"])
    mentions_hidden_process = any(token in lowered for token in ["lane", "worker", "summarizer", "adversarial"])

    scores = {
        "decisiveness": 8 if has_recommendation else 5,
        "tradeoffHandling": 8 if has_tradeoff else 5,
        "objectionAbsorption": 8 if has_conditions else 5,
        "actionability": 8 if has_next_step else 5,
        "singleVoice": 9 if not mentions_hidden_process else 4,
        "overallQuality": 0,
    }
    penalty = 1 if paragraphs > 3 else 0
    scores["overallQuality"] = max(1, round(mean([value for key, value in scores.items() if key != "overallQuality"])) - penalty)
    return {
        "mode": "mock",
        "scores": scores,
        "verdict": "Heuristic quality estimate.",
        "strongestStrength": "Clear recommendation" if has_recommendation else "Readable structure",
        "strongestWeakness": "Needs a more operational next step" if not has_next_step else "Needs stronger objection absorption",
        "rationale": "Mock judge used heuristic signals because no live judge model was available.",
        "responseId": None,
    }


def control_judge_live(
    runtime: LoopRuntime,
    api_key: str,
    judge_model: str,
    case: Dict[str, Any],
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    front_answer = summary.get("frontAnswer", {}) if isinstance(summary.get("frontAnswer"), dict) else {}
    opinion = summary.get("summarizerOpinion", {}) if isinstance(summary.get("summarizerOpinion"), dict) else {}
    control_audit = summary.get("controlAudit", {}) if isinstance(summary.get("controlAudit"), dict) else {}
    instructions = (
        "You are grading whether a lead assistant thread stayed in control of adversarial pressure.\n"
        "Reward answers where the lead direction is clear, accepted objections are selective, rejected pressure is actually rejected, and the self-check is meaningful.\n"
        "Penalize funnel-like behavior where internal pressure is merely forwarded or averaged into the final answer.\n"
        "Return JSON only that matches the schema."
    )
    input_text = (
        f"Objective:\n{case['objective']}\n\n"
        f"Constraints:\n{json.dumps(case.get('constraints', []), ensure_ascii=False, indent=2)}\n\n"
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
        schema_name="eval_control_judge",
        schema=control_judge_schema(),
        max_output_tokens=1400,
        target_kind="generic",
    )
    parsed = result.parsed
    scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
    return {
        "mode": "live",
        "scores": {field: int(scores.get(field, 0) or 0) for field in CONTROL_SCORE_FIELDS},
        "verdict": str(parsed.get("verdict", "")).strip(),
        "strongestControlStrength": str(parsed.get("strongestControlStrength", "")).strip(),
        "strongestControlWeakness": str(parsed.get("strongestControlWeakness", "")).strip(),
        "rationale": str(parsed.get("rationale", "")).strip(),
        "responseId": result.response_id,
    }


def heuristic_control_judge(summary: Dict[str, Any]) -> Dict[str, Any]:
    front_answer = summary.get("frontAnswer", {}) if isinstance(summary.get("frontAnswer"), dict) else {}
    opinion = summary.get("summarizerOpinion", {}) if isinstance(summary.get("summarizerOpinion"), dict) else {}
    control_audit = summary.get("controlAudit", {}) if isinstance(summary.get("controlAudit"), dict) else {}
    answer_text = str(front_answer.get("answer", "")).lower()
    mentions_process = any(token in answer_text for token in ["lane", "worker", "summarizer", "adversarial"])
    accepted = control_audit.get("acceptedAdversarialPoints", []) if isinstance(control_audit.get("acceptedAdversarialPoints"), list) else []
    rejected = control_audit.get("rejectedAdversarialPoints", []) if isinstance(control_audit.get("rejectedAdversarialPoints"), list) else []
    held_out = control_audit.get("heldOutConcerns", []) if isinstance(control_audit.get("heldOutConcerns"), list) else []

    scores = {
        "leadControl": 9 if front_answer.get("leadDirection") and control_audit.get("leadDraft") else 5,
        "adversarialDiscipline": 9 if accepted and rejected else 5,
        "selfCheckQuality": 8 if control_audit.get("selfCheck") else 4,
        "nonFunnelIntegration": 9 if not mentions_process and opinion.get("integrationMode") else 4,
        "overallControl": 0,
    }
    if held_out:
        scores["adversarialDiscipline"] = min(10, scores["adversarialDiscipline"] + 1)
    scores["overallControl"] = round(mean([value for key, value in scores.items() if key != "overallControl"]))
    return {
        "mode": "mock",
        "scores": scores,
        "verdict": "Heuristic control estimate.",
        "strongestControlStrength": "Lead-thread structure is explicit." if scores["leadControl"] >= 8 else "Some control audit fields are present.",
        "strongestControlWeakness": "Public answer still leaks process." if mentions_process else "Control is only structurally inferred in mock mode.",
        "rationale": "Mock control judge used structural signals because no live judge model was available.",
        "responseId": None,
    }


def run_quality_judge(
    judge_runtime: LoopRuntime,
    api_key: Optional[str],
    judge_model: str,
    case: Dict[str, Any],
    judge_rubric: Any,
    public_answer: str,
) -> Dict[str, Any]:
    if api_key:
        try:
            return quality_judge_live(judge_runtime, api_key, judge_model, case, judge_rubric, public_answer)
        except RuntimeErrorWithCode:
            pass
    return heuristic_quality_judge(public_answer)


def run_control_judge(
    judge_runtime: LoopRuntime,
    api_key: Optional[str],
    judge_model: str,
    case: Dict[str, Any],
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    if api_key:
        try:
            return control_judge_live(judge_runtime, api_key, judge_model, case, summary)
        except RuntimeErrorWithCode:
            pass
    return heuristic_control_judge(summary)


def extract_public_answer(arm: Dict[str, Any], result: Dict[str, Any]) -> str:
    if arm["type"] == "direct":
        return str(result.get("answer", {}).get("answer", "")).strip()
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    front_answer = summary.get("frontAnswer", {}) if isinstance(summary.get("frontAnswer"), dict) else {}
    return str(front_answer.get("answer", "")).strip()


def mode_summary_for_steered(workspace_root: Path, task_id: str, loop_rounds: int) -> Dict[str, Any]:
    output_dir = workspace_root / "data" / "outputs"
    modes: Dict[str, str] = {}
    for artifact_file in sorted(output_dir.glob("*.json")):
        name = artifact_file.name
        payload = read_json(artifact_file)
        mode = str(payload.get("mode", "")).strip().lower() or "unknown"
        if re.match(rf"^{re.escape(task_id)}_[A-Z]_step\d+_output\.json$", name):
            worker_id = name.split("_")[1]
            modes[worker_id] = mode
        elif name == f"{task_id}_summary_round{int(loop_rounds):03d}_output.json":
            modes["summarizer"] = mode
    return {
        "workerModes": {key: modes[key] for key in sorted(key for key in modes.keys() if key != "summarizer")},
        "summaryMode": modes.get("summarizer", "unknown"),
    }


def deterministic_checks(case: Dict[str, Any], arm: Dict[str, Any], result: Dict[str, Any], public_answer: str) -> Dict[str, Any]:
    checks = case.get("checks", {}) if isinstance(case.get("checks"), dict) else {}
    usage = normalize_usage_state(result.get("usage") if isinstance(result.get("usage"), dict) else {})
    runtime_budget = arm["runtime"]["budget"]
    required_live = bool(checks.get("requireLive")) or bool(arm["runtime"]["requireLive"])
    required_fields = ["answer", "stance", "confidenceNote"] if arm["type"] == "direct" else ["frontAnswer", "summarizerOpinion", "controlAudit"]
    result_fields_ok = True
    missing_fields: List[str] = []
    if arm["type"] == "direct":
        answer = result.get("answer")
        if not isinstance(answer, dict):
            result_fields_ok = False
            missing_fields = required_fields
        else:
            missing_fields = [field for field in required_fields if not str(answer.get(field, "")).strip()]
            result_fields_ok = not missing_fields
    else:
        summary = result.get("summary")
        if not isinstance(summary, dict):
            result_fields_ok = False
            missing_fields = required_fields
        else:
            for field in required_fields:
                if not isinstance(summary.get(field), dict):
                    missing_fields.append(field)
            result_fields_ok = not missing_fields

    mode_state = result.get("modeState") if isinstance(result.get("modeState"), dict) else {}
    mode_values = []
    if arm["type"] == "direct":
        mode_values = [str(result.get("mode", "unknown")).strip().lower() or "unknown"]
    else:
        mode_values = list((mode_state.get("workerModes") or {}).values()) + [str(mode_state.get("summaryMode", "unknown"))]

    live_ok = all(mode == "live" for mode in mode_values if mode) if mode_values else False
    mock_fallback_ok = bool(arm["runtime"]["allowMockFallback"]) or all(mode == "live" for mode in mode_values if mode)
    max_paragraphs = int(checks.get("maxParagraphs", 0) or 0)
    paragraph_count = count_paragraphs(public_answer)
    required_phrases = [str(item).strip() for item in checks.get("requiredPhrases", []) if str(item).strip()] if isinstance(checks.get("requiredPhrases"), list) else []
    forbidden_phrases = [str(item).strip() for item in checks.get("forbiddenPhrases", []) if str(item).strip()] if isinstance(checks.get("forbiddenPhrases"), list) else []
    lowered_answer = public_answer.lower()
    missing_phrases = [phrase for phrase in required_phrases if phrase.lower() not in lowered_answer]
    found_forbidden = [phrase for phrase in forbidden_phrases if phrase.lower() in lowered_answer]
    token_ok = int(runtime_budget["maxTotalTokens"]) <= 0 or int(usage["totalTokens"]) <= int(runtime_budget["maxTotalTokens"])
    cost_ok = float(runtime_budget["maxCostUsd"]) <= 0 or float(usage["estimatedCostUsd"]) <= float(runtime_budget["maxCostUsd"])
    checks_out = {
        "requiredArtifactFields": {
            "passed": result_fields_ok,
            "detail": "All required artifact fields were present." if result_fields_ok else f"Missing fields: {', '.join(missing_fields)}.",
        },
        "budgetCompliance": {
            "passed": token_ok and cost_ok,
            "detail": f"tokens {int(usage['totalTokens'])}/{int(runtime_budget['maxTotalTokens'])} | cost ${float(usage['estimatedCostUsd']):0.4f}/${float(runtime_budget['maxCostUsd']):0.4f}",
        },
        "requiredPhrases": {
            "passed": not missing_phrases,
            "detail": "All required phrases were present." if not missing_phrases else f"Missing required phrases: {', '.join(missing_phrases)}.",
        },
        "forbiddenPhrases": {
            "passed": not found_forbidden,
            "detail": "No forbidden phrases were found." if not found_forbidden else f"Found forbidden phrases: {', '.join(found_forbidden)}.",
        },
        "maxParagraphs": {
            "passed": max_paragraphs <= 0 or paragraph_count <= max_paragraphs,
            "detail": f"{paragraph_count} paragraph(s) against cap {max_paragraphs or 'none'}.",
        },
    }
    if required_live:
        checks_out["requireLive"] = {
            "passed": live_ok,
            "detail": "Run stayed live throughout." if live_ok else f"Non-live modes observed: {', '.join(mode_values) or 'none'}",
        }
    checks_out["noMockFallback"] = {
        "passed": mock_fallback_ok,
        "detail": "Mock fallback policy respected." if mock_fallback_ok else f"Mock fallback occurred in modes: {', '.join(mode_values)}",
    }
    passed_count = sum(1 for entry in checks_out.values() if entry["passed"])
    total_count = len(checks_out)
    return {
        "passed": passed_count == total_count,
        "passedCount": passed_count,
        "totalCount": total_count,
        "checks": checks_out,
    }


def artifact_meta_from_payload(path: Path, relative_path: Path, payload: Dict[str, Any], run_id: str, case_id: str, variant_id: str, replicate: int) -> Dict[str, Any]:
    name = path.name
    kind = "artifact"
    target = str(payload.get("target", "") or payload.get("artifactType", "") or "artifact")
    step = payload.get("step")
    round_number = payload.get("round")
    if name == "score.json":
        kind = "score"
        target = "score"
    elif name == "result.json":
        kind = "result"
        target = "result"
    elif re.match(r".+_[A-Z]_step\d+_output\.json$", name):
        kind = "worker_output"
        target = payload.get("target") or name.split("_")[1]
    elif re.match(r".+_summary_round\d+_output\.json$", name):
        kind = "summary_output"
        target = "summarizer"
    elif re.match(r".+_[A-Z]_step\d+\.json$", name):
        kind = "worker_step"
        target = name.split("_")[1]
    elif re.match(r".+_summary_round\d+\.json$", name):
        kind = "summary_round"
        target = "summarizer"
    elif name == "direct_answer_output.json":
        kind = "direct_output"
        target = "direct"
    artifact_id = sanitize_id(f"{case_id}-{variant_id}-r{replicate}-{kind}-{name}")
    summary = {
        "taskId": payload.get("taskId"),
        "target": target,
        "mode": payload.get("mode"),
        "model": payload.get("model") or payload.get("modelUsed"),
        "step": int(step or 0) if step is not None else None,
        "round": int(round_number or 0) if round_number is not None else None,
        "responseId": payload.get("responseId"),
        "requestedMaxOutputTokens": ((payload.get("responseMeta") or {}).get("requestedMaxOutputTokens") if isinstance(payload.get("responseMeta"), dict) else None),
        "effectiveMaxOutputTokens": ((payload.get("responseMeta") or {}).get("effectiveMaxOutputTokens") if isinstance(payload.get("responseMeta"), dict) else None),
        "maxOutputTokenAttempts": ((payload.get("responseMeta") or {}).get("maxOutputTokenAttempts") if isinstance(payload.get("responseMeta"), dict) else []),
        "recoveredFromIncomplete": ((payload.get("responseMeta") or {}).get("recoveredFromIncomplete") if isinstance(payload.get("responseMeta"), dict) else False),
        "rawOutputAvailable": bool(str(payload.get("rawOutputText", "") or "").strip()),
    }
    return {
        "artifactId": artifact_id,
        "name": name,
        "kind": kind,
        "storage": "eval",
        "relativePath": str(relative_path).replace("\\", "/"),
        "modifiedAt": utc_now(),
        "size": path.stat().st_size,
        "caseId": case_id,
        "variantId": variant_id,
        "replicate": int(replicate),
        "runId": run_id,
        "summary": summary,
    }


def register_artifact(run: Dict[str, Any], entry: Dict[str, Any]) -> None:
    artifact_index = run.setdefault("artifactIndex", {})
    artifact_index[entry["artifactId"]] = entry


def collect_replicate_artifacts(run: Dict[str, Any], run_dir: Path, case_id: str, variant_id: str, replicate: int, replicate_dir: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for path in sorted(replicate_dir.rglob("*.json")):
        if path.name == "run.json":
            continue
        relative_text = str(path.relative_to(replicate_dir)).replace("\\", "/")
        is_review_surface = (
            path.name in {"score.json", "result.json", "direct_answer_output.json"}
            or relative_text.startswith("workspace/data/outputs/")
            or relative_text.startswith("workspace/data/checkpoints/")
        )
        if not is_review_surface:
            continue
        try:
            payload = read_json(path)
        except EvalError:
            continue
        relative_path = path.relative_to(run_dir)
        entry = artifact_meta_from_payload(path, relative_path, payload, str(run["runId"]), case_id, variant_id, replicate)
        register_artifact(run, entry)
        entries.append(entry)
    entries.sort(key=lambda item: (str(item.get("kind", "")), str(item.get("name", ""))))
    return entries


def aggregate_variant(variant: Dict[str, Any]) -> Dict[str, Any]:
    replicates = variant.get("replicates", []) if isinstance(variant.get("replicates"), list) else []
    completed = [entry for entry in replicates if str(entry.get("status", "")) == "completed"]
    quality_blocks = [entry["quality"]["scores"] for entry in completed if isinstance(entry.get("quality"), dict) and isinstance(entry["quality"].get("scores"), dict)]
    control_blocks = [entry["control"]["scores"] for entry in completed if isinstance(entry.get("control"), dict) and isinstance(entry["control"].get("scores"), dict)]
    deterministic_passes = sum(1 for entry in completed if entry.get("deterministic", {}).get("passed"))
    total_tokens = sum(int((entry.get("usage") or {}).get("totalTokens", 0) or 0) for entry in completed)
    total_cost = sum(float((entry.get("usage") or {}).get("estimatedCostUsd", 0.0) or 0.0) for entry in completed)
    return {
        "replicateCount": len(replicates),
        "completedReplicates": len(completed),
        "errorCount": sum(1 for entry in replicates if str(entry.get("status", "")) == "error"),
        "deterministicPassRate": round((deterministic_passes / len(completed)) if completed else 0.0, 2),
        "quality": average_score_blocks(quality_blocks, QUALITY_SCORE_FIELDS),
        "control": average_score_blocks(control_blocks, CONTROL_SCORE_FIELDS),
        "totalTokens": total_tokens,
        "estimatedCostUsd": round(total_cost, 6),
    }


def aggregate_run(run: Dict[str, Any]) -> Dict[str, Any]:
    variant_summaries: List[Dict[str, Any]] = []
    for case_entry in run.get("cases", []):
        if not isinstance(case_entry, dict):
            continue
        for variant in case_entry.get("variants", []):
            if not isinstance(variant, dict):
                continue
            variant_summary = deepcopy(variant.get("aggregate") if isinstance(variant.get("aggregate"), dict) else {})
            variant_summaries.append(
                {
                    "caseId": case_entry.get("caseId"),
                    "caseTitle": case_entry.get("title"),
                    "variantId": variant.get("variantId"),
                    "armId": variant.get("armId"),
                    "title": variant.get("title"),
                    "type": variant.get("type"),
                    "loopRounds": variant.get("loopRounds"),
                    **variant_summary,
                }
            )
    total_tokens = sum(int(entry.get("totalTokens", 0) or 0) for entry in variant_summaries)
    total_cost = sum(float(entry.get("estimatedCostUsd", 0.0) or 0.0) for entry in variant_summaries)
    quality_blocks = [entry.get("quality", {}) for entry in variant_summaries if isinstance(entry.get("quality"), dict)]
    control_blocks = [entry.get("control", {}) for entry in variant_summaries if isinstance(entry.get("control"), dict) and any(entry.get("control", {}).values())]
    return {
        "caseCount": len(run.get("cases", [])),
        "variantCount": len(variant_summaries),
        "errorCount": sum(int(entry.get("errorCount", 0) or 0) for entry in variant_summaries),
        "totalTokens": total_tokens,
        "estimatedCostUsd": round(total_cost, 6),
        "averageQuality": average_score_blocks(quality_blocks, QUALITY_SCORE_FIELDS),
        "averageControl": average_score_blocks(control_blocks, CONTROL_SCORE_FIELDS),
        "variants": variant_summaries,
    }


def persist_run(run_path: Path, run: Dict[str, Any]) -> None:
    run["updatedAt"] = utc_now()
    write_json(run_path, run)


def find_case_entry(run: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    for case_entry in run.setdefault("cases", []):
        if case_entry.get("caseId") == case_id:
            return case_entry
    case_entry = {"caseId": case_id, "title": "", "variants": []}
    run["cases"].append(case_entry)
    return case_entry


def find_variant_entry(case_entry: Dict[str, Any], variant_id: str) -> Dict[str, Any]:
    for variant in case_entry.setdefault("variants", []):
        if variant.get("variantId") == variant_id:
            return variant
    variant = {"variantId": variant_id, "replicates": []}
    case_entry["variants"].append(variant)
    return variant


def execute_replicate(
    run: Dict[str, Any],
    run_dir: Path,
    case: Dict[str, Any],
    arm: Dict[str, Any],
    loop_rounds: int,
    replicate_index: int,
    judge_model: str,
    auth_path: Path,
) -> Dict[str, Any]:
    variant_id = variant_id_for_arm(arm, loop_rounds)
    replicate_dir = run_dir / "cases" / case["caseId"] / variant_id / f"replicate-{replicate_index:03d}"
    replicate_dir.mkdir(parents=True, exist_ok=True)
    seed = f"{run['runId']}:{case['caseId']}:{variant_id}:{replicate_index}"
    judge_runtime = LoopRuntime(replicate_dir / "_judge_runtime", auth_path=auth_path)
    judge_auth_assignment = judge_runtime.get_api_key_assignment("judge", salt=seed + ":judge")
    api_key = str(judge_auth_assignment.get("apiKey")) if judge_auth_assignment else None
    result: Dict[str, Any]
    if arm["type"] == "direct":
        runtime = LoopRuntime(replicate_dir / "_direct_runtime", auth_path=auth_path)
        direct = run_direct_answer(runtime, runtime.get_api_key_assignment("direct", salt=seed + ":direct"), case, arm)
        output_payload = {
            "taskId": None,
            "artifactType": "eval_direct_output",
            "target": "direct",
            "label": arm["title"],
            "mode": direct["mode"],
            "model": direct["model"],
            "capturedAt": utc_now(),
            "responseId": direct["responseId"],
            "responseMeta": direct["responseMeta"],
            "authMeta": direct.get("authMeta"),
            "rawOutputText": direct["rawOutputText"],
            "output": direct["answer"],
        }
        write_json(replicate_dir / "direct_answer_output.json", output_payload)
        result = {
            "mode": direct["mode"],
            "answer": direct["answer"],
            "usage": normalize_usage_state(direct["usage"]),
            "responseId": direct["responseId"],
            "responseMeta": direct["responseMeta"],
            "modeState": {"directMode": direct["mode"]},
        }
    else:
        steered = run_steered_answer(Path("."), auth_path, case, arm, loop_rounds, replicate_dir, seed)
        mode_state = mode_summary_for_steered(steered["workspaceRoot"], steered["taskId"], loop_rounds)
        result = {
            "mode": mode_state["summaryMode"],
            "taskId": steered["taskId"],
            "summary": steered["summary"],
            "usage": normalize_usage_state(steered["usage"]),
            "responseId": None,
            "responseMeta": None,
            "modeState": mode_state,
        }

    public_answer = extract_public_answer(arm, result)
    quality = run_quality_judge(judge_runtime, api_key or None, judge_model, case, run.get("suite", {}).get("judgeRubric", {}), public_answer)
    control = run_control_judge(judge_runtime, api_key or None, judge_model, case, result["summary"]) if arm["type"] == "steered" else None
    deterministic = deterministic_checks(case, arm, result, public_answer)
    score_payload: Dict[str, Any] = {
        "runId": run["runId"],
        "caseId": case["caseId"],
        "armId": arm["armId"],
        "variantId": variant_id,
        "replicate": replicate_index,
        "deterministic": deterministic,
        "quality": quality,
        "control": control,
        "usage": result["usage"],
        "generatedAt": utc_now(),
    }
    write_json(replicate_dir / "score.json", score_payload)

    result_payload: Dict[str, Any] = {
        "runId": run["runId"],
        "caseId": case["caseId"],
        "armId": arm["armId"],
        "variantId": variant_id,
        "replicate": replicate_index,
        "mode": result["mode"],
        "modeState": result.get("modeState", {}),
        "usage": result["usage"],
        "publicAnswer": public_answer,
        "answer": result.get("answer"),
        "summary": result.get("summary"),
        "generatedAt": utc_now(),
    }
    write_json(replicate_dir / "result.json", result_payload)
    artifacts = collect_replicate_artifacts(run, run_dir, case["caseId"], variant_id, replicate_index, replicate_dir)
    return {
        "replicate": replicate_index,
        "status": "completed",
        "publicAnswer": public_answer,
        "usage": result["usage"],
        "mode": result["mode"],
        "modeState": result.get("modeState", {}),
        "deterministic": deterministic,
        "quality": quality,
        "control": control,
        "artifactIds": [entry["artifactId"] for entry in artifacts],
        "artifacts": artifacts,
        "updatedAt": utc_now(),
    }


def execute_run(root: Path, run_id: str) -> Dict[str, Any]:
    run_dir = root / "data" / "evals" / "runs" / run_id
    run_path = run_dir / "run.json"
    run = read_json(run_path)
    suite_path = root / "data" / "evals" / "suites" / f"{run['suiteId']}.json"
    suite = validate_suite_manifest(read_json(suite_path), suite_path)
    arm_map: Dict[str, Dict[str, Any]] = {}
    for arm_id in run.get("armIds", []):
        arm_path = root / "data" / "evals" / "arms" / f"{arm_id}.json"
        arm_map[arm_id] = validate_arm_manifest(read_json(arm_path), arm_path)
    auth_path = root / "Auth.txt"
    run["suite"] = {
        "suiteId": suite["suiteId"],
        "title": suite["title"],
        "description": suite["description"],
        "judgeRubric": suite["judgeRubric"],
    }
    run["arms"] = [
        {
            "armId": arm["armId"],
            "title": arm["title"],
            "description": arm["description"],
            "type": arm["type"],
        }
        for arm in arm_map.values()
    ]
    run["cases"] = []
    run["artifactIndex"] = {}
    run["status"] = "running"
    run["startedAt"] = utc_now()
    run["error"] = None
    persist_run(run_path, run)

    loop_sweep = [int(value) for value in run.get("loopSweep", []) if int(value) > 0]
    if not loop_sweep:
        loop_sweep = [1]
    judge_model = normalize_model_id(str(run.get("judgeModel", "")).strip(), "gpt-5.4")

    for case in suite["cases"]:
        case_entry = find_case_entry(run, case["caseId"])
        case_entry["title"] = case["title"]
        case_entry["objective"] = case["objective"]
        case_entry["constraints"] = case["constraints"]
        for arm_id in run.get("armIds", []):
            arm = arm_map[arm_id]
            loop_values = [1] if arm["type"] == "direct" else loop_sweep
            for loop_rounds in loop_values:
                variant_id = variant_id_for_arm(arm, loop_rounds)
                variant_entry = find_variant_entry(case_entry, variant_id)
                variant_entry.update(
                    {
                        "variantId": variant_id,
                        "armId": arm["armId"],
                        "title": arm["title"],
                        "description": arm["description"],
                        "type": arm["type"],
                        "loopRounds": int(loop_rounds),
                        "replicates": [],
                    }
                )
                for replicate_index in range(1, max(1, int(run.get("replicates", 1) or 1)) + 1):
                    run["current"] = {
                        "caseId": case["caseId"],
                        "variantId": variant_id,
                        "replicate": replicate_index,
                    }
                    persist_run(run_path, run)
                    try:
                        replicate_result = execute_replicate(
                            run=run,
                            run_dir=run_dir,
                            case=case,
                            arm=arm,
                            loop_rounds=int(loop_rounds),
                            replicate_index=replicate_index,
                            judge_model=judge_model,
                            auth_path=auth_path,
                        )
                    except Exception as error:
                        error_payload = {
                            "replicate": replicate_index,
                            "status": "error",
                            "error": str(error),
                            "traceback": traceback.format_exc(),
                            "updatedAt": utc_now(),
                            "artifactIds": [],
                            "artifacts": [],
                        }
                        write_json(
                            run_dir / "cases" / case["caseId"] / variant_id / f"replicate-{replicate_index:03d}" / "score.json",
                            {
                                "runId": run["runId"],
                                "caseId": case["caseId"],
                                "armId": arm["armId"],
                                "variantId": variant_id,
                                "replicate": replicate_index,
                                "error": str(error),
                                "generatedAt": utc_now(),
                            },
                        )
                        variant_entry["replicates"].append(error_payload)
                        variant_entry["aggregate"] = aggregate_variant(variant_entry)
                        persist_run(run_path, run)
                        continue
                    variant_entry["replicates"].append(replicate_result)
                    variant_entry["aggregate"] = aggregate_variant(variant_entry)
                    persist_run(run_path, run)

    run["summary"] = aggregate_run(run)
    run["status"] = "completed"
    run["completedAt"] = utc_now()
    run["current"] = None
    persist_run(run_path, run)
    return run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute an isolated eval run against the loop runtime.")
    parser.add_argument("--root", required=True, help="Project root.")
    parser.add_argument("--run-id", required=True, help="Eval run id to execute.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    try:
        execute_run(root, str(args.run_id).strip())
        return 0
    except Exception as error:
        run_path = root / "data" / "evals" / "runs" / str(args.run_id).strip() / "run.json"
        if run_path.exists():
            try:
                run = read_json(run_path)
                run["status"] = "error"
                run["completedAt"] = utc_now()
                run["error"] = str(error)
                run["traceback"] = traceback.format_exc()
                persist_run(run_path, run)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
