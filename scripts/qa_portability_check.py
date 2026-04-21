from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REQUIRED_ENV_KEYS = [
    "LOOP_HOST",
    "LOOP_PORT",
    "LOOP_PUBLISHED_PORT",
    "LOOP_POSTGRES_PUBLISHED_PORT",
    "LOOP_REDIS_PUBLISHED_PORT",
    "LOOP_OBJECT_STORE_PUBLISHED_PORT",
    "LOOP_OBJECT_STORE_CONSOLE_PUBLISHED_PORT",
    "LOOP_ROOT",
    "LOOP_DATA_ROOT",
    "LOOP_AUTH_FILE",
    "LOOP_DEPLOYMENT_PROFILE",
    "LOOP_QUEUE_BACKEND",
    "LOOP_METADATA_BACKEND",
    "LOOP_ARTIFACT_BACKEND",
    "LOOP_SECRET_BACKEND",
    "LOOP_SECRET_FILE",
    "LOOP_RUNTIME_EXECUTION_BACKEND",
    "LOOP_DATABASE_URL",
    "LOOP_REDIS_URL",
    "LOOP_OBJECT_STORE_URL",
    "LOOP_OBJECT_STORE_BUCKET",
    "LOOP_OBJECT_STORE_HEALTHCHECK_URL",
    "LOOP_OBJECT_STORE_ACCESS_KEY",
    "LOOP_OBJECT_STORE_SECRET_KEY",
    "LOOP_OBJECT_STORE_REGION",
    "LOOP_RUNTIME_HOST",
    "LOOP_RUNTIME_PORT",
    "LOOP_RUNTIME_SERVICE_URL",
    "LOOP_SECRET_PROVIDER_HEALTHCHECK_URL",
    "LOOP_OPENAI_API_KEYS",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def qa_print(message: str) -> None:
    print(f"[portability] {message}")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the Python-only portability surface.")
    return parser.parse_args()


def main() -> int:
    parse_args()
    root = project_root()
    env_example = root / ".env.example"
    deploy_compose = root / "deploy" / "compose.yml"
    hosted_compose = root / "deploy" / "compose.hosted-dev.yml"
    deploy_readme = root / "deploy" / "README.md"
    launcher = root / "scripts" / "run_local_stack.py"

    qa_print("Checking env contract")
    raw_env = env_example.read_text(encoding="utf-8")
    for key in REQUIRED_ENV_KEYS:
        assert_true(f"{key}=" in raw_env, f"Missing {key} in .env.example")

    qa_print("Checking Python-only deploy docs")
    deploy_text = deploy_readme.read_text(encoding="utf-8")
    assert_true("Python-only" in deploy_text or "Python only" in deploy_text, "deploy/README.md should describe the Python-only stack.")
    assert_true("service boundary" in deploy_text.lower(), "deploy/README.md should describe service boundaries.")

    qa_print("Checking compose file")
    compose_text = deploy_compose.read_text(encoding="utf-8")
    assert_true("backend:" in compose_text, "compose.yml must include the backend service.")
    assert_true("${LOOP_PUBLISHED_PORT:-8787}:8787" in compose_text, "compose.yml should expose the backend shell port through LOOP_PUBLISHED_PORT.")
    assert_true("LOOP_DEPLOYMENT_PROFILE: local-single-node" in compose_text, "compose.yml should declare the local deployment profile.")

    qa_print("Checking hosted-dev compose file")
    hosted_text = hosted_compose.read_text(encoding="utf-8")
    assert_true("postgres:" in hosted_text, "compose.hosted-dev.yml must include postgres.")
    assert_true("redis:" in hosted_text, "compose.hosted-dev.yml must include redis.")
    assert_true("minio:" in hosted_text, "compose.hosted-dev.yml must include minio.")
    assert_true("LOOP_DEPLOYMENT_PROFILE: hosted-single-node" in hosted_text, "compose.hosted-dev.yml should declare the hosted profile.")
    assert_true("LOOP_SECRET_BACKEND: docker_secret" in hosted_text, "compose.hosted-dev.yml should default to docker_secret.")
    assert_true("${LOOP_OBJECT_STORE_PUBLISHED_PORT:-9000}:9000" in hosted_text, "compose.hosted-dev.yml should expose object storage through configurable published ports.")
    assert_true("openai_api_keys:" in hosted_text, "compose.hosted-dev.yml should declare the openai_api_keys secret.")

    qa_print("Checking local launcher")
    assert_true(launcher.is_file(), "scripts/run_local_stack.py is missing.")
    subprocess.run(  # noqa: S603
        [sys.executable, str(launcher), "--help"],
        cwd=str(root),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ.copy(),
    )

    hosted_smoke = root / "scripts" / "qa_hosted_dev_stack.py"
    qa_print("Checking hosted-dev smoke harness")
    assert_true(hosted_smoke.is_file(), "scripts/qa_hosted_dev_stack.py is missing.")

    qa_print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
