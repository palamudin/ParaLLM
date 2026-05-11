from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import traceback
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import judge_learning, metadata as metadata_store
from backend.app.control import auth_file_path
from runtime.engine import (
    LoopRuntime,
    RuntimeErrorWithCode,
    auth_assignment_meta,
    coerce_bool,
    default_context_mode,
    default_direct_baseline_mode,
    default_target_timeout_config,
    default_timeout_mode,
    default_summarizer_harness,
    default_direct_harness,
    default_judge_model_for_provider,
    default_knowledgebase_config,
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
    parse_structured_output_text,
    normalize_direct_baseline_mode,
    normalize_direct_answer_payload,
    normalize_harness_config,
    normalize_knowledgebase_config,
    normalize_model_id,
    normalize_ollama_base_url,
    normalize_ollama_timeout_profile,
    normalize_target_timeout_config,
    normalize_provider_id,
    normalize_provider_routing_config,
    normalize_research_config,
    normalize_string_array_preserve_items,
    normalize_timeout_mode,
    normalize_usage_state,
    normalize_vetting_config,
    provider_capability_profile,
    task_workers,
    target_timeout_seconds,
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

LIVE_JUDGE_MAX_ATTEMPTS = 3
LIVE_JUDGE_RETRY_BASE_DELAY_SECONDS = 0.75
LIVE_JUDGE_TRANSIENT_STATUS_CODES = {408, 409, 425, 429, 502, 503, 504}
LIVE_JUDGE_TRANSIENT_MESSAGE_MARKERS = (
    "http 408",
    "http 409",
    "http 425",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "server_error",
    "rate limit",
    "rate_limit",
    "too many requests",
    "timeout",
    "timed out",
    "temporarily unavailable",
    "connection reset",
)


def default_judge_learning_config() -> Dict[str, Any]:
    return {
        "enabled": False,
        "bankId": "",
        "dryRun": False,
        "writeMode": "knowledgebase",
        "source": "judge_scores",
    }


def infer_judge_learning_bank_id(arms: Dict[str, Dict[str, Any]] | List[Dict[str, Any]]) -> str:
    arm_values = arms.values() if isinstance(arms, dict) else arms
    candidates: List[str] = []
    for arm in arm_values:
        if not isinstance(arm, dict):
            continue
        runtime_config = arm.get("runtime") if isinstance(arm.get("runtime"), dict) else {}
        knowledgebase_config = normalize_knowledgebase_config(
            runtime_config.get("knowledgebase") if isinstance(runtime_config.get("knowledgebase"), dict) else {}
        )
        bank_id = str(knowledgebase_config.get("bankId") or "").strip()
        if (
            bool(knowledgebase_config.get("enabled"))
            and bool(knowledgebase_config.get("includePersistent"))
            and bank_id
            and bank_id not in candidates
        ):
            candidates.append(bank_id)
    return candidates[0] if candidates else judge_learning.DEFAULT_LEARNING_BANK_ID


def normalize_judge_learning_config(config: Optional[Dict[str, Any]], arms: Dict[str, Dict[str, Any]] | List[Dict[str, Any]]) -> Dict[str, Any]:
    raw = config if isinstance(config, dict) else {}
    default = default_judge_learning_config()
    bank_id = str(raw.get("bankId") or raw.get("bank_id") or "").strip() or infer_judge_learning_bank_id(arms)
    write_mode = str(raw.get("writeMode") or raw.get("write_mode") or default["writeMode"]).strip().lower()
    if write_mode not in {"knowledgebase"}:
        write_mode = "knowledgebase"
    return {
        "enabled": coerce_bool(raw.get("enabled"), default["enabled"]),
        "bankId": bank_id,
        "dryRun": coerce_bool(raw.get("dryRun", raw.get("dry_run")), default["dryRun"]),
        "writeMode": write_mode,
        "source": str(raw.get("source") or default["source"]).strip() or default["source"],
    }


def compact_judge_learning_result(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schemaVersion": str(result.get("schemaVersion") or judge_learning.SCHEMA_VERSION),
        "generatedAt": str(result.get("generatedAt") or ""),
        "dryRun": bool(result.get("dryRun")),
        "bankId": str(result.get("bankId") or ""),
        "runIds": normalize_string_array_preserve_items(result.get("runIds", []))[:12],
        "scoreFilesSeen": int(result.get("scoreFilesSeen") or 0),
        "scoreFilesLearned": int(result.get("scoreFilesLearned") or 0),
        "learnedRecordCount": int(result.get("learnedRecordCount") or 0),
        "write": result.get("write") if isinstance(result.get("write"), dict) else {},
        "librarian": result.get("librarian") if isinstance(result.get("librarian"), dict) else {},
        "warnings": normalize_string_array_preserve_items(result.get("warnings", []))[:12],
    }

QUALITY_SCORE_ALIASES = {
    "decisiveness": "decisiveness",
    "decisivenessscore": "decisiveness",
    "tradeoffhandling": "tradeoffHandling",
    "trade_off_handling": "tradeoffHandling",
    "tradeoffscore": "tradeoffHandling",
    "objectionabsorption": "objectionAbsorption",
    "objection_absorption": "objectionAbsorption",
    "actionability": "actionability",
    "actionabilityscore": "actionability",
    "singlevoice": "singleVoice",
    "single_voice": "singleVoice",
    "overallquality": "overallQuality",
    "overall_quality": "overallQuality",
    "overall": "overallQuality",
}

ANSWER_HEALTH_SCORE_ALIASES = {
    "instructionfit": "instructionFit",
    "instruction_fit": "instructionFit",
    "structuralclarity": "structuralClarity",
    "structural_clarity": "structuralClarity",
    "confidencecalibration": "confidenceCalibration",
    "confidence_calibration": "confidenceCalibration",
    "evidencehygiene": "evidenceHygiene",
    "evidence_hygiene": "evidenceHygiene",
    "efficiencydiscipline": "efficiencyDiscipline",
    "efficiency_discipline": "efficiencyDiscipline",
    "overallhealth": "overallHealth",
    "overall_health": "overallHealth",
    "overall": "overallHealth",
}

CONTROL_SCORE_ALIASES = {
    "leadcontrol": "leadControl",
    "lead_control": "leadControl",
    "adversarialdiscipline": "adversarialDiscipline",
    "adversarial_discipline": "adversarialDiscipline",
    "selfcheckquality": "selfCheckQuality",
    "self_check_quality": "selfCheckQuality",
    "nonfunnelintegration": "nonFunnelIntegration",
    "non_funnel_integration": "nonFunnelIntegration",
    "overallcontrol": "overallControl",
    "overall_control": "overallControl",
    "overall": "overallControl",
}

COMPARISON_SCORE_ALIASES = {
    "materialdifference": "materialDifference",
    "material_difference": "materialDifference",
    "decisionshift": "decisionShift",
    "decision_shift": "decisionShift",
    "validationstrength": "validationStrength",
    "validation_strength": "validationStrength",
    "operationalseparation": "operationalSeparation",
    "operational_separation": "operationalSeparation",
    "overalldifferentiation": "overallDifferentiation",
    "overall_differentiation": "overallDifferentiation",
    "overall": "overallDifferentiation",
}

VETTING_MATRIX_SCORE_FIELDS = [
    "blastRadiusPerception",
    "humanUsability",
    "agentExecutability",
    "commsAndIncidentDiscipline",
    "tacticalDetail",
    "restraintAndCollateral",
    "decisionGates",
    "firstHourRealism",
    "overall",
]

VETTING_MATRIX_SCORE_LABELS = {
    "blastRadiusPerception": "Blast path & tenant-boundary perception",
    "humanUsability": "Operator usability under pressure",
    "agentExecutability": "Tenant-safe executability",
    "commsAndIncidentDiscipline": "Comms & incident-record discipline",
    "tacticalDetail": "Evidence & action detail",
    "restraintAndCollateral": "Collateral & compliance restraint",
    "decisionGates": "Decision / escalation gates",
    "firstHourRealism": "First-hour MSP realism",
    "overall": "Lead hireability",
}

VETTING_ADVANTAGE_BANDS = ["tied", "narrow", "clear", "decisive"]
VETTING_HIRE_VERDICTS = ["hire", "hire_with_supervision", "not_for_lead", "disqualifying"]
VETTING_ALL_HIRE_VERDICTS = VETTING_HIRE_VERDICTS + ["unknown"]

VETTING_SCORE_FIELD_ALIASES = {
    "blastRadiusPerception": "blastRadiusPerception",
    "blast_radius_perception": "blastRadiusPerception",
    "blastRadius": "blastRadiusPerception",
    "humanUsability": "humanUsability",
    "human_usability": "humanUsability",
    "agentExecutability": "agentExecutability",
    "agent_executability": "agentExecutability",
    "aiAgentExecutability": "agentExecutability",
    "ai_agent_executability": "agentExecutability",
    "aiAgentExecutable": "agentExecutability",
    "commsAndIncidentDiscipline": "commsAndIncidentDiscipline",
    "comms_and_incident_discipline": "commsAndIncidentDiscipline",
    "communicationsAndIncidentDiscipline": "commsAndIncidentDiscipline",
    "communications_and_incident_discipline": "commsAndIncidentDiscipline",
    "incidentRecordDiscipline": "commsAndIncidentDiscipline",
    "incident_record_discipline": "commsAndIncidentDiscipline",
    "commsDiscipline": "commsAndIncidentDiscipline",
    "communicationsSafety": "commsAndIncidentDiscipline",
    "communications_safety": "commsAndIncidentDiscipline",
    "tacticalDetail": "tacticalDetail",
    "tactical_detail": "tacticalDetail",
    "restraintAndCollateral": "restraintAndCollateral",
    "restraint_and_collateral": "restraintAndCollateral",
    "restraint_collateral": "restraintAndCollateral",
    "restraintCollateralControl": "restraintAndCollateral",
    "restraint_collateral_control": "restraintAndCollateral",
    "restraint": "restraintAndCollateral",
    "decisionGates": "decisionGates",
    "decision_gates": "decisionGates",
    "firstHourRealism": "firstHourRealism",
    "first_hour_realism": "firstHourRealism",
    "overall": "overall",
    "overallQuality": "overall",
    "overall_quality": "overall",
}

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


def compact_dir_component(value: str, prefix: str, max_length: int = 32) -> str:
    cleaned = sanitize_id(value)
    max_length = max(16, int(max_length or 32))
    if len(cleaned) <= max_length:
        return cleaned
    digest = hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()[:8]
    head_budget = max(6, max_length - len(prefix) - len(digest) - 2)
    head = cleaned[:head_budget].strip("-_") or prefix
    return f"{prefix}-{head}-{digest}"


def replicate_dir_for(run_dir: Path, case_id: str, variant_id: str, replicate_index: int) -> Path:
    return (
        run_dir
        / "cases"
        / compact_dir_component(case_id, "case", 32)
        / compact_dir_component(variant_id, "variant", 36)
        / f"replicate-{replicate_index:03d}"
    )


def build_task_id(seed: str) -> str:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()[:6]
    # Keep eval task ids short so Windows artifact paths stay below common
    # MAX_PATH limits inside nested run/case/replicate workspaces.
    return f"te-{digest}"


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


def _normalize_live_score_number(value: Any) -> int:
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        candidate = 0.0
    candidate = max(0.0, min(10.0, candidate))
    return int(round(candidate))


def _extract_live_score_block(
    parsed: Any,
    field_names: List[str],
    aliases: Dict[str, str],
    *,
    minimum_fields: int = 3,
) -> Dict[str, int]:
    source = parsed if isinstance(parsed, dict) else {}
    normalized = {field: 0 for field in field_names}
    populated = 0
    candidate_blocks: List[Any] = []
    if isinstance(source.get("scores"), dict):
        candidate_blocks.append(source.get("scores"))
    candidate_blocks.append(source)
    if isinstance(source.get("scores"), list):
        candidate_blocks.append(source.get("scores"))

    for block in candidate_blocks:
        if isinstance(block, dict):
            for raw_key, raw_value in block.items():
                key = str(raw_key).strip()
                canonical = aliases.get(key, aliases.get(key.lower()))
                if not canonical or canonical not in normalized:
                    continue
                value = _normalize_live_score_number(raw_value)
                if value > 0 and normalized[canonical] <= 0:
                    populated += 1
                normalized[canonical] = max(normalized[canonical], value)
        elif isinstance(block, list):
            for item in block:
                if not isinstance(item, dict):
                    continue
                field_key = str(item.get("field") or item.get("name") or item.get("id") or "").strip()
                canonical = aliases.get(field_key, aliases.get(field_key.lower()))
                if not canonical or canonical not in normalized:
                    continue
                value = _normalize_live_score_number(item.get("score"))
                if value <= 0:
                    value = _normalize_live_score_number(item.get("value"))
                if value > 0 and normalized[canonical] <= 0:
                    populated += 1
                normalized[canonical] = max(normalized[canonical], value)

    overall_field = field_names[-1] if field_names else ""
    if overall_field and normalized.get(overall_field, 0) <= 0:
        component_values = [normalized[field] for field in field_names if field != overall_field and normalized[field] > 0]
        if component_values:
            normalized[overall_field] = int(round(mean(component_values)))
            populated += 1

    if populated < minimum_fields:
        raise RuntimeErrorWithCode("Live judge returned no usable score payload.", 500)
    return normalized


def missing_judge_audit_fields(payload: Dict[str, Any], required_fields: List[str]) -> List[str]:
    return [field for field in required_fields if not str(payload.get(field, "") or "").strip()]


def require_judge_audit_text(
    payload: Dict[str, Any],
    required_fields: List[str],
    judge_label: str,
    *,
    raw_output_text: str = "",
) -> None:
    missing = missing_judge_audit_fields(payload, required_fields)
    if not missing:
        return
    error = RuntimeErrorWithCode(
        f"Live {judge_label} judge returned score-only payload; missing audit fields: {', '.join(missing)}.",
        500,
    )
    error.raw_output_text = str(raw_output_text or "")
    error.failure_kind = "score_only_judge"
    raise error


def _error_status_code(error: RuntimeErrorWithCode) -> int:
    try:
        return int(getattr(error, "status_code", 0) or 0)
    except (TypeError, ValueError):
        return 0


def is_transient_live_judge_error(error: RuntimeErrorWithCode) -> bool:
    if str(getattr(error, "failure_kind", "") or "").strip():
        return False
    message = str(error or "").lower()
    if "live judge returned" in message or "score-only payload" in message:
        return False
    if any(marker in message for marker in LIVE_JUDGE_TRANSIENT_MESSAGE_MARKERS):
        return True
    return _error_status_code(error) in LIVE_JUDGE_TRANSIENT_STATUS_CODES


def live_judge_retry_delay_seconds(attempt_number: int) -> float:
    attempt_index = max(0, int(attempt_number or 1) - 1)
    return min(6.0, LIVE_JUDGE_RETRY_BASE_DELAY_SECONDS * (2**attempt_index))


def run_live_judge_with_transient_retries(
    call_judge: Callable[[], Dict[str, Any]],
    persist_failure: Callable[[RuntimeErrorWithCode], None],
    *,
    max_attempts: int = LIVE_JUDGE_MAX_ATTEMPTS,
) -> Dict[str, Any]:
    attempts = max(1, int(max_attempts or 1))
    last_error: Optional[RuntimeErrorWithCode] = None
    for attempt_number in range(1, attempts + 1):
        try:
            return call_judge()
        except RuntimeErrorWithCode as error:
            last_error = error
            persist_failure(error)
            if attempt_number >= attempts or not is_transient_live_judge_error(error):
                raise
            time.sleep(live_judge_retry_delay_seconds(attempt_number))
    if last_error is not None:
        raise last_error
    raise RuntimeErrorWithCode("Live judge retry loop exited unexpectedly.", 500)


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
            "hireVerdicts",
            "hardFailFlags",
            "trapFindings",
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
            "hireVerdicts": {
                "type": "object",
                "additionalProperties": False,
                "required": normalized_ids,
                "properties": {
                    answer_id: {"type": "string", "enum": VETTING_HIRE_VERDICTS}
                    for answer_id in normalized_ids
                },
            },
            "hardFailFlags": {
                "type": "object",
                "additionalProperties": False,
                "required": normalized_ids,
                "properties": {
                    answer_id: {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                    for answer_id in normalized_ids
                },
            },
            "trapFindings": {
                "type": "object",
                "additionalProperties": False,
                "required": normalized_ids,
                "properties": {
                    answer_id: {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["triggered", "caught", "missed"],
                        "properties": {
                            "triggered": {"type": "array", "items": {"type": "string"}},
                            "caught": {"type": "array", "items": {"type": "string"}},
                            "missed": {"type": "array", "items": {"type": "string"}},
                        },
                    }
                    for answer_id in normalized_ids
                },
            },
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


def _normalize_vetting_score_block(score_block: Any) -> Dict[str, float]:
    source = score_block if isinstance(score_block, dict) else {}
    normalized_block = {field: 0.0 for field in VETTING_MATRIX_SCORE_FIELDS}
    for raw_key, raw_value in source.items():
        key = str(raw_key or "").strip()
        alias_candidates = [
            key,
            key.lower(),
            key.replace("-", "_"),
            key.lower().replace("-", "_"),
            key.replace("-", ""),
            key.lower().replace("-", ""),
        ]
        canonical_key = ""
        for candidate in alias_candidates:
            canonical_key = VETTING_SCORE_FIELD_ALIASES.get(candidate, "")
            if canonical_key:
                break
        if canonical_key:
            normalized_block[canonical_key] = normalize_vetting_score_value(raw_value)
    if normalized_block["overall"] <= 0:
        average_without_overall = mean([normalized_block[field] for field in VETTING_MATRIX_SCORE_FIELDS if field != "overall"])
        normalized_block["overall"] = normalize_vetting_score_value(average_without_overall)
    return normalized_block


def _has_populated_vetting_score_block(score_block: Any) -> bool:
    normalized_block = _normalize_vetting_score_block(score_block)
    return any(float(normalized_block.get(field, 0.0) or 0.0) > 0.0 for field in VETTING_MATRIX_SCORE_FIELDS)


def _collect_recursive_vetting_score_blocks(payload: Any, normalized_ids: List[str]) -> Dict[str, Any]:
    collected: Dict[str, Any] = {}

    def visit(node: Any) -> None:
        if len(collected) >= len(normalized_ids):
            return
        if isinstance(node, dict):
            inline_answer_id = _normalize_vetting_answer_id(
                node.get("answer_id") or node.get("id") or node.get("answer") or node.get("slot"),
                normalized_ids,
            )
            inline_scores = node.get("scores") if isinstance(node.get("scores"), dict) else None
            if inline_answer_id in normalized_ids and inline_answer_id not in collected and inline_scores is not None and _has_populated_vetting_score_block(inline_scores):
                collected[inline_answer_id] = inline_scores
            for raw_key, value in node.items():
                nested_answer_id = _normalize_vetting_answer_id(raw_key, normalized_ids)
                if nested_answer_id in normalized_ids and nested_answer_id not in collected and isinstance(value, dict):
                    nested_scores = value.get("scores") if isinstance(value.get("scores"), dict) else value
                    if _has_populated_vetting_score_block(nested_scores):
                        collected[nested_answer_id] = nested_scores
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return collected


def _normalize_vetting_answer_id(candidate: Any, normalized_ids: List[str]) -> str:
    raw = str(candidate or "").strip()
    if not raw:
        return ""
    if raw in normalized_ids:
        return raw
    lowered = raw.lower()
    for answer_id in normalized_ids:
        if lowered == str(answer_id).strip().lower():
            return answer_id
    compact = re.sub(r"[\s\-]+", "_", lowered)
    if compact.startswith("answer_"):
        compact = compact[len("answer_"):]
    if compact.startswith("candidate_"):
        compact = compact[len("candidate_"):]
    compact = compact.strip("_")
    for answer_id in normalized_ids:
        if compact == str(answer_id).strip().lower():
            return answer_id
    return ""


def _extract_vetting_score_matrix(parsed: Dict[str, Any], normalized_ids: List[str]) -> Dict[str, Dict[str, float]]:
    parsed_scores = parsed.get("scores")
    if isinstance(parsed_scores, dict):
        normalized_score_lookup: Dict[str, Any] = {}
        for raw_answer_id, candidate_block in parsed_scores.items():
            if not isinstance(candidate_block, dict):
                continue
            normalized_answer_id = _normalize_vetting_answer_id(raw_answer_id, normalized_ids)
            if normalized_answer_id and normalized_answer_id not in normalized_score_lookup:
                normalized_score_lookup[normalized_answer_id] = candidate_block
        if normalized_score_lookup:
            score_matrix: Dict[str, Dict[str, float]] = {}
            for answer_id in normalized_ids:
                candidate_block = normalized_score_lookup.get(answer_id)
                score_matrix[answer_id] = _normalize_vetting_score_block(candidate_block)
            return score_matrix
    normalized_top_level_lookup: Dict[str, Any] = {}
    for raw_answer_id, candidate_block in parsed.items():
        if not isinstance(candidate_block, dict):
            continue
        normalized_answer_id = _normalize_vetting_answer_id(raw_answer_id, normalized_ids)
        if normalized_answer_id and normalized_answer_id not in normalized_top_level_lookup:
            normalized_top_level_lookup[normalized_answer_id] = candidate_block
    if normalized_top_level_lookup:
        score_matrix = {}
        for answer_id in normalized_ids:
            candidate_block = normalized_top_level_lookup.get(answer_id)
            nested_scores = candidate_block.get("scores") if isinstance(candidate_block, dict) and isinstance(candidate_block.get("scores"), dict) else candidate_block
            score_matrix[answer_id] = _normalize_vetting_score_block(nested_scores)
        return score_matrix
    evaluation_node = parsed.get("evaluation")
    if isinstance(evaluation_node, dict):
        evaluation_scores = evaluation_node.get("scores") if isinstance(evaluation_node.get("scores"), dict) else evaluation_node
        normalized_score_lookup = {}
        if isinstance(evaluation_scores, dict):
            for raw_answer_id, candidate_block in evaluation_scores.items():
                normalized_answer_id = _normalize_vetting_answer_id(raw_answer_id, normalized_ids)
                if normalized_answer_id and normalized_answer_id not in normalized_score_lookup:
                    normalized_score_lookup[normalized_answer_id] = candidate_block
        score_matrix = {}
        for answer_id in normalized_ids:
            candidate_block = normalized_score_lookup.get(answer_id)
            score_matrix[answer_id] = _normalize_vetting_score_block(candidate_block)
        return score_matrix

    candidate_lists: List[Any] = []
    if isinstance(parsed_scores, list):
        candidate_lists.append(parsed_scores)
    if isinstance(parsed.get("verdicts"), list):
        candidate_lists.append(parsed.get("verdicts"))
    if isinstance(parsed.get("evaluations"), list):
        candidate_lists.append(parsed.get("evaluations"))
    if isinstance(parsed.get("answers"), list):
        candidate_lists.append(parsed.get("answers"))

    for candidate_list in candidate_lists:
        score_matrix = {}
        for item in candidate_list:
            if not isinstance(item, dict):
                continue
            answer_id = _normalize_vetting_answer_id(
                item.get("id") or item.get("answer") or item.get("slot") or item.get("answer_id"),
                normalized_ids,
            )
            if answer_id not in normalized_ids:
                continue
            nested_scores = item.get("scores") if isinstance(item.get("scores"), dict) else None
            score_matrix[answer_id] = _normalize_vetting_score_block(nested_scores if nested_scores is not None else item)
        if score_matrix:
            return {
                answer_id: score_matrix.get(answer_id, _normalize_vetting_score_block({}))
                for answer_id in normalized_ids
            }

    recursive_score_lookup = _collect_recursive_vetting_score_blocks(parsed, normalized_ids)
    if recursive_score_lookup:
        return {
            answer_id: _normalize_vetting_score_block(recursive_score_lookup.get(answer_id))
            for answer_id in normalized_ids
        }

    return {answer_id: _normalize_vetting_score_block({}) for answer_id in normalized_ids}


def _extract_vetting_answer_notes(parsed: Dict[str, Any], normalized_ids: List[str]) -> Dict[str, str]:
    answer_notes_raw = parsed.get("answerNotes") if isinstance(parsed.get("answerNotes"), dict) else {}
    if isinstance(answer_notes_raw, dict):
        direct_notes = {}
        for answer_id in normalized_ids:
            value = answer_notes_raw.get(answer_id)
            if value is None:
                value = answer_notes_raw.get(str(answer_id).lower())
            if value is None:
                value = answer_notes_raw.get(f"answer_{str(answer_id).lower()}")
            direct_notes[answer_id] = truncate_text(value or "", 320)
        if any(direct_notes.values()):
            return direct_notes
    notes_node = parsed.get("notes")
    if isinstance(notes_node, dict):
        direct_notes = {}
        for answer_id in normalized_ids:
            value = notes_node.get(answer_id)
            if value is None:
                value = notes_node.get(str(answer_id).lower())
            if value is None:
                value = notes_node.get(f"answer_{str(answer_id).lower()}")
            direct_notes[answer_id] = truncate_text(value or "", 320)
        if any(direct_notes.values()):
            return direct_notes
    evaluation_node = parsed.get("evaluation") if isinstance(parsed.get("evaluation"), dict) else {}
    if evaluation_node:
        extracted = {
            answer_id: truncate_text(
                (
                    ((evaluation_node.get(answer_id) or {}) if isinstance(evaluation_node.get(answer_id), dict) else {}).get("note", "")
                    or ((evaluation_node.get(answer_id) or {}) if isinstance(evaluation_node.get(answer_id), dict) else {}).get("notes", "")
                ),
                320,
            )
            for answer_id in normalized_ids
        }
        if not any(extracted.values()):
            extracted = {}
            for answer_id in normalized_ids:
                node = evaluation_node.get(answer_id)
                if node is None:
                    node = evaluation_node.get(str(answer_id).lower())
                if node is None:
                    node = evaluation_node.get(f"answer_{str(answer_id).lower()}")
                note_text = ""
                if isinstance(node, dict):
                    note_text = str(node.get("note") or node.get("notes") or "").strip()
                extracted[answer_id] = truncate_text(note_text, 320)
        if any(extracted.values()):
            return extracted
    top_level_notes = {}
    for answer_id in normalized_ids:
        node = parsed.get(f"candidate_{str(answer_id).lower()}") or parsed.get(answer_id)
        note_text = ""
        if isinstance(node, dict):
            note_text = str(node.get("summary") or node.get("note") or node.get("notes") or "").strip()
        top_level_notes[answer_id] = truncate_text(note_text, 320)
    if any(top_level_notes.values()):
        return top_level_notes

    notes: Dict[str, str] = {answer_id: "" for answer_id in normalized_ids}
    candidate_lists = []
    if isinstance(parsed.get("verdicts"), list):
        candidate_lists.append(parsed.get("verdicts"))
    if isinstance(parsed.get("evaluations"), list):
        candidate_lists.append(parsed.get("evaluations"))
    if isinstance(parsed.get("scores"), list):
        candidate_lists.append(parsed.get("scores"))
    if isinstance(parsed.get("answers"), list):
        candidate_lists.append(parsed.get("answers"))
    for candidate_list in candidate_lists:
        for item in candidate_list:
            if not isinstance(item, dict):
                continue
            answer_id = _normalize_vetting_answer_id(
                item.get("id") or item.get("answer") or item.get("slot") or item.get("answer_id"),
                normalized_ids,
            )
            if answer_id not in normalized_ids:
                continue
            note_parts = []
            commentary = str(
                item.get("commentary", "")
                or item.get("reasoning", "")
                or item.get("note", "")
                or item.get("notes", "")
                or item.get("best_for_rationale", "")
            ).strip()
            if commentary:
                note_parts.append(commentary)
            strengths = item.get("strengths")
            if isinstance(strengths, list) and strengths:
                note_parts.append("Strengths: " + "; ".join([str(entry).strip() for entry in strengths if str(entry).strip()]))
            weaknesses = item.get("weaknesses")
            if isinstance(weaknesses, list) and weaknesses:
                note_parts.append("Weaknesses: " + "; ".join([str(entry).strip() for entry in weaknesses if str(entry).strip()]))
            strengths_text = str(item.get("strengths", "")).strip() if not isinstance(strengths, list) else ""
            weaknesses_text = str(item.get("weaknesses", "")).strip() if not isinstance(weaknesses, list) else ""
            if strengths_text:
                note_parts.append("Strengths: " + strengths_text)
            if weaknesses_text:
                note_parts.append("Weaknesses: " + weaknesses_text)
            if note_parts:
                notes[answer_id] = truncate_text(" ".join(note_parts), 320)
        if any(notes.values()):
            return notes
    return notes


def _normalize_vetting_hire_verdict(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "hire": "hire",
        "strong_hire": "hire",
        "hire_with_supervision": "hire_with_supervision",
        "hire_with_guardrails": "hire_with_supervision",
        "supervised_hire": "hire_with_supervision",
        "not_for_lead": "not_for_lead",
        "no_hire": "not_for_lead",
        "do_not_hire": "not_for_lead",
        "not_hireable": "not_for_lead",
        "disqualifying": "disqualifying",
        "hard_fail": "disqualifying",
        "red_card": "disqualifying",
    }
    return aliases.get(raw, "unknown")


def _extract_vetting_hire_verdicts(parsed: Dict[str, Any], normalized_ids: List[str]) -> Dict[str, str]:
    verdicts = {answer_id: "unknown" for answer_id in normalized_ids}
    candidate_nodes: List[Any] = []
    for key in ("hireVerdicts", "hire_verdicts"):
        node = parsed.get(key)
        if node is not None:
            candidate_nodes.append(node)
    for key in ("answers", "verdicts", "scores", "evaluations"):
        node = parsed.get(key)
        if isinstance(node, list):
            candidate_nodes.append(node)
    evaluation_node = parsed.get("evaluation")
    if isinstance(evaluation_node, dict):
        candidate_nodes.append(evaluation_node)
    candidate_nodes.append(parsed)
    for node in candidate_nodes:
        if isinstance(node, dict):
            for raw_key, raw_value in node.items():
                answer_id = _normalize_vetting_answer_id(raw_key, normalized_ids)
                if answer_id not in normalized_ids:
                    continue
                verdict = _normalize_vetting_hire_verdict(
                    (
                        raw_value.get("hireVerdict")
                        or raw_value.get("hire_verdict")
                        or raw_value.get("candidateVerdict")
                    ) if isinstance(raw_value, dict) else raw_value
                )
                if verdict != "unknown":
                    verdicts[answer_id] = verdict
        elif isinstance(node, list):
            for item in node:
                if not isinstance(item, dict):
                    continue
                answer_id = _normalize_vetting_answer_id(
                    item.get("id") or item.get("answer") or item.get("slot") or item.get("answer_id"),
                    normalized_ids,
                )
                if answer_id not in normalized_ids:
                    continue
                verdict = _normalize_vetting_hire_verdict(
                    item.get("hireVerdict") or item.get("hire_verdict") or item.get("candidateVerdict")
                )
                if verdict != "unknown":
                    verdicts[answer_id] = verdict
    return verdicts


def _normalize_vetting_string_list(value: Any, *, limit: int = 8) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()][:limit]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in re.split(r"[;\n]+", value) if part.strip()][:limit]
    return []


def _extract_vetting_hard_fail_flags(parsed: Dict[str, Any], normalized_ids: List[str]) -> Dict[str, List[str]]:
    flags = {answer_id: [] for answer_id in normalized_ids}
    direct_node = parsed.get("hardFailFlags") if isinstance(parsed.get("hardFailFlags"), dict) else parsed.get("hard_fail_flags")
    if isinstance(direct_node, dict):
        for raw_key, raw_value in direct_node.items():
            answer_id = _normalize_vetting_answer_id(raw_key, normalized_ids)
            if answer_id in normalized_ids:
                flags[answer_id] = _normalize_vetting_string_list(raw_value)
    for key in ("answers", "verdicts", "scores", "evaluations"):
        node = parsed.get(key)
        if not isinstance(node, list):
            continue
        for item in node:
            if not isinstance(item, dict):
                continue
            answer_id = _normalize_vetting_answer_id(
                item.get("id") or item.get("answer") or item.get("slot") or item.get("answer_id"),
                normalized_ids,
            )
            if answer_id not in normalized_ids:
                continue
            extracted = _normalize_vetting_string_list(
                item.get("hardFailFlags") or item.get("hard_fail_flags") or item.get("disqualifiers") or item.get("redFlags")
            )
            if extracted:
                flags[answer_id] = extracted
    for raw_key, raw_value in parsed.items():
        if not isinstance(raw_value, dict):
            continue
        answer_id = _normalize_vetting_answer_id(raw_key, normalized_ids)
        if answer_id not in normalized_ids:
            continue
        extracted = _normalize_vetting_string_list(
            raw_value.get("hardFailFlags") or raw_value.get("hard_fail_flags") or raw_value.get("disqualifiers") or raw_value.get("redFlags")
        )
        if extracted:
            flags[answer_id] = extracted
    return flags


def _extract_vetting_trap_findings(parsed: Dict[str, Any], normalized_ids: List[str]) -> Dict[str, Dict[str, List[str]]]:
    findings = {
        answer_id: {"triggered": [], "caught": [], "missed": []}
        for answer_id in normalized_ids
    }
    direct_node = parsed.get("trapFindings") if isinstance(parsed.get("trapFindings"), dict) else parsed.get("trap_findings")
    if isinstance(direct_node, dict):
        for raw_key, raw_value in direct_node.items():
            answer_id = _normalize_vetting_answer_id(raw_key, normalized_ids)
            if answer_id not in normalized_ids or not isinstance(raw_value, dict):
                continue
            findings[answer_id] = {
                "triggered": _normalize_vetting_string_list(raw_value.get("triggered")),
                "caught": _normalize_vetting_string_list(raw_value.get("caught")),
                "missed": _normalize_vetting_string_list(raw_value.get("missed")),
            }
    for key in ("answers", "verdicts", "scores", "evaluations"):
        node = parsed.get(key)
        if not isinstance(node, list):
            continue
        for item in node:
            if not isinstance(item, dict):
                continue
            answer_id = _normalize_vetting_answer_id(
                item.get("id") or item.get("answer") or item.get("slot") or item.get("answer_id"),
                normalized_ids,
            )
            if answer_id not in normalized_ids:
                continue
            trap_node = item.get("trapFindings") or item.get("trap_findings") or item.get("traps")
            if not isinstance(trap_node, dict):
                continue
            findings[answer_id] = {
                "triggered": _normalize_vetting_string_list(trap_node.get("triggered")),
                "caught": _normalize_vetting_string_list(trap_node.get("caught")),
                "missed": _normalize_vetting_string_list(trap_node.get("missed")),
            }
    for raw_key, raw_value in parsed.items():
        if not isinstance(raw_value, dict):
            continue
        answer_id = _normalize_vetting_answer_id(raw_key, normalized_ids)
        if answer_id not in normalized_ids:
            continue
        trap_node = raw_value.get("trapFindings") or raw_value.get("trap_findings") or raw_value.get("traps")
        if isinstance(trap_node, dict):
            if all(key in trap_node for key in ("triggered", "caught", "missed")):
                findings[answer_id] = {
                    "triggered": _normalize_vetting_string_list(trap_node.get("triggered")),
                    "caught": _normalize_vetting_string_list(trap_node.get("caught")),
                    "missed": _normalize_vetting_string_list(trap_node.get("missed")),
                }
                continue
            triggered: List[str] = []
            caught: List[str] = []
            missed: List[str] = []
            for trap_name, trap_value in trap_node.items():
                label = str(trap_name or "").strip().replace("_", " ")
                detail = str(trap_value or "").strip().lower()
                if not label:
                    continue
                if any(token in detail for token in ("avoid", "avoided", "caught")):
                    caught.append(label)
                elif any(token in detail for token in ("miss", "missed")):
                    missed.append(label)
                elif any(token in detail for token in ("trigger", "violation", "violated", "hard fail", "failed")):
                    triggered.append(label)
            if triggered or caught or missed:
                findings[answer_id] = {
                    "triggered": _normalize_vetting_string_list(triggered),
                    "caught": _normalize_vetting_string_list(caught),
                    "missed": _normalize_vetting_string_list(missed),
                }
    return findings


def _extract_vetting_ranking(parsed: Dict[str, Any], normalized_ids: List[str], score_matrix: Dict[str, Dict[str, float]]) -> List[str]:
    ranking = [
        normalized
        for normalized in (_normalize_vetting_answer_id(answer_id, normalized_ids) for answer_id in parsed.get("ranking", []))
        if normalized
    ]
    if not ranking:
        rankings_node = parsed.get("rankings")
        if isinstance(rankings_node, list):
            ranking = [
                normalized
                for normalized in (_normalize_vetting_answer_id(answer_id, normalized_ids) for answer_id in rankings_node)
                if normalized
            ]
        elif isinstance(rankings_node, dict):
            for key in ("overall", "final", "bestFinalAnswer"):
                candidate_list = rankings_node.get(key)
                if isinstance(candidate_list, list):
                    ranking = [
                        normalized
                        for normalized in (_normalize_vetting_answer_id(answer_id, normalized_ids) for answer_id in candidate_list)
                        if normalized
                    ]
                    if ranking:
                        break
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
    return ranking


def _extract_vetting_choice(parsed: Dict[str, Any], ranking: List[str], field_names: List[str], fallback_index: int = 0) -> str:
    comparisons_node = parsed.get("comparisons") if isinstance(parsed.get("comparisons"), dict) else {}
    evaluation_node = parsed.get("evaluation") if isinstance(parsed.get("evaluation"), dict) else {}
    verdict_node = parsed.get("verdict") if isinstance(parsed.get("verdict"), dict) else {}
    for field_name in field_names:
        aliases = [field_name]
        snake_case = re.sub(r"(?<!^)([A-Z])", r"_\1", field_name).lower()
        if snake_case not in aliases:
            aliases.append(snake_case)
        if field_name == "bestFinalAnswer" and "best_answer" not in aliases:
            aliases.append("best_answer")
        if snake_case and f"{snake_case}_answer" not in aliases:
            aliases.append(f"{snake_case}_answer")
        if snake_case.endswith("_answer"):
            base_alias = snake_case[: -len("_answer")]
            if base_alias and base_alias not in aliases:
                aliases.append(base_alias)
        for alias in aliases:
            candidate = _normalize_vetting_answer_id(parsed.get(alias, ""), ranking)
            if candidate in ranking:
                return candidate
            candidate = _normalize_vetting_answer_id(comparisons_node.get(alias, ""), ranking)
            if candidate in ranking:
                return candidate
            candidate = _normalize_vetting_answer_id(evaluation_node.get(alias, ""), ranking)
            if candidate in ranking:
                return candidate
            candidate = _normalize_vetting_answer_id(verdict_node.get(alias, ""), ranking)
            if candidate in ranking:
                return candidate
    if evaluation_node:
        for answer_id in ranking:
            node = evaluation_node.get(answer_id)
            if node is None:
                node = evaluation_node.get(str(answer_id).lower())
            if node is None:
                node = evaluation_node.get(f"answer_{str(answer_id).lower()}")
            if not isinstance(node, dict):
                continue
            if any(
                bool(node.get(flag))
                for flag in ([field_names[0], re.sub(r"(?<!^)([A-Z])", r"_\1", field_names[0]).lower()] if field_names else [])
            ):
                return answer_id
    return ranking[min(fallback_index, len(ranking) - 1)]


def build_vetting_advantage_summary(score_matrix: Dict[str, Dict[str, float]], ranking: List[str]) -> Dict[str, Any]:
    if not ranking:
        return {
            "leader": "",
            "runnerUp": "",
            "leaderOverall": 0.0,
            "runnerUpOverall": 0.0,
            "overallMargin": 0.0,
            "uniqueCategoryLeads": 0,
            "sharedCategoryLeads": 0,
            "band": "tied",
        }
    leader = ranking[0]
    runner_up = ranking[1] if len(ranking) > 1 else ""
    leader_overall = float((score_matrix.get(leader) or {}).get("overall", 0.0) or 0.0)
    runner_up_overall = float((score_matrix.get(runner_up) or {}).get("overall", 0.0) or 0.0) if runner_up else 0.0
    overall_margin = round(leader_overall - runner_up_overall, 2)
    unique_category_leads = 0
    shared_category_leads = 0
    for field in VETTING_MATRIX_SCORE_FIELDS:
        field_values = {
            answer_id: float((score_block or {}).get(field, 0.0) or 0.0)
            for answer_id, score_block in score_matrix.items()
        }
        if not field_values:
            continue
        best_value = max(field_values.values())
        leaders = [answer_id for answer_id, value in field_values.items() if value == best_value]
        if leader in leaders:
            if len(leaders) == 1:
                unique_category_leads += 1
            else:
                shared_category_leads += 1
    band = "tied"
    if overall_margin >= 1.0 or unique_category_leads >= 5:
        band = "decisive"
    elif overall_margin >= 0.5 or unique_category_leads >= 3:
        band = "clear"
    elif overall_margin > 0.0 or unique_category_leads >= 1 or shared_category_leads >= 1:
        band = "narrow"
    return {
        "leader": leader,
        "runnerUp": runner_up,
        "leaderOverall": round(leader_overall, 2),
        "runnerUpOverall": round(runner_up_overall, 2),
        "overallMargin": overall_margin,
        "uniqueCategoryLeads": unique_category_leads,
        "sharedCategoryLeads": shared_category_leads,
        "band": band if band in VETTING_ADVANTAGE_BANDS else "tied",
    }


def _extract_vetting_rationale(parsed: Dict[str, Any], answer_notes: Dict[str, str], best_final_answer: str) -> str:
    direct_node = parsed.get("rationale")
    direct = ""
    if isinstance(direct_node, str):
        direct = direct_node.strip()
    elif isinstance(direct_node, dict):
        for key in ("summary", "overall", "explanation", "rationale", "text", "key_differentiator", "bestFinalAnswer", "bestTacticalDetail", "best_final_answer", "best_tactical_detail"):
            candidate = str(direct_node.get(key, "")).strip()
            if candidate:
                direct = candidate
                break
        if not direct and best_final_answer:
            normalized_key = _normalize_vetting_answer_id(best_final_answer, [best_final_answer]) or best_final_answer
            best_answer_keys = [
                normalized_key,
                str(normalized_key).lower(),
                f"answer_{str(normalized_key).lower()}",
            ]
            for key in best_answer_keys:
                candidate = str(direct_node.get(key, "")).strip()
                if candidate:
                    direct = candidate
                    break
    if not direct:
        notes_node = parsed.get("notes")
        if isinstance(notes_node, str):
            direct = notes_node.strip()
        elif isinstance(notes_node, dict):
            for key in ("summary", "overall", "explanation", "rationale", "text"):
                candidate = str(notes_node.get(key, "")).strip()
                if candidate:
                    direct = candidate
                    break
    if direct:
        return truncate_text(direct, 1600)
    reasoning_node = parsed.get("reasoning")
    if isinstance(reasoning_node, str) and reasoning_node.strip():
        return truncate_text(reasoning_node.strip(), 1600)
    if isinstance(reasoning_node, dict):
        for key in ("tiebreaker rationale", "tiebreaker_rationale", "summary", "overall", "explanation", "text"):
            candidate = str(reasoning_node.get(key, "")).strip()
            if candidate:
                return truncate_text(candidate, 1600)
    evaluator_notes = str(parsed.get("evaluator_notes") or "").strip()
    if evaluator_notes:
        return truncate_text(evaluator_notes, 1600)
    verdict_node = parsed.get("verdict")
    if isinstance(verdict_node, dict):
        for key in ("rationale", "summary", "overall", "explanation", "text"):
            candidate = str(verdict_node.get(key, "")).strip()
            if candidate:
                return truncate_text(candidate, 1600)
    for key in ("best_answer_summary", "best_tactical_detail_rationale"):
        candidate = str(parsed.get(key) or "").strip()
        if candidate:
            return truncate_text(candidate, 1600)
    scoring_notes_node = parsed.get("scoring_notes")
    if isinstance(scoring_notes_node, dict):
        for key in ("differentiation", "summary", "overall", "explanation", "text", "non_scoring_notes"):
            candidate = str(scoring_notes_node.get(key, "")).strip()
            if candidate:
                return truncate_text(candidate, 1600)
    evaluation_node = parsed.get("evaluation") if isinstance(parsed.get("evaluation"), dict) else {}
    if evaluation_node:
        justification = evaluation_node.get("justification")
        if isinstance(justification, dict):
            preferred = [
                str(justification.get("best_final_answer") or "").strip(),
                str(justification.get("best_tactical_detail") or "").strip(),
                str(justification.get("summary") or "").strip(),
                str(justification.get("overall") or "").strip(),
            ]
            for candidate in preferred:
                if candidate:
                    return truncate_text(candidate, 1600)
    comparisons_node = parsed.get("comparisons") if isinstance(parsed.get("comparisons"), dict) else {}
    comparison_direct_node = comparisons_node.get("rationale")
    comparison_direct = ""
    if isinstance(comparison_direct_node, str):
        comparison_direct = comparison_direct_node.strip()
    elif isinstance(comparison_direct_node, dict):
        for key in ("summary", "overall", "explanation", "rationale", "text", "bestFinalAnswer", "bestTacticalDetail", "best_final_answer", "best_tactical_detail"):
            candidate = str(comparison_direct_node.get(key, "")).strip()
            if candidate:
                comparison_direct = candidate
                break
    if comparison_direct:
        return truncate_text(comparison_direct, 1600)
    differential_rationale = str(parsed.get("differential_rationale") or "").strip()
    if differential_rationale:
        return truncate_text(differential_rationale, 1600)
    comparison_summary = str(parsed.get("comparison_summary") or "").strip()
    if comparison_summary:
        return truncate_text(comparison_summary, 1600)
    text_candidates: List[str] = []

    def visit(node: Any, depth: int = 0) -> None:
        if depth > 6:
            return
        if isinstance(node, dict):
            for raw_key, value in node.items():
                key = str(raw_key or "").strip().lower()
                if isinstance(value, str):
                    text = value.strip()
                    if text and any(token in key for token in ("rationale", "summary", "explanation", "notes", "differentiator")):
                        text_candidates.append(text)
                else:
                    visit(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                visit(item, depth + 1)

    visit(parsed)
    for candidate in text_candidates:
        if candidate:
            return truncate_text(candidate, 1600)
    note = str(answer_notes.get(best_final_answer, "")).strip()
    if note:
        return truncate_text(note, 1600)
    return ""


def normalize_vetting_matrix_result(parsed: Dict[str, Any], answer_ids: List[str], response_id: Optional[str] = None) -> Dict[str, Any]:
    normalized_ids = [str(answer_id or "").strip() for answer_id in answer_ids if str(answer_id or "").strip()]
    score_matrix = _extract_vetting_score_matrix(parsed, normalized_ids)
    ranking = _extract_vetting_ranking(parsed, normalized_ids, score_matrix)
    answer_notes = _extract_vetting_answer_notes(parsed, normalized_ids)
    hire_verdicts = _extract_vetting_hire_verdicts(parsed, normalized_ids)
    hard_fail_flags = _extract_vetting_hard_fail_flags(parsed, normalized_ids)
    trap_findings = _extract_vetting_trap_findings(parsed, normalized_ids)
    best_final_answer = _extract_vetting_choice(parsed, ranking, ["bestFinalAnswer", "bestFinal"], 0)
    best_tactical_detail = _extract_vetting_choice(parsed, ranking, ["bestTacticalDetail"], 0)
    advantage_summary = build_vetting_advantage_summary(score_matrix, ranking)
    rationale = _extract_vetting_rationale(parsed, answer_notes, best_final_answer)

    return {
        "scores": score_matrix,
        "ranking": ranking,
        "bestFinalAnswer": best_final_answer,
        "bestTacticalDetail": best_tactical_detail,
        "hireVerdicts": hire_verdicts,
        "hardFailFlags": hard_fail_flags,
        "trapFindings": trap_findings,
        "answerNotes": answer_notes,
        "categoryLeaders": vetting_category_leaders(score_matrix),
        "advantageSummary": advantage_summary,
        "rationale": rationale,
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
    execution_mode = str(runtime_payload.get("executionMode", "live")).strip().lower() or "live"
    if execution_mode != "live":
        raise EvalError(f"Arm {arm_id} uses unsupported executionMode {execution_mode!r}; eval arms must run live.")
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
    knowledgebase_payload = runtime_payload.get("knowledgebase") if isinstance(runtime_payload.get("knowledgebase"), dict) else None
    knowledgebase = normalize_knowledgebase_config(knowledgebase_payload if isinstance(knowledgebase_payload, dict) else {})
    preferred_loop = normalize_loop_preferences(runtime_payload.get("preferredLoop") if isinstance(runtime_payload.get("preferredLoop"), dict) else {})
    target_timeouts = normalize_target_timeout_config(
        runtime_payload.get("targetTimeouts") if isinstance(runtime_payload.get("targetTimeouts"), dict) else {}
    )
    provider_routing = normalize_provider_routing_config(
        runtime_payload.get("providerRouting") if isinstance(runtime_payload.get("providerRouting"), dict) else {}
    )
    ollama_base_url = normalize_ollama_base_url(runtime_payload.get("ollamaBaseUrl", default_ollama_base_url()))
    summarizer_harness = normalize_harness_config(
        runtime_payload.get("summarizerHarness", default_summarizer_harness()),
        default_summarizer_harness()["concision"],
    )
    direct_harness = normalize_harness_config(
        runtime_payload.get("directHarness", default_direct_harness()),
        default_direct_harness()["concision"],
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
            "providerRouting": provider_routing,
            "summarizerProvider": summarizer_provider,
            "summarizerModel": summarizer_model,
            "summarizerHarness": summarizer_harness,
            "directHarness": direct_harness,
            "reasoningEffort": reasoning_effort,
            "budget": budget,
            "research": research,
            "vetting": vetting,
            "knowledgebase": knowledgebase,
            "knowledgebaseExplicit": isinstance(knowledgebase_payload, dict),
            "preferredLoop": preferred_loop,
            "targetTimeouts": target_timeouts,
            "requireLive": True,
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
            "directHarness": deepcopy(runtime_config["directHarness"]),
            "ollamaBaseUrl": runtime_config["ollamaBaseUrl"],
            "providerRouting": deepcopy(runtime_config["providerRouting"]),
            "reasoningEffort": runtime_config["reasoningEffort"],
            "budget": deepcopy(runtime_config["budget"]),
            "research": deepcopy(runtime_config["research"]),
            "vetting": deepcopy(runtime_config["vetting"]),
            "knowledgebase": deepcopy(runtime_config.get("knowledgebase", default_knowledgebase_config())),
            "targetTimeouts": deepcopy(runtime_config["targetTimeouts"]),
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


def hydrate_eval_knowledgebase(runtime: LoopRuntime, runtime_config: Dict[str, Any]) -> List[str]:
    """Copy explicitly requested persistent eval memory banks into the isolated runtime workspace."""
    if not runtime_config.get("knowledgebaseExplicit"):
        return []
    config = normalize_knowledgebase_config(runtime_config.get("knowledgebase") if isinstance(runtime_config.get("knowledgebase"), dict) else {})
    if not config["enabled"] or not config["includePersistent"]:
        return []

    config_root = Path(getattr(runtime, "config_root", getattr(runtime, "root", Path(".")))).resolve()
    runtime_root = Path(getattr(runtime, "root", Path("."))).resolve()
    source_banks_root = config_root / "data" / "knowledgebase" / "banks"
    dest_banks_root = runtime_root / "data" / "knowledgebase" / "banks"
    if not source_banks_root.is_dir():
        return []

    if config["bankId"]:
        source_banks = [source_banks_root / config["bankId"]]
    else:
        source_banks = [path for path in source_banks_root.iterdir() if path.is_dir()]

    copied: List[str] = []
    for source_bank in source_banks:
        if not source_bank.is_dir():
            continue
        dest_bank = dest_banks_root / source_bank.name
        try:
            if source_bank.resolve() == dest_bank.resolve():
                continue
        except FileNotFoundError:
            pass
        for source_file in source_bank.rglob("*"):
            if not source_file.is_file():
                continue
            relative = source_file.relative_to(source_bank)
            target_file = dest_bank / relative
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
        copied.append(source_bank.name)
    return copied


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
    with runtime.with_lock():
        runtime.initialize_task_state_unlocked(task, state)


def build_offline_fixture_direct_answer(case: Dict[str, Any]) -> Dict[str, Any]:
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
        "confidenceNote": f"Offline fixture answer for {title}; useful for eval plumbing, not factual confidence.",
    }


def run_direct_answer(
    runtime: LoopRuntime,
    auth_assignments: Optional[List[Dict[str, Any]]],
    case: Dict[str, Any],
    arm: Dict[str, Any],
) -> Dict[str, Any]:
    provider = str(arm["runtime"].get("provider") or "openai").strip()
    hydrate_eval_knowledgebase(runtime, arm["runtime"])
    primary_assignment = (
        dict(auth_assignments[0])
        if isinstance(auth_assignments, list) and auth_assignments and isinstance(auth_assignments[0], dict)
        else None
    )
    api_key = str(primary_assignment.get("apiKey")) if isinstance(primary_assignment, dict) else ""
    if provider == "openai" and not api_key:
        api_key = runtime.get_api_key()
    if provider != "openai":
        api_key = runtime.provider_live_api_key(provider, auth_assignments)
    auth_meta = runtime.live_auth_meta(provider, primary_assignment)
    runtime_config = arm["runtime"]
    model = runtime_config["model"]
    reasoning_effort = runtime_config["reasoningEffort"]
    runtime_budget = runtime_config.get("budget") if isinstance(runtime_config.get("budget"), dict) else {}
    requested_max_output = int(runtime_budget.get("maxOutputTokens", 0) or 0)
    prompt_packet = build_direct_answer_prompt(case, runtime_config, runtime=runtime)
    instructions = prompt_packet["instructions"]
    input_text = prompt_packet["inputText"]
    if not (runtime_config["executionMode"] == "live" and (api_key or not runtime.provider_requires_api_key(provider))):
        runtime.raise_live_stage_missing_credentials(
            stage="eval_direct_answer",
            target_label="direct_baseline",
            task_id=sanitize_id(str(case.get("caseId") or "eval-direct")),
            auth_meta=auth_meta,
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
                auth_assignments=auth_assignments,
                provider_settings=runtime_config,
                task_id=sanitize_id(str(case.get("caseId") or "eval-direct")),
            )
            usage = runtime.get_response_usage_delta(result.response, model) or default_usage_state()
            normalized_answer = normalize_direct_answer_payload(
                result.parsed,
                case.get("objective", ""),
                provider=provider,
            )
            return {
                "mode": "live",
                "provider": provider,
                "providerCapabilities": provider_capability_profile(provider),
                "model": model,
                "inputText": prompt_packet["inputText"],
                "fullPrompt": prompt_packet["fullPrompt"],
                "answer": normalized_answer,
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
        except RuntimeErrorWithCode as error:
            persist_failed_call_from_error(
                runtime,
                error,
                task_id=sanitize_id(str(case.get("caseId") or "eval-direct")),
                target_kind="generic",
                provider=provider,
                model=model,
                schema_name="eval_direct_answer",
                max_output_tokens=requested_max_output,
            )
            raise
    raise RuntimeErrorWithCode("Live direct eval did not produce a validated answer.", 502)


def answer_path_call_plan(answer_path: str, worker_count: int, loop_rounds: int) -> Dict[str, Any]:
    normalized_path = normalize_direct_baseline_mode(answer_path, default_direct_baseline_mode())
    rounds = max(1, int(loop_rounds or 1))
    workers = max(0, int(worker_count or 0))
    nodes: List[str] = []
    if normalized_path in {"single", "both"}:
        nodes.append("direct_baseline")
    if normalized_path != "single":
        for round_index in range(1, rounds + 1):
            prefix = f"round{round_index}"
            nodes.append(f"{prefix}:commander")
            nodes.extend(f"{prefix}:worker:{worker_index + 1}" for worker_index in range(workers))
            nodes.append(f"{prefix}:commander_review")
            nodes.append(f"{prefix}:summarizer")
    return {
        "answerPath": normalized_path,
        "loopRounds": rounds,
        "workerCount": workers,
        "plannedVendorCalls": len(nodes),
        "nodes": nodes,
        "scope": "answer_generation_only",
        "excludes": ["quality_judge", "answer_health_judge", "control_judge", "comparison_judge", "judge_learning_librarian"],
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
    hydrate_eval_knowledgebase(runtime, arm["runtime"])
    initialize_steered_workspace(runtime, task)
    worker_ids = [worker["id"] for worker in task_workers(task)]
    answer_path = normalize_direct_baseline_mode(arm["runtime"].get("directBaselineMode"), default_direct_baseline_mode())
    call_plan = answer_path_call_plan(answer_path, len(worker_ids), loop_rounds)

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
    previous_context = runtime.current_execution_context()
    runtime.set_execution_context(
        {
            **previous_context,
            "taskId": task["taskId"],
            "stateScopeTaskId": task["taskId"],
        }
    )
    try:
        state = runtime.read_state()
    finally:
        runtime.set_execution_context(previous_context)
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
            str(direct_baseline.get("mode", "unknown")).strip().lower()
            if answer_path == "single" and isinstance(direct_baseline, dict)
            else ("live" if summary_mode and usage.get("totalTokens", 0) else "unknown")
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
        "answerPathCallPlan": call_plan,
    }


def judge_provider_settings(run: Dict[str, Any], judge_provider: str) -> Dict[str, Any]:
    runtime_settings = run.get("judgeRuntime") if isinstance(run.get("judgeRuntime"), dict) else {}
    provider = normalize_provider_id(judge_provider, "openai")
    settings: Dict[str, Any] = {
        "requestTimeoutSeconds": target_timeout_seconds(default_target_timeout_config(), "arbiter"),
        "providerRouting": normalize_provider_routing_config(
            runtime_settings.get("providerRouting") if isinstance(runtime_settings.get("providerRouting"), dict) else {}
        ),
    }
    if provider == "ollama":
        settings["ollamaBaseUrl"] = normalize_ollama_base_url(runtime_settings.get("ollamaBaseUrl", default_ollama_base_url()))
        timeout_mode = normalize_timeout_mode(runtime_settings.get("timeoutMode"), default_timeout_mode())
        profile = normalize_ollama_timeout_profile(runtime_settings.get("ollamaTimeoutProfile"))
        if timeout_mode == "auto" and str(profile.get("status") or "") == "ready":
            settings["requestTimeoutSeconds"] = target_timeout_seconds(
                normalize_target_timeout_config(profile.get("targetTimeouts")),
                "arbiter",
            )
        else:
            settings["requestTimeoutSeconds"] = target_timeout_seconds(
                normalize_target_timeout_config(runtime_settings.get("targetTimeouts")),
                "arbiter",
            )
    else:
        settings["requestTimeoutSeconds"] = target_timeout_seconds(
            normalize_target_timeout_config(runtime_settings.get("targetTimeouts")),
            "arbiter",
        )
    return settings


def invoke_live_judge_json(
    runtime: LoopRuntime,
    judge_provider: str,
    api_key: str,
    judge_model: str,
    instructions: str,
    input_text: str,
    schema_name: str,
    schema: Dict[str, Any],
    max_output_tokens: int,
    provider_settings: Optional[Dict[str, Any]] = None,
):
    return runtime.invoke_provider_json(
        provider=judge_provider,
        api_key=api_key,
        model=judge_model,
        reasoning_effort="high",
        instructions=instructions,
        input_text=input_text,
        schema_name=schema_name,
        schema=schema,
        max_output_tokens=max_output_tokens,
        target_kind="arbiter",
        provider_settings=provider_settings or {},
        task_id=sanitize_id(str(schema_name or "eval-judge")),
    )


def persist_failed_call_from_error(
    runtime: LoopRuntime,
    error: RuntimeErrorWithCode,
    *,
    task_id: str,
    target_kind: str,
    provider: str,
    model: str,
    schema_name: str,
    max_output_tokens: int = 0,
) -> Optional[Dict[str, Any]]:
    existing = getattr(error, "failed_call_artifact", None)
    if isinstance(existing, dict):
        return existing
    if not hasattr(runtime, "write_failed_call_artifact"):
        return None
    raw_output_text = str(getattr(error, "raw_output_text", "") or "")
    failure_kind = str(getattr(error, "failure_kind", "") or "")
    artifact = runtime.write_failed_call_artifact(
        task_id=task_id,
        target_kind=target_kind,
        provider=provider,
        model=model,
        schema_name=schema_name,
        error=error,
        raw_output_text=raw_output_text,
        requested_max_output_tokens=max_output_tokens,
        failure_kind=failure_kind,
    )
    error.failed_call_artifact = artifact
    return artifact


def format_prompt_value(value: Any, depth: int = 0) -> str:
    indent = "  " * depth
    if value is None:
        return indent + "none"
    if isinstance(value, list):
        lines: List[str] = []
        for item in value:
            if isinstance(item, (list, dict)):
                lines.append(f"{indent}-")
                nested = format_prompt_value(item, depth + 1)
                lines.extend(nested.splitlines())
            else:
                text = str(item or "").strip()
                if text:
                    lines.append(f"{indent}- {text}")
        return "\n".join(lines) if lines else indent + "- none"
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            key_label = re.sub(r"(?<!^)([A-Z])", r" \1", str(key or "")).replace("_", " ").strip() or "item"
            if isinstance(item, (list, dict)):
                lines.append(f"{indent}- {key_label}:")
                nested = format_prompt_value(item, depth + 1)
                lines.extend(nested.splitlines())
            else:
                item_text = str(item or "").strip() or "none"
                lines.append(f"{indent}- {key_label}: {item_text}")
        return "\n".join(lines) if lines else indent + "- none"
    text = str(value or "").strip()
    return indent + (text or "none")


def format_prompt_section(title: str, body: str) -> str:
    normalized_title = str(title or "").strip() or "Section"
    normalized_body = str(body or "").strip() or "none"
    return f"{normalized_title}:\n{normalized_body}"


def format_candidate_answer_packets(answers: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for answer in answers:
        blocks.append(
            "\n".join(
                [
                    f"Answer {str(answer.get('id', '')).strip() or '?'}",
                    str(answer.get("text", "")).strip() or "No answer captured.",
                ]
            ).strip()
        )
    return "\n\n".join(blocks).strip() or "No candidate answers supplied."


def build_direct_answer_prompt(
    case: Dict[str, Any],
    runtime_config: Dict[str, Any],
    runtime: Optional[LoopRuntime] = None,
) -> Dict[str, Any]:
    harness_lines = direct_baseline_harness_instruction_lines(
        runtime_config.get("directHarness", default_direct_harness())
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
    sections = [
        format_prompt_section("Objective", str(case.get("objective") or "").strip()),
        format_prompt_section("Constraints", format_prompt_value(case.get("constraints", []))),
        format_prompt_section("Session context", str(case.get("sessionContext", "") or "none").strip() or "none"),
    ]
    if runtime_config.get("knowledgebaseExplicit") and runtime is not None and hasattr(runtime, "build_knowledgebase_recall_packet"):
        task = {
            "taskId": sanitize_id(str(case.get("caseId") or "eval-direct")),
            "objective": str(case.get("objective") or "").strip(),
            "constraints": list(case.get("constraints", [])) if isinstance(case.get("constraints"), list) else [],
            "sessionContext": str(case.get("sessionContext") or "").strip(),
            "runtime": {"knowledgebase": deepcopy(runtime_config.get("knowledgebase", default_knowledgebase_config()))},
        }
        knowledgebase_packet = runtime.build_knowledgebase_recall_packet(
            task,
            task["runtime"],
            "direct_baseline",
            label="Direct Baseline",
            role="direct_answer",
            focus="single-thread user-facing answer",
            constraints=task["constraints"],
        )
        sections.append(runtime.render_knowledgebase_prompt_block(knowledgebase_packet).strip())
    input_text = "\n\n".join(sections).strip()
    return {
        "instructions": instructions,
        "inputText": input_text,
        "fullPrompt": f"Instructions:\n{instructions}\n\n{input_text}".strip(),
    }


def quality_judge_live(
    runtime: LoopRuntime,
    judge_provider: str,
    api_key: str,
    judge_model: str,
    case: Dict[str, Any],
    judge_rubric: Any,
    public_answer: str,
    provider_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    instructions = (
        "You are grading one candidate assistant answer to a benchmark prompt.\n"
        "Score from 1 to 10 on each quality dimension.\n"
        "Reward decisiveness, tradeoff handling, objection absorption, actionability, and a clean single assistant voice.\n"
        "Use the hidden rubric and gold notes as guidance, but do not require exact wording.\n"
        "Every narrative field must be a non-empty sentence; never return empty strings for verdict, strengths, weaknesses, or rationale.\n"
        "Return JSON only that matches the schema."
    )
    input_text = "\n\n".join(
        [
            format_prompt_section("Objective", str(case.get("objective") or "").strip()),
            format_prompt_section("Constraints", format_prompt_value(case.get("constraints", []))),
            format_prompt_section("Hidden rubric", format_prompt_value(judge_rubric)),
            format_prompt_section("Hidden gold guidance", format_prompt_value(case.get("gold", {}))),
            format_prompt_section("Candidate answer", str(public_answer or "").strip()),
        ]
    ).strip()
    result = invoke_live_judge_json(
        runtime,
        judge_provider,
        api_key,
        judge_model,
        instructions,
        input_text,
        "eval_quality_judge",
        quality_judge_schema(),
        1400,
        provider_settings,
    )
    parsed = result.parsed
    scores = _extract_live_score_block(parsed, QUALITY_SCORE_FIELDS, QUALITY_SCORE_ALIASES)
    require_judge_audit_text(
        parsed,
        ["verdict", "strongestStrength", "strongestWeakness", "rationale"],
        "quality",
        raw_output_text=str(result.output_text or ""),
    )
    return {
        "mode": "live",
        "scores": scores,
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
        "mode": "heuristic",
        "scores": quality_scores,
        "verdict": "Heuristic quality estimate.",
        "strongestStrength": "Clear recommendation" if has_recommendation else "Readable structure",
        "strongestWeakness": "Needs a more operational next step" if not has_next_step else "Needs stronger objection absorption",
        "rationale": "Heuristic judge used structural quality signals because no live judge model was available.",
        "responseId": None,
    }


def answer_health_judge_live(
    runtime: LoopRuntime,
    judge_provider: str,
    api_key: str,
    judge_model: str,
    case: Dict[str, Any],
    public_answer: str,
    telemetry: Dict[str, Any],
    provider_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    instructions = (
        "You are grading the operational health of one candidate assistant answer.\n"
        "Score from 1 to 10 on instruction fit, structural clarity, confidence calibration, evidence hygiene, and efficiency/discipline.\n"
        "Use telemetry as supporting context, not as a substitute for reading the answer.\n"
        "Every narrative field must be a non-empty sentence; never return empty strings for verdict, strengths, weaknesses, or rationale.\n"
        "Return JSON only that matches the schema."
    )
    input_text = "\n\n".join(
        [
            format_prompt_section("Objective", str(case.get("objective") or "").strip()),
            format_prompt_section("Constraints", format_prompt_value(case.get("constraints", []))),
            format_prompt_section("Answer telemetry", format_prompt_value(telemetry)),
            format_prompt_section("Candidate answer", str(public_answer or "").strip()),
        ]
    ).strip()
    result = invoke_live_judge_json(
        runtime,
        judge_provider,
        api_key,
        judge_model,
        instructions,
        input_text,
        "eval_answer_health_judge",
        answer_health_judge_schema(),
        1200,
        provider_settings,
    )
    parsed = result.parsed
    scores = _extract_live_score_block(parsed, ANSWER_HEALTH_SCORE_FIELDS, ANSWER_HEALTH_SCORE_ALIASES)
    require_judge_audit_text(
        parsed,
        ["verdict", "strongestStrength", "strongestWeakness", "rationale"],
        "answer-health",
        raw_output_text=str(result.output_text or ""),
    )
    return {
        "mode": "live",
        "scores": scores,
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
        "mode": "heuristic",
        "scores": scores,
        "verdict": "Heuristic answer-health estimate.",
        "strongestStrength": "The answer stays structurally disciplined." if scores["instructionFit"] >= 8 else "Some structural discipline is present.",
        "strongestWeakness": "Efficiency/calibration signals are weak." if scores["efficiencyDiscipline"] <= 5 else "Evidence handling remains structurally inferred without a live judge.",
        "rationale": "Heuristic judge used telemetry and structural cues because no live judge model was available.",
        "responseId": None,
        "telemetry": telemetry,
    }


def control_judge_live(
    runtime: LoopRuntime,
    judge_provider: str,
    api_key: str,
    judge_model: str,
    case: Dict[str, Any],
    summary: Dict[str, Any],
    provider_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    front_answer = summary.get("frontAnswer", {}) if isinstance(summary.get("frontAnswer"), dict) else {}
    opinion = summary.get("summarizerOpinion", {}) if isinstance(summary.get("summarizerOpinion"), dict) else {}
    control_audit = summary.get("controlAudit", {}) if isinstance(summary.get("controlAudit"), dict) else {}
    instructions = (
        "You are grading whether a lead assistant thread stayed in control of adversarial pressure.\n"
        "Reward answers where the lead direction is clear, accepted objections are selective, rejected pressure is actually rejected, and the self-check is meaningful.\n"
        "Penalize funnel-like behavior where internal pressure is merely forwarded or averaged into the final answer.\n"
        "Every narrative field must be a non-empty sentence; never return empty strings for verdict, strengths, weaknesses, or rationale.\n"
        "Return JSON only that matches the schema."
    )
    input_text = "\n\n".join(
        [
            format_prompt_section("Objective", str(case.get("objective") or "").strip()),
            format_prompt_section("Constraints", format_prompt_value(case.get("constraints", []))),
            format_prompt_section("Public answer", str(front_answer.get("answer", "") or "").strip()),
            format_prompt_section("Lead direction", str(front_answer.get("leadDirection", "") or "").strip()),
            format_prompt_section("Absorbed adversarial pressure", str(front_answer.get("adversarialPressure", "") or "").strip()),
            format_prompt_section("Current stance", str(opinion.get("stance", "") or "").strip()),
            format_prompt_section("Integration mode", str(opinion.get("integrationMode", "") or "").strip()),
            format_prompt_section("Lead draft before pressure", str(control_audit.get("leadDraft", "") or "").strip()),
            format_prompt_section("Control question", str(control_audit.get("integrationQuestion", "") or "").strip()),
            format_prompt_section("Accepted adversarial points", format_prompt_value(control_audit.get("acceptedAdversarialPoints", []))),
            format_prompt_section("Rejected adversarial points", format_prompt_value(control_audit.get("rejectedAdversarialPoints", []))),
            format_prompt_section("Held-out concerns", format_prompt_value(control_audit.get("heldOutConcerns", []))),
            format_prompt_section("Pre-release self-check", str(control_audit.get("selfCheck", "") or "").strip()),
        ]
    ).strip()
    result = invoke_live_judge_json(
        runtime,
        judge_provider,
        api_key,
        judge_model,
        instructions,
        input_text,
        "eval_control_judge",
        control_judge_schema(),
        1400,
        provider_settings,
    )
    parsed = result.parsed
    scores = _extract_live_score_block(parsed, CONTROL_SCORE_FIELDS, CONTROL_SCORE_ALIASES)
    require_judge_audit_text(
        parsed,
        ["verdict", "strongestControlStrength", "strongestControlWeakness", "rationale"],
        "control",
        raw_output_text=str(result.output_text or ""),
    )
    return {
        "mode": "live",
        "scores": scores,
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
        "mode": "heuristic",
        "scores": scores,
        "verdict": "Heuristic control estimate.",
        "strongestControlStrength": "Lead-thread structure is explicit." if scores["leadControl"] >= 8 else "Some control audit fields are present.",
        "strongestControlWeakness": "Public answer still leaks process." if mentions_process else "Control is only structurally inferred without a live judge.",
        "rationale": "Heuristic control judge used structural signals because no live judge model was available.",
        "responseId": None,
    }


def run_quality_judge(
    judge_runtime: LoopRuntime,
    judge_provider: str,
    api_key: Optional[str],
    judge_model: str,
    case: Dict[str, Any],
    judge_rubric: Any,
    public_answer: str,
    provider_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if api_key or not judge_runtime.provider_requires_api_key(judge_provider):
        def call_judge() -> Dict[str, Any]:
            result = quality_judge_live(judge_runtime, judge_provider, api_key or "", judge_model, case, judge_rubric, public_answer, provider_settings)
            if not any(int((result.get("scores") or {}).get(field, 0) or 0) > 0 for field in QUALITY_SCORE_FIELDS):
                raise RuntimeErrorWithCode("Live judge returned no usable quality scores.", 500)
            require_judge_audit_text(result, ["verdict", "strongestStrength", "strongestWeakness", "rationale"], "quality")
            return result

        def persist_failure(error: RuntimeErrorWithCode) -> None:
            persist_failed_call_from_error(
                judge_runtime,
                error,
                task_id=sanitize_id(str(case.get("caseId") or "quality-judge")),
                target_kind="arbiter",
                provider=judge_provider,
                model=judge_model,
                schema_name="quality_judge",
            )

        return run_live_judge_with_transient_retries(call_judge, persist_failure)
    raise RuntimeErrorWithCode("Live quality judge requires a configured provider key.", 401)


def run_answer_health_judge(
    judge_runtime: LoopRuntime,
    judge_provider: str,
    api_key: Optional[str],
    judge_model: str,
    case: Dict[str, Any],
    public_answer: str,
    telemetry: Dict[str, Any],
    provider_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if api_key or not judge_runtime.provider_requires_api_key(judge_provider):
        def call_judge() -> Dict[str, Any]:
            result = answer_health_judge_live(judge_runtime, judge_provider, api_key or "", judge_model, case, public_answer, telemetry, provider_settings)
            if not any(int((result.get("scores") or {}).get(field, 0) or 0) > 0 for field in ANSWER_HEALTH_SCORE_FIELDS):
                raise RuntimeErrorWithCode("Live judge returned no usable answer-health scores.", 500)
            require_judge_audit_text(result, ["verdict", "strongestStrength", "strongestWeakness", "rationale"], "answer-health")
            return result

        def persist_failure(error: RuntimeErrorWithCode) -> None:
            persist_failed_call_from_error(
                judge_runtime,
                error,
                task_id=sanitize_id(str(case.get("caseId") or "answer-health-judge")),
                target_kind="arbiter",
                provider=judge_provider,
                model=judge_model,
                schema_name="answer_health_judge",
            )

        return run_live_judge_with_transient_retries(call_judge, persist_failure)
    raise RuntimeErrorWithCode("Live answer-health judge requires a configured provider key.", 401)


def run_control_judge(
    judge_runtime: LoopRuntime,
    judge_provider: str,
    api_key: Optional[str],
    judge_model: str,
    case: Dict[str, Any],
    summary: Dict[str, Any],
    provider_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if api_key or not judge_runtime.provider_requires_api_key(judge_provider):
        def call_judge() -> Dict[str, Any]:
            result = control_judge_live(judge_runtime, judge_provider, api_key or "", judge_model, case, summary, provider_settings)
            if not any(int((result.get("scores") or {}).get(field, 0) or 0) > 0 for field in CONTROL_SCORE_FIELDS):
                raise RuntimeErrorWithCode("Live judge returned no usable control scores.", 500)
            require_judge_audit_text(result, ["verdict", "strongestControlStrength", "strongestControlWeakness", "rationale"], "control")
            return result

        def persist_failure(error: RuntimeErrorWithCode) -> None:
            persist_failed_call_from_error(
                judge_runtime,
                error,
                task_id=sanitize_id(str(case.get("caseId") or "control-judge")),
                target_kind="arbiter",
                provider=judge_provider,
                model=judge_model,
                schema_name="control_judge",
            )

        return run_live_judge_with_transient_retries(call_judge, persist_failure)
    raise RuntimeErrorWithCode("Live control judge requires a configured provider key.", 401)


def comparison_judge_live(
    runtime: LoopRuntime,
    judge_provider: str,
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
    provider_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    instructions = (
        "You are comparing a pressurized multi-lane answer against a single-thread baseline for the same prompt.\n"
        "Judge whether the answers are materially different, whether the difference changes the operational decision, and whether one answer is genuinely better.\n"
        "Do not reward superficial paraphrase. If the answers mostly say the same thing, mark material difference low even if wording changes.\n"
        "Verdict must be exactly one of: pressurized_advantage, baseline_advantage, mixed.\n"
        "decisionRelation must be exactly one of: same_direction, refined_direction, different_direction, opposed_direction.\n"
        "Use the supplied quality/health summaries and similarity metrics as context, but base the verdict on the actual answer texts.\n"
        "Every narrative field must be a non-empty sentence; never return empty strings for verdict, edges, relation, or rationale.\n"
        "Return JSON only that matches the schema."
    )
    input_text = "\n\n".join(
        [
            format_prompt_section("Objective", str(case.get("objective") or "").strip()),
            format_prompt_section("Constraints", format_prompt_value(case.get("constraints", []))),
            format_prompt_section("Hidden rubric", format_prompt_value(judge_rubric)),
            format_prompt_section("Hidden gold guidance", format_prompt_value(case.get("gold", {}))),
            format_prompt_section("Pressurized answer quality summary", format_prompt_value(primary_quality)),
            format_prompt_section("Pressurized answer health summary", format_prompt_value(primary_health)),
            format_prompt_section("Baseline answer quality summary", format_prompt_value(baseline_quality)),
            format_prompt_section("Baseline answer health summary", format_prompt_value(baseline_health)),
            format_prompt_section("Similarity metrics", format_prompt_value(similarity)),
            format_prompt_section("Pressurized answer", str(primary_answer or "").strip()),
            format_prompt_section("Single-thread baseline answer", str(baseline_answer or "").strip()),
        ]
    ).strip()
    result = invoke_live_judge_json(
        runtime,
        judge_provider,
        api_key,
        judge_model,
        instructions,
        input_text,
        "eval_comparison_judge",
        comparison_judge_schema(),
        1600,
        provider_settings,
    )
    parsed = result.parsed
    scores = _extract_live_score_block(parsed, COMPARISON_SCORE_FIELDS, COMPARISON_SCORE_ALIASES)
    require_judge_audit_text(
        parsed,
        ["verdict", "decisionRelation", "primaryEdge", "baselineEdge", "rationale"],
        "comparison",
        raw_output_text=str(result.output_text or ""),
    )
    return {
        "mode": "live",
        "scores": scores,
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
        "mode": "heuristic",
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
    judge_provider: str,
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
    provider_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if api_key or not judge_runtime.provider_requires_api_key(judge_provider):
        def call_judge() -> Dict[str, Any]:
            result = comparison_judge_live(
                judge_runtime,
                judge_provider,
                api_key or "",
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
                provider_settings,
            )
            if not any(int((result.get("scores") or {}).get(field, 0) or 0) > 0 for field in COMPARISON_SCORE_FIELDS):
                raise RuntimeErrorWithCode("Live judge returned no usable comparison scores.", 500)
            require_judge_audit_text(result, ["verdict", "decisionRelation", "primaryEdge", "baselineEdge", "rationale"], "comparison")
            return result

        def persist_failure(error: RuntimeErrorWithCode) -> None:
            persist_failed_call_from_error(
                judge_runtime,
                error,
                task_id=sanitize_id(str(case.get("caseId") or "comparison-judge")),
                target_kind="arbiter",
                provider=judge_provider,
                model=judge_model,
                schema_name="comparison_judge",
            )

        return run_live_judge_with_transient_retries(call_judge, persist_failure)
    raise RuntimeErrorWithCode("Live comparison judge requires a configured provider key.", 401)


def vetting_matrix_judge_live(
    runtime: LoopRuntime,
    judge_provider: str,
    api_key: str,
    judge_model: str,
    case: Dict[str, Any],
    judge_rubric: Any,
    answers: List[Dict[str, Any]],
    provider_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_answers = [dict(answer) for answer in answers if isinstance(answer, dict) and str(answer.get("id", "")).strip()]
    if not normalized_answers:
        raise EvalError("Vetting matrix judge requires at least one answer.")
    answer_ids = [str(answer.get("id", "")).strip() for answer in normalized_answers]
    prompt_packet = build_vetting_matrix_judge_prompt(case, judge_rubric, normalized_answers)
    instructions = prompt_packet["instructions"]
    input_text = prompt_packet["inputText"]
    result = invoke_live_judge_json(
        runtime,
        judge_provider,
        api_key,
        judge_model,
        instructions,
        input_text,
        "eval_vetting_matrix_judge",
        vetting_matrix_judge_schema(answer_ids),
        2600,
        provider_settings,
    )
    parsed_payload = result.parsed if isinstance(result.parsed, dict) else {}
    if not any(
        float((score_block or {}).get("overall", 0.0) or 0.0) > 0.0
        for score_block in _extract_vetting_score_matrix(parsed_payload, answer_ids).values()
    ):
        raw_output = str(result.output_text or "").strip()
        if raw_output:
            try:
                reparsed = parse_structured_output_text(raw_output)
            except Exception:
                reparsed = {}
            if isinstance(reparsed, dict) and any(
                float((score_block or {}).get("overall", 0.0) or 0.0) > 0.0
                for score_block in _extract_vetting_score_matrix(reparsed, answer_ids).values()
            ):
                parsed_payload = reparsed
    normalized = normalize_vetting_matrix_result(parsed_payload, answer_ids, result.response_id)
    return {
        "mode": "live",
        "fullPrompt": prompt_packet["fullPrompt"],
        "inputText": prompt_packet["inputText"],
        "answerPackets": prompt_packet["answerPackets"],
        "rawOutputText": result.output_text,
        "responseMeta": {
            "provider": judge_provider,
            "model": judge_model,
            "requestedMaxOutputTokens": result.requested_max_output_tokens,
            "effectiveMaxOutputTokens": result.effective_max_output_tokens,
            "attempts": list(result.attempts or []),
            "recoveredFromIncomplete": bool(result.recovered_from_incomplete),
        },
        **normalized,
    }


def build_vetting_matrix_judge_prompt(
    case: Dict[str, Any],
    judge_rubric: Any,
    answers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized_answers = [dict(answer) for answer in answers if isinstance(answer, dict) and str(answer.get("id", "")).strip()]
    answer_packets = []
    for answer in normalized_answers:
        answer_packets.append(
            {
                "id": str(answer.get("id", "")).strip(),
                "costUsd": (
                    round(float(answer.get("costUsd", 0.0) or 0.0), 6)
                    if answer.get("costUsd") is not None
                    else None
                ),
                "costNote": str(answer.get("costNote", "")).strip() or None,
                "familyHint": str(answer.get("familyHint", "")).strip() or None,
                "text": str(answer.get("text", "")).strip(),
            }
        )
    instructions = (
        "Blindly evaluate the candidate answers to the same prompt as if you were vetting a lead MSP incident responder for a live multi-tenant severity-1 event.\n"
        "Use only the judge metric below plus the shared prompt, constraints, and answer texts.\n"
        "Score each answer from 0 to 10 in 0.5-point increments for every listed category.\n"
        "Record hire verdicts, hard-fail flags, and trap findings for each answer.\n"
        "An answer that triggers a hard fail should not win best final answer unless every answer hard-fails.\n"
        "Choose one best final answer and one best tactical detail answer.\n"
        "Return JSON only that matches the schema."
    )
    input_text = "\n\n".join(
        [
            format_prompt_section("Judge metric", format_prompt_value(judge_rubric)),
            format_prompt_section("Objective", str(case.get("objective") or "").strip()),
            format_prompt_section("Constraints", format_prompt_value(case.get("constraints", []))),
            format_prompt_section("Candidate answers", format_candidate_answer_packets(answer_packets)),
        ]
    ).strip()
    return {
        "instructions": instructions,
        "inputText": input_text,
        "answerPackets": answer_packets,
        "fullPrompt": f"Instructions:\n{instructions}\n\n{input_text}".strip(),
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


def normalize_required_concept_groups(checks: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_groups = checks.get("requiredConceptGroups")
    if not isinstance(raw_groups, list):
        return []
    groups: List[Dict[str, Any]] = []
    for index, raw in enumerate(raw_groups, start=1):
        if not isinstance(raw, dict):
            continue
        group_id = sanitize_id(str(raw.get("id") or f"concept-{index}").strip()) or f"concept-{index}"
        label = str(raw.get("label") or group_id).strip() or group_id
        any_of = [str(item).strip() for item in raw.get("anyOf", []) if str(item).strip()] if isinstance(raw.get("anyOf"), list) else []
        all_of = [str(item).strip() for item in raw.get("allOf", []) if str(item).strip()] if isinstance(raw.get("allOf"), list) else []
        if not any_of and not all_of:
            continue
        groups.append({"id": group_id, "label": label, "anyOf": any_of, "allOf": all_of})
    return groups


def evaluate_required_concept_groups(public_answer: str, checks: Dict[str, Any]) -> Dict[str, Any]:
    groups = normalize_required_concept_groups(checks)
    if not groups:
        return {"passed": True, "detail": "No required concept groups configured.", "groups": []}
    lowered_answer = public_answer.lower()
    results: List[Dict[str, Any]] = []
    for group in groups:
        any_of = list(group.get("anyOf") or [])
        all_of = list(group.get("allOf") or [])
        matched_any = [phrase for phrase in any_of if phrase.lower() in lowered_answer]
        missing_all = [phrase for phrase in all_of if phrase.lower() not in lowered_answer]
        any_passed = bool(matched_any) if any_of else True
        passed = any_passed and not missing_all
        results.append(
            {
                "id": group["id"],
                "label": group["label"],
                "passed": passed,
                "matchedAnyOf": matched_any[:8],
                "missingAnyOf": [] if any_passed else any_of[:12],
                "missingAllOf": missing_all[:12],
            }
        )
    missing = [item["label"] for item in results if not item["passed"]]
    return {
        "passed": not missing,
        "detail": "All required SOP concept groups were present." if not missing else f"Missing SOP concept groups: {', '.join(missing)}.",
        "groups": results,
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
    live_only_ok = all(mode == "live" for mode in mode_values if mode)
    max_paragraphs = int(checks.get("maxParagraphs", 0) or 0)
    paragraph_count = count_paragraphs(public_answer)
    required_phrases = [str(item).strip() for item in checks.get("requiredPhrases", []) if str(item).strip()] if isinstance(checks.get("requiredPhrases"), list) else []
    forbidden_phrases = [str(item).strip() for item in checks.get("forbiddenPhrases", []) if str(item).strip()] if isinstance(checks.get("forbiddenPhrases"), list) else []
    lowered_answer = public_answer.lower()
    missing_phrases = [phrase for phrase in required_phrases if phrase.lower() not in lowered_answer]
    found_forbidden = [phrase for phrase in forbidden_phrases if phrase.lower() in lowered_answer]
    token_ok = int(runtime_budget["maxTotalTokens"]) <= 0 or int(usage["totalTokens"]) <= int(runtime_budget["maxTotalTokens"])
    cost_ok = float(runtime_budget["maxCostUsd"]) <= 0 or float(usage["estimatedCostUsd"]) <= float(runtime_budget["maxCostUsd"])
    budget_detail = f"cost ${float(usage['estimatedCostUsd']):0.4f}/${float(runtime_budget['maxCostUsd']):0.4f}"
    if int(runtime_budget["maxTotalTokens"]) > 0:
        budget_detail = f"tokens {int(usage['totalTokens'])}/{int(runtime_budget['maxTotalTokens'])} | {budget_detail}"
    checks_out = {
        "requiredArtifactFields": {
            "passed": result_fields_ok,
            "detail": "All required artifact fields were present." if result_fields_ok else f"Missing fields: {', '.join(missing_fields)}.",
        },
        "budgetCompliance": {
            "passed": token_ok and cost_ok,
            "detail": budget_detail,
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
        "requiredConceptGroups": evaluate_required_concept_groups(public_answer, checks),
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
    checks_out["liveOnly"] = {
        "passed": live_only_ok,
        "detail": "All execution outputs were live." if live_only_ok else f"Non-live modes observed: {', '.join(mode_values)}",
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
    elif payload.get("artifactType") == "node_transfer":
        kind = "node_transfer"
        target = payload.get("sourceNode") or "node_transfer"
    elif payload.get("artifactType") == "failed_call" or "failed_call" in name:
        kind = "failed_call"
        target = payload.get("target") or "failed_call"
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
        "failureKind": payload.get("failureKind"),
        "error": payload.get("error"),
        "passStatus": payload.get("passStatus") or ("discarded_failed_attempt" if payload.get("artifactType") == "failed_call" else None),
        "passedToNextNode": bool(payload.get("passedToNextNode")) if payload.get("artifactType") == "failed_call" else None,
        "handoffNote": payload.get("handoffNote") or (
            "Failed-call artifacts are review-only and are not passed between nodes."
            if payload.get("artifactType") == "failed_call"
            else None
        ),
        "transferStatus": payload.get("status") if payload.get("artifactType") == "node_transfer" else None,
        "validationStatus": payload.get("validationStatus") if payload.get("artifactType") == "node_transfer" else None,
        "integrity": payload.get("integrity") if isinstance(payload.get("integrity"), dict) else {},
        "integrityCheck": payload.get("integrityCheck") if isinstance(payload.get("integrityCheck"), dict) else {},
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
            or relative_text.startswith("workspace/data/failed_calls/")
            or relative_text.startswith("workspace/data/node_transfers/")
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
    replicate_dir = replicate_dir_for(run_dir, case["caseId"], variant_id, replicate_index)
    replicate_dir.mkdir(parents=True, exist_ok=True)
    seed = f"{run['runId']}:{case['caseId']}:{variant_id}:{replicate_index}"
    judge_runtime = LoopRuntime(replicate_dir / "_judge_runtime", auth_path=auth_path)
    judge_provider = normalize_provider_id(str(run.get("judgeProvider") or "openai").strip(), "openai")
    judge_runtime_settings = judge_provider_settings(run, judge_provider)
    selected_judge_instance = judge_runtime.select_provider_instance(
        None,
        judge_runtime_settings,
        judge_provider,
        judge_model,
        "arbiter",
        replicate_index,
    )
    if isinstance(selected_judge_instance, dict):
        judge_runtime_settings["providerInstance"] = selected_judge_instance
        if judge_provider == "ollama":
            judge_runtime_settings["ollamaBaseUrl"] = str(selected_judge_instance.get("baseUrl") or judge_runtime_settings.get("ollamaBaseUrl") or "")
    judge_auth_assignments = judge_runtime.provider_auth_assignments(judge_provider, "judge", salt=seed + ":judge")
    judge_auth_assignment = judge_auth_assignments[0] if judge_auth_assignments else None
    api_key = judge_runtime.provider_live_api_key(judge_provider, judge_auth_assignments) or None
    result: Dict[str, Any]
    baseline_quality: Optional[Dict[str, Any]] = None
    answer_health: Optional[Dict[str, Any]] = None
    baseline_answer_health: Optional[Dict[str, Any]] = None
    comparison: Optional[Dict[str, Any]] = None
    if arm["type"] == "direct":
        runtime = LoopRuntime(replicate_dir / "_direct_runtime", auth_path=auth_path)
        direct = run_direct_answer(
            runtime,
            runtime.provider_auth_assignments(arm["runtime"].get("provider"), "direct", salt=seed + ":direct"),
            case,
            arm,
        )
        output_payload = {
            "taskId": None,
            "artifactType": "eval_direct_output",
            "target": "direct",
            "label": arm["title"],
            "mode": direct["mode"],
            "model": direct["model"],
            "capturedAt": utc_now(),
            "responseId": direct["responseId"],
            "inputText": direct.get("inputText"),
            "fullPrompt": direct.get("fullPrompt"),
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
            "answerPathCallPlan": steered.get("answerPathCallPlan"),
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
        judge_provider,
        api_key or None,
        judge_model,
        case,
        run.get("suite", {}).get("judgeRubric", {}),
        public_answer,
        judge_runtime_settings,
    )
    answer_health = run_answer_health_judge(
        judge_runtime,
        judge_provider,
        api_key or None,
        judge_model,
        case,
        public_answer,
        primary_telemetry,
        judge_runtime_settings,
    )
    control = (
        run_control_judge(judge_runtime, judge_provider, api_key or None, judge_model, case, result["summary"], judge_runtime_settings)
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
                judge_provider,
                api_key or None,
                judge_model,
                case,
                run.get("suite", {}).get("judgeRubric", {}),
                baseline_text,
                judge_runtime_settings,
            )
            baseline_answer_health = run_answer_health_judge(
                judge_runtime,
                judge_provider,
                api_key or None,
                judge_model,
                case,
                baseline_text,
                baseline_telemetry,
                judge_runtime_settings,
            )
            primary_scores = quality.get("scores") if isinstance(quality.get("scores"), dict) else {}
            baseline_scores = baseline_quality.get("scores") if isinstance(baseline_quality.get("scores"), dict) else {}
            score_delta = comparison_score_delta(primary_scores, baseline_scores, QUALITY_SCORE_FIELDS)
            similarity = answer_similarity_metrics(public_answer, baseline_text)
            comparison = run_comparison_judge(
                judge_runtime,
                judge_provider,
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
                judge_runtime_settings,
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
        "answerPathCallPlan": result.get("answerPathCallPlan"),
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
        "answerPathCallPlan": result.get("answerPathCallPlan"),
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
        "answerPathCallPlan": result.get("answerPathCallPlan"),
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
    inline_suite = run.get("inlineSuite") if isinstance(run.get("inlineSuite"), dict) else None
    if inline_suite:
        suite = validate_suite_manifest(inline_suite, run_dir / "_inline_suite.json")
    else:
        suite_path = root / "data" / "evals" / "suites" / f"{run['suiteId']}.json"
        suite = validate_suite_manifest(read_json(suite_path), suite_path)
    inline_arms = run.get("inlineArms") if isinstance(run.get("inlineArms"), dict) else {}
    arm_map: Dict[str, Dict[str, Any]] = {}
    for arm_id in run.get("armIds", []):
        inline_arm = inline_arms.get(arm_id) if isinstance(inline_arms.get(arm_id), dict) else None
        if inline_arm:
            arm_map[arm_id] = validate_arm_manifest(inline_arm, run_dir / f"_inline_arm_{arm_id}.json")
            continue
        arm_path = root / "data" / "evals" / "arms" / f"{arm_id}.json"
        arm_map[arm_id] = validate_arm_manifest(read_json(arm_path), arm_path)
    auth_path = auth_file_path(root)
    run["judgeLearning"] = normalize_judge_learning_config(
        run.get("judgeLearning") if isinstance(run.get("judgeLearning"), dict) else {},
        arm_map,
    )
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
            "knowledgebase": deepcopy(arm["runtime"].get("knowledgebase", default_knowledgebase_config())),
            "knowledgebaseExplicit": bool(arm["runtime"].get("knowledgebaseExplicit")),
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
    judge_provider = normalize_provider_id(str(run.get("judgeProvider") or "openai").strip(), "openai")
    judge_model = normalize_model_id(
        str(run.get("judgeModel", "")).strip(),
        default_judge_model_for_provider(judge_provider),
        judge_provider,
    )

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
                        "knowledgebase": deepcopy(arm["runtime"].get("knowledgebase", default_knowledgebase_config())),
                        "knowledgebaseExplicit": bool(arm["runtime"].get("knowledgebaseExplicit")),
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
                        replicate_dir = replicate_dir_for(run_dir, case["caseId"], variant_id, replicate_index)
                        score_path = replicate_dir / "score.json"
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
                            score_path,
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
                        try:
                            error_artifacts = collect_replicate_artifacts(
                                run,
                                run_dir,
                                case["caseId"],
                                variant_id,
                                replicate_index,
                                replicate_dir,
                            )
                        except Exception:
                            error_artifacts = []
                        error_payload["artifacts"] = error_artifacts
                        error_payload["artifactIds"] = [entry["artifactId"] for entry in error_artifacts]
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
    learning_config = run.get("judgeLearning") if isinstance(run.get("judgeLearning"), dict) else {}
    if bool(learning_config.get("enabled")):
        try:
            learning_result = judge_learning.learn_from_eval_runs(
                root,
                run_ids=[run_id],
                bank_id=str(learning_config.get("bankId") or infer_judge_learning_bank_id(arm_map)),
                dry_run=coerce_bool(learning_config.get("dryRun"), False),
            )
            run["judgeLearning"] = {
                **learning_config,
                "status": "completed",
                "lastResult": compact_judge_learning_result(learning_result),
            }
        except Exception as exc:
            run["judgeLearning"] = {
                **learning_config,
                "status": "error",
                "error": f"{exc.__class__.__name__}: {str(exc)}",
            }
        run["summary"]["judgeLearning"] = {
            key: value
            for key, value in run["judgeLearning"].items()
            if key in {"enabled", "bankId", "dryRun", "writeMode", "source", "status", "error", "lastResult"}
        }
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
