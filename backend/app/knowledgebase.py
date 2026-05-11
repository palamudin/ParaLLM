from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import artifacts, storage


SCHEMA_VERSION = "parallm-native-knowledgebase/v0"
DEFAULT_BANK_ID = "runtime"
MAX_RECORD_TEXT = 8000
VALID_FACT_TYPES = {"world", "experience", "observation", "runbook", "note", "event", "state", "artifact"}
MSP_BANK_ID = "msp-knowledgebase"
MSP_BASELINE_SOURCE_IDS = {
    "msp-usecase-sop#common-major-incident": "major_incident_baseline",
    "msp-usecase-sop#247-operations": "continuity_baseline",
}
MSP_CONTINUITY_TERMS = {
    "24/7",
    "24x7",
    "continuity",
    "medical",
    "logistics",
    "restore",
    "restoring",
    "night-shift",
    "night",
    "outage",
    "operations",
}
MSP_MAJOR_INCIDENT_TERMS = {
    "msp",
    "tenant",
    "tenants",
    "client",
    "clients",
    "customer",
    "customers",
    "multi-tenant",
    "control-plane",
    "rmm",
    "psa",
    "backup",
    "restore",
    "oauth",
    "entra",
    "microsoft",
    "destructive",
    "ransomware",
    "incident",
    "severity",
    "sev-1",
    "after-hours",
    "overnight",
}
MSP_AMBIENT_RECALL_TERMS = {
    "msp",
    "mssp",
    "tenant",
    "tenants",
    "multi-tenant",
    "rmm",
    "psa",
    "backup",
    "restore",
    "restoring",
    "oauth",
    "entra",
    "ransomware",
    "severity",
    "sev-1",
    "after-hours",
    "overnight",
    "control-plane",
}


@dataclass(frozen=True)
class MemoryPaths:
    root: Path
    banks: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compact(value: Any, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def slug(value: Any, fallback: str = "item", limit: int = 80) -> str:
    text = re.sub(r"[^a-z0-9._:-]+", "_", str(value or "").lower()).strip("_")
    text = re.sub(r"_+", "_", text)
    return (text[:limit].strip("_") or fallback)[:limit]


def safe_bank_id(value: Any) -> str:
    return slug(value or DEFAULT_BANK_ID, DEFAULT_BANK_ID, 96).replace(":", "_")


def memory_paths(root: Path | str) -> MemoryPaths:
    paths = storage.project_paths(Path(root))
    base = paths.data / "knowledgebase"
    return MemoryPaths(root=base, banks=base / "banks")


def bank_dir(root: Path | str, bank_id: str) -> Path:
    return memory_paths(root).banks / safe_bank_id(bank_id)


def bank_records_path(root: Path | str, bank_id: str) -> Path:
    return bank_dir(root, bank_id) / "memory_units.jsonl"


def tokenize(value: Any) -> List[str]:
    return [token for token in re.findall(r"[a-z0-9][a-z0-9._:-]{1,80}", str(value or "").lower()) if token]


def approx_tokens(value: Any) -> int:
    text = str(value or "")
    return max(1, math.ceil(len(text) / 4))


def parse_tags(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = [part.strip() for part in re.split(r"[,\s]+", value) if part.strip()]
    elif isinstance(value, list):
        raw = [str(part).strip() for part in value if str(part).strip()]
    else:
        raw = []
    tags: List[str] = []
    for item in raw:
        normalized = slug(item, "", 80)
        if normalized and normalized not in tags:
            tags.append(normalized)
    return tags


def parse_types(value: Any) -> Optional[List[str]]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        raw = [part.strip().lower() for part in re.split(r"[,\s]+", value) if part.strip()]
    elif isinstance(value, list):
        raw = [str(part).strip().lower() for part in value if str(part).strip()]
    else:
        raw = []
    parsed = [item for item in raw if item in VALID_FACT_TYPES]
    return parsed or None


def coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def metadata_field(payload: Any, key: str = "metadata") -> Dict[str, Any]:
    value = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(value, dict):
        return {}
    clean: Dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        field = str(raw_key or "").strip()
        if not field:
            continue
        if raw_value is None or isinstance(raw_value, (str, int, float, bool)):
            clean[field] = raw_value
        else:
            clean[field] = compact(raw_value, 400)
    return clean


def metadata_search_text(value: Any) -> str:
    metadata = value if isinstance(value, dict) else {}
    parts: List[str] = []
    for raw_value in metadata.values():
        if isinstance(raw_value, (str, int, float, bool)):
            text = str(raw_value).strip()
            if text:
                parts.append(text)
    return " ".join(parts)


def compact_string_list(value: Any, limit: int = 8, item_limit: int = 220) -> List[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    items: List[str] = []
    for item in raw:
        normalized = compact(item, item_limit)
        if normalized and normalized not in items:
            items.append(normalized)
        if len(items) >= max(1, limit):
            break
    return items


def normalize_sop_packet(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    packet: Dict[str, Any] = {}
    scalar_fields = {
        "schemaVersion": 80,
        "useCase": 120,
        "summary": 260,
        "owner": 100,
        "severity": 80,
        "fallback": 220,
    }
    list_fields = {
        "eventTypes": (10, 80),
        "triggers": (8, 180),
        "firstActions": (8, 220),
        "evidence": (10, 180),
        "decisionGates": (8, 220),
        "communications": (6, 220),
        "escalation": (6, 220),
        "agentChecklist": (8, 180),
        "avoid": (8, 180),
        "handoff": (6, 220),
        "sourceRefs": (6, 180),
    }
    for field, limit in scalar_fields.items():
        text = compact(value.get(field), limit)
        if text:
            packet[field] = text
    for field, (limit, item_limit) in list_fields.items():
        items = compact_string_list(value.get(field), limit=limit, item_limit=item_limit)
        if items:
            packet[field] = items
    return packet


def extract_entities(text: str, tags: Optional[Iterable[str]] = None) -> List[str]:
    entities: List[str] = []
    for candidate in re.findall(r"\b[A-Z][A-Za-z0-9._-]{2,}(?:\s+[A-Z][A-Za-z0-9._-]{2,}){0,3}", text or ""):
        normalized = compact(candidate, 80)
        if normalized and normalized not in entities:
            entities.append(normalized)
    for tag in tags or []:
        if ":" in tag:
            label = tag.split(":", 1)[1].strip()
            if label and label not in entities:
                entities.append(label)
    return entities[:24]


def stable_id(prefix: str, *parts: Any) -> str:
    import hashlib

    seed = "\n".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha1(seed.encode('utf-8', errors='replace')).hexdigest()[:16]}"


def record_fingerprint(record: Dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    comparable = {
        "bankId": safe_bank_id(record.get("bankId") or DEFAULT_BANK_ID),
        "title": compact(record.get("title"), 140).lower(),
        "type": str(record.get("type") or record.get("factType") or "note").strip().lower(),
        "text": compact(record.get("text"), MAX_RECORD_TEXT).lower(),
        "context": compact(record.get("context"), 1000).lower(),
        "tags": sorted(parse_tags(record.get("tags"))),
        "metadata": {str(key): str(value) for key, value in sorted(metadata.items())},
        "sop": normalize_sop_packet(record.get("sop")),
    }
    return stable_id("mem_fp", json.dumps(comparable, ensure_ascii=True, sort_keys=True))


def normalize_record(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    text = compact(record.get("text"), MAX_RECORD_TEXT)
    if not text:
        return None
    bank_id = safe_bank_id(record.get("bankId") or record.get("bank_id") or DEFAULT_BANK_ID)
    tags = parse_tags(record.get("tags"))
    fact_type = str(record.get("type") or record.get("factType") or record.get("fact_type") or "note").strip().lower()
    if fact_type not in VALID_FACT_TYPES:
        fact_type = "note"
    created_at = str(record.get("createdAt") or record.get("timestamp") or record.get("occurredAt") or utc_now())
    record_id = str(record.get("id") or stable_id("mem", bank_id, created_at, text))
    normalized = {
        "id": record_id,
        "bankId": bank_id,
        "title": compact(record.get("title") or record.get("sourceId") or record_id, 140),
        "type": fact_type,
        "source": compact(record.get("source") or "local_jsonl", 80),
        "sourceId": compact(record.get("sourceId") or record.get("documentId") or record_id, 180),
        "text": text,
        "context": compact(record.get("context"), 1000),
        "tags": tags,
        "entities": [compact(item, 80) for item in (record.get("entities") or []) if compact(item, 80)][:24],
        "metadata": metadata_field(record),
        "createdAt": created_at,
    }
    sop = normalize_sop_packet(record.get("sop"))
    if sop:
        normalized["sop"] = sop
    return normalized


def record_from_payload(bank_id: str, item: Dict[str, Any], base: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    content = item.get("content")
    if content is None:
        content = item.get("text")
    text = compact(content, MAX_RECORD_TEXT)
    if not text:
        return None
    merged_tags = parse_tags(base.get("tags")) + [tag for tag in parse_tags(item.get("tags")) if tag not in parse_tags(base.get("tags"))]
    lane_id = str(item.get("laneId") or item.get("lane_id") or base.get("laneId") or base.get("lane_id") or "").strip()
    if lane_id:
        lane_tag = f"lane:{slug(lane_id, 'lane')}"
        if lane_tag not in merged_tags:
            merged_tags.append(lane_tag)
    document_id = str(item.get("documentId") or item.get("document_id") or base.get("documentId") or base.get("document_id") or "").strip()
    timestamp = str(item.get("occurredAt") or item.get("timestamp") or base.get("occurredAt") or base.get("timestamp") or utc_now())
    metadata = dict(metadata_field(base))
    metadata.update(metadata_field(item))
    if lane_id:
        metadata["laneId"] = lane_id
    if document_id:
        metadata["documentId"] = document_id
    source = item.get("source") or base.get("source") or "manual"
    fact_type = item.get("type") or item.get("factType") or base.get("type") or base.get("factType") or "note"
    record = {
        "id": stable_id("mem", bank_id, document_id, timestamp, text, uuid.uuid4().hex[:8]),
        "bankId": bank_id,
        "title": item.get("title") or base.get("title") or compact(text, 80),
        "type": fact_type,
        "source": source,
        "sourceId": document_id or item.get("sourceId") or base.get("sourceId"),
        "text": text,
        "context": item.get("context") or base.get("context"),
        "tags": merged_tags,
        "entities": extract_entities(text, merged_tags),
        "metadata": metadata,
        "createdAt": timestamp,
    }
    sop = item.get("sop") if isinstance(item.get("sop"), dict) else base.get("sop")
    if isinstance(sop, dict):
        record["sop"] = sop
    return normalize_record(record)


def append_records(root: Path | str, bank_id: str, records: List[Dict[str, Any]]) -> None:
    if not records:
        return
    target = bank_records_path(root, bank_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def upsert_memory_records(root: Path | str, bank_id: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {"stored": 0, "duplicates": 0, "records": [], "path": str(bank_records_path(root, bank_id))}
    target = bank_records_path(root, bank_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing, _warnings = read_jsonl_records(target, limit=100000)
    seen = {record_fingerprint(record) for record in existing}
    stored_records: List[Dict[str, Any]] = []
    duplicates = 0
    for record in records:
        fingerprint = record_fingerprint(record)
        if fingerprint in seen:
            duplicates += 1
            continue
        seen.add(fingerprint)
        stored_records.append(record)
    append_records(root, bank_id, stored_records)
    return {"stored": len(stored_records), "duplicates": duplicates, "records": stored_records, "path": str(target)}


def read_jsonl_records(path: Path, limit: int = 2000) -> tuple[List[Dict[str, Any]], List[str]]:
    records: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if not path.is_file():
        return records, warnings
    tail: deque[tuple[int, str]] = deque(maxlen=max(1, int(limit or 1)))
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for offset, raw in enumerate(handle, start=1):
            tail.append((offset, raw.rstrip("\n")))
    for offset, raw in tail:
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            warnings.append(f"{path.name}:{offset} invalid JSONL record: {exc.msg}")
            continue
        if isinstance(parsed, dict):
            normalized = normalize_record(parsed)
            if normalized:
                records.append(normalized)
    return records, warnings[:20]


def list_banks(root: Path | str) -> List[Dict[str, Any]]:
    paths = memory_paths(root)
    if not paths.banks.exists():
        return []
    banks: List[Dict[str, Any]] = []
    for item in sorted(paths.banks.iterdir(), key=lambda path: path.name):
        record_path = item / "memory_units.jsonl"
        if not item.is_dir() or not record_path.exists():
            continue
        with record_path.open("r", encoding="utf-8", errors="replace") as handle:
            line_count = sum(1 for line in handle if line.strip())
        stat = record_path.stat()
        banks.append(
            {
                "bankId": item.name,
                "records": line_count,
                "updatedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
            }
        )
    return banks


def runtime_records(root: Path | str, *, max_events: int = 80, max_steps: int = 80, max_artifacts: int = 40) -> List[Dict[str, Any]]:
    paths = storage.project_paths(Path(root))
    records: List[Dict[str, Any]] = []
    state = storage.read_state_payload(paths)
    active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else {}
    loop = state.get("loop") if isinstance(state.get("loop"), dict) else {}
    usage = state.get("usage") if isinstance(state.get("usage"), dict) else {}
    draft = state.get("draft") if isinstance(state.get("draft"), dict) else {}
    objective = compact((active_task or {}).get("objective") or (draft or {}).get("objective") or "", 1000)
    records.append(
        normalize_record(
            {
                "id": "runtime_state",
                "bankId": DEFAULT_BANK_ID,
                "title": "Runtime State",
                "type": "state",
                "source": "runtime_fallback",
                "sourceId": "data/state.json",
                "text": f"Active objective: {objective or 'none'}. Loop status {loop.get('status') or 'idle'}; last message: {loop.get('lastMessage') or 'Ready.'}",
                "tags": ["runtime", "state", "fallback"],
                "metadata": {
                    "taskId": (active_task or {}).get("taskId"),
                    "memoryVersion": state.get("memoryVersion"),
                    "loopStatus": loop.get("status"),
                },
                "createdAt": state.get("lastUpdated") or utc_now(),
            }
        )
    )
    records.append(
        normalize_record(
            {
                "id": "runtime_usage",
                "bankId": DEFAULT_BANK_ID,
                "title": "Usage Ledger",
                "type": "state",
                "source": "runtime_fallback",
                "sourceId": "data/state.json#usage",
                "text": f"Usage ledger: {usage.get('calls') or 0} provider calls, {usage.get('totalTokens') or 0} total tokens, estimated cost ${usage.get('estimatedCostUsd') or 0}. Last model {usage.get('lastModel') or 'none'}.",
                "tags": ["runtime", "usage", "fallback"],
                "metadata": {"lastResponseId": usage.get("lastResponseId"), "lastModel": usage.get("lastModel")},
                "createdAt": usage.get("lastUpdated") or state.get("lastUpdated") or utc_now(),
            }
        )
    )

    steps = storage.read_recent_jsonl_report(paths.steps, max_steps)
    for index, entry in enumerate(steps.get("entries") or [], start=1):
        if not isinstance(entry, dict):
            continue
        stage = slug(entry.get("stage") or "step", "step")
        context = entry.get("context") if isinstance(entry.get("context"), dict) else {}
        records.append(
            normalize_record(
                {
                    "id": stable_id("runtime_step", index, entry.get("ts"), entry.get("stage"), entry.get("message")),
                    "bankId": DEFAULT_BANK_ID,
                    "title": f"Step: {entry.get('stage') or 'step'}",
                    "type": "event",
                    "source": "runtime_fallback",
                    "sourceId": "data/steps.jsonl",
                    "text": f"Step {entry.get('stage') or 'step'}: {entry.get('message') or ''}. Context keys: {', '.join(sorted(context.keys())[:12]) or 'none'}.",
                    "tags": ["runtime", "step", stage, "fallback"],
                    "metadata": {"stage": entry.get("stage"), **{f"context.{key}": value for key, value in list(context.items())[:12] if isinstance(value, (str, int, float, bool))}},
                    "createdAt": entry.get("ts") or utc_now(),
                }
            )
        )

    events = storage.read_recent_jsonl_report(paths.events, max_events)
    for index, entry in enumerate(events.get("entries") or [], start=1):
        if not isinstance(entry, dict):
            continue
        event_type = slug(entry.get("type") or "event", "event")
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        records.append(
            normalize_record(
                {
                    "id": stable_id("runtime_event", index, entry.get("ts"), entry.get("type"), payload),
                    "bankId": DEFAULT_BANK_ID,
                    "title": f"Event: {entry.get('type') or 'event'}",
                    "type": "event",
                    "source": "runtime_fallback",
                    "sourceId": "data/events.jsonl",
                    "text": f"Event {entry.get('type') or 'event'}: {compact(payload or entry.get('type'), 900)}",
                    "tags": ["runtime", "event", event_type, "fallback"],
                    "metadata": {f"payload.{key}": value for key, value in list(payload.items())[:12] if isinstance(value, (str, int, float, bool))},
                    "createdAt": entry.get("ts") or utc_now(),
                }
            )
        )

    for item in artifacts.list_json_artifacts(paths.root, ["outputs", "checkpoints", "sessions"])[:max_artifacts]:
        name = str(item.get("name") or "artifact")
        category = str(item.get("category") or "artifact")
        records.append(
            normalize_record(
                {
                    "id": stable_id("runtime_artifact", category, name, item.get("modifiedAt")),
                    "bankId": DEFAULT_BANK_ID,
                    "title": f"Artifact: {name}",
                    "type": "artifact",
                    "source": "runtime_fallback",
                    "sourceId": f"data/{category}/{name}",
                    "text": f"Artifact {category}/{name}: {item.get('size') or 0} bytes, modified {item.get('modifiedAt') or 'unknown'}.",
                    "tags": ["runtime", "artifact", slug(category, "artifact"), "fallback"],
                    "metadata": {"category": category, "name": name, "size": item.get("size")},
                    "createdAt": item.get("modifiedAt") or utc_now(),
                }
            )
        )

    howto_path = paths.root / "docs" / "eval-subject-howto-msp-101.md"
    if howto_path.is_file():
        records.append(
            normalize_record(
                {
                    "id": "runtime_msp_howto",
                    "bankId": MSP_BANK_ID,
                    "title": "MSP Knowledgebase How-To",
                    "type": "runbook",
                    "source": "runtime_fallback",
                    "sourceId": "docs/eval-subject-howto-msp-101.md",
                    "text": howto_path.read_text(encoding="utf-8", errors="replace")[:MAX_RECORD_TEXT],
                    "tags": ["msp", "runbook", "eval", "fallback"],
                    "metadata": {"path": "docs/eval-subject-howto-msp-101.md"},
                    "createdAt": datetime.fromtimestamp(howto_path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
                }
            )
        )

    return [record for record in records if record]


def status(root: Path | str) -> Dict[str, Any]:
    paths = storage.project_paths(Path(root))
    banks = list_banks(paths.root)
    fallback_sources = {
        "state": paths.state.exists(),
        "steps": paths.steps.exists(),
        "events": paths.events.exists(),
        "artifacts": any((paths.data / name).exists() for name in ("outputs", "checkpoints", "sessions")),
        "mspHowTo": (paths.root / "docs" / "eval-subject-howto-msp-101.md").is_file(),
    }
    persistent_count = sum(int(bank.get("records") or 0) for bank in banks)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "available": True,
        "coreDependency": False,
        "generatedAt": utc_now(),
        "storage": {
            "backend": "local_jsonl",
            "root": str(memory_paths(paths.root).root),
            "banks": banks,
            "recordCount": persistent_count,
        },
        "fallback": {
            "engine": "runtime_log_readout",
            "available": any(fallback_sources.values()),
            "sources": fallback_sources,
            "policy": "Use runtime state, steps, events, artifacts, and local runbooks when no durable memory is available.",
        },
        "adapters": [
            {"id": "runtime_fallback", "available": True, "required": True, "role": "core readout"},
            {"id": "local_jsonl", "available": True, "required": False, "role": "durable native memory"},
            {"id": "external_memory", "available": False, "required": False, "role": "future optional adapter"},
        ],
    }


def retain(root: Path | str, payload: Dict[str, Any]) -> Dict[str, Any]:
    bank_id = safe_bank_id(payload.get("bankId") or payload.get("bank_id") or DEFAULT_BANK_ID)
    raw_items = payload.get("items")
    if isinstance(raw_items, list):
        items = [item if isinstance(item, dict) else {"content": item} for item in raw_items]
    else:
        items = [{"content": payload.get("content") if payload.get("content") is not None else payload.get("text")}]
    records = [record for item in items if (record := record_from_payload(bank_id, item, payload))]
    upsert_result = upsert_memory_records(root, bank_id, records)
    stored_records = upsert_result.get("records") if isinstance(upsert_result.get("records"), list) else []
    return {
        "schemaVersion": SCHEMA_VERSION,
        "bankId": bank_id,
        "stored": int(upsert_result["stored"]),
        "duplicates": int(upsert_result["duplicates"]),
        "records": [
            {
                "id": record["id"],
                "title": record["title"],
                "type": record["type"],
                "source": record["source"],
                "tags": record["tags"],
                "createdAt": record["createdAt"],
            }
            for record in stored_records
        ],
        "storage": {"backend": "local_jsonl", "path": str(upsert_result["path"])},
        "fallbackSafe": True,
    }


def load_persistent_records(root: Path | str, bank_id: str = "", limit: int = 2000) -> tuple[List[Dict[str, Any]], List[str]]:
    paths = memory_paths(root)
    warnings: List[str] = []
    records: List[Dict[str, Any]] = []
    if bank_id:
        banks = [safe_bank_id(bank_id)]
    else:
        banks = [bank.get("bankId") for bank in list_banks(root)]
    for current_bank in banks:
        if not current_bank:
            continue
        loaded, loaded_warnings = read_jsonl_records(paths.banks / str(current_bank) / "memory_units.jsonl", limit=limit)
        records.extend(loaded)
        warnings.extend(loaded_warnings)
    return records, warnings[:30]


def tag_matches(record_tags: List[str], wanted: List[str], mode: str = "any") -> bool:
    if not wanted:
        return True
    record_set = set(record_tags or [])
    wanted_set = set(wanted)
    if mode == "all":
        return wanted_set.issubset(record_set)
    return bool(record_set & wanted_set)


def baseline_reason(record: Dict[str, Any], query: str, query_terms: List[str], wanted_tags: List[str], bank_id: str) -> str:
    if record.get("bankId") != MSP_BANK_ID and bank_id != MSP_BANK_ID:
        return ""
    source_id = str(record.get("sourceId") or "").strip()
    reason = MSP_BASELINE_SOURCE_IDS.get(source_id)
    if not reason:
        return ""
    terms = set(query_terms)
    query_lower = str(query or "").lower()
    has_msp_context = bank_id == MSP_BANK_ID or "msp" in wanted_tags or "msp" in terms
    if not has_msp_context:
        return ""
    if source_id == "msp-usecase-sop#common-major-incident":
        if terms & MSP_MAJOR_INCIDENT_TERMS or "multi-tenant" in query_lower or "control plane" in query_lower:
            return reason
        return ""
    if source_id == "msp-usecase-sop#247-operations":
        if terms & MSP_CONTINUITY_TERMS or "24/7" in query_lower or "night shift" in query_lower:
            return reason
        return ""
    return reason


def has_msp_recall_context(query: str, query_terms: List[str], wanted_tags: List[str], bank_id: str) -> bool:
    if bank_id == MSP_BANK_ID:
        return True
    tag_set = {str(tag or "").lower() for tag in wanted_tags}
    if "msp" in tag_set or "mssp" in tag_set:
        return True
    terms = set(query_terms)
    if terms & MSP_AMBIENT_RECALL_TERMS:
        return True
    query_lower = str(query or "").lower()
    return any(
        phrase in query_lower
        for phrase in (
            "managed service provider",
            "managed services provider",
            "managed service",
            "customer tenant",
            "customer tenants",
            "control plane",
        )
    )


def baseline_priority(record: Dict[str, Any]) -> int:
    source_id = str(record.get("sourceId") or "").strip()
    order = {
        "msp-usecase-sop#common-major-incident": 0,
        "msp-usecase-sop#247-operations": 1,
    }
    return order.get(source_id, 50)


def parse_timestamp(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def record_score(record: Dict[str, Any], query: str, query_terms: List[str], wanted_tags: List[str]) -> tuple[float, Dict[str, float]]:
    sop = record.get("sop") if isinstance(record.get("sop"), dict) else {}
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    haystack = " ".join(
        [
            str(record.get("title") or ""),
            str(record.get("text") or ""),
            str(record.get("context") or ""),
            " ".join(record.get("tags") or []),
            " ".join(record.get("entities") or []),
            metadata_search_text(metadata),
            str(sop.get("useCase") or ""),
            " ".join(sop.get("eventTypes") or []),
            " ".join(sop.get("triggers") or []),
            " ".join(sop.get("firstActions") or []),
            " ".join(sop.get("decisionGates") or []),
        ]
    )
    lower_haystack = haystack.lower()
    tokens = Counter(tokenize(haystack))
    overlap = sum(min(tokens.get(term, 0), count) for term, count in Counter(query_terms).items())
    keyword = overlap / max(1, len(query_terms))
    phrase = 1.0 if query and query.lower() in lower_haystack else 0.0
    tag = 1.0 if wanted_tags and tag_matches(record.get("tags") or [], wanted_tags) else 0.0
    source = 0.25 if record.get("source") == "runtime_fallback" else 0.1
    sop_boost = 0.0
    if sop and query_terms:
        sop_terms = set(tokenize(" ".join(
            [
                str(sop.get("useCase") or ""),
                " ".join(sop.get("eventTypes") or []),
                " ".join(sop.get("triggers") or []),
            ]
        )))
        if sop_terms:
            sop_boost = min(1.0, len(sop_terms & set(query_terms)) / max(1, min(len(sop_terms), len(set(query_terms)))))
    learning_boost = 0.0
    if metadata.get("learning.kind") and query_terms:
        try:
            adaptive_weight = float(metadata.get("learning.adaptiveWeight") or 0.0)
        except (TypeError, ValueError):
            adaptive_weight = 0.0
        try:
            miss_count = float(metadata.get("learning.missCount") or 0.0)
        except (TypeError, ValueError):
            miss_count = 0.0
        learning_boost = min(1.4, adaptive_weight * 0.08 + math.log1p(max(0.0, miss_count)) * 0.18)
    timestamp = parse_timestamp(record.get("createdAt"))
    recency = 0.0
    if timestamp is not None:
        age_days = max(0.0, (datetime.now(timezone.utc).timestamp() - timestamp) / 86400)
        recency = 1.0 / (1.0 + min(age_days, 90.0) / 14.0)
    if not query_terms:
        keyword = 0.1
    score = keyword * 4.0 + phrase * 2.0 + tag * 1.2 + source + recency * 0.35 + sop_boost * 1.6 + learning_boost
    return score, {
        "keyword": round(keyword, 4),
        "phrase": phrase,
        "tag": tag,
        "source": source,
        "recency": round(recency, 4),
        "sop": round(sop_boost, 4),
        "learning": round(learning_boost, 4),
    }


def sop_context_line(hit: Dict[str, Any]) -> str:
    sop = hit.get("sop") if isinstance(hit.get("sop"), dict) else {}
    if not sop:
        return compact(hit.get("text"), 700)
    parts = [
        f"useCase={sop.get('useCase')}",
        f"events={', '.join(sop.get('eventTypes') or [])}",
    ]
    for label, field in [
        ("first", "firstActions"),
        ("evidence", "evidence"),
        ("gates", "decisionGates"),
        ("avoid", "avoid"),
    ]:
        items = sop.get(field) if isinstance(sop.get(field), list) else []
        if items:
            parts.append(f"{label}: " + " | ".join(items[:4]))
    return compact("; ".join(part for part in parts if part and not part.endswith("=None")), 900)


def recall(
    root: Path | str,
    *,
    query: str = "",
    bank_id: str = "",
    max_records: int = 12,
    max_tokens: int = 2048,
    tags: Optional[List[str]] = None,
    tags_match: str = "any",
    types: Optional[List[str]] = None,
    include_runtime: bool = True,
    include_persistent: bool = True,
) -> Dict[str, Any]:
    paths = storage.project_paths(Path(root))
    bank_id = safe_bank_id(bank_id) if bank_id else ""
    max_records = max(1, min(80, int(max_records or 12)))
    max_tokens = max(128, min(50000, int(max_tokens or 2048)))
    wanted_tags = parse_tags(tags or [])
    tags_match = "all" if str(tags_match or "").lower() == "all" else "any"
    types = parse_types(types)
    warnings: List[str] = []
    records: List[Dict[str, Any]] = []
    engines: List[str] = []

    if include_persistent:
        loaded, loaded_warnings = load_persistent_records(paths.root, bank_id=bank_id, limit=2500)
        records.extend(loaded)
        warnings.extend(loaded_warnings)
        engines.append("local_jsonl")
    if include_runtime:
        records.extend(runtime_records(paths.root))
        engines.append("runtime_fallback")

    filtered: List[Dict[str, Any]] = []
    for record in records:
        if bank_id and record.get("bankId") != bank_id and record.get("source") != "runtime_fallback":
            continue
        if types and record.get("type") not in types:
            continue
        if not tag_matches(record.get("tags") or [], wanted_tags, tags_match):
            continue
        filtered.append(record)

    query_terms = tokenize(query)
    allow_ambient_msp = has_msp_recall_context(query, query_terms, wanted_tags, bank_id)
    scored: List[Dict[str, Any]] = []
    baseline_scored: List[Dict[str, Any]] = []
    for record in filtered:
        score, parts = record_score(record, query, query_terms, wanted_tags)
        reason = baseline_reason(record, query, query_terms, wanted_tags, bank_id)
        enriched = {**record, "score": round(score, 4), "scoreParts": parts}
        if reason:
            enriched["memoryLayer"] = "baseline"
            enriched["baselineReason"] = reason
            baseline_scored.append(enriched)
            continue
        demand_score = (
            float(parts.get("keyword") or 0.0) * 4.0
            + float(parts.get("phrase") or 0.0) * 2.0
            + float(parts.get("tag") or 0.0) * 1.2
            + float(parts.get("sop") or 0.0) * 1.6
        )
        enriched["scoreParts"] = {**parts, "demand": round(demand_score, 4)}
        if query_terms and demand_score <= 0.35:
            continue
        enriched["memoryLayer"] = "adaptive" if record.get("sop") else "supporting"
        scored.append(enriched)
    baseline_scored.sort(
        key=lambda item: (
            -baseline_priority(item),
            float(item.get("score") or 0),
            parse_timestamp(item.get("createdAt")) or 0,
        ),
        reverse=True,
    )
    scored.sort(key=lambda item: (float(item.get("score") or 0), parse_timestamp(item.get("createdAt")) or 0), reverse=True)

    selected: List[Dict[str, Any]] = []
    used_tokens = 0
    baseline_limit = min(2, max_records)
    if scored and max_records > 1:
        baseline_limit = min(baseline_limit, max_records - 1)
    for item in baseline_scored[:baseline_limit]:
        item_tokens = approx_tokens(item.get("text"))
        if selected and used_tokens + item_tokens > max_tokens:
            continue
        selected.append(item)
        used_tokens += item_tokens
    selected_ids = {str(item.get("id") or "") for item in selected}
    for item in scored:
        if str(item.get("id") or "") in selected_ids:
            continue
        item_tokens = approx_tokens(item.get("text"))
        if selected and used_tokens + item_tokens > max_tokens:
            continue
        selected.append(item)
        used_tokens += item_tokens
        if len(selected) >= max_records:
            break

    context_lines = [
        f"[{index}] {hit.get('title')} ({hit.get('type')}, {hit.get('sourceId')}): {sop_context_line(hit)}"
        for index, hit in enumerate(selected, start=1)
    ]
    selected_has_msp = any(hit.get("bankId") == MSP_BANK_ID or "msp" in (hit.get("tags") or []) for hit in selected)
    baseline_policy = (
        "MSP high-risk incidents reserve mandatory baseline SOP packets before adaptive recall fills the remaining slots."
        if selected_has_msp or allow_ambient_msp or bank_id == MSP_BANK_ID
        else "Use targeted baseline packets only when the current task context explicitly matches their domain."
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "query": query,
        "bankId": bank_id or "all",
        "generatedAt": utc_now(),
        "engines": engines,
        "fallbackUsed": any(hit.get("source") == "runtime_fallback" for hit in selected),
        "degraded": False,
        "warnings": warnings[:20],
        "resultCount": len(selected),
        "totalCandidates": len(scored) + len(baseline_scored),
        "maxTokens": max_tokens,
        "usedTokensApprox": used_tokens,
        "memoryPlan": {
            "mode": "baseline_and_adaptive",
            "baselineCount": sum(1 for hit in selected if hit.get("memoryLayer") == "baseline"),
            "adaptiveCount": sum(1 for hit in selected if hit.get("memoryLayer") == "adaptive"),
            "supportingCount": sum(1 for hit in selected if hit.get("memoryLayer") == "supporting"),
            "baselinePolicy": baseline_policy,
        },
        "hits": [
            {
                "id": hit.get("id"),
                "bankId": hit.get("bankId"),
                "title": hit.get("title"),
                "type": hit.get("type"),
                "source": hit.get("source"),
                "sourceId": hit.get("sourceId"),
                "summary": compact(hit.get("text"), 520),
                "text": hit.get("text"),
                "score": hit.get("score"),
                "scoreParts": hit.get("scoreParts"),
                "tags": hit.get("tags"),
                "entities": hit.get("entities"),
                "metadata": hit.get("metadata"),
                "sop": hit.get("sop") if isinstance(hit.get("sop"), dict) else {},
                "memoryLayer": hit.get("memoryLayer") or "adaptive",
                "baselineReason": hit.get("baselineReason"),
                "createdAt": hit.get("createdAt"),
            }
            for hit in selected
        ],
        "aiPacket": {
            "intent": "knowledgebase.recall",
            "coreDependency": False,
            "fallbackPolicy": "If durable memory is empty or unavailable, use runtime state, steps, events, artifacts, and local runbooks.",
            "selectedEvidenceIds": [str(hit.get("id") or "") for hit in selected],
            "contextText": "\n".join(context_lines),
        },
    }


def reflect(root: Path | str, payload: Dict[str, Any]) -> Dict[str, Any]:
    query = str(payload.get("query") or payload.get("prompt") or "").strip()
    recall_result = recall(
        root,
        query=query,
        bank_id=str(payload.get("bankId") or payload.get("bank_id") or ""),
        max_records=int(payload.get("maxRecords") or payload.get("max_records") or 10),
        max_tokens=int(payload.get("maxTokens") or payload.get("max_tokens") or 2048),
        tags=parse_tags(payload.get("tags")),
        tags_match=str(payload.get("tagsMatch") or payload.get("tags_match") or "any"),
        types=parse_types(payload.get("types")),
        include_runtime=coerce_bool(payload.get("includeRuntime"), True),
        include_persistent=coerce_bool(payload.get("includePersistent"), True),
    )
    hits = recall_result.get("hits") if isinstance(recall_result.get("hits"), list) else []
    by_type: Dict[str, int] = defaultdict(int)
    by_source: Dict[str, int] = defaultdict(int)
    for hit in hits:
        if isinstance(hit, dict):
            by_type[str(hit.get("type") or "unknown")] += 1
            by_source[str(hit.get("source") or "unknown")] += 1
    if hits:
        leading = "; ".join(compact((hit or {}).get("summary"), 160) for hit in hits[:3] if isinstance(hit, dict))
        text = (
            f"Native knowledgebase reflection found {len(hits)} evidence record(s) for '{query or 'current context'}'. "
            f"Type mix: {dict(by_type)}. Source mix: {dict(by_source)}. Leading evidence: {leading}"
        )
        next_check = "Open the selected evidence IDs before treating the reflection as a decision."
    else:
        text = (
            f"Native knowledgebase reflection found no durable match for '{query or 'current context'}'. "
            "The system remains operational through current runtime state and live logs."
        )
        next_check = "Retain a short runbook or inspect current steps/events for fresh evidence."
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "query": query,
        "text": text,
        "basedOn": {
            "hits": hits,
            "evidenceIds": [str((hit or {}).get("id") or "") for hit in hits if isinstance(hit, dict)],
        },
        "structuredOutput": {
            "typeCounts": dict(by_type),
            "sourceCounts": dict(by_source),
            "recommendedNextCheck": next_check,
            "coreDependency": False,
        },
        "recall": recall_result,
    }
