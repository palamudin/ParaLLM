from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

import eval_runner  # type: ignore  # noqa: E402
from engine import LoopRuntime, RuntimeErrorWithCode, utc_now  # type: ignore  # noqa: E402


DEFAULT_JUDGE_PROVIDER = "openai"
DEFAULT_JUDGE_MODEL = "gpt-5.4"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "benchmarks" / "vetting"


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


def extract_answer_text(payload: Any) -> str:
    if isinstance(payload, dict):
        raw_output = payload.get("rawOutputText")
        if isinstance(raw_output, str) and raw_output.strip():
            raw_text = raw_output.strip()
            if raw_text.startswith("{") or raw_text.startswith("["):
                try:
                    decoded_raw = json.loads(raw_text)
                except json.JSONDecodeError:
                    decoded_raw = None
                if decoded_raw is not None:
                    nested = extract_answer_text(decoded_raw)
                    if nested:
                        return nested
            return raw_text
        answer_value = payload.get("answer")
        if isinstance(answer_value, str) and answer_value.strip():
            return answer_value.strip()
        if isinstance(answer_value, dict):
            nested = extract_answer_text(answer_value)
            if nested:
                return nested
        front_answer = payload.get("frontAnswer")
        if isinstance(front_answer, dict):
            nested = extract_answer_text(front_answer)
            if nested:
                return nested
        output_value = payload.get("output")
        if isinstance(output_value, dict):
            nested = extract_answer_text(output_value)
            if nested:
                return nested
        if isinstance(output_value, str) and output_value.strip():
            return output_value.strip()
        summary_value = payload.get("summary")
        if isinstance(summary_value, dict):
            nested = extract_answer_text(summary_value)
            if nested:
                return nested
    if isinstance(payload, str):
        return payload.strip()
    return ""


def load_answer_entry(entry: Dict[str, Any], repo_root: Path) -> Dict[str, Any]:
    answer_id = str(entry.get("id") or entry.get("answerId") or "").strip()
    if not answer_id:
        raise ValueError("Each answer entry needs an id.")
    label = str(entry.get("label") or answer_id).strip() or answer_id
    cohort = str(entry.get("cohort") or label).strip() or label
    family_hint = str(entry.get("familyHint") or "").strip()
    cost_note = str(entry.get("costNote") or "").strip()
    text = str(entry.get("text") or "").strip()
    artifact_file = str(entry.get("artifactFile") or "").strip()
    artifact_payload: Dict[str, Any] = {}
    elapsed_seconds = normalize_seconds(entry.get("elapsedSeconds"))
    if not text and artifact_file:
        artifact_path = Path(artifact_file)
        if not artifact_path.is_absolute():
            artifact_path = (repo_root / artifact_path).resolve()
        artifact_payload = read_json(artifact_path)
        text = extract_answer_text(artifact_payload)
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
        "familyHint": family_hint,
        "costUsd": normalize_cost(entry.get("costUsd")),
        "costNote": cost_note,
        "elapsedSeconds": elapsed_seconds,
        "text": text,
        "chars": len(text),
        "words": len(eval_runner.tokenize_compare_text(text)),
        "artifactFile": artifact_file or None,
        "provider": str(provider_trace.get("provider") or "").strip() or None,
        "model": str(provider_trace.get("model") or "").strip() or None,
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
        "mustDo": [
            "Assume the evaluator is reading for operational safety, not rhetorical polish.",
            "Reward answers that stop the blast path early, preserve evidence, and use escalation gates before destructive action.",
            "Penalize answers that jump straight to panic actions without proving the threshold.",
            "Ignore formatting noise unless it hides or distorts meaning.",
        ],
        "categories": {
            "blastRadiusPerception": "Did the answer identify the likely blast path and center early actions around it?",
            "humanUsability": "Could a tired but competent operator follow this under pressure?",
            "agentExecutability": "Could an AI or scripted assistant execute this safely with minimal ambiguity?",
            "tacticalDetail": "Did it include useful concrete checks, artifacts, and immediate tactical moves?",
            "restraintAndCollateral": "Did it avoid collateral damage and irreversible actions until gates were met?",
            "decisionGates": "Did it specify threshold-based gates for escalation, isolation, or rollback?",
            "firstHourRealism": "Does it feel like a credible first-hour plan instead of a generic checklist?",
            "overall": "Overall production quality as the answer you would ship to an operator.",
        },
        "awards": {
            "bestFinalAnswer": "The safest, clearest, most production-ready primary answer.",
            "bestTacticalDetail": "The answer that contributed the strongest useful extra checks or artifacts.",
            "bestValue": "The strongest answer relative to its declared cost / compute envelope.",
        },
        "computeVerdict": {
            "earned": "Extra compute or orchestration clearly improved the result enough to justify itself.",
            "mixed": "The gain exists but is situational, narrow, or not decisive.",
            "did_not_earn": "The extra compute or orchestration did not justify its cost or complexity.",
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
        return {
            "slot": slot,
            "answerId": str(answer.get("answerId") or "").strip(),
            "label": str(answer.get("label") or "").strip(),
            "cohort": str(answer.get("cohort") or "").strip(),
            "costUsd": answer.get("costUsd"),
            "costNote": answer.get("costNote"),
            "elapsedSeconds": answer.get("elapsedSeconds"),
        }

    scores_by_answer = {
        str(answer.get("answerId") or ""): dict(slot_result["scores"].get(str(answer.get("slot") or ""), {}))
        for answer in slotted_answers
    }
    notes_by_answer = {
        str(answer.get("answerId") or ""): str((slot_result.get("answerNotes") or {}).get(str(answer.get("slot") or ""), "")).strip()
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
    return {
        "slotResult": slot_result,
        "scoresByAnswer": scores_by_answer,
        "notesByAnswer": notes_by_answer,
        "rankingAnswers": ranking_answers,
        "bestFinalAnswer": describe_slot(str(slot_result.get("bestFinalAnswer") or "")),
        "bestTacticalDetail": describe_slot(str(slot_result.get("bestTacticalDetail") or "")),
        "bestValue": describe_slot(str(slot_result.get("bestValue") or "")),
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
    best_value = result.get("bestValue") or {}
    return "\n".join(
        [
            f"- Best final answer: `{best_final.get('slot', '')}` | {best_final.get('label', '')}",
            f"- Best tactical detail: `{best_tactical.get('slot', '')}` | {best_tactical.get('label', '')}",
            f"- Best value: `{best_value.get('slot', '')}` | {best_value.get('label', '')}",
            f"- Compute verdict: `{result.get('slotResult', {}).get('computeVerdict', 'mixed')}`",
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
    cohort_aggregates: Dict[str, Dict[str, Any]] = {}
    for run in runs:
        answers = run.get("answers") if isinstance(run.get("answers"), list) else []
        best_final = (run.get("bestFinalAnswer") or {}).get("slot")
        best_tactical = (run.get("bestTacticalDetail") or {}).get("slot")
        best_value = (run.get("bestValue") or {}).get("slot")
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
                    "bestValueWins": 0,
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
            if str(answer.get("slot") or "") == str(best_value or ""):
                aggregate["bestValueWins"] += 1
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
                "bestValueWins": int(aggregate["bestValueWins"]),
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
    return {
        "updatedAt": utc_now(),
        "runCount": len(runs),
        "cohorts": cohorts,
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
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="Judge model id. Default: gpt-5.4")
    parser.add_argument("--judge-provider", default=DEFAULT_JUDGE_PROVIDER, help="Judge provider. Default: openai")
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
    judge_model = str(args.judge_model or manifest.get("judgeModel") or DEFAULT_JUDGE_MODEL).strip() or DEFAULT_JUDGE_MODEL
    if judge_provider != "openai":
        raise SystemExit("The scripted vetting matrix currently uses the OpenAI judge path only.")

    runtime = LoopRuntime(PROJECT_ROOT)
    api_key = runtime.get_api_key(judge_provider)
    if not api_key:
        raise SystemExit("No OpenAI API key is available for the vetting judge.")

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
    try:
        slot_result = eval_runner.vetting_matrix_judge_live(
            runtime=runtime,
            api_key=api_key,
            judge_model=judge_model,
            case=case,
            judge_rubric=judge_rubric,
            answers=slot_payload,
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
        "bestValue": remapped["bestValue"],
        "categoryLeaders": remapped["categoryLeaders"],
        "markdown": {
            "scoreTable": markdown_score_table(remapped["answers"], remapped["scoresByAnswer"]),
            "legend": markdown_legend(remapped["answers"]),
            "summary": markdown_summary(remapped),
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
