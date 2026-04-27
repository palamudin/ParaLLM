from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


class QAError(RuntimeError):
    pass


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def qa_print(message: str) -> None:
    print(f"[python-crossover] {message}")


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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


def require_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise QAError(f"{label} was empty.")
    return text


def wait_for_health(backend_base: str, timeout_seconds: float = 12.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            health = request_json(backend_base.rstrip("/") + "/health", timeout=2)
            if health.get("ok"):
                return
        except QAError as error:
            last_error = str(error)
        time.sleep(0.2)
    raise QAError(f"Python backend did not become healthy within {timeout_seconds:.1f}s. {last_error}".strip())


def wait_for_dispatch_idle(backend_base: str, timeout_seconds: float = 60.0) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_state: Dict[str, Any] | None = None
    while time.time() < deadline:
        last_state = request_json(backend_base.rstrip("/") + "/v1/state", timeout=10)
        dispatch = last_state.get("dispatch") if isinstance(last_state.get("dispatch"), dict) else {}
        if str(dispatch.get("status") or "idle") == "idle":
            return last_state
        time.sleep(0.4)
    raise QAError(f"Dispatch did not settle within {timeout_seconds:.1f}s. Last state: {json.dumps(last_state or {}, indent=2)}")


def wait_for_eval_completion(backend_base: str, run_id: str, timeout_seconds: float = 90.0) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_payload: Dict[str, Any] | None = None
    while time.time() < deadline:
        last_payload = request_json(
            backend_base.rstrip("/") + "/v1/evals/history?" + urllib.parse.urlencode({"runId": run_id}),
            timeout=10,
        )
        selected = last_payload.get("selectedRun") if isinstance(last_payload.get("selectedRun"), dict) else None
        if selected and str(selected.get("status") or "") not in {"queued", "running"}:
            return selected
        time.sleep(0.5)
    raise QAError(f"Eval run {run_id} did not finish within {timeout_seconds:.1f}s. Last payload: {json.dumps(last_payload or {}, indent=2)}")


class PreservedWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.temp_dir = Path(tempfile.mkdtemp(prefix="loop-python-crossover-"))
        self.files = {
            "state": self.root / "data" / "state.json",
            "events": self.root / "data" / "events.jsonl",
            "steps": self.root / "data" / "steps.jsonl",
            "auth": self.root / "Auth.txt",
        }
        self.existed = {name: path.exists() for name, path in self.files.items()}

    def __enter__(self) -> "PreservedWorkspace":
        for name, path in self.files.items():
            backup = self.temp_dir / f"{name}{path.suffix}"
            if path.exists():
                shutil.copy2(path, backup)
            else:
                backup.write_text("", encoding="utf-8")
        return self

    def restore(self) -> None:
        for name, path in self.files.items():
            backup = self.temp_dir / f"{name}{path.suffix}"
            if not backup.exists():
                continue
            if not self.existed.get(name, False):
                path.unlink(missing_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, path)

    def cleanup_task_artifacts(self, task_id: str) -> None:
        directories = [
            self.root / "data" / "tasks",
            self.root / "data" / "checkpoints",
            self.root / "data" / "outputs",
        ]
        patterns = [f"{task_id}.json", f"{task_id}_*", f"{task_id}*"]
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
                if isinstance(content, dict) and str(content.get("taskId") or "") == task_id:
                    path.unlink(missing_ok=True)

    def cleanup_eval_run(self, run_id: str) -> None:
        run_dir = self.root / "data" / "evals" / "runs" / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)

    def __exit__(self, exc_type, exc, tb) -> None:
        self.restore()
        shutil.rmtree(self.temp_dir, ignore_errors=True)


def start_backend(root: Path, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["LOOP_ROOT"] = str(root)
    command = [
        sys.executable,
        "-m",
        "backend.app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    return subprocess.Popen(
        command,
        cwd=str(root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        text=True,
    )


def run_crossover_smoke(root: Path) -> Dict[str, Any]:
    task_id = ""
    archive_file = ""
    eval_run_id = ""
    port = find_free_port()
    backend_base = f"http://127.0.0.1:{port}"
    backend_proc = start_backend(root, port)
    wait_for_health(backend_base)

    try:
        qa_print("Checking the Python-served shell")
        status, body = request(backend_base + "/", timeout=10)
        if (
            status != 200
            or "assets/app.js" not in body
            or 'class="workspace-pill-row"' not in body
            or 'id="headerTaskId"' not in body
            or 'id="headerApiMode"' in body
        ):
            raise QAError("The Python-served shell did not return the expected app HTML.")

        with PreservedWorkspace(root) as preserved:
            qa_print("Ensuring the current workspace is idle before reversible crossover smoke")
            initial_state = request_json(backend_base + "/v1/state", timeout=10)
            loop = initial_state.get("loop") if isinstance(initial_state.get("loop"), dict) else {}
            dispatch = initial_state.get("dispatch") if isinstance(initial_state.get("dispatch"), dict) else {}
            if str(loop.get("status") or "idle") in {"queued", "running"}:
                raise QAError("The workspace loop is active. Finish or cancel it before running the Python crossover smoke.")
            if str(dispatch.get("status") or "idle") in {"queued", "running"}:
                raise QAError("Target dispatch is active. Finish it before running the Python crossover smoke.")

            qa_print("Resetting state through the Python control plane")
            request_json(backend_base + "/v1/state/reset", method="POST", timeout=20)

            qa_print("Checking auth mutation parity against the Python API")
            auth_status = request_json(backend_base + "/v1/auth/status", timeout=20)
            provider_groups = auth_status.get("providerGroups") if isinstance(auth_status.get("providerGroups"), dict) else {}
            openai_group = provider_groups.get("openai") if isinstance(provider_groups.get("openai"), dict) else {}
            openai_selected_mode = str(openai_group.get("selectedMode") or "").strip().lower()
            openai_writable = bool(openai_group.get("writable"))
            if openai_writable:
                request_json(backend_base + "/v1/auth/keys", method="POST", form_data={"clear": "1"}, timeout=20)
                request_json(backend_base + "/v1/auth/keys", method="POST", form_data={"appendKey": "sk-test-1111"}, timeout=20)
                post_auth_status = request_json(backend_base + "/v1/auth/status", timeout=20)
                post_groups = post_auth_status.get("providerGroups") if isinstance(post_auth_status.get("providerGroups"), dict) else {}
                post_openai_group = post_groups.get("openai") if isinstance(post_groups.get("openai"), dict) else {}
                if int(post_openai_group.get("keyCount") or 0) < 1:
                    raise QAError("Python auth append did not leave at least one OpenAI key available.")
            else:
                status_code, body = request(
                    backend_base + "/v1/auth/keys",
                    method="POST",
                    form_data={"appendKey": "sk-test-1111"},
                    timeout=20,
                )
                if openai_selected_mode != "local":
                    if status_code != 409 or "mode" not in body.lower():
                        raise QAError(
                            "Python auth mutation did not reject writes in managed credential mode as expected: "
                            + f"HTTP {status_code} | {body}"
                        )
                else:
                    raise QAError(
                        "OpenAI auth group was non-writable outside managed mode during crossover smoke: "
                        + json.dumps(openai_group, indent=2)
                    )

            qa_print("Adding a staged adversarial lane through the Python API")
            added = request_json(backend_base + "/v1/workers/add", method="POST", form_data={"type": "security"}, timeout=20)
            if str(((added.get("worker") or {}) if isinstance(added.get("worker"), dict) else {}).get("id") or "") != "C":
                raise QAError("Python worker-add path did not stage worker C as expected.")

            state_after_add = request_json(backend_base + "/v1/state", timeout=10)
            draft = state_after_add.get("draft") if isinstance(state_after_add.get("draft"), dict) else None
            if not isinstance(draft, dict):
                raise QAError("Draft was missing after adding a worker through Python.")

            qa_print("Starting a mock task through the Python control plane")
            start = request_json(
                backend_base + "/v1/tasks",
                method="POST",
                form_data={
                    "objective": "QA the Python control-plane crossover path.",
                    "executionMode": "mock",
                    "model": "gpt-5-mini",
                    "summarizerModel": "gpt-5-mini",
                    "workers": json.dumps(draft.get("workers") or []),
                    "loopRounds": "2",
                    "loopDelayMs": "0",
                },
                timeout=20,
            )
            task_id = require_text(start.get("taskId"), "taskId")

            qa_print("Applying runtime/settings through Python")
            request_json(
                backend_base + "/v1/runtime/apply",
                method="POST",
                form_data={
                    "model": "gpt-5.4-mini",
                    "summarizerModel": "gpt-5.4",
                    "reasoningEffort": "medium",
                    "loopRounds": "2",
                    "loopDelayMs": "0",
                    "dynamicSpinupEnabled": "1",
                },
                timeout=20,
            )

            qa_print("Updating staged worker configuration through Python")
            updated_worker = request_json(
                backend_base + "/v1/workers/update",
                method="POST",
                form_data={"workerId": "C", "temperature": "hot", "type": "security"},
                timeout=20,
            )
            worker_payload = updated_worker.get("worker") if isinstance(updated_worker.get("worker"), dict) else {}
            if str(worker_payload.get("temperature") or "") != "hot":
                raise QAError("Python worker-update did not preserve the requested temperature.")

            qa_print("Updating an active task position model through Python")
            request_json(
                backend_base + "/v1/positions/model",
                method="POST",
                form_data={"positionId": "summarizer", "model": "gpt-5.4"},
                timeout=20,
            )

            qa_print("Queueing a background round through Python and waiting for dispatch to settle")
            request_json(backend_base + "/v1/rounds", method="POST", timeout=20)
            settled_state = wait_for_dispatch_idle(backend_base)
            summary = settled_state.get("summary") if isinstance(settled_state.get("summary"), dict) else None
            if not isinstance(summary, dict):
                raise QAError("Python round dispatch completed without producing a summary.")
            front_answer = summary.get("frontAnswer") if isinstance(summary.get("frontAnswer"), dict) else None
            if not isinstance(front_answer, dict):
                raise QAError("Python summary was missing frontAnswer.")
            require_text(front_answer.get("answer"), "summary.frontAnswer.answer")

            qa_print("Exporting the current session bundle through Python")
            export_bundle = request_json(backend_base + "/v1/session/export", timeout=20)
            if not isinstance(export_bundle.get("state"), dict):
                raise QAError("Python session export did not include current state.")

            qa_print("Resetting and replaying the session through Python")
            reset = request_json(backend_base + "/v1/session/reset", method="POST", timeout=20)
            archive_file = require_text(reset.get("archiveFile"), "archiveFile")
            replay = request_json(
                backend_base + "/v1/session/replay",
                method="POST",
                form_data={"archiveFile": archive_file},
                timeout=20,
            )
            replay_state = replay.get("state") if isinstance(replay.get("state"), dict) else None
            replay_task = (replay_state.get("activeTask") if isinstance(replay_state, dict) else None) if replay_state else None
            if not isinstance(replay_task, dict) or str(replay_task.get("taskId") or "") != task_id:
                raise QAError("Python session replay did not restore the archived task.")

            qa_print("Switching the active task into front-eval mode through Python")
            runtime_eval = request_json(
                backend_base + "/v1/runtime/apply",
                method="POST",
                form_data={
                    "frontMode": "eval",
                    "directBaselineMode": "both",
                },
                timeout=20,
            )
            active_task = runtime_eval.get("activeTask") if isinstance(runtime_eval.get("activeTask"), dict) else None
            if not isinstance(active_task, dict):
                runtime_eval = request_json(backend_base + "/v1/state", timeout=20)
                active_task = runtime_eval.get("activeTask") if isinstance(runtime_eval.get("activeTask"), dict) else None
            runtime_settings = active_task.get("runtime") if isinstance(active_task, dict) and isinstance(active_task.get("runtime"), dict) else {}
            if str(runtime_settings.get("frontMode") or "") != "eval":
                raise QAError("Python runtime apply did not switch the active task into front eval mode.")
            if str(runtime_settings.get("directBaselineMode") or "") != "both":
                raise QAError("Python runtime apply did not keep the compare baseline enabled in eval mode.")

            qa_print("Checking that the retired isolated eval launcher now returns a migration message")
            legacy_status, legacy_body = request(
                backend_base + "/v1/evals/runs",
                method="POST",
                form_data={
                    "suiteId": "smoke-mock",
                    "armIds": json.dumps(["steered-mock"]),
                    "replicates": "1",
                    "loopSweep": "1",
                    "judgeModel": "gpt-5.4-mini",
                },
                timeout=20,
            )
            if legacy_status != 410 or "Front mode to Eval" not in legacy_body:
                raise QAError(
                    "Retired eval launcher did not return the expected migration response: "
                    + f"HTTP {legacy_status} | {legacy_body}"
                )
            eval_run_id = "retired"

            history = request_json(backend_base + "/v1/history", timeout=20)
            dispatch_state = history.get("dispatch") if isinstance(history.get("dispatch"), dict) else {}
            if str(dispatch_state.get("status") or "idle") != "idle":
                raise QAError("History still showed active dispatch after the Python crossover smoke settled.")

            preserved.cleanup_task_artifacts(task_id)
            if archive_file:
                (root / "data" / "sessions" / archive_file).unlink(missing_ok=True)
            if eval_run_id and eval_run_id != "retired":
                preserved.cleanup_eval_run(eval_run_id)

            return {
                "taskId": task_id,
                "archiveFile": archive_file,
                "evalRunId": eval_run_id,
                "backendBase": backend_base,
                "summaryAnswer": front_answer.get("answer"),
            }
    finally:
        backend_proc.terminate()
        try:
            backend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend_proc.kill()
            backend_proc.wait(timeout=5)


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description="Run a reversible Python-control-plane smoke.").parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()
    try:
        result = run_crossover_smoke(root)
    except QAError as error:
        print(f"[python-crossover] FAIL: {error}", file=sys.stderr)
        return 1
    qa_print(
        "PASS: task=%s archive=%s eval=%s backend=%s"
        % (result["taskId"], result["archiveFile"], result["evalRunId"], result["backendBase"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
