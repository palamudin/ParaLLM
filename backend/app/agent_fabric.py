from __future__ import annotations

import hashlib
import os
import secrets
import signal
import sqlite3
import subprocess
import sys
import threading
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from . import storage


SCHEMA_VERSION = "parallm.python-agent-fabric.v1"
DEFAULT_PROJECT_ID = "project_default"
PRIMARY_AGENT_ID = "agent_primary"
PROCEED_DIRECTIVE = (
    "If there is no show-stopper blocker, proceed with your tasks. "
    "Report current progress and any blocker through agent_report."
)

MESSAGE_KINDS = {
    "note", "question", "answer", "progress", "blocker", "decision",
    "handover", "directive", "result",
}
SEVERITIES = {"info", "recoverable", "showstopper"}
PROJECT_ROLES = {"owner", "supervisor", "contributor", "observer"}
REPORT_KINDS = {"progress", "blocked", "completed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_time(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def bounded(value: Any, limit: int, *, required: bool = True) -> str:
    text = str(value or "").strip()
    if (required and not text) or len(text.encode("utf-8")) > limit:
        requirement = "required" if required else "optional"
        raise ValueError(f"A {requirement} value of at most {limit} bytes is required.")
    return text


class AgentFabric:
    def __init__(
        self,
        root: Path,
        *,
        database: Optional[Path] = None,
        spawn_processes: bool = True,
        steward_interval_seconds: float = 5.0,
    ) -> None:
        self.root = Path(root).resolve()
        paths = storage.project_paths(self.root)
        paths.data.mkdir(parents=True, exist_ok=True)
        self.database = Path(database).resolve() if database else paths.data / "agent_fabric.sqlite3"
        self.spawn_processes = spawn_processes
        self.steward_interval_seconds = max(0.25, float(steward_interval_seconds))
        self._stop = threading.Event()
        self._steward_thread: Optional[threading.Thread] = None
        self._children: dict[str, subprocess.Popen[bytes]] = {}
        self._children_lock = threading.RLock()
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=15000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_fabric_meta(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_definition(
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    agent_function TEXT NOT NULL,
                    instructions TEXT,
                    desired_state TEXT NOT NULL DEFAULT 'active'
                        CHECK(desired_state IN ('active','stopped')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_project(
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK(status IN ('active','archived')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_project_member(
                    project_id TEXT NOT NULL REFERENCES agent_project(project_id) ON DELETE CASCADE,
                    agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('owner','supervisor','contributor','observer')),
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY(project_id,agent_id)
                );
                CREATE TABLE IF NOT EXISTS agent_instance(
                    instance_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id) ON DELETE CASCADE,
                    process_id INTEGER,
                    status TEXT NOT NULL CHECK(status IN ('starting','idle','running','stopping','stopped','failed','orphaned')),
                    current_job_id TEXT,
                    started_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    stopped_at TEXT,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_job(
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES agent_project(project_id),
                    source_agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id),
                    target_agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id),
                    claimed_instance_id TEXT REFERENCES agent_instance(instance_id),
                    session_id TEXT,
                    objective TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 50,
                    status TEXT NOT NULL DEFAULT 'queued'
                        CHECK(status IN ('queued','running','completed','failed','cancelled','blocked')),
                    runtime_task_id TEXT,
                    runtime_run_id TEXT,
                    result TEXT,
                    error TEXT,
                    steward_state TEXT NOT NULL DEFAULT 'normal'
                        CHECK(steward_state IN ('normal','nudged','showstopper','held','completed')),
                    nudge_count INTEGER NOT NULL DEFAULT 0,
                    queued_at TEXT NOT NULL,
                    claimed_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    heartbeat_at TEXT,
                    activity_at TEXT,
                    last_progress_at TEXT,
                    last_nudge_at TEXT
                );
                CREATE INDEX IF NOT EXISTS agent_job_project_status
                    ON agent_job(project_id,status,priority DESC,queued_at);
                CREATE TABLE IF NOT EXISTS agent_goal(
                    goal_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES agent_project(project_id) ON DELETE CASCADE,
                    job_id TEXT REFERENCES agent_job(job_id) ON DELETE CASCADE,
                    parent_goal_id TEXT REFERENCES agent_goal(goal_id) ON DELETE CASCADE,
                    agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id),
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','in_progress','blocked','completed','cancelled')),
                    blocker_severity TEXT NOT NULL DEFAULT 'none'
                        CHECK(blocker_severity IN ('none','recoverable','showstopper')),
                    required_resolution TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS agent_goal_project ON agent_goal(project_id,status,updated_at);
                CREATE TABLE IF NOT EXISTS agent_checkin(
                    checkin_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES agent_project(project_id) ON DELETE CASCADE,
                    job_id TEXT NOT NULL REFERENCES agent_job(job_id) ON DELETE CASCADE,
                    goal_id TEXT REFERENCES agent_goal(goal_id) ON DELETE SET NULL,
                    agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id),
                    report_kind TEXT NOT NULL CHECK(report_kind IN ('progress','blocked','completed')),
                    summary TEXT NOT NULL,
                    blocker_severity TEXT NOT NULL DEFAULT 'none'
                        CHECK(blocker_severity IN ('none','recoverable','showstopper')),
                    required_resolution TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_directive(
                    directive_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES agent_project(project_id) ON DELETE CASCADE,
                    job_id TEXT NOT NULL REFERENCES agent_job(job_id) ON DELETE CASCADE,
                    goal_id TEXT REFERENCES agent_goal(goal_id) ON DELETE SET NULL,
                    source_agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id),
                    target_agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id),
                    directive_kind TEXT NOT NULL CHECK(directive_kind IN ('continue','hold','escalate')),
                    content TEXT NOT NULL,
                    acknowledged_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_board_thread(
                    thread_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES agent_project(project_id) ON DELETE CASCADE,
                    job_id TEXT REFERENCES agent_job(job_id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    thread_kind TEXT NOT NULL CHECK(thread_kind IN ('general','job')),
                    created_at TEXT NOT NULL,
                    UNIQUE(project_id,job_id)
                );
                CREATE TABLE IF NOT EXISTS agent_board_message(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    project_id TEXT NOT NULL REFERENCES agent_project(project_id) ON DELETE CASCADE,
                    thread_id TEXT NOT NULL REFERENCES agent_board_thread(thread_id) ON DELETE CASCADE,
                    job_id TEXT REFERENCES agent_job(job_id) ON DELETE CASCADE,
                    goal_id TEXT REFERENCES agent_goal(goal_id) ON DELETE SET NULL,
                    source_agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id),
                    target_agent_id TEXT REFERENCES agent_definition(agent_id),
                    reply_to_message_id TEXT REFERENCES agent_board_message(message_id),
                    message_kind TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS agent_board_project_sequence
                    ON agent_board_message(project_id,seq);
                CREATE TABLE IF NOT EXISTS agent_board_cursor(
                    project_id TEXT NOT NULL REFERENCES agent_project(project_id) ON DELETE CASCADE,
                    agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id) ON DELETE CASCADE,
                    last_read_sequence INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(project_id,agent_id)
                );
                CREATE TABLE IF NOT EXISTS agent_board_ack(
                    message_id TEXT NOT NULL REFERENCES agent_board_message(message_id) ON DELETE CASCADE,
                    agent_id TEXT NOT NULL REFERENCES agent_definition(agent_id) ON DELETE CASCADE,
                    acknowledged_at TEXT NOT NULL,
                    PRIMARY KEY(message_id,agent_id)
                );
                CREATE TABLE IF NOT EXISTS agent_supervisor_config(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    stale_seconds INTEGER NOT NULL DEFAULT 60,
                    showstopper_seconds INTEGER NOT NULL DEFAULT 120,
                    max_nudges INTEGER NOT NULL DEFAULT 3,
                    updated_at TEXT NOT NULL
                );
                """
            )
            now = utc_now()
            db.execute(
                "INSERT INTO agent_fabric_meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (SCHEMA_VERSION,),
            )
            db.execute(
                "INSERT OR IGNORE INTO agent_definition(agent_id,name,agent_function,instructions,desired_state,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    PRIMARY_AGENT_ID,
                    "Para",
                    "Own project outcomes, supervise assigned agents, and preserve auditable decisions.",
                    "Work only from the active project's goals, directives, and message board.",
                    "active",
                    now,
                    now,
                ),
            )
            db.execute(
                "INSERT OR IGNORE INTO agent_project(project_id,name,description,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    DEFAULT_PROJECT_ID,
                    "Default project",
                    "Default project for existing and unscoped agent work.",
                    "active",
                    now,
                    now,
                ),
            )
            db.execute(
                "INSERT OR IGNORE INTO agent_project_member(project_id,agent_id,role,joined_at) VALUES(?,?,?,?)",
                (DEFAULT_PROJECT_ID, PRIMARY_AGENT_ID, "owner", now),
            )
            self._ensure_general_thread(db, DEFAULT_PROJECT_ID, now)
            db.execute(
                "INSERT OR IGNORE INTO agent_supervisor_config(singleton,updated_at) VALUES(1,?)",
                (now,),
            )

    @staticmethod
    def _ensure_general_thread(db: sqlite3.Connection, project_id: str, now: Optional[str] = None) -> str:
        row = db.execute(
            "SELECT thread_id FROM agent_board_thread WHERE project_id=? AND thread_kind='general'",
            (project_id,),
        ).fetchone()
        if row:
            return str(row["thread_id"])
        thread_id = new_id("thread")
        db.execute(
            "INSERT INTO agent_board_thread(thread_id,project_id,job_id,title,thread_kind,created_at) "
            "VALUES(?,?,NULL,'Project board','general',?)",
            (thread_id, project_id, now or utc_now()),
        )
        return thread_id

    @staticmethod
    def _is_member(db: sqlite3.Connection, project_id: str, agent_id: str) -> bool:
        return db.execute(
            "SELECT 1 FROM agent_project_member WHERE project_id=? AND agent_id=?",
            (project_id, agent_id),
        ).fetchone() is not None

    @staticmethod
    def _member_role(db: sqlite3.Connection, project_id: str, agent_id: str) -> Optional[str]:
        row = db.execute(
            "SELECT role FROM agent_project_member WHERE project_id=? AND agent_id=?",
            (project_id, agent_id),
        ).fetchone()
        return str(row["role"]) if row else None

    def create_project(self, name: Any, description: Any = "") -> dict[str, Any]:
        clean_name = bounded(name, 128)
        clean_description = bounded(description, 4096, required=False)
        project_id = new_id("project")
        now = utc_now()
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO agent_project(project_id,name,description,status,created_at,updated_at) VALUES(?,?,?,'active',?,?)",
                    (project_id, clean_name, clean_description or None, now, now),
                )
                db.execute(
                    "INSERT INTO agent_project_member(project_id,agent_id,role,joined_at) VALUES(?,?,?,?)",
                    (project_id, PRIMARY_AGENT_ID, "owner", now),
                )
                self._ensure_general_thread(db, project_id, now)
                db.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("A project with that name already exists.") from exc
        return {"ok": True, "projectId": project_id}

    def assign(self, project_id: Any, agent_id: Any, role: Any = "contributor") -> dict[str, Any]:
        project = bounded(project_id, 47)
        agent = bounded(agent_id, 47)
        clean_role = bounded(role, 24)
        if clean_role not in PROJECT_ROLES:
            raise ValueError("Project role must be owner, supervisor, contributor, or observer.")
        now = utc_now()
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM agent_project WHERE project_id=?", (project,)).fetchone():
                raise KeyError("Project not found.")
            if not db.execute("SELECT 1 FROM agent_definition WHERE agent_id=?", (agent,)).fetchone():
                raise KeyError("Agent not found.")
            db.execute(
                "INSERT INTO agent_project_member(project_id,agent_id,role,joined_at) VALUES(?,?,?,?) "
                "ON CONFLICT(project_id,agent_id) DO UPDATE SET role=excluded.role",
                (project, agent, clean_role, now),
            )
            db.execute(
                "INSERT INTO agent_board_cursor(project_id,agent_id,last_read_sequence,updated_at) VALUES(?,?,0,?) "
                "ON CONFLICT(project_id,agent_id) DO NOTHING",
                (project, agent, now),
            )
        return {"ok": True}

    def create_agent(self, name: Any, agent_function: Any, instructions: Any = "", *, start: bool = True) -> dict[str, Any]:
        clean_name = bounded(name, 96)
        clean_function = bounded(agent_function, 4096)
        clean_instructions = bounded(instructions, 16384, required=False)
        agent_id = new_id("agent")
        now = utc_now()
        try:
            with self.connect() as db:
                db.execute(
                    "INSERT INTO agent_definition(agent_id,name,agent_function,instructions,desired_state,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (agent_id, clean_name, clean_function, clean_instructions or None, "active" if start else "stopped", now, now),
                )
                db.execute(
                    "INSERT INTO agent_project_member(project_id,agent_id,role,joined_at) VALUES(?,?,?,?)",
                    (DEFAULT_PROJECT_ID, agent_id, "contributor", now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("An agent with that name already exists.") from exc
        result: dict[str, Any] = {"ok": True, "agentId": agent_id}
        if start:
            result.update(self.start_agent(agent_id))
        return result

    def start_agent(self, agent_id: Any) -> dict[str, Any]:
        agent = bounded(agent_id, 47)
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM agent_definition WHERE agent_id=?", (agent,)).fetchone():
                raise KeyError("Agent not found.")
            live = db.execute(
                "SELECT instance_id,process_id FROM agent_instance WHERE agent_id=? "
                "AND status IN ('starting','idle','running') ORDER BY started_at DESC LIMIT 1",
                (agent,),
            ).fetchone()
            if live:
                raise ValueError("This agent already has a healthy process.")
            instance_id = new_id("instance")
            now = utc_now()
            db.execute(
                "UPDATE agent_definition SET desired_state='active',updated_at=? WHERE agent_id=?",
                (now, agent),
            )
            db.execute(
                "INSERT INTO agent_instance(instance_id,agent_id,process_id,status,started_at,heartbeat_at) "
                "VALUES(?,?,NULL,'starting',?,?)",
                (instance_id, agent, now, now),
            )
        process_id: Optional[int] = None
        if self.spawn_processes:
            command = [
                sys.executable,
                "-m",
                "backend.app.agent_worker",
                "--root",
                str(self.root),
                "--database",
                str(self.database),
                "--agent-id",
                agent,
                "--instance-id",
                instance_id,
            ]
            kwargs: dict[str, Any] = {
                "cwd": str(Path(__file__).resolve().parents[2]),
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "shell": False,
                "close_fds": True,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            child = subprocess.Popen(command, **kwargs)  # noqa: S603
            process_id = child.pid
            with self._children_lock:
                self._children[instance_id] = child
        with self.connect() as db:
            db.execute(
                "UPDATE agent_instance SET process_id=?,status=?,heartbeat_at=? WHERE instance_id=?",
                (process_id, "starting" if self.spawn_processes else "idle", utc_now(), instance_id),
            )
        return {"instanceId": instance_id, "processId": process_id}

    def stop_agent(self, agent_id: Any) -> dict[str, Any]:
        agent = bounded(agent_id, 47)
        with self.connect() as db:
            rows = db.execute(
                "SELECT instance_id,process_id FROM agent_instance WHERE agent_id=? "
                "AND status IN ('starting','idle','running','stopping')",
                (agent,),
            ).fetchall()
            now = utc_now()
            db.execute("UPDATE agent_definition SET desired_state='stopped',updated_at=? WHERE agent_id=?", (now, agent))
            db.execute(
                "UPDATE agent_instance SET status='stopping',heartbeat_at=? WHERE agent_id=? "
                "AND status IN ('starting','idle','running')",
                (now, agent),
            )
        for row in rows:
            instance_id = str(row["instance_id"])
            with self._children_lock:
                child = self._children.pop(instance_id, None)
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            elif row["process_id"] and int(row["process_id"]) != os.getpid():
                try:
                    os.kill(int(row["process_id"]), signal.SIGTERM)
                except (OSError, PermissionError):
                    pass
        with self.connect() as db:
            now = utc_now()
            db.execute(
                "UPDATE agent_instance SET status='stopped',stopped_at=?,heartbeat_at=? WHERE agent_id=? "
                "AND status IN ('starting','idle','running','stopping')",
                (now, now, agent),
            )
        return {"ok": True}

    def projects(self, *, query: str = "", limit: int = 100) -> dict[str, Any]:
        search = bounded(query, 512, required=False)
        limit = max(1, min(int(limit), 500))
        with self.connect() as db:
            rows = db.execute(
                "SELECT p.* FROM agent_project p WHERE (?='' OR p.name LIKE '%'||?||'%' OR COALESCE(p.description,'') LIKE '%'||?||'%') "
                "ORDER BY CASE WHEN p.project_id=? THEN 0 ELSE 1 END,p.updated_at DESC LIMIT ?",
                (search, search, search, DEFAULT_PROJECT_ID, limit),
            ).fetchall()
            items = []
            for row in rows:
                members = db.execute(
                    "SELECT m.agent_id,d.name,m.role FROM agent_project_member m "
                    "JOIN agent_definition d ON d.agent_id=m.agent_id WHERE m.project_id=? ORDER BY d.name",
                    (row["project_id"],),
                ).fetchall()
                counts = db.execute(
                    "SELECT status,count(*) count FROM agent_job WHERE project_id=? GROUP BY status",
                    (row["project_id"],),
                ).fetchall()
                job_counts = {status: 0 for status in ("queued", "running", "blocked", "completed", "failed")}
                job_counts.update({str(item["status"]): int(item["count"]) for item in counts})
                open_showstoppers = db.execute(
                    "SELECT count(*) count FROM agent_goal WHERE project_id=? AND status='blocked' AND blocker_severity='showstopper'",
                    (row["project_id"],),
                ).fetchone()["count"]
                message_count = db.execute(
                    "SELECT count(*) count FROM agent_board_message WHERE project_id=?",
                    (row["project_id"],),
                ).fetchone()["count"]
                items.append({
                    "projectId": row["project_id"],
                    "name": row["name"],
                    "description": row["description"],
                    "status": row["status"],
                    "createdAt": row["created_at"],
                    "updatedAt": row["updated_at"],
                    "members": [
                        {"agentId": member["agent_id"], "name": member["name"], "role": member["role"]}
                        for member in members
                    ],
                    "jobs": job_counts,
                    "openShowstoppers": int(open_showstoppers),
                    "messageCount": int(message_count),
                })
        return {"schemaVersion": "parallm.agent-projects.v1", "items": items}

    def agents(self, *, project_id: str = "", query: str = "", limit: int = 100) -> dict[str, Any]:
        project = bounded(project_id, 47, required=False)
        search = bounded(query, 512, required=False)
        limit = max(1, min(int(limit), 500))
        with self.connect() as db:
            rows = db.execute(
                "SELECT d.* FROM agent_definition d WHERE (?='' OR d.name LIKE '%'||?||'%' OR d.agent_function LIKE '%'||?||'%') "
                "AND (?='' OR EXISTS(SELECT 1 FROM agent_project_member pm WHERE pm.project_id=? AND pm.agent_id=d.agent_id)) "
                "ORDER BY CASE WHEN d.agent_id=? THEN 0 ELSE 1 END,d.name LIMIT ?",
                (search, search, search, project, project, PRIMARY_AGENT_ID, limit),
            ).fetchall()
            items = []
            for row in rows:
                instance = db.execute(
                    "SELECT * FROM agent_instance WHERE agent_id=? ORDER BY started_at DESC LIMIT 1",
                    (row["agent_id"],),
                ).fetchone()
                memberships = db.execute(
                    "SELECT pm.project_id,p.name,pm.role FROM agent_project_member pm "
                    "JOIN agent_project p ON p.project_id=pm.project_id WHERE pm.agent_id=? ORDER BY p.name",
                    (row["agent_id"],),
                ).fetchall()
                items.append({
                    "agentId": row["agent_id"],
                    "name": row["name"],
                    "function": row["agent_function"],
                    "instructions": row["instructions"],
                    "desiredState": row["desired_state"],
                    "projects": [
                        {"projectId": member["project_id"], "name": member["name"], "role": member["role"]}
                        for member in memberships
                    ],
                    "instance": ({
                        "instanceId": instance["instance_id"],
                        "processId": instance["process_id"],
                        "status": instance["status"],
                        "currentJobId": instance["current_job_id"],
                        "heartbeatAt": instance["heartbeat_at"],
                        "lastError": instance["last_error"],
                    } if instance else None),
                })
        return {"schemaVersion": "parallm.agents.v1", "items": items}

    def submit(
        self,
        project_id: Any,
        target_agent_id: Any,
        objective: Any,
        *,
        source_agent_id: Any = PRIMARY_AGENT_ID,
        session_id: Any = "",
        priority: Any = 50,
    ) -> dict[str, Any]:
        project = bounded(project_id or DEFAULT_PROJECT_ID, 47)
        target = bounded(target_agent_id, 47)
        source = bounded(source_agent_id or PRIMARY_AGENT_ID, 47)
        clean_objective = bounded(objective, 65536)
        clean_session = bounded(session_id, 128, required=False)
        try:
            clean_priority = max(0, min(100, int(priority)))
        except (TypeError, ValueError) as exc:
            raise ValueError("Priority must be an integer between 0 and 100.") from exc
        job_id = new_id("job")
        goal_id = new_id("goal")
        thread_id = new_id("thread")
        message_id = new_id("board")
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self._is_member(db, project, source) or not self._is_member(db, project, target):
                db.rollback()
                raise ValueError("Both source and target agents must belong to the selected project.")
            db.execute(
                "INSERT INTO agent_job(job_id,project_id,source_agent_id,target_agent_id,session_id,objective,priority,status,queued_at) "
                "VALUES(?,?,?,?,?,?,?,'queued',?)",
                (job_id, project, source, target, clean_session or None, clean_objective, clean_priority, now),
            )
            db.execute(
                "INSERT INTO agent_goal(goal_id,project_id,job_id,parent_goal_id,agent_id,title,description,status,created_at,updated_at) "
                "VALUES(?,?,?,NULL,?,?,?,'pending',?,?)",
                (goal_id, project, job_id, target, clean_objective[:160], clean_objective, now, now),
            )
            db.execute(
                "INSERT INTO agent_board_thread(thread_id,project_id,job_id,title,thread_kind,created_at) VALUES(?,?,?,?,?,?)",
                (thread_id, project, job_id, clean_objective[:160], "job", now),
            )
            db.execute(
                "INSERT INTO agent_board_message(message_id,project_id,thread_id,job_id,goal_id,source_agent_id,target_agent_id,"
                "message_kind,severity,content,content_sha256,created_at) VALUES(?,?,?,?,?,?,?,'question','info',?,?,?)",
                (message_id, project, thread_id, job_id, goal_id, source, target, clean_objective, text_hash(clean_objective), now),
            )
            db.commit()
        return {
            "ok": True,
            "projectId": project,
            "jobId": job_id,
            "goalId": goal_id,
            "threadId": thread_id,
            "targetAgentId": target,
        }

    def jobs(self, *, project_id: str = "", query: str = "", limit: int = 100) -> dict[str, Any]:
        project = bounded(project_id, 47, required=False)
        search = bounded(query, 512, required=False)
        limit = max(1, min(int(limit), 500))
        with self.connect() as db:
            rows = db.execute(
                "SELECT j.*,s.name source_name,t.name target_name FROM agent_job j "
                "JOIN agent_definition s ON s.agent_id=j.source_agent_id "
                "JOIN agent_definition t ON t.agent_id=j.target_agent_id "
                "WHERE (?='' OR j.project_id=?) AND (?='' OR j.objective LIKE '%'||?||'%' OR j.job_id LIKE '%'||?||'%') "
                "ORDER BY CASE j.status WHEN 'running' THEN 0 WHEN 'blocked' THEN 1 WHEN 'queued' THEN 2 ELSE 3 END,"
                "j.priority DESC,j.queued_at DESC LIMIT ?",
                (project, project, search, search, search, limit),
            ).fetchall()
        return {
            "schemaVersion": "parallm.agent-jobs.v1",
            "items": [self._job_payload(row) for row in rows],
        }

    @staticmethod
    def _job_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "jobId": row["job_id"],
            "projectId": row["project_id"],
            "sourceAgentId": row["source_agent_id"],
            "sourceName": row["source_name"] if "source_name" in row.keys() else None,
            "targetAgentId": row["target_agent_id"],
            "targetName": row["target_name"] if "target_name" in row.keys() else None,
            "objective": row["objective"],
            "priority": row["priority"],
            "status": row["status"],
            "stewardState": row["steward_state"],
            "nudgeCount": row["nudge_count"],
            "runtimeTaskId": row["runtime_task_id"],
            "runtimeRunId": row["runtime_run_id"],
            "result": row["result"],
            "error": row["error"],
            "queuedAt": row["queued_at"],
            "startedAt": row["started_at"],
            "completedAt": row["completed_at"],
            "heartbeatAt": row["heartbeat_at"],
            "lastProgressAt": row["last_progress_at"],
        }

    def goals(self, project_id: Any, *, job_id: Any = "", limit: int = 100) -> dict[str, Any]:
        project = bounded(project_id, 47)
        job = bounded(job_id, 47, required=False)
        limit = max(1, min(int(limit), 500))
        with self.connect() as db:
            rows = db.execute(
                "SELECT g.*,d.name agent_name FROM agent_goal g JOIN agent_definition d ON d.agent_id=g.agent_id "
                "WHERE g.project_id=? AND (?='' OR g.job_id=?) ORDER BY g.created_at LIMIT ?",
                (project, job, job, limit),
            ).fetchall()
        return {
            "schemaVersion": "parallm.agent-goals.v1",
            "items": [{
                "goalId": row["goal_id"],
                "projectId": row["project_id"],
                "jobId": row["job_id"],
                "parentGoalId": row["parent_goal_id"],
                "agentId": row["agent_id"],
                "agentName": row["agent_name"],
                "title": row["title"],
                "description": row["description"],
                "status": row["status"],
                "blockerSeverity": row["blocker_severity"],
                "requiredResolution": row["required_resolution"],
                "updatedAt": row["updated_at"],
            } for row in rows],
        }

    def board(
        self,
        project_id: Any,
        *,
        agent_id: Any = PRIMARY_AGENT_ID,
        thread_id: Any = "",
        unread_only: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        project = bounded(project_id, 47)
        agent = bounded(agent_id or PRIMARY_AGENT_ID, 47)
        thread = bounded(thread_id, 47, required=False)
        limit = max(1, min(int(limit), 500))
        with self.connect() as db:
            role = self._member_role(db, project, agent)
            if role is None:
                raise ValueError("The reader is not a member of this project.")
            cursor = db.execute(
                "SELECT last_read_sequence FROM agent_board_cursor WHERE project_id=? AND agent_id=?",
                (project, agent),
            ).fetchone()
            last_read = int(cursor["last_read_sequence"]) if cursor else 0
            oversight = role in {"owner", "supervisor"}
            rows = db.execute(
                "SELECT m.*,t.title thread_title,s.name source_name,d.name target_name,"
                "EXISTS(SELECT 1 FROM agent_board_ack a WHERE a.message_id=m.message_id AND a.agent_id=?) acknowledged "
                "FROM agent_board_message m JOIN agent_board_thread t ON t.thread_id=m.thread_id "
                "JOIN agent_definition s ON s.agent_id=m.source_agent_id "
                "LEFT JOIN agent_definition d ON d.agent_id=m.target_agent_id "
                "WHERE m.project_id=? AND (?='' OR m.thread_id=?) AND (?=0 OR m.seq>?) "
                "AND (?=1 OR m.target_agent_id IS NULL OR m.target_agent_id=? OR m.source_agent_id=?) "
                "ORDER BY m.seq DESC LIMIT ?",
                (agent, project, thread, thread, 1 if unread_only else 0, last_read,
                 1 if oversight else 0, agent, agent, limit),
            ).fetchall()
            rows = list(reversed(rows))
        return {
            "schemaVersion": "parallm.agent-board.v1",
            "projectId": project,
            "readerAgentId": agent,
            "lastReadSequence": last_read,
            "items": [{
                "sequence": row["seq"],
                "messageId": row["message_id"],
                "projectId": row["project_id"],
                "threadId": row["thread_id"],
                "threadTitle": row["thread_title"],
                "jobId": row["job_id"],
                "goalId": row["goal_id"],
                "sourceAgentId": row["source_agent_id"],
                "sourceName": row["source_name"],
                "targetAgentId": row["target_agent_id"],
                "targetName": row["target_name"],
                "replyToMessageId": row["reply_to_message_id"],
                "kind": row["message_kind"],
                "severity": row["severity"],
                "content": row["content"],
                "contentSha256": row["content_sha256"],
                "createdAt": row["created_at"],
                "acknowledged": bool(row["acknowledged"]),
            } for row in rows],
        }

    def post(
        self,
        project_id: Any,
        content: Any,
        *,
        source_agent_id: Any = PRIMARY_AGENT_ID,
        target_agent_id: Any = "",
        thread_id: Any = "",
        job_id: Any = "",
        goal_id: Any = "",
        reply_to_message_id: Any = "",
        kind: Any = "note",
        severity: Any = "info",
    ) -> dict[str, Any]:
        project = bounded(project_id, 47)
        source = bounded(source_agent_id or PRIMARY_AGENT_ID, 47)
        target = bounded(target_agent_id, 47, required=False)
        thread = bounded(thread_id, 47, required=False)
        job = bounded(job_id, 47, required=False)
        goal = bounded(goal_id, 47, required=False)
        reply = bounded(reply_to_message_id, 47, required=False)
        message_kind = bounded(kind, 24)
        message_severity = bounded(severity, 24)
        clean_content = bounded(content, 65536)
        if message_kind not in MESSAGE_KINDS:
            raise ValueError("Invalid project-board message kind.")
        if message_severity not in SEVERITIES:
            raise ValueError("Invalid project-board severity.")
        message_id = new_id("board")
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self._is_member(db, project, source):
                db.rollback()
                raise ValueError("The source agent is not a member of this project.")
            if target and not self._is_member(db, project, target):
                db.rollback()
                raise ValueError("The target agent is not a member of this project.")
            if thread:
                thread_row = db.execute(
                    "SELECT project_id,job_id FROM agent_board_thread WHERE thread_id=?",
                    (thread,),
                ).fetchone()
                if not thread_row or str(thread_row["project_id"]) != project:
                    db.rollback()
                    raise ValueError("The selected thread does not belong to this project.")
                if job and str(thread_row["job_id"] or "") != job:
                    db.rollback()
                    raise ValueError("The selected thread does not belong to this project job.")
            elif job:
                thread_row = db.execute(
                    "SELECT thread_id FROM agent_board_thread WHERE project_id=? AND job_id=?",
                    (project, job),
                ).fetchone()
                if not thread_row:
                    db.rollback()
                    raise ValueError("No board thread exists for this project job.")
                thread = str(thread_row["thread_id"])
            else:
                thread = self._ensure_general_thread(db, project, now)
            db.execute(
                "INSERT INTO agent_board_message(message_id,project_id,thread_id,job_id,goal_id,source_agent_id,target_agent_id,"
                "reply_to_message_id,message_kind,severity,content,content_sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    message_id, project, thread, job or None, goal or None, source, target or None,
                    reply or None, message_kind, message_severity, clean_content, text_hash(clean_content), now,
                ),
            )
            sequence = int(db.execute("SELECT last_insert_rowid() value").fetchone()["value"])
            db.execute("UPDATE agent_project SET updated_at=? WHERE project_id=?", (now, project))
            db.commit()
        return {"ok": True, "messageId": message_id, "threadId": thread, "sequence": sequence}

    def mark_read(self, project_id: Any, agent_id: Any, sequence: Any) -> dict[str, Any]:
        project = bounded(project_id, 47)
        agent = bounded(agent_id, 47)
        try:
            clean_sequence = max(0, int(sequence))
        except (TypeError, ValueError) as exc:
            raise ValueError("Board sequence must be a non-negative integer.") from exc
        with self.connect() as db:
            if not self._is_member(db, project, agent):
                raise ValueError("The reader is not a member of this project.")
            db.execute(
                "INSERT INTO agent_board_cursor(project_id,agent_id,last_read_sequence,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(project_id,agent_id) DO UPDATE SET "
                "last_read_sequence=max(last_read_sequence,excluded.last_read_sequence),updated_at=excluded.updated_at",
                (project, agent, clean_sequence, utc_now()),
            )
        return {"ok": True}

    def report(
        self,
        job_or_task_id: Any,
        kind: Any,
        summary: Any,
        *,
        blocker_severity: Any = "none",
        required_resolution: Any = "",
    ) -> dict[str, Any]:
        identifier = bounded(job_or_task_id, 128)
        report_kind = bounded(kind, 24)
        clean_summary = bounded(summary, 65536)
        severity = bounded(blocker_severity or "none", 24)
        resolution = bounded(required_resolution, 4096, required=False)
        if report_kind not in REPORT_KINDS:
            raise ValueError("Report kind must be progress, blocked, or completed.")
        if severity not in {"none", "recoverable", "showstopper"}:
            raise ValueError("Blocker severity must be none, recoverable, or showstopper.")
        if report_kind == "blocked" and severity == "none":
            severity = "recoverable"
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute(
                "SELECT * FROM agent_job WHERE job_id=? OR runtime_task_id=? ORDER BY CASE WHEN job_id=? THEN 0 ELSE 1 END LIMIT 1",
                (identifier, identifier, identifier),
            ).fetchone()
            if not job:
                db.rollback()
                raise KeyError("Agent job not found.")
            goal = db.execute(
                "SELECT goal_id FROM agent_goal WHERE job_id=? AND parent_goal_id IS NULL LIMIT 1",
                (job["job_id"],),
            ).fetchone()
            goal_id = str(goal["goal_id"]) if goal else None
            checkin_id = new_id("checkin")
            db.execute(
                "INSERT INTO agent_checkin(checkin_id,project_id,job_id,goal_id,agent_id,report_kind,summary,"
                "blocker_severity,required_resolution,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    checkin_id, job["project_id"], job["job_id"], goal_id, job["target_agent_id"], report_kind,
                    clean_summary, severity, resolution or None, now,
                ),
            )
            if report_kind == "completed":
                job_status, goal_status, steward_state = "completed", "completed", "completed"
            elif report_kind == "blocked":
                job_status, goal_status = "blocked", "blocked"
                steward_state = "showstopper" if severity == "showstopper" else "normal"
            else:
                job_status, goal_status, steward_state = "running", "in_progress", "normal"
            db.execute(
                "UPDATE agent_job SET status=?,steward_state=?,result=CASE WHEN ?='completed' THEN ? ELSE result END,"
                "last_progress_at=?,heartbeat_at=?,completed_at=CASE WHEN ?='completed' THEN ? ELSE completed_at END "
                "WHERE job_id=?",
                (job_status, steward_state, report_kind, clean_summary, now, now, report_kind, now, job["job_id"]),
            )
            if goal_id:
                db.execute(
                    "UPDATE agent_goal SET status=?,blocker_severity=?,required_resolution=?,updated_at=? WHERE goal_id=?",
                    (goal_status, severity, resolution or None, now, goal_id),
                )
            thread = db.execute(
                "SELECT thread_id FROM agent_board_thread WHERE project_id=? AND job_id=?",
                (job["project_id"], job["job_id"]),
            ).fetchone()
            if thread:
                message_kind = "blocker" if report_kind == "blocked" else "result" if report_kind == "completed" else "progress"
                message_severity = "info" if severity == "none" else severity
                message_id = new_id("board")
                db.execute(
                    "INSERT INTO agent_board_message(message_id,project_id,thread_id,job_id,goal_id,source_agent_id,"
                    "message_kind,severity,content,content_sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        message_id, job["project_id"], thread["thread_id"], job["job_id"], goal_id,
                        job["target_agent_id"], message_kind, message_severity, clean_summary,
                        text_hash(clean_summary), now,
                    ),
                )
            db.commit()
        return {"ok": True, "checkinId": checkin_id, "jobId": job["job_id"]}

    def directives(self, agent_id: Any, *, job_id: Any = "", unread_only: bool = False, limit: int = 100) -> dict[str, Any]:
        agent = bounded(agent_id, 47)
        job = bounded(job_id, 47, required=False)
        limit = max(1, min(int(limit), 500))
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM agent_directive WHERE target_agent_id=? AND (?='' OR job_id=?) "
                "AND (?=0 OR acknowledged_at IS NULL) ORDER BY created_at LIMIT ?",
                (agent, job, job, 1 if unread_only else 0, limit),
            ).fetchall()
        return {
            "schemaVersion": "parallm.agent-directives.v1",
            "items": [{
                "directiveId": row["directive_id"],
                "projectId": row["project_id"],
                "jobId": row["job_id"],
                "goalId": row["goal_id"],
                "sourceAgentId": row["source_agent_id"],
                "targetAgentId": row["target_agent_id"],
                "kind": row["directive_kind"],
                "content": row["content"],
                "acknowledgedAt": row["acknowledged_at"],
                "createdAt": row["created_at"],
            } for row in rows],
        }

    def context(self, project_id: Any, agent_id: Any, *, job_id: Any = "") -> dict[str, Any]:
        project = bounded(project_id, 47)
        agent = bounded(agent_id, 47)
        job = bounded(job_id, 47, required=False)
        if not self._project_membership(project, agent):
            raise ValueError("The agent is not a member of this project.")
        project_items = self.projects(limit=500)["items"]
        project_payload = next(item for item in project_items if item["projectId"] == project)
        return {
            "schemaVersion": "parallm.agent-context.v1",
            "project": project_payload,
            "goals": self.goals(project, job_id=job, limit=100)["items"],
            "board": self.board(project, agent_id=agent, unread_only=True, limit=100)["items"],
            "directives": self.directives(agent, job_id=job, unread_only=True, limit=100)["items"],
        }

    def _project_membership(self, project_id: str, agent_id: str) -> bool:
        with self.connect() as db:
            return self._is_member(db, project_id, agent_id)

    def heartbeat(self, instance_id: str, *, status: str = "idle", current_job_id: str = "") -> None:
        clean_status = status if status in {"starting", "idle", "running", "stopping", "stopped", "failed"} else "idle"
        with self.connect() as db:
            db.execute(
                "UPDATE agent_instance SET status=?,current_job_id=?,heartbeat_at=? WHERE instance_id=?",
                (clean_status, current_job_id or None, utc_now(), instance_id),
            )
            if current_job_id:
                db.execute(
                    "UPDATE agent_job SET heartbeat_at=? WHERE job_id=?",
                    (utc_now(), current_job_id),
                )

    def claim_next_job(self, agent_id: str, instance_id: str) -> Optional[dict[str, Any]]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM agent_job WHERE target_agent_id=? AND status='queued' "
                "ORDER BY priority DESC,queued_at LIMIT 1",
                (agent_id,),
            ).fetchone()
            if not row:
                db.commit()
                return None
            now = utc_now()
            changed = db.execute(
                "UPDATE agent_job SET status='running',claimed_instance_id=?,claimed_at=?,started_at=?,heartbeat_at=?,"
                "activity_at=?,last_progress_at=? WHERE job_id=? AND status='queued'",
                (instance_id, now, now, now, now, now, row["job_id"]),
            ).rowcount
            if changed != 1:
                db.rollback()
                return None
            db.execute(
                "UPDATE agent_goal SET status='in_progress',updated_at=? WHERE job_id=? AND status='pending'",
                (now, row["job_id"]),
            )
            db.execute(
                "UPDATE agent_instance SET status='running',current_job_id=?,heartbeat_at=? WHERE instance_id=?",
                (row["job_id"], now, instance_id),
            )
            db.commit()
            payload = dict(row)
            payload["status"] = "running"
            return payload

    def bind_runtime(self, job_id: str, task_id: str, run_id: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE agent_job SET runtime_task_id=?,runtime_run_id=?,activity_at=?,heartbeat_at=? WHERE job_id=?",
                (task_id or None, run_id or None, utc_now(), utc_now(), job_id),
            )

    def fail_job(self, job_id: str, error: str) -> None:
        now = utc_now()
        with self.connect() as db:
            db.execute(
                "UPDATE agent_job SET status='failed',error=?,completed_at=?,heartbeat_at=? WHERE job_id=?",
                (bounded(error, 65536), now, now, job_id),
            )
            db.execute(
                "UPDATE agent_goal SET status='blocked',blocker_severity='recoverable',required_resolution=?,updated_at=? "
                "WHERE job_id=?",
                (bounded(error, 4096)[:4096], now, job_id),
            )

    def finish_instance(self, instance_id: str, *, error: str = "") -> None:
        now = utc_now()
        with self.connect() as db:
            db.execute(
                "UPDATE agent_instance SET status=?,current_job_id=NULL,stopped_at=?,heartbeat_at=?,last_error=? WHERE instance_id=?",
                ("failed" if error else "stopped", now, now, error or None, instance_id),
            )

    def steward_once(self, *, now: Optional[datetime] = None) -> dict[str, Any]:
        observed_at = now or datetime.now(timezone.utc)
        with self.connect() as db:
            config = db.execute("SELECT * FROM agent_supervisor_config WHERE singleton=1").fetchone()
            stale_seconds = int(config["stale_seconds"])
            showstopper_seconds = int(config["showstopper_seconds"])
            max_nudges = int(config["max_nudges"])
            rows = db.execute(
                "SELECT j.*,g.goal_id,g.blocker_severity,g.required_resolution FROM agent_job j "
                "LEFT JOIN agent_goal g ON g.job_id=j.job_id AND g.parent_goal_id IS NULL "
                "WHERE j.status IN ('running','blocked') ORDER BY j.queued_at"
            ).fetchall()
        nudged = held = skipped_active = 0
        for row in rows:
            job = dict(row)
            progress_at = parse_time(job.get("last_progress_at")) or parse_time(job.get("started_at"))
            activity_samples = [
                sample
                for sample in (parse_time(job.get("activity_at")), parse_time(job.get("heartbeat_at")))
                if sample is not None
            ]
            activity_at = max(activity_samples) if activity_samples else None
            stale = progress_at is None or (observed_at - progress_at).total_seconds() >= stale_seconds
            active = activity_at is not None and (observed_at - activity_at).total_seconds() < stale_seconds
            showstopper = str(job.get("blocker_severity") or "none") == "showstopper"
            if showstopper:
                last_progress = progress_at or observed_at
                if (observed_at - last_progress).total_seconds() >= showstopper_seconds or str(job.get("steward_state")) != "held":
                    self._issue_directive(
                        job,
                        "hold",
                        "Show-stopper reported. Hold execution and wait for the required resolution: "
                        + str(job.get("required_resolution") or "operator intervention required"),
                        "showstopper",
                    )
                    held += 1
                continue
            if not stale:
                continue
            if active:
                skipped_active += 1
                continue
            if int(job.get("nudge_count") or 0) >= max_nudges:
                self._issue_directive(
                    job,
                    "escalate",
                    "Agent remains stalled after bounded continuation nudges. Operator review is required.",
                    "recoverable",
                )
                continue
            self._issue_directive(job, "continue", PROCEED_DIRECTIVE, "info")
            nudged += 1
        return {"nudged": nudged, "held": held, "skippedActive": skipped_active, "checked": len(rows)}

    def _issue_directive(self, job: dict[str, Any], kind: str, content: str, severity: str) -> None:
        now = utc_now()
        with self.connect() as db:
            recent = db.execute(
                "SELECT 1 FROM agent_directive WHERE job_id=? AND directive_kind=? AND acknowledged_at IS NULL "
                "AND created_at>=? LIMIT 1",
                (
                    job["job_id"],
                    kind,
                    (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                ),
            ).fetchone()
            if recent:
                return
            directive_id = new_id("directive")
            db.execute(
                "INSERT INTO agent_directive(directive_id,project_id,job_id,goal_id,source_agent_id,target_agent_id,"
                "directive_kind,content,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    directive_id, job["project_id"], job["job_id"], job.get("goal_id"), PRIMARY_AGENT_ID,
                    job["target_agent_id"], kind, content, now,
                ),
            )
            thread = db.execute(
                "SELECT thread_id FROM agent_board_thread WHERE project_id=? AND job_id=?",
                (job["project_id"], job["job_id"]),
            ).fetchone()
            if thread:
                db.execute(
                    "INSERT INTO agent_board_message(message_id,project_id,thread_id,job_id,goal_id,source_agent_id,"
                    "target_agent_id,message_kind,severity,content,content_sha256,created_at) VALUES(?,?,?,?,?,?,?,'directive',?,?,?,?)",
                    (
                        new_id("board"), job["project_id"], thread["thread_id"], job["job_id"], job.get("goal_id"),
                        PRIMARY_AGENT_ID, job["target_agent_id"], severity, content, text_hash(content), now,
                    ),
                )
            db.execute(
                "UPDATE agent_job SET steward_state=?,nudge_count=nudge_count+CASE WHEN ?='continue' THEN 1 ELSE 0 END,"
                "last_nudge_at=? WHERE job_id=?",
                ("held" if kind == "hold" else "nudged", kind, now, job["job_id"]),
            )

    def start(self) -> None:
        if self._steward_thread and self._steward_thread.is_alive():
            return
        self._stop.clear()

        def run() -> None:
            while not self._stop.wait(self.steward_interval_seconds):
                try:
                    self.steward_once()
                except Exception:
                    continue

        self._steward_thread = threading.Thread(target=run, name="para-agent-steward", daemon=True)
        self._steward_thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._steward_thread:
            self._steward_thread.join(timeout=max(1.0, self.steward_interval_seconds * 2))
        with self._children_lock:
            agents = list(self._children)
        for instance_id in agents:
            with self.connect() as db:
                row = db.execute("SELECT agent_id FROM agent_instance WHERE instance_id=?", (instance_id,)).fetchone()
            if row:
                self.stop_agent(str(row["agent_id"]))


def extract_answer(state: dict[str, Any]) -> str:
    summary = state.get("summary") if isinstance(state.get("summary"), dict) else {}
    front = summary.get("frontAnswer") if isinstance(summary.get("frontAnswer"), dict) else {}
    for value in (
        front.get("answer"),
        summary.get("answer"),
        summary.get("output"),
        summary.get("summary"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""
