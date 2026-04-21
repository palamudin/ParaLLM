from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from runtime.engine import (
    DEFAULT_MODEL_ID,
    LoopRuntime,
    RuntimeErrorWithCode,
    coerce_bool,
    default_budget_config,
    default_dynamic_spinup_config,
    default_github_tool_config,
    default_local_file_tool_config,
    default_research_config,
    default_summarizer_harness,
    default_vetting_config,
    normalize_allowed_domains,
    normalize_budget_config,
    normalize_dynamic_spinup_config,
    normalize_github_repos,
    normalize_github_tool_config,
    normalize_harness_config,
    normalize_local_file_roots,
    normalize_local_file_tool_config,
    normalize_model_id,
    normalize_research_config,
    normalize_string_list,
    normalize_vetting_config,
    task_workers,
    worker_catalog,
)

from .config import deployment_topology
from .secrets import env_secret_keys, external_secret_keys, normalize_auth_key_pool
from . import storage


PRICING_SOURCE = "https://openai.com/api/pricing"
PRICING_CHECKED_AT = "2026-04-19"
PRICING_SOURCES = [
    "https://openai.com/api/pricing/",
    "https://developers.openai.com/api/docs/pricing",
]
PRICING_ACCURACY = "assume_chargeable"
PRICING_NOTE = (
    "This workspace uses a conservative chargeable-search assumption: web-search-related model "
    "tokens are treated as billable and tool calls stay separately priced."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_loop_preferences() -> Dict[str, int]:
    return {"rounds": 3, "delayMs": 1000}


def normalize_loop_preferences(config: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    current = config or {}
    default = default_loop_preferences()
    rounds = int(current.get("rounds", default["rounds"]) or default["rounds"])
    delay_ms = int(current.get("delayMs", default["delayMs"]) or default["delayMs"])
    return {
        "rounds": max(1, min(12, rounds)),
        "delayMs": max(0, min(10000, delay_ms)),
    }


def default_draft_state() -> Dict[str, Any]:
    budget = default_budget_config()
    model = DEFAULT_MODEL_ID
    loop = default_loop_preferences()
    local_files = default_local_file_tool_config()
    github_tools = default_github_tool_config()
    dynamic_spinup = default_dynamic_spinup_config()
    return {
        "objective": "",
        "constraints": [],
        "sessionContext": "",
        "executionMode": "live",
        "model": model,
        "summarizerModel": model,
        "reasoningEffort": "low",
        "maxTotalTokens": budget["maxTotalTokens"],
        "maxCostUsd": budget["maxCostUsd"],
        "maxOutputTokens": budget["maxOutputTokens"],
        "budgetTargets": budget["targets"],
        "researchEnabled": False,
        "researchExternalWebAccess": True,
        "researchDomains": [],
        "localFilesEnabled": local_files["enabled"],
        "localFileRoots": local_files["roots"],
        "githubToolsEnabled": github_tools["enabled"],
        "githubAllowedRepos": github_tools["repos"],
        "dynamicSpinupEnabled": dynamic_spinup["enabled"],
        "vettingEnabled": True,
        "summarizerHarness": default_summarizer_harness(),
        "loopRounds": loop["rounds"],
        "loopDelayMs": loop["delayMs"],
        "workers": worker_catalog(model)[:2],
        "updatedAt": utc_now(),
    }


def normalize_draft_state(draft: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    current = draft or {}
    default = default_draft_state()
    budget = normalize_budget_config(
        {
            "maxTotalTokens": current.get("maxTotalTokens", default["maxTotalTokens"]),
            "maxCostUsd": current.get("maxCostUsd", default["maxCostUsd"]),
            "maxOutputTokens": current.get("maxOutputTokens", default["maxOutputTokens"]),
            "targets": current.get("budgetTargets", default["budgetTargets"]),
        }
    )
    loop = normalize_loop_preferences(
        {
            "rounds": current.get("loopRounds", default["loopRounds"]),
            "delayMs": current.get("loopDelayMs", default["loopDelayMs"]),
        }
    )
    local_files = normalize_local_file_tool_config(
        {
            "enabled": current.get("localFilesEnabled", default["localFilesEnabled"]),
            "roots": current.get("localFileRoots", default["localFileRoots"]),
        }
    )
    github_tools = normalize_github_tool_config(
        {
            "enabled": current.get("githubToolsEnabled", default["githubToolsEnabled"]),
            "repos": current.get("githubAllowedRepos", default["githubAllowedRepos"]),
        }
    )
    dynamic_spinup = normalize_dynamic_spinup_config(
        {"enabled": current.get("dynamicSpinupEnabled", default["dynamicSpinupEnabled"])}
    )
    reasoning_effort = str(current.get("reasoningEffort", default["reasoningEffort"])).strip()
    if reasoning_effort not in {"none", "low", "medium", "high", "xhigh"}:
        reasoning_effort = str(default["reasoningEffort"])
    execution_mode = str(current.get("executionMode", default["executionMode"])).strip()
    if execution_mode not in {"live", "mock"}:
        execution_mode = str(default["executionMode"])
    model = normalize_model_id(str(current.get("model", default["model"])), str(default["model"]))
    summarizer_model = normalize_model_id(
        str(current.get("summarizerModel", default["summarizerModel"])),
        model,
    )
    return {
        "objective": str(current.get("objective", default["objective"])).strip(),
        "constraints": list(normalize_string_list(current.get("constraints", default["constraints"]))),
        "sessionContext": str(current.get("sessionContext", default["sessionContext"])).strip(),
        "executionMode": execution_mode,
        "model": model,
        "summarizerModel": summarizer_model,
        "reasoningEffort": reasoning_effort,
        "maxTotalTokens": budget["maxTotalTokens"],
        "maxCostUsd": budget["maxCostUsd"],
        "maxOutputTokens": budget["maxOutputTokens"],
        "budgetTargets": budget["targets"],
        "researchEnabled": coerce_bool(current.get("researchEnabled", default["researchEnabled"]), bool(default["researchEnabled"])),
        "researchExternalWebAccess": coerce_bool(
            current.get("researchExternalWebAccess", default["researchExternalWebAccess"]),
            bool(default["researchExternalWebAccess"]),
        ),
        "researchDomains": normalize_allowed_domains(current.get("researchDomains", default["researchDomains"])),
        "localFilesEnabled": local_files["enabled"],
        "localFileRoots": local_files["roots"],
        "githubToolsEnabled": github_tools["enabled"],
        "githubAllowedRepos": github_tools["repos"],
        "dynamicSpinupEnabled": dynamic_spinup["enabled"],
        "vettingEnabled": coerce_bool(current.get("vettingEnabled", default["vettingEnabled"]), bool(default["vettingEnabled"])),
        "summarizerHarness": normalize_harness_config(
            current.get("summarizerHarness", default["summarizerHarness"]),
            default_summarizer_harness()["concision"],
        ),
        "loopRounds": loop["rounds"],
        "loopDelayMs": loop["delayMs"],
        "workers": task_workers(
            {
                "runtime": {"model": model},
                "workers": current.get("workers", default["workers"]),
            }
        ),
        "updatedAt": str(current.get("updatedAt") or "").strip() or utc_now(),
    }


def build_draft_from_task(task: Optional[Dict[str, Any]], overrides: Optional[Dict[str, Any]] = None, reset_budget: bool = False) -> Dict[str, Any]:
    overrides = overrides or {}
    default = default_draft_state()
    if task is None:
        merged = dict(default)
        merged.update(overrides)
        return normalize_draft_state(merged)

    runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
    budget = default_budget_config() if reset_budget else normalize_budget_config(runtime.get("budget") if isinstance(runtime.get("budget"), dict) else {})
    research = normalize_research_config(runtime.get("research") if isinstance(runtime.get("research"), dict) else {})
    local_files = normalize_local_file_tool_config(runtime.get("localFiles") if isinstance(runtime.get("localFiles"), dict) else {})
    github_tools = normalize_github_tool_config(runtime.get("githubTools") if isinstance(runtime.get("githubTools"), dict) else {})
    dynamic_spinup = normalize_dynamic_spinup_config(runtime.get("dynamicSpinup") if isinstance(runtime.get("dynamicSpinup"), dict) else {})
    vetting = normalize_vetting_config(runtime.get("vetting") if isinstance(runtime.get("vetting"), dict) else {})
    model = normalize_model_id(str(runtime.get("model", default["model"])), str(default["model"]))
    summarizer = task.get("summarizer") if isinstance(task.get("summarizer"), dict) else {}
    loop_prefs = normalize_loop_preferences(task.get("preferredLoop") if isinstance(task.get("preferredLoop"), dict) else {})

    draft = {
        "objective": str(task.get("objective", default["objective"])).strip(),
        "constraints": list(normalize_string_list(task.get("constraints", default["constraints"]))),
        "sessionContext": str(task.get("sessionContext", default["sessionContext"])).strip(),
        "executionMode": str(runtime.get("executionMode", default["executionMode"])).strip(),
        "model": model,
        "summarizerModel": normalize_model_id(str(summarizer.get("model", model)), model),
        "reasoningEffort": str(runtime.get("reasoningEffort", default["reasoningEffort"])).strip(),
        "maxTotalTokens": budget["maxTotalTokens"],
        "maxCostUsd": budget["maxCostUsd"],
        "maxOutputTokens": budget["maxOutputTokens"],
        "budgetTargets": budget["targets"],
        "researchEnabled": research["enabled"],
        "researchExternalWebAccess": research["externalWebAccess"],
        "researchDomains": research["domains"],
        "localFilesEnabled": local_files["enabled"],
        "localFileRoots": local_files["roots"],
        "githubToolsEnabled": github_tools["enabled"],
        "githubAllowedRepos": github_tools["repos"],
        "dynamicSpinupEnabled": dynamic_spinup["enabled"],
        "vettingEnabled": vetting["enabled"],
        "summarizerHarness": normalize_harness_config(
            summarizer.get("harness", default["summarizerHarness"]),
            default_summarizer_harness()["concision"],
        ),
        "loopRounds": loop_prefs["rounds"],
        "loopDelayMs": loop_prefs["delayMs"],
        "workers": task_workers(task),
        "updatedAt": utc_now(),
    }
    draft.update(overrides)
    return normalize_draft_state(draft)
def auth_file_path(root: Optional[Path] = None) -> Path:
    topology = deployment_topology(root)
    if topology.secret_backend == "docker_secret" and topology.secret_file is not None:
        return topology.secret_file
    if topology.auth_file is None:
        return topology.root / "Auth.txt"
    return topology.auth_file


def read_auth_key_pool(root: Optional[Path] = None) -> list[str]:
    topology = deployment_topology(root)
    if topology.secret_backend == "env":
        return normalize_auth_key_pool(env_secret_keys())
    if topology.secret_backend == "external":
        return normalize_auth_key_pool(external_secret_keys(root))
    if topology.secret_backend == "docker_secret":
        secret_path = auth_file_path(root)
        if not secret_path.is_file():
            return []
        return normalize_auth_key_pool(secret_path.read_text(encoding="utf-8", errors="replace"))
    path = auth_file_path(root)
    if not path.is_file():
        return []
    return normalize_auth_key_pool(path.read_text(encoding="utf-8", errors="replace"))


def mask_auth_key(key: str) -> str:
    last4 = key[-4:] if len(key) >= 4 else key
    return "*" * max(4, len(key) - len(last4)) + last4


def auth_pool_status(root: Optional[Path] = None) -> Dict[str, Any]:
    topology = deployment_topology(root)
    keys = read_auth_key_pool(root)
    masks = [mask_auth_key(key) for key in keys]
    first = keys[0] if keys else ""
    last4 = first[-4:] if len(first) >= 4 else first
    return {
        "backend": topology.secret_backend,
        "hasKey": len(keys) > 0,
        "keyCount": len(keys),
        "last4": last4,
        "masked": masks[0] if masks else None,
        "masks": masks,
        "writable": topology.secret_backend == "local_file",
    }


def _parse_json_like(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    text = str(value).strip()
    if text == "":
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def _new_task_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    entropy = hashlib.md5(os.urandom(16)).hexdigest()[:6]
    return f"t-{stamp}-{entropy}"


def _empty_worker_state_map(workers: list[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for worker in workers:
        worker_id = str(worker.get("id") or "").strip()
        if worker_id:
            result[worker_id] = None
    return result


def _runtime(root: Optional[Path] = None) -> LoopRuntime:
    return LoopRuntime(Path(root).resolve() if root else Path(__file__).resolve().parents[2])


def _write_task_snapshot_unlocked(runtime: LoopRuntime, task: Dict[str, Any]) -> None:
    task_id = str(task.get("taskId") or "").strip()
    if task_id:
        runtime.write_task_snapshot_unlocked(task)


def save_draft(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    state = storage.read_state_payload(storage.project_paths(runtime.root))
    existing_draft = normalize_draft_state(state.get("draft") if isinstance(state.get("draft"), dict) else {})
    constraints = _parse_json_like(payload.get("constraints"), existing_draft["constraints"])
    workers = _parse_json_like(payload.get("workers"), existing_draft["workers"])
    summarizer_harness = _parse_json_like(payload.get("summarizerHarness"), existing_draft["summarizerHarness"])
    budget_targets = _parse_json_like(payload.get("budgetTargets"), existing_draft["budgetTargets"])
    draft = normalize_draft_state(
        {
            **existing_draft,
            "objective": str(payload.get("objective", existing_draft["objective"])).strip(),
            "constraints": constraints if isinstance(constraints, list) else existing_draft["constraints"],
            "sessionContext": str(payload.get("sessionContext", existing_draft["sessionContext"])).strip(),
            "executionMode": payload.get("executionMode", existing_draft["executionMode"]),
            "model": payload.get("model", existing_draft["model"]),
            "summarizerModel": payload.get("summarizerModel", existing_draft["summarizerModel"]),
            "reasoningEffort": payload.get("reasoningEffort", existing_draft["reasoningEffort"]),
            "maxCostUsd": payload.get("maxCostUsd", existing_draft["maxCostUsd"]),
            "maxTotalTokens": payload.get("maxTotalTokens", existing_draft["maxTotalTokens"]),
            "maxOutputTokens": payload.get("maxOutputTokens", existing_draft["maxOutputTokens"]),
            "budgetTargets": budget_targets if isinstance(budget_targets, dict) else existing_draft["budgetTargets"],
            "researchEnabled": payload.get("researchEnabled", existing_draft["researchEnabled"]),
            "researchExternalWebAccess": payload.get("researchExternalWebAccess", existing_draft["researchExternalWebAccess"]),
            "researchDomains": payload.get("researchDomains", existing_draft["researchDomains"]),
            "localFilesEnabled": payload.get("localFilesEnabled", existing_draft["localFilesEnabled"]),
            "localFileRoots": payload.get("localFileRoots", existing_draft["localFileRoots"]),
            "githubToolsEnabled": payload.get("githubToolsEnabled", existing_draft["githubToolsEnabled"]),
            "githubAllowedRepos": payload.get("githubAllowedRepos", existing_draft["githubAllowedRepos"]),
            "dynamicSpinupEnabled": payload.get("dynamicSpinupEnabled", existing_draft["dynamicSpinupEnabled"]),
            "vettingEnabled": payload.get("vettingEnabled", existing_draft["vettingEnabled"]),
            "summarizerHarness": summarizer_harness if isinstance(summarizer_harness, dict) else existing_draft["summarizerHarness"],
            "loopRounds": payload.get("loopRounds", existing_draft["loopRounds"]),
            "loopDelayMs": payload.get("loopDelayMs", existing_draft["loopDelayMs"]),
            "workers": workers if isinstance(workers, list) else existing_draft["workers"],
            "updatedAt": utc_now(),
        }
    )
    updated_state = runtime.mutate_state(lambda current: {**current, "draft": draft})
    return {"message": "Draft saved.", "draft": updated_state["draft"]}


def create_task(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    current_state = storage.read_state_payload(storage.project_paths(runtime.root))
    loop_status = str(((current_state.get("loop") or {}) if isinstance(current_state.get("loop"), dict) else {}).get("status") or "idle")
    if loop_status in {"queued", "running"}:
        raise RuntimeErrorWithCode("An autonomous loop is active. Cancel it before starting a new task.", 409)

    objective = str(payload.get("objective") or "").strip()
    if not objective:
        raise RuntimeErrorWithCode("Objective is required.", 400)

    session_context = str(payload.get("sessionContext") or "").strip()
    constraints = _parse_json_like(payload.get("constraints"), [])
    workers_input = _parse_json_like(payload.get("workers"), [])
    summarizer_harness_input = _parse_json_like(payload.get("summarizerHarness"), {})
    budget_targets_input = _parse_json_like(payload.get("budgetTargets"), {})

    execution_mode = str(payload.get("executionMode", "live")).strip()
    if execution_mode not in {"live", "mock"}:
        execution_mode = "live"
    model = normalize_model_id(str(payload.get("model", DEFAULT_MODEL_ID)), DEFAULT_MODEL_ID)
    summarizer_model = normalize_model_id(str(payload.get("summarizerModel", model)), model)
    reasoning_effort = str(payload.get("reasoningEffort", "low")).strip()
    if reasoning_effort not in {"none", "low", "medium", "high", "xhigh"}:
        reasoning_effort = "low"

    budget = normalize_budget_config(
        {
            "maxTotalTokens": payload.get("maxTotalTokens", default_budget_config()["maxTotalTokens"]),
            "maxCostUsd": payload.get("maxCostUsd", default_budget_config()["maxCostUsd"]),
            "maxOutputTokens": payload.get("maxOutputTokens", default_budget_config()["maxOutputTokens"]),
            "targets": budget_targets_input if isinstance(budget_targets_input, dict) else {},
        }
    )
    research = normalize_research_config(
        {
            "enabled": payload.get("researchEnabled", default_research_config()["enabled"]),
            "externalWebAccess": payload.get("researchExternalWebAccess", default_research_config()["externalWebAccess"]),
            "domains": payload.get("researchDomains", default_research_config()["domains"]),
        }
    )
    local_files = normalize_local_file_tool_config(
        {
            "enabled": payload.get("localFilesEnabled", default_local_file_tool_config()["enabled"]),
            "roots": payload.get("localFileRoots", default_local_file_tool_config()["roots"]),
        }
    )
    github_tools = normalize_github_tool_config(
        {
            "enabled": payload.get("githubToolsEnabled", default_github_tool_config()["enabled"]),
            "repos": payload.get("githubAllowedRepos", default_github_tool_config()["repos"]),
        }
    )
    dynamic_spinup = normalize_dynamic_spinup_config(
        {"enabled": payload.get("dynamicSpinupEnabled", default_dynamic_spinup_config()["enabled"])}
    )
    vetting = normalize_vetting_config(
        {"enabled": payload.get("vettingEnabled", default_vetting_config()["enabled"])}
    )
    preferred_loop = normalize_loop_preferences(
        {
            "rounds": payload.get("loopRounds", default_loop_preferences()["rounds"]),
            "delayMs": payload.get("loopDelayMs", default_loop_preferences()["delayMs"]),
        }
    )
    workers = task_workers(
        {
            "runtime": {"model": model},
            "workers": workers_input if isinstance(workers_input, list) else [],
        }
    )
    task_id = _new_task_id()
    task = {
        "taskId": task_id,
        "objective": objective,
        "constraints": list(constraints) if isinstance(constraints, list) else [],
        "sessionContext": session_context,
        "createdAt": utc_now(),
        "runtime": {
            "executionMode": execution_mode,
            "model": model,
            "reasoningEffort": reasoning_effort,
            "budget": budget,
            "research": research,
            "localFiles": local_files,
            "githubTools": github_tools,
            "dynamicSpinup": dynamic_spinup,
            "vetting": vetting,
            "pricingSource": PRICING_SOURCE,
            "pricingCheckedAt": PRICING_CHECKED_AT,
            "pricingSources": PRICING_SOURCES,
            "pricingAccuracy": PRICING_ACCURACY,
            "pricingNote": PRICING_NOTE,
        },
        "summarizer": {
            "id": "summarizer",
            "label": "Summarizer",
            "model": summarizer_model,
            "harness": normalize_harness_config(
                summarizer_harness_input if isinstance(summarizer_harness_input, dict) else {},
                default_summarizer_harness()["concision"],
            ),
        },
        "syncPolicy": {
            "mode": "checkpoint",
            "shareOnBlocker": True,
            "shareEverySteps": 3,
        },
        "preferredLoop": preferred_loop,
        "workers": workers,
    }

    def mutate(current: Dict[str, Any]) -> Dict[str, Any]:
        next_state = dict(current)
        next_state["activeTask"] = task
        next_state["draft"] = build_draft_from_task(task)
        next_state["commander"] = None
        next_state["commanderReview"] = None
        next_state["workers"] = _empty_worker_state_map(task_workers(task))
        next_state["summary"] = None
        next_state["memoryVersion"] = int(current.get("memoryVersion") or 0) + 1
        next_state["usage"] = storage.default_usage_state()
        next_state["loop"] = storage.default_loop_state()
        return next_state

    with runtime.with_lock():
        state = runtime.read_state_unlocked()
        next_state = mutate(state)
        runtime.write_state_unlocked(next_state)
        _write_task_snapshot_unlocked(runtime, task)

    runtime.append_event("task_started", {"taskId": task_id, "objective": objective})
    runtime.append_step(
        "task",
        "Created a new task and reset worker memory.",
        {
            "taskId": task_id,
            "constraintCount": len(task["constraints"]),
            "hasSessionContext": session_context != "",
            "runtime": task["runtime"],
            "preferredLoop": preferred_loop,
            "syncPolicy": task["syncPolicy"],
            "workerCount": len(workers),
            "summarizerModel": summarizer_model,
        },
    )

    return {"message": "Task created.", "taskId": task_id}
