from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

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
    require_sequence,
    require_text,
    restart_runtime,
    run_http_checks,
    run_js_checks,
    run_python_checks,
)


DEFAULT_ALLOWED_DOMAINS = [
    "openai.com",
    "platform.openai.com",
    "help.openai.com",
    "developers.openai.com",
]


def normalize_allowed_domains(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_ALLOWED_DOMAINS)
    values = [item.strip().lower() for item in raw.split(",")]
    return [item for item in values if item]


def domain_is_allowed(url: str, allowed_domains: list[str]) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return False
    return any(hostname == domain or hostname.endswith("." + domain) for domain in allowed_domains)


def ensure_auth_available(base_url: str) -> None:
    status = request_json(api_url(base_url, "auth_status"), timeout=10)
    if not status.get("hasKey"):
        raise QAError("SKIP: no API key is stored locally, so the live QA smoke was not run.")


def run_live_smoke(
    root: Path,
    base_url: str,
    runtime_url: str,
    allowed_domains: list[str],
    model: str,
    summarizer_model: str,
    max_cost_usd: float,
    max_total_tokens: int,
    max_output_tokens: int,
    restart_runtime_first: bool,
) -> Dict[str, Any]:
    if restart_runtime_first:
        restart_runtime(runtime_url)

    workers = [
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
    ]

    task_id = ""
    with PreservedState(root) as preserved:
        try:
            qa_print("Starting reversible live smoke task")
            start = request_json(
                api_url(base_url, "task_start"),
                method="POST",
                form_data={
                    "objective": (
                        "Using only OpenAI-owned sources, assess whether gpt-5-mini or gpt-5.4-mini is the better low-cost default "
                        "for a local reasoning-loop prototype. Keep the answer brief and evidence-led."
                    ),
                    "constraints": json.dumps(
                        [
                            "Use only OpenAI-owned sources.",
                            "Do not claim certainty beyond the supplied evidence.",
                            "Keep the public answer concise.",
                        ]
                    ),
                    "sessionContext": "",
                    "workers": json.dumps(workers),
                    "executionMode": "live",
                    "model": model,
                    "summarizerModel": summarizer_model,
                    "reasoningEffort": "low",
                    "maxTotalTokens": str(max_total_tokens),
                    "maxCostUsd": f"{max_cost_usd:.4f}",
                    "maxOutputTokens": str(max_output_tokens),
                    "researchEnabled": "1",
                    "researchExternalWebAccess": "1",
                    "researchDomains": json.dumps(allowed_domains),
                    "vettingEnabled": "1",
                    "loopRounds": "1",
                    "loopDelayMs": "0",
                },
                timeout=30,
            )
            task_id = require_text(start.get("taskId"), "start_task taskId")

            for target in ("commander", "A", "B", "summarizer"):
                qa_print(f"Running live smoke target {target}")
                request_json(
                    api_url(base_url, "target_run"),
                    method="POST",
                    form_data={"target": target},
                    timeout=300,
                )

            state = request_json(api_url(base_url, "state"), timeout=15)
            summary = state.get("summary")
            if not isinstance(summary, dict):
                raise QAError("Live smoke summary was missing from state.")
            require_text(summary.get("frontAnswer", {}).get("answer"), "summary.frontAnswer.answer")
            require_text(summary.get("summarizerOpinion", {}).get("stance"), "summary.summarizerOpinion.stance")
            require_sequence(summary.get("lineCatalog"), "summary.lineCatalog")

            usage = state.get("usage") if isinstance(state.get("usage"), dict) else {}
            if int(usage.get("totalTokens", 0) or 0) <= 0:
                raise QAError("Live smoke usage.totalTokens did not advance.")
            if int(usage.get("webSearchCalls", 0) or 0) <= 0:
                raise QAError("Live smoke usage.webSearchCalls did not advance.")
            estimated_cost = float(usage.get("estimatedCostUsd", 0.0) or 0.0)
            if max_cost_usd > 0 and estimated_cost > max_cost_usd:
                raise QAError(
                    f"Live smoke exceeded the configured estimated cost budget: ${estimated_cost:.4f} > ${max_cost_usd:.4f}."
                )

            worker_artifacts: dict[str, Dict[str, Any]] = {}
            for worker_id in ("A", "B"):
                artifact = request_json(
                    api_url(base_url, "artifact") + f"?name={task_id}_{worker_id}_step001_output.json",
                    timeout=15,
                )
                worker_artifacts[worker_id] = artifact
                if str(artifact.get("content", {}).get("mode", "")) != "live":
                    raise QAError(f"Worker {worker_id} artifact did not stay on the live path.")
                output = artifact.get("content", {}).get("output")
                if not isinstance(output, dict):
                    raise QAError(f"Worker {worker_id} artifact output was missing.")
                require_sequence(output.get("researchSources"), f"worker {worker_id} researchSources")
                for url in output.get("researchSources", []):
                    if not domain_is_allowed(str(url), allowed_domains):
                        raise QAError(f"Worker {worker_id} consulted a source outside the allow-list: {url}")
                for url in output.get("urlCitations", []):
                    if not domain_is_allowed(str(url), allowed_domains):
                        raise QAError(f"Worker {worker_id} cited a URL outside the allow-list: {url}")

            summary_artifact_name = f"{task_id}_summary_round001_output.json"
            summary_artifact = request_json(
                api_url(base_url, "artifact") + f"?name={summary_artifact_name}",
                timeout=15,
            )
            if str(summary_artifact.get("content", {}).get("mode", "")) != "live":
                raise QAError("Summary artifact did not stay on the live path.")
            require_text(
                summary_artifact.get("content", {}).get("output", {}).get("frontAnswer", {}).get("answer"),
                "summary artifact frontAnswer.answer",
            )

            return {
                "taskId": task_id,
                "workerModels": {worker_id: worker_artifacts[worker_id].get("content", {}).get("model") for worker_id in ("A", "B")},
                "summaryModel": summary_artifact.get("content", {}).get("model"),
                "estimatedCostUsd": round(estimated_cost, 6),
                "totalTokens": int(usage.get("totalTokens", 0) or 0),
                "webSearchCalls": int(usage.get("webSearchCalls", 0) or 0),
                "allowedDomains": allowed_domains,
                "summaryArtifact": summary_artifact_name,
                "frontAnswerStance": summary.get("frontAnswer", {}).get("stance"),
            }
        finally:
            if task_id:
                qa_print(f"Cleaning reversible live smoke artifacts for {task_id}")
                preserved.cleanup_task_artifacts(task_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a reversible live-mode smoke with tight budgets and source restrictions.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base browser URL for the local app.")
    parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL, help="Resident Python runtime URL.")
    parser.add_argument("--model", default="gpt-5-mini", help="Worker model for the live smoke.")
    parser.add_argument("--summarizer-model", default="gpt-5-mini", help="Summarizer model for the live smoke.")
    parser.add_argument("--max-cost-usd", type=float, default=0.08, help="Estimated spend cap for the smoke task.")
    parser.add_argument("--max-total-tokens", type=int, default=40000, help="Token cap for the smoke task.")
    parser.add_argument("--max-output-tokens", type=int, default=500, help="Requested output cap before runtime floors apply.")
    parser.add_argument(
        "--allowed-domains",
        default=",".join(DEFAULT_ALLOWED_DOMAINS),
        help="Comma-separated allow-list for worker web search sources.",
    )
    parser.add_argument("--skip-prechecks", action="store_true", help="Skip Python/JS/http prechecks and run only the live smoke.")
    parser.add_argument("--no-restart-runtime", action="store_true", help="Do not refresh the resident runtime before the live smoke.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()
    allowed_domains = normalize_allowed_domains(args.allowed_domains)

    if not allowed_domains:
        qa_print("FAIL: no allowed domains were provided for the live smoke")
        return 1

    try:
        ensure_auth_available(args.base_url)
    except QAError as error:
        message = str(error)
        if message.startswith("SKIP:"):
            qa_print(message)
            return 0
        qa_print(f"FAIL: {message}")
        return 1

    node_bin = find_node_binary()

    qa_print(f"Project root: {root}")
    qa_print(f"Worker model: {args.model}")
    qa_print(f"Summarizer model: {args.summarizer_model}")
    qa_print(f"Allowed domains: {', '.join(allowed_domains)}")
    qa_print(f"Estimated spend cap: ${args.max_cost_usd:.4f}")

    try:
        if not args.skip_prechecks:
            run_python_checks(root)
            run_js_checks(root, node_bin)
            run_http_checks(args.base_url)
        result = run_live_smoke(
            root=root,
            base_url=args.base_url,
            runtime_url=args.runtime_url,
            allowed_domains=allowed_domains,
            model=args.model,
            summarizer_model=args.summarizer_model,
            max_cost_usd=args.max_cost_usd,
            max_total_tokens=args.max_total_tokens,
            max_output_tokens=args.max_output_tokens,
            restart_runtime_first=not args.no_restart_runtime,
        )
        qa_print("PASS")
        print(json.dumps(result, indent=2))
        return 0
    except QAError as error:
        qa_print(f"FAIL: {error}")
        return 1
    except Exception as error:
        qa_print(f"FAIL: unexpected error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
