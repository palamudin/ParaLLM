from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, List, Optional

try:
    import redis as redis_lib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency in some runtimes
    redis_lib = None

from .config import deployment_topology


LOOP_ACTIVE_TTL_SECONDS = 6 * 60 * 60


def _ordered_unique(values: Iterable[str]) -> List[str]:
    ordered: List[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def redis_enabled(root: Optional[Path] = None) -> bool:
    return deployment_topology(root).queue_backend == "redis"


def _namespace(root: Optional[Path] = None) -> str:
    topology = deployment_topology(root)
    digest = hashlib.sha1(str(topology.root).encode("utf-8")).hexdigest()[:12]
    return f"parallm:{digest}"


def _redis_client(topology) -> object:
    if redis_lib is None:
        raise RuntimeError("redis dependency is not installed.")
    if not topology.redis_url:
        raise RuntimeError("LOOP_REDIS_URL is not configured.")
    return redis_lib.Redis.from_url(topology.redis_url, decode_responses=True)


def _loop_queue_key(topology, task_id: str) -> str:
    return f"{_namespace(topology.root)}:queue:loop:{task_id}:queued"


def _loop_active_key(topology, task_id: str) -> str:
    return f"{_namespace(topology.root)}:queue:loop:{task_id}:active"


def _dispatch_ready_key(topology) -> str:
    return f"{_namespace(topology.root)}:queue:dispatch:ready"


def sync_loop_queue(
    root: Optional[Path],
    task_id: str,
    ordered_job_ids: Iterable[str],
    active_job_id: Optional[str] = None,
) -> List[str]:
    desired = [job_id for job_id in _ordered_unique(ordered_job_ids) if job_id != str(active_job_id or "").strip()]
    if not redis_enabled(root):
        return desired

    topology = deployment_topology(root)
    client = _redis_client(topology)
    queue_key = _loop_queue_key(topology, task_id)
    active_key = _loop_active_key(topology, task_id)

    current = [str(value or "").strip() for value in (client.lrange(queue_key, 0, -1) or []) if str(value or "").strip()]
    if current != desired:
        client.delete(queue_key)
        if desired:
            client.rpush(queue_key, *desired)

    active_value = str(active_job_id or "").strip()
    if active_value:
        client.set(active_key, active_value, ex=LOOP_ACTIVE_TTL_SECONDS)
    else:
        client.delete(active_key)
    return desired


def claim_next_loop_job_id(
    root: Optional[Path],
    task_id: str,
    ordered_job_ids: Iterable[str],
    active_job_id: Optional[str] = None,
) -> Optional[str]:
    desired = sync_loop_queue(root, task_id, ordered_job_ids, active_job_id=active_job_id)
    if not redis_enabled(root):
        return desired[0] if desired else None
    if str(active_job_id or "").strip():
        return None

    topology = deployment_topology(root)
    client = _redis_client(topology)
    queue_key = _loop_queue_key(topology, task_id)
    active_key = _loop_active_key(topology, task_id)

    if str(client.get(active_key) or "").strip():
        return None
    candidate = str(client.lindex(queue_key, 0) or "").strip()
    if not candidate:
        return None
    if client.set(active_key, candidate, nx=True, ex=LOOP_ACTIVE_TTL_SECONDS):
        client.lpop(queue_key)
        return candidate
    return None


def current_loop_claim(root: Optional[Path], task_id: str) -> Optional[str]:
    if not redis_enabled(root):
        return None
    topology = deployment_topology(root)
    client = _redis_client(topology)
    value = str(client.get(_loop_active_key(topology, task_id)) or "").strip()
    return value or None


def release_loop_claim(root: Optional[Path], task_id: str, job_id: Optional[str]) -> None:
    claimed = str(job_id or "").strip()
    if not claimed or not redis_enabled(root):
        return
    topology = deployment_topology(root)
    client = _redis_client(topology)
    active_key = _loop_active_key(topology, task_id)
    if str(client.get(active_key) or "").strip() == claimed:
        client.delete(active_key)


def enqueue_dispatch_launches(root: Optional[Path], job_ids: Iterable[str]) -> List[str]:
    ordered = _ordered_unique(job_ids)
    if not redis_enabled(root) or not ordered:
        return ordered
    topology = deployment_topology(root)
    client = _redis_client(topology)
    client.rpush(_dispatch_ready_key(topology), *ordered)
    return ordered


def drain_dispatch_launches(root: Optional[Path], limit: Optional[int] = None) -> List[str]:
    if not redis_enabled(root):
        return []
    topology = deployment_topology(root)
    client = _redis_client(topology)
    queue_key = _dispatch_ready_key(topology)
    results: List[str] = []
    max_items = max(0, int(limit or 0))
    while True:
        if max_items and len(results) >= max_items:
            break
        item = str(client.lpop(queue_key) or "").strip()
        if not item:
            break
        results.append(item)
    return results
