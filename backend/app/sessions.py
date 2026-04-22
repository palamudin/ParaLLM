from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from runtime.engine import LoopRuntime, RuntimeErrorWithCode

from . import artifacts, control, faults, jobs, storage


def _runtime(root: Optional[Path] = None) -> LoopRuntime:
    return LoopRuntime(Path(root).resolve() if root else Path(__file__).resolve().parents[2])


def truncate_plain_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    return text if len(text) <= limit else text[: max(0, limit - 3)].rstrip() + "..."


def normalize_state_snapshot(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    current = state if isinstance(state, dict) else {}
    normalized = storage.normalize_state_contract(current)
    normalized["draft"] = control.normalize_draft_state(normalized.get("draft") if isinstance(normalized.get("draft"), dict) else {})
    return normalized


def build_session_context_summary(state: Dict[str, Any]) -> str:
    task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    summary = state.get("summary") if isinstance(state.get("summary"), dict) else None
    usage = storage.normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
    workers = state.get("workers") if isinstance(state.get("workers"), dict) else {}
    lines: list[str] = []

    if task:
        objective = truncate_plain_text(task.get("objective"), 240)
        if objective:
            lines.append("Prior objective: " + objective)

    if summary:
        front_answer = ""
        if isinstance(summary.get("frontAnswer"), dict):
            front_answer = truncate_plain_text((summary.get("frontAnswer") or {}).get("answer"), 220)
        if front_answer:
            lines.append("Prior adjudicated answer: " + front_answer)

        opinion = ""
        if isinstance(summary.get("summarizerOpinion"), dict):
            opinion = truncate_plain_text((summary.get("summarizerOpinion") or {}).get("stance"), 170)
        elif isinstance(summary.get("frontAnswer"), dict):
            opinion = truncate_plain_text((summary.get("frontAnswer") or {}).get("stance"), 170)
        if opinion:
            lines.append("Prior summarizer stance: " + opinion)

        stable: list[str] = []
        for finding in list(summary.get("stableFindings") or [])[:3]:
            trimmed = truncate_plain_text(finding, 150)
            if trimmed:
                stable.append(trimmed)
        if stable:
            lines.append("Stable findings: " + "; ".join(stable))

        recommended = truncate_plain_text(summary.get("recommendedNextAction"), 180)
        if recommended:
            lines.append("Recommended next action: " + recommended)

        conflicts: list[str] = []
        for conflict in list(summary.get("conflicts") or [])[:3]:
            if not isinstance(conflict, dict):
                continue
            topic = truncate_plain_text(conflict.get("topic"), 120)
            if topic:
                conflicts.append(topic)
        if conflicts:
            lines.append("Open conflicts: " + "; ".join(conflicts))

    if not summary and workers:
        observations: list[str] = []
        for worker_id, checkpoint in workers.items():
            if not isinstance(checkpoint, dict):
                continue
            observation = truncate_plain_text(checkpoint.get("observation"), 120)
            if observation:
                observations.append(f"{worker_id}: {observation}")
            if len(observations) >= 3:
                break
        if observations:
            lines.append("Latest lane signals: " + " | ".join(observations))

    if int(usage.get("totalTokens") or 0) > 0 or float(usage.get("estimatedCostUsd") or 0.0) > 0.0:
        lines.append(
            "Prior usage: %d tokens, approx $%.4f spend."
            % (int(usage.get("totalTokens") or 0), float(usage.get("estimatedCostUsd") or 0.0))
        )

    if not lines:
        lines.append("No prior session context was available.")
    return "\n".join(lines[:5])


def _session_archive_filename(task_id: Optional[str]) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", str(task_id or "session")).strip("-") or "session"
    return f"session-{control.utc_now().replace(':', '').replace('-', '').replace('+00:00', 'Z').replace('T', '-')}-{slug}.json"


def _export_bundle_filename(source: str, task_id: Optional[str]) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", str(task_id or source or "session")).strip("-") or "session"
    prefix = "export-archive" if str(source or "").strip().lower() == "archive" else "export-current"
    return f"{prefix}-{control.utc_now().replace(':', '').replace('-', '').replace('+00:00', 'Z').replace('T', '-')}-{slug}.json"


def _write_session_archive(paths: storage.Paths, archive: Dict[str, Any]) -> str:
    faults.maybe_raise_fault("session.reset.before_archive_write")
    archive_file = _session_archive_filename(archive.get("taskId"))
    artifacts.write_json_artifact(paths.root, "sessions", archive_file, archive)
    return archive_file


def _read_session_archive(paths: storage.Paths, archive_file: str) -> Optional[Dict[str, Any]]:
    return artifacts.read_json_artifact(paths.root, "sessions", archive_file)


def _write_export_bundle(paths: storage.Paths, bundle: Dict[str, Any], source: str, task_id: Optional[str]) -> str:
    faults.maybe_raise_fault("session.export.before_bundle_write")
    bundle_file = _export_bundle_filename(source, task_id)
    artifacts.write_json_artifact(paths.root, "exports", bundle_file, bundle)
    return bundle_file


def reset_session(root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    paths = storage.project_paths(runtime.root)
    state = storage.read_state_payload(paths)
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("An autonomous loop is running. Cancel it before resetting the session.", 409)

    previous_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    previous_task_id = (previous_task or {}).get("taskId")
    archive_file: Optional[str] = None
    carry_context = ""
    had_session = bool(previous_task or state.get("summary") or state.get("workers"))

    def mutate(current: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal archive_file, carry_context
        carry_context = build_session_context_summary(current) if had_session else ""
        if had_session:
            archive = {
                "createdAt": control.utc_now(),
                "archivedAt": control.utc_now(),
                "reason": "reset_session",
                "taskId": (previous_task or {}).get("taskId"),
                "objective": (previous_task or {}).get("objective"),
                "summaryRound": int(((current.get("summary") or {}) if isinstance(current.get("summary"), dict) else {}).get("round") or 0),
                "carryContext": carry_context,
                "state": normalize_state_snapshot(current),
            }
            archive_file = _write_session_archive(paths, archive)
        next_state = storage.default_state()
        next_state["draft"] = (
            control.build_draft_from_task(
                previous_task,
                {"objective": "", "constraints": [], "sessionContext": carry_context, "updatedAt": control.utc_now()},
                True,
            )
            if previous_task
            else control.build_draft_from_task(None, {"sessionContext": carry_context, "updatedAt": control.utc_now()})
        )
        return next_state

    updated_state = runtime.mutate_state(mutate)
    runtime.append_event("session_reset", {"fromTaskId": previous_task_id, "archiveFile": archive_file, "hasCarryContext": carry_context != ""})
    runtime.append_step(
        "session",
        "Archived the current session and loaded a carry-forward draft." if had_session else "Loaded a fresh draft with no prior session to archive.",
        {"fromTaskId": previous_task_id, "archiveFile": archive_file, "hasCarryContext": carry_context != ""},
    )
    return {
        "message": "Session reset and carry-forward draft loaded." if had_session else "Fresh draft loaded.",
        "archiveFile": archive_file,
        "carryContext": carry_context,
        "draft": updated_state["draft"],
    }


def reset_state(root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    state = storage.read_state_payload(storage.project_paths(runtime.root))
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("An autonomous loop is running. Cancel it before resetting state.", 409)
    with runtime.with_lock():
        runtime.write_state_unlocked(storage.default_state())
    runtime.append_event("state_reset", {})
    runtime.append_step("reset", "State reset to defaults.", {})
    return {"message": "State reset."}


def replay_session(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    paths = storage.project_paths(runtime.root)
    archive_file = Path(str(payload.get("archiveFile") or "").strip()).name
    if not archive_file:
        raise RuntimeErrorWithCode("An archive file is required.", 400)
    state = storage.read_state_payload(paths)
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("Cancel the active loop before replaying an archived session.", 409)

    archive = _read_session_archive(paths, archive_file)
    if not isinstance(archive, dict):
        raise RuntimeErrorWithCode("Archive not found.", 404)

    archived_state = normalize_state_snapshot(archive.get("state") if isinstance(archive.get("state"), dict) else {})
    faults.maybe_raise_fault("session.replay.before_restore")

    def mutate(_: Dict[str, Any]) -> Dict[str, Any]:
        next_state = normalize_state_snapshot(archived_state)
        next_state["loop"] = storage.default_loop_state()
        next_state["loop"]["lastMessage"] = "Replayed archived session into the workspace."
        next_state["lastUpdated"] = control.utc_now()
        return next_state

    restored_state = runtime.mutate_state(mutate)
    if isinstance(restored_state.get("activeTask"), dict):
        control._write_task_snapshot_unlocked(runtime, restored_state["activeTask"])

    runtime.append_event("session_replayed", {"archiveFile": archive_file, "taskId": ((restored_state.get("activeTask") or {}) if isinstance(restored_state.get("activeTask"), dict) else {}).get("taskId")})
    runtime.append_step("session", "Replayed an archived session into the workspace.", {"archiveFile": archive_file, "taskId": ((restored_state.get("activeTask") or {}) if isinstance(restored_state.get("activeTask"), dict) else {}).get("taskId")})
    return {"message": "Archived session replayed.", "archiveFile": archive_file, "state": restored_state}


def export_session(archive_file: str = "", root: Optional[Path] = None) -> Dict[str, Any]:
    paths = storage.project_paths(root)
    archive_file = Path(str(archive_file or "").strip()).name
    source = "archive" if archive_file else "current"
    bundle_warnings: list[str] = []
    bundle: Dict[str, Any] = {
        "exportedAt": control.utc_now(),
        "source": source,
        "artifactPolicy": storage.artifact_visibility_policy(),
        "contractWarnings": bundle_warnings,
    }

    task_id: Optional[str]
    if archive_file:
        archive = _read_session_archive(paths, archive_file)
        if not isinstance(archive, dict):
            raise RuntimeErrorWithCode("Archive not found.", 404)
        bundle["archiveFile"] = archive_file
        bundle["archive"] = archive
        archived_state = normalize_state_snapshot(archive.get("state") if isinstance(archive.get("state"), dict) else {})
        for warning in archived_state.get("contractWarnings") or []:
            storage.append_contract_warning(bundle_warnings, f"archive state: {warning}")
        task_id = str(archive.get("taskId") or "").strip() or None
    else:
        state = storage.read_state_payload(paths)
        bundle["state"] = normalize_state_snapshot(state)
        for warning in (bundle["state"].get("contractWarnings") or []):
            storage.append_contract_warning(bundle_warnings, f"state: {warning}")
        task_id = str((((state.get("activeTask") or {}) if isinstance(state.get("activeTask"), dict) else {}).get("taskId")) or "").strip() or None

    jobs_out = []
    for job in storage.read_jobs(paths):
        if task_id is not None and str(job.get("taskId") or "") != task_id:
            continue
        normalized_job = storage.default_job(job)
        for warning in normalized_job.get("contractWarnings") or []:
            storage.append_contract_warning(bundle_warnings, f"job {normalized_job.get('jobId') or 'unknown'}: {warning}")
        jobs_out.append(normalized_job)
    bundle["jobs"] = jobs_out

    exported_artifacts = []
    artifact_files = artifacts.list_json_artifacts(paths.root, ["checkpoints", "outputs"])
    for artifact_file in artifact_files:
        artifact_name = str(artifact_file.get("name") or "").strip()
        artifact_category = str(artifact_file.get("category") or "").strip()
        if not artifact_name or not artifact_category:
            storage.append_contract_warning(bundle_warnings, "Dropped an artifact entry with missing name or category during export.")
            continue
        content = artifacts.read_json_artifact(paths.root, artifact_category, artifact_name)
        artifact_size = storage.coerce_int(
            artifact_file.get("size"),
            default=0,
            minimum=0,
            warnings=bundle_warnings,
            label=f"{artifact_name}.size",
        ) or 0
        entry = storage.build_artifact_history_entry(
            artifact_name,
            str(artifact_file.get("modifiedAt") or ""),
            artifact_size,
            content,
        )
        if entry is None:
            storage.append_contract_warning(bundle_warnings, f"Dropped non-round artifact {artifact_name} from export.")
            continue
        if task_id is not None and str(entry.get("taskId") or "") != task_id:
            continue
        if not isinstance(content, dict):
            storage.append_contract_warning(bundle_warnings, f"Dropped unreadable artifact content for {artifact_name}.")
            continue
        meta = dict(entry)
        meta.pop("path", None)
        for warning in meta.get("contractWarnings") or []:
            storage.append_contract_warning(bundle_warnings, f"artifact {artifact_name}: {warning}")
        exported_artifacts.append({"meta": meta, "content": content})
    bundle["artifacts"] = exported_artifacts
    bundle_file = _write_export_bundle(paths, bundle, source, task_id)
    bundle["bundleFile"] = bundle_file
    return bundle
