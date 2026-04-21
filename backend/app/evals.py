from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from runtime.engine import normalize_model_id

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
    paths = storage.project_paths(root)
    ensure_eval_paths(paths)

    suite_id = str(payload.get("suiteId") or "").strip()
    suite = read_manifest_by_id(paths.eval_suites, suite_id, "suiteId")
    if not suite:
        raise ValueError("Choose a valid eval suite first.")

    arm_ids_raw = payload.get("armIds", [])
    if isinstance(arm_ids_raw, str):
        try:
            parsed = json.loads(arm_ids_raw)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in arm_ids_raw.split(",")]
        arm_ids = parsed if isinstance(parsed, list) else []
    else:
        arm_ids = arm_ids_raw if isinstance(arm_ids_raw, list) else []
    arm_ids = [str(value).strip() for value in arm_ids if str(value).strip()]
    arm_ids = list(dict.fromkeys(arm_ids))
    if not arm_ids:
        raise ValueError("Choose at least one eval arm.")
    for arm_id in arm_ids:
        if not read_manifest_by_id(paths.eval_arms, arm_id, "armId"):
            raise ValueError("Unknown eval arm: " + arm_id)

    replicates = max(1, min(5, int(payload.get("replicates") or 1)))
    loop_sweep_raw = str(payload.get("loopSweep") or "1").strip()
    loop_sweep: list[int] = []
    for chunk in [piece.strip() for piece in loop_sweep_raw.replace(",", " ").split()]:
        if not chunk:
            continue
        if not chunk.isdigit():
            raise ValueError("Loop sweep must contain only integers such as 1,2,3.")
        value = max(1, min(12, int(chunk)))
        if value not in loop_sweep:
            loop_sweep.append(value)
    if not loop_sweep:
        loop_sweep = [1]

    judge_model = normalize_model_id(str(payload.get("judgeModel") or "gpt-5.4").strip(), "gpt-5.4")
    run_id = "eval-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(8).hex()[:6]
    run = {
        "runId": run_id,
        "status": "queued",
        "createdAt": storage.utc_now(),
        "updatedAt": storage.utc_now(),
        "startedAt": None,
        "completedAt": None,
        "suiteId": suite_id,
        "armIds": arm_ids,
        "replicates": replicates,
        "loopSweep": loop_sweep,
        "judgeModel": judge_model,
        "current": None,
        "summary": None,
        "artifactIndex": {},
        "cases": [],
        "error": None,
    }
    write_eval_run(paths, run)
    try:
        launch_eval_runner(run_id, paths.root)
    except Exception as exc:  # noqa: BLE001
        run["status"] = "error"
        run["completedAt"] = storage.utc_now()
        run["error"] = str(exc)
        write_eval_run(paths, run)
        raise
    return {
        "message": "Eval run queued.",
        "runId": run_id,
        "suiteId": suite_id,
        "armIds": arm_ids,
        "replicates": replicates,
        "loopSweep": loop_sweep,
        "judgeModel": judge_model,
    }
