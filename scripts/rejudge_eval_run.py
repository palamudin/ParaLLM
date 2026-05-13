from __future__ import annotations

import argparse
import shutil
import sys
import traceback
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.control import auth_file_path
from runtime.engine import (
    LoopRuntime,
    default_judge_model_for_provider,
    normalize_provider_id,
    utc_now,
)
from runtime.eval_runner import (
    aggregate_run,
    aggregate_variant,
    build_answer_telemetry,
    collect_replicate_artifacts,
    judge_provider_settings,
    read_json,
    read_run,
    replicate_dir_for,
    run_answer_health_judge,
    run_control_judge,
    run_quality_judge,
    variant_id_for_arm,
    write_json,
)


def _compact_provider_list(values: Iterable[str]) -> List[str]:
    providers: List[str] = []
    for raw in values:
        for part in str(raw or "").split(","):
            provider = normalize_provider_id(part.strip(), "")
            if provider and provider not in providers:
                providers.append(provider)
    return providers


def _run_id_for(source_run_id: str, provider: str, suffix: str) -> str:
    cleaned_suffix = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in suffix.strip())
    if cleaned_suffix:
        cleaned_suffix = "-" + cleaned_suffix.strip("-_")
    return f"{source_run_id}-rejudge-{provider}{cleaned_suffix}"


def _clone_run_header(source: Dict[str, Any], run_id: str, provider: str, judge_model: str) -> Dict[str, Any]:
    target = {
        key: deepcopy(value)
        for key, value in source.items()
        if key
        not in {
            "artifactIndex",
            "cases",
            "completedAt",
            "current",
            "error",
            "startedAt",
            "status",
            "summary",
            "traceback",
            "updatedAt",
        }
    }
    target.update(
        {
            "runId": run_id,
            "judgeProvider": provider,
            "judgeModel": judge_model,
            "previousRunId": source.get("runId"),
            "source": "rejudge-existing-answers",
            "purpose": (
                f"Rejudge source run {source.get('runId')} with {provider} "
                "while preserving the original answer artifacts."
            ),
            "artifactIndex": {},
            "cases": [],
            "status": "running",
            "startedAt": utc_now(),
            "current": None,
            "summary": None,
        }
    )
    return target


def _clone_case_entry(source_case: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in source_case.items()
        if key not in {"variants"}
    } | {"variants": []}


def _clone_variant_entry(source_variant: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in source_variant.items()
        if key not in {"replicates", "aggregate"}
    } | {"replicates": []}


def _write_run(run_dir: Path, run: Dict[str, Any]) -> None:
    run["updatedAt"] = utc_now()
    write_json(run_dir / "run.json", run)


def rejudge_provider(
    root: Path,
    source_run_id: str,
    provider: str,
    suffix: str,
    force: bool = False,
    judge_model_override: Optional[str] = None,
) -> Dict[str, Any]:
    source = read_run(root, source_run_id)
    provider = normalize_provider_id(provider, "openai")
    judge_model = str(judge_model_override or default_judge_model_for_provider(provider)).strip()
    run_id = _run_id_for(source_run_id, provider, suffix)
    target_run_dir = root / "data" / "evals" / "runs" / run_id
    if target_run_dir.exists():
        if not force:
            raise RuntimeError(f"Target run already exists: {run_id}. Use --force to replace it.")
        resolved = target_run_dir.resolve()
        allowed_root = (root / "data" / "evals" / "runs").resolve()
        if allowed_root not in resolved.parents:
            raise RuntimeError(f"Refusing to remove unexpected path: {resolved}")
        shutil.rmtree(resolved)
    target_run_dir.mkdir(parents=True, exist_ok=True)

    target = _clone_run_header(source, run_id, provider, judge_model)
    _write_run(target_run_dir, target)

    auth_path = auth_file_path(root)
    source_run_dir = root / "data" / "evals" / "runs" / source_run_id
    arm_map = {str(arm.get("armId")): arm for arm in source.get("arms", []) if isinstance(arm, dict)}

    for source_case in source.get("cases", []):
        if not isinstance(source_case, dict):
            continue
        case_id = str(source_case.get("caseId") or "").strip()
        if not case_id:
            continue
        case_entry = _clone_case_entry(source_case)
        target["cases"].append(case_entry)
        for source_variant in source_case.get("variants", []):
            if not isinstance(source_variant, dict):
                continue
            arm_id = str(source_variant.get("armId") or "").strip()
            arm = arm_map.get(arm_id)
            if not isinstance(arm, dict):
                continue
            loop_rounds = int(source_variant.get("loopRounds") or 1)
            variant_id = str(source_variant.get("variantId") or variant_id_for_arm(arm, loop_rounds))
            variant_entry = _clone_variant_entry(source_variant)
            case_entry["variants"].append(variant_entry)
            for source_replicate in source_variant.get("replicates", []):
                if not isinstance(source_replicate, dict):
                    continue
                replicate_index = int(source_replicate.get("replicate") or 1)
                source_replicate_dir = replicate_dir_for(source_run_dir, case_id, variant_id, replicate_index)
                target_replicate_dir = replicate_dir_for(target_run_dir, case_id, variant_id, replicate_index)
                target_replicate_dir.mkdir(parents=True, exist_ok=True)
                target["current"] = {
                    "caseId": case_id,
                    "variantId": variant_id,
                    "replicate": replicate_index,
                    "judgeProvider": provider,
                }
                _write_run(target_run_dir, target)
                try:
                    source_result = read_json(source_replicate_dir / "result.json")
                    public_answer = str(source_result.get("publicAnswer") or source_replicate.get("publicAnswer") or "").strip()
                    if not public_answer:
                        raise RuntimeError("Source replicate has no publicAnswer to rejudge.")

                    judge_runtime = LoopRuntime(target_replicate_dir / "_judge_runtime", auth_path=auth_path)
                    provider_settings = judge_provider_settings(target, provider)
                    selected_instance = judge_runtime.select_provider_instance(
                        None,
                        provider_settings,
                        provider,
                        judge_model,
                        "arbiter",
                        replicate_index,
                    )
                    if isinstance(selected_instance, dict):
                        provider_settings["providerInstance"] = selected_instance
                        if provider == "ollama":
                            provider_settings["ollamaBaseUrl"] = str(
                                selected_instance.get("baseUrl") or provider_settings.get("ollamaBaseUrl") or ""
                            )
                    seed = f"{run_id}:{case_id}:{variant_id}:{replicate_index}"
                    auth_assignments = judge_runtime.provider_auth_assignments(provider, "judge", salt=seed + ":judge")
                    api_key = judge_runtime.provider_live_api_key(provider, auth_assignments) or None

                    response_meta = source_result.get("responseMeta")
                    if not isinstance(response_meta, dict):
                        response_meta = source_result.get("summaryResponseMeta")
                    if not isinstance(response_meta, dict):
                        response_meta = None
                    telemetry = build_answer_telemetry(
                        public_answer,
                        response_meta,
                        str(source_result.get("provider") or ""),
                        str(source_result.get("model") or ""),
                    )
                    judge_memory_context = str(
                        source_result.get("judgeMemoryContext") or source_replicate.get("judgeMemoryContext") or ""
                    )
                    quality = run_quality_judge(
                        judge_runtime,
                        provider,
                        api_key,
                        judge_model,
                        source_case,
                        target.get("suite", {}).get("judgeRubric", {}),
                        public_answer,
                        provider_settings,
                        judge_memory_context,
                    )
                    answer_health = run_answer_health_judge(
                        judge_runtime,
                        provider,
                        api_key,
                        judge_model,
                        source_case,
                        public_answer,
                        telemetry,
                        provider_settings,
                        judge_memory_context,
                    )
                    summary = source_result.get("summary") if isinstance(source_result.get("summary"), dict) else None
                    control = (
                        run_control_judge(
                            judge_runtime,
                            provider,
                            api_key,
                            judge_model,
                            source_case,
                            summary,
                            provider_settings,
                            judge_memory_context,
                        )
                        if arm.get("type") == "steered" and isinstance(summary, dict)
                        else None
                    )
                    usage = deepcopy(source_replicate.get("usage") or source_result.get("usage") or {})
                    score_payload = {
                        "runId": run_id,
                        "caseId": case_id,
                        "armId": arm_id,
                        "variantId": variant_id,
                        "replicate": replicate_index,
                        "sourceRunId": source_run_id,
                        "deterministic": deepcopy(source_replicate.get("deterministic") or {}),
                        "quality": quality,
                        "answerHealth": answer_health,
                        "control": control,
                        "baselineQuality": None,
                        "baselineAnswerHealth": None,
                        "comparison": None,
                        "usage": usage,
                        "answerPathCallPlan": deepcopy(source_replicate.get("answerPathCallPlan")),
                        "judgeMemoryContext": judge_memory_context,
                        "generatedAt": utc_now(),
                    }
                    write_json(target_replicate_dir / "score.json", score_payload)
                    result_payload = {
                        "runId": run_id,
                        "caseId": case_id,
                        "armId": arm_id,
                        "variantId": variant_id,
                        "replicate": replicate_index,
                        "sourceRunId": source_run_id,
                        "mode": source_result.get("mode") or source_replicate.get("mode"),
                        "provider": source_result.get("provider"),
                        "model": source_result.get("model"),
                        "answerPath": source_result.get("answerPath") if arm.get("type") == "steered" else "off",
                        "contextMode": source_result.get("contextMode") or arm.get("runtime", {}).get("contextMode"),
                        "modeState": deepcopy(source_result.get("modeState") or source_replicate.get("modeState") or {}),
                        "usage": usage,
                        "judgeMemoryContext": judge_memory_context,
                        "publicAnswer": public_answer,
                        "answerHealth": answer_health,
                        "summary": summary,
                        "quality": quality,
                        "control": control,
                        "generatedAt": utc_now(),
                    }
                    write_json(target_replicate_dir / "result.json", result_payload)
                    artifacts = collect_replicate_artifacts(
                        target,
                        target_run_dir,
                        case_id,
                        variant_id,
                        replicate_index,
                        target_replicate_dir,
                    )
                    replicate_result = {
                        "replicate": replicate_index,
                        "status": "completed",
                        "publicAnswer": public_answer,
                        "usage": usage,
                        "answerPathCallPlan": deepcopy(source_replicate.get("answerPathCallPlan")),
                        "judgeMemoryContext": judge_memory_context,
                        "mode": source_result.get("mode") or source_replicate.get("mode"),
                        "answerPath": source_result.get("answerPath") if arm.get("type") == "steered" else "off",
                        "contextMode": source_result.get("contextMode") or arm.get("runtime", {}).get("contextMode"),
                        "modeState": deepcopy(source_result.get("modeState") or source_replicate.get("modeState") or {}),
                        "deterministic": deepcopy(source_replicate.get("deterministic") or {}),
                        "quality": quality,
                        "answerHealth": answer_health,
                        "control": control,
                        "baselineQuality": None,
                        "baselineAnswerHealth": None,
                        "comparison": None,
                        "artifactIds": [entry["artifactId"] for entry in artifacts],
                        "artifacts": artifacts,
                        "updatedAt": utc_now(),
                    }
                except Exception as exc:
                    write_json(
                        target_replicate_dir / "score.json",
                        {
                            "runId": run_id,
                            "caseId": case_id,
                            "armId": arm_id,
                            "variantId": variant_id,
                            "replicate": replicate_index,
                            "sourceRunId": source_run_id,
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                            "generatedAt": utc_now(),
                        },
                    )
                    replicate_result = {
                        "replicate": replicate_index,
                        "status": "error",
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        "updatedAt": utc_now(),
                        "artifactIds": [],
                        "artifacts": [],
                    }
                variant_entry["replicates"].append(replicate_result)
                variant_entry["aggregate"] = aggregate_variant(variant_entry)
                _write_run(target_run_dir, target)
    target["summary"] = aggregate_run(target)
    target["status"] = "completed"
    target["completedAt"] = utc_now()
    target["current"] = None
    _write_run(target_run_dir, target)
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rejudge an existing eval run's answer artifacts with another judge provider.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--source-run-id", required=True, help="Existing eval run to rejudge.")
    parser.add_argument("--provider", action="append", required=True, help="Judge provider. Repeat or comma-separate.")
    parser.add_argument(
        "--judge-model",
        action="append",
        default=[],
        help="Optional model override. Use provider=model for one provider, or model when running a single provider.",
    )
    parser.add_argument("--suffix", default="", help="Run id suffix.")
    parser.add_argument("--force", action="store_true", help="Replace existing target rejudge run directories.")
    return parser.parse_args()


def _judge_model_overrides(values: Iterable[str], providers: List[str]) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    raw_values = [str(value or "").strip() for value in values if str(value or "").strip()]
    if len(providers) == 1 and len(raw_values) == 1 and "=" not in raw_values[0]:
        overrides[providers[0]] = raw_values[0]
        return overrides
    for raw in raw_values:
        if "=" not in raw:
            continue
        provider, model = raw.split("=", 1)
        normalized = normalize_provider_id(provider.strip(), "")
        if normalized and model.strip():
            overrides[normalized] = model.strip()
    return overrides


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    providers = _compact_provider_list(args.provider)
    if not providers:
        raise SystemExit("No valid providers supplied.")
    model_overrides = _judge_model_overrides(args.judge_model, providers)
    for provider in providers:
        run = rejudge_provider(
            root,
            args.source_run_id,
            provider,
            args.suffix,
            force=bool(args.force),
            judge_model_override=model_overrides.get(provider),
        )
        summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
        print(
            f"{run['runId']} completed: errors={summary.get('errorCount')} "
            f"quality={((summary.get('averageQuality') or {}).get('overallQuality'))} "
            f"ownerQuality={((summary.get('averageQualityAudit') or {}).get('overallOwnerProtection'))}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
