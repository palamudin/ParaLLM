from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from qa_check import (
    DEFAULT_BASE_URL,
    PreservedState,
    QAError,
    api_url,
    project_root,
    qa_print,
    request_json,
    require_sequence,
    require_text,
)


AUTH_ROUTE_MODEL_SOURCE = {
    "api_key": "openai_api",
    "codex_current_user": "codex_auth",
}


def legacy_model_source(auth_route: str) -> str:
    return AUTH_ROUTE_MODEL_SOURCE.get(str(auth_route or "").strip().lower(), "openai_api")


def parse_csv(raw: str) -> list[str]:
    return [value.strip() for value in str(raw or "").split(",") if value.strip()]


def parse_counts(raw: str) -> list[int]:
    values: list[int] = []
    for item in parse_csv(raw):
        try:
            count = int(item)
        except ValueError as exc:
            raise QAError(f"Invalid worker count: {item}") from exc
        if count not in {1, 4, 8}:
            raise QAError("Provider matrix worker counts must be selected from 1, 4, and 8.")
        if count not in values:
            values.append(count)
    return values


def load_model_manifest(base_url: str) -> Dict[str, Any]:
    manifest = request_json(api_url(base_url, "models"), timeout=30)
    if str(manifest.get("schemaVersion") or "") != "parallm.provider-model-catalog.v1":
        raise QAError("The control plane returned an unsupported provider-model catalog.")
    if not isinstance(manifest.get("providers"), dict) or not isinstance(manifest.get("models"), list):
        raise QAError("The provider-model catalog is malformed.")
    return manifest


def provider_model_cases(
    manifest: Dict[str, Any],
    provider: str,
    *,
    all_models: bool,
    requested_models: set[str],
) -> list[Dict[str, str]]:
    providers = manifest.get("providers") if isinstance(manifest.get("providers"), dict) else {}
    provider_definition = providers.get(provider) if isinstance(providers.get(provider), dict) else {}
    rows = [
        row
        for row in manifest.get("models", [])
        if isinstance(row, dict) and str(row.get("provider") or "") == provider
    ]
    if requested_models:
        rows = [row for row in rows if str(row.get("id") or "") in requested_models]
    elif all_models:
        rows = [row for row in rows if bool(row.get("liveValidation"))]
    else:
        default_model = str(provider_definition.get("defaultModel") or "")
        rows = [row for row in rows if str(row.get("id") or "") == default_model]

    cases: list[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        model = str(row.get("id") or "").strip()
        if not model:
            continue
        raw_routes = row.get("authRoutes") if isinstance(row.get("authRoutes"), list) else []
        auth_routes = [str(value or "").strip().lower() for value in raw_routes if str(value or "").strip()]
        if not auth_routes:
            auth_routes = ["api_key"]
        if not all_models and not requested_models:
            preferred = "codex_current_user" if provider == "openai" and "codex_current_user" in auth_routes else auth_routes[0]
            auth_routes = [preferred]
        for auth_route in auth_routes:
            identity = (model, auth_route)
            if identity in seen:
                continue
            seen.add(identity)
            cases.append(
                {
                    "model": model,
                    "authRoute": auth_route,
                    "modelSource": legacy_model_source(auth_route),
                }
            )
    return cases


def ensure_provider_auth(base_url: str, providers: list[str], manifest: Dict[str, Any]) -> None:
    status = request_json(api_url(base_url, "auth_status"), timeout=20)
    groups = status.get("providerGroups") if isinstance(status.get("providerGroups"), dict) else {}
    provider_catalog = manifest.get("providers") if isinstance(manifest.get("providers"), dict) else {}
    missing = [
        provider
        for provider in providers
        if bool((provider_catalog.get(provider) or {}).get("credentialRequired", True))
        if not bool((groups.get(provider) or {}).get("available"))
    ]
    if missing:
        raise QAError("Provider credentials are unavailable for: " + ", ".join(missing))


def worker_definitions(count: int, model: str) -> list[Dict[str, Any]]:
    return [
        {
            "id": chr(ord("A") + index),
            "model": model,
            "activeFromRound": 1,
        }
        for index in range(count)
    ]


def wait_for_run(base_url: str, task_id: str) -> Dict[str, Any]:
    last_marker = ""
    while True:
        state = request_json(api_url(base_url, "state"), timeout=30)
        active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else {}
        if str(active_task.get("taskId") or "") != task_id:
            raise QAError(f"Active task changed while provider matrix task {task_id} was running.")
        loop = state.get("loop") if isinstance(state.get("loop"), dict) else {}
        status = str(loop.get("status") or "idle").strip().lower()
        message = str(loop.get("lastMessage") or "").strip()
        active_targets = loop.get("activeTargets") if isinstance(loop.get("activeTargets"), list) else []
        marker = f"{status}|{message}|{','.join(str(value) for value in active_targets)}"
        if marker != last_marker:
            qa_print(f"{task_id}: {status} - {message or 'waiting'}")
            last_marker = marker
        if status in {"error", "budget_exhausted", "cancelled", "interrupted"}:
            raise QAError(f"Provider matrix task {task_id} failed: {message or status}")
        if status not in {"queued", "running"}:
            summary = state.get("summary")
            if isinstance(summary, dict):
                return state
            raise QAError(f"Provider matrix task {task_id} stopped without a summary: {message or status}")
        time.sleep(0.5)


def validate_state(
    root: Path,
    base_url: str,
    state: Dict[str, Any],
    task_id: str,
    provider: str,
    model: str,
    auth_route: str,
    model_source: str,
    worker_count: int,
) -> Dict[str, Any]:
    active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else {}
    runtime = active_task.get("runtime") if isinstance(active_task.get("runtime"), dict) else {}
    if str(runtime.get("provider") or "") != provider:
        raise QAError(f"{task_id} routed through {runtime.get('provider')!r}, expected {provider!r}.")
    if str(runtime.get("model") or "") != model:
        raise QAError(f"{task_id} used model {runtime.get('model')!r}, expected {model!r}.")
    if str(runtime.get("modelSource") or "") != model_source:
        raise QAError(
            f"{task_id} used model source {runtime.get('modelSource')!r}, expected {model_source!r}."
        )
    if str(runtime.get("authRoute") or auth_route) != auth_route:
        raise QAError(
            f"{task_id} used auth route {runtime.get('authRoute')!r}, expected {auth_route!r}."
        )

    commander = state.get("commander")
    if not isinstance(commander, dict):
        raise QAError(f"{task_id} commander output was missing or malformed.")
    require_text(commander.get("answerDraft"), f"{task_id} commander.answerDraft")

    workers = state.get("workers") if isinstance(state.get("workers"), dict) else {}
    expected_ids = [chr(ord("A") + index) for index in range(worker_count)]
    if sorted(workers) != expected_ids:
        raise QAError(f"{task_id} worker map was {sorted(workers)}, expected {expected_ids}.")
    for worker_id in expected_ids:
        worker = workers.get(worker_id)
        if not isinstance(worker, dict):
            raise QAError(f"{task_id} worker {worker_id} output was missing or malformed.")
        if str(worker.get("workerId") or "") != worker_id:
            raise QAError(f"{task_id} worker {worker_id} returned the wrong identity.")
        require_text(worker.get("observation"), f"{task_id} worker {worker_id}.observation")
        require_sequence(worker.get("benefits"), f"{task_id} worker {worker_id}.benefits")
        require_sequence(worker.get("detriments"), f"{task_id} worker {worker_id}.detriments")

    review = state.get("commanderReview")
    if not isinstance(review, dict):
        raise QAError(f"{task_id} commander review was missing or malformed.")
    require_text(review.get("answerDraft"), f"{task_id} commanderReview.answerDraft")

    summary = state.get("summary")
    if not isinstance(summary, dict):
        raise QAError(f"{task_id} summary was missing or malformed.")
    answer = require_text(summary.get("frontAnswer", {}).get("answer"), f"{task_id} summary.frontAnswer.answer")
    require_text(summary.get("summarizerOpinion", {}).get("stance"), f"{task_id} summary.summarizerOpinion.stance")
    require_sequence(summary.get("lineCatalog"), f"{task_id} summary.lineCatalog")

    summary_artifact_name = f"{task_id}_summary_round001_output.json"
    summary_artifact = request_json(
        api_url(base_url, "artifact") + f"?name={summary_artifact_name}",
        timeout=30,
    )
    content = summary_artifact.get("content") if isinstance(summary_artifact.get("content"), dict) else {}
    if str(content.get("provider") or "") != provider or str(content.get("model") or "") != model:
        raise QAError(
            f"{task_id} summary artifact route was {content.get('provider')}/{content.get('model')}, "
            f"expected {provider}/{model}."
        )
    if str(content.get("mode") or "") != "live":
        raise QAError(f"{task_id} summary artifact did not use the live provider path.")

    usage = state.get("usage") if isinstance(state.get("usage"), dict) else {}
    return {
        "taskId": task_id,
        "provider": provider,
        "model": model,
        "authRoute": auth_route,
        "modelSource": model_source,
        "workerCount": worker_count,
        "workersReturned": len(workers),
        "answerChars": len(answer),
        "totalTokens": int(usage.get("totalTokens", 0) or 0),
        "estimatedCostUsd": round(float(usage.get("estimatedCostUsd", 0.0) or 0.0), 6),
        "summaryArtifact": summary_artifact_name,
    }


def run_case(
    root: Path,
    base_url: str,
    provider: str,
    model: str,
    auth_route: str,
    model_source: str,
    worker_count: int,
    task_ids: list[str],
) -> tuple[str, Dict[str, Any]]:
    objective_token = f"ROUTE_{provider.upper()}_{worker_count}_OK"
    started_at = time.monotonic()
    start = request_json(
        api_url(base_url, "task_start"),
        method="POST",
        form_data={
            "objective": (
                "Prepare a concise release-readiness recommendation for a reversible configuration change. "
                f"The final answer must include the exact verification token {objective_token}."
            ),
            "constraints": json.dumps(
                [
                    "Separate pre-change verification, execution, validation, and rollback.",
                    "Do not claim that any real system was changed.",
                    "Keep the final answer under 220 words.",
                ]
            ),
            "sessionContext": "This is a provider-routing and structured-output conformance test.",
            "workers": json.dumps(worker_definitions(worker_count, model)),
            "executionMode": "live",
            "provider": provider,
            "model": model,
            "authRoute": auth_route,
            "modelSource": model_source,
            "summarizerProvider": provider,
            "summarizerModel": model,
            "summarizerAuthRoute": auth_route,
            "summarizerModelSource": model_source,
            "engineVersion": "v1",
            "contextMode": "weighted",
            "directBaselineMode": "off",
            "reasoningEffort": "low",
            "codexSubagentsEnabled": "0",
            "codexNoTimeout": "1" if model_source == "codex_auth" else "0",
            "timeoutMode": "user",
            "targetTimeouts": json.dumps(
                {
                    "commander": 1800,
                    "workerDefault": 1800,
                    "commanderReview": 1800,
                    "summarizer": 1800,
                }
            ),
            "maxTotalTokens": "0",
            "maxCostUsd": "0",
            "maxOutputTokens": "1800",
            "researchEnabled": "0",
            "researchExternalWebAccess": "0",
            "localFilesEnabled": "0",
            "githubToolsEnabled": "0",
            "knowledgebaseEnabled": "0",
            "dynamicSpinupEnabled": "0",
            "vettingEnabled": "0",
            "loopRounds": "1",
            "loopDelayMs": "0",
        },
        timeout=60,
    )
    task_id = require_text(start.get("taskId"), "provider matrix taskId")
    task_ids.append(task_id)
    request_json(
        api_url(base_url, "loop_start"),
        method="POST",
        form_data={"rounds": "1", "delayMs": "0"},
        timeout=60,
    )
    state = wait_for_run(base_url, task_id)
    result = validate_state(root, base_url, state, task_id, provider, model, auth_route, model_source, worker_count)
    answer = str((state.get("summary") or {}).get("frontAnswer", {}).get("answer") or "")
    if objective_token not in answer:
        raise QAError(
            f"{task_id} final answer omitted required token {objective_token}. "
            f"Answer preview: {answer[:1200]!r}"
        )
    result["durationSeconds"] = round(time.monotonic() - started_at, 3)
    return task_id, result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run reversible full Para provider-routing checks at 1, 4, and 8 lanes.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--providers", default="")
    parser.add_argument("--counts", default="1,4,8")
    parser.add_argument("--all-models", action="store_true")
    parser.add_argument("--models", default="")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()
    try:
        model_manifest = load_model_manifest(args.base_url)
    except Exception as error:
        qa_print(f"FAIL: unable to load canonical model catalog: {error}")
        return 1
    catalog_providers = model_manifest.get("providers") if isinstance(model_manifest.get("providers"), dict) else {}
    providers = parse_csv(args.providers) or [provider for provider in catalog_providers if provider != "ollama"]
    counts = parse_counts(args.counts)
    requested_models = set(parse_csv(args.models))
    unsupported = [provider for provider in providers if provider not in catalog_providers]
    if unsupported:
        qa_print("FAIL: unsupported providers: " + ", ".join(unsupported))
        return 1
    ensure_provider_auth(args.base_url, providers, model_manifest)

    results: list[Dict[str, Any]] = []
    failures: list[Dict[str, str]] = []
    task_ids: list[str] = []
    selected_models: set[str] = set()
    started_at = datetime.now(timezone.utc)
    try:
        with PreservedState(root) as preserved:
            try:
                for provider in providers:
                    model_cases = provider_model_cases(
                        model_manifest,
                        provider,
                        all_models=bool(args.all_models),
                        requested_models=requested_models,
                    )
                    if not model_cases:
                        raise QAError(f"No executable model/auth-route cases were selected for provider {provider!r}.")
                    selected_models.update(str(case["model"]) for case in model_cases)
                    for model_case in model_cases:
                        model = model_case["model"]
                        auth_route = model_case["authRoute"]
                        model_source = model_case["modelSource"]
                        for count in counts:
                            qa_print(
                                f"Running {provider}/{model} via {auth_route} with {count} adversarial lane(s)"
                            )
                            try:
                                task_id, result = run_case(
                                    root,
                                    args.base_url,
                                    provider,
                                    model,
                                    auth_route,
                                    model_source,
                                    count,
                                    task_ids,
                                )
                                results.append(result)
                                qa_print(f"PASS: {provider}/{model} via {auth_route} workers={count}")
                            except Exception as error:
                                failure = {
                                    "provider": provider,
                                    "model": model,
                                    "authRoute": auth_route,
                                    "modelSource": model_source,
                                    "workerCount": str(count),
                                    "error": str(error),
                                }
                                failures.append(failure)
                                qa_print(f"FAIL: {provider}/{model} via {auth_route}: {error}")
                                if not args.continue_on_failure:
                                    raise
                unmatched_models = requested_models - selected_models
                if unmatched_models:
                    raise QAError("No selected provider matched --models: " + ", ".join(sorted(unmatched_models)))
            finally:
                if not args.keep_artifacts:
                    for task_id in task_ids:
                        preserved.cleanup_task_artifacts(task_id)
    except QAError as error:
        qa_print(f"FAIL: {error}")
        print(json.dumps({"status": "failed", "results": results, "failures": failures}, indent=2))
        return 1
    except Exception as error:
        qa_print(f"FAIL: unexpected error: {error}")
        print(json.dumps({"status": "failed", "results": results, "failures": failures}, indent=2))
        return 1

    report = {
        "schemaVersion": "parallm.python-provider-model-matrix.v1",
        "startedAt": started_at.isoformat(timespec="seconds"),
        "completedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "providers": providers,
        "workerCounts": counts,
        "allModels": bool(args.all_models),
        "modelCatalog": {
            "schemaVersion": model_manifest.get("schemaVersion"),
            "sourceSchemaVersion": model_manifest.get("sourceSchemaVersion"),
            "source": model_manifest.get("source"),
        },
        "artifactsRetained": bool(args.keep_artifacts),
        "results": results,
        "failures": failures,
        "passed": not failures,
    }
    if args.report:
        report_path = args.report if args.report.is_absolute() else root / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
