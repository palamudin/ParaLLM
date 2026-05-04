from __future__ import annotations

import ast
import base64
import hashlib
import json
import math
import os
import re
import shutil
import socket
import time
import urllib.error
import urllib.request
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlsplit, urlunsplit

from backend.app import artifacts as artifact_store
from backend.app import knowledgebase
from backend.app import metadata as metadata_store
from backend.app import model_capacities
from backend.app import provider_responses
from backend.app import storage
from backend.app.config import deployment_topology
from backend.app.secrets import (
    auth_key_file_path,
    auth_backend_mode_label,
    auth_key_provider_ids,
    auth_key_provider_label,
    env_secret_status,
    external_secret_status,
    normalize_auth_key_provider,
    preferred_safe_secret_backend,
    read_local_auth_keys,
    resolve_provider_secret_backend,
)


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

ANTHROPIC_MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "claude-opus-4-7": {"label": "Claude Opus 4.7"},
    "claude-sonnet-4-6": {"label": "Claude Sonnet 4.6"},
    "claude-opus-4-6": {"label": "Claude Opus 4.6"},
    "claude-opus-4-5-20251101": {"label": "Claude Opus 4.5"},
    "claude-haiku-4-5-20251001": {"label": "Claude Haiku 4.5"},
    "claude-sonnet-4-5-20250929": {"label": "Claude Sonnet 4.5"},
    "claude-opus-4-1-20250805": {"label": "Claude Opus 4.1"},
}

XAI_MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "grok-4.20-reasoning": {"label": "Grok 4.20 Reasoning"},
    "grok-4-1-fast-reasoning": {"label": "Grok 4.1 Fast Reasoning"},
    "grok-4.20-multi-agent": {"label": "Grok 4.20 Multi-Agent"},
    "grok-4.20": {"label": "Grok 4.20"},
}

DEEPSEEK_MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "deepseek-v4-pro": {"label": "DeepSeek V4 Pro"},
    "deepseek-v4-flash": {"label": "DeepSeek V4 Flash"},
    "deepseek-chat": {"label": "DeepSeek Chat (Legacy)"},
    "deepseek-reasoner": {"label": "DeepSeek Reasoner (Legacy)"},
}

PROVIDER_CATALOG: Dict[str, Dict[str, str]] = {
    "openai": {"label": "OpenAI", "status": "primary"},
    "deepseek": {"label": "DeepSeek", "status": "primary"},
    "anthropic": {"label": "Anthropic", "status": "primary"},
    "xai": {"label": "xAI", "status": "primary"},
    "minimax": {"label": "MiniMax", "status": "deferred"},
    "ollama": {"label": "Ollama", "status": "deferred_local"},
}

PROVIDER_CAPABILITY_CATALOG: Dict[str, Dict[str, Any]] = {
    "openai": {
        "toolLoop": True,
        "webSearch": True,
        "localFiles": True,
        "githubTools": True,
        "costTracking": True,
        "reasoningSummary": True,
        "notes": [
            "Full live research and audited function-tool path.",
            "Estimated token and spend tracking are available.",
        ],
    },
    "deepseek": {
        "toolLoop": True,
        "webSearch": False,
        "localFiles": True,
        "githubTools": True,
        "costTracking": False,
        "reasoningSummary": True,
        "notes": [
            "OpenAI-compatible chat-completions path is the default for DeepSeek in this runtime.",
            "Anthropic-compatible transport remains available as a fallback when explicitly selected.",
            "Client tool loops are supported, but built-in live web search is not wired here yet.",
        ],
    },
    "anthropic": {
        "toolLoop": True,
        "webSearch": True,
        "localFiles": True,
        "githubTools": True,
        "costTracking": False,
        "reasoningSummary": True,
        "notes": [
            "Native Messages API path with tool_use and tool_result turns.",
            "Server-side web search and client tool loops are supported in this runtime.",
        ],
    },
    "xai": {
        "toolLoop": True,
        "webSearch": True,
        "localFiles": True,
        "githubTools": True,
        "costTracking": False,
        "reasoningSummary": True,
        "notes": [
            "OpenAI-compatible Responses path backed by xAI's Grok models.",
            "Built-in web search plus local function tools are supported in this runtime.",
        ],
    },
    "minimax": {
        "toolLoop": True,
        "webSearch": False,
        "localFiles": True,
        "githubTools": True,
        "costTracking": False,
        "reasoningSummary": True,
        "notes": [
            "MiniMax is intentionally deferred from the primary hosted provider set until its review path is boring and repeatable.",
            "OpenAI-compatible chat-completions is the active transport, with Anthropic-compatible fallback available only for targeted debugging.",
            "Client tool loops are supported, but built-in live web search is not wired here yet.",
        ],
    },
    "ollama": {
        "toolLoop": True,
        "webSearch": False,
        "localFiles": True,
        "githubTools": True,
        "costTracking": False,
        "reasoningSummary": True,
        "notes": [
            "Native local structured generation path with client-side function tools.",
            "Live web search is still disabled for Ollama in this runtime.",
        ],
    },
}

OLLAMA_MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "qwen3": {"label": "Qwen3"},
    "qwen3-coder": {"label": "Qwen3 Coder"},
    "gemma3": {"label": "Gemma 3"},
    "llama3.2": {"label": "Llama 3.2"},
}

MINIMAX_MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "MiniMax-M2.7": {"label": "MiniMax M2.7"},
    "MiniMax-M2.7-highspeed": {"label": "MiniMax M2.7 Highspeed"},
    "MiniMax-M2.5": {"label": "MiniMax M2.5"},
    "MiniMax-M2.5-highspeed": {"label": "MiniMax M2.5 Highspeed"},
    "MiniMax-M2.1": {"label": "MiniMax M2.1"},
    "MiniMax-M2.1-highspeed": {"label": "MiniMax M2.1 Highspeed"},
    "MiniMax-M2": {"label": "MiniMax M2"},
}

PROVIDER_MODEL_CATALOG: Dict[str, Dict[str, Dict[str, Any]]] = {
    "openai": MODEL_CATALOG,
    "deepseek": DEEPSEEK_MODEL_CATALOG,
    "anthropic": ANTHROPIC_MODEL_CATALOG,
    "xai": XAI_MODEL_CATALOG,
    "minimax": MINIMAX_MODEL_CATALOG,
    "ollama": OLLAMA_MODEL_CATALOG,
}

PROVIDER_DEFAULT_MODELS: Dict[str, str] = {
    "openai": "gpt-5-mini",
    "deepseek": "deepseek-v4-flash",
    "anthropic": "claude-sonnet-4-20250514",
    "xai": "grok-4.20-reasoning",
    "minimax": "MiniMax-M2.7",
    "ollama": "qwen3",
}

PROVIDER_DEFAULT_JUDGE_MODELS: Dict[str, str] = {
    "openai": "gpt-5.4",
    "deepseek": "deepseek-v4-pro",
    "anthropic": "claude-opus-4-7",
    "xai": "grok-4.20-reasoning",
    "minimax": "MiniMax-M2.7",
    "ollama": "qwen3",
}

WORKER_TEMPERATURE_CATALOG: Dict[str, Dict[str, str]] = {
    "cool": {"label": "Cool", "instruction": "deliberate, restrained, careful under pressure"},
    "balanced": {"label": "Balanced", "instruction": "practical, even-tempered, evidence-first"},
    "hot": {"label": "Hot", "instruction": "provocative, forceful, aggressively pressure-testing"},
}

HARNESS_CONCISION_CATALOG: Dict[str, Dict[str, str]] = {
    "none": {"label": "No harness"},
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
EXECUTION_CANCELLED_MESSAGE = "Execution cancelled by operator."
WEB_SEARCH_TOOL_CALL_PRICE_USD = 0.01
REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_CONTEXT_PATH = REPO_ROOT / "AGENTS.md"
PERSONA_SKILL_MAP_PATH = REPO_ROOT / ".agents" / "persona-skill-map.json"
SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"
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


def provider_model_catalog(provider: Optional[str]) -> Dict[str, Dict[str, Any]]:
    normalized = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    return PROVIDER_MODEL_CATALOG.get(normalized, {})


def provider_display_label(provider: Optional[str]) -> str:
    normalized = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    catalog_entry = PROVIDER_CATALOG.get(normalized)
    if isinstance(catalog_entry, dict):
        label = str(catalog_entry.get("label") or "").strip()
        if label:
            return label
    return auth_key_provider_label(normalized)


def provider_status(provider: Optional[str]) -> str:
    normalized = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    catalog_entry = PROVIDER_CATALOG.get(normalized)
    if isinstance(catalog_entry, dict):
        status = str(catalog_entry.get("status") or "").strip().lower()
        if status:
            return status
    return "primary"


def provider_is_primary(provider: Optional[str]) -> bool:
    return provider_status(provider) == "primary"


def provider_supports_custom_model(provider: Optional[str]) -> bool:
    normalized = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    return normalized in {"deepseek", "anthropic", "xai", "minimax", "ollama"}


def strip_markdown_frontmatter(text: str) -> str:
    body = str(text or "").replace("\r\n", "\n")
    if not body.startswith("---\n"):
        return body.strip()
    parts = body.split("\n---\n", 1)
    if len(parts) == 2:
        return parts[1].strip()
    return body.strip()


@lru_cache(maxsize=1)
def load_agent_context() -> str:
    if not AGENT_CONTEXT_PATH.exists():
        return ""
    try:
        return AGENT_CONTEXT_PATH.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""


@lru_cache(maxsize=1)
def load_persona_skill_map() -> Dict[str, Any]:
    if not PERSONA_SKILL_MAP_PATH.exists():
        return {}
    try:
        parsed = json.loads(PERSONA_SKILL_MAP_PATH.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@lru_cache(maxsize=64)
def load_skill_text(skill_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "", str(skill_name or "").strip().lower())
    if not normalized:
        return ""
    skill_path = SKILLS_ROOT / normalized / "SKILL.md"
    if not skill_path.exists():
        return ""
    try:
        content = skill_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return strip_markdown_frontmatter(content)


def runtime_skill_names(provider: Optional[str], role: str, worker_type: Optional[str] = None) -> List[str]:
    config = load_persona_skill_map()
    names: List[str] = []
    for entry in config.get("shared", []) if isinstance(config.get("shared"), list) else []:
        names.append(str(entry).strip())

    providers_node = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    provider_node = providers_node.get(normalize_provider_id(provider, DEFAULT_PROVIDER_ID))
    if isinstance(provider_node, dict):
        for entry in provider_node.get("shared", []) if isinstance(provider_node.get("shared"), list) else []:
            names.append(str(entry).strip())
        role_entries = provider_node.get(role)
        if isinstance(role_entries, list):
            for entry in role_entries:
                names.append(str(entry).strip())

    if worker_type:
        personas_node = config.get("personas") if isinstance(config.get("personas"), dict) else {}
        persona_skills = personas_node.get(str(worker_type).strip().lower())
        if isinstance(persona_skills, list):
            for entry in persona_skills:
                names.append(str(entry).strip())

    ordered: List[str] = []
    seen: Dict[str, bool] = {}
    for name in names:
        normalized = name.strip().lower()
        if normalized and normalized not in seen:
            seen[normalized] = True
            ordered.append(normalized)
    return ordered


def build_runtime_skill_context(
    provider: Optional[str],
    role: str,
    worker_type: Optional[str] = None,
    compact: bool = False,
) -> Dict[str, Any]:
    names = runtime_skill_names(provider, role, worker_type)
    if compact:
        compact_lines: List[str] = []
        if names:
            compact_lines.append(
                "Apply these internal disciplines silently: " + ", ".join(names) + "."
            )
        return {"names": names, "prompt": "\n".join(compact_lines).strip()}
    sections: List[str] = []
    agent_context = load_agent_context()
    if agent_context:
        sections.append("Repo agent context:\n" + agent_context)
    skill_sections: List[str] = []
    for name in names:
        skill_text = load_skill_text(name)
        if skill_text:
            skill_sections.append(f"[{name}]\n{skill_text}")
    if skill_sections:
        sections.append("Active skills:\n" + "\n\n".join(skill_sections))
    return {"names": names, "prompt": "\n\n".join(sections).strip()}


def model_prefers_compact_context(provider: Optional[str], model: Optional[str]) -> bool:
    normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    normalized_model = normalize_model_id(model, default_model_for_provider(normalized_provider), normalized_provider).lower()
    if normalized_provider in {"deepseek", "minimax"}:
        return True
    compact_markers = ("mini", "nano", "flash", "highspeed")
    return any(marker in normalized_model for marker in compact_markers)


class RuntimeErrorWithCode(Exception):
    def __init__(self, message: str, status_code: int = 500, failed_call_artifact: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.failed_call_artifact = failed_call_artifact


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def budget_target_keys() -> List[str]:
    return ["commander", "worker", "summarizer"]


def normalize_budget_limits(config: Optional[Dict[str, Any]] = None, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    base = fallback or {"maxTotalTokens": 0, "maxCostUsd": 0.0, "maxOutputTokens": 0}
    return {
        "maxTotalTokens": 0,
        "maxCostUsd": round(max(0.0, float(config.get("maxCostUsd", base["maxCostUsd"]))), 6),
        "maxOutputTokens": 0,
    }


def default_budget_config() -> Dict[str, Any]:
    overall = {"maxTotalTokens": 0, "maxCostUsd": 5.0, "maxOutputTokens": 0}
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


def default_knowledgebase_config() -> Dict[str, Any]:
    return {
        "enabled": True,
        "scope": "shared",
        "bankId": "",
        "maxRecords": 6,
        "maxTokens": 900,
        "includeRuntime": True,
        "includePersistent": True,
        "fallbackToShared": True,
        "tags": [],
        "tagsMatch": "any",
    }


def default_context_mode() -> str:
    return "weighted"


def normalize_context_mode(value: Any, fallback: str = "weighted") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"weighted", "full"}:
        return candidate
    return fallback if fallback in {"weighted", "full"} else default_context_mode()


def default_front_mode() -> str:
    return "full"


def normalize_front_mode(value: Any, fallback: str = "full") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"full", "eval"}:
        return candidate
    return fallback if fallback in {"full", "eval"} else default_front_mode()


def default_engine_version() -> str:
    return "v1"


def normalize_engine_version(value: Any, fallback: str = "v1") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"v1", "v2"}:
        return candidate
    return fallback if fallback in {"v1", "v2"} else default_engine_version()


ENGINE_V2_NODE_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "prompt": {
        "role": "input",
        "executionClass": "virtual",
        "defaultTarget": None,
        "outputs": ["prompt_packet"],
        "supportsSpawnCount": False,
        "supportsToolLinks": False,
        "supportsWorkerLinks": False,
    },
    "activator": {
        "role": "lead",
        "executionClass": "blocking",
        "defaultTarget": "commander",
        "outputs": ["course_packet", "questions_for_pressure"],
        "supportsSpawnCount": False,
        "supportsToolLinks": False,
        "supportsWorkerLinks": True,
    },
    "workers": {
        "role": "pressure",
        "executionClass": "fanout",
        "defaultTarget": "workers",
        "outputs": ["worker_checkpoints", "pressure_notes"],
        "supportsSpawnCount": True,
        "supportsToolLinks": True,
        "supportsWorkerLinks": True,
    },
    "review": {
        "role": "adjudication",
        "executionClass": "blocking",
        "defaultTarget": "commander_review",
        "outputs": ["control_audit", "direction_update"],
        "supportsSpawnCount": False,
        "supportsToolLinks": True,
        "supportsWorkerLinks": False,
    },
    "tools": {
        "role": "capability",
        "executionClass": "virtual",
        "defaultTarget": None,
        "outputs": ["capability_grants"],
        "supportsSpawnCount": False,
        "supportsToolLinks": False,
        "supportsWorkerLinks": True,
    },
    "answerNow": {
        "role": "sidecar",
        "executionClass": "sidecar",
        "defaultTarget": "answer_now",
        "outputs": ["partial_answer"],
        "supportsSpawnCount": False,
        "supportsToolLinks": True,
        "supportsWorkerLinks": False,
    },
    "final": {
        "role": "output",
        "executionClass": "blocking",
        "defaultTarget": "summarizer",
        "outputs": ["front_answer", "summary_artifact"],
        "supportsSpawnCount": False,
        "supportsToolLinks": True,
        "supportsWorkerLinks": False,
    },
    "judge": {
        "role": "verification",
        "executionClass": "post",
        "defaultTarget": "arbiter",
        "outputs": ["score_matrix", "blind_verdict"],
        "supportsSpawnCount": False,
        "supportsToolLinks": False,
        "supportsWorkerLinks": False,
    },
}


def default_engine_graph() -> Dict[str, Any]:
    return {
        "version": "v2",
        "nodes": {
            "prompt": {
                "id": "prompt",
                "moduleType": "prompt",
                "label": "Prompt ingress",
                "kicker": "Input",
                "meta": "objective + constraints",
                "enabled": True,
                "protected": True,
                "blockingMode": "blocking",
                "packetMode": "full",
                "x": 28,
                "y": 32,
                "width": 208,
                "spawnCount": 1,
                "timeoutControlMode": "session",
                "timeoutSeconds": 0,
            },
            "activator": {
                "id": "activator",
                "moduleType": "activator",
                "label": "Main activator",
                "kicker": "Lead thread",
                "meta": "sets direction and asks for pressure",
                "enabled": True,
                "protected": True,
                "blockingMode": "blocking",
                "packetMode": "full",
                "x": 290,
                "y": 32,
                "width": 236,
                "spawnCount": 1,
                "timeoutControlMode": "session",
                "timeoutSeconds": 0,
            },
            "workers": {
                "id": "workers",
                "moduleType": "workers",
                "label": "Adversarial lanes",
                "kicker": "Pressure mesh",
                "meta": "spawnable packet-driven workers",
                "enabled": True,
                "protected": True,
                "blockingMode": "blocking",
                "packetMode": "weighted",
                "x": 116,
                "y": 196,
                "width": 230,
                "spawnCount": 3,
                "timeoutControlMode": "session",
                "timeoutSeconds": 0,
            },
            "review": {
                "id": "review",
                "moduleType": "review",
                "label": "Review / redirect",
                "kicker": "Control gate",
                "meta": "accept or redirect pressure",
                "enabled": True,
                "protected": True,
                "blockingMode": "blocking",
                "packetMode": "full",
                "x": 432,
                "y": 196,
                "width": 236,
                "spawnCount": 1,
                "timeoutControlMode": "session",
                "timeoutSeconds": 0,
            },
            "tools": {
                "id": "tools",
                "moduleType": "tools",
                "label": "Capability plane",
                "kicker": "Tools",
                "meta": "research, local, GitHub",
                "enabled": True,
                "protected": True,
                "blockingMode": "optional",
                "packetMode": "on-demand",
                "x": 824,
                "y": 32,
                "width": 212,
                "spawnCount": 1,
                "timeoutControlMode": "session",
                "timeoutSeconds": 0,
            },
            "answerNow": {
                "id": "answerNow",
                "moduleType": "answerNow",
                "label": "Answer now",
                "kicker": "Sidecar",
                "meta": "non-blocking partial answer",
                "enabled": True,
                "protected": True,
                "blockingMode": "sidecar",
                "packetMode": "compact",
                "x": 676,
                "y": 382,
                "width": 200,
                "spawnCount": 1,
                "timeoutControlMode": "session",
                "timeoutSeconds": 0,
            },
            "final": {
                "id": "final",
                "moduleType": "final",
                "label": "Final answer",
                "kicker": "Output",
                "meta": "single accountable voice",
                "enabled": True,
                "protected": True,
                "blockingMode": "blocking",
                "packetMode": "merge",
                "x": 840,
                "y": 196,
                "width": 204,
                "spawnCount": 1,
                "timeoutControlMode": "session",
                "timeoutSeconds": 0,
            },
            "judge": {
                "id": "judge",
                "moduleType": "judge",
                "label": "Judge tap",
                "kicker": "Verify",
                "meta": "blind vetting and scoring",
                "enabled": True,
                "protected": True,
                "blockingMode": "post",
                "packetMode": "blind",
                "x": 904,
                "y": 382,
                "width": 184,
                "spawnCount": 1,
                "timeoutControlMode": "session",
                "timeoutSeconds": 0,
            },
        },
        "edges": [
            {"from": "prompt", "to": "activator", "label": "prompt"},
            {"from": "activator", "to": "workers", "label": "pressure"},
            {"from": "tools", "to": "workers", "label": "tools"},
            {"from": "workers", "to": "review", "label": "checkpoints"},
            {"from": "activator", "to": "review", "label": "course"},
            {"from": "review", "to": "answerNow", "label": "sidecar"},
            {"from": "review", "to": "final", "label": "merge"},
            {"from": "answerNow", "to": "final", "label": "early view"},
            {"from": "final", "to": "judge", "label": "verify"},
        ],
    }


def normalize_engine_graph(value: Any) -> Dict[str, Any]:
    default_graph = default_engine_graph()
    source = value if isinstance(value, dict) else {}
    source_nodes = source.get("nodes") if isinstance(source.get("nodes"), dict) else {}
    source_edges = source.get("edges") if isinstance(source.get("edges"), list) else []
    nodes: Dict[str, Dict[str, Any]] = {}

    def _normalize_timeout_control_mode(raw: Any, fallback: str = "session") -> str:
        normalized = str(raw or "").strip().lower()
        if normalized == "override":
            return "override"
        return "session" if fallback not in {"session", "override"} else fallback

    def _normalize_node(node_id: str, raw: Any, fallback: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not re.match(r"^[a-zA-Z0-9_-]+$", str(node_id or "")):
            return None
        base = dict(fallback or {})
        if isinstance(raw, dict):
            base.update(raw)
        module_type = str(base.get("moduleType") or node_id).strip() or node_id
        return {
            "id": str(node_id),
            "moduleType": module_type,
            "label": str(base.get("label") or module_type).strip() or module_type,
            "kicker": str(base.get("kicker") or "Module").strip() or "Module",
            "meta": str(base.get("meta") or "").strip(),
            "enabled": coerce_bool(base.get("enabled"), True),
            "protected": coerce_bool(base.get("protected"), False),
            "blockingMode": str(base.get("blockingMode") or "blocking").strip() or "blocking",
            "packetMode": str(base.get("packetMode") or "full").strip() or "full",
            "x": max(0, min(1800, int(base.get("x") or 0))),
            "y": max(0, min(1200, int(base.get("y") or 0))),
            "width": max(168, min(360, int(base.get("width") or 208))),
            "spawnCount": max(1, min(12, int(base.get("spawnCount") or 1))),
            "timeoutControlMode": _normalize_timeout_control_mode(
                base.get("timeoutControlMode"),
                str((fallback or {}).get("timeoutControlMode") or "session"),
            ),
            "timeoutSeconds": max(0, min(3600, int(base.get("timeoutSeconds") or 0))),
        }

    for node_id, default_node in default_graph["nodes"].items():
        normalized = _normalize_node(node_id, source_nodes.get(node_id), default_node)
        if normalized is not None:
            nodes[node_id] = normalized

    for node_id, raw_node in source_nodes.items():
        if node_id in nodes:
            continue
        normalized = _normalize_node(node_id, raw_node)
        if normalized is not None:
            nodes[node_id] = normalized

    seen_edges: set[tuple[str, str, str]] = set()
    edges: List[Dict[str, str]] = []
    for raw_edge in source_edges or default_graph["edges"]:
        if not isinstance(raw_edge, dict):
            continue
        source_id = str(raw_edge.get("from") or "").strip()
        target_id = str(raw_edge.get("to") or "").strip()
        if source_id not in nodes or target_id not in nodes or source_id == target_id:
            continue
        label = str(raw_edge.get("label") or "").strip()
        edge_key = (source_id, target_id, label)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        edges.append({"from": source_id, "to": target_id, "label": label})

    if not edges:
        return default_graph
    return {"version": "v2", "nodes": nodes, "edges": edges}


def engine_v2_node_contract(module_type: Any) -> Dict[str, Any]:
    normalized = str(module_type or "").strip()
    return dict(ENGINE_V2_NODE_CONTRACTS.get(normalized) or {
        "role": "custom",
        "executionClass": "blocking",
        "defaultTarget": None,
        "outputs": [],
        "supportsSpawnCount": True,
        "supportsToolLinks": True,
        "supportsWorkerLinks": True,
    })


def default_engine_plan() -> Dict[str, Any]:
    return {
        "version": "v2",
        "graphSignature": "",
        "valid": True,
        "errors": [],
        "warnings": [],
        "summary": {
            "nodeCount": 0,
            "enabledNodeCount": 0,
            "edgeCount": 0,
            "stageCount": 0,
            "workerBlocks": 0,
            "sidecarBlocks": 0,
            "postBlocks": 0,
            "workItemCount": 0,
        },
        "roots": [],
        "terminals": [],
        "executionOrder": [],
        "stages": [],
        "nodes": [],
        "nodesById": {},
        "runner": {
            "mainPath": [],
            "workerBlocks": [],
            "sidecars": [],
            "post": [],
            "workItems": [],
            "workItemsById": {},
            "liveExecution": {
                "supported": False,
                "mode": "fallback-only",
                "reason": "V2 execution has not been classified yet.",
                "reasons": [],
            },
        },
    }


def compile_engine_graph(
    graph: Any,
    *,
    task: Optional[Dict[str, Any]] = None,
    runtime_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_graph = normalize_engine_graph(graph)
    plan = default_engine_plan()
    plan["graphSignature"] = hashlib.md5(
        json.dumps(normalized_graph, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    nodes = normalized_graph.get("nodes") if isinstance(normalized_graph.get("nodes"), dict) else {}
    edges = normalized_graph.get("edges") if isinstance(normalized_graph.get("edges"), list) else []
    enabled_nodes = {
        node_id: node
        for node_id, node in nodes.items()
        if isinstance(node, dict) and coerce_bool(node.get("enabled"), True)
    }
    inbound: Dict[str, List[Dict[str, str]]] = {node_id: [] for node_id in enabled_nodes}
    outbound: Dict[str, List[Dict[str, str]]] = {node_id: [] for node_id in enabled_nodes}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source_id = str(edge.get("from") or "").strip()
        target_id = str(edge.get("to") or "").strip()
        if source_id not in enabled_nodes or target_id not in enabled_nodes:
            continue
        normalized_edge = {
            "from": source_id,
            "to": target_id,
            "label": str(edge.get("label") or "").strip(),
        }
        outbound[source_id].append(normalized_edge)
        inbound[target_id].append(normalized_edge)

    indegree: Dict[str, int] = {node_id: len(inbound[node_id]) for node_id in enabled_nodes}
    ready: List[str] = sorted([node_id for node_id, count in indegree.items() if count == 0])
    topo_order: List[str] = []
    while ready:
        current = ready.pop(0)
        topo_order.append(current)
        for edge in outbound.get(current, []):
            target_id = edge["to"]
            indegree[target_id] = max(0, indegree[target_id] - 1)
            if indegree[target_id] == 0:
                ready.append(target_id)
                ready.sort()

    if len(topo_order) != len(enabled_nodes):
        cycle_nodes = sorted(node_id for node_id in enabled_nodes if node_id not in topo_order)
        plan["valid"] = False
        plan["errors"].append(
            f"Engine graph contains a cycle or unreachable dependency loop involving: {', '.join(cycle_nodes)}"
        )
        topo_order.extend(cycle_nodes)

    stage_by_id: Dict[str, int] = {}
    for node_id in topo_order:
        dependencies = [edge["from"] for edge in inbound.get(node_id, [])]
        if not dependencies:
            stage_by_id[node_id] = 0
        else:
            stage_by_id[node_id] = max(stage_by_id.get(dep_id, 0) for dep_id in dependencies) + 1

    task_workers_count = len(task_workers(task or {})) if isinstance(task, dict) else 0
    runtime_provider = normalize_provider_id(
        ((runtime_config or {}).get("provider") if isinstance(runtime_config, dict) else None) or ((task or {}).get("runtime") or {}).get("provider"),
        DEFAULT_PROVIDER_ID,
    ) if isinstance((task or {}).get("runtime"), dict) or isinstance(runtime_config, dict) else DEFAULT_PROVIDER_ID
    capability_profile = provider_capability_profile(runtime_provider)

    nodes_payload: List[Dict[str, Any]] = []
    nodes_by_id: Dict[str, Dict[str, Any]] = {}
    worker_block_ids: List[str] = []
    sidecar_ids: List[str] = []
    post_ids: List[str] = []
    roots = sorted(node_id for node_id in enabled_nodes if not inbound.get(node_id))
    terminals = sorted(node_id for node_id in enabled_nodes if not outbound.get(node_id))

    for node_id in topo_order:
        node = enabled_nodes.get(node_id)
        if not isinstance(node, dict):
            continue
        module_type = str(node.get("moduleType") or node_id).strip() or node_id
        contract = engine_v2_node_contract(module_type)
        dependencies = [edge["from"] for edge in inbound.get(node_id, [])]
        dependents = [edge["to"] for edge in outbound.get(node_id, [])]
        tool_inputs = [edge["from"] for edge in inbound.get(node_id, []) if str(nodes.get(edge["from"], {}).get("moduleType") or "") == "tools"]
        worker_parents = [
            edge["from"]
            for edge in inbound.get(node_id, [])
            if str(nodes.get(edge["from"], {}).get("moduleType") or "") == "workers"
        ]
        worker_children = [
            edge["to"]
            for edge in outbound.get(node_id, [])
            if str(nodes.get(edge["to"], {}).get("moduleType") or "") == "workers"
        ]
        schedule_class = str(contract.get("executionClass") or "blocking")
        runner_target = contract.get("defaultTarget")
        lane_count = int(node.get("spawnCount") or 1)
        if module_type == "workers":
            lane_count = max(1, lane_count or task_workers_count or 1)
            worker_block_ids.append(node_id)
        if schedule_class == "sidecar":
            sidecar_ids.append(node_id)
        if schedule_class == "post":
            post_ids.append(node_id)
        if module_type == "workers" and not worker_parents:
            plan["warnings"].append(f"Worker block '{node_id}' has no activator or parent worker input.")
        if module_type == "final" and "review" not in [str(nodes.get(dep_id, {}).get("moduleType") or "") for dep_id in dependencies]:
            plan["warnings"].append(f"Final block '{node_id}' is not directly gated by a review block.")
        if module_type == "judge" and runner_target and "final" not in [str(nodes.get(dep_id, {}).get("moduleType") or "") for dep_id in dependencies]:
            plan["warnings"].append(f"Judge block '{node_id}' is not downstream of a final-answer block.")
        timeout_control_mode = str(node.get("timeoutControlMode") or "session").strip().lower()
        timeout_override_seconds = max(0, int(node.get("timeoutSeconds") or 0)) if timeout_control_mode == "override" else 0
        node_payload = {
            "id": node_id,
            "label": str(node.get("label") or node_id),
            "moduleType": module_type,
            "kicker": str(node.get("kicker") or "Module"),
            "meta": str(node.get("meta") or ""),
            "enabled": True,
            "protected": coerce_bool(node.get("protected"), False),
            "blockingMode": str(node.get("blockingMode") or "blocking"),
            "packetMode": str(node.get("packetMode") or "full"),
            "timeoutControlMode": timeout_control_mode if timeout_control_mode in {"session", "override"} else "session",
            "timeoutSeconds": max(0, int(node.get("timeoutSeconds") or 0)),
            "stageIndex": int(stage_by_id.get(node_id, 0)),
            "dependencies": dependencies,
            "dependents": dependents,
            "toolInputs": tool_inputs,
            "workerParents": worker_parents,
            "workerChildren": worker_children,
            "contract": {
                "role": contract.get("role"),
                "executionClass": schedule_class,
                "defaultTarget": runner_target,
                "outputs": list(contract.get("outputs") or []),
                "supportsSpawnCount": bool(contract.get("supportsSpawnCount")),
                "supportsToolLinks": bool(contract.get("supportsToolLinks")),
                "supportsWorkerLinks": bool(contract.get("supportsWorkerLinks")),
            },
            "execution": {
                "target": runner_target,
                "scheduleClass": schedule_class,
                "sidecar": schedule_class == "sidecar",
                "post": schedule_class == "post",
                "virtual": schedule_class == "virtual",
                "blocking": schedule_class == "blocking",
                "fanout": schedule_class == "fanout",
                "laneCount": lane_count,
                "timeoutControlMode": timeout_control_mode if timeout_control_mode in {"session", "override"} else "session",
                "timeoutSeconds": timeout_override_seconds,
                "configuredTimeoutSeconds": max(0, int(node.get("timeoutSeconds") or 0)),
                "provider": runtime_provider,
                "toolsEnabled": bool(tool_inputs) and (
                    capability_profile.get("localFiles")
                    or capability_profile.get("githubTools")
                    or capability_profile.get("webSearch")
                ),
            },
        }
        nodes_payload.append(node_payload)
        nodes_by_id[node_id] = node_payload

    max_stage = max(stage_by_id.values(), default=-1)
    stages: List[Dict[str, Any]] = []
    for stage_index in range(max_stage + 1):
        stage_node_ids = [node_id for node_id in topo_order if stage_by_id.get(node_id) == stage_index]
        blocking_nodes = [node_id for node_id in stage_node_ids if nodes_by_id[node_id]["execution"]["blocking"]]
        fanout_nodes = [node_id for node_id in stage_node_ids if nodes_by_id[node_id]["execution"]["fanout"]]
        sidecar_nodes = [node_id for node_id in stage_node_ids if nodes_by_id[node_id]["execution"]["sidecar"]]
        post_nodes = [node_id for node_id in stage_node_ids if nodes_by_id[node_id]["execution"]["post"]]
        virtual_nodes = [node_id for node_id in stage_node_ids if nodes_by_id[node_id]["execution"]["virtual"]]
        stages.append(
            {
                "index": stage_index,
                "nodeIds": stage_node_ids,
                "blockingNodeIds": blocking_nodes,
                "fanoutNodeIds": fanout_nodes,
                "sidecarNodeIds": sidecar_nodes,
                "postNodeIds": post_nodes,
                "virtualNodeIds": virtual_nodes,
            }
        )

    executable_node_ids = [
        node_id
        for node_id in topo_order
        if node_id in nodes_by_id and nodes_by_id[node_id]["execution"]["target"]
    ]
    work_items: List[Dict[str, Any]] = []
    work_items_by_id: Dict[str, Dict[str, Any]] = {}
    work_item_ids_by_node: Dict[str, str] = {}
    work_item_schedule_class_by_node: Dict[str, str] = {}
    for index, node_id in enumerate(executable_node_ids, start=1):
        node_payload = nodes_by_id[node_id]
        execution_payload = node_payload["execution"]
        work_item_id = f"work-{index:02d}-{node_id}"
        blocking_dependency_work_item_ids: List[str] = []
        advisory_dependency_work_item_ids: List[str] = []
        for dep_id in node_payload["dependencies"]:
            if dep_id not in work_item_ids_by_node:
                continue
            dep_work_item_id = work_item_ids_by_node[dep_id]
            dep_schedule_class = str(work_item_schedule_class_by_node.get(dep_id) or "")
            if dep_schedule_class in {"sidecar", "post", "virtual"}:
                advisory_dependency_work_item_ids.append(dep_work_item_id)
            else:
                blocking_dependency_work_item_ids.append(dep_work_item_id)
        work_item = {
            "id": work_item_id,
            "nodeId": node_id,
            "moduleType": node_payload["moduleType"],
            "target": execution_payload["target"],
            "stageIndex": int(node_payload["stageIndex"]),
            "scheduleClass": execution_payload["scheduleClass"],
            "blocking": bool(execution_payload["blocking"]),
            "fanout": bool(execution_payload["fanout"]),
            "sidecar": bool(execution_payload["sidecar"]),
            "post": bool(execution_payload["post"]),
            "laneCount": int(execution_payload["laneCount"] or 1),
            "timeoutControlMode": str(execution_payload.get("timeoutControlMode") or "session"),
            "timeoutSeconds": max(0, int(execution_payload.get("timeoutSeconds") or 0)),
            "configuredTimeoutSeconds": max(0, int(execution_payload.get("configuredTimeoutSeconds") or 0)),
            "provider": execution_payload["provider"],
            "packetMode": str(node_payload["packetMode"] or "full"),
            "dependencies": list(node_payload["dependencies"]),
            "dependencyWorkItemIds": blocking_dependency_work_item_ids,
            "advisoryDependencyWorkItemIds": advisory_dependency_work_item_ids,
            "toolNodeIds": list(node_payload["toolInputs"]),
        }
        work_items.append(work_item)
        work_items_by_id[work_item_id] = work_item
        work_item_ids_by_node[node_id] = work_item_id
        work_item_schedule_class_by_node[node_id] = str(execution_payload["scheduleClass"] or "")
        execution_payload["workItemId"] = work_item_id
        execution_payload["dependencyWorkItemIds"] = blocking_dependency_work_item_ids
        execution_payload["advisoryDependencyWorkItemIds"] = advisory_dependency_work_item_ids

    executable_module_ids_by_type: Dict[str, List[str]] = {}
    for node_id in executable_node_ids:
        executable_module_ids_by_type.setdefault(str(nodes_by_id[node_id]["moduleType"]), []).append(node_id)

    main_path_targets = [
        str(nodes_by_id[node_id]["execution"]["target"])
        for node_id in topo_order
        if node_id in nodes_by_id
        and (
            nodes_by_id[node_id]["execution"]["blocking"]
            or nodes_by_id[node_id]["execution"]["fanout"]
        )
        and nodes_by_id[node_id]["execution"]["target"]
    ]
    live_execution_reasons: List[str] = []
    activator_ids = executable_module_ids_by_type.get("activator", [])
    worker_ids = executable_module_ids_by_type.get("workers", [])
    review_ids = executable_module_ids_by_type.get("review", [])
    final_ids = executable_module_ids_by_type.get("final", [])
    answer_now_ids = executable_module_ids_by_type.get("answerNow", [])
    judge_ids = executable_module_ids_by_type.get("judge", [])

    if len(activator_ids) != 1:
        live_execution_reasons.append("V2 live execution currently requires exactly one activator block.")
    if len(review_ids) != 1:
        live_execution_reasons.append("V2 live execution currently requires exactly one review block.")
    if len(final_ids) != 1:
        live_execution_reasons.append("V2 live execution currently requires exactly one final block.")
    if len(worker_ids) > 1:
        live_execution_reasons.append("V2 live execution currently supports at most one worker fan-out block.")
    nested_worker_ids = [node_id for node_id in worker_ids if nodes_by_id[node_id]["workerParents"]]
    if nested_worker_ids:
        live_execution_reasons.append(
            "Nested worker-to-worker chains compile, but they still fall back to V1 execution."
        )
    if len(answer_now_ids) > 1:
        live_execution_reasons.append("V2 live execution currently supports at most one Answer Now sidecar.")
    if len(judge_ids) > 1:
        live_execution_reasons.append("V2 live execution currently supports at most one judge block.")
    if main_path_targets not in (
        ["commander", "commander_review", "summarizer"],
        ["commander", "workers", "commander_review", "summarizer"],
    ):
        live_execution_reasons.append(
            "Main path must currently resolve to commander -> [workers] -> commander_review -> summarizer."
        )

    if activator_ids and worker_ids:
        activator_id = activator_ids[0]
        worker_id = worker_ids[0]
        if activator_id not in nodes_by_id[worker_id]["dependencies"]:
            live_execution_reasons.append("Worker fan-out must currently depend directly on the activator.")
    if review_ids and final_ids:
        review_id = review_ids[0]
        final_id = final_ids[0]
        if review_id not in nodes_by_id[final_id]["dependencies"]:
            live_execution_reasons.append("Final block must currently depend directly on the review block.")
    if review_ids and worker_ids:
        review_id = review_ids[0]
        worker_id = worker_ids[0]
        if worker_id not in nodes_by_id[review_id]["dependencies"]:
            live_execution_reasons.append("Review block must currently ingest the worker fan-out output.")
    if judge_ids and final_ids:
        judge_id = judge_ids[0]
        final_id = final_ids[0]
        if final_id not in nodes_by_id[judge_id]["dependencies"]:
            live_execution_reasons.append("Judge block must currently sit downstream of the final answer.")

    live_execution_supported = bool(plan["valid"]) and not live_execution_reasons
    if live_execution_reasons:
        for reason in live_execution_reasons:
            plan["warnings"].append(f"V2 execution fallback: {reason}")

    plan["summary"] = {
        "nodeCount": len(nodes),
        "enabledNodeCount": len(enabled_nodes),
        "edgeCount": len(edges),
        "stageCount": len(stages),
        "workerBlocks": len(worker_block_ids),
        "sidecarBlocks": len(sidecar_ids),
        "postBlocks": len(post_ids),
        "workItemCount": len(work_items),
    }
    plan["roots"] = roots
    plan["terminals"] = terminals
    plan["executionOrder"] = topo_order
    plan["stages"] = stages
    plan["nodes"] = nodes_payload
    plan["nodesById"] = nodes_by_id
    plan["runner"] = {
        "mainPath": [
            node_id
            for node_id in topo_order
            if nodes_by_id[node_id]["execution"]["blocking"] or nodes_by_id[node_id]["execution"]["fanout"]
        ],
        "workerBlocks": worker_block_ids,
        "sidecars": sidecar_ids,
        "post": post_ids,
        "workItems": work_items,
        "workItemsById": work_items_by_id,
        "liveExecution": {
            "supported": live_execution_supported,
            "mode": "v1-compatible" if live_execution_supported else "fallback-only",
            "reason": "" if live_execution_supported else live_execution_reasons[0],
            "reasons": live_execution_reasons,
        },
    }
    if not any(str(nodes_by_id[node_id]["moduleType"]) == "final" for node_id in topo_order if node_id in nodes_by_id):
        plan["warnings"].append("No final-answer block is enabled in the current V2 graph.")
    return plan


def default_direct_baseline_mode() -> str:
    return "off"


def normalize_direct_baseline_mode(value: Any, fallback: str = "off") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"off", "single", "both"}:
        return candidate
    return fallback if fallback in {"off", "single", "both"} else default_direct_baseline_mode()


def default_target_timeout_config() -> Dict[str, Any]:
    return {
        "directBaseline": 150,
        "commander": 180,
        "workerDefault": 180,
        "workers": {},
        "commanderReview": 240,
        "summarizer": 240,
        "answerNow": 180,
        "arbiter": 180,
    }


def default_timeout_mode() -> str:
    return "default"


def normalize_timeout_mode(value: Any, fallback: str = "default") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"default", "user", "auto"}:
        return candidate
    return fallback if fallback in {"default", "user", "auto"} else default_timeout_mode()


def clamp_timeout_seconds(value: Any, fallback: int) -> int:
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        candidate = int(fallback)
    return max(15, min(3600, candidate))


def normalize_worker_timeout_overrides(value: Any) -> Dict[str, int]:
    overrides: Dict[str, int] = {}
    if not isinstance(value, dict):
        return overrides
    for worker_id, seconds in value.items():
        candidate = str(worker_id or "").strip().upper()
        if not re.match(r"^[A-Z]$", candidate):
            continue
        overrides[candidate] = clamp_timeout_seconds(seconds, default_target_timeout_config()["workerDefault"])
    return overrides


def normalize_target_timeout_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    default = default_target_timeout_config()
    return {
        "directBaseline": clamp_timeout_seconds(config.get("directBaseline"), default["directBaseline"]),
        "commander": clamp_timeout_seconds(config.get("commander"), default["commander"]),
        "workerDefault": clamp_timeout_seconds(config.get("workerDefault"), default["workerDefault"]),
        "workers": normalize_worker_timeout_overrides(config.get("workers")),
        "commanderReview": clamp_timeout_seconds(config.get("commanderReview"), default["commanderReview"]),
        "summarizer": clamp_timeout_seconds(config.get("summarizer"), default["summarizer"]),
        "answerNow": clamp_timeout_seconds(config.get("answerNow"), default["answerNow"]),
        "arbiter": clamp_timeout_seconds(config.get("arbiter"), default["arbiter"]),
    }


def default_ollama_timeout_profile() -> Dict[str, Any]:
    return {
        "status": "idle",
        "measuredAt": None,
        "baseUrl": default_ollama_base_url(),
        "models": {},
        "targetTimeouts": default_target_timeout_config(),
        "note": "",
    }


def normalize_ollama_timeout_profile(value: Any) -> Dict[str, Any]:
    current = value if isinstance(value, dict) else {}
    raw_models = current.get("models") if isinstance(current.get("models"), dict) else {}
    models: Dict[str, Dict[str, Any]] = {}
    for model_name, model_payload in raw_models.items():
        normalized_model = str(model_name or "").strip()
        if not normalized_model:
            continue
        payload = model_payload if isinstance(model_payload, dict) else {}
        try:
            wall_seconds = float(payload.get("wallSeconds") or 0.0)
        except (TypeError, ValueError):
            wall_seconds = 0.0
        try:
            total_duration_ms = float(payload.get("totalDurationMs") or 0.0)
        except (TypeError, ValueError):
            total_duration_ms = 0.0
        models[normalized_model] = {
            "wallSeconds": max(0.0, round(wall_seconds, 3)),
            "totalDurationMs": max(0.0, round(total_duration_ms, 3)),
            "evalCount": max(0, int(payload.get("evalCount") or 0)),
            "promptEvalCount": max(0, int(payload.get("promptEvalCount") or 0)),
        }
    return {
        "status": "ready" if str(current.get("status") or "").strip().lower() == "ready" else "idle",
        "measuredAt": str(current.get("measuredAt") or "").strip() or None,
        "baseUrl": normalize_ollama_base_url(current.get("baseUrl", default_ollama_base_url())),
        "models": models,
        "targetTimeouts": normalize_target_timeout_config(current.get("targetTimeouts") if isinstance(current.get("targetTimeouts"), dict) else {}),
        "note": str(current.get("note") or "").strip(),
    }


def target_timeout_seconds(config: Optional[Dict[str, Any]], target: Any) -> int:
    normalized_config = normalize_target_timeout_config(config)
    normalized_target = normalize_auth_target(target)
    if re.match(r"^[A-Z]$", normalized_target):
        return int(normalized_config["workers"].get(normalized_target, normalized_config["workerDefault"]))
    if normalized_target == "direct_baseline":
        return int(normalized_config["directBaseline"])
    if normalized_target == "commander":
        return int(normalized_config["commander"])
    if normalized_target == "commander_review":
        return int(normalized_config["commanderReview"])
    if normalized_target == "summarizer":
        return int(normalized_config["summarizer"])
    if normalized_target == "answer_now":
        return int(normalized_config["answerNow"])
    if normalized_target == "arbiter":
        return int(normalized_config["arbiter"])
    return int(normalized_config["workerDefault"])


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
        "activeTargets": [],
        "providerTrace": None,
    }


def default_state() -> Dict[str, Any]:
    return {
        "activeTask": None,
        "draft": {},
        "commander": None,
        "commanderReview": None,
        "workers": {},
        "directBaseline": None,
        "summary": None,
        "arbiter": None,
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
    return str(PROVIDER_DEFAULT_MODELS.get(normalized) or DEFAULT_MODEL_ID)


def default_judge_model_for_provider(provider: Optional[str]) -> str:
    normalized = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    if normalized == "ollama":
        return str(os.getenv("LOOP_OLLAMA_DEFAULT_JUDGE_MODEL") or os.getenv("LOOP_OLLAMA_DEFAULT_MODEL") or PROVIDER_DEFAULT_JUDGE_MODELS.get("ollama") or DEFAULT_OLLAMA_MODEL_ID).strip() or DEFAULT_OLLAMA_MODEL_ID
    return str(PROVIDER_DEFAULT_JUDGE_MODELS.get(normalized) or default_model_for_provider(normalized)).strip() or default_model_for_provider(normalized)


def infer_provider_from_model_id(model: Optional[str]) -> Optional[str]:
    candidate = (model or "").strip()
    if not candidate:
        return None
    for provider_id, catalog in PROVIDER_MODEL_CATALOG.items():
        if candidate in catalog:
            return provider_id
    if candidate.lower().startswith("claude-"):
        return "anthropic"
    if candidate.lower().startswith("deepseek-"):
        return "deepseek"
    if candidate.lower().startswith("grok-"):
        return "xai"
    if candidate.startswith("MiniMax-"):
        return "minimax"
    return "ollama"


def provider_capability_profile(provider: Optional[str]) -> Dict[str, Any]:
    normalized = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    raw = PROVIDER_CAPABILITY_CATALOG.get(normalized) or {}
    status = provider_status(normalized)
    return {
        "provider": normalized,
        "status": status,
        "primary": status == "primary",
        "toolLoop": bool(raw.get("toolLoop", False)),
        "webSearch": bool(raw.get("webSearch", False)),
        "localFiles": bool(raw.get("localFiles", False)),
        "githubTools": bool(raw.get("githubTools", False)),
        "costTracking": bool(raw.get("costTracking", False)),
        "reasoningSummary": bool(raw.get("reasoningSummary", False)),
        "notes": limit_string_list(raw.get("notes", []), 6, 180),
    }


def default_ollama_base_url() -> str:
    return str(os.getenv("LOOP_OLLAMA_BASE_URL") or "http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434"


def normalize_ollama_base_url(value: Any) -> str:
    raw = str(value or "").strip()
    base = raw or default_ollama_base_url()
    return base.rstrip("/")


def default_provider_routing_config() -> Dict[str, Any]:
    return {
        "ollama": {
            "selectionMode": "single",
            "judgeMode": "prefer_distinct",
        }
    }


def normalize_provider_routing_config(value: Any) -> Dict[str, Any]:
    current = value if isinstance(value, dict) else {}
    normalized: Dict[str, Any] = {}
    for provider_id, default_node in default_provider_routing_config().items():
        source_node = current.get(provider_id) if isinstance(current.get(provider_id), dict) else {}
        selection_mode = str(source_node.get("selectionMode", default_node.get("selectionMode", "single"))).strip().lower()
        if selection_mode not in {"single", "rotate", "mix"}:
            selection_mode = str(default_node.get("selectionMode", "single"))
        judge_mode = str(source_node.get("judgeMode", default_node.get("judgeMode", "prefer_distinct"))).strip().lower()
        if judge_mode not in {"default", "prefer_distinct"}:
            judge_mode = str(default_node.get("judgeMode", "prefer_distinct"))
        normalized[provider_id] = {
            "selectionMode": selection_mode,
            "judgeMode": judge_mode,
        }
    return normalized


def provider_instance_file_path(root: Path) -> Path:
    return Path(root).resolve() / "providers.txt"


def _provider_instance_id_from_base_url(provider: str, base_url: str, index: int = 1) -> str:
    host = re.sub(r"[^a-z0-9]+", "-", normalize_ollama_base_url(base_url).lower()).strip("-")
    provider_prefix = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    candidate = f"{provider_prefix}-{host}" if host else provider_prefix
    if not candidate:
        candidate = f"{provider_prefix}-{index}"
    return candidate[:80]


def default_provider_instance_entry(provider: Any, base_url: Any, index: int = 1) -> Dict[str, Any]:
    normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    normalized_base_url = normalize_ollama_base_url(base_url)
    return {
        "id": _provider_instance_id_from_base_url(normalized_provider, normalized_base_url, index),
        "provider": normalized_provider,
        "label": f"{provider_display_label(normalized_provider)} {index}",
        "baseUrl": normalized_base_url,
        "enabled": True,
        "models": [],
    }


def normalize_provider_instance_entry(entry: Any, fallback_provider: Any = DEFAULT_PROVIDER_ID, index: int = 1) -> Optional[Dict[str, Any]]:
    current = entry if isinstance(entry, dict) else {}
    provider = normalize_provider_id(current.get("provider"), normalize_provider_id(fallback_provider, DEFAULT_PROVIDER_ID))
    raw_base_url = current.get("baseUrl", current.get("url"))
    base_url = normalize_ollama_base_url(raw_base_url)
    if not base_url:
        return None
    raw_models = current.get("models")
    if isinstance(raw_models, str):
        models = normalize_string_list(raw_models)
    elif isinstance(raw_models, (list, tuple)):
        models = normalize_string_list(list(raw_models))
    else:
        models = []
    identifier = str(current.get("id") or "").strip()
    if not identifier:
        identifier = _provider_instance_id_from_base_url(provider, base_url, index)
    label = str(current.get("label") or "").strip() or f"{provider_display_label(provider)} {index}"
    return {
        "id": identifier[:80],
        "provider": provider,
        "label": label[:120],
        "baseUrl": base_url,
        "enabled": coerce_bool(current.get("enabled"), True),
        "models": models,
    }


def normalize_provider_instance_catalog(value: Any) -> Dict[str, List[Dict[str, Any]]]:
    catalog = value if isinstance(value, dict) else {}
    normalized: Dict[str, List[Dict[str, Any]]] = {}
    for provider_id in PROVIDER_CATALOG:
        entries = catalog.get(provider_id)
        source_entries = entries if isinstance(entries, list) else []
        cleaned: List[Dict[str, Any]] = []
        seen_ids: Dict[str, bool] = {}
        seen_urls: Dict[str, bool] = {}
        for index, entry in enumerate(source_entries, start=1):
            normalized_entry = normalize_provider_instance_entry(entry, provider_id, index)
            if not normalized_entry:
                continue
            entry_id = str(normalized_entry.get("id") or "").strip().lower()
            base_url = str(normalized_entry.get("baseUrl") or "").strip().lower()
            if not entry_id or entry_id in seen_ids or base_url in seen_urls:
                continue
            seen_ids[entry_id] = True
            seen_urls[base_url] = True
            cleaned.append(normalized_entry)
        normalized[provider_id] = cleaned
    return normalized


def read_provider_instance_catalog(root: Path) -> Dict[str, List[Dict[str, Any]]]:
    path = provider_instance_file_path(root)
    if not path.is_file():
        return normalize_provider_instance_catalog({})
    raw = path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
    if not raw:
        return normalize_provider_instance_catalog({})
    parsed: Any = None
    if raw.startswith("{") or raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
    if isinstance(parsed, list):
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for index, entry in enumerate(parsed, start=1):
            normalized_entry = normalize_provider_instance_entry(entry, (entry or {}).get("provider"), index)
            if not normalized_entry:
                continue
            grouped.setdefault(normalized_entry["provider"], []).append(normalized_entry)
        return normalize_provider_instance_catalog(grouped)
    if isinstance(parsed, dict):
        return normalize_provider_instance_catalog(parsed)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for index, raw_line in enumerate(raw.splitlines(), start=1):
        line = str(raw_line or "").strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        provider = ""
        base_url = ""
        label = ""
        models: List[str] = []
        match = re.match(r"^([a-z0-9_-]+)\s*:\s*(https?://\S+)$", line, flags=re.IGNORECASE)
        if match:
            provider = match.group(1)
            base_url = match.group(2)
        else:
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 2:
                provider = parts[0]
                base_url = parts[1]
                if len(parts) >= 3:
                    label = parts[2]
                if len(parts) >= 4:
                    models = normalize_string_list(parts[3:])
        normalized_entry = normalize_provider_instance_entry(
            {"provider": provider, "baseUrl": base_url, "label": label, "models": models},
            provider,
            index,
        )
        if not normalized_entry:
            continue
        grouped.setdefault(normalized_entry["provider"], []).append(normalized_entry)
    return normalize_provider_instance_catalog(grouped)


def write_provider_instance_catalog(root: Path, catalog: Any) -> Dict[str, List[Dict[str, Any]]]:
    normalized = normalize_provider_instance_catalog(catalog)
    path = provider_instance_file_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(normalized.get(provider_id) for provider_id in normalized):
        path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()
    return normalize_provider_instance_catalog(normalized)


def provider_instance_pool_status(root: Path) -> Dict[str, Any]:
    catalog = read_provider_instance_catalog(root)
    provider_groups: Dict[str, Any] = {}
    for provider_id in PROVIDER_CATALOG:
        instances = list(catalog.get(provider_id, []))
        provider_groups[provider_id] = {
            "provider": provider_id,
            "label": provider_display_label(provider_id),
            "status": provider_status(provider_id),
            "writable": True,
            "instanceCount": len(instances),
            "instances": instances,
            "statusNote": (
                f"{len(instances)} local endpoint(s) available."
                if instances
                else "No local endpoints configured for this provider group."
            ),
        }
    return {
        "file": str(provider_instance_file_path(root)),
        "providerOrder": list(PROVIDER_CATALOG.keys()),
        "providerGroups": provider_groups,
        "storage": "local_file",
        "statusNote": "Provider instance pools are local-file backed for the prototype and can later move to managed state.",
    }


def normalize_model_id(model: Optional[str], fallback: Optional[str] = None, provider: Optional[str] = None) -> str:
    normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
    candidate = (model or "").strip()
    catalog = provider_model_catalog(normalized_provider)
    if provider_supports_custom_model(normalized_provider):
        if candidate:
            return candidate
        fallback_value = (fallback or default_model_for_provider(normalized_provider)).strip()
        return fallback_value or default_model_for_provider(normalized_provider)
    if candidate in catalog:
        return candidate
    fallback_value = (fallback or default_model_for_provider(normalized_provider)).strip()
    return fallback_value if fallback_value in catalog else default_model_for_provider(normalized_provider)


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


def read_env_api_key_pool(provider: Any = "openai") -> List[str]:
    return env_secret_status(provider=normalize_auth_key_provider(provider)).get("keys", [])


def read_api_key_pool(path: Path, provider: Any = "openai") -> List[str]:
    normalized_provider = normalize_auth_key_provider(provider)
    root = path.parent if isinstance(path, Path) else None
    backend_resolution = resolve_provider_secret_backend(root, normalized_provider)
    secret_backend = backend_resolution["backend"]
    if secret_backend == "env":
        return read_env_api_key_pool(normalized_provider)
    if secret_backend == "external":
        return normalize_string_array_preserve_items(external_secret_status(provider=normalized_provider)["keys"])
    if secret_backend == "docker_secret":
        provider_path = auth_key_file_path(path, normalized_provider)
        if provider_path.exists():
            return normalize_string_array_preserve_items(provider_path.read_text(encoding="utf-8", errors="replace").splitlines())
        return []
    if secret_backend == "local_file":
        return normalize_string_array_preserve_items(read_local_auth_keys(path, normalized_provider))
    return read_env_api_key_pool(normalized_provider)


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


def normalize_knowledgebase_scope(value: Any, fallback: str = "shared") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"off", "runtime", "shared", "lane", "strict"}:
        return candidate
    return fallback if fallback in {"off", "runtime", "shared", "lane", "strict"} else "shared"


def normalize_knowledgebase_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or {}
    default = default_knowledgebase_config()
    scope = normalize_knowledgebase_scope(config.get("scope"), default["scope"])
    enabled = coerce_bool(config.get("enabled", default["enabled"]), default["enabled"]) and scope != "off"
    try:
        max_records = int(config.get("maxRecords", config.get("max_records", default["maxRecords"])) or default["maxRecords"])
    except (TypeError, ValueError):
        max_records = int(default["maxRecords"])
    try:
        max_tokens = int(config.get("maxTokens", config.get("max_tokens", default["maxTokens"])) or default["maxTokens"])
    except (TypeError, ValueError):
        max_tokens = int(default["maxTokens"])
    tags_match = "all" if str(config.get("tagsMatch", config.get("tags_match", default["tagsMatch"]))).strip().lower() == "all" else "any"
    return {
        "enabled": enabled,
        "scope": scope,
        "bankId": knowledgebase.safe_bank_id(config.get("bankId") or config.get("bank_id")) if str(config.get("bankId") or config.get("bank_id") or "").strip() else "",
        "maxRecords": max(1, min(24, max_records)),
        "maxTokens": max(256, min(8000, max_tokens)),
        "includeRuntime": coerce_bool(config.get("includeRuntime", default["includeRuntime"]), default["includeRuntime"]),
        "includePersistent": coerce_bool(config.get("includePersistent", default["includePersistent"]), default["includePersistent"]),
        "fallbackToShared": coerce_bool(config.get("fallbackToShared", default["fallbackToShared"]), default["fallbackToShared"]),
        "tags": knowledgebase.parse_tags(config.get("tags", default["tags"])),
        "tagsMatch": tags_match,
    }


def context_mode_label(mode: Any) -> str:
    normalized = normalize_context_mode(mode)
    return "Full context" if normalized == "full" else "Weighted context"


def direct_baseline_mode_label(mode: Any) -> str:
    normalized = normalize_direct_baseline_mode(mode)
    if normalized == "single":
        return "Single only"
    if normalized == "both":
        return "Both compare"
    return "Off"


def normalize_direct_answer_payload(payload: Any, objective: str = "", provider: Any = "") -> Dict[str, str]:
    current = payload if isinstance(payload, dict) else {}
    fallback_answer = str(objective or "").strip() or "No direct baseline answer was captured."
    answer = str(current.get("answer", "") or "").strip()
    if not answer:
        recommendation = str(current.get("recommendation", "") or "").strip()
        next_actions = current.get("nextActions")
        next_action_lines: List[str] = []
        if isinstance(next_actions, list):
            for entry in next_actions:
                text = str(entry or "").strip()
                if text:
                    next_action_lines.append(text)
        if recommendation:
            answer = recommendation
            if next_action_lines:
                answer += "\n\nNext actions:\n" + "\n".join(f"- {line}" for line in next_action_lines[:8])
        else:
            has_raw_provider_shape = any(
                key in current
                for key in (
                    "rawOutputText",
                    "rawProviderResponse",
                    "rawResponse",
                    "outputText",
                    "responseText",
                    "choices",
                    "output",
                    "message",
                    "content",
                    "completion",
                )
            )
            normalized_answer = (
                str(provider_responses.extract_normalized_provider_answer(provider, current) or "").strip()
                if has_raw_provider_shape
                else ""
            )
            answer = normalized_answer or flatten_output_payload_text(current, "direct_output")
    answer = answer or fallback_answer
    stance = truncate_text(current.get("stance", ""), 260) or truncate_text(answer, 260) or "No explicit stance was captured."
    confidence_note = (
        truncate_text(current.get("confidenceNote", ""), 320)
        or truncate_text(current.get("confidence_note", ""), 320)
        or "No confidence note was captured."
    )
    return {
        "answer": answer,
        "stance": stance,
        "confidenceNote": confidence_note,
    }


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
    return {
        "concision": "none",
        "instruction": "Prefer the most detailed factual response the evidence supports. Be concrete, complete, and explicit about uncertainty.",
    }


def default_direct_harness() -> Dict[str, str]:
    return {
        "concision": "none",
        "instruction": "Prefer the most detailed factual response the evidence supports. Be concrete, complete, and explicit about uncertainty.",
    }


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
    return [normalize_worker_definition({"id": worker_id}, model, provider) for worker_id in worker_slot_ids()]


def normalize_worker_definition(
    worker: Dict[str, Any],
    default_model: Optional[str] = None,
    default_provider: Optional[str] = None,
) -> Dict[str, str]:
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
    provider = normalize_provider_id(default_provider, infer_provider_from_model_id(default_model) or DEFAULT_PROVIDER_ID)
    fallback_model = normalize_model_id(default_model, default_model_for_provider(provider), provider)
    active_from_round = max(1, int(worker.get("activeFromRound", 1) or 1))
    return {
        "id": worker_id,
        "type": worker_type,
        "label": str(worker.get("label", catalog_worker["label"])).strip() or catalog_worker["label"],
        "role": str(worker.get("role", catalog_worker["role"])).strip() or catalog_worker["role"],
        "focus": str(worker.get("focus", catalog_worker["focus"])).strip() or catalog_worker["focus"],
        "temperature": normalize_worker_temperature(worker.get("temperature"), str(catalog_worker.get("temperature", "balanced"))),
        "model": normalize_model_id(worker.get("model"), fallback_model, provider),
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
                normalized = normalize_worker_definition(worker, default_model, default_provider)
                workers[normalized["id"]] = normalized
    if not workers:
        for worker in worker_catalog(default_model, default_provider)[:2]:
            normalized = normalize_worker_definition(worker, default_model, default_provider)
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


def coerce_confidence_value(value: Any) -> float:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"high", "strong", "confident"}:
            return 0.85
        if lowered in {"medium", "moderate", "mixed"}:
            return 0.6
        if lowered in {"low", "weak", "uncertain"}:
            return 0.35
        if lowered.endswith("%"):
            try:
                return max(0.0, min(1.0, float(lowered[:-1].strip()) / 100.0))
            except ValueError:
                return 0.0
    try:
        candidate = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if candidate > 1.0:
        candidate = candidate / 100.0 if candidate <= 100.0 else 1.0
    return max(0.0, min(1.0, candidate))


def compact_text_middle(value: Any, max_length: int = 3200) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    if max_length <= 240:
        return truncate_text(text, max_length)
    marker = "\n\n[... auto-compacted ...]\n\n"
    available = max_length - len(marker)
    if available <= 120:
        return truncate_text(text, max_length)
    head = max(80, int(available * 0.58))
    tail = max(40, available - head)
    return text[:head].rstrip() + marker + text[-tail:].lstrip()


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
    if concision == "none":
        return [f"Extra harness instruction: {config['instruction']}"] if config["instruction"] else []
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
    if concision == "none":
        return [f"Extra harness instruction: {config['instruction']}"] if config["instruction"] else []
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


def direct_baseline_harness_instruction_lines(harness: Any) -> List[str]:
    config = normalize_harness_config(harness, default_direct_harness()["concision"])
    concision = config["concision"]
    if concision == "none":
        return [f"Extra harness instruction: {config['instruction']}"] if config["instruction"] else []
    lines = [
        "Treat Objective as the authoritative current user input.",
        "Treat Session context as background only; if it conflicts with Objective or current evidence, Objective wins.",
        "Write as a structured, methodical, factual operator response rather than a casual chat reply.",
        "Make the recommendation explicit, then explain the reasoning and next action without filler.",
    ]
    if concision == "tight":
        lines.extend(
            [
                "Keep answer to at most 3 short paragraphs or 6 short bullets.",
                "Use short, high-signal sentences and skip scene-setting.",
                "Keep confidenceNote concise and concrete.",
            ]
        )
    elif concision == "balanced":
        lines.extend(
            [
                "Keep answer focused, but allow up to 5 compact paragraphs when the tradeoffs need unpacking.",
                "Prefer clear sections, factual qualifiers, and explicit operator next steps.",
                "Keep confidenceNote brief, but explain the main uncertainty or constraint.",
            ]
        )
    else:
        lines.extend(
            [
                "Use answer for substantive synthesis when the situation is dense, high-stakes, or operationally messy; up to 7 compact paragraphs is acceptable.",
                "Prefer a clear structure such as recommendation, reasoning, risks, and next steps.",
                "Be factual and methodical, and make conditional boundaries explicit instead of implied.",
                "Use confidenceNote to state the main confidence driver and the main unresolved risk.",
            ]
        )
    if config["instruction"]:
        lines.append(f"Extra harness instruction: {config['instruction']}")
    return lines


def commander_harness_instruction_lines(harness: Any) -> List[str]:
    config = normalize_harness_config(harness, default_summarizer_harness()["concision"])
    concision = config["concision"]
    if concision == "none":
        return [f"Extra harness instruction: {config['instruction']}"] if config["instruction"] else []
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
    answer_draft = str(summary.get("answerDraft", "") or "").strip()
    paragraphs: List[str] = []
    if stable_findings:
        paragraphs.append(" ".join(stable_findings))
    if conflict_topics:
        paragraphs.append("Remaining disagreement: " + "; ".join(conflict_topics) + ".")
    if recommended_next_action:
        paragraphs.append("Next step: " + recommended_next_action)
    stance = stable_findings[0] if stable_findings else (truncate_text(answer_draft, 260) or recommended_next_action or confidence_note)
    answer = "\n\n".join(paragraphs).strip() or answer_draft or stance
    return {
        "answer": answer or "No adjudicated answer was captured.",
        "stance": stance or "No adjudicated stance was captured.",
        "confidenceNote": confidence_note,
    }


_INTERNAL_PUBLIC_ANSWER_MARKER_PATTERNS = [
    re.compile(r"\bworker [a-z]\b", re.IGNORECASE),
    re.compile(r"\baccepted from worker [a-z]\b", re.IGNORECASE),
    re.compile(r"\bguardrail from worker [a-z]\b", re.IGNORECASE),
    re.compile(r"\bworker [a-z] pressure\b", re.IGNORECASE),
]


def find_internal_public_answer_markers(text: Any) -> List[str]:
    candidate = str(text or "").strip()
    if not candidate:
        return []
    matches: List[str] = []
    seen: Dict[str, bool] = {}
    for pattern in _INTERNAL_PUBLIC_ANSWER_MARKER_PATTERNS:
        for match in pattern.finditer(candidate):
            marker = match.group(0).strip()
            normalized = marker.lower()
            if marker and normalized not in seen:
                seen[normalized] = True
                matches.append(marker)
    return matches


def assert_public_answer_free_of_internal_provenance(text: Any, target_kind: str = "answer") -> None:
    markers = find_internal_public_answer_markers(text)
    if markers:
        raise RuntimeErrorWithCode(
            f"Model response leaked internal provenance markers into the public {target_kind}: {', '.join(markers)}",
            500,
        )


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
        answer = str(front_answer.get("answer", "") or "").strip()
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


def flatten_provider_text_fragments(value: Any, depth: int = 0, limit: int = 160) -> List[str]:
    if value is None or depth > 12 or limit <= 0:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        collected: List[str] = []
        for item in value:
            fragments = flatten_provider_text_fragments(item, depth + 1, limit - len(collected))
            for fragment in fragments:
                if fragment:
                    collected.append(fragment)
                if len(collected) >= limit:
                    return collected[:limit]
        return collected[:limit]
    if not isinstance(value, dict):
        return []

    block_type = str(value.get("type") or "").strip().lower()
    if block_type in {"thinking", "reasoning", "tool_use", "tool_result", "server_tool_use"}:
        return []

    collected: List[str] = []
    direct_text_keys = ("text", "content", "completion", "output_text", "answer", "value")
    for key in direct_text_keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            collected.append(candidate.strip())
            break

    container_keys = ("message", "content", "output", "messages", "parts", "items", "data", "result")
    for key in container_keys:
        candidate = value.get(key)
        fragments = flatten_provider_text_fragments(candidate, depth + 1, limit - len(collected))
        for fragment in fragments:
            if fragment and fragment not in collected:
                collected.append(fragment)
            if len(collected) >= limit:
                return collected[:limit]
    if not collected:
        for key, candidate in value.items():
            if key in direct_text_keys or key in container_keys or key == "type":
                continue
            fragments = flatten_provider_text_fragments(candidate, depth + 1, limit - len(collected))
            for fragment in fragments:
                if fragment and fragment not in collected:
                    collected.append(fragment)
                if len(collected) >= limit:
                    return collected[:limit]
    return collected[:limit]


def join_flattened_provider_text(value: Any, separator: str = "\n\n") -> str:
    fragments = flatten_provider_text_fragments(value)
    deduped: List[str] = []
    for fragment in fragments:
        cleaned = str(fragment or "").strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return separator.join(deduped).strip()


def strip_structured_output_prefix(text: str) -> str:
    raw = str(text or "").lstrip("\ufeff").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    for prefix in ("json\n", "json\r\n", "json:", "json -", "json only\n", "json only:\n"):
        if lowered.startswith(prefix):
            trimmed = raw[len(prefix):].strip()
            if trimmed:
                return trimmed
    return raw


def extract_balanced_json_object(text: str) -> str:
    objects = extract_balanced_json_objects(text, limit=1)
    return objects[0] if objects else ""


def extract_balanced_json_object_spans(text: str, limit: int = 32) -> List[Tuple[int, int, str]]:
    raw = str(text or "")
    if "{" not in raw:
        return []
    results: List[Tuple[int, int, str]] = []
    scanned_starts = 0
    max_starts = max(limit * 16, 64)
    for start, start_char in enumerate(raw):
        if start_char != "{":
            continue
        scanned_starts += 1
        if scanned_starts > max_starts and results:
            break
        if scanned_starts > 2048:
            break
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(raw)):
            char = raw[index]
            if in_string:
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
                continue
            if char == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start:index + 1].strip()
                    if candidate and all(candidate != existing[2] for existing in results):
                        results.append((start, index + 1, candidate))
                    break
        if len(results) >= limit:
            break
    return results


def extract_balanced_json_objects(text: str, limit: int = 32) -> List[str]:
    return [candidate for _start, _end, candidate in extract_balanced_json_object_spans(text, limit=limit)]


def escape_json_string_control_chars(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    repaired: List[str] = []
    in_string = False
    escape = False
    total = len(raw)
    for index, char in enumerate(raw):
        if in_string:
            if escape:
                repaired.append(char)
                escape = False
                continue
            if char == "\\":
                repaired.append(char)
                escape = True
                continue
            if char == '"':
                lookahead = ""
                for probe in range(index + 1, total):
                    candidate = raw[probe]
                    if candidate.isspace():
                        continue
                    lookahead = candidate
                    break
                if lookahead in {"", ",", "}", "]", ":"}:
                    repaired.append(char)
                    in_string = False
                else:
                    repaired.append('\\"')
                continue
            if char == "\n":
                repaired.append("\\n")
                continue
            if char == "\r":
                repaired.append("\\r")
                continue
            if char == "\t":
                repaired.append("\\t")
                continue
            if ord(char) < 0x20:
                repaired.append(f"\\u{ord(char):04x}")
                continue
            repaired.append(char)
            continue
        repaired.append(char)
        if char == '"':
            in_string = True
    return "".join(repaired)


def normalize_relaxed_json_text(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    normalized = (
        raw.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    normalized = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', normalized)
    normalized = re.sub(r",(\s*[}\]])", r"\1", normalized)
    return normalized


def parse_pythonish_object_text(text: str) -> Optional[Dict[str, Any]]:
    candidate = normalize_relaxed_json_text(text)
    if not candidate:
        return None
    pythonish = re.sub(r"\btrue\b", "True", candidate, flags=re.IGNORECASE)
    pythonish = re.sub(r"\bfalse\b", "False", pythonish, flags=re.IGNORECASE)
    pythonish = re.sub(r"\bnull\b", "None", pythonish, flags=re.IGNORECASE)
    try:
        parsed = ast.literal_eval(pythonish)
    except (SyntaxError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


STRUCTURED_OUTPUT_PAYLOAD_HINT_KEYS = {
    "answer",
    "answerDraft",
    "frontAnswer",
    "publicAnswer",
    "summarizerOpinion",
    "sourceWorkers",
    "workerId",
    "taskId",
    "round",
    "stance",
    "leadDirection",
    "confidenceNote",
    "controlAudit",
    "observation",
    "benefits",
    "detriments",
    "incident",
    "immediateActions",
    "decisionGates",
}
STRUCTURED_OUTPUT_SCHEMA_FRAGMENT_KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "description",
    "enum",
    "format",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
}
STRUCTURED_OUTPUT_JSON_SCHEMA_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


def looks_like_schema_echo(payload: Dict[str, Any]) -> bool:
    keys = {str(key) for key in payload.keys()}
    if not keys:
        return False
    if keys.isdisjoint(STRUCTURED_OUTPUT_PAYLOAD_HINT_KEYS) and keys.issubset(STRUCTURED_OUTPUT_SCHEMA_FRAGMENT_KEYS):
        return True
    type_value = str(payload.get("type") or "").strip().lower()
    if type_value in STRUCTURED_OUTPUT_JSON_SCHEMA_TYPES and keys.isdisjoint(STRUCTURED_OUTPUT_PAYLOAD_HINT_KEYS):
        return True
    non_empty_values = [value for value in payload.values() if value not in (None, "", [], {})]
    if keys.intersection(STRUCTURED_OUTPUT_PAYLOAD_HINT_KEYS) and non_empty_values:
        if all(looks_like_schema_fragment_value(value) for value in non_empty_values):
            return True
    return False


def looks_like_schema_fragment_value(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    keys = {str(key) for key in value.keys()}
    if not keys:
        return False
    type_value = str(value.get("type") or "").strip().lower()
    if type_value in STRUCTURED_OUTPUT_JSON_SCHEMA_TYPES and keys.issubset(STRUCTURED_OUTPUT_SCHEMA_FRAGMENT_KEYS):
        return True
    return looks_like_schema_echo(value)


def structured_output_payload_score(payload: Dict[str, Any]) -> int:
    if looks_like_schema_echo(payload):
        return -1000
    score = 0
    weights = {
        "frontAnswer": 20,
        "answer": 18,
        "publicAnswer": 18,
        "answerDraft": 16,
        "summarizerOpinion": 10,
        "workerId": 10,
        "taskId": 8,
        "round": 4,
        "stance": 4,
        "leadDirection": 6,
        "confidenceNote": 4,
        "controlAudit": 6,
        "observation": 5,
        "benefits": 5,
        "detriments": 5,
        "incident": 6,
        "immediateActions": 6,
        "decisionGates": 6,
        "scores": 10,
        "verdict": 8,
        "strongestStrength": 6,
        "strongestWeakness": 6,
        "strongestControlStrength": 6,
        "strongestControlWeakness": 6,
        "primaryEdge": 6,
        "baselineEdge": 6,
        "decisionRelation": 6,
        "rationale": 8,
    }
    for key, weight in weights.items():
        if key in payload and payload.get(key) not in (None, "", [], {}):
            score += weight
    score += structured_output_content_quality_score(payload)
    score += min(len(payload), 12)
    return score


def structured_output_content_quality_score(payload: Dict[str, Any]) -> int:
    text_parts: List[str] = []
    for key in (
        "answer",
        "answerDraft",
        "publicAnswer",
        "leadDirection",
        "stance",
        "confidenceNote",
        "verdict",
        "strongestStrength",
        "strongestWeakness",
        "strongestControlStrength",
        "strongestControlWeakness",
        "primaryEdge",
        "baselineEdge",
        "rationale",
    ):
        value = payload.get(key)
        if isinstance(value, str):
            text_parts.append(value)
    front_answer = payload.get("frontAnswer")
    if isinstance(front_answer, dict):
        nested_answer = front_answer.get("answer")
        if isinstance(nested_answer, str):
            text_parts.append(nested_answer)
    joined = "\n".join(text_parts).strip()
    if not joined:
        return 0
    compact = re.sub(r"[\s.…_-]+", "", joined)
    if not compact:
        return -250
    score = min(len(joined) // 80, 60)
    if len(joined) >= 240:
        score += 10
    return score


def parse_structured_output_text(output_text: str) -> Dict[str, Any]:
    raw = strip_structured_output_prefix(output_text)
    def parse_error(message: str, failure_kind: str = "malformed_json") -> RuntimeErrorWithCode:
        error = RuntimeErrorWithCode(message, 500)
        error.raw_output_text = str(output_text or "")
        error.failure_kind = failure_kind
        return error

    if not raw:
        raise parse_error("Model response JSON parse failed: empty output.", "empty_output")
    candidates: List[str] = [raw]
    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    for block in fenced_blocks:
        cleaned = strip_structured_output_prefix(block)
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
    balanced_spans = extract_balanced_json_object_spans(raw)
    leading_offset = len(raw) - len(raw.lstrip())
    raw_starts_as_object = raw.lstrip().startswith("{")
    has_top_level_span = any(start == leading_offset for start, _end, _candidate in balanced_spans)
    for start, _end, balanced_object in balanced_spans:
        if raw_starts_as_object and not has_top_level_span and start > leading_offset:
            continue
        if balanced_object and balanced_object not in candidates:
            candidates.append(balanced_object)
    for candidate in list(candidates):
        repaired = escape_json_string_control_chars(candidate)
        if repaired and repaired not in candidates:
            candidates.append(repaired)
        relaxed = normalize_relaxed_json_text(candidate)
        if relaxed and relaxed not in candidates:
            candidates.append(relaxed)
    last_error: Optional[json.JSONDecodeError] = None
    parsed_candidates: List[Tuple[int, int, Dict[str, Any]]] = []
    saw_non_object = False
    saw_schema_echo = False
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as error:
            last_error = error
            parsed = parse_pythonish_object_text(candidate)
            if parsed is None:
                continue
        if not isinstance(parsed, dict):
            saw_non_object = True
            continue
        score = structured_output_payload_score(parsed)
        if score <= -1000:
            saw_schema_echo = True
            continue
        parsed_candidates.append((score, -len(parsed_candidates), parsed))
    if parsed_candidates:
        parsed_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return parsed_candidates[0][2]
    if saw_schema_echo:
        raise parse_error("Model response JSON parse failed: response contained schema echo but no payload object.")
    if saw_non_object:
        raise parse_error("Model response JSON parse failed: expected object output.")
    if last_error is not None:
        raise parse_error(f"Model response JSON parse failed: {last_error}")
    raise parse_error("Model response JSON parse failed: expected object output.")


def looks_like_incomplete_structured_output(output_text: Any) -> bool:
    raw = str(output_text or "").strip()
    if not raw:
        return False
    depth = 0
    in_string = False
    escape = False
    saw_container = False
    for char in raw:
        if in_string:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            saw_container = True
            depth += 1
            continue
        if char in "}]":
            depth -= 1
            continue
    if not saw_container:
        return False
    if in_string or depth > 0:
        return True
    tail = raw[-80:].rstrip()
    return tail.endswith((':', ',', '\\'))


def schema_looks_like_direct_answer(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    required = schema.get("required")
    if not isinstance(required, list):
        return False
    required_names = {str(item or "").strip() for item in required}
    return {"answer", "stance", "confidenceNote"}.issubset(required_names)


def salvage_direct_answer_payload(provider: Any, raw_output_text: Any) -> Optional[Dict[str, str]]:
    normalized = provider_responses.normalize_provider_response(provider, raw_output_text)
    answer = str(normalized.get("answer") or "").strip()
    if not answer:
        return None
    stance = truncate_text(normalized.get("stance"), 260) or truncate_text(answer, 260) or "No explicit stance was captured."
    confidence_note = (
        truncate_text(normalized.get("confidenceNote"), 320)
        or f"Recovered from {normalize_provider_id(provider, DEFAULT_PROVIDER_ID)} response normalization after schema drift."
    )
    return {
        "answer": answer,
        "stance": stance,
        "confidenceNote": confidence_note,
    }


def flatten_output_payload_text(payload: Any, artifact_type: str = "", provider_hint: Any = "") -> str:
    normalized_type = str(artifact_type or "").strip().lower()
    if isinstance(payload, dict):
        provider = str(
            payload.get("provider")
            or payload.get("providerName")
            or payload.get("providerHint")
            or provider_hint
            or ""
        ).strip()
        raw_candidates = [
            payload.get("rawOutputText"),
            payload.get("rawProviderResponse"),
            payload.get("rawResponse"),
            payload.get("outputText"),
            payload.get("responseText"),
        ]
        if provider:
            for raw_candidate in raw_candidates:
                normalized_answer = str(provider_responses.extract_normalized_provider_answer(provider, raw_candidate) or "").strip()
                if normalized_answer:
                    return normalized_answer
        front_answer = payload.get("frontAnswer")
        if isinstance(front_answer, dict):
            front_text = str(front_answer.get("answer", "") or "").strip()
            if front_text:
                return front_text
        answer = payload.get("answer")
        if isinstance(answer, dict):
            answer_text = str(answer.get("answer", "") or "").strip()
            if answer_text:
                return answer_text
        if normalized_type in {"commander_output", "commander_review_output", "summary_output", "summary_partial_output"}:
            answer_draft = str(payload.get("answerDraft", "") or "").strip()
            if answer_draft:
                return answer_draft
        if normalized_type in {"worker_output", "worker_step"}:
            observation = str(payload.get("observation", "") or "").strip()
            if observation:
                return observation
            request_to_peer = str(payload.get("requestToPeer", "") or "").strip()
            if request_to_peer:
                return request_to_peer
    return join_flattened_provider_text(payload)


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
        "answerDraft": truncate_text(base_commander.get("answerDraft", ""), 3200) or "No reviewed answer draft was captured.",
        "whyThisDirection": (
            truncate_text(base_commander.get("whyThisDirection", ""), 360)
            or "No commander reevaluation rationale was captured."
        ),
        "controlAudit": {},
        "dynamicLaneDecision": normalize_dynamic_lane_decision(None),
        "dynamicLaneResolution": normalize_dynamic_lane_resolution(None),
        "claimsToStrengthen": [],
        "claimsToLimit": [],
        "requiredDecisionGates": [],
        "evidenceOrCommsRisks": [],
        "discardedPressure": [],
        "remainingUncertainty": limit_string_list(base_commander.get("uncertainty", []), 4, 220),
        "sourceWorkers": normalize_worker_id_list(fallback_workers or []),
    }
    if isinstance(checkpoint, dict):
        normalized["taskId"] = str(checkpoint.get("taskId", normalized["taskId"]))
        normalized["round"] = max(1, int(fallback_round or normalized["round"]))
        stance = truncate_text(checkpoint.get("stance", ""), 260)
        lead_direction = truncate_text(checkpoint.get("leadDirection", ""), 280)
        answer_draft = truncate_text(checkpoint.get("answerDraft", ""), 3200)
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
        normalized["claimsToStrengthen"] = limit_string_list(checkpoint.get("claimsToStrengthen", []), 4, 220)
        normalized["claimsToLimit"] = limit_string_list(checkpoint.get("claimsToLimit", []), 4, 220)
        normalized["requiredDecisionGates"] = limit_string_list(checkpoint.get("requiredDecisionGates", []), 4, 220)
        normalized["evidenceOrCommsRisks"] = limit_string_list(checkpoint.get("evidenceOrCommsRisks", []), 4, 220)
        normalized["discardedPressure"] = limit_string_list(checkpoint.get("discardedPressure", []), 4, 220)
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


MSP_CONTRADICTION_GATE_TRIGGERS = {
    "msp",
    "mssp",
    "tenant",
    "customer",
    "client",
    "rmm",
    "psa",
    "backup",
    "restore",
    "deletion",
    "identity",
    "oauth",
    "mfa",
    "azure",
    "soc",
    "service desk",
    "vendor",
    "portal",
    "control plane",
}


MSP_FINAL_ANSWER_GATES = [
    {
        "id": "msp-tenant-ownership",
        "title": "Tenant record ownership",
        "requirement": "Open one internal major-incident record with an evidence-compatible decision log plus a named owner for every affected tenant child record.",
        "matchAny": ["named owner", "owner per affected tenant", "owner for every affected tenant", "tenant child record", "child record", "decision log", "log all decisions"],
        "triggers": ["tenant", "customer", "client", "msp", "backup", "restore", "rmm", "psa", "identity", "oauth", "azure"],
        "source": "msp-provider-sop",
    },
    {
        "id": "msp-evidence-before-cleanup",
        "title": "Evidence before destructive action",
        "requirement": "Preserve/export per-tenant evidence before cleanup, cancellation, deletion, or restore-impacting action unless an emergency exception is owned and logged.",
        "matchAny": ["evidence before", "preserve evidence", "export evidence", "export logs", "chain-of-custody", "chain of custody"],
        "triggers": ["backup", "restore", "deletion", "rmm", "psa", "identity", "oauth", "incident", "compromise"],
        "source": "msp-provider-sop",
    },
    {
        "id": "msp-control-plane-distrust",
        "title": "Control-plane skepticism",
        "requirement": "Treat the affected RMM, PSA, backup, identity, vendor, or portal control plane as suspect until validated out of band.",
        "matchAny": ["out-of-band", "out of band", "independent validation", "do not trust", "treat the control plane as suspect", "portal as suspect"],
        "triggers": ["rmm", "psa", "backup", "restore", "identity", "oauth", "vendor", "portal", "control plane"],
        "source": "msp-provider-sop",
    },
    {
        "id": "msp-tenant-safe-communications",
        "title": "Tenant-safe communications",
        "requirement": "Keep customer communications tenant-specific and do not reveal other affected customers unless legal/customer authority explicitly allows it.",
        "matchAny": ["tenant-specific", "customer-specific", "per-tenant", "per customer", "do not reveal other affected customers", "separate customer"],
        "triggers": ["tenant", "customer", "client", "msp", "multi-tenant", "incident", "communications"],
        "source": "msp-provider-sop",
    },
    {
        "id": "msp-continuity-authority-gate",
        "title": "Continuity and authority gate",
        "requirement": "Map medical/logistics/24x7 continuity commitments and get the named customer/internal authority before disruptive containment or restore changes.",
        "matchAny": ["continuity", "24/7", "24x7", "medical", "logistics", "customer authority", "approval before disruptive"],
        "triggers": ["24/7", "24x7", "medical", "logistics", "restore", "backup", "disruptive", "outage"],
        "source": "msp-provider-sop",
    },
    {
        "id": "msp-vendor-escalation",
        "title": "Vendor and senior escalation",
        "requirement": "Escalate to the vendor, senior incident owner, legal, or compliance track when hosted control-plane, credential, evidence, or multi-tenant risk is involved.",
        "matchAny": ["vendor escalation", "escalate to the vendor", "senior incident", "legal", "compliance", "hosted control-plane"],
        "triggers": ["vendor", "portal", "control plane", "backup", "restore", "identity", "oauth", "multi-tenant"],
        "source": "msp-provider-sop",
    },
]


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
    provider_trace: Optional[Dict[str, Any]] = None


PROVIDER_TRACE_STAGE_LABELS: Dict[str, str] = {
    "sending": "Sending request",
    "headers": "Headers received",
    "retrying": "Retrying request",
    "completed": "Completed",
    "error": "Provider error",
    "timeout": "Timed out",
}


def provider_trace_target_label(target: Any) -> str:
    normalized = str(target or "").strip().lower()
    worker_match = re.match(r"^worker[_:-]?([a-z0-9]+)$", normalized)
    if worker_match:
        return f"Worker {worker_match.group(1).upper()}"
    if normalized == "commander":
        return "Commander"
    if normalized == "direct_baseline":
        return "Direct baseline"
    if normalized == "commander_review":
        return "Commander review"
    if normalized == "summarizer":
        return "Summarizer"
    if normalized == "answer_now":
        return "Answer now"
    if normalized == "arbiter":
        return "External arbiter"
    if len(normalized) == 1 and normalized.isalpha():
        return f"Worker {normalized.upper()}"
    return normalized or "Target"


def node_target_from_schema_or_target(schema_name: Any, target: Any) -> str:
    schema_text = str(schema_name or "").strip().lower()
    schema_match = re.match(r"^worker[_:-]?([a-z0-9]+)[_:-]checkpoint$", schema_text)
    if schema_match:
        return f"worker_{schema_match.group(1).upper()}"
    normalized = normalize_auth_target(target)
    if len(normalized) == 1 and normalized.isalpha():
        return f"worker_{normalized.upper()}"
    return normalized


class LoopRuntime:
    def __init__(self, root: str | Path, auth_path: str | Path | None = None) -> None:
        self.root = Path(root).resolve()
        self.data_path = self.root / "data"
        self.tasks_path = self.data_path / "tasks"
        self.task_states_path = self.data_path / "task_states"
        self.checkpoints_path = self.data_path / "checkpoints"
        self.outputs_path = self.data_path / "outputs"
        self.failed_calls_path = self.data_path / "failed_calls"
        self.handoffs_path = self.data_path / "handoffs"
        self.node_transfers_path = self.data_path / "node_transfers"
        self.sessions_path = self.data_path / "sessions"
        self.jobs_path = self.data_path / "jobs"
        self.locks_path = self.data_path / "locks"
        self.state_path = self.data_path / "state.json"
        self.events_path = self.data_path / "events.jsonl"
        self.steps_path = self.data_path / "steps.jsonl"
        self.auth_path = Path(auth_path).resolve() if auth_path else (self.root / "Auth.txt")
        self.config_root = self.auth_path.parent.resolve() if auth_path else self.root
        self._current_execution_context: Dict[str, Any] = {}

    def ensure_data_paths(self) -> None:
        for path in (
            self.data_path,
            self.tasks_path,
            self.task_states_path,
            self.checkpoints_path,
            self.outputs_path,
            self.failed_calls_path,
            self.handoffs_path,
            self.node_transfers_path,
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
        path.parent.mkdir(parents=True, exist_ok=True)
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

    def _scoped_task_state_id(self) -> Optional[str]:
        task_id = str(self._current_execution_context.get("stateScopeTaskId") or "").strip()
        return task_id or None

    def _task_state_path(self, task_id: str) -> Path:
        return self.task_states_path / f"{str(task_id or '').strip()}.json"

    def read_task_snapshot_unlocked(self, task_id: str) -> Optional[Dict[str, Any]]:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return None
        if metadata_store.postgres_enabled(self.root):
            data = metadata_store.read_task_payload(self.root, normalized_task_id)
            return data if isinstance(data, dict) else None
        data = self._read_json_file(self.tasks_path / f"{normalized_task_id}.json", None)
        return data if isinstance(data, dict) else None

    def initialize_task_state_unlocked(self, task: Dict[str, Any], seed_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        task_id = str(task.get("taskId") or "").strip()
        if not task_id:
            raise RuntimeErrorWithCode("Task payload is missing taskId.", 500)
        base = self.normalize_state(seed_state if isinstance(seed_state, dict) else default_state())
        base["activeTask"] = task
        normalized = self.normalize_state(base)
        self._write_json_file(self._task_state_path(task_id), normalized)
        return normalized

    def read_task_state_unlocked(self, task_id: str, bootstrap: bool = True) -> Dict[str, Any]:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return self.normalize_state(default_state())
        path = self._task_state_path(normalized_task_id)
        data = self._read_json_file(path, None)
        if isinstance(data, dict):
            return self.normalize_state(data)
        if bootstrap:
            task = self.read_task_snapshot_unlocked(normalized_task_id)
            if isinstance(task, dict):
                return self.initialize_task_state_unlocked(task)
        return self.normalize_state(default_state())

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
        scoped_task_id = self._scoped_task_state_id()
        if scoped_task_id:
            return self.read_task_state_unlocked(scoped_task_id)
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
        scoped_task_id = self._scoped_task_state_id()
        if scoped_task_id:
            self._write_json_file(self._task_state_path(scoped_task_id), normalized)
            active_task = normalized.get("activeTask")
            if isinstance(active_task, dict) and str(active_task.get("taskId") or "").strip() == scoped_task_id:
                self.write_task_snapshot_unlocked(active_task)
            return normalized
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

    def set_execution_context(self, context: Optional[Dict[str, Any]]) -> None:
        self._current_execution_context = dict(context or {})

    def clear_execution_context(self) -> None:
        self._current_execution_context = {}

    def current_execution_context(self) -> Dict[str, Any]:
        return dict(self._current_execution_context)

    def execution_cancelled_reason(self) -> Optional[str]:
        context = self.current_execution_context()
        dispatch_job_id = str(context.get("dispatchJobId") or "").strip()
        loop_job_id = str(context.get("loopJobId") or "").strip()
        with self.with_lock():
            if dispatch_job_id:
                dispatch_job = self.read_job_unlocked(dispatch_job_id)
                if isinstance(dispatch_job, dict):
                    dispatch_status = str(dispatch_job.get("status") or "").strip().lower()
                    if bool(dispatch_job.get("cancelRequested")) or dispatch_status == "cancelled":
                        return EXECUTION_CANCELLED_MESSAGE
            if loop_job_id:
                loop_job = self.read_job_unlocked(loop_job_id)
                if isinstance(loop_job, dict):
                    loop_status = str(loop_job.get("status") or "").strip().lower()
                    if bool(loop_job.get("cancelRequested")) or loop_status == "cancelled":
                        return EXECUTION_CANCELLED_MESSAGE
        return None

    def execution_cancelled(self) -> bool:
        return bool(self.execution_cancelled_reason())

    def assert_execution_not_cancelled(self) -> None:
        reason = self.execution_cancelled_reason()
        if reason:
            raise RuntimeErrorWithCode(reason, 409)

    def current_trace_target(self, fallback: str = "generic") -> str:
        context = self.current_execution_context()
        candidate = str(context.get("traceTarget") or context.get("target") or fallback).strip()
        return candidate or fallback

    def normalize_provider_trace(self, trace: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(trace, dict):
            return None
        normalized: Dict[str, Any] = {}
        for key, value in trace.items():
            field = str(key or "").strip()
            if not field:
                continue
            if value is None or isinstance(value, (str, int, float, bool)):
                normalized[field] = value
                continue
            if isinstance(value, list):
                normalized[field] = [
                    item
                    for item in value
                    if item is None or isinstance(item, (str, int, float, bool))
                ][:20]
                continue
            if isinstance(value, dict):
                child: Dict[str, Any] = {}
                for child_key, child_value in value.items():
                    child_field = str(child_key or "").strip()
                    if not child_field:
                        continue
                    if child_value is None or isinstance(child_value, (str, int, float, bool)):
                        child[child_field] = child_value
                normalized[field] = child
        return normalized or None

    def provider_trace_header_map(self, response: Any) -> Dict[str, str]:
        headers_node = None
        if hasattr(response, "headers"):
            headers_node = getattr(response, "headers")
        elif hasattr(response, "info"):
            try:
                headers_node = response.info()
            except Exception:  # noqa: BLE001
                headers_node = None
        headers: Dict[str, str] = {}
        if headers_node is None:
            return headers
        try:
            items = headers_node.items()
        except Exception:  # noqa: BLE001
            return headers
        for key, value in items:
            name = str(key or "").strip().lower()
            if not name:
                continue
            headers[name] = str(value or "").strip()
        return headers

    def provider_trace_header_value(self, headers: Dict[str, str], *names: str) -> str:
        for name in names:
            value = str(headers.get(str(name or "").strip().lower()) or "").strip()
            if value:
                return value
        return ""

    def provider_trace_int(self, value: Any) -> Optional[int]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None

    def provider_trace_ms_from_ns(self, value: Any) -> Optional[int]:
        parsed = self.provider_trace_int(value)
        if parsed is None:
            return None
        return max(0, int(parsed / 1_000_000))

    def build_provider_trace_base(
        self,
        provider: str,
        model: str,
        target_kind: str,
        request_timeout_seconds: int,
    ) -> Dict[str, Any]:
        trace_target = self.current_trace_target(target_kind)
        normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
        return {
            "target": trace_target,
            "targetLabel": provider_trace_target_label(trace_target),
            "provider": normalized_provider,
            "providerLabel": PROVIDER_CATALOG.get(normalized_provider, {}).get("label") or normalized_provider.title(),
            "model": str(model or "").strip(),
            "stage": "sending",
            "stageLabel": PROVIDER_TRACE_STAGE_LABELS["sending"],
            "requestTimeoutSeconds": max(1, int(request_timeout_seconds or 0)),
            "requestCount": 0,
            "startedAt": utc_now(),
            "updatedAt": utc_now(),
        }

    def provider_trace_from_headers(self, provider: str, headers: Dict[str, str]) -> Dict[str, Any]:
        normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
        trace: Dict[str, Any] = {}
        request_id = self.provider_trace_header_value(headers, "x-request-id", "request-id")
        if request_id:
            trace["providerRequestId"] = request_id
        processing_ms = self.provider_trace_int(self.provider_trace_header_value(headers, "openai-processing-ms"))
        if processing_ms is not None:
            trace["providerProcessingMs"] = processing_ms
        remaining_requests = self.provider_trace_int(
            self.provider_trace_header_value(
                headers,
                "x-ratelimit-remaining-requests",
                "anthropic-ratelimit-requests-remaining",
            )
        )
        if remaining_requests is not None:
            trace["rateLimitRequestsRemaining"] = remaining_requests
        remaining_tokens = self.provider_trace_int(
            self.provider_trace_header_value(
                headers,
                "x-ratelimit-remaining-tokens",
                "anthropic-ratelimit-tokens-remaining",
            )
        )
        if remaining_tokens is not None:
            trace["rateLimitTokensRemaining"] = remaining_tokens
        remaining_input_tokens = self.provider_trace_int(
            self.provider_trace_header_value(headers, "anthropic-ratelimit-input-tokens-remaining")
        )
        if remaining_input_tokens is not None:
            trace["rateLimitInputTokensRemaining"] = remaining_input_tokens
        remaining_output_tokens = self.provider_trace_int(
            self.provider_trace_header_value(headers, "anthropic-ratelimit-output-tokens-remaining")
        )
        if remaining_output_tokens is not None:
            trace["rateLimitOutputTokensRemaining"] = remaining_output_tokens
        retry_after = self.provider_trace_int(self.provider_trace_header_value(headers, "retry-after"))
        if retry_after is not None:
            trace["retryAfterSeconds"] = retry_after
        if normalized_provider == "ollama":
            server = self.provider_trace_header_value(headers, "server")
            if server:
                trace["providerServer"] = server
        return trace

    def provider_trace_message(self, trace: Dict[str, Any]) -> str:
        provider_label = str(trace.get("providerLabel") or trace.get("provider") or "Provider").strip()
        target_label = str(trace.get("targetLabel") or trace.get("target") or "target").strip()
        stage_label = str(trace.get("stageLabel") or trace.get("stage") or "in flight").strip()
        parts = [provider_label, target_label, stage_label]
        request_id = str(trace.get("providerRequestId") or "").strip()
        if request_id:
            parts.append("request " + truncate_text(request_id, 32))
        error = str(trace.get("error") or "").strip()
        if error:
            parts.append(truncate_text(error, 120))
        return " | ".join(part for part in parts if part)

    def update_provider_trace(self, trace: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        normalized = self.normalize_provider_trace(trace)
        if normalized is None:
            return None
        if self.execution_cancelled():
            return normalized
        normalized["updatedAt"] = utc_now()
        message = self.provider_trace_message(normalized)
        context = self.current_execution_context()
        task_id = str(context.get("taskId") or "").strip()
        dispatch_job_id = str(context.get("dispatchJobId") or "").strip()

        with self.with_lock():
            if dispatch_job_id:
                existing_job = self.read_job_unlocked(dispatch_job_id)
                if isinstance(existing_job, dict):
                    metadata = dict(existing_job.get("metadata") or {}) if isinstance(existing_job.get("metadata"), dict) else {}
                    metadata["providerTrace"] = normalized
                    self.write_job_unlocked(
                        storage.default_job(
                            {
                                **existing_job,
                                "metadata": metadata,
                                "lastHeartbeatAt": utc_now(),
                                "lastMessage": message,
                            }
                        )
                    )
                return normalized

            state = self.read_state_unlocked()
            active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
            active_task_id = str((active_task or {}).get("taskId") or "").strip()
            if task_id and active_task_id and task_id == active_task_id:
                loop = dict(storage.default_loop_state(), **(state.get("loop") if isinstance(state.get("loop"), dict) else {}))
                loop["providerTrace"] = normalized
                loop["lastHeartbeatAt"] = utc_now()
                loop["lastMessage"] = message
                state["loop"] = loop
                self.write_state_unlocked(state)
                loop_job_id = str(loop.get("jobId") or "").strip()
                if loop_job_id:
                    existing_job = self.read_job_unlocked(loop_job_id)
                    if isinstance(existing_job, dict):
                        metadata = dict(existing_job.get("metadata") or {}) if isinstance(existing_job.get("metadata"), dict) else {}
                        metadata["providerTrace"] = normalized
                        self.write_job_unlocked(
                            storage.default_job(
                                {
                                    **existing_job,
                                    "metadata": metadata,
                                    "lastHeartbeatAt": utc_now(),
                                }
                            )
                        )
        return normalized

    def clear_provider_trace(self) -> None:
        context = self.current_execution_context()
        task_id = str(context.get("taskId") or "").strip()
        dispatch_job_id = str(context.get("dispatchJobId") or "").strip()

        with self.with_lock():
            if dispatch_job_id:
                existing_job = self.read_job_unlocked(dispatch_job_id)
                if isinstance(existing_job, dict):
                    metadata = dict(existing_job.get("metadata") or {}) if isinstance(existing_job.get("metadata"), dict) else {}
                    metadata.pop("providerTrace", None)
                    self.write_job_unlocked(storage.default_job({**existing_job, "metadata": metadata}))
                return

            state = self.read_state_unlocked()
            active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else None
            active_task_id = str((active_task or {}).get("taskId") or "").strip()
            if task_id and active_task_id and task_id == active_task_id:
                loop = dict(storage.default_loop_state(), **(state.get("loop") if isinstance(state.get("loop"), dict) else {}))
                loop["providerTrace"] = None
                state["loop"] = loop
                self.write_state_unlocked(state)
                loop_job_id = str(loop.get("jobId") or "").strip()
                if loop_job_id:
                    existing_job = self.read_job_unlocked(loop_job_id)
                    if isinstance(existing_job, dict):
                        metadata = dict(existing_job.get("metadata") or {}) if isinstance(existing_job.get("metadata"), dict) else {}
                        metadata.pop("providerTrace", None)
                        self.write_job_unlocked(storage.default_job({**existing_job, "metadata": metadata}))

    def normalize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = default_state()
        normalized["activeTask"] = state.get("activeTask")
        normalized["draft"] = state.get("draft") if isinstance(state.get("draft"), dict) else normalized["draft"]
        normalized["commander"] = state.get("commander") if isinstance(state.get("commander"), dict) else None
        normalized["commanderReview"] = state.get("commanderReview") if isinstance(state.get("commanderReview"), dict) else None
        normalized["summary"] = state.get("summary")
        normalized["directBaseline"] = state.get("directBaseline") if isinstance(state.get("directBaseline"), dict) else None
        normalized["arbiter"] = state.get("arbiter") if isinstance(state.get("arbiter"), dict) else None
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

    def get_api_key(self, provider: Any = "openai") -> Optional[str]:
        assignment = self.get_api_key_assignment(provider=provider)
        return str(assignment.get("apiKey")) if assignment else None

    def load_api_keys(self, provider: Any = "openai") -> List[str]:
        return self.load_api_key_pool_state(provider)["keys"]

    def load_api_key_pool_state(self, provider: Any = "openai") -> Dict[str, Any]:
        normalized_provider = normalize_auth_key_provider(provider)
        label = auth_key_provider_label(normalized_provider)
        topology = deployment_topology(self.config_root)
        backend_resolution = resolve_provider_secret_backend(self.config_root, normalized_provider)
        backend_mode = backend_resolution["mode"]
        backend = backend_resolution["backend"]
        if backend == "env":
            status = env_secret_status(normalized_provider)
            return {
                "backend": "env",
                "selectedMode": backend_mode,
                "selectedModeLabel": auth_backend_mode_label(backend_mode),
                "safeBackend": preferred_safe_secret_backend(self.config_root),
                "provider": normalized_provider,
                "label": label,
                "keys": normalize_string_array_preserve_items(status.get("keys", [])),
                "managed": True,
                "writable": False,
                "configured": bool(status.get("configured")),
                "ready": bool(status.get("ready")),
                "failureMode": status.get("failureMode"),
                "failureDetail": str(status.get("detail") or ""),
            }
        if backend == "external":
            status = external_secret_status(self.root, provider=normalized_provider)
            return {
                "backend": "external",
                "selectedMode": backend_mode,
                "selectedModeLabel": auth_backend_mode_label(backend_mode),
                "safeBackend": preferred_safe_secret_backend(self.config_root),
                "provider": normalized_provider,
                "label": label,
                "keys": normalize_string_array_preserve_items(status.get("keys", [])),
                "managed": True,
                "writable": False,
                "configured": bool(status.get("configured")),
                "ready": bool(status.get("ready")),
                "failureMode": status.get("failureMode"),
                "failureDetail": str(status.get("detail") or ""),
            }
        if backend == "docker_secret":
            secret_base_path = topology.secret_file if topology.secret_file is not None else self.auth_path
            secret_path = auth_key_file_path(secret_base_path, normalized_provider)
            if not secret_path.is_file():
                return {
                    "backend": "docker_secret",
                    "selectedMode": backend_mode,
                    "selectedModeLabel": auth_backend_mode_label(backend_mode),
                    "safeBackend": preferred_safe_secret_backend(self.config_root),
                    "provider": normalized_provider,
                    "label": label,
                    "keys": [],
                    "managed": True,
                    "writable": False,
                    "configured": bool(secret_path),
                    "ready": False,
                    "failureMode": "misconfigured",
                    "failureDetail": f"Mounted {label} secret file not found at {secret_path}.",
                }
            keys = normalize_string_array_preserve_items(secret_path.read_text(encoding="utf-8", errors="replace").splitlines())
            return {
                "backend": "docker_secret",
                "selectedMode": backend_mode,
                "selectedModeLabel": auth_backend_mode_label(backend_mode),
                "safeBackend": preferred_safe_secret_backend(self.config_root),
                "provider": normalized_provider,
                "label": label,
                "keys": keys,
                "managed": True,
                "writable": False,
                "configured": True,
                "ready": len(keys) > 0,
                "failureMode": None if keys else "empty",
                "failureDetail": f"Using mounted {label} secret file at {secret_path}." if keys else f"Mounted {label} secret file at {secret_path} is empty.",
            }
        local_path = Path(topology.auth_file).resolve() if topology.auth_file is not None else (self.root / "Auth.txt")
        keys = normalize_string_array_preserve_items(read_local_auth_keys(local_path, normalized_provider))
        if not local_path.is_file() and not keys:
            return {
                "backend": "local_file",
                "selectedMode": backend_mode,
                "selectedModeLabel": auth_backend_mode_label(backend_mode),
                "safeBackend": preferred_safe_secret_backend(self.config_root),
                "provider": normalized_provider,
                "label": label,
                "keys": [],
                "managed": False,
                "writable": True,
                "configured": True,
                "ready": False,
                "failureMode": "empty",
                "failureDetail": f"Local fallback {label} secret file not found at {local_path}.",
            }
        return {
            "backend": "local_file",
            "selectedMode": backend_mode,
            "selectedModeLabel": auth_backend_mode_label(backend_mode),
            "safeBackend": preferred_safe_secret_backend(self.config_root),
            "provider": normalized_provider,
            "label": label,
            "keys": keys,
            "managed": False,
            "writable": True,
            "configured": True,
            "ready": len(keys) > 0,
            "failureMode": None if keys else "empty",
            "failureDetail": f"Using local fallback {label} secret file at {local_path}." if keys else f"Local fallback {label} secret file at {local_path} is empty.",
        }

    def raise_if_managed_secret_backend_unavailable(
        self,
        stage: str,
        task_id: str,
        model: str,
        target: str,
        provider: Any = "openai",
    ) -> None:
        normalized_provider = normalize_auth_key_provider(provider)
        auth_state = self.load_api_key_pool_state(normalized_provider)
        if not bool(auth_state.get("managed")) or auth_state.get("keys"):
            return
        failure_mode = str(auth_state.get("failureMode") or "empty")
        detail = str(auth_state.get("failureDetail") or f"{auth_state.get('backend')} returned no usable keys.")
        self.append_step(
            stage,
            "Managed secret backend is unavailable; refusing synthetic fallback for live execution.",
            {
                "taskId": task_id,
                "target": target,
                "model": model,
                "secretBackend": auth_state.get("backend"),
                "provider": normalized_provider,
                "failureMode": failure_mode,
                "failureDetail": detail,
            },
        )
        status_code = 503 if failure_mode in {"misconfigured", "unreachable"} else 409
        raise RuntimeErrorWithCode(
            f"Live run requires {auth_key_provider_label(normalized_provider)} keys from the {auth_state.get('backend')} secret backend, but it is {failure_mode}: {detail}",
            status_code,
        )

    def build_api_key_assignments(
        self,
        target: str = "generic",
        task: Optional[Dict[str, Any]] = None,
        round_number: Optional[int] = None,
        salt: str = "",
        provider: Any = "openai",
    ) -> List[Dict[str, Any]]:
        normalized_provider = normalize_auth_key_provider(provider)
        keys = self.load_api_keys(normalized_provider)
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
                    "provider": normalized_provider,
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
        provider: Any = "openai",
    ) -> Optional[Dict[str, Any]]:
        assignments = self.build_api_key_assignments(target, task, round_number, salt, provider)
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

    def timeout_provider_for_target(self, task: Dict[str, Any], target: Optional[str] = None) -> str:
        normalized_target = normalize_auth_target(target)
        runtime_config = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        provider = normalize_provider_id(runtime_config.get("provider"), DEFAULT_PROVIDER_ID)
        if normalized_target == "direct_baseline":
            return normalize_provider_id(runtime_config.get("directProvider"), provider)
        if normalized_target in {"summarizer", "answer_now"}:
            summarizer = task.get("summarizer") if isinstance(task.get("summarizer"), dict) else {}
            return normalize_provider_id(summarizer.get("provider"), provider)
        if normalized_target == "arbiter":
            return "openai"
        return provider

    def get_target_timeout_config(self, task: Dict[str, Any], target: Optional[str] = None) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        timeout_mode = normalize_timeout_mode(task_runtime.get("timeoutMode"), default_timeout_mode())
        manual = normalize_target_timeout_config(
            task_runtime.get("targetTimeouts") if isinstance(task_runtime.get("targetTimeouts"), dict) else {}
        )
        if timeout_mode == "user":
            return manual
        if timeout_mode == "auto":
            provider = self.timeout_provider_for_target(task, target)
            profile = normalize_ollama_timeout_profile(
                task_runtime.get("ollamaTimeoutProfile") if isinstance(task_runtime.get("ollamaTimeoutProfile"), dict) else {}
            )
            if provider == "ollama" and str(profile.get("status") or "") == "ready":
                return normalize_target_timeout_config(profile.get("targetTimeouts"))
        return default_target_timeout_config()

    def get_request_timeout_seconds(self, task: Dict[str, Any], target: Optional[str] = None) -> int:
        fallback = target_timeout_seconds(self.get_target_timeout_config(task, target), target)
        context = self.current_execution_context()
        override_raw = context.get("timeoutSeconds")
        if override_raw is None:
            return fallback
        try:
            override_seconds = int(override_raw)
        except (TypeError, ValueError):
            return fallback
        if override_seconds <= 0:
            return fallback
        override_target = normalize_auth_target(
            context.get("timeoutTarget") or context.get("traceTarget") or context.get("target") or target
        )
        requested_target = normalize_auth_target(target or override_target)
        if target is None or requested_target == override_target:
            return clamp_timeout_seconds(override_seconds, fallback)
        return fallback

    def get_provider_routing_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_provider_routing_config(
            task_runtime.get("providerRouting") if isinstance(task_runtime.get("providerRouting"), dict) else {}
        )

    def load_provider_instances(
        self,
        provider: Optional[str],
        runtime_config: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
        if normalized_provider != "ollama":
            return []
        catalog = read_provider_instance_catalog(self.config_root)
        pool = catalog.get(normalized_provider, []) if isinstance(catalog, dict) else []
        normalized_model = str(model or "").strip()
        instances = []
        for entry in pool if isinstance(pool, list) else []:
            current = normalize_provider_instance_entry(entry, normalized_provider)
            if not current or not bool(current.get("enabled")):
                continue
            supported_models = normalize_string_list(current.get("models", []))
            if supported_models and normalized_model and normalized_model not in supported_models:
                continue
            current["models"] = supported_models
            instances.append(current)
        primary_base_url = normalize_ollama_base_url(
            (runtime_config or {}).get("ollamaBaseUrl", default_ollama_base_url())
        )
        if not instances and primary_base_url:
            instances.append(default_provider_instance_entry(normalized_provider, primary_base_url, 1))
        elif primary_base_url and not normalized_model and not any(
            normalize_ollama_base_url(entry.get("baseUrl")) == primary_base_url for entry in instances
        ):
            instances.append(
                normalize_provider_instance_entry(
                    {
                        "id": "ollama-primary",
                        "provider": normalized_provider,
                        "label": "Primary session endpoint",
                        "baseUrl": primary_base_url,
                        "enabled": True,
                        "models": [],
                    },
                    normalized_provider,
                    len(instances) + 1,
                )
            )
        return [entry for entry in instances if isinstance(entry, dict)]

    def select_provider_instance(
        self,
        task: Optional[Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]],
        provider: Optional[str],
        model: Optional[str],
        target: Optional[str],
        round_number: Optional[int] = None,
        *,
        prefer_distinct_judge: bool = True,
    ) -> Optional[Dict[str, Any]]:
        normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
        if normalized_provider != "ollama":
            return None
        instances = self.load_provider_instances(normalized_provider, runtime_config, model)
        if not instances:
            return None
        if len(instances) == 1:
            return dict(instances[0])
        task_runtime = runtime_config if isinstance(runtime_config, dict) else {}
        routing = normalize_provider_routing_config(
            task_runtime.get("providerRouting") if isinstance(task_runtime.get("providerRouting"), dict) else {}
        )
        routing_node = routing.get(normalized_provider, default_provider_routing_config()["ollama"])
        selection_mode = str(routing_node.get("selectionMode") or "single").strip().lower()
        judge_mode = str(routing_node.get("judgeMode") or "prefer_distinct").strip().lower()
        normalized_target = normalize_auth_target(target)
        if selection_mode == "single":
            base_index = 0
        else:
            task_id = str((task or {}).get("taskId") or task_runtime.get("liveRunId") or "").strip()
            seed_source = "|".join(
                [
                    task_id,
                    str(model or "").strip(),
                    normalized_target,
                    str(int(round_number or 1)),
                ]
            )
            seed_value = int(hashlib.md5(seed_source.encode("utf-8")).hexdigest()[:8], 16) if seed_source else 0
            role_bias = {
                "commander": 0,
                "commander_review": 1,
                "summarizer": 2,
                "answer_now": 3,
                "direct_baseline": 4,
                "arbiter": 5,
            }.get(normalized_target, 0)
            if re.match(r"^[A-Z]$", normalized_target):
                role_bias += (ord(normalized_target) - ord("A"))
            base_index = seed_value % len(instances)
            if selection_mode == "mix":
                base_index = (base_index + role_bias) % len(instances)
        if (
            normalized_target == "arbiter"
            and prefer_distinct_judge
            and judge_mode == "prefer_distinct"
            and len(instances) > 1
        ):
            answer_instance = self.select_provider_instance(
                task,
                runtime_config,
                provider,
                model,
                "summarizer",
                round_number,
                prefer_distinct_judge=False,
            )
            if isinstance(answer_instance, dict) and str(answer_instance.get("id") or "").strip():
                answer_id = str(answer_instance.get("id") or "").strip()
                if str(instances[base_index].get("id") or "").strip() == answer_id:
                    base_index = (base_index + 1) % len(instances)
        return dict(instances[base_index])

    def resolve_provider_settings(
        self,
        task: Optional[Dict[str, Any]],
        runtime_config: Optional[Dict[str, Any]],
        provider: Optional[str],
        model: Optional[str],
        target: Optional[str],
        round_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        settings = dict(runtime_config or {})
        instance = self.select_provider_instance(task, settings, provider, model, target, round_number)
        if isinstance(instance, dict):
            settings["providerInstance"] = instance
            if normalize_provider_id(provider, DEFAULT_PROVIDER_ID) == "ollama":
                settings["ollamaBaseUrl"] = normalize_ollama_base_url(instance.get("baseUrl"))
        return settings

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
            "frontMode": default_front_mode(),
            "engineVersion": default_engine_version(),
            "engineGraph": default_engine_graph(),
            "enginePlan": default_engine_plan(),
            "providerRouting": default_provider_routing_config(),
            "contextMode": default_context_mode(),
            "directBaselineMode": default_direct_baseline_mode(),
            "directProvider": DEFAULT_PROVIDER_ID,
            "directModel": DEFAULT_MODEL_ID,
            "ollamaBaseUrl": default_ollama_base_url(),
            "timeoutMode": default_timeout_mode(),
            "ollamaTimeoutProfile": default_ollama_timeout_profile(),
            "reasoningEffort": "low",
            "maxOutputTokens": default_budget_config()["maxOutputTokens"],
            "targetTimeouts": default_target_timeout_config(),
            "requestTimeoutSeconds": default_target_timeout_config()["workerDefault"],
            "research": default_research_config(),
            "localFiles": default_local_file_tool_config(),
            "githubTools": default_github_tool_config(),
            "dynamicSpinup": default_dynamic_spinup_config(),
            "vetting": default_vetting_config(),
            "knowledgebase": default_knowledgebase_config(),
        }
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        if task_runtime:
            execution_mode = str(task_runtime.get("executionMode", runtime["executionMode"])).strip().lower()
            if execution_mode and execution_mode != "live":
                raise RuntimeErrorWithCode("Only live execution mode is supported. Configure a real provider/key instead of a synthetic run.", 400)
            runtime["executionMode"] = "live"
            reasoning_effort = str(task_runtime.get("reasoningEffort", runtime["reasoningEffort"])).strip()
            if reasoning_effort in {"none", "low", "medium", "high", "xhigh"}:
                runtime["reasoningEffort"] = reasoning_effort
            runtime["provider"] = normalize_provider_id(task_runtime.get("provider"), runtime["provider"])
            runtime["model"] = normalize_model_id(
                task_runtime.get("model"),
                default_model_for_provider(runtime["provider"]),
                runtime["provider"],
            )
            runtime["frontMode"] = normalize_front_mode(task_runtime.get("frontMode"), runtime["frontMode"])
            runtime["engineVersion"] = normalize_engine_version(task_runtime.get("engineVersion"), runtime["engineVersion"])
            runtime["engineGraph"] = normalize_engine_graph(task_runtime.get("engineGraph", runtime["engineGraph"]))
            runtime["providerRouting"] = normalize_provider_routing_config(
                task_runtime.get("providerRouting") if isinstance(task_runtime.get("providerRouting"), dict) else {}
            )
            runtime["contextMode"] = normalize_context_mode(task_runtime.get("contextMode"), runtime["contextMode"])
            runtime["directBaselineMode"] = normalize_direct_baseline_mode(task_runtime.get("directBaselineMode"), runtime["directBaselineMode"])
            runtime["directProvider"] = normalize_provider_id(task_runtime.get("directProvider"), runtime["provider"])
            runtime["directModel"] = normalize_model_id(
                task_runtime.get("directModel"),
                default_model_for_provider(runtime["directProvider"]),
                runtime["directProvider"],
            )
            runtime["ollamaBaseUrl"] = normalize_ollama_base_url(task_runtime.get("ollamaBaseUrl"))
            runtime["timeoutMode"] = normalize_timeout_mode(task_runtime.get("timeoutMode"), runtime["timeoutMode"])
            runtime["ollamaTimeoutProfile"] = normalize_ollama_timeout_profile(
                task_runtime.get("ollamaTimeoutProfile") if isinstance(task_runtime.get("ollamaTimeoutProfile"), dict) else {}
            )
            runtime["targetTimeouts"] = normalize_target_timeout_config(
                task_runtime.get("targetTimeouts") if isinstance(task_runtime.get("targetTimeouts"), dict) else {}
            )
            runtime["research"] = normalize_research_config(task_runtime.get("research") if isinstance(task_runtime.get("research"), dict) else {})
            runtime["localFiles"] = normalize_local_file_tool_config(task_runtime.get("localFiles") if isinstance(task_runtime.get("localFiles"), dict) else {})
            runtime["githubTools"] = normalize_github_tool_config(task_runtime.get("githubTools") if isinstance(task_runtime.get("githubTools"), dict) else {})
            runtime["dynamicSpinup"] = normalize_dynamic_spinup_config(task_runtime.get("dynamicSpinup") if isinstance(task_runtime.get("dynamicSpinup"), dict) else {})
            runtime["vetting"] = normalize_vetting_config(task_runtime.get("vetting") if isinstance(task_runtime.get("vetting"), dict) else {})
            runtime["knowledgebase"] = normalize_knowledgebase_config(
                task_runtime.get("knowledgebase") if isinstance(task_runtime.get("knowledgebase"), dict) else {}
            )
        runtime["maxOutputTokens"] = self.get_budget_limits(task, budget_target)["maxOutputTokens"]
        runtime["requestTimeoutSeconds"] = self.get_request_timeout_seconds(task, budget_target)
        if provider_override:
            runtime["provider"] = normalize_provider_id(provider_override, runtime["provider"])
        if model_override:
            runtime["model"] = normalize_model_id(model_override, runtime["model"], runtime["provider"])
        runtime["enginePlan"] = compile_engine_graph(runtime["engineGraph"], task=task, runtime_config=runtime)
        return runtime

    def get_direct_baseline_runtime(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        runtime = self.get_task_runtime(task)
        provider = normalize_provider_id(task_runtime.get("directProvider"), runtime["provider"])
        model = normalize_model_id(
            task_runtime.get("directModel"),
            default_model_for_provider(provider),
            provider,
        )
        return {
            "mode": normalize_direct_baseline_mode(task_runtime.get("directBaselineMode"), runtime.get("directBaselineMode", default_direct_baseline_mode())),
            "executionMode": runtime["executionMode"],
            "provider": provider,
            "model": model,
            "reasoningEffort": runtime["reasoningEffort"],
            "maxOutputTokens": runtime["maxOutputTokens"],
            "ollamaBaseUrl": normalize_ollama_base_url(task_runtime.get("ollamaBaseUrl", runtime.get("ollamaBaseUrl"))),
            "providerRouting": normalize_provider_routing_config(
                task_runtime.get("providerRouting") if isinstance(task_runtime.get("providerRouting"), dict) else {}
            ),
            "targetTimeouts": normalize_target_timeout_config(
                task_runtime.get("targetTimeouts") if isinstance(task_runtime.get("targetTimeouts"), dict) else {}
            ),
            "requestTimeoutSeconds": self.get_request_timeout_seconds(task, "direct_baseline"),
        }

    def provider_uses_api_key_pool(self, provider: Optional[str]) -> bool:
        normalized = str(provider or "").strip().lower()
        if not normalized:
            normalized = DEFAULT_PROVIDER_ID
        return normalized in auth_key_provider_ids()

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
        return self.build_api_key_assignments(target, task, round_number, salt, provider)

    def provider_live_api_key(
        self,
        provider: Optional[str],
        auth_assignments: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        normalized_provider = str(provider or "").strip().lower() or DEFAULT_PROVIDER_ID
        if normalized_provider in auth_key_provider_ids():
            assignment = auth_assignments[0] if auth_assignments else None
            return str(assignment.get("apiKey")) if isinstance(assignment, dict) else ""
        if normalize_provider_id(normalized_provider, DEFAULT_PROVIDER_ID) == "ollama":
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

    def get_knowledgebase_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_knowledgebase_config(task_runtime.get("knowledgebase") if isinstance(task_runtime.get("knowledgebase"), dict) else {})

    def knowledgebase_route_tags(
        self,
        task: Dict[str, Any],
        target: str,
        *,
        role: str = "",
        session_id: str = "",
        client_id: str = "",
    ) -> List[str]:
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        task_id = str(task.get("taskId") or metadata.get("taskId") or "").strip()
        lane_id = normalize_auth_target(target)
        tags: List[str] = []

        def add(prefix: str, value: Any) -> None:
            normalized = knowledgebase.slug(value, "", 80)
            if normalized:
                tag = f"{prefix}:{normalized}"
                if tag not in tags:
                    tags.append(tag)

        add("task", task_id)
        add("lane", lane_id)
        add("role", role)
        add("session", session_id or task.get("sessionId") or metadata.get("sessionId"))
        add("client", client_id or task.get("clientId") or metadata.get("clientId"))
        return tags

    def build_knowledgebase_recall_query(
        self,
        task: Dict[str, Any],
        target: str,
        *,
        label: str = "",
        role: str = "",
        focus: str = "",
        constraints: Optional[List[str]] = None,
        prior_summary: Optional[Dict[str, Any]] = None,
        commander_checkpoint: Optional[Dict[str, Any]] = None,
    ) -> str:
        parts = [
            str(task.get("objective") or ""),
            str(task.get("sessionContext") or ""),
            " ".join(limit_string_list(constraints or task.get("constraints", []), 8, 220)),
            f"{normalize_auth_target(target)} {label} {role} {focus}",
        ]
        if isinstance(prior_summary, dict):
            parts.extend(
                [
                    str(prior_summary.get("recommendedNextAction") or ""),
                    str((prior_summary.get("frontAnswer") or {}).get("answer") if isinstance(prior_summary.get("frontAnswer"), dict) else ""),
                    " ".join(limit_string_list(prior_summary.get("claimsNeedingVerification", []), 4, 180)),
                ]
            )
        if isinstance(commander_checkpoint, dict):
            parts.extend(
                [
                    str(commander_checkpoint.get("leadDirection") or ""),
                    str(commander_checkpoint.get("answerDraft") or ""),
                    " ".join(limit_string_list(commander_checkpoint.get("pressurePoints", []), 4, 180)),
                ]
            )
        return truncate_text(" ".join(part for part in parts if str(part or "").strip()), 2200)

    def build_knowledgebase_recall_packet(
        self,
        task: Dict[str, Any],
        runtime: Optional[Dict[str, Any]],
        target: str,
        *,
        label: str = "",
        role: str = "",
        focus: str = "",
        round_number: Optional[int] = None,
        constraints: Optional[List[str]] = None,
        prior_summary: Optional[Dict[str, Any]] = None,
        commander_checkpoint: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        runtime_config = runtime if isinstance(runtime, dict) else self.get_task_runtime(task)
        config = normalize_knowledgebase_config(runtime_config.get("knowledgebase") if isinstance(runtime_config.get("knowledgebase"), dict) else {})
        target_id = normalize_auth_target(target)
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        kb_runtime = runtime_config.get("knowledgebase") if isinstance(runtime_config.get("knowledgebase"), dict) else {}
        session_id = str(kb_runtime.get("sessionId") or task.get("sessionId") or metadata.get("sessionId") or self.current_execution_context().get("sessionId") or "").strip()
        client_id = str(kb_runtime.get("clientId") or task.get("clientId") or metadata.get("clientId") or self.current_execution_context().get("clientId") or "").strip()
        route_tags = self.knowledgebase_route_tags(task, target_id, role=role, session_id=session_id, client_id=client_id)
        query = self.build_knowledgebase_recall_query(
            task,
            target_id,
            label=label,
            role=role,
            focus=focus,
            constraints=constraints,
            prior_summary=prior_summary,
            commander_checkpoint=commander_checkpoint,
        )
        base_packet: Dict[str, Any] = {
            "schemaVersion": knowledgebase.SCHEMA_VERSION,
            "intent": "advisor_dispatch_recall",
            "enabled": bool(config["enabled"]),
            "available": True,
            "coreDependency": False,
            "target": target_id,
            "route": {
                "taskId": str(task.get("taskId") or ""),
                "laneId": target_id,
                "label": label or provider_trace_target_label(target_id),
                "role": role,
                "focus": focus,
                "round": int(round_number or 0),
                "sessionId": session_id,
                "clientId": client_id,
                "tags": route_tags,
            },
            "config": {
                "scope": config["scope"],
                "bankId": config["bankId"] or "all",
                "maxRecords": config["maxRecords"],
                "maxTokens": config["maxTokens"],
                "includeRuntime": config["includeRuntime"],
                "includePersistent": config["includePersistent"],
                "fallbackToShared": config["fallbackToShared"],
            },
            "query": query,
            "resultCount": 0,
            "fallbackUsed": False,
            "degraded": False,
            "warnings": [],
            "hits": [],
            "aiPacket": {
                "intent": "knowledgebase.recall",
                "coreDependency": False,
                "fallbackPolicy": "If durable memory is empty or unavailable, continue with current task context, runtime state, logs, artifacts, and live tool evidence.",
                "selectedEvidenceIds": [],
                "contextText": "",
            },
        }
        if not config["enabled"]:
            base_packet["available"] = False
            base_packet["disabledReason"] = "runtime.knowledgebase is disabled or scoped off"
            return base_packet

        scope = str(config["scope"])
        bank_id = "" if scope == "runtime" else str(config["bankId"] or "")
        include_runtime = bool(config["includeRuntime"])
        include_persistent = bool(config["includePersistent"]) and scope != "runtime"
        filter_tags = list(config["tags"])
        if scope in {"lane", "strict"}:
            filter_tags.extend(tag for tag in route_tags if tag not in filter_tags)

        try:
            recall = knowledgebase.recall(
                self.root,
                query=query,
                bank_id=bank_id,
                max_records=int(config["maxRecords"]),
                max_tokens=int(config["maxTokens"]),
                tags=filter_tags,
                tags_match=str(config["tagsMatch"]),
                include_runtime=include_runtime,
                include_persistent=include_persistent,
            )
            fallback_reason = ""
            if (
                scope == "lane"
                and int(recall.get("resultCount") or 0) == 0
                and bool(config["fallbackToShared"])
            ):
                recall = knowledgebase.recall(
                    self.root,
                    query=query,
                    bank_id=bank_id,
                    max_records=int(config["maxRecords"]),
                    max_tokens=int(config["maxTokens"]),
                    tags=list(config["tags"]),
                    tags_match=str(config["tagsMatch"]),
                    include_runtime=include_runtime,
                    include_persistent=include_persistent,
                )
                fallback_reason = "lane_scope_empty_used_shared_recall"
            base_packet.update(
                {
                    "resultCount": int(recall.get("resultCount") or 0),
                    "totalCandidates": int(recall.get("totalCandidates") or 0),
                    "fallbackUsed": bool(recall.get("fallbackUsed")),
                    "degraded": bool(recall.get("degraded")) or bool(fallback_reason),
                    "degradedReason": fallback_reason,
                    "warnings": normalize_string_array_preserve_items(recall.get("warnings", []))[:12],
                    "hits": recall.get("hits") if isinstance(recall.get("hits"), list) else [],
                    "aiPacket": recall.get("aiPacket") if isinstance(recall.get("aiPacket"), dict) else base_packet["aiPacket"],
                    "memoryPlan": recall.get("memoryPlan") if isinstance(recall.get("memoryPlan"), dict) else {},
                    "filters": {
                        "tags": filter_tags,
                        "tagsMatch": str(config["tagsMatch"]),
                        "bankId": bank_id or "all",
                    },
                }
            )
        except Exception as exc:
            base_packet.update(
                {
                    "available": False,
                    "degraded": True,
                    "error": f"{exc.__class__.__name__}: {truncate_text(str(exc), 260)}",
                    "warnings": ["Knowledgebase recall failed; dispatch must continue from current task context."],
                }
            )
        return base_packet

    def project_knowledgebase_prompt_packet(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        ai_packet = packet.get("aiPacket") if isinstance(packet.get("aiPacket"), dict) else {}
        hits = packet.get("hits") if isinstance(packet.get("hits"), list) else []
        return {
            "schemaVersion": str(packet.get("schemaVersion") or knowledgebase.SCHEMA_VERSION),
            "intent": str(packet.get("intent") or "advisor_dispatch_recall"),
            "enabled": bool(packet.get("enabled")),
            "available": bool(packet.get("available")),
            "coreDependency": False,
            "target": str(packet.get("target") or ""),
            "route": packet.get("route") if isinstance(packet.get("route"), dict) else {},
            "config": packet.get("config") if isinstance(packet.get("config"), dict) else {},
            "filters": packet.get("filters") if isinstance(packet.get("filters"), dict) else {},
            "memoryPlan": packet.get("memoryPlan") if isinstance(packet.get("memoryPlan"), dict) else {},
            "resultCount": int(packet.get("resultCount") or 0),
            "totalCandidates": int(packet.get("totalCandidates") or 0),
            "fallbackUsed": bool(packet.get("fallbackUsed")),
            "degraded": bool(packet.get("degraded")),
            "degradedReason": str(packet.get("degradedReason") or ""),
            "warnings": normalize_string_array_preserve_items(packet.get("warnings", []))[:8],
            "selectedEvidenceIds": normalize_string_array_preserve_items(ai_packet.get("selectedEvidenceIds", []))[:12],
            "contextText": truncate_text(ai_packet.get("contextText") or "", 3600),
            "hits": [
                {
                    "id": str(hit.get("id") or ""),
                    "title": truncate_text(hit.get("title") or "", 140),
                    "type": str(hit.get("type") or ""),
                    "source": str(hit.get("source") or ""),
                    "sourceId": truncate_text(hit.get("sourceId") or "", 180),
                    "summary": truncate_text(hit.get("summary") or hit.get("text") or "", 520),
                    "metadata": hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {},
                    "sop": hit.get("sop") if isinstance(hit.get("sop"), dict) else {},
                    "memoryLayer": str(hit.get("memoryLayer") or "adaptive"),
                    "baselineReason": str(hit.get("baselineReason") or ""),
                    "score": hit.get("score"),
                    "tags": normalize_string_array_preserve_items(hit.get("tags", []))[:12],
                    "createdAt": str(hit.get("createdAt") or ""),
                }
                for hit in hits[:8]
                if isinstance(hit, dict)
            ],
            "fallbackPolicy": str(ai_packet.get("fallbackPolicy") or "Memory is optional; current task context and inspected evidence win."),
        }

    def project_targeted_sop_prompt_packet(self, projected: Dict[str, Any]) -> Dict[str, Any]:
        baseline_packets: List[Dict[str, Any]] = []
        adaptive_packets: List[Dict[str, Any]] = []
        non_sop_hits: List[Dict[str, Any]] = []

        def short_items(value: Any, count: int, limit: int = 150) -> List[str]:
            return [truncate_text(item, limit) for item in normalize_string_array_preserve_items(value)[:count] if truncate_text(item, limit)]

        for hit in projected.get("hits", []):
            if not isinstance(hit, dict):
                continue
            sop = hit.get("sop") if isinstance(hit.get("sop"), dict) else {}
            metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
            learning_meta = {}
            if metadata.get("learning.kind"):
                learning_meta = {
                    "kind": truncate_text(metadata.get("learning.kind") or "", 80),
                    "failureClass": truncate_text(metadata.get("learning.failureClass") or "", 80),
                    "scenarioId": truncate_text(metadata.get("learning.scenarioId") or "", 100),
                    "missCount": metadata.get("learning.missCount"),
                    "scoreRefCount": metadata.get("learning.scoreRefCount"),
                    "eventCount": metadata.get("learning.eventCount"),
                    "adaptiveWeight": metadata.get("learning.adaptiveWeight"),
                    "replayIntervalDays": metadata.get("learning.replayIntervalDays"),
                }
            if not sop:
                non_sop_hits.append(
                    {
                        "id": hit.get("id"),
                        "title": hit.get("title"),
                        "type": hit.get("type"),
                        "sourceId": hit.get("sourceId"),
                        "summary": truncate_text(hit.get("summary") or "", 240),
                    }
                )
                continue
            packet = {
                "id": hit.get("id"),
                "title": hit.get("title"),
                "useCase": sop.get("useCase") or hit.get("title"),
                "eventTypes": short_items(sop.get("eventTypes", []), 8, 80),
                "summary": truncate_text(sop.get("summary") or "", 220),
                "triggers": short_items(sop.get("triggers", []), 4),
                "firstActions": short_items(sop.get("firstActions", []), 4),
                "evidence": short_items(sop.get("evidence", []), 5, 120),
                "decisionGates": short_items(sop.get("decisionGates", []), 4),
                "communications": short_items(sop.get("communications", []), 3),
                "escalation": short_items(sop.get("escalation", []), 3),
                "agentChecklist": short_items(sop.get("agentChecklist", []), 4),
                "avoid": short_items(sop.get("avoid", []), 4),
                "sourceRefs": short_items(sop.get("sourceRefs", []), 3, 140),
                "learning": learning_meta,
            }
            if str(hit.get("memoryLayer") or "").lower() == "baseline":
                packet["baselineReason"] = truncate_text(hit.get("baselineReason") or "baseline", 80)
                baseline_packets.append(packet)
            else:
                adaptive_packets.append(packet)
        if not baseline_packets and not adaptive_packets:
            return projected
        config = projected.get("config") if isinstance(projected.get("config"), dict) else {}
        memory_plan = projected.get("memoryPlan") if isinstance(projected.get("memoryPlan"), dict) else {}
        sop_packets = [*baseline_packets, *adaptive_packets]
        return {
            "schemaVersion": projected["schemaVersion"],
            "intent": "targeted_usecase_sop_recall",
            "enabled": projected["enabled"],
            "available": projected["available"],
            "coreDependency": False,
            "target": projected["target"],
            "bankId": config.get("bankId"),
            "resultCount": projected["resultCount"],
            "fallbackUsed": projected["fallbackUsed"],
            "degraded": projected["degraded"],
            "warnings": projected["warnings"],
            "selectedEvidenceIds": projected["selectedEvidenceIds"],
            "memoryMode": "baseline_and_adaptive_sop_packets",
            "omittedFullText": True,
            "retrievalPolicy": {
                "mode": str(memory_plan.get("mode") or "baseline_and_adaptive"),
                "baselineCount": memory_plan.get("baselineCount", len(baseline_packets)),
                "adaptiveCount": memory_plan.get("adaptiveCount", len(adaptive_packets)),
                "baselinePolicy": str(memory_plan.get("baselinePolicy") or "Baseline packets are mandatory guardrails; adaptive packets are scenario/learning recall."),
            },
            "baselinePackets": baseline_packets[:2],
            "adaptivePackets": adaptive_packets[:3],
            "sopPackets": sop_packets[:5],
            "supportingHits": non_sop_hits[:3],
            "fallbackPolicy": projected["fallbackPolicy"],
        }

    def render_knowledgebase_prompt_block(self, packet: Dict[str, Any]) -> str:
        projected = self.project_knowledgebase_prompt_packet(packet)
        if not projected.get("enabled") or not projected.get("available"):
            return ""
        prompt_packet = self.project_targeted_sop_prompt_packet(projected)
        heading = (
            "MSP knowledgebase recall (optional background, never a core dependency):\n"
            if prompt_packet.get("intent") == "targeted_usecase_sop_recall"
            else "Knowledgebase recall (optional background, never a core dependency):\n"
        )
        return (
            heading
            + json.dumps(prompt_packet, ensure_ascii=False, indent=2)
            + "\n\n"
            "Memory handling rule: use this as supporting context only. Current user input, current constraints, live tool evidence, and inspected files override stale or conflicting memory.\n\n"
        )

    def task_matches_msp_contradiction_gate(self, task: Dict[str, Any], prompt_packet: Optional[Dict[str, Any]] = None) -> bool:
        task_text = " ".join(
            [
                str(task.get("objective") or ""),
                str(task.get("sessionContext") or ""),
                " ".join(normalize_string_array_preserve_items(task.get("constraints", []))),
            ]
        ).lower()
        if any(trigger in task_text for trigger in MSP_CONTRADICTION_GATE_TRIGGERS):
            return True
        return False

    def msp_final_gate_applies(self, gate: Dict[str, Any], task_text: str) -> bool:
        triggers = [str(item).lower() for item in gate.get("triggers", []) if str(item).strip()]
        return not triggers or any(trigger in task_text for trigger in triggers)

    def final_answer_satisfies_gate(self, answer_text: str, gate: Dict[str, Any]) -> bool:
        lowered = str(answer_text or "").lower()
        if not lowered:
            return False
        gate_id = str(gate.get("id") or "")
        gate_library_entry = next((item for item in MSP_FINAL_ANSWER_GATES if item.get("id") == gate_id), {})
        match_source = gate.get("matchAny", gate_library_entry.get("matchAny", []))
        match_any = [str(item).lower() for item in match_source if str(item).strip()]
        if any(item in lowered for item in match_any):
            if gate_id != "msp-tenant-ownership":
                return True
        if gate_id == "msp-tenant-ownership":
            has_major_record = any(
                item in lowered
                for item in (
                    "internal major-incident record",
                    "internal major incident record",
                    "major-incident record",
                    "major incident record",
                )
            )
            has_tenant_owner = any(
                item in lowered
                for item in (
                    "named owner for every affected tenant",
                    "named owner for each affected tenant",
                    "owner for every affected tenant",
                    "owner for each affected tenant",
                    "owner per affected tenant",
                    "per-tenant owner",
                    "per-customer owner",
                    "tenant child record",
                    "affected tenant child record",
                    "customer child record",
                )
            )
            has_decision_log = (
                "decision log" in lowered
                or "evidence-compatible decision" in lowered
                or "evidence compatible decision" in lowered
                or "log all decisions" in lowered
                or "log every decision" in lowered
                or "log decisions" in lowered
                or "decision-and-rationale log" in lowered
                or "decision and rationale log" in lowered
            )
            return (
                has_major_record
                and has_tenant_owner
                and has_decision_log
            )
        if gate_id == "msp-evidence-before-cleanup":
            return (
                any(item in lowered for item in ("evidence", "log", "export", "snapshot", "chain"))
                and any(item in lowered for item in ("before", "prior to", "first"))
                and any(item in lowered for item in ("delete", "cancel", "cleanup", "restore", "contain"))
            )
        if gate_id == "msp-control-plane-distrust":
            return (
                any(item in lowered for item in ("out-of-band", "out of band", "independent", "do not trust", "suspect"))
                and any(item in lowered for item in ("rmm", "psa", "backup", "identity", "vendor", "portal", "control plane"))
            )
        return False

    def build_contradiction_memory_packet(
        self,
        task: Dict[str, Any],
        runtime: Optional[Dict[str, Any]],
        commander_review_checkpoint: Optional[Dict[str, Any]],
        worker_state: Optional[Dict[str, Any]],
        workers: Optional[List[Dict[str, str]]],
        knowledgebase_packet: Optional[Dict[str, Any]] = None,
        round_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        runtime_config = runtime if isinstance(runtime, dict) else self.get_task_runtime(task)
        knowledgebase_config = normalize_knowledgebase_config(
            runtime_config.get("knowledgebase") if isinstance(runtime_config.get("knowledgebase"), dict) else {}
        )
        if not knowledgebase_config.get("enabled"):
            return {
                "schemaVersion": "contradiction-memory/v1",
                "intent": "cross_round_final_answer_gate",
                "enabled": False,
                "coreDependency": False,
                "round": int(round_number or ((commander_review_checkpoint or {}).get("round", 0) if isinstance(commander_review_checkpoint, dict) else 0) or 0),
                "source": "disabled_by_runtime_knowledgebase_switch",
                "openContradictions": [],
                "sopObligations": [],
                "finalAnswerGates": [],
                "fallbackPolicy": "Runtime knowledgebase memory is disabled for this task.",
            }
        if not isinstance(knowledgebase_packet, dict):
            knowledgebase_packet = self.build_knowledgebase_recall_packet(
                task,
                runtime_config,
                "summarizer",
                label="Summarizer",
                role="final_answer",
                focus="final user-facing synthesis",
                round_number=round_number,
                constraints=limit_string_list(task.get("constraints", []), 24, 400),
            )
        projected_recall = self.project_knowledgebase_prompt_packet(knowledgebase_packet)
        prompt_packet = self.project_targeted_sop_prompt_packet(projected_recall)
        review_projection = self.project_commander_review_for_summary(
            commander_review_checkpoint,
            task,
            int(round_number or (commander_review_checkpoint or {}).get("round", 0) or 1),
            None,
            [worker["id"] for worker in workers or [] if isinstance((worker_state or {}).get(worker["id"]), dict)],
        )
        control_audit = normalize_control_audit(review_projection.get("controlAudit"), {
            "frontAnswer": {
                "answer": review_projection.get("answerDraft", ""),
                "stance": review_projection.get("stance", ""),
                "leadDirection": review_projection.get("leadDirection", ""),
                "adversarialPressure": "",
                "confidenceNote": "",
            },
            "summarizerOpinion": {
                "stance": review_projection.get("stance", ""),
                "because": review_projection.get("whyThisDirection", ""),
                "uncertainty": (review_projection.get("remainingUncertainty") or [""])[0],
                "integrationMode": "",
            },
            "claimsNeedingVerification": review_projection.get("remainingUncertainty", []),
        })

        open_items: List[str] = []

        def add_items(value: Any, max_items: int = 4, max_length: int = 220) -> None:
            for item in limit_string_list(value, max_items, max_length):
                if item and item not in open_items:
                    open_items.append(item)

        add_items(review_projection.get("requiredDecisionGates", []))
        add_items(review_projection.get("evidenceOrCommsRisks", []))
        add_items(review_projection.get("claimsToLimit", []), 3)
        add_items(review_projection.get("remainingUncertainty", []), 3)
        add_items(control_audit.get("heldOutConcerns", []), 3)
        worker_projection = self.project_worker_state_for_adjudication(worker_state or {}, workers or [])
        for checkpoint in worker_projection:
            add_items(checkpoint.get("evidenceGaps", []), 2, 180)
            add_items(checkpoint.get("uncertainty", []), 2, 180)
            add_items(checkpoint.get("detriments", []), 1, 180)

        task_trigger_text = " ".join(
            [
                str(task.get("objective") or ""),
                str(task.get("sessionContext") or ""),
                " ".join(normalize_string_array_preserve_items(task.get("constraints", []))),
            ]
        ).lower()
        final_gates: List[Dict[str, Any]] = []
        if self.task_matches_msp_contradiction_gate(task, prompt_packet):
            for gate in MSP_FINAL_ANSWER_GATES:
                if self.msp_final_gate_applies(gate, task_trigger_text):
                    final_gates.append(
                        {
                            "id": gate["id"],
                            "title": gate["title"],
                            "requirement": gate["requirement"],
                            "source": gate["source"],
                        }
                    )

        sop_obligations: List[str] = []
        if isinstance(prompt_packet, dict):
            for key in ("baselinePackets", "adaptivePackets"):
                for sop in prompt_packet.get(key, []) if isinstance(prompt_packet.get(key), list) else []:
                    if not isinstance(sop, dict):
                        continue
                    for field in ("firstActions", "decisionGates", "avoid", "communications", "escalation"):
                        for item in limit_string_list(sop.get(field, []), 3, 180):
                            if item and item not in sop_obligations:
                                sop_obligations.append(item)
        packet = {
            "schemaVersion": "contradiction-memory/v1",
            "intent": "cross_round_final_answer_gate",
            "enabled": bool(final_gates or open_items or sop_obligations),
            "coreDependency": False,
            "round": int(round_number or review_projection.get("round", 0) or 0),
            "source": "commander_review + worker_pressure + msp_knowledgebase_recall",
            "openContradictions": open_items[:8],
            "sopObligations": sop_obligations[:10],
            "finalAnswerGates": final_gates[:6],
            "fallbackPolicy": "If this packet is empty, continue normally. If non-empty, satisfy or explicitly reject each finalAnswerGate before the public answer leaves the summarizer.",
        }
        return packet

    def render_contradiction_memory_prompt_block(self, packet: Dict[str, Any]) -> str:
        if not isinstance(packet, dict) or not packet.get("enabled"):
            return ""
        projected = {
            "schemaVersion": str(packet.get("schemaVersion") or "contradiction-memory/v1"),
            "intent": str(packet.get("intent") or "cross_round_final_answer_gate"),
            "coreDependency": False,
            "round": int(packet.get("round") or 0),
            "openContradictions": limit_string_list(packet.get("openContradictions", []), 6, 180),
            "sopObligations": limit_string_list(packet.get("sopObligations", []), 8, 180),
            "finalAnswerGates": [
                {
                    "id": str(gate.get("id") or ""),
                    "title": truncate_text(gate.get("title") or "", 100),
                    "requirement": truncate_text(gate.get("requirement") or "", 240),
                    "source": str(gate.get("source") or ""),
                }
                for gate in packet.get("finalAnswerGates", [])[:6]
                if isinstance(gate, dict)
            ],
            "fallbackPolicy": str(packet.get("fallbackPolicy") or ""),
        }
        return (
            "Cross-round contradiction memory (mandatory final-answer coverage check):\n"
            + json.dumps(projected, ensure_ascii=False, indent=2)
            + "\n\n"
            "Contradiction handling rule: do not parrot this packet. Resolve each finalAnswerGate naturally inside the answer, or explicitly reject it in controlAudit.selfCheck with a reason. Do not drop a gate just because the lead draft already feels complete.\n\n"
        )

    def apply_contradiction_memory_final_gates(self, summary: Dict[str, Any], packet: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(summary, dict) or not isinstance(packet, dict) or not packet.get("enabled"):
            return summary
        final_gates = [gate for gate in packet.get("finalAnswerGates", []) if isinstance(gate, dict)]
        if not final_gates:
            return summary
        front_answer = summary.get("frontAnswer") if isinstance(summary.get("frontAnswer"), dict) else {}
        answer_text = str(front_answer.get("answer") or "").strip()
        missing = [gate for gate in final_gates if not self.final_answer_satisfies_gate(answer_text, gate)]
        if not missing:
            return summary
        gate_lines = [
            f"- {truncate_text(gate.get('requirement') or gate.get('title') or gate.get('id') or '', 260)}"
            for gate in missing[:6]
        ]
        backstop = "Operational gates to keep explicit:\n" + "\n".join(gate_lines)
        front_answer["answer"] = (answer_text + "\n\n" + backstop).strip() if answer_text else backstop
        summary["frontAnswer"] = front_answer
        control_audit = summary.get("controlAudit") if isinstance(summary.get("controlAudit"), dict) else {}
        held_out = normalize_string_array_preserve_items(control_audit.get("heldOutConcerns", []))
        for gate in missing[:6]:
            note = truncate_text(f"Final answer backstop inserted: {gate.get('title') or gate.get('id')}", 180)
            if note not in held_out:
                held_out.append(note)
        control_audit["heldOutConcerns"] = held_out[:8]
        existing_self_check = str(control_audit.get("selfCheck") or "").strip()
        inserted = ", ".join(str(gate.get("id") or "") for gate in missing[:6] if str(gate.get("id") or "").strip())
        self_check = f"Contradiction-memory backstop verified mandatory MSP gates and inserted missing gates: {inserted}."
        control_audit["selfCheck"] = truncate_text((existing_self_check + " " + self_check).strip(), 420)
        summary["controlAudit"] = control_audit
        summary["publicAnswer"] = str(front_answer.get("answer") or "").strip()
        summary["flattenedOutputText"] = flatten_output_payload_text(summary, "summary_output")
        return summary

    def contradiction_memory_call_meta(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "enabled": bool(packet.get("enabled")) if isinstance(packet, dict) else False,
            "coreDependency": False,
            "round": int(packet.get("round") or 0) if isinstance(packet, dict) else 0,
            "openContradictionCount": len(packet.get("openContradictions", [])) if isinstance(packet, dict) and isinstance(packet.get("openContradictions"), list) else 0,
            "sopObligationCount": len(packet.get("sopObligations", [])) if isinstance(packet, dict) and isinstance(packet.get("sopObligations"), list) else 0,
            "finalGateCount": len(packet.get("finalAnswerGates", [])) if isinstance(packet, dict) and isinstance(packet.get("finalAnswerGates"), list) else 0,
            "gateIds": [
                str(gate.get("id") or "")
                for gate in packet.get("finalAnswerGates", [])[:8]
                if isinstance(gate, dict) and str(gate.get("id") or "").strip()
            ] if isinstance(packet, dict) else [],
        }

    def knowledgebase_call_meta(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        projected = self.project_knowledgebase_prompt_packet(packet)
        return {
            "enabled": projected["enabled"],
            "available": projected["available"],
            "coreDependency": False,
            "scope": (projected.get("config") or {}).get("scope"),
            "target": projected["target"],
            "route": projected["route"],
            "resultCount": projected["resultCount"],
            "fallbackUsed": projected["fallbackUsed"],
            "degraded": projected["degraded"],
            "selectedEvidenceIds": projected["selectedEvidenceIds"],
            "warnings": projected["warnings"],
        }

    def get_model_pricing(self, model: str) -> Dict[str, Any]:
        inferred_provider = infer_provider_from_model_id(model) or DEFAULT_PROVIDER_ID
        resolved = normalize_model_id(model, default_model_for_provider(inferred_provider), inferred_provider)
        pricing = MODEL_CATALOG.get(resolved, {"inputPer1M": 0.0, "cachedInputPer1M": 0.0, "outputPer1M": 0.0})
        return {"model": resolved, **pricing}

    def get_response_output_text(self, response: Dict[str, Any]) -> Optional[str]:
        flattened = join_flattened_provider_text(response)
        return flattened or None

    def get_response_thinking_text(self, response: Dict[str, Any]) -> Optional[str]:
        if isinstance(response.get("message"), dict):
            thinking = response["message"].get("thinking")
            if thinking:
                return str(thinking)
        content_blocks = response.get("content")
        if isinstance(content_blocks, list):
            thinking_parts: List[str] = []
            for block in content_blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "thinking" and block.get("thinking"):
                    thinking_parts.append(str(block.get("thinking")))
            combined = "\n".join([item for item in thinking_parts if item]).strip()
            if combined:
                return combined
        return None

    def get_web_search_call_items(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = [
            item for item in response.get("output", []) if isinstance(item, dict) and item.get("type") == "web_search_call"
        ]
        content_blocks = response.get("content")
        if isinstance(content_blocks, list):
            items.extend(
                [
                    block
                    for block in content_blocks
                    if isinstance(block, dict)
                    and block.get("type") == "server_tool_use"
                    and str(block.get("name") or "").strip() == "web_search"
                ]
            )
        return items

    def get_response_web_search_queries(self, response: Dict[str, Any]) -> List[str]:
        queries: Dict[str, bool] = {}
        for item in self.get_web_search_call_items(response):
            action = item.get("action") if isinstance(item.get("action"), dict) else {}
            input_payload = item.get("input") if isinstance(item.get("input"), dict) else {}
            query = action.get("query") or input_payload.get("query")
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
        content_blocks = response.get("content")
        if isinstance(content_blocks, list):
            for block in content_blocks:
                if not isinstance(block, dict) or block.get("type") != "web_search_tool_result":
                    continue
                for source in block.get("content", []) if isinstance(block.get("content"), list) else []:
                    if isinstance(source, dict) and source.get("url"):
                        urls[str(source.get("url"))] = True
        return list(urls.keys())

    def get_response_url_citations(self, response: Dict[str, Any]) -> List[str]:
        urls: Dict[str, bool] = {}
        content_blocks = response.get("content")
        if isinstance(content_blocks, list):
            for block in content_blocks:
                if not isinstance(block, dict):
                    continue
                for citation in block.get("citations", []) if isinstance(block.get("citations"), list) else []:
                    if isinstance(citation, dict) and citation.get("url"):
                        urls[str(citation.get("url"))] = True
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
            input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
            output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
            total_tokens = int(usage.get("total_tokens", 0) or 0)
            cached_input_tokens = int(((usage.get("input_tokens_details") or {}).get("cached_tokens", 0)) or 0)
            if cached_input_tokens <= 0:
                cached_input_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
            reasoning_tokens = int(
                (
                    ((usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0))
                    or ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0))
                    or 0
                )
            )
            billable_input_tokens = max(0, input_tokens - cached_input_tokens)
            web_search_calls = max(
                len(self.get_web_search_call_items(response)),
                int(((usage.get("server_tool_use") or {}).get("web_search_requests", 0)) or 0),
            )
            pricing = self.get_model_pricing(model)
            model_cost = (
                (billable_input_tokens * float(pricing["inputPer1M"]))
                + (cached_input_tokens * float(pricing["cachedInputPer1M"]))
                + (output_tokens * float(pricing["outputPer1M"]))
            ) / 1_000_000.0
            tool_cost = web_search_calls * WEB_SEARCH_TOOL_CALL_PRICE_USD
            estimated_cost = model_cost + tool_cost
            if total_tokens <= 0:
                total_tokens = input_tokens + output_tokens
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

    def is_retryable_live_failure(self, error: RuntimeErrorWithCode) -> bool:
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

    def live_retry_attempt_limit(self, target: str) -> int:
        normalized = str(target or "").strip().lower()
        if normalized == "answer_now":
            return 2
        if normalized in {"direct_baseline", "commander", "commander_review", "summarizer"}:
            return 2
        if len(normalized) == 1 and normalized.isalpha():
            return 2
        return 2

    def should_retry_live_failure(self, error: RuntimeErrorWithCode) -> bool:
        if str(error).startswith("Budget limit reached:"):
            return False
        return self.is_retryable_live_failure(error)

    def execute_live_stage_with_retry(
        self,
        *,
        stage: str,
        target_label: str,
        task_id: str,
        model: str,
        requested_max_output_tokens: int,
        auth_meta: Optional[Dict[str, Any]],
        call: Callable[[], Any],
        extra_context: Optional[Dict[str, Any]] = None,
        retry_message: str = "Live API call failed; retrying live call.",
        exhausted_message: str = "Live API call failed after retries; no synthetic output was used.",
    ) -> tuple[Any, int]:
        attempts_allowed = max(1, int(self.live_retry_attempt_limit(target_label)))
        extra = dict(extra_context or {})
        for attempt_number in range(1, attempts_allowed + 1):
            try:
                return call(), attempt_number
            except RuntimeErrorWithCode as error:
                if str(error).startswith("Budget limit reached:"):
                    raise
                context = {
                    "taskId": task_id,
                    "target": target_label,
                    "model": model,
                    "requestedMaxOutputTokens": int(requested_max_output_tokens or 0),
                    "attempt": attempt_number,
                    "maxAttempts": attempts_allowed,
                    "error": str(error),
                    "auth": auth_meta,
                    **extra,
                }
                if attempt_number < attempts_allowed and self.should_retry_live_failure(error):
                    self.append_step(stage, retry_message, context)
                    continue
                failed_call_artifact = getattr(error, "failed_call_artifact", None)
                if not isinstance(failed_call_artifact, dict):
                    raw_output_text = str(getattr(error, "raw_output_text", "") or "")
                    failure_kind = str(getattr(error, "failure_kind", "") or "")
                    failed_call_artifact = self.write_failed_call_artifact(
                        task_id=task_id,
                        target_kind=target_label,
                        provider=str((auth_meta or {}).get("provider") or ""),
                        model=model,
                        error=error,
                        raw_output_text=raw_output_text,
                        requested_max_output_tokens=int(requested_max_output_tokens or 0),
                        auth_assignment=auth_meta,
                        failure_kind=failure_kind,
                    )
                    error.failed_call_artifact = failed_call_artifact
                context["failedCallArtifact"] = failed_call_artifact
                self.append_step(stage, exhausted_message, context)
                raise RuntimeErrorWithCode(
                    f"Live run failed for {target_label}: {error}",
                    error.status_code,
                    failed_call_artifact=failed_call_artifact,
                ) from error

    def raise_live_stage_missing_credentials(
        self,
        *,
        stage: str,
        target_label: str,
        task_id: str,
        auth_meta: Optional[Dict[str, Any]],
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.append_step(
            stage,
            "No API key found for a live run; no synthetic output was used.",
            {
                "taskId": task_id,
                "target": target_label,
                "auth": auth_meta,
                **dict(extra_context or {}),
            },
        )
        raise RuntimeErrorWithCode(f"Live run failed for {target_label}: no API key found.", 503)

    def is_request_timeout_error(self, error: Exception) -> bool:
        if isinstance(error, (TimeoutError, socket.timeout)):
            return True
        if isinstance(error, urllib.error.URLError):
            reason = getattr(error, "reason", None)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                return True
            if reason and "timed out" in str(reason).lower():
                return True
        return "timed out" in str(error).lower()

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
        request_timeout_seconds: int = 1800,
    ) -> OpenAIResult:
        handlers = function_handlers if isinstance(function_handlers, dict) else {}
        assignment_candidates = [dict(entry) for entry in (auth_assignments or []) if isinstance(entry, dict) and str(entry.get("apiKey", "")).strip()]
        if not assignment_candidates and str(api_key or "").strip():
            assignment_candidates = [{"apiKey": str(api_key).strip()}]
        if not assignment_candidates:
            raise RuntimeErrorWithCode("No API key available for live model call.", 401)

        auth_failover_history: List[Dict[str, Any]] = []
        last_error: Optional[RuntimeErrorWithCode] = None
        provider_trace = self.build_provider_trace_base("openai", model, target_kind, request_timeout_seconds)

        def report_trace(stage: str, **updates: Any) -> None:
            provider_trace.update({key: value for key, value in updates.items() if value is not None})
            provider_trace["stage"] = stage
            provider_trace["stageLabel"] = PROVIDER_TRACE_STAGE_LABELS.get(stage, stage.replace("_", " ").title())
            self.update_provider_trace(provider_trace)

        for assignment_index, assignment in enumerate(assignment_candidates):
            current_api_key = str(assignment.get("apiKey", "")).strip()
            if not current_api_key:
                continue
            attempts = self.build_output_token_attempts(max_output_tokens, target_kind, provider="openai", model=model)
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
                            "truncation": "auto",
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
                        report_trace(
                            "sending",
                            requestCount=int(provider_trace.get("requestCount") or 0) + 1,
                            attemptIndex=index + 1,
                            effectiveMaxOutputTokens=effective_tokens,
                            toolTurn=tool_turns,
                            authKeySlot=int(assignment.get("keySlot", 0) or 0) if assignment.get("keySlot") is not None else None,
                            authMasked=str(assignment.get("masked", "")).strip() or None,
                            requestUrl=request.full_url,
                            sentAt=utc_now(),
                        )
                        try:
                            with urllib.request.urlopen(request, timeout=request_timeout_seconds) as handle:
                                header_map = self.provider_trace_header_map(handle)
                                report_trace(
                                    "headers",
                                    headersAt=utc_now(),
                                    httpStatus=getattr(handle, "status", None) or getattr(handle, "code", None) or 200,
                                    **self.provider_trace_from_headers("openai", header_map),
                                )
                                response = json.loads(handle.read().decode("utf-8"))
                        except urllib.error.HTTPError as error:
                            body_text = error.read().decode("utf-8", errors="replace")
                            header_map = self.provider_trace_header_map(error)
                            report_trace(
                                "error",
                                headersAt=utc_now(),
                                completedAt=utc_now(),
                                httpStatus=error.code,
                                error=f"HTTP {error.code}",
                                **self.provider_trace_from_headers("openai", header_map),
                            )
                            raise RuntimeErrorWithCode(f"OpenAI API request failed: HTTP {error.code} | {body_text}", 500)
                        except Exception as error:
                            if self.is_request_timeout_error(error):
                                report_trace("timeout", completedAt=utc_now(), error=f"Timed out after {request_timeout_seconds}s")
                                raise RuntimeErrorWithCode(
                                    f"OpenAI API request timed out after {request_timeout_seconds}s.",
                                    504,
                                )
                            report_trace("error", completedAt=utc_now(), error=str(error))
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
                            report_trace(
                                "retrying",
                                completedAt=utc_now(),
                                responseStatus=str(response.get("status", "")).strip() or None,
                                incompleteReason=incomplete_reason,
                                providerResponseId=str(response.get("id", "")).strip() or None,
                            )
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
                            parsed = parse_structured_output_text(output_text)
                        except RuntimeErrorWithCode:
                            if response.get("status") == "incomplete" and incomplete_reason:
                                detail = f"Model response incomplete: {incomplete_reason}"
                                if incomplete_reason == "max_output_tokens":
                                    detail += f" after attempts {attempts}"
                                raise RuntimeErrorWithCode(detail, 500)
                            raise

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
                            provider_trace=self.update_provider_trace(
                                {
                                    **provider_trace,
                                    "stage": "completed",
                                    "stageLabel": PROVIDER_TRACE_STAGE_LABELS["completed"],
                                    "completedAt": utc_now(),
                                    "providerResponseId": str(response.get("id", "")).strip() or None,
                                    "responseStatus": str(response.get("status", "completed")).strip() or "completed",
                                    "toolTurn": tool_turns,
                                    "localToolCallCount": len(executed_tools),
                                    "webSearchQueryCount": len(web_search_queries),
                                }
                            ),
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

    def xai_responses_url(self) -> str:
        base = str(os.getenv("LOOP_XAI_BASE_URL") or "https://api.x.ai/v1").strip() or "https://api.x.ai/v1"
        return base.rstrip("/") + "/responses"

    def minimax_transport_mode(self, provider_settings: Optional[Dict[str, Any]] = None) -> str:
        runtime_value = ""
        if isinstance(provider_settings, dict):
            runtime_value = str(provider_settings.get("minimaxTransport") or "").strip().lower()
        env_value = str(os.getenv("LOOP_MINIMAX_TRANSPORT") or "").strip().lower()
        selected = runtime_value or env_value or "openai"
        if selected not in {"openai", "anthropic"}:
            return "openai"
        return selected

    def deepseek_transport_mode(self, provider_settings: Optional[Dict[str, Any]] = None) -> str:
        runtime_value = ""
        if isinstance(provider_settings, dict):
            runtime_value = str(provider_settings.get("deepseekTransport") or "").strip().lower()
        env_value = str(os.getenv("LOOP_DEEPSEEK_TRANSPORT") or "").strip().lower()
        selected = runtime_value or env_value or "openai"
        if selected not in {"openai", "anthropic"}:
            return "openai"
        return selected

    def minimax_openai_chat_url(self) -> str:
        base = str(os.getenv("LOOP_MINIMAX_OPENAI_BASE_URL") or "https://api.minimax.io/v1").strip() or "https://api.minimax.io/v1"
        normalized_base = base.rstrip("/")
        if normalized_base.endswith("/chat/completions"):
            return normalized_base
        if normalized_base.endswith("/v1"):
            return normalized_base + "/chat/completions"
        return normalized_base + "/v1/chat/completions"

    def deepseek_openai_chat_url(self) -> str:
        base = str(os.getenv("LOOP_DEEPSEEK_OPENAI_BASE_URL") or "https://api.deepseek.com").strip() or "https://api.deepseek.com"
        normalized_base = base.rstrip("/")
        if normalized_base.endswith("/chat/completions"):
            return normalized_base
        return normalized_base + "/chat/completions"

    def anthropic_messages_url(self, provider: str = "anthropic") -> str:
        normalized = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
        if normalized == "minimax":
            base = str(os.getenv("LOOP_MINIMAX_ANTHROPIC_BASE_URL") or "https://api.minimax.io/anthropic").strip()
        elif normalized == "deepseek":
            base = str(os.getenv("LOOP_DEEPSEEK_ANTHROPIC_BASE_URL") or "https://api.deepseek.com/anthropic").strip()
        else:
            base = str(os.getenv("LOOP_ANTHROPIC_BASE_URL") or "https://api.anthropic.com").strip()
        if normalized == "minimax":
            fallback_base = "https://api.minimax.io/anthropic"
        elif normalized == "deepseek":
            fallback_base = "https://api.deepseek.com/anthropic"
        else:
            fallback_base = "https://api.anthropic.com"
        base = base or fallback_base
        normalized_base = base.rstrip("/")
        if normalized_base.endswith("/v1/messages"):
            return normalized_base
        return normalized_base + "/v1/messages"

    def xai_accepts_reasoning_effort(self, model: str) -> bool:
        return str(model or "").strip() == "grok-4.20-multi-agent"

    def convert_function_tools_to_anthropic(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        converted: List[Dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            if str(tool.get("type", "")).strip() != "function":
                continue
            name = str(tool.get("name", "")).strip()
            if not name:
                continue
            converted.append(
                {
                    "name": name,
                    "description": str(tool.get("description", "")).strip(),
                    "input_schema": dict(tool.get("parameters")) if isinstance(tool.get("parameters"), dict) else {"type": "object", "properties": {}},
                }
            )
        return converted

    def anthropic_tool_choice(self, tool_choice: Optional[Any]) -> Optional[Dict[str, Any]]:
        if tool_choice is None:
            return None
        if isinstance(tool_choice, str):
            normalized = tool_choice.strip().lower()
            if normalized == "auto":
                return {"type": "auto"}
            if normalized == "none":
                return {"type": "none"}
        return None

    def invoke_minimax_openai_json(
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
        function_handlers: Optional[Dict[str, Any]] = None,
        auth_assignments: Optional[List[Dict[str, Any]]] = None,
        request_timeout_seconds: int = 1800,
        task_id: Optional[str] = None,
    ) -> OpenAIResult:
        handlers = function_handlers if isinstance(function_handlers, dict) else {}
        assignment_candidates = [dict(entry) for entry in (auth_assignments or []) if isinstance(entry, dict) and str(entry.get("apiKey", "")).strip()]
        if not assignment_candidates and str(api_key or "").strip():
            assignment_candidates = [{"apiKey": str(api_key).strip()}]
        if not assignment_candidates:
            raise RuntimeErrorWithCode("No API key available for live model call.", 401)

        normalized_tools = [tool for tool in (tools or []) if isinstance(tool, dict)]
        unsupported_tool_types = sorted(
            {
                str(tool.get("type", "")).strip() or "unknown"
                for tool in normalized_tools
                if str(tool.get("type", "")).strip() != "function"
            }
        )
        if unsupported_tool_types:
            raise RuntimeErrorWithCode(
                "provider_does_not_support: MiniMax OpenAI-compatible live mode only supports local function tools in this runtime"
                + f" (unsupported: {', '.join(unsupported_tool_types)}).",
                400,
            )

        auth_failover_history: List[Dict[str, Any]] = []
        last_error: Optional[RuntimeErrorWithCode] = None
        provider_trace = self.build_provider_trace_base("minimax", model, target_kind, request_timeout_seconds)

        def report_trace(stage: str, **updates: Any) -> None:
            provider_trace.update({key: value for key, value in updates.items() if value is not None})
            provider_trace["stage"] = stage
            provider_trace["stageLabel"] = PROVIDER_TRACE_STAGE_LABELS.get(stage, stage.replace("_", " ").title())
            self.update_provider_trace(provider_trace)

        for assignment_index, assignment in enumerate(assignment_candidates):
            current_api_key = str(assignment.get("apiKey", "")).strip()
            if not current_api_key:
                continue
            attempts = self.build_output_token_attempts(
                max_output_tokens,
                target_kind,
                provider="minimax",
                model=model,
                require_explicit_max=True,
            )
            recovered_from_incomplete = False

            try:
                for index, effective_tokens in enumerate(attempts):
                    effective_instructions = (
                        str(instructions or "").rstrip()
                        + "\nReturn raw JSON text only."
                        + "\nDo not use markdown fences."
                        + "\nDo not add commentary before or after the JSON object."
                        + "\nEscape every newline inside string values as \\\\n and every tab as \\\\t."
                    ).strip()
                    messages: List[Dict[str, Any]] = [
                        {"role": "system", "content": effective_instructions},
                        {
                            "role": "user",
                            "content": (
                                "Return JSON only that matches this schema exactly.\n\n"
                                f"Schema name: {schema_name}\n"
                                f"Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
                                f"Input:\n{input_text}"
                            ),
                        },
                    ]
                    executed_tools: List[Dict[str, Any]] = []
                    tool_turns = 0
                    retry_attempt = False
                    while True:
                        transport_max_tokens = max(1, int(effective_tokens or 0))
                        body: Dict[str, Any] = {
                            "model": model,
                            "messages": messages,
                            "stream": False,
                            "max_completion_tokens": transport_max_tokens,
                        }
                        if normalized_tools:
                            body["tools"] = normalized_tools
                        if tool_choice is not None:
                            body["tool_choice"] = tool_choice

                        request = urllib.request.Request(
                            self.minimax_openai_chat_url(),
                            data=json.dumps(body).encode("utf-8"),
                            headers={"Authorization": f"Bearer {current_api_key}", "Content-Type": "application/json"},
                            method="POST",
                        )
                        report_trace(
                            "sending",
                            requestCount=int(provider_trace.get("requestCount") or 0) + 1,
                            attemptIndex=index + 1,
                            effectiveMaxOutputTokens=transport_max_tokens,
                            toolTurn=tool_turns,
                            authKeySlot=int(assignment.get("keySlot", 0) or 0) if assignment.get("keySlot") is not None else None,
                            authMasked=str(assignment.get("masked", "")).strip() or None,
                            requestUrl=request.full_url,
                            sentAt=utc_now(),
                        )
                        try:
                            with urllib.request.urlopen(request, timeout=request_timeout_seconds) as handle:
                                header_map = self.provider_trace_header_map(handle)
                                report_trace(
                                    "headers",
                                    headersAt=utc_now(),
                                    httpStatus=getattr(handle, "status", None) or getattr(handle, "code", None) or 200,
                                    **self.provider_trace_from_headers("minimax", header_map),
                                )
                                response = json.loads(handle.read().decode("utf-8"))
                        except urllib.error.HTTPError as error:
                            body_text = error.read().decode("utf-8", errors="replace")
                            header_map = self.provider_trace_header_map(error)
                            report_trace(
                                "error",
                                headersAt=utc_now(),
                                completedAt=utc_now(),
                                httpStatus=error.code,
                                error=f"HTTP {error.code}",
                                **self.provider_trace_from_headers("minimax", header_map),
                            )
                            runtime_error = RuntimeErrorWithCode(f"MiniMax API request failed: HTTP {error.code} | {body_text}", 500)
                            runtime_error.failed_call_artifact = self.write_failed_call_artifact(
                                task_id=task_id,
                                target_kind=target_kind,
                                provider="minimax",
                                model=model,
                                schema_name=schema_name,
                                error=runtime_error,
                                raw_output_text=body_text,
                                finish_reason=f"HTTP {error.code}",
                                requested_max_output_tokens=max_output_tokens,
                                effective_max_output_tokens=transport_max_tokens,
                                attempts=attempts,
                                provider_trace=provider_trace,
                                auth_assignment=auth_assignment_meta(assignment),
                                failure_kind="http_error",
                            )
                            raise runtime_error
                        except Exception as error:
                            if self.is_request_timeout_error(error):
                                report_trace("timeout", completedAt=utc_now(), error=f"Timed out after {request_timeout_seconds}s")
                                runtime_error = RuntimeErrorWithCode(
                                    f"MiniMax API request timed out after {request_timeout_seconds}s.",
                                    504,
                                )
                                runtime_error.failed_call_artifact = self.write_failed_call_artifact(
                                    task_id=task_id,
                                    target_kind=target_kind,
                                    provider="minimax",
                                    model=model,
                                    schema_name=schema_name,
                                    error=runtime_error,
                                    requested_max_output_tokens=max_output_tokens,
                                    effective_max_output_tokens=transport_max_tokens,
                                    attempts=attempts,
                                    provider_trace=provider_trace,
                                    auth_assignment=auth_assignment_meta(assignment),
                                    failure_kind="timeout",
                                )
                                raise runtime_error
                            report_trace("error", completedAt=utc_now(), error=str(error))
                            runtime_error = RuntimeErrorWithCode(f"MiniMax API request failed: {error}", 500)
                            runtime_error.failed_call_artifact = self.write_failed_call_artifact(
                                task_id=task_id,
                                target_kind=target_kind,
                                provider="minimax",
                                model=model,
                                schema_name=schema_name,
                                error=runtime_error,
                                requested_max_output_tokens=max_output_tokens,
                                effective_max_output_tokens=transport_max_tokens,
                                attempts=attempts,
                                provider_trace=provider_trace,
                                auth_assignment=auth_assignment_meta(assignment),
                                failure_kind="connection",
                            )
                            raise runtime_error

                        if isinstance(response.get("error"), dict):
                            runtime_error = RuntimeErrorWithCode(f"Model response error: {json.dumps(response['error'], ensure_ascii=False)}", 500)
                            runtime_error.failed_call_artifact = self.write_failed_call_artifact(
                                task_id=task_id,
                                target_kind=target_kind,
                                provider="minimax",
                                model=model,
                                schema_name=schema_name,
                                error=runtime_error,
                                raw_response=response,
                                response_id=str(response.get("id", "")),
                                requested_max_output_tokens=max_output_tokens,
                                effective_max_output_tokens=transport_max_tokens,
                                attempts=attempts,
                                provider_trace=provider_trace,
                                auth_assignment=auth_assignment_meta(assignment),
                                failure_kind="provider_error",
                            )
                            raise runtime_error
                        base_resp = response.get("base_resp") if isinstance(response.get("base_resp"), dict) else {}
                        status_code = int(base_resp.get("status_code", 0) or 0)
                        status_msg = str(base_resp.get("status_msg", "") or "").strip()
                        if status_code:
                            detail = status_msg or f"MiniMax base_resp status_code={status_code}"
                            runtime_error = RuntimeErrorWithCode(f"Model response error: {detail}", 500)
                            runtime_error.failed_call_artifact = self.write_failed_call_artifact(
                                task_id=task_id,
                                target_kind=target_kind,
                                provider="minimax",
                                model=model,
                                schema_name=schema_name,
                                error=runtime_error,
                                raw_response=response,
                                response_id=str(response.get("id", "")),
                                requested_max_output_tokens=max_output_tokens,
                                effective_max_output_tokens=transport_max_tokens,
                                attempts=attempts,
                                provider_trace=provider_trace,
                                auth_assignment=auth_assignment_meta(assignment),
                                failure_kind="provider_error",
                            )
                            raise runtime_error

                        choices = response.get("choices") if isinstance(response.get("choices"), list) else []
                        first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
                        message_node = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
                        finish_reason = str(first_choice.get("finish_reason", "") or "").strip().lower()

                        tool_calls = []
                        if handlers:
                            for item in message_node.get("tool_calls") if isinstance(message_node.get("tool_calls"), list) else []:
                                if not isinstance(item, dict):
                                    continue
                                function_node = item.get("function") if isinstance(item.get("function"), dict) else {}
                                name = str(function_node.get("name", "")).strip()
                                if name not in handlers:
                                    continue
                                tool_calls.append(item)

                        if tool_calls:
                            if tool_turns >= 8:
                                raise RuntimeErrorWithCode("Model exceeded the allowed local tool turn count.", 500)
                            assistant_message: Dict[str, Any] = {
                                "role": "assistant",
                                "content": str(message_node.get("content", "") or ""),
                                "tool_calls": tool_calls,
                            }
                            messages.append(assistant_message)
                            for item in tool_calls:
                                function_node = item.get("function") if isinstance(item.get("function"), dict) else {}
                                name = str(function_node.get("name", "")).strip()
                                raw_arguments = function_node.get("arguments")
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
                                if item.get("id"):
                                    audit_entry["callId"] = str(item.get("id"))
                                executed_tools.append(audit_entry)
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": str(item.get("id", "")),
                                        "content": json.dumps(tool_output, ensure_ascii=False),
                                    }
                                )
                            tool_turns += 1
                            continue

                        output_text = str(message_node.get("content", "") or "").strip() or self.get_response_output_text(response)
                        if not output_text:
                            if finish_reason == "length" and index < len(attempts) - 1:
                                report_trace(
                                    "retrying",
                                    completedAt=utc_now(),
                                    responseStatus=finish_reason or None,
                                    providerResponseId=str(response.get("id", "")).strip() or None,
                                )
                                recovered_from_incomplete = True
                                retry_attempt = True
                                break
                            runtime_error = RuntimeErrorWithCode("Model response did not include choices[0].message.content.", 500)
                            runtime_error.failed_call_artifact = self.write_failed_call_artifact(
                                task_id=task_id,
                                target_kind=target_kind,
                                provider="minimax",
                                model=model,
                                schema_name=schema_name,
                                error=runtime_error,
                                raw_response=response,
                                response_id=str(response.get("id", "")),
                                finish_reason=finish_reason,
                                requested_max_output_tokens=max_output_tokens,
                                effective_max_output_tokens=transport_max_tokens,
                                attempts=attempts,
                                recovered_from_incomplete=recovered_from_incomplete,
                                provider_trace=provider_trace,
                                auth_assignment=auth_assignment_meta(assignment),
                                failure_kind="overflow" if finish_reason == "length" else "empty_output",
                            )
                            raise runtime_error

                        try:
                            parsed = parse_structured_output_text(output_text)
                        except RuntimeErrorWithCode as parse_error:
                            salvaged = (
                                salvage_direct_answer_payload("minimax", output_text)
                                if schema_looks_like_direct_answer(schema)
                                else None
                            )
                            if salvaged is not None:
                                parsed = salvaged
                            else:
                                incomplete_output = finish_reason == "length" or looks_like_incomplete_structured_output(output_text)
                                if incomplete_output and index < len(attempts) - 1:
                                    recovered_from_incomplete = True
                                    retry_attempt = True
                                    break
                                parse_error.failed_call_artifact = self.write_failed_call_artifact(
                                    task_id=task_id,
                                    target_kind=target_kind,
                                    provider="minimax",
                                    model=model,
                                    schema_name=schema_name,
                                    error=parse_error,
                                    raw_output_text=output_text,
                                    raw_response=response,
                                    response_id=str(response.get("id", "")),
                                    finish_reason=finish_reason,
                                    requested_max_output_tokens=max_output_tokens,
                                    effective_max_output_tokens=transport_max_tokens,
                                    attempts=attempts,
                                    recovered_from_incomplete=recovered_from_incomplete,
                                    provider_trace=provider_trace,
                                    auth_assignment=auth_assignment_meta(assignment),
                                    failure_kind="overflow" if finish_reason == "length" else "malformed_json",
                                )
                                raise parse_error

                        return OpenAIResult(
                            provider="minimax",
                            parsed=parsed,
                            response=response,
                            response_id=str(response.get("id", "")),
                            output_text=output_text,
                            thinking_text=None,
                            web_search_queries=[],
                            web_search_sources=[],
                            url_citations=[],
                            requested_max_output_tokens=max(0, int(max_output_tokens or 0)),
                            effective_max_output_tokens=transport_max_tokens,
                            attempts=attempts,
                            recovered_from_incomplete=recovered_from_incomplete,
                            executed_tools=executed_tools,
                            auth_assignment=auth_assignment_meta(assignment),
                            auth_failover_history=list(auth_failover_history),
                            provider_trace=self.update_provider_trace(
                                {
                                    **provider_trace,
                                    "stage": "completed",
                                    "stageLabel": PROVIDER_TRACE_STAGE_LABELS["completed"],
                                    "completedAt": utc_now(),
                                    "providerResponseId": str(response.get("id", "")).strip() or None,
                                    "responseStatus": finish_reason or "completed",
                                    "toolTurn": tool_turns,
                                    "localToolCallCount": len(executed_tools),
                                }
                            ),
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
        raise RuntimeErrorWithCode("MiniMax response did not produce a usable structured output.", 500)

    def invoke_deepseek_openai_json(
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
        function_handlers: Optional[Dict[str, Any]] = None,
        auth_assignments: Optional[List[Dict[str, Any]]] = None,
        request_timeout_seconds: int = 1800,
        task_id: Optional[str] = None,
    ) -> OpenAIResult:
        handlers = function_handlers if isinstance(function_handlers, dict) else {}
        assignment_candidates = [dict(entry) for entry in (auth_assignments or []) if isinstance(entry, dict) and str(entry.get("apiKey", "")).strip()]
        if not assignment_candidates and str(api_key or "").strip():
            assignment_candidates = [{"apiKey": str(api_key).strip()}]
        if not assignment_candidates:
            raise RuntimeErrorWithCode("No API key available for live model call.", 401)

        normalized_tools = [tool for tool in (tools or []) if isinstance(tool, dict)]
        unsupported_tool_types = sorted(
            {
                str(tool.get("type", "")).strip() or "unknown"
                for tool in normalized_tools
                if str(tool.get("type", "")).strip() != "function"
            }
        )
        if unsupported_tool_types:
            raise RuntimeErrorWithCode(
                "provider_does_not_support: DeepSeek OpenAI-compatible live mode only supports local function tools in this runtime"
                + f" (unsupported: {', '.join(unsupported_tool_types)}).",
                400,
            )

        auth_failover_history: List[Dict[str, Any]] = []
        last_error: Optional[RuntimeErrorWithCode] = None
        provider_trace = self.build_provider_trace_base("deepseek", model, target_kind, request_timeout_seconds)

        def report_trace(stage: str, **updates: Any) -> None:
            provider_trace.update({key: value for key, value in updates.items() if value is not None})
            provider_trace["stage"] = stage
            provider_trace["stageLabel"] = PROVIDER_TRACE_STAGE_LABELS.get(stage, stage.replace("_", " ").title())
            self.update_provider_trace(provider_trace)

        for assignment_index, assignment in enumerate(assignment_candidates):
            current_api_key = str(assignment.get("apiKey", "")).strip()
            if not current_api_key:
                continue
            attempts = self.build_output_token_attempts(
                max_output_tokens,
                target_kind,
                provider="deepseek",
                model=model,
                require_explicit_max=True,
            )
            recovered_from_incomplete = False

            try:
                for index, effective_tokens in enumerate(attempts):
                    effective_instructions = (
                        str(instructions or "").rstrip()
                        + "\nReturn raw JSON text only."
                        + "\nDo not use markdown fences."
                        + "\nDo not add commentary before or after the JSON object."
                        + "\nEscape every newline inside string values as \\\\n and every tab as \\\\t."
                    ).strip()
                    messages: List[Dict[str, Any]] = [
                        {"role": "system", "content": effective_instructions},
                        {
                            "role": "user",
                            "content": (
                                "Return JSON only that matches this schema exactly.\n\n"
                                f"Schema name: {schema_name}\n"
                                f"Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
                                f"Input:\n{input_text}"
                            ),
                        },
                    ]
                    executed_tools: List[Dict[str, Any]] = []
                    tool_turns = 0
                    retry_attempt = False
                    while True:
                        transport_max_tokens = max(1, int(effective_tokens or 0))
                        body: Dict[str, Any] = {
                            "model": model,
                            "messages": messages,
                            "stream": False,
                            "max_tokens": transport_max_tokens,
                        }
                        if str(reasoning_effort or "").strip():
                            body["reasoning_effort"] = str(reasoning_effort).strip()
                        if normalized_tools:
                            body["tools"] = normalized_tools
                        else:
                            body["response_format"] = {"type": "json_object"}
                        if tool_choice is not None:
                            body["tool_choice"] = tool_choice

                        request = urllib.request.Request(
                            self.deepseek_openai_chat_url(),
                            data=json.dumps(body).encode("utf-8"),
                            headers={"Authorization": f"Bearer {current_api_key}", "Content-Type": "application/json"},
                            method="POST",
                        )
                        report_trace(
                            "sending",
                            requestCount=int(provider_trace.get("requestCount") or 0) + 1,
                            attemptIndex=index + 1,
                            effectiveMaxOutputTokens=transport_max_tokens,
                            toolTurn=tool_turns,
                            authKeySlot=int(assignment.get("keySlot", 0) or 0) if assignment.get("keySlot") is not None else None,
                            authMasked=str(assignment.get("masked", "")).strip() or None,
                            requestUrl=request.full_url,
                            sentAt=utc_now(),
                        )
                        try:
                            with urllib.request.urlopen(request, timeout=request_timeout_seconds) as handle:
                                header_map = self.provider_trace_header_map(handle)
                                report_trace(
                                    "headers",
                                    headersAt=utc_now(),
                                    httpStatus=getattr(handle, "status", None) or getattr(handle, "code", None) or 200,
                                    **self.provider_trace_from_headers("deepseek", header_map),
                                )
                                response = json.loads(handle.read().decode("utf-8"))
                        except urllib.error.HTTPError as error:
                            body_text = error.read().decode("utf-8", errors="replace")
                            header_map = self.provider_trace_header_map(error)
                            report_trace(
                                "error",
                                headersAt=utc_now(),
                                completedAt=utc_now(),
                                httpStatus=error.code,
                                error=f"HTTP {error.code}",
                                **self.provider_trace_from_headers("deepseek", header_map),
                            )
                            runtime_error = RuntimeErrorWithCode(f"DeepSeek API request failed: HTTP {error.code} | {body_text}", 500)
                            runtime_error.failed_call_artifact = self.write_failed_call_artifact(
                                task_id=task_id,
                                target_kind=target_kind,
                                provider="deepseek",
                                model=model,
                                schema_name=schema_name,
                                error=runtime_error,
                                raw_output_text=body_text,
                                finish_reason=f"HTTP {error.code}",
                                requested_max_output_tokens=max_output_tokens,
                                effective_max_output_tokens=transport_max_tokens,
                                attempts=attempts,
                                provider_trace=provider_trace,
                                auth_assignment=auth_assignment_meta(assignment),
                                failure_kind="http_error",
                            )
                            raise runtime_error
                        except Exception as error:
                            if self.is_request_timeout_error(error):
                                report_trace("timeout", completedAt=utc_now(), error=f"Timed out after {request_timeout_seconds}s")
                                runtime_error = RuntimeErrorWithCode(
                                    f"DeepSeek API request timed out after {request_timeout_seconds}s.",
                                    504,
                                )
                                runtime_error.failed_call_artifact = self.write_failed_call_artifact(
                                    task_id=task_id,
                                    target_kind=target_kind,
                                    provider="deepseek",
                                    model=model,
                                    schema_name=schema_name,
                                    error=runtime_error,
                                    requested_max_output_tokens=max_output_tokens,
                                    effective_max_output_tokens=transport_max_tokens,
                                    attempts=attempts,
                                    provider_trace=provider_trace,
                                    auth_assignment=auth_assignment_meta(assignment),
                                    failure_kind="timeout",
                                )
                                raise runtime_error
                            report_trace("error", completedAt=utc_now(), error=str(error))
                            runtime_error = RuntimeErrorWithCode(f"DeepSeek API request failed: {error}", 500)
                            runtime_error.failed_call_artifact = self.write_failed_call_artifact(
                                task_id=task_id,
                                target_kind=target_kind,
                                provider="deepseek",
                                model=model,
                                schema_name=schema_name,
                                error=runtime_error,
                                requested_max_output_tokens=max_output_tokens,
                                effective_max_output_tokens=transport_max_tokens,
                                attempts=attempts,
                                provider_trace=provider_trace,
                                auth_assignment=auth_assignment_meta(assignment),
                                failure_kind="connection",
                            )
                            raise runtime_error

                        if isinstance(response.get("error"), dict):
                            raise RuntimeErrorWithCode(f"Model response error: {json.dumps(response['error'], ensure_ascii=False)}", 500)

                        choices = response.get("choices") if isinstance(response.get("choices"), list) else []
                        first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
                        message_node = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
                        finish_reason = str(first_choice.get("finish_reason", "") or "").strip().lower()

                        tool_calls = []
                        if handlers:
                            for item in message_node.get("tool_calls") if isinstance(message_node.get("tool_calls"), list) else []:
                                if not isinstance(item, dict):
                                    continue
                                function_node = item.get("function") if isinstance(item.get("function"), dict) else {}
                                name = str(function_node.get("name", "")).strip()
                                if name not in handlers:
                                    continue
                                tool_calls.append(item)

                        if tool_calls:
                            if tool_turns >= 8:
                                raise RuntimeErrorWithCode("Model exceeded the allowed local tool turn count.", 500)
                            assistant_message: Dict[str, Any] = {
                                "role": "assistant",
                                "content": str(message_node.get("content", "") or ""),
                                "tool_calls": tool_calls,
                            }
                            messages.append(assistant_message)
                            for item in tool_calls:
                                function_node = item.get("function") if isinstance(item.get("function"), dict) else {}
                                name = str(function_node.get("name", "")).strip()
                                raw_arguments = function_node.get("arguments")
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
                                if item.get("id"):
                                    audit_entry["callId"] = str(item.get("id"))
                                executed_tools.append(audit_entry)
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": str(item.get("id", "")),
                                        "content": json.dumps(tool_output, ensure_ascii=False),
                                    }
                                )
                            tool_turns += 1
                            continue

                        output_text = str(message_node.get("content", "") or "").strip() or self.get_response_output_text(response)
                        if not output_text:
                            if finish_reason == "length" and index < len(attempts) - 1:
                                report_trace(
                                    "retrying",
                                    completedAt=utc_now(),
                                    responseStatus=finish_reason or None,
                                    providerResponseId=str(response.get("id", "")).strip() or None,
                                )
                                recovered_from_incomplete = True
                                retry_attempt = True
                                break
                            runtime_error = RuntimeErrorWithCode("Model response did not include choices[0].message.content.", 500)
                            runtime_error.failed_call_artifact = self.write_failed_call_artifact(
                                task_id=task_id,
                                target_kind=target_kind,
                                provider="deepseek",
                                model=model,
                                schema_name=schema_name,
                                error=runtime_error,
                                raw_response=response,
                                response_id=str(response.get("id", "")),
                                finish_reason=finish_reason,
                                requested_max_output_tokens=max_output_tokens,
                                effective_max_output_tokens=transport_max_tokens,
                                attempts=attempts,
                                recovered_from_incomplete=recovered_from_incomplete,
                                provider_trace=provider_trace,
                                auth_assignment=auth_assignment_meta(assignment),
                                failure_kind="overflow" if finish_reason == "length" else "empty_output",
                            )
                            raise runtime_error

                        try:
                            parsed = parse_structured_output_text(output_text)
                        except RuntimeErrorWithCode as parse_error:
                            salvaged = (
                                salvage_direct_answer_payload("deepseek", output_text)
                                if schema_looks_like_direct_answer(schema)
                                else None
                            )
                            if salvaged is not None:
                                parsed = salvaged
                            else:
                                incomplete_output = finish_reason == "length" or looks_like_incomplete_structured_output(output_text)
                                if incomplete_output and index < len(attempts) - 1:
                                    recovered_from_incomplete = True
                                    retry_attempt = True
                                    break
                                parse_error.failed_call_artifact = self.write_failed_call_artifact(
                                    task_id=task_id,
                                    target_kind=target_kind,
                                    provider="deepseek",
                                    model=model,
                                    schema_name=schema_name,
                                    error=parse_error,
                                    raw_output_text=output_text,
                                    raw_response=response,
                                    response_id=str(response.get("id", "")),
                                    finish_reason=finish_reason,
                                    requested_max_output_tokens=max_output_tokens,
                                    effective_max_output_tokens=transport_max_tokens,
                                    attempts=attempts,
                                    recovered_from_incomplete=recovered_from_incomplete,
                                    provider_trace=provider_trace,
                                    auth_assignment=auth_assignment_meta(assignment),
                                    failure_kind="overflow" if finish_reason == "length" else "malformed_json",
                                )
                                raise parse_error

                        return OpenAIResult(
                            provider="deepseek",
                            parsed=parsed,
                            response=response,
                            response_id=str(response.get("id", "")),
                            output_text=output_text,
                            thinking_text=None,
                            web_search_queries=[],
                            web_search_sources=[],
                            url_citations=[],
                            requested_max_output_tokens=max(0, int(max_output_tokens or 0)),
                            effective_max_output_tokens=transport_max_tokens,
                            attempts=attempts,
                            recovered_from_incomplete=recovered_from_incomplete,
                            executed_tools=executed_tools,
                            auth_assignment=auth_assignment_meta(assignment),
                            auth_failover_history=list(auth_failover_history),
                            provider_trace=self.update_provider_trace(
                                {
                                    **provider_trace,
                                    "stage": "completed",
                                    "stageLabel": PROVIDER_TRACE_STAGE_LABELS["completed"],
                                    "completedAt": utc_now(),
                                    "providerResponseId": str(response.get("id", "")).strip() or None,
                                    "responseStatus": finish_reason or "completed",
                                    "toolTurn": tool_turns,
                                    "localToolCallCount": len(executed_tools),
                                }
                            ),
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
        raise RuntimeErrorWithCode("DeepSeek response did not produce a usable structured output.", 500)

    def convert_function_tools_to_ollama(self, tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        converted: List[Dict[str, Any]] = []
        for tool in tools or []:
            if not isinstance(tool, dict):
                continue
            if str(tool.get("type", "")).strip() != "function":
                continue
            name = str(tool.get("name", "")).strip()
            if not name:
                continue
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": str(tool.get("description", "")).strip(),
                        "parameters": tool.get("parameters") if isinstance(tool.get("parameters"), dict) else {"type": "object", "properties": {}},
                    },
                }
            )
        return converted

    def invoke_xai_json(
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
        request_timeout_seconds: int = 1800,
    ) -> OpenAIResult:
        handlers = function_handlers if isinstance(function_handlers, dict) else {}
        assignment_candidates = [dict(entry) for entry in (auth_assignments or []) if isinstance(entry, dict) and str(entry.get("apiKey", "")).strip()]
        if not assignment_candidates and str(api_key or "").strip():
            assignment_candidates = [{"apiKey": str(api_key).strip()}]
        if not assignment_candidates:
            raise RuntimeErrorWithCode("No API key available for live model call.", 401)

        auth_failover_history: List[Dict[str, Any]] = []
        last_error: Optional[RuntimeErrorWithCode] = None
        provider_trace = self.build_provider_trace_base("xai", model, target_kind, request_timeout_seconds)

        def report_trace(stage: str, **updates: Any) -> None:
            provider_trace.update({key: value for key, value in updates.items() if value is not None})
            provider_trace["stage"] = stage
            provider_trace["stageLabel"] = PROVIDER_TRACE_STAGE_LABELS.get(stage, stage.replace("_", " ").title())
            self.update_provider_trace(provider_trace)

        for assignment_index, assignment in enumerate(assignment_candidates):
            current_api_key = str(assignment.get("apiKey", "")).strip()
            if not current_api_key:
                continue
            attempts = self.build_output_token_attempts(max_output_tokens, target_kind, provider="xai", model=model)
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
                            "text": {
                                "verbosity": "low",
                                "format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema},
                            },
                        }
                        if self.xai_accepts_reasoning_effort(model):
                            body["reasoning"] = {"effort": reasoning_effort}
                        if previous_response_id:
                            body["previous_response_id"] = previous_response_id
                        if effective_tokens > 0:
                            body["max_output_tokens"] = effective_tokens
                        if tools:
                            body["tools"] = tools
                        if tool_choice is not None:
                            body["tool_choice"] = tool_choice
                        if include and any(str(item or "").strip() for item in include):
                            body["include"] = [item for item in include if str(item or "").strip() in {"no_inline_citations"}]

                        request = urllib.request.Request(
                            self.xai_responses_url(),
                            data=json.dumps(body).encode("utf-8"),
                            headers={"Authorization": f"Bearer {current_api_key}", "Content-Type": "application/json"},
                            method="POST",
                        )
                        report_trace(
                            "sending",
                            requestCount=int(provider_trace.get("requestCount") or 0) + 1,
                            attemptIndex=index + 1,
                            effectiveMaxOutputTokens=effective_tokens,
                            toolTurn=tool_turns,
                            authKeySlot=int(assignment.get("keySlot", 0) or 0) if assignment.get("keySlot") is not None else None,
                            authMasked=str(assignment.get("masked", "")).strip() or None,
                            requestUrl=request.full_url,
                            sentAt=utc_now(),
                        )
                        try:
                            with urllib.request.urlopen(request, timeout=request_timeout_seconds) as handle:
                                header_map = self.provider_trace_header_map(handle)
                                report_trace(
                                    "headers",
                                    headersAt=utc_now(),
                                    httpStatus=getattr(handle, "status", None) or getattr(handle, "code", None) or 200,
                                    **self.provider_trace_from_headers("xai", header_map),
                                )
                                response = json.loads(handle.read().decode("utf-8"))
                        except urllib.error.HTTPError as error:
                            body_text = error.read().decode("utf-8", errors="replace")
                            header_map = self.provider_trace_header_map(error)
                            report_trace(
                                "error",
                                headersAt=utc_now(),
                                completedAt=utc_now(),
                                httpStatus=error.code,
                                error=f"HTTP {error.code}",
                                **self.provider_trace_from_headers("xai", header_map),
                            )
                            raise RuntimeErrorWithCode(f"xAI API request failed: HTTP {error.code} | {body_text}", 500)
                        except Exception as error:
                            if self.is_request_timeout_error(error):
                                report_trace("timeout", completedAt=utc_now(), error=f"Timed out after {request_timeout_seconds}s")
                                raise RuntimeErrorWithCode(
                                    f"xAI API request timed out after {request_timeout_seconds}s.",
                                    504,
                                )
                            report_trace("error", completedAt=utc_now(), error=str(error))
                            raise RuntimeErrorWithCode(f"xAI API request failed: {error}", 500)

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
                            report_trace(
                                "retrying",
                                completedAt=utc_now(),
                                responseStatus=str(response.get("status", "")).strip() or None,
                                incompleteReason=incomplete_reason,
                                providerResponseId=str(response.get("id", "")).strip() or None,
                            )
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
                            parsed = parse_structured_output_text(output_text)
                        except RuntimeErrorWithCode:
                            if response.get("status") == "incomplete" and incomplete_reason:
                                detail = f"Model response incomplete: {incomplete_reason}"
                                if incomplete_reason == "max_output_tokens":
                                    detail += f" after attempts {attempts}"
                                raise RuntimeErrorWithCode(detail, 500)
                            raise

                        return OpenAIResult(
                            provider="xai",
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
                            provider_trace=self.update_provider_trace(
                                {
                                    **provider_trace,
                                    "stage": "completed",
                                    "stageLabel": PROVIDER_TRACE_STAGE_LABELS["completed"],
                                    "completedAt": utc_now(),
                                    "providerResponseId": str(response.get("id", "")).strip() or None,
                                    "responseStatus": str(response.get("status", "completed")).strip() or "completed",
                                    "toolTurn": tool_turns,
                                    "localToolCallCount": len(executed_tools),
                                    "webSearchQueryCount": len(web_search_queries),
                                }
                            ),
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

    def invoke_anthropic_messages_json(
        self,
        provider: str,
        api_key: str,
        model: str,
        instructions: str,
        input_text: str,
        schema: Dict[str, Any],
        max_output_tokens: int = 0,
        target_kind: str = "generic",
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        function_handlers: Optional[Dict[str, Any]] = None,
        auth_assignments: Optional[List[Dict[str, Any]]] = None,
        request_timeout_seconds: int = 1800,
    ) -> OpenAIResult:
        normalized_provider = normalize_provider_id(provider, "anthropic")
        provider_label = provider_capability_profile(normalized_provider)["provider"]
        handlers = function_handlers if isinstance(function_handlers, dict) else {}
        assignment_candidates = [dict(entry) for entry in (auth_assignments or []) if isinstance(entry, dict) and str(entry.get("apiKey", "")).strip()]
        if not assignment_candidates and str(api_key or "").strip():
            assignment_candidates = [{"apiKey": str(api_key).strip()}]
        if not assignment_candidates:
            raise RuntimeErrorWithCode("No API key available for live model call.", 401)

        messages_tools: List[Dict[str, Any]] = []
        if tools:
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                tool_type = str(tool.get("type", "")).strip()
                if tool_type == "web_search":
                    if normalized_provider != "anthropic":
                        raise RuntimeErrorWithCode(
                            f"provider_does_not_support: {PROVIDER_CATALOG[normalized_provider]['label']} live mode does not yet support built-in web search in this runtime.",
                            400,
                        )
                    converted_tool: Dict[str, Any] = {"type": "web_search_20250305", "name": "web_search"}
                    filters = tool.get("filters") if isinstance(tool.get("filters"), dict) else {}
                    allowed_domains = normalize_string_array_preserve_items(filters.get("allowed_domains", []))
                    if allowed_domains:
                        converted_tool["allowed_domains"] = allowed_domains
                    messages_tools.append(converted_tool)
                    continue
                if tool_type == "function":
                    messages_tools.extend(self.convert_function_tools_to_anthropic([tool]))
                    continue
                raise RuntimeErrorWithCode(
                    f"provider_does_not_support: Unsupported tool type {tool_type or 'unknown'} for {PROVIDER_CATALOG[normalized_provider]['label']} in this runtime.",
                    400,
                )

        auth_failover_history: List[Dict[str, Any]] = []
        last_error: Optional[RuntimeErrorWithCode] = None
        provider_trace = self.build_provider_trace_base(normalized_provider, model, target_kind, request_timeout_seconds)

        def report_trace(stage: str, **updates: Any) -> None:
            provider_trace.update({key: value for key, value in updates.items() if value is not None})
            provider_trace["stage"] = stage
            provider_trace["stageLabel"] = PROVIDER_TRACE_STAGE_LABELS.get(stage, stage.replace("_", " ").title())
            self.update_provider_trace(provider_trace)

        for assignment_index, assignment in enumerate(assignment_candidates):
            current_api_key = str(assignment.get("apiKey", "")).strip()
            if not current_api_key:
                continue
            attempts = self.build_output_token_attempts(
                max_output_tokens,
                target_kind,
                provider=normalized_provider,
                model=model,
                require_explicit_max=True,
            )
            recovered_from_incomplete = False

            try:
                for index, effective_tokens in enumerate(attempts):
                    messages: List[Dict[str, Any]] = [
                        {"role": "user", "content": [{"type": "text", "text": input_text}]}
                    ]
                    tool_turns = 0
                    pause_turns = 0
                    web_search_queries: Dict[str, bool] = {}
                    web_search_sources: Dict[str, bool] = {}
                    url_citations: Dict[str, bool] = {}
                    executed_tools: List[Dict[str, Any]] = []
                    retry_attempt = False

                    while True:
                        effective_instructions = instructions
                        if normalized_provider == "minimax":
                            effective_instructions = (
                                str(instructions or "").rstrip()
                                + "\nReturn raw JSON text only."
                                + "\nDo not use markdown fences."
                                + "\nDo not add commentary before or after the JSON object."
                                + "\nEscape every newline inside string values as \\\\n and every tab as \\\\t."
                            ).strip()
                        transport_max_tokens = max(1, int(effective_tokens or 0))
                        body: Dict[str, Any] = {
                            "model": model,
                            "max_tokens": transport_max_tokens,
                            "system": effective_instructions,
                            "messages": messages,
                        }
                        if messages_tools:
                            body["tools"] = messages_tools
                        converted_tool_choice = self.anthropic_tool_choice(tool_choice)
                        if converted_tool_choice:
                            body["tool_choice"] = converted_tool_choice

                        request = urllib.request.Request(
                            self.anthropic_messages_url(normalized_provider),
                            data=json.dumps(body).encode("utf-8"),
                            headers={
                                "x-api-key": current_api_key,
                                "anthropic-version": "2023-06-01",
                                "Content-Type": "application/json",
                            },
                            method="POST",
                        )
                        report_trace(
                            "sending",
                            requestCount=int(provider_trace.get("requestCount") or 0) + 1,
                            attemptIndex=index + 1,
                            effectiveMaxOutputTokens=effective_tokens,
                            toolTurn=tool_turns,
                            authKeySlot=int(assignment.get("keySlot", 0) or 0) if assignment.get("keySlot") is not None else None,
                            authMasked=str(assignment.get("masked", "")).strip() or None,
                            requestUrl=request.full_url,
                            sentAt=utc_now(),
                        )
                        try:
                            with urllib.request.urlopen(request, timeout=request_timeout_seconds) as handle:
                                header_map = self.provider_trace_header_map(handle)
                                report_trace(
                                    "headers",
                                    headersAt=utc_now(),
                                    httpStatus=getattr(handle, "status", None) or getattr(handle, "code", None) or 200,
                                    **self.provider_trace_from_headers(normalized_provider, header_map),
                                )
                                response = json.loads(handle.read().decode("utf-8"))
                        except urllib.error.HTTPError as error:
                            body_text = error.read().decode("utf-8", errors="replace")
                            header_map = self.provider_trace_header_map(error)
                            report_trace(
                                "error",
                                headersAt=utc_now(),
                                completedAt=utc_now(),
                                httpStatus=error.code,
                                error=f"HTTP {error.code}",
                                **self.provider_trace_from_headers(normalized_provider, header_map),
                            )
                            raise RuntimeErrorWithCode(f"{PROVIDER_CATALOG[normalized_provider]['label']} API request failed: HTTP {error.code} | {body_text}", 500)
                        except Exception as error:
                            if self.is_request_timeout_error(error):
                                report_trace("timeout", completedAt=utc_now(), error=f"Timed out after {request_timeout_seconds}s")
                                raise RuntimeErrorWithCode(
                                    f"{PROVIDER_CATALOG[normalized_provider]['label']} API request timed out after {request_timeout_seconds}s.",
                                    504,
                                )
                            report_trace("error", completedAt=utc_now(), error=str(error))
                            raise RuntimeErrorWithCode(f"{PROVIDER_CATALOG[normalized_provider]['label']} API request failed: {error}", 500)

                        if isinstance(response.get("error"), dict):
                            raise RuntimeErrorWithCode(f"Model response error: {json.dumps(response['error'], ensure_ascii=False)}", 500)

                        for query in self.get_response_web_search_queries(response):
                            web_search_queries[query] = True
                        for source in self.get_response_web_search_sources(response):
                            web_search_sources[source] = True
                        for citation in self.get_response_url_citations(response):
                            url_citations[citation] = True

                        stop_reason = str(response.get("stop_reason", "")).strip()
                        content_blocks = response.get("content") if isinstance(response.get("content"), list) else []

                        tool_calls: List[Dict[str, Any]] = []
                        if handlers:
                            for block in content_blocks:
                                if not isinstance(block, dict):
                                    continue
                                if str(block.get("type", "")).strip() != "tool_use":
                                    continue
                                name = str(block.get("name", "")).strip()
                                if name not in handlers:
                                    continue
                                tool_calls.append(block)

                        if tool_calls:
                            if tool_turns >= 8:
                                raise RuntimeErrorWithCode("Model exceeded the allowed local tool turn count.", 500)
                            messages.append({"role": "assistant", "content": content_blocks})
                            continuation_blocks: List[Dict[str, Any]] = []
                            for block in tool_calls:
                                name = str(block.get("name", "")).strip()
                                arguments = block.get("input") if isinstance(block.get("input"), dict) else {}
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
                                if block.get("id"):
                                    audit_entry["callId"] = str(block.get("id"))
                                executed_tools.append(audit_entry)
                                continuation_blocks.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": str(block.get("id", "")),
                                        "content": json.dumps(tool_output, ensure_ascii=False),
                                    }
                                )
                            messages.append({"role": "user", "content": continuation_blocks})
                            tool_turns += 1
                            continue

                        if stop_reason == "pause_turn":
                            if pause_turns >= 4:
                                raise RuntimeErrorWithCode("Model exceeded the allowed paused-turn continuation count.", 500)
                            messages.append({"role": "assistant", "content": content_blocks})
                            pause_turns += 1
                            continue

                        output_text = self.get_response_output_text(response)
                        if not output_text:
                            if stop_reason == "max_tokens" and index < len(attempts) - 1:
                                report_trace(
                                    "retrying",
                                    completedAt=utc_now(),
                                    responseStatus=stop_reason,
                                    providerResponseId=str(response.get("id", "")).strip() or None,
                                )
                                recovered_from_incomplete = True
                                retry_attempt = True
                                break
                            raise RuntimeErrorWithCode("Model response did not include output_text.", 500)

                        try:
                            parsed = parse_structured_output_text(output_text)
                        except RuntimeErrorWithCode:
                            salvaged = (
                                salvage_direct_answer_payload(normalized_provider, output_text)
                                if schema_looks_like_direct_answer(schema)
                                else None
                            )
                            if salvaged is not None:
                                parsed = salvaged
                            else:
                                if stop_reason == "max_tokens" and index < len(attempts) - 1:
                                    recovered_from_incomplete = True
                                    retry_attempt = True
                                    break
                                raise

                        return OpenAIResult(
                            provider=normalized_provider,
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
                            provider_trace=self.update_provider_trace(
                                {
                                    **provider_trace,
                                    "stage": "completed",
                                    "stageLabel": PROVIDER_TRACE_STAGE_LABELS["completed"],
                                    "completedAt": utc_now(),
                                    "providerResponseId": str(response.get("id", "")).strip() or None,
                                    "responseStatus": stop_reason or "completed",
                                    "toolTurn": tool_turns,
                                    "localToolCallCount": len(executed_tools),
                                    "webSearchQueryCount": len(web_search_queries),
                                }
                            ),
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
        raise RuntimeErrorWithCode(f"{provider_label} response did not produce a usable structured output.", 500)

    def ollama_chat_url(self, base_url: Optional[str] = None) -> str:
        base = normalize_ollama_base_url(base_url)
        if base.endswith("/api"):
            return base + "/chat"
        return base + "/api/chat"

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
        tools: Optional[List[Dict[str, Any]]] = None,
        function_handlers: Optional[Dict[str, Any]] = None,
        base_url: Optional[str] = None,
        provider_instance: Optional[Dict[str, Any]] = None,
        request_timeout_seconds: int = 1800,
    ) -> OpenAIResult:
        attempts = self.build_output_token_attempts(max_output_tokens, target_kind, provider="ollama", model=model)
        last_error: Optional[RuntimeErrorWithCode] = None
        api_key = self.ollama_api_key()
        ollama_tools = self.convert_function_tools_to_ollama(tools)
        handlers = function_handlers if isinstance(function_handlers, dict) else {}
        provider_trace = self.build_provider_trace_base("ollama", model, target_kind, request_timeout_seconds)
        normalized_instance = normalize_provider_instance_entry(provider_instance, "ollama") if isinstance(provider_instance, dict) else None
        if isinstance(normalized_instance, dict):
            provider_trace["providerInstanceId"] = str(normalized_instance.get("id") or "").strip() or None
            provider_trace["providerInstanceLabel"] = str(normalized_instance.get("label") or "").strip() or None
            provider_trace["providerEndpoint"] = normalize_ollama_base_url(normalized_instance.get("baseUrl"))

        def report_trace(stage: str, **updates: Any) -> None:
            provider_trace.update({key: value for key, value in updates.items() if value is not None})
            provider_trace["stage"] = stage
            provider_trace["stageLabel"] = PROVIDER_TRACE_STAGE_LABELS.get(stage, stage.replace("_", " ").title())
            self.update_provider_trace(provider_trace)

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
            executed_tools: List[Dict[str, Any]] = []
            tool_turns = 0
            while True:
                body: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "format": schema,
                    "options": {},
                }
                if ollama_tools:
                    body["tools"] = ollama_tools
                if effective_tokens > 0:
                    body["options"]["num_predict"] = effective_tokens
                if not body["options"]:
                    body.pop("options", None)

                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                request = urllib.request.Request(
                    self.ollama_chat_url(base_url),
                    data=json.dumps(body).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                report_trace(
                    "sending",
                    requestCount=int(provider_trace.get("requestCount") or 0) + 1,
                    attemptIndex=max(1, attempts.index(effective_tokens) + 1 if effective_tokens in attempts else 1),
                    effectiveMaxOutputTokens=effective_tokens,
                    toolTurn=tool_turns,
                    requestUrl=request.full_url,
                    sentAt=utc_now(),
                )
                try:
                    with urllib.request.urlopen(request, timeout=request_timeout_seconds) as handle:
                        header_map = self.provider_trace_header_map(handle)
                        report_trace(
                            "headers",
                            headersAt=utc_now(),
                            httpStatus=getattr(handle, "status", None) or getattr(handle, "code", None) or 200,
                            **self.provider_trace_from_headers("ollama", header_map),
                        )
                        response = json.loads(handle.read().decode("utf-8"))
                except urllib.error.HTTPError as error:
                    body_text = error.read().decode("utf-8", errors="replace")
                    header_map = self.provider_trace_header_map(error)
                    report_trace(
                        "error",
                        headersAt=utc_now(),
                        completedAt=utc_now(),
                        httpStatus=error.code,
                        error=f"HTTP {error.code}",
                        **self.provider_trace_from_headers("ollama", header_map),
                    )
                    raise RuntimeErrorWithCode(f"Ollama API request failed: HTTP {error.code} | {body_text}", 500)
                except Exception as error:
                    if self.is_request_timeout_error(error):
                        report_trace("timeout", completedAt=utc_now(), error=f"Timed out after {request_timeout_seconds}s")
                        raise RuntimeErrorWithCode(
                            f"Ollama API request timed out after {request_timeout_seconds}s.",
                            504,
                        )
                    report_trace("error", completedAt=utc_now(), error=str(error))
                    raise RuntimeErrorWithCode(f"Ollama API request failed: {error}", 500)

                message_node = response.get("message") if isinstance(response.get("message"), dict) else {}
                raw_tool_calls = message_node.get("tool_calls") if isinstance(message_node.get("tool_calls"), list) else []
                tool_calls: List[Dict[str, Any]] = []
                if ollama_tools and handlers:
                    for item in raw_tool_calls:
                        if not isinstance(item, dict):
                            continue
                        function_node = item.get("function") if isinstance(item.get("function"), dict) else {}
                        name = str(function_node.get("name", "")).strip()
                        if name not in handlers:
                            continue
                        tool_calls.append(item)

                if tool_calls:
                    if tool_turns >= 8:
                        raise RuntimeErrorWithCode("Model exceeded the allowed local tool turn count.", 500)
                    assistant_message: Dict[str, Any] = {
                        "role": "assistant",
                        "content": str(message_node.get("content", "") or ""),
                        "tool_calls": tool_calls,
                    }
                    if message_node.get("thinking"):
                        assistant_message["thinking"] = str(message_node.get("thinking"))
                    messages.append(assistant_message)
                    for item in tool_calls:
                        function_node = item.get("function") if isinstance(item.get("function"), dict) else {}
                        name = str(function_node.get("name", "")).strip()
                        raw_arguments = function_node.get("arguments")
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
                        executed_tools.append(audit_entry)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_name": name,
                                "content": json.dumps(tool_output, ensure_ascii=False),
                            }
                        )
                    tool_turns += 1
                    continue

                output_text = self.get_response_output_text(response)
                if not output_text:
                    last_error = RuntimeErrorWithCode("Ollama response did not include message.content.", 500)
                    break
                try:
                    parsed = parse_structured_output_text(output_text)
                except RuntimeErrorWithCode as error:
                    last_error = error
                    break

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
                    executed_tools=executed_tools,
                    auth_assignment=None,
                    auth_failover_history=[],
                    provider_trace=self.update_provider_trace(
                        {
                            **provider_trace,
                            "stage": "completed",
                            "stageLabel": PROVIDER_TRACE_STAGE_LABELS["completed"],
                            "completedAt": utc_now(),
                            "providerResponseId": response_id,
                            "responseStatus": "completed" if bool(response.get("done")) else "partial",
                            "toolTurn": tool_turns,
                            "localToolCallCount": len(executed_tools),
                            "ollamaTotalDurationMs": self.provider_trace_ms_from_ns(response.get("total_duration")),
                            "ollamaLoadDurationMs": self.provider_trace_ms_from_ns(response.get("load_duration")),
                            "ollamaPromptEvalCount": self.provider_trace_int(response.get("prompt_eval_count")),
                            "ollamaPromptEvalDurationMs": self.provider_trace_ms_from_ns(response.get("prompt_eval_duration")),
                            "ollamaEvalCount": self.provider_trace_int(response.get("eval_count")),
                            "ollamaEvalDurationMs": self.provider_trace_ms_from_ns(response.get("eval_duration")),
                        }
                    ),
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
        provider_settings: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> OpenAIResult:
        normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
        request_timeout_seconds = clamp_timeout_seconds(
            (provider_settings or {}).get("requestTimeoutSeconds"),
            target_timeout_seconds(default_target_timeout_config(), target_kind),
        )
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
                request_timeout_seconds=request_timeout_seconds,
            )
        if normalized_provider == "xai":
            return self.invoke_xai_json(
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
                request_timeout_seconds=request_timeout_seconds,
            )
        if normalized_provider == "deepseek":
            if include:
                include = None
            deepseek_transport = self.deepseek_transport_mode(provider_settings if isinstance(provider_settings, dict) else None)
            if deepseek_transport == "anthropic":
                return self.invoke_anthropic_messages_json(
                    provider=normalized_provider,
                    api_key=api_key,
                    model=model,
                    instructions=instructions,
                    input_text=input_text,
                    schema=schema,
                    max_output_tokens=max_output_tokens,
                    target_kind=target_kind,
                    tools=tools,
                    tool_choice=tool_choice,
                    function_handlers=function_handlers,
                    auth_assignments=auth_assignments,
                    request_timeout_seconds=request_timeout_seconds,
                )
            return self.invoke_deepseek_openai_json(
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
                function_handlers=function_handlers,
                auth_assignments=auth_assignments,
                request_timeout_seconds=request_timeout_seconds,
                task_id=task_id,
            )
        if normalized_provider == "minimax":
            if include:
                include = None
            minimax_transport = self.minimax_transport_mode(provider_settings if isinstance(provider_settings, dict) else None)
            if minimax_transport == "anthropic":
                return self.invoke_anthropic_messages_json(
                    provider=normalized_provider,
                    api_key=api_key,
                    model=model,
                    instructions=instructions,
                    input_text=input_text,
                    schema=schema,
                    max_output_tokens=max_output_tokens,
                    target_kind=target_kind,
                    tools=tools,
                    tool_choice=tool_choice,
                    function_handlers=function_handlers,
                    auth_assignments=auth_assignments,
                    request_timeout_seconds=request_timeout_seconds,
                )
            return self.invoke_minimax_openai_json(
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
                function_handlers=function_handlers,
                auth_assignments=auth_assignments,
                request_timeout_seconds=request_timeout_seconds,
                task_id=task_id,
            )
        if normalized_provider == "anthropic":
            if include:
                include = None
            return self.invoke_anthropic_messages_json(
                provider=normalized_provider,
                api_key=api_key,
                model=model,
                instructions=instructions,
                input_text=input_text,
                schema=schema,
                max_output_tokens=max_output_tokens,
                target_kind=target_kind,
                tools=tools,
                tool_choice=tool_choice,
                function_handlers=function_handlers,
                auth_assignments=auth_assignments,
                request_timeout_seconds=request_timeout_seconds,
            )
        if normalized_provider == "ollama":
            normalized_tools = [tool for tool in (tools or []) if isinstance(tool, dict)]
            unsupported_tool_types = sorted(
                {
                    str(tool.get("type", "")).strip() or "unknown"
                    for tool in normalized_tools
                    if str(tool.get("type", "")).strip() != "function"
                }
            )
            if unsupported_tool_types:
                raise RuntimeErrorWithCode(
                    "provider_does_not_support: Ollama live mode only supports local function tools in this runtime"
                    + f" (unsupported: {', '.join(unsupported_tool_types)}).",
                    400,
                )
            normalized_tool_choice = ""
            if tool_choice is not None:
                if not isinstance(tool_choice, str):
                    raise RuntimeErrorWithCode(
                        "provider_does_not_support: Ollama live mode only supports tool_choice 'auto' for local function tools.",
                        400,
                    )
                normalized_tool_choice = tool_choice.strip().lower()
                if normalized_tool_choice not in {"auto", "none"}:
                    raise RuntimeErrorWithCode(
                        "provider_does_not_support: Ollama live mode only supports tool_choice 'auto' for local function tools.",
                        400,
                    )
            if include:
                include = None
            if normalized_tool_choice == "none":
                normalized_tools = []
                function_handlers = None
            ollama_base_url = None
            if isinstance(provider_settings, dict) and provider_settings.get("ollamaBaseUrl") is not None:
                ollama_base_url = str(provider_settings.get("ollamaBaseUrl"))
            provider_instance = provider_settings.get("providerInstance") if isinstance(provider_settings, dict) else None
            return self.invoke_ollama_json(
                model=model,
                instructions=instructions,
                input_text=input_text,
                schema=schema,
                max_output_tokens=max_output_tokens,
                target_kind=target_kind,
                tools=normalized_tools,
                function_handlers=function_handlers,
                base_url=ollama_base_url,
                provider_instance=provider_instance if isinstance(provider_instance, dict) else None,
                request_timeout_seconds=request_timeout_seconds,
            )
        raise RuntimeErrorWithCode(f"provider_not_configured: Unsupported provider {normalized_provider}.", 400)

    def build_output_token_attempts(
        self,
        requested_max_output_tokens: int,
        target_kind: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        require_explicit_max: bool = False,
    ) -> List[int]:
        requested = max(0, int(requested_max_output_tokens or 0))
        model_ceiling = model_capacities.max_output_tokens(provider, model)
        if requested <= 0:
            if require_explicit_max:
                explicit_ceiling = model_ceiling or model_capacities.explicit_output_fallback_tokens(provider)
                return [max(0, int(explicit_ceiling or 0))]
            return [0]

        retry_policy = model_capacities.output_retry_policy(target_kind)
        floor = int(retry_policy["floor"])
        retry_floor = int(retry_policy["retryFloor"])
        hard_ceiling = model_ceiling or int(retry_policy["fallbackCeiling"])

        initial = min(max(requested, floor), hard_ceiling) if hard_ceiling > 0 else max(requested, floor)
        attempts = [initial]

        retry_candidate = max(initial * 2, retry_floor)
        if hard_ceiling > 0:
            retry_candidate = min(retry_candidate, max(initial, hard_ceiling))
        if retry_candidate > initial:
            attempts.append(retry_candidate)
        final_candidate = max(retry_candidate * 2, retry_floor)
        if hard_ceiling > 0:
            final_candidate = min(final_candidate, hard_ceiling)
        if final_candidate > retry_candidate:
            attempts.append(final_candidate)
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
                normalize_provider_id((task.get("runtime") or {}).get("provider"), DEFAULT_PROVIDER_ID),
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

    def new_offline_fixture_commander(
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
        skill_context = build_runtime_skill_context(runtime["provider"], "commander")
        worker_context_mode = normalize_context_mode(runtime.get("contextMode"))
        main_thread_context_mode = "full"
        session_context = str(task.get("sessionContext", "")).strip()
        summary_projection = self.project_prior_summary_for_worker(prior_summary)
        summary_text = json.dumps(summary_projection, ensure_ascii=False, indent=2) if summary_projection else "none"
        task_brief = self.project_task_for_adjudication(task)
        local_file_config = normalize_local_file_tool_config(runtime.get("localFiles") if isinstance(runtime.get("localFiles"), dict) else {})
        github_tool_config = normalize_github_tool_config(runtime.get("githubTools") if isinstance(runtime.get("githubTools"), dict) else {})
        knowledgebase_packet = self.build_knowledgebase_recall_packet(
            task,
            runtime,
            "commander",
            label="Commander",
            role="lead",
            focus="first-pass answer direction",
            round_number=round_number,
            constraints=constraints,
            prior_summary=prior_summary,
        )
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
                "Main-thread full context is active. Read the fuller background packet below, but Objective and current Constraints still win on conflicts.\n"
                + (
                    "Workers for this task are set to Light Workers mode, so later adversarial lanes will receive weighted digests instead of the full packet.\n"
                    if worker_context_mode == "weighted"
                    else
                    "Workers for this task are set to Full Workers mode, so later adversarial lanes will also receive the fuller background packet.\n"
                )
            )
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
            + skill_context["prompt"]
            + "\nReturn JSON only that matches the schema exactly."
        )
        input_text = (
            f"Authoritative current user input:\n{task.get('objective', '')}\n\n"
            f"Current constraints:\n{chr(10).join(constraints) if constraints else 'none'}\n\n"
            + self.build_context_weight_block(
                worker_context_mode,
                [
                    ("objective", "primary"),
                    ("constraints", "high"),
                    ("prior summary", "medium"),
                    ("session context", "low"),
                ],
            )
            + f"Carry-forward session context (background only, not authoritative):\n{session_context or 'none'}\n\n"
            + f"Prior adjudicated summary (background only):\n{summary_text}\n\n"
            + self.render_knowledgebase_prompt_block(knowledgebase_packet)
            + self.build_full_context_block(
                main_thread_context_mode,
                [
                    ("Task brief", json.dumps(task_brief, ensure_ascii=False, indent=2)),
                ],
            )
            + "Produce the commander's first-pass answer direction for this round."
        )
        input_text = self.maybe_compact_prompt_text(input_text, runtime, "commander")
        provider_settings = self.resolve_provider_settings(task, runtime, runtime["provider"], runtime["model"], "commander", round_number)
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
            provider_settings=provider_settings,
            task_id=str(task["taskId"]),
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
            "skills": skill_context["names"],
            "providerTrace": result.provider_trace,
            "auth": result.auth_assignment,
            "authFailoverHistory": result.auth_failover_history,
            "localToolCalls": parsed["localToolCalls"],
            "localFileSources": parsed["localFileSources"],
            "githubToolCalls": parsed["githubToolCalls"],
            "githubSources": parsed["githubSources"],
            "knowledgebaseRecall": self.knowledgebase_call_meta(knowledgebase_packet),
        }
        return parsed, result.response_id, result.response, call_meta

    def commander_review_schema(self) -> Dict[str, Any]:
        return self.commander_review_schema_for_mode(compact=False)

    def provider_prefers_compact_commander_review(self, provider: Optional[str], model: Optional[str]) -> bool:
        return model_prefers_compact_context(provider, model)

    def commander_review_schema_for_mode(self, compact: bool = False) -> Dict[str, Any]:
        if compact:
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
                    "claimsToStrengthen",
                    "claimsToLimit",
                    "requiredDecisionGates",
                    "evidenceOrCommsRisks",
                    "discardedPressure",
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
                    "claimsToStrengthen": {"type": "array", "items": {"type": "string"}},
                    "claimsToLimit": {"type": "array", "items": {"type": "string"}},
                    "requiredDecisionGates": {"type": "array", "items": {"type": "string"}},
                    "evidenceOrCommsRisks": {"type": "array", "items": {"type": "string"}},
                    "discardedPressure": {"type": "array", "items": {"type": "string"}},
                    "remainingUncertainty": {"type": "array", "items": {"type": "string"}},
                    "sourceWorkers": {"type": "array", "items": {"type": "string"}},
                },
            }
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
                "claimsToStrengthen",
                "claimsToLimit",
                "requiredDecisionGates",
                "evidenceOrCommsRisks",
                "discardedPressure",
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
                "claimsToStrengthen": {"type": "array", "items": {"type": "string"}},
                "claimsToLimit": {"type": "array", "items": {"type": "string"}},
                "requiredDecisionGates": {"type": "array", "items": {"type": "string"}},
                "evidenceOrCommsRisks": {"type": "array", "items": {"type": "string"}},
                "discardedPressure": {"type": "array", "items": {"type": "string"}},
                "remainingUncertainty": {"type": "array", "items": {"type": "string"}},
                "sourceWorkers": {"type": "array", "items": {"type": "string"}},
            },
        }

    def new_offline_fixture_commander_review(
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
        decision_gates: List[str] = []
        evidence_or_comms_risks: List[str] = []
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
            for item in limit_string_list(checkpoint.get("invalidatingCircumstances", []), 1, 180):
                decision_gates.append(item)
            for item in (
                limit_string_list(checkpoint.get("evidenceGaps", []), 1, 180)
                + limit_string_list(checkpoint.get("uncertainty", []), 1, 180)
            ):
                evidence_or_comms_risks.append(item)
        strongest_points = strongest_points[:3]
        held_out = limit_string_list(held_out, 3, 220)
        decision_gates = limit_string_list(decision_gates, 3, 220)
        evidence_or_comms_risks = limit_string_list(evidence_or_comms_risks, 3, 220)
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
                    "courseDecisionReason": "Offline fixture reevaluation defaults to maintaining course unless a worker checkpoint clearly invalidates the lead direction.",
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
                    "reason": "Offline fixture commander review did not identify a clearly missing adversarial lane.",
                    "requiredPressure": "",
                    "temperature": "",
                    "instruction": "",
                },
                "claimsToStrengthen": strongest_points,
                "claimsToLimit": held_out,
                "requiredDecisionGates": decision_gates,
                "evidenceOrCommsRisks": evidence_or_comms_risks,
                "discardedPressure": [],
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
        prior_summary: Optional[Dict[str, Any]],
        workers: List[Dict[str, str]],
        worker_state: Dict[str, Any],
        runtime: Dict[str, Any],
        line_catalog: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], str, Dict[str, Any], Dict[str, Any]]:
        review_config = commander_review_config(task)
        harness_lines = summarizer_harness_instruction_lines(review_config.get("harness"))
        compact_review = self.provider_prefers_compact_commander_review(runtime["provider"], runtime["model"])
        skill_context = build_runtime_skill_context(runtime["provider"], "commander_review", compact=compact_review)
        worker_context_mode = normalize_context_mode(runtime.get("contextMode"))
        main_thread_context_mode = "full"
        constraints = limit_string_list(task.get("constraints", []), 24, 400)
        session_context = str(task.get("sessionContext", "")).strip()
        commander_projection = self.project_commander_for_summary(commander_checkpoint)
        round_number = int(commander_projection.get("round", 0) or 1)
        worker_projection = self.project_worker_state_for_adjudication(worker_state, workers)
        task_brief = self.project_task_for_adjudication(task)
        lane_type_catalog = normalize_lane_type_list(list(WORKER_TYPE_CATALOG.keys()), False, 12)
        source_workers = [worker["id"] for worker in workers if isinstance(worker_state.get(worker["id"]), dict)]
        knowledgebase_packet = self.build_knowledgebase_recall_packet(
            task,
            runtime,
            "commander_review",
            label="Commander Review",
            role="lead_review",
            focus="pressure-filtered lead decision",
            round_number=round_number,
            constraints=constraints,
            prior_summary=prior_summary,
            commander_checkpoint=commander_checkpoint,
        )
        if compact_review:
            instructions = (
                "You have just completed an internal pressure test on the lead thread's first-pass answer.\n"
                "The commander already produced a first-pass direction. The workers have now pressure-tested it.\n"
                "Do not write the final public answer yet.\n"
                "Produce only the compact lead-thread binder that the summarizer should think from after pressure.\n"
                "Treat this stage as a pressure filter and cohesive binder, not as a debate recap.\n"
                "leadDirection should state the surviving answer direction after pressure.\n"
                "answerDraft should be the revised lead draft after pressure.\n"
                "whyThisDirection should explain briefly why that direction still holds.\n"
                "claimsToStrengthen should hold the 1 to 4 ideas that must survive more clearly or more forcefully.\n"
                "claimsToLimit should hold the 1 to 4 claims that must stay narrower, more conditional, or less confident.\n"
                "requiredDecisionGates should hold the explicit gates the final answer must retain before disruptive action.\n"
                "evidenceOrCommsRisks should hold the evidence-handling, tenant-boundary, or communication risks that must stay visible.\n"
                "remainingUncertainty should hold what still stays unresolved after reevaluation.\n"
                "If you include stance, make it one short sentence. If you include sourceWorkers, list only workers that materially changed the lead.\n"
                "Default to maintain when objections only add evidence, conditions, or guardrails.\n"
                "Use qualify when the lead stays on course but needs narrower scope, stronger conditions, or sharper caveats.\n"
                "Use redirect when the destination changes while still serving the user's core goal.\n"
                "Use reverse only when the current lead answer would now be materially wrong, unsafe, or misleading.\n"
                "Indecisive drift is worse than a clear qualified answer when reversal is not justified.\n"
                "Do not mention workers, lanes, or hidden process in answerDraft.\n"
                + "\n".join(harness_lines)
                + skill_context["prompt"]
                + "\nReturn JSON only that matches the schema exactly."
            )
            input_text = (
                f"Current incident request:\n{task.get('objective', '')}\n\n"
                f"Current constraints:\n{chr(10).join(constraints) if constraints else 'none'}\n\n"
                f"Background context:\n{session_context or 'none'}\n\n"
                + self.render_knowledgebase_prompt_block(knowledgebase_packet)
                + f"Initial commander draft for this round:\n{json.dumps(commander_projection, ensure_ascii=False, indent=2)}\n\n"
                + f"Worker checkpoint digests:\n{json.dumps(worker_projection, ensure_ascii=False, indent=2)}"
            )
        else:
            instructions = (
                "You have just completed an internal pressure test on the lead thread's first-pass answer.\n"
                "The commander already produced a first-pass direction. The workers have now pressure-tested it.\n"
                "Your job is to decide whether the lead thread should maintain, qualify, redirect, or reverse before any public answer is written.\n"
                "This is the authoritative lead-thread reevaluation for the round.\n"
                "Read the full current user input, the original commander draft, and the worker checkpoints.\n"
                "Do not write the final public answer yet. Produce the revised lead answer that the summarizer will later present cleanly.\n"
                "Use stance, leadDirection, answerDraft, and whyThisDirection for the revised lead position after adversarial pressure.\n"
                "Treat this stage as a pressure filter and cohesive binder, not as a debate recap.\n"
                "Use claimsToStrengthen for the 1 to 4 ideas that should survive into the final answer more clearly or more forcefully.\n"
                "Use claimsToLimit for the 1 to 4 claims that should stay narrower, more conditional, or less confident after pressure.\n"
                "Use requiredDecisionGates for the explicit gates the final answer must retain before taking disruptive action.\n"
                "Use evidenceOrCommsRisks for the evidence-handling, tenant-boundary, or communication risks that must stay visible.\n"
                "Use discardedPressure for objections or lane pressure that sounded loud but should not shape the final answer.\n"
                "These binder fields are what the summarizer should think from before it looks at any raw worker detail.\n"
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
                + (
                    "Main-thread full context is active. Read the fuller background packet below during reevaluation, but Objective and current Constraints still win on conflicts.\n"
                    + (
                        "Workers for this task are set to Light Workers mode, so lane prompts were intentionally lighter than the full packet.\n"
                        if worker_context_mode == "weighted"
                        else
                        "Workers for this task are set to Full Workers mode, so lane prompts also received the fuller background packet.\n"
                    )
                )
                + "\n".join(harness_lines)
                + skill_context["prompt"]
                + "\nReturn JSON only that matches the schema exactly."
            )
            input_text = (
                f"Authoritative current user input:\n{task.get('objective', '')}\n\n"
                f"Current constraints:\n{chr(10).join(constraints) if constraints else 'none'}\n\n"
                + self.build_context_weight_block(
                    worker_context_mode,
                    [
                        ("objective", "primary"),
                        ("constraints", "high"),
                        ("commander draft", "high"),
                        ("worker checkpoints", "high"),
                        ("session context", "low"),
                    ],
                )
                + self.build_full_context_block(
                    main_thread_context_mode,
                    [
                        ("Task brief", json.dumps(self.project_task_for_summary(task), ensure_ascii=False, indent=2)),
                        ("Prior summary packet", json.dumps(self.project_prior_summary_for_worker(prior_summary), ensure_ascii=False, indent=2)),
                    ],
                )
                + f"Carry-forward session context (background only, not authoritative):\n{session_context or 'none'}\n\n"
                + self.render_knowledgebase_prompt_block(knowledgebase_packet)
                + f"Initial commander draft for this round:\n{json.dumps(commander_projection, ensure_ascii=False, indent=2)}\n\n"
                + f"Known adversarial lane types:\n{json.dumps(lane_type_catalog, ensure_ascii=False, indent=2)}\n\n"
                + f"Worker checkpoint digests:\n{json.dumps(worker_projection, ensure_ascii=False, indent=2)}\n\n"
                + f"Worker review line catalog:\n{json.dumps(line_catalog, ensure_ascii=False, indent=2)}"
            )
        input_text = self.maybe_compact_prompt_text(input_text, runtime, "commander_review")
        provider_settings = self.resolve_provider_settings(
            task,
            runtime,
            runtime["provider"],
            runtime["model"],
            "commander_review",
            round_number,
        )
        result = self.invoke_provider_json(
            provider=runtime["provider"],
            api_key=api_key,
            model=runtime["model"],
            reasoning_effort=runtime["reasoningEffort"],
            instructions=instructions,
            input_text=input_text,
            schema_name="loop_commander_review",
            schema=self.commander_review_schema_for_mode(compact_review),
            max_output_tokens=int(runtime["maxOutputTokens"]),
            target_kind="commander_review",
            auth_assignments=auth_assignments,
            provider_settings=provider_settings,
            task_id=str(task["taskId"]),
        )
        parsed = normalize_commander_review_checkpoint(
            dict(result.parsed),
            task,
            round_number,
            commander_checkpoint,
            source_workers,
        )
        prompt_metrics = self.prompt_observability_metrics(instructions, input_text, runtime, "commander_review")
        call_meta = {
            "requestedMaxOutputTokens": result.requested_max_output_tokens,
            "effectiveMaxOutputTokens": result.effective_max_output_tokens,
            "attempts": result.attempts,
            "recoveredFromIncomplete": result.recovered_from_incomplete,
            "inputText": input_text,
            "fullPrompt": f"Instructions:\n{instructions}\n\n{input_text}".strip(),
            "reviewMode": "compact_binder" if compact_review else "full_review",
            "lineCatalogIncluded": not compact_review,
            "schemaRequiredFields": list(self.commander_review_schema_for_mode(compact_review).get("required", [])),
            "skills": skill_context["names"],
            "providerTrace": result.provider_trace,
            "auth": result.auth_assignment,
            "authFailoverHistory": result.auth_failover_history,
            "knowledgebaseRecall": self.knowledgebase_call_meta(knowledgebase_packet),
            **prompt_metrics,
        }
        return parsed, result.response_id, result.response, call_meta

    def new_offline_fixture_checkpoint(
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
        research_mode = "offline_fixture_research" if research_config["enabled"] else "offline_fixture"
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
                    "note": "Offline fixture only; this scaffolded claim still needs grounded evidence.",
                },
                {
                    "claim": "Budget ceilings and model controls are necessary once multiple lanes can run live.",
                    "supportLevel": "weak",
                    "sourceUrls": [],
                    "note": "Offline fixture only; production confidence depends on live accounting and observed loop behavior.",
                },
            ],
            "evidenceGaps": [
                "No live web sources were consulted in offline fixture mode.",
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
        worker_context_mode = normalize_context_mode(runtime.get("contextMode"))
        session_context = str(task.get("sessionContext", "")).strip()
        summary_projection = self.project_prior_summary_for_worker(prior_summary)
        summary_text = json.dumps(summary_projection, ensure_ascii=False, indent=2) if summary_projection else "none"
        commander_projection = self.project_commander_for_worker(commander_checkpoint)
        commander_text = json.dumps(commander_projection, ensure_ascii=False, indent=2) if commander_projection else "none"
        commander_full_text = json.dumps(self.project_commander_for_summary(commander_checkpoint), ensure_ascii=False, indent=2) if isinstance(commander_checkpoint, dict) else "none"
        harness_lines = worker_harness_instruction_lines(worker.get("harness"))
        skill_context = build_runtime_skill_context(runtime["provider"], "worker", worker.get("type"))
        local_file_config = normalize_local_file_tool_config(runtime.get("localFiles") if isinstance(runtime.get("localFiles"), dict) else {})
        github_tool_config = normalize_github_tool_config(runtime.get("githubTools") if isinstance(runtime.get("githubTools"), dict) else {})
        knowledgebase_packet = self.build_knowledgebase_recall_packet(
            task,
            runtime,
            worker["id"],
            label=worker["label"],
            role=worker["role"],
            focus=worker["focus"],
            round_number=step_number,
            constraints=constraints,
            prior_summary=prior_summary,
            commander_checkpoint=commander_checkpoint,
        )
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
                "Light Workers mode is active. Treat Objective and current Constraints as primary. Treat the commander draft as high-weight. Treat peer steer and prior summary as medium-weight. Treat carry-forward session context as low-weight background.\n"
                if worker_context_mode == "weighted"
                else
                "Full Workers mode is active. The fuller background packet below should inform your lane's judgment, but Objective and current Constraints still win on conflicts.\n"
            )
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
            + skill_context["prompt"]
        )
        research_description = "Enabled. Workers may use web_search." if research_config["enabled"] else "Disabled. Workers must reason from existing context only."
        research_domains_text = ", ".join(research_config["domains"]) if research_config["domains"] else "none"
        input_text = (
            f"Objective:\n{task['objective']}\n\n"
            + self.build_context_weight_block(
                worker_context_mode,
                [
                    ("objective", "primary"),
                    ("constraints", "high"),
                    ("commander draft", "high"),
                    ("peer steer", "medium"),
                    ("prior summary", "medium"),
                    ("session context", "low"),
                ],
            )
            + self.build_full_context_block(
                worker_context_mode,
                [
                    ("Task brief", json.dumps(self.project_task_for_summary(task), ensure_ascii=False, indent=2)),
                    ("Full commander packet", commander_full_text),
                    ("Full prior summary packet", json.dumps(summary_projection, ensure_ascii=False, indent=2) if summary_projection else "none"),
                ],
            )
            + f"Session context:\n{session_context or 'none'}\n\n"
            + f"Constraints:\n{chr(10).join(constraints)}\n\n"
            + self.render_knowledgebase_prompt_block(knowledgebase_packet)
            + f"Worker roster:\n{json.dumps(task_workers(task, step_number), ensure_ascii=False, indent=2)}\n\n"
            + f"Research policy:\n{research_description}\n"
            + f"externalWebAccess: {research_config['externalWebAccess']}\n"
            + f"allowedDomains: {research_domains_text}\n\n"
            + f"Shared memory version seen:\n{prior_memory_version}\n\n"
            + f"Current commander draft for this round:\n{commander_text}\n\n"
            + f"Prior summary:\n{summary_text}\n\n"
            + f"Peer steer addressed to this lane:\n{peer_text}\n\n"
            + "Produce a checkpoint from your assigned viewpoint."
        )
        input_text = self.maybe_compact_prompt_text(input_text, runtime, "worker")
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
        provider_settings = self.resolve_provider_settings(
            task,
            runtime,
            runtime["provider"],
            runtime["model"],
            worker.get("id"),
            step_number,
        )
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
            provider_settings=provider_settings,
            task_id=str(task["taskId"]),
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
            "skills": skill_context["names"],
            "providerTrace": result.provider_trace,
            "auth": result.auth_assignment,
            "authFailoverHistory": result.auth_failover_history,
            "localToolCalls": parsed["localToolCalls"],
            "localFileSources": parsed["localFileSources"],
            "githubToolCalls": parsed["githubToolCalls"],
            "githubSources": parsed["githubSources"],
            "knowledgebaseRecall": self.knowledgebase_call_meta(knowledgebase_packet),
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
                "engineVersion": str(runtime.get("engineVersion", default_engine_version())),
                "contextMode": str(runtime.get("contextMode", default_context_mode())),
                "directBaselineMode": str(runtime.get("directBaselineMode", default_direct_baseline_mode())),
                "directProvider": str(runtime.get("directProvider", runtime["provider"])),
                "directModel": str(runtime.get("directModel", runtime["model"])),
                "ollamaBaseUrl": str(runtime.get("ollamaBaseUrl", default_ollama_base_url())),
                "timeoutMode": str(runtime.get("timeoutMode", default_timeout_mode())),
                "ollamaTimeoutProfile": normalize_ollama_timeout_profile(runtime.get("ollamaTimeoutProfile")),
                "provider": str(runtime["provider"]),
                "model": str(runtime["model"]),
                "reasoningEffort": str(runtime["reasoningEffort"]),
                "budget": self.get_budget_config(task),
                "research": self.get_research_config(task),
                "localFiles": self.get_local_file_tool_config(task),
                "githubTools": self.get_github_tool_config(task),
                "dynamicSpinup": self.get_dynamic_spinup_config(task),
                "vetting": self.get_vetting_config(task),
                "knowledgebase": self.get_knowledgebase_config(task),
            },
        }

    def project_task_for_adjudication(self, task: Dict[str, Any]) -> Dict[str, Any]:
        runtime = self.get_task_runtime(task)
        return {
            "taskId": str(task.get("taskId", "")),
            "objectivePreview": truncate_text(task.get("objective", ""), 280),
            "sessionContextPreview": truncate_text(task.get("sessionContext", ""), 240),
            "constraints": limit_string_list(task.get("constraints", []), 10, 200),
            "engineVersion": normalize_engine_version(runtime.get("engineVersion")),
            "contextMode": normalize_context_mode(runtime.get("contextMode")),
            "dynamicSpinupEnabled": bool(self.get_dynamic_spinup_config(task).get("enabled")),
            "vettingEnabled": bool(self.get_vetting_config(task).get("enabled")),
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
            "claimsToStrengthen": limit_string_list(checkpoint.get("claimsToStrengthen", []), 4, 220),
            "claimsToLimit": limit_string_list(checkpoint.get("claimsToLimit", []), 4, 220),
            "requiredDecisionGates": limit_string_list(checkpoint.get("requiredDecisionGates", []), 4, 220),
            "evidenceOrCommsRisks": limit_string_list(checkpoint.get("evidenceOrCommsRisks", []), 4, 220),
            "discardedPressure": limit_string_list(checkpoint.get("discardedPressure", []), 4, 220),
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

    def project_commander_review_binder_for_summary(
        self,
        commander_review: Optional[Dict[str, Any]],
        fallback_task: Optional[Dict[str, Any]] = None,
        fallback_round: int = 1,
        fallback_commander: Optional[Dict[str, Any]] = None,
        fallback_workers: Optional[List[str]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        projection = self.project_commander_review_for_summary(
            commander_review,
            fallback_task,
            fallback_round,
            fallback_commander,
            fallback_workers,
        )
        binder = {
            "leadDirection": truncate_text(projection.get("leadDirection", ""), 260),
            "answerDraft": truncate_text(projection.get("answerDraft", ""), 900),
            "whyThisDirection": truncate_text(projection.get("whyThisDirection", ""), 320),
            "claimsToStrengthen": limit_string_list(projection.get("claimsToStrengthen", []), 4, 220),
            "claimsToLimit": limit_string_list(projection.get("claimsToLimit", []), 4, 220),
            "requiredDecisionGates": limit_string_list(projection.get("requiredDecisionGates", []), 4, 220),
            "evidenceOrCommsRisks": limit_string_list(projection.get("evidenceOrCommsRisks", []), 4, 220),
            "discardedPressure": limit_string_list(projection.get("discardedPressure", []), 4, 220),
            "remainingUncertainty": limit_string_list(projection.get("remainingUncertainty", []), 4, 220),
        }
        return self.compact_review_binder_for_model(binder, provider, model)

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

    def build_context_weight_block(self, mode: Any, items: List[tuple[str, str]]) -> str:
        if normalize_context_mode(mode) != "weighted":
            return ""
        lines = [f"{label}: {value}" for label, value in items if str(label).strip() and str(value).strip()]
        if not lines:
            return ""
        return "Context weights:\n" + "\n".join(lines) + "\n\n"

    def build_full_context_block(self, mode: Any, sections: List[tuple[str, str]]) -> str:
        if normalize_context_mode(mode) != "full":
            return ""
        rendered: List[str] = []
        for label, payload in sections:
            label_text = str(label or "").strip()
            payload_text = str(payload or "").strip() or "none"
            if not label_text:
                continue
            rendered.append(f"{label_text}:\n{payload_text}")
        if not rendered:
            return ""
        return "\n\n".join(rendered) + "\n\n"

    def provider_supports_server_input_autocompress(self, provider: Optional[str]) -> bool:
        return normalize_provider_id(provider, DEFAULT_PROVIDER_ID) == "openai"

    def prompt_compaction_char_limit(self, provider: Optional[str], target_kind: str) -> int:
        normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID)
        normalized_target = str(target_kind or "generic").strip().lower()
        if self.provider_supports_server_input_autocompress(normalized_provider):
            limits = {
                "commander": 22000,
                "commander_review": 26000,
                "worker": 24000,
                "summarizer": 36000,
                "generic": 18000,
            }
        else:
            limits = {
                "commander": 14000,
                "commander_review": 16000,
                "worker": 15000,
                "summarizer": 22000,
                "generic": 12000,
            }
        return int(limits.get(normalized_target, limits["generic"]))

    def maybe_compact_prompt_text(self, prompt_text: str, runtime: Optional[Dict[str, Any]], target_kind: str) -> str:
        raw = str(prompt_text or "").strip()
        if not raw:
            return raw
        provider = runtime.get("provider") if isinstance(runtime, dict) else DEFAULT_PROVIDER_ID
        soft_limit = self.prompt_compaction_char_limit(provider, target_kind)
        if len(raw) <= soft_limit:
            return raw
        note = (
            "Context note: part of the background packet was locally compacted to stay within model limits and budget.\n\n"
        )
        sections = [section.strip() for section in re.split(r"\n{2,}", raw) if str(section).strip()]
        if not sections:
            return note + compact_text_middle(raw, max(600, soft_limit - len(note)))
        per_section = max(260, int((soft_limit - len(note)) / max(len(sections), 1)))
        compacted_sections = [compact_text_middle(section, per_section) for section in sections]
        compacted = note + "\n\n".join(compacted_sections)
        if len(compacted) <= soft_limit:
            return compacted
        return note + compact_text_middle("\n\n".join(compacted_sections), max(600, soft_limit - len(note)))

    def prompt_observability_metrics(
        self,
        instructions: str,
        input_text: str,
        runtime: Optional[Dict[str, Any]],
        target_kind: str,
    ) -> Dict[str, Any]:
        instructions_text = str(instructions or "")
        input_payload = str(input_text or "")
        full_prompt = f"Instructions:\n{instructions_text}\n\n{input_payload}".strip()
        provider = runtime.get("provider") if isinstance(runtime, dict) else DEFAULT_PROVIDER_ID
        soft_limit = self.prompt_compaction_char_limit(provider, target_kind)
        return {
            "instructionsChars": len(instructions_text),
            "inputTextChars": len(input_payload),
            "fullPromptChars": len(full_prompt),
            "softLimitChars": soft_limit,
            "estimatedPromptTokens": max(1, math.ceil(len(full_prompt) / 4)),
        }

    def estimate_structured_payload_tokens(self, payload: Any) -> int:
        try:
            rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            rendered = str(payload or "")
        return max(1, math.ceil(len(rendered) / 4))

    def compact_review_binder_for_model(
        self,
        binder: Dict[str, Any],
        provider: Optional[str],
        model: Optional[str],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        current = dict(binder or {})
        budget_tokens = model_capacities.inferred_prompt_budget_tokens(provider, model, "review_binder")
        before_tokens = self.estimate_structured_payload_tokens(current)
        compaction_applied = False

        def keep_list(name: str, max_items: int, max_length: int) -> None:
            current[name] = limit_string_list(current.get(name, []), max_items, max_length)

        def keep_text(name: str, max_length: int) -> None:
            current[name] = truncate_text(current.get(name, ""), max_length)

        if before_tokens > budget_tokens:
            compaction_applied = True
            keep_text("leadDirection", 220)
            keep_text("answerDraft", 700)
            keep_text("whyThisDirection", 240)
            for name in (
                "claimsToStrengthen",
                "claimsToLimit",
                "requiredDecisionGates",
                "evidenceOrCommsRisks",
                "discardedPressure",
                "remainingUncertainty",
            ):
                keep_list(name, 3, 180)

        if self.estimate_structured_payload_tokens(current) > budget_tokens:
            keep_text("answerDraft", 520)
            keep_text("whyThisDirection", 200)
            for name in (
                "claimsToStrengthen",
                "claimsToLimit",
                "requiredDecisionGates",
                "evidenceOrCommsRisks",
                "remainingUncertainty",
            ):
                keep_list(name, 2, 140)
            keep_list("discardedPressure", 1, 140)

        if self.estimate_structured_payload_tokens(current) > budget_tokens:
            current.pop("discardedPressure", None)
            current["claimsToStrengthen"] = []
            current["claimsToLimit"] = []
            keep_text("answerDraft", 360)
            keep_text("whyThisDirection", 160)
            keep_list("requiredDecisionGates", 2, 120)
            keep_list("evidenceOrCommsRisks", 2, 120)
            keep_list("remainingUncertainty", 2, 120)

        after_tokens = self.estimate_structured_payload_tokens(current)
        return current, {
            "reviewBinderBudgetTokens": budget_tokens,
            "reviewBinderEstimatedTokens": after_tokens,
            "reviewBinderInitialTokens": before_tokens,
            "reviewBinderCompacted": compaction_applied or after_tokens < before_tokens,
            "modelContextWindowTokens": int((model_capacities.resolve_model_capacity(provider, model) or {}).get("contextWindowTokens", 0) or 0),
            "modelMaxOutputTokens": int((model_capacities.resolve_model_capacity(provider, model) or {}).get("maxOutputTokens", 0) or 0),
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
            "confidence": coerce_confidence_value(checkpoint.get("confidence", 0.0)),
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

    def project_worker_checkpoint_for_adjudication(self, checkpoint: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(checkpoint, dict):
            return None
        ledger: List[Dict[str, Any]] = []
        for entry in checkpoint.get("evidenceLedger", [])[:3] if isinstance(checkpoint.get("evidenceLedger"), list) else []:
            if not isinstance(entry, dict):
                continue
            ledger.append(
                {
                    "claim": truncate_text(entry.get("claim", ""), 220),
                    "supportLevel": str(entry.get("supportLevel", "")),
                    "note": truncate_text(entry.get("note", ""), 160),
                    "sourceUrls": limit_url_list(entry.get("sourceUrls", []), 3),
                }
            )
        return {
            "workerId": str(checkpoint.get("workerId", "")),
            "label": str(checkpoint.get("label", "")),
            "role": str(checkpoint.get("role", "")),
            "focus": truncate_text(checkpoint.get("focus", ""), 140),
            "step": int(checkpoint.get("step", 0) or 0),
            "observation": truncate_text(checkpoint.get("observation", ""), 320),
            "benefits": limit_string_list(checkpoint.get("benefits", []), 2, 160),
            "detriments": limit_string_list(checkpoint.get("detriments", []), 2, 160),
            "requiredCircumstances": limit_string_list(checkpoint.get("requiredCircumstances", []), 2, 160),
            "invalidatingCircumstances": limit_string_list(checkpoint.get("invalidatingCircumstances", []), 2, 160),
            "immediateConsequences": limit_string_list(checkpoint.get("immediateConsequences", []), 2, 160),
            "downstreamConsequences": limit_string_list(checkpoint.get("downstreamConsequences", []), 2, 160),
            "uncertainty": limit_string_list(checkpoint.get("uncertainty", []), 2, 160),
            "reversalConditions": limit_string_list(checkpoint.get("reversalConditions", []), 2, 160),
            "evidenceGaps": limit_string_list(checkpoint.get("evidenceGaps", []), 3, 160),
            "evidenceLedger": ledger,
            "confidence": coerce_confidence_value(checkpoint.get("confidence", 0.0)),
            "requestToPeer": truncate_text(checkpoint.get("requestToPeer", ""), 180),
        }

    def project_worker_state_for_adjudication(self, worker_state: Dict[str, Any], workers: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        projected: List[Dict[str, Any]] = []
        for worker in workers:
            checkpoint = self.project_worker_checkpoint_for_adjudication(worker_state.get(worker["id"]))
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

    def new_offline_fixture_summary(
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
        commander_review_fallback = normalize_commander_review_checkpoint(
            commander_review_checkpoint,
            task,
            max(round_number, int(commander_projection.get("round", 0) or 1)),
            commander_checkpoint,
            [worker["id"] for worker in workers if isinstance(worker_state.get(worker["id"]), dict)],
        )
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
                "answer": truncate_text(commander_review_fallback.get("answerDraft", ""), 3200) or front_answer_text,
                "stance": truncate_text(commander_review_fallback.get("stance", ""), 260) or lead_direction,
                "leadDirection": truncate_text(commander_review_fallback.get("leadDirection", ""), 260) or lead_direction,
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
                "Offline fixture vetting suggests the checkpoint schema is ready for evidence review, but the claims still need live sourced validation."
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
                    "rationale": "Offline fixture mode cannot confirm the claim with live source evidence, but both lanes converge on it as an operating principle.",
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
        return self.summary_schema_for_mode(compact=False)

    def summary_schema_for_mode(self, compact: bool = False) -> Dict[str, Any]:
        if compact:
            return {
                "type": "object",
                "additionalProperties": False,
                "required": ["taskId", "round", "frontAnswer", "summarizerOpinion", "sourceWorkers"],
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
                    "sourceWorkers": {"type": "array", "items": {"type": "string"}},
                },
            }
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
        worker_context_mode = normalize_context_mode(runtime.get("contextMode"))
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
        commander_review_binder, binder_meta = self.project_commander_review_binder_for_summary(
            commander_review_checkpoint,
            task,
            int(commander_projection.get("round", 0) or 1),
            commander_checkpoint,
            [worker["id"] for worker in workers if isinstance(worker_state.get(worker["id"]), dict)],
            runtime["provider"],
            runtime["model"],
        )
        task_brief = self.project_task_for_adjudication(task)
        worker_projection = self.project_worker_state_for_adjudication(worker_state, workers)
        pending_workers = normalize_worker_id_list(pending_workers or [])
        knowledgebase_packet = self.build_knowledgebase_recall_packet(
            task,
            runtime,
            "answer_now" if partial_mode else "summarizer",
            label="Answer Now" if partial_mode else "Summarizer",
            role="final_answer",
            focus="final user-facing synthesis",
            round_number=int(commander_projection.get("round", 0) or 1),
            constraints=constraints,
            commander_checkpoint=commander_checkpoint,
        )
        contradiction_memory_packet = self.build_contradiction_memory_packet(
            task,
            runtime,
            commander_review_checkpoint,
            worker_state,
            workers,
            knowledgebase_packet,
            round_number=int(commander_projection.get("round", 0) or 1),
        )
        has_commander_review = isinstance(commander_review_checkpoint, dict) and int(commander_review_checkpoint.get("round", 0) or 0) > 0
        compact_summary = has_commander_review and model_prefers_compact_context(runtime["provider"], runtime["model"])
        skill_context = build_runtime_skill_context(runtime["provider"], "summarizer", compact=compact_summary)
        if compact_summary:
            instructions = (
                "Use the commander review binder as the only authoritative state for this round.\n"
                "Write one clean user-facing answer plus brief review-facing fields.\n"
                "Do not mention workers, lanes, review, or hidden process.\n"
                "Keep fields short, distinct, and non-repetitive.\n"
                "Preserve real uncertainty, but do not turn the answer into a hedge pile.\n"
            )
            if partial_mode:
                instructions += (
                    "This is a partial summary request. Make the confidence note and uncertainty say plainly that some checkpoints are still missing.\n"
                )
            instructions += "\n".join(harness_lines)
            if skill_context["prompt"]:
                instructions += "\n" + skill_context["prompt"]
            instructions += "\nReturn JSON only that matches the schema exactly."
            input_text = (
                f"Current incident request:\n{task.get('objective', '')}\n\n"
                f"Current constraints:\n{chr(10).join(constraints) if constraints else 'none'}\n\n"
                f"Background context:\n{session_context or 'none'}\n\n"
                + self.render_knowledgebase_prompt_block(knowledgebase_packet)
                + self.render_contradiction_memory_prompt_block(contradiction_memory_packet)
                + f"Authoritative rebound lead binder:\n{json.dumps(commander_review_binder, ensure_ascii=False, indent=2)}"
            )
            if partial_mode:
                input_text += (
                    "\n\n"
                    f"Partial summary mode:\n{partial_mode}\n\n"
                    f"Pending workers:\n{json.dumps(pending_workers, ensure_ascii=False, indent=2)}"
                )
        else:
            instructions = (
                "You have just completed a rigorous internal pressure test on a lead answer draft.\n"
                "The commander review has already rebound that pressure into a revised lead position.\n"
                "Your task now is to produce the single best final answer from that rebound state while still completing the review-facing evidence fields.\n"
                "Treat the commander review binder as the primary integration packet.\n"
                "Treat raw worker checkpoint detail as background evidence for review-facing fields, not as the thing that speaks directly to the user.\n"
                "The public answer should feel like one coherent mind speaking after a hard internal stress test, not like a debate recap or committee merge.\n"
                "Act as the evidence vetter for shared memory.\n"
                "Preserve disagreements, conditional truths, and real uncertainty.\n"
                "Do not erase contradictions.\n"
                "Judge worker claims using the evidence they provide.\n"
                "The lead thread stays in control at all times.\n"
            )
            instructions += (
                "The supplied commander review is the authoritative lead-thread reevaluation for this round.\n"
                "Preserve its controlAudit and dynamicLaneDecision in your output instead of making a fresh lane request.\n"
                "Start from the supplied commander review answerDraft when forming the visible answer.\n"
                "Let the public answer reflect that reevaluated course cleanly, without re-running the course decision from scratch.\n"
                "Use claimsToStrengthen, claimsToLimit, requiredDecisionGates, evidenceOrCommsRisks, discardedPressure, and remainingUncertainty as the main binder that links adversarial pressure to the final answer.\n"
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
                "Rewrite surviving pressure into your own natural language before it reaches frontAnswer.answer.\n"
                "Do not reuse worker wording or review wording verbatim when a cleaner phrasing would preserve the same meaning.\n"
                "Prefer a decisive but conditional answer over a timid laundry list of caveats.\n"
                "Do not let the mere existence of objections trigger a course change.\n"
                "Indecisive drift is worse than a clear qualified answer when the evidence does not justify reversal.\n"
                "Do not mention workers, lanes, adversaries, or hidden process inside frontAnswer.answer unless the user explicitly asked for process detail.\n"
                "Do not use literal provenance markers such as Worker A, Worker B, accepted from Worker A, guardrail from Worker B, or similar internal labels inside frontAnswer.answer.\n"
                "If a private objection materially changed the answer, translate that into plain user-facing reasoning without naming the internal source.\n"
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
                + (
                    "Main-thread full context is active. Read the full task and worker packet below, but Objective and current Constraints still win on conflicts.\n"
                    + (
                        "Workers for this task are set to Light Workers mode.\n"
                        if worker_context_mode == "weighted"
                        else
                        "Workers for this task are set to Full Workers mode.\n"
                    )
                )
            )
            if partial_mode:
                instructions += (
                    "This is a partial summary request.\n"
                    "Some worker checkpoints are still missing or still running.\n"
                    "Use only the currently available checkpoints.\n"
                    "The public answer should still be useful and decisive, but its confidence note must clearly reflect the missing evidence.\n"
                )
            instructions += "\n".join(harness_lines)
            instructions += skill_context["prompt"]
            instructions += "\nReturn JSON only that matches the schema exactly."
            input_text = (
                f"Current incident request:\n{task.get('objective', '')}\n\n"
                f"Current constraints:\n{chr(10).join(constraints) if constraints else 'none'}\n\n"
                f"Background context:\n{session_context or 'none'}\n\n"
                + self.render_knowledgebase_prompt_block(knowledgebase_packet)
                + self.render_contradiction_memory_prompt_block(contradiction_memory_packet)
                + f"Rebound lead position from the internal pressure test:\n{json.dumps(commander_review_binder, ensure_ascii=False, indent=2)}\n\n"
                + f"Lead draft before the final rewrite:\n{json.dumps(commander_projection, ensure_ascii=False, indent=2)}\n\n"
                + f"Partial summary mode:\n{partial_mode}\n\n"
                + f"Pending workers:\n{json.dumps(pending_workers, ensure_ascii=False, indent=2)}\n\n"
                + f"Vetting enabled:\n{vetting_config['enabled']}\n\n"
                + "Supporting evidence packet for review-facing fields only:\n"
                + f"Worker checkpoint digests:\n{json.dumps(worker_projection, ensure_ascii=False, indent=2)}\n\n"
                + f"Worker review line catalog:\n{json.dumps(line_catalog, ensure_ascii=False, indent=2)}"
            )
        input_text = self.maybe_compact_prompt_text(input_text, runtime, "summarizer")
        provider_settings = self.resolve_provider_settings(
            task,
            runtime,
            runtime["provider"],
            runtime["model"],
            "answer_now" if partial_mode else "summarizer",
            int(commander_projection.get("round", 0) or 1),
        )
        result = self.invoke_provider_json(
            provider=runtime["provider"],
            api_key=api_key,
            model=runtime["model"],
            reasoning_effort=runtime["reasoningEffort"],
            instructions=instructions,
            input_text=input_text,
            schema_name="loop_summary_multi",
            schema=self.summary_schema_for_mode(compact_summary),
            max_output_tokens=int(runtime["maxOutputTokens"]),
            target_kind="summarizer",
            auth_assignments=auth_assignments,
            provider_settings=provider_settings,
            task_id=str(task["taskId"]),
        )
        parsed = dict(result.parsed)
        if compact_summary:
            parsed["taskId"] = str(parsed.get("taskId") or task.get("taskId") or "")
        authoritative_round = int(commander_review_projection.get("round", 0) or commander_projection.get("round", 0) or 0)
        if authoritative_round > 0:
            parsed["round"] = authoritative_round
        if has_commander_review:
            parsed["controlAudit"] = commander_review_projection.get("controlAudit", parsed.get("controlAudit"))
            parsed["dynamicLaneDecision"] = commander_review_projection.get("dynamicLaneDecision", parsed.get("dynamicLaneDecision"))
            parsed["dynamicLaneResolution"] = commander_review_projection.get("dynamicLaneResolution", parsed.get("dynamicLaneResolution"))
            parsed["sourceWorkers"] = normalize_worker_id_list(parsed.get("sourceWorkers", [])) or commander_review_projection.get("sourceWorkers", [])
            front_answer = parsed.get("frontAnswer") if isinstance(parsed.get("frontAnswer"), dict) else {}
            if not str(front_answer.get("leadDirection", "")).strip():
                front_answer["leadDirection"] = commander_review_projection.get("leadDirection", "")
            if not str(front_answer.get("stance", "")).strip():
                front_answer["stance"] = commander_review_projection.get("stance", "")
            parsed["frontAnswer"] = front_answer
        parsed = self.apply_contradiction_memory_final_gates(parsed, contradiction_memory_packet)
        assert_public_answer_free_of_internal_provenance(
            flatten_output_payload_text(parsed, "summary_output"),
            "summary",
        )
        parsed["evidenceVerdicts"] = normalize_evidence_verdicts(parsed.get("evidenceVerdicts", []))
        parsed["claimsNeedingVerification"] = normalize_string_array_preserve_items(parsed.get("claimsNeedingVerification", []))
        parsed["mergedAt"] = utc_now()
        prompt_metrics = self.prompt_observability_metrics(instructions, input_text, runtime, "summarizer")
        call_meta = {
            "requestedMaxOutputTokens": result.requested_max_output_tokens,
            "effectiveMaxOutputTokens": result.effective_max_output_tokens,
            "attempts": result.attempts,
            "recoveredFromIncomplete": result.recovered_from_incomplete,
            "inputText": input_text,
            "fullPrompt": f"Instructions:\n{instructions}\n\n{input_text}".strip(),
            "summaryMode": "compact_binder" if compact_summary else "full_summary",
            "lineCatalogIncluded": not compact_summary,
            "workerEvidenceIncluded": not compact_summary,
            "schemaRequiredFields": list(self.summary_schema_for_mode(compact_summary).get("required", [])),
            "skills": skill_context["names"],
            "providerTrace": result.provider_trace,
            "auth": result.auth_assignment,
            "authFailoverHistory": result.auth_failover_history,
            "knowledgebaseRecall": self.knowledgebase_call_meta(knowledgebase_packet),
            "contradictionMemory": self.contradiction_memory_call_meta(contradiction_memory_packet),
            **prompt_metrics,
            **binder_meta,
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
        summary["publicAnswer"] = str(summary.get("frontAnswer", {}).get("answer", "") or "").strip()
        summary["flattenedOutputText"] = flatten_output_payload_text(summary, "summary_output")
        return summary

    def annotate_partial_summary(self, summary: Dict[str, Any], available_workers: List[str], pending_workers: List[str]) -> Dict[str, Any]:
        available_workers = normalize_worker_id_list(available_workers)
        pending_workers = normalize_worker_id_list(pending_workers)
        summary["partialSummary"] = True
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

    def direct_baseline_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer", "stance", "confidenceNote"],
            "properties": {
                "answer": {"type": "string"},
                "stance": {"type": "string"},
                "confidenceNote": {"type": "string"},
            },
        }

    def new_offline_fixture_direct_baseline_answer(self, task: Dict[str, Any]) -> Dict[str, str]:
        objective = str(task.get("objective") or "")
        lowered = objective.lower()
        if "billing" in lowered or "holiday" in lowered:
            answer = (
                "My recommendation is no-go on a full billing replatform right before peak traffic. The safer path is a staged dual-run or a narrower cutover that proves the queue path without putting revenue collection at risk.\n\n"
                "The next step is to keep the current system as the source of truth for peak season and run the new path in shadow mode with explicit rollback gates."
            )
            stance = "Hold the full cutover and de-risk it through a staged path."
        else:
            answer = (
                "My recommendation is a conditional ship, not a blind launch. Move forward only with a tightly bounded rollout that keeps sensitive outputs behind review and makes privacy or contract-sensitive failures visible fast.\n\n"
                "The next step is to launch to a small internal or design-partner cohort with manual review, clear escalation rules, and a narrow scope."
            )
            stance = "Ship only through a constrained rollout with strong guardrails."
        return normalize_direct_answer_payload(
            {
                "answer": answer,
                "stance": stance,
                "confidenceNote": "Offline fixture direct baseline for runtime plumbing; useful for compare flow validation, not factual confidence.",
            },
            objective,
        )

    def new_live_direct_baseline(
        self,
        api_key: str,
        auth_assignments: List[Dict[str, Any]],
        task: Dict[str, Any],
        direct_runtime: Dict[str, Any],
    ) -> tuple[Dict[str, str], Optional[str], Optional[Dict[str, Any]], Dict[str, Any]]:
        runtime_config = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        direct_harness = normalize_harness_config(
            runtime_config.get("directHarness", default_direct_harness()),
            default_direct_harness()["concision"],
        )
        harness_lines = direct_baseline_harness_instruction_lines(direct_harness)
        instructions = (
            "Answer the user directly as one assistant.\n"
            "Give a decisive but conditional recommendation.\n"
            "Do not narrate hidden process.\n"
            "Absorb tradeoffs into the recommendation itself.\n"
        )
        if harness_lines:
            instructions += "\n".join(harness_lines) + "\n"
        instructions += (
            "Return JSON only that matches the schema exactly."
        )
        constraints = normalize_string_array_preserve_items(task.get("constraints", []))
        input_text = (
            f"Objective:\n{task.get('objective', '')}\n\n"
            f"Constraints:\n{json.dumps(constraints, ensure_ascii=False, indent=2)}\n\n"
            f"Session context:\n{task.get('sessionContext', '') or 'none'}\n"
        )
        input_text = self.maybe_compact_prompt_text(input_text, direct_runtime, "generic")
        provider_settings = self.resolve_provider_settings(
            task,
            direct_runtime,
            direct_runtime["provider"],
            direct_runtime["model"],
            "direct_baseline",
            1,
        )
        result = self.invoke_provider_json(
            provider=direct_runtime["provider"],
            api_key=api_key,
            model=direct_runtime["model"],
            reasoning_effort=direct_runtime["reasoningEffort"],
            instructions=instructions,
            input_text=input_text,
            schema_name="loop_direct_baseline",
            schema=self.direct_baseline_schema(),
            max_output_tokens=int(direct_runtime["maxOutputTokens"]),
            target_kind="generic",
            auth_assignments=auth_assignments,
            provider_settings=provider_settings,
            task_id=str(task["taskId"]),
        )
        parsed = normalize_direct_answer_payload(
            result.parsed,
            str(task.get("objective") or ""),
            provider=direct_runtime["provider"],
        )
        call_meta = {
            "requestedMaxOutputTokens": result.requested_max_output_tokens,
            "effectiveMaxOutputTokens": result.effective_max_output_tokens,
            "attempts": list(result.attempts),
            "recoveredFromIncomplete": result.recovered_from_incomplete,
            "inputText": input_text,
            "fullPrompt": f"Instructions:\n{instructions}\n\n{input_text}".strip(),
            "auth": result.auth_assignment,
            "authFailoverHistory": result.auth_failover_history,
            "skills": normalize_string_array_preserve_items(getattr(result, "used_skills", [])),
            "providerTrace": result.provider_trace,
        }
        return parsed, result.response_id, result.response, call_meta

    def write_direct_baseline_files(self, task_id: str, round_number: int, baseline: Dict[str, Any]) -> tuple[Path, Path]:
        latest_name = f"{task_id}_direct_baseline.json"
        history_name = f"{task_id}_direct_baseline_round{round_number:03d}.json"
        artifact_store.write_json_artifact(self.root, "checkpoints", latest_name, baseline)
        artifact_store.write_json_artifact(self.root, "checkpoints", history_name, baseline)
        return Path(latest_name), Path(history_name)

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

    def node_transfer_filename_component(self, value: Any, fallback: str = "node", max_length: int = 40) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip("-._")
        if not normalized:
            normalized = fallback
        return normalized[: max(8, int(max_length or 40))].strip("-._") or fallback

    def canonical_transfer_bytes(self, payload: Any) -> bytes:
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def transfer_integrity(self, payload: Any) -> Dict[str, Any]:
        body = self.canonical_transfer_bytes(payload)
        return {
            "canonicalJsonBytes": len(body),
            "crc32": f"{zlib.crc32(body) & 0xFFFFFFFF:08x}",
            "sha256": hashlib.sha256(body).hexdigest(),
        }

    def verify_transfer_integrity(self, payload: Any, integrity: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        expected = integrity if isinstance(integrity, dict) else {}
        actual = self.transfer_integrity(payload)
        expected_sha = str(expected.get("sha256") or "").strip()
        expected_crc = str(expected.get("crc32") or "").strip().lower()
        expected_bytes = int(expected.get("canonicalJsonBytes") or 0)
        mismatches: List[str] = []
        if expected_sha and expected_sha != actual["sha256"]:
            mismatches.append("sha256")
        if expected_crc and expected_crc != actual["crc32"]:
            mismatches.append("crc32")
        if expected_bytes and expected_bytes != actual["canonicalJsonBytes"]:
            mismatches.append("canonicalJsonBytes")
        return {
            "ok": not mismatches,
            "actual": actual,
            "expected": expected,
            "mismatches": mismatches,
        }

    def write_node_transfer_artifact(
        self,
        *,
        task_id: str,
        source_node: str,
        target_nodes: List[str],
        payload: Any,
        status: str = "accepted",
        validation_status: str = "valid",
        checkpoint_artifact: str = "",
        output_artifact: str = "",
        failed_call_artifact: str = "",
        failure_kind: str = "",
        error: Any = "",
        retryable: bool = False,
        oversight_action: str = "",
    ) -> Dict[str, Any]:
        self.ensure_data_paths()
        normalized_status = str(status or "accepted").strip().lower()
        normalized_validation = str(validation_status or "valid").strip().lower()
        source = self.node_transfer_filename_component(source_node, "source", 28)
        target_label = self.node_transfer_filename_component("-".join(target_nodes or []), "target", 28)
        task_component = self.node_transfer_filename_component(task_id, "task", 14).replace("-", "")
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S%f")
        route_hash = hashlib.sha1(f"{source_node}|{'|'.join(target_nodes or [])}".encode("utf-8")).hexdigest()[:10]
        transfer_id = f"nt_{task_component}_{route_hash}_{timestamp}"
        integrity = self.transfer_integrity(payload)
        check = self.verify_transfer_integrity(payload, integrity)
        payload_keys = sorted(str(key) for key in payload.keys())[:80] if isinstance(payload, dict) else []
        packet = {
            "schemaVersion": "parallm.node_transfer.v1",
            "artifactType": "node_transfer",
            "transferId": transfer_id,
            "createdAt": utc_now(),
            "taskId": str(task_id or "").strip(),
            "sourceNode": str(source_node or "").strip(),
            "targetNodes": [str(node or "").strip() for node in (target_nodes or []) if str(node or "").strip()],
            "routeLabel": {
                "source": source,
                "target": target_label,
                "hash": route_hash,
            },
            "status": normalized_status,
            "validationStatus": normalized_validation,
            "passedToNextNode": normalized_status == "accepted" and normalized_validation == "valid" and bool(check.get("ok")),
            "retryable": bool(retryable),
            "oversightAction": str(oversight_action or "").strip() or (
                "spin_up_adversary_or_retry" if normalized_status in {"deceased", "reader_rejected", "pass_corrupt"} else "none"
            ),
            "failureKind": str(failure_kind or "").strip() or None,
            "error": str(error or "").strip() or None,
            "integrity": integrity,
            "integrityCheck": check,
            "payloadShape": {
                "type": type(payload).__name__,
                "keys": payload_keys,
                "keyCount": len(payload.keys()) if isinstance(payload, dict) else None,
            },
            "artifacts": {
                "checkpoint": str(checkpoint_artifact or "").strip() or None,
                "output": str(output_artifact or "").strip() or None,
                "failedCall": str(failed_call_artifact or "").strip() or None,
            },
            "contract": {
                "writerRule": "Only canonical parsed payloads may be marked accepted.",
                "readerRule": "Verify crc32, sha256, and canonicalJsonBytes before parsing or reasoning over this transfer.",
                "failureSplit": "Checksum mismatch means pass_corrupt; checksum ok but schema/parser rejection means reader_rejected.",
            },
        }
        artifact_meta = artifact_store.write_json_artifact(self.root, "node_transfers", f"{transfer_id}.json", packet)
        packet["artifact"] = artifact_meta
        self.append_step(
            "node_transfer",
            "Node transfer " + ("accepted." if packet["passedToNextNode"] else f"{normalized_status}."),
            {
                "taskId": task_id,
                "sourceNode": source_node,
                "targetNodes": packet["targetNodes"],
                "status": normalized_status,
                "validationStatus": normalized_validation,
                "passedToNextNode": packet["passedToNextNode"],
                "crc32": integrity["crc32"],
                "sha256": integrity["sha256"],
                "artifact": artifact_meta.get("name"),
                "failureKind": packet["failureKind"],
            },
        )
        return packet

    def latest_node_transfer_packet(self, task_id: str, source_node: str, target_node: str) -> Optional[Dict[str, Any]]:
        normalized_task = str(task_id or "").strip()
        normalized_source = str(source_node or "").strip()
        normalized_target = str(target_node or "").strip()
        if not normalized_task or not normalized_source or not normalized_target:
            return None
        for artifact in artifact_store.list_json_artifacts(self.root, ["node_transfers"]):
            packet = artifact_store.read_json_artifact(self.root, "node_transfers", str(artifact.get("name") or ""))
            if not isinstance(packet, dict):
                continue
            if str(packet.get("taskId") or "").strip() != normalized_task:
                continue
            if str(packet.get("sourceNode") or "").strip() != normalized_source:
                continue
            targets = [str(node or "").strip() for node in (packet.get("targetNodes") or []) if str(node or "").strip()] if isinstance(packet.get("targetNodes"), list) else []
            if normalized_target not in targets and "workers" not in targets:
                continue
            return packet
        return None

    def verify_node_transfer_before_read(
        self,
        *,
        task_id: str,
        source_node: str,
        target_node: str,
        payload: Any,
        stage: str,
    ) -> Dict[str, Any]:
        packet = self.latest_node_transfer_packet(task_id, source_node, target_node)
        if not isinstance(packet, dict):
            self.append_step(
                "node_transfer",
                "Node transfer reader encountered legacy unsealed payload.",
                {
                    "taskId": task_id,
                    "sourceNode": source_node,
                    "targetNode": target_node,
                    "stage": stage,
                    "status": "legacy_unsealed",
                },
            )
            return {"ok": True, "status": "legacy_unsealed"}
        if str(packet.get("status") or "").strip().lower() != "accepted" or not bool(packet.get("passedToNextNode")):
            raise RuntimeErrorWithCode(
                f"Node transfer from {source_node} to {target_node} is not accepted: {packet.get('status') or 'unknown'}.",
                409,
            )
        check = self.verify_transfer_integrity(payload, packet.get("integrity") if isinstance(packet.get("integrity"), dict) else {})
        if not bool(check.get("ok")):
            self.write_node_transfer_artifact(
                task_id=task_id,
                source_node=source_node,
                target_nodes=[target_node],
                payload=payload,
                status="pass_corrupt",
                validation_status="checksum_mismatch",
                failure_kind="checksum_mismatch",
                error="Node transfer checksum mismatch before reader parse.",
                retryable=False,
                oversight_action="declare_transfer_deceased_and_spawn_replacement_adversary",
            )
            raise RuntimeErrorWithCode(
                f"Node transfer checksum failed from {source_node} to {target_node}: {', '.join(check.get('mismatches') or [])}.",
                409,
            )
        self.append_step(
            "node_transfer",
            "Node transfer checksum verified before reader parse.",
            {
                "taskId": task_id,
                "sourceNode": source_node,
                "targetNode": target_node,
                "stage": stage,
                "status": "verified",
                "crc32": check["actual"]["crc32"],
                "sha256": check["actual"]["sha256"],
            },
        )
        return {"ok": True, "status": "verified", "integrity": check["actual"]}

    def failed_call_task_id(self, task_id: Optional[str] = None) -> str:
        normalized = str(task_id or "").strip()
        if normalized:
            return normalized
        context = self.current_execution_context()
        for key in ("stateScopeTaskId", "taskId"):
            candidate = str(context.get(key) or "").strip()
            if candidate:
                return candidate
        try:
            active_task = self.read_state().get("activeTask")
        except Exception:
            active_task = None
        if isinstance(active_task, dict):
            candidate = str(active_task.get("taskId") or "").strip()
            if candidate:
                return candidate
        return "unknown-task"

    def failed_call_filename_component(self, value: Any, fallback: str = "unknown", max_length: int = 80) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip("-._")
        if not normalized:
            normalized = fallback
        return normalized[:max(12, int(max_length or 80))].strip("-._") or fallback

    def classify_failed_call_kind(self, error: Any, raw_output_text: str = "", finish_reason: str = "") -> str:
        message = str(error or "").lower()
        normalized_finish = str(finish_reason or "").strip().lower()
        if normalized_finish == "length" or "incomplete" in message or "max output" in message or "token" in message and "exceed" in message:
            return "overflow"
        if "json parse" in message or str(raw_output_text or "").strip():
            return "malformed_json"
        if "timed out" in message or "timeout" in message:
            return "timeout"
        if "http " in message:
            return "http_error"
        if "connection" in message or "temporary failure" in message or "name resolution" in message or "network" in message:
            return "connection"
        if "no api key" in message or "invalid_api_key" in message or "incorrect api key" in message:
            return "credentials"
        return "provider_error"

    def build_failed_call_ingestion(self, raw_output_text: str, error: Any) -> Dict[str, Any]:
        raw = str(raw_output_text or "")
        ingestion: Dict[str, Any] = {
            "rawLength": len(raw),
            "rawPreview": truncate_text(raw, 4000),
            "parseError": str(error or ""),
            "candidateKind": "empty",
            "candidateJsonText": "",
            "candidateParseError": "",
            "candidatePackets": [],
        }
        if not raw.strip():
            return ingestion
        candidates = [("raw", raw)]
        first_object = raw.find("{")
        last_object = raw.rfind("}")
        if first_object >= 0 and last_object > first_object:
            candidates.append(("first_object_span", raw[first_object:last_object + 1]))
        first_array = raw.find("[")
        last_array = raw.rfind("]")
        if first_array >= 0 and last_array > first_array:
            candidates.append(("first_array_span", raw[first_array:last_array + 1]))
        for index, (start, end, candidate_text) in enumerate(extract_balanced_json_object_spans(raw, limit=12), start=1):
            packet: Dict[str, Any] = {
                "index": index,
                "kind": "balanced_object",
                "start": start,
                "end": end,
                "length": len(candidate_text),
                "preview": truncate_text(candidate_text, 600),
                "parseError": "",
                "parsedType": "",
                "keys": [],
                "payloadScore": 0,
                "schemaEcho": False,
            }
            try:
                parsed_packet = json.loads(candidate_text)
            except json.JSONDecodeError as parse_error:
                packet["parseError"] = str(parse_error)
            else:
                packet["parsedType"] = type(parsed_packet).__name__
                if isinstance(parsed_packet, dict):
                    packet["keys"] = sorted(str(key) for key in parsed_packet.keys())[:40]
                    packet["payloadScore"] = structured_output_payload_score(parsed_packet)
                    packet["schemaEcho"] = looks_like_schema_echo(parsed_packet)
            ingestion["candidatePackets"].append(packet)
        for candidate_kind, candidate_text in candidates:
            ingestion["candidateKind"] = candidate_kind
            ingestion["candidateJsonText"] = truncate_text(candidate_text, 12000)
            try:
                parsed = json.loads(candidate_text)
            except json.JSONDecodeError as parse_error:
                ingestion["candidateParseError"] = str(parse_error)
                continue
            ingestion["candidateParseError"] = ""
            ingestion["candidateParsedType"] = type(parsed).__name__
            if isinstance(parsed, dict):
                ingestion["candidateKeys"] = sorted(str(key) for key in parsed.keys())[:40]
                ingestion["candidatePayloadScore"] = structured_output_payload_score(parsed)
                ingestion["candidateSchemaEcho"] = looks_like_schema_echo(parsed)
            return ingestion
        return ingestion

    def write_failed_call_artifact(
        self,
        *,
        task_id: Optional[str] = None,
        target_kind: str = "generic",
        provider: str = "",
        model: str = "",
        schema_name: str = "",
        error: Any = "",
        raw_output_text: str = "",
        raw_response: Optional[Dict[str, Any]] = None,
        response_id: str = "",
        finish_reason: str = "",
        requested_max_output_tokens: int = 0,
        effective_max_output_tokens: int = 0,
        attempts: Optional[List[int]] = None,
        recovered_from_incomplete: bool = False,
        provider_trace: Optional[Dict[str, Any]] = None,
        auth_assignment: Optional[Dict[str, Any]] = None,
        failure_kind: str = "",
    ) -> Dict[str, Any]:
        normalized_provider = normalize_provider_id(provider, DEFAULT_PROVIDER_ID) if str(provider or "").strip() else "unknown"
        normalized_target = normalize_auth_target(target_kind)
        node_target = node_target_from_schema_or_target(schema_name, normalized_target)
        normalized_task_id = self.failed_call_task_id(task_id)
        detected_kind = str(failure_kind or "").strip().lower() or self.classify_failed_call_kind(error, raw_output_text, finish_reason)
        detected_kind = self.failed_call_filename_component(detected_kind, "provider_error", 40)
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S%f")
        compact_task = self.failed_call_filename_component(normalized_task_id, "task", 12).replace("-", "")
        compact_target = self.failed_call_filename_component(normalized_target, "target", 10).replace("-", "")
        compact_provider = self.failed_call_filename_component(normalized_provider, "provider", 8).replace("-", "")
        compact_kind = self.failed_call_filename_component(detected_kind, "failure", 12).replace("-", "")
        safe_name = "_".join(
            [
                "fc",
                compact_task,
                compact_target,
                compact_provider,
                compact_kind,
                timestamp,
            ]
        ) + ".json"
        response_meta = {
            "requestedMaxOutputTokens": max(0, int(requested_max_output_tokens or 0)),
            "effectiveMaxOutputTokens": max(0, int(effective_max_output_tokens or 0)),
            "maxOutputTokenAttempts": list(attempts or []),
            "recoveredFromIncomplete": bool(recovered_from_incomplete),
            "finishReason": str(finish_reason or "").strip() or None,
            "providerTrace": self.normalize_provider_trace(provider_trace),
        }
        payload: Dict[str, Any] = {
            "schemaVersion": "parallm.failed_call.v1",
            "artifactType": "failed_call",
            "capturedAt": utc_now(),
            "passStatus": "discarded_failed_attempt",
            "passedToNextNode": False,
            "handoffNote": "This raw provider payload failed validation and is stored for review only. It must not be used as a node handoff payload.",
            "taskId": normalized_task_id,
            "target": normalized_target,
            "targetNode": node_target,
            "targetLabel": provider_trace_target_label(node_target),
            "provider": normalized_provider,
            "providerLabel": PROVIDER_CATALOG.get(normalized_provider, {}).get("label") or normalized_provider.title(),
            "model": str(model or "").strip(),
            "schemaName": str(schema_name or "").strip(),
            "failureKind": detected_kind,
            "error": str(error or ""),
            "responseId": str(response_id or "").strip(),
            "rawOutputText": str(raw_output_text or ""),
            "ingestion": self.build_failed_call_ingestion(str(raw_output_text or ""), error),
            "responseMeta": response_meta,
            "auth": auth_assignment,
        }
        if isinstance(raw_response, dict):
            payload["rawProviderResponse"] = raw_response
        artifact_meta = artifact_store.write_json_artifact(self.root, "failed_calls", safe_name, payload)
        transfer_packet = self.write_node_transfer_artifact(
            task_id=normalized_task_id,
            source_node=f"{normalized_provider}:provider_ingress",
            target_nodes=[node_target],
            payload={
                "rawOutputText": str(raw_output_text or ""),
                "rawProviderResponse": raw_response if isinstance(raw_response, dict) else None,
                "error": str(error or ""),
                "failureKind": detected_kind,
                "responseId": str(response_id or "").strip(),
            },
            status="deceased",
            validation_status="reader_rejected" if str(raw_output_text or "").strip() else "provider_unavailable",
            failed_call_artifact=str(artifact_meta.get("name") or safe_name),
            failure_kind=detected_kind,
            error=error,
            retryable=detected_kind in {"overflow", "malformed_json", "timeout", "connection", "empty_output", "provider_error"},
            oversight_action="retry_same_node_or_spawn_adversary_if_repeated",
        )
        payload["nodeTransferArtifact"] = transfer_packet.get("artifact", {}).get("name")
        artifact_store.write_json_artifact(self.root, "failed_calls", safe_name, payload)
        return {
            "name": artifact_meta.get("name") or safe_name,
            "category": artifact_meta.get("category") or "failed_calls",
            "failureKind": detected_kind,
            "taskId": normalized_task_id,
            "target": normalized_target,
            "targetNode": node_target,
            "passStatus": "discarded_failed_attempt",
            "passedToNextNode": False,
            "nodeTransferArtifact": transfer_packet.get("artifact", {}).get("name"),
            "provider": normalized_provider,
            "model": str(model or "").strip(),
            "rawOutputAvailable": bool(str(raw_output_text or "").strip()),
            "modifiedAt": artifact_meta.get("modifiedAt"),
            "size": artifact_meta.get("size"),
        }

    def flatten_output_for_artifact(
        self,
        payload: Any,
        artifact_type: str,
        *,
        provider: str = "",
        model: str = "",
        task_id: str = "",
        target_kind: str = "generic",
        schema_name: str = "",
        raw_output_text: Any = "",
        raw_response: Optional[Dict[str, Any]] = None,
        response_id: str = "",
    ) -> str:
        try:
            flattened = flatten_output_payload_text(payload, artifact_type, provider_hint=provider)
        except Exception as error:
            self.write_failed_call_artifact(
                task_id=task_id,
                target_kind=target_kind,
                provider=provider,
                model=model,
                schema_name=schema_name,
                error=error,
                raw_output_text=str(raw_output_text or ""),
                raw_response=raw_response,
                response_id=response_id,
                failure_kind="flattener_error",
            )
            return ""
        if not str(flattened or "").strip():
            self.write_failed_call_artifact(
                task_id=task_id,
                target_kind=target_kind,
                provider=provider,
                model=model,
                schema_name=schema_name,
                error="Flattener returned empty output.",
                raw_output_text=str(raw_output_text or ""),
                raw_response=raw_response,
                response_id=response_id,
                failure_kind="flattener_empty",
            )
            return ""
        return str(flattened or "").strip()

    def run_direct_baseline(self) -> Dict[str, Any]:
        state = self.read_state()
        task = state.get("activeTask")
        if not isinstance(task, dict):
            raise RuntimeErrorWithCode("No active task.", 400)
        if isinstance(state.get("directBaseline"), dict):
            raise RuntimeErrorWithCode("Direct baseline already exists for the active task.", 409)
        direct_runtime = self.get_direct_baseline_runtime(task)
        if normalize_direct_baseline_mode(direct_runtime.get("mode")) == "off":
            raise RuntimeErrorWithCode("Direct baseline is disabled for the active task.", 409)

        baseline_answer: Optional[Dict[str, str]] = None
        response_id: Optional[str] = None
        response: Optional[Dict[str, Any]] = None
        usage_snapshot: Optional[Dict[str, Any]] = None
        call_meta: Dict[str, Any] = {
            "requestedMaxOutputTokens": int(direct_runtime["maxOutputTokens"]),
            "effectiveMaxOutputTokens": int(direct_runtime["maxOutputTokens"]),
            "attempts": [int(direct_runtime["maxOutputTokens"])] if int(direct_runtime["maxOutputTokens"]) > 0 else [],
            "recoveredFromIncomplete": False,
        }
        mode_used = "live"
        auth_assignments = self.provider_auth_assignments(direct_runtime["provider"], "direct_baseline", task, round_number=1)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(direct_runtime["provider"], auth_assignment)
        if direct_runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(direct_runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(direct_runtime["provider"]):
                self.assert_budget_available("direct_baseline", task)
                (baseline_answer, response_id, response, call_meta), live_attempts = self.execute_live_stage_with_retry(
                    stage="direct_baseline",
                    target_label="direct_baseline",
                    task_id=str(task["taskId"]),
                    model=direct_runtime["model"],
                    requested_max_output_tokens=int(direct_runtime["maxOutputTokens"]),
                    auth_meta=auth_meta,
                    call=lambda: self.new_live_direct_baseline(
                        api_key,
                        auth_assignments,
                        task,
                        direct_runtime,
                    ),
                )
                call_meta = dict(call_meta or {})
                call_meta["liveAttempts"] = int(live_attempts)
                auth_meta = self.live_auth_meta(direct_runtime["provider"], call_meta.get("auth"))
                self.append_auth_failover_step("direct_baseline", str(task["taskId"]), direct_runtime["model"], call_meta, "direct_baseline")
                usage_snapshot = self.update_usage_tracking("direct_baseline", str(task["taskId"]), direct_runtime["model"], response_id, response)
                mode_used = "live"
            else:
                if self.provider_uses_api_key_pool(direct_runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable(
                        "direct_baseline",
                        str(task["taskId"]),
                        direct_runtime["model"],
                        "direct_baseline",
                        direct_runtime["provider"],
                    )
                self.raise_live_stage_missing_credentials(
                    stage="direct_baseline",
                    target_label="direct_baseline",
                    task_id=str(task["taskId"]),
                    auth_meta=auth_meta,
                )
        if baseline_answer is None:
            raise RuntimeErrorWithCode("Live direct baseline did not produce a validated output.", 502)
        self.assert_execution_not_cancelled()

        baseline = {
            "taskId": str(task["taskId"]),
            "round": 1,
            "capturedAt": utc_now(),
            "mode": mode_used,
            "provider": direct_runtime["provider"],
            "providerCapabilities": provider_capability_profile(direct_runtime["provider"]),
            "model": direct_runtime["model"],
            "responseId": response_id,
            "responseMeta": {
                "status": str(response.get("status", "completed")),
                "usageDelta": self.get_response_usage_delta(response, direct_runtime["model"]),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", direct_runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", direct_runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "skills": normalize_string_array_preserve_items(call_meta.get("skills", [])),
                "providerTrace": self.normalize_provider_trace(call_meta.get("providerTrace")),
            } if response else None,
            "authMeta": auth_meta,
                "answer": normalize_direct_answer_payload(
                    baseline_answer,
                    str(task.get("objective") or ""),
                    provider=direct_runtime["provider"],
                ),
        }

        state = self.mutate_state(lambda current: {**current, "directBaseline": baseline})
        _, history_cp = self.write_direct_baseline_files(str(task["taskId"]), 1, baseline)
        output_artifact = {
            "taskId": str(task["taskId"]),
            "artifactType": "direct_baseline_output",
            "target": "direct_baseline",
            "label": "Single-thread baseline",
            "mode": mode_used,
            "provider": direct_runtime["provider"],
            "providerCapabilities": provider_capability_profile(direct_runtime["provider"]),
            "model": direct_runtime["model"],
            "round": 1,
            "capturedAt": baseline["capturedAt"],
            "responseId": response_id,
            "inputText": str(call_meta.get("inputText") or "").strip() or None,
            "fullPrompt": str(call_meta.get("fullPrompt") or "").strip() or None,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "flattenedOutputText": self.flatten_output_for_artifact(
                baseline,
                "direct_baseline_output",
                provider=direct_runtime["provider"],
                model=direct_runtime["model"],
                task_id=str(task["taskId"]),
                target_kind="direct_baseline",
                schema_name="direct_answer",
                raw_output_text=self.get_response_output_text(response) if response else "",
                raw_response=response,
                response_id=str(response_id or ""),
            ),
            "responseMeta": baseline["responseMeta"],
            "authMeta": auth_meta,
            "output": baseline,
        }
        _, history_output = self.write_output_artifact(
            f"{task['taskId']}_direct_baseline_output.json",
            f"{task['taskId']}_direct_baseline_round001_output.json",
            output_artifact,
        )
        self.write_node_transfer_artifact(
            task_id=str(task["taskId"]),
            source_node="direct_baseline",
            target_nodes=["summarizer", "review", "score_judge"],
            payload=baseline,
            status="accepted",
            validation_status="valid",
            checkpoint_artifact=str(history_cp),
            output_artifact=str(history_output),
        )
        budget_totals = usage_snapshot or normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
        self.append_event(
            "direct_baseline_written",
            {
                "taskId": task["taskId"],
                "mode": mode_used,
                "provider": direct_runtime["provider"],
                "model": direct_runtime["model"],
            },
        )
        self.append_step(
            "direct_baseline",
            "Single-thread baseline answer captured.",
            {
                "taskId": task["taskId"],
                "mode": mode_used,
                "provider": direct_runtime["provider"],
                "model": direct_runtime["model"],
                "responseId": response_id,
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", direct_runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", direct_runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "totalTokens": int(budget_totals.get("totalTokens", 0)),
                "estimatedCostUsd": float(budget_totals.get("estimatedCostUsd", 0.0)),
                "checkpointFile": history_cp.name,
                "outputFile": history_output.name,
                "auth": auth_meta,
            },
        )
        self.append_event(
            "runtime_run",
            {"target": "direct_baseline", "backend": "python", "exitCode": 0, "output": "Direct baseline written."},
        )
        return {"target": "direct_baseline", "output": "Direct baseline written.", "exitCode": 0}

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
        mode_used = "live"
        auth_assignments = self.provider_auth_assignments(runtime["provider"], "commander", task, round_number=round_number)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(runtime["provider"], auth_assignment)
        if runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(runtime["provider"]):
                self.assert_budget_available("commander", task)
                (checkpoint, response_id, response, call_meta), live_attempts = self.execute_live_stage_with_retry(
                    stage="commander",
                    target_label="commander",
                    task_id=str(task["taskId"]),
                    model=runtime["model"],
                    requested_max_output_tokens=int(runtime["maxOutputTokens"]),
                    auth_meta=auth_meta,
                    call=lambda: self.new_live_commander(
                        api_key,
                        auth_assignments,
                        task,
                        runtime,
                        round_number,
                        constraints,
                        prior_summary,
                    ),
                )
                call_meta = dict(call_meta or {})
                call_meta["liveAttempts"] = int(live_attempts)
                auth_meta = self.live_auth_meta(runtime["provider"], call_meta.get("auth"))
                self.append_auth_failover_step("commander", str(task["taskId"]), runtime["model"], call_meta, "commander")
                usage_snapshot = self.update_usage_tracking("commander", str(task["taskId"]), runtime["model"], response_id, response)
                mode_used = "live"
            else:
                if self.provider_uses_api_key_pool(runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable("commander", str(task["taskId"]), runtime["model"], "commander", runtime["provider"])
                self.raise_live_stage_missing_credentials(
                    stage="commander",
                    target_label="commander",
                    task_id=str(task["taskId"]),
                    auth_meta=auth_meta,
                )
        if checkpoint is None:
            raise RuntimeErrorWithCode("Live commander did not produce a validated checkpoint.", 502)
        checkpoint = normalize_commander_checkpoint(checkpoint, task, round_number)
        checkpoint["localToolCalls"] = normalize_local_tool_calls(call_meta.get("localToolCalls", []))
        checkpoint["localFileSources"] = normalize_string_array_preserve_items(call_meta.get("localFileSources", []))
        checkpoint["githubToolCalls"] = normalize_local_tool_calls(call_meta.get("githubToolCalls", []))
        checkpoint["githubSources"] = normalize_url_array_values(call_meta.get("githubSources", []))
        self.assert_execution_not_cancelled()

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
            "provider": runtime["provider"],
            "providerCapabilities": provider_capability_profile(runtime["provider"]),
            "model": runtime["model"],
            "round": round_number,
            "capturedAt": utc_now(),
            "responseId": response_id,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "flattenedOutputText": self.flatten_output_for_artifact(
                checkpoint,
                "commander_output",
                provider=runtime["provider"],
                model=runtime["model"],
                task_id=str(task["taskId"]),
                target_kind="commander",
                schema_name="commander_checkpoint",
                raw_output_text=self.get_response_output_text(response) if response else "",
                raw_response=response,
                response_id=str(response_id or ""),
            ),
            "responseMeta": {
                "status": str(response.get("status", "completed")),
                "usageDelta": self.get_response_usage_delta(response, runtime["model"]),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "skills": normalize_string_array_preserve_items(call_meta.get("skills", [])),
                "providerTrace": self.normalize_provider_trace(call_meta.get("providerTrace")),
                "localToolCalls": normalize_local_tool_calls(call_meta.get("localToolCalls", [])),
                "localFileSources": normalize_string_array_preserve_items(call_meta.get("localFileSources", [])),
                "githubToolCalls": normalize_local_tool_calls(call_meta.get("githubToolCalls", [])),
                "githubSources": normalize_url_array_values(call_meta.get("githubSources", [])),
            } if response else None,
            "authMeta": auth_meta,
            "skills": normalize_string_array_preserve_items(call_meta.get("skills", [])),
            "output": checkpoint,
        }
        _, history_output = self.write_output_artifact(
            f"{task['taskId']}_commander_output.json",
            f"{task['taskId']}_commander_round{round_number:03d}_output.json",
            output_artifact,
        )
        self.write_node_transfer_artifact(
            task_id=str(task["taskId"]),
            source_node="commander",
            target_nodes=["workers", "commander_review", "summarizer"],
            payload=checkpoint,
            status="accepted",
            validation_status="valid",
            checkpoint_artifact=str(history_cp),
            output_artifact=str(history_output),
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
        prior_summary = state.get("summary") if isinstance(state.get("summary"), dict) else None
        for worker in workers:
            checkpoint = worker_state.get(worker["id"])
            if not isinstance(checkpoint, dict) or int(checkpoint.get("step", 0) or 0) != commander_round:
                raise RuntimeErrorWithCode(
                    f"Worker {worker['id']} is not aligned with commander round {commander_round}.",
                    409,
                )
            self.verify_node_transfer_before_read(
                task_id=str(task["taskId"]),
                source_node=f"worker_{worker['id']}",
                target_node="commander_review",
                payload=checkpoint,
                stage="commander_review",
            )
        review_config = commander_review_config(task)
        runtime = self.get_task_runtime(task, review_config["model"], "commander_review", review_config["provider"])
        line_catalog = self.build_summary_line_catalog(worker_state, workers, max_items_per_worker=8)
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
        mode_used = "live"
        auth_assignments = self.provider_auth_assignments(runtime["provider"], "commander_review", task, round_number=commander_round)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(runtime["provider"], auth_assignment)
        if runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(runtime["provider"]):
                self.assert_budget_available("commander_review", task)
                (checkpoint, response_id, response, call_meta), live_attempts = self.execute_live_stage_with_retry(
                    stage="commander_review",
                    target_label="commander_review",
                    task_id=str(task["taskId"]),
                    model=runtime["model"],
                    requested_max_output_tokens=int(runtime["maxOutputTokens"]),
                    auth_meta=auth_meta,
                    call=lambda: self.new_live_commander_review(
                        api_key,
                        auth_assignments,
                        task,
                        commander_checkpoint,
                        prior_summary,
                        workers,
                        worker_state,
                        runtime,
                        line_catalog,
                    ),
                )
                call_meta = dict(call_meta or {})
                call_meta["liveAttempts"] = int(live_attempts)
                auth_meta = self.live_auth_meta(runtime["provider"], call_meta.get("auth"))
                self.append_auth_failover_step("commander_review", str(task["taskId"]), runtime["model"], call_meta, "commander_review")
                usage_snapshot = self.update_usage_tracking("commander_review", str(task["taskId"]), runtime["model"], response_id, response)
                mode_used = "live"
            else:
                if self.provider_uses_api_key_pool(runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable("commander_review", str(task["taskId"]), runtime["model"], "commander_review", runtime["provider"])
                self.raise_live_stage_missing_credentials(
                    stage="commander_review",
                    target_label="commander_review",
                    task_id=str(task["taskId"]),
                    auth_meta=auth_meta,
                )
        if checkpoint is None:
            raise RuntimeErrorWithCode("Live commander review did not produce a validated checkpoint.", 502)
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
        self.assert_execution_not_cancelled()

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
            "provider": runtime["provider"],
            "providerCapabilities": provider_capability_profile(runtime["provider"]),
            "model": runtime["model"],
            "round": commander_round,
            "capturedAt": utc_now(),
            "responseId": response_id,
            "inputText": str(call_meta.get("inputText") or "").strip() or None,
            "fullPrompt": str(call_meta.get("fullPrompt") or "").strip() or None,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "flattenedOutputText": self.flatten_output_for_artifact(
                checkpoint,
                "commander_review_output",
                provider=runtime["provider"],
                model=runtime["model"],
                task_id=str(task["taskId"]),
                target_kind="commander_review",
                schema_name="commander_review",
                raw_output_text=self.get_response_output_text(response) if response else "",
                raw_response=response,
                response_id=str(response_id or ""),
            ),
            "responseMeta": {
                "status": str(response.get("status", "completed")),
                "usageDelta": self.get_response_usage_delta(response, runtime["model"]),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "skills": normalize_string_array_preserve_items(call_meta.get("skills", [])),
                "providerTrace": self.normalize_provider_trace(call_meta.get("providerTrace")),
                "reviewMode": str(call_meta.get("reviewMode", "")),
                "lineCatalogIncluded": bool(call_meta.get("lineCatalogIncluded", False)),
                "schemaRequiredFields": normalize_string_array_preserve_items(call_meta.get("schemaRequiredFields", [])),
                "instructionsChars": int(call_meta.get("instructionsChars", 0) or 0),
                "inputTextChars": int(call_meta.get("inputTextChars", 0) or 0),
                "fullPromptChars": int(call_meta.get("fullPromptChars", 0) or 0),
                "softLimitChars": int(call_meta.get("softLimitChars", 0) or 0),
                "estimatedPromptTokens": int(call_meta.get("estimatedPromptTokens", 0) or 0),
                "dynamicLaneDecision": dynamic_lane_decision,
                "dynamicLaneResolution": dynamic_lane_resolution,
                "spawnedWorkerId": spawned_worker["id"] if spawned_worker else None,
            } if response else None,
            "authMeta": auth_meta,
            "skills": normalize_string_array_preserve_items(call_meta.get("skills", [])),
            "output": checkpoint,
        }
        _, history_output = self.write_output_artifact(
            f"{task['taskId']}_commander_review_output.json",
            f"{task['taskId']}_commander_review_round{commander_round:03d}_output.json",
            output_artifact,
        )
        self.write_node_transfer_artifact(
            task_id=str(task["taskId"]),
            source_node="commander_review",
            target_nodes=["workers", "summarizer"],
            payload=checkpoint,
            status="accepted",
            validation_status="valid",
            checkpoint_artifact=str(history_cp),
            output_artifact=str(history_output),
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
        if isinstance(commander_checkpoint, dict):
            self.verify_node_transfer_before_read(
                task_id=str(task["taskId"]),
                source_node="commander",
                target_node=f"worker_{worker_id}",
                payload=commander_checkpoint,
                stage=f"worker_{worker_id}",
            )
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
        mode_used = "live"
        auth_assignments = self.provider_auth_assignments(runtime["provider"], worker_id, task, round_number=commander_round)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(runtime["provider"], auth_assignment)
        if runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(runtime["provider"]):
                self.assert_budget_available(worker_id, task)
                (checkpoint, response_id, response, call_meta), live_attempts = self.execute_live_stage_with_retry(
                    stage=f"worker_{worker_id}",
                    target_label=worker_id,
                    task_id=str(task["taskId"]),
                    model=runtime["model"],
                    requested_max_output_tokens=int(runtime["maxOutputTokens"]),
                    auth_meta=auth_meta,
                    call=lambda: self.new_live_checkpoint(
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
                    ),
                    extra_context={"workerId": worker_id, "step": step_number},
                )
                call_meta = dict(call_meta or {})
                call_meta["liveAttempts"] = int(live_attempts)
                auth_meta = self.live_auth_meta(runtime["provider"], call_meta.get("auth"))
                self.append_auth_failover_step(f"worker_{worker_id}", str(task["taskId"]), runtime["model"], call_meta, worker_id)
                usage_snapshot = self.update_usage_tracking(worker_id, str(task["taskId"]), runtime["model"], response_id, response)
                mode_used = "live"
            else:
                if self.provider_uses_api_key_pool(runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable(f"worker_{worker_id}", str(task["taskId"]), runtime["model"], worker_id, runtime["provider"])
                self.raise_live_stage_missing_credentials(
                    stage=f"worker_{worker_id}",
                    target_label=worker_id,
                    task_id=str(task["taskId"]),
                    auth_meta=auth_meta,
                    extra_context={"workerId": worker_id, "step": step_number},
                )
        if checkpoint is None:
            raise RuntimeErrorWithCode(f"Live worker {worker_id} did not produce a validated checkpoint.", 502)
        checkpoint = self.normalize_checkpoint(task, worker_id, worker, runtime, checkpoint, step_number)
        self.assert_execution_not_cancelled()
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
            "provider": runtime["provider"],
            "providerCapabilities": provider_capability_profile(runtime["provider"]),
            "model": runtime["model"],
            "step": step_number,
            "capturedAt": utc_now(),
            "responseId": response_id,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "flattenedOutputText": self.flatten_output_for_artifact(
                checkpoint,
                "worker_output",
                provider=runtime["provider"],
                model=runtime["model"],
                task_id=str(task["taskId"]),
                target_kind=worker_id,
                schema_name="worker_checkpoint",
                raw_output_text=self.get_response_output_text(response) if response else "",
                raw_response=response,
                response_id=str(response_id or ""),
            ),
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
                "skills": normalize_string_array_preserve_items(call_meta.get("skills", [])),
                "providerTrace": self.normalize_provider_trace(call_meta.get("providerTrace")),
                "localToolCalls": normalize_local_tool_calls(call_meta.get("localToolCalls", [])),
                "localFileSources": normalize_string_array_preserve_items(call_meta.get("localFileSources", [])),
                "githubToolCalls": normalize_local_tool_calls(call_meta.get("githubToolCalls", [])),
                "githubSources": normalize_url_array_values(call_meta.get("githubSources", [])),
            }
            if response
            else None,
            "authMeta": auth_meta,
            "skills": normalize_string_array_preserve_items(call_meta.get("skills", [])),
            "output": checkpoint,
        }
        _, history_output = self.write_output_artifact(
            f"{task['taskId']}_{worker_id}_output.json",
            f"{task['taskId']}_{worker_id}_step{step_number:03d}_output.json",
            output_artifact,
        )
        self.write_node_transfer_artifact(
            task_id=str(task["taskId"]),
            source_node=f"worker_{worker_id}",
            target_nodes=["commander_review", "summarizer"],
            payload=checkpoint,
            status="accepted",
            validation_status="valid",
            checkpoint_artifact=str(history_cp),
            output_artifact=str(history_output),
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
        self.verify_node_transfer_before_read(
            task_id=str(task["taskId"]),
            source_node="commander_review",
            target_node="summarizer",
            payload=commander_review_checkpoint,
            stage="summarizer",
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
            self.verify_node_transfer_before_read(
                task_id=str(task["taskId"]),
                source_node=f"worker_{worker['id']}",
                target_node="summarizer",
                payload=checkpoint,
                stage="summarizer",
            )
            worker_state[worker["id"]] = checkpoint
        summary_config = summarizer_config(task)
        runtime = self.get_task_runtime(task, summary_config["model"], "summarizer", summary_config["provider"])
        vetting_config = self.get_vetting_config(task)
        line_catalog = self.build_summary_line_catalog(worker_state, workers, max_items_per_worker=10)
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
        mode_used = "live"
        auth_assignments = self.provider_auth_assignments(runtime["provider"], "summarizer", task, round_number=commander_round)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(runtime["provider"], auth_assignment)
        if runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(runtime["provider"]):
                self.assert_budget_available("summarizer", task)
                (summary, response_id, response, call_meta), live_attempts = self.execute_live_stage_with_retry(
                    stage="summarizer",
                    target_label="summarizer",
                    task_id=str(task["taskId"]),
                    model=runtime["model"],
                    requested_max_output_tokens=int(runtime["maxOutputTokens"]),
                    auth_meta=auth_meta,
                    call=lambda: self.new_live_summary(
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
                    ),
                )
                call_meta = dict(call_meta or {})
                call_meta["liveAttempts"] = int(live_attempts)
                auth_meta = self.live_auth_meta(runtime["provider"], call_meta.get("auth"))
                self.append_auth_failover_step("summarizer", str(task["taskId"]), runtime["model"], call_meta, "summarizer")
                usage_snapshot = self.update_usage_tracking("summarizer", str(task["taskId"]), runtime["model"], response_id, response)
                mode_used = "live"
            else:
                if self.provider_uses_api_key_pool(runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable("summarizer", str(task["taskId"]), runtime["model"], "summarizer", runtime["provider"])
                self.raise_live_stage_missing_credentials(
                    stage="summarizer",
                    target_label="summarizer",
                    task_id=str(task["taskId"]),
                    auth_meta=auth_meta,
                )
        if summary is None:
            raise RuntimeErrorWithCode("Live summarizer did not produce a validated summary.", 502)
        summary = self.normalize_summary(summary, line_catalog)
        contradiction_memory_packet = self.build_contradiction_memory_packet(
            task,
            runtime,
            commander_review_checkpoint,
            worker_state,
            workers,
            round_number=commander_round,
        )
        summary = self.apply_contradiction_memory_final_gates(summary, contradiction_memory_packet)
        summary = self.normalize_summary(summary, line_catalog)
        summary["partialSummary"] = False
        summary["round"] = commander_round
        dynamic_lane_decision = summary.get("dynamicLaneDecision") if isinstance(summary.get("dynamicLaneDecision"), dict) else {}
        self.assert_execution_not_cancelled()

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
            "provider": runtime["provider"],
            "providerCapabilities": provider_capability_profile(runtime["provider"]),
            "model": runtime["model"],
            "round": int(summary.get("round", 0) or 0),
            "capturedAt": utc_now(),
            "responseId": response_id,
            "inputText": str(call_meta.get("inputText") or "").strip() or None,
            "fullPrompt": str(call_meta.get("fullPrompt") or "").strip() or None,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "flattenedOutputText": self.flatten_output_for_artifact(
                summary,
                "summary_output",
                provider=runtime["provider"],
                model=runtime["model"],
                task_id=str(task["taskId"]),
                target_kind="summarizer",
                schema_name="loop_summary_multi",
                raw_output_text=self.get_response_output_text(response) if response else "",
                raw_response=response,
                response_id=str(response_id or ""),
            ),
            "responseMeta": {
                "status": str(response.get("status", "completed")),
                "usageDelta": self.get_response_usage_delta(response, runtime["model"]),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "skills": normalize_string_array_preserve_items(call_meta.get("skills", [])),
                "providerTrace": self.normalize_provider_trace(call_meta.get("providerTrace")),
                "summaryMode": str(call_meta.get("summaryMode", "")),
                "lineCatalogIncluded": bool(call_meta.get("lineCatalogIncluded", False)),
                "workerEvidenceIncluded": bool(call_meta.get("workerEvidenceIncluded", False)),
                "schemaRequiredFields": normalize_string_array_preserve_items(call_meta.get("schemaRequiredFields", [])),
                "instructionsChars": int(call_meta.get("instructionsChars", 0) or 0),
                "inputTextChars": int(call_meta.get("inputTextChars", 0) or 0),
                "fullPromptChars": int(call_meta.get("fullPromptChars", 0) or 0),
                "softLimitChars": int(call_meta.get("softLimitChars", 0) or 0),
                "estimatedPromptTokens": int(call_meta.get("estimatedPromptTokens", 0) or 0),
                "reviewBinderBudgetTokens": int(call_meta.get("reviewBinderBudgetTokens", 0) or 0),
                "reviewBinderEstimatedTokens": int(call_meta.get("reviewBinderEstimatedTokens", 0) or 0),
                "reviewBinderInitialTokens": int(call_meta.get("reviewBinderInitialTokens", 0) or 0),
                "reviewBinderCompacted": bool(call_meta.get("reviewBinderCompacted", False)),
                "contradictionMemory": call_meta.get("contradictionMemory") if isinstance(call_meta.get("contradictionMemory"), dict) else self.contradiction_memory_call_meta(contradiction_memory_packet),
                "modelContextWindowTokens": int(call_meta.get("modelContextWindowTokens", 0) or 0),
                "modelMaxOutputTokens": int(call_meta.get("modelMaxOutputTokens", 0) or 0),
            } if response else None,
            "authMeta": auth_meta,
            "skills": normalize_string_array_preserve_items(call_meta.get("skills", [])),
            "output": summary,
        }
        _, history_output = self.write_output_artifact(
            f"{task['taskId']}_summary_output.json",
            f"{task['taskId']}_summary_round{int(summary.get('round', 0) or 0):03d}_output.json",
            output_artifact,
        )
        self.write_node_transfer_artifact(
            task_id=str(task["taskId"]),
            source_node="summarizer",
            target_nodes=["review", "judge_learning", "memory_bank"],
            payload=summary,
            status="accepted",
            validation_status="valid",
            checkpoint_artifact=str(history_summary),
            output_artifact=str(history_output),
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
                "contradictionMemory": self.contradiction_memory_call_meta(contradiction_memory_packet),
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
        runtime["maxOutputTokens"] = requested_partial_tokens if requested_partial_tokens > 0 else 0
        if runtime["reasoningEffort"] in {"high", "xhigh"}:
            runtime["reasoningEffort"] = "medium"
        elif runtime["reasoningEffort"] == "none":
            runtime["reasoningEffort"] = "low"
        vetting_config = self.get_vetting_config(task)
        line_catalog = self.build_summary_line_catalog(worker_state, workers, max_items_per_worker=10)
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
        mode_used = "live"
        auth_assignments = self.provider_auth_assignments(runtime["provider"], "summarizer", task, round_number=commander_round)
        auth_assignment = auth_assignments[0] if auth_assignments else None
        auth_meta = self.live_auth_meta(runtime["provider"], auth_assignment)
        if runtime["executionMode"] == "live":
            api_key = self.provider_live_api_key(runtime["provider"], auth_assignments)
            if api_key or not self.provider_requires_api_key(runtime["provider"]):
                self.assert_budget_available("summarizer", task)
                (summary, response_id, response, call_meta), live_attempts = self.execute_live_stage_with_retry(
                    stage="summarizer",
                    target_label="answer_now",
                    task_id=str(task["taskId"]),
                    model=runtime["model"],
                    requested_max_output_tokens=int(runtime["maxOutputTokens"]),
                    auth_meta=auth_meta,
                    call=lambda: self.new_live_summary(
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
                    ),
                    extra_context={"reasoningEffort": runtime["reasoningEffort"]},
                    retry_message="Live Answer Now call failed; retrying live call.",
                    exhausted_message="Live Answer Now call failed after retries; no synthetic output was used.",
                )
                call_meta = dict(call_meta or {})
                call_meta["liveAttempts"] = int(live_attempts)
                auth_meta = self.live_auth_meta(runtime["provider"], call_meta.get("auth"))
                self.append_auth_failover_step("summarizer", str(task["taskId"]), runtime["model"], call_meta, "answer_now")
                usage_snapshot = self.update_usage_tracking("summarizer", str(task["taskId"]), runtime["model"], response_id, response)
                mode_used = "live"
            else:
                if self.provider_uses_api_key_pool(runtime["provider"]):
                    self.raise_if_managed_secret_backend_unavailable("summarizer", str(task["taskId"]), runtime["model"], "answer_now", runtime["provider"])
                self.raise_live_stage_missing_credentials(
                    stage="summarizer",
                    target_label="answer_now",
                    task_id=str(task["taskId"]),
                    auth_meta=auth_meta,
                    extra_context={"reasoningEffort": runtime["reasoningEffort"]},
                )
        if summary is None:
            raise RuntimeErrorWithCode("Live Answer Now did not produce a validated summary.", 502)
        summary = self.normalize_summary(summary, line_catalog)
        contradiction_memory_packet = self.build_contradiction_memory_packet(
            task,
            runtime,
            commander_review_checkpoint if isinstance(commander_review_checkpoint, dict) and int(commander_review_checkpoint.get("round", 0) or 0) == commander_round else None,
            worker_state,
            workers,
            round_number=commander_round,
        )
        summary = self.apply_contradiction_memory_final_gates(summary, contradiction_memory_packet)
        summary = self.normalize_summary(summary, line_catalog)
        summary["round"] = commander_round
        summary = self.annotate_partial_summary(summary, list(worker_state.keys()), pending_workers)
        self.assert_execution_not_cancelled()
        summary_write_applied = {"value": False}
        def update_state(current: Dict[str, Any]) -> Dict[str, Any]:
            current_summary = current.get("summary") if isinstance(current.get("summary"), dict) else None
            current_summary_round = int((current_summary or {}).get("round", 0) or 0)
            current_summary_partial = bool((current_summary or {}).get("partialSummary"))
            current_commander = current.get("commander") if isinstance(current.get("commander"), dict) else None
            current_commander_round = int((current_commander or {}).get("round", 0) or 0)
            if current_commander_round > commander_round:
                return current
            if current_summary_round > commander_round:
                return current
            if current_summary_round == commander_round and not current_summary_partial:
                return current
            current["summary"] = summary
            current["memoryVersion"] = int(current.get("memoryVersion", 0) or 0) + 1
            summary_write_applied["value"] = True
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
            "provider": runtime["provider"],
            "providerCapabilities": provider_capability_profile(runtime["provider"]),
            "model": runtime["model"],
            "round": int(summary.get("round", 0) or 0),
            "capturedAt": utc_now(),
            "responseId": response_id,
            "inputText": str(call_meta.get("inputText") or "").strip() or None,
            "fullPrompt": str(call_meta.get("fullPrompt") or "").strip() or None,
            "rawOutputText": self.get_response_output_text(response) if response else None,
            "flattenedOutputText": self.flatten_output_for_artifact(
                summary,
                "summary_partial_output",
                provider=runtime["provider"],
                model=runtime["model"],
                task_id=str(task["taskId"]),
                target_kind="answer_now",
                schema_name="loop_summary_multi",
                raw_output_text=self.get_response_output_text(response) if response else "",
                raw_response=response,
                response_id=str(response_id or ""),
            ),
            "responseMeta": {
                "status": str(response.get("status", "completed")),
                "usageDelta": self.get_response_usage_delta(response, runtime["model"]),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "partialSummary": True,
                "providerTrace": self.normalize_provider_trace(call_meta.get("providerTrace")),
                "summaryMode": str(call_meta.get("summaryMode", "")),
                "lineCatalogIncluded": bool(call_meta.get("lineCatalogIncluded", False)),
                "workerEvidenceIncluded": bool(call_meta.get("workerEvidenceIncluded", False)),
                "schemaRequiredFields": normalize_string_array_preserve_items(call_meta.get("schemaRequiredFields", [])),
                "contradictionMemory": call_meta.get("contradictionMemory") if isinstance(call_meta.get("contradictionMemory"), dict) else self.contradiction_memory_call_meta(contradiction_memory_packet),
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
        self.write_node_transfer_artifact(
            task_id=str(task["taskId"]),
            source_node="answer_now",
            target_nodes=["review"],
            payload=summary,
            status="accepted" if summary_write_applied.get("value") else "superseded",
            validation_status="valid",
            checkpoint_artifact=str(history_summary),
            output_artifact=str(history_output),
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
                "contradictionMemory": self.contradiction_memory_call_meta(contradiction_memory_packet),
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "totalTokens": int(budget_totals.get("totalTokens", 0)),
                "estimatedCostUsd": float(budget_totals.get("estimatedCostUsd", 0.0)),
                "checkpointFile": history_summary.name,
                "outputFile": history_output.name,
                "stateSummaryUpdated": bool(summary_write_applied["value"]),
                "auth": auth_meta,
            },
        )
        self.append_event(
            "runtime_run",
            {"target": "answer_now", "backend": "python", "exitCode": 0, "output": "Partial summary written."},
        )
        return {"target": "answer_now", "output": "Partial summary written.", "exitCode": 0}

    def run_target(self, target: str, task_id: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        execution_context = dict(options or {})
        if task_id:
            execution_context["taskId"] = str(task_id or "")
            execution_context["stateScopeTaskId"] = str(task_id or "")
        execution_context["traceTarget"] = str(target or "").strip()
        self.set_execution_context(execution_context)
        self.clear_provider_trace()
        try:
            self.assert_execution_not_cancelled()
            current_state = self.read_state()
            task = current_state.get("activeTask")
            if not isinstance(task, dict):
                raise RuntimeErrorWithCode("No active task.", 400)
            if task_id and str(task.get("taskId", "")) != str(task_id):
                raise RuntimeErrorWithCode("Requested task does not match the active task.", 409)
            execution_context["taskId"] = str(task.get("taskId") or "")
            self.set_execution_context(execution_context)
            self.assert_execution_not_cancelled()
            if target == "commander":
                return self.run_commander()
            if target == "direct_baseline":
                return self.run_direct_baseline()
            if target == "commander_review":
                return self.run_commander_review()
            if target == "summarizer":
                return self.run_summarizer()
            if target == "answer_now" or (isinstance(options, dict) and options.get("partialSummary") and target == "summarizer"):
                return self.run_answer_now()
            return self.run_worker(target)
        finally:
            self.clear_execution_context()
