from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from runtime import native_core


TIMING_SCHEMA_VERSION = "parallm.timing.v1"
_PATH_LOCKS: Dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def timing_enabled() -> bool:
    raw = str(os.getenv("PARALLM_TIMING_ENABLED") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def monotonic_ns() -> int:
    return native_core.monotonic_ns()


def wall_time_ns() -> int:
    return time.time_ns()


def _iso_utc(value_ns: int) -> str:
    return datetime.fromtimestamp(value_ns / 1_000_000_000, timezone.utc).isoformat(timespec="milliseconds")


def _path_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[key] = lock
        return lock


def timing_path(root: str | Path) -> Path:
    return Path(root).resolve() / "data" / "logs" / "timing.jsonl"


def append_timing_record(root: str | Path, record: Dict[str, Any]) -> None:
    if not timing_enabled():
        return
    path = timing_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)
    with _path_lock(path):
        native_core.append_line(path, line)


def _trace_id(attributes: Dict[str, Any]) -> Optional[str]:
    for key in ("traceId", "runId", "taskId", "jobId"):
        value = str(attributes.get(key) or "").strip()
        if value:
            return value
    return None


@contextmanager
def timed_span(
    root: str | Path,
    component: str,
    stage: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Iterator[Dict[str, Any]]:
    attrs = dict(attributes or {})
    started_wall_ns = wall_time_ns()
    started_monotonic_ns = monotonic_ns()
    span: Dict[str, Any] = {
        "spanId": uuid.uuid4().hex,
        "traceId": _trace_id(attrs),
        "component": str(component or "runtime"),
        "stage": str(stage or "unknown"),
        "attributes": attrs,
        "startedAt": _iso_utc(started_wall_ns),
        "startedWallNs": started_wall_ns,
        "startedMonotonicNs": started_monotonic_ns,
    }
    error: Optional[BaseException] = None
    try:
        yield span
    except BaseException as exc:
        error = exc
        raise
    finally:
        completed_wall_ns = wall_time_ns()
        completed_monotonic_ns = monotonic_ns()
        duration_ns = max(0, completed_monotonic_ns - started_monotonic_ns)
        core = native_core.status()
        fingerprint_input = f"{span.get('traceId') or ''}\0{span['component']}\0{span['stage']}"
        record: Dict[str, Any] = {
            "schemaVersion": TIMING_SCHEMA_VERSION,
            **span,
            "spanFingerprint": native_core.fnv1a64_hex(fingerprint_input),
            "status": "error" if error is not None else "completed",
            "completedAt": _iso_utc(completed_wall_ns),
            "completedWallNs": completed_wall_ns,
            "completedMonotonicNs": completed_monotonic_ns,
            "durationNs": duration_ns,
            "durationMs": round(duration_ns / 1_000_000.0, 3),
            "processId": os.getpid(),
            "threadName": threading.current_thread().name,
            "coreMode": core["effectiveMode"],
            "coreRequestedMode": core["requestedMode"],
        }
        if error is not None:
            record["errorType"] = error.__class__.__name__
            record["error"] = str(error)
        append_timing_record(root, record)
