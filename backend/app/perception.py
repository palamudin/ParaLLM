from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.engine import RuntimeErrorWithCode

from .config import deployment_topology


PERCEPTION_EVENT_SCHEMA = "percsi.perception-event.v1"
PERCEPTION_EXECUTION_AUTHORITY = "none"
PERCEPTION_INGEST_TOKEN_ENV = "LOOP_PERCEPTION_INGEST_TOKEN"
MAX_EVENT_BYTES = 128 * 1024
MAX_OBSERVATION_ATTRIBUTES_BYTES = 64 * 1024
MAX_EVENT_ID_LENGTH = 128
MAX_TEXT_LENGTH = 2048
EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
RELATION_KINDS = {"new", "update", "contradiction", "resolution", "heartbeat"}
PRIVACY_LEVELS = {"device_only", "deployment_private", "restricted", "shareable"}
CAPTURE_CONSENT_VALUES = {"explicit", "system", "not_required"}
_WRITE_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def perception_root(root: Optional[Path] = None) -> Path:
    return deployment_topology(root).data_root / "perception"


def perception_events_path(root: Optional[Path] = None) -> Path:
    return perception_root(root) / "events.jsonl"


def _required_object(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeErrorWithCode(f"{label} must be an object.", 400)
    return value


def _reject_unknown(value: Dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(str(key) for key in value if str(key) not in allowed)
    if unknown:
        raise RuntimeErrorWithCode(f"{label} contains unsupported fields: {', '.join(unknown)}.", 400)


def _required_text(value: Any, label: str, *, max_length: int = MAX_TEXT_LENGTH) -> str:
    text = str(value or "").strip()
    if not text:
        raise RuntimeErrorWithCode(f"{label} is required.", 400)
    if len(text) > max_length:
        raise RuntimeErrorWithCode(f"{label} exceeds {max_length} characters.", 400)
    return text


def _optional_text(value: Any, label: str, *, max_length: int = MAX_TEXT_LENGTH) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length:
        raise RuntimeErrorWithCode(f"{label} exceeds {max_length} characters.", 400)
    return text


def _bounded_number(value: Any, label: str, default: float) -> float:
    try:
        parsed = float(default if value is None else value)
    except (TypeError, ValueError) as exc:
        raise RuntimeErrorWithCode(f"{label} must be a number between 0 and 1.", 400) from exc
    if parsed < 0.0 or parsed > 1.0:
        raise RuntimeErrorWithCode(f"{label} must be between 0 and 1.", 400)
    return round(parsed, 6)


def _non_negative_int(value: Any, label: str) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeErrorWithCode(f"{label} must be a non-negative integer.", 400) from exc
    if parsed < 0:
        raise RuntimeErrorWithCode(f"{label} must be a non-negative integer.", 400)
    return parsed


def _timestamp(value: Any, label: str) -> str:
    text = _required_text(value, label, max_length=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeErrorWithCode(f"{label} must be an ISO-8601 timestamp.", 400) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeErrorWithCode(f"{label} must include a timezone offset.", 400)
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise RuntimeErrorWithCode("Perception event values must be JSON serializable.", 400) from exc


def _normalize_references(value: Any) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeErrorWithCode("relation.references must be a list.", 400)
    references: List[str] = []
    for item in value[:32]:
        reference = _required_text(item, "relation reference", max_length=MAX_EVENT_ID_LENGTH)
        if reference not in references:
            references.append(reference)
    return references


def normalize_event(payload: Dict[str, Any], *, received_at: Optional[str] = None) -> Dict[str, Any]:
    current = _required_object(payload, "event")
    _reject_unknown(
        current,
        {
            "schemaVersion",
            "eventId",
            "observedAt",
            "sequence",
            "monotonicNanos",
            "source",
            "scope",
            "observation",
            "quality",
            "relation",
            "constraints",
            "evidence",
        },
        "event",
    )
    schema_version = _required_text(current.get("schemaVersion"), "schemaVersion", max_length=64)
    if schema_version != PERCEPTION_EVENT_SCHEMA:
        raise RuntimeErrorWithCode(
            f"Unsupported perception schema {schema_version!r}; expected {PERCEPTION_EVENT_SCHEMA!r}.",
            400,
        )

    event_id = _required_text(current.get("eventId"), "eventId", max_length=MAX_EVENT_ID_LENGTH)
    if not EVENT_ID_PATTERN.fullmatch(event_id):
        raise RuntimeErrorWithCode("eventId contains unsupported characters.", 400)

    source = _required_object(current.get("source"), "source")
    scope = _required_object(current.get("scope"), "scope")
    observation = _required_object(current.get("observation"), "observation")
    quality = _required_object(current.get("quality"), "quality")
    relation = _required_object(current.get("relation"), "relation")
    constraints = _required_object(current.get("constraints"), "constraints")
    if current.get("evidence") is not None and not isinstance(current.get("evidence"), dict):
        raise RuntimeErrorWithCode("evidence must be an object.", 400)
    evidence = current.get("evidence") if isinstance(current.get("evidence"), dict) else {}
    _reject_unknown(source, {"deviceId", "channel", "component", "authority"}, "source")
    _reject_unknown(scope, {"deploymentId", "subjectType", "subjectId"}, "scope")
    _reject_unknown(observation, {"kind", "summary", "attributes"}, "observation")
    _reject_unknown(quality, {"confidence", "novelty", "urgency", "clockUncertaintyMs"}, "quality")
    _reject_unknown(relation, {"kind", "references"}, "relation")
    _reject_unknown(constraints, {"privacy", "execution", "captureConsent", "expiresAt"}, "constraints")
    _reject_unknown(evidence, {"artifactRef", "sha256", "mimeType"}, "evidence")

    attributes = observation.get("attributes") if isinstance(observation.get("attributes"), dict) else {}
    if observation.get("attributes") is not None and not isinstance(observation.get("attributes"), dict):
        raise RuntimeErrorWithCode("observation.attributes must be an object.", 400)
    if _json_size(attributes) > MAX_OBSERVATION_ATTRIBUTES_BYTES:
        raise RuntimeErrorWithCode(
            f"observation.attributes exceeds {MAX_OBSERVATION_ATTRIBUTES_BYTES} bytes; store bulk data as an artifact.",
            413,
        )

    relation_kind = _required_text(relation.get("kind"), "relation.kind", max_length=32).lower()
    if relation_kind not in RELATION_KINDS:
        raise RuntimeErrorWithCode(f"relation.kind must be one of {sorted(RELATION_KINDS)}.", 400)
    privacy = _required_text(constraints.get("privacy"), "constraints.privacy", max_length=32).lower()
    if privacy not in PRIVACY_LEVELS:
        raise RuntimeErrorWithCode(f"constraints.privacy must be one of {sorted(PRIVACY_LEVELS)}.", 400)
    execution = _required_text(constraints.get("execution"), "constraints.execution", max_length=32).lower()
    if execution != "observe_only":
        raise RuntimeErrorWithCode("Perception ingestion accepts observation only; execution must be 'observe_only'.", 403)
    capture_consent = _required_text(
        constraints.get("captureConsent"),
        "constraints.captureConsent",
        max_length=32,
    ).lower()
    if capture_consent not in CAPTURE_CONSENT_VALUES:
        raise RuntimeErrorWithCode(
            f"constraints.captureConsent must be one of {sorted(CAPTURE_CONSENT_VALUES)}.",
            400,
        )

    normalized: Dict[str, Any] = {
        "schemaVersion": PERCEPTION_EVENT_SCHEMA,
        "eventId": event_id,
        "observedAt": _timestamp(current.get("observedAt"), "observedAt"),
        "receivedAt": _timestamp(received_at or utc_now(), "receivedAt"),
        "sequence": _non_negative_int(current.get("sequence"), "sequence"),
        "monotonicNanos": _non_negative_int(current.get("monotonicNanos"), "monotonicNanos"),
        "source": {
            "deviceId": _required_text(source.get("deviceId"), "source.deviceId", max_length=128),
            "channel": _required_text(source.get("channel"), "source.channel", max_length=64).lower(),
            "component": _required_text(source.get("component"), "source.component", max_length=128),
            "authority": _required_text(source.get("authority"), "source.authority", max_length=64).lower(),
        },
        "scope": {
            "deploymentId": _required_text(scope.get("deploymentId"), "scope.deploymentId", max_length=128),
            "subjectType": _required_text(scope.get("subjectType"), "scope.subjectType", max_length=64).lower(),
            "subjectId": _required_text(scope.get("subjectId"), "scope.subjectId", max_length=128),
        },
        "observation": {
            "kind": _required_text(observation.get("kind"), "observation.kind", max_length=128).lower(),
            "summary": _required_text(observation.get("summary"), "observation.summary"),
            "attributes": attributes,
        },
        "quality": {
            "confidence": _bounded_number(quality.get("confidence"), "quality.confidence", 0.5),
            "novelty": _bounded_number(quality.get("novelty"), "quality.novelty", 0.0),
            "urgency": _bounded_number(quality.get("urgency"), "quality.urgency", 0.0),
            "clockUncertaintyMs": _non_negative_int(quality.get("clockUncertaintyMs"), "quality.clockUncertaintyMs"),
        },
        "relation": {
            "kind": relation_kind,
            "references": _normalize_references(relation.get("references")),
        },
        "constraints": {
            "privacy": privacy,
            "execution": "observe_only",
            "captureConsent": capture_consent,
            "expiresAt": _timestamp(constraints.get("expiresAt"), "constraints.expiresAt")
            if constraints.get("expiresAt")
            else None,
        },
        "evidence": {
            "artifactRef": _optional_text(evidence.get("artifactRef"), "evidence.artifactRef", max_length=1024),
            "sha256": _optional_text(evidence.get("sha256"), "evidence.sha256", max_length=64),
            "mimeType": _optional_text(evidence.get("mimeType"), "evidence.mimeType", max_length=128),
        },
        "executionAuthority": PERCEPTION_EXECUTION_AUTHORITY,
    }
    if normalized["evidence"]["sha256"] and not re.fullmatch(r"[a-fA-F0-9]{64}", normalized["evidence"]["sha256"]):
        raise RuntimeErrorWithCode("evidence.sha256 must contain 64 hexadecimal characters.", 400)
    if _json_size(normalized) > MAX_EVENT_BYTES:
        raise RuntimeErrorWithCode(f"Perception event exceeds {MAX_EVENT_BYTES} bytes.", 413)
    canonical = dict(normalized)
    canonical.pop("receivedAt", None)
    normalized["eventHash"] = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return normalized


def _read_events(path: Path) -> tuple[List[Dict[str, Any]], int]:
    records: List[Dict[str, Any]] = []
    malformed = 0
    if not path.is_file():
        return records, malformed
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
        else:
            malformed += 1
    return records, malformed


def authorize_ingest(authorization: str) -> None:
    expected = str(os.getenv(PERCEPTION_INGEST_TOKEN_ENV) or "").strip()
    if not expected:
        raise RuntimeErrorWithCode(
            f"Perception ingestion is disabled until {PERCEPTION_INGEST_TOKEN_ENV} is configured.",
            503,
        )
    scheme, _, supplied = str(authorization or "").strip().partition(" ")
    if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied.strip(), expected):
        raise RuntimeErrorWithCode("Valid perception ingest bearer authentication is required.", 401)


def ingest(root: Optional[Path], payload: Dict[str, Any], authorization: str) -> Dict[str, Any]:
    authorize_ingest(authorization)
    normalized = normalize_event(payload)
    path = perception_events_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        existing, malformed = _read_events(path)
        matching = next((item for item in existing if item.get("eventId") == normalized["eventId"]), None)
        if matching is not None:
            if hmac.compare_digest(str(matching.get("eventHash") or ""), normalized["eventHash"]):
                return {
                    "accepted": True,
                    "duplicate": True,
                    "event": matching,
                    "warnings": [f"Ignored {malformed} malformed stored event(s)."] if malformed else [],
                }
            raise RuntimeErrorWithCode("eventId already exists with different content.", 409)
        line = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return {
        "accepted": True,
        "duplicate": False,
        "event": normalized,
        "warnings": [f"Ignored {malformed} malformed stored event(s)."] if malformed else [],
    }


def list_events(root: Optional[Path], limit: int = 100) -> Dict[str, Any]:
    bounded_limit = max(1, min(int(limit or 100), 500))
    path = perception_events_path(root)
    records, malformed = _read_events(path)
    return {
        "schemaVersion": PERCEPTION_EVENT_SCHEMA,
        "events": records[-bounded_limit:],
        "count": len(records),
        "malformed": malformed,
        "executionAuthority": PERCEPTION_EXECUTION_AUTHORITY,
    }


def status(root: Optional[Path]) -> Dict[str, Any]:
    path = perception_events_path(root)
    records, malformed = _read_events(path)
    return {
        "available": True,
        "ingestEnabled": bool(str(os.getenv(PERCEPTION_INGEST_TOKEN_ENV) or "").strip()),
        "schemaVersion": PERCEPTION_EVENT_SCHEMA,
        "storage": {"backend": "local_jsonl", "path": str(path), "eventCount": len(records), "malformed": malformed},
        "authorityBoundary": {
            "accepted": "observation",
            "executionAuthority": PERCEPTION_EXECUTION_AUTHORITY,
            "note": "Perception events cannot authorize actions.",
        },
    }
