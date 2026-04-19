from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_BASE_URL = "http://127.0.0.1/loop"
DEFAULT_RUNTIME_URL = os.getenv("LOOP_RUNTIME_URL", "http://127.0.0.1:8765")


class QAError(RuntimeError):
    pass


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def qa_print(message: str) -> None:
    print(f"[qa] {message}")


def find_php_binary(root: Path) -> str:
    candidates = [
        os.getenv("LOOP_PHP_BIN"),
        os.getenv("PHP_BIN"),
        shutil.which("php"),
        str(Path("C:/xampp/php/php.exe")),
        str(root.parents[1] / "php" / "php.exe") if len(root.parents) >= 2 else None,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    raise QAError("PHP executable not found. Set LOOP_PHP_BIN or install PHP locally.")


def find_node_binary() -> Optional[str]:
    candidates = [
        os.getenv("LOOP_NODE_BIN"),
        os.getenv("NODE_BIN"),
        shutil.which("node"),
        str(Path("C:/Program Files/nodejs/node.exe")),
        str(Path("C:/Program Files (x86)/nodejs/node.exe")),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return None


def run_command(argv: list[str], cwd: Path, label: str) -> None:
    qa_print(label)
    result = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True)
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    if result.returncode != 0:
        raise QAError(f"{label} failed with exit code {result.returncode}.")


def request(
    url: str,
    method: str = "GET",
    form_data: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> tuple[int, str]:
    headers = {"Accept": "application/json, text/plain;q=0.9, */*;q=0.8"}
    payload: Optional[bytes] = None
    if form_data is not None:
        encoded = urllib.parse.urlencode({key: str(value) for key, value in form_data.items()})
        payload = encoded.encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url=url, data=payload, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return int(response.status), body
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return int(error.code), body
    except urllib.error.URLError as error:
        raise QAError(f"HTTP request failed for {url}: {error}") from error


def request_json(
    url: str,
    method: str = "GET",
    form_data: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    status, body = request(url, method=method, form_data=form_data, timeout=timeout)
    if status < 200 or status >= 300:
        raise QAError(f"Request to {url} returned HTTP {status}: {body}")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        raise QAError(f"Response from {url} was not valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise QAError(f"Response from {url} was not a JSON object.")
    return parsed


def wait_for_runtime_state(runtime_url: str, should_be_online: bool, timeout_seconds: float = 8.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            health = request_json(runtime_url.rstrip("/") + "/health", timeout=2)
            if should_be_online and health.get("ok"):
                return
        except QAError:
            if not should_be_online:
                return
        time.sleep(0.2)
    expected = "online" if should_be_online else "offline"
    raise QAError(f"Resident runtime did not become {expected} within {timeout_seconds:.1f}s.")


def restart_runtime(runtime_url: str) -> None:
    health_url = runtime_url.rstrip("/") + "/health"
    qa_print("Refreshing resident Python runtime to avoid stale loaded code")
    try:
        health = request_json(health_url, timeout=2)
    except QAError:
        qa_print("Resident runtime is already offline")
        return
    pid = int(health.get("pid", 0) or 0)
    if pid <= 0:
        raise QAError("Resident runtime health response did not include a valid pid.")
    if os.name == "nt":
        run_command(["taskkill", "/PID", str(pid), "/F"], project_root(), f"Stopping resident runtime pid {pid}")
    else:
        os.kill(pid, 15)
    wait_for_runtime_state(runtime_url, should_be_online=False)


class PreservedState:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.temp_dir = Path(tempfile.mkdtemp(prefix="loop-qa-"))
        self.files = {
            "state": self.root / "data" / "state.json",
            "events": self.root / "data" / "events.jsonl",
            "steps": self.root / "data" / "steps.jsonl",
        }

    def __enter__(self) -> "PreservedState":
        for name, path in self.files.items():
            shutil.copy2(path, self.temp_dir / f"{name}{path.suffix}")
        return self

    def restore(self) -> None:
        for name, path in self.files.items():
            shutil.copy2(self.temp_dir / f"{name}{path.suffix}", path)

    def cleanup_task_artifacts(self, task_id: str) -> None:
        directories = [
            self.root / "data" / "tasks",
            self.root / "data" / "checkpoints",
            self.root / "data" / "outputs",
        ]
        patterns = [
            f"{task_id}.json",
            f"{task_id}_*",
            f"{task_id}*",
        ]
        for directory in directories:
            if not directory.exists():
                continue
            seen: set[Path] = set()
            for pattern in patterns:
                for path in directory.glob(pattern):
                    if path in seen or not path.is_file():
                        continue
                    seen.add(path)
                    path.unlink(missing_ok=True)

        for directory in (self.root / "data" / "jobs", self.root / "data" / "sessions"):
            if not directory.exists():
                continue
            for path in directory.glob("*.json"):
                if not path.is_file():
                    continue
                try:
                    content = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(content, dict):
                    continue
                if str(content.get("taskId") or "") == task_id:
                    path.unlink(missing_ok=True)

    def __exit__(self, exc_type, exc, tb) -> None:
        self.restore()
        shutil.rmtree(self.temp_dir, ignore_errors=True)


def require_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise QAError(f"{label} was empty.")
    return text


def require_sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise QAError(f"{label} was missing or empty.")
    return value


def api_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/api/" + path.lstrip("/")


def http_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def wait_for_loop_clear(base_url: str, timeout_seconds: float = 45.0) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_state: Dict[str, Any] | None = None
    while time.time() < deadline:
        last_state = request_json(api_url(base_url, "get_state.php"), timeout=10)
        loop = last_state.get("loop") if isinstance(last_state.get("loop"), dict) else {}
        if loop.get("status") not in {"queued", "running"}:
            return last_state
        time.sleep(0.4)
    raise QAError(f"Loop did not settle within {timeout_seconds:.1f}s. Last state: {json.dumps(last_state or {}, indent=2)}")


def run_python_checks(root: Path) -> None:
    import py_compile

    qa_print("Compiling Python runtime files")
    for path in sorted((root / "runtime").glob("*.py")):
        py_compile.compile(str(path), doraise=True)
        qa_print(f"Python OK: {path.relative_to(root)}")


def run_php_checks(root: Path, php_bin: str) -> None:
    for path in sorted((root / "api").glob("*.php")):
        run_command([php_bin, "-l", str(path)], root, f"PHP lint {path.relative_to(root)}")
    for path in sorted((root / "scripts").glob("*.php")):
        run_command([php_bin, "-l", str(path)], root, f"PHP lint {path.relative_to(root)}")


def run_js_checks(root: Path, node_bin: Optional[str]) -> None:
    if not node_bin:
        qa_print("Node not found; skipping JavaScript syntax check")
        return
    run_command([node_bin, "--check", str(root / "assets" / "app.js")], root, "JavaScript syntax check assets/app.js")


def run_http_checks(base_url: str) -> None:
    qa_print(f"Checking HTTP reachability at {base_url}")
    status, _ = request(http_url(base_url, "/"), timeout=10)
    if status != 200:
        raise QAError(f"Base URL returned HTTP {status}.")
    status, _ = request(http_url(base_url, "/assets/app.js"), timeout=10)
    if status != 200:
        raise QAError(f"assets/app.js returned HTTP {status}.")
    state = request_json(api_url(base_url, "get_state.php"), timeout=10)
    if "memoryVersion" not in state:
        raise QAError("get_state.php response did not include memoryVersion.")


def run_mock_smoke(root: Path, base_url: str, runtime_url: str, restart_runtime_first: bool) -> Dict[str, Any]:
    if restart_runtime_first:
        restart_runtime(runtime_url)

    task_id = ""
    artifact_name = ""
    queued_job_id = ""
    retried_job_id = ""
    resumed_job_id = ""

    with PreservedState(root) as preserved:
        try:
            qa_print("Resetting workspace for deterministic reversible smoke")
            request_json(api_url(base_url, "reset_state.php"), method="POST", timeout=20)

            qa_print("Adding a templated security lane to the staged draft")
            added_worker = request_json(
                api_url(base_url, "add_adversarial.php"),
                method="POST",
                form_data={"type": "security"},
                timeout=20,
            )
            added_worker_info = added_worker.get("worker")
            if not isinstance(added_worker_info, dict) or added_worker_info.get("type") != "security":
                raise QAError("add_adversarial.php did not create the requested security worker.")

            draft_state = request_json(api_url(base_url, "get_state.php"), timeout=10)
            draft = draft_state.get("draft")
            if not isinstance(draft, dict):
                raise QAError("Draft state was missing after adding a worker.")
            draft_workers = require_sequence(draft.get("workers"), "draft.workers")
            if len(draft_workers) < 3 or str(draft_workers[2].get("type") or "") != "security":
                raise QAError("Draft worker roster did not preserve the requested lane template.")

            qa_print("Starting reversible mock smoke task")
            start = request_json(
                api_url(base_url, "start_task.php"),
                method="POST",
                form_data={
                    "objective": "Smoke test the adjudicated summary surface, queue controls, review export, and replay flow. The public answer should read as one normal assistant reply while the trace stays review-only.",
                    "constraints": "[]",
                    "sessionContext": "",
                    "workers": json.dumps(draft_workers),
                    "executionMode": "mock",
                    "model": "gpt-5-mini",
                    "summarizerModel": "gpt-5-mini",
                    "reasoningEffort": "low",
                    "maxTotalTokens": "250000",
                    "maxCostUsd": "5",
                    "maxOutputTokens": "1200",
                    "researchEnabled": "0",
                    "researchExternalWebAccess": "1",
                    "researchDomains": "[]",
                    "vettingEnabled": "1",
                    "loopRounds": "1",
                    "loopDelayMs": "0",
                },
            )
            task_id = require_text(start.get("taskId"), "start_task taskId")

            active_state = request_json(api_url(base_url, "get_state.php"), timeout=10)
            active_task = active_state.get("activeTask")
            if not isinstance(active_task, dict):
                raise QAError("Active task was missing after start_task.")
            active_workers = require_sequence(active_task.get("workers"), "activeTask.workers")
            worker_targets = [require_text(worker.get("id"), "active worker id") for worker in active_workers]
            if "C" not in worker_targets:
                raise QAError("Expanded worker roster did not carry into the active task.")

            for target in [*worker_targets, "summarizer"]:
                qa_print(f"Running smoke target {target}")
                request_json(
                    api_url(base_url, "run_target.php"),
                    method="POST",
                    form_data={"target": target},
                    timeout=120,
                )

            state = request_json(api_url(base_url, "get_state.php"), timeout=10)
            summary = state.get("summary")
            if not isinstance(summary, dict):
                raise QAError("Smoke summary was missing from state.")
            front_answer = summary.get("frontAnswer")
            if not isinstance(front_answer, dict):
                raise QAError("Smoke summary frontAnswer was missing.")
            summarizer_opinion = summary.get("summarizerOpinion")
            if not isinstance(summarizer_opinion, dict):
                raise QAError("Smoke summary summarizerOpinion was missing.")
            require_text(front_answer.get("answer"), "summary.frontAnswer.answer")
            require_text(front_answer.get("stance"), "summary.frontAnswer.stance")
            require_text(summarizer_opinion.get("stance"), "summary.summarizerOpinion.stance")
            review_trace = require_sequence(summary.get("reviewTrace"), "summary.reviewTrace")
            line_catalog = require_sequence(summary.get("lineCatalog"), "summary.lineCatalog")

            artifact_name = f"{task_id}_summary_round001_output.json"
            artifact = request_json(
                api_url(base_url, "get_artifact.php") + "?name=" + urllib.parse.quote(artifact_name),
                timeout=10,
            )
            output = artifact.get("content", {}).get("output")
            if not isinstance(output, dict):
                raise QAError("Smoke artifact output was missing.")
            require_text(output.get("frontAnswer", {}).get("answer"), "artifact.output.frontAnswer.answer")
            require_sequence(output.get("reviewTrace"), "artifact.output.reviewTrace")

            qa_print("Verifying current-session export bundle")
            current_export = request_json(api_url(base_url, "export_session.php"), timeout=20)
            if current_export.get("source") != "current":
                raise QAError("Current export did not report source=current.")
            if not isinstance(current_export.get("artifactPolicy"), dict):
                raise QAError("Current export did not include artifactPolicy.")
            if not isinstance(current_export.get("state"), dict):
                raise QAError("Current export did not include current state.")

            history_before_reset = request_json(api_url(base_url, "get_history.php"), timeout=20)
            prior_archives = {
                str(entry.get("file") or "")
                for entry in history_before_reset.get("sessions", [])
                if isinstance(entry, dict) and entry.get("file")
            }

            qa_print("Archiving the current session and verifying replay/export endpoints")
            request_json(api_url(base_url, "reset_session.php"), method="POST", timeout=20)
            history_after_reset = request_json(api_url(base_url, "get_history.php"), timeout=20)
            sessions = require_sequence(history_after_reset.get("sessions"), "history.sessions")
            archive_file = ""
            for entry in sessions:
                if isinstance(entry, dict):
                    candidate = str(entry.get("file") or "")
                    if candidate and candidate not in prior_archives:
                        archive_file = candidate
                        break
            if not archive_file:
                archive_file = require_text(sessions[0].get("file"), "latest archive file")

            archive_export = request_json(
                api_url(base_url, "export_session.php") + "?archiveFile=" + urllib.parse.quote(archive_file),
                timeout=20,
            )
            if archive_export.get("source") != "archive":
                raise QAError("Archive export did not report source=archive.")
            if require_text(archive_export.get("archiveFile"), "archive export file") != archive_file:
                raise QAError("Archive export returned an unexpected archive file.")

            replay = request_json(
                api_url(base_url, "replay_session.php"),
                method="POST",
                form_data={"archiveFile": archive_file},
                timeout=20,
            )
            replay_state = replay.get("state")
            if not isinstance(replay_state, dict):
                raise QAError("Replay response did not include restored state.")
            replay_task = replay_state.get("activeTask")
            if not isinstance(replay_task, dict) or require_text(replay_task.get("taskId"), "replayed taskId") != task_id:
                raise QAError("Replay did not restore the archived task.")

            qa_print("Queueing two background loops to verify bounded queueing")
            first_loop = request_json(
                api_url(base_url, "start_loop.php"),
                method="POST",
                form_data={"rounds": "2", "delayMs": "50"},
                timeout=20,
            )
            queued_job_id = require_text(first_loop.get("jobId"), "first queued jobId")
            second_loop = request_json(
                api_url(base_url, "start_loop.php"),
                method="POST",
                form_data={"rounds": "2", "delayMs": "50"},
                timeout=20,
            )
            if int(second_loop.get("queuePosition", 0) or 0) < 1:
                raise QAError("Second background loop did not enter the queue behind the active job.")

            cancel_result = request_json(api_url(base_url, "cancel_loop.php"), method="POST", timeout=20)
            if int(cancel_result.get("queuedJobsCancelled", 0) or 0) < 1:
                raise QAError("cancel_loop.php did not report draining the queued background jobs.")
            wait_for_loop_clear(base_url)

            history_after_cancel = request_json(api_url(base_url, "get_history.php"), timeout=20)
            retry_source = None
            for job in history_after_cancel.get("jobs", []):
                if not isinstance(job, dict):
                    continue
                if str(job.get("taskId") or "") != task_id:
                    continue
                if bool(job.get("canRetry")):
                    retry_source = job
                    break
            if retry_source is None:
                raise QAError("History did not expose a retryable job after cancellation.")

            qa_print("Retrying a cancelled background job through manage_job.php")
            retry_result = request_json(
                api_url(base_url, "manage_job.php"),
                method="POST",
                form_data={"jobId": retry_source["jobId"], "action": "retry"},
                timeout=20,
            )
            retried_job_id = require_text(retry_result.get("jobId"), "retry jobId")
            wait_for_loop_clear(base_url)

            history_after_retry = request_json(api_url(base_url, "get_history.php"), timeout=20)
            retry_entry = None
            for job in history_after_retry.get("jobs", []):
                if isinstance(job, dict) and str(job.get("jobId") or "") == retried_job_id:
                    retry_entry = job
                    break
            if retry_entry is None or str(retry_entry.get("retryOfJobId") or "") != str(retry_source["jobId"]):
                raise QAError("Retried job metadata did not preserve retryOfJobId.")

            qa_print("Creating a synthetic interrupted job to verify resume tooling")
            interrupted_job_id = f"{task_id}-interrupted"
            interrupted_job_path = root / "data" / "jobs" / f"{interrupted_job_id}.json"
            interrupted_job = {
                "jobId": interrupted_job_id,
                "taskId": task_id,
                "mode": "background",
                "status": "interrupted",
                "queuePosition": 0,
                "attempt": 1,
                "resumeOfJobId": None,
                "retryOfJobId": None,
                "resumeFromRound": 2,
                "rounds": 2,
                "delayMs": 0,
                "workerCount": len(active_workers),
                "usage": {
                    "calls": 0,
                    "webSearchCalls": 0,
                    "inputTokens": 0,
                    "cachedInputTokens": 0,
                    "billableInputTokens": 0,
                    "outputTokens": 0,
                    "reasoningTokens": 0,
                    "totalTokens": 0,
                    "modelCostUsd": 0.0,
                    "toolCostUsd": 0.0,
                    "estimatedCostUsd": 0.0,
                    "lastModel": None,
                    "lastResponseId": None,
                    "lastUpdated": None,
                    "byTarget": {},
                    "byModel": {},
                },
                "queuedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "lastHeartbeatAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "lastMessage": "Synthetic interrupted job for QA.",
                "results": [{"round": 1, "targets": []}],
                "completedRounds": 1,
                "error": None,
                "cancelRequested": False,
            }
            interrupted_job_path.write_text(json.dumps(interrupted_job, indent=2), encoding="utf-8")

            history_with_interrupted = request_json(api_url(base_url, "get_history.php"), timeout=20)
            interrupted_entry = None
            for job in history_with_interrupted.get("jobs", []):
                if isinstance(job, dict) and str(job.get("jobId") or "") == interrupted_job_id:
                    interrupted_entry = job
                    break
            if interrupted_entry is None or not bool(interrupted_entry.get("canResume")):
                raise QAError("Interrupted job was not exposed as resumable in history.")

            resume_result = request_json(
                api_url(base_url, "manage_job.php"),
                method="POST",
                form_data={"jobId": interrupted_job_id, "action": "resume"},
                timeout=20,
            )
            resumed_job_id = require_text(resume_result.get("jobId"), "resume jobId")
            if int(resume_result.get("resumeFromRound", 0) or 0) != 2:
                raise QAError("Resume response did not preserve the expected resumeFromRound.")
            wait_for_loop_clear(base_url)

            history_after_resume = request_json(api_url(base_url, "get_history.php"), timeout=20)
            resume_entry = None
            for job in history_after_resume.get("jobs", []):
                if isinstance(job, dict) and str(job.get("jobId") or "") == resumed_job_id:
                    resume_entry = job
                    break
            if resume_entry is None or str(resume_entry.get("resumeOfJobId") or "") != interrupted_job_id:
                raise QAError("Resumed job metadata did not preserve resumeOfJobId.")

            runtime_health = request_json(runtime_url.rstrip("/") + "/health", timeout=5)
            if not runtime_health.get("ok"):
                raise QAError("Resident runtime was not healthy after smoke.")

            return {
                "taskId": task_id,
                "artifact": artifact_name,
                "workerCount": len(active_workers),
                "reviewTraceCount": len(review_trace),
                "lineCatalogCount": len(line_catalog),
                "queuedJobId": queued_job_id,
                "retriedJobId": retried_job_id,
                "resumedJobId": resumed_job_id,
                "runtimePid": runtime_health.get("pid"),
                "frontAnswerStance": front_answer.get("stance"),
            }
        finally:
            if task_id:
                qa_print(f"Cleaning reversible smoke artifacts for {task_id}")
                preserved.cleanup_task_artifacts(task_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local syntax checks and a reversible HTTP smoke for the loop prototype.")
    parser.add_argument("--base-url", default=os.getenv("LOOP_QA_BASE_URL", DEFAULT_BASE_URL), help="Base browser URL for the local app.")
    parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL, help="Resident Python runtime URL.")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip the reversible HTTP smoke and run only lint/syntax checks.")
    parser.add_argument("--skip-http", action="store_true", help="Skip HTTP reachability checks.")
    parser.add_argument("--no-restart-runtime", action="store_true", help="Do not refresh the resident Python runtime before the smoke.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()
    php_bin = find_php_binary(root)
    node_bin = find_node_binary()

    qa_print(f"Project root: {root}")
    qa_print(f"PHP binary: {php_bin}")
    qa_print(f"Node binary: {node_bin or 'not found'}")

    try:
        run_python_checks(root)
        run_php_checks(root, php_bin)
        run_js_checks(root, node_bin)
        if not args.skip_http:
            run_http_checks(args.base_url)
        smoke_result = None
        if not args.skip_smoke:
            smoke_result = run_mock_smoke(root, args.base_url, args.runtime_url, not args.no_restart_runtime)
        qa_print("PASS")
        if smoke_result is not None:
            print(json.dumps(smoke_result, indent=2))
        return 0
    except QAError as error:
        qa_print(f"FAIL: {error}")
        return 1
    except Exception as error:
        qa_print(f"FAIL: unexpected error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
