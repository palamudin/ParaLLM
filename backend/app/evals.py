from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.engine import RuntimeErrorWithCode
from runtime.eval_runner import validate_arm_manifest, validate_suite_manifest

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


def _new_run_id(prefix: str) -> str:
    stamp = storage.utc_now().replace("-", "").replace(":", "").replace("+00:00", "z").replace("T", "-")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:6]}"


def _parse_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _parse_float(value: Any, default: float, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _load_suite(paths: storage.Paths, suite_id: str) -> Dict[str, Any]:
    manifest = read_manifest_by_id(paths.eval_suites, suite_id, "suiteId")
    if not isinstance(manifest, dict):
        raise RuntimeErrorWithCode(f"Unknown suiteId: {suite_id}", 404)
    return validate_suite_manifest(manifest, paths.eval_suites / f"{suite_id}.json")


def _load_arm(paths: storage.Paths, arm_id: str) -> Dict[str, Any]:
    manifest = read_manifest_by_id(paths.eval_arms, arm_id, "armId")
    if not isinstance(manifest, dict):
        raise RuntimeErrorWithCode(f"Unknown armId: {arm_id}", 404)
    return validate_arm_manifest(manifest, paths.eval_arms / f"{arm_id}.json")


def _subset_suite_case(suite: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    if not case_id:
        return suite
    cases = [case for case in suite.get("cases", []) if str(case.get("caseId") or "") == case_id]
    if not cases:
        raise RuntimeErrorWithCode(f"Case {case_id} was not found in suite {suite.get('suiteId')}.", 404)
    return {
        **suite,
        "suiteId": f"{suite['suiteId']}--{case_id}",
        "title": f"{suite['title']} | {cases[0]['title']}",
        "cases": cases,
    }


def _combine_suites(suites: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not suites:
        raise RuntimeErrorWithCode("Judge needs at least one suite.", 400)
    title_bits = [str(suite.get("title") or suite.get("suiteId") or "").strip() for suite in suites]
    combined_cases: List[Dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for suite in suites:
        suite_id = str(suite.get("suiteId") or "").strip()
        for case in suite.get("cases", []):
            if not isinstance(case, dict):
                continue
            base_case_id = str(case.get("caseId") or "").strip()
            next_case = dict(case)
            next_case_id = base_case_id
            if next_case_id in seen_case_ids:
                next_case_id = f"{suite_id}-{base_case_id}"
            next_case["caseId"] = next_case_id
            seen_case_ids.add(next_case_id)
            combined_cases.append(next_case)
    return {
        "suiteId": f"judge-{uuid.uuid4().hex[:8]}",
        "title": "Judge suite | " + " + ".join([bit for bit in title_bits if bit][:3]),
        "description": "Composite judge suite launched from the front canvas.",
        "judgeRubric": suites[0].get("judgeRubric", {}),
        "cases": combined_cases,
    }


def _front_runtime_budget(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "maxCostUsd": _parse_float(payload.get("maxCostUsd"), 5.0, 0.0),
        "maxTotalTokens": 0,
        "maxOutputTokens": 0,
    }


def _front_runtime_research(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": _parse_bool(payload.get("researchEnabled"), False),
        "externalWebAccess": _parse_bool(payload.get("researchExternalWebAccess"), True),
        "domains": _parse_list(payload.get("researchDomains")),
    }


def _front_runtime_vetting(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"enabled": _parse_bool(payload.get("vettingEnabled"), True)}


def _front_runtime_loop(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rounds": _parse_int(payload.get("loopRounds"), 1, 1),
        "delayMs": _parse_int(payload.get("loopDelayMs"), 0, 0),
    }


def _front_runtime_timeouts(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("targetTimeouts")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _front_summarizer_harness(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("summarizerHarness")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _front_worker_list(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("workers")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    return raw if isinstance(raw, list) else []


def _build_front_eval_arm(payload: Dict[str, Any]) -> Dict[str, Any]:
    provider = str(payload.get("provider") or "openai").strip() or "openai"
    model = str(payload.get("model") or "").strip()
    summarizer_provider = str(payload.get("summarizerProvider") or provider).strip() or provider
    summarizer_model = str(payload.get("summarizerModel") or model).strip() or model
    direct_provider = str(payload.get("directProvider") or provider).strip() or provider
    direct_model = str(payload.get("directModel") or model).strip() or model
    execution_mode = str(payload.get("executionMode") or "live").strip() or "live"
    return {
        "armId": f"front-eval-{uuid.uuid4().hex[:8]}",
        "title": str(payload.get("title") or "Current setup vs single-thread baseline").strip() or "Current setup vs single-thread baseline",
        "description": "Front canvas compare run using the current staged worker/summarizer setup against a direct baseline.",
        "type": "steered",
        "runtime": {
            "executionMode": execution_mode,
            "contextMode": str(payload.get("contextMode") or "weighted").strip() or "weighted",
            "directBaselineMode": "both",
            "provider": provider,
            "model": model,
            "directProvider": direct_provider,
            "directModel": direct_model,
            "ollamaBaseUrl": payload.get("ollamaBaseUrl"),
            "summarizerProvider": summarizer_provider,
            "summarizerModel": summarizer_model,
            "summarizerHarness": _front_summarizer_harness(payload),
            "reasoningEffort": str(payload.get("reasoningEffort") or "low").strip() or "low",
            "budget": _front_runtime_budget(payload),
            "research": _front_runtime_research(payload),
            "vetting": _front_runtime_vetting(payload),
            "preferredLoop": _front_runtime_loop(payload),
            "targetTimeouts": _front_runtime_timeouts(payload),
            "requireLive": execution_mode == "live",
            "allowMockFallback": execution_mode != "live",
        },
        "workers": _front_worker_list(payload),
    }


def _base_run_payload(run_id: str, suite: Dict[str, Any], arm_ids: List[str], judge_model: str, canvas: str) -> Dict[str, Any]:
    return {
        "runId": run_id,
        "suiteId": str(suite.get("suiteId") or "").strip(),
        "armIds": arm_ids,
        "replicates": 1,
        "loopSweep": [1],
        "judgeModel": str(judge_model or "gpt-5.4").strip() or "gpt-5.4",
        "status": "queued",
        "createdAt": storage.utc_now(),
        "updatedAt": storage.utc_now(),
        "source": "front",
        "canvas": canvas,
    }


def start_front_eval_run(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    paths = storage.project_paths(root)
    ensure_eval_paths(paths)
    suite_id = str(payload.get("suiteId") or "").strip()
    if not suite_id:
        raise RuntimeErrorWithCode("Eval needs a suite selection.", 400)
    case_id = str(payload.get("caseId") or "").strip()
    suite = _subset_suite_case(_load_suite(paths, suite_id), case_id)
    arm = validate_arm_manifest(_build_front_eval_arm(payload), paths.root / "front-eval")
    run_id = _new_run_id("eval")
    run = _base_run_payload(run_id, suite, [arm["armId"]], str(payload.get("judgeModel") or "gpt-5.4"), "eval")
    run["loopSweep"] = [max(1, int(arm["runtime"]["preferredLoop"]["rounds"]))]
    run["inlineSuite"] = suite
    run["inlineArms"] = {arm["armId"]: arm}
    run["selectedCaseId"] = case_id or (suite.get("cases") or [{}])[0].get("caseId")
    run["launcher"] = {"kind": "front-eval", "label": arm["title"]}
    write_eval_run(paths, run)
    launch_eval_runner(run_id, paths.root)
    return {"message": "Front eval queued.", "runId": run_id, "run": storage.build_eval_run_preview(run)}


def start_front_judge_run(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    paths = storage.project_paths(root)
    ensure_eval_paths(paths)
    suite_ids = _parse_list(payload.get("suiteIds"))
    if not suite_ids:
        raise RuntimeErrorWithCode("Judge needs at least one selected suite.", 400)
    arm_ids = _parse_list(payload.get("armIds"))
    if not arm_ids:
        raise RuntimeErrorWithCode("Judge needs at least one selected arm.", 400)
    suites = [_load_suite(paths, suite_id) for suite_id in suite_ids]
    arms = [_load_arm(paths, arm_id) for arm_id in arm_ids]
    suite = validate_suite_manifest(_combine_suites(suites), paths.root / "front-judge")
    run_id = _new_run_id("judge")
    run = _base_run_payload(run_id, suite, [arm["armId"] for arm in arms], str(payload.get("judgeModel") or "gpt-5.4"), "judge")
    run["replicates"] = _parse_int(payload.get("replicates"), 1, 1)
    run["loopSweep"] = [
        _parse_int(value, 1, 1)
        for value in _parse_list(payload.get("loopSweep"))
        if _parse_int(value, 1, 1) > 0
    ] or [1]
    run["inlineSuite"] = suite
    run["inlineArms"] = {arm["armId"]: arm for arm in arms}
    run["launcher"] = {
        "kind": "front-judge",
        "suiteIds": suite_ids,
        "armIds": [arm["armId"] for arm in arms],
    }
    write_eval_run(paths, run)
    launch_eval_runner(run_id, paths.root)
    return {"message": "Front judge queued.", "runId": run_id, "run": storage.build_eval_run_preview(run)}


def start_eval_run(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    raise RuntimeErrorWithCode(
        "Legacy batch eval launch has moved to Home. Set Front mode to Eval and run from the main composer.",
        410,
    )
