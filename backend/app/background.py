from __future__ import annotations

import os
import queue
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Optional, Tuple

from runtime import native_core
from runtime.timing import monotonic_ns, timed_span


BackgroundCallable = Callable[..., Any]
WorkItem = Tuple[str, str, Path, int, BackgroundCallable, tuple[Any, ...], Dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _worker_count(kind: str, fallback: int) -> int:
    env_name = f"PARALLM_{kind.upper()}_WORKERS"
    try:
        return max(1, min(64, int(os.getenv(env_name) or fallback)))
    except (TypeError, ValueError):
        return fallback


class InProcessPool:
    def __init__(self, kind: str, worker_count: int, queue_capacity: int = 512) -> None:
        self.kind = str(kind or "runtime")
        self.worker_count = max(1, int(worker_count))
        self._queue: queue.Queue[Optional[WorkItem]] = queue.Queue(maxsize=max(1, int(queue_capacity)))
        self._lock = threading.Lock()
        self._recent: Deque[Dict[str, Any]] = deque(maxlen=128)
        self._threads = [
            threading.Thread(
                target=self._worker,
                name=f"para-{self.kind}-{index + 1}",
                daemon=True,
            )
            for index in range(self.worker_count)
        ]
        for thread in self._threads:
            thread.start()

    def submit(
        self,
        label: str,
        timing_root: str | Path,
        function: BackgroundCallable,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        task_id = f"{self.kind}-{uuid.uuid4().hex[:12]}"
        repo_root = Path(timing_root).resolve()
        queued_ns = monotonic_ns()
        entry = {
            "taskId": task_id,
            "kind": self.kind,
            "label": str(label or function.__name__),
            "status": "queued",
            "queuedAt": _utc_now(),
        }
        with self._lock:
            self._recent.append(entry)
        try:
            self._queue.put_nowait((task_id, entry["label"], repo_root, queued_ns, function, args, kwargs))
        except queue.Full as exc:
            entry.update({"status": "rejected", "finishedAt": _utc_now(), "error": "in-process queue is full"})
            raise RuntimeError(f"The {self.kind} in-process queue is full.") from exc
        return task_id

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            recent = [dict(entry) for entry in self._recent]
        return {
            "kind": self.kind,
            "workerCount": self.worker_count,
            "queuedCount": self._queue.qsize(),
            "recent": recent,
        }

    def _entry(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for entry in reversed(self._recent):
                if entry.get("taskId") == task_id:
                    return entry
        return None

    @staticmethod
    def _transition(entry: Dict[str, Any], status: str, **values: Any) -> None:
        previous = str(entry.get("status") or "unknown")
        if not native_core.transition_allowed(previous, status):
            raise RuntimeError(f"Invalid background lifecycle transition: {previous} -> {status}.")
        entry.update({"status": status, **values})

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            task_id, label, root, queued_ns, function, args, kwargs = item
            entry = self._entry(task_id)
            started_ns = monotonic_ns()
            if entry is not None:
                self._transition(
                    entry,
                    "running",
                    startedAt=_utc_now(),
                    queueWaitMs=round(max(0, started_ns - queued_ns) / 1_000_000.0, 3),
                )
            try:
                with timed_span(
                    root,
                    "background",
                    f"{self.kind}.execute",
                    {
                        "backgroundTaskId": task_id,
                        "label": label,
                        "queueWaitNs": max(0, started_ns - queued_ns),
                    },
                ):
                    function(*args, **kwargs)
            except BaseException as exc:  # noqa: BLE001 - worker must remain alive
                if entry is not None:
                    self._transition(
                        entry,
                        "error",
                        finishedAt=_utc_now(),
                        errorType=exc.__class__.__name__,
                        error=str(exc),
                    )
            else:
                if entry is not None:
                    self._transition(entry, "completed", finishedAt=_utc_now())
            finally:
                self._queue.task_done()


_POOLS: Dict[str, InProcessPool] = {}
_POOLS_LOCK = threading.Lock()
_DEFAULT_WORKERS = {"loop": 2, "dispatch": 12, "eval": 2}


def pool(kind: str) -> InProcessPool:
    normalized = str(kind or "runtime").strip().lower()
    with _POOLS_LOCK:
        existing = _POOLS.get(normalized)
        if existing is not None:
            return existing
        created = InProcessPool(normalized, _worker_count(normalized, _DEFAULT_WORKERS.get(normalized, 4)))
        _POOLS[normalized] = created
        return created


def submit(
    kind: str,
    label: str,
    timing_root: str | Path,
    function: BackgroundCallable,
    *args: Any,
    **kwargs: Any,
) -> str:
    return pool(kind).submit(label, timing_root, function, *args, **kwargs)


def status() -> Dict[str, Any]:
    with _POOLS_LOCK:
        pools = list(_POOLS.values())
    return {"backend": "in_process", "pools": {item.kind: item.snapshot() for item in pools}}
