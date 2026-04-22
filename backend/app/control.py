from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from runtime.engine import (
    DEFAULT_MODEL_ID,
    DEFAULT_PROVIDER_ID,
    LoopRuntime,
    RuntimeErrorWithCode,
    coerce_bool,
    default_budget_config,
    default_model_for_provider,
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
    normalize_provider_id,
    normalize_research_config,
    normalize_string_list,
    normalize_vetting_config,
    provider_capability_profile,
    task_workers,
    worker_catalog,
)

from .config import deployment_topology
from .secrets import (
    auth_key_file_path,
    auth_key_provider_ids,
    auth_key_provider_label,
    env_secret_status,
    external_secret_status,
    normalize_auth_key_pool,
    normalize_auth_key_provider,
)
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
    provider = DEFAULT_PROVIDER_ID
    loop = default_loop_preferences()
    local_files = default_local_file_tool_config()
    github_tools = default_github_tool_config()
    dynamic_spinup = default_dynamic_spinup_config()
    return {
        "objective": "",
        "constraints": [],
        "sessionContext": "",
        "executionMode": "live",
        "provider": provider,
        "model": model,
        "summarizerProvider": provider,
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
        "workers": worker_catalog(model, provider)[:2],
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
    provider = normalize_provider_id(str(current.get("provider", default["provider"])), str(default["provider"]))
    model = normalize_model_id(
        str(current.get("model", default["model"])),
        default_model_for_provider(provider),
        provider,
    )
    summarizer_provider = normalize_provider_id(
        str(current.get("summarizerProvider", current.get("provider", default["summarizerProvider"]))),
        provider,
    )
    summarizer_model = normalize_model_id(
        str(current.get("summarizerModel", default["summarizerModel"])),
        default_model_for_provider(summarizer_provider),
        summarizer_provider,
    )
    feature_alignment = align_provider_runtime_features(
        provider,
        {
            "enabled": current.get("researchEnabled", default["researchEnabled"]),
            "externalWebAccess": current.get("researchExternalWebAccess", default["researchExternalWebAccess"]),
            "domains": current.get("researchDomains", default["researchDomains"]),
        },
        local_files,
        github_tools,
    )
    return {
        "objective": str(current.get("objective", default["objective"])).strip(),
        "constraints": list(normalize_string_list(current.get("constraints", default["constraints"]))),
        "sessionContext": str(current.get("sessionContext", default["sessionContext"])).strip(),
        "executionMode": execution_mode,
        "provider": provider,
        "model": model,
        "summarizerProvider": summarizer_provider,
        "summarizerModel": summarizer_model,
        "reasoningEffort": reasoning_effort,
        "maxTotalTokens": budget["maxTotalTokens"],
        "maxCostUsd": budget["maxCostUsd"],
        "maxOutputTokens": budget["maxOutputTokens"],
        "budgetTargets": budget["targets"],
        "researchEnabled": feature_alignment["research"]["enabled"],
        "researchExternalWebAccess": feature_alignment["research"]["externalWebAccess"],
        "researchDomains": feature_alignment["research"]["domains"],
        "localFilesEnabled": feature_alignment["localFiles"]["enabled"],
        "localFileRoots": feature_alignment["localFiles"]["roots"],
        "githubToolsEnabled": feature_alignment["githubTools"]["enabled"],
        "githubAllowedRepos": feature_alignment["githubTools"]["repos"],
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
                "runtime": {"provider": provider, "model": model},
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
    provider = normalize_provider_id(str(runtime.get("provider", default["provider"])), str(default["provider"]))
    model = normalize_model_id(str(runtime.get("model", default["model"])), default_model_for_provider(provider), provider)
    summarizer = task.get("summarizer") if isinstance(task.get("summarizer"), dict) else {}
    summarizer_provider = normalize_provider_id(str(summarizer.get("provider", provider)), provider)
    loop_prefs = normalize_loop_preferences(task.get("preferredLoop") if isinstance(task.get("preferredLoop"), dict) else {})

    draft = {
        "objective": str(task.get("objective", default["objective"])).strip(),
        "constraints": list(normalize_string_list(task.get("constraints", default["constraints"]))),
        "sessionContext": str(task.get("sessionContext", default["sessionContext"])).strip(),
        "executionMode": str(runtime.get("executionMode", default["executionMode"])).strip(),
        "provider": provider,
        "model": model,
        "summarizerProvider": summarizer_provider,
        "summarizerModel": normalize_model_id(
            str(summarizer.get("model", default["summarizerModel"])),
            default_model_for_provider(summarizer_provider),
            summarizer_provider,
        ),
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


def provider_auth_file_path(root: Optional[Path] = None, provider: Any = "openai") -> Path:
    return auth_key_file_path(auth_file_path(root), provider)


def read_auth_key_pool(root: Optional[Path] = None, provider: Any = "openai") -> list[str]:
    return auth_key_pool_state(root, provider)["keys"]


def auth_key_pool_state(root: Optional[Path] = None, provider: Any = "openai") -> Dict[str, Any]:
    normalized_provider = normalize_auth_key_provider(provider)
    label = auth_key_provider_label(normalized_provider)
    topology = deployment_topology(root)
    if topology.secret_backend == "env":
        status = env_secret_status(normalized_provider)
        return {
            "backend": "env",
            "provider": normalized_provider,
            "label": label,
            "keys": normalize_auth_key_pool(status.get("keys", [])),
            "configured": bool(status.get("configured")),
            "ready": bool(status.get("ready")),
            "failureMode": status.get("failureMode"),
            "failureDetail": str(status.get("detail") or ""),
            "managed": True,
            "writable": False,
        }
    if topology.secret_backend == "external":
        status = external_secret_status(root, provider=normalized_provider)
        return {
            "backend": "external",
            "provider": normalized_provider,
            "label": label,
            "keys": normalize_auth_key_pool(status.get("keys", [])),
            "configured": bool(status.get("configured")),
            "ready": bool(status.get("ready")),
            "failureMode": status.get("failureMode"),
            "failureDetail": str(status.get("detail") or ""),
            "managed": True,
            "writable": False,
        }
    if topology.secret_backend == "docker_secret":
        secret_path = provider_auth_file_path(root, normalized_provider)
        if not secret_path.is_file():
            return {
                "backend": "docker_secret",
                "provider": normalized_provider,
                "label": label,
                "keys": [],
                "configured": bool(secret_path),
                "ready": False,
                "failureMode": "misconfigured",
                "failureDetail": f"Mounted {label} secret file not found at {secret_path}.",
                "managed": True,
                "writable": False,
            }
        keys = normalize_auth_key_pool(secret_path.read_text(encoding="utf-8", errors="replace"))
        return {
            "backend": "docker_secret",
            "provider": normalized_provider,
            "label": label,
            "keys": keys,
            "configured": True,
            "ready": len(keys) > 0,
            "failureMode": None if keys else "empty",
            "failureDetail": f"Using mounted {label} secret file at {secret_path}." if keys else f"Mounted {label} secret file at {secret_path} is empty.",
            "managed": True,
            "writable": False,
        }
    path = provider_auth_file_path(root, normalized_provider)
    if not path.is_file():
        return {
            "backend": "local_file",
            "provider": normalized_provider,
            "label": label,
            "keys": [],
            "configured": True,
            "ready": False,
            "failureMode": "empty",
            "failureDetail": f"Local fallback {label} secret file not found at {path}.",
            "managed": False,
            "writable": True,
        }
    keys = normalize_auth_key_pool(path.read_text(encoding="utf-8", errors="replace"))
    return {
        "backend": "local_file",
        "provider": normalized_provider,
        "label": label,
        "keys": keys,
        "configured": True,
        "ready": len(keys) > 0,
        "failureMode": None if keys else "empty",
        "failureDetail": f"Using local fallback {label} secret file at {path}." if keys else f"Local fallback {label} secret file at {path} is empty.",
        "managed": False,
        "writable": True,
    }


def mask_auth_key(key: str) -> str:
    last4 = key[-4:] if len(key) >= 4 else key
    return "*" * max(4, len(key) - len(last4)) + last4


def preferred_secret_backends(topology=None) -> list[str]:
    current = topology or deployment_topology()
    if current.profile in {"hosted-single-node", "hosted-distributed"}:
        return ["docker_secret", "external"]
    return ["env", "external"]


def recommended_secret_backend(topology=None) -> str:
    current = topology or deployment_topology()
    return "docker_secret" if current.profile in {"hosted-single-node", "hosted-distributed"} else "env"


def secret_rotation_policy(backend: str, topology=None) -> Dict[str, Any]:
    current = topology or deployment_topology()
    backend_name = str(backend or "").strip().lower()
    base = {
        "immediateOnExposure": True,
        "recommendedDays": 30,
        "hostedApproved": backend_name in {"docker_secret", "external"},
    }
    if backend_name == "local_file":
        return {
            **base,
            "recommendedDays": 7,
            "hostedApproved": False,
            "summary": "Transitional local-file fallback only. Rotate quickly and move to env, docker_secret, or external before hosted use.",
        }
    if backend_name == "env":
        return {
            **base,
            "hostedApproved": current.profile == "local-single-node",
            "summary": "Preferred for local development when keys are injected outside the workspace.",
        }
    if backend_name == "docker_secret":
        return {
            **base,
            "summary": "Preferred for Docker and self-hosted deployments through mounted read-only secret files.",
        }
    if backend_name == "external":
        return {
            **base,
            "summary": "Preferred for hosted deployments behind a managed secret provider.",
        }
    return {
        **base,
        "summary": "Secret rotation should be explicit, regular, and immediate on exposure.",
    }


def secret_backend_status_note(topology=None) -> str:
    current = topology or deployment_topology()
    backend = current.secret_backend
    if backend == "local_file":
        return "Transitional local-file fallback only. Provider pools stay isolated by file. Prefer env for local work and docker_secret or external for hosted use."
    if backend == "env":
        return "Using environment-injected provider key groups. This is the preferred local path."
    if backend == "docker_secret":
        return "Using mounted Docker secrets with provider-isolated key files. This is the preferred hosted/self-host path."
    if backend == "external":
        return "Using an external read-only secret provider with provider-isolated key groups."
    return "Using a custom secret backend."


def auth_pool_status(root: Optional[Path] = None) -> Dict[str, Any]:
    topology = deployment_topology(root)
    provider_groups: Dict[str, Any] = {}
    total_keys = 0
    has_any_key = False
    writable = False
    for provider_id in auth_key_provider_ids():
        pool_state = auth_key_pool_state(root, provider_id)
        keys = pool_state["keys"]
        masks = [mask_auth_key(key) for key in keys]
        first = keys[0] if keys else ""
        last4 = first[-4:] if len(first) >= 4 else first
        provider_groups[provider_id] = {
            "provider": provider_id,
            "label": auth_key_provider_label(provider_id),
            "hasKey": len(keys) > 0,
            "keyCount": len(keys),
            "last4": last4,
            "masked": masks[0] if masks else None,
            "masks": masks,
            "available": len(keys) > 0,
            "managed": bool(pool_state.get("managed")),
            "writable": bool(pool_state.get("writable")),
            "failureMode": pool_state.get("failureMode"),
            "failureDetail": pool_state.get("failureDetail"),
            "strictLiveFailure": bool(pool_state.get("managed")) and len(keys) == 0,
        }
        total_keys += len(keys)
        has_any_key = has_any_key or len(keys) > 0
        writable = writable or bool(pool_state.get("writable"))
    failure_mode = None
    failure_detail = ""
    strict_live_failure = topology.secret_backend in {"env", "docker_secret", "external"} and not has_any_key
    if not has_any_key:
        failure_modes = [
            str(group.get("failureMode") or "").strip()
            for group in provider_groups.values()
            if str(group.get("failureMode") or "").strip()
        ]
        for candidate in ("unreachable", "misconfigured", "empty"):
            if candidate in failure_modes:
                failure_mode = candidate
                break
        if failure_mode is None and failure_modes:
            failure_mode = failure_modes[0]
        labels = [str(group.get("label") or group.get("provider") or "").strip() for group in provider_groups.values()]
        checked_labels = ", ".join([label for label in labels if label]) or "provider groups"
        matching_detail = next(
            (
                str(group.get("failureDetail") or "").strip()
                for group in provider_groups.values()
                if str(group.get("failureMode") or "").strip() == str(failure_mode or "").strip()
                and str(group.get("failureDetail") or "").strip()
            ),
            "",
        )
        fallback_detail = next(
            (str(group.get("failureDetail") or "").strip() for group in provider_groups.values() if str(group.get("failureDetail") or "").strip()),
            "",
        )
        detail_source = matching_detail or fallback_detail
        failure_detail = f"No provider key groups are ready via the {topology.secret_backend} secret backend. Checked {checked_labels}."
        if detail_source:
            failure_detail = f"{failure_detail} {detail_source}"
    preferred_backends = preferred_secret_backends(topology)
    rotation_policy = secret_rotation_policy(topology.secret_backend, topology)
    return {
        "backend": topology.secret_backend,
        "hasKey": has_any_key,
        "keyCount": total_keys,
        "writable": writable,
        "available": has_any_key,
        "failureMode": failure_mode,
        "failureDetail": failure_detail,
        "strictLiveFailure": strict_live_failure,
        "providerOrder": auth_key_provider_ids(),
        "providerGroups": provider_groups,
        "preferred": topology.secret_backend in preferred_backends,
        "preferredBackends": preferred_backends,
        "recommendedBackend": recommended_secret_backend(topology),
        "deprecated": topology.secret_backend == "local_file",
        "statusNote": secret_backend_status_note(topology),
        "rotationPolicy": rotation_policy,
        "isolationNote": "Provider pools stay isolated. OpenAI lanes never reuse Anthropic, xAI, or MiniMax keys.",
        "termsWarning": "Cross-vendor orchestration can implicate provider ToS or acceptable-use rules. Review each vendor's terms before mixing providers in one workflow.",
    }


def align_provider_runtime_features(
    provider: Any,
    research: Optional[Dict[str, Any]] = None,
    local_files: Optional[Dict[str, Any]] = None,
    github_tools: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_provider = normalize_provider_id(str(provider or DEFAULT_PROVIDER_ID), DEFAULT_PROVIDER_ID)
    capabilities = provider_capability_profile(normalized_provider)
    normalized_research = normalize_research_config(research if isinstance(research, dict) else {})
    normalized_local_files = normalize_local_file_tool_config(local_files if isinstance(local_files, dict) else {})
    normalized_github_tools = normalize_github_tool_config(github_tools if isinstance(github_tools, dict) else {})
    disabled: list[str] = []

    if not capabilities["webSearch"] and normalized_research["enabled"]:
        normalized_research = {**normalized_research, "enabled": False}
        disabled.append("research")
    if not capabilities["localFiles"] and normalized_local_files["enabled"]:
        normalized_local_files = {**normalized_local_files, "enabled": False}
        disabled.append("localFiles")
    if not capabilities["githubTools"] and normalized_github_tools["enabled"]:
        normalized_github_tools = {**normalized_github_tools, "enabled": False}
        disabled.append("githubTools")

    return {
        "provider": normalized_provider,
        "capabilities": capabilities,
        "research": normalized_research,
        "localFiles": normalized_local_files,
        "githubTools": normalized_github_tools,
        "disabled": disabled,
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
            "provider": payload.get("provider", existing_draft["provider"]),
            "model": payload.get("model", existing_draft["model"]),
            "summarizerProvider": payload.get("summarizerProvider", existing_draft["summarizerProvider"]),
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
    provider = normalize_provider_id(str(payload.get("provider", DEFAULT_PROVIDER_ID)), DEFAULT_PROVIDER_ID)
    model = normalize_model_id(str(payload.get("model", default_model_for_provider(provider))), default_model_for_provider(provider), provider)
    summarizer_provider = normalize_provider_id(str(payload.get("summarizerProvider", provider)), provider)
    summarizer_model = normalize_model_id(
        str(payload.get("summarizerModel", default_model_for_provider(summarizer_provider))),
        default_model_for_provider(summarizer_provider),
        summarizer_provider,
    )
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
    feature_alignment = align_provider_runtime_features(provider, research, local_files, github_tools)
    research = feature_alignment["research"]
    local_files = feature_alignment["localFiles"]
    github_tools = feature_alignment["githubTools"]
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
            "runtime": {"provider": provider, "model": model},
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
            "provider": provider,
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
            "provider": summarizer_provider,
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
