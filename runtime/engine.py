from __future__ import annotations

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
from urllib.parse import urlsplit, urlunsplit


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

WORKER_TEMPERATURE_CATALOG: Dict[str, Dict[str, str]] = {
    "cool": {"label": "Cool", "instruction": "deliberate, restrained, careful under pressure"},
    "balanced": {"label": "Balanced", "instruction": "practical, even-tempered, evidence-first"},
    "hot": {"label": "Hot", "instruction": "provocative, forceful, aggressively pressure-testing"},
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
WEB_SEARCH_TOOL_CALL_PRICE_USD = 0.01


class RuntimeErrorWithCode(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_budget_config() -> Dict[str, Any]:
    return {"maxTotalTokens": 250000, "maxCostUsd": 5.0, "maxOutputTokens": 1200}


def default_research_config() -> Dict[str, Any]:
    return {"enabled": False, "externalWebAccess": True, "domains": []}


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
        "workers": {},
        "summary": None,
        "memoryVersion": 0,
        "usage": default_usage_state(),
        "loop": default_loop_state(),
        "lastUpdated": utc_now(),
    }


def normalize_model_id(model: Optional[str], fallback: Optional[str] = None) -> str:
    candidate = (model or "").strip()
    if candidate in MODEL_CATALOG:
        return candidate
    fallback_value = (fallback or DEFAULT_MODEL_ID).strip()
    return fallback_value if fallback_value in MODEL_CATALOG else DEFAULT_MODEL_ID


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
    return {
        "maxTotalTokens": max(0, int(config.get("maxTotalTokens", default["maxTotalTokens"]))),
        "maxCostUsd": round(max(0.0, float(config.get("maxCostUsd", default["maxCostUsd"]))), 6),
        "maxOutputTokens": max(0, int(config.get("maxOutputTokens", default["maxOutputTokens"]))),
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


def worker_catalog(default_model: Optional[str] = None) -> List[Dict[str, str]]:
    model = normalize_model_id(default_model, DEFAULT_MODEL_ID)
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
    return {
        "id": worker_id,
        "type": worker_type,
        "label": str(worker.get("label", catalog_worker["label"])).strip() or catalog_worker["label"],
        "role": str(worker.get("role", catalog_worker["role"])).strip() or catalog_worker["role"],
        "focus": str(worker.get("focus", catalog_worker["focus"])).strip() or catalog_worker["focus"],
        "temperature": normalize_worker_temperature(worker.get("temperature"), str(catalog_worker.get("temperature", "balanced"))),
        "model": normalize_model_id(worker.get("model"), fallback_model),
    }


def task_workers(task: Dict[str, Any]) -> List[Dict[str, str]]:
    default_model = normalize_model_id((task.get("runtime") or {}).get("model"), DEFAULT_MODEL_ID)
    workers: Dict[str, Dict[str, str]] = {}
    raw_workers = task.get("workers")
    if isinstance(raw_workers, list):
        for worker in raw_workers:
            if isinstance(worker, dict):
                normalized = normalize_worker_definition(worker, default_model)
                workers[normalized["id"]] = normalized
    if not workers:
        for worker in worker_catalog(default_model)[:2]:
            normalized = normalize_worker_definition(worker, default_model)
            workers[normalized["id"]] = normalized
    return [workers[key] for key in sorted(workers)]


def find_task_worker(task: Dict[str, Any], worker_id: str) -> Optional[Dict[str, str]]:
    target = worker_id.strip().upper()
    for worker in task_workers(task):
        if worker["id"] == target:
            return worker
    return None


def summarizer_config(task: Dict[str, Any]) -> Dict[str, str]:
    default_model = normalize_model_id((task.get("runtime") or {}).get("model"), DEFAULT_MODEL_ID)
    summary = task.get("summarizer") if isinstance(task.get("summarizer"), dict) else {}
    return {
        "id": "summarizer",
        "label": str(summary.get("label", "Summarizer")).strip() or "Summarizer",
        "model": normalize_model_id(summary.get("model"), default_model),
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
    parsed: Dict[str, Any]
    response: Dict[str, Any]
    response_id: str
    output_text: Optional[str]
    web_search_queries: List[str]
    web_search_sources: List[str]
    url_citations: List[str]
    requested_max_output_tokens: int
    effective_max_output_tokens: int
    attempts: List[int]
    recovered_from_incomplete: bool


class LoopRuntime:
    def __init__(self, root: str | Path) -> None:
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
        self.auth_path = self.root / "Auth.txt"

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

    def normalize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = default_state()
        normalized["activeTask"] = state.get("activeTask")
        normalized["draft"] = state.get("draft") if isinstance(state.get("draft"), dict) else normalized["draft"]
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
        if not self.auth_path.exists():
            return None
        key = self.auth_path.read_text(encoding="utf-8").strip()
        return key or None

    def get_task_runtime(self, task: Dict[str, Any], model_override: Optional[str] = None) -> Dict[str, Any]:
        runtime = {
            "executionMode": "live",
            "model": DEFAULT_MODEL_ID,
            "reasoningEffort": "low",
            "maxOutputTokens": default_budget_config()["maxOutputTokens"],
            "research": default_research_config(),
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
            runtime["model"] = normalize_model_id(task_runtime.get("model"), runtime["model"])
            runtime["maxOutputTokens"] = normalize_budget_config(task_runtime.get("budget") if isinstance(task_runtime.get("budget"), dict) else {})["maxOutputTokens"]
            runtime["research"] = normalize_research_config(task_runtime.get("research") if isinstance(task_runtime.get("research"), dict) else {})
            runtime["vetting"] = normalize_vetting_config(task_runtime.get("vetting") if isinstance(task_runtime.get("vetting"), dict) else {})
        if model_override:
            runtime["model"] = normalize_model_id(model_override, runtime["model"])
        return runtime

    def get_research_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_research_config(task_runtime.get("research") if isinstance(task_runtime.get("research"), dict) else {})

    def get_vetting_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_vetting_config(task_runtime.get("vetting") if isinstance(task_runtime.get("vetting"), dict) else {})

    def get_budget_config(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_runtime = task.get("runtime") if isinstance(task.get("runtime"), dict) else {}
        return normalize_budget_config(task_runtime.get("budget") if isinstance(task_runtime.get("budget"), dict) else {})

    def get_model_pricing(self, model: str) -> Dict[str, Any]:
        resolved = normalize_model_id(model, DEFAULT_MODEL_ID)
        pricing = MODEL_CATALOG.get(resolved, {"inputPer1M": 0.0, "cachedInputPer1M": 0.0, "outputPer1M": 0.0})
        return {"model": resolved, **pricing}

    def get_response_output_text(self, response: Dict[str, Any]) -> Optional[str]:
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return str(content["text"])
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

    def get_response_usage_delta(self, response: Dict[str, Any], model: str) -> Optional[Dict[str, Any]]:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return None
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
                self._write_json_file(self.tasks_path / f"{task_id}.json", active_task)
            self.write_state_unlocked(state)
            return usage

    def get_budget_status(self, task: Dict[str, Any], usage: Dict[str, Any]) -> Dict[str, Any]:
        budget = self.get_budget_config(task)
        normalized_usage = normalize_usage_state(usage)
        reasons: List[str] = []
        if int(budget["maxTotalTokens"]) > 0 and int(normalized_usage["totalTokens"]) >= int(budget["maxTotalTokens"]):
            reasons.append(f"tokens {int(normalized_usage['totalTokens'])}/{int(budget['maxTotalTokens'])}")
        if float(budget["maxCostUsd"]) > 0 and float(normalized_usage["estimatedCostUsd"]) >= float(budget["maxCostUsd"]):
            reasons.append(
                f"estimated cost ${float(normalized_usage['estimatedCostUsd']):0.4f}/${float(budget['maxCostUsd']):0.4f}"
            )
        return {"exceeded": bool(reasons), "message": "; ".join(reasons), "budget": budget, "usage": normalized_usage}

    def assert_budget_available(self, target: str, task: Dict[str, Any]) -> None:
        state = self.read_state()
        status = self.get_budget_status(task, state.get("usage") if isinstance(state.get("usage"), dict) else {})
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
        )
        return not any(marker in message for marker in fatal_markers)

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
    ) -> OpenAIResult:
        attempts = self.build_output_token_attempts(max_output_tokens, target_kind)
        last_error: Optional[RuntimeErrorWithCode] = None
        recovered_from_incomplete = False

        for index, effective_tokens in enumerate(attempts):
            body: Dict[str, Any] = {
                "model": model,
                "instructions": instructions,
                "input": input_text,
                "reasoning": {"effort": reasoning_effort},
                "text": {
                    "verbosity": "low",
                    "format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema},
                },
            }
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
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=180) as handle:
                    response = json.loads(handle.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                body_text = error.read().decode("utf-8", errors="replace")
                raise RuntimeErrorWithCode(f"OpenAI API request failed: HTTP {error.code} | {body_text}", 500)
            except Exception as error:
                raise RuntimeErrorWithCode(f"OpenAI API request failed: {error}", 500)

            if isinstance(response.get("error"), dict):
                raise RuntimeErrorWithCode(f"Model response error: {json.dumps(response['error'], ensure_ascii=False)}", 500)

            incomplete_details = response.get("incomplete_details") if isinstance(response.get("incomplete_details"), dict) else {}
            incomplete_reason = str(incomplete_details.get("reason", "")).strip()
            if response.get("status") == "incomplete" and incomplete_reason == "max_output_tokens" and index < len(attempts) - 1:
                recovered_from_incomplete = True
                last_error = RuntimeErrorWithCode(f"Model response incomplete: {incomplete_reason}", 500)
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
                parsed=parsed,
                response=response,
                response_id=str(response.get("id", "")),
                output_text=output_text,
                web_search_queries=normalize_string_array_preserve_items(self.get_response_web_search_queries(response)),
                web_search_sources=normalize_url_array_values(self.get_response_web_search_sources(response)),
                url_citations=normalize_url_array_values(self.get_response_url_citations(response)),
                requested_max_output_tokens=max(0, int(max_output_tokens or 0)),
                effective_max_output_tokens=effective_tokens,
                attempts=attempts,
                recovered_from_incomplete=recovered_from_incomplete,
            )

        if last_error is not None:
            raise last_error
        raise RuntimeErrorWithCode("Model response did not produce a usable structured output.", 500)

    def build_output_token_attempts(self, requested_max_output_tokens: int, target_kind: str) -> List[int]:
        requested = max(0, int(requested_max_output_tokens or 0))
        kind = target_kind.strip().lower()
        if kind == "worker":
            floor = 900
            retry_floor = 1800
            hard_ceiling = 4000
        elif kind == "summarizer":
            floor = 1400
            retry_floor = 2800
            hard_ceiling = 6000
        else:
            floor = 900
            retry_floor = 1800
            hard_ceiling = 4000

        initial = max(requested, floor)
        attempts = [initial]

        retry_candidate = max(initial * 2, retry_floor)
        retry_candidate = min(retry_candidate, max(initial, hard_ceiling))
        if retry_candidate > initial:
            attempts.append(retry_candidate)

        deduped: List[int] = []
        for value in attempts:
            if value not in deduped:
                deduped.append(value)
        return deduped

    def get_default_request_targets(self, task: Dict[str, Any], current_worker_id: str) -> List[str]:
        peer_ids = [worker["id"] for worker in task_workers(task) if worker["id"] != current_worker_id]
        if not peer_ids:
            return []
        if current_worker_id == "A" and "B" in peer_ids:
            return ["B"]
        if current_worker_id != "A" and "A" in peer_ids:
            return ["A"]
        return [peer_ids[0]]

    def normalize_request_targets(self, targets: Any, task: Dict[str, Any], current_worker_id: str) -> List[str]:
        valid_targets = {
            worker["id"]: True
            for worker in task_workers(task)
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
        return self.get_default_request_targets(task, current_worker_id)

    def get_peer_steer_messages(self, state: Dict[str, Any], task: Dict[str, Any], worker_id: str) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        workers_state = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        for peer in task_workers(task):
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

    def expand_peer_steer_packets(self, task: Dict[str, Any], state: Dict[str, Any]) -> List[Dict[str, str]]:
        packets: List[Dict[str, str]] = []
        workers_state = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        roster = task_workers(task)
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
            "requestTargets": self.get_default_request_targets(task, worker["id"]),
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
        task: Dict[str, Any],
        worker: Dict[str, str],
        runtime: Dict[str, Any],
        research_config: Dict[str, Any],
        step_number: int,
        constraints: List[str],
        prior_summary: Optional[Dict[str, Any]],
        prior_memory_version: int,
        peer_messages: List[Dict[str, str]],
    ) -> tuple[Dict[str, Any], str, Dict[str, Any], Dict[str, Any]]:
        peer_targets = [item["id"] for item in task_workers(task) if item["id"] != worker["id"]]
        peer_text = "\n".join(f"{item['from']}: {item['message']}" for item in peer_messages) if peer_messages else "No peer steer received yet."
        session_context = str(task.get("sessionContext", "")).strip()
        summary_projection = self.project_prior_summary_for_worker(prior_summary)
        summary_text = json.dumps(summary_projection, ensure_ascii=False, indent=2) if summary_projection else "none"
        instructions = (
            f"You are {worker['label']} in a sparse multi-lane reasoning loop.\n"
            f"Worker type: {worker.get('type', 'custom')}.\n"
            f"Role: {worker['role']}.\n"
            f"Your special focus is: {worker['focus']}.\n"
            f"Reasoning temperature: {worker.get('temperature', 'balanced')} ({WORKER_TEMPERATURE_CATALOG.get(worker.get('temperature', 'balanced'), {}).get('instruction', 'practical and evidence-first')}).\n"
            "Return JSON only that matches the schema exactly.\n"
            "Be concise but specific.\n"
            "Keep observation to 2 short sentences maximum.\n"
            "For each array field, return at most 3 items.\n"
            "Keep each string item compact, ideally under 18 words.\n"
            "Limit evidenceLedger to 2 concrete claims.\n"
            "Keep requestToPeer to 1 short sentence.\n"
            "Preserve disagreement rather than smoothing it away.\n"
            "Your checkpoint is steering pressure for a later lead answer; do not try to sound like the final user-facing assistant.\n"
            "Push, qualify, or defend from your lane, but do not narrate the whole system.\n"
            "Do not reveal hidden chain-of-thought.\n"
            f"Set workerId to {worker['id']}, label to {worker['label']}, role to {worker['role']}, focus to {worker['focus']}, modelUsed to {runtime['model']}, and step to {step_number}.\n"
            f"requestTargets must only contain peers from this list: {', '.join(peer_targets)}.\n"
            "If researchMode is web_search, use the web search tool before answering and keep evidence grounded in URLs actually consulted.\n"
            "Every evidenceLedger item must capture one concrete claim, its supportLevel, the relevant sourceUrls, and a short note on why the evidence matters.\n"
            "If evidence is missing or weak, say so in evidenceGaps instead of overstating certainty."
        )
        research_description = "Enabled. Workers may use web_search." if research_config["enabled"] else "Disabled. Workers must reason from existing context only."
        research_domains_text = ", ".join(research_config["domains"]) if research_config["domains"] else "none"
        input_text = (
            f"Objective:\n{task['objective']}\n\n"
            f"Session context:\n{session_context or 'none'}\n\n"
            f"Constraints:\n{chr(10).join(constraints)}\n\n"
            f"Worker roster:\n{json.dumps(task.get('workers', []), ensure_ascii=False, indent=2)}\n\n"
            f"Research policy:\n{research_description}\n"
            f"externalWebAccess: {research_config['externalWebAccess']}\n"
            f"allowedDomains: {research_domains_text}\n\n"
            f"Shared memory version seen:\n{prior_memory_version}\n\n"
            f"Prior summary:\n{summary_text}\n\n"
            f"Peer steer addressed to this lane:\n{peer_text}\n\n"
            "Produce a checkpoint from your assigned viewpoint."
        )
        tools: List[Dict[str, Any]] = []
        tool_choice: Optional[str] = None
        include: List[str] = []
        if research_config["enabled"]:
            web_search_tool: Dict[str, Any] = {"type": "web_search", "external_web_access": bool(research_config["externalWebAccess"])}
            if research_config["domains"]:
                web_search_tool["filters"] = {"allowed_domains": list(research_config["domains"])}
            tools = [web_search_tool]
            tool_choice = "auto"
            include = ["web_search_call.action.sources"]
        result = self.invoke_openai_json(
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
        )
        parsed = dict(result.parsed)
        parsed["researchQueries"] = normalize_string_array_preserve_items(result.web_search_queries)
        parsed["researchSources"] = normalize_url_array_values(result.web_search_sources)
        parsed["urlCitations"] = normalize_url_array_values(result.url_citations)
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
        }
        return parsed, result.response_id, result.response, call_meta

    def project_task_for_summary(self, task: Dict[str, Any]) -> Dict[str, Any]:
        runtime = self.get_task_runtime(task)
        return {
            "taskId": str(task.get("taskId", "")),
            "objective": truncate_text(task.get("objective", ""), 800),
            "sessionContext": truncate_text(task.get("sessionContext", ""), 600),
            "constraints": limit_string_list(task.get("constraints", []), 12, 240),
            "syncPolicy": task.get("syncPolicy") if isinstance(task.get("syncPolicy"), dict) else {},
            "runtime": {
                "executionMode": str(runtime["executionMode"]),
                "reasoningEffort": str(runtime["reasoningEffort"]),
                "budget": self.get_budget_config(task),
                "research": self.get_research_config(task),
                "vetting": self.get_vetting_config(task),
            },
        }

    def project_prior_summary_for_worker(self, prior_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(prior_summary, dict):
            return {}
        review_trace = normalize_review_trace(prior_summary.get("reviewTrace", []))
        return {
            "taskId": str(prior_summary.get("taskId", "")),
            "round": int(prior_summary.get("round", 0) or 0),
            "frontAnswer": normalize_front_answer(prior_summary.get("frontAnswer"), prior_summary),
            "summarizerOpinion": normalize_summarizer_opinion(prior_summary.get("summarizerOpinion"), prior_summary),
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
        packets = self.expand_peer_steer_packets(task, {"workers": worker_state})
        conflicts: List[Dict[str, Any]] = []
        review_trace: List[Dict[str, Any]] = []
        primary = next((worker for worker in workers if worker["id"] == "A"), workers[0] if workers else None)
        challengers = [worker for worker in workers if worker["id"] != "A"][:3]

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
        front_answer_text = (
            "My current answer is to keep one clear lead voice in the front chat and let the adversarial lanes sharpen it behind the scenes.\n\n"
            "The answer should not read like a recap of a debate. It should read like one mind reached a view, then let the strongest objections narrow, qualify, or reverse weak parts before speaking."
        )
        return {
            "taskId": task["taskId"],
            "round": round_number,
            "frontAnswer": {
                "answer": front_answer_text,
                "stance": "The public answer should be a shaped judgment, not a recap of the internal lanes.",
                "leadDirection": "Answer in one voice with one directional thesis, then pressure-test it privately before it reaches the user.",
                "adversarialPressure": "The strongest shaping pressure is that adversarial reasoning should tighten the answer without taking over the public voice.",
                "confidenceNote": (
                    "This is a mock adjudication based on checkpoint structure, so the reasoning shape is stronger than the factual validation."
                    if vetting_config["enabled"]
                    else "Vetting is disabled here, so this opinion is structurally useful but weakly evidenced."
                ),
            },
            "summarizerOpinion": {
                "stance": "I would keep the single-voice chat illusion and move process transparency into review surfaces.",
                "because": "The strongest combined signal is that the user wants a normal answer up front while still preserving the adversarial pressure and audit trail for review.",
                "uncertainty": "The review depth should stay adjustable so the trace remains useful instead of becoming noise.",
                "integrationMode": "Start with a lead answer, then let the strongest objections narrow, condition, redirect, or overturn it before the final wording is shown.",
            },
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
            "sourceWorkers": [worker["id"] for worker in workers],
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
        task: Dict[str, Any],
        workers: List[Dict[str, str]],
        worker_state: Dict[str, Any],
        runtime: Dict[str, Any],
        vetting_config: Dict[str, Any],
        line_catalog: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], str, Dict[str, Any], Dict[str, Any]]:
        instructions = (
            "You are the summarizer in a sparse multi-lane reasoning loop.\n"
            "Merge all worker checkpoints into a structured adjudication.\n"
            "Act as the evidence vetter for the shared memory.\n"
            "Preserve disagreements and conditional truths.\n"
            "Do not erase contradictions.\n"
            "Judge worker claims using the evidence they provide.\n"
            "Form an opinion from the worker evidence and arguments instead of narrating the process.\n"
            "Treat the public answer as a lead thought, not a consensus blend.\n"
            "First decide what you would say if you had to answer alone.\n"
            "Then let the strongest adversarial lines narrow, qualify, redirect, or overturn that lead thought.\n"
            "Use adversarial pressure to improve the answer, not to speak directly through it.\n"
            "frontAnswer.answer must read like a normal single-assistant reply to the user.\n"
            "frontAnswer.answer should feel more reasonable because it privately absorbed objections, not because it publicly recaps them.\n"
            "Prefer a decisive but conditional answer over a timid laundry list of caveats.\n"
            "Do not mention workers, lanes, adversaries, or hidden process inside frontAnswer.answer unless the user explicitly asked for process detail.\n"
            "frontAnswer.stance should capture your current view in one sentence.\n"
            "frontAnswer.leadDirection should state the answer's leading direction before pressure-testing refined it.\n"
            "frontAnswer.adversarialPressure should name the strongest internal objection that changed or constrained the answer.\n"
            "summarizerOpinion is review-facing and may speak in the first person.\n"
            "summarizerOpinion.integrationMode should explain how the strongest objections changed the lead direction.\n"
            "reviewTrace is for review operations, not for the public answer.\n"
            "Every reviewTrace line ref must come from the supplied line catalog exactly as written.\n"
            "Do not upgrade weak evidence into a supported fact.\n"
            "Do not do new research.\n"
            "If vetting is disabled, keep verdicts conservative and mark unsupported confidence clearly.\n"
            "Keep frontAnswer.answer to at most 3 short paragraphs.\n"
            "Keep reviewTrace to at most 4 items.\n"
            "Keep stableFindings, conditionalTruths, and claimsNeedingVerification to at most 3 items each.\n"
            "Keep conflicts to at most 2 topics and evidenceVerdicts to at most 3 claims.\n"
            "Keep vettingSummary, recommendedNextAction, and frontAnswer.confidenceNote brief.\n"
            "Return JSON only that matches the schema exactly."
        )
        input_text = (
            f"Task brief:\n{json.dumps(self.project_task_for_summary(task), ensure_ascii=False, indent=2)}\n\n"
            f"Worker lineup:\n{json.dumps(self.project_worker_roster_for_summary(workers), ensure_ascii=False, indent=2)}\n\n"
            f"Vetting enabled:\n{vetting_config['enabled']}\n\n"
            f"Worker checkpoint digests:\n{json.dumps(self.project_worker_state_for_summary(worker_state, workers), ensure_ascii=False, indent=2)}\n\n"
            f"Worker review line catalog:\n{json.dumps(line_catalog, ensure_ascii=False, indent=2)}"
        )
        result = self.invoke_openai_json(
            api_key=api_key,
            model=runtime["model"],
            reasoning_effort=runtime["reasoningEffort"],
            instructions=instructions,
            input_text=input_text,
            schema_name="loop_summary_multi",
            schema=self.summary_schema(),
            max_output_tokens=int(runtime["maxOutputTokens"]),
            target_kind="summarizer",
        )
        parsed = dict(result.parsed)
        parsed["evidenceVerdicts"] = normalize_evidence_verdicts(parsed.get("evidenceVerdicts", []))
        parsed["claimsNeedingVerification"] = normalize_string_array_preserve_items(parsed.get("claimsNeedingVerification", []))
        parsed["mergedAt"] = utc_now()
        call_meta = {
            "requestedMaxOutputTokens": result.requested_max_output_tokens,
            "effectiveMaxOutputTokens": result.effective_max_output_tokens,
            "attempts": result.attempts,
            "recoveredFromIncomplete": result.recovered_from_incomplete,
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
        ):
            checkpoint[field] = normalize_string_array_preserve_items(checkpoint.get(field, []))
        checkpoint["researchSources"] = normalize_url_array_values(checkpoint.get("researchSources", []))
        checkpoint["urlCitations"] = normalize_url_array_values(checkpoint.get("urlCitations", []))
        checkpoint["evidenceLedger"] = normalize_evidence_ledger(checkpoint.get("evidenceLedger", []))
        checkpoint["requestTargets"] = self.normalize_request_targets(checkpoint.get("requestTargets", []), task, worker_id)
        checkpoint["updatedAt"] = utc_now()
        return checkpoint

    def normalize_summary(self, summary: Dict[str, Any], line_catalog: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        summary["frontAnswer"] = normalize_front_answer(summary.get("frontAnswer"), summary)
        summary["summarizerOpinion"] = normalize_summarizer_opinion(summary.get("summarizerOpinion"), summary)
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

    def write_worker_checkpoint_files(self, task_id: str, worker_id: str, step_number: int, checkpoint: Dict[str, Any]) -> tuple[Path, Path]:
        latest = self.checkpoints_path / f"{task_id}_{worker_id}.json"
        history = self.checkpoints_path / f"{task_id}_{worker_id}_step{step_number:03d}.json"
        payload = json.dumps(checkpoint, indent=2, ensure_ascii=False)
        latest.write_text(payload, encoding="utf-8")
        history.write_text(payload, encoding="utf-8")
        return latest, history

    def write_summary_files(self, task_id: str, round_number: int, summary: Dict[str, Any]) -> tuple[Path, Path]:
        latest = self.checkpoints_path / f"{task_id}_summary.json"
        history = self.checkpoints_path / f"{task_id}_summary_round{round_number:03d}.json"
        payload = json.dumps(summary, indent=2, ensure_ascii=False)
        latest.write_text(payload, encoding="utf-8")
        history.write_text(payload, encoding="utf-8")
        return latest, history

    def write_output_artifact(self, filename: str, history_filename: str, payload: Dict[str, Any]) -> tuple[Path, Path]:
        latest = self.outputs_path / filename
        history = self.outputs_path / history_filename
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        latest.write_text(body, encoding="utf-8")
        history.write_text(body, encoding="utf-8")
        return latest, history

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
        runtime = self.get_task_runtime(task, worker["model"])
        research_config = self.get_research_config(task)
        constraints = normalize_string_array_preserve_items(task.get("constraints", []))
        prior_summary = state.get("summary") if isinstance(state.get("summary"), dict) else None
        prior_memory_version = int(state.get("memoryVersion", 0) or 0)
        step_number = 1
        checkpoint_state = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        existing = checkpoint_state.get(worker_id)
        if isinstance(existing, dict):
            step_number = int(existing.get("step", 0) or 0) + 1
        peer_messages = self.get_peer_steer_messages(state, task, worker_id)
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
        if runtime["executionMode"] == "live":
            api_key = self.get_api_key()
            if api_key:
                try:
                    self.assert_budget_available(worker_id, task)
                    checkpoint, response_id, response, call_meta = self.new_live_checkpoint(
                        api_key,
                        task,
                        worker,
                        runtime,
                        research_config,
                        step_number,
                        constraints,
                        prior_summary,
                        prior_memory_version,
                        peer_messages,
                    )
                    usage_snapshot = self.update_usage_tracking(worker_id, str(task["taskId"]), runtime["model"], response_id, response)
                    mode_used = "live"
                except RuntimeErrorWithCode as error:
                    if str(error).startswith("Budget limit reached:"):
                        self.append_step(
                            "budget",
                            f"Budget stopped {worker['label']} before another live call.",
                            {"taskId": task["taskId"], "workerId": worker_id, "model": runtime["model"], "error": str(error)},
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
                        },
                    )
            else:
                self.append_step(
                    f"worker_{worker_id}",
                    "No API key found; falling back to mock.",
                    {"taskId": task["taskId"], "workerId": worker_id, "step": step_number},
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
            }
            if response
            else None,
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
        budget_totals = usage_snapshot or normalize_usage_state(state.get("usage") if isinstance(state.get("usage"), dict) else {})
        self.append_step(
            f"worker_{worker_id}",
            f"{worker['label']} produced a checkpoint.",
            {
                "taskId": task["taskId"],
                "workerId": worker_id,
                "step": step_number,
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
                "totalTokens": int(budget_totals.get("totalTokens", 0)),
                "estimatedCostUsd": float(budget_totals.get("estimatedCostUsd", 0.0)),
                "checkpointFile": history_cp.name,
                "outputFile": history_output.name,
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
        workers = task_workers(task)
        worker_state: Dict[str, Any] = {}
        state_workers = state.get("workers") if isinstance(state.get("workers"), dict) else {}
        for worker in workers:
            checkpoint = state_workers.get(worker["id"])
            if not isinstance(checkpoint, dict):
                raise RuntimeErrorWithCode("All configured worker checkpoints are required before summarizing.", 409)
            worker_state[worker["id"]] = checkpoint
        summary_config = summarizer_config(task)
        runtime = self.get_task_runtime(task, summary_config["model"])
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
        if runtime["executionMode"] == "live":
            api_key = self.get_api_key()
            if api_key:
                try:
                    self.assert_budget_available("summarizer", task)
                    summary, response_id, response, call_meta = self.new_live_summary(api_key, task, workers, worker_state, runtime, vetting_config, line_catalog)
                    usage_snapshot = self.update_usage_tracking("summarizer", str(task["taskId"]), runtime["model"], response_id, response)
                    mode_used = "live"
                except RuntimeErrorWithCode as error:
                    if str(error).startswith("Budget limit reached:"):
                        self.append_step(
                            "budget",
                            "Budget stopped the summarizer before another live call.",
                            {"taskId": task["taskId"], "model": runtime["model"], "error": str(error)},
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
                        },
                    )
            else:
                self.append_step("summarizer", "No API key found; falling back to mock.", {"taskId": task["taskId"]})
        if summary is None:
            summary = self.new_mock_summary(task, workers, worker_state, vetting_config, line_catalog)
        summary = self.normalize_summary(summary, line_catalog)
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
                "requestedMaxOutputTokens": int(call_meta.get("requestedMaxOutputTokens", runtime["maxOutputTokens"])),
                "effectiveMaxOutputTokens": int(call_meta.get("effectiveMaxOutputTokens", runtime["maxOutputTokens"])),
                "maxOutputTokenAttempts": list(call_meta.get("attempts", [])),
                "recoveredFromIncomplete": bool(call_meta.get("recoveredFromIncomplete", False)),
                "totalTokens": int(budget_totals.get("totalTokens", 0)),
                "estimatedCostUsd": float(budget_totals.get("estimatedCostUsd", 0.0)),
                "checkpointFile": history_summary.name,
                "outputFile": history_output.name,
            },
        )
        self.append_event(
            "runtime_run",
            {"target": "summarizer", "backend": "python", "exitCode": 0, "output": "Summary written."},
        )
        return {"target": "summarizer", "output": "Summary written.", "exitCode": 0}

    def run_target(self, target: str, task_id: Optional[str] = None) -> Dict[str, Any]:
        current_state = self.read_state()
        task = current_state.get("activeTask")
        if not isinstance(task, dict):
            raise RuntimeErrorWithCode("No active task.", 400)
        if task_id and str(task.get("taskId", "")) != str(task_id):
            raise RuntimeErrorWithCode("Requested task does not match the active task.", 409)
        if target == "summarizer":
            return self.run_summarizer()
        return self.run_worker(target)
