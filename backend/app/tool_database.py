from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


MAX_VALUE_BYTES = 256 * 1024
MAX_LIST_LIMIT = 100
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


class ToolDatabaseError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def database_path(root: Path) -> Path:
    return Path(root).resolve() / "data" / "tool_records.sqlite3"


def _identifier(value: Any, label: str) -> str:
    candidate = str(value or "").strip()
    if not IDENTIFIER_PATTERN.fullmatch(candidate):
        raise ToolDatabaseError(
            f"{label} must be 1-128 characters using letters, numbers, dot, underscore, colon, slash, or dash."
        )
    return candidate


def _value(value: Any) -> str:
    candidate = str(value if value is not None else "")
    size = len(candidate.encode("utf-8"))
    if size > MAX_VALUE_BYTES:
        raise ToolDatabaseError(f"Database tool values are limited to {MAX_VALUE_BYTES} UTF-8 bytes.", 413)
    return candidate


def _content_type(value: Any) -> str:
    candidate = str(value or "text/plain").strip().lower()
    if candidate not in {"text/plain", "application/json", "text/markdown"}:
        raise ToolDatabaseError("content_type must be text/plain, text/markdown, or application/json.")
    return candidate


def _actor(value: Any) -> str:
    candidate = str(value or "para").strip()
    return candidate[:128] or "para"


def _connect(root: Path) -> sqlite3.Connection:
    path = database_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA synchronous=NORMAL;")
    connection.execute("PRAGMA foreign_keys=ON;")
    connection.execute("PRAGMA busy_timeout=5000;")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tool_record (
            namespace TEXT NOT NULL,
            record_key TEXT NOT NULL,
            value_text TEXT NOT NULL,
            content_type TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK (revision >= 1),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            PRIMARY KEY (namespace, record_key)
        ) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS tool_record_updated_idx
            ON tool_record(namespace, updated_at DESC, record_key);
        PRAGMA user_version=1;
        """
    )
    return connection


@contextmanager
def _transaction(root: Path) -> Iterator[sqlite3.Connection]:
    connection = _connect(root)
    try:
        connection.execute("BEGIN IMMEDIATE;")
        yield connection
        connection.execute("COMMIT;")
    except Exception:
        connection.execute("ROLLBACK;")
        raise
    finally:
        connection.close()


def _record(row: sqlite3.Row, *, include_value: bool = True) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "namespace": str(row["namespace"]),
        "key": str(row["record_key"]),
        "contentType": str(row["content_type"]),
        "contentSha256": str(row["content_sha256"]),
        "revision": int(row["revision"]),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
        "createdBy": str(row["created_by"]),
        "updatedBy": str(row["updated_by"]),
    }
    value = str(row["value_text"])
    payload["bytes"] = len(value.encode("utf-8"))
    if include_value:
        payload["value"] = value
    else:
        payload["preview"] = value[:240]
    return payload


def write_record(
    root: Path,
    namespace: Any,
    key: Any,
    value: Any,
    *,
    content_type: Any = "text/plain",
    actor: Any = "para",
) -> Dict[str, Any]:
    normalized_namespace = _identifier(namespace, "namespace")
    normalized_key = _identifier(key, "key")
    normalized_value = _value(value)
    normalized_type = _content_type(content_type)
    normalized_actor = _actor(actor)
    content_hash = hashlib.sha256(normalized_value.encode("utf-8")).hexdigest()
    try:
        with _transaction(root) as connection:
            connection.execute(
                """
                INSERT INTO tool_record(
                    namespace, record_key, value_text, content_type, content_sha256,
                    revision, created_at, updated_at, created_by, updated_by
                ) VALUES(
                    ?, ?, ?, ?, ?, 1,
                    strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                    strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?
                );
                """,
                (
                    normalized_namespace,
                    normalized_key,
                    normalized_value,
                    normalized_type,
                    content_hash,
                    normalized_actor,
                    normalized_actor,
                ),
            )
            row = connection.execute(
                "SELECT * FROM tool_record WHERE namespace=? AND record_key=?;",
                (normalized_namespace, normalized_key),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise ToolDatabaseError(
            "Record already exists. Use db_update with its current revision to change it.", 409
        ) from error
    if row is None:
        raise ToolDatabaseError("Database write did not return the inserted record.", 500)
    return _record(row)


def read_record(root: Path, namespace: Any, key: Any) -> Dict[str, Any]:
    normalized_namespace = _identifier(namespace, "namespace")
    normalized_key = _identifier(key, "key")
    connection = _connect(root)
    try:
        row = connection.execute(
            "SELECT * FROM tool_record WHERE namespace=? AND record_key=?;",
            (normalized_namespace, normalized_key),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ToolDatabaseError("Database record not found.", 404)
    return _record(row)


def update_record(
    root: Path,
    namespace: Any,
    key: Any,
    value: Any,
    *,
    expected_revision: Optional[int] = None,
    content_type: Any = "text/plain",
    actor: Any = "para",
) -> Dict[str, Any]:
    normalized_namespace = _identifier(namespace, "namespace")
    normalized_key = _identifier(key, "key")
    normalized_value = _value(value)
    normalized_type = _content_type(content_type)
    normalized_actor = _actor(actor)
    content_hash = hashlib.sha256(normalized_value.encode("utf-8")).hexdigest()
    if expected_revision is not None and int(expected_revision) < 1:
        raise ToolDatabaseError("expected_revision must be at least 1.")
    with _transaction(root) as connection:
        existing = connection.execute(
            "SELECT revision FROM tool_record WHERE namespace=? AND record_key=?;",
            (normalized_namespace, normalized_key),
        ).fetchone()
        if existing is None:
            raise ToolDatabaseError("Database record not found.", 404)
        current_revision = int(existing["revision"])
        if expected_revision is not None and current_revision != int(expected_revision):
            raise ToolDatabaseError(
                f"Revision conflict: expected {int(expected_revision)}, current revision is {current_revision}.", 409
            )
        connection.execute(
            """
            UPDATE tool_record
            SET value_text=?, content_type=?, content_sha256=?, revision=revision+1,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_by=?
            WHERE namespace=? AND record_key=? AND revision=?;
            """,
            (
                normalized_value,
                normalized_type,
                content_hash,
                normalized_actor,
                normalized_namespace,
                normalized_key,
                current_revision,
            ),
        )
        if connection.execute("SELECT changes();").fetchone()[0] != 1:
            raise ToolDatabaseError("Database record changed concurrently; read it again before updating.", 409)
        row = connection.execute(
            "SELECT * FROM tool_record WHERE namespace=? AND record_key=?;",
            (normalized_namespace, normalized_key),
        ).fetchone()
    if row is None:
        raise ToolDatabaseError("Database update did not return the updated record.", 500)
    return _record(row)


def list_records(
    root: Path,
    namespace: Any,
    *,
    prefix: Any = "",
    limit: Any = 20,
) -> Dict[str, Any]:
    normalized_namespace = _identifier(namespace, "namespace")
    normalized_prefix = str(prefix or "").strip()
    if len(normalized_prefix) > 128:
        raise ToolDatabaseError("prefix is limited to 128 characters.")
    normalized_limit = max(1, min(MAX_LIST_LIMIT, int(limit or 20)))
    connection = _connect(root)
    try:
        rows: List[sqlite3.Row] = connection.execute(
            """
            SELECT * FROM tool_record
            WHERE namespace=? AND record_key LIKE ? ESCAPE '\\'
            ORDER BY updated_at DESC, record_key
            LIMIT ?;
            """,
            (normalized_namespace, _like_prefix(normalized_prefix), normalized_limit + 1),
        ).fetchall()
    finally:
        connection.close()
    truncated = len(rows) > normalized_limit
    selected = rows[:normalized_limit]
    return {
        "namespace": normalized_namespace,
        "prefix": normalized_prefix,
        "count": len(selected),
        "truncated": truncated,
        "records": [_record(row, include_value=False) for row in selected],
    }


def _like_prefix(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}%"


def status(root: Path) -> Dict[str, Any]:
    connection = _connect(root)
    try:
        row = connection.execute("SELECT COUNT(*), COALESCE(MAX(updated_at), '') FROM tool_record;").fetchone()
        integrity = str(connection.execute("PRAGMA quick_check;").fetchone()[0])
    finally:
        connection.close()
    path = database_path(root)
    return {
        "available": integrity == "ok",
        "path": str(path),
        "records": int(row[0] if row else 0),
        "lastUpdated": str(row[1] if row else ""),
        "quickCheck": integrity,
        "bytes": path.stat().st_size if path.exists() else 0,
    }
