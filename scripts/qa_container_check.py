from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml


class ContainerCheckError(RuntimeError):
    pass


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def qa_print(message: str) -> None:
    print(f"[container] {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContainerCheckError(message)


def load_compose(path: Path) -> dict:
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ContainerCheckError(f"Could not parse {path}: {exc}") from exc
    require(isinstance(parsed, dict), "compose.yml did not parse to a mapping.")
    return parsed


def validate_compose(compose: dict, repo_root: Path) -> None:
    services = compose.get("services")
    require(isinstance(services, dict), "compose.yml is missing services.")
    require("backend" in services, "compose.yml is missing service backend.")
    backend = services["backend"]

    for service_name, service in (("backend", backend),):
        require(isinstance(service, dict), f"{service_name} service must be a mapping.")
        build = service.get("build")
        require(isinstance(build, dict), f"{service_name} build config is required.")
        dockerfile = build.get("dockerfile")
        require(isinstance(dockerfile, str) and dockerfile.strip(), f"{service_name} dockerfile is required.")
        dockerfile_path = (repo_root / dockerfile).resolve()
        require(dockerfile_path.is_file(), f"{service_name} dockerfile does not exist: {dockerfile}")

    volumes = compose.get("volumes")
    require(isinstance(volumes, dict), "compose.yml must declare named volumes.")
    require("loop_data" in volumes, "compose.yml must declare loop_data volume.")
    require("loop_auth" in volumes, "compose.yml must declare loop_auth volume.")


def validate_dockerfiles(repo_root: Path) -> None:
    backend_dockerfile = (repo_root / "deploy" / "backend" / "Dockerfile").read_text(encoding="utf-8")
    runtime_dockerfile = (repo_root / "deploy" / "runtime" / "Dockerfile").read_text(encoding="utf-8")
    require("requirements-ci.txt" in backend_dockerfile, "Backend Dockerfile must install requirements-ci.txt.")
    require("requirements-ci.txt" in runtime_dockerfile, "Runtime Dockerfile must install requirements-ci.txt.")


def validate_hosted_compose(compose: dict, repo_root: Path) -> None:
    services = compose.get("services")
    require(isinstance(services, dict), "compose.hosted-dev.yml is missing services.")
    for name in ("backend", "postgres", "redis", "minio"):
        require(name in services, f"compose.hosted-dev.yml is missing service {name}.")
    backend = services["backend"]
    require(isinstance(backend, dict), "compose.hosted-dev.yml backend must be a mapping.")
    environment = backend.get("environment")
    require(isinstance(environment, dict), "compose.hosted-dev.yml backend environment is required.")
    require(environment.get("LOOP_QUEUE_BACKEND") == "redis", "Hosted-dev backend must use redis queue backend.")
    require(environment.get("LOOP_METADATA_BACKEND") == "postgres", "Hosted-dev backend must use postgres metadata backend.")
    require(environment.get("LOOP_ARTIFACT_BACKEND") == "object_storage", "Hosted-dev backend must use object_storage artifact backend.")
    require(environment.get("LOOP_SECRET_BACKEND") == "docker_secret", "Hosted-dev backend must use docker_secret backend.")
    require("secrets" in backend, "Hosted-dev backend must mount Docker secrets.")
    secrets = compose.get("secrets")
    require(isinstance(secrets, dict) and "openai_api_keys" in secrets, "compose.hosted-dev.yml must declare openai_api_keys secret.")


def validate_hosted_runtime_override(compose: dict) -> None:
    services = compose.get("services")
    require(isinstance(services, dict), "compose.hosted-dev.runtime-service.yml is missing services.")
    require("backend" in services, "Runtime-service override must include backend override.")
    require("runtime" in services, "Runtime-service override must include runtime service.")
    backend = services["backend"]
    runtime = services["runtime"]
    require(isinstance(backend, dict), "Runtime-service override backend must be a mapping.")
    require(isinstance(runtime, dict), "Runtime-service override runtime must be a mapping.")
    backend_env = backend.get("environment")
    require(isinstance(backend_env, dict), "Runtime-service override backend environment is required.")
    require(
        backend_env.get("LOOP_RUNTIME_EXECUTION_BACKEND") == "runtime_service",
        "Runtime-service override backend must switch LOOP_RUNTIME_EXECUTION_BACKEND to runtime_service.",
    )
    require(
        str(backend_env.get("LOOP_RUNTIME_SERVICE_URL") or "").strip() == "http://runtime:8765",
        "Runtime-service override backend must point LOOP_RUNTIME_SERVICE_URL at the runtime service.",
    )
    runtime_env = runtime.get("environment")
    require(isinstance(runtime_env, dict), "Runtime-service override runtime environment is required.")
    require(runtime_env.get("LOOP_SECRET_BACKEND") == "docker_secret", "Runtime service must use docker_secret backend.")
    require(runtime_env.get("LOOP_METADATA_BACKEND") == "postgres", "Runtime service must use postgres metadata backend.")
    require(runtime_env.get("LOOP_ARTIFACT_BACKEND") == "object_storage", "Runtime service must use object_storage backend.")
    require("secrets" in runtime, "Runtime service must mount Docker secrets.")


def maybe_run_docker_compose_config(repo_root: Path) -> None:
    docker_bin = shutil.which("docker")
    if not docker_bin:
        qa_print("Docker not found locally; YAML/static validation only.")
        return
    qa_print("Running docker compose config")
    result = subprocess.run(
        [docker_bin, "compose", "-f", str(repo_root / "deploy" / "compose.yml"), "config"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        raise ContainerCheckError(f"docker compose config failed with exit code {result.returncode}.")


def main() -> int:
    repo_root = root()
    compose_path = repo_root / "deploy" / "compose.yml"
    hosted_compose_path = repo_root / "deploy" / "compose.hosted-dev.yml"
    hosted_runtime_override_path = repo_root / "deploy" / "compose.hosted-dev.runtime-service.yml"
    require(compose_path.is_file(), "deploy/compose.yml is missing.")
    require(hosted_compose_path.is_file(), "deploy/compose.hosted-dev.yml is missing.")
    require(hosted_runtime_override_path.is_file(), "deploy/compose.hosted-dev.runtime-service.yml is missing.")
    require((repo_root / ".dockerignore").is_file(), ".dockerignore is missing.")
    require((repo_root / "scripts" / "qa_hosted_dev_stack.py").is_file(), "scripts/qa_hosted_dev_stack.py is missing.")
    require((repo_root / "scripts" / "package_hosted_bundle.py").is_file(), "scripts/package_hosted_bundle.py is missing.")
    compose = load_compose(compose_path)
    hosted_compose = load_compose(hosted_compose_path)
    hosted_runtime_override = load_compose(hosted_runtime_override_path)
    validate_compose(compose, repo_root)
    validate_dockerfiles(repo_root)
    validate_hosted_compose(hosted_compose, repo_root)
    validate_hosted_runtime_override(hosted_runtime_override)
    maybe_run_docker_compose_config(repo_root)
    qa_print("PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContainerCheckError as exc:
        qa_print(f"FAIL: {exc}")
        raise SystemExit(1)
