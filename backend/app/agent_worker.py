from __future__ import annotations

import argparse
import os
import signal
import threading
import time
from pathlib import Path
from typing import Any

from . import evals, storage
from .agent_fabric import AgentFabric, extract_answer, utc_now


TERMINAL_RUN_STATES = {"completed", "cancelled", "error", "budget_exhausted", "interrupted", "failed"}


def build_agent_prompt(fabric: AgentFabric, agent_id: str, job: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    context = fabric.context(str(job["project_id"]), agent_id, job_id=str(job["job_id"]))
    with fabric.connect() as db:
        definition = db.execute(
            "SELECT name,agent_function,instructions FROM agent_definition WHERE agent_id=?",
            (agent_id,),
        ).fetchone()
    if not definition:
        raise RuntimeError("Agent definition disappeared before execution.")
    project = context["project"]
    lines = [
        f"You are {definition['name']} working inside ParaLLM project {project['name']}.",
        f"Function: {definition['agent_function']}",
    ]
    if definition["instructions"]:
        lines.append(f"Standing instructions: {definition['instructions']}")
    lines.extend(
        [
            "Use only the project context below for inter-agent collaboration. Do not infer messages from other projects.",
            "Report progress, blockers, and completion through the agent reporting contract.",
            "",
            "Assigned objective:",
            str(job["objective"]),
        ]
    )
    if context["goals"]:
        lines.extend(["", "Current project goals:"])
        for goal in context["goals"]:
            lines.append(
                f"- [{goal['status']}] {goal['title']}"
                + (f" | blocker={goal['blockerSeverity']}" if goal["blockerSeverity"] != "none" else "")
            )
    if context["directives"]:
        lines.extend(["", "Supervisor directives:"])
        lines.extend(f"- {item['content']}" for item in context["directives"])
    if context["board"]:
        lines.extend(["", "Unread project-board messages:"])
        for item in context["board"]:
            target = f" -> {item['targetName']}" if item.get("targetName") else ""
            lines.append(f"- {item['sourceName']}{target} [{item['kind']}/{item['severity']}]: {item['content']}")
    return "\n".join(lines).strip(), context


def acknowledge_context(fabric: AgentFabric, project_id: str, agent_id: str, context: dict[str, Any]) -> None:
    board = context.get("board") if isinstance(context.get("board"), list) else []
    if board:
        fabric.mark_read(project_id, agent_id, max(int(item.get("sequence") or 0) for item in board))
    directives = context.get("directives") if isinstance(context.get("directives"), list) else []
    if directives:
        with fabric.connect() as db:
            db.executemany(
                "UPDATE agent_directive SET acknowledged_at=? WHERE directive_id=? AND target_agent_id=?",
                [(utc_now(), str(item["directiveId"]), agent_id) for item in directives],
            )


def execute_job(fabric: AgentFabric, instance_id: str, agent_id: str, job: dict[str, Any]) -> None:
    prompt, context = build_agent_prompt(fabric, agent_id, job)
    acknowledge_context(fabric, str(job["project_id"]), agent_id, context)
    launched = evals.start_front_live_run(
        {
            "objective": prompt,
            "loopRounds": 1,
            "loopDelayMs": 0,
        },
        fabric.root,
    )
    task_id = str(launched.get("taskId") or "")
    run_id = str(launched.get("runId") or "")
    fabric.bind_runtime(str(job["job_id"]), task_id, run_id)
    while True:
        fabric.heartbeat(instance_id, status="running", current_job_id=str(job["job_id"]))
        run = evals.sync_front_live_run(run_id, fabric.root) or {}
        status = str(run.get("status") or "queued").strip().lower()
        if status in TERMINAL_RUN_STATES:
            break
        time.sleep(1.0)
    if status != "completed":
        message = str(run.get("error") or f"Para runtime ended in {status} state.")
        fabric.fail_job(str(job["job_id"]), message)
        fabric.report(
            str(job["job_id"]),
            "blocked",
            message,
            blocker_severity="recoverable",
            required_resolution="Inspect the linked Para runtime task and retry after resolving its failure.",
        )
        return
    state = storage.read_task_state_payload(task_id, storage.project_paths(fabric.root)) or {}
    answer = extract_answer(state) or "Para completed the assigned objective without a canonical summary answer."
    fabric.report(str(job["job_id"]), "completed", answer)


def run_worker(root: Path, database: Path, agent_id: str, instance_id: str) -> int:
    fabric = AgentFabric(root, database=database, spawn_processes=False)
    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    with fabric.connect() as db:
        db.execute(
            "UPDATE agent_instance SET process_id=?,status='idle',heartbeat_at=? WHERE instance_id=? AND agent_id=?",
            (os.getpid(), utc_now(), instance_id, agent_id),
        )
    error = ""
    try:
        while not stop.is_set():
            with fabric.connect() as db:
                definition = db.execute(
                    "SELECT desired_state FROM agent_definition WHERE agent_id=?",
                    (agent_id,),
                ).fetchone()
            if not definition or str(definition["desired_state"]) != "active":
                break
            job = fabric.claim_next_job(agent_id, instance_id)
            if job is None:
                fabric.heartbeat(instance_id, status="idle")
                stop.wait(0.5)
                continue
            try:
                execute_job(fabric, instance_id, agent_id, job)
            except Exception as exc:  # noqa: BLE001 - the process must persist and audit task failure
                message = f"{type(exc).__name__}: {exc}"
                fabric.fail_job(str(job["job_id"]), message)
            finally:
                fabric.heartbeat(instance_id, status="idle")
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        return 1
    finally:
        fabric.finish_instance(instance_id, error=error)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one durable ParaLLM Python agent process.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--instance-id", required=True)
    args = parser.parse_args()
    return run_worker(
        args.root.resolve(),
        args.database.resolve(),
        str(args.agent_id),
        str(args.instance_id),
    )


if __name__ == "__main__":
    raise SystemExit(main())
