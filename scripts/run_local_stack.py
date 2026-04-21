from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_env(args: argparse.Namespace, root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("LOOP_ROOT", str(root))
    env.setdefault("LOOP_HOST", args.host)
    env.setdefault("LOOP_PORT", str(args.port))
    env.setdefault("LOOP_DEPLOYMENT_PROFILE", "local-single-node")
    env.setdefault("LOOP_QUEUE_BACKEND", "local_subprocess")
    env.setdefault("LOOP_METADATA_BACKEND", "json_files")
    env.setdefault("LOOP_ARTIFACT_BACKEND", "filesystem")
    env.setdefault("LOOP_SECRET_BACKEND", "local_file")
    env.setdefault("LOOP_RUNTIME_EXECUTION_BACKEND", "embedded_engine_subprocess")
    env.setdefault("LOOP_RUNTIME_HOST", args.runtime_host)
    env.setdefault("LOOP_RUNTIME_PORT", str(args.runtime_port))
    if args.with_runtime_service:
        env["LOOP_RUNTIME_EXECUTION_BACKEND"] = "runtime_service"
        env["LOOP_RUNTIME_SERVICE_URL"] = f"http://{args.runtime_host}:{args.runtime_port}"
    if args.data_root:
        env["LOOP_DATA_ROOT"] = str(Path(args.data_root).resolve())
    if args.auth_file:
        env["LOOP_AUTH_FILE"] = str(Path(args.auth_file).resolve())
    return env


def spawn(command: Sequence[str], env: dict[str, str], cwd: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(  # noqa: S603
        list(command),
        cwd=str(cwd),
        env=env,
    )


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            process.terminate()
    except Exception:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the portable local ParaLLM Python stack.")
    parser.add_argument("--host", default=os.getenv("LOOP_HOST", "127.0.0.1"), help="Backend bind host.")
    parser.add_argument("--port", type=int, default=int(os.getenv("LOOP_PORT", "8787")), help="Backend bind port.")
    parser.add_argument(
        "--runtime-host",
        default=os.getenv("LOOP_RUNTIME_HOST", "127.0.0.1"),
        help="Optional resident runtime bind host.",
    )
    parser.add_argument(
        "--runtime-port",
        type=int,
        default=int(os.getenv("LOOP_RUNTIME_PORT", "8765")),
        help="Optional resident runtime bind port.",
    )
    parser.add_argument("--data-root", default=os.getenv("LOOP_DATA_ROOT", ""), help="Optional data directory override.")
    parser.add_argument("--auth-file", default=os.getenv("LOOP_AUTH_FILE", ""), help="Optional auth file override.")
    parser.add_argument("--reload", action="store_true", help="Enable backend auto-reload for local development.")
    parser.add_argument(
        "--with-runtime-service",
        action="store_true",
        help="Also launch the legacy resident runtime service for compatibility/testing flows.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()
    env = build_env(args, root)

    backend_command = [
        sys.executable,
        "-m",
        "backend.app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        backend_command.append("--reload")

    runtime_command = [
        sys.executable,
        "runtime/service.py",
        "--root",
        str(root),
        "--host",
        args.runtime_host,
        "--port",
        str(args.runtime_port),
    ]
    if args.auth_file:
        runtime_command.extend(["--auth-path", str(Path(args.auth_file).resolve())])

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    try:
        backend = spawn(backend_command, env, root)
        processes.append(("backend", backend))
        print(f"[stack] backend http://{args.host}:{args.port}/")

        if args.with_runtime_service:
            runtime = spawn(runtime_command, env, root)
            processes.append(("runtime", runtime))
            print(f"[stack] runtime http://{args.runtime_host}:{args.runtime_port}/health")

        print("[stack] Ctrl+C to stop all local services.")
        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    raise RuntimeError(f"{name} exited early with code {code}.")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[stack] stopping...")
    finally:
        for _, process in reversed(processes):
            terminate_process(process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
