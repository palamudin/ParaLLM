from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from runtime.engine import (
    DEFAULT_MODEL_ID,
    LoopRuntime,
    RuntimeErrorWithCode,
    coerce_bool,
    normalize_budget_config,
    normalize_dynamic_spinup_config,
    normalize_github_tool_config,
    normalize_model_id,
    normalize_research_config,
    normalize_vetting_config,
    normalize_worker_definition,
    summarizer_config,
    task_workers,
    worker_slot_ids,
)

from . import control, jobs, storage


def utc_now() -> str:
    return control.utc_now()


def _runtime(root: Optional[Path] = None) -> LoopRuntime:
    return LoopRuntime(Path(root).resolve() if root else Path(__file__).resolve().parents[2])


def write_auth_key_pool(keys: list[str], root: Optional[Path] = None) -> None:
    auth_path = control.auth_file_path(root)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = control.normalize_auth_key_pool(keys)
    payload = "\n".join(normalized) + ("\n" if normalized else "")
    auth_path.write_text(payload, encoding="utf-8")


def set_auth_keys(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    auth_status = control.auth_pool_status(runtime.root)
    if not bool(auth_status.get("writable")):
        raise RuntimeErrorWithCode(
            f"API key mutation is disabled because the active secret backend is {auth_status.get('backend')}.",
            409,
        )
    auth_path = control.auth_file_path(runtime.root)
    clear = coerce_bool(payload.get("clear"), False)
    append_key = str(payload.get("appendKey") or "").strip()
    api_key = str(payload.get("apiKey") or "").strip()
    replace_index = payload.get("replaceIndex")
    remove_index = payload.get("removeIndex")
    api_keys = control.normalize_auth_key_pool(payload.get("apiKeys", payload.get("apiKey", "")))

    if clear:
        write_auth_key_pool([], runtime.root)
        runtime.append_step("auth", "Cleared the local API key pool file.", {})
        return {"ok": True, "message": "Stored API key pool cleared.", **control.auth_pool_status(runtime.root)}

    if append_key:
        pool = control.read_auth_key_pool(runtime.root)
        pool.append(append_key)
        write_auth_key_pool(pool, runtime.root)
        runtime.append_step("auth", "Appended one API key into the local key pool.", {"keyCount": len(control.read_auth_key_pool(runtime.root))})
        return {
            "ok": True,
            "message": f"Stored {len(control.read_auth_key_pool(runtime.root))} API keys.",
            **control.auth_pool_status(runtime.root),
        }

    if replace_index is not None and api_key:
        index = int(replace_index) if str(replace_index).strip().lstrip("-").isdigit() else -1
        pool = control.read_auth_key_pool(runtime.root)
        if index < 0 or index >= len(pool):
            raise RuntimeErrorWithCode("Key slot is out of range.", 400)
        pool[index] = api_key
        write_auth_key_pool(pool, runtime.root)
        runtime.append_step("auth", "Replaced one API key in the local key pool.", {"slot": index + 1, "keyCount": len(control.read_auth_key_pool(runtime.root))})
        return {
            "ok": True,
            "message": f"Updated key slot {index + 1}.",
            **control.auth_pool_status(runtime.root),
        }

    if remove_index is not None:
        index = int(remove_index) if str(remove_index).strip().lstrip("-").isdigit() else -1
        pool = control.read_auth_key_pool(runtime.root)
        if index < 0 or index >= len(pool):
            raise RuntimeErrorWithCode("Key slot is out of range.", 400)
        del pool[index]
        write_auth_key_pool(pool, runtime.root)
        runtime.append_step("auth", "Removed one API key from the local key pool.", {"slot": index + 1, "keyCount": len(control.read_auth_key_pool(runtime.root))})
        return {
            "ok": True,
            "message": f"Stored {len(pool)} API keys." if pool else "Stored API key pool cleared.",
            **control.auth_pool_status(runtime.root),
        }

    if not api_keys:
        raise RuntimeErrorWithCode("At least one API key is required.", 400)

    write_auth_key_pool(api_keys, runtime.root)
    runtime.append_step("auth", "Updated the local API key pool file.", {"keyCount": len(control.read_auth_key_pool(runtime.root))})
    count = len(control.read_auth_key_pool(runtime.root))
    return {
        "ok": True,
        "message": "Stored 1 API key." if count == 1 else f"Stored {count} API keys.",
        **control.auth_pool_status(runtime.root),
    }


def apply_runtime_settings(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    state = storage.read_state_payload(storage.project_paths(runtime.root))
    if not isinstance(state.get("activeTask"), dict):
        raise RuntimeErrorWithCode("No active task. Start one first.", 400)
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("The autonomous loop is active. Cancel it before changing runtime settings.", 409)

    active_task = state["activeTask"]
    runtime_config = active_task.get("runtime") if isinstance(active_task.get("runtime"), dict) else {}
    current_budget = normalize_budget_config(runtime_config.get("budget") if isinstance(runtime_config.get("budget"), dict) else {})
    current_research = normalize_research_config(runtime_config.get("research") if isinstance(runtime_config.get("research"), dict) else {})
    current_local_files = control.normalize_local_file_tool_config(runtime_config.get("localFiles") if isinstance(runtime_config.get("localFiles"), dict) else {})
    current_github_tools = control.normalize_github_tool_config(runtime_config.get("githubTools") if isinstance(runtime_config.get("githubTools"), dict) else {})
    current_dynamic_spinup = normalize_dynamic_spinup_config(runtime_config.get("dynamicSpinup") if isinstance(runtime_config.get("dynamicSpinup"), dict) else {})
    current_vetting = normalize_vetting_config(runtime_config.get("vetting") if isinstance(runtime_config.get("vetting"), dict) else {})
    current_loop = control.normalize_loop_preferences(active_task.get("preferredLoop") if isinstance(active_task.get("preferredLoop"), dict) else {})
    current_reasoning_effort = str(runtime_config.get("reasoningEffort") or "low").strip()
    if current_reasoning_effort not in {"none", "low", "medium", "high", "xhigh"}:
        current_reasoning_effort = "low"

    model = normalize_model_id(str(payload.get("model") or DEFAULT_MODEL_ID), DEFAULT_MODEL_ID)
    summarizer_model = normalize_model_id(str(payload.get("summarizerModel") or model), model)
    reasoning_effort = str(payload.get("reasoningEffort", current_reasoning_effort)).strip()
    if reasoning_effort not in {"none", "low", "medium", "high", "xhigh"}:
        reasoning_effort = current_reasoning_effort

    budget = normalize_budget_config(
        {
            "maxTotalTokens": payload.get("maxTotalTokens", current_budget["maxTotalTokens"]),
            "maxCostUsd": payload.get("maxCostUsd", current_budget["maxCostUsd"]),
            "maxOutputTokens": payload.get("maxOutputTokens", current_budget["maxOutputTokens"]),
            "targets": payload.get("budgetTargets", current_budget["targets"]),
        }
    )
    preferred_loop = control.normalize_loop_preferences(
        {
            "rounds": payload.get("loopRounds", current_loop["rounds"]),
            "delayMs": payload.get("loopDelayMs", current_loop["delayMs"]),
        }
    )
    research = normalize_research_config(
        {
            "enabled": payload.get("researchEnabled", current_research["enabled"]),
            "externalWebAccess": payload.get("researchExternalWebAccess", current_research["externalWebAccess"]),
            "domains": payload.get("researchDomains", current_research["domains"]),
        }
    )
    local_files = control.normalize_local_file_tool_config(
        {
            "enabled": payload.get("localFilesEnabled", current_local_files["enabled"]),
            "roots": payload.get("localFileRoots", current_local_files["roots"]),
        }
    )
    github_tools = control.normalize_github_tool_config(
        {
            "enabled": payload.get("githubToolsEnabled", current_github_tools["enabled"]),
            "repos": payload.get("githubAllowedRepos", current_github_tools["repos"]),
        }
    )
    dynamic_spinup = normalize_dynamic_spinup_config(
        {"enabled": payload.get("dynamicSpinupEnabled", current_dynamic_spinup["enabled"])}
    )
    vetting = normalize_vetting_config(
        {"enabled": payload.get("vettingEnabled", current_vetting["enabled"])}
    )

    def mutate(current: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(current.get("activeTask"), dict):
            raise RuntimeErrorWithCode("No active task.", 400)
        state_next = dict(current)
        task = dict(state_next["activeTask"])
        workers = task_workers(task)
        for worker in workers:
            worker["model"] = model
        task["workers"] = workers
        task_runtime = dict(task.get("runtime") if isinstance(task.get("runtime"), dict) else {})
        task_runtime["model"] = model
        task_runtime["reasoningEffort"] = reasoning_effort
        task_runtime["budget"] = budget
        task_runtime["research"] = research
        task_runtime["localFiles"] = local_files
        task_runtime["githubTools"] = github_tools
        task_runtime["dynamicSpinup"] = dynamic_spinup
        task_runtime["vetting"] = vetting
        task["runtime"] = task_runtime
        task["preferredLoop"] = preferred_loop
        summary = summarizer_config(task)
        summary["model"] = summarizer_model
        task["summarizer"] = summary
        state_next["activeTask"] = task
        state_next["draft"] = control.build_draft_from_task(task)
        return state_next

    updated_state = runtime.mutate_state(mutate)
    control._write_task_snapshot_unlocked(runtime, updated_state["activeTask"])
    runtime.append_step(
        "model",
        "Applied settings runtime and loop selection to the active task.",
        {
            "taskId": updated_state["activeTask"].get("taskId"),
            "workerModel": model,
            "summarizerModel": summarizer_model,
            "reasoningEffort": reasoning_effort,
            "budget": budget,
            "research": research,
            "localFiles": local_files,
            "githubTools": github_tools,
            "dynamicSpinup": dynamic_spinup,
            "vetting": vetting,
            "preferredLoop": preferred_loop,
            "workerCount": len(task_workers(updated_state["activeTask"])),
        },
    )
    return {
        "message": "Applied runtime settings to the active task.",
        "workerModel": model,
        "summarizerModel": summarizer_model,
        "reasoningEffort": reasoning_effort,
        "budget": budget,
        "research": research,
        "localFiles": local_files,
        "githubTools": github_tools,
        "dynamicSpinup": dynamic_spinup,
        "vetting": vetting,
        "preferredLoop": preferred_loop,
    }


def update_worker_config(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    state = storage.read_state_payload(storage.project_paths(runtime.root))
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("The autonomous loop is active. Cancel it before changing worker settings.", 409)

    worker_id = str(payload.get("workerId") or "").strip().upper()
    if len(worker_id) != 1 or not worker_id.isalpha():
        raise RuntimeErrorWithCode("A valid workerId is required.", 400)

    worker_type = payload.get("type")
    temperature = payload.get("temperature")
    model = payload.get("model")
    if worker_type is None and temperature is None and model is None:
        raise RuntimeErrorWithCode("Provide at least one worker property to update.", 400)

    def mutate(current: Dict[str, Any]) -> Dict[str, Any]:
        draft = control.normalize_draft_state(current.get("draft") if isinstance(current.get("draft"), dict) else {})
        draft_workers = task_workers({"runtime": {"model": draft["model"]}, "workers": draft["workers"]})
        updated = []
        found = False
        for worker in draft_workers:
            if not isinstance(worker, dict) or str(worker.get("id") or "").upper() != worker_id:
                updated.append(worker)
                continue
            patch = {key: value for key, value in {"type": worker_type, "temperature": temperature, "model": model}.items() if value is not None}
            if worker_type is not None:
                patch["label"] = ""
                patch["role"] = ""
                patch["focus"] = ""
            updated.append(normalize_worker_definition({**worker, **patch}, draft["model"]))
            found = True
        if not found:
            raise RuntimeErrorWithCode("Unknown worker position.", 409)
        next_state = dict(current)
        draft["workers"] = task_workers({"runtime": {"model": draft["model"]}, "workers": updated})
        next_state["draft"] = draft
        return next_state

    updated_state = runtime.mutate_state(mutate)
    worker = next((candidate for candidate in updated_state["draft"]["workers"] if candidate.get("id") == worker_id), None)
    runtime.append_step(
        "worker_roster",
        "Updated worker configuration.",
        {
            "taskId": ((updated_state.get("activeTask") or {}) if isinstance(updated_state.get("activeTask"), dict) else {}).get("taskId"),
            "workerId": worker_id,
            "type": (worker or {}).get("type"),
            "temperature": (worker or {}).get("temperature"),
            "model": (worker or {}).get("model"),
        },
    )
    return {"message": "Worker updated.", "worker": worker, "draft": updated_state["draft"]}


def _next_adversarial_worker_definition(task: Dict[str, Any], requested_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    default_model = normalize_model_id(((task.get("runtime") or {}) if isinstance(task.get("runtime"), dict) else {}).get("model"), DEFAULT_MODEL_ID)
    existing_ids = {str(worker.get("id") or "") for worker in task_workers(task)}
    requested = str(requested_type or "").strip().lower()
    valid_types = {str(worker.get("type") or "").strip().lower() for worker in control.worker_catalog(default_model)}
    for worker_id in worker_slot_ids():
        if worker_id in existing_ids:
            continue
        definition: Dict[str, Any] = {"id": worker_id}
        if requested and requested in valid_types:
            definition["type"] = requested
            definition["label"] = ""
            definition["role"] = ""
            definition["focus"] = ""
        return normalize_worker_definition(definition, default_model)
    return None


def add_adversarial_worker(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    state = storage.read_state_payload(storage.project_paths(runtime.root))
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("The autonomous loop is active. Cancel it before changing the worker roster.", 409)

    requested_type = str(payload.get("type") or "").strip().lower() or None
    active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    draft = control.normalize_draft_state(state.get("draft") if isinstance(state.get("draft"), dict) else {})
    worker = _next_adversarial_worker_definition(active_task or draft, requested_type)
    if worker is None:
        raise RuntimeErrorWithCode("All available adversarial worker slots are already in use.", 409)

    def mutate(current: Dict[str, Any]) -> Dict[str, Any]:
        next_state = dict(current)
        next_draft = control.normalize_draft_state(current.get("draft") if isinstance(current.get("draft"), dict) else {})
        draft_workers = task_workers({"runtime": {"model": next_draft["model"]}, "workers": next_draft["workers"]})
        draft_workers.append(worker)
        next_draft["workers"] = task_workers({"runtime": {"model": next_draft["model"]}, "workers": draft_workers})
        next_state["draft"] = next_draft
        return next_state

    updated_state = runtime.mutate_state(mutate)
    runtime.append_step(
        "worker_roster",
        "Added a new adversarial worker slot.",
        {
            "taskId": ((updated_state.get("activeTask") or {}) if isinstance(updated_state.get("activeTask"), dict) else {}).get("taskId"),
            "workerId": worker["id"],
            "label": worker["label"],
            "type": worker.get("type"),
            "temperature": worker.get("temperature"),
            "model": worker.get("model"),
        },
    )
    return {"message": "Adversarial worker added.", "worker": worker}


def set_position_model(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    state = storage.read_state_payload(storage.project_paths(runtime.root))
    if not isinstance(state.get("activeTask"), dict):
        raise RuntimeErrorWithCode("No active task. Start one first.", 400)
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("The autonomous loop is active. Cancel it before changing models.", 409)

    position_id = str(payload.get("positionId") or "").strip()
    if not position_id:
        raise RuntimeErrorWithCode("positionId is required.", 400)
    model = normalize_model_id(str(payload.get("model") or DEFAULT_MODEL_ID), DEFAULT_MODEL_ID)

    def mutate(current: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(current.get("activeTask"), dict):
            raise RuntimeErrorWithCode("No active task.", 400)
        next_state = dict(current)
        task = dict(next_state["activeTask"])
        if position_id == "summarizer":
            summary = summarizer_config(task)
            summary["model"] = model
            task["summarizer"] = summary
            next_state["activeTask"] = task
            return next_state
        workers = task_workers(task)
        found = False
        for worker in workers:
            if str(worker.get("id") or "").upper() == position_id.upper():
                worker["model"] = model
                found = True
                break
        if not found:
            raise RuntimeErrorWithCode("Unknown worker position.", 409)
        task["workers"] = workers
        next_state["activeTask"] = task
        return next_state

    updated_state = runtime.mutate_state(mutate)
    control._write_task_snapshot_unlocked(runtime, updated_state["activeTask"])
    runtime.append_step(
        "model",
        "Updated the model selection for a task position.",
        {
            "taskId": updated_state["activeTask"].get("taskId"),
            "positionId": position_id,
            "model": model,
        },
    )
    return {"message": "Model updated.", "positionId": position_id, "model": model}
