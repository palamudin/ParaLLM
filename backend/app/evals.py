from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from runtime.engine import RuntimeErrorWithCode

from . import metadata, storage


def ensure_eval_paths(paths: storage.Paths) -> None:
    for path in [paths.evals, paths.eval_suites, paths.eval_arms, paths.eval_runs]:
        path.mkdir(parents=True, exist_ok=True)


def read_manifest_by_id(directory: Path, manifest_id: str, id_key: str) -> Optional[Dict[str, Any]]:
    candidate = directory / f"{manifest_id}.json"
    payload = storage.read_json_file(candidate)
    if isinstance(payload, dict) and str(payload.get(id_key) or "").strip() == manifest_id:
        return payload
    for file_path in sorted(directory.glob("*.json")):
        payload = storage.read_json_file(file_path)
        if isinstance(payload, dict) and str(payload.get(id_key) or "").strip() == manifest_id:
            return payload
    return None


def _subprocess_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "cwd": str(Path(__file__).resolve().parents[2]),
        "env": os.environ.copy(),
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    return kwargs


def write_eval_run(paths: storage.Paths, run: Dict[str, Any]) -> Dict[str, Any]:
    ensure_eval_paths(paths)
    run_id = str(run.get("runId") or "").strip()
    if not run_id:
        raise ValueError("Eval runId is required.")
    run_dir = paths.eval_runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run["updatedAt"] = storage.utc_now()
    if metadata.postgres_enabled(paths.root):
        metadata.write_eval_run_payload(paths.root, run)
    else:
        (run_dir / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    return run


def launch_eval_runner(run_id: str, root: Optional[Path] = None) -> None:
    repo_root = Path(root).resolve() if root else Path(__file__).resolve().parents[2]
    command = [sys.executable, str(repo_root / "runtime" / "eval_runner.py"), f"--root={repo_root}", f"--run-id={run_id}"]
    subprocess.Popen(command, **_subprocess_kwargs())  # noqa: S603,S607


def start_eval_run(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    raise RuntimeErrorWithCode(
        "Legacy batch eval launch has moved to Home. Set Front mode to Eval and run from the main composer.",
        410,
    )
