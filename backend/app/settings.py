from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from runtime.engine import (
    DEFAULT_MODEL_ID,
    DEFAULT_PROVIDER_ID,
    LoopRuntime,
    RuntimeErrorWithCode,
    coerce_bool,
    compile_engine_graph,
    default_context_mode,
    default_engine_graph,
    default_engine_version,
    default_direct_baseline_mode,
    default_front_mode,
    default_model_for_provider,
    default_ollama_base_url,
    default_ollama_timeout_profile,
    default_provider_routing_config,
    default_timeout_mode,
    default_target_timeout_config,
    clamp_timeout_seconds,
    normalize_ollama_timeout_profile,
    normalize_timeout_mode,
    normalize_budget_config,
    normalize_context_mode,
    normalize_engine_graph,
    normalize_engine_version,
    normalize_direct_baseline_mode,
    normalize_dynamic_spinup_config,
    normalize_front_mode,
    normalize_github_tool_config,
    normalize_model_id,
    normalize_ollama_base_url,
    normalize_provider_id,
    normalize_provider_routing_config,
    normalize_provider_instance_catalog,
    normalize_research_config,
    normalize_target_timeout_config,
    normalize_vetting_config,
    provider_instance_pool_status,
    read_provider_instance_catalog,
    normalize_worker_definition,
    summarizer_config,
    task_workers,
    write_provider_instance_catalog,
    worker_slot_ids,
)

from . import control, jobs, storage
from .secrets import (
    auth_backend_mode_for_provider,
    auth_key_provider_label,
    normalize_auth_backend_mode,
    write_auth_backend_mode_override,
    write_local_auth_keys,
)


def utc_now() -> str:
    return control.utc_now()


def _runtime(root: Optional[Path] = None) -> LoopRuntime:
    return LoopRuntime(Path(root).resolve() if root else Path(__file__).resolve().parents[2])


def _sync_active_task_state(runtime: LoopRuntime, state: Dict[str, Any]) -> None:
    active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    if not isinstance(active_task, dict):
        return
    with runtime.with_lock():
        runtime.initialize_task_state_unlocked(active_task, state)


def write_auth_key_pool(keys: list[str], root: Optional[Path] = None, provider: Any = "openai") -> None:
    auth_path = control.local_auth_file_path(root)
    write_local_auth_keys(auth_path, provider, control.normalize_auth_key_pool(keys))


def set_auth_keys(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    provider = control.normalize_auth_key_provider(payload.get("provider", "openai"))
    auth_status = control.auth_pool_status(runtime.root)
    provider_group = ((auth_status.get("providerGroups") or {}) if isinstance(auth_status.get("providerGroups"), dict) else {}).get(provider) or {}
    if not bool(provider_group.get("writable")):
        raise RuntimeErrorWithCode(
            f"API key mutation is disabled for {auth_key_provider_label(provider)} because that provider group is in {str(provider_group.get('selectedModeLabel') or auth_backend_mode_for_provider(runtime.root, provider)).lower()} mode.",
            409,
        )
    provider_label = control.auth_key_provider_label(provider)
    clear = coerce_bool(payload.get("clear"), False)
    append_key = str(payload.get("appendKey") or "").strip()
    api_key = str(payload.get("apiKey") or "").strip()
    replace_index = payload.get("replaceIndex")
    remove_index = payload.get("removeIndex")
    api_keys = control.normalize_auth_key_pool(payload.get("apiKeys", payload.get("apiKey", "")))

    if clear:
        write_auth_key_pool([], runtime.root, provider)
        runtime.append_step("auth", f"Cleared the local {provider_label} API key pool file.", {"provider": provider})
        return {"ok": True, "message": f"Stored {provider_label} API key pool cleared.", **control.auth_pool_status(runtime.root)}

    if append_key:
        pool = control.read_auth_key_pool(runtime.root, provider)
        pool.append(append_key)
        write_auth_key_pool(pool, runtime.root, provider)
        runtime.append_step(
            "auth",
            f"Appended one {provider_label} API key into the local key pool.",
            {"provider": provider, "keyCount": len(control.read_auth_key_pool(runtime.root, provider))},
        )
        return {
            "ok": True,
            "message": f"Stored {len(control.read_auth_key_pool(runtime.root, provider))} {provider_label} API keys.",
            **control.auth_pool_status(runtime.root),
        }

    if replace_index is not None and api_key:
        index = int(replace_index) if str(replace_index).strip().lstrip("-").isdigit() else -1
        pool = control.read_auth_key_pool(runtime.root, provider)
        if index < 0 or index >= len(pool):
            raise RuntimeErrorWithCode("Key slot is out of range.", 400)
        pool[index] = api_key
        write_auth_key_pool(pool, runtime.root, provider)
        runtime.append_step(
            "auth",
            f"Replaced one {provider_label} API key in the local key pool.",
            {"provider": provider, "slot": index + 1, "keyCount": len(control.read_auth_key_pool(runtime.root, provider))},
        )
        return {
            "ok": True,
            "message": f"Updated {provider_label} key slot {index + 1}.",
            **control.auth_pool_status(runtime.root),
        }

    if remove_index is not None:
        index = int(remove_index) if str(remove_index).strip().lstrip("-").isdigit() else -1
        pool = control.read_auth_key_pool(runtime.root, provider)
        if index < 0 or index >= len(pool):
            raise RuntimeErrorWithCode("Key slot is out of range.", 400)
        del pool[index]
        write_auth_key_pool(pool, runtime.root, provider)
        runtime.append_step(
            "auth",
            f"Removed one {provider_label} API key from the local key pool.",
            {"provider": provider, "slot": index + 1, "keyCount": len(control.read_auth_key_pool(runtime.root, provider))},
        )
        return {
            "ok": True,
            "message": f"Stored {len(pool)} {provider_label} API keys." if pool else f"Stored {provider_label} API key pool cleared.",
            **control.auth_pool_status(runtime.root),
        }

    if not api_keys:
        raise RuntimeErrorWithCode("At least one API key is required.", 400)

    write_auth_key_pool(api_keys, runtime.root, provider)
    runtime.append_step(
        "auth",
        f"Updated the local {provider_label} API key pool file.",
        {"provider": provider, "keyCount": len(control.read_auth_key_pool(runtime.root, provider))},
    )
    count = len(control.read_auth_key_pool(runtime.root, provider))
    return {
        "ok": True,
        "message": f"Stored 1 {provider_label} API key." if count == 1 else f"Stored {count} {provider_label} API keys.",
        **control.auth_pool_status(runtime.root),
    }


def set_auth_backend_mode(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    provider = control.normalize_auth_key_provider(payload.get("provider", "openai"))
    requested_mode = normalize_auth_backend_mode(payload.get("mode"), auth_backend_mode_for_provider(runtime.root, provider))
    write_auth_backend_mode_override(runtime.root, provider, requested_mode)
    runtime.append_step(
        "auth",
        f"Set {auth_key_provider_label(provider)} credential mode to {requested_mode}.",
        {"provider": provider, "mode": requested_mode},
    )
    return {
        "ok": True,
        "message": f"{auth_key_provider_label(provider)} credential mode set to {requested_mode}.",
        **control.auth_pool_status(runtime.root),
    }


def get_provider_instance_status(root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    return provider_instance_pool_status(runtime.root)


def set_provider_instances(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    provider = normalize_provider_id(payload.get("provider"), DEFAULT_PROVIDER_ID)
    instances_input = control._parse_json_like(payload.get("instances"), [])
    if not isinstance(instances_input, list):
        raise RuntimeErrorWithCode("instances must be a list.", 400)
    catalog = read_provider_instance_catalog(runtime.root)
    catalog[provider] = instances_input
    saved_catalog = write_provider_instance_catalog(runtime.root, catalog)
    instances = normalize_provider_instance_catalog(saved_catalog).get(provider, [])
    runtime.append_step(
        "provider_pool",
        "Updated provider instance pool.",
        {
            "provider": provider,
            "instanceCount": len(instances),
            "instances": instances,
        },
    )
    return {
        "ok": True,
        "message": f"Updated {provider} provider instances.",
        "provider": provider,
        "instances": instances,
        "status": provider_instance_pool_status(runtime.root),
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

    current_provider = normalize_provider_id(str(runtime_config.get("provider") or DEFAULT_PROVIDER_ID), DEFAULT_PROVIDER_ID)
    current_summarizer_provider = normalize_provider_id(
        str((active_task.get("summarizer") or {}).get("provider") or current_provider),
        current_provider,
    )
    current_front_mode = normalize_front_mode(runtime_config.get("frontMode", default_front_mode()), default_front_mode())
    current_engine_version = normalize_engine_version(runtime_config.get("engineVersion", default_engine_version()), default_engine_version())
    current_engine_graph = normalize_engine_graph(runtime_config.get("engineGraph", default_engine_graph()))
    current_provider_routing = normalize_provider_routing_config(
        runtime_config.get("providerRouting") if isinstance(runtime_config.get("providerRouting"), dict) else default_provider_routing_config()
    )
    current_context_mode = normalize_context_mode(runtime_config.get("contextMode", default_context_mode()), default_context_mode())
    current_direct_baseline_mode = normalize_direct_baseline_mode(runtime_config.get("directBaselineMode", default_direct_baseline_mode()), default_direct_baseline_mode())
    current_direct_provider = normalize_provider_id(str(runtime_config.get("directProvider") or current_provider), current_provider)
    current_ollama_base_url = normalize_ollama_base_url(runtime_config.get("ollamaBaseUrl", default_ollama_base_url()))
    current_timeout_mode = normalize_timeout_mode(runtime_config.get("timeoutMode", default_timeout_mode()), default_timeout_mode())
    current_ollama_timeout_profile = normalize_ollama_timeout_profile(
        runtime_config.get("ollamaTimeoutProfile") if isinstance(runtime_config.get("ollamaTimeoutProfile"), dict) else default_ollama_timeout_profile()
    )
    current_target_timeouts = normalize_target_timeout_config(
        runtime_config.get("targetTimeouts") if isinstance(runtime_config.get("targetTimeouts"), dict) else default_target_timeout_config()
    )
    provider = normalize_provider_id(str(payload.get("provider") or current_provider), current_provider)
    summarizer_provider = normalize_provider_id(str(payload.get("summarizerProvider") or current_summarizer_provider), provider)
    model = normalize_model_id(
        str(payload.get("model") or default_model_for_provider(provider)),
        default_model_for_provider(provider),
        provider,
    )
    summarizer_model = normalize_model_id(
        str(payload.get("summarizerModel") or default_model_for_provider(summarizer_provider)),
        default_model_for_provider(summarizer_provider),
        summarizer_provider,
    )
    front_mode = normalize_front_mode(payload.get("frontMode", current_front_mode), current_front_mode)
    engine_version = normalize_engine_version(payload.get("engineVersion", current_engine_version), current_engine_version)
    engine_graph_input = control._parse_json_like(payload.get("engineGraph"), current_engine_graph)
    engine_graph = normalize_engine_graph(engine_graph_input if isinstance(engine_graph_input, dict) else current_engine_graph)
    provider_routing_input = control._parse_json_like(payload.get("providerRouting"), current_provider_routing)
    provider_routing = normalize_provider_routing_config(
        provider_routing_input if isinstance(provider_routing_input, dict) else current_provider_routing
    )
    context_mode = normalize_context_mode(payload.get("contextMode", current_context_mode), current_context_mode)
    direct_baseline_mode = normalize_direct_baseline_mode(payload.get("directBaselineMode", current_direct_baseline_mode), current_direct_baseline_mode)
    direct_provider = normalize_provider_id(str(payload.get("directProvider") or current_direct_provider), provider)
    direct_model = normalize_model_id(
        str(payload.get("directModel") or default_model_for_provider(direct_provider)),
        default_model_for_provider(direct_provider),
        direct_provider,
    )
    ollama_base_url = normalize_ollama_base_url(payload.get("ollamaBaseUrl", current_ollama_base_url))
    timeout_mode = normalize_timeout_mode(payload.get("timeoutMode", current_timeout_mode), current_timeout_mode)
    ollama_timeout_profile = normalize_ollama_timeout_profile(
        control._parse_json_like(payload.get("ollamaTimeoutProfile"), current_ollama_timeout_profile)
    )
    target_timeouts_input = control._parse_json_like(payload.get("targetTimeouts"), current_target_timeouts)
    target_timeouts = normalize_target_timeout_config(
        target_timeouts_input if isinstance(target_timeouts_input, dict) else current_target_timeouts
    )
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
    feature_alignment = control.align_provider_runtime_features(provider, research, local_files, github_tools)
    research = feature_alignment["research"]
    local_files = feature_alignment["localFiles"]
    github_tools = feature_alignment["githubTools"]
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
        task_runtime["provider"] = provider
        task_runtime["model"] = model
        task_runtime["frontMode"] = front_mode
        task_runtime["engineVersion"] = engine_version
        task_runtime["engineGraph"] = engine_graph
        task_runtime["providerRouting"] = provider_routing
        task_runtime["enginePlan"] = {}
        task_runtime["contextMode"] = context_mode
        task_runtime["directBaselineMode"] = direct_baseline_mode
        task_runtime["directProvider"] = direct_provider
        task_runtime["directModel"] = direct_model
        task_runtime["ollamaBaseUrl"] = ollama_base_url
        task_runtime["timeoutMode"] = timeout_mode
        task_runtime["ollamaTimeoutProfile"] = ollama_timeout_profile
        task_runtime["targetTimeouts"] = target_timeouts
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
        summary["provider"] = summarizer_provider
        summary["model"] = summarizer_model
        task["summarizer"] = summary
        task_runtime["enginePlan"] = compile_engine_graph(engine_graph, task=task, runtime_config=task_runtime)
        state_next["activeTask"] = task
        state_next["arbiter"] = None
        existing_draft = control.normalize_draft_state(
            current.get("draft") if isinstance(current.get("draft"), dict) else control.build_draft_from_task(task)
        )
        state_next["draft"] = control.normalize_draft_state(
            {
                **existing_draft,
                "provider": provider,
                "model": model,
                "summarizerProvider": summarizer_provider,
                "summarizerModel": summarizer_model,
                "frontMode": front_mode,
                "engineVersion": engine_version,
                "engineGraph": engine_graph,
                "providerRouting": provider_routing,
                "contextMode": context_mode,
                "directBaselineMode": direct_baseline_mode,
                "directProvider": direct_provider,
                "directModel": direct_model,
                "ollamaBaseUrl": ollama_base_url,
                "timeoutMode": timeout_mode,
                "ollamaTimeoutProfile": ollama_timeout_profile,
                "targetTimeouts": target_timeouts,
                "reasoningEffort": reasoning_effort,
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
                "loopRounds": preferred_loop["rounds"],
                "loopDelayMs": preferred_loop["delayMs"],
                "updatedAt": utc_now(),
            }
        )
        return state_next

    updated_state = runtime.mutate_state(mutate)
    control._write_task_snapshot_unlocked(runtime, updated_state["activeTask"])
    _sync_active_task_state(runtime, updated_state)
    runtime.append_step(
        "model",
        "Applied settings runtime and loop selection to the active task.",
        {
            "taskId": updated_state["activeTask"].get("taskId"),
            "workerModel": model,
            "summarizerModel": summarizer_model,
            "frontMode": front_mode,
            "engineVersion": engine_version,
            "engineGraph": engine_graph,
            "providerRouting": provider_routing,
            "enginePlan": ((updated_state["activeTask"].get("runtime") or {}) if isinstance(updated_state["activeTask"], dict) else {}).get("enginePlan"),
            "contextMode": context_mode,
            "directBaselineMode": direct_baseline_mode,
            "directProvider": direct_provider,
            "directModel": direct_model,
            "ollamaBaseUrl": ollama_base_url,
            "timeoutMode": timeout_mode,
            "ollamaTimeoutProfile": ollama_timeout_profile,
            "targetTimeouts": target_timeouts,
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
        "provider": provider,
        "workerModel": model,
        "summarizerProvider": summarizer_provider,
        "summarizerModel": summarizer_model,
        "frontMode": front_mode,
        "engineVersion": engine_version,
        "engineGraph": engine_graph,
        "providerRouting": provider_routing,
        "enginePlan": (updated_state["activeTask"].get("runtime") or {}).get("enginePlan"),
        "contextMode": context_mode,
        "directBaselineMode": direct_baseline_mode,
        "directProvider": direct_provider,
        "directModel": direct_model,
        "ollamaBaseUrl": ollama_base_url,
        "timeoutMode": timeout_mode,
        "ollamaTimeoutProfile": ollama_timeout_profile,
        "targetTimeouts": target_timeouts,
        "reasoningEffort": reasoning_effort,
        "budget": budget,
        "research": research,
        "localFiles": local_files,
        "githubTools": github_tools,
        "dynamicSpinup": dynamic_spinup,
        "vetting": vetting,
        "preferredLoop": preferred_loop,
    }


def _ollama_generate_url(base_url: str) -> str:
    normalized = normalize_ollama_base_url(base_url)
    lowered = normalized.rstrip("/").lower()
    if lowered.endswith("/api"):
        return normalized.rstrip("/") + "/generate"
    return normalized.rstrip("/") + "/api/generate"


def _build_task_from_draft(draft: Dict[str, Any]) -> Dict[str, Any]:
    normalized = control.normalize_draft_state(draft)
    provider = normalize_provider_id(normalized.get("provider"), DEFAULT_PROVIDER_ID)
    summarizer_provider = normalize_provider_id(normalized.get("summarizerProvider"), provider)
    return {
        "taskId": "draft-timeout-profile",
        "objective": str(normalized.get("objective") or "").strip(),
        "constraints": list(normalized.get("constraints") or []),
        "sessionContext": str(normalized.get("sessionContext") or "").strip(),
        "runtime": {
            "provider": provider,
            "model": normalize_model_id(normalized.get("model"), default_model_for_provider(provider), provider),
            "frontMode": normalize_front_mode(normalized.get("frontMode", default_front_mode()), default_front_mode()),
            "engineVersion": normalize_engine_version(normalized.get("engineVersion", default_engine_version()), default_engine_version()),
            "engineGraph": normalize_engine_graph(normalized.get("engineGraph", default_engine_graph())),
            "providerRouting": normalize_provider_routing_config(
                normalized.get("providerRouting", default_provider_routing_config())
            ),
            "contextMode": normalize_context_mode(normalized.get("contextMode", default_context_mode()), default_context_mode()),
            "directBaselineMode": normalize_direct_baseline_mode(normalized.get("directBaselineMode", default_direct_baseline_mode()), default_direct_baseline_mode()),
            "directProvider": normalize_provider_id(normalized.get("directProvider"), provider),
            "directModel": normalize_model_id(
                normalized.get("directModel"),
                default_model_for_provider(normalize_provider_id(normalized.get("directProvider"), provider)),
                normalize_provider_id(normalized.get("directProvider"), provider),
            ),
            "ollamaBaseUrl": normalize_ollama_base_url(normalized.get("ollamaBaseUrl", default_ollama_base_url())),
            "timeoutMode": normalize_timeout_mode(normalized.get("timeoutMode", default_timeout_mode()), default_timeout_mode()),
            "ollamaTimeoutProfile": normalize_ollama_timeout_profile(normalized.get("ollamaTimeoutProfile", default_ollama_timeout_profile())),
            "targetTimeouts": normalize_target_timeout_config(normalized.get("targetTimeouts", default_target_timeout_config())),
        },
        "summarizer": {
            "provider": summarizer_provider,
            "model": normalize_model_id(normalized.get("summarizerModel"), default_model_for_provider(summarizer_provider), summarizer_provider),
        },
        "workers": task_workers(
            {
                "runtime": {"provider": provider, "model": normalize_model_id(normalized.get("model"), default_model_for_provider(provider), provider)},
                "workers": normalized.get("workers", []),
            }
        ),
    }


def _ollama_timeout_benchmark_models(task: Dict[str, Any]) -> Dict[str, str]:
    runtime_config = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
    summarizer = task.get("summarizer") if isinstance(task.get("summarizer"), dict) else {}
    roles: Dict[str, str] = {}
    main_provider = normalize_provider_id(runtime_config.get("provider"), DEFAULT_PROVIDER_ID)
    if main_provider == "ollama":
        main_model = normalize_model_id(runtime_config.get("model"), default_model_for_provider("ollama"), "ollama")
        roles["commander"] = main_model
        roles["review"] = main_model
        for worker in task_workers(task):
            worker_id = str(worker.get("id") or "").strip().upper()
            if worker_id:
                roles[f"worker:{worker_id}"] = normalize_model_id(worker.get("model"), main_model, "ollama")
    summarizer_provider = normalize_provider_id(summarizer.get("provider"), main_provider)
    if summarizer_provider == "ollama":
        roles["summarizer"] = normalize_model_id(summarizer.get("model"), default_model_for_provider("ollama"), "ollama")
        roles["answer_now"] = roles["summarizer"]
    direct_mode = normalize_direct_baseline_mode(runtime_config.get("directBaselineMode", default_direct_baseline_mode()), default_direct_baseline_mode())
    direct_provider = normalize_provider_id(runtime_config.get("directProvider"), main_provider)
    if direct_mode != "off" and direct_provider == "ollama":
        roles["direct_baseline"] = normalize_model_id(runtime_config.get("directModel"), default_model_for_provider("ollama"), "ollama")
    return roles


def _benchmark_ollama_model(base_url: str, model: str) -> Dict[str, Any]:
    payload = {
        "model": model,
        "prompt": "Reply with READY only.",
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 8,
        },
    }
    request = urllib.request.Request(
        _ollama_generate_url(base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=900) as handle:
        response = json.loads(handle.read().decode("utf-8"))
    finished = time.perf_counter()
    total_duration_ns = float(response.get("total_duration") or 0.0)
    return {
        "wallSeconds": max(0.001, round(finished - started, 3)),
        "totalDurationMs": max(0.0, round(total_duration_ns / 1_000_000.0, 3)),
        "evalCount": max(0, int(response.get("eval_count") or 0)),
        "promptEvalCount": max(0, int(response.get("prompt_eval_count") or 0)),
    }


def _scaled_timeout(default_seconds: int, benchmark_seconds: float, factor: float, buffer_seconds: int) -> int:
    candidate = int(round((max(0.0, float(benchmark_seconds or 0.0)) * factor) + float(buffer_seconds)))
    return clamp_timeout_seconds(max(int(default_seconds), candidate), int(default_seconds))


def _derive_ollama_auto_target_timeouts(task: Dict[str, Any], model_metrics: Dict[str, Dict[str, Any]], roles: Dict[str, str]) -> Dict[str, Any]:
    defaults = default_target_timeout_config()

    def _seconds_for_model(model: str, fallback: float = 0.0) -> float:
        payload = model_metrics.get(str(model or "").strip()) if isinstance(model_metrics, dict) else None
        if not isinstance(payload, dict):
            return float(fallback)
        try:
            return max(0.0, float(payload.get("wallSeconds") or fallback))
        except (TypeError, ValueError):
            return float(fallback)

    main_seconds = max(
        [_seconds_for_model(model) for role, model in roles.items() if role in {"commander", "review"}] or [0.0]
    )
    summary_seconds = max(
        [_seconds_for_model(model, main_seconds) for role, model in roles.items() if role in {"summarizer", "answer_now"}] or [main_seconds]
    )
    direct_seconds = max(
        [_seconds_for_model(model, main_seconds) for role, model in roles.items() if role == "direct_baseline"] or [main_seconds]
    )

    worker_overrides: Dict[str, int] = {}
    for role, model in roles.items():
        if not role.startswith("worker:"):
            continue
        worker_id = role.split(":", 1)[1].strip().upper()
        worker_overrides[worker_id] = _scaled_timeout(defaults["workerDefault"], _seconds_for_model(model, main_seconds), 6.0, 60)

    return normalize_target_timeout_config(
        {
            "directBaseline": _scaled_timeout(defaults["directBaseline"], direct_seconds, 6.0, 60),
            "commander": _scaled_timeout(defaults["commander"], main_seconds, 6.0, 90),
            "workerDefault": _scaled_timeout(defaults["workerDefault"], max([_seconds_for_model(model, main_seconds) for role, model in roles.items() if role.startswith("worker:")] or [main_seconds]), 6.0, 60),
            "workers": worker_overrides,
            "commanderReview": _scaled_timeout(defaults["commanderReview"], main_seconds, 8.0, 120),
            "summarizer": _scaled_timeout(defaults["summarizer"], summary_seconds, 10.0, 120),
            "answerNow": _scaled_timeout(defaults["answerNow"], summary_seconds, 6.0, 60),
            "arbiter": defaults["arbiter"],
        }
    )


def benchmark_ollama_timeouts(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    state = storage.read_state_payload(storage.project_paths(runtime.root))
    active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    draft = control.normalize_draft_state(state.get("draft") if isinstance(state.get("draft"), dict) else {})
    task = active_task if isinstance(active_task, dict) else _build_task_from_draft(draft)
    runtime_config = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
    base_url = normalize_ollama_base_url(payload.get("ollamaBaseUrl", runtime_config.get("ollamaBaseUrl", default_ollama_base_url())))
    roles = _ollama_timeout_benchmark_models(task)
    unique_models = sorted({model for model in roles.values() if str(model).strip()})
    if not unique_models:
        raise RuntimeErrorWithCode("No Ollama-backed models are active for the current session.", 409)

    model_metrics: Dict[str, Dict[str, Any]] = {}
    for model in unique_models:
        try:
            model_metrics[model] = _benchmark_ollama_model(base_url, model)
        except urllib.error.URLError as exc:
            raise RuntimeErrorWithCode(f"Ollama benchmark failed for {model}: {exc}", 502) from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeErrorWithCode(f"Ollama benchmark failed for {model}: {exc}", 500) from exc

    derived_timeouts = _derive_ollama_auto_target_timeouts(task, model_metrics, roles)
    profile = normalize_ollama_timeout_profile(
        {
            "status": "ready",
            "measuredAt": utc_now(),
            "baseUrl": base_url,
            "models": model_metrics,
            "targetTimeouts": derived_timeouts,
            "note": f"Auto profile derived from {len(unique_models)} Ollama benchmark call(s).",
        }
    )

    def mutate(current: Dict[str, Any]) -> Dict[str, Any]:
        next_state = dict(current)
        current_draft = control.normalize_draft_state(next_state.get("draft") if isinstance(next_state.get("draft"), dict) else {})
        next_state["draft"] = control.normalize_draft_state(
            {
                **current_draft,
                "ollamaBaseUrl": base_url,
                "timeoutMode": "auto",
                "ollamaTimeoutProfile": profile,
                "updatedAt": utc_now(),
            }
        )
        if isinstance(next_state.get("activeTask"), dict):
            task_next = dict(next_state["activeTask"])
            task_runtime = dict(task_next.get("runtime") if isinstance(task_next.get("runtime"), dict) else {})
            task_runtime["ollamaBaseUrl"] = base_url
            task_runtime["timeoutMode"] = "auto"
            task_runtime["ollamaTimeoutProfile"] = profile
            task_next["runtime"] = task_runtime
            task_runtime["enginePlan"] = compile_engine_graph(
                normalize_engine_graph(task_runtime.get("engineGraph", default_engine_graph())),
                task=task_next,
                runtime_config=task_runtime,
            )
            next_state["activeTask"] = task_next
        return next_state

    updated_state = runtime.mutate_state(mutate)
    if isinstance(updated_state.get("activeTask"), dict):
        control._write_task_snapshot_unlocked(runtime, updated_state["activeTask"])
        _sync_active_task_state(runtime, updated_state)
    runtime.append_step(
        "model",
        "Benchmarked Ollama and derived an automatic timeout profile.",
        {
            "taskId": ((updated_state.get("activeTask") or {}) if isinstance(updated_state.get("activeTask"), dict) else {}).get("taskId"),
            "ollamaBaseUrl": base_url,
            "timeoutMode": "auto",
            "models": model_metrics,
            "targetTimeouts": derived_timeouts,
        },
    )
    return {
        "message": "Ollama timeout profile updated from live benchmark.",
        "timeoutMode": "auto",
        "ollamaBaseUrl": base_url,
        "ollamaTimeoutProfile": profile,
        "targetTimeouts": derived_timeouts,
        "benchmarkedModels": unique_models,
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
        draft_workers = task_workers({"runtime": {"provider": draft["provider"], "model": draft["model"]}, "workers": draft["workers"]})
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
            updated.append(normalize_worker_definition({**worker, **patch}, draft["model"], draft["provider"]))
            found = True
        if not found:
            raise RuntimeErrorWithCode("Unknown worker position.", 409)
        next_state = dict(current)
        draft["workers"] = task_workers({"runtime": {"provider": draft["provider"], "model": draft["model"]}, "workers": updated})
        next_state["draft"] = draft
        return next_state

    updated_state = runtime.mutate_state(mutate)
    _sync_active_task_state(runtime, updated_state)
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
    runtime_config = (task.get("runtime") or {}) if isinstance(task.get("runtime"), dict) else {}
    default_provider = normalize_provider_id(runtime_config.get("provider"), DEFAULT_PROVIDER_ID)
    default_model = normalize_model_id(
        runtime_config.get("model"),
        default_model_for_provider(default_provider),
        default_provider,
    )
    existing_ids = {str(worker.get("id") or "") for worker in task_workers(task)}
    requested = str(requested_type or "").strip().lower()
    valid_types = {str(worker.get("type") or "").strip().lower() for worker in control.worker_catalog(default_model, default_provider)}
    for worker_id in worker_slot_ids():
        if worker_id in existing_ids:
            continue
        definition: Dict[str, Any] = {"id": worker_id}
        if requested and requested in valid_types:
            definition["type"] = requested
            definition["label"] = ""
            definition["role"] = ""
            definition["focus"] = ""
        return normalize_worker_definition(definition, default_model, default_provider)
    return None


def add_adversarial_worker(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    state = storage.read_state_payload(storage.project_paths(runtime.root))
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("The autonomous loop is active. Cancel it before changing the worker roster.", 409)

    requested_type = str(payload.get("type") or "").strip().lower() or None
    draft = control.normalize_draft_state(state.get("draft") if isinstance(state.get("draft"), dict) else {})
    active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
    candidate_source = draft if draft.get("workers") else (active_task or draft)
    worker = _next_adversarial_worker_definition(candidate_source, requested_type)
    if worker is None:
        raise RuntimeErrorWithCode("All available adversarial worker slots are already in use.", 409)

    def mutate(current: Dict[str, Any]) -> Dict[str, Any]:
        next_state = dict(current)
        next_draft = control.normalize_draft_state(current.get("draft") if isinstance(current.get("draft"), dict) else {})
        draft_workers = task_workers({"runtime": {"provider": next_draft["provider"], "model": next_draft["model"]}, "workers": next_draft["workers"]})
        draft_workers.append(worker)
        next_draft["workers"] = task_workers({"runtime": {"provider": next_draft["provider"], "model": next_draft["model"]}, "workers": draft_workers})
        next_state["draft"] = next_draft
        return next_state

    updated_state = runtime.mutate_state(mutate)
    _sync_active_task_state(runtime, updated_state)
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


def remove_adversarial_worker(payload: Dict[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    runtime = _runtime(root)
    state = storage.read_state_payload(storage.project_paths(runtime.root))
    if jobs.loop_is_active(state):
        raise RuntimeErrorWithCode("The autonomous loop is active. Cancel it before changing the worker roster.", 409)

    draft = control.normalize_draft_state(state.get("draft") if isinstance(state.get("draft"), dict) else {})
    draft_workers = task_workers({"runtime": {"provider": draft["provider"], "model": draft["model"]}, "workers": draft["workers"]})
    if len(draft_workers) <= 2:
        raise RuntimeErrorWithCode("At least two adversarial workers must remain configured.", 409)

    removed_worker = dict(draft_workers[-1])

    def mutate(current: Dict[str, Any]) -> Dict[str, Any]:
        next_state = dict(current)
        next_draft = control.normalize_draft_state(current.get("draft") if isinstance(current.get("draft"), dict) else {})
        next_workers = task_workers({"runtime": {"provider": next_draft["provider"], "model": next_draft["model"]}, "workers": next_draft["workers"]})
        if len(next_workers) <= 2:
            raise RuntimeErrorWithCode("At least two adversarial workers must remain configured.", 409)
        next_workers = next_workers[:-1]
        next_draft["workers"] = task_workers({"runtime": {"provider": next_draft["provider"], "model": next_draft["model"]}, "workers": next_workers})
        next_state["draft"] = next_draft
        active_task = current.get("activeTask") if isinstance(current.get("activeTask"), dict) else None
        if active_task is not None:
            active_workers = task_workers(active_task)
            filtered_workers = [worker for worker in active_workers if str(worker.get("id") or "").upper() != str(removed_worker.get("id") or "").upper()]
            if len(filtered_workers) != len(active_workers):
                updated_task = dict(active_task)
                updated_task["workers"] = filtered_workers
                next_state["activeTask"] = updated_task
        return next_state

    updated_state = runtime.mutate_state(mutate)
    if isinstance(updated_state.get("activeTask"), dict):
        control._write_task_snapshot_unlocked(runtime, updated_state["activeTask"])
    _sync_active_task_state(runtime, updated_state)
    runtime.append_step(
        "worker_roster",
        "Removed the last adversarial worker slot.",
        {
            "taskId": ((updated_state.get("activeTask") or {}) if isinstance(updated_state.get("activeTask"), dict) else {}).get("taskId"),
            "workerId": removed_worker.get("id"),
            "label": removed_worker.get("label"),
            "type": removed_worker.get("type"),
            "temperature": removed_worker.get("temperature"),
            "model": removed_worker.get("model"),
        },
    )
    return {"message": "Adversarial worker removed.", "worker": removed_worker}


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
    active_task = state["activeTask"]
    runtime_config = active_task.get("runtime") if isinstance(active_task.get("runtime"), dict) else {}
    runtime_provider = normalize_provider_id(runtime_config.get("provider"), DEFAULT_PROVIDER_ID)
    active_summary = active_task.get("summarizer") if isinstance(active_task.get("summarizer"), dict) else {}
    summarizer_provider = normalize_provider_id(active_summary.get("provider"), runtime_provider)
    selected_provider = summarizer_provider if position_id == "summarizer" else runtime_provider
    model = normalize_model_id(
        str(payload.get("model") or default_model_for_provider(selected_provider)),
        default_model_for_provider(selected_provider),
        selected_provider,
    )

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
    _sync_active_task_state(runtime, updated_state)
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
