from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import storage, control


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y%m%d-%H%M%SZ")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def move_dir_contents(source_dir: Path, archive_dir: Path) -> List[str]:
    moved: List[str] = []
    if not source_dir.exists():
        return moved
    archive_dir.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source_dir.iterdir(), key=lambda item: item.name.lower()):
        destination = archive_dir / entry.name
        if destination.exists():
            suffix = 1
            while True:
                candidate = archive_dir / f"{entry.stem}-{suffix}{entry.suffix}"
                if not candidate.exists():
                    destination = candidate
                    break
                suffix += 1
        shutil.move(str(entry), str(destination))
        moved.append(str(destination))
    source_dir.mkdir(parents=True, exist_ok=True)
    return moved


def move_file(source_file: Path, archive_dir: Path, warnings: List[str] | None = None) -> str | None:
    if not source_file.exists():
        return None
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / source_file.name
    if destination.exists():
        suffix = 1
        while True:
            candidate = archive_dir / f"{source_file.stem}-{suffix}{source_file.suffix}"
            if not candidate.exists():
                destination = candidate
                break
            suffix += 1
    try:
        shutil.move(str(source_file), str(destination))
    except PermissionError as exc:
        # Live backend logs can be held open on Windows. Preserve a snapshot and
        # leave the active writer alone so archiving does not die halfway.
        try:
            shutil.copy2(source_file, destination)
            if warnings is not None:
                warnings.append(f"Copied locked file instead of moving it: {source_file} ({exc})")
        except OSError as copy_exc:
            if warnings is not None:
                warnings.append(f"Skipped locked file that could not be copied: {source_file} ({copy_exc})")
            return None
    return str(destination)


def build_fresh_state(current_state: Dict[str, Any]) -> Dict[str, Any]:
    next_state = storage.default_state()
    draft = control.normalize_draft_state(
        current_state.get("draft") if isinstance(current_state.get("draft"), dict) else {}
    )
    next_state["draft"] = draft
    next_state["lastUpdated"] = control.utc_now()
    return next_state


def archive_active_logs(root: Path) -> Dict[str, Any]:
    paths = storage.project_paths(root)
    stamp = utc_stamp()
    archive_root = paths.data / "old_logs" / stamp
    archive_root.mkdir(parents=True, exist_ok=True)

    current_state = storage.read_state_payload(paths)
    write_json(archive_root / "state.before_reset.json", current_state)
    auth_backend_file = paths.data / "auth_provider_backends.json"
    if auth_backend_file.exists():
        shutil.copy2(auth_backend_file, archive_root / "auth_provider_backends.before_reset.json")

    moved: Dict[str, Any] = {
        "directories": {},
        "files": {},
    }
    warnings: List[str] = []

    dir_targets = [
        ("checkpoints", paths.checkpoints),
        ("outputs", paths.outputs),
        ("sessions", paths.sessions),
        ("tasks", paths.tasks),
        ("task_states", paths.task_states),
        ("jobs", paths.jobs),
        ("locks", paths.data / "locks"),
        ("logs", paths.data / "logs"),
        ("exports", paths.data / "exports"),
        ("eval_runs", paths.eval_runs),
        ("benchmark_runs", paths.data / "benchmarks" / "vetting" / "runs"),
    ]
    for label, source_dir in dir_targets:
        moved["directories"][label] = move_dir_contents(source_dir, archive_root / label)

    file_targets = [
        ("steps", paths.steps),
        ("events", paths.events),
        ("backend_live", paths.data / "backend-live.log"),
        ("backend_live_err", paths.data / "backend-live.err.log"),
    ]
    for label, source_file in file_targets:
        moved["files"][label] = move_file(source_file, archive_root / "files", warnings)

    fresh_state = build_fresh_state(current_state)
    write_json(paths.state, fresh_state)
    paths.steps.write_text("", encoding="utf-8")
    paths.events.write_text("", encoding="utf-8")

    placeholder_summary = {
        "status": "verification_reset",
        "message": "Historic benchmark runs were archived to data/old_logs. Fresh verified runs will repopulate this file.",
        "updatedAt": control.utc_now(),
    }
    bench_root = paths.data / "benchmarks" / "vetting"
    bench_root.mkdir(parents=True, exist_ok=True)
    write_json(bench_root / "summary.json", placeholder_summary)
    write_json(bench_root / "latest.json", placeholder_summary)

    manifest = {
        "archivedAt": control.utc_now(),
        "archiveRoot": str(archive_root),
        "preservedDraft": fresh_state.get("draft"),
        "previousTaskId": ((current_state.get("activeTask") or {}) if isinstance(current_state.get("activeTask"), dict) else {}).get("taskId"),
        "moved": moved,
        "warnings": warnings,
    }
    write_json(archive_root / "manifest.json", manifest)
    return manifest


def main() -> int:
    root = project_root()
    manifest = archive_active_logs(root)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
