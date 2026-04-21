from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import psycopg  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency in some runtimes
    psycopg = None

try:
    import redis as redis_lib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency in some runtimes
    redis_lib = None

from .config import DeploymentTopology, deployment_topology
from .secrets import env_secret_keys as read_env_secret_keys
from .secrets import external_secret_keys


def _http_probe(url: Optional[str], timeout: float = 3.0, headers: Optional[Dict[str, str]] = None) -> tuple[bool, str]:
    target = str(url or "").strip()
    if not target:
        return False, "No healthcheck URL configured."
    request = urllib.request.Request(target, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as handle:
            code = getattr(handle, "status", 200)
        if int(code) >= 400:
            return False, f"HTTP {code}"
        return True, "reachable"
    except urllib.error.HTTPError as error:
        return False, f"HTTP {error.code}"
    except Exception as error:  # noqa: BLE001
        return False, str(error)


def _redis_probe(url: Optional[str]) -> tuple[bool, str]:
    target = str(url or "").strip()
    if not target:
        return False, "LOOP_REDIS_URL is not configured."
    if redis_lib is None:
        return False, "redis dependency is not installed."
    try:
        client = redis_lib.Redis.from_url(target, socket_timeout=3, socket_connect_timeout=3)
        client.ping()
        return True, "reachable"
    except Exception as error:  # noqa: BLE001
        return False, str(error)


def _postgres_probe(url: Optional[str]) -> tuple[bool, str]:
    target = str(url or "").strip()
    if not target:
        return False, "LOOP_DATABASE_URL is not configured."
    if psycopg is None:
        return False, "psycopg dependency is not installed."
    try:
        with psycopg.connect(target, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                cursor.fetchone()
        return True, "reachable"
    except Exception as error:  # noqa: BLE001
        return False, str(error)


def _filesystem_status(topology: DeploymentTopology) -> Dict[str, Any]:
    path = topology.data_root
    return {
        "backend": "filesystem",
        "configured": True,
        "ready": path.exists(),
        "detail": f"Using {path}",
    }


def _json_metadata_status(topology: DeploymentTopology) -> Dict[str, Any]:
    path = topology.data_root
    return {
        "backend": "json_files",
        "configured": True,
        "ready": path.exists(),
        "detail": f"Using local metadata under {path}",
    }


def _local_queue_status() -> Dict[str, Any]:
    return {
        "backend": "local_subprocess",
        "configured": True,
        "ready": True,
        "detail": "Using Python subprocess-backed local queueing.",
    }


def _local_secret_status(topology: DeploymentTopology) -> Dict[str, Any]:
    auth_file = topology.auth_file
    parent = auth_file.parent if auth_file else topology.root
    return {
        "backend": "local_file",
        "configured": True,
        "ready": parent.exists(),
        "detail": f"Using transitional local secret file at {auth_file}" if auth_file else "Using transitional local secret file.",
        "writable": True,
        "keyCount": None,
    }


def _env_secret_status() -> Dict[str, Any]:
    keys = read_env_secret_keys()
    return {
        "backend": "env",
        "configured": True,
        "ready": len(keys) > 0,
        "detail": "Using env-provided API keys from LOOP_OPENAI_API_KEYS or OPENAI_API_KEYS.",
        "writable": False,
        "keyCount": len(keys),
    }


def _docker_secret_status(topology: DeploymentTopology) -> Dict[str, Any]:
    secret_path = topology.secret_file
    ready = bool(secret_path and secret_path.is_file())
    key_count = 0
    if ready and secret_path is not None:
        raw = secret_path.read_text(encoding="utf-8", errors="replace")
        key_count = len([line.strip() for line in raw.splitlines() if line.strip()])
    return {
        "backend": "docker_secret",
        "configured": bool(secret_path),
        "ready": ready and key_count > 0,
        "detail": f"Using mounted secret file at {secret_path}" if secret_path else "No mounted secret file configured.",
        "writable": False,
        "keyCount": key_count,
    }


def _external_secret_status(topology: DeploymentTopology) -> Dict[str, Any]:
    provider_url = str(topology.secret_provider_url or "").strip()
    health_url = str(topology.secret_provider_healthcheck_url or provider_url).strip()
    if not provider_url:
        return {
            "backend": "external",
            "configured": False,
            "ready": False,
            "detail": "LOOP_SECRET_PROVIDER_URL is not configured.",
            "writable": False,
            "keyCount": 0,
        }
    token = str(os.getenv("LOOP_SECRET_PROVIDER_TOKEN") or "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else None
    ready, detail = _http_probe(health_url, headers=headers)
    key_count = 0
    if ready:
        key_count = len(external_secret_keys(topology.root))
        ready = key_count > 0
        detail = f"reachable; {key_count} keys exposed" if ready else "reachable but returned no keys"
    return {
        "backend": "external",
        "configured": True,
        "ready": ready,
        "detail": detail,
        "writable": False,
        "keyCount": key_count,
    }


def queue_status(topology: DeploymentTopology) -> Dict[str, Any]:
    if topology.queue_backend == "redis":
        ready, detail = _redis_probe(topology.redis_url)
        return {
            "backend": topology.queue_backend,
            "configured": bool(topology.redis_url),
            "ready": ready,
            "detail": detail,
            "redisUrl": topology.redis_url,
        }
    return _local_queue_status()


def metadata_status(topology: DeploymentTopology) -> Dict[str, Any]:
    if topology.metadata_backend == "postgres":
        ready, detail = _postgres_probe(topology.database_url)
        return {
            "backend": topology.metadata_backend,
            "configured": bool(topology.database_url),
            "ready": ready,
            "detail": detail,
            "databaseUrl": topology.database_url,
        }
    return _json_metadata_status(topology)


def artifact_status(topology: DeploymentTopology) -> Dict[str, Any]:
    if topology.artifact_backend == "object_storage":
        ready, detail = _http_probe(topology.object_store_healthcheck_url or topology.object_store_url)
        return {
            "backend": topology.artifact_backend,
            "configured": bool(topology.object_store_url),
            "ready": ready,
            "detail": detail,
            "objectStoreUrl": topology.object_store_url,
            "bucket": topology.object_store_bucket,
        }
    return _filesystem_status(topology)


def secret_status(topology: DeploymentTopology) -> Dict[str, Any]:
    if topology.secret_backend == "env":
        return _env_secret_status()
    if topology.secret_backend == "docker_secret":
        return _docker_secret_status(topology)
    if topology.secret_backend == "external":
        return _external_secret_status(topology)
    return _local_secret_status(topology)


def runtime_execution_status(topology: DeploymentTopology) -> Dict[str, Any]:
    if topology.runtime_execution_backend == "runtime_service":
        ready, detail = _http_probe(
            (str(topology.runtime_service_url).rstrip("/") + "/health") if topology.runtime_service_url else None
        )
        return {
            "backend": topology.runtime_execution_backend,
            "configured": bool(topology.runtime_service_url),
            "ready": ready,
            "detail": detail,
            "runtimeServiceUrl": topology.runtime_service_url,
        }
    return {
        "backend": topology.runtime_execution_backend,
        "configured": True,
        "ready": True,
        "detail": "Using embedded engine subprocess execution.",
    }


def infrastructure_status(root: Optional[Path] = None) -> Dict[str, Any]:
    topology = deployment_topology(root)
    queue = queue_status(topology)
    metadata = metadata_status(topology)
    artifacts = artifact_status(topology)
    secrets = secret_status(topology)
    runtime_execution = runtime_execution_status(topology)
    return {
        "profile": topology.profile,
        "backends": {
            "queue": queue,
            "metadata": metadata,
            "artifacts": artifacts,
            "secrets": secrets,
            "runtimeExecution": runtime_execution,
        },
        "ready": all(
            bool(section.get("ready"))
            for section in (queue, metadata, artifacts, secrets, runtime_execution)
        ),
    }


def env_secret_keys() -> list[str]:
    return list(read_env_secret_keys())
