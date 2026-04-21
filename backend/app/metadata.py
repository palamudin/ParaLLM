from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psycopg  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency in some runtimes
    psycopg = None

from .config import deployment_topology


_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY: set[str] = set()


def postgres_enabled(root: Optional[Path] = None) -> bool:
    return deployment_topology(root).metadata_backend == "postgres"


def _project_key(root: Optional[Path] = None) -> str:
    topology = deployment_topology(root)
    digest = hashlib.sha1(str(topology.root).encode("utf-8")).hexdigest()[:16]
    return f"parallm:{digest}"


def _database_url(root: Optional[Path] = None) -> str:
    topology = deployment_topology(root)
    if not topology.database_url:
        raise RuntimeError("LOOP_DATABASE_URL is not configured.")
    return str(topology.database_url)


def _connect(root: Optional[Path] = None):
    if psycopg is None:
        raise RuntimeError("psycopg dependency is not installed.")
    return psycopg.connect(_database_url(root), connect_timeout=3)


def _ensure_schema(root: Optional[Path] = None) -> None:
    if not postgres_enabled(root):
        return
    database_url = _database_url(root)
    with _SCHEMA_LOCK:
        if database_url in _SCHEMA_READY:
            return
        with _connect(root) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                create table if not exists parallm_state (
                    project_key text primary key,
                    payload jsonb not null,
                    updated_at timestamptz not null default now()
                )
                """
            )
            cursor.execute(
                """
                create table if not exists parallm_jobs (
                    project_key text not null,
                    job_id text not null,
                    task_id text,
                    job_type text,
                    status text,
                    queued_at timestamptz,
                    updated_at timestamptz not null default now(),
                    payload jsonb not null,
                    primary key (project_key, job_id)
                )
                """
            )
            cursor.execute(
                """
                create index if not exists parallm_jobs_project_status_idx
                on parallm_jobs (project_key, job_type, status, queued_at desc)
                """
            )
            cursor.execute(
                """
                create table if not exists parallm_tasks (
                    project_key text not null,
                    task_id text not null,
                    updated_at timestamptz not null default now(),
                    payload jsonb not null,
                    primary key (project_key, task_id)
                )
                """
            )
            cursor.execute(
                """
                create table if not exists parallm_eval_runs (
                    project_key text not null,
                    run_id text not null,
                    status text,
                    created_at timestamptz,
                    updated_at timestamptz not null default now(),
                    payload jsonb not null,
                    primary key (project_key, run_id)
                )
                """
            )
            cursor.execute(
                """
                create index if not exists parallm_eval_runs_project_status_idx
                on parallm_eval_runs (project_key, status, created_at desc, updated_at desc)
                """
            )
        _SCHEMA_READY.add(database_url)


def _decode_payload(raw: Any, fallback: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return fallback
    text = str(raw).strip()
    if not text:
        return fallback
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return fallback
    return parsed if isinstance(parsed, dict) else fallback


def read_state_payload(root: Optional[Path], fallback: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_schema(root)
    project_key = _project_key(root)
    with _connect(root) as connection, connection.cursor() as cursor:
        cursor.execute("select payload::text from parallm_state where project_key = %s", (project_key,))
        row = cursor.fetchone()
    payload = _decode_payload(row[0] if row else None, fallback)
    return payload if isinstance(payload, dict) else dict(fallback)


def write_state_payload(root: Optional[Path], payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_schema(root)
    project_key = _project_key(root)
    body = json.dumps(payload, ensure_ascii=False)
    with _connect(root) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            insert into parallm_state (project_key, payload, updated_at)
            values (%s, %s::jsonb, now())
            on conflict (project_key)
            do update set payload = excluded.payload, updated_at = now()
            """,
            (project_key, body),
        )
    return payload


def read_job_payload(root: Optional[Path], job_id: str) -> Optional[Dict[str, Any]]:
    _ensure_schema(root)
    project_key = _project_key(root)
    with _connect(root) as connection, connection.cursor() as cursor:
        cursor.execute(
            "select payload::text from parallm_jobs where project_key = %s and job_id = %s",
            (project_key, str(job_id or "").strip()),
        )
        row = cursor.fetchone()
    return _decode_payload(row[0] if row else None, None)


def write_job_payload(root: Optional[Path], job: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_schema(root)
    project_key = _project_key(root)
    job_id = str(job.get("jobId") or "").strip()
    if not job_id:
        raise RuntimeError("Job payload is missing jobId.")
    body = json.dumps(job, ensure_ascii=False)
    with _connect(root) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            insert into parallm_jobs (project_key, job_id, task_id, job_type, status, queued_at, updated_at, payload)
            values (%s, %s, %s, %s, %s, %s, now(), %s::jsonb)
            on conflict (project_key, job_id)
            do update set
                task_id = excluded.task_id,
                job_type = excluded.job_type,
                status = excluded.status,
                queued_at = excluded.queued_at,
                updated_at = now(),
                payload = excluded.payload
            """,
            (
                project_key,
                job_id,
                str(job.get("taskId") or "").strip() or None,
                str(job.get("jobType") or "loop"),
                str(job.get("status") or "queued"),
                job.get("queuedAt"),
                body,
            ),
        )
    return job


def read_all_job_payloads(root: Optional[Path]) -> List[Dict[str, Any]]:
    _ensure_schema(root)
    project_key = _project_key(root)
    with _connect(root) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select payload::text
            from parallm_jobs
            where project_key = %s
            order by coalesce(queued_at, updated_at) asc, job_id asc
            """,
            (project_key,),
        )
        rows = cursor.fetchall() or []
    results: List[Dict[str, Any]] = []
    for row in rows:
        payload = _decode_payload(row[0] if row else None, None)
        if isinstance(payload, dict):
            results.append(payload)
    return results


def read_task_payload(root: Optional[Path], task_id: str) -> Optional[Dict[str, Any]]:
    _ensure_schema(root)
    project_key = _project_key(root)
    with _connect(root) as connection, connection.cursor() as cursor:
        cursor.execute(
            "select payload::text from parallm_tasks where project_key = %s and task_id = %s",
            (project_key, str(task_id or "").strip()),
        )
        row = cursor.fetchone()
    return _decode_payload(row[0] if row else None, None)


def write_task_payload(root: Optional[Path], task: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_schema(root)
    project_key = _project_key(root)
    task_id = str(task.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError("Task payload is missing taskId.")
    body = json.dumps(task, ensure_ascii=False)
    with _connect(root) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            insert into parallm_tasks (project_key, task_id, updated_at, payload)
            values (%s, %s, now(), %s::jsonb)
            on conflict (project_key, task_id)
            do update set updated_at = now(), payload = excluded.payload
            """,
            (project_key, task_id, body),
        )
    return task


def read_eval_run_payload(root: Optional[Path], run_id: str) -> Optional[Dict[str, Any]]:
    _ensure_schema(root)
    project_key = _project_key(root)
    with _connect(root) as connection, connection.cursor() as cursor:
        cursor.execute(
            "select payload::text from parallm_eval_runs where project_key = %s and run_id = %s",
            (project_key, str(run_id or "").strip()),
        )
        row = cursor.fetchone()
    return _decode_payload(row[0] if row else None, None)


def write_eval_run_payload(root: Optional[Path], run: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_schema(root)
    project_key = _project_key(root)
    run_id = str(run.get("runId") or "").strip()
    if not run_id:
        raise RuntimeError("Eval run payload is missing runId.")
    body = json.dumps(run, ensure_ascii=False)
    with _connect(root) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            insert into parallm_eval_runs (project_key, run_id, status, created_at, updated_at, payload)
            values (%s, %s, %s, %s, now(), %s::jsonb)
            on conflict (project_key, run_id)
            do update set
                status = excluded.status,
                created_at = excluded.created_at,
                updated_at = now(),
                payload = excluded.payload
            """,
            (
                project_key,
                run_id,
                str(run.get("status") or "queued"),
                run.get("createdAt"),
                body,
            ),
        )
    return run


def read_all_eval_run_payloads(root: Optional[Path]) -> List[Dict[str, Any]]:
    _ensure_schema(root)
    project_key = _project_key(root)
    with _connect(root) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select payload::text
            from parallm_eval_runs
            where project_key = %s
            order by coalesce(updated_at, created_at) desc, run_id desc
            """,
            (project_key,),
        )
        rows = cursor.fetchall() or []
    results: List[Dict[str, Any]] = []
    for row in rows:
        payload = _decode_payload(row[0] if row else None, None)
        if isinstance(payload, dict):
            results.append(payload)
    return results
