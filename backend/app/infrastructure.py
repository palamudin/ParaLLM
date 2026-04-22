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

from . import control
from .config import DeploymentTopology, deployment_topology


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
    status = env_secret_status()
    return {
        "backend": "env",
        "configured": bool(status.get("configured")),
        "ready": bool(status.get("ready")),
        "detail": str(status.get("detail") or ""),
        "writable": False,
        "keyCount": len(status.get("keys", [])) if isinstance(status.get("keys"), list) else 0,
        "failureMode": status.get("failureMode"),
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
    status = external_secret_status(topology.root)
    return {
        "backend": "external",
        "configured": bool(status.get("configured")),
        "ready": bool(status.get("ready")),
        "detail": str(status.get("detail") or ""),
        "writable": False,
        "keyCount": len(status.get("keys", [])) if isinstance(status.get("keys"), list) else 0,
        "failureMode": status.get("failureMode"),
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
    auth_status = control.auth_pool_status(topology.root)
    provider_groups = {
        provider_id: {
            "label": str(group.get("label") or provider_id),
            "ready": bool(group.get("hasKey")),
            "keyCount": int(group.get("keyCount", 0) or 0),
            "failureMode": group.get("failureMode"),
        }
        for provider_id, group in (auth_status.get("providerGroups") or {}).items()
        if isinstance(group, dict)
    }
    configured = True
    if topology.secret_backend == "docker_secret":
        configured = bool(topology.secret_file)
    elif topology.secret_backend == "external":
        configured = bool(topology.secret_provider_url)
    detail_parts = [str(auth_status.get("statusNote") or "").strip()]
    if not auth_status.get("available") and str(auth_status.get("failureDetail") or "").strip():
        detail_parts.append(str(auth_status.get("failureDetail") or "").strip())
    detail = " ".join(part for part in detail_parts if part).strip()
    return {
        "backend": str(auth_status.get("backend") or topology.secret_backend),
        "configured": configured,
        "ready": bool(auth_status.get("available")),
        "detail": detail,
        "writable": bool(auth_status.get("writable")),
        "keyCount": int(auth_status.get("keyCount", 0) or 0),
        "failureMode": auth_status.get("failureMode"),
        "strictLiveFailure": bool(auth_status.get("strictLiveFailure")),
        "providerGroups": provider_groups,
    }


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
