from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from qa_check import (
    DEFAULT_BASE_URL,
    PreservedState,
    QAError,
    api_url,
    find_node_binary,
    project_root,
    qa_print,
    request_json,
    run_http_checks,
    run_js_checks,
    run_python_checks,
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_for_eval_run(base_url: str, run_id: str, timeout_seconds: float = 120.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload: dict | None = None
    while time.time() < deadline:
        last_payload = request_json(api_url(base_url, "eval_history") + f"?runId={run_id}", timeout=20)
        selected = last_payload.get("selectedRun")
        if isinstance(selected, dict) and selected.get("status") in {"completed", "error"}:
            return last_payload
        time.sleep(2.0)
    raise QAError(f"Eval run {run_id} did not finish within {timeout_seconds:.1f}s. Last payload: {json.dumps(last_payload or {}, indent=2)}")


def validate_isolated_snapshot(root: Path, run_id: str) -> None:
    task_dir = root / "data" / "evals" / "runs" / run_id / "cases" / "internal-rollout" / "steered-mock--loops-1" / "replicate-001" / "workspace" / "data" / "tasks"
    task_files = sorted(task_dir.glob("*.json"))
    if not task_files:
        raise QAError("Isolated steered task snapshot was missing.")
    raw = task_files[0].read_text(encoding="utf-8")
    for forbidden in ['"gold"', 'judgeRubric', '"checks"']:
        if forbidden in raw:
            raise QAError(f"Isolated task snapshot leaked eval-only metadata: {forbidden}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an isolated eval smoke against the dedicated eval subsystem.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base browser URL for the local app.")
    parser.add_argument("--skip-prechecks", action="store_true", help="Skip Python/JS/http prechecks.")
    args = parser.parse_args()

    root = project_root()
    if not args.skip_prechecks:
        run_python_checks(root)
        run_js_checks(root, find_node_binary())
        run_http_checks(args.base_url)

    state_path = root / "data" / "state.json"
    state_hash_before = file_sha256(state_path)

    with PreservedState(root):
        qa_print("Starting isolated mock eval smoke")
        start = request_json(
            api_url(args.base_url, "eval_run_start"),
            method="POST",
            form_data={
                "suiteId": "smoke-mock",
                "armIds": json.dumps(["direct-mock", "steered-mock"]),
                "replicates": "1",
                "loopSweep": "1,2",
            },
            timeout=30,
        )
        run_id = str(start.get("runId") or "").strip()
        if not run_id:
            raise QAError("eval_run_start did not return a runId.")

        payload = wait_for_eval_run(args.base_url, run_id)
        selected = payload.get("selectedRun")
        if not isinstance(selected, dict):
            raise QAError("Eval history did not return selectedRun.")
        if selected.get("status") != "completed":
            raise QAError(f"Eval run finished in unexpected status {selected.get('status')}: {selected.get('error')}")

        summary = selected.get("summary") if isinstance(selected.get("summary"), dict) else {}
        if int(summary.get("caseCount", 0) or 0) < 1:
            raise QAError("Eval run summary did not include any cases.")
        if int(summary.get("variantCount", 0) or 0) < 3:
            raise QAError("Eval run summary did not include the expected direct + loop-swept steered variants.")

        artifacts = selected.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise QAError("Eval run did not expose any review artifacts.")
        first_artifact = artifacts[0]
        artifact_id = str(first_artifact.get("artifactId") or "").strip()
        if not artifact_id:
            raise QAError("Eval artifact list did not contain artifact ids.")

        artifact = request_json(
            api_url(args.base_url, "eval_artifact") + f"?runId={run_id}&artifactId={artifact_id}",
            timeout=20,
        )
        if artifact.get("storage") != "eval":
            raise QAError("Eval artifact endpoint did not report eval storage.")
        if not isinstance(artifact.get("content"), dict):
            raise QAError("Eval artifact endpoint did not return JSON content.")

        validate_isolated_snapshot(root, run_id)
        qa_print(f"PASS: isolated eval smoke completed for {run_id}")

    state_hash_after = file_sha256(state_path)
    if state_hash_before != state_hash_after:
        raise QAError("Interactive data/state.json was not restored after the isolated eval smoke.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
