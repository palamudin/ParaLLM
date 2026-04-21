from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict

import boto3
from botocore.config import Config as BotoConfig


DEFAULT_PORTS = {
    "backend": 8788,
    "postgres": 55432,
    "redis": 56379,
    "object_store": 59000,
    "object_store_console": 59001,
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def qa_print(message: str) -> None:
    print(f"[hosted-dev] {message}")


def fail(message: str) -> RuntimeError:
    return RuntimeError(message)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise fail(message)


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", int(port)))
        except OSError:
            return False
    return True


def choose_port(start: int) -> int:
    for port in range(start, start + 200):
        if port_is_free(port):
            return port
    raise fail(f"No free port found near {start}.")


def run_command(command: list[str], env: Dict[str, str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        raise fail(f"Missing executable: {command[0]}") from error


def ensure_docker(root: Path) -> None:
    for command in (["docker", "--version"], ["docker", "compose", "version"]):
        result = run_command(command, os.environ.copy(), root, timeout=60)
        if result.returncode != 0:
            raise fail(
                "Docker is not available. Install/start Docker Desktop first. "
                f"Command failed: {' '.join(command)}\n{result.stderr or result.stdout}"
            )


def http_json(method: str, url: str, payload: Dict[str, Any] | None = None, timeout: float = 10.0) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise fail(f"HTTP {error.code} for {url}: {body}") from error
    except Exception as error:  # noqa: BLE001
        raise fail(f"Request failed for {url}: {error}") from error
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        raise fail(f"Expected JSON from {url}, got: {body[:400]}") from error
    if not isinstance(parsed, dict):
        raise fail(f"Expected JSON object from {url}.")
    return parsed


def wait_for_backend(base_url: str, timeout: float = 240.0) -> None:
    deadline = time.time() + timeout
    last_error = "backend not yet reachable"
    while time.time() < deadline:
        try:
            payload = http_json("GET", f"{base_url}/health", timeout=5.0)
            if str(payload.get("status") or "").lower() == "ok":
                return
            last_error = json.dumps(payload)
        except Exception as error:  # noqa: BLE001
            last_error = str(error)
        time.sleep(2.0)
    raise fail(f"Timed out waiting for hosted-dev backend: {last_error}")


def build_secret_source(root: Path) -> Path:
    env_keys = str(os.getenv("LOOP_OPENAI_API_KEYS") or "").strip()
    auth_path = root / "Auth.txt"
    content = env_keys
    if not content and auth_path.is_file():
        content = auth_path.read_text(encoding="utf-8", errors="replace").strip()
    if not content:
        content = "sk-hosted-dev-smoke-dummy\n"
    temp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False)
    with temp:
        temp.write(content.rstrip() + "\n")
    return Path(temp.name)


def compose_env(root: Path, project_name: str) -> Dict[str, str]:
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = project_name
    env["LOOP_PUBLISHED_PORT"] = str(choose_port(DEFAULT_PORTS["backend"]))
    env["LOOP_POSTGRES_PUBLISHED_PORT"] = str(choose_port(DEFAULT_PORTS["postgres"]))
    env["LOOP_REDIS_PUBLISHED_PORT"] = str(choose_port(DEFAULT_PORTS["redis"]))
    env["LOOP_OBJECT_STORE_PUBLISHED_PORT"] = str(choose_port(DEFAULT_PORTS["object_store"]))
    env["LOOP_OBJECT_STORE_CONSOLE_PUBLISHED_PORT"] = str(choose_port(DEFAULT_PORTS["object_store_console"]))
    env["LOOP_SECRET_SOURCE_FILE"] = str(build_secret_source(root))
    return env


def docker_compose(env: Dict[str, str], root: Path, *args: str, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    return run_command(["docker", "compose", "-f", "deploy/compose.hosted-dev.yml", *args], env, root, timeout=timeout)


def assert_compose_ok(result: subprocess.CompletedProcess[str], context: str) -> None:
    if result.returncode != 0:
        raise fail(f"{context} failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


def docker_exec(env: Dict[str, str], root: Path, service: str, *args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return docker_compose(env, root, "exec", "-T", service, *args, timeout=timeout)


def wait_for_loop_completion(base_url: str, timeout: float = 180.0) -> Dict[str, Any]:
    deadline = time.time() + timeout
    last_state: Dict[str, Any] = {}
    while time.time() < deadline:
        state = http_json("GET", f"{base_url}/v1/state", timeout=10.0)
        last_state = state
        loop = state.get("loop") if isinstance(state.get("loop"), dict) else {}
        status = str(loop.get("status") or "idle")
        if status not in {"queued", "running"}:
            if status in {"error", "interrupted", "budget_exhausted"}:
                raise fail(f"Hosted loop finished badly: {json.dumps(loop)}")
            return state
        time.sleep(2.0)
    raise fail(f"Timed out waiting for hosted loop completion. Last state: {json.dumps(last_state)}")


def minio_client(endpoint_url: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
        region_name="us-east-1",
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def collect_bucket_keys(endpoint_url: str, bucket: str) -> list[str]:
    client = minio_client(endpoint_url)
    response = client.list_objects_v2(Bucket=bucket)
    items = response.get("Contents") or []
    return sorted(str(item.get("Key") or "") for item in items)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bring up the hosted-dev Docker stack and prove the hosted backends are live.")
    parser.add_argument("--project-name", default="parallmhostedsmoke", help="Docker Compose project name.")
    parser.add_argument("--keep-up", action="store_true", help="Leave the stack running after the smoke.")
    parser.add_argument("--skip-build", action="store_true", help="Skip the compose build step.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()
    ensure_docker(root)
    env = compose_env(root, args.project_name)
    base_url = f"http://127.0.0.1:{env['LOOP_PUBLISHED_PORT']}"
    minio_url = f"http://127.0.0.1:{env['LOOP_OBJECT_STORE_PUBLISHED_PORT']}"
    secret_file = Path(env["LOOP_SECRET_SOURCE_FILE"])

    qa_print(f"Using backend port {env['LOOP_PUBLISHED_PORT']}")
    qa_print(f"Using project name {args.project_name}")
    cleanup_needed = True
    try:
        up_args = ["up", "-d"]
        if not args.skip_build:
            up_args.append("--build")
        qa_print("Starting hosted-dev compose stack")
        result = docker_compose(env, root, *up_args, timeout=3600)
        assert_compose_ok(result, "docker compose up")

        qa_print("Waiting for backend health")
        wait_for_backend(base_url)

        topology = http_json("GET", f"{base_url}/v1/system/topology")
        infrastructure = http_json("GET", f"{base_url}/v1/system/infrastructure")
        auth_status = http_json("GET", f"{base_url}/v1/auth/status")

        assert_true(str(topology.get("profile") or "") == "hosted-single-node", "Hosted topology profile mismatch.")
        assert_true(str(topology.get("queueBackend") or "") == "redis", "Queue backend is not redis in hosted-dev.")
        assert_true(str(topology.get("metadataBackend") or "") == "postgres", "Metadata backend is not postgres in hosted-dev.")
        assert_true(str(topology.get("artifactBackend") or "") == "object_storage", "Artifact backend is not object_storage in hosted-dev.")
        assert_true(str(topology.get("secretBackend") or "") == "docker_secret", "Secret backend is not docker_secret in hosted-dev.")
        assert_true(bool(infrastructure.get("ready")), f"Infrastructure not ready: {json.dumps(infrastructure)}")
        assert_true(str(auth_status.get("backend") or "") == "docker_secret", "Auth status is not using docker_secret.")
        assert_true(bool(auth_status.get("hasKey")), "Mounted secret backend did not expose any keys.")

        qa_print("Creating hosted smoke task")
        task = http_json(
            "POST",
            f"{base_url}/v1/tasks",
            {
                "objective": "Hosted-dev smoke: prove queue, metadata, artifacts, and secrets are live.",
                "executionMode": "mock",
                "model": "gpt-5-mini",
                "summarizerModel": "gpt-5-mini",
                "loopRounds": 2,
                "loopDelayMs": 200,
            },
        )
        task_id = str(task.get("taskId") or "")
        assert_true(bool(task_id), "Task creation did not return a taskId.")

        qa_print("Queuing two background loops to exercise Redis ordering")
        first_loop = http_json("POST", f"{base_url}/v1/loops", {"rounds": 2, "delayMs": 200})
        second_loop = http_json("POST", f"{base_url}/v1/loops", {"rounds": 1, "delayMs": 0})
        assert_true(int(first_loop.get("queuePosition") or 0) == 0, f"Expected first hosted loop to start immediately: {first_loop}")
        assert_true(int(second_loop.get("queuePosition") or 0) >= 1, f"Expected second hosted loop to queue behind the first: {second_loop}")

        redis_keys = docker_exec(env, root, "redis", "redis-cli", "--scan", "--pattern", "parallm:*queue*")
        assert_compose_ok(redis_keys, "redis queue inspection")
        assert_true(bool(redis_keys.stdout.strip()), "Redis queue inspection returned no ParaLLM queue keys during hosted loop activity.")

        qa_print("Waiting for hosted loops to complete")
        final_state = wait_for_loop_completion(base_url)
        history = http_json("GET", f"{base_url}/v1/history")
        sessions_reset = http_json("POST", f"{base_url}/v1/session/reset")
        archive_file = str(sessions_reset.get("archiveFile") or "")
        assert_true(bool(archive_file), "Session reset did not produce an archive file.")
        export_bundle = http_json(
            "GET",
            f"{base_url}/v1/session/export?{urllib.parse.urlencode({'archiveFile': archive_file})}",
        )
        bundle_file = str(export_bundle.get("bundleFile") or "")
        assert_true(bool(bundle_file), "Session export did not produce a bundle file.")

        qa_print("Validating Postgres metadata is populated")
        postgres_checks = {
            "state": "select count(*) from parallm_state;",
            "tasks": "select count(*) from parallm_tasks;",
            "jobs": "select count(*) from parallm_jobs;",
        }
        for label, query in postgres_checks.items():
            result = docker_exec(env, root, "postgres", "psql", "-U", "postgres", "-d", "parallm", "-t", "-A", "-c", query)
            assert_compose_ok(result, f"postgres {label} check")
            count = int((result.stdout or "0").strip().splitlines()[-1] or "0")
            assert_true(count > 0, f"Expected postgres {label} table to contain rows.")

        qa_print("Validating object storage contains runtime/session/export artifacts")
        keys = collect_bucket_keys(minio_url, "parallm")
        assert_true(any(key.startswith("checkpoints/") for key in keys), f"Expected checkpoint objects in MinIO, got: {keys}")
        assert_true(any(key.startswith("outputs/") for key in keys), f"Expected output objects in MinIO, got: {keys}")
        assert_true(any(key.startswith("sessions/") for key in keys), f"Expected session archive objects in MinIO, got: {keys}")
        assert_true(any(key.startswith("exports/") for key in keys), f"Expected export bundle objects in MinIO, got: {keys}")

        qa_print("Hosted-dev stack is live and exercising real backends")
        print(
            json.dumps(
                {
                    "baseUrl": base_url,
                    "taskId": task_id,
                    "archiveFile": archive_file,
                    "bundleFile": bundle_file,
                    "topology": {
                        "profile": topology.get("profile"),
                        "queueBackend": topology.get("queueBackend"),
                        "metadataBackend": topology.get("metadataBackend"),
                        "artifactBackend": topology.get("artifactBackend"),
                        "secretBackend": topology.get("secretBackend"),
                    },
                    "finalLoopStatus": ((final_state.get("loop") or {}) if isinstance(final_state.get("loop"), dict) else {}).get("status"),
                    "historyJobs": len(history.get("jobs") or []),
                    "bucketObjectCount": len(keys),
                },
                indent=2,
            )
        )
        if args.keep_up:
            cleanup_needed = False
        return 0
    finally:
        try:
            if cleanup_needed:
                qa_print("Tearing down hosted-dev compose stack")
                docker_compose(env, root, "down", "-v", "--remove-orphans", timeout=1200)
        finally:
            if "secret_file" in locals() and secret_file.exists():
                secret_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
