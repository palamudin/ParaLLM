from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import traceback
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import metadata as metadata_store
from backend.app.control import auth_file_path
from runtime.engine import (
    LoopRuntime,
    RuntimeErrorWithCode,
    auth_assignment_meta,
    coerce_bool,
    default_context_mode,
    default_direct_baseline_mode,
    default_summarizer_harness,
    default_model_for_provider,
    default_budget_config,
    default_loop_state,
    default_ollama_base_url,
    default_research_config,
    default_state,
    default_usage_state,
    default_vetting_config,
    direct_baseline_harness_instruction_lines,
    normalize_budget_config,
    normalize_context_mode,
    normalize_direct_baseline_mode,
    normalize_harness_config,
    normalize_model_id,
    normalize_ollama_base_url,
    normalize_provider_id,
    normalize_research_config,
    normalize_string_array_preserve_items,
    normalize_usage_state,
    normalize_vetting_config,
    provider_capability_profile,
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

ANSWER_HEALTH_SCORE_FIELDS = [
    "instructionFit",
    "structuralClarity",
    "confidenceCalibration",
    "evidenceHygiene",
    "efficiencyDiscipline",
    "overallHealth",
]

CONTROL_SCORE_FIELDS = [
    "leadControl",
    "adversarialDiscipline",
    "selfCheckQuality",
    "nonFunnelIntegration",
    "overallControl",
]

COMPARISON_SCORE_FIELDS = [
    "materialDifference",
    "decisionShift",
    "validationStrength",
    "operationalSeparation",
    "overallDifferentiation",
]

VETTING_MATRIX_SCORE_FIELDS = [
    "blastRadiusPerception",
    "humanUsability",
    "agentExecutability",
    "tacticalDetail",
    "restraintAndCollateral",
    "decisionGates",
    "firstHourRealism",
    "overall",
]

VETTING_MATRIX_SCORE_LABELS = {
    "blastRadiusPerception": "Blast radius perception",
    "humanUsability": "Human usability",
    "agentExecutability": "AI-agent executability",
    "tacticalDetail": "Tactical artifact detail",
    "restraintAndCollateral": "Restraint / avoiding collateral damage",
    "decisionGates": "Decision gates",
    "firstHourRealism": "First-hour realism",
    "overall": "Overall",
}

VETTING_COMPUTE_VERDICTS = ["earned", "mixed", "did_not_earn"]

COMPARE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "we",
    "with",
    "you",
}


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


def count_sentences(text: str) -> int:
    parts = [part.strip() for part in re.split(r"[.!?]+\s+", str(text or "").strip()) if part.strip()]
    return len(parts) if parts else (1 if str(text or "").strip() else 0)


def tokenize_compare_text(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]{2,}", str(text or "").lower())
    return [token for token in tokens if token not in COMPARE_STOPWORDS]


def answer_similarity_metrics(primary_text: str, baseline_text: str) -> Dict[str, Any]:
    primary = str(primary_text or "").strip()
    baseline = str(baseline_text or "").strip()
    normalized_primary = re.sub(r"\s+", " ", primary.lower()).strip()
    normalized_baseline = re.sub(r"\s+", " ", baseline.lower()).strip()
    primary_tokens = tokenize_compare_text(primary)
    baseline_tokens = tokenize_compare_text(baseline)
    token_union = set(primary_tokens) | set(baseline_tokens)
    token_overlap = 0.0
    if token_union:
        token_overlap = len(set(primary_tokens) & set(baseline_tokens)) / len(token_union)
    primary_first_sentence = re.split(r"(?<=[.!?])\s+", primary, maxsplit=1)[0].strip().lower()
    baseline_first_sentence = re.split(r"(?<=[.!?])\s+", baseline, maxsplit=1)[0].strip().lower()
    sequence_similarity = SequenceMatcher(None, normalized_primary, normalized_baseline).ratio() if normalized_primary or normalized_baseline else 0.0
    return {
        "sequenceSimilarity": round(sequence_similarity, 3),
        "tokenOverlap": round(token_overlap, 3),
        "sharedOpening": bool(primary_first_sentence and primary_first_sentence == baseline_first_sentence),
        "primaryParagraphs": count_paragraphs(primary),
        "baselineParagraphs": count_paragraphs(baseline),
        "paragraphDelta": count_paragraphs(primary) - count_paragraphs(baseline),
        "primaryChars": len(primary),
        "baselineChars": len(baseline),
        "charDelta": len(primary) - len(baseline),
        "primaryWords": len(primary_tokens),
        "baselineWords": len(baseline_tokens),
        "wordDelta": len(primary_tokens) - len(baseline_tokens),
    }


def build_answer_telemetry(
    answer_text: str,
    response_meta: Optional[Dict[str, Any]] = None,
    provider: str = "",
    model: str = "",
) -> Dict[str, Any]:
    response_meta = response_meta if isinstance(response_meta, dict) else {}
    usage_delta = normalize_usage_state(response_meta.get("usageDelta") if isinstance(response_meta.get("usageDelta"), dict) else {})
    search_queries = normalize_string_array_preserve_items(response_meta.get("webSearchQueries", []))
    search_sources = normalize_string_array_preserve_items(response_meta.get("webSearchSources", []))
    citations = normalize_string_array_preserve_items(response_meta.get("urlCitations", []))
    output_tokens = int(usage_delta.get("outputTokens", 0) or 0)
    reasoning_tokens = int(usage_delta.get("reasoningTokens", 0) or 0)
    effective_max_tokens = int(response_meta.get("effectiveMaxOutputTokens", 0) or 0)
    output_budget_utilization = 0.0
    if effective_max_tokens > 0 and output_tokens > 0:
        output_budget_utilization = output_tokens / effective_max_tokens
    reasoning_share = 0.0
    if output_tokens > 0 and reasoning_tokens > 0:
        reasoning_share = reasoning_tokens / output_tokens
    return {
        "provider": str(provider or "").strip(),
        "model": str(model or "").strip(),
        "paragraphCount": count_paragraphs(answer_text),
        "sentenceCount": count_sentences(answer_text),
        "charCount": len(str(answer_text or "").strip()),
        "wordCount": len(tokenize_compare_text(answer_text)),
        "inputTokens": int(usage_delta.get("inputTokens", 0) or 0),
        "outputTokens": output_tokens,
        "reasoningTokens": reasoning_tokens,
        "totalTokens": int(usage_delta.get("totalTokens", 0) or 0),
        "webSearchCalls": int(usage_delta.get("webSearchCalls", 0) or 0),
        "searchQueryCount": len(search_queries),
        "sourceCount": len(search_sources),
        "citationCount": len(citations),
        "recoveredFromIncomplete": bool(response_meta.get("recoveredFromIncomplete", False)),
        "effectiveMaxOutputTokens": effective_max_tokens,
        "outputBudgetUtilization": round(output_budget_utilization, 3),
        "reasoningShare": round(reasoning_share, 3),
    }


def normalize_loop_preferences(config: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    payload = config if isinstance(config, dict) else {}
    rounds = int(payload.get("rounds", 1) or 1)
    delay_ms = int(payload.get("delayMs", 0) or 0)
    return {
        "rounds": max(1, min(12, rounds)),
        "delayMs": max(0, min(10000, delay_ms)),
    }


def response_meta_from_result(runtime: LoopRuntime, response: Optional[Dict[str, Any]], call_meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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


def answer_health_judge_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "scores",
            "verdict",
            "strongestStrength",
            "strongestWeakness",
            "rationale",
        ],
        "properties": {
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": ANSWER_HEALTH_SCORE_FIELDS,
                "properties": {field: {"type": "integer"} for field in ANSWER_HEALTH_SCORE_FIELDS},
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


def comparison_judge_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "scores",
            "verdict",
            "decisionRelation",
            "materialDifference",
            "primaryEdge",
            "baselineEdge",
            "rationale",
        ],
        "properties": {
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": COMPARISON_SCORE_FIELDS,
                "properties": {field: {"type": "integer"} for field in COMPARISON_SCORE_FIELDS},
            },
            "verdict": {"type": "string", "enum": ["pressurized_advantage", "baseline_advantage", "mixed"]},
            "decisionRelation": {"type": "string", "enum": ["same_direction", "refined_direction", "different_direction", "opposed_direction"]},
            "materialDifference": {"type": "boolean"},
            "primaryEdge": {"type": "string"},
            "baselineEdge": {"type": "string"},
            "rationale": {"type": "string"},
        },
    }


def vetting_matrix_judge_schema(answer_ids: List[str]) -> Dict[str, Any]:
    normalized_ids = [str(answer_id or "").strip() for answer_id in answer_ids if str(answer_id or "").strip()]
    if not normalized_ids:
        raise EvalError("Vetting matrix judge schema requires at least one answer id.")
    score_block = {
        "type": "object",
        "additionalProperties": False,
        "required": VETTING_MATRIX_SCORE_FIELDS,
        "properties": {
            field: {"type": "number", "minimum": 0, "maximum": 10}
            for field in VETTING_MATRIX_SCORE_FIELDS
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "scores",
            "ranking",
            "bestFinalAnswer",
            "bestTacticalDetail",
            "bestValue",
            "computeVerdict",
            "answerNotes",
            "rationale",
        ],
        "properties": {
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": normalized_ids,
                "properties": {answer_id: score_block for answer_id in normalized_ids},
            },
            "ranking": {
                "type": "array",
                "minItems": len(normalized_ids),
                "maxItems": len(normalized_ids),
                "items": {"type": "string", "enum": normalized_ids},
            },
            "bestFinalAnswer": {"type": "string", "enum": normalized_ids},
            "bestTacticalDetail": {"type": "string", "enum": normalized_ids},
            "bestValue": {"type": "string", "enum": normalized_ids},
            "computeVerdict": {"type": "string", "enum": VETTING_COMPUTE_VERDICTS},
            "answerNotes": {
                "type": "object",
                "additionalProperties": False,
                "required": normalized_ids,
                "properties": {answer_id: {"type": "string"} for answer_id in normalized_ids},
            },
            "rationale": {"type": "string"},
        },
    }


def normalize_vetting_score_value(value: Any) -> float:
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        candidate = 0.0
    candidate = max(0.0, min(10.0, candidate))
    return round(candidate * 2) / 2


def vetting_category_leaders(scores: Dict[str, Dict[str, float]]) -> Dict[str, List[str]]:
    leaders: Dict[str, List[str]] = {}
    for field in VETTING_MATRIX_SCORE_FIELDS:
        field_values = {
            str(answer_id): normalize_vetting_score_value((score_block or {}).get(field, 0.0))
            for answer_id, score_block in scores.items()
        }
        if not field_values:
            leaders[field] = []
            continue
        best_value = max(field_values.values())
        leaders[field] = [answer_id for answer_id, value in field_values.items() if value == best_value]
    return leaders


def normalize_vetting_matrix_result(parsed: Dict[str, Any], answer_ids: List[str], response_id: Optional[str] = None) -> Dict[str, Any]:
    normalized_ids = [str(answer_id or "").strip() for answer_id in answer_ids if str(answer_id or "").strip()]
    parsed_scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
    score_matrix: Dict[str, Dict[str, float]] = {}
    for answer_id in normalized_ids:
        score_block = parsed_scores.get(answer_id) if isinstance(parsed_scores.get(answer_id), dict) else {}
        normalized_block = {
            field: normalize_vetting_score_value(score_block.get(field, 0.0))
            for field in VETTING_MATRIX_SCORE_FIELDS
        }
        if normalized_block["overall"] <= 0:
            average_without_overall = mean([normalized_block[field] for field in VETTING_MATRIX_SCORE_FIELDS if field != "overall"])
            normalized_block["overall"] = normalize_vetting_score_value(average_without_overall)
        score_matrix[answer_id] = normalized_block

    ranking = [str(answer_id).strip() for answer_id in parsed.get("ranking", []) if str(answer_id).strip() in normalized_ids]
    ranking = list(dict.fromkeys(ranking))
    if len(ranking) != len(normalized_ids):
        fallback_ranking = sorted(
            normalized_ids,
            key=lambda answer_id: (
                -float(score_matrix.get(answer_id, {}).get("overall", 0.0)),
                normalized_ids.index(answer_id),
            ),
        )
        for answer_id in fallback_ranking:
            if answer_id not in ranking:
                ranking.append(answer_id)

    answer_notes_raw = parsed.get("answerNotes") if isinstance(parsed.get("answerNotes"), dict) else {}
    answer_notes = {
        answer_id: truncate_text(answer_notes_raw.get(answer_id, ""), 320)
        for answer_id in normalized_ids
    }

    def choose_answer_id(field_name: str, fallback_index: int = 0) -> str:
        candidate = str(parsed.get(field_name, "")).strip()
        if candidate in normalized_ids:
            return candidate
        return ranking[min(fallback_index, len(ranking) - 1)]

    return {
        "scores": score_matrix,
        "ranking": ranking,
        "bestFinalAnswer": choose_answer_id("bestFinalAnswer", 0),
        "bestTacticalDetail": choose_answer_id("bestTacticalDetail", 0),
        "bestValue": choose_answer_id("bestValue", 0),
        "computeVerdict": (
            str(parsed.get("computeVerdict", "")).strip()
            if str(parsed.get("computeVerdict", "")).strip() in VETTING_COMPUTE_VERDICTS
            else "mixed"
        ),
        "answerNotes": answer_notes,
        "categoryLeaders": vetting_category_leaders(score_matrix),
        "rationale": truncate_text(parsed.get("rationale", ""), 1600),
        "responseId": response_id,
    }


def comparison_score_delta(primary_scores: Dict[str, Any], baseline_scores: Dict[str, Any], fields: List[str]) -> Dict[str, float]:
    return {
        field: round(float(primary_scores.get(field, 0) or 0.0) - float(baseline_scores.get(field, 0) or 0.0), 2)
        for field in fields
    }


def comparison_verdict_from_delta(overall_delta: float) -> str:
    if overall_delta >= 0.5:
        return "pressurized_advantage"
    if overall_delta <= -0.5:
        return "baseline_advantage"
    return "mixed"


def comparison_verdict_from_counts(pressurized_wins: int, baseline_wins: int, mean_overall_delta: float) -> str:
    if pressurized_wins > baseline_wins:
        return "pressurized_advantage"
    if baseline_wins > pressurized_wins:
        return "baseline_advantage"
    return comparison_verdict_from_delta(mean_overall_delta)


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
    provider = normalize_provider_id(str(runtime_payload.get("provider", "")).strip(), "openai")
    model = normalize_model_id(str(runtime_payload.get("model", "")).strip(), default_model_for_provider(provider), provider)
    summarizer_provider = normalize_provider_id(str(runtime_payload.get("summarizerProvider", "")).strip(), provider)
    summarizer_model = normalize_model_id(
        str(runtime_payload.get("summarizerModel", "")).strip(),
        model,
        summarizer_provider,
    )
    reasoning_effort = str(runtime_payload.get("reasoningEffort", "low")).strip().lower()
    if reasoning_effort not in {"none", "low", "medium", "high", "xhigh"}:
        reasoning_effort = "low"
    execution_mode = str(runtime_payload.get("executionMode", "live")).strip().lower()
    if execution_mode not in {"live", "mock"}:
        execution_mode = "live"
    context_mode = normalize_context_mode(runtime_payload.get("contextMode", default_context_mode()), default_context_mode())
    direct_baseline_mode = normalize_direct_baseline_mode(
        runtime_payload.get("directBaselineMode", default_direct_baseline_mode()),
        default_direct_baseline_mode(),
    )
    direct_provider = normalize_provider_id(str(runtime_payload.get("directProvider", provider)).strip(), provider)
    direct_model = normalize_model_id(
        str(runtime_payload.get("directModel", "")).strip(),
        default_model_for_provider(direct_provider),
        direct_provider,
    )
    budget = normalize_budget_config(runtime_payload.get("budget") if isinstance(runtime_payload.get("budget"), dict) else {})
    research = normalize_research_config(runtime_payload.get("research") if isinstance(runtime_payload.get("research"), dict) else {})
    vetting = normalize_vetting_config(runtime_payload.get("vetting") if isinstance(runtime_payload.get("vetting"), dict) else {})
    preferred_loop = normalize_loop_preferences(runtime_payload.get("preferredLoop") if isinstance(runtime_payload.get("preferredLoop"), dict) else {})
    ollama_base_url = normalize_ollama_base_url(runtime_payload.get("ollamaBaseUrl", default_ollama_base_url()))
    summarizer_harness = normalize_harness_config(
        runtime_payload.get("summarizerHarness", default_summarizer_harness()),
        default_summarizer_harness()["concision"],
    )
    workers = payload.get("workers") if isinstance(payload.get("workers"), list) else []
    normalized_workers = task_workers({"runtime": {"model": model, "provider": provider}, "workers": workers}) if workers else []
    if arm_type == "steered" and not normalized_workers:
        raise EvalError(f"Steered arm {arm_id} must include at least one worker.")
    return {
        "armId": arm_id,
        "title": title,
        "description": str(payload.get("description", "")).strip(),
        "type": arm_type,
        "runtime": {
            "executionMode": execution_mode,
            "contextMode": context_mode,
            "directBaselineMode": direct_baseline_mode,
            "provider": provider,
            "model": model,
            "directProvider": direct_provider,
            "directModel": direct_model,
            "ollamaBaseUrl": ollama_base_url,
            "summarizerProvider": summarizer_provider,
            "summarizerModel": summarizer_model,
            "summarizerHarness": summarizer_harness,
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
            "contextMode": runtime_config["contextMode"],
            "directBaselineMode": runtime_config["directBaselineMode"],
            "provider": runtime_config["provider"],
            "model": runtime_config["model"],
            "directProvider": runtime_config["directProvider"],
            "directModel": runtime_config["directModel"],
            "ollamaBaseUrl": runtime_config["ollamaBaseUrl"],
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
            "provider": runtime_config["summarizerProvider"],
            "model": runtime_config["summarizerModel"],
            "harness": deepcopy(runtime_config["summarizerHarness"]),
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
    provider = str(arm["runtime"].get("provider") or "openai").strip()
    api_key = str(auth_assignment.get("apiKey")) if isinstance(auth_assignment, dict) else ""
    if provider == "openai" and not api_key:
        api_key = runtime.get_api_key()
    if provider != "openai":
        api_key = runtime.provider_live_api_key(provider, None)
    auth_meta = runtime.live_auth_meta(provider, auth_assignment)
    runtime_config = arm["runtime"]
    model = runtime_config["model"]
    reasoning_effort = runtime_config["reasoningEffort"]
    requested_max_output = int(runtime_config["budget"]["maxOutputTokens"])
    harness_lines = direct_baseline_harness_instruction_lines(
        runtime_config.get("summarizerHarness", default_summarizer_harness())
    )
    instructions = (
        "Answer the user directly as one assistant.\n"
        "Give a decisive but conditional recommendation.\n"
        "Do not narrate hidden process.\n"
        "Absorb tradeoffs into the recommendation itself.\n"
    )
    if harness_lines:
        instructions += "\n".join(harness_lines) + "\n"
    instructions += "Return JSON only that matches the schema."
    input_text = (
        f"Objective:\n{case['objective']}\n\n"
        f"Constraints:\n{json.dumps(case.get('constraints', []), ensure_ascii=False, indent=2)}\n\n"
        f"Session context:\n{case.get('sessionContext', '') or 'none'}\n"
    )
    if runtime_config["executionMode"] == "live" and (api_key or not runtime.provider_requires_api_key(provider)):
        try:
            result = runtime.invoke_provider_json(
                provider=provider,
                api_key=api_key,
                model=model,
                reasoning_effort=reasoning_effort,
                instructions=instructions,
                input_text=input_text,
                schema_name="eval_direct_answer",
                schema=direct_answer_schema(),
                max_output_tokens=requested_max_output,
                target_kind="generic",
                provider_settings=runtime_config,
            )
            usage = runtime.get_response_usage_delta(result.response, model) or default_usage_state()
            return {
                "mode": "live",
                "provider": provider,
                "providerCapabilities": provider_capability_profile(provider),
                "model": model,
                "answer": result.parsed,
                "usage": normalize_usage_state(usage),
                "responseId": result.response_id,
                "rawOutputText": result.output_text,
                "responseMeta": response_meta_from_result(
                    runtime,
                    result.response,
                    {
                        "model": model,
                        "requestedMaxOutputTokens": result.requested_max_output_tokens,
                        "effectiveMaxOutputTokens": result.effective_max_output_tokens,
                        "attempts": result.attempts,
                        "recoveredFromIncomplete": result.recovered_from_incomplete,
                    },
                ),
                "authMeta": auth_meta,
            }
        except RuntimeErrorWithCode:
            if not runtime_config["allowMockFallback"]:
                raise
    return {
        "mode": "mock",
        "provider": provider,
        "providerCapabilities": provider_capability_profile(provider),
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
    answer_path = normalize_direct_baseline_mode(arm["runtime"].get("directBaselineMode"), default_direct_baseline_mode())

    if answer_path == "single":
        runtime.run_target("direct_baseline", task["taskId"])
    else:
        if answer_path == "both":
            runtime.run_target("direct_baseline", task["taskId"])
        for _round in range(1, max(1, loop_rounds) + 1):
            runtime.run_target("commander", task["taskId"])
            for worker_id in worker_ids:
                runtime.run_target(worker_id, task["taskId"])
            runtime.run_target("commander_review", task["taskId"])
            runtime.run_target("summarizer", task["taskId"])
    state = runtime.read_state()
    summary = state.get("summary")
    direct_baseline = state.get("directBaseline")
    if answer_path == "single":
        if not isinstance(direct_baseline, dict):
            raise EvalError("Single-answer steered run finished without a direct baseline.")
    elif not isinstance(summary, dict):
        raise EvalError("Steered run finished without a summary.")
    usage = normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
    outputs_root = workspace_root / "data"
    summary_mode = str(((summary.get("frontAnswer") or {}) if isinstance(summary, dict) else {}).get("confidenceNote", "")).strip()
    summary_output_payload: Optional[Dict[str, Any]] = None
    direct_baseline_output_payload: Optional[Dict[str, Any]] = None
    summary_output_path = outputs_root / "outputs" / f"{task['taskId']}_summary_round{int(loop_rounds):03d}_output.json"
    if summary_output_path.exists():
        summary_output_payload = read_json(summary_output_path)
    direct_baseline_output_path = outputs_root / "outputs" / f"{task['taskId']}_direct_baseline_round001_output.json"
    if direct_baseline_output_path.exists():
        direct_baseline_output_payload = read_json(direct_baseline_output_path)
    return {
        "mode": (
            str(direct_baseline.get("mode", "mock")).strip().lower()
            if answer_path == "single" and isinstance(direct_baseline, dict)
            else ("live" if summary_mode and usage.get("totalTokens", 0) else "mock")
        ),
        "taskId": task["taskId"],
        "summary": summary if isinstance(summary, dict) else None,
        "directBaseline": direct_baseline if isinstance(direct_baseline, dict) else None,
        "answerPath": answer_path,
        "baselineError": None,
        "usage": usage,
        "state": state,
        "workspaceRoot": workspace_root,
        "outputsRoot": outputs_root,
        "summaryOutput": summary_output_payload,
        "directBaselineOutput": direct_baseline_output_payload,
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
    return {
        "mode": "live",
        "scores": {field: int((parsed.get("scores") or {}).get(field, 0) or 0) for field in QUALITY_SCORE_FIELDS},
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

    quality_scores = {
        "decisiveness": 8 if has_recommendation else 5,
        "tradeoffHandling": 8 if has_tradeoff else 5,
        "objectionAbsorption": 8 if has_conditions else 5,
        "actionability": 8 if has_next_step else 5,
        "singleVoice": 9 if not mentions_hidden_process else 4,
        "overallQuality": 0,
    }
    penalty = 1 if paragraphs > 3 else 0
    quality_scores["overallQuality"] = max(1, round(mean([value for key, value in quality_scores.items() if key != "overallQuality"])) - penalty)
    return {
        "mode": "mock",
        "scores": quality_scores,
        "verdict": "Heuristic quality estimate.",
        "strongestStrength": "Clear recommendation" if has_recommendation else "Readable structure",
        "strongestWeakness": "Needs a more operational next step" if not has_next_step else "Needs stronger objection absorption",
        "rationale": "Mock judge used heuristic quality signals because no live judge model was available.",
        "responseId": None,
    }


def answer_health_judge_live(
    runtime: LoopRuntime,
    api_key: str,
    judge_model: str,
    case: Dict[str, Any],
    public_answer: str,
    telemetry: Dict[str, Any],
) -> Dict[str, Any]:
    instructions = (
        "You are grading the operational health of one candidate assistant answer.\n"
        "Score from 1 to 10 on instruction fit, structural clarity, confidence calibration, evidence hygiene, and efficiency/discipline.\n"
        "Use telemetry as supporting context, not as a substitute for reading the answer.\n"
        "Return JSON only that matches the schema."
    )
    input_text = (
        f"Objective:\n{case['objective']}\n\n"
        f"Constraints:\n{json.dumps(case.get('constraints', []), ensure_ascii=False, indent=2)}\n\n"
        f"Answer telemetry:\n{json.dumps(telemetry, ensure_ascii=False, indent=2)}\n\n"
        f"Candidate answer:\n{public_answer}\n"
    )
    result = runtime.invoke_openai_json(
        api_key=api_key,
        model=judge_model,
        reasoning_effort="high",
        instructions=instructions,
        input_text=input_text,
        schema_name="eval_answer_health_judge",
        schema=answer_health_judge_schema(),
        max_output_tokens=1200,
        target_kind="generic",
    )
    parsed = result.parsed
    scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
    return {
        "mode": "live",
        "scores": {field: int(scores.get(field, 0) or 0) for field in ANSWER_HEALTH_SCORE_FIELDS},
        "verdict": str(parsed.get("verdict", "")).strip(),
        "strongestStrength": str(parsed.get("strongestStrength", "")).strip(),
        "strongestWeakness": str(parsed.get("strongestWeakness", "")).strip(),
        "rationale": str(parsed.get("rationale", "")).strip(),
        "responseId": result.response_id,
        "telemetry": telemetry,
    }


def heuristic_answer_health(public_answer: str, telemetry: Dict[str, Any]) -> Dict[str, Any]:
    text = str(public_answer or "").strip()
    lowered = text.lower()
    paragraphs = count_paragraphs(text)
    mentions_hidden_process = any(token in lowered for token in ["lane", "worker", "summarizer", "adversarial"])
    has_calibration = any(token in lowered for token in ["if", "unless", "assume", "likely", "unknown", "depends"])
    has_evidence_language = any(token in lowered for token in ["evidence", "log", "audit", "source", "trace", "capture"])
    reasoning_share = float(telemetry.get("reasoningShare", 0.0) or 0.0)
    recovered = bool(telemetry.get("recoveredFromIncomplete", False))
    char_count = int(telemetry.get("charCount", 0) or 0)
    output_budget_utilization = float(telemetry.get("outputBudgetUtilization", 0.0) or 0.0)
    scores = {
        "instructionFit": 9 if not mentions_hidden_process and paragraphs <= 4 else 5,
        "structuralClarity": 8 if 1 <= paragraphs <= 4 and char_count > 0 else 5,
        "confidenceCalibration": 8 if has_calibration else 5,
        "evidenceHygiene": 8 if has_evidence_language or int(telemetry.get("citationCount", 0) or 0) > 0 else 5,
        "efficiencyDiscipline": 8 if not recovered and output_budget_utilization <= 0.9 and reasoning_share <= 1.5 else 5,
        "overallHealth": 0,
    }
    scores["overallHealth"] = max(1, round(mean([value for key, value in scores.items() if key != "overallHealth"])))
    return {
        "mode": "mock",
        "scores": scores,
        "verdict": "Heuristic answer-health estimate.",
        "strongestStrength": "The answer stays structurally disciplined." if scores["instructionFit"] >= 8 else "Some structural discipline is present.",
        "strongestWeakness": "Efficiency/calibration signals are weak." if scores["efficiencyDiscipline"] <= 5 else "Evidence handling remains structurally inferred in mock mode.",
        "rationale": "Mock judge used telemetry and structural cues because no live judge model was available.",
        "responseId": None,
        "telemetry": telemetry,
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


def run_answer_health_judge(
    judge_runtime: LoopRuntime,
    api_key: Optional[str],
    judge_model: str,
    case: Dict[str, Any],
    public_answer: str,
    telemetry: Dict[str, Any],
) -> Dict[str, Any]:
    if api_key:
        try:
            return answer_health_judge_live(judge_runtime, api_key, judge_model, case, public_answer, telemetry)
        except RuntimeErrorWithCode:
            pass
    return heuristic_answer_health(public_answer, telemetry)


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


def comparison_judge_live(
    runtime: LoopRuntime,
    api_key: str,
    judge_model: str,
    case: Dict[str, Any],
    judge_rubric: Any,
    primary_answer: str,
    baseline_answer: str,
    primary_quality: Dict[str, Any],
    primary_health: Dict[str, Any],
    baseline_quality: Dict[str, Any],
    baseline_health: Dict[str, Any],
    similarity: Dict[str, Any],
) -> Dict[str, Any]:
    instructions = (
        "You are comparing a pressurized multi-lane answer against a single-thread baseline for the same prompt.\n"
        "Judge whether the answers are materially different, whether the difference changes the operational decision, and whether one answer is genuinely better.\n"
        "Do not reward superficial paraphrase. If the answers mostly say the same thing, mark material difference low even if wording changes.\n"
        "Verdict must be exactly one of: pressurized_advantage, baseline_advantage, mixed.\n"
        "decisionRelation must be exactly one of: same_direction, refined_direction, different_direction, opposed_direction.\n"
        "Use the supplied quality/health summaries and similarity metrics as context, but base the verdict on the actual answer texts.\n"
        "Return JSON only that matches the schema."
    )
    input_text = (
        f"Objective:\n{case['objective']}\n\n"
        f"Constraints:\n{json.dumps(case.get('constraints', []), ensure_ascii=False, indent=2)}\n\n"
        f"Hidden rubric:\n{json.dumps(judge_rubric, ensure_ascii=False, indent=2)}\n\n"
        f"Hidden gold guidance:\n{json.dumps(case.get('gold', {}), ensure_ascii=False, indent=2)}\n\n"
        f"Pressurized answer quality summary:\n{json.dumps(primary_quality, ensure_ascii=False, indent=2)}\n\n"
        f"Pressurized answer health summary:\n{json.dumps(primary_health, ensure_ascii=False, indent=2)}\n\n"
        f"Baseline answer quality summary:\n{json.dumps(baseline_quality, ensure_ascii=False, indent=2)}\n\n"
        f"Baseline answer health summary:\n{json.dumps(baseline_health, ensure_ascii=False, indent=2)}\n\n"
        f"Similarity metrics:\n{json.dumps(similarity, ensure_ascii=False, indent=2)}\n\n"
        f"Pressurized answer:\n{primary_answer}\n\n"
        f"Single-thread baseline answer:\n{baseline_answer}\n"
    )
    result = runtime.invoke_openai_json(
        api_key=api_key,
        model=judge_model,
        reasoning_effort="high",
        instructions=instructions,
        input_text=input_text,
        schema_name="eval_comparison_judge",
        schema=comparison_judge_schema(),
        max_output_tokens=1600,
        target_kind="generic",
    )
    parsed = result.parsed
    scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
    return {
        "mode": "live",
        "scores": {field: int(scores.get(field, 0) or 0) for field in COMPARISON_SCORE_FIELDS},
        "verdict": str(parsed.get("verdict", "")).strip() or "mixed",
        "decisionRelation": str(parsed.get("decisionRelation", "")).strip(),
        "materialDifference": bool(parsed.get("materialDifference", False)),
        "primaryEdge": str(parsed.get("primaryEdge", "")).strip(),
        "baselineEdge": str(parsed.get("baselineEdge", "")).strip(),
        "rationale": str(parsed.get("rationale", "")).strip(),
        "responseId": result.response_id,
    }


def heuristic_comparison_judge(
    primary_answer: str,
    baseline_answer: str,
    primary_quality: Dict[str, Any],
    baseline_quality: Dict[str, Any],
    similarity: Dict[str, Any],
) -> Dict[str, Any]:
    sequence_similarity = float(similarity.get("sequenceSimilarity", 0.0) or 0.0)
    token_overlap = float(similarity.get("tokenOverlap", 0.0) or 0.0)
    overlap_mean = mean([sequence_similarity, token_overlap])
    overall_delta = float((primary_quality.get("scores") or {}).get("overallQuality", 0.0) or 0.0) - float((baseline_quality.get("scores") or {}).get("overallQuality", 0.0) or 0.0)
    material_difference_score = max(1, min(10, round((1.0 - overlap_mean) * 10)))
    decision_shift_score = max(1, min(10, round((1.0 - sequence_similarity) * 10)))
    validation_strength = max(1, min(10, round(5 + abs(overall_delta) * 2 - (2 if material_difference_score <= 3 else 0))))
    operational_separation = max(1, min(10, round(((1.0 - overlap_mean) * 6) + min(4, abs(int(similarity.get("paragraphDelta", 0) or 0)) + abs(int(similarity.get("wordDelta", 0) or 0)) / 120))))
    overall_differentiation = max(1, min(10, round(mean([material_difference_score, decision_shift_score, validation_strength, operational_separation]))))
    if material_difference_score <= 3 and abs(overall_delta) < 0.5:
        decision_relation = "same_direction"
    elif sequence_similarity >= 0.55:
        decision_relation = "refined_direction"
    else:
        decision_relation = "different_direction"
    verdict = comparison_verdict_from_delta(overall_delta)
    if material_difference_score <= 3 and verdict != "mixed":
        verdict = "mixed"
    return {
        "mode": "mock",
        "scores": {
            "materialDifference": material_difference_score,
            "decisionShift": decision_shift_score,
            "validationStrength": validation_strength,
            "operationalSeparation": operational_separation,
            "overallDifferentiation": overall_differentiation,
        },
        "verdict": verdict,
        "decisionRelation": decision_relation,
        "materialDifference": material_difference_score >= 5,
        "primaryEdge": "Pressurized answer shows a stronger net advantage." if overall_delta > 0.4 else "Pressurized answer mostly refines phrasing rather than changing the course.",
        "baselineEdge": "Baseline answer keeps the stronger immediate call and escalation cadence." if overall_delta < -0.4 else "Baseline answer mostly overlaps the same decision.",
        "rationale": "Heuristic comparison used quality deltas plus text-similarity signals because no live comparison judge was available.",
        "responseId": None,
    }


def run_comparison_judge(
    judge_runtime: LoopRuntime,
    api_key: Optional[str],
    judge_model: str,
    case: Dict[str, Any],
    judge_rubric: Any,
    primary_answer: str,
    baseline_answer: str,
    primary_quality: Dict[str, Any],
    primary_health: Dict[str, Any],
    baseline_quality: Dict[str, Any],
    baseline_health: Dict[str, Any],
    similarity: Dict[str, Any],
) -> Dict[str, Any]:
    if api_key:
        try:
            return comparison_judge_live(
                judge_runtime,
                api_key,
                judge_model,
                case,
                judge_rubric,
                primary_answer,
                baseline_answer,
                primary_quality,
                primary_health,
                baseline_quality,
                baseline_health,
                similarity,
            )
        except RuntimeErrorWithCode:
            pass
    return heuristic_comparison_judge(primary_answer, baseline_answer, primary_quality, baseline_quality, similarity)


def vetting_matrix_judge_live(
    runtime: LoopRuntime,
    api_key: str,
    judge_model: str,
    case: Dict[str, Any],
    judge_rubric: Any,
    answers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized_answers = [dict(answer) for answer in answers if isinstance(answer, dict) and str(answer.get("id", "")).strip()]
    if not normalized_answers:
        raise EvalError("Vetting matrix judge requires at least one answer.")
    answer_ids = [str(answer.get("id", "")).strip() for answer in normalized_answers]
    instructions = (
        "You are acting as an impartial senior evaluator reviewing multiple candidate answers to the same prompt.\n"
        "Ignore cosmetic formatting unless it changes meaning.\n"
        "Score each answer from 0 to 10 in 0.5-point increments on these categories: blast radius perception, human usability, AI-agent executability, tactical detail, restraint / collateral control, decision gates, first-hour realism, and overall quality.\n"
        "Best final answer means the answer you would most trust to ship to an operator as the primary response.\n"
        "Best tactical detail means the answer that contributes the most useful extra checks, artifacts, or specialist detail.\n"
        "Best value means the answer with the strongest quality relative to its declared compute/cost envelope.\n"
        "computeVerdict must be exactly one of: earned, mixed, did_not_earn.\n"
        "Do not bias toward length or drama. Reward correct sequencing, evidence preservation, escalation discipline, and operational restraint.\n"
        "Return JSON only that matches the schema."
    )
    answer_packets = []
    for answer in normalized_answers:
        answer_packets.append(
            {
                "id": str(answer.get("id", "")).strip(),
                "declaredCostUsd": (
                    round(float(answer.get("costUsd", 0.0) or 0.0), 6)
                    if answer.get("costUsd") is not None
                    else None
                ),
                "declaredCostNote": str(answer.get("costNote", "")).strip() or None,
                "familyHint": str(answer.get("familyHint", "")).strip() or None,
                "answer": str(answer.get("text", "")).strip(),
            }
        )
    input_text = (
        f"Objective:\n{case['objective']}\n\n"
        f"Constraints:\n{json.dumps(case.get('constraints', []), ensure_ascii=False, indent=2)}\n\n"
        f"Judge rubric:\n{json.dumps(judge_rubric, ensure_ascii=False, indent=2)}\n\n"
        f"Hidden gold guidance:\n{json.dumps(case.get('gold', {}), ensure_ascii=False, indent=2)}\n\n"
        f"Candidate answers:\n{json.dumps(answer_packets, ensure_ascii=False, indent=2)}\n"
    )
    result = runtime.invoke_openai_json(
        api_key=api_key,
        model=judge_model,
        reasoning_effort="high",
        instructions=instructions,
        input_text=input_text,
        schema_name="eval_vetting_matrix_judge",
        schema=vetting_matrix_judge_schema(answer_ids),
        max_output_tokens=2600,
        target_kind="generic",
    )
    normalized = normalize_vetting_matrix_result(result.parsed, answer_ids, result.response_id)
    return {
        "mode": "live",
        **normalized,
    }


def extract_public_answer(arm: Dict[str, Any], result: Dict[str, Any]) -> str:
    if arm["type"] == "direct":
        return str(result.get("answer", {}).get("answer", "")).strip()
    if normalize_direct_baseline_mode(result.get("answerPath"), "off") == "single":
        direct_baseline = result.get("directBaseline") if isinstance(result.get("directBaseline"), dict) else {}
        answer = direct_baseline.get("answer") if isinstance(direct_baseline.get("answer"), dict) else {}
        return str(answer.get("answer", "")).strip()
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
    answer_path = normalize_direct_baseline_mode(result.get("answerPath"), "off")
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
    elif answer_path == "single":
        direct_baseline = result.get("directBaseline")
        if not isinstance(direct_baseline, dict):
            result_fields_ok = False
            missing_fields = ["directBaseline"]
        else:
            answer = direct_baseline.get("answer")
            if not isinstance(answer, dict):
                result_fields_ok = False
                missing_fields = ["directBaseline.answer"]
            else:
                missing_fields = [field for field in ["answer", "stance", "confidenceNote"] if not str(answer.get(field, "")).strip()]
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
    elif answer_path == "single":
        direct_baseline = result.get("directBaseline") if isinstance(result.get("directBaseline"), dict) else {}
        mode_values = [str(direct_baseline.get("mode", result.get("mode", "unknown"))).strip().lower() or "unknown"]
    else:
        mode_values = list((mode_state.get("workerModes") or {}).values()) + [str(mode_state.get("summaryMode", "unknown"))]
        if answer_path == "both":
            direct_baseline = result.get("directBaseline") if isinstance(result.get("directBaseline"), dict) else {}
            mode_values.append(str(direct_baseline.get("mode", "unknown")).strip().lower() or "unknown")

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
    if arm["type"] == "steered" and answer_path == "both":
        has_direct_baseline = isinstance(result.get("directBaseline"), dict)
        checks_out["directBaselineCaptured"] = {
            "passed": has_direct_baseline,
            "detail": "Parallel direct baseline was captured." if has_direct_baseline else f"Direct baseline missing. Error: {result.get('baselineError') or 'none'}",
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
    elif name == "comparison.json":
        kind = "comparison"
        target = "compare"
    elif re.match(r".+_direct_baseline(?:_round\d+)?_output\.json$", name):
        kind = "direct_output"
        target = "direct_baseline"
    elif re.match(r".+_[A-Z]_step\d+_output\.json$", name):
        kind = "worker_output"
        target = payload.get("target") or name.split("_")[1]
    elif re.match(r".+_summary_round\d+_output\.json$", name):
        kind = "summary_output"
        target = "summarizer"
    elif re.match(r".+_direct_baseline(?:_round\d+)?\.json$", name):
        kind = "direct_round"
        target = "direct_baseline"
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
        "provider": payload.get("provider"),
        "providerCapabilities": payload.get("providerCapabilities") if isinstance(payload.get("providerCapabilities"), dict) else {},
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
    answer_health_blocks = [
        entry["answerHealth"]["scores"]
        for entry in completed
        if isinstance(entry.get("answerHealth"), dict) and isinstance(entry["answerHealth"].get("scores"), dict)
    ]
    control_blocks = [entry["control"]["scores"] for entry in completed if isinstance(entry.get("control"), dict) and isinstance(entry["control"].get("scores"), dict)]
    baseline_quality_blocks = [
        entry["baselineQuality"]["scores"]
        for entry in completed
        if isinstance(entry.get("baselineQuality"), dict) and isinstance(entry["baselineQuality"].get("scores"), dict)
    ]
    baseline_answer_health_blocks = [
        entry["baselineAnswerHealth"]["scores"]
        for entry in completed
        if isinstance(entry.get("baselineAnswerHealth"), dict) and isinstance(entry["baselineAnswerHealth"].get("scores"), dict)
    ]
    comparison_blocks = [entry.get("comparison") for entry in completed if isinstance(entry.get("comparison"), dict)]
    deterministic_passes = sum(1 for entry in completed if entry.get("deterministic", {}).get("passed"))
    total_tokens = sum(int((entry.get("usage") or {}).get("totalTokens", 0) or 0) for entry in completed)
    total_cost = sum(float((entry.get("usage") or {}).get("estimatedCostUsd", 0.0) or 0.0) for entry in completed)
    score_delta_blocks = [
        block.get("scoreDelta")
        for block in comparison_blocks
        if isinstance(block.get("scoreDelta"), dict)
    ]
    comparison_score_blocks = [
        block.get("scores")
        for block in comparison_blocks
        if isinstance(block.get("scores"), dict)
    ]
    pressurized_wins = sum(1 for block in comparison_blocks if str(block.get("verdict", "")).strip() == "pressurized_advantage")
    baseline_wins = sum(1 for block in comparison_blocks if str(block.get("verdict", "")).strip() == "baseline_advantage")
    ties = max(0, len(comparison_blocks) - pressurized_wins - baseline_wins)
    mean_overall_delta = mean([float(block.get("scoreDelta", {}).get("overallQuality", 0.0) or 0.0) for block in comparison_blocks]) if comparison_blocks else 0.0
    meaningful_difference_rate = mean([1.0 if bool(block.get("materialDifference")) else 0.0 for block in comparison_blocks]) if comparison_blocks else 0.0
    return {
        "replicateCount": len(replicates),
        "completedReplicates": len(completed),
        "errorCount": sum(1 for entry in replicates if str(entry.get("status", "")) == "error"),
        "deterministicPassRate": round((deterministic_passes / len(completed)) if completed else 0.0, 2),
        "quality": average_score_blocks(quality_blocks, QUALITY_SCORE_FIELDS),
        "answerHealth": average_score_blocks(answer_health_blocks, ANSWER_HEALTH_SCORE_FIELDS),
        "control": average_score_blocks(control_blocks, CONTROL_SCORE_FIELDS),
        "baselineQuality": average_score_blocks(baseline_quality_blocks, QUALITY_SCORE_FIELDS),
        "baselineAnswerHealth": average_score_blocks(baseline_answer_health_blocks, ANSWER_HEALTH_SCORE_FIELDS),
        "comparison": {
            "replicateCount": len(comparison_blocks),
            "pressurizedWins": pressurized_wins,
            "baselineWins": baseline_wins,
            "ties": ties,
            "averageScoreDelta": average_score_blocks(score_delta_blocks, QUALITY_SCORE_FIELDS),
            "averageScores": average_score_blocks(comparison_score_blocks, COMPARISON_SCORE_FIELDS),
            "meaningfulDifferenceRate": round(meaningful_difference_rate, 2),
            "verdict": comparison_verdict_from_counts(pressurized_wins, baseline_wins, mean_overall_delta) if comparison_blocks else "unavailable",
        },
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
                    "answerPath": variant.get("answerPath"),
                    "contextMode": variant.get("contextMode"),
                    "loopRounds": variant.get("loopRounds"),
                    **variant_summary,
                }
            )
    total_tokens = sum(int(entry.get("totalTokens", 0) or 0) for entry in variant_summaries)
    total_cost = sum(float(entry.get("estimatedCostUsd", 0.0) or 0.0) for entry in variant_summaries)
    quality_blocks = [entry.get("quality", {}) for entry in variant_summaries if isinstance(entry.get("quality"), dict)]
    answer_health_blocks = [entry.get("answerHealth", {}) for entry in variant_summaries if isinstance(entry.get("answerHealth"), dict)]
    control_blocks = [entry.get("control", {}) for entry in variant_summaries if isinstance(entry.get("control"), dict) and any(entry.get("control", {}).values())]
    return {
        "caseCount": len(run.get("cases", [])),
        "variantCount": len(variant_summaries),
        "errorCount": sum(int(entry.get("errorCount", 0) or 0) for entry in variant_summaries),
        "totalTokens": total_tokens,
        "estimatedCostUsd": round(total_cost, 6),
        "averageQuality": average_score_blocks(quality_blocks, QUALITY_SCORE_FIELDS),
        "averageAnswerHealth": average_score_blocks(answer_health_blocks, ANSWER_HEALTH_SCORE_FIELDS),
        "averageControl": average_score_blocks(control_blocks, CONTROL_SCORE_FIELDS),
        "variants": variant_summaries,
    }


def persist_run(run_path: Path, run: Dict[str, Any]) -> None:
    run["updatedAt"] = utc_now()
    root = run_path.parents[4]
    if metadata_store.postgres_enabled(root):
        metadata_store.write_eval_run_payload(root, run)
    else:
        write_json(run_path, run)


def read_run(root: Path, run_id: str) -> Dict[str, Any]:
    if metadata_store.postgres_enabled(root):
        payload = metadata_store.read_eval_run_payload(root, run_id)
        if not isinstance(payload, dict):
            raise EvalError(f"Missing eval run metadata: {run_id}")
        return payload
    run_path = root / "data" / "evals" / "runs" / run_id / "run.json"
    return read_json(run_path)


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
    baseline_quality: Optional[Dict[str, Any]] = None
    answer_health: Optional[Dict[str, Any]] = None
    baseline_answer_health: Optional[Dict[str, Any]] = None
    comparison: Optional[Dict[str, Any]] = None
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
            "provider": direct["provider"],
            "providerCapabilities": direct["providerCapabilities"],
            "answer": direct["answer"],
            "usage": normalize_usage_state(direct["usage"]),
            "responseId": direct["responseId"],
            "responseMeta": direct["responseMeta"],
            "model": direct["model"],
            "modeState": {"directMode": direct["mode"]},
        }
    else:
        steered = run_steered_answer(Path("."), auth_path, case, arm, loop_rounds, replicate_dir, seed)
        answer_path = normalize_direct_baseline_mode(steered.get("answerPath"), default_direct_baseline_mode())
        mode_state = (
            {"workerModes": {}, "summaryMode": str((steered.get("directBaseline") or {}).get("mode", steered.get("mode", "unknown")))}
            if answer_path == "single"
            else mode_summary_for_steered(steered["workspaceRoot"], steered["taskId"], loop_rounds)
        )
        result = {
            "mode": mode_state["summaryMode"],
            "provider": arm["runtime"]["directProvider"] if answer_path == "single" else arm["runtime"]["summarizerProvider"],
            "providerCapabilities": provider_capability_profile(arm["runtime"]["directProvider"] if answer_path == "single" else arm["runtime"]["summarizerProvider"]),
            "taskId": steered["taskId"],
            "summary": steered["summary"],
            "directBaseline": steered.get("directBaseline"),
            "answerPath": answer_path,
            "baselineError": steered.get("baselineError"),
            "usage": normalize_usage_state(steered["usage"]),
            "responseId": None,
            "responseMeta": None,
            "summaryResponseMeta": (
                (steered.get("summaryOutput") or {}).get("responseMeta")
                if isinstance(steered.get("summaryOutput"), dict)
                else None
            ),
            "directBaselineResponseMeta": (
                (steered.get("directBaselineOutput") or {}).get("responseMeta")
                if isinstance(steered.get("directBaselineOutput"), dict)
                else None
            ),
            "model": arm["runtime"]["directModel"] if answer_path == "single" else arm["runtime"]["summarizerModel"],
            "modeState": mode_state,
        }

    public_answer = extract_public_answer(arm, result)
    primary_response_meta = (
        result.get("responseMeta")
        if arm["type"] == "direct"
        else (
            result.get("directBaselineResponseMeta")
            if normalize_direct_baseline_mode(result.get("answerPath"), "off") == "single"
            else result.get("summaryResponseMeta")
        )
    )
    primary_telemetry = build_answer_telemetry(
        public_answer,
        primary_response_meta if isinstance(primary_response_meta, dict) else None,
        str(result.get("provider", "") or ""),
        str(result.get("model", "") or ""),
    )
    quality = run_quality_judge(
        judge_runtime,
        api_key or None,
        judge_model,
        case,
        run.get("suite", {}).get("judgeRubric", {}),
        public_answer,
    )
    answer_health = run_answer_health_judge(
        judge_runtime,
        api_key or None,
        judge_model,
        case,
        public_answer,
        primary_telemetry,
    )
    control = (
        run_control_judge(judge_runtime, api_key or None, judge_model, case, result["summary"])
        if arm["type"] == "steered" and isinstance(result.get("summary"), dict)
        else None
    )
    if arm["type"] == "steered":
        direct_baseline = result.get("directBaseline") if isinstance(result.get("directBaseline"), dict) else {}
        baseline_answer = direct_baseline.get("answer") if isinstance(direct_baseline.get("answer"), dict) else {}
        baseline_text = str(baseline_answer.get("answer", "")).strip()
        if baseline_text and normalize_direct_baseline_mode(result.get("answerPath"), "off") == "both":
            baseline_telemetry = build_answer_telemetry(
                baseline_text,
                result.get("directBaselineResponseMeta") if isinstance(result.get("directBaselineResponseMeta"), dict) else None,
                str((direct_baseline.get("provider") if isinstance(direct_baseline, dict) else "") or result.get("provider", "") or ""),
                str((direct_baseline.get("model") if isinstance(direct_baseline, dict) else "") or arm["runtime"].get("directModel", "") or ""),
            )
            baseline_quality = run_quality_judge(
                judge_runtime,
                api_key or None,
                judge_model,
                case,
                run.get("suite", {}).get("judgeRubric", {}),
                baseline_text,
            )
            baseline_answer_health = run_answer_health_judge(
                judge_runtime,
                api_key or None,
                judge_model,
                case,
                baseline_text,
                baseline_telemetry,
            )
            primary_scores = quality.get("scores") if isinstance(quality.get("scores"), dict) else {}
            baseline_scores = baseline_quality.get("scores") if isinstance(baseline_quality.get("scores"), dict) else {}
            score_delta = comparison_score_delta(primary_scores, baseline_scores, QUALITY_SCORE_FIELDS)
            similarity = answer_similarity_metrics(public_answer, baseline_text)
            comparison = run_comparison_judge(
                judge_runtime,
                api_key or None,
                judge_model,
                case,
                run.get("suite", {}).get("judgeRubric", {}),
                public_answer,
                baseline_text,
                quality,
                answer_health,
                baseline_quality,
                baseline_answer_health,
                similarity,
            )
            comparison = {
                **comparison,
                "answerPath": normalize_direct_baseline_mode(result.get("answerPath"), "off"),
                "contextMode": normalize_context_mode(arm["runtime"].get("contextMode"), default_context_mode()),
                "primaryLabel": "pressurized_answer",
                "baselineLabel": "single_thread_baseline",
                "primaryAnswer": public_answer,
                "baselineAnswer": baseline_text,
                "primaryQuality": quality,
                "primaryAnswerHealth": answer_health,
                "primaryTelemetry": primary_telemetry,
                "baselineQuality": baseline_quality,
                "baselineAnswerHealth": baseline_answer_health,
                "baselineTelemetry": baseline_telemetry,
                "scoreDelta": score_delta,
                "similarity": similarity,
                "identicalAnswers": public_answer.strip() == baseline_text.strip(),
            }
    deterministic = deterministic_checks(case, arm, result, public_answer)
    score_payload: Dict[str, Any] = {
        "runId": run["runId"],
        "caseId": case["caseId"],
        "armId": arm["armId"],
        "variantId": variant_id,
        "replicate": replicate_index,
        "deterministic": deterministic,
        "quality": quality,
        "answerHealth": answer_health,
        "control": control,
        "baselineQuality": baseline_quality,
        "baselineAnswerHealth": baseline_answer_health,
        "comparison": comparison,
        "usage": result["usage"],
        "generatedAt": utc_now(),
    }
    write_json(replicate_dir / "score.json", score_payload)

    if comparison is not None:
        comparison_payload = {
            "runId": run["runId"],
            "caseId": case["caseId"],
            "armId": arm["armId"],
            "variantId": variant_id,
            "replicate": replicate_index,
            "generatedAt": utc_now(),
            **comparison,
        }
        write_json(replicate_dir / "comparison.json", comparison_payload)

    result_payload: Dict[str, Any] = {
        "runId": run["runId"],
        "caseId": case["caseId"],
        "armId": arm["armId"],
        "variantId": variant_id,
        "replicate": replicate_index,
        "mode": result["mode"],
        "provider": result.get("provider"),
        "providerCapabilities": result.get("providerCapabilities"),
        "answerPath": result.get("answerPath") if arm["type"] == "steered" else "off",
        "contextMode": arm["runtime"].get("contextMode"),
        "modeState": result.get("modeState", {}),
        "usage": result["usage"],
        "publicAnswer": public_answer,
        "answer": result.get("answer"),
        "directBaseline": result.get("directBaseline"),
        "answerHealth": answer_health,
        "baselineQuality": baseline_quality,
        "baselineAnswerHealth": baseline_answer_health,
        "comparison": comparison,
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
        "answerPath": result.get("answerPath") if arm["type"] == "steered" else "off",
        "contextMode": arm["runtime"].get("contextMode"),
        "modeState": result.get("modeState", {}),
        "deterministic": deterministic,
        "quality": quality,
        "answerHealth": answer_health,
        "control": control,
        "baselineQuality": baseline_quality,
        "baselineAnswerHealth": baseline_answer_health,
        "comparison": comparison,
        "artifactIds": [entry["artifactId"] for entry in artifacts],
        "artifacts": artifacts,
        "updatedAt": utc_now(),
    }


def execute_run(root: Path, run_id: str) -> Dict[str, Any]:
    run_dir = root / "data" / "evals" / "runs" / run_id
    run_path = run_dir / "run.json"
    run = read_run(root, run_id)
    suite_path = root / "data" / "evals" / "suites" / f"{run['suiteId']}.json"
    suite = validate_suite_manifest(read_json(suite_path), suite_path)
    arm_map: Dict[str, Dict[str, Any]] = {}
    for arm_id in run.get("armIds", []):
        arm_path = root / "data" / "evals" / "arms" / f"{arm_id}.json"
        arm_map[arm_id] = validate_arm_manifest(read_json(arm_path), arm_path)
    auth_path = auth_file_path(root)
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
            "provider": arm["runtime"]["provider"],
            "summarizerProvider": arm["runtime"]["summarizerProvider"],
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
                        "answerPath": arm["runtime"]["directBaselineMode"] if arm["type"] == "steered" else "off",
                        "contextMode": arm["runtime"]["contextMode"],
                        "provider": arm["runtime"]["provider"],
                        "summarizerProvider": arm["runtime"]["summarizerProvider"],
                        "model": arm["runtime"]["model"],
                        "summarizerModel": arm["runtime"]["summarizerModel"],
                        "directProvider": arm["runtime"]["directProvider"],
                        "directModel": arm["runtime"]["directModel"],
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
        run_id = str(args.run_id).strip()
        try:
            run = read_run(root, run_id)
        except Exception:
            run = None
        if isinstance(run, dict):
            try:
                run["status"] = "error"
                run["completedAt"] = utc_now()
                run["error"] = str(error)
                run["traceback"] = traceback.format_exc()
                persist_run(root / "data" / "evals" / "runs" / run_id / "run.json", run)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
