from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from backend.app.provider_responses import extract_normalized_provider_answer, parse_embedded_json_value  # noqa: E402
import eval_runner  # type: ignore  # noqa: E402
from engine import LoopRuntime, RuntimeErrorWithCode, default_judge_model_for_provider, utc_now  # type: ignore  # noqa: E402


DEFAULT_JUDGE_PROVIDER = "openai"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "benchmarks" / "vetting"
JUDGE_SYSTEMS = {"council", "provider_owned"}
PROVIDER_FAMILY_ALIASES = {
    "oai": "openai",
    "grok": "xai",
    "claude": "anthropic",
    "ant": "anthropic",
    "min": "minimax",
    "mini": "minimax",
}


def read_json(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8").lstrip("\ufeff")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected an object in {path.name}.")
    return parsed


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def sanitize_id(value: str) -> str:
    return eval_runner.sanitize_id(value)


def normalize_judge_system(value: Any) -> str:
    candidate = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if candidate in JUDGE_SYSTEMS:
        return candidate
    return "council"


def normalize_provider_family(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return ""
    return PROVIDER_FAMILY_ALIASES.get(candidate, candidate)


def infer_answer_role(entry: Dict[str, Any]) -> str:
    explicit = str(entry.get("role") or entry.get("answerRole") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if explicit in {"direct", "baseline", "single"}:
        return "direct"
    if explicit in {"parallm", "pressurized", "orchestrated", "multi_lane"}:
        return "parallm"
    probe = " ".join(
        [
            str(entry.get("id") or entry.get("answerId") or ""),
            str(entry.get("label") or ""),
            str(entry.get("cohort") or ""),
        ]
    ).lower()
    if "direct" in probe or "baseline" in probe or "single" in probe:
        return "direct"
    return "candidate"


def run_id_for_manifest(manifest_path: Path, manifest: Dict[str, Any]) -> str:
    timestamp = utc_now().replace(":", "").replace("-", "").replace("T", "-").replace("Z", "")
    seed = f"{manifest_path.name}:{manifest.get('title', '')}:{manifest.get('objective', '')}:{timestamp}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]
    return f"vet-{timestamp}-{digest}"


def slot_label(index: int) -> str:
    if index < 0:
        return "A"
    label = ""
    current = index
    while True:
        current, remainder = divmod(current, 26)
        label = chr(ord("A") + remainder) + label
        if current == 0:
            break
        current -= 1
    return label


def normalize_cost(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def normalize_seconds(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return round(seconds, 2)


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_provider_trace(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    response_meta = payload.get("responseMeta")
    if not isinstance(response_meta, dict):
        return {}
    provider_trace = response_meta.get("providerTrace")
    return provider_trace if isinstance(provider_trace, dict) else {}


def extract_elapsed_seconds(payload: Any) -> Optional[float]:
    provider_trace = extract_provider_trace(payload)
    elapsed_ms = provider_trace.get("elapsedMs")
    if elapsed_ms not in (None, ""):
        try:
            milliseconds = float(elapsed_ms)
        except (TypeError, ValueError):
            milliseconds = 0.0
        if milliseconds > 0:
            return round(milliseconds / 1000.0, 2)
    started_at = parse_iso_datetime(provider_trace.get("startedAt"))
    completed_at = parse_iso_datetime(provider_trace.get("completedAt"))
    if started_at and completed_at and completed_at >= started_at:
        return round((completed_at - started_at).total_seconds(), 2)
    return None


def extract_answer_text(payload: Any, provider: str = "") -> str:
    if isinstance(payload, dict):
        output_value = payload.get("output")
        if isinstance(output_value, dict):
            nested = extract_answer_text(output_value, provider or str(payload.get("provider") or ""))
            if nested:
                return nested
        if isinstance(output_value, str) and output_value.strip():
            nested_output = extract_answer_text(output_value.strip(), provider or str(payload.get("provider") or ""))
            if nested_output:
                return nested_output
        front_answer = payload.get("frontAnswer")
        if isinstance(front_answer, dict):
            nested = extract_answer_text(front_answer, provider or str(payload.get("provider") or ""))
            if nested:
                return nested
        answer_value = payload.get("answer")
        if isinstance(answer_value, dict):
            nested = extract_answer_text(answer_value, provider or str(payload.get("provider") or ""))
            if nested:
                return nested
        if isinstance(answer_value, str) and answer_value.strip():
            nested_answer = extract_answer_text(answer_value.strip(), provider or str(payload.get("provider") or ""))
            if nested_answer:
                return nested_answer
            return answer_value.strip()
        summary_value = payload.get("summary")
        if isinstance(summary_value, dict):
            nested = extract_answer_text(summary_value, provider or str(payload.get("provider") or ""))
            if nested:
                return nested
        flattened_output = payload.get("flattenedOutputText")
        if isinstance(flattened_output, str) and flattened_output.strip():
            return flattened_output.strip()
        raw_output = payload.get("rawOutputText")
        if isinstance(raw_output, str) and raw_output.strip():
            normalized = extract_normalized_provider_answer(provider or str(payload.get("provider") or ""), raw_output)
            if normalized:
                return normalized
            decoded_raw = parse_embedded_json_value(raw_output)
            if decoded_raw is not None:
                nested = extract_answer_text(decoded_raw, provider or str(payload.get("provider") or ""))
                if nested:
                    return nested
            return raw_output.strip()
    if isinstance(payload, str):
        raw_text = payload.strip()
        normalized = extract_normalized_provider_answer(provider, raw_text)
        if normalized:
            return normalized
        decoded_raw = parse_embedded_json_value(raw_text)
        if decoded_raw is not None:
            nested = extract_answer_text(decoded_raw, provider)
            if nested:
                return nested
        return raw_text
    return ""


def load_answer_entry(entry: Dict[str, Any], repo_root: Path) -> Dict[str, Any]:
    answer_id = str(entry.get("id") or entry.get("answerId") or "").strip()
    if not answer_id:
        raise ValueError("Each answer entry needs an id.")
    label = str(entry.get("label") or answer_id).strip() or answer_id
    cohort = str(entry.get("cohort") or label).strip() or label
    family_hint = str(entry.get("familyHint") or "").strip()
    cost_note = str(entry.get("costNote") or "").strip()
    role = infer_answer_role(entry)
    declared_provider = normalize_provider_family(entry.get("provider") or entry.get("providerFamily") or entry.get("providerId"))
    declared_model = str(entry.get("model") or "").strip()
    text = str(entry.get("text") or "").strip()
    artifact_file = str(entry.get("artifactFile") or "").strip()
    artifact_payload: Dict[str, Any] = {}
    elapsed_seconds = normalize_seconds(entry.get("elapsedSeconds"))
    if not text and artifact_file:
        artifact_path = Path(artifact_file)
        if not artifact_path.is_absolute():
            artifact_path = (repo_root / artifact_path).resolve()
        artifact_payload = read_json(artifact_path)
        text = extract_answer_text(artifact_payload, declared_provider)
        if not text:
            raise ValueError(f"Could not extract answer text from artifact {artifact_path}.")
    elif artifact_file:
        artifact_path = Path(artifact_file)
        if not artifact_path.is_absolute():
            artifact_path = (repo_root / artifact_path).resolve()
        artifact_payload = read_json(artifact_path)
    if elapsed_seconds is None and artifact_payload:
        elapsed_seconds = extract_elapsed_seconds(artifact_payload)
    provider_trace = extract_provider_trace(artifact_payload)
    if not text:
        raise ValueError(f"Answer {answer_id} needs text or artifactFile.")
    return {
        "answerId": answer_id,
        "label": label,
        "cohort": cohort,
        "role": role,
        "familyHint": family_hint,
        "costUsd": normalize_cost(entry.get("costUsd")),
        "costNote": cost_note,
        "elapsedSeconds": elapsed_seconds,
        "text": text,
        "chars": len(text),
        "words": len(eval_runner.tokenize_compare_text(text)),
        "artifactFile": artifact_file or None,
        "provider": declared_provider or normalize_provider_family(provider_trace.get("provider")) or None,
        "model": declared_model or str(provider_trace.get("model") or "").strip() or None,
    }


def validate_judge_manifest_mode(manifest: Dict[str, Any], answers: List[Dict[str, Any]], judge_system: str, judge_provider: str) -> Dict[str, Any]:
    provider_family = normalize_provider_family(manifest.get("providerFamily") or manifest.get("answerProviderFamily") or judge_provider)
    role_counts = {
        "direct": sum(1 for answer in answers if str(answer.get("role") or "") == "direct"),
        "parallm": sum(1 for answer in answers if str(answer.get("role") or "") == "parallm"),
        "candidate": sum(1 for answer in answers if str(answer.get("role") or "") == "candidate"),
    }
    provider_mismatches: List[str] = []
    if judge_system == "provider_owned":
        if not provider_family:
            raise ValueError("Provider-owned judging requires a providerFamily.")
        normalized_judge_provider = normalize_provider_family(judge_provider)
        if normalized_judge_provider and provider_family and normalized_judge_provider != provider_family:
            raise ValueError(
                f"Provider-owned judging requires judge provider '{provider_family}', but got '{normalized_judge_provider}'."
            )
        if role_counts["direct"] < 1:
            raise ValueError("Provider-owned judging requires at least one direct baseline answer.")
        if (role_counts["parallm"] + role_counts["candidate"]) < 1:
            raise ValueError("Provider-owned judging requires at least one non-direct answer.")
        for answer in answers:
            answer_provider = normalize_provider_family(answer.get("provider"))
            if answer_provider and answer_provider != provider_family:
                provider_mismatches.append(str(answer.get("label") or answer.get("answerId") or "answer"))
        if provider_mismatches:
            mismatch_list = ", ".join(provider_mismatches[:6])
            raise ValueError(
                f"Provider-owned judging requires all answers to belong to '{provider_family}'. Mismatches: {mismatch_list}"
            )
    return {
        "judgeSystem": judge_system,
        "providerFamily": provider_family or None,
        "roleCounts": role_counts,
    }


def assign_blind_slots(answers: List[Dict[str, Any]], seed: str) -> List[Dict[str, Any]]:
    shuffled = [dict(answer) for answer in answers]
    random.Random(seed).shuffle(shuffled)
    slotted: List[Dict[str, Any]] = []
    for index, answer in enumerate(shuffled):
        slot = slot_label(index)
        slotted.append({**answer, "slot": slot, "id": slot})
    return slotted


def default_vetting_rubric() -> Dict[str, Any]:
    return {
        "qualifier": "MSP Live Incident Lead Qualifier",
        "candidateStandard": "Judge each answer as if you were vetting a candidate to lead a real multi-tenant MSP severity-1 incident in the first hour.",
        "mustDo": [
            "Assume every wrong step can expand customer harm, breach tenant boundaries, destroy evidence, or trigger compliance escalation.",
            "Reward answers that preserve tenant separation, distrust a potentially compromised control plane, preserve evidence, and use escalation gates before destructive action.",
            "Require per-customer incident ownership, an internal major-incident record, and communication steps that remain evidence-compatible and tenant-safe.",
            "Penalize answers that sound decisive but create cross-tenant disclosure risk, evidence loss, or blind service disruption.",
            "Ignore formatting noise unless it hides or distorts meaning.",
        ],
        "hardFailRules": [
            "Any recommendation that could create cross-tenant customer disclosure, shared customer-facing ticketing, or mixed-tenant outbound communication is disqualifying.",
            "Any answer that fails to establish per-customer incident ownership plus an internal major-incident record and evidence-compatible decision log for a multi-tenant severity-1 event is disqualifying.",
            "Any recommendation to trust or operate the suspected compromised RMM or PSA control plane before preserving/exporting its evidence is a hard fail unless explicitly justified and sequenced safely.",
            "Any recommendation for blind mass shutdown, mass isolation, or destructive cleanup without threshold gates is a hard fail.",
            "Any recommendation that destroys volatile evidence before capture without explicit necessity is a hard fail.",
        ],
        "trapCatalog": [
            "Cross-tenant comms trap: one customer-facing ticket, one shared outbound thread, or one blended client artifact.",
            "Incident-record trap: no internal major incident record, no per-customer ownership, or no evidence-compatible decision log.",
            "Control-plane trust trap: immediately using the suspected RMM/PSA as trusted truth or control surface.",
            "Evidence destruction trap: kill, reboot, wipe, or rollback before preserving volatile evidence and audit data.",
            "Blanket action trap: isolate or power off everything without threshold-based justification.",
            "Managerial fantasy trap: a central artifact that sounds neat but cannot support per-client incident ownership under load.",
        ],
        "categories": {
            "blastRadiusPerception": "Did the answer identify the real blast path, including tenant-boundary and control-plane exposure, and center early actions around it?",
            "humanUsability": "Could a tired but competent MSP operator follow this safely under pressure while keeping customer and tenant boundaries straight?",
            "agentExecutability": "Could an AI or scripted assistant execute this safely without creating tenant-boundary or compliance mistakes?",
            "commsAndIncidentDiscipline": "Did it establish per-customer incident ownership, an internal major-incident record, evidence-compatible logging, and customer-safe communication boundaries?",
            "tacticalDetail": "Did it include useful concrete checks, artifacts, evidence handling steps, and immediate tactical moves?",
            "restraintAndCollateral": "Did it avoid collateral damage, compliance exposure, and irreversible actions until gates were met?",
            "decisionGates": "Did it specify threshold-based gates for escalation, isolation, customer communication, and disruptive action?",
            "firstHourRealism": "Does it feel like a credible first-hour MSP incident lead plan instead of generic IR language?",
            "overall": "Would you trust this candidate to lead the incident bridge with limited supervision?",
        },
        "awards": {
            "bestFinalAnswer": "The safest, clearest, most hireable incident-lead answer you would trust to ship to an overnight MSP operator.",
            "bestTacticalDetail": "The answer that contributed the strongest useful extra checks, artifacts, or control-plane cautions.",
        },
        "verdicts": {
            "hire": "Safe enough to lead the first-hour response with limited supervision.",
            "hire_with_supervision": "Usable, but needs senior oversight to avoid meaningful risk.",
            "not_for_lead": "Contains enough weakness that you would not trust it to lead the bridge.",
            "disqualifying": "Contains a hard-fail transgression that would expand incident, compliance, or customer risk.",
        },
    }


def build_case(manifest: Dict[str, Any]) -> Dict[str, Any]:
    objective = str(manifest.get("objective") or "").strip()
    if not objective:
        raise ValueError("Manifest requires an objective.")
    return {
        "caseId": sanitize_id(str(manifest.get("caseId") or manifest.get("title") or "vetting-case")),
        "title": str(manifest.get("title") or "Benchmark vetting").strip() or "Benchmark vetting",
        "objective": objective,
        "constraints": [str(item).strip() for item in (manifest.get("constraints") or []) if str(item).strip()],
        "gold": manifest.get("gold") if isinstance(manifest.get("gold"), (dict, list, str)) else {},
    }


def remap_vetting_result(slot_result: Dict[str, Any], slotted_answers: List[Dict[str, Any]]) -> Dict[str, Any]:
    slot_lookup = {str(answer["slot"]): answer for answer in slotted_answers}

    def describe_slot(slot: str) -> Dict[str, Any]:
        answer = slot_lookup.get(slot) or {}
        answer_id = str(answer.get("answerId") or "").strip()
        return {
            "slot": slot,
            "answerId": answer_id,
            "label": str(answer.get("label") or "").strip(),
            "cohort": str(answer.get("cohort") or "").strip(),
            "costUsd": answer.get("costUsd"),
            "costNote": answer.get("costNote"),
            "elapsedSeconds": answer.get("elapsedSeconds"),
            "hireVerdict": str((slot_result.get("hireVerdicts") or {}).get(slot, "")).strip() or None,
            "hardFailFlags": list(((slot_result.get("hardFailFlags") or {}).get(slot, [])) or []),
            "trapFindings": dict(((slot_result.get("trapFindings") or {}).get(slot, {})) or {}),
        }

    scores_by_answer = {
        str(answer.get("answerId") or ""): dict(slot_result["scores"].get(str(answer.get("slot") or ""), {}))
        for answer in slotted_answers
    }
    notes_by_answer = {
        str(answer.get("answerId") or ""): str((slot_result.get("answerNotes") or {}).get(str(answer.get("slot") or ""), "")).strip()
        for answer in slotted_answers
    }
    hire_verdicts_by_answer = {
        str(answer.get("answerId") or ""): str((slot_result.get("hireVerdicts") or {}).get(str(answer.get("slot") or ""), "")).strip()
        for answer in slotted_answers
    }
    hard_fail_flags_by_answer = {
        str(answer.get("answerId") or ""): list(((slot_result.get("hardFailFlags") or {}).get(str(answer.get("slot") or ""), [])) or [])
        for answer in slotted_answers
    }
    trap_findings_by_answer = {
        str(answer.get("answerId") or ""): dict(((slot_result.get("trapFindings") or {}).get(str(answer.get("slot") or ""), {})) or {})
        for answer in slotted_answers
    }
    ranking_slots = [slot for slot in slot_result.get("ranking", []) if slot in slot_lookup]
    ranking_answers = [describe_slot(slot) for slot in ranking_slots]
    category_leaders_slots = {
        field: [slot for slot in leaders if slot in slot_lookup]
        for field, leaders in (slot_result.get("categoryLeaders") or {}).items()
    }
    category_leaders_answers = {
        field: [describe_slot(slot) for slot in leaders]
        for field, leaders in category_leaders_slots.items()
    }
    advantage_summary_raw = slot_result.get("advantageSummary") if isinstance(slot_result.get("advantageSummary"), dict) else {}
    answers = []
    for answer in slotted_answers:
        answer_id = str(answer.get("answerId") or "").strip()
        slot = str(answer.get("slot") or "").strip()
        answers.append(
            {
                "slot": slot,
                "answerId": answer_id,
                "label": answer.get("label"),
                "cohort": answer.get("cohort"),
                "role": answer.get("role"),
                "familyHint": answer.get("familyHint"),
                "costUsd": answer.get("costUsd"),
                "costNote": answer.get("costNote"),
                "elapsedSeconds": answer.get("elapsedSeconds"),
                "artifactFile": answer.get("artifactFile"),
                "provider": answer.get("provider"),
                "model": answer.get("model"),
                "text": answer.get("text"),
                "chars": answer.get("chars"),
                "words": answer.get("words"),
                "scores": scores_by_answer.get(answer_id, {}),
                "note": notes_by_answer.get(answer_id, ""),
                "hireVerdict": hire_verdicts_by_answer.get(answer_id, "") or None,
                "hardFailFlags": hard_fail_flags_by_answer.get(answer_id, []),
                "trapFindings": trap_findings_by_answer.get(answer_id, {"triggered": [], "caught": [], "missed": []}),
            }
        )
    timed_answers = [answer for answer in answers if isinstance(answer.get("elapsedSeconds"), (int, float))]
    fastest_seconds = min([float(answer["elapsedSeconds"]) for answer in timed_answers], default=None)
    slowest_seconds = max([float(answer["elapsedSeconds"]) for answer in timed_answers], default=None)
    speed_adjusted_ranking: List[Dict[str, Any]] = []
    for answer in answers:
        score_block = answer.get("scores") if isinstance(answer.get("scores"), dict) else {}
        overall = float(score_block.get("overall", 0.0) or 0.0)
        elapsed_seconds = answer.get("elapsedSeconds")
        internal_timing: Dict[str, Any] = {
            "elapsedSeconds": elapsed_seconds,
            "latencyRatioVsFastest": None,
            "timeAdjustedOverall": None,
        }
        if fastest_seconds and isinstance(elapsed_seconds, (int, float)) and float(elapsed_seconds) > 0:
            latency_ratio = round(float(elapsed_seconds) / float(fastest_seconds), 2)
            time_adjusted_overall = round(overall / math.sqrt(max(latency_ratio, 1.0)), 2)
            internal_timing = {
                "elapsedSeconds": round(float(elapsed_seconds), 2),
                "latencyRatioVsFastest": latency_ratio,
                "timeAdjustedOverall": time_adjusted_overall,
            }
            speed_adjusted_ranking.append(
                {
                    "slot": answer.get("slot"),
                    "answerId": answer.get("answerId"),
                    "label": answer.get("label"),
                    "cohort": answer.get("cohort"),
                    "elapsedSeconds": round(float(elapsed_seconds), 2),
                    "latencyRatioVsFastest": latency_ratio,
                    "timeAdjustedOverall": time_adjusted_overall,
                    "overall": round(overall, 2),
                }
            )
        answer["internalTiming"] = internal_timing
    speed_adjusted_ranking.sort(
        key=lambda item: (
            -float(item.get("timeAdjustedOverall") or 0.0),
            float(item.get("elapsedSeconds") or 0.0),
            str(item.get("answerId") or ""),
        )
    )
    leader_slot = str(advantage_summary_raw.get("leader") or "").strip()
    runner_up_slot = str(advantage_summary_raw.get("runnerUp") or "").strip()
    advantage_summary = {
        "band": str(advantage_summary_raw.get("band") or "tied").strip() or "tied",
        "leader": describe_slot(leader_slot) if leader_slot else {},
        "runnerUp": describe_slot(runner_up_slot) if runner_up_slot else {},
        "leaderOverall": advantage_summary_raw.get("leaderOverall"),
        "runnerUpOverall": advantage_summary_raw.get("runnerUpOverall"),
        "overallMargin": advantage_summary_raw.get("overallMargin"),
        "uniqueCategoryLeads": advantage_summary_raw.get("uniqueCategoryLeads"),
        "sharedCategoryLeads": advantage_summary_raw.get("sharedCategoryLeads"),
    }
    return {
        "slotResult": slot_result,
        "scoresByAnswer": scores_by_answer,
        "notesByAnswer": notes_by_answer,
        "hireVerdictsByAnswer": hire_verdicts_by_answer,
        "hardFailFlagsByAnswer": hard_fail_flags_by_answer,
        "trapFindingsByAnswer": trap_findings_by_answer,
        "rankingAnswers": ranking_answers,
        "bestFinalAnswer": describe_slot(str(slot_result.get("bestFinalAnswer") or "")),
        "bestTacticalDetail": describe_slot(str(slot_result.get("bestTacticalDetail") or "")),
        "advantageSummary": advantage_summary,
        "categoryLeaders": category_leaders_answers,
        "answers": answers,
        "internalTiming": {
            "fastestElapsedSeconds": round(float(fastest_seconds), 2) if fastest_seconds else None,
            "slowestElapsedSeconds": round(float(slowest_seconds), 2) if slowest_seconds else None,
            "answersWithTiming": len(timed_answers),
            "speedAdjustedRanking": speed_adjusted_ranking,
        },
    }


def markdown_score_table(answers: List[Dict[str, Any]], scores_by_answer: Dict[str, Dict[str, float]]) -> str:
    columns = ["Area"] + [str(answer.get("slot") or answer.get("answerId") or "") for answer in answers]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS:
        row = [str(eval_runner.VETTING_MATRIX_SCORE_LABELS.get(field, field))]
        for answer in answers:
            answer_id = str(answer.get("answerId") or "").strip()
            value = (scores_by_answer.get(answer_id) or {}).get(field, 0.0)
            row.append(f"{float(value):.1f}")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def markdown_legend(answers: List[Dict[str, Any]]) -> str:
    lines = [
        "| Slot | Answer | Cohort | Declared cost |",
        "| --- | --- | --- | --- |",
    ]
    for answer in answers:
        cost_value = answer.get("costUsd")
        cost_text = (
            f"${float(cost_value):.6f}".rstrip("0").rstrip(".")
            if isinstance(cost_value, (int, float))
            else (str(answer.get("costNote") or "").strip() or "n/a")
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(answer.get("slot") or ""),
                    str(answer.get("label") or ""),
                    str(answer.get("cohort") or ""),
                    cost_text,
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def markdown_summary(result: Dict[str, Any]) -> str:
    best_final = result.get("bestFinalAnswer") or {}
    best_tactical = result.get("bestTacticalDetail") or {}
    judge_system = str(result.get("judgeSystem") or "council").strip() or "council"
    provider_family = str(result.get("providerFamily") or "").strip()
    advantage_summary = result.get("advantageSummary") if isinstance(result.get("advantageSummary"), dict) else {}
    leader = advantage_summary.get("leader") if isinstance(advantage_summary.get("leader"), dict) else {}
    runner_up = advantage_summary.get("runnerUp") if isinstance(advantage_summary.get("runnerUp"), dict) else {}
    leader_text = f"`{leader.get('slot', '')}` | {leader.get('label', '')}".strip()
    runner_up_text = f"`{runner_up.get('slot', '')}` | {runner_up.get('label', '')}".strip()
    measured_advantage = (
        f"`{advantage_summary.get('band', 'tied')}`"
        f" | leader {leader_text or 'n/a'}"
        f" | runner-up {runner_up_text or 'n/a'}"
        f" | overall margin {advantage_summary.get('overallMargin', 0.0)}"
        f" | unique category leads {advantage_summary.get('uniqueCategoryLeads', 0)}"
    )
    best_final_verdict = str(best_final.get("hireVerdict") or "").strip()
    best_final_hard_fails = best_final.get("hardFailFlags") if isinstance(best_final.get("hardFailFlags"), list) else []
    return "\n".join(
        [
            f"- Judge system: `{judge_system}`" + (f" | provider family `{provider_family}`" if provider_family else ""),
            f"- Best final answer: `{best_final.get('slot', '')}` | {best_final.get('label', '')}",
            f"- Best tactical detail: `{best_tactical.get('slot', '')}` | {best_tactical.get('label', '')}",
            f"- Hire verdict: `{best_final_verdict or 'unknown'}`"
            + (
                f" | hard fails {', '.join([str(item).strip() for item in best_final_hard_fails if str(item).strip()])}"
                if best_final_hard_fails
                else ""
            ),
            f"- Measured advantage: {measured_advantage}",
            f"- Judge rationale: {str(result.get('slotResult', {}).get('rationale') or '').strip()}",
        ]
    )


def load_all_runs(output_root: Path) -> List[Dict[str, Any]]:
    runs_dir = output_root / "runs"
    if not runs_dir.exists():
        return []
    runs: List[Dict[str, Any]] = []
    for run_file in sorted(runs_dir.glob("*.json")):
        try:
            runs.append(read_json(run_file))
        except Exception:
            continue
    return runs


def build_rollup(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    def build_cohort_aggregates(subset_runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cohort_aggregates: Dict[str, Dict[str, Any]] = {}
        for run in subset_runs:
            answers = run.get("answers") if isinstance(run.get("answers"), list) else []
            best_final = (run.get("bestFinalAnswer") or {}).get("slot")
            best_tactical = (run.get("bestTacticalDetail") or {}).get("slot")
            leader_slot = ((run.get("advantageSummary") or {}).get("leader") or {}).get("slot")
            for answer in answers:
                if not isinstance(answer, dict):
                    continue
                cohort = str(answer.get("cohort") or answer.get("label") or answer.get("answerId") or "unknown").strip() or "unknown"
                aggregate = cohort_aggregates.setdefault(
                    cohort,
                    {
                        "cohort": cohort,
                        "label": str(answer.get("label") or answer.get("answerId") or cohort).strip(),
                        "appearances": 0,
                        "bestFinalWins": 0,
                        "bestTacticalWins": 0,
                        "leaderWins": 0,
                        "scoreSums": {field: 0.0 for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS},
                        "timedAppearances": 0,
                        "elapsedSecondsSum": 0.0,
                        "timeAdjustedOverallSum": 0.0,
                    },
                )
                aggregate["appearances"] += 1
                if str(answer.get("slot") or "") == str(best_final or ""):
                    aggregate["bestFinalWins"] += 1
                if str(answer.get("slot") or "") == str(best_tactical or ""):
                    aggregate["bestTacticalWins"] += 1
                if str(answer.get("slot") or "") == str(leader_slot or ""):
                    aggregate["leaderWins"] += 1
                score_block = answer.get("scores") if isinstance(answer.get("scores"), dict) else {}
                for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS:
                    aggregate["scoreSums"][field] += float(score_block.get(field, 0.0) or 0.0)
                internal_timing = answer.get("internalTiming") if isinstance(answer.get("internalTiming"), dict) else {}
                if isinstance(internal_timing.get("elapsedSeconds"), (int, float)):
                    aggregate["timedAppearances"] += 1
                    aggregate["elapsedSecondsSum"] += float(internal_timing.get("elapsedSeconds") or 0.0)
                if isinstance(internal_timing.get("timeAdjustedOverall"), (int, float)):
                    aggregate["timeAdjustedOverallSum"] += float(internal_timing.get("timeAdjustedOverall") or 0.0)
        cohorts: List[Dict[str, Any]] = []
        for aggregate in cohort_aggregates.values():
            appearances = max(1, int(aggregate["appearances"]))
            timed_appearances = int(aggregate["timedAppearances"])
            average_scores = {
                field: round(float(aggregate["scoreSums"][field]) / appearances, 2)
                for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS
            }
            cohorts.append(
                {
                    "cohort": aggregate["cohort"],
                    "label": aggregate["label"],
                    "appearances": appearances,
                    "bestFinalWins": int(aggregate["bestFinalWins"]),
                    "bestTacticalWins": int(aggregate["bestTacticalWins"]),
                    "leaderWins": int(aggregate["leaderWins"]),
                    "averageScores": average_scores,
                    "timedAppearances": timed_appearances,
                    "averageElapsedSeconds": (
                        round(float(aggregate["elapsedSecondsSum"]) / timed_appearances, 2)
                        if timed_appearances
                        else None
                    ),
                    "averageTimeAdjustedOverall": (
                        round(float(aggregate["timeAdjustedOverallSum"]) / timed_appearances, 2)
                        if timed_appearances
                        else None
                    ),
                }
            )
        cohorts.sort(key=lambda item: (-float((item.get("averageScores") or {}).get("overall", 0.0)), item.get("cohort", "")))
        return cohorts

    grouped_runs: Dict[str, List[Dict[str, Any]]] = {}
    for run in runs:
        judge_system = normalize_judge_system(run.get("judgeSystem"))
        grouped_runs.setdefault(judge_system, []).append(run)
    by_judge_system = {
        system: {
            "runCount": len(system_runs),
            "cohorts": build_cohort_aggregates(system_runs),
        }
        for system, system_runs in grouped_runs.items()
    }
    return {
        "updatedAt": utc_now(),
        "runCount": len(runs),
        "cohorts": build_cohort_aggregates(runs),
        "byJudgeSystem": by_judge_system,
    }


def print_run_summary(run_payload: Dict[str, Any]) -> None:
    print("")
    print(run_payload["markdown"]["scoreTable"])
    print("")
    print(run_payload["markdown"]["legend"])
    print("")
    print(run_payload["markdown"]["summary"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a generalized benchmark vetting matrix against multiple answer variants.")
    parser.add_argument("--input", required=True, help="JSON manifest with objective + answers to vet.")
    parser.add_argument("--judge-model", default="", help="Optional judge model id override. Defaults to the manifest value, then the flagship judge model for the selected provider.")
    parser.add_argument("--judge-provider", default="", help="Optional judge provider override. Defaults to the manifest value, then openai.")
    parser.add_argument("--seed", default="", help="Optional deterministic shuffle seed.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Directory for local benchmark artifacts.")
    args = parser.parse_args()

    manifest_path = Path(args.input)
    if not manifest_path.is_absolute():
        manifest_path = (PROJECT_ROOT / manifest_path).resolve()
    manifest = read_json(manifest_path)
    case = build_case(manifest)
    raw_answers = manifest.get("answers")
    if not isinstance(raw_answers, list) or len(raw_answers) < 2:
        raise SystemExit("Manifest needs at least two answers.")
    answers = [load_answer_entry(entry, PROJECT_ROOT) for entry in raw_answers if isinstance(entry, dict)]
    if len(answers) < 2:
        raise SystemExit("Manifest did not yield at least two valid answers.")

    judge_provider = str(args.judge_provider or manifest.get("judgeProvider") or DEFAULT_JUDGE_PROVIDER).strip().lower() or DEFAULT_JUDGE_PROVIDER
    judge_model = str(args.judge_model or manifest.get("judgeModel") or default_judge_model_for_provider(judge_provider)).strip() or default_judge_model_for_provider(judge_provider)
    judge_system = normalize_judge_system(manifest.get("judgeSystem"))
    manifest_mode = validate_judge_manifest_mode(manifest, answers, judge_system, judge_provider)
    runtime = LoopRuntime(PROJECT_ROOT)
    api_key = runtime.provider_live_api_key(judge_provider, None) or runtime.get_api_key(judge_provider)
    if runtime.provider_requires_api_key(judge_provider) and not api_key:
        raise SystemExit(f"No live API key is available for the {judge_provider} vetting judge.")

    run_seed = str(args.seed or manifest.get("seed") or manifest_path.name).strip()
    slotted_answers = assign_blind_slots(answers, run_seed)
    slot_payload = [
        {
            "id": answer["slot"],
            "text": answer["text"],
            "costUsd": answer["costUsd"],
            "costNote": answer["costNote"],
            "familyHint": answer["familyHint"],
        }
        for answer in slotted_answers
    ]
    judge_rubric = manifest.get("judgeRubric") if isinstance(manifest.get("judgeRubric"), dict) else default_vetting_rubric()
    judge_runtime = manifest.get("judgeRuntime") if isinstance(manifest.get("judgeRuntime"), dict) else {}
    try:
        slot_result = eval_runner.vetting_matrix_judge_live(
            runtime=runtime,
            judge_provider=judge_provider,
            api_key=api_key,
            judge_model=judge_model,
            case=case,
            judge_rubric=judge_rubric,
            answers=slot_payload,
            provider_settings=judge_runtime,
        )
    except RuntimeErrorWithCode as error:
        raise SystemExit(str(error)) from error

    remapped = remap_vetting_result(slot_result, slotted_answers)
    run_id = run_id_for_manifest(manifest_path, manifest)
    run_payload = {
        "runId": run_id,
        "createdAt": utc_now(),
        "sourceManifest": str(manifest_path),
        "judge": {
            "provider": judge_provider,
            "model": judge_model,
        },
        "judgeSystem": manifest_mode["judgeSystem"],
        "providerFamily": manifest_mode["providerFamily"],
        "answerRoleCounts": manifest_mode["roleCounts"],
        "case": case,
        "blindSeed": run_seed,
        "answers": remapped["answers"],
        "slotResult": remapped["slotResult"],
        "scoresByAnswer": remapped["scoresByAnswer"],
        "notesByAnswer": remapped["notesByAnswer"],
        "rankingAnswers": remapped["rankingAnswers"],
        "internalTiming": remapped["internalTiming"],
        "bestFinalAnswer": remapped["bestFinalAnswer"],
        "bestTacticalDetail": remapped["bestTacticalDetail"],
        "advantageSummary": remapped["advantageSummary"],
        "categoryLeaders": remapped["categoryLeaders"],
        "judgeTrace": {
            "fullPrompt": str(slot_result.get("fullPrompt") or "").strip(),
            "inputText": str(slot_result.get("inputText") or "").strip(),
            "answerPackets": slot_result.get("answerPackets") if isinstance(slot_result.get("answerPackets"), list) else [],
            "rawOutputText": str(slot_result.get("rawOutputText") or "").strip() or None,
            "responseId": slot_result.get("responseId"),
            "responseMeta": slot_result.get("responseMeta") if isinstance(slot_result.get("responseMeta"), dict) else {},
        },
        "markdown": {
            "scoreTable": markdown_score_table(remapped["answers"], remapped["scoresByAnswer"]),
            "legend": markdown_legend(remapped["answers"]),
            "summary": markdown_summary({
                **remapped,
                "judgeSystem": manifest_mode["judgeSystem"],
                "providerFamily": manifest_mode["providerFamily"],
            }),
        },
    }

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = (PROJECT_ROOT / output_root).resolve()
    run_path = output_root / "runs" / f"{run_id}.json"
    write_json(run_path, run_payload)
    write_json(output_root / "latest.json", run_payload)
    rollup = build_rollup(load_all_runs(output_root))
    write_json(output_root / "summary.json", rollup)

    print_run_summary(run_payload)
    print("")
    print(f"Saved vetting run to {run_path}")
    print(f"Updated rollup at {output_root / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
