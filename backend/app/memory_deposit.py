from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import knowledgebase, storage


CANDIDATE_SCHEMA_VERSION = "parallm-memory-candidate/v0"
CANDIDATE_LEDGER_RELATIVE = Path("data") / "knowledgebase" / "candidates" / "memory_candidates.jsonl"
ALLOWED_DESTINATIONS = {"session", "user", "domain", "sop", "eval", "benchmark", "artifact", "quarantine", "reject"}
ALLOWED_STORE_CLASSES = {"STS", "LTS", "eval", "artifact", "quarantine", "reject"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compact(value: Any, limit: int = 500) -> str:
    return knowledgebase.compact(value, limit)


def candidate_ledger_path(root: Path | str) -> Path:
    return storage.project_paths(Path(root)).root / CANDIDATE_LEDGER_RELATIVE


def relative_to_root(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def section_text(section: Any) -> Dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    return {
        "scores": dict(scores),
        "verdict": compact(data.get("verdict"), 320),
        "strength": compact(data.get("strongestStrength") or data.get("strongestControlStrength"), 320),
        "weakness": compact(data.get("strongestWeakness") or data.get("strongestControlWeakness"), 420),
        "rationale": compact(data.get("rationale"), 520),
        "memoryCompliance": compact(data.get("memoryCompliance"), 420),
    }


def normalize_destination(value: Any) -> str:
    destination = str(value or "").strip().lower().replace("_", "-")
    if destination in {"short-term", "shortterm", "sts"}:
        return "session"
    if destination in {"long-term", "longterm", "lts"}:
        return "domain"
    if destination in ALLOWED_DESTINATIONS:
        return destination
    return "quarantine"


def normalize_store_class(value: Any, destination: str) -> str:
    store_class = str(value or "").strip()
    normalized = store_class.upper() if store_class.lower() in {"sts", "lts"} else store_class.lower()
    if normalized in ALLOWED_STORE_CLASSES:
        return normalized
    if destination in {"session", "user"}:
        return "STS"
    if destination in {"domain", "sop"}:
        return "LTS"
    return destination if destination in {"eval", "artifact", "quarantine", "reject"} else "quarantine"


def normalize_confidence(value: Any) -> str:
    confidence = str(value or "").strip().lower()
    if confidence in {"low", "medium", "high"}:
        return confidence
    return "low"


def normalize_proposal(raw: Any, *, requested_bank_id: str) -> Dict[str, Any]:
    proposal = raw if isinstance(raw, dict) else {}
    destination = normalize_destination(proposal.get("destination") or proposal.get("memoryDestination"))
    store_class = normalize_store_class(proposal.get("storeClass"), destination)
    target_bank_id = knowledgebase.safe_bank_id(proposal.get("targetBankId") or proposal.get("bankId") or "")
    status = "pending_context_review"
    blockers: List[str] = []
    if not proposal:
        blockers.append("router_missing")
    if destination == "reject":
        status = "rejected"
    elif proposal and destination != "quarantine":
        status = "routed"
    else:
        blockers.append("route_unresolved")
    return {
        "status": status,
        "destination": destination,
        "storeClass": store_class,
        "targetBankId": target_bank_id,
        "requestedBankId": knowledgebase.safe_bank_id(requested_bank_id),
        "ttlDays": proposal.get("ttlDays") if isinstance(proposal.get("ttlDays"), int) else None,
        "confidence": normalize_confidence(proposal.get("confidence")),
        "rationale": compact(proposal.get("rationale") or proposal.get("reason"), 640),
        "blockers": blockers,
    }


def score_signal(score: Dict[str, Any]) -> Dict[str, Any]:
    deterministic = score.get("deterministic") if isinstance(score.get("deterministic"), dict) else {}
    return {
        "quality": section_text(score.get("quality")),
        "answerHealth": section_text(score.get("answerHealth")),
        "control": section_text(score.get("control")),
        "comparison": section_text(score.get("comparison")),
        "deterministic": {
            "passed": bool(deterministic.get("passed")) if "passed" in deterministic else None,
            "checks": deterministic.get("checks") if isinstance(deterministic.get("checks"), dict) else {},
        },
    }


def build_eval_score_candidate(
    root: Path | str,
    *,
    run_id: str,
    score_path: Path,
    score: Dict[str, Any],
    case: Dict[str, Any],
    requested_bank_id: str = "",
) -> Dict[str, Any]:
    paths = storage.project_paths(Path(root))
    source_ref = relative_to_root(paths.root, Path(score_path))
    proposal = normalize_proposal(score.get("memoryProposal"), requested_bank_id=requested_bank_id)
    candidate_id = knowledgebase.stable_id("memcand", run_id, source_ref)
    now = utc_now()
    return {
        "id": candidate_id,
        "schemaVersion": CANDIDATE_SCHEMA_VERSION,
        "createdAt": now,
        "updatedAt": now,
        "source": {
            "kind": "eval-score",
            "runId": str(run_id or ""),
            "caseId": str(score.get("caseId") or case.get("caseId") or ""),
            "armId": str(score.get("armId") or ""),
            "variantId": str(score.get("variantId") or ""),
            "scoreRef": source_ref,
        },
        "case": {
            "caseId": str(case.get("caseId") or score.get("caseId") or ""),
            "title": compact(case.get("title"), 240),
            "objective": compact(case.get("objective"), 1000),
            "sessionContext": compact(case.get("sessionContext"), 640),
        },
        "judgeSignals": score_signal(score),
        "routing": {
            key: value
            for key, value in proposal.items()
            if key not in {"blockers"}
        },
        "arbiter": {
            "state": "hold" if proposal["status"] in {"pending_context_review", "routed"} else proposal["status"],
            "blockers": list(proposal.get("blockers", [])),
            "promotion": "disabled_until_context_review",
        },
        "evidenceRefs": [source_ref],
        "safety": {
            "rawSecretsStored": False,
            "durableBankWrite": False,
        },
    }


def read_candidate_ledger(root: Path | str) -> Tuple[List[Dict[str, Any]], List[str]]:
    path = candidate_ledger_path(root)
    records: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if not path.is_file():
        return records, warnings
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for offset, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                warnings.append(f"{path.name}:{offset} invalid JSONL candidate: {exc.msg}")
                continue
            if isinstance(parsed, dict) and parsed.get("id"):
                records.append(parsed)
    return records, warnings[:20]


def write_candidate_ledger(root: Path | str, candidates: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    path = candidate_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing, warnings = read_candidate_ledger(root)
    by_id: Dict[str, Dict[str, Any]] = {str(record.get("id")): record for record in existing if record.get("id")}
    inserted = 0
    updated = 0
    unchanged = 0
    for candidate in candidates:
        candidate_id = str(candidate.get("id") or "").strip()
        if not candidate_id:
            continue
        current = by_id.get(candidate_id)
        if current is None:
            by_id[candidate_id] = dict(candidate)
            inserted += 1
            continue
        merged = dict(current)
        changed = False
        for key in ("routing", "arbiter", "judgeSignals", "safety"):
            if candidate.get(key) != current.get(key):
                merged[key] = candidate.get(key)
                changed = True
        evidence_refs = list(dict.fromkeys([*(current.get("evidenceRefs") or []), *(candidate.get("evidenceRefs") or [])]))
        if evidence_refs != current.get("evidenceRefs"):
            merged["evidenceRefs"] = evidence_refs
            changed = True
        if changed:
            merged["updatedAt"] = utc_now()
            by_id[candidate_id] = merged
            updated += 1
        else:
            unchanged += 1
    ordered = sorted(by_id.values(), key=lambda item: (str(item.get("source", {}).get("runId") if isinstance(item.get("source"), dict) else ""), str(item.get("id") or "")))
    path.write_text("\n".join(json.dumps(item, ensure_ascii=True, sort_keys=True) for item in ordered) + ("\n" if ordered else ""), encoding="utf-8")
    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "count": len(ordered),
        "path": str(path),
        "warnings": warnings,
    }
