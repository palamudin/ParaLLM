from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEPLOYMENT_PROFILES = {"local-single-node", "hosted-single-node", "hosted-distributed"}
QUEUE_BACKENDS = {"local_subprocess", "redis"}
METADATA_BACKENDS = {"json_files", "postgres"}
ARTIFACT_BACKENDS = {"filesystem", "object_storage"}
SECRET_BACKENDS = {"local_file", "env", "docker_secret", "external"}
RUNTIME_EXECUTION_BACKENDS = {"embedded_engine_subprocess", "runtime_service"}


def _clean_choice(value: str, allowed: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "-")
    return normalized if normalized in allowed else default


def _optional_env(name: str) -> Optional[str]:
    value = str(os.getenv(name) or "").strip()
    return value or None


@dataclass(frozen=True)
class DeploymentTopology:
    profile: str
    root: Path
    data_root: Path
    auth_file: Optional[Path]
    host: str
    port: int
    runtime_host: str
    runtime_port: int
    queue_backend: str
    metadata_backend: str
    artifact_backend: str
    secret_backend: str
    secret_file: Optional[Path]
    runtime_execution_backend: str
    database_url: Optional[str]
    redis_url: Optional[str]
    object_store_url: Optional[str]
    object_store_bucket: Optional[str]
    object_store_healthcheck_url: Optional[str]
    object_store_access_key: Optional[str]
    object_store_secret_key: Optional[str]
    object_store_region: Optional[str]
    runtime_service_url: Optional[str]
    secret_provider_url: Optional[str]
    secret_provider_healthcheck_url: Optional[str]

    def as_dict(self) -> dict[str, object]:
        services = {
            "shell": "backend",
            "controlPlane": "backend",
            "queue": self.queue_backend,
            "metadata": self.metadata_backend,
            "artifacts": self.artifact_backend,
            "secrets": self.secret_backend,
            "runtimeExecution": self.runtime_execution_backend,
        }
        return {
            "profile": self.profile,
            "root": str(self.root),
            "dataRoot": str(self.data_root),
            "authFile": str(self.auth_file) if self.auth_file else None,
            "host": self.host,
            "port": self.port,
            "runtimeHost": self.runtime_host,
            "runtimePort": self.runtime_port,
            "queueBackend": self.queue_backend,
            "metadataBackend": self.metadata_backend,
            "artifactBackend": self.artifact_backend,
            "secretBackend": self.secret_backend,
            "secretFile": str(self.secret_file) if self.secret_file else None,
            "runtimeExecutionBackend": self.runtime_execution_backend,
            "databaseUrl": self.database_url,
            "redisUrl": self.redis_url,
            "objectStoreUrl": self.object_store_url,
            "objectStoreBucket": self.object_store_bucket,
            "objectStoreHealthcheckUrl": self.object_store_healthcheck_url,
            "objectStoreAccessKeyConfigured": bool(self.object_store_access_key),
            "objectStoreSecretKeyConfigured": bool(self.object_store_secret_key),
            "objectStoreRegion": self.object_store_region,
            "runtimeServiceUrl": self.runtime_service_url,
            "secretProviderUrl": self.secret_provider_url,
            "secretProviderHealthcheckUrl": self.secret_provider_healthcheck_url,
            "services": services,
        }


def deployment_topology(root: Optional[Path] = None) -> DeploymentTopology:
    base = (root or Path(os.getenv("LOOP_ROOT") or Path(__file__).resolve().parents[2])).resolve()
    data_override = _optional_env("LOOP_DATA_ROOT")
    data_root = Path(data_override).resolve() if data_override else base / "data"
    auth_override = _optional_env("LOOP_AUTH_FILE")
    auth_file = Path(auth_override).resolve() if auth_override else base / "Auth.txt"

    profile = _clean_choice(
        str(os.getenv("LOOP_DEPLOYMENT_PROFILE") or "local-single-node"),
        DEPLOYMENT_PROFILES,
        "local-single-node",
    )
    queue_backend = _clean_choice(
        str(os.getenv("LOOP_QUEUE_BACKEND") or "local_subprocess"),
        QUEUE_BACKENDS,
        "local_subprocess",
    )
    metadata_backend = _clean_choice(
        str(os.getenv("LOOP_METADATA_BACKEND") or "json_files"),
        METADATA_BACKENDS,
        "json_files",
    )
    artifact_backend = _clean_choice(
        str(os.getenv("LOOP_ARTIFACT_BACKEND") or "filesystem"),
        ARTIFACT_BACKENDS,
        "filesystem",
    )
    secret_backend = _clean_choice(
        str(os.getenv("LOOP_SECRET_BACKEND") or "local_file"),
        SECRET_BACKENDS,
        "local_file",
    )
    secret_file_override = _optional_env("LOOP_SECRET_FILE")
    secret_file = Path(secret_file_override).resolve() if secret_file_override else None
    if secret_backend == "docker_secret" and secret_file is None:
        secret_file = Path("/run/secrets/openai_api_keys")
    runtime_execution_backend = _clean_choice(
        str(os.getenv("LOOP_RUNTIME_EXECUTION_BACKEND") or "embedded_engine_subprocess"),
        RUNTIME_EXECUTION_BACKENDS,
        "embedded_engine_subprocess",
    )

    host = str(os.getenv("LOOP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("LOOP_PORT") or 8787)
    runtime_host = str(os.getenv("LOOP_RUNTIME_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    runtime_port = int(os.getenv("LOOP_RUNTIME_PORT") or 8765)

    runtime_service_url = _optional_env("LOOP_RUNTIME_SERVICE_URL")
    if runtime_service_url is None and runtime_execution_backend == "runtime_service":
        runtime_service_url = f"http://{runtime_host}:{runtime_port}"

    return DeploymentTopology(
        profile=profile,
        root=base,
        data_root=data_root,
        auth_file=auth_file,
        host=host,
        port=port,
        runtime_host=runtime_host,
        runtime_port=runtime_port,
        queue_backend=queue_backend,
        metadata_backend=metadata_backend,
        artifact_backend=artifact_backend,
        secret_backend=secret_backend,
        secret_file=secret_file,
        runtime_execution_backend=runtime_execution_backend,
        database_url=_optional_env("LOOP_DATABASE_URL"),
        redis_url=_optional_env("LOOP_REDIS_URL"),
        object_store_url=_optional_env("LOOP_OBJECT_STORE_URL"),
        object_store_bucket=_optional_env("LOOP_OBJECT_STORE_BUCKET"),
        object_store_healthcheck_url=_optional_env("LOOP_OBJECT_STORE_HEALTHCHECK_URL"),
        object_store_access_key=_optional_env("LOOP_OBJECT_STORE_ACCESS_KEY"),
        object_store_secret_key=_optional_env("LOOP_OBJECT_STORE_SECRET_KEY"),
        object_store_region=_optional_env("LOOP_OBJECT_STORE_REGION") or "us-east-1",
        runtime_service_url=runtime_service_url,
        secret_provider_url=_optional_env("LOOP_SECRET_PROVIDER_URL"),
        secret_provider_healthcheck_url=_optional_env("LOOP_SECRET_PROVIDER_HEALTHCHECK_URL"),
    )
