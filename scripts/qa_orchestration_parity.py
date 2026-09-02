from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NATIVE_DEV = ROOT / "deployment" / "dev"
for import_root in (SCRIPTS, NATIVE_DEV):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from qa_check import PreservedState, QAError, api_url, request_json  # noqa: E402
from qa_provider_matrix_live import (  # noqa: E402
    validate_state,
    wait_for_run,
    worker_definitions,
)
from verify_native_provider_matrix import http_json as native_http_json  # noqa: E402
from verify_native_provider_matrix import validate_trace as validate_native_trace  # noqa: E402


DEFAULT_PYTHON_URL = "http://127.0.0.1:8787"
DEFAULT_NATIVE_URL = "http://127.0.0.1:8790"
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_REPORT = ROOT / "deployment" / "dev" / "audits" / "python-native-orchestration-parity-latest.json"
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r'"authorization"\s*:\s*"bearer\s+[^"*]{16,}"', re.IGNORECASE),
    re.compile(r"\bBearer\s+eyJ[A-Za-z0-9._-]{20,}", re.IGNORECASE),
)


def parse_counts(raw: str) -> list[int]:
    counts: list[int] = []
    for item in str(raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            count = int(item)
        except ValueError as exc:
            raise QAError(f"Invalid lane count: {item}") from exc
        if count not in {1, 4, 8}:
            raise QAError("Parity lane counts must be selected from 1, 4, and 8.")
        if count not in counts:
            counts.append(count)
    if not counts:
        raise QAError("At least one parity lane count is required.")
    return counts


def parity_prompt(count: int) -> tuple[str, str]:
    token = f"PARITY_LANES_{count}_OK"
    prompt = (
        "ORCHESTRATION PARITY CHECK. Review a hypothetical, reversible service configuration change. "
        "Give a concise release-readiness recommendation that clearly separates pre-change verification, "
        "execution, validation, and rollback. Do not claim that any real system was changed. State the main "
        "uncertainty and one concrete stop condition. Keep the final answer under 220 words and include the "
        f"exact verification token {token}."
    )
    return prompt, token


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def text_payload(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def assert_no_plaintext_secrets(label: str, value: Any) -> None:
    text = text_payload(value)
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise QAError(f"{label} appears to contain a plaintext credential.")


def python_provider_artifacts() -> set[Path]:
    return set((ROOT / "data" / "provider_calls").glob("*.json"))


def inspect_python_audit(task_id: str, prompt: str, before: set[Path], expected_calls: int) -> dict[str, Any]:
    created = sorted(python_provider_artifacts() - before, key=lambda path: path.stat().st_mtime_ns)
    records: list[tuple[Path, dict[str, Any]]] = []
    for path in created:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and str(payload.get("taskId") or "") == task_id:
            records.append((path, payload))

    completed = [(path, payload) for path, payload in records if payload.get("status") == "completed"]
    if len(completed) < expected_calls:
        raise QAError(
            f"Python audit retained {len(completed)} completed provider calls for {task_id}; "
            f"expected at least {expected_calls}."
        )

    call_rows: list[dict[str, Any]] = []
    for path, payload in completed:
        request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
        integrity = payload.get("integrity") if isinstance(payload.get("integrity"), dict) else {}
        instructions = str(request.get("instructions") or "")
        input_text = str(request.get("inputText") or "")
        output_text = str(response.get("rawOutputText") or "")
        raw_response = response.get("rawResponse")
        integrity_hash = str(integrity.get("sha256") or "")

        if not instructions.strip():
            raise QAError(f"Python audit {path.name} omitted provider instructions.")
        if prompt not in input_text:
            raise QAError(f"Python audit {path.name} omitted the exact user prompt from assembled input.")
        if not output_text.strip():
            raise QAError(f"Python audit {path.name} omitted human-readable vendor output.")
        if len(integrity_hash) != 64:
            raise QAError(f"Python audit {path.name} omitted its integrity hash.")
        if int(integrity.get("requestChars") or 0) <= 0 or int(integrity.get("responseChars") or 0) <= 0:
            raise QAError(f"Python audit {path.name} omitted request/response lengths.")
        assert_no_plaintext_secrets(f"Python audit {path.name}", payload)

        call_rows.append(
            {
                "artifact": str(path.relative_to(ROOT)),
                "target": payload.get("target"),
                "provider": payload.get("provider"),
                "model": payload.get("model"),
                "status": payload.get("status"),
                "promptPresent": True,
                "instructionsChars": len(instructions),
                "inputChars": len(input_text),
                "outputChars": len(output_text),
                "rawCallbackPresent": raw_response not in (None, "", {}, []),
                "integritySha256": integrity_hash,
            }
        )

    return {
        "recordCount": len(records),
        "completedCount": len(completed),
        "humanReadableCount": len(call_rows),
        "promptSha256": sha256_text(prompt),
        "calls": call_rows,
    }


def run_python_case(base_url: str, model: str, count: int) -> dict[str, Any]:
    prompt, token = parity_prompt(count)
    before = python_provider_artifacts()
    started = time.monotonic()
    start = request_json(
        api_url(base_url, "task_start"),
        method="POST",
        form_data={
            "objective": prompt,
            "constraints": "[]",
            "sessionContext": "",
            "workers": json.dumps(worker_definitions(count, model)),
            "executionMode": "live",
            "provider": "openai",
            "model": model,
            "authRoute": "codex_current_user",
            "modelSource": "codex_auth",
            "summarizerProvider": "openai",
            "summarizerModel": model,
            "summarizerAuthRoute": "codex_current_user",
            "summarizerModelSource": "codex_auth",
            "engineVersion": "v1",
            "contextMode": "weighted",
            "directBaselineMode": "off",
            "reasoningEffort": "low",
            "codexSubagentsEnabled": "0",
            "codexNoTimeout": "1",
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
    task_id = str(start.get("taskId") or "").strip()
    if not task_id:
        raise QAError(f"Python task creation did not return a task id: {start}")
    request_json(
        api_url(base_url, "loop_start"),
        method="POST",
        form_data={"rounds": "1", "delayMs": "0"},
        timeout=60,
    )
    state = wait_for_run(base_url, task_id)
    validation = validate_state(
        ROOT,
        base_url,
        state,
        task_id,
        "openai",
        model,
        "codex_current_user",
        "codex_auth",
        count,
    )
    answer = str((state.get("summary") or {}).get("frontAnswer", {}).get("answer") or "").strip()
    if token not in answer:
        raise QAError(f"Python final answer omitted {token}: {answer[:800]!r}")
    audit = inspect_python_audit(task_id, prompt, before, expected_calls=count + 3)
    return {
        "runtime": "python",
        "taskId": task_id,
        "laneCount": count,
        "model": model,
        "prompt": prompt,
        "promptSha256": sha256_text(prompt),
        "token": token,
        "answer": answer,
        "answerSha256": sha256_text(answer),
        "durationSeconds": round(time.monotonic() - started, 3),
        "validation": validation,
        "audit": audit,
    }


def native_config_form(config: dict[str, Any]) -> dict[str, str]:
    return {
        "provider": str(config.get("provider") or "openai"),
        "authMode": str(config.get("authMode") or "codex_current_user"),
        "authProfileId": str(config.get("authProfileId") or ""),
        "model": str(config.get("model") or DEFAULT_MODEL),
        "reasoningEffort": str(config.get("reasoningEffort") or "low"),
        "workerCount": str(int(config.get("workerCount") or 1)),
        "memoryEnabled": "true" if bool(config.get("memoryEnabled")) else "false",
        "toolsEnabled": "true" if bool(config.get("toolsEnabled")) else "false",
        "apiKeyEnvironment": str(config.get("apiKeyEnvironment") or "OPENAI_API_KEY"),
        "apiKeyFileEnvironment": str(config.get("apiKeyFileEnvironment") or "OPENAI_API_KEY_FILE"),
    }


def inspect_native_audit(base_url: str, task_id: str, prompt: str, expected_calls: int) -> dict[str, Any]:
    index = native_http_json(base_url + "/v1/audit/calls?limit=1000", timeout=60)
    rows = [
        row
        for row in (index.get("items") if isinstance(index.get("items"), list) else [])
        if isinstance(row, dict) and str(row.get("taskId") or "") == task_id
    ]
    completed = [row for row in rows if row.get("status") == "completed"]
    if len(completed) < expected_calls:
        raise QAError(
            f"Native audit exposed {len(completed)} completed provider calls for {task_id}; "
            f"expected at least {expected_calls}."
        )

    detail_rows: list[dict[str, Any]] = []
    for row in completed:
        call_id = str(row.get("callId") or "")
        query = urllib.parse.urlencode({"callId": call_id, "raw": "true"})
        detail = native_http_json(base_url + "/v1/audit/call?" + query, timeout=120)
        objective = str(detail.get("objective") or "")
        instructions = str(detail.get("instructions") or "")
        input_text = str(detail.get("inputText") or "")
        output_text = str(detail.get("outputText") or "")
        raw_response = detail.get("rawResponse")
        hashes = {
            "instructionsSha256": str(detail.get("instructionsSha256") or ""),
            "inputSha256": str(detail.get("inputSha256") or ""),
            "outputSha256": str(detail.get("outputSha256") or ""),
        }
        if objective != prompt:
            raise QAError(f"Native audit {call_id} did not retain the exact user objective.")
        if not instructions.strip():
            raise QAError(f"Native audit {call_id} omitted provider instructions.")
        if prompt not in input_text:
            raise QAError(f"Native audit {call_id} omitted the exact prompt from assembled lane input.")
        if not output_text.strip():
            raise QAError(f"Native audit {call_id} omitted human-readable vendor output.")
        if raw_response in (None, "", {}, []):
            raise QAError(f"Native audit {call_id} omitted the raw vendor callback.")
        if any(len(value) != 64 for value in hashes.values()):
            raise QAError(f"Native audit {call_id} omitted one or more content hashes.")
        assert_no_plaintext_secrets(f"Native audit {call_id}", detail)
        detail_rows.append(
            {
                "callId": call_id,
                "stage": detail.get("stage"),
                "laneId": detail.get("laneId"),
                "provider": detail.get("provider"),
                "model": detail.get("model"),
                "status": detail.get("status"),
                "httpStatus": detail.get("httpStatus"),
                "durationMs": detail.get("durationMs"),
                "promptExact": True,
                "instructionsChars": len(instructions),
                "inputChars": len(input_text),
                "outputChars": len(output_text),
                "rawCallbackPresent": True,
                **hashes,
            }
        )

    return {
        "recordCount": len(rows),
        "completedCount": len(completed),
        "humanReadableCount": len(detail_rows),
        "promptSha256": sha256_text(prompt),
        "calls": detail_rows,
    }


def run_native_case(base_url: str, model: str, count: int, timeout: int) -> dict[str, Any]:
    prompt, token = parity_prompt(count)
    config = native_http_json(
        base_url + "/v1/config/apply",
        form={
            "provider": "openai",
            "authMode": "codex_current_user",
            "authProfileId": "",
            "model": model,
            "reasoningEffort": "low",
            "workerCount": str(count),
            "memoryEnabled": "false",
            "toolsEnabled": "false",
            "apiKeyEnvironment": "OPENAI_API_KEY",
            "apiKeyFileEnvironment": "OPENAI_API_KEY_FILE",
        },
        timeout=60,
    )
    if config.get("provider") != "openai" or config.get("model") != model:
        raise QAError(f"Native runtime selected an unexpected route: {config}")

    started = time.monotonic()
    response = native_http_json(
        base_url + "/v1/chat",
        form={
            "prompt": prompt,
            "sessionId": f"native-parity-{count}-{time.time_ns()}",
        },
        timeout=timeout,
    )
    task_id = str(response.get("taskId") or "").strip()
    if not task_id:
        raise QAError(f"Native chat did not return a task id: {response}")
    trace_query = urllib.parse.urlencode({"taskId": task_id, "raw": "false"})
    trace = native_http_json(base_url + "/v1/task?" + trace_query, timeout=60)
    validation = validate_native_trace(
        trace,
        provider="openai",
        model=model,
        count=count,
        token=token,
        response=response,
    )
    answer = str(trace.get("answer") or response.get("summary") or "").strip()
    audit = inspect_native_audit(base_url, task_id, prompt, expected_calls=count + 3)
    return {
        "runtime": "native",
        "taskId": task_id,
        "laneCount": count,
        "model": model,
        "prompt": prompt,
        "promptSha256": sha256_text(prompt),
        "token": token,
        "answer": answer,
        "answerSha256": sha256_text(answer),
        "durationSeconds": round(time.monotonic() - started, 3),
        "validation": validation,
        "audit": audit,
    }


def answer_terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) > 3}


def compare_cases(python_case: dict[str, Any], native_case: dict[str, Any]) -> dict[str, Any]:
    if python_case["promptSha256"] != native_case["promptSha256"]:
        raise QAError("Python and native cases did not receive byte-identical prompts.")
    python_terms = answer_terms(str(python_case.get("answer") or ""))
    native_terms = answer_terms(str(native_case.get("answer") or ""))
    union = python_terms | native_terms
    overlap = len(python_terms & native_terms) / len(union) if union else 1.0
    return {
        "promptByteIdentical": True,
        "promptSha256": python_case["promptSha256"],
        "bothReturnedRequiredToken": (
            python_case["token"] in python_case["answer"] and native_case["token"] in native_case["answer"]
        ),
        "lexicalJaccard": round(overlap, 4),
        "pythonAnswerChars": len(python_case["answer"]),
        "nativeAnswerChars": len(native_case["answer"]),
        "pythonAuditCalls": python_case["audit"]["completedCount"],
        "nativeAuditCalls": native_case["audit"]["completedCount"],
        "auditHumanReadable": (
            python_case["audit"]["humanReadableCount"] == python_case["audit"]["completedCount"]
            and native_case["audit"]["humanReadableCount"] == native_case["audit"]["completedCount"]
        ),
    }


def write_markdown_report(report_path: Path, report: dict[str, Any]) -> Path:
    markdown_path = report_path.with_suffix(".md")
    lines = [
        "# Python / Native Orchestration Parity",
        "",
        f"- Completed: `{report['completedAt']}`",
        f"- Model: `{report['model']}` via current-user Codex authentication",
        f"- Passed: `{'yes' if report['passed'] else 'no'}`",
        "- Memory, research, external tools, dynamic spin-up, vetting, and vendor subagents were disabled.",
        "",
        "| Lanes | Python | Native | Prompt exact | Human-readable audit | Lexical overlap |",
        "| ---: | :---: | :---: | :---: | :---: | ---: |",
    ]
    by_count = {int(case["laneCount"]): case for case in report.get("cases", [])}
    for count in report.get("laneCounts", []):
        case = by_count.get(int(count), {})
        comparison = case.get("comparison") if isinstance(case.get("comparison"), dict) else {}
        lines.append(
            f"| {count} | {'pass' if case.get('python') else 'fail'} | "
            f"{'pass' if case.get('native') else 'fail'} | "
            f"{'yes' if comparison.get('promptByteIdentical') else 'no'} | "
            f"{'yes' if comparison.get('auditHumanReadable') else 'no'} | "
            f"{comparison.get('lexicalJaccard', 'n/a')} |"
        )
    if report.get("failures"):
        lines.extend(["", "## Failures", ""])
        for failure in report["failures"]:
            lines.append(
                f"- `{failure.get('runtime')}` lanes `{failure.get('laneCount')}`: {failure.get('error')}"
            )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return markdown_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run byte-identical 1/4/8-lane orchestration and audit parity checks on Python and native Para."
    )
    parser.add_argument("--python-url", default=DEFAULT_PYTHON_URL)
    parser.add_argument("--native-url", default=DEFAULT_NATIVE_URL)
    parser.add_argument("--counts", default="1,4,8")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    counts = parse_counts(args.counts)
    report_path = args.report if args.report.is_absolute() else ROOT / args.report
    original_native_config = native_http_json(args.native_url.rstrip("/") + "/v1/config", timeout=60)
    started_at = datetime.now(timezone.utc)
    cases: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    try:
        with PreservedState(ROOT):
            for count in counts:
                print(f"RUN  python openai/{args.model} lanes={count}", flush=True)
                python_case: dict[str, Any] | None = None
                native_case: dict[str, Any] | None = None
                try:
                    python_case = run_python_case(args.python_url.rstrip("/"), args.model, count)
                    print(
                        f"PASS python lanes={count} audit={python_case['audit']['completedCount']} "
                        f"duration={python_case['durationSeconds']}s",
                        flush=True,
                    )
                except Exception as exc:
                    failures.append({"runtime": "python", "laneCount": count, "error": str(exc)})
                    print(f"FAIL python lanes={count}: {exc}", flush=True)

                print(f"RUN  native openai/{args.model} lanes={count}", flush=True)
                try:
                    native_case = run_native_case(args.native_url.rstrip("/"), args.model, count, args.timeout)
                    print(
                        f"PASS native lanes={count} audit={native_case['audit']['completedCount']} "
                        f"duration={native_case['durationSeconds']}s",
                        flush=True,
                    )
                except Exception as exc:
                    failures.append({"runtime": "native", "laneCount": count, "error": str(exc)})
                    print(f"FAIL native lanes={count}: {exc}", flush=True)

                case: dict[str, Any] = {"laneCount": count}
                if python_case is not None:
                    case["python"] = python_case
                if native_case is not None:
                    case["native"] = native_case
                if python_case is not None and native_case is not None:
                    try:
                        case["comparison"] = compare_cases(python_case, native_case)
                    except Exception as exc:
                        failures.append({"runtime": "comparison", "laneCount": count, "error": str(exc)})
                cases.append(case)
    finally:
        native_http_json(
            args.native_url.rstrip("/") + "/v1/config/apply",
            form=native_config_form(original_native_config),
            timeout=60,
        )

    report = {
        "schemaVersion": "parallm.python-native-orchestration-parity.v1",
        "startedAt": started_at.isoformat(timespec="seconds"),
        "completedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pythonUrl": args.python_url,
        "nativeUrl": args.native_url,
        "model": args.model,
        "authRoute": "codex_current_user",
        "reasoningEffort": "low",
        "laneCounts": counts,
        "isolation": {
            "memory": False,
            "research": False,
            "tools": False,
            "dynamicSpinup": False,
            "vetting": False,
            "vendorSubagents": False,
        },
        "cases": cases,
        "failures": failures,
        "passed": not failures and len(cases) == len(counts),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path = write_markdown_report(report_path, report)
    print(json.dumps({"passed": report["passed"], "report": str(report_path), "markdown": str(markdown_path)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
