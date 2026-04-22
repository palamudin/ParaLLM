from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urlsplit, urlunsplit

from backend.app import artifacts as artifact_store
from backend.app import metadata as metadata_store
from backend.app.config import deployment_topology
from backend.app.secrets import env_secret_status, external_secret_status


MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "gpt-5.4": {"label": "GPT-5.4", "inputPer1M": 2.50, "cachedInputPer1M": 0.25, "outputPer1M": 15.00},
    "gpt-5.4-mini": {"label": "GPT-5.4 mini", "inputPer1M": 0.75, "cachedInputPer1M": 0.075, "outputPer1M": 4.50},
    "gpt-5.4-nano": {"label": "GPT-5.4 nano", "inputPer1M": 0.20, "cachedInputPer1M": 0.02, "outputPer1M": 1.25},
    "gpt-5.2": {"label": "GPT-5.2", "inputPer1M": 1.75, "cachedInputPer1M": 0.175, "outputPer1M": 14.00},
    "gpt-5.1": {"label": "GPT-5.1", "inputPer1M": 1.25, "cachedInputPer1M": 0.125, "outputPer1M": 10.00},
    "gpt-5": {"label": "GPT-5", "inputPer1M": 1.25, "cachedInputPer1M": 0.125, "outputPer1M": 10.00},
    "gpt-5-mini": {"label": "GPT-5 mini", "inputPer1M": 0.25, "cachedInputPer1M": 0.025, "outputPer1M": 2.00},
    "gpt-5-nano": {"label": "GPT-5 nano", "inputPer1M": 0.05, "cachedInputPer1M": 0.005, "outputPer1M": 0.40},
    "gpt-4.1": {"label": "GPT-4.1", "inputPer1M": 2.00, "cachedInputPer1M": 0.50, "outputPer1M": 8.00},
    "gpt-4.1-mini": {"label": "GPT-4.1 mini", "inputPer1M": 0.40, "cachedInputPer1M": 0.10, "outputPer1M": 1.60},
    "gpt-4.1-nano": {"label": "GPT-4.1 nano", "inputPer1M": 0.10, "cachedInputPer1M": 0.025, "outputPer1M": 0.40},
    "gpt-4o": {"label": "GPT-4o", "inputPer1M": 2.50, "cachedInputPer1M": 1.25, "outputPer1M": 10.00},
    "gpt-4o-mini": {"label": "GPT-4o mini", "inputPer1M": 0.15, "cachedInputPer1M": 0.075, "outputPer1M": 0.60},
}

PROVIDER_CATALOG: Dict[str, Dict[str, str]] = {
    "openai": {"label": "OpenAI"},
    "ollama": {"label": "Ollama"},
}

OLLAMA_MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "qwen3": {"label": "Qwen3"},
    "qwen3-coder": {"label": "Qwen3 Coder"},
    "gemma3": {"label": "Gemma 3"},
    "llama3.2": {"label": "Llama 3.2"},
}

WORKER_TEMPERATURE_CATALOG: Dict[str, Dict[str, str]] = {
    "cool": {"label": "Cool", "instruction": "deliberate, restrained, careful under pressure"},
    "balanced": {"label": "Balanced", "instruction": "practical, even-tempered, evidence-first"},
    "hot": {"label": "Hot", "instruction": "provocative, forceful, aggressively pressure-testing"},
}

HARNESS_CONCISION_CATALOG: Dict[str, Dict[str, str]] = {
    "tight": {"label": "Tight"},
    "balanced": {"label": "Balanced"},
    "expansive": {"label": "Expansive"},
}

WORKER_TYPE_CATALOG: Dict[str, Dict[str, str]] = {
    "proponent": {"label": "Proponent", "role": "utility", "focus": "benefits, feasibility, leverage, momentum, practical execution", "temperature": "balanced"},
    "sceptic": {"label": "Sceptic", "role": "adversarial", "focus": "failure modes, downside, hidden coupling, consequences, externalities", "temperature": "cool"},
    "economist": {"label": "Economist", "role": "adversarial", "focus": "cost ceilings, burn rate, return on effort, economic drag", "temperature": "cool"},
    "security": {"label": "Security", "role": "adversarial", "focus": "security abuse, privilege escalation, hostile actors", "temperature": "hot"},
    "reliability": {"label": "Reliability", "role": "adversarial", "focus": "reliability collapse, uptime loss, brittle dependencies", "temperature": "cool"},
    "concurrency": {"label": "Concurrency", "role": "adversarial", "focus": "concurrency races, lock contention, timing faults", "temperature": "hot"},
    "data": {"label": "Data Integrity", "role": "adversarial", "focus": "data integrity, corruption, replay hazards", "temperature": "cool"},
    "compliance": {"label": "Compliance", "role": "adversarial", "focus": "compliance, policy drift, governance gaps", "temperature": "balanced"},
    "user": {"label": "User Advocate", "role": "adversarial", "focus": "user confusion, adoption friction, trust loss", "temperature": "balanced"},
    "performance": {"label": "Performance", "role": "adversarial", "focus": "performance cliffs, hot paths, slow feedback", "temperature": "hot"},
    "observability": {"label": "Observability", "role": "adversarial", "focus": "observability blind spots, missing traces, opaque failures", "temperature": "cool"},
    "scalability": {"label": "Scalability", "role": "adversarial", "focus": "scalability failure, fan-out load, resource exhaustion", "temperature": "hot"},
    "recovery": {"label": "Recovery", "role": "adversarial", "focus": "recovery posture, rollback gaps, broken resumes", "temperature": "cool"},
    "integration": {"label": "Integrations", "role": "adversarial", "focus": "integration mismatch, boundary contracts, interoperability", "temperature": "balanced"},
    "abuse": {"label": "Abuse Cases", "role": "adversarial", "focus": "abuse cases, spam, malicious automation", "temperature": "hot"},
    "latency": {"label": "Latency", "role": "adversarial", "focus": "latency budgets, throughput realism, field conditions", "temperature": "balanced"},
    "incentives": {"label": "Incentives", "role": "adversarial", "focus": "incentive mismatch, local maxima, misuse of metrics", "temperature": "balanced"},
    "scope": {"label": "Scope Control", "role": "adversarial", "focus": "scope creep, hidden complexity, disguised expansions", "temperature": "cool"},
    "maintainability": {"label": "Maintainability", "role": "adversarial", "focus": "maintainability drag, operator toil, handoff risk", "temperature": "cool"},
    "edge": {"label": "Edge Cases", "role": "adversarial", "focus": "edge cases, chaos inputs, pathological sequences", "temperature": "hot"},
    "human": {"label": "Human Factors", "role": "adversarial", "focus": "human factors, fatigue, procedural mistakes", "temperature": "balanced"},
    "portability": {"label": "Portability", "role": "adversarial", "focus": "vendor lock-in, portability loss, external dependence", "temperature": "cool"},
    "privacy": {"label": "Privacy", "role": "adversarial", "focus": "privacy leakage, retention risk, oversharing", "temperature": "cool"},
    "product": {"label": "Product Strategy", "role": "adversarial", "focus": "product mismatch, weak demand signal, false confidence", "temperature": "balanced"},
    "governance": {"label": "Governance", "role": "adversarial", "focus": "decision paralysis, review bottlenecks, process drag", "temperature": "cool"},
    "wildcard": {"label": "Wildcard", "role": "adversarial", "focus": "wildcard attack surfaces, overlooked weirdness, novel failure", "temperature": "hot"},
}

DYNAMIC_LANE_OVERLAP_GROUPS: Dict[str, str] = {
    "security": "threat",
    "abuse": "threat",
    "reliability": "resilience",
    "recovery": "resilience",
    "data": "state",
    "concurrency": "state",
    "performance": "performance",
    "latency": "performance",
    "scalability": "performance",
    "governance": "governance",
    "compliance": "governance",
    "user": "human",
    "human": "human",
    "product": "product",
    "incentives": "product",
}

DYNAMIC_LANE_KEYWORD_HINTS: List[tuple[str, List[str]]] = [
    ("abuse exploit hostile attacker privilege escalation red team spam malicious adversary threat", ["security", "abuse"]),
    ("telemetry observability monitor trace tracing metrics alert drift blind spot instrumentation", ["observability"]),
    ("rollback resume crash outage recover recovery corruption integrity replay publish durable", ["recovery", "reliability", "data"]),
    ("race deadlock lock contention concurrent ordering state transition", ["concurrency", "data"]),
    ("latency throughput hot path fan-out scale capacity load", ["latency", "performance", "scalability"]),
    ("policy compliance approval audit governance review obligation", ["compliance", "governance"]),
    ("privacy pii retention oversharing secret leak leakage", ["privacy", "security"]),
    ("adoption trust confusion operator fatigue human error", ["user", "human"]),
    ("integration boundary contract interoperability migration dependency", ["integration", "portability"]),
    ("scope creep hidden complexity maintainability toil handoff", ["scope", "maintainability"]),
    ("economics roi burn spend budget return incentive", ["economist", "incentives"]),
]

DEFAULT_WORKER_TYPE_SEQUENCE: List[str] = [
    "proponent",
    "sceptic",
    "economist",
    "security",
    "reliability",
    "concurrency",
    "data",
    "compliance",
    "user",
    "performance",
    "observability",
    "scalability",
    "recovery",
    "integration",
    "abuse",
    "latency",
    "incentives",
    "scope",
    "maintainability",
    "edge",
    "human",
    "portability",
    "privacy",
    "product",
    "governance",
    "wildcard",
]

DEFAULT_MODEL_ID = "gpt-5-mini"
DEFAULT_PROVIDER_ID = "openai"
DEFAULT_OLLAMA_MODEL_ID = "qwen3"
WEB_SEARCH_TOOL_CALL_PRICE_USD = 0.01
SENSITIVE_PATH_SEGMENTS = {"secrets", ".ssh", ".aws", ".gnupg"}
SENSITIVE_FILE_NAMES = {
    "auth.txt",
    "openai_api_keys",
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_ed25519",
    "credentials",
    ".npmrc",
    ".pypirc",
}
SENSITIVE_FILE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx", ".asc")


class RuntimeErrorWithCode(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def budget_target_keys() -> List[str]:
    return ["commander", "worker", "summarizer"]


def normalize_budget_limits(config: Optional[Dict[str, Any]] = None, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    base = fallback or {"maxTotalTokens": 0, "maxCostUsd": 0.0, "maxOutputTokens": 0}
    return {
        "maxTotalTokens": max(0, int(config.get("maxTotalTokens", base["maxTotalTokens"]))),
        "maxCostUsd": round(max(0.0, float(config.get("maxCostUsd", base["maxCostUsd"]))), 6),
        "maxOutputTokens": max(0, int(config.get("maxOutputTokens", base["maxOutputTokens"]))),
    }


def default_budget_config() -> Dict[str, Any]:
    overall = {"maxTotalTokens": 250000, "maxCostUsd": 5.0, "maxOutputTokens": 1200}
    return {
        "maxTotalTokens": overall["maxTotalTokens"],
        "maxCostUsd": overall["maxCostUsd"],
        "maxOutputTokens": overall["maxOutputTokens"],
        "targets": {key: dict(overall) for key in budget_target_keys()},
    }


def default_research_config() -> Dict[str, Any]:
    return {"enabled": False, "externalWebAccess": True, "domains": []}


def default_local_file_tool_config() -> Dict[str, Any]:
    return {"enabled": False, "roots": ["."]}


def default_github_tool_config() -> Dict[str, Any]:
    return {"enabled": False, "repos": []}


def default_dynamic_spinup_config() -> Dict[str, Any]:
    return {"enabled": False}


def default_vetting_config() -> Dict[str, Any]:
    return {"enabled": False}


def default_usage_bucket() -> Dict[str, Any]:
    return {
        "calls": 0,
        "webSearchCalls": 0,
        "inputTokens": 0,
        "cachedInputTokens": 0,
        "billableInputTokens": 0,
        "outputTokens": 0,
        "reasoningTokens": 0,
        "totalTokens": 0,
        "modelCostUsd": 0.0,
        "toolCostUsd": 0.0,
        "estimatedCostUsd": 0.0,
        "lastModel": None,
        "lastResponseId": None,
        "lastUpdated": None,
    }


def default_usage_state() -> Dict[str, Any]:
    usage = default_usage_bucket()
    usage["byTarget"] = {}
    usage["byModel"] = {}
    return usage


def is_sensitive_repo_path(value: Any) -> bool:
    raw = str(value or "").strip().replace("\\", "/").strip("/")
    if not raw or raw == ".":
        return False
    parts = [part for part in raw.split("/") if part and part != "."]
    if not parts:
        return False
    lowered_parts = [part.lower() for part in parts]
    if any(part in SENSITIVE_PATH_SEGMENTS for part in lowered_parts[:-1]):
        return True
    basename = lowered_parts[-1]
    if basename in SENSITIVE_PATH_SEGMENTS:
        return True
    if basename in SENSITIVE_FILE_NAMES or basename.startswith(".env."):
        return True
    return basename.endswith(SENSITIVE_FILE_SUFFIXES)


def default_loop_state() -> Dict[str, Any]:
    return {
        "status": "idle",
        "jobId": None,
        "mode": "manual",
        "totalRounds": 0,
        "completedRounds": 0,
        "currentRound": 0,
        "delayMs": 0,
        "cancelRequested": False,
        "queuedAt": None,
        "startedAt": None,
        "finishedAt": None,
        "lastHeartbeatAt": None,
        "lastMessage": "Ready.",
    }


def default_state() -> Dict[str, Any]:
    return {
        "activeTask": None,
        "draft": {},
        "commander": None,
        "commanderReview": None,
        "workers": {},
        "summary": None,
        "memoryVersion": 0,
        "usage": default_usage_state(),
        "loop": default_loop_state(),
        "lastUpdated": utc_now(),
    }

def normalize_provider_id(provider: Optional[str], fallback: Optional[str] = None) -> str:
    candidate = (provider or "").strip().lower()
    if candidate in PROVIDER_CATALOG:
        return candidate
    fallback_value = (fallback or DEFAULT_PROVIDER_ID).strip().lower()
    return fallback_value if fallback_value in PROVIDER_CATALOG else DEFAULT_PROVIDER_ID


def default_model_for_provider(provider: Optional[str]) -> str:
    normalized = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    if normalized == "ollama":
        return str(os.getenv("LOOP_OLLAMA_DEFAULT_MODEL") or DEFAULT_OLLAMA_MODEL_ID).strip() or DEFAULT_OLLAMA_MODEL_ID
    return DEFAULT_MODEL_ID


def normalize_model_id(model: Optional[str], fallback: Optional[str] = None, provider: Optional[str] = None) -> str:
    normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    candidate = (model or "").strip()
    if normalized_provider == "ollama":
        if candidate:
            return candidate
        fallback_value = (fallback or default_model_for_provider(normalized_provider)).strip()
        return fallback_value or default_model_for_provider(normalized_provider)
    if candidate in MODEL_CATALOG:
        return candidate
    fallback_value = (fallback or default_model_for_provider(normalized_provider)).strip()
    return fallback_value if fallback_value in MODEL_CATALOG else default_model_for_provider(normalized_provider)


def coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def normalize_string_list(value: Any) -> List[str]:
    items: List[str] = []
    if isinstance(value, (list, tuple)):
        for entry in value:
            items.extend(normalize_string_list(entry))
    elif isinstance(value, str):
        for entry in re.split(r"[\r\n,]+", value):
            trimmed = entry.strip()
            if trimmed:
                items.append(trimmed)
    deduped: Dict[str, bool] = {}
    for item in items:
        deduped[item] = True
    return list(deduped.keys())


def normalize_local_file_roots(value: Any) -> List[str]:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed.startswith("["):
            try:
                decoded = json.loads(trimmed)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, list):
                value = decoded

    roots: Dict[str, bool] = {}
    for entry in normalize_string_list(value):
        candidate = str(entry or "").strip().replace("\\", "/")
        if candidate in {"", ".", "./"}:
            roots["."] = True
            continue
        if re.match(r"^[A-Za-z]:", candidate) or candidate.startswith("/"):
            continue
        candidate = re.sub(r"^(\./)+", "", candidate).strip().strip("/")
        if not candidate:
            roots["."] = True
            continue
        parts = [part for part in candidate.split("/") if part and part != "."]
        if not parts:
            roots["."] = True
            continue
        if ".." in parts:
            continue
        roots["/".join(parts)] = True
    normalized = list(roots.keys())[:20]
    return normalized or ["."]


def normalize_github_repos(value: Any) -> List[str]:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed.startswith("["):
            try:
                decoded = json.loads(trimmed)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, list):
                value = decoded

    repos: Dict[str, bool] = {}
    for entry in normalize_string_list(value):
        candidate = str(entry or "").strip().lower()
        candidate = re.sub(r"^https?://github\.com/", "", candidate, flags=re.IGNORECASE).strip().strip("/")
        if not candidate:
            continue
        if not re.match(r"^[a-z0-9_.-]+/[a-z0-9_.-]+$", candidate):
            continue
        repos[candidate] = True
    return list(repos.keys())[:50]


def normalize_string_array_preserve_items(value: Any) -> List[str]:
    items: List[str] = []
    if isinstance(value, (list, tuple)):
        for entry in value:
            items.extend(normalize_string_array_preserve_items(entry))
    elif isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            items.append(trimmed)
    deduped: Dict[str, bool] = {}
    ordered: List[str] = []
    for item in items:
        if item not in deduped:
            deduped[item] = True
            ordered.append(item)
    return ordered


def read_env_api_key_pool() -> List[str]:
    raw = str(os.getenv("LOOP_OPENAI_API_KEYS") or os.getenv("OPENAI_API_KEYS") or "").strip()
    if not raw:
        return []
    keys: List[str] = []
    seen: Dict[str, bool] = {}
    for entry in raw.replace(",", "\n").splitlines():
        key = str(entry or "").strip()
        if key and key not in seen:
            seen[key] = True
            keys.append(key)
    return keys


def read_api_key_pool(path: Path) -> List[str]:
    secret_backend = str(os.getenv("LOOP_SECRET_BACKEND") or "").strip().lower()
    if secret_backend == "env":
        return read_env_api_key_pool()
    if secret_backend == "external":
        return normalize_string_array_preserve_items(external_secret_status()["keys"])
    if secret_backend == "docker_secret":
        if path.exists():
            return normalize_string_array_preserve_items(path.read_text(encoding="utf-8", errors="replace").splitlines())
        return []
    if secret_backend == "local_file":
        if path.exists():
            return normalize_string_array_preserve_items(path.read_text(encoding="utf-8", errors="replace").splitlines())
        return []
    if path.exists():
        keys = normalize_string_array_preserve_items(path.read_text(encoding="utf-8", errors="replace").splitlines())
        if keys:
            return keys
    return read_env_api_key_pool()


def mask_api_key(key: str) -> str:
    last4 = key[-4:] if len(key) >= 4 else key
    return ("*" * max(4, len(key) - len(last4))) + last4


def normalize_auth_target(target: Any) -> str:
    candidate = str(target or "").strip()
    if not candidate:
        return "generic"
    if re.match(r"^[A-Za-z]$", candidate):
        return candidate.upper()
    lowered = candidate.lower()
    return lowered or "generic"


def auth_assignment_meta(assignment: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(assignment, dict):
        return None
    return {
        "target": str(assignment.get("target", "generic")),
        "positionSlot": int(assignment.get("positionSlot", 0) or 0),
        "keySlot": int(assignment.get("keySlot", 0) or 0),
        "poolSize": int(assignment.get("poolSize", 0) or 0),
        "rotationOffset": int(assignment.get("rotationOffset", 0) or 0),
        "reused": bool(assignment.get("reused", False)),
        "masked": str(assignment.get("masked", "")),
        "last4": str(assignment.get("last4", "")),
    }


def normalize_allowed_domains(value: Any) -> List[str]:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed.startswith("["):
            try:
                decoded = json.loads(trimmed)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, list):
                value = decoded
    domains: Dict[str, bool] = {}
    for entry in normalize_string_list(value):
        normalized = re.sub(r"^https?://", "", entry.strip(), flags=re.IGNORECASE)
        normalized = re.sub(r"/.*$", "", normalized)
        normalized = normalized.strip(" .").lower()
        if normalized:
            domains[normalized] = True
    return list(domains.keys())[:100]


def normalize_budget_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    default = default_budget_config()
    overall = normalize_budget_limits(config, default)
    raw_targets = config.get("targets") if isinstance(config.get("targets"), dict) else {}
    targets: Dict[str, Dict[str, Any]] = {}
    for key in budget_target_keys():
        target_config = raw_targets.get(key) if isinstance(raw_targets.get(key), dict) else {}
        targets[key] = normalize_budget_limits(target_config, overall)
    return {
        "maxTotalTokens": overall["maxTotalTokens"],
        "maxCostUsd": overall["maxCostUsd"],
        "maxOutputTokens": overall["maxOutputTokens"],
        "targets": targets,
    }


def normalize_research_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    default = default_research_config()
    return {
        "enabled": coerce_bool(config.get("enabled", default["enabled"]), default["enabled"]),
        "externalWebAccess": coerce_bool(
            config.get("externalWebAccess", default["externalWebAccess"]),
            default["externalWebAccess"],
        ),
        "domains": normalize_allowed_domains(config.get("domains", default["domains"])),
    }


def normalize_local_file_tool_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    default = default_local_file_tool_config()
    return {
        "enabled": coerce_bool(config.get("enabled", default["enabled"]), default["enabled"]),
        "roots": normalize_local_file_roots(config.get("roots", default["roots"])),
    }


def normalize_github_tool_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    default = default_github_tool_config()
    return {
        "enabled": coerce_bool(config.get("enabled", default["enabled"]), default["enabled"]),
        "repos": normalize_github_repos(config.get("repos", default["repos"])),
    }


def normalize_dynamic_spinup_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    default = default_dynamic_spinup_config()
    return {"enabled": coerce_bool(config.get("enabled", default["enabled"]), default["enabled"])}


def normalize_vetting_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    default = default_vetting_config()
    return {"enabled": coerce_bool(config.get("enabled", default["enabled"]), default["enabled"])}


def normalize_usage_bucket(bucket: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    bucket = bucket or {}
    default = default_usage_bucket()
    normalized = dict(default)
    for key in (
        "calls",
        "webSearchCalls",
        "inputTokens",
        "cachedInputTokens",
        "billableInputTokens",
        "outputTokens",
        "reasoningTokens",
        "totalTokens",
    ):
        normalized[key] = max(0, int(bucket.get(key, default[key])))
    for key in ("modelCostUsd", "toolCostUsd", "estimatedCostUsd"):
        normalized[key] = round(max(0.0, float(bucket.get(key, default[key]))), 6)
    for key in ("lastModel", "lastResponseId", "lastUpdated"):
        normalized[key] = bucket.get(key, default[key])
    return normalized


def normalize_usage_state(usage: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    usage = usage or {}
    normalized = normalize_usage_bucket(usage)
    normalized["byTarget"] = {}
    normalized["byModel"] = {}
    if isinstance(usage.get("byTarget"), dict):
        for key, value in usage["byTarget"].items():
            key_text = str(key).strip()
            if key_text:
                normalized["byTarget"][key_text] = normalize_usage_bucket(value if isinstance(value, dict) else {})
    if isinstance(usage.get("byModel"), dict):
        for key, value in usage["byModel"].items():
            key_text = str(key).strip()
            if key_text:
                normalized["byModel"][key_text] = normalize_usage_bucket(value if isinstance(value, dict) else {})
    return normalized


def worker_slot_ids() -> List[str]:
    return [chr(value) for value in range(ord("A"), ord("Z") + 1)]


def default_worker_type_for_slot(worker_id: str) -> str:
    worker_id = (worker_id or "").strip().upper()
    try:
        index = worker_slot_ids().index(worker_id)
    except ValueError:
        return "wildcard"
    return DEFAULT_WORKER_TYPE_SEQUENCE[index] if index < len(DEFAULT_WORKER_TYPE_SEQUENCE) else "wildcard"


def normalize_worker_temperature(value: Any, fallback: str = "balanced") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in WORKER_TEMPERATURE_CATALOG:
        return candidate
    return fallback if fallback in WORKER_TEMPERATURE_CATALOG else "balanced"


def normalize_harness_concision(value: Any, fallback: str = "tight") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in HARNESS_CONCISION_CATALOG:
        return candidate
    return fallback if fallback in HARNESS_CONCISION_CATALOG else "tight"


def normalize_harness_instruction(value: Any, max_length: int = 600) -> str:
    return truncate_text(re.sub(r"\s+", " ", str(value or "")).strip(), max_length)


def default_worker_harness() -> Dict[str, str]:
    return {"concision": "tight", "instruction": ""}


def default_summarizer_harness() -> Dict[str, str]:
    return {"concision": "balanced", "instruction": ""}


def normalize_harness_config(value: Any, fallback_concision: str = "tight") -> Dict[str, str]:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed.startswith("{"):
            try:
                decoded = json.loads(trimmed)
            except Exception:
                decoded = None
            if isinstance(decoded, dict):
                value = decoded
            elif trimmed.lower() in HARNESS_CONCISION_CATALOG:
                value = {"concision": trimmed}
            else:
                value = {"instruction": trimmed}
        elif trimmed.lower() in HARNESS_CONCISION_CATALOG:
            value = {"concision": trimmed}
        else:
            value = {"instruction": trimmed}
    config = value if isinstance(value, dict) else {}
    return {
        "concision": normalize_harness_concision(config.get("concision"), fallback_concision),
        "instruction": normalize_harness_instruction(config.get("instruction", "")),
    }


def worker_catalog(default_model: Optional[str] = None, default_provider: Optional[str] = None) -> List[Dict[str, str]]:
    provider = normalize_provider_id(default_provider, DEFAULT_PROVIDER_ID)
    model = normalize_model_id(default_model, default_model_for_provider(provider), provider)
    return [normalize_worker_definition({"id": worker_id}, model) for worker_id in worker_slot_ids()]


def normalize_worker_definition(worker: Dict[str, Any], default_model: Optional[str] = None) -> Dict[str, str]:
    worker_id = str(worker.get("id", "")).strip().upper()
    if not re.match(r"^[A-Z]$", worker_id):
        raise RuntimeErrorWithCode("Worker ids must be single uppercase letters.", 500)
    default_type = default_worker_type_for_slot(worker_id)
    worker_type = str(worker.get("type", default_type)).strip().lower()
    if worker_type not in WORKER_TYPE_CATALOG:
        worker_type = default_type
    catalog_worker = WORKER_TYPE_CATALOG.get(
        worker_type,
        {
            "label": f"Worker {worker_id}",
            "role": "adversarial",
            "focus": "general adversarial review",
            "temperature": "balanced",
        },
    )
    fallback_model = normalize_model_id(default_model, DEFAULT_MODEL_ID)
    active_from_round = max(1, int(worker.get("activeFromRound", 1) or 1))
    return {
        "id": worker_id,
        "type": worker_type,
        "label": str(worker.get("label", catalog_worker["label"])).strip() or catalog_worker["label"],
        "role": str(worker.get("role", catalog_worker["role"])).strip() or catalog_worker["role"],
        "focus": str(worker.get("focus", catalog_worker["focus"])).strip() or catalog_worker["focus"],
        "temperature": normalize_worker_temperature(worker.get("temperature"), str(catalog_worker.get("temperature", "balanced"))),
        "model": normalize_model_id(worker.get("model"), fallback_model),
        "activeFromRound": active_from_round,
        "harness": normalize_harness_config(worker.get("harness"), default_worker_harness()["concision"]),
    }


def task_workers(task: Dict[str, Any], round_number: Optional[int] = None) -> List[Dict[str, str]]:
    runtime_config = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
    default_provider = normalize_provider_id(runtime_config.get("provider"), DEFAULT_PROVIDER_ID)
    default_model = normalize_model_id(runtime_config.get("model"), default_model_for_provider(default_provider), default_provider)
    workers: Dict[str, Dict[str, str]] = {}
    raw_workers = task.get("workers")
    if isinstance(raw_workers, list):
        for worker in raw_workers:
            if isinstance(worker, dict):
                normalized = normalize_worker_definition(worker, default_model)
                workers[normalized["id"]] = normalized
    if not workers:
        for worker in worker_catalog(default_model, default_provider)[:2]:
            normalized = normalize_worker_definition(worker, default_model)
            workers[normalized["id"]] = normalized
    ordered = [workers[key] for key in sorted(workers)]
    if round_number is None:
        return ordered
    active_round = max(1, int(round_number or 1))
    return [worker for worker in ordered if int(worker.get("activeFromRound", 1) or 1) <= active_round]


def find_task_worker(task: Dict[str, Any], worker_id: str) -> Optional[Dict[str, str]]:
    target = worker_id.strip().upper()
    for worker in task_workers(task):
        if worker["id"] == target:
            return worker
    return None


def worker_active_from_round(worker: Dict[str, Any]) -> int:
    return max(1, int(worker.get("activeFromRound", 1) or 1))


def summarizer_config(task: Dict[str, Any]) -> Dict[str, str]:
    runtime_config = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
    runtime_provider = normalize_provider_id(runtime_config.get("provider"), DEFAULT_PROVIDER_ID)
    default_model = normalize_model_id(runtime_config.get("model"), default_model_for_provider(runtime_provider), runtime_provider)
    summary = task.get("summarizer") if isinstance(task.get("summarizer"), dict) else {}
    provider = normalize_provider_id(summary.get("provider"), runtime_provider)
    return {
        "id": "summarizer",
        "label": str(summary.get("label", "Summarizer")).strip() or "Summarizer",
        "provider": provider,
        "model": normalize_model_id(summary.get("model"), default_model_for_provider(provider), provider),
        "harness": normalize_harness_config(summary.get("harness"), default_summarizer_harness()["concision"]),
    }


def commander_config(task: Dict[str, Any]) -> Dict[str, str]:
    summary = summarizer_config(task)
    return {
        "id": "commander",
        "label": "Commander",
        "provider": summary["provider"],
        "model": summary["model"],
        "harness": summary["harness"],
    }


def commander_review_config(task: Dict[str, Any]) -> Dict[str, str]:
    summary = summarizer_config(task)
    return {
        "id": "commander_review",
        "label": "Commander Review",
        "provider": summary["provider"],
        "model": summary["model"],
        "harness": summary["harness"],
    }


def normalize_worker_id_list(ids: Any) -> List[str]:
    normalized: Dict[str, bool] = {}
    for value in normalize_string_array_preserve_items(ids):
        candidate = value.strip().upper()
        if re.match(r"^[A-Z]+$", candidate):
            normalized[candidate] = True
    return list(normalized.keys())


def normalize_canonical_url(url: str) -> Optional[str]:
    candidate = str(url).strip().strip('"\'`')
    if not candidate:
        return None
    candidate = re.sub(r"[\uFFFD]+$", "", candidate)
    candidate = re.sub(r"(?i)(%EF%BF%BD)+$", "", candidate)
    candidate = re.sub(r"[\.,;\)\]\}>]+$", "", candidate)
    try:
        parts = urlsplit(candidate)
    except Exception:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return None
    scheme = parts.scheme.lower()
    host = parts.hostname.lower() if parts.hostname else ""
    if not host:
        return None
    port = parts.port
    netloc = host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    path = parts.path or ""
    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def normalize_url_array_values(value: Any) -> List[str]:
    urls: List[str] = []
    if isinstance(value, (list, tuple)):
        for entry in value:
            urls.extend(normalize_url_array_values(entry))
    elif isinstance(value, str):
        matches = re.findall(r"https?://[^\s\"'<>())]+", value)
        if matches:
            for match in matches:
                normalized = normalize_canonical_url(match)
                if normalized:
                    urls.append(normalized)
        else:
            normalized = normalize_canonical_url(value)
            if normalized:
                urls.append(normalized)
    deduped: Dict[str, bool] = {}
    ordered: List[str] = []
    for url in urls:
        if url not in deduped:
            deduped[url] = True
            ordered.append(url)
    return ordered


def truncate_text(value: Any, max_length: int = 320) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 3)].rstrip() + "..."


def limit_string_list(value: Any, max_items: int = 8, max_length: int = 220) -> List[str]:
    items: List[str] = []
    for entry in normalize_string_array_preserve_items(value)[:max_items]:
        trimmed = truncate_text(entry, max_length)
        if trimmed:
            items.append(trimmed)
    return items


def limit_url_list(value: Any, max_items: int = 10) -> List[str]:
    items: List[str] = []
    for entry in normalize_url_array_values(value)[:max_items]:
        trimmed = str(entry).strip()
        if trimmed:
            items.append(trimmed)
    return items


def normalize_local_tool_calls(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for entry in value[:20]:
        if not isinstance(entry, dict):
            continue
        normalized.append(
            {
                "name": truncate_text(entry.get("name", ""), 60),
                "path": truncate_text(entry.get("path", ""), 260),
                "summary": truncate_text(entry.get("summary", ""), 260),
                "sources": limit_string_list(entry.get("sources", []), 10, 220),
                "error": truncate_text(entry.get("error", ""), 220),
                "lineCount": max(0, int(entry.get("lineCount", 0) or 0)),
                "entryCount": max(0, int(entry.get("entryCount", 0) or 0)),
                "matchCount": max(0, int(entry.get("matchCount", 0) or 0)),
                "filesScanned": max(0, int(entry.get("filesScanned", 0) or 0)),
                "bytesRead": max(0, int(entry.get("bytesRead", 0) or 0)),
                "truncated": bool(entry.get("truncated", False)),
            }
        )
    return normalized


def filter_tool_calls_by_prefixes(value: Any, prefixes: tuple[str, ...]) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    filtered: List[Dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip().lower()
        if any(name.startswith(prefix) for prefix in prefixes):
            filtered.append(entry)
    return filtered


def collect_tool_sources_by_prefixes(value: Any, prefixes: tuple[str, ...]) -> List[str]:
    sources: List[str] = []
    for entry in filter_tool_calls_by_prefixes(value, prefixes):
        if not isinstance(entry, dict):
            continue
        for source in entry.get("sources", []):
            sources.append(str(source))
    return normalize_string_array_preserve_items(sources)


def normalize_lane_type_list(value: Any, include_utility: bool = False, max_items: int = 3) -> List[str]:
    allowed: List[str] = []
    for lane_type in normalize_string_array_preserve_items(value):
        candidate = str(lane_type).strip().lower()
        if candidate not in WORKER_TYPE_CATALOG:
            continue
        if not include_utility and str(WORKER_TYPE_CATALOG[candidate].get("role", "adversarial")) != "adversarial":
            continue
        if candidate not in allowed:
            allowed.append(candidate)
        if len(allowed) >= max_items:
            break
    return allowed


def worker_harness_instruction_lines(harness: Any) -> List[str]:
    config = normalize_harness_config(harness, default_worker_harness()["concision"])
    concision = config["concision"]
    lines = [
        "Treat Objective as the authoritative current user input.",
        "Treat Session context and Prior summary as background only; if they conflict with Objective or current evidence, Objective wins.",
    ]
    if concision == "tight":
        lines.extend(
            [
                "Be concise but specific.",
                "Keep observation to 2 short sentences maximum.",
                "For each array field, return at most 3 items.",
                "Keep each string item compact, ideally under 18 words.",
                "Limit evidenceLedger to 2 concrete claims.",
                "Keep requestToPeer to 1 short sentence.",
            ]
        )
    elif concision == "balanced":
        lines.extend(
            [
                "Be concise first, but expand when the user's input is dense or technical.",
                "Keep observation to at most 4 sentences.",
                "For each array field, return at most 4 items.",
                "Keep each string item focused, ideally under 30 words.",
                "Limit evidenceLedger to 3 concrete claims.",
                "Keep requestToPeer to at most 2 short sentences.",
            ]
        )
    else:
        lines.extend(
            [
                "Prefer rich synthesis over aggressive compression when the user provided dense source material.",
                "Keep observation to at most 6 sentences.",
                "For each array field, return at most 5 items.",
                "Keep each string item clear and compact, ideally under 45 words.",
                "Limit evidenceLedger to 4 concrete claims.",
                "Keep requestToPeer to at most 3 short sentences.",
            ]
        )
    if config["instruction"]:
        lines.append(f"Extra harness instruction: {config['instruction']}")
    return lines


def summarizer_harness_instruction_lines(harness: Any) -> List[str]:
    config = normalize_harness_config(harness, default_summarizer_harness()["concision"])
    concision = config["concision"]
    lines = [
        "Treat Objective as the authoritative current user input.",
        "Treat Session context as background only; if it conflicts with Objective or current evidence, Objective wins.",
        "The lead thread must reason over the user's actual request before it absorbs adversarial pressure.",
    ]
    if concision == "tight":
        lines.extend(
            [
                "Keep frontAnswer.answer to at most 3 short paragraphs.",
                "Keep reviewTrace to at most 4 items.",
                "Keep stableFindings, conditionalTruths, and claimsNeedingVerification to at most 3 items each.",
                "Keep conflicts to at most 2 topics and evidenceVerdicts to at most 3 claims.",
                "Keep vettingSummary, recommendedNextAction, and frontAnswer.confidenceNote brief.",
            ]
        )
    elif concision == "balanced":
        lines.extend(
            [
                "Keep frontAnswer.answer focused, but allow up to 5 reasonably sized paragraphs when the source material is dense.",
                "ReviewTrace may use up to 5 items when needed.",
                "Keep stableFindings, conditionalTruths, and claimsNeedingVerification to at most 4 items each.",
                "Keep conflicts to at most 3 topics and evidenceVerdicts to at most 4 claims.",
                "Keep vettingSummary, recommendedNextAction, and frontAnswer.confidenceNote concise, not skeletal.",
            ]
        )
    else:
        lines.extend(
            [
                "Use frontAnswer.answer for substantive synthesis when the user supplied long source material; up to 7 paragraphs is acceptable.",
                "ReviewTrace may use up to 6 items when necessary.",
                "Keep stableFindings, conditionalTruths, and claimsNeedingVerification to at most 5 items each.",
                "Keep conflicts to at most 4 topics and evidenceVerdicts to at most 5 claims.",
                "Prefer clarity and completeness over aggressive brevity.",
            ]
        )
    if config["instruction"]:
        lines.append(f"Extra harness instruction: {config['instruction']}")
    return lines


def commander_harness_instruction_lines(harness: Any) -> List[str]:
    config = normalize_harness_config(harness, default_summarizer_harness()["concision"])
    concision = config["concision"]
    lines = [
        "Treat Objective as the authoritative current user input.",
        "Treat Session context and Prior summary as background only; if they conflict with Objective, Objective wins.",
        "Use answerDraft for a compact lead answer, not a full memo.",
        "Keep questionsForWorkers, pressurePoints, keepCourseIf, changeCourseIf, and uncertainty tightly pruned to the strongest points only.",
    ]
    if concision == "tight":
        lines.extend(
            [
                "Keep answerDraft to at most 2 short paragraphs or 5 short bullets.",
                "Keep questionsForWorkers, pressurePoints, keepCourseIf, changeCourseIf, and uncertainty to at most 2 items each.",
                "Prefer the clearest decision and the smallest set of pivot conditions.",
            ]
        )
    elif concision == "balanced":
        lines.extend(
            [
                "Keep answerDraft to at most 3 compact paragraphs or 6 short bullets.",
                "Keep questionsForWorkers, pressurePoints, keepCourseIf, changeCourseIf, and uncertainty to at most 3 items each.",
                "Be specific enough to steer the adversaries, but do not write the whole final answer yet.",
            ]
        )
    else:
        lines.extend(
            [
                "Keep answerDraft to at most 4 compact paragraphs or 8 short bullets.",
                "Keep questionsForWorkers, pressurePoints, keepCourseIf, changeCourseIf, and uncertainty to at most 4 items each.",
                "Prefer clarity and steering value over long-form exposition.",
            ]
        )
    if config["instruction"]:
        lines.append(f"Extra harness instruction: {config['instruction']}")
    return lines


def normalize_evidence_ledger(ledger: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(ledger, list):
        return normalized
    for entry in ledger:
        if not isinstance(entry, dict):
            continue
        claim = str(entry.get("claim", "")).strip()
        if not claim:
            continue
        support_level = str(entry.get("supportLevel", "weak")).strip() or "weak"
        note = str(entry.get("note", "")).strip()
        normalized.append(
            {
                "claim": claim,
                "supportLevel": support_level,
                "sourceUrls": normalize_url_array_values(entry.get("sourceUrls", [])),
                "note": note,
            }
        )
    return normalized


def normalize_evidence_verdicts(verdicts: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(verdicts, list):
        return normalized
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            continue
        claim = str(verdict.get("claim", "")).strip()
        if not claim:
            continue
        status = str(verdict.get("status", "unvetted")).strip() or "unvetted"
        rationale = str(verdict.get("rationale", "")).strip()
        normalized.append(
            {
                "claim": claim,
                "status": status,
                "supportingWorkers": normalize_worker_id_list(verdict.get("supportingWorkers", [])),
                "challengingWorkers": normalize_worker_id_list(verdict.get("challengingWorkers", [])),
                "sourceUrls": normalize_url_array_values(verdict.get("sourceUrls", [])),
                "rationale": rationale,
            }
        )
    return normalized


def normalize_line_ref_list(refs: Any) -> List[str]:
    normalized: List[str] = []
    seen: Dict[str, bool] = {}
    for entry in normalize_string_array_preserve_items(refs):
        candidate = str(entry).strip()
        if candidate and candidate not in seen:
            seen[candidate] = True
            normalized.append(candidate)
    return normalized


def build_legacy_front_answer(summary: Optional[Dict[str, Any]]) -> Dict[str, str]:
    summary = summary or {}
    stable_findings = limit_string_list(summary.get("stableFindings", []), 3, 220)
    conflict_topics: List[str] = []
    for conflict in summary.get("conflicts", []) if isinstance(summary.get("conflicts"), list) else []:
        if not isinstance(conflict, dict):
            continue
        topic = truncate_text(conflict.get("topic", ""), 180)
        if topic:
            conflict_topics.append(topic)
    recommended_next_action = truncate_text(summary.get("recommendedNextAction", ""), 260)
    confidence_note = truncate_text(summary.get("vettingSummary", ""), 240)
    paragraphs: List[str] = []
    if stable_findings:
        paragraphs.append(" ".join(stable_findings))
    if conflict_topics:
        paragraphs.append("Remaining disagreement: " + "; ".join(conflict_topics) + ".")
    if recommended_next_action:
        paragraphs.append("Next step: " + recommended_next_action)
    stance = stable_findings[0] if stable_findings else (recommended_next_action or confidence_note)
    answer = "\n\n".join(paragraphs).strip() or stance
    return {
        "answer": answer or "No adjudicated answer was captured.",
        "stance": stance or "No adjudicated stance was captured.",
        "confidenceNote": confidence_note,
    }


def normalize_front_answer(front_answer: Any, fallback_summary: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    fallback_summary = fallback_summary or {}
    normalized = build_legacy_front_answer(fallback_summary)
    fallback_pressure = ""
    for conflict in fallback_summary.get("conflicts", []) if isinstance(fallback_summary.get("conflicts"), list) else []:
        if isinstance(conflict, dict):
            topic = truncate_text(conflict.get("topic", ""), 220)
            if topic:
                fallback_pressure = f"The strongest shaping objection was around {topic}."
                break
    if not fallback_pressure:
        for item in normalize_string_array_preserve_items(fallback_summary.get("claimsNeedingVerification", [])):
            item_text = truncate_text(item, 220)
            if item_text:
                fallback_pressure = item_text
                break
    normalized["leadDirection"] = truncate_text(normalized.get("stance", ""), 260) or "No explicit lead direction was captured."
    normalized["adversarialPressure"] = fallback_pressure or "No strong adversarial pressure was captured."
    if isinstance(front_answer, dict):
        answer = truncate_text(front_answer.get("answer", ""), 3200)
        stance = truncate_text(front_answer.get("stance", ""), 260)
        confidence_note = truncate_text(front_answer.get("confidenceNote", ""), 260)
        lead_direction = truncate_text(front_answer.get("leadDirection", ""), 260)
        adversarial_pressure = truncate_text(front_answer.get("adversarialPressure", ""), 320)
        if answer:
            normalized["answer"] = answer
        if stance:
            normalized["stance"] = stance
        if confidence_note or normalized["confidenceNote"] == "":
            normalized["confidenceNote"] = confidence_note
        if lead_direction:
            normalized["leadDirection"] = lead_direction
        if adversarial_pressure:
            normalized["adversarialPressure"] = adversarial_pressure
    if not normalized["answer"]:
        normalized["answer"] = normalized["stance"] or "No adjudicated answer was captured."
    if not normalized["stance"]:
        normalized["stance"] = truncate_text(normalized["answer"], 260) or "No adjudicated stance was captured."
    if not normalized["leadDirection"]:
        normalized["leadDirection"] = normalized["stance"] or "No explicit lead direction was captured."
    if not normalized["adversarialPressure"]:
        normalized["adversarialPressure"] = "No strong adversarial pressure was captured."
    return normalized


def normalize_summarizer_opinion(opinion: Any, fallback_summary: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    fallback_summary = fallback_summary or {}
    fallback_front_answer = normalize_front_answer(fallback_summary.get("frontAnswer"), fallback_summary)
    fallback_uncertainty = ""
    for item in normalize_string_array_preserve_items(fallback_summary.get("claimsNeedingVerification", [])):
        fallback_uncertainty = truncate_text(item, 240)
        if fallback_uncertainty:
            break
    if not fallback_uncertainty:
        for item in normalize_string_array_preserve_items(fallback_summary.get("conditionalTruths", [])):
            fallback_uncertainty = truncate_text(item, 240)
            if fallback_uncertainty:
                break
    normalized = {
        "stance": truncate_text(fallback_front_answer.get("stance", ""), 260) or "No explicit opinion was captured.",
        "because": truncate_text(fallback_summary.get("vettingSummary", ""), 320) or "This view reflects the strongest evidence that survived the lane disagreement.",
        "uncertainty": fallback_uncertainty or "This position should stay revisable as stronger evidence appears.",
        "integrationMode": "Start with one lead answer, then let the strongest objections narrow, condition, redirect, or overturn it before it reaches the user.",
    }
    if isinstance(opinion, dict):
        stance = truncate_text(opinion.get("stance", ""), 260)
        because = truncate_text(opinion.get("because", ""), 360)
        uncertainty = truncate_text(opinion.get("uncertainty", ""), 260)
        integration_mode = truncate_text(opinion.get("integrationMode", ""), 260)
        if stance:
            normalized["stance"] = stance
        if because:
            normalized["because"] = because
        if uncertainty:
            normalized["uncertainty"] = uncertainty
        if integration_mode:
            normalized["integrationMode"] = integration_mode
    return normalized


def normalize_course_decision(value: Any, default: str = "maintain") -> str:
    normalized = truncate_text(value, 24).lower().replace("-", "_").replace(" ", "_")
    if normalized in {"maintain", "qualify", "redirect", "reverse"}:
        return normalized
    return default


def normalize_contribution_value(value: Any, default: str = "medium") -> str:
    normalized = truncate_text(value, 16).lower().replace("-", "_").replace(" ", "_")
    if normalized in {"high", "medium", "low", "negative"}:
        return normalized
    return default


def normalize_contribution_effect(value: Any, default: str = "support") -> str:
    normalized = truncate_text(value, 16).lower().replace("-", "_").replace(" ", "_")
    if normalized in {"support", "qualify", "redirect", "reverse", "reject"}:
        return normalized
    return default


def normalize_contribution_assessments(items: Any) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    if not isinstance(items, list):
        return normalized
    for entry in items:
        if not isinstance(entry, dict):
            continue
        contribution = truncate_text(entry.get("contribution", ""), 220)
        reason = truncate_text(entry.get("reason", ""), 280)
        if not contribution:
            continue
        normalized.append(
            {
                "contribution": contribution,
                "value": normalize_contribution_value(entry.get("value")),
                "effect": normalize_contribution_effect(entry.get("effect")),
                "reason": reason or "No reason was captured.",
            }
        )
    return normalized[:4]


def normalize_commander_checkpoint(checkpoint: Any, fallback_task: Optional[Dict[str, Any]] = None, fallback_round: int = 1) -> Dict[str, Any]:
    fallback_task = fallback_task or {}
    objective = truncate_text(fallback_task.get("objective", ""), 260)
    fallback_direction = objective or "No commander direction was captured."
    normalized = {
        "taskId": str(fallback_task.get("taskId", "")),
        "round": max(1, int(fallback_round or 1)),
        "stance": fallback_direction,
        "leadDirection": fallback_direction,
        "answerDraft": fallback_direction,
        "whyThisDirection": "Start from the clearest answer direction visible in the user's current objective.",
        "questionsForWorkers": [],
        "pressurePoints": [],
        "keepCourseIf": [],
        "changeCourseIf": [],
        "uncertainty": [],
        "suggestedLaneTypes": [],
        "suggestedLaneReason": "",
        "constraintsSeen": limit_string_list(fallback_task.get("constraints", []), 6, 180),
    }
    if not isinstance(checkpoint, dict):
        return normalized
    normalized["taskId"] = str(checkpoint.get("taskId", normalized["taskId"]))
    # The runtime decides which round is being executed; do not let a stale model
    # echo drag the checkpoint backward and break worker alignment on later rounds.
    normalized["round"] = max(1, int(fallback_round or normalized["round"]))
    stance = truncate_text(checkpoint.get("stance", ""), 260)
    lead_direction = truncate_text(checkpoint.get("leadDirection", ""), 280)
    answer_draft = truncate_text(checkpoint.get("answerDraft", ""), 1400)
    why_this_direction = truncate_text(checkpoint.get("whyThisDirection", ""), 360)
    if stance:
        normalized["stance"] = stance
    if lead_direction:
        normalized["leadDirection"] = lead_direction
    if answer_draft:
        normalized["answerDraft"] = answer_draft
    if why_this_direction:
        normalized["whyThisDirection"] = why_this_direction
    normalized["questionsForWorkers"] = limit_string_list(checkpoint.get("questionsForWorkers", []), 4, 220)
    normalized["pressurePoints"] = limit_string_list(checkpoint.get("pressurePoints", []), 4, 220)
    normalized["keepCourseIf"] = limit_string_list(checkpoint.get("keepCourseIf", []), 4, 220)
    normalized["changeCourseIf"] = limit_string_list(checkpoint.get("changeCourseIf", []), 4, 220)
    normalized["uncertainty"] = limit_string_list(checkpoint.get("uncertainty", []), 4, 220)
    normalized["suggestedLaneTypes"] = normalize_lane_type_list(checkpoint.get("suggestedLaneTypes", []))
    normalized["suggestedLaneReason"] = truncate_text(checkpoint.get("suggestedLaneReason", ""), 280)
    normalized["constraintsSeen"] = limit_string_list(checkpoint.get("constraintsSeen", []), 8, 180)
    if not normalized["stance"]:
        normalized["stance"] = normalized["leadDirection"] or fallback_direction
    if not normalized["leadDirection"]:
        normalized["leadDirection"] = normalized["stance"] or fallback_direction
    if not normalized["answerDraft"]:
        normalized["answerDraft"] = normalized["leadDirection"] or fallback_direction
    if not normalized["whyThisDirection"]:
        normalized["whyThisDirection"] = "No commander rationale was captured."
    return normalized


def normalize_commander_review_checkpoint(
    checkpoint: Any,
    fallback_task: Optional[Dict[str, Any]] = None,
    fallback_round: int = 1,
    fallback_commander: Optional[Dict[str, Any]] = None,
    fallback_workers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    base_commander = normalize_commander_checkpoint(fallback_commander or {}, fallback_task, fallback_round)
    normalized = {
        "taskId": str(base_commander.get("taskId", "")),
        "round": max(1, int(fallback_round or 1)),
        "stance": truncate_text(base_commander.get("stance", ""), 260) or "No reviewed stance was captured.",
        "leadDirection": truncate_text(base_commander.get("leadDirection", ""), 280) or "No reviewed lead direction was captured.",
        "answerDraft": truncate_text(base_commander.get("answerDraft", ""), 1800) or "No reviewed answer draft was captured.",
        "whyThisDirection": (
            truncate_text(base_commander.get("whyThisDirection", ""), 360)
            or "No commander reevaluation rationale was captured."
        ),
        "controlAudit": {},
        "dynamicLaneDecision": normalize_dynamic_lane_decision(None),
        "dynamicLaneResolution": normalize_dynamic_lane_resolution(None),
        "remainingUncertainty": limit_string_list(base_commander.get("uncertainty", []), 4, 220),
        "sourceWorkers": normalize_worker_id_list(fallback_workers or []),
    }
    if isinstance(checkpoint, dict):
        normalized["taskId"] = str(checkpoint.get("taskId", normalized["taskId"]))
        normalized["round"] = max(1, int(fallback_round or normalized["round"]))
        stance = truncate_text(checkpoint.get("stance", ""), 260)
        lead_direction = truncate_text(checkpoint.get("leadDirection", ""), 280)
        answer_draft = truncate_text(checkpoint.get("answerDraft", ""), 1800)
        why_this_direction = truncate_text(checkpoint.get("whyThisDirection", ""), 360)
        if stance:
            normalized["stance"] = stance
        if lead_direction:
            normalized["leadDirection"] = lead_direction
        if answer_draft:
            normalized["answerDraft"] = answer_draft
        if why_this_direction:
            normalized["whyThisDirection"] = why_this_direction
        normalized["remainingUncertainty"] = limit_string_list(checkpoint.get("remainingUncertainty", []), 4, 220)
        normalized["sourceWorkers"] = normalize_worker_id_list(checkpoint.get("sourceWorkers", fallback_workers or []))
        normalized["dynamicLaneDecision"] = normalize_dynamic_lane_decision(checkpoint.get("dynamicLaneDecision"))
        normalized["dynamicLaneResolution"] = normalize_dynamic_lane_resolution(checkpoint.get("dynamicLaneResolution"))
        normalized["controlAudit"] = normalize_control_audit(
            checkpoint.get("controlAudit"),
            {
                "frontAnswer": {
                    "answer": normalized["answerDraft"],
                    "stance": normalized["stance"],
                    "leadDirection": normalized["leadDirection"],
                    "adversarialPressure": "",
                    "confidenceNote": "",
                },
                "summarizerOpinion": {
                    "stance": normalized["stance"],
                    "because": normalized["whyThisDirection"],
                    "uncertainty": (
                        normalized["remainingUncertainty"][0]
                        if normalized["remainingUncertainty"]
                        else "The lead answer should stay revisable if stronger objections land."
                    ),
                    "integrationMode": "The lead thread re-evaluates adversarial pressure before the public answer is formed.",
                },
                "claimsNeedingVerification": normalized["remainingUncertainty"],
            },
        )
    if not normalized["sourceWorkers"]:
        normalized["sourceWorkers"] = normalize_worker_id_list(fallback_workers or [])
    if not normalized["controlAudit"]:
        normalized["controlAudit"] = normalize_control_audit(
            {
                "leadDraft": normalized["answerDraft"],
                "courseDecision": "maintain",
                "courseDecisionReason": (
                    "No commander reevaluation audit was captured, so the lead thread maintained its initial course by default."
                ),
                "acceptedAdversarialPoints": [],
                "rejectedAdversarialPoints": [],
                "heldOutConcerns": normalized["remainingUncertainty"],
                "selfCheck": "Before speaking, the lead thread should explicitly compare the revised draft against the user's actual request.",
            },
            {
                "frontAnswer": {
                    "answer": normalized["answerDraft"],
                    "stance": normalized["stance"],
                    "leadDirection": normalized["leadDirection"],
                    "adversarialPressure": "",
                    "confidenceNote": "",
                },
                "summarizerOpinion": {
                    "stance": normalized["stance"],
                    "because": normalized["whyThisDirection"],
                    "uncertainty": (
                        normalized["remainingUncertainty"][0]
                        if normalized["remainingUncertainty"]
                        else "The lead answer should stay revisable if stronger objections land."
                    ),
                    "integrationMode": "The lead thread re-evaluates adversarial pressure before the public answer is formed.",
                },
                "claimsNeedingVerification": normalized["remainingUncertainty"],
            },
        )
    if not normalized["answerDraft"]:
        normalized["answerDraft"] = normalized["leadDirection"] or normalized["stance"]
    if not normalized["leadDirection"]:
        normalized["leadDirection"] = normalized["stance"] or truncate_text(normalized["answerDraft"], 260)
    if not normalized["stance"]:
        normalized["stance"] = normalized["leadDirection"] or truncate_text(normalized["answerDraft"], 260)
    if not normalized["whyThisDirection"]:
        normalized["whyThisDirection"] = "No commander reevaluation rationale was captured."
    return normalized


def normalize_control_audit(control_audit: Any, fallback_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    fallback_summary = fallback_summary or {}
    fallback_front_answer = normalize_front_answer(fallback_summary.get("frontAnswer"), fallback_summary)
    fallback_opinion = normalize_summarizer_opinion(fallback_summary.get("summarizerOpinion"), fallback_summary)

    accepted_points: List[str] = []
    fallback_pressure = truncate_text(fallback_front_answer.get("adversarialPressure", ""), 220)
    if fallback_pressure and fallback_pressure != "No strong adversarial pressure was captured.":
        accepted_points.append(fallback_pressure)

    normalized = {
        "leadDraft": truncate_text(fallback_front_answer.get("leadDirection", ""), 280)
        or truncate_text(fallback_front_answer.get("stance", ""), 280)
        or "No lead draft was captured.",
        "integrationQuestion": (
            "Does this adversarial point improve correctness, scope, safety, or usefulness, or does it only pull the answer off course?"
        ),
        "courseDecision": "maintain",
        "courseDecisionReason": (
            "Default to maintaining the lead direction unless adversarial pressure materially changes correctness, safety, or viability."
        ),
        "contributionAssessments": (
            [
                {
                    "contribution": fallback_pressure,
                    "value": "high",
                    "effect": "qualify",
                    "reason": "This pressure appears strong enough to narrow or condition the lead answer without replacing it outright.",
                }
            ]
            if accepted_points
            else []
        ),
        "acceptedAdversarialPoints": limit_string_list(accepted_points, 3, 220),
        "rejectedAdversarialPoints": [],
        "heldOutConcerns": limit_string_list(fallback_summary.get("claimsNeedingVerification", []), 3, 220),
        "selfCheck": (
            truncate_text(fallback_opinion.get("integrationMode", ""), 320)
            or "Before speaking, I checked that the final answer still matched the lead direction and the user's actual request."
        ),
    }

    if isinstance(control_audit, dict):
        lead_draft = truncate_text(control_audit.get("leadDraft", ""), 280)
        integration_question = truncate_text(control_audit.get("integrationQuestion", ""), 260)
        course_decision = normalize_course_decision(control_audit.get("courseDecision"), normalized["courseDecision"])
        course_reason = truncate_text(control_audit.get("courseDecisionReason", ""), 320)
        contribution_assessments = normalize_contribution_assessments(control_audit.get("contributionAssessments", []))
        accepted = limit_string_list(control_audit.get("acceptedAdversarialPoints", []), 3, 220)
        rejected = limit_string_list(control_audit.get("rejectedAdversarialPoints", []), 3, 220)
        held_out = limit_string_list(control_audit.get("heldOutConcerns", []), 3, 220)
        self_check = truncate_text(control_audit.get("selfCheck", ""), 360)
        if lead_draft:
            normalized["leadDraft"] = lead_draft
        if integration_question:
            normalized["integrationQuestion"] = integration_question
        normalized["courseDecision"] = course_decision
        if course_reason:
            normalized["courseDecisionReason"] = course_reason
        normalized["contributionAssessments"] = contribution_assessments
        normalized["acceptedAdversarialPoints"] = accepted
        normalized["rejectedAdversarialPoints"] = rejected
        normalized["heldOutConcerns"] = held_out
        if self_check:
            normalized["selfCheck"] = self_check

    if not normalized["contributionAssessments"]:
        derived_assessments: List[Dict[str, str]] = []
        for point in normalized["acceptedAdversarialPoints"]:
            derived_assessments.append(
                {
                    "contribution": point,
                    "value": "high",
                    "effect": "qualify" if normalized["courseDecision"] != "maintain" else "support",
                    "reason": "This point survived the control gate and materially improved the final answer.",
                }
            )
        for point in normalized["rejectedAdversarialPoints"]:
            derived_assessments.append(
                {
                    "contribution": point,
                    "value": "low",
                    "effect": "reject",
                    "reason": "This point was judged too weak or too distracting to change the course.",
                }
            )
        normalized["contributionAssessments"] = derived_assessments[:4]

    return normalized


def normalize_dynamic_lane_decision(decision: Any) -> Dict[str, Any]:
    normalized = {
        "shouldSpawn": False,
        "suggestedLaneTypes": [],
        "reason": "No additional adversarial lane is needed yet.",
        "requiredPressure": "",
        "temperature": "",
        "instruction": "",
    }
    if not isinstance(decision, dict):
        return normalized
    normalized["shouldSpawn"] = bool(decision.get("shouldSpawn", normalized["shouldSpawn"]))
    normalized["suggestedLaneTypes"] = normalize_lane_type_list(decision.get("suggestedLaneTypes", []), False, 2)
    reason = truncate_text(decision.get("reason", ""), 320)
    required_pressure = truncate_text(decision.get("requiredPressure", ""), 240)
    instruction = truncate_text(decision.get("instruction", ""), 320)
    temperature = str(decision.get("temperature", "")).strip().lower().replace("-", "_").replace(" ", "_")
    if reason:
        normalized["reason"] = reason
    if required_pressure:
        normalized["requiredPressure"] = required_pressure
    if instruction:
        normalized["instruction"] = instruction
    if temperature in WORKER_TEMPERATURE_CATALOG:
        normalized["temperature"] = temperature
    if not normalized["suggestedLaneTypes"]:
        normalized["shouldSpawn"] = False
    return normalized


def dynamic_lane_overlap_key(lane_type: Any) -> str:
    candidate = str(lane_type or "").strip().lower()
    return DYNAMIC_LANE_OVERLAP_GROUPS.get(candidate, candidate)


def infer_dynamic_lane_types_from_text(*parts: Any, max_items: int = 4) -> List[str]:
    combined = " ".join(str(part or "").strip().lower() for part in parts if str(part or "").strip())
    if not combined:
        return []
    tokens = {token for token in re.findall(r"[a-z0-9_]+", combined) if token}
    inferred: List[str] = []
    for keywords, lane_types in DYNAMIC_LANE_KEYWORD_HINTS:
        keyword_list = [keyword for keyword in keywords.split() if keyword]
        if not keyword_list:
            continue
        if not any(keyword in tokens for keyword in keyword_list):
            continue
        for lane_type in lane_types:
            if lane_type in WORKER_TYPE_CATALOG and lane_type not in inferred:
                inferred.append(lane_type)
                if len(inferred) >= max_items:
                    return inferred
    return inferred[:max_items]


def normalize_dynamic_lane_resolution(value: Any) -> Dict[str, Any]:
    normalized = {
        "status": "not_requested",
        "requestedLaneTypes": [],
        "inferredLaneTypes": [],
        "selectedLaneType": "",
        "selectedBecause": "",
        "activationRound": 0,
        "spawnedWorkerId": "",
        "rejectedLaneTypes": [],
    }
    if not isinstance(value, dict):
        return normalized
    status = str(value.get("status", normalized["status"])).strip().lower().replace("-", "_").replace(" ", "_")
    if status in {
        "not_requested",
        "spawned",
        "rejected_duplicate",
        "rejected_covered",
        "rejected_invalid",
        "rejected_unresolved",
    }:
        normalized["status"] = status
    normalized["requestedLaneTypes"] = normalize_lane_type_list(value.get("requestedLaneTypes", []), False, 4)
    normalized["inferredLaneTypes"] = normalize_lane_type_list(value.get("inferredLaneTypes", []), False, 4)
    selected_lane_type = str(value.get("selectedLaneType", "") or "").strip().lower()
    if selected_lane_type in WORKER_TYPE_CATALOG:
        normalized["selectedLaneType"] = selected_lane_type
    normalized["selectedBecause"] = truncate_text(value.get("selectedBecause", ""), 320)
    normalized["activationRound"] = max(0, int(value.get("activationRound", 0) or 0))
    spawned_worker_id = str(value.get("spawnedWorkerId", "") or "").strip().upper()
    if re.match(r"^[A-Z]$", spawned_worker_id):
        normalized["spawnedWorkerId"] = spawned_worker_id
    rejected: List[Dict[str, str]] = []
    raw_rejected = value.get("rejectedLaneTypes", [])
    if isinstance(raw_rejected, list):
        for entry in raw_rejected[:6]:
            if not isinstance(entry, dict):
                continue
            lane_type = str(entry.get("laneType", "") or "").strip().lower()
            reason = truncate_text(entry.get("reason", ""), 220)
            if lane_type not in WORKER_TYPE_CATALOG or not reason:
                continue
            rejected.append({"laneType": lane_type, "reason": reason})
    normalized["rejectedLaneTypes"] = rejected
    return normalized


def normalize_review_trace(review_trace: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(review_trace, list):
        return normalized
    for entry in review_trace:
        if not isinstance(entry, dict):
            continue
        topic = truncate_text(entry.get("topic", ""), 180)
        judgment = truncate_text(entry.get("judgment", ""), 260)
        because = truncate_text(entry.get("because", ""), 360)
        if not topic or not judgment:
            continue
        normalized.append(
            {
                "topic": topic,
                "judgment": judgment,
                "because": because,
                "supportingLineRefs": normalize_line_ref_list(entry.get("supportingLineRefs", [])),
                "challengingLineRefs": normalize_line_ref_list(entry.get("challengingLineRefs", [])),
                "openQuestions": limit_string_list(entry.get("openQuestions", []), 3, 220),
            }
        )
    return normalized


def normalize_summary_line_catalog(catalog: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(catalog, list):
        return normalized
    seen: Dict[str, bool] = {}
    for entry in catalog:
        if not isinstance(entry, dict):
            continue
        ref = str(entry.get("ref", "")).strip()
        text = truncate_text(entry.get("text", ""), 320)
        if not ref or not text or ref in seen:
            continue
        seen[ref] = True
        normalized.append(
            {
                "ref": ref,
                "workerId": str(entry.get("workerId", "")).strip().upper(),
                "label": truncate_text(entry.get("label", ""), 120),
                "role": truncate_text(entry.get("role", ""), 40),
                "step": max(0, int(entry.get("step", 0) or 0)),
                "kind": truncate_text(entry.get("kind", ""), 60),
                "text": text,
                "supportLevel": truncate_text(entry.get("supportLevel", ""), 32),
                "sourceUrls": limit_url_list(entry.get("sourceUrls", []), 8),
            }
        )
    return normalized


@dataclass
class OpenAIResult:
    provider: str
    parsed: Dict[str, Any]
    response: Dict[str, Any]
    response_id: str
    output_text: Optional[str]
    thinking_text: Optional[str]
    web_search_queries: List[str]
    web_search_sources: List[str]
    url_citations: List[str]
    requested_max_output_tokens: int
    effective_max_output_tokens: int
    attempts: List[int]
    recovered_from_incomplete: bool
    executed_tools: List[Dict[str, Any]]
    auth_assignment: Optional[Dict[str, Any]]
    auth_failover_history: List[Dict[str, Any]]


class LoopRuntime:
    def __init__(self, root: str | Path, auth_path: str | Path | None = None) -> None:
        self.root = Path(root).resolve()
        self.data_path = self.root / "data"
        self.tasks_path = self.data_path / "tasks"
        self.checkpoints_path = self.data_path / "checkpoints"
        self.outputs_path = self.data_path / "outputs"
        self.sessions_path = self.data_path / "sessions"
        self.jobs_path = self.data_path / "jobs"
        self.locks_path = self.data_path / "locks"
        self.state_path = self.data_path / "state.json"
        self.events_path = self.data_path / "events.jsonl"
        self.steps_path = self.data_path / "steps.jsonl"
        self.auth_path = Path(auth_path).resolve() if auth_path else (self.root / "Auth.txt")

    def ensure_data_paths(self) -> None:
        for path in (
            self.data_path,
            self.tasks_path,
            self.checkpoints_path,
            self.outputs_path,
            self.sessions_path,
            self.jobs_path,
            self.locks_path,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write_json_file(self.state_path, default_state())
        if not self.events_path.exists():
            self.events_path.write_text("", encoding="utf-8")
        if not self.steps_path.exists():
            self.steps_path.write_text("", encoding="utf-8")

    def _write_json_file(self, path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _read_json_file(self, path: Path, fallback: Any) -> Any:
        if not path.exists():
            return fallback
        raw = path.read_text(encoding="utf-8").lstrip("\ufeff")
        if not raw.strip():
            return fallback
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return fallback
        return data

    def _lock_path(self, name: str = "loop") -> Path:
        return self.locks_path / f"{name}.lock"

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_path / f"{job_id}.json"

    def _remove_tree(self, path: Path) -> None:
        if not path.exists():
            return
        if path.is_file() or path.is_symlink():
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        shutil.rmtree(path, ignore_errors=True)

    @contextmanager
    def with_lock(self, name: str = "loop", timeout_seconds: float = 15.0, stale_seconds: int = 45):
        self.ensure_data_paths()
        lock_path = self._lock_path(name)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                os.mkdir(lock_path)
                owner = {"pid": os.getpid(), "ts": utc_now()}
                self._write_json_file(lock_path / "owner.json", owner)
                break
            except FileExistsError:
                try:
                    mtime = lock_path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if (time.time() - mtime) > stale_seconds:
                    self._remove_tree(lock_path)
                    continue
                time.sleep(0.1)
        else:
            raise RuntimeErrorWithCode("Timed out acquiring loop lock.", 500)
        try:
            yield
        finally:
            self._remove_tree(lock_path)

    def read_state_unlocked(self) -> Dict[str, Any]:
        self.ensure_data_paths()
        if metadata_store.postgres_enabled(self.root):
            data = metadata_store.read_state_payload(self.root, default_state())
        else:
            data = self._read_json_file(self.state_path, default_state())
        if not isinstance(data, dict):
            data = default_state()
        return self.normalize_state(data)

    def read_state(self) -> Dict[str, Any]:
        with self.with_lock():
            return self.read_state_unlocked()

    def write_state_unlocked(self, state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self.normalize_state(state)
        normalized["lastUpdated"] = utc_now()
        if metadata_store.postgres_enabled(self.root):
            metadata_store.write_state_payload(self.root, normalized)
        else:
            self._write_json_file(self.state_path, normalized)
        return normalized

    def write_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        with self.with_lock():
            return self.write_state_unlocked(state)

    def mutate_state(self, callback) -> Dict[str, Any]:
        with self.with_lock():
            state = self.read_state_unlocked()
            next_state = callback(state)
            if not isinstance(next_state, dict):
                next_state = state
            return self.write_state_unlocked(next_state)

    def append_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        line = json.dumps({"ts": utc_now(), "type": event_type, "payload": payload}, ensure_ascii=False)
        with self.with_lock():
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def append_step(self, stage: str, message: str, context: Dict[str, Any]) -> None:
        line = json.dumps({"ts": utc_now(), "stage": stage, "message": message, "context": context}, ensure_ascii=False)
        with self.with_lock():
            with self.steps_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def read_job_unlocked(self, job_id: str) -> Optional[Dict[str, Any]]:
        normalized_job_id = str(job_id or "").strip()
        if metadata_store.postgres_enabled(self.root):
            data = metadata_store.read_job_payload(self.root, normalized_job_id)
            return data if isinstance(data, dict) else None
        path = self._job_path(normalized_job_id)
        if not path.exists():
            return None
        data = self._read_json_file(path, None)
        return data if isinstance(data, dict) else None

    def write_job_unlocked(self, job: Dict[str, Any]) -> Dict[str, Any]:
        job_id = str(job.get("jobId", "")).strip()
        if not job_id:
            raise RuntimeErrorWithCode("Job payload is missing jobId.", 500)
        if metadata_store.postgres_enabled(self.root):
            metadata_store.write_job_payload(self.root, job)
        else:
            path = self._job_path(job_id)
            self._write_json_file(path, job)
        return job

    def write_task_snapshot_unlocked(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(task.get("taskId") or "").strip()
        if not task_id:
            raise RuntimeErrorWithCode("Task payload is missing taskId.", 500)
        if metadata_store.postgres_enabled(self.root):
            metadata_store.write_task_payload(self.root, task)
        else:
            self._write_json_file(self.tasks_path / f"{task_id}.json", task)
        return task

    def mutate_job(self, job_id: str, callback) -> Optional[Dict[str, Any]]:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return None
        with self.with_lock():
            existing = self.read_job_unlocked(normalized_job_id)
            next_job = callback(existing)
            if next_job is None:
                return existing
            if not isinstance(next_job, dict):
                return existing
            return self.write_job_unlocked(next_job)

    def heartbeat_dispatch_job(self, job_id: str, message: Optional[str] = None) -> Optional[Dict[str, Any]]:
        timestamp = utc_now()

        def updater(existing: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            if not isinstance(existing, dict):
                return existing
            status = str(existing.get("status", ""))
            if status not in {"queued", "running"}:
                return existing
            updated = dict(existing)
            updated["lastHeartbeatAt"] = timestamp
            if message:
                updated["lastMessage"] = message
            return updated

        return self.mutate_job(job_id, updater)

    def normalize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = default_state()
        normalized["activeTask"] = state.get("activeTask")
        normalized["draft"] = state.get("draft") if isinstance(state.get("draft"), dict) else normalized["draft"]
        normalized["commander"] = state.get("commander") if isinstance(state.get("commander"), dict) else None
        normalized["commanderReview"] = state.get("commanderReview") if isinstance(state.get("commanderReview"), dict) else None
        normalized["summary"] = state.get("summary")
        normalized["memoryVersion"] = int(state.get("memoryVersion", 0) or 0)
        normalized["usage"] = normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
        normalized["lastUpdated"] = state.get("lastUpdated") or utc_now()
        workers = state.get("workers")
        if isinstance(workers, dict):
            normalized["workers"] = {str(key): value for key, value in workers.items() if str(key).strip()}
        loop = state.get("loop")
        if isinstance(loop, dict):
            normalized["loop"] = {**default_loop_state(), **loop}
        return normalized

    def get_api_key(self) -> Optional[str]:
        assignment = self.get_api_key_assignment()
        return str(assignment.get("apiKey")) if assignment else None

    def load_api_keys(self) -> List[str]:
        return self.load_api_key_pool_state()["keys"]

    def load_api_key_pool_state(self) -> Dict[str, Any]:
        topology = deployment_topology(self.root)
        backend = topology.secret_backend
        if backend == "env":
            status = env_secret_status()
            return {
                "backend": "env",
                "keys": normalize_string_array_preserve_items(status.get("keys", [])),
                "managed": True,
                "writable": False,
                "configured": bool(status.get("configured")),
                "ready": bool(status.get("ready")),
                "failureMode": status.get("failureMode"),
                "failureDetail": str(status.get("detail") or ""),
            }
        if backend == "external":
            status = external_secret_status(self.root)
            return {
                "backend": "external",
                "keys": normalize_string_array_preserve_items(status.get("keys", [])),
                "managed": True,
                "writable": False,
                "configured": bool(status.get("configured")),
                "ready": bool(status.get("ready")),
                "failureMode": status.get("failureMode"),
                "failureDetail": str(status.get("detail") or ""),
            }
        if backend == "docker_secret":
            secret_path = self.auth_path
            if not secret_path.is_file():
                return {
                    "backend": "docker_secret",
                    "keys": [],
                    "managed": True,
                    "writable": False,
                    "configured": bool(secret_path),
                    "ready": False,
                    "failureMode": "misconfigured",
                    "failureDetail": f"Mounted secret file not found at {secret_path}.",
                }
            keys = normalize_string_array_preserve_items(secret_path.read_text(encoding="utf-8", errors="replace").splitlines())
            return {
                "backend": "docker_secret",
                "keys": keys,
                "managed": True,
                "writable": False,
                "configured": True,
                "ready": len(keys) > 0,
                "failureMode": None if keys else "empty",
                "failureDetail": f"Using mounted secret file at {secret_path}." if keys else f"Mounted secret file at {secret_path} is empty.",
            }
        local_path = self.auth_path
        if not local_path.is_file():
            return {
                "backend": "local_file",
                "keys": [],
                "managed": False,
                "writable": True,
                "configured": True,
                "ready": False,
                "failureMode": "empty",
                "failureDetail": f"Local fallback secret file not found at {local_path}.",
            }
        keys = normalize_string_array_preserve_items(local_path.read_text(encoding="utf-8", errors="replace").splitlines())
        return {
            "backend": "local_file",
            "keys": keys,
            "managed": False,
            "writable": True,
            "configured": True,
            "ready": len(keys) > 0,
            "failureMode": None if keys else "empty",
            "failureDetail": f"Using local fallback secret file at {local_path}." if keys else f"Local fallback secret file at {local_path} is empty.",
        }

    def raise_if_managed_secret_backend_unavailable(self, stage: str, task_id: str, model: str, target: str) -> None:
        auth_state = self.load_api_key_pool_state()
        if not bool(auth_state.get("managed")) or auth_state.get("keys"):
            return
        failure_mode = str(auth_state.get("failureMode") or "empty")
        detail = str(auth_state.get("failureDetail") or f"{auth_state.get('backend')} returned no usable keys.")
        self.append_step(
            stage,
            "Managed secret backend is unavailable; refusing mock fallback for live execution.",
            {
                "taskId": task_id,
                "target": target,
                "model": model,
                "secretBackend": auth_state.get("backend"),
                "failureMode": failure_mode,
                "failureDetail": detail,
            },
        )
        status_code = 503 if failure_mode in {"misconfigured", "unreachable"} else 409
        raise RuntimeErrorWithCode(
            f"Live run requires the {auth_state.get('backend')} secret backend, but it is {failure_mode}: {detail}",
            status_code,
        )

    def build_api_key_assignments(
        self,
        target: str = "generic",
        task: Optional[Dict[str, Any]] = None,
        round_number: Optional[int] = None,
        salt: str = "",
    ) -> List[Dict[str, Any]]:
        keys = self.load_api_keys()
        if not keys:
            return []
        normalized_target = normalize_auth_target(target)
        target_order = self.auth_target_order(task, [normalized_target])
        position_index = target_order.index(normalized_target) if normalized_target in target_order else 0
        rotation_offset = self.auth_rotation_offset(len(keys), task, round_number, salt)
        start_index = (position_index + rotation_offset) % len(keys)
        assignments: List[Dict[str, Any]] = []
        for failover_index in range(len(keys)):
            key_index = (start_index + failover_index) % len(keys)
            api_key = keys[key_index]
            assignments.append(
                {
                    "apiKey": api_key,
                    "target": normalized_target,
                    "positionSlot": position_index + 1,
                    "keySlot": key_index + 1,
                    "poolSize": len(keys),
                    "rotationOffset": rotation_offset,
                    "reused": position_index >= len(keys),
                    "last4": api_key[-4:] if len(api_key) >= 4 else api_key,
                    "masked": mask_api_key(api_key),
                    "preferred": failover_index == 0,
                    "failoverIndex": failover_index,
                }
            )
        return assignments

    def auth_target_order(self, task: Optional[Dict[str, Any]] = None, extra_targets: Optional[Iterable[str]] = None) -> List[str]:
        ordered: List[str] = []
        seen: Dict[str, bool] = {}

        def add_target(value: Any) -> None:
            normalized = normalize_auth_target(value)
            if normalized and normalized not in seen:
                seen[normalized] = True
                ordered.append(normalized)

        if isinstance(task, dict):
            add_target("commander")
            for worker in task_workers(task):
                add_target(worker.get("id"))
            add_target("commander_review")
            add_target("summarizer")
        for target in extra_targets or []:
            add_target(target)
        if not ordered:
            add_target("generic")
        return ordered

    def auth_rotation_offset(self, pool_size: int, task: Optional[Dict[str, Any]] = None, round_number: Optional[int] = None, salt: str = "") -> int:
        if pool_size <= 1:
            return 0
        task_id = str((task or {}).get("taskId", "")).strip() if isinstance(task, dict) else ""
        seed_source = task_id or str(salt or "").strip()
        seed_value = 0
        if seed_source:
            seed_value = int(hashlib.md5(seed_source.encode("utf-8")).hexdigest()[:8], 16)
        round_offset = max(0, int(round_number or 1) - 1)
        return (seed_value + round_offset) % pool_size

    def get_api_key_assignment(
        self,
        target: str = "generic",
        task: Optional[Dict[str, Any]] = None,
        round_number: Optional[int] = None,
        salt: str = "",
    ) -> Optional[Dict[str, Any]]:
        assignments = self.build_api_key_assignments(target, task, round_number, salt)
        return dict(assignments[0]) if assignments else None

    def budget_scope_key(self, target: Optional[str]) -> Optional[str]:
        normalized = normalize_auth_target(target)
        if normalized in {"commander", "commander_review"}:
            return "commander"
        if normalized == "summarizer":
            return "summarizer"
        if re.match(r"^[A-Z]$", normalized):
            return "worker"
        return None

    def get_budget_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_budget_config(task_runtime.get("budget") if isinstance(task_runtime.get("budget"), dict) else {})

    def get_budget_limits(self, task: Dict[str, Any], target: Optional[str] = None) -> Dict[str, Any]:
        budget = self.get_budget_config(task)
        scope_key = self.budget_scope_key(target)
        if scope_key:
            target_budget = budget.get("targets", {}).get(scope_key)
            if isinstance(target_budget, dict):
                return normalize_budget_limits(target_budget, budget)
        return normalize_budget_limits(budget, default_budget_config())

    def get_task_runtime(
        self,
        task: Dict[str, Any],
        model_override: Optional[str] = None,
        budget_target: Optional[str] = None,
        provider_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        runtime = {
            "executionMode": "live",
            "provider": DEFAULT_PROVIDER_ID,
            "model": DEFAULT_MODEL_ID,
            "reasoningEffort": "low",
            "maxOutputTokens": default_budget_config()["maxOutputTokens"],
            "research": default_research_config(),
            "localFiles": default_local_file_tool_config(),
            "githubTools": default_github_tool_config(),
            "dynamicSpinup": default_dynamic_spinup_config(),
            "vetting": default_vetting_config(),
        }
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        if task_runtime:
            execution_mode = str(task_runtime.get("executionMode", runtime["executionMode"])).strip()
            if execution_mode in {"live", "mock"}:
                runtime["executionMode"] = execution_mode
            reasoning_effort = str(task_runtime.get("reasoningEffort", runtime["reasoningEffort"])).strip()
            if reasoning_effort in {"none", "low", "medium", "high", "xhigh"}:
                runtime["reasoningEffort"] = reasoning_effort
            runtime["provider"] = normalize_provider_id(task_runtime.get("provider"), runtime["provider"])
            runtime["model"] = normalize_model_id(
                task_runtime.get("model"),
                default_model_for_provider(runtime["provider"]),
                runtime["provider"],
            )
            runtime["research"] = normalize_research_config(task_runtime.get("research") if isinstance(task_runtime.get("research"), dict) else {})
            runtime["localFiles"] = normalize_local_file_tool_config(task_runtime.get("localFiles") if isinstance(task_runtime.get("localFiles"), dict) else {})
            runtime["githubTools"] = normalize_github_tool_config(task_runtime.get("githubTools") if isinstance(task_runtime.get("githubTools"), dict) else {})
            runtime["dynamicSpinup"] = normalize_dynamic_spinup_config(task_runtime.get("dynamicSpinup") if isinstance(task_runtime.get("dynamicSpinup"), dict) else {})
            runtime["vetting"] = normalize_vetting_config(task_runtime.get("vetting") if isinstance(task_runtime.get("vetting"), dict) else {})
        runtime["maxOutputTokens"] = self.get_budget_limits(task, budget_target)["maxOutputTokens"]
        if provider_override:
            runtime["provider"] = normalize_provider_id(provider_override, runtime["provider"])
        if model_override:
            runtime["model"] = normalize_model_id(model_override, runtime["model"], runtime["provider"])
        return runtime

    def provider_uses_api_key_pool(self, provider: Optional[str]) -> bool:
        return normalize_provider_id(provider, DEFAULT_PROVIDER_ID) == "openai"

    def provider_requires_api_key(self, provider: Optional[str]) -> bool:
        return self.provider_uses_api_key_pool(provider)

    def provider_auth_assignments(
        self,
        provider: Optional[str],
        target: str = "generic",
        task: Optional[Dict[str, Any]] = None,
        round_number: Optional[int] = None,
        salt: str = "",
    ) -> List[Dict[str, Any]]:
        if not self.provider_uses_api_key_pool(provider):
            return []
        return self.build_api_key_assignments(target, task, round_number, salt)

    def provider_live_api_key(
        self,
        provider: Optional[str],
        auth_assignments: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
        if normalized_provider == "openai":
            assignment = auth_assignments[0] if auth_assignments else None
            return str(assignment.get("apiKey")) if isinstance(assignment, dict) else ""
        if normalized_provider == "ollama":
            return self.ollama_api_key()
        return ""

    def live_auth_meta(self, provider: Optional[str], assignment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        meta = auth_assignment_meta(assignment) or {}
        meta["provider"] = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
        return meta

    def get_research_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_research_config(task_runtime.get("research") if isinstance(task_runtime.get("research"), dict) else {})

    def get_local_file_tool_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_local_file_tool_config(task_runtime.get("localFiles") if isinstance(task_runtime.get("localFiles"), dict) else {})

    def get_github_tool_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_github_tool_config(task_runtime.get("githubTools") if isinstance(task_runtime.get("githubTools"), dict) else {})

    def get_dynamic_spinup_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_dynamic_spinup_config(task_runtime.get("dynamicSpinup") if isinstance(task_runtime.get("dynamicSpinup"), dict) else {})

    def get_vetting_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_vetting_config(task_runtime.get("vetting") if isinstance(task_runtime.get("vetting"), dict) else {})

    def get_model_pricing(self, model: str) -> Dict[str, Any]:
        resolved = normalize_model_id(model, DEFAULT_MODEL_ID, DEFAULT_PROVIDER_ID)
        pricing = MODEL_CATALOG.get(resolved, {"inputPer1M": 0.0, "cachedInputPer1M": 0.0, "outputPer1M": 0.0})
        return {"model": resolved, **pricing}

    def get_response_output_text(self, response: Dict[str, Any]) -> Optional[str]:
        if isinstance(response.get("message"), dict):
            content = response["message"].get("content")
            if content:
                return str(content)
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return str(content["text"])
        return None

    def get_response_thinking_text(self, response: Dict[str, Any]) -> Optional[str]:
        if isinstance(response.get("message"), dict):
            thinking = response["message"].get("thinking")
            if thinking:
                return str(thinking)
        return None

    def get_web_search_call_items(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [item for item in response.get("output", []) if isinstance(item, dict) and item.get("type") == "web_search_call"]

    def get_response_web_search_queries(self, response: Dict[str, Any]) -> List[str]:
        queries: Dict[str, bool] = {}
        for item in self.get_web_search_call_items(response):
            action = item.get("action") if isinstance(item.get("action"), dict) else {}
            query = action.get("query")
            if query:
                queries[str(query)] = True
            for value in action.get("queries", []) if isinstance(action.get("queries"), list) else []:
                if value:
                    queries[str(value)] = True
        return list(queries.keys())

    def get_response_web_search_sources(self, response: Dict[str, Any]) -> List[str]:
        urls: Dict[str, bool] = {}
        for item in self.get_web_search_call_items(response):
            action = item.get("action") if isinstance(item.get("action"), dict) else {}
            for source in action.get("sources", []) if isinstance(action.get("sources"), list) else []:
                if isinstance(source, dict) and source.get("url"):
                    urls[str(source["url"])] = True
        return list(urls.keys())

    def get_response_url_citations(self, response: Dict[str, Any]) -> List[str]:
        urls: Dict[str, bool] = {}
        for item in response.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                for annotation in content.get("annotations", []) if isinstance(content.get("annotations"), list) else []:
                    if isinstance(annotation, dict) and annotation.get("type") == "url_citation" and annotation.get("url"):
                        urls[str(annotation["url"])] = True
        return list(urls.keys())

    def is_path_within(self, candidate: Path, root: Path) -> bool:
        try:
            return candidate == root or root in candidate.parents
        except Exception:
            return False

    def repo_relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        if resolved == self.root:
            return "."
        try:
            return resolved.relative_to(self.root).as_posix() or "."
        except Exception:
            return resolved.as_posix()

    def is_sensitive_tool_path(self, value: Any) -> bool:
        return is_sensitive_repo_path(value)

    def assert_tool_path_not_sensitive(self, value: Any, tool_name: str) -> None:
        if self.is_sensitive_tool_path(value):
            raise RuntimeErrorWithCode(f"{tool_name} is blocked from accessing secret-shaped files or directories.", 403)

    def resolve_local_tool_roots(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        resolved_roots: List[Dict[str, Any]] = []
        seen: Dict[str, bool] = {}
        for entry in normalize_local_file_roots(config.get("roots", ["."])):
            candidate = (self.root / entry).resolve()
            if not candidate.exists():
                continue
            if not self.is_path_within(candidate, self.root):
                continue
            relative = self.repo_relative_path(candidate)
            if relative not in seen:
                seen[relative] = True
                resolved_roots.append({"id": relative, "path": candidate})
        if not resolved_roots:
            resolved_roots.append({"id": ".", "path": self.root})
        return resolved_roots

    def resolve_local_tool_path(
        self,
        requested_path: Any,
        config: Dict[str, Any],
        *,
        require_exists: bool = True,
        allow_file: bool = True,
        allow_dir: bool = True,
    ) -> tuple[Path, str]:
        candidate_text = str(requested_path or ".").strip().replace("\\", "/")
        if candidate_text in {"", ".", "./"}:
            candidate_text = "."
        if re.match(r"^[A-Za-z]:", candidate_text) or candidate_text.startswith("/"):
            raise RuntimeErrorWithCode("Local file tools only accept repo-relative paths.", 400)
        candidate_text = re.sub(r"^(\./)+", "", candidate_text).strip().strip("/")
        parts = [part for part in candidate_text.split("/") if part and part != "."]
        if ".." in parts:
            raise RuntimeErrorWithCode("Local file tools rejected a path traversal attempt.", 400)
        normalized = "/".join(parts) if parts else "."
        resolved = (self.root / normalized).resolve()
        if not self.is_path_within(resolved, self.root):
            raise RuntimeErrorWithCode("Local file tools only operate inside the workspace root.", 400)
        allowed = self.resolve_local_tool_roots(config)
        if not any(self.is_path_within(resolved, Path(root["path"])) for root in allowed):
            raise RuntimeErrorWithCode("Requested path is outside the allowed local file roots.", 403)
        if require_exists and not resolved.exists():
            raise RuntimeErrorWithCode(f"Local path not found: {normalized}", 404)
        if require_exists and resolved.is_file() and not allow_file:
            raise RuntimeErrorWithCode("Expected a directory path for this local file tool.", 400)
        if require_exists and resolved.is_dir() and not allow_dir:
            raise RuntimeErrorWithCode("Expected a file path for this local file tool.", 400)
        return resolved, self.repo_relative_path(resolved)

    def is_probably_text_file(self, path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            with path.open("rb") as handle:
                sample = handle.read(4096)
        except OSError:
            return False
        if b"\x00" in sample:
            return False
        return True

    def build_local_file_function_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        allowed_roots = ", ".join(normalize_local_file_roots(config.get("roots", ["."]))) or "."
        return [
            {
                "type": "function",
                "name": "local_list_dir",
                "description": f"List files and folders inside the local workspace. Only use repo-relative paths within these allowed roots: {allowed_roots}.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string", "description": "Repo-relative directory path to inspect. Use . for the workspace root."},
                        "max_entries": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                },
            },
            {
                "type": "function",
                "name": "local_read_file",
                "description": f"Read text from a local file inside the workspace. Only use repo-relative file paths within these allowed roots: {allowed_roots}.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string", "description": "Repo-relative file path to read."},
                        "start_line": {"type": "integer", "minimum": 1},
                        "end_line": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path"],
                },
            },
            {
                "type": "function",
                "name": "local_search_text",
                "description": f"Search local text files for a literal pattern inside the workspace. Only use repo-relative paths within these allowed roots: {allowed_roots}.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "pattern": {"type": "string", "description": "Literal text to search for."},
                        "path": {"type": "string", "description": "Optional repo-relative file or directory path to search under. Defaults to ."},
                        "max_matches": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["pattern"],
                },
            },
        ]

    def execute_local_file_tool_call(self, name: str, arguments: Dict[str, Any], config: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        allowed_roots = [str(entry["id"]) for entry in self.resolve_local_tool_roots(config)]
        if name == "local_list_dir":
            max_entries = min(50, max(1, int(arguments.get("max_entries", 20) or 20)))
            resolved, repo_path = self.resolve_local_tool_path(arguments.get("path", "."), config, allow_file=False, allow_dir=True)
            self.assert_tool_path_not_sensitive(repo_path, name)
            entries: List[Dict[str, Any]] = []
            filtered_sensitive = 0
            children = sorted(
                resolved.iterdir(),
                key=lambda item: (0 if item.is_dir() else 1, item.name.lower()),
            )
            for child in children[:max_entries]:
                child_repo_path = self.repo_relative_path(child)
                if self.is_sensitive_tool_path(child_repo_path):
                    filtered_sensitive += 1
                    continue
                item: Dict[str, Any] = {
                    "name": child.name,
                    "path": child_repo_path,
                    "kind": "dir" if child.is_dir() else "file",
                }
                if child.is_file():
                    try:
                        item["size"] = int(child.stat().st_size)
                    except OSError:
                        item["size"] = 0
                entries.append(item)
            result = {
                "path": repo_path,
                "allowedRoots": allowed_roots,
                "entries": entries,
                "truncated": len(children) > max_entries,
                "filteredSensitiveEntries": filtered_sensitive,
            }
            audit = {
                "name": name,
                "path": repo_path,
                "sources": [repo_path],
                "entryCount": len(entries),
                "filteredSensitiveEntries": filtered_sensitive,
                "truncated": bool(result["truncated"]),
                "summary": f"Listed {len(entries)} entries under {repo_path}.",
            }
            return result, audit

        if name == "local_read_file":
            resolved, repo_path = self.resolve_local_tool_path(arguments.get("path", ""), config, allow_file=True, allow_dir=False)
            self.assert_tool_path_not_sensitive(repo_path, name)
            if not self.is_probably_text_file(resolved):
                raise RuntimeErrorWithCode("Local read only supports probable text files.", 400)
            start_line = max(1, int(arguments.get("start_line", 1) or 1))
            end_line = max(start_line, int(arguments.get("end_line", start_line + 199) or (start_line + 199)))
            end_line = min(end_line, start_line + 399)
            numbered_lines: List[str] = []
            with resolved.open("r", encoding="utf-8", errors="replace") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if line_number < start_line:
                        continue
                    if line_number > end_line:
                        break
                    numbered_lines.append(f"{line_number}:{line.rstrip()}")
            content = "\n".join(numbered_lines)
            result = {
                "path": repo_path,
                "allowedRoots": allowed_roots,
                "startLine": start_line,
                "endLine": start_line + max(0, len(numbered_lines) - 1),
                "lineCount": len(numbered_lines),
                "content": content,
                "truncated": len(numbered_lines) >= (end_line - start_line + 1),
            }
            audit = {
                "name": name,
                "path": repo_path,
                "sources": [repo_path],
                "lineCount": len(numbered_lines),
                "bytesRead": len(content.encode("utf-8")),
                "truncated": bool(result["truncated"]),
                "summary": f"Read {len(numbered_lines)} lines from {repo_path}.",
            }
            return result, audit

        if name == "local_search_text":
            pattern = str(arguments.get("pattern", "") or "").strip()
            if not pattern:
                raise RuntimeErrorWithCode("local_search_text requires a non-empty pattern.", 400)
            max_matches = min(20, max(1, int(arguments.get("max_matches", 12) or 12)))
            resolved, repo_path = self.resolve_local_tool_path(arguments.get("path", "."), config, allow_file=True, allow_dir=True)
            self.assert_tool_path_not_sensitive(repo_path, name)
            candidates: List[Path] = [resolved] if resolved.is_file() else [path for path in resolved.rglob("*") if path.is_file()]
            matches: List[Dict[str, Any]] = []
            source_paths: Dict[str, bool] = {}
            files_scanned = 0
            filtered_sensitive = 0
            pattern_lower = pattern.lower()
            for file_path in candidates:
                if len(matches) >= max_matches:
                    break
                relative = self.repo_relative_path(file_path)
                if self.is_sensitive_tool_path(relative):
                    filtered_sensitive += 1
                    continue
                if not self.is_probably_text_file(file_path):
                    continue
                files_scanned += 1
                try:
                    with file_path.open("r", encoding="utf-8", errors="replace") as handle:
                        for line_number, line in enumerate(handle, start=1):
                            if pattern_lower not in line.lower():
                                continue
                            source_paths[relative] = True
                            matches.append(
                                {
                                    "path": relative,
                                    "line": line_number,
                                    "text": truncate_text(line.strip(), 240),
                                }
                            )
                            if len(matches) >= max_matches:
                                break
                except OSError:
                    continue
            result = {
                "pattern": pattern,
                "path": repo_path,
                "allowedRoots": allowed_roots,
                "matches": matches,
                "filesScanned": files_scanned,
                "truncated": len(matches) >= max_matches,
                "filteredSensitiveFiles": filtered_sensitive,
            }
            audit = {
                "name": name,
                "path": repo_path,
                "sources": list(source_paths.keys())[:10],
                "matchCount": len(matches),
                "filesScanned": files_scanned,
                "filteredSensitiveFiles": filtered_sensitive,
                "truncated": bool(result["truncated"]),
                "summary": f"Found {len(matches)} matches for '{truncate_text(pattern, 80)}' under {repo_path}.",
            }
            return result, audit

        raise RuntimeErrorWithCode(f"Unsupported local tool: {name}", 400)

    def get_github_token(self) -> Optional[str]:
        for env_name in ("GITHUB_TOKEN", "GH_TOKEN"):
            value = str(os.environ.get(env_name, "") or "").strip()
            if value:
                return value
        return None

    def github_request_json(self, url: str) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ParaLLM/1.0",
        }
        token = self.get_github_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=60) as handle:
                return json.loads(handle.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body_text = error.read().decode("utf-8", errors="replace")
            raise RuntimeErrorWithCode(f"GitHub API request failed: HTTP {error.code} | {body_text}", error.code)
        except Exception as error:
            raise RuntimeErrorWithCode(f"GitHub API request failed: {error}", 500)

    def resolve_github_repo(self, requested_repo: Any, config: Dict[str, Any]) -> str:
        candidate = str(requested_repo or "").strip().lower()
        candidate = re.sub(r"^https?://github\.com/", "", candidate, flags=re.IGNORECASE).strip().strip("/")
        if not candidate:
            raise RuntimeErrorWithCode("GitHub tools require a repository like owner/repo.", 400)
        if not re.match(r"^[a-z0-9_.-]+/[a-z0-9_.-]+$", candidate):
            raise RuntimeErrorWithCode("GitHub repo must be in owner/repo form.", 400)
        allowed = normalize_github_repos(config.get("repos", []))
        if candidate not in allowed:
            raise RuntimeErrorWithCode("Requested GitHub repo is outside the allowed repo list.", 403)
        return candidate

    def github_api_contents_url(self, repo: str, path: str = "", ref: str = "") -> str:
        cleaned_path = str(path or "").strip().strip("/")
        suffix = f"/{quote(cleaned_path, safe='/')}" if cleaned_path else ""
        ref_value = str(ref or "HEAD").strip() or "HEAD"
        return f"https://api.github.com/repos/{repo}/contents{suffix}?ref={quote(ref_value, safe='')}"

    def github_html_blob_url(self, repo: str, ref: str, path: str) -> str:
        cleaned_path = str(path or "").strip().strip("/")
        ref_value = str(ref or "HEAD").strip() or "HEAD"
        if not cleaned_path:
            return f"https://github.com/{repo}/tree/{quote(ref_value, safe='')}"
        return f"https://github.com/{repo}/blob/{quote(ref_value, safe='')}/{quote(cleaned_path, safe='/')}"

    def github_html_tree_url(self, repo: str, ref: str, path: str = "") -> str:
        cleaned_path = str(path or "").strip().strip("/")
        ref_value = str(ref or "HEAD").strip() or "HEAD"
        base = f"https://github.com/{repo}/tree/{quote(ref_value, safe='')}"
        if not cleaned_path:
            return base
        return base + "/" + quote(cleaned_path, safe="/")

    def build_github_function_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        allowed_repos = ", ".join(normalize_github_repos(config.get("repos", []))) or "none"
        return [
            {
                "type": "function",
                "name": "github_list_paths",
                "description": f"List files or folders in an allowed public GitHub repo. Only use repos from this allowlist: {allowed_repos}.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "repo": {"type": "string", "description": "Repository in owner/repo form."},
                        "path": {"type": "string", "description": "Optional directory path inside the repo."},
                        "ref": {"type": "string", "description": "Optional branch, tag, or commit SHA."},
                        "max_entries": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "required": ["repo"],
                },
            },
            {
                "type": "function",
                "name": "github_read_file",
                "description": f"Read text from a file in an allowed public GitHub repo. Only use repos from this allowlist: {allowed_repos}.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "repo": {"type": "string"},
                        "path": {"type": "string"},
                        "ref": {"type": "string"},
                        "start_line": {"type": "integer", "minimum": 1},
                        "end_line": {"type": "integer", "minimum": 1},
                    },
                    "required": ["repo", "path"],
                },
            },
            {
                "type": "function",
                "name": "github_get_issue",
                "description": f"Fetch issue metadata and body from an allowed public GitHub repo. Only use repos from this allowlist: {allowed_repos}.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "repo": {"type": "string"},
                        "issue_number": {"type": "integer", "minimum": 1},
                    },
                    "required": ["repo", "issue_number"],
                },
            },
            {
                "type": "function",
                "name": "github_get_pull_request",
                "description": f"Fetch pull request metadata and body from an allowed public GitHub repo. Only use repos from this allowlist: {allowed_repos}.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "repo": {"type": "string"},
                        "pr_number": {"type": "integer", "minimum": 1},
                    },
                    "required": ["repo", "pr_number"],
                },
            },
            {
                "type": "function",
                "name": "github_get_commit",
                "description": f"Fetch commit metadata from an allowed public GitHub repo. Only use repos from this allowlist: {allowed_repos}.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "repo": {"type": "string"},
                        "ref": {"type": "string", "description": "Commit SHA or ref."},
                    },
                    "required": ["repo", "ref"],
                },
            },
        ]

    def execute_github_tool_call(self, name: str, arguments: Dict[str, Any], config: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        repo = self.resolve_github_repo(arguments.get("repo", ""), config)
        allowed_repos = normalize_github_repos(config.get("repos", []))
        if name == "github_list_paths":
            max_entries = min(50, max(1, int(arguments.get("max_entries", 20) or 20)))
            path = str(arguments.get("path", "") or "").strip().strip("/")
            self.assert_tool_path_not_sensitive(path or ".", name)
            ref = str(arguments.get("ref", "HEAD") or "HEAD").strip() or "HEAD"
            payload = self.github_request_json(self.github_api_contents_url(repo, path, ref))
            entries_payload = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
            entries: List[Dict[str, Any]] = []
            filtered_sensitive = 0
            for item in entries_payload:
                if not isinstance(item, dict):
                    continue
                item_path = str(item.get("path", ""))
                if self.is_sensitive_tool_path(item_path):
                    filtered_sensitive += 1
                    continue
                entries.append(
                    {
                        "name": str(item.get("name", "")),
                        "path": item_path,
                        "kind": str(item.get("type", "")),
                        "size": int(item.get("size", 0) or 0),
                        "htmlUrl": str(item.get("html_url", "")),
                    }
                )
                if len(entries) >= max_entries:
                    break
            result = {
                "repo": repo,
                "path": path or ".",
                "ref": ref,
                "allowedRepos": allowed_repos,
                "entries": entries,
                "truncated": len(entries_payload) > max_entries,
                "filteredSensitiveEntries": filtered_sensitive,
            }
            audit = {
                "name": name,
                "path": f"{repo}:{path or '.'}@{ref}",
                "sources": [self.github_html_tree_url(repo, ref, path)],
                "entryCount": len(entries),
                "filteredSensitiveEntries": filtered_sensitive,
                "truncated": bool(result["truncated"]),
                "summary": f"Listed {len(entries)} GitHub paths under {repo}:{path or '.'}@{ref}.",
            }
            return result, audit

        if name == "github_read_file":
            path = str(arguments.get("path", "") or "").strip().strip("/")
            if not path:
                raise RuntimeErrorWithCode("github_read_file requires a file path.", 400)
            self.assert_tool_path_not_sensitive(path, name)
            ref = str(arguments.get("ref", "HEAD") or "HEAD").strip() or "HEAD"
            payload = self.github_request_json(self.github_api_contents_url(repo, path, ref))
            if not isinstance(payload, dict) or str(payload.get("type", "")) != "file":
                raise RuntimeErrorWithCode("github_read_file expected a file path.", 400)
            size = int(payload.get("size", 0) or 0)
            if size > 200000:
                raise RuntimeErrorWithCode("github_read_file is limited to files smaller than 200 KB.", 400)
            encoded = str(payload.get("content", "") or "")
            try:
                decoded = base64.b64decode(encoded.encode("utf-8"), validate=False).decode("utf-8", errors="replace")
            except Exception:
                raise RuntimeErrorWithCode("Failed to decode GitHub file content.", 500)
            start_line = max(1, int(arguments.get("start_line", 1) or 1))
            end_line = max(start_line, int(arguments.get("end_line", start_line + 199) or (start_line + 199)))
            end_line = min(end_line, start_line + 399)
            numbered_lines: List[str] = []
            for line_number, line in enumerate(decoded.splitlines(), start=1):
                if line_number < start_line:
                    continue
                if line_number > end_line:
                    break
                numbered_lines.append(f"{line_number}:{line}")
            content = "\n".join(numbered_lines)
            result = {
                "repo": repo,
                "path": path,
                "ref": ref,
                "allowedRepos": allowed_repos,
                "startLine": start_line,
                "endLine": start_line + max(0, len(numbered_lines) - 1),
                "lineCount": len(numbered_lines),
                "content": content,
                "truncated": len(numbered_lines) >= (end_line - start_line + 1),
            }
            audit = {
                "name": name,
                "path": f"{repo}:{path}@{ref}",
                "sources": [str(payload.get("html_url", "")) or self.github_html_blob_url(repo, ref, path)],
                "lineCount": len(numbered_lines),
                "bytesRead": len(content.encode("utf-8")),
                "truncated": bool(result["truncated"]),
                "summary": f"Read {len(numbered_lines)} lines from {repo}:{path}@{ref}.",
            }
            return result, audit

        if name == "github_get_issue":
            issue_number = max(1, int(arguments.get("issue_number", 0) or 0))
            payload = self.github_request_json(f"https://api.github.com/repos/{repo}/issues/{issue_number}")
            if not isinstance(payload, dict):
                raise RuntimeErrorWithCode("GitHub issue payload was malformed.", 500)
            result = {
                "repo": repo,
                "issueNumber": issue_number,
                "allowedRepos": allowed_repos,
                "title": str(payload.get("title", "")),
                "state": str(payload.get("state", "")),
                "body": truncate_text(payload.get("body", ""), 4000),
                "labels": [str(item.get("name", "")) for item in payload.get("labels", []) if isinstance(item, dict)],
                "htmlUrl": str(payload.get("html_url", "")),
            }
            audit = {
                "name": name,
                "path": f"{repo}#issue-{issue_number}",
                "sources": [result["htmlUrl"]] if result["htmlUrl"] else [],
                "summary": f"Fetched issue #{issue_number} from {repo}.",
            }
            return result, audit

        if name == "github_get_pull_request":
            pr_number = max(1, int(arguments.get("pr_number", 0) or 0))
            payload = self.github_request_json(f"https://api.github.com/repos/{repo}/pulls/{pr_number}")
            if not isinstance(payload, dict):
                raise RuntimeErrorWithCode("GitHub pull request payload was malformed.", 500)
            result = {
                "repo": repo,
                "prNumber": pr_number,
                "allowedRepos": allowed_repos,
                "title": str(payload.get("title", "")),
                "state": str(payload.get("state", "")),
                "draft": bool(payload.get("draft", False)),
                "merged": bool(payload.get("merged", False)),
                "baseRef": str(((payload.get("base") or {}).get("ref", "")) or ""),
                "headRef": str(((payload.get("head") or {}).get("ref", "")) or ""),
                "body": truncate_text(payload.get("body", ""), 4000),
                "htmlUrl": str(payload.get("html_url", "")),
            }
            audit = {
                "name": name,
                "path": f"{repo}#pr-{pr_number}",
                "sources": [result["htmlUrl"]] if result["htmlUrl"] else [],
                "summary": f"Fetched pull request #{pr_number} from {repo}.",
            }
            return result, audit

        if name == "github_get_commit":
            ref = str(arguments.get("ref", "") or "").strip()
            if not ref:
                raise RuntimeErrorWithCode("github_get_commit requires a commit ref.", 400)
            payload = self.github_request_json(f"https://api.github.com/repos/{repo}/commits/{quote(ref, safe='')}")
            if not isinstance(payload, dict):
                raise RuntimeErrorWithCode("GitHub commit payload was malformed.", 500)
            commit_data = payload.get("commit") if isinstance(payload.get("commit"), dict) else {}
            html_url = str(payload.get("html_url", ""))
            result = {
                "repo": repo,
                "ref": ref,
                "allowedRepos": allowed_repos,
                "sha": str(payload.get("sha", "")),
                "author": str(((commit_data.get("author") or {}).get("name", "")) or ""),
                "message": truncate_text(commit_data.get("message", ""), 2000),
                "htmlUrl": html_url,
            }
            audit = {
                "name": name,
                "path": f"{repo}@{ref}",
                "sources": [html_url] if html_url else [],
                "summary": f"Fetched commit {truncate_text(ref, 16)} from {repo}.",
            }
            return result, audit

        raise RuntimeErrorWithCode(f"Unsupported GitHub tool: {name}", 400)

    def get_response_usage_delta(self, response: Dict[str, Any], model: str) -> Optional[Dict[str, Any]]:
        usage = response.get("usage")
        if isinstance(usage, dict):
            input_tokens = int(usage.get("input_tokens", 0) or 0)
            output_tokens = int(usage.get("output_tokens", 0) or 0)
            total_tokens = int(usage.get("total_tokens", 0) or 0)
            cached_input_tokens = int(((usage.get("input_tokens_details") or {}).get("cached_tokens", 0)) or 0)
            reasoning_tokens = int(((usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0)) or 0)
            billable_input_tokens = max(0, input_tokens - cached_input_tokens)
            web_search_calls = len(self.get_web_search_call_items(response))
            pricing = self.get_model_pricing(model)
            model_cost = (
                (billable_input_tokens * float(pricing["inputPer1M"]))
                + (cached_input_tokens * float(pricing["cachedInputPer1M"]))
                + (output_tokens * float(pricing["outputPer1M"]))
            ) / 1_000_000.0
            tool_cost = web_search_calls * WEB_SEARCH_TOOL_CALL_PRICE_USD
            estimated_cost = model_cost + tool_cost
            return {
                "calls": 1,
                "webSearchCalls": web_search_calls,
                "inputTokens": input_tokens,
                "cachedInputTokens": cached_input_tokens,
                "billableInputTokens": billable_input_tokens,
                "outputTokens": output_tokens,
                "reasoningTokens": reasoning_tokens,
                "totalTokens": total_tokens,
                "modelCostUsd": round(model_cost, 6),
                "toolCostUsd": round(tool_cost, 6),
                "estimatedCostUsd": round(estimated_cost, 6),
            }
        if any(key in response for key in ("prompt_eval_count", "eval_count")):
            input_tokens = max(0, int(response.get("prompt_eval_count", 0) or 0))
            output_tokens = max(0, int(response.get("eval_count", 0) or 0))
            total_tokens = input_tokens + output_tokens
            return {
                "calls": 1,
                "webSearchCalls": 0,
                "inputTokens": input_tokens,
                "cachedInputTokens": 0,
                "billableInputTokens": input_tokens,
                "outputTokens": output_tokens,
                "reasoningTokens": 0,
                "totalTokens": total_tokens,
                "modelCostUsd": 0.0,
                "toolCostUsd": 0.0,
                "estimatedCostUsd": 0.0,
            }
        return None

    def merge_usage_bucket(self, bucket: Optional[Dict[str, Any]], delta: Dict[str, Any], model: str, response_id: str) -> Dict[str, Any]:
        merged = normalize_usage_bucket(bucket)
        for key in (
            "calls",
            "webSearchCalls",
            "inputTokens",
            "cachedInputTokens",
            "billableInputTokens",
            "outputTokens",
            "reasoningTokens",
            "totalTokens",
        ):
            merged[key] = int(merged[key]) + int(delta[key])
        for key in ("modelCostUsd", "toolCostUsd", "estimatedCostUsd"):
            merged[key] = round(float(merged[key]) + float(delta[key]), 6)
        merged["lastModel"] = model
        merged["lastResponseId"] = response_id
        merged["lastUpdated"] = utc_now()
        return merged

    def update_usage_tracking(
        self,
        target: str,
        task_id: str,
        model: str,
        response_id: str,
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        delta = self.get_response_usage_delta(response, model)
        if delta is None:
            return None
        with self.with_lock():
            state = self.read_state_unlocked()
            usage = normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
            existing_by_target = usage.get("byTarget", {}) if isinstance(usage.get("byTarget"), dict) else {}
            existing_by_model = usage.get("byModel", {}) if isinstance(usage.get("byModel"), dict) else {}
            usage = self.merge_usage_bucket(usage, delta, model, response_id)
            usage["byTarget"] = existing_by_target
            usage["byModel"] = existing_by_model
            usage["byTarget"][target] = self.merge_usage_bucket(usage["byTarget"].get(target), delta, model, response_id)
            usage["byModel"][model] = self.merge_usage_bucket(usage["byModel"].get(model), delta, model, response_id)
            state["usage"] = usage
            active_task = state.get("activeTask")
            if isinstance(active_task, dict) and active_task.get("taskId") == task_id:
                active_task["usage"] = usage
                self.write_task_snapshot_unlocked(active_task)
            self.write_state_unlocked(state)
            return usage

    def describe_budget_overrun(self, budget: Dict[str, Any], usage: Dict[str, Any], label: str) -> List[str]:
        reasons: List[str] = []
        if int(budget["maxTotalTokens"]) > 0 and int(usage["totalTokens"]) >= int(budget["maxTotalTokens"]):
            reasons.append(f"{label} tokens {int(usage['totalTokens'])}/{int(budget['maxTotalTokens'])}")
        if float(budget["maxCostUsd"]) > 0 and float(usage["estimatedCostUsd"]) >= float(budget["maxCostUsd"]):
            reasons.append(
                f"{label} estimated cost ${float(usage['estimatedCostUsd']):0.4f}/${float(budget['maxCostUsd']):0.4f}"
            )
        return reasons

    def get_budget_status(self, task: Dict[str, Any], usage: Dict[str, Any], target: Optional[str] = None) -> Dict[str, Any]:
        normalized_usage = normalize_usage_state(usage)
        overall_budget = normalize_budget_limits(self.get_budget_config(task), default_budget_config())
        overall_usage = normalize_usage_bucket(normalized_usage)
        reasons: List[str] = self.describe_budget_overrun(overall_budget, overall_usage, "overall")

        scope_key = self.budget_scope_key(target)
        target_budget = self.get_budget_limits(task, target) if target else overall_budget
        target_usage = overall_usage
        normalized_target = normalize_auth_target(target) if target else None
        if normalized_target:
            target_bucket = normalized_usage.get("byTarget", {}).get(normalized_target)
            target_usage = normalize_usage_bucket(target_bucket if isinstance(target_bucket, dict) else {})
        if scope_key and normalized_target:
            reasons.extend(self.describe_budget_overrun(target_budget, target_usage, f"{scope_key}:{normalized_target}"))

        return {
            "exceeded": bool(reasons),
            "message": "; ".join(reasons),
            "budget": overall_budget,
            "usage": overall_usage,
            "target": normalized_target,
            "scope": scope_key,
            "targetBudget": target_budget,
            "targetUsage": target_usage,
        }

    def assert_budget_available(self, target: str, task: Dict[str, Any]) -> None:
        state = self.read_state()
        status = self.get_budget_status(task, state.get("usage") if isinstance(state.get("usage"), dict) else {}, target)
        if status["exceeded"]:
            raise RuntimeErrorWithCode(f"Budget limit reached: {status['message']}", 409)

    def should_fallback_to_mock(self, error: RuntimeErrorWithCode) -> bool:
        message = str(error).lower()
        fatal_markers = (
            "model_not_found",
            "does not have access to model",
            "http 401",
            "http 403",
            "incorrect api key",
            "invalid_api_key",
            "organization not found",
            "provider_does_not_support",
            "provider_not_configured",
        )
        return not any(marker in message for marker in fatal_markers)

    def is_auth_rotation_error(self, error: RuntimeErrorWithCode) -> bool:
        message = str(error).lower()
        markers = (
            "http 401",
            "http 403",
            "incorrect api key",
            "invalid_api_key",
            "organization not found",
            "does not have access to model",
            "expired_api_key",
            "authentication",
        )
        return any(marker in message for marker in markers)

    def summarize_auth_failover_history(self, history: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        for entry in history:
            slot = int(entry.get("failedKeySlot", 0) or 0)
            reason = truncate_text(entry.get("error", ""), 120)
            if slot > 0:
                parts.append(f"slot {slot}: {reason}")
            elif reason:
                parts.append(reason)
        return " | ".join(parts)

    def append_auth_failover_step(
        self,
        stage: str,
        task_id: str,
        model: str,
        call_meta: Dict[str, Any],
        target: str,
    ) -> None:
        history = call_meta.get("authFailoverHistory")
        if not isinstance(history, list) or not history:
            return
        final_auth = call_meta.get("auth") if isinstance(call_meta.get("auth"), dict) else None
        self.append_step(
            stage,
            "Rotated to a different API key after a live auth failure.",
            {
                "taskId": task_id,
                "target": target,
                "model": model,
                "auth": final_auth,
                "authFailoverHistory": history,
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", 0) or 0),
            },
        )

    def invoke_openai_json(
        self,
        api_key: str,
        model: str,
        reasoning_effort: str,
        instructions: str,
        input_text: str,
        schema_name: str,
        schema: Dict[str, Any],
        max_output_tokens: int = 0,
        target_kind: str = "generic",
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        include: Optional[List[str]] = None,
        function_handlers: Optional[Dict[str, Any]] = None,
        auth_assignments: Optional[List[Dict[str, Any]]] = None,
    ) -> OpenAIResult:
        handlers = function_handlers if isinstance(function_handlers, dict) else {}
        assignment_candidates = [dict(entry) for entry in (auth_assignments or []) if isinstance(entry, dict) and str(entry.get("apiKey", "")).strip()]
        if not assignment_candidates and str(api_key or "").strip():
            assignment_candidates = [{"apiKey": str(api_key).strip()}]
        if not assignment_candidates:
            raise RuntimeErrorWithCode("No API key available for live model call.", 401)

        auth_failover_history: List[Dict[str, Any]] = []
        last_error: Optional[RuntimeErrorWithCode] = None

        for assignment_index, assignment in enumerate(assignment_candidates):
            current_api_key = str(assignment.get("apiKey", "")).strip()
            if not current_api_key:
                continue
            attempts = self.build_output_token_attempts(max_output_tokens, target_kind)
            recovered_from_incomplete = False

            try:
                for index, effective_tokens in enumerate(attempts):
                    previous_response_id: Optional[str] = None
                    pending_input: Any = input_text
                    tool_turns = 0
                    web_search_queries: Dict[str, bool] = {}
                    web_search_sources: Dict[str, bool] = {}
                    url_citations: Dict[str, bool] = {}
                    executed_tools: List[Dict[str, Any]] = []
                    retry_attempt = False

                    while True:
                        body: Dict[str, Any] = {
                            "model": model,
                            "instructions": instructions,
                            "input": pending_input,
                            "reasoning": {"effort": reasoning_effort},
                            "text": {
                                "verbosity": "low",
                                "format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema},
                            },
                        }
                        if previous_response_id:
                            body["previous_response_id"] = previous_response_id
                        if effective_tokens > 0:
                            body["max_output_tokens"] = effective_tokens
                        if tools:
                            body["tools"] = tools
                        if tool_choice is not None:
                            body["tool_choice"] = tool_choice
                        if include:
                            body["include"] = include

                        request = urllib.request.Request(
                            "https://api.openai.com/v1/responses",
                            data=json.dumps(body).encode("utf-8"),
                            headers={"Authorization": f"Bearer {current_api_key}", "Content-Type": "application/json"},
                            method="POST",
                        )
                        try:
                            with urllib.request.urlopen(request, timeout=1800) as handle:
                                response = json.loads(handle.read().decode("utf-8"))
                        except urllib.error.HTTPError as error:
                            body_text = error.read().decode("utf-8", errors="replace")
                            raise RuntimeErrorWithCode(f"OpenAI API request failed: HTTP {error.code} | {body_text}", 500)
                        except Exception as error:
                            raise RuntimeErrorWithCode(f"OpenAI API request failed: {error}", 500)

                        if isinstance(response.get("error"), dict):
                            raise RuntimeErrorWithCode(f"Model response error: {json.dumps(response['error'], ensure_ascii=False)}", 500)

                        for query in self.get_response_web_search_queries(response):
                            web_search_queries[query] = True
                        for source in self.get_response_web_search_sources(response):
                            web_search_sources[source] = True
                        for citation in self.get_response_url_citations(response):
                            url_citations[citation] = True

                        incomplete_details = response.get("incomplete_details") if isinstance(response.get("incomplete_details"), dict) else {}
                        incomplete_reason = str(incomplete_details.get("reason", "")).strip()
                        if response.get("status") == "incomplete" and incomplete_reason == "max_output_tokens" and index < len(attempts) - 1:
                            recovered_from_incomplete = True
                            last_error = RuntimeErrorWithCode(f"Model response incomplete: {incomplete_reason}", 500)
                            retry_attempt = True
                            break

                        tool_calls: List[Dict[str, Any]] = []
                        if handlers:
                            for item in response.get("output", []):
                                if not isinstance(item, dict):
                                    continue
                                item_type = str(item.get("type", "")).strip()
                                name = str(item.get("name", "")).strip()
                                if item_type not in {"function_call", "custom_tool_call"} or name not in handlers:
                                    continue
                                tool_calls.append(item)

                        if tool_calls:
                            if tool_turns >= 8:
                                raise RuntimeErrorWithCode("Model exceeded the allowed local tool turn count.", 500)
                            continuation_items: List[Dict[str, Any]] = []
                            for item in tool_calls:
                                name = str(item.get("name", "")).strip()
                                raw_arguments: Any = item.get("arguments")
                                if item.get("type") == "custom_tool_call":
                                    raw_arguments = item.get("input")
                                arguments: Dict[str, Any] = {}
                                if isinstance(raw_arguments, dict):
                                    arguments = dict(raw_arguments)
                                elif isinstance(raw_arguments, str) and raw_arguments.strip():
                                    try:
                                        decoded_arguments = json.loads(raw_arguments)
                                    except json.JSONDecodeError:
                                        decoded_arguments = None
                                    if isinstance(decoded_arguments, dict):
                                        arguments = decoded_arguments
                                call_id = str(item.get("call_id", "")).strip()
                                tool_output: Dict[str, Any]
                                tool_audit: Dict[str, Any]
                                try:
                                    tool_output, tool_audit = handlers[name](arguments)
                                except RuntimeErrorWithCode as error:
                                    tool_output = {"ok": False, "error": str(error)}
                                    tool_audit = {
                                        "name": name,
                                        "path": str(arguments.get("path", ".")),
                                        "sources": [],
                                        "error": str(error),
                                        "summary": f"{name} failed: {truncate_text(str(error), 180)}",
                                    }
                                except Exception as error:
                                    tool_output = {"ok": False, "error": str(error)}
                                    tool_audit = {
                                        "name": name,
                                        "path": str(arguments.get("path", ".")),
                                        "sources": [],
                                        "error": str(error),
                                        "summary": f"{name} crashed: {truncate_text(str(error), 180)}",
                                    }
                                audit_entry = dict(tool_audit or {})
                                audit_entry["name"] = name
                                audit_entry["arguments"] = arguments
                                if call_id:
                                    audit_entry["callId"] = call_id
                                executed_tools.append(audit_entry)
                                continuation_items.append(
                                    {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps(tool_output, ensure_ascii=False),
                                    }
                                )
                            previous_response_id = str(response.get("id", "")).strip() or previous_response_id
                            pending_input = continuation_items
                            tool_turns += 1
                            continue

                        output_text = self.get_response_output_text(response)
                        if not output_text:
                            if response.get("status") == "incomplete" and incomplete_reason:
                                detail = f"Model response incomplete: {incomplete_reason}"
                                if incomplete_reason == "max_output_tokens":
                                    detail += f" after attempts {attempts}"
                                raise RuntimeErrorWithCode(detail, 500)
                            raise RuntimeErrorWithCode("Model response did not include output_text.", 500)

                        if response.get("status") == "incomplete" and incomplete_reason:
                            detail = f"Model response incomplete: {incomplete_reason}"
                            if incomplete_reason == "max_output_tokens":
                                detail += f" after attempts {attempts}"
                            raise RuntimeErrorWithCode(detail, 500)

                        try:
                            parsed = json.loads(output_text)
                        except json.JSONDecodeError as error:
                            if response.get("status") == "incomplete" and incomplete_reason:
                                detail = f"Model response incomplete: {incomplete_reason}"
                                if incomplete_reason == "max_output_tokens":
                                    detail += f" after attempts {attempts}"
                                raise RuntimeErrorWithCode(detail, 500)
                            raise RuntimeErrorWithCode(f"Model response JSON parse failed: {error}", 500)

                        if not isinstance(parsed, dict):
                            raise RuntimeErrorWithCode("Model response JSON parse failed: expected object output.", 500)

                        return OpenAIResult(
                            provider="openai",
                            parsed=parsed,
                            response=response,
                            response_id=str(response.get("id", "")),
                            output_text=output_text,
                            thinking_text=self.get_response_thinking_text(response),
                            web_search_queries=normalize_string_array_preserve_items(list(web_search_queries.keys())),
                            web_search_sources=normalize_url_array_values(list(web_search_sources.keys())),
                            url_citations=normalize_url_array_values(list(url_citations.keys())),
                            requested_max_output_tokens=max(0, int(max_output_tokens or 0)),
                            effective_max_output_tokens=effective_tokens,
                            attempts=attempts,
                            recovered_from_incomplete=recovered_from_incomplete,
                            executed_tools=executed_tools,
                            auth_assignment=auth_assignment_meta(assignment),
                            auth_failover_history=list(auth_failover_history),
                        )

                    if retry_attempt:
                        continue

            except RuntimeErrorWithCode as error:
                last_error = error
                if assignment_index < len(assignment_candidates) - 1 and self.is_auth_rotation_error(error):
                    auth_failover_history.append(
                        {
                            "failedTarget": str(assignment.get("target", target_kind)),
                            "failedKeySlot": int(assignment.get("keySlot", 0) or 0),
                            "failedMasked": str(assignment.get("masked", "")),
                            "error": str(error),
                            "nextKeySlot": int(assignment_candidates[assignment_index + 1].get("keySlot", 0) or 0),
                            "nextMasked": str(assignment_candidates[assignment_index + 1].get("masked", "")),
                        }
                    )
                    continue
                if auth_failover_history and self.is_auth_rotation_error(error):
                    history_summary = self.summarize_auth_failover_history(auth_failover_history)
                    raise RuntimeErrorWithCode(
                        f"{error} | auth_failover_exhausted after {len(auth_failover_history) + 1} key attempts"
                        + (f" | {history_summary}" if history_summary else ""),
                        error.status_code,
                    )
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeErrorWithCode("Model response did not produce a usable structured output.", 500)

    def ollama_chat_url(self) -> str:
        base = str(os.getenv("LOOP_OLLAMA_BASE_URL") or "http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434"
        return base.rstrip("/") + "/api/chat"

    def ollama_api_key(self) -> str:
        return str(os.getenv("LOOP_OLLAMA_API_KEY") or os.getenv("OLLAMA_API_KEY") or "").strip()

    def invoke_ollama_json(
        self,
        model: str,
        instructions: str,
        input_text: str,
        schema: Dict[str, Any],
        max_output_tokens: int = 0,
        target_kind: str = "generic",
    ) -> OpenAIResult:
        attempts = self.build_output_token_attempts(max_output_tokens, target_kind)
        last_error: Optional[RuntimeErrorWithCode] = None
        api_key = self.ollama_api_key()
        for effective_tokens in attempts:
            messages = [
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": (
                        "Return JSON only that matches this schema exactly.\n\n"
                        f"Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
                        f"Input:\n{input_text}"
                    ),
                },
            ]
            body: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": False,
                "format": schema,
                "options": {},
            }
            if effective_tokens > 0:
                body["options"]["num_predict"] = effective_tokens
            if not body["options"]:
                body.pop("options", None)

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            request = urllib.request.Request(
                self.ollama_chat_url(),
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=1800) as handle:
                    response = json.loads(handle.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                body_text = error.read().decode("utf-8", errors="replace")
                raise RuntimeErrorWithCode(f"Ollama API request failed: HTTP {error.code} | {body_text}", 500)
            except Exception as error:
                raise RuntimeErrorWithCode(f"Ollama API request failed: {error}", 500)

            output_text = self.get_response_output_text(response)
            if not output_text:
                last_error = RuntimeErrorWithCode("Ollama response did not include message.content.", 500)
                continue
            try:
                parsed = json.loads(output_text)
            except json.JSONDecodeError as error:
                last_error = RuntimeErrorWithCode(f"Ollama response JSON parse failed: {error}", 500)
                continue
            if not isinstance(parsed, dict):
                last_error = RuntimeErrorWithCode("Ollama response JSON parse failed: expected object output.", 500)
                continue

            response_id = str(response.get("created_at", "") or "") or f"ollama:{int(time.time())}"
            return OpenAIResult(
                provider="ollama",
                parsed=parsed,
                response=response,
                response_id=response_id,
                output_text=output_text,
                thinking_text=self.get_response_thinking_text(response),
                web_search_queries=[],
                web_search_sources=[],
                url_citations=[],
                requested_max_output_tokens=max(0, int(max_output_tokens or 0)),
                effective_max_output_tokens=effective_tokens,
                attempts=attempts,
                recovered_from_incomplete=False,
                executed_tools=[],
                auth_assignment=None,
                auth_failover_history=[],
            )
        if last_error is not None:
            raise last_error
        raise RuntimeErrorWithCode("Ollama response did not produce a usable structured output.", 500)

    def invoke_provider_json(
        self,
        provider: str,
        api_key: str,
        model: str,
        reasoning_effort: str,
        instructions: str,
        input_text: str,
        schema_name: str,
        schema: Dict[str, Any],
        max_output_tokens: int = 0,
        target_kind: str = "generic",
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        include: Optional[List[str]] = None,
        function_handlers: Optional[Dict[str, Any]] = None,
        auth_assignments: Optional[List[Dict[str, Any]]] = None,
    ) -> OpenAIResult:
        normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
        if normalized_provider == "openai":
            return self.invoke_openai_json(
                api_key=api_key,
                model=model,
                reasoning_effort=reasoning_effort,
                instructions=instructions,
                input_text=input_text,
                schema_name=schema_name,
                schema=schema,
                max_output_tokens=max_output_tokens,
                target_kind=target_kind,
                tools=tools,
                tool_choice=tool_choice,
                include=include,
                function_handlers=function_handlers,
                auth_assignments=auth_assignments,
            )
        if normalized_provider == "ollama":
            if tools or tool_choice is not None or include or function_handlers:
                raise RuntimeErrorWithCode(
                    "provider_does_not_support: Ollama live mode does not yet support research or function tools in this runtime.",
                    400,
                )
            return self.invoke_ollama_json(
                model=model,
                instructions=instructions,
                input_text=input_text,
                schema=schema,
                max_output_tokens=max_output_tokens,
                target_kind=target_kind,
            )
        raise RuntimeErrorWithCode(f"provider_not_configured: Unsupported provider {normalized_provider}.", 400)

    def build_output_token_attempts(self, requested_max_output_tokens: int, target_kind: str) -> List[int]:
        requested = max(0, int(requested_max_output_tokens or 0))
        kind = target_kind.strip().lower()
        if kind == "worker":
            floor = 1600
            retry_floor = 3200
            hard_ceiling = 12000
        elif kind == "summarizer":
            floor = 2400
            retry_floor = 5200
            hard_ceiling = 18000
        else:
            floor = 1600
            retry_floor = 3200
            hard_ceiling = 12000

        initial = max(requested, floor)
        attempts = [initial]

        retry_candidate = max(initial * 2, retry_floor)
        retry_candidate = min(retry_candidate, max(initial, hard_ceiling))
        if retry_candidate > initial:
            attempts.append(retry_candidate)
        final_candidate = min(max(retry_candidate * 2, retry_floor), hard_ceiling)
        if final_candidate > retry_candidate:
            attempts.append(final_candidate)
        if kind == "summarizer" and final_candidate < hard_ceiling:
            attempts.append(hard_ceiling)

        deduped: List[int] = []
        for value in attempts:
            if value not in deduped:
                deduped.append(value)
        return deduped

    def get_default_request_targets(self, task: Dict[str, Any], current_worker_id: str, round_number: Optional[int] = None) -> List[str]:
        peer_ids = [worker["id"] for worker in task_workers(task, round_number) if worker["id"] != current_worker_id]
        if not peer_ids:
            return []
        if current_worker_id == "A" and "B" in peer_ids:
            return ["B"]
        if current_worker_id != "A" and "A" in peer_ids:
            return ["A"]
        return [peer_ids[0]]

    def normalize_request_targets(self, targets: Any, task: Dict[str, Any], current_worker_id: str, round_number: Optional[int] = None) -> List[str]:
        valid_targets = {
            worker["id"]: True
            for worker in task_workers(task, round_number)
            if worker["id"] != current_worker_id
        }
        normalized: List[str] = []
        if isinstance(targets, list):
            for target in targets:
                candidate = str(target).strip().upper()
                if candidate in valid_targets:
                    normalized.append(candidate)
        if normalized:
            return list(dict.fromkeys(normalized).keys())
        return self.get_default_request_targets(task, current_worker_id, round_number)

    def get_peer_steer_messages(self, state: Dict[str, Any], task: Dict[str, Any], worker_id: str, round_number: Optional[int] = None) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        workers_state = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        for peer in task_workers(task, round_number):
            if peer["id"] == worker_id:
                continue
            checkpoint = workers_state.get(peer["id"])
            if not isinstance(checkpoint, dict):
                continue
            targets = checkpoint.get("requestTargets", [])
            target_values = targets if isinstance(targets, list) else []
            if target_values and worker_id not in target_values and "*" not in target_values:
                continue
            message = str(checkpoint.get("requestToPeer", "")).strip()
            if not message:
                continue
            messages.append({"from": peer["id"], "message": message})
        return messages

    def expand_peer_steer_packets(self, task: Dict[str, Any], state: Dict[str, Any], round_number: Optional[int] = None) -> List[Dict[str, str]]:
        packets: List[Dict[str, str]] = []
        workers_state = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        roster = task_workers(task, round_number)
        for worker in roster:
            checkpoint = workers_state.get(worker["id"])
            if not isinstance(checkpoint, dict):
                continue
            message = str(checkpoint.get("requestToPeer", "")).strip()
            if not message:
                continue
            targets = checkpoint.get("requestTargets") if isinstance(checkpoint.get("requestTargets"), list) else ["*"]
            if not targets:
                targets = ["*"]
            target_list: Iterable[str]
            if "*" in targets:
                target_list = [peer["id"] for peer in roster if peer["id"] != worker["id"]]
            else:
                target_list = [str(target).strip().upper() for target in targets if str(target).strip().upper() != worker["id"]]
            for target in target_list:
                if target:
                    packets.append({"from": worker["id"], "to": target, "message": message})
        return packets

    def get_latest_summary_round(self, state: Dict[str, Any]) -> int:
        summary = state.get("summary") if isinstance(state.get("summary"), dict) else None
        return max(0, int((summary or {}).get("round", 0) or 0))

    def get_latest_commander_round(self, state: Dict[str, Any]) -> int:
        commander = state.get("commander") if isinstance(state.get("commander"), dict) else None
        return max(0, int((commander or {}).get("round", 0) or 0))

    def get_latest_commander_review_round(self, state: Dict[str, Any]) -> int:
        checkpoint = state.get("commanderReview") if isinstance(state.get("commanderReview"), dict) else None
        return max(0, int((checkpoint or {}).get("round", 0) or 0))

    def get_latest_worker_round(self, state: Dict[str, Any]) -> int:
        workers_state = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        latest = 0
        for checkpoint in workers_state.values():
            if isinstance(checkpoint, dict):
                latest = max(latest, int(checkpoint.get("step", 0) or 0))
        return latest

    def get_open_round(self, state: Dict[str, Any]) -> int:
        completed_round = self.get_latest_summary_round(state)
        commander_round = self.get_latest_commander_round(state)
        commander_review_round = self.get_latest_commander_review_round(state)
        worker_round = self.get_latest_worker_round(state)
        if commander_round > completed_round:
            return commander_round
        if commander_review_round > completed_round:
            return commander_review_round
        if worker_round > completed_round:
            return worker_round
        return 0

    def resolve_dynamic_lane_request(self, task: Dict[str, Any], decision: Any, active_from_round: int = 1) -> Dict[str, Any]:
        normalized_decision = normalize_dynamic_lane_decision(decision)
        requested_lane_types = normalize_lane_type_list(normalized_decision.get("suggestedLaneTypes", []), include_utility=False, max_items=4)
        inferred_lane_types = infer_dynamic_lane_types_from_text(
            normalized_decision.get("requiredPressure", ""),
            normalized_decision.get("reason", ""),
            normalized_decision.get("instruction", ""),
            max_items=4,
        )
        existing_workers = task_workers(task)
        existing_types = {str(worker.get("type", "")).strip().lower() for worker in existing_workers}
        existing_overlap_keys = {dynamic_lane_overlap_key(worker.get("type")) for worker in existing_workers}
        candidates: List[str] = []
        for lane_type in requested_lane_types + inferred_lane_types:
            if lane_type not in candidates:
                candidates.append(lane_type)
        resolution = {
            "status": "not_requested",
            "requestedLaneTypes": requested_lane_types,
            "inferredLaneTypes": inferred_lane_types,
            "selectedLaneType": "",
            "selectedBecause": "",
            "activationRound": max(0, int(active_from_round or 0)),
            "spawnedWorkerId": "",
            "rejectedLaneTypes": [],
        }
        if not bool(normalized_decision.get("shouldSpawn")):
            return normalize_dynamic_lane_resolution(resolution)
        if not candidates:
            resolution["status"] = "rejected_invalid"
            resolution["selectedBecause"] = "Commander review requested another lane but did not identify a valid adversarial type."
            return normalize_dynamic_lane_resolution(resolution)
        for lane_type in candidates:
            overlap_key = dynamic_lane_overlap_key(lane_type)
            if lane_type in existing_types:
                resolution["rejectedLaneTypes"].append(
                    {"laneType": lane_type, "reason": "Exact lane type is already active in the roster."}
                )
                continue
            if overlap_key in existing_overlap_keys:
                resolution["rejectedLaneTypes"].append(
                    {"laneType": lane_type, "reason": "A near-duplicate adversarial lens is already active in the roster."}
                )
                continue
            resolution["status"] = "spawned"
            resolution["selectedLaneType"] = lane_type
            if lane_type in requested_lane_types and lane_type in inferred_lane_types:
                resolution["selectedBecause"] = "Commander review requested this lane and the unresolved pressure text independently reinforced it."
            elif lane_type in requested_lane_types:
                resolution["selectedBecause"] = "Commander review explicitly requested this lane type and it was not already covered."
            else:
                resolution["selectedBecause"] = "The unresolved pressure text matched this lane more strongly than the requested types that were already covered."
            return normalize_dynamic_lane_resolution(resolution)
        resolution["status"] = "rejected_covered" if resolution["rejectedLaneTypes"] else "rejected_unresolved"
        resolution["selectedBecause"] = (
            "Commander review requested another lane, but every viable candidate was already covered by the current roster."
            if resolution["rejectedLaneTypes"]
            else "Commander review requested another lane, but no sufficiently distinct adversarial lens could be resolved."
        )
        return normalize_dynamic_lane_resolution(resolution)

    def build_dynamic_worker(
        self,
        task: Dict[str, Any],
        decision: Any,
        active_from_round: int = 1,
    ) -> tuple[Optional[Dict[str, str]], Dict[str, Any]]:
        normalized_decision = normalize_dynamic_lane_decision(decision)
        resolution = self.resolve_dynamic_lane_request(task, normalized_decision, active_from_round)
        selected_type = str(resolution.get("selectedLaneType", "") or "").strip().lower()
        catalog_entry = WORKER_TYPE_CATALOG.get(selected_type)
        if not catalog_entry or str(catalog_entry.get("role", "adversarial")) != "adversarial":
            return None, resolution
        existing_ids = {worker["id"] for worker in task_workers(task)}
        for worker_id in worker_slot_ids():
            if worker_id in existing_ids:
                continue
            focus = str(catalog_entry.get("focus", "")).strip()
            required_pressure = str(normalized_decision.get("requiredPressure", "")).strip()
            reason = str(normalized_decision.get("reason", "")).strip()
            instruction = str(normalized_decision.get("instruction", "")).strip()
            if required_pressure:
                focus = truncate_text(f"{focus}; specifically attack this unresolved pressure: {required_pressure}", 220)
            harness_bits: List[str] = []
            if required_pressure:
                harness_bits.append(f"Primary unresolved pressure: {required_pressure}.")
            if reason:
                harness_bits.append(f"Why this lane exists: {reason}.")
            if instruction:
                harness_bits.append(instruction)
            worker_definition: Dict[str, Any] = {
                "id": worker_id,
                "type": selected_type,
                "focus": focus or str(catalog_entry.get("focus", "")).strip(),
                "activeFromRound": max(1, int(active_from_round or 1)),
            }
            temperature = str(normalized_decision.get("temperature", "")).strip().lower()
            if temperature in WORKER_TEMPERATURE_CATALOG:
                worker_definition["temperature"] = temperature
            if harness_bits:
                worker_definition["harness"] = {
                    "concision": default_worker_harness()["concision"],
                    "instruction": truncate_text(" ".join(harness_bits), 320),
                }
            normalized_worker = normalize_worker_definition(
                worker_definition,
                normalize_model_id((task.get("runtime") or {}).get("model"), DEFAULT_MODEL_ID),
            )
            resolution["spawnedWorkerId"] = normalized_worker["id"]
            return normalized_worker, normalize_dynamic_lane_resolution(resolution)
        resolution["status"] = "rejected_unresolved"
        resolution["selectedBecause"] = "Commander review identified a useful missing lane, but no worker slots were available."
        return None, normalize_dynamic_lane_resolution(resolution)

    def commander_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "taskId",
                "round",
                "stance",
                "leadDirection",
                "answerDraft",
                "whyThisDirection",
                "questionsForWorkers",
                "pressurePoints",
                "keepCourseIf",
                "changeCourseIf",
                "uncertainty",
                "suggestedLaneTypes",
                "suggestedLaneReason",
                "constraintsSeen",
            ],
            "properties": {
                "taskId": {"type": "string"},
                "round": {"type": "integer"},
                "stance": {"type": "string"},
                "leadDirection": {"type": "string"},
                "answerDraft": {"type": "string"},
                "whyThisDirection": {"type": "string"},
                "questionsForWorkers": {"type": "array", "items": {"type": "string"}},
                "pressurePoints": {"type": "array", "items": {"type": "string"}},
                "keepCourseIf": {"type": "array", "items": {"type": "string"}},
                "changeCourseIf": {"type": "array", "items": {"type": "string"}},
                "uncertainty": {"type": "array", "items": {"type": "string"}},
                "suggestedLaneTypes": {"type": "array", "items": {"type": "string"}},
                "suggestedLaneReason": {"type": "string"},
                "constraintsSeen": {"type": "array", "items": {"type": "string"}},
            },
        }

    def new_mock_commander(
        self,
        task: Dict[str, Any],
        runtime: Dict[str, Any],
        round_number: int,
        constraints: List[str],
        prior_summary: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        objective = truncate_text(task.get("objective", ""), 600)
        prior_direction = truncate_text((prior_summary or {}).get("recommendedNextAction", ""), 220)
        lead_direction = prior_direction or truncate_text(objective, 260) or "Clarify the user's objective before committing."
        answer_draft = (
            f"{lead_direction}\n\n"
            "This is the commander's first-pass answer direction before adversarial pressure."
        )
        return {
            "taskId": str(task.get("taskId", "")),
            "round": round_number,
            "stance": lead_direction,
            "leadDirection": lead_direction,
            "answerDraft": answer_draft,
            "whyThisDirection": "Start from the clearest practical answer visible in the current objective, then let objections test whether it actually survives.",
            "questionsForWorkers": [
                "What is the strongest reason this direction could be wrong, unsafe, or too expensive?",
                "What condition would justify changing course instead of merely qualifying it?",
            ],
            "pressurePoints": [
                "Hidden cost, brittleness, or scope drift that would weaken this recommendation.",
                "Missing evidence or assumptions that make the draft look more certain than it should.",
            ],
            "keepCourseIf": [
                "Objections only add guardrails, conditions, or measurement hooks without changing the core recommendation.",
            ],
            "changeCourseIf": [
                "A strong objection shows the current direction is materially wrong, unsafe, or impractical under the stated constraints.",
            ],
            "uncertainty": [
                "This is a draft checkpoint, not the final adjudicated answer.",
            ],
            "suggestedLaneTypes": [],
            "suggestedLaneReason": "",
            "constraintsSeen": constraints,
            "updatedAt": utc_now(),
        }

    def new_live_commander(
        self,
        api_key: str,
        auth_assignments: Optional[List[Dict[str, Any]]],
        task: Dict[str, Any],
        runtime: Dict[str, Any],
        round_number: int,
        constraints: List[str],
        prior_summary: Optional[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], str, Dict[str, Any], Dict[str, Any]]:
        command_config = commander_config(task)
        harness_lines = commander_harness_instruction_lines(command_config.get("harness"))
        session_context = str(task.get("sessionContext", "")).strip()
        summary_projection = self.project_prior_summary_for_worker(prior_summary)
        summary_text = json.dumps(summary_projection, ensure_ascii=False, indent=2) if summary_projection else "none"
        local_file_config = normalize_local_file_tool_config(runtime.get("localFiles") if isinstance(runtime.get("localFiles"), dict) else {})
        github_tool_config = normalize_github_tool_config(runtime.get("githubTools") if isinstance(runtime.get("githubTools"), dict) else {})
        tools: List[Dict[str, Any]] = []
        function_handlers: Dict[str, Any] = {}
        if local_file_config["enabled"]:
            tools.extend(self.build_local_file_function_tools(local_file_config))
            function_handlers.update({
                "local_list_dir": lambda arguments: self.execute_local_file_tool_call("local_list_dir", arguments, local_file_config),
                "local_read_file": lambda arguments: self.execute_local_file_tool_call("local_read_file", arguments, local_file_config),
                "local_search_text": lambda arguments: self.execute_local_file_tool_call("local_search_text", arguments, local_file_config),
            })
        if github_tool_config["enabled"]:
            tools.extend(self.build_github_function_tools(github_tool_config))
            function_handlers.update({
                "github_list_paths": lambda arguments: self.execute_github_tool_call("github_list_paths", arguments, github_tool_config),
                "github_read_file": lambda arguments: self.execute_github_tool_call("github_read_file", arguments, github_tool_config),
                "github_get_issue": lambda arguments: self.execute_github_tool_call("github_get_issue", arguments, github_tool_config),
                "github_get_pull_request": lambda arguments: self.execute_github_tool_call("github_get_pull_request", arguments, github_tool_config),
                "github_get_commit": lambda arguments: self.execute_github_tool_call("github_get_commit", arguments, github_tool_config),
            })
        instructions = (
            "You are the commander / lead thread in a sparse multi-lane reasoning loop.\n"
            "Your job is to draft the answer direction before adversarial pressure arrives.\n"
            "Read the full current user input and produce one clear first-pass direction.\n"
            "This is not the final public answer yet.\n"
            "Be decisive, but explicitly name what kind of objection would justify changing course.\n"
            "Do not wait for perfect certainty before taking a direction.\n"
            "Do not narrate the hidden system or mention workers inside answerDraft.\n"
            "Set taskId, round, stance, and leadDirection explicitly.\n"
            "Use answerDraft for the provisional lead answer the adversaries will pressure-test.\n"
            "Use whyThisDirection to explain why this is your best current direction.\n"
            "Use questionsForWorkers to ask the adversaries for the strongest pressure tests you need next.\n"
            "Use pressurePoints for the assumptions, costs, safety issues, or blind spots that should be challenged.\n"
            "Use keepCourseIf for what kinds of objections should only qualify the answer.\n"
            "Use changeCourseIf for what kinds of objections would justify redirecting or reversing the answer.\n"
            "If a crucial adversarial viewpoint is missing from the current roster, use suggestedLaneTypes for up to 2 adversarial lane types that should be added for a later round.\n"
            "Use suggestedLaneReason to explain why the missing viewpoint matters.\n"
            "Leave suggestedLaneTypes empty when the current roster is sufficient.\n"
            "Keep uncertainty honest, but do not become timid or vague.\n"
            + (
                "If local file tools are available, inspect the relevant workspace files before asserting repository-specific details.\n"
                if local_file_config["enabled"]
                else ""
            )
            + (
                "If GitHub tools are available, inspect the allowlisted repositories directly before asserting GitHub-specific details.\n"
                if github_tool_config["enabled"]
                else ""
            )
            + "\n".join(harness_lines)
            + "\nReturn JSON only that matches the schema exactly."
        )
        input_text = (
            f"Authoritative current user input:\n{task.get('objective', '')}\n\n"
            f"Current constraints:\n{chr(10).join(constraints) if constraints else 'none'}\n\n"
            f"Carry-forward session context (background only, not authoritative):\n{session_context or 'none'}\n\n"
            f"Prior adjudicated summary (background only):\n{summary_text}\n\n"
            "Produce the commander's first-pass answer direction for this round."
        )
        result = self.invoke_provider_json(
            provider=runtime["provider"],
            api_key=api_key,
            model=runtime["model"],
            reasoning_effort=runtime["reasoningEffort"],
            instructions=instructions,
            input_text=input_text,
            schema_name="loop_commander_draft",
            schema=self.commander_schema(),
            max_output_tokens=int(runtime["maxOutputTokens"]),
            target_kind="commander",
            tools=tools or None,
            tool_choice="auto" if tools else None,
            function_handlers=function_handlers if function_handlers else None,
            auth_assignments=auth_assignments,
        )
        parsed = normalize_commander_checkpoint(dict(result.parsed), task, round_number)
        parsed["localToolCalls"] = normalize_local_tool_calls(filter_tool_calls_by_prefixes(result.executed_tools, ("local_",)))
        parsed["localFileSources"] = collect_tool_sources_by_prefixes(result.executed_tools, ("local_",))
        parsed["githubToolCalls"] = normalize_local_tool_calls(filter_tool_calls_by_prefixes(result.executed_tools, ("github_",)))
        parsed["githubSources"] = normalize_url_array_values(collect_tool_sources_by_prefixes(result.executed_tools, ("github_",)))
        call_meta = {
            "requestedMaxOutputTokens": result.requested_max_output_tokens,
            "effectiveMaxOutputTokens": result.effective_max_output_tokens,
            "attempts": result.attempts,
            "recoveredFromIncomplete": result.recovered_from_incomplete,
            "auth": result.auth_assignment,
            "authFailoverHistory": result.auth_failover_history,
            "localToolCalls": parsed["localToolCalls"],
            "localFileSources": parsed["localFileSources"],
            "githubToolCalls": parsed["githubToolCalls"],
            "githubSources": parsed["githubSources"],
        }
        return parsed, result.response_id, result.response, call_meta

    def commander_review_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "taskId",
                "round",
                "stance",
                "leadDirection",
                "answerDraft",
                "whyThisDirection",
                "controlAudit",
                "dynamicLaneDecision",
                "remainingUncertainty",
                "sourceWorkers",
            ],
            "properties": {
                "taskId": {"type": "string"},
                "round": {"type": "integer"},
                "stance": {"type": "string"},
                "leadDirection": {"type": "string"},
                "answerDraft": {"type": "string"},
                "whyThisDirection": {"type": "string"},
                "controlAudit": self.summary_schema()["properties"]["controlAudit"],
                "dynamicLaneDecision": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "shouldSpawn",
                        "suggestedLaneTypes",
                        "reason",
                        "requiredPressure",
                        "temperature",
                        "instruction",
                    ],
                    "properties": {
                        "shouldSpawn": {"type": "boolean"},
                        "suggestedLaneTypes": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"},
                        "requiredPressure": {"type": "string"},
                        "temperature": {"type": "string"},
                        "instruction": {"type": "string"},
                    },
                },
                "remainingUncertainty": {"type": "array", "items": {"type": "string"}},
                "sourceWorkers": {"type": "array", "items": {"type": "string"}},
            },
        }

    def new_mock_commander_review(
        self,
        task: Dict[str, Any],
        commander_checkpoint: Optional[Dict[str, Any]],
        workers: List[Dict[str, str]],
        worker_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        commander_projection = self.project_commander_for_summary(commander_checkpoint)
        round_number = int(commander_projection.get("round", 0) or 1)
        source_workers = [worker["id"] for worker in workers if isinstance(worker_state.get(worker["id"]), dict)]
        strongest_points: List[str] = []
        held_out: List[str] = []
        for worker in workers:
            checkpoint = self.project_worker_checkpoint_for_summary(worker_state.get(worker["id"]))
            if checkpoint is None:
                continue
            challenge = (
                limit_string_list(checkpoint.get("invalidatingCircumstances", []), 1, 180)
                + limit_string_list(checkpoint.get("evidenceGaps", []), 1, 180)
                + limit_string_list(checkpoint.get("uncertainty", []), 1, 180)
            )
            if challenge:
                strongest_points.append(f"{worker['label']}: {challenge[0]}")
            if checkpoint.get("requestToPeer"):
                held_out.append(str(checkpoint.get("requestToPeer")))
        strongest_points = strongest_points[:3]
        held_out = limit_string_list(held_out, 3, 220)
        answer_draft = truncate_text(commander_projection.get("answerDraft", ""), 1600)
        lead_direction = truncate_text(commander_projection.get("leadDirection", ""), 260)
        return normalize_commander_review_checkpoint(
            {
                "taskId": str(task.get("taskId", "")),
                "round": round_number,
                "stance": truncate_text(commander_projection.get("stance", ""), 240) or lead_direction,
                "leadDirection": lead_direction,
                "answerDraft": answer_draft or lead_direction,
                "whyThisDirection": (
                    "The lead thread kept the clearest answer direction, then checked whether the strongest objections only qualified it or actually forced a course change."
                ),
                "controlAudit": {
                    "leadDraft": answer_draft or lead_direction,
                    "integrationQuestion": "Does this adversarial point materially improve correctness, scope, safety, or usefulness, or is it mostly noise?",
                    "courseDecision": "maintain",
                    "courseDecisionReason": "Mock reevaluation defaults to maintaining course unless a worker checkpoint clearly invalidates the lead direction.",
                    "contributionAssessments": [
                        {
                            "contribution": point,
                            "value": "high",
                            "effect": "qualify",
                            "reason": "This objection should sharpen the lead answer without automatically replacing it."
                        }
                        for point in strongest_points
                    ][:4],
                    "acceptedAdversarialPoints": strongest_points,
                    "rejectedAdversarialPoints": [],
                    "heldOutConcerns": held_out,
                    "selfCheck": "Before speaking, the lead thread checked that the revised draft still answered the user's request directly.",
                },
                "dynamicLaneDecision": {
                    "shouldSpawn": False,
                    "suggestedLaneTypes": [],
                    "reason": "Mock commander review did not identify a clearly missing adversarial lane.",
                    "requiredPressure": "",
                    "temperature": "",
                    "instruction": "",
                },
                "remainingUncertainty": limit_string_list(commander_projection.get("uncertainty", []), 3, 220),
                "sourceWorkers": source_workers,
            },
            task,
            round_number,
            commander_checkpoint,
            source_workers,
        )

    def new_live_commander_review(
        self,
        api_key: str,
        auth_assignments: Optional[List[Dict[str, Any]]],
        task: Dict[str, Any],
        commander_checkpoint: Optional[Dict[str, Any]],
        workers: List[Dict[str, str]],
        worker_state: Dict[str, Any],
        runtime: Dict[str, Any],
        line_catalog: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], str, Dict[str, Any], Dict[str, Any]]:
        review_config = commander_review_config(task)
        harness_lines = summarizer_harness_instruction_lines(review_config.get("harness"))
        constraints = limit_string_list(task.get("constraints", []), 24, 400)
        session_context = str(task.get("sessionContext", "")).strip()
        commander_projection = self.project_commander_for_summary(commander_checkpoint)
        round_number = int(commander_projection.get("round", 0) or 1)
        worker_projection = self.project_worker_state_for_summary(worker_state, workers)
        source_workers = [worker["id"] for worker in workers if isinstance(worker_state.get(worker["id"]), dict)]
        instructions = (
            "You are the commander_review stage in a sparse multi-lane reasoning loop.\n"
            "The commander already produced a first-pass direction. The workers have now pressure-tested it.\n"
            "Your job is to decide whether the lead thread should maintain, qualify, redirect, or reverse before any public answer is written.\n"
            "This is the authoritative lead-thread reevaluation for the round.\n"
            "Read the full current user input, the original commander draft, and the worker checkpoints.\n"
            "Do not write the final public answer yet. Produce the revised lead answer that the summarizer will later present cleanly.\n"
            "Use stance, leadDirection, answerDraft, and whyThisDirection for the revised lead position after adversarial pressure.\n"
            "Use controlAudit to show that the lead thread explicitly judged the value of each strong adversarial contribution instead of submitting to it.\n"
            "Default to maintain when objections only add evidence, conditions, or guardrails.\n"
            "Use qualify when the lead stays on course but needs narrower scope, stronger conditions, or sharper caveats.\n"
            "Use redirect when the destination changes while still serving the user's core goal.\n"
            "Use reverse only when the current lead answer would now be materially wrong, unsafe, or misleading.\n"
            "Indecisive drift is worse than a clear qualified answer when reversal is not justified.\n"
            "Use dynamicLaneDecision only when the current roster still lacks one materially missing adversarial lens for the NEXT round.\n"
            "dynamicLaneDecision.suggestedLaneTypes may contain up to 2 known adversarial lane types from the catalog.\n"
            "dynamicLaneDecision.requiredPressure should name the unresolved uncertainty or pressure that the next lane must attack.\n"
            "dynamicLaneDecision.temperature may be cool, balanced, or hot when the next lane needs a deliberate reasoning style.\n"
            "dynamicLaneDecision.instruction should be one short lane-specific harness instruction for that spawned worker.\n"
            "Leave shouldSpawn false when the current roster already covers the relevant pressure.\n"
            "remainingUncertainty should capture what still stays unresolved after this reevaluation.\n"
            "sourceWorkers should list the workers whose checkpoints materially informed the reevaluation.\n"
            + "\n".join(harness_lines)
            + "\nReturn JSON only that matches the schema exactly."
        )
        input_text = (
            f"Authoritative current user input:\n{task.get('objective', '')}\n\n"
            f"Current constraints:\n{chr(10).join(constraints) if constraints else 'none'}\n\n"
            f"Carry-forward session context (background only, not authoritative):\n{session_context or 'none'}\n\n"
            f"Initial commander draft for this round:\n{json.dumps(commander_projection, ensure_ascii=False, indent=2)}\n\n"
            f"Worker lineup:\n{json.dumps(self.project_worker_roster_for_summary(workers), ensure_ascii=False, indent=2)}\n\n"
            f"Known adversarial lane types:\n{json.dumps(normalize_lane_type_list(list(WORKER_TYPE_CATALOG.keys()), False, 32), ensure_ascii=False, indent=2)}\n\n"
            f"Worker checkpoint digests:\n{json.dumps(worker_projection, ensure_ascii=False, indent=2)}\n\n"
            f"Worker review line catalog:\n{json.dumps(line_catalog, ensure_ascii=False, indent=2)}"
        )
        result = self.invoke_provider_json(
            provider=runtime["provider"],
            api_key=api_key,
            model=runtime["model"],
            reasoning_effort=runtime["reasoningEffort"],
            instructions=instructions,
            input_text=input_text,
            schema_name="loop_commander_review",
            schema=self.commander_review_schema(),
            max_output_tokens=int(runtime["maxOutputTokens"]),
            target_kind="commander_review",
            auth_assignments=auth_assignments,
        )
        parsed = normalize_commander_review_checkpoint(
            dict(result.parsed),
            task,
            round_number,
            commander_checkpoint,
            source_workers,
        )
        call_meta = {
            "requestedMaxOutputTokens": result.requested_max_output_tokens,
            "effectiveMaxOutputTokens": result.effective_max_output_tokens,
            "attempts": result.attempts,
            "recoveredFromIncomplete": result.recovered_from_incomplete,
            "auth": result.auth_assignment,
            "authFailoverHistory": result.auth_failover_history,
        }
        return parsed, result.response_id, result.response, call_meta

    def new_mock_checkpoint(
        self,
        task: Dict[str, Any],
        worker: Dict[str, str],
        runtime: Dict[str, Any],
        research_config: Dict[str, Any],
        step_number: int,
        constraints: List[str],
        prior_summary: Optional[Dict[str, Any]],
        prior_memory_version: int,
        peer_messages: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        viewpoint = "utility" if worker["role"] == "utility" else "adversarial"
        session_context = str(task.get("sessionContext", "")).strip()
        peer_text = "\n".join(f"{item['from']}: {item['message']}" for item in peer_messages) if peer_messages else "No peer steer received yet."
        research_mode = "mock_research" if research_config["enabled"] else "mock"
        request_to_peer = (
            "Pressure-test whether the expected upside survives real-world constraints without adding hidden coordination drag."
            if worker["role"] == "utility"
            else f"Defend why the plan survives the failure mode centered on {worker['focus']}."
        )
        return {
            "workerId": worker["id"],
            "label": worker["label"],
            "role": worker["role"],
            "viewpoint": viewpoint,
            "focus": worker["focus"],
            "step": step_number,
            "modelUsed": runtime["model"],
            "observation": (
                f"{worker['label']} reading of objective with focus on {worker['focus']} at {worker.get('temperature', 'balanced')} temperature, informed by carry-forward session context."
                if session_context
                else f"{worker['label']} reading of objective with focus on {worker['focus']} at {worker.get('temperature', 'balanced')} temperature."
            ),
            "peerSteer": peer_text,
            "sharedMemorySeen": {
                "memoryVersion": prior_memory_version,
                "recommendedNextAction": str((prior_summary or {}).get("recommendedNextAction") or "No summary available yet."),
            },
            "benefits": [
                f"Keeps an explicit lane focused on {worker['focus']}",
                "Preserves parallel disagreement instead of forcing one blended answer",
                "Supports sparse steer packets without merging all process state",
            ],
            "detriments": [
                "Adds more coordination cost as the roster expands",
                "Can magnify review noise if every lane argues without discipline",
            ],
            "requiredCircumstances": [
                "Structured checkpoint schema",
                "Stable locked state updates",
                "A hard distinction between observations, risks, and requests to peers",
            ],
            "invalidatingCircumstances": [
                "Freeform high-frequency raw-thought sharing",
                "Missing budget ceilings for live runs",
                "Untracked worker additions or silent model changes",
            ],
            "immediateConsequences": [
                f"More coverage over blind spots tied to {worker['focus']}",
                "Higher coordination load per round",
            ],
            "downstreamConsequences": [
                "Better auditability of why a lane disagreed",
                "Higher spend risk if worker growth is not capped by budget",
            ],
            "uncertainty": [
                "The useful number of simultaneous lanes is task-dependent",
                "Per-position model choice can improve outcomes or just waste budget",
                "Steer packets need tuning so they influence without collapsing independence",
            ],
            "reversalConditions": [
                "Reduce this lane if it stops adding distinct evidence",
                "Raise or lower sharing cadence only after checking budget and convergence behavior",
            ],
            "researchMode": research_mode,
            "researchQueries": [task["objective"], session_context] if research_config["enabled"] and session_context else ([task["objective"]] if research_config["enabled"] else []),
            "researchSources": [],
            "urlCitations": [],
            "evidenceLedger": [
                {
                    "claim": "Parallel lane separation keeps this viewpoint explicit instead of flattening it into a single answer.",
                    "supportLevel": "weak",
                    "sourceUrls": [],
                    "note": "Mock mode only; this is a scaffolded claim and still needs grounded evidence.",
                },
                {
                    "claim": "Budget ceilings and model controls are necessary once multiple lanes can run live.",
                    "supportLevel": "weak",
                    "sourceUrls": [],
                    "note": "Mock mode only; production confidence depends on live accounting and observed loop behavior.",
                },
            ],
            "evidenceGaps": [
                "No live web sources were consulted in mock mode.",
                "Claims should be re-run with grounded research before being treated as supported.",
            ],
            "confidence": 0.72 if worker["role"] == "utility" else 0.77,
            "requestToPeer": request_to_peer,
            "requestTargets": self.get_default_request_targets(task, worker["id"], step_number),
            "constraintsSeen": constraints,
            "updatedAt": utc_now(),
        }

    def worker_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "workerId",
                "label",
                "role",
                "viewpoint",
                "focus",
                "step",
                "modelUsed",
                "observation",
                "peerSteer",
                "sharedMemorySeen",
                "benefits",
                "detriments",
                "requiredCircumstances",
                "invalidatingCircumstances",
                "immediateConsequences",
                "downstreamConsequences",
                "uncertainty",
                "reversalConditions",
                "researchMode",
                "researchQueries",
                "researchSources",
                "urlCitations",
                "evidenceLedger",
                "evidenceGaps",
                "confidence",
                "requestToPeer",
                "requestTargets",
                "constraintsSeen",
            ],
            "properties": {
                "workerId": {"type": "string"},
                "label": {"type": "string"},
                "role": {"type": "string"},
                "viewpoint": {"type": "string"},
                "focus": {"type": "string"},
                "step": {"type": "integer"},
                "modelUsed": {"type": "string"},
                "observation": {"type": "string"},
                "peerSteer": {"type": "string"},
                "sharedMemorySeen": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["memoryVersion", "recommendedNextAction"],
                    "properties": {
                        "memoryVersion": {"type": "integer"},
                        "recommendedNextAction": {"type": "string"},
                    },
                },
                "benefits": {"type": "array", "items": {"type": "string"}},
                "detriments": {"type": "array", "items": {"type": "string"}},
                "requiredCircumstances": {"type": "array", "items": {"type": "string"}},
                "invalidatingCircumstances": {"type": "array", "items": {"type": "string"}},
                "immediateConsequences": {"type": "array", "items": {"type": "string"}},
                "downstreamConsequences": {"type": "array", "items": {"type": "string"}},
                "uncertainty": {"type": "array", "items": {"type": "string"}},
                "reversalConditions": {"type": "array", "items": {"type": "string"}},
                "researchMode": {"type": "string"},
                "researchQueries": {"type": "array", "items": {"type": "string"}},
                "researchSources": {"type": "array", "items": {"type": "string"}},
                "urlCitations": {"type": "array", "items": {"type": "string"}},
                "evidenceLedger": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["claim", "supportLevel", "sourceUrls", "note"],
                        "properties": {
                            "claim": {"type": "string"},
                            "supportLevel": {"type": "string"},
                            "sourceUrls": {"type": "array", "items": {"type": "string"}},
                            "note": {"type": "string"},
                        },
                    },
                },
                "evidenceGaps": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
                "requestToPeer": {"type": "string"},
                "requestTargets": {"type": "array", "items": {"type": "string"}},
                "constraintsSeen": {"type": "array", "items": {"type": "string"}},
            },
        }

    def new_live_checkpoint(
        self,
        api_key: str,
        auth_assignments: Optional[List[Dict[str, Any]]],
        task: Dict[str, Any],
        worker: Dict[str, str],
        runtime: Dict[str, Any],
        research_config: Dict[str, Any],
        step_number: int,
        constraints: List[str],
        commander_checkpoint: Optional[Dict[str, Any]],
        prior_summary: Optional[Dict[str, Any]],
        prior_memory_version: int,
        peer_messages: List[Dict[str, str]],
    ) -> tuple[Dict[str, Any], str, Dict[str, Any], Dict[str, Any]]:
        peer_targets = [item["id"] for item in task_workers(task, step_number) if item["id"] != worker["id"]]
        peer_text = "\n".join(f"{item['from']}: {item['message']}" for item in peer_messages) if peer_messages else "No peer steer received yet."
        session_context = str(task.get("sessionContext", "")).strip()
        summary_projection = self.project_prior_summary_for_worker(prior_summary)
        summary_text = json.dumps(summary_projection, ensure_ascii=False, indent=2) if summary_projection else "none"
        commander_projection = self.project_commander_for_worker(commander_checkpoint)
        commander_text = json.dumps(commander_projection, ensure_ascii=False, indent=2) if commander_projection else "none"
        harness_lines = worker_harness_instruction_lines(worker.get("harness"))
        local_file_config = normalize_local_file_tool_config(runtime.get("localFiles") if isinstance(runtime.get("localFiles"), dict) else {})
        github_tool_config = normalize_github_tool_config(runtime.get("githubTools") if isinstance(runtime.get("githubTools"), dict) else {})
        instructions = (
            f"You are {worker['label']} in a sparse multi-lane reasoning loop.\n"
            f"Worker type: {worker.get('type', 'custom')}.\n"
            f"Role: {worker['role']}.\n"
            f"Your special focus is: {worker['focus']}.\n"
            f"Reasoning temperature: {worker.get('temperature', 'balanced')} ({WORKER_TEMPERATURE_CATALOG.get(worker.get('temperature', 'balanced'), {}).get('instruction', 'practical and evidence-first')}).\n"
            "Return JSON only that matches the schema exactly.\n"
            "Preserve disagreement rather than smoothing it away.\n"
            "Your checkpoint is steering pressure for a later lead answer; do not try to sound like the final user-facing assistant.\n"
            "The current commander draft is the lead hypothesis for this round.\n"
            "Your job is to test, qualify, narrow, or overturn that draft from your lane if the evidence or reasoning justifies it.\n"
            "Push, qualify, or defend from your lane, but do not narrate the whole system.\n"
            "Do not reveal hidden chain-of-thought.\n"
            f"Set workerId to {worker['id']}, label to {worker['label']}, role to {worker['role']}, focus to {worker['focus']}, modelUsed to {runtime['model']}, and step to {step_number}.\n"
            f"requestTargets must only contain peers from this list: {', '.join(peer_targets)}.\n"
            "If researchMode is web_search, use the web search tool before answering and keep evidence grounded in URLs actually consulted.\n"
            + (
                "If local file tools are available, inspect the relevant workspace files before asserting repository-specific details.\n"
                if local_file_config["enabled"]
                else ""
            )
            + (
                "If GitHub tools are available, inspect the allowlisted repositories directly before asserting GitHub-specific details.\n"
                if github_tool_config["enabled"]
                else ""
            )
            + "Every evidenceLedger item must capture one concrete claim, its supportLevel, the relevant sourceUrls, and a short note on why the evidence matters.\n"
            + "If evidence is missing or weak, say so in evidenceGaps instead of overstating certainty.\n"
            + "\n".join(harness_lines)
        )
        research_description = "Enabled. Workers may use web_search." if research_config["enabled"] else "Disabled. Workers must reason from existing context only."
        research_domains_text = ", ".join(research_config["domains"]) if research_config["domains"] else "none"
        input_text = (
            f"Objective:\n{task['objective']}\n\n"
            f"Session context:\n{session_context or 'none'}\n\n"
            f"Constraints:\n{chr(10).join(constraints)}\n\n"
            f"Worker roster:\n{json.dumps(task_workers(task, step_number), ensure_ascii=False, indent=2)}\n\n"
            f"Research policy:\n{research_description}\n"
            f"externalWebAccess: {research_config['externalWebAccess']}\n"
            f"allowedDomains: {research_domains_text}\n\n"
            f"Shared memory version seen:\n{prior_memory_version}\n\n"
            f"Current commander draft for this round:\n{commander_text}\n\n"
            f"Prior summary:\n{summary_text}\n\n"
            f"Peer steer addressed to this lane:\n{peer_text}\n\n"
            "Produce a checkpoint from your assigned viewpoint."
        )
        tools: List[Dict[str, Any]] = []
        tool_choice: Optional[str] = None
        include: List[str] = []
        function_handlers: Dict[str, Any] = {}
        if research_config["enabled"]:
            web_search_tool: Dict[str, Any] = {"type": "web_search", "external_web_access": bool(research_config["externalWebAccess"])}
            if research_config["domains"]:
                web_search_tool["filters"] = {"allowed_domains": list(research_config["domains"])}
            tools = [web_search_tool]
            tool_choice = "auto"
            include = ["web_search_call.action.sources"]
        if local_file_config["enabled"]:
            tools.extend(self.build_local_file_function_tools(local_file_config))
            tool_choice = "auto"
            function_handlers.update({
                "local_list_dir": lambda arguments: self.execute_local_file_tool_call("local_list_dir", arguments, local_file_config),
                "local_read_file": lambda arguments: self.execute_local_file_tool_call("local_read_file", arguments, local_file_config),
                "local_search_text": lambda arguments: self.execute_local_file_tool_call("local_search_text", arguments, local_file_config),
            })
        if github_tool_config["enabled"]:
            tools.extend(self.build_github_function_tools(github_tool_config))
            tool_choice = "auto"
            function_handlers.update({
                "github_list_paths": lambda arguments: self.execute_github_tool_call("github_list_paths", arguments, github_tool_config),
                "github_read_file": lambda arguments: self.execute_github_tool_call("github_read_file", arguments, github_tool_config),
                "github_get_issue": lambda arguments: self.execute_github_tool_call("github_get_issue", arguments, github_tool_config),
                "github_get_pull_request": lambda arguments: self.execute_github_tool_call("github_get_pull_request", arguments, github_tool_config),
                "github_get_commit": lambda arguments: self.execute_github_tool_call("github_get_commit", arguments, github_tool_config),
            })
        result = self.invoke_provider_json(
            provider=runtime["provider"],
            api_key=api_key,
            model=runtime["model"],
            reasoning_effort=runtime["reasoningEffort"],
            instructions=instructions,
            input_text=input_text,
            schema_name=f"worker_{worker['id'].lower()}_checkpoint",
            schema=self.worker_schema(),
            max_output_tokens=int(runtime["maxOutputTokens"]),
            target_kind="worker",
            tools=tools,
            tool_choice=tool_choice,
            include=include,
            function_handlers=function_handlers if function_handlers else None,
            auth_assignments=auth_assignments,
        )
        parsed = dict(result.parsed)
        parsed["researchQueries"] = normalize_string_array_preserve_items(result.web_search_queries)
        parsed["researchSources"] = normalize_url_array_values(result.web_search_sources)
        parsed["urlCitations"] = normalize_url_array_values(result.url_citations)
        parsed["localToolCalls"] = normalize_local_tool_calls(filter_tool_calls_by_prefixes(result.executed_tools, ("local_",)))
        parsed["localFileSources"] = collect_tool_sources_by_prefixes(result.executed_tools, ("local_",))
        parsed["githubToolCalls"] = normalize_local_tool_calls(filter_tool_calls_by_prefixes(result.executed_tools, ("github_",)))
        parsed["githubSources"] = normalize_url_array_values(collect_tool_sources_by_prefixes(result.executed_tools, ("github_",)))
        parsed["researchMode"] = (
            "web_search"
            if parsed["researchSources"] or parsed["researchQueries"]
            else ("research_requested_no_sources" if research_config["enabled"] else "model_only")
        )
        parsed["evidenceLedger"] = normalize_evidence_ledger(parsed.get("evidenceLedger", []))
        parsed["evidenceGaps"] = normalize_string_array_preserve_items(parsed.get("evidenceGaps", []))
        parsed["updatedAt"] = utc_now()
        call_meta = {
            "requestedMaxOutputTokens": result.requested_max_output_tokens,
            "effectiveMaxOutputTokens": result.effective_max_output_tokens,
            "attempts": result.attempts,
            "recoveredFromIncomplete": result.recovered_from_incomplete,
            "auth": result.auth_assignment,
            "authFailoverHistory": result.auth_failover_history,
            "localToolCalls": parsed["localToolCalls"],
            "localFileSources": parsed["localFileSources"],
            "githubToolCalls": parsed["githubToolCalls"],
            "githubSources": parsed["githubSources"],
        }
        return parsed, result.response_id, result.response, call_meta

    def project_task_for_summary(self, task: Dict[str, Any]) -> Dict[str, Any]:
        runtime = self.get_task_runtime(task)
        return {
            "taskId": str(task.get("taskId", "")),
            "objectivePreview": truncate_text(task.get("objective", ""), 220),
            "sessionContextPreview": truncate_text(task.get("sessionContext", ""), 220),
            "constraints": limit_string_list(task.get("constraints", []), 12, 240),
            "syncPolicy": task.get("syncPolicy") if isinstance(task.get("syncPolicy"), dict) else {},
            "runtime": {
                "executionMode": str(runtime["executionMode"]),
                "provider": str(runtime["provider"]),
                "model": str(runtime["model"]),
                "reasoningEffort": str(runtime["reasoningEffort"]),
                "budget": self.get_budget_config(task),
                "research": self.get_research_config(task),
                "localFiles": self.get_local_file_tool_config(task),
                "githubTools": self.get_github_tool_config(task),
                "dynamicSpinup": self.get_dynamic_spinup_config(task),
                "vetting": self.get_vetting_config(task),
            },
        }

    def project_commander_for_worker(self, commander: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        checkpoint = normalize_commander_checkpoint(commander or {})
        return {
            "round": int(checkpoint.get("round", 0) or 0),
            "stance": truncate_text(checkpoint.get("stance", ""), 220),
            "leadDirection": truncate_text(checkpoint.get("leadDirection", ""), 240),
            "answerDraft": truncate_text(checkpoint.get("answerDraft", ""), 520),
            "whyThisDirection": truncate_text(checkpoint.get("whyThisDirection", ""), 260),
            "questionsForWorkers": limit_string_list(checkpoint.get("questionsForWorkers", []), 3, 180),
            "pressurePoints": limit_string_list(checkpoint.get("pressurePoints", []), 3, 180),
            "keepCourseIf": limit_string_list(checkpoint.get("keepCourseIf", []), 2, 180),
            "changeCourseIf": limit_string_list(checkpoint.get("changeCourseIf", []), 2, 180),
            "uncertainty": limit_string_list(checkpoint.get("uncertainty", []), 2, 180),
            "suggestedLaneTypes": normalize_lane_type_list(checkpoint.get("suggestedLaneTypes", []), False, 2),
            "suggestedLaneReason": truncate_text(checkpoint.get("suggestedLaneReason", ""), 220),
        }

    def project_commander_for_summary(self, commander: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        checkpoint = normalize_commander_checkpoint(commander or {})
        return {
            "taskId": str(checkpoint.get("taskId", "")),
            "round": int(checkpoint.get("round", 0) or 0),
            "stance": truncate_text(checkpoint.get("stance", ""), 240),
            "leadDirection": truncate_text(checkpoint.get("leadDirection", ""), 260),
            "answerDraft": truncate_text(checkpoint.get("answerDraft", ""), 700),
            "whyThisDirection": truncate_text(checkpoint.get("whyThisDirection", ""), 320),
            "questionsForWorkers": limit_string_list(checkpoint.get("questionsForWorkers", []), 4, 220),
            "pressurePoints": limit_string_list(checkpoint.get("pressurePoints", []), 4, 220),
            "keepCourseIf": limit_string_list(checkpoint.get("keepCourseIf", []), 3, 220),
            "changeCourseIf": limit_string_list(checkpoint.get("changeCourseIf", []), 3, 220),
            "uncertainty": limit_string_list(checkpoint.get("uncertainty", []), 3, 220),
            "suggestedLaneTypes": normalize_lane_type_list(checkpoint.get("suggestedLaneTypes", []), False, 2),
            "suggestedLaneReason": truncate_text(checkpoint.get("suggestedLaneReason", ""), 240),
            "constraintsSeen": limit_string_list(checkpoint.get("constraintsSeen", []), 6, 180),
        }

    def project_commander_review_for_summary(
        self,
        commander_review: Optional[Dict[str, Any]],
        fallback_task: Optional[Dict[str, Any]] = None,
        fallback_round: int = 1,
        fallback_commander: Optional[Dict[str, Any]] = None,
        fallback_workers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        checkpoint = normalize_commander_review_checkpoint(
            commander_review or {},
            fallback_task,
            fallback_round,
            fallback_commander,
            fallback_workers,
        )
        return {
            "taskId": str(checkpoint.get("taskId", "")),
            "round": int(checkpoint.get("round", 0) or 0),
            "stance": truncate_text(checkpoint.get("stance", ""), 240),
            "leadDirection": truncate_text(checkpoint.get("leadDirection", ""), 260),
            "answerDraft": truncate_text(checkpoint.get("answerDraft", ""), 900),
            "whyThisDirection": truncate_text(checkpoint.get("whyThisDirection", ""), 320),
            "controlAudit": normalize_control_audit(checkpoint.get("controlAudit"), {
                "frontAnswer": {
                    "answer": checkpoint.get("answerDraft", ""),
                    "stance": checkpoint.get("stance", ""),
                    "leadDirection": checkpoint.get("leadDirection", ""),
                    "adversarialPressure": "",
                    "confidenceNote": "",
                },
                "summarizerOpinion": {
                    "stance": checkpoint.get("stance", ""),
                    "because": checkpoint.get("whyThisDirection", ""),
                    "uncertainty": (checkpoint.get("remainingUncertainty") or [""])[0],
                    "integrationMode": "The lead thread re-evaluates adversarial pressure before the public answer is formed.",
                },
                "claimsNeedingVerification": checkpoint.get("remainingUncertainty", []),
            }),
            "dynamicLaneDecision": normalize_dynamic_lane_decision(checkpoint.get("dynamicLaneDecision")),
            "dynamicLaneResolution": normalize_dynamic_lane_resolution(checkpoint.get("dynamicLaneResolution")),
            "remainingUncertainty": limit_string_list(checkpoint.get("remainingUncertainty", []), 4, 220),
            "sourceWorkers": normalize_worker_id_list(checkpoint.get("sourceWorkers", [])),
        }

    def project_prior_summary_for_worker(self, prior_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(prior_summary, dict):
            return {}
        review_trace = normalize_review_trace(prior_summary.get("reviewTrace", []))
        control_audit = normalize_control_audit(prior_summary.get("controlAudit"), prior_summary)
        return {
            "taskId": str(prior_summary.get("taskId", "")),
            "round": int(prior_summary.get("round", 0) or 0),
            "frontAnswer": normalize_front_answer(prior_summary.get("frontAnswer"), prior_summary),
            "summarizerOpinion": normalize_summarizer_opinion(prior_summary.get("summarizerOpinion"), prior_summary),
            "controlAudit": {
                "leadDraft": truncate_text(control_audit.get("leadDraft", ""), 220),
                "courseDecision": normalize_course_decision(control_audit.get("courseDecision"), "maintain"),
                "courseDecisionReason": truncate_text(control_audit.get("courseDecisionReason", ""), 220),
                "contributionAssessments": normalize_contribution_assessments(control_audit.get("contributionAssessments", []))[:2],
                "acceptedAdversarialPoints": limit_string_list(control_audit.get("acceptedAdversarialPoints", []), 2, 180),
                "rejectedAdversarialPoints": limit_string_list(control_audit.get("rejectedAdversarialPoints", []), 2, 180),
                "heldOutConcerns": limit_string_list(control_audit.get("heldOutConcerns", []), 2, 180),
                "selfCheck": truncate_text(control_audit.get("selfCheck", ""), 220),
            },
            "stableFindings": limit_string_list(prior_summary.get("stableFindings", []), 3, 220),
            "conditionalTruths": limit_string_list(prior_summary.get("conditionalTruths", []), 3, 220),
            "claimsNeedingVerification": limit_string_list(prior_summary.get("claimsNeedingVerification", []), 3, 220),
            "reviewTrace": [
                {
                    "topic": truncate_text(item.get("topic", ""), 180),
                    "judgment": truncate_text(item.get("judgment", ""), 220),
                }
                for item in review_trace[:2]
            ],
            "recommendedNextAction": truncate_text(prior_summary.get("recommendedNextAction", ""), 220),
            "vettingSummary": truncate_text(prior_summary.get("vettingSummary", ""), 220),
        }

    def project_worker_roster_for_summary(self, workers: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        return [
            {
                "id": worker["id"],
                "type": worker.get("type", ""),
                "label": worker["label"],
                "role": worker["role"],
                "focus": truncate_text(worker["focus"], 180),
                "temperature": worker.get("temperature", "balanced"),
                "model": worker["model"],
            }
            for worker in workers
        ]

    def project_worker_checkpoint_for_summary(self, checkpoint: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(checkpoint, dict):
            return None
        ledger: List[Dict[str, Any]] = []
        for entry in checkpoint.get("evidenceLedger", [])[:6] if isinstance(checkpoint.get("evidenceLedger"), list) else []:
            if not isinstance(entry, dict):
                continue
            ledger.append(
                {
                    "claim": truncate_text(entry.get("claim", ""), 260),
                    "supportLevel": str(entry.get("supportLevel", "")),
                    "sourceUrls": limit_url_list(entry.get("sourceUrls", []), 6),
                    "note": truncate_text(entry.get("note", ""), 220),
                }
            )
        return {
            "workerId": str(checkpoint.get("workerId", "")),
            "label": str(checkpoint.get("label", "")),
            "role": str(checkpoint.get("role", "")),
            "focus": truncate_text(checkpoint.get("focus", ""), 180),
            "step": int(checkpoint.get("step", 0) or 0),
            "observation": truncate_text(checkpoint.get("observation", ""), 420),
            "benefits": limit_string_list(checkpoint.get("benefits", []), 4, 180),
            "detriments": limit_string_list(checkpoint.get("detriments", []), 4, 180),
            "requiredCircumstances": limit_string_list(checkpoint.get("requiredCircumstances", []), 4, 180),
            "invalidatingCircumstances": limit_string_list(checkpoint.get("invalidatingCircumstances", []), 4, 180),
            "immediateConsequences": limit_string_list(checkpoint.get("immediateConsequences", []), 4, 180),
            "downstreamConsequences": limit_string_list(checkpoint.get("downstreamConsequences", []), 4, 180),
            "uncertainty": limit_string_list(checkpoint.get("uncertainty", []), 4, 180),
            "reversalConditions": limit_string_list(checkpoint.get("reversalConditions", []), 4, 180),
            "researchMode": str(checkpoint.get("researchMode", "")),
            "researchQueries": limit_string_list(checkpoint.get("researchQueries", []), 6, 180),
            "researchSources": limit_url_list(checkpoint.get("researchSources", []), 10),
            "urlCitations": limit_url_list(checkpoint.get("urlCitations", []), 10),
            "localFileSources": limit_string_list(checkpoint.get("localFileSources", []), 10, 220),
            "localToolCalls": normalize_local_tool_calls(checkpoint.get("localToolCalls", []))[:6],
            "githubSources": limit_url_list(checkpoint.get("githubSources", []), 10),
            "githubToolCalls": normalize_local_tool_calls(checkpoint.get("githubToolCalls", []))[:6],
            "evidenceLedger": ledger,
            "evidenceGaps": limit_string_list(checkpoint.get("evidenceGaps", []), 6, 180),
            "confidence": float(checkpoint.get("confidence", 0.0) or 0.0),
            "requestToPeer": truncate_text(checkpoint.get("requestToPeer", ""), 220),
            "requestTargets": normalize_worker_id_list(checkpoint.get("requestTargets", [])),
            "sharedMemorySeen": checkpoint.get("sharedMemorySeen") if isinstance(checkpoint.get("sharedMemorySeen"), dict) else {},
        }

    def project_worker_state_for_summary(self, worker_state: Dict[str, Any], workers: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        projected: List[Dict[str, Any]] = []
        for worker in workers:
            checkpoint = self.project_worker_checkpoint_for_summary(worker_state.get(worker["id"]))
            if checkpoint is not None:
                projected.append(checkpoint)
        return projected

    def build_summary_line_catalog(self, worker_state: Dict[str, Any], workers: List[Dict[str, str]], max_items_per_worker: int = 14) -> List[Dict[str, Any]]:
        catalog: List[Dict[str, Any]] = []
        ordered_fields = [
            ("benefits", "benefit"),
            ("detriments", "risk"),
            ("requiredCircumstances", "requirement"),
            ("invalidatingCircumstances", "invalidator"),
            ("immediateConsequences", "immediate_consequence"),
            ("downstreamConsequences", "downstream_consequence"),
            ("uncertainty", "uncertainty"),
            ("reversalConditions", "reversal_condition"),
            ("evidenceGaps", "evidence_gap"),
        ]

        for worker in workers:
            checkpoint = self.project_worker_checkpoint_for_summary(worker_state.get(worker["id"]))
            if checkpoint is None:
                continue
            worker_id = str(checkpoint.get("workerId", worker["id"]))
            label = str(checkpoint.get("label", worker.get("label", worker_id)))
            role = str(checkpoint.get("role", worker.get("role", "")))
            step = int(checkpoint.get("step", 0) or 0)
            added = 0

            def append_line(ref_suffix: str, kind: str, text: Any, source_urls: Optional[List[str]] = None, support_level: str = "") -> None:
                nonlocal added
                if added >= max_items_per_worker:
                    return
                content = truncate_text(text, 300)
                if not content:
                    return
                catalog.append(
                    {
                        "ref": f"{worker_id}.{ref_suffix}",
                        "workerId": worker_id,
                        "label": label,
                        "role": role,
                        "step": step,
                        "kind": kind,
                        "text": content,
                        "supportLevel": support_level,
                        "sourceUrls": limit_url_list(source_urls or [], 8),
                    }
                )
                added += 1

            append_line("observation", "observation", checkpoint.get("observation", ""))

            for index, entry in enumerate(checkpoint.get("evidenceLedger", []) if isinstance(checkpoint.get("evidenceLedger"), list) else []):
                if not isinstance(entry, dict):
                    continue
                claim = truncate_text(entry.get("claim", ""), 220)
                note = truncate_text(entry.get("note", ""), 140)
                combined = claim
                if note:
                    combined = f"{claim} Evidence note: {note}" if claim else note
                append_line(
                    f"evidenceLedger[{index}]",
                    "evidence",
                    combined,
                    entry.get("sourceUrls", []),
                    str(entry.get("supportLevel", "")).strip(),
                )

            for field_name, kind in ordered_fields:
                for index, item in enumerate(checkpoint.get(field_name, []) if isinstance(checkpoint.get(field_name), list) else []):
                    append_line(f"{field_name}[{index}]", kind, item)

            for index, url in enumerate(checkpoint.get("urlCitations", [])[:2] if isinstance(checkpoint.get("urlCitations"), list) else []):
                append_line(f"urlCitations[{index}]", "citation", url, [url], "cited")

            append_line("requestToPeer", "peer_steer", checkpoint.get("requestToPeer", ""))

        return normalize_summary_line_catalog(catalog)

    def new_mock_summary(
        self,
        task: Dict[str, Any],
        commander_checkpoint: Optional[Dict[str, Any]],
        commander_review_checkpoint: Optional[Dict[str, Any]],
        workers: List[Dict[str, str]],
        worker_state: Dict[str, Any],
        vetting_config: Dict[str, Any],
        line_catalog: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        round_number = 0
        for worker in workers:
            checkpoint = worker_state.get(worker["id"])
            if isinstance(checkpoint, dict):
                round_number = max(round_number, int(checkpoint.get("step", 0) or 0))
        packets = self.expand_peer_steer_packets(task, {"workers": worker_state}, round_number)
        conflicts: List[Dict[str, Any]] = []
        review_trace: List[Dict[str, Any]] = []
        primary = next((worker for worker in workers if worker["id"] == "A"), workers[0] if workers else None)
        challengers = [worker for worker in workers if worker["id"] != "A"][:3]
        commander_projection = self.project_commander_for_summary(commander_checkpoint)
        commander_review_projection = self.project_commander_review_for_summary(
            commander_review_checkpoint,
            task,
            max(round_number, int(commander_projection.get("round", 0) or 1)),
            commander_checkpoint,
            [worker["id"] for worker in workers if isinstance(worker_state.get(worker["id"]), dict)],
        )
        primary_checkpoint = self.project_worker_checkpoint_for_summary(worker_state.get(primary["id"])) if primary else None

        def pick_refs(worker_id: str, prefixes: List[str], limit: int = 3) -> List[str]:
            refs: List[str] = []
            for entry in line_catalog:
                if str(entry.get("workerId", "")) != worker_id:
                    continue
                ref = str(entry.get("ref", ""))
                if not ref:
                    continue
                if not any(ref.startswith(f"{worker_id}.{prefix}") for prefix in prefixes):
                    continue
                refs.append(ref)
                if len(refs) >= limit:
                    break
            return refs

        for challenger in challengers:
            conflicts.append(
                {
                    "topic": challenger["focus"],
                    "positions": [
                        {
                            "workerId": primary["id"] if primary else worker["id"],
                            "claim": "Momentum is only justified when it remains auditable and budget-bounded.",
                        },
                        {
                            "workerId": challenger["id"],
                            "claim": f"This lane argues that the design is still exposed around {challenger['focus']}.",
                        },
                    ],
                }
            )
            review_trace.append(
                {
                    "topic": truncate_text(challenger["focus"], 180),
                    "judgment": f"My current view keeps the design, but only if the answer absorbs the objection around {challenger['focus']}.",
                    "because": "The positive case is still useful, but the adversarial line identifies a condition that should shape the final wording rather than sit beside it as a recap.",
                    "supportingLineRefs": pick_refs(primary["id"], ["observation", "benefits", "evidenceLedger"], 3) if primary else [],
                    "challengingLineRefs": pick_refs(challenger["id"], ["detriments", "uncertainty", "evidenceLedger", "evidenceGaps"], 3),
                    "openQuestions": ["Which retained risk needs to be surfaced directly in the public answer?"],
                }
            )
        lead_direction = truncate_text(
            commander_review_projection.get("leadDirection", "")
            or commander_projection.get("leadDirection", "")
            or (primary_checkpoint or {}).get("observation", "")
            or task.get("objective", ""),
            320,
        ) or "Use the current task as the lead direction and keep the answer evidence-aware."
        strongest_pressure = truncate_text(
            next(
                (
                    self.project_worker_checkpoint_for_summary(worker_state.get(challenger["id"])) or {}
                ).get("observation", "")
                or challenger["focus"]
                for challenger in challengers
            ) if challengers else "",
            260,
        ) or "No strong adversarial pressure was captured."
        front_answer_parts = [lead_direction]
        if strongest_pressure:
            front_answer_parts.append(
                "Strongest retained pressure: "
                + strongest_pressure
                + "."
            )
        front_answer_parts.append(
            "This is a provisional fallback answer because live summarization did not complete cleanly."
        )
        front_answer_text = "\n\n".join(front_answer_parts)
        review_control_audit = normalize_control_audit(
            commander_review_projection.get("controlAudit"),
            {
                "frontAnswer": {
                    "answer": commander_review_projection.get("answerDraft", "") or lead_direction,
                    "stance": commander_review_projection.get("stance", "") or lead_direction,
                    "leadDirection": commander_review_projection.get("leadDirection", "") or lead_direction,
                    "adversarialPressure": strongest_pressure,
                    "confidenceNote": "",
                },
                "summarizerOpinion": {
                    "stance": commander_review_projection.get("stance", "") or lead_direction,
                    "because": commander_review_projection.get("whyThisDirection", ""),
                    "uncertainty": (commander_review_projection.get("remainingUncertainty") or [""])[0],
                    "integrationMode": "The lead thread re-evaluates adversarial pressure before the public answer is formed.",
                },
                "claimsNeedingVerification": commander_review_projection.get("remainingUncertainty", []),
            },
        )
        dynamic_lane_decision = normalize_dynamic_lane_decision(commander_review_projection.get("dynamicLaneDecision"))
        dynamic_lane_resolution = normalize_dynamic_lane_resolution(commander_review_projection.get("dynamicLaneResolution"))
        return {
            "taskId": task["taskId"],
            "round": round_number,
            "frontAnswer": {
                "answer": truncate_text(commander_review_projection.get("answerDraft", ""), 3200) or front_answer_text,
                "stance": truncate_text(commander_review_projection.get("stance", ""), 260) or lead_direction,
                "leadDirection": truncate_text(commander_review_projection.get("leadDirection", ""), 260) or lead_direction,
                "adversarialPressure": strongest_pressure,
                "confidenceNote": (
                    "This is a fallback summary based on task and checkpoint structure, so the reasoning shape is stronger than the factual validation."
                    if vetting_config["enabled"]
                    else "Vetting is disabled here, so this fallback answer is structurally useful but weakly evidenced."
                ),
            },
            "summarizerOpinion": {
                "stance": truncate_text(commander_review_projection.get("stance", ""), 260)
                or "I would keep the lead direction grounded in the current task and let adversarial pressure narrow it only where it materially improves the answer.",
                "because": truncate_text(commander_review_projection.get("whyThisDirection", ""), 360)
                or "Even in fallback mode, the strongest available grounding comes from the current task, the current commander review, and the latest worker checkpoints, not from generic lane mythology.",
                "uncertainty": truncate_text((commander_review_projection.get("remainingUncertainty") or [""])[0], 260)
                or "Live summarization failed, so the output is weaker than a completed live merge and should be treated as provisional.",
                "integrationMode": "Start from the commander review, then preserve its course decision while packaging the answer for the user.",
            },
            "controlAudit": review_control_audit,
            "dynamicLaneDecision": dynamic_lane_decision,
            "dynamicLaneResolution": dynamic_lane_resolution,
            "reviewTrace": review_trace,
            "stableFindings": [
                "Structured checkpoints let many lanes disagree without losing continuity.",
                "Budget ceilings are mandatory once multiple model-backed lanes are active.",
                "Per-position model selection changes both quality and spend, so it must be visible.",
            ],
            "conflicts": conflicts,
            "conditionalTruths": [
                "More lanes help only when each lane preserves a distinct viewpoint.",
                "Adversarial expansion is useful when the spend ceiling and output cap stay hard enough to prevent runaway loops.",
                "Mixing models by position can improve robustness if the cheaper lanes carry most of the exploration.",
            ],
            "vettingSummary": (
                "Mock vetting suggests the checkpoint schema is ready for evidence review, but the claims still need live sourced validation."
                if vetting_config["enabled"]
                else "Vetting is disabled; this summary preserves conflicts but does not score evidence quality."
            ),
            "evidenceVerdicts": [
                {
                    "claim": "Budget ceilings are necessary once multiple live lanes are active.",
                    "status": "weak" if vetting_config["enabled"] else "unvetted",
                    "supportingWorkers": ["A", "B"],
                    "challengingWorkers": [],
                    "sourceUrls": [],
                    "rationale": "Mock mode cannot confirm the claim with live source evidence, but both lanes converge on it as an operating principle.",
                }
            ],
            "claimsNeedingVerification": [
                "Any claim that relies on current external facts rather than local design intent.",
                "Any recommendation that assumes the current pricing or capability mix stays unchanged.",
            ],
            "evidenceCoverage": {
                "supported": 0,
                "mixed": 0,
                "weak": 1 if vetting_config["enabled"] else 0,
                "unsupported": 0,
                "unvetted": 0 if vetting_config["enabled"] else 1,
            },
            "peerSteerPackets": packets,
            "recommendedNextAction": "Keep the default live model cheap, override only the lanes that need stronger reasoning, and review cost deltas after each round.",
            "sourceWorkers": normalize_worker_id_list(commander_review_projection.get("sourceWorkers", [])) or [worker["id"] for worker in workers],
            "mergedAt": utc_now(),
        }

    def summary_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "taskId",
                "round",
                "frontAnswer",
                "summarizerOpinion",
                "controlAudit",
                "dynamicLaneDecision",
                "reviewTrace",
                "stableFindings",
                "conflicts",
                "conditionalTruths",
                "vettingSummary",
                "evidenceVerdicts",
                "claimsNeedingVerification",
                "evidenceCoverage",
                "peerSteerPackets",
                "recommendedNextAction",
                "sourceWorkers",
            ],
            "properties": {
                "taskId": {"type": "string"},
                "round": {"type": "integer"},
                "frontAnswer": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["answer", "stance", "leadDirection", "adversarialPressure", "confidenceNote"],
                    "properties": {
                        "answer": {"type": "string"},
                        "stance": {"type": "string"},
                        "leadDirection": {"type": "string"},
                        "adversarialPressure": {"type": "string"},
                        "confidenceNote": {"type": "string"},
                    },
                },
                "summarizerOpinion": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["stance", "because", "uncertainty", "integrationMode"],
                    "properties": {
                        "stance": {"type": "string"},
                        "because": {"type": "string"},
                        "uncertainty": {"type": "string"},
                        "integrationMode": {"type": "string"},
                    },
                },
                "controlAudit": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "leadDraft",
                        "integrationQuestion",
                        "courseDecision",
                        "courseDecisionReason",
                        "contributionAssessments",
                        "acceptedAdversarialPoints",
                        "rejectedAdversarialPoints",
                        "heldOutConcerns",
                        "selfCheck",
                    ],
                    "properties": {
                        "leadDraft": {"type": "string"},
                        "integrationQuestion": {"type": "string"},
                        "courseDecision": {"type": "string"},
                        "courseDecisionReason": {"type": "string"},
                        "contributionAssessments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["contribution", "value", "effect", "reason"],
                                "properties": {
                                    "contribution": {"type": "string"},
                                    "value": {"type": "string"},
                                    "effect": {"type": "string"},
                                    "reason": {"type": "string"},
                                },
                            },
                        },
                        "acceptedAdversarialPoints": {"type": "array", "items": {"type": "string"}},
                        "rejectedAdversarialPoints": {"type": "array", "items": {"type": "string"}},
                        "heldOutConcerns": {"type": "array", "items": {"type": "string"}},
                        "selfCheck": {"type": "string"},
                    },
                },
                "reviewTrace": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["topic", "judgment", "because", "supportingLineRefs", "challengingLineRefs", "openQuestions"],
                        "properties": {
                            "topic": {"type": "string"},
                            "judgment": {"type": "string"},
                            "because": {"type": "string"},
                            "supportingLineRefs": {"type": "array", "items": {"type": "string"}},
                            "challengingLineRefs": {"type": "array", "items": {"type": "string"}},
                            "openQuestions": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "dynamicLaneDecision": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["shouldSpawn", "suggestedLaneTypes", "reason", "requiredPressure", "temperature", "instruction"],
                    "properties": {
                        "shouldSpawn": {"type": "boolean"},
                        "suggestedLaneTypes": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"},
                        "requiredPressure": {"type": "string"},
                        "temperature": {"type": "string"},
                        "instruction": {"type": "string"},
                    },
                },
                "stableFindings": {"type": "array", "items": {"type": "string"}},
                "conflicts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["topic", "positions"],
                        "properties": {
                            "topic": {"type": "string"},
                            "positions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["workerId", "claim"],
                                    "properties": {"workerId": {"type": "string"}, "claim": {"type": "string"}},
                                },
                            },
                        },
                    },
                },
                "conditionalTruths": {"type": "array", "items": {"type": "string"}},
                "vettingSummary": {"type": "string"},
                "evidenceVerdicts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["claim", "status", "supportingWorkers", "challengingWorkers", "sourceUrls", "rationale"],
                        "properties": {
                            "claim": {"type": "string"},
                            "status": {"type": "string"},
                            "supportingWorkers": {"type": "array", "items": {"type": "string"}},
                            "challengingWorkers": {"type": "array", "items": {"type": "string"}},
                            "sourceUrls": {"type": "array", "items": {"type": "string"}},
                            "rationale": {"type": "string"},
                        },
                    },
                },
                "claimsNeedingVerification": {"type": "array", "items": {"type": "string"}},
                "evidenceCoverage": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["supported", "mixed", "weak", "unsupported", "unvetted"],
                    "properties": {
                        "supported": {"type": "integer"},
                        "mixed": {"type": "integer"},
                        "weak": {"type": "integer"},
                        "unsupported": {"type": "integer"},
                        "unvetted": {"type": "integer"},
                    },
                },
                "peerSteerPackets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["from", "to", "message"],
                        "properties": {
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "message": {"type": "string"},
                        },
                    },
                },
                "recommendedNextAction": {"type": "string"},
                "sourceWorkers": {"type": "array", "items": {"type": "string"}},
            },
        }

    def new_live_summary(
        self,
        api_key: str,
        auth_assignments: Optional[List[Dict[str, Any]]],
        task: Dict[str, Any],
        commander_checkpoint: Optional[Dict[str, Any]],
        commander_review_checkpoint: Optional[Dict[str, Any]],
        workers: List[Dict[str, str]],
        worker_state: Dict[str, Any],
        runtime: Dict[str, Any],
        vetting_config: Dict[str, Any],
        line_catalog: List[Dict[str, Any]],
        partial_mode: bool = False,
        pending_workers: Optional[List[str]] = None,
    ) -> tuple[Dict[str, Any], str, Dict[str, Any], Dict[str, Any]]:
        summary_config = summarizer_config(task)
        harness_lines = summarizer_harness_instruction_lines(summary_config.get("harness"))
        constraints = limit_string_list(task.get("constraints", []), 24, 400)
        session_context = str(task.get("sessionContext", "")).strip()
        commander_projection = self.project_commander_for_summary(commander_checkpoint)
        commander_review_projection = self.project_commander_review_for_summary(
            commander_review_checkpoint,
            task,
            int(commander_projection.get("round", 0) or 1),
            commander_checkpoint,
            [worker["id"] for worker in workers if isinstance(worker_state.get(worker["id"]), dict)],
        )
        pending_workers = normalize_worker_id_list(pending_workers or [])
        has_commander_review = isinstance(commander_review_checkpoint, dict) and int(commander_review_checkpoint.get("round", 0) or 0) > 0
        instructions = (
            "You are the summarizer in a sparse multi-lane reasoning loop.\n"
            "Merge all worker checkpoints into a structured adjudication.\n"
            "Act as the evidence vetter for the shared memory.\n"
            "Preserve disagreements and conditional truths.\n"
            "Do not erase contradictions.\n"
            "Judge worker claims using the evidence they provide.\n"
            "Form an opinion from the worker evidence and arguments instead of narrating the process.\n"
            "Treat the public answer as a lead thought, not a consensus blend.\n"
            "The lead thread stays in control at all times.\n"
        )
        instructions += (
            "The supplied commander review is the authoritative lead-thread reevaluation for this round.\n"
            "Preserve its controlAudit and dynamicLaneDecision in your output instead of making a fresh lane request.\n"
            "Start from the supplied commander review answerDraft when forming the visible answer.\n"
            "Let the public answer reflect that reevaluated course cleanly, without re-running the course decision from scratch.\n"
            if has_commander_review
            else
            "Start from the supplied commander draft for this round unless the surviving objections justify changing it.\n"
            "Write that commander-facing starting point into controlAudit.leadDraft.\n"
            "Then question each strong adversarial contribution against one control question: does it improve correctness, scope, safety, or usefulness, or does it merely pull the answer off course?\n"
            "Write that question into controlAudit.integrationQuestion.\n"
            "After that check, make one explicit course decision for the visible answer: maintain, qualify, redirect, or reverse.\n"
            "Default to maintain when objections only add support, evidence, or guardrails.\n"
            "Use qualify when the answer stays on course but needs narrower scope, sharper conditions, or stronger caveats.\n"
            "Use redirect when the answer's destination changes but the user's core goal still points the same way.\n"
            "Use reverse only when adversarial pressure shows the original direction would be materially wrong, unsafe, or misleading.\n"
            "Write that label into controlAudit.courseDecision and explain it in controlAudit.courseDecisionReason.\n"
            "For the 1 to 4 strongest contributions, write controlAudit.contributionAssessments with contribution, value, effect, and reason.\n"
            "Use value to judge how much the contribution improved the final answer: high, medium, low, or negative.\n"
            "Use effect to judge whether the contribution supported, qualified, redirected, reversed, or should be rejected.\n"
            "Only absorb adversarial pressure that survives that check.\n"
            "Put accepted pressure into controlAudit.acceptedAdversarialPoints.\n"
            "Put rejected or downgraded pressure into controlAudit.rejectedAdversarialPoints.\n"
            "Put concerns you are keeping visible but not letting dominate the answer into controlAudit.heldOutConcerns.\n"
            "Before you finalize frontAnswer.answer, compare the final wording against your own lead draft and the user's actual request.\n"
            "Write that last self-audit into controlAudit.selfCheck.\n"
        )
        instructions += (
            "Use adversarial pressure to improve the answer, not to speak directly through it.\n"
            "Do not let the summarizer behave like a funnel that merely forwards or averages lane output.\n"
            "frontAnswer.answer must read like a normal single-assistant reply to the user.\n"
            "frontAnswer.answer should feel more reasonable because it privately absorbed objections, not because it publicly recaps them.\n"
            "Prefer a decisive but conditional answer over a timid laundry list of caveats.\n"
            "Do not let the mere existence of objections trigger a course change.\n"
            "Indecisive drift is worse than a clear qualified answer when the evidence does not justify reversal.\n"
            "Do not mention workers, lanes, adversaries, or hidden process inside frontAnswer.answer unless the user explicitly asked for process detail.\n"
            "frontAnswer.stance should capture your current view in one sentence.\n"
            "frontAnswer.leadDirection should state the answer's leading direction before pressure-testing refined it.\n"
            "frontAnswer.adversarialPressure should name the strongest internal objection that changed or constrained the answer.\n"
            "summarizerOpinion is review-facing and may speak in the first person.\n"
            "summarizerOpinion.integrationMode should explain how the strongest objections changed the lead direction.\n"
            "controlAudit is review-facing and should show that the lead thread actively interrogated adversarial pressure instead of submitting to it.\n"
            "reviewTrace is for review operations, not for the public answer.\n"
        )
        instructions += (
            "Copy dynamicLaneDecision from the commander review unchanged unless the supplied value is malformed.\n"
            if has_commander_review
            else
            "Use dynamicLaneDecision to decide whether the next round needs one additional adversarial lane.\n"
            "Only set dynamicLaneDecision.shouldSpawn to true when a materially missing adversarial lens remains unresolved after the current round.\n"
            "dynamicLaneDecision.suggestedLaneTypes may contain up to 2 adversarial lane types from the known catalog.\n"
            "dynamicLaneDecision.requiredPressure should name the unresolved pressure the next lane must attack.\n"
            "dynamicLaneDecision.temperature may be cool, balanced, or hot when the next lane needs a specific reasoning temperature.\n"
            "dynamicLaneDecision.instruction should be one short harness instruction for the next spawned lane.\n"
            "Prefer false when the current roster already covers the relevant pressure.\n"
        )
        instructions += (
            "Every reviewTrace line ref must come from the supplied line catalog exactly as written.\n"
            "Do not upgrade weak evidence into a supported fact.\n"
            "Do not do new research.\n"
            "If vetting is disabled, keep verdicts conservative and mark unsupported confidence clearly.\n"
        )
        if partial_mode:
            instructions += (
                "This is a partial summary request.\n"
                "Some worker checkpoints are still missing or still running.\n"
                "Use only the currently available checkpoints.\n"
                "The public answer should still be useful and decisive, but its confidence note must clearly reflect the missing evidence.\n"
            )
        instructions += "\n".join(harness_lines)
        instructions += "\nReturn JSON only that matches the schema exactly."
        input_text = (
            f"Authoritative current user input:\n{task.get('objective', '')}\n\n"
            f"Current constraints:\n{chr(10).join(constraints) if constraints else 'none'}\n\n"
            f"Carry-forward session context (background only, not authoritative):\n{session_context or 'none'}\n\n"
            f"Commander draft for this round:\n{json.dumps(commander_projection, ensure_ascii=False, indent=2)}\n\n"
            f"Commander review for this round:\n{json.dumps(commander_review_projection, ensure_ascii=False, indent=2)}\n\n"
            f"Task brief:\n{json.dumps(self.project_task_for_summary(task), ensure_ascii=False, indent=2)}\n\n"
            f"Worker lineup:\n{json.dumps(self.project_worker_roster_for_summary(workers), ensure_ascii=False, indent=2)}\n\n"
            f"Known adversarial lane types:\n{json.dumps(normalize_lane_type_list(list(WORKER_TYPE_CATALOG.keys()), False, 32), ensure_ascii=False, indent=2)}\n\n"
            f"Partial summary mode:\n{partial_mode}\n\n"
            f"Pending workers:\n{json.dumps(pending_workers, ensure_ascii=False, indent=2)}\n\n"
            f"Vetting enabled:\n{vetting_config['enabled']}\n\n"
            f"Worker checkpoint digests:\n{json.dumps(self.project_worker_state_for_summary(worker_state, workers), ensure_ascii=False, indent=2)}\n\n"
            f"Worker review line catalog:\n{json.dumps(line_catalog, ensure_ascii=False, indent=2)}"
        )
        result = self.invoke_provider_json(
            provider=runtime["provider"],
            api_key=api_key,
            model=runtime["model"],
            reasoning_effort=runtime["reasoningEffort"],
            instructions=instructions,
            input_text=input_text,
            schema_name="loop_summary_multi",
            schema=self.summary_schema(),
            max_output_tokens=int(runtime["maxOutputTokens"]),
            target_kind="summarizer",
            auth_assignments=auth_assignments,
        )
        parsed = dict(result.parsed)
        authoritative_round = int(commander_review_projection.get("round", 0) or commander_projection.get("round", 0) or 0)
        if authoritative_round > 0:
            parsed["round"] = authoritative_round
        if has_commander_review:
            parsed["controlAudit"] = commander_review_projection.get("controlAudit", parsed.get("controlAudit"))
            parsed["dynamicLaneDecision"] = commander_review_projection.get("dynamicLaneDecision", parsed.get("dynamicLaneDecision"))
            parsed["dynamicLaneResolution"] = commander_review_projection.get("dynamicLaneResolution", parsed.get("dynamicLaneResolution"))
            front_answer = parsed.get("frontAnswer") if isinstance(parsed.get("frontAnswer"), dict) else {}
            if not str(front_answer.get("leadDirection", "")).strip():
                front_answer["leadDirection"] = commander_review_projection.get("leadDirection", "")
            if not str(front_answer.get("stance", "")).strip():
                front_answer["stance"] = commander_review_projection.get("stance", "")
            parsed["frontAnswer"] = front_answer
        parsed["evidenceVerdicts"] = normalize_evidence_verdicts(parsed.get("evidenceVerdicts", []))
        parsed["claimsNeedingVerification"] = normalize_string_array_preserve_items(parsed.get("claimsNeedingVerification", []))
        parsed["mergedAt"] = utc_now()
        call_meta = {
            "requestedMaxOutputTokens": result.requested_max_output_tokens,
            "effectiveMaxOutputTokens": result.effective_max_output_tokens,
            "attempts": result.attempts,
            "recoveredFromIncomplete": result.recovered_from_incomplete,
            "auth": result.auth_assignment,
            "authFailoverHistory": result.auth_failover_history,
        }
        return parsed, result.response_id, result.response, call_meta

    def normalize_checkpoint(self, task: Dict[str, Any], worker_id: str, worker: Dict[str, str], runtime: Dict[str, Any], checkpoint: Dict[str, Any], step_number: int) -> Dict[str, Any]:
        checkpoint["step"] = step_number
        checkpoint["workerId"] = worker_id
        checkpoint["label"] = worker["label"]
        checkpoint["role"] = worker["role"]
        checkpoint["focus"] = worker["focus"]
        checkpoint["modelUsed"] = runtime["model"]
        for field in (
            "benefits",
            "detriments",
            "requiredCircumstances",
            "invalidatingCircumstances",
            "immediateConsequences",
            "downstreamConsequences",
            "uncertainty",
            "reversalConditions",
            "constraintsSeen",
            "researchQueries",
            "evidenceGaps",
            "localFileSources",
        ):
            checkpoint[field] = normalize_string_array_preserve_items(checkpoint.get(field, []))
        checkpoint["researchSources"] = normalize_url_array_values(checkpoint.get("researchSources", []))
        checkpoint["urlCitations"] = normalize_url_array_values(checkpoint.get("urlCitations", []))
        checkpoint["githubSources"] = normalize_url_array_values(checkpoint.get("githubSources", []))
        checkpoint["evidenceLedger"] = normalize_evidence_ledger(checkpoint.get("evidenceLedger", []))
        checkpoint["localToolCalls"] = normalize_local_tool_calls(checkpoint.get("localToolCalls", []))
        checkpoint["githubToolCalls"] = normalize_local_tool_calls(checkpoint.get("githubToolCalls", []))
        checkpoint["requestTargets"] = self.normalize_request_targets(checkpoint.get("requestTargets", []), task, worker_id, step_number)
        checkpoint["updatedAt"] = utc_now()
        return checkpoint

    def normalize_summary(self, summary: Dict[str, Any], line_catalog: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        summary["frontAnswer"] = normalize_front_answer(summary.get("frontAnswer"), summary)
        summary["summarizerOpinion"] = normalize_summarizer_opinion(summary.get("summarizerOpinion"), summary)
        summary["controlAudit"] = normalize_control_audit(summary.get("controlAudit"), summary)
        summary["dynamicLaneDecision"] = normalize_dynamic_lane_decision(summary.get("dynamicLaneDecision"))
        summary["dynamicLaneResolution"] = normalize_dynamic_lane_resolution(summary.get("dynamicLaneResolution"))
        summary["reviewTrace"] = normalize_review_trace(summary.get("reviewTrace", []))
        summary["stableFindings"] = normalize_string_array_preserve_items(summary.get("stableFindings", []))
        summary["conditionalTruths"] = normalize_string_array_preserve_items(summary.get("conditionalTruths", []))
        summary["claimsNeedingVerification"] = normalize_string_array_preserve_items(summary.get("claimsNeedingVerification", []))
        summary["sourceWorkers"] = normalize_worker_id_list(summary.get("sourceWorkers", []))
        summary["evidenceVerdicts"] = normalize_evidence_verdicts(summary.get("evidenceVerdicts", []))
        summary["lineCatalog"] = normalize_summary_line_catalog(line_catalog if line_catalog is not None else summary.get("lineCatalog", []))
        valid_refs = {entry.get("ref", "") for entry in summary["lineCatalog"] if isinstance(entry, dict)}
        for entry in summary["reviewTrace"]:
            entry["supportingLineRefs"] = [ref for ref in entry.get("supportingLineRefs", []) if ref in valid_refs]
            entry["challengingLineRefs"] = [ref for ref in entry.get("challengingLineRefs", []) if ref in valid_refs]
        summary["mergedAt"] = summary.get("mergedAt") or utc_now()
        return summary

    def annotate_partial_summary(self, summary: Dict[str, Any], available_workers: List[str], pending_workers: List[str]) -> Dict[str, Any]:
        available_workers = normalize_worker_id_list(available_workers)
        pending_workers = normalize_worker_id_list(pending_workers)
        note_bits = []
        if available_workers:
            note_bits.append("Used current checkpoints from " + ", ".join(available_workers) + ".")
        if pending_workers:
            note_bits.append("Still waiting on " + ", ".join(pending_workers) + ".")
        note_bits.append("This answer was forced from current checkpoints before the full merge finished.")
        summary["frontAnswer"]["confidenceNote"] = truncate_text(
            " ".join(note_bits),
            320,
        )
        summary["summarizerOpinion"]["uncertainty"] = truncate_text(
            (summary["summarizerOpinion"].get("uncertainty", "") + " Partial merge only; missing workers can still change the answer.")
            .strip(),
            320,
        )
        summary["summarizerOpinion"]["integrationMode"] = truncate_text(
            "Lead answer from current evidence only; pending workers remain advisory until a full merge completes.",
            220,
        )
        control_audit = summary.get("controlAudit") if isinstance(summary.get("controlAudit"), dict) else {}
        held_out = normalize_string_array_preserve_items(control_audit.get("heldOutConcerns", []))
        if pending_workers:
            held_out.append("Pending worker checkpoints: " + ", ".join(pending_workers))
        control_audit["heldOutConcerns"] = held_out[:6]
        control_audit["selfCheck"] = truncate_text(
            (str(control_audit.get("selfCheck", "")).strip() + " This was released as a partial answer, so keep course changes conservative until all workers land.")
            .strip(),
            320,
        )
        summary["controlAudit"] = normalize_control_audit(control_audit, summary)
        summary["sourceWorkers"] = available_workers
        return summary

    def write_commander_files(self, task_id: str, round_number: int, checkpoint: Dict[str, Any]) -> tuple[Path, Path]:
        latest_name = f"{task_id}_commander.json"
        history_name = f"{task_id}_commander_round{round_number:03d}.json"
        artifact_store.write_json_artifact(self.root, "checkpoints", latest_name, checkpoint)
        artifact_store.write_json_artifact(self.root, "checkpoints", history_name, checkpoint)
        return Path(latest_name), Path(history_name)

    def write_commander_review_files(self, task_id: str, round_number: int, checkpoint: Dict[str, Any]) -> tuple[Path, Path]:
        latest_name = f"{task_id}_commander_review.json"
        history_name = f"{task_id}_commander_review_round{round_number:03d}.json"
        artifact_store.write_json_artifact(self.root, "checkpoints", latest_name, checkpoint)
        artifact_store.write_json_artifact(self.root, "checkpoints", history_name, checkpoint)
        return Path(latest_name), Path(history_name)

    def write_worker_checkpoint_files(self, task_id: str, worker_id: str, step_number: int, checkpoint: Dict[str, Any]) -> tuple[Path, Path]:
        latest_name = f"{task_id}_{worker_id}.json"
        history_name = f"{task_id}_{worker_id}_step{step_number:03d}.json"
        artifact_store.write_json_artifact(self.root, "checkpoints", latest_name, checkpoint)
        artifact_store.write_json_artifact(self.root, "checkpoints", history_name, checkpoint)
        return Path(latest_name), Path(history_name)

    def write_summary_files(self, task_id: str, round_number: int, summary: Dict[str, Any], suffix: str = "") -> tuple[Path, Path]:
        normalized_suffix = f"_{suffix}" if suffix else ""
        latest_name = f"{task_id}_summary{normalized_suffix}.json"
        history_name = f"{task_id}_summary{normalized_suffix}_round{round_number:03d}.json"
        artifact_store.write_json_artifact(self.root, "checkpoints", latest_name, summary)
        artifact_store.write_json_artifact(self.root, "checkpoints", history_name, summary)
        return Path(latest_name), Path(history_name)

    def write_output_artifact(self, filename: str, history_filename: str, payload: Dict[str, Any]) -> tuple[Path, Path]:
        artifact_store.write_json_artifact(self.root, "outputs", filename, payload)
        artifact_store.write_json_artifact(self.root, "outputs", history_filename, payload)
        return Path(filename), Path(history_filename)

    def run_commander(self) -> Dict[str, Any]:
        state = self.read_state()
        task = state.get("activeTask")
        if not isinstance(task, dict):
            raise RuntimeErrorWithCode("No active task.", 400)
        open_round = self.get_open_round(state)
        completed_round = self.get_latest_summary_round(state)
        if open_round > completed_round:
            raise RuntimeErrorWithCode(
                f"Commander already drafted round {open_round}. Complete the worker and summary pass for that round before drafting the next one.",
                409,
            )
        round_number = completed_round + 1
        summary_config = commander_config(task)
        runtime = self.get_task_runtime(task, summary_config["model"], "commander", summary_config["provider"])
        constraints = normalize_string_array_preserve_items(task.get("constraints", []))
        prior_summary = state.get("summary") if isinstance(state.get("summary"), dict) else None
        checkpoint: Optional[Dict[str, Any]] = None
        response_id: Optional[str] = None
        response: Optional[Dict[str, Any]] = None
        usage_snapshot: Optional[Dict[str, Any]] = None
        call_meta: Dict[str, Any] = {
            "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
            "effectiveMaxOutputTokens": int(runtime["maxOutputTokens"]),
            "attempts": [int(runtime["maxOutputTokens"])] if int(runtime["maxOutputTokens"]) > 0 else [],
            "recoveredFromIncomplete": False,
        }
        mode_used = "mock"
        auth_assignments = self.provider_auth_assignments(runtime["provider"], "commander", task, round_number=round_number)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(runtime["provider"], auth_assignment)
        if runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(runtime["provider"]):
                try:
                    self.assert_budget_available("commander", task)
                    checkpoint, response_id, response, call_meta = self.new_live_commander(
                        api_key,
                        auth_assignments,
                        task,
                        runtime,
                        round_number,
                        constraints,
                        prior_summary,
                    )
                    auth_meta = self.live_auth_meta(runtime["provider"], call_meta.get("auth"))
                    self.append_auth_failover_step("commander", str(task["taskId"]), runtime["model"], call_meta, "commander")
                    usage_snapshot = self.update_usage_tracking("commander", str(task["taskId"]), runtime["model"], response_id, response)
                    mode_used = "live"
                except RuntimeErrorWithCode as error:
                    if str(error).startswith("Budget limit reached:"):
                        self.append_step(
                            "budget",
                            "Budget stopped the commander before another live call.",
                            {"taskId": task["taskId"], "model": runtime["model"], "error": str(error), "auth": auth_meta},
                        )
                        raise
                    if not self.should_fallback_to_mock(error):
                        self.append_step(
                            "commander",
                            "Live API call failed and was not downgraded to mock.",
                            {
                                "taskId": task["taskId"],
                                "model": runtime["model"],
                                "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
                                "error": str(error),
                                "auth": auth_meta,
                            },
                        )
                        raise RuntimeErrorWithCode(f"Live run failed for commander: {error}", error.status_code)
                    self.append_step(
                        "commander",
                        "Live API call failed; falling back to mock.",
                        {
                            "taskId": task["taskId"],
                            "model": runtime["model"],
                            "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
                            "error": str(error),
                            "auth": auth_meta,
                        },
                    )
            else:
                if self.provider_uses_api_key_pool(runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable("commander", str(task["taskId"]), runtime["model"], "commander")
                self.append_step("commander", "No API key found; falling back to mock.", {"taskId": task["taskId"], "auth": auth_meta})
        if checkpoint is None:
            checkpoint = self.new_mock_commander(task, runtime, round_number, constraints, prior_summary)
        checkpoint = normalize_commander_checkpoint(checkpoint, task, round_number)
        checkpoint["localToolCalls"] = normalize_local_tool_calls(call_meta.get("localToolCalls", []))
        checkpoint["localFileSources"] = normalize_string_array_preserve_items(call_meta.get("localFileSources", []))
        checkpoint["githubToolCalls"] = normalize_local_tool_calls(call_meta.get("githubToolCalls", []))
        checkpoint["githubSources"] = normalize_url_array_values(call_meta.get("githubSources", []))

        def update_state(current: Dict[str, Any]) -> Dict[str, Any]:
            current["commander"] = checkpoint
            return current

        state = self.mutate_state(update_state)
        _, history_cp = self.write_commander_files(str(task["taskId"]), round_number, checkpoint)
        output_artifact = {
            "taskId": str(task["taskId"]),
            "artifactType": "commander_output",
            "target": "commander",
            "label": summary_config["label"],
            "mode": mode_used,
            "model": runtime["model"],
            "round": round_number,
            "capturedAt": utc_now(),
            "responseId": response_id,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "responseMeta": {
                "status": str(response.get("status", "completed")),
                "usageDelta": self.get_response_usage_delta(response, runtime["model"]),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "localToolCalls": normalize_local_tool_calls(call_meta.get("localToolCalls", [])),
                "localFileSources": normalize_string_array_preserve_items(call_meta.get("localFileSources", [])),
                "githubToolCalls": normalize_local_tool_calls(call_meta.get("githubToolCalls", [])),
                "githubSources": normalize_url_array_values(call_meta.get("githubSources", [])),
            } if response else None,
            "authMeta": auth_meta,
            "output": checkpoint,
        }
        _, history_output = self.write_output_artifact(
            f"{task['taskId']}_commander_output.json",
            f"{task['taskId']}_commander_round{round_number:03d}_output.json",
            output_artifact,
        )
        budget_totals = usage_snapshot or normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
        self.append_event(
            "commander_checkpoint",
            {
                "taskId": task["taskId"],
                "round": round_number,
                "mode": mode_used,
                "model": runtime["model"],
            },
        )
        for tool_call in normalize_local_tool_calls(call_meta.get("localToolCalls", [])):
            self.append_step(
                "local_tool",
                f"Commander used {tool_call.get('name') or 'local tool'}.",
                {
                    "taskId": task["taskId"],
                    "target": "commander",
                    "round": round_number,
                    "tool": tool_call,
                    "auth": auth_meta,
                },
            )
        for tool_call in normalize_local_tool_calls(call_meta.get("githubToolCalls", [])):
            self.append_step(
                "github_tool",
                f"Commander used {tool_call.get('name') or 'GitHub tool'}.",
                {
                    "taskId": task["taskId"],
                    "target": "commander",
                    "round": round_number,
                    "tool": tool_call,
                    "auth": auth_meta,
                },
            )
        self.append_step(
            "commander",
            "Commander drafted the lead answer for this round.",
            {
                "taskId": task["taskId"],
                "round": round_number,
                "mode": mode_used,
                "model": runtime["model"],
                "responseId": response_id,
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "localToolCalls": normalize_local_tool_calls(call_meta.get("localToolCalls", [])),
                "localFileSources": normalize_string_array_preserve_items(call_meta.get("localFileSources", [])),
                "githubToolCalls": normalize_local_tool_calls(call_meta.get("githubToolCalls", [])),
                "githubSources": normalize_url_array_values(call_meta.get("githubSources", [])),
                "totalTokens": int(budget_totals.get("totalTokens", 0)),
                "estimatedCostUsd": float(budget_totals.get("estimatedCostUsd", 0.0)),
                "checkpointFile": history_cp.name,
                "outputFile": history_output.name,
                "auth": auth_meta,
            },
        )
        self.append_event(
            "runtime_run",
            {"target": "commander", "backend": "python", "exitCode": 0, "output": "Commander draft written."},
        )
        return {"target": "commander", "output": "Commander draft written.", "exitCode": 0}

    def run_commander_review(self) -> Dict[str, Any]:
        state = self.read_state()
        task = state.get("activeTask")
        if not isinstance(task, dict):
            raise RuntimeErrorWithCode("No active task.", 400)
        commander_checkpoint = state.get("commander") if isinstance(state.get("commander"), dict) else None
        if not isinstance(commander_checkpoint, dict):
            raise RuntimeErrorWithCode("Commander draft is required before commander review.", 409)
        commander_round = int(commander_checkpoint.get("round", 0) or 0)
        if commander_round <= 0:
            raise RuntimeErrorWithCode("Commander draft is required before commander review.", 409)
        existing_review = state.get("commanderReview") if isinstance(state.get("commanderReview"), dict) else None
        if isinstance(existing_review, dict) and int(existing_review.get("round", 0) or 0) == commander_round:
            raise RuntimeErrorWithCode(
                f"Commander review already completed for round {commander_round}. Run the summarizer or start the next round first.",
                409,
            )
        workers = task_workers(task, commander_round)
        worker_state = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        for worker in workers:
            checkpoint = worker_state.get(worker["id"])
            if not isinstance(checkpoint, dict) or int(checkpoint.get("step", 0) or 0) != commander_round:
                raise RuntimeErrorWithCode(
                    f"Worker {worker['id']} is not aligned with commander round {commander_round}.",
                    409,
                )
        review_config = commander_review_config(task)
        runtime = self.get_task_runtime(task, review_config["model"], "commander_review", review_config["provider"])
        line_catalog = self.build_summary_line_catalog(worker_state, workers)
        checkpoint: Optional[Dict[str, Any]] = None
        response_id: Optional[str] = None
        response: Optional[Dict[str, Any]] = None
        usage_snapshot: Optional[Dict[str, Any]] = None
        call_meta: Dict[str, Any] = {
            "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
            "effectiveMaxOutputTokens": int(runtime["maxOutputTokens"]),
            "attempts": [int(runtime["maxOutputTokens"])] if int(runtime["maxOutputTokens"]) > 0 else [],
            "recoveredFromIncomplete": False,
        }
        mode_used = "mock"
        auth_assignments = self.provider_auth_assignments(runtime["provider"], "commander_review", task, round_number=commander_round)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(runtime["provider"], auth_assignment)
        if runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(runtime["provider"]):
                try:
                    self.assert_budget_available("commander_review", task)
                    checkpoint, response_id, response, call_meta = self.new_live_commander_review(
                        api_key,
                        auth_assignments,
                        task,
                        commander_checkpoint,
                        workers,
                        worker_state,
                        runtime,
                        line_catalog,
                    )
                    auth_meta = self.live_auth_meta(runtime["provider"], call_meta.get("auth"))
                    self.append_auth_failover_step("commander_review", str(task["taskId"]), runtime["model"], call_meta, "commander_review")
                    usage_snapshot = self.update_usage_tracking("commander_review", str(task["taskId"]), runtime["model"], response_id, response)
                    mode_used = "live"
                except RuntimeErrorWithCode as error:
                    if str(error).startswith("Budget limit reached:"):
                        self.append_step(
                            "budget",
                            "Budget stopped commander review before another live call.",
                            {"taskId": task["taskId"], "model": runtime["model"], "error": str(error), "auth": auth_meta},
                        )
                        raise
                    if not self.should_fallback_to_mock(error):
                        self.append_step(
                            "commander_review",
                            "Live API call failed and was not downgraded to mock.",
                            {
                                "taskId": task["taskId"],
                                "model": runtime["model"],
                                "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
                                "error": str(error),
                                "auth": auth_meta,
                            },
                        )
                        raise RuntimeErrorWithCode(f"Live run failed for commander review: {error}", error.status_code)
                    self.append_step(
                        "commander_review",
                        "Live API call failed; falling back to mock.",
                        {
                            "taskId": task["taskId"],
                            "model": runtime["model"],
                            "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
                            "error": str(error),
                            "auth": auth_meta,
                        },
                    )
            else:
                if self.provider_uses_api_key_pool(runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable("commander_review", str(task["taskId"]), runtime["model"], "commander_review")
                self.append_step("commander_review", "No API key found; falling back to mock.", {"taskId": task["taskId"], "auth": auth_meta})
        if checkpoint is None:
            checkpoint = self.new_mock_commander_review(task, commander_checkpoint, workers, worker_state)
        checkpoint = normalize_commander_review_checkpoint(
            checkpoint,
            task,
            commander_round,
            commander_checkpoint,
            [worker["id"] for worker in workers],
        )
        dynamic_spinup = self.get_dynamic_spinup_config(task)
        dynamic_lane_decision = checkpoint.get("dynamicLaneDecision") if isinstance(checkpoint.get("dynamicLaneDecision"), dict) else {}
        dynamic_lane_resolution = normalize_dynamic_lane_resolution(None)
        selected_dynamic_worker: Optional[Dict[str, str]] = None
        if dynamic_spinup["enabled"] and bool(dynamic_lane_decision.get("shouldSpawn")):
            selected_dynamic_worker, dynamic_lane_resolution = self.build_dynamic_worker(task, dynamic_lane_decision, commander_round + 1)
        checkpoint["dynamicLaneResolution"] = dynamic_lane_resolution
        spawned_worker: Optional[Dict[str, str]] = None

        def update_state(current: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal spawned_worker
            current["commanderReview"] = checkpoint
            if selected_dynamic_worker is not None and isinstance(current.get("activeTask"), dict):
                current_task = current["activeTask"]
                existing_workers = task_workers(current_task)
                if selected_dynamic_worker["id"] not in {worker["id"] for worker in existing_workers}:
                    current_task["workers"] = existing_workers + [selected_dynamic_worker]
                    workers_state = current.get("workers") if isinstance(current.get("workers"), dict) else {}
                    workers_state[selected_dynamic_worker["id"]] = None
                    current["workers"] = workers_state
                    current["activeTask"] = current_task
                    spawned_worker = selected_dynamic_worker
            return current

        state = self.mutate_state(update_state)
        if spawned_worker is not None and isinstance(state.get("activeTask"), dict):
            self.write_task_snapshot_unlocked(state["activeTask"])
        _, history_cp = self.write_commander_review_files(str(task["taskId"]), commander_round, checkpoint)
        output_artifact = {
            "taskId": str(task["taskId"]),
            "artifactType": "commander_review_output",
            "target": "commander_review",
            "label": review_config["label"],
            "mode": mode_used,
            "model": runtime["model"],
            "round": commander_round,
            "capturedAt": utc_now(),
            "responseId": response_id,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "responseMeta": {
                "status": str(response.get("status", "completed")),
                "usageDelta": self.get_response_usage_delta(response, runtime["model"]),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "dynamicLaneDecision": dynamic_lane_decision,
                "dynamicLaneResolution": dynamic_lane_resolution,
                "spawnedWorkerId": spawned_worker["id"] if spawned_worker else None,
            } if response else None,
            "authMeta": auth_meta,
            "output": checkpoint,
        }
        _, history_output = self.write_output_artifact(
            f"{task['taskId']}_commander_review_output.json",
            f"{task['taskId']}_commander_review_round{commander_round:03d}_output.json",
            output_artifact,
        )
        budget_totals = usage_snapshot or normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
        self.append_event(
            "commander_review_checkpoint",
            {
                "taskId": task["taskId"],
                "round": commander_round,
                "mode": mode_used,
                "model": runtime["model"],
                "dynamicLaneDecision": dynamic_lane_decision,
                "dynamicLaneResolution": dynamic_lane_resolution,
                "spawnedWorkerId": spawned_worker["id"] if spawned_worker else None,
            },
        )
        if spawned_worker is not None:
            self.append_step(
                "dynamic_lane",
                f"Spawned {spawned_worker['label']} for the next round.",
                {
                    "taskId": task["taskId"],
                    "round": commander_round,
                    "workerId": spawned_worker["id"],
                    "workerType": spawned_worker.get("type"),
                    "temperature": spawned_worker.get("temperature"),
                    "focus": spawned_worker.get("focus"),
                    "harness": spawned_worker.get("harness"),
                    "reason": str(dynamic_lane_decision.get("reason", "")).strip(),
                    "requiredPressure": str(dynamic_lane_decision.get("requiredPressure", "")).strip(),
                    "instruction": str(dynamic_lane_decision.get("instruction", "")).strip(),
                    "suggestedLaneTypes": normalize_lane_type_list(dynamic_lane_decision.get("suggestedLaneTypes", []), False, 2),
                    "resolution": dynamic_lane_resolution,
                },
            )
        elif dynamic_spinup["enabled"] and bool(dynamic_lane_decision.get("shouldSpawn")):
            self.append_step(
                "dynamic_lane",
                "Commander review requested another lane, but the request was rejected.",
                {
                    "taskId": task["taskId"],
                    "round": commander_round,
                    "reason": str(dynamic_lane_decision.get("reason", "")).strip(),
                    "requiredPressure": str(dynamic_lane_decision.get("requiredPressure", "")).strip(),
                    "instruction": str(dynamic_lane_decision.get("instruction", "")).strip(),
                    "suggestedLaneTypes": normalize_lane_type_list(dynamic_lane_decision.get("suggestedLaneTypes", []), False, 2),
                    "resolution": dynamic_lane_resolution,
                },
            )
        self.append_step(
            "commander_review",
            "Commander reevaluated the lead answer after worker pressure.",
            {
                "taskId": task["taskId"],
                "round": commander_round,
                "mode": mode_used,
                "model": runtime["model"],
                "responseId": response_id,
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "courseDecision": str((checkpoint.get("controlAudit") or {}).get("courseDecision", "")),
                "dynamicLaneDecision": checkpoint.get("dynamicLaneDecision"),
                "dynamicLaneResolution": checkpoint.get("dynamicLaneResolution"),
                "spawnedWorkerId": spawned_worker["id"] if spawned_worker else None,
                "totalTokens": int(budget_totals.get("totalTokens", 0)),
                "estimatedCostUsd": float(budget_totals.get("estimatedCostUsd", 0.0)),
                "checkpointFile": history_cp.name,
                "outputFile": history_output.name,
                "auth": auth_meta,
            },
        )
        self.append_event(
            "runtime_run",
            {"target": "commander_review", "backend": "python", "exitCode": 0, "output": "Commander review written."},
        )
        return {"target": "commander_review", "output": "Commander review written.", "exitCode": 0}

    def run_worker(self, worker_id: str) -> Dict[str, Any]:
        worker_id = worker_id.strip().upper()
        if not re.match(r"^[A-Z]$", worker_id):
            raise RuntimeErrorWithCode("A single uppercase worker id is required.", 400)
        state = self.read_state()
        task = state.get("activeTask")
        if not isinstance(task, dict):
            raise RuntimeErrorWithCode("No active task.", 400)
        worker = find_task_worker(task, worker_id)
        if worker is None:
            raise RuntimeErrorWithCode(f"Unknown worker id: {worker_id}", 400)
        runtime = self.get_task_runtime(task, worker["model"], worker_id)
        research_config = self.get_research_config(task)
        constraints = normalize_string_array_preserve_items(task.get("constraints", []))
        prior_summary = state.get("summary") if isinstance(state.get("summary"), dict) else None
        commander_checkpoint = state.get("commander") if isinstance(state.get("commander"), dict) else None
        prior_memory_version = int(state.get("memoryVersion", 0) or 0)
        commander_round = int((commander_checkpoint or {}).get("round", 0) or 0)
        step_number = commander_round if commander_round > 0 else 1
        checkpoint_state = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        existing = checkpoint_state.get(worker_id)
        if isinstance(existing, dict):
            step_number = int(existing.get("step", 0) or 0) + 1
        if commander_round <= 0:
            raise RuntimeErrorWithCode("Commander draft is required before workers can run.", 409)
        if commander_round != step_number:
            raise RuntimeErrorWithCode(
                f"Commander draft is not aligned for {worker['label']}. Expected commander round {step_number}, found round {commander_round}.",
                409,
            )
        if commander_round < worker_active_from_round(worker):
            raise RuntimeErrorWithCode(
                f"{worker['label']} activates in round {worker_active_from_round(worker)} and is not ready for commander round {commander_round}.",
                409,
            )
        peer_messages = self.get_peer_steer_messages(state, task, worker_id, commander_round)
        checkpoint: Optional[Dict[str, Any]] = None
        response_id: Optional[str] = None
        response: Optional[Dict[str, Any]] = None
        usage_snapshot: Optional[Dict[str, Any]] = None
        call_meta: Dict[str, Any] = {
            "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
            "effectiveMaxOutputTokens": int(runtime["maxOutputTokens"]),
            "attempts": [int(runtime["maxOutputTokens"])] if int(runtime["maxOutputTokens"]) > 0 else [],
            "recoveredFromIncomplete": False,
        }
        mode_used = "mock"
        auth_assignments = self.provider_auth_assignments(runtime["provider"], worker_id, task, round_number=commander_round)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(runtime["provider"], auth_assignment)
        if runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(runtime["provider"]):
                try:
                    self.assert_budget_available(worker_id, task)
                    checkpoint, response_id, response, call_meta = self.new_live_checkpoint(
                        api_key,
                        auth_assignments,
                        task,
                        worker,
                        runtime,
                        research_config,
                        step_number,
                        constraints,
                        commander_checkpoint,
                        prior_summary,
                        prior_memory_version,
                        peer_messages,
                    )
                    auth_meta = self.live_auth_meta(runtime["provider"], call_meta.get("auth"))
                    self.append_auth_failover_step(f"worker_{worker_id}", str(task["taskId"]), runtime["model"], call_meta, worker_id)
                    usage_snapshot = self.update_usage_tracking(worker_id, str(task["taskId"]), runtime["model"], response_id, response)
                    mode_used = "live"
                except RuntimeErrorWithCode as error:
                    if str(error).startswith("Budget limit reached:"):
                        self.append_step(
                            "budget",
                            f"Budget stopped {worker['label']} before another live call.",
                            {"taskId": task["taskId"], "workerId": worker_id, "model": runtime["model"], "error": str(error), "auth": auth_meta},
                        )
                        raise
                    if not self.should_fallback_to_mock(error):
                        self.append_step(
                            f"worker_{worker_id}",
                            "Live API call failed and was not downgraded to mock.",
                            {
                                "taskId": task["taskId"],
                                "workerId": worker_id,
                                "step": step_number,
                                "model": runtime["model"],
                                "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
                                "error": str(error),
                                "auth": auth_meta,
                            },
                        )
                        raise RuntimeErrorWithCode(f"Live run failed for {worker['label']}: {error}", error.status_code)
                    self.append_step(
                        f"worker_{worker_id}",
                        "Live API call failed; falling back to mock.",
                        {
                            "taskId": task["taskId"],
                            "workerId": worker_id,
                            "step": step_number,
                            "model": runtime["model"],
                            "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
                            "error": str(error),
                            "auth": auth_meta,
                        },
                    )
            else:
                if self.provider_uses_api_key_pool(runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable(f"worker_{worker_id}", str(task["taskId"]), runtime["model"], worker_id)
                self.append_step(
                    f"worker_{worker_id}",
                    "No API key found; falling back to mock.",
                    {"taskId": task["taskId"], "workerId": worker_id, "step": step_number, "auth": auth_meta},
                )
        if checkpoint is None:
            checkpoint = self.new_mock_checkpoint(task, worker, runtime, research_config, step_number, constraints, prior_summary, prior_memory_version, peer_messages)
        checkpoint = self.normalize_checkpoint(task, worker_id, worker, runtime, checkpoint, step_number)
        def update_state(current: Dict[str, Any]) -> Dict[str, Any]:
            workers_state = current.get("workers") if isinstance(current.get("workers"), dict) else {}
            workers_state[worker_id] = checkpoint
            current["workers"] = workers_state
            return current
        state = self.mutate_state(update_state)
        latest_cp, history_cp = self.write_worker_checkpoint_files(str(task["taskId"]), worker_id, step_number, checkpoint)
        output_artifact = {
            "taskId": str(task["taskId"]),
            "artifactType": "worker_output",
            "target": worker_id,
            "label": worker["label"],
            "mode": mode_used,
            "model": runtime["model"],
            "step": step_number,
            "capturedAt": utc_now(),
            "responseId": response_id,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "responseMeta": {
                "status": str(response.get("status", "completed")),
                "usageDelta": self.get_response_usage_delta(response, runtime["model"]),
                "webSearchQueries": normalize_string_array_preserve_items(self.get_response_web_search_queries(response)),
                "webSearchSources": normalize_url_array_values(self.get_response_web_search_sources(response)),
                "urlCitations": normalize_url_array_values(self.get_response_url_citations(response)),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "localToolCalls": normalize_local_tool_calls(call_meta.get("localToolCalls", [])),
                "localFileSources": normalize_string_array_preserve_items(call_meta.get("localFileSources", [])),
                "githubToolCalls": normalize_local_tool_calls(call_meta.get("githubToolCalls", [])),
                "githubSources": normalize_url_array_values(call_meta.get("githubSources", [])),
            }
            if response
            else None,
            "authMeta": auth_meta,
            "output": checkpoint,
        }
        _, history_output = self.write_output_artifact(
            f"{task['taskId']}_{worker_id}_output.json",
            f"{task['taskId']}_{worker_id}_step{step_number:03d}_output.json",
            output_artifact,
        )
        self.append_event(
            "worker_checkpoint",
            {
                "worker": worker_id,
                "label": worker["label"],
                "taskId": task["taskId"],
                "role": worker["role"],
                "model": runtime["model"],
                "mode": mode_used,
            },
        )
        for tool_call in normalize_local_tool_calls(call_meta.get("localToolCalls", [])):
            self.append_step(
                "local_tool",
                f"{worker['label']} used {tool_call.get('name') or 'local tool'}.",
                {
                    "taskId": task["taskId"],
                    "target": worker_id,
                    "step": step_number,
                    "tool": tool_call,
                    "auth": auth_meta,
                },
            )
        for tool_call in normalize_local_tool_calls(call_meta.get("githubToolCalls", [])):
            self.append_step(
                "github_tool",
                f"{worker['label']} used {tool_call.get('name') or 'GitHub tool'}.",
                {
                    "taskId": task["taskId"],
                    "target": worker_id,
                    "step": step_number,
                    "tool": tool_call,
                    "auth": auth_meta,
                },
            )
        budget_totals = usage_snapshot or normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
        self.append_step(
            f"worker_{worker_id}",
            f"{worker['label']} produced a checkpoint.",
            {
                "taskId": task["taskId"],
                "workerId": worker_id,
                "step": step_number,
                "commanderRound": commander_round,
                "memoryVersionSeen": prior_memory_version,
                "mode": mode_used,
                "model": runtime["model"],
                "researchMode": checkpoint.get("researchMode"),
                "researchSourceCount": len(checkpoint.get("researchSources", [])),
                "responseId": response_id,
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "localToolCalls": normalize_local_tool_calls(call_meta.get("localToolCalls", [])),
                "localFileSources": normalize_string_array_preserve_items(call_meta.get("localFileSources", [])),
                "githubToolCalls": normalize_local_tool_calls(call_meta.get("githubToolCalls", [])),
                "githubSources": normalize_url_array_values(call_meta.get("githubSources", [])),
                "totalTokens": int(budget_totals.get("totalTokens", 0)),
                "estimatedCostUsd": float(budget_totals.get("estimatedCostUsd", 0.0)),
                "checkpointFile": history_cp.name,
                "outputFile": history_output.name,
                "auth": auth_meta,
            },
        )
        self.append_event(
            "runtime_run",
            {"target": worker_id, "backend": "python", "exitCode": 0, "output": f"{worker['label']} checkpoint written."},
        )
        return {"target": worker_id, "output": f"{worker['label']} checkpoint written.", "exitCode": 0}

    def run_summarizer(self) -> Dict[str, Any]:
        state = self.read_state()
        task = state.get("activeTask")
        if not isinstance(task, dict):
            raise RuntimeErrorWithCode("No active task.", 400)
        commander_checkpoint = state.get("commander") if isinstance(state.get("commander"), dict) else None
        if not isinstance(commander_checkpoint, dict):
            raise RuntimeErrorWithCode("Commander draft is required before summarizing.", 409)
        commander_review_checkpoint = state.get("commanderReview") if isinstance(state.get("commanderReview"), dict) else None
        if not isinstance(commander_review_checkpoint, dict):
            raise RuntimeErrorWithCode("Commander review is required before summarizing.", 409)
        worker_state: Dict[str, Any] = {}
        state_workers = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        commander_round = int(commander_checkpoint.get("round", 0) or 0)
        commander_review_round = int(commander_review_checkpoint.get("round", 0) or 0)
        workers = task_workers(task, commander_round)
        if commander_review_round != commander_round:
            raise RuntimeErrorWithCode(
                f"Commander review is not aligned with commander round {commander_round}.",
                409,
            )
        for worker in workers:
            checkpoint = state_workers.get(worker["id"])
            if not isinstance(checkpoint, dict):
                raise RuntimeErrorWithCode("All configured worker checkpoints are required before summarizing.", 409)
            if int(checkpoint.get("step", 0) or 0) != commander_round:
                raise RuntimeErrorWithCode(
                    f"Worker {worker['id']} is not aligned with commander round {commander_round}.",
                    409,
                )
            worker_state[worker["id"]] = checkpoint
        summary_config = summarizer_config(task)
        runtime = self.get_task_runtime(task, summary_config["model"], "summarizer", summary_config["provider"])
        vetting_config = self.get_vetting_config(task)
        line_catalog = self.build_summary_line_catalog(worker_state, workers)
        summary: Optional[Dict[str, Any]] = None
        response_id: Optional[str] = None
        response: Optional[Dict[str, Any]] = None
        usage_snapshot: Optional[Dict[str, Any]] = None
        call_meta: Dict[str, Any] = {
            "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
            "effectiveMaxOutputTokens": int(runtime["maxOutputTokens"]),
            "attempts": [int(runtime["maxOutputTokens"])] if int(runtime["maxOutputTokens"]) > 0 else [],
            "recoveredFromIncomplete": False,
        }
        mode_used = "mock"
        auth_assignments = self.provider_auth_assignments(runtime["provider"], "summarizer", task, round_number=commander_round)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(runtime["provider"], auth_assignment)
        if runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(runtime["provider"]):
                try:
                    self.assert_budget_available("summarizer", task)
                    summary, response_id, response, call_meta = self.new_live_summary(
                        api_key,
                        auth_assignments,
                        task,
                        commander_checkpoint,
                        commander_review_checkpoint,
                        workers,
                        worker_state,
                        runtime,
                        vetting_config,
                        line_catalog,
                    )
                    auth_meta = self.live_auth_meta(runtime["provider"], call_meta.get("auth"))
                    self.append_auth_failover_step("summarizer", str(task["taskId"]), runtime["model"], call_meta, "summarizer")
                    usage_snapshot = self.update_usage_tracking("summarizer", str(task["taskId"]), runtime["model"], response_id, response)
                    mode_used = "live"
                except RuntimeErrorWithCode as error:
                    if str(error).startswith("Budget limit reached:"):
                        self.append_step(
                            "budget",
                            "Budget stopped the summarizer before another live call.",
                            {"taskId": task["taskId"], "model": runtime["model"], "error": str(error), "auth": auth_meta},
                        )
                        raise
                    if not self.should_fallback_to_mock(error):
                        self.append_step(
                            "summarizer",
                            "Live API call failed and was not downgraded to mock.",
                            {
                                "taskId": task["taskId"],
                                "model": runtime["model"],
                                "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
                                "error": str(error),
                                "auth": auth_meta,
                            },
                        )
                        raise RuntimeErrorWithCode(f"Live run failed for summarizer: {error}", error.status_code)
                    self.append_step(
                        "summarizer",
                        "Live API call failed; falling back to mock.",
                        {
                            "taskId": task["taskId"],
                            "model": runtime["model"],
                            "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
                            "error": str(error),
                            "auth": auth_meta,
                        },
                    )
            else:
                if self.provider_uses_api_key_pool(runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable("summarizer", str(task["taskId"]), runtime["model"], "summarizer")
                self.append_step("summarizer", "No API key found; falling back to mock.", {"taskId": task["taskId"], "auth": auth_meta})
        if summary is None:
            summary = self.new_mock_summary(task, commander_checkpoint, commander_review_checkpoint, workers, worker_state, vetting_config, line_catalog)
        summary = self.normalize_summary(summary, line_catalog)
        summary["round"] = commander_round
        dynamic_lane_decision = summary.get("dynamicLaneDecision") if isinstance(summary.get("dynamicLaneDecision"), dict) else {}

        def update_state(current: Dict[str, Any]) -> Dict[str, Any]:
            current["summary"] = summary
            current["memoryVersion"] = int(current.get("memoryVersion", 0) or 0) + 1
            return current
        state = self.mutate_state(update_state)
        current_memory_version = int(state.get("memoryVersion", 0) or 0)
        latest_summary, history_summary = self.write_summary_files(str(task["taskId"]), int(summary.get("round", 0) or 0), summary)
        output_artifact = {
            "taskId": str(task["taskId"]),
            "artifactType": "summary_output",
            "target": "summarizer",
            "label": summary_config["label"],
            "mode": mode_used,
            "model": runtime["model"],
            "round": int(summary.get("round", 0) or 0),
            "capturedAt": utc_now(),
            "responseId": response_id,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "responseMeta": {
                "status": str(response.get("status", "completed")),
                "usageDelta": self.get_response_usage_delta(response, runtime["model"]),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
            } if response else None,
            "authMeta": auth_meta,
            "output": summary,
        }
        _, history_output = self.write_output_artifact(
            f"{task['taskId']}_summary_output.json",
            f"{task['taskId']}_summary_round{int(summary.get('round', 0) or 0):03d}_output.json",
            output_artifact,
        )
        self.append_event(
            "summary_written",
            {
                "taskId": task["taskId"],
                "memoryVersion": current_memory_version,
                "mode": mode_used,
                "model": runtime["model"],
                "sourceWorkers": [worker["id"] for worker in workers],
                "dynamicLaneDecision": dynamic_lane_decision,
                "dynamicLaneResolution": summary.get("dynamicLaneResolution"),
            },
        )
        budget_totals = usage_snapshot or normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
        self.append_step(
            "summarizer",
            "Summarizer merged worker checkpoints.",
            {
                "taskId": task["taskId"],
                "round": int(summary.get("round", 0) or 0),
                "memoryVersion": current_memory_version,
                "mode": mode_used,
                "model": runtime["model"],
                "responseId": response_id,
                "workerCount": len(workers),
                "vettingEnabled": bool(vetting_config["enabled"]),
                "dynamicLaneDecision": dynamic_lane_decision,
                "dynamicLaneResolution": summary.get("dynamicLaneResolution"),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "totalTokens": int(budget_totals.get("totalTokens", 0)),
                "estimatedCostUsd": float(budget_totals.get("estimatedCostUsd", 0.0)),
                "checkpointFile": history_summary.name,
                "outputFile": history_output.name,
                "auth": auth_meta,
            },
        )
        self.append_event(
            "runtime_run",
            {"target": "summarizer", "backend": "python", "exitCode": 0, "output": "Summary written."},
        )
        return {"target": "summarizer", "output": "Summary written.", "exitCode": 0}

    def run_answer_now(self) -> Dict[str, Any]:
        state = self.read_state()
        task = state.get("activeTask")
        if not isinstance(task, dict):
            raise RuntimeErrorWithCode("No active task.", 400)
        commander_checkpoint = state.get("commander") if isinstance(state.get("commander"), dict) else None
        commander_review_checkpoint = state.get("commanderReview") if isinstance(state.get("commanderReview"), dict) else None
        if not isinstance(commander_checkpoint, dict):
            raise RuntimeErrorWithCode("Commander draft is required before forcing an answer.", 409)
        state_workers = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        commander_round = int(commander_checkpoint.get("round", 0) or 0)
        workers = task_workers(task, commander_round)
        worker_state: Dict[str, Any] = {}
        pending_workers: List[str] = []
        for worker in workers:
            checkpoint = state_workers.get(worker["id"])
            if isinstance(checkpoint, dict) and int(checkpoint.get("step", 0) or 0) == commander_round:
                worker_state[worker["id"]] = checkpoint
            else:
                pending_workers.append(worker["id"])
        summary_config = summarizer_config(task)
        runtime = self.get_task_runtime(task, summary_config["model"], "summarizer", summary_config["provider"])
        requested_partial_tokens = int(runtime.get("maxOutputTokens", 0) or 0)
        runtime["maxOutputTokens"] = min(max(requested_partial_tokens, 2200), 3200) if requested_partial_tokens > 0 else 2200
        if runtime["reasoningEffort"] in {"high", "xhigh"}:
            runtime["reasoningEffort"] = "medium"
        elif runtime["reasoningEffort"] == "none":
            runtime["reasoningEffort"] = "low"
        vetting_config = self.get_vetting_config(task)
        line_catalog = self.build_summary_line_catalog(worker_state, workers)
        summary: Optional[Dict[str, Any]] = None
        response_id: Optional[str] = None
        response: Optional[Dict[str, Any]] = None
        usage_snapshot: Optional[Dict[str, Any]] = None
        call_meta: Dict[str, Any] = {
            "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
            "effectiveMaxOutputTokens": int(runtime["maxOutputTokens"]),
            "attempts": [int(runtime["maxOutputTokens"])] if int(runtime["maxOutputTokens"]) > 0 else [],
            "recoveredFromIncomplete": False,
        }
        mode_used = "mock"
        auth_assignments = self.provider_auth_assignments(runtime["provider"], "summarizer", task, round_number=commander_round)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(runtime["provider"], auth_assignment)
        if runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(runtime["provider"]):
                try:
                    self.assert_budget_available("summarizer", task)
                    summary, response_id, response, call_meta = self.new_live_summary(
                        api_key,
                        auth_assignments,
                        task,
                        commander_checkpoint,
                        commander_review_checkpoint if isinstance(commander_review_checkpoint, dict) and int(commander_review_checkpoint.get("round", 0) or 0) == commander_round else None,
                        workers,
                        worker_state,
                        runtime,
                        vetting_config,
                        line_catalog,
                        partial_mode=True,
                        pending_workers=pending_workers,
                    )
                    auth_meta = self.live_auth_meta(runtime["provider"], call_meta.get("auth"))
                    self.append_auth_failover_step("summarizer", str(task["taskId"]), runtime["model"], call_meta, "answer_now")
                    usage_snapshot = self.update_usage_tracking("summarizer", str(task["taskId"]), runtime["model"], response_id, response)
                    mode_used = "live"
                except RuntimeErrorWithCode as error:
                    if str(error).startswith("Budget limit reached:"):
                        self.append_step(
                            "budget",
                            "Budget stopped Answer Now before another live call.",
                            {"taskId": task["taskId"], "model": runtime["model"], "error": str(error), "auth": auth_meta},
                        )
                        raise
                    if not self.should_fallback_to_mock(error):
                        raise RuntimeErrorWithCode(f"Live run failed for answer_now: {error}", error.status_code)
                    self.append_step(
                        "summarizer",
                        "Live Answer Now call failed; falling back to mock.",
                        {
                            "taskId": task["taskId"],
                            "model": runtime["model"],
                            "reasoningEffort": runtime["reasoningEffort"],
                            "requestedMaxOutputTokens": int(runtime["maxOutputTokens"]),
                            "error": str(error),
                            "auth": auth_meta,
                        },
                    )
            else:
                if self.provider_uses_api_key_pool(runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable("summarizer", str(task["taskId"]), runtime["model"], "answer_now")
                self.append_step("summarizer", "No API key found for Answer Now; falling back to mock.", {"taskId": task["taskId"], "auth": auth_meta})
        if summary is None:
            summary = self.new_mock_summary(
                task,
                commander_checkpoint,
                commander_review_checkpoint if isinstance(commander_review_checkpoint, dict) and int(commander_review_checkpoint.get("round", 0) or 0) == commander_round else None,
                workers,
                worker_state,
                vetting_config,
                line_catalog,
            )
        summary = self.normalize_summary(summary, line_catalog)
        summary["round"] = commander_round
        summary = self.annotate_partial_summary(summary, list(worker_state.keys()), pending_workers)
        def update_state(current: Dict[str, Any]) -> Dict[str, Any]:
            current["summary"] = summary
            current["memoryVersion"] = int(current.get("memoryVersion", 0) or 0) + 1
            return current
        state = self.mutate_state(update_state)
        current_memory_version = int(state.get("memoryVersion", 0) or 0)
        _, history_summary = self.write_summary_files(str(task["taskId"]), int(summary.get("round", 0) or 0), summary, "partial")
        output_artifact = {
            "taskId": str(task["taskId"]),
            "artifactType": "summary_partial_output",
            "target": "answer_now",
            "label": "Answer Now",
            "mode": mode_used,
            "model": runtime["model"],
            "round": int(summary.get("round", 0) or 0),
            "capturedAt": utc_now(),
            "responseId": response_id,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "responseMeta": {
                "status": str(response.get("status", "completed")),
                "usageDelta": self.get_response_usage_delta(response, runtime["model"]),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "partialSummary": True,
                "pendingWorkers": pending_workers,
            } if response else None,
            "authMeta": auth_meta,
            "output": summary,
        }
        _, history_output = self.write_output_artifact(
            f"{task['taskId']}_summary_partial_output.json",
            f"{task['taskId']}_summary_partial_round{int(summary.get('round', 0) or 0):03d}_output.json",
            output_artifact,
        )
        budget_totals = usage_snapshot or normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
        self.append_step(
            "summarizer",
            "Answer Now produced a partial summary from current checkpoints.",
            {
                "taskId": task["taskId"],
                "round": int(summary.get("round", 0) or 0),
                "memoryVersion": current_memory_version,
                "mode": mode_used,
                "model": runtime["model"],
                "reasoningEffort": runtime["reasoningEffort"],
                "responseId": response_id,
                "availableWorkers": list(worker_state.keys()),
                "pendingWorkers": pending_workers,
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "totalTokens": int(budget_totals.get("totalTokens", 0)),
                "estimatedCostUsd": float(budget_totals.get("estimatedCostUsd", 0.0)),
                "checkpointFile": history_summary.name,
                "outputFile": history_output.name,
                "auth": auth_meta,
            },
        )
        self.append_event(
            "runtime_run",
            {"target": "answer_now", "backend": "python", "exitCode": 0, "output": "Partial summary written."},
        )
        return {"target": "answer_now", "output": "Partial summary written.", "exitCode": 0}

    def run_target(self, target: str, task_id: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        current_state = self.read_state()
        task = current_state.get("activeTask")
        if not isinstance(task, dict):
            raise RuntimeErrorWithCode("No active task.", 400)
        if task_id and str(task.get("taskId", "")) != str(task_id):
            raise RuntimeErrorWithCode("Requested task does not match the active task.", 409)
        if target == "commander":
            return self.run_commander()
        if target == "commander_review":
            return self.run_commander_review()
        if target == "summarizer":
            return self.run_summarizer()
        if target == "answer_now" or (isinstance(options, dict) and options.get("partialSummary") and target == "summarizer"):
            return self.run_answer_now()
        return self.run_worker(target)
