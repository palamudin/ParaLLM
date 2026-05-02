from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import knowledgebase, storage


SCHEMA_VERSION = "parallm-judge-learning/v0"
DEFAULT_LEARNING_BANK_ID = "msp-knowledgebase"
REPLAY_INTERVAL_DAYS = [1, 3, 7, 14, 30]
LEARNING_EVENT_LEDGER_NAME = "learning_events.jsonl"
LEARNING_EVENT_SCHEMA_VERSION = f"{SCHEMA_VERSION}/event"
MAX_PACKET_SCORE_REFS = 3


@dataclass(frozen=True)
class FailureClass:
    class_id: str
    title: str
    summary: str
    keywords: tuple[str, ...]
    event_types: tuple[str, ...]
    triggers: tuple[str, ...]
    first_actions: tuple[str, ...]
    evidence: tuple[str, ...]
    decision_gates: tuple[str, ...]
    escalation: tuple[str, ...]
    agent_checklist: tuple[str, ...]
    avoid: tuple[str, ...]


FAILURE_CLASSES: tuple[FailureClass, ...] = (
    FailureClass(
        class_id="control-plane-distrust",
        title="Untrusted control-plane integrity check",
        summary="When a management plane is implicated, treat the console, portal, audit log, and API as evidence sources that require corroboration.",
        keywords=("control-plane", "console", "portal", "audit gap", "audit log", "out-of-band", "trusted truth", "green vendor status", "vendor api", "rmm", "psa", "backup portal", "idp"),
        event_types=("control-plane", "rmm", "backup", "psa", "identity", "vendor-portal"),
        triggers=("Management plane appears involved", "Audit trail has gaps", "Portal/API reports conflict with observed impact"),
        first_actions=("Create or move command outside the suspect platform", "Export and hash console/portal/API state before mutation", "Corroborate with identity, endpoint, storage, or vendor-side evidence"),
        evidence=("Console/portal audit export", "API/session logs", "Identity sign-in and admin-action logs", "Endpoint or storage-side corroboration"),
        decision_gates=("Do not use the suspect plane for cleanup until evidence and integrity are preserved", "Use emergency exceptions only when active harm outweighs evidence loss"),
        escalation=("Escalate to infrastructure/vendor liaison when the management plane may be compromised",),
        agent_checklist=("Name the suspect control plane", "State what evidence proves or disproves its integrity", "Use an out-of-band path for command and evidence tracking"),
        avoid=("Do not treat a working console or green status page as proof", "Do not clean up through the suspect platform as the first action"),
    ),
    FailureClass(
        class_id="vendor-escalation",
        title="Vendor escalation and artifact handoff",
        summary="When vendor software, portals, APIs, plugins, or hosted control planes may be part of the incident, open a vendor escalation with preserved artifact IDs.",
        keywords=("vendor", "plugin", "support", "escalation", "status page", "supply chain", "artifact id", "case number", "job queue", "hosted"),
        event_types=("vendor", "supply-chain", "plugin", "hosted-control-plane", "support-case"),
        triggers=("Vendor plugin/update anomaly", "Vendor-hosted control plane shows destructive or suspicious activity", "Local evidence is insufficient to prove vendor-side state"),
        first_actions=("Open vendor escalation after preserving local evidence", "Provide artifact IDs, timestamps, hashes, tenant scope, and observed blast radius", "Ask vendor for server-side audit, job executor, token, and rollout evidence"),
        evidence=("Vendor ticket/case ID", "Artifact hashes", "Timestamps in UTC", "Affected tenant list kept internal", "Vendor-side audit/export response"),
        decision_gates=("Escalate vendor before relying on portal status for containment claims", "Do not delay emergency containment solely for vendor response when active harm is imminent"),
        escalation=("Vendor support/security escalation", "Senior incident lead owns vendor-facing scope and wording"),
        agent_checklist=("Name the vendor risk path", "List exactly what artifacts go to vendor", "Separate vendor escalation from customer-facing confirmation"),
        avoid=("Do not say vendor compromise is confirmed without evidence", "Do not let vendor status page replace evidence preservation"),
    ),
    FailureClass(
        class_id="tenant-safe-communications",
        title="Tenant-safe incident communications",
        summary="Customer communications must be tenant-specific, confidence-calibrated, and separated from internal cross-tenant bridge knowledge.",
        keywords=("tenant", "customer", "communication", "comms", "shared customer", "one customer email", "cross-tenant", "disclose", "notification", "sales vp", "contained"),
        event_types=("communications", "multi-tenant", "customer-notification", "regulated-client"),
        triggers=("Multiple customers affected", "Pressure to send a single shared update", "Material facts are still unconfirmed"),
        first_actions=("Open internal major incident record plus per-tenant child/customer records", "Draft tenant-specific updates with known/unknown/actions/next-update", "Keep cross-tenant blast radius internal and access-controlled"),
        evidence=("Per-tenant impact matrix", "Communication approval log", "Known/unknown facts at send time", "Next update timestamp"),
        decision_gates=("Do not assert breach or containment before evidence supports it", "Legal/compliance review for regulated or material notifications"),
        escalation=("Customer-success/comms owner", "Legal/compliance when disclosure obligations may be triggered"),
        agent_checklist=("Say what is tenant-specific", "State confidence and next update time", "Name who approves customer wording"),
        avoid=("Do not send one shared customer email", "Do not reveal other affected clients", "Do not over-confirm containment"),
    ),
    FailureClass(
        class_id="evidence-preservation",
        title="Evidence-first containment sequencing",
        summary="Preserve volatile, identity, SaaS, endpoint, and control-plane evidence before disruptive cleanup unless a documented emergency gate is crossed.",
        keywords=("evidence", "preserve", "volatile", "hash", "forensic", "logs", "token", "session", "audit", "memory", "mutation", "cleanup", "destroy"),
        event_types=("evidence", "forensics", "containment", "audit", "volatile-state"),
        triggers=("Responder action could destroy logs or session state", "Cleanup or revocation is proposed before export", "Endpoint/control-plane evidence is volatile"),
        first_actions=("Capture raw logs/artifacts before mutation", "Hash exported artifacts and record collector/time/source", "Use write-once or restricted evidence storage"),
        evidence=("Raw alert/export files", "Hash ledger", "Collector/source/time notes", "Volatile host/session state where feasible"),
        decision_gates=("Capture first unless active harm threshold is worse than waiting", "Document emergency exception before destructive action"),
        escalation=("Evidence owner or incident scribe owns chain-of-custody notes",),
        agent_checklist=("State what evidence is volatile", "State what can be safely collected", "State what action would mutate evidence"),
        avoid=("Do not store live bearer/session tokens loosely", "Do not reboot, revoke, delete, or roll back before evidence gates"),
    ),
    FailureClass(
        class_id="continuity-gating",
        title="Service continuity containment gate",
        summary="Security containment must be segmented by tenant and continuity risk, especially for 24/7, medical, logistics, restore, and night-shift operations.",
        keywords=("continuity", "24/7", "24x7", "medical", "logistics", "restore", "night-shift", "availability", "active restores", "lock out", "operations"),
        event_types=("24x7", "service-continuity", "restore", "medical", "logistics", "access-continuity"),
        triggers=("Critical customer operations are active", "Mass isolation/sign-out/cancellation may break service", "Restores or night-shift access are in progress"),
        first_actions=("Build tenant impact and continuity matrix", "Use narrow reversible containment before broad disruption", "Get customer-owner gate for continuity-protected actions when feasible"),
        evidence=("Customer impact matrix", "Service health evidence", "Approvals/exceptions", "Rollback readiness"),
        decision_gates=("Emergency override only when active harm is worse than operational disruption", "Rollback path and monitoring must be named before broad action"),
        escalation=("Senior incident lead and customer owner for disruptive continuity decisions",),
        agent_checklist=("Identify protected operations", "Separate tenants by risk and action", "Name rollback and monitor checks"),
        avoid=("Do not mass isolate/sign out/cancel across tenants blindly", "Do not protect evidence by breaking active restores without a gate"),
    ),
    FailureClass(
        class_id="authority-escalation",
        title="Authority and role activation",
        summary="Broad multi-tenant, destructive, regulated, or control-plane events require named incident authority instead of a solo overnight engineer.",
        keywords=("authority", "senior", "leadership", "overnight", "solo", "wake", "incident lead", "legal", "compliance", "role", "owner", "approval"),
        event_types=("authority", "major-incident", "after-hours", "regulated-client", "destructive-action"),
        triggers=("Only one engineer is awake", "Action affects multiple tenants", "Legal/compliance or destructive authority is exceeded"),
        first_actions=("Declare major incident posture", "Assign incident lead, evidence owner, technical owner, comms owner, and vendor liaison as needed", "Escalate legal/compliance when regulated or material notification risk exists"),
        evidence=("Decision log", "Role assignment log", "Approval source", "Legal/compliance escalation note"),
        decision_gates=("Wake senior authority for cross-tenant, destructive, regulated, or control-plane scope", "Record owner and approval before broad or irreversible action"),
        escalation=("Senior incident lead", "Infrastructure lead", "Customer-success/comms owner", "Legal/compliance when facts warrant"),
        agent_checklist=("Name who owns the incident", "Name who owns evidence/comms/vendor path", "State when legal/compliance wakes"),
        avoid=("Do not let one overnight engineer silently carry a SEV-1", "Do not bury authority gaps inside technical steps"),
    ),
    FailureClass(
        class_id="operator-efficiency",
        title="First-hour operator efficiency",
        summary="A strong answer must be executable under pressure: short enough to run, ordered by time/owner/gate, and free of idealized collection steps.",
        keywords=("too long", "overextended", "efficiency", "first-hour", "under pressure", "idealized", "harder to execute", "concise", "checklist", "operationally underspecified"),
        event_types=("operator-execution", "first-hour", "runbook"),
        triggers=("Answer is accurate but too long for an on-call responder", "Collection details are idealized or hidden behind judgment calls"),
        first_actions=("Prefer a timed checklist with owner, gate, and output for each block", "Separate immediate actions from follow-up depth", "Cut narrative that does not change a first-hour decision"),
        evidence=("Time-boxed action list", "Owner/gate per action", "Deferred deep-dive list"),
        decision_gates=("If a step is infeasible at 2 AM, downgrade it to follow-up or condition it",),
        escalation=("Incident scribe tracks deferred depth and unresolved assumptions",),
        agent_checklist=("Keep the public plan runnable", "Prefer numbered steps over long prose", "Make every line change an action or decision"),
        avoid=("Do not turn first-hour response into a full IR policy", "Do not hide risky collection details behind vague language"),
    ),
    FailureClass(
        class_id="lead-control-self-check",
        title="Lead-thread control and self-check",
        summary="Para should show private control: accept useful pressure, reject irrelevant pressure, and perform a final self-check before the public answer.",
        keywords=("self-check", "adversarial", "rejected", "discarded", "control", "funnel", "pressure", "objection", "absorption", "lead direction"),
        event_types=("para-control", "self-check", "adversarial-review"),
        triggers=("Judge says objections were forwarded without filtering", "Self-check is procedural rather than substantive", "Objection absorption score is weak"),
        first_actions=("Ask whether each pressure point changes correctness, scope, safety, or usefulness", "Accept only pressure that survives that check", "Write final answer from the lead position, not as a debate recap"),
        evidence=("Control audit", "Accepted pressure list", "Rejected/downgraded pressure list", "Final self-check"),
        decision_gates=("Do not change course merely because an objection exists", "Reject pressure that does not change the decision"),
        escalation=("Spawn a new lane only for materially missing pressure",),
        agent_checklist=("State accepted pressure", "State rejected pressure", "Run final self-check against user request"),
        avoid=("Do not act as a funnel for every lane", "Do not erase contradictions by averaging them"),
    ),
)


SCENARIO_RULES: tuple[tuple[str, tuple[str, ...], str, tuple[str, ...]], ...] = (
    ("rmm-control-plane", ("rmm", "powershell", "vendor plugin", "agent", "supply chain"), "RMM control-plane incident", ("rmm", "control-plane", "remote-access")),
    ("backup-restore-destruction", ("backup", "restore", "immutable", "deletion job", "job queue"), "Backup/restore destruction incident", ("backup", "restore", "destructive-job")),
    ("identity-oauth-saas", ("oauth", "microsoft 365", "entra", "mailbox", "conditional access", "sign-in"), "Identity/OAuth SaaS incident", ("identity", "oauth", "saas")),
    ("service-desk-access", ("password", "mfa", "offboarding", "caller", "access request"), "Service desk access incident", ("service-desk", "access")),
    ("azure-hosting", ("azure", "app service", "rbac", "key vault", "nsg", "dns", "subscription"), "Azure hosting incident", ("azure", "hosting")),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compact(value: Any, limit: int = 360) -> str:
    return knowledgebase.compact(value, limit)


def tokenize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def split_csv(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[,;\n]+", str(value or ""))
    items: List[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def unique_items(values: Iterable[Any]) -> List[str]:
    items: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def exemplar_refs(refs: List[str], limit: int = MAX_PACKET_SCORE_REFS) -> List[str]:
    clean = unique_items(refs)
    max_items = max(1, int(limit or 1))
    if len(clean) <= max_items:
        return clean
    if max_items == 1:
        return [clean[-1]]
    head_count = max(1, max_items - 1)
    selected = clean[:head_count] + clean[-(max_items - head_count) :]
    return unique_items(selected)[:max_items]


def learning_group_key(scenario_id: Any, failure_class: Any) -> str:
    scenario = str(scenario_id or "unknown").strip() or "unknown"
    failure = str(failure_class or "unknown").strip() or "unknown"
    return f"{scenario}:{failure}"


def relative_to_root(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def learning_event_ledger_path(root: Path | str, bank_id: str) -> Path:
    return knowledgebase.bank_dir(root, bank_id) / LEARNING_EVENT_LEDGER_NAME


def parse_score_ref(score_ref: Any) -> Dict[str, str]:
    ref = str(score_ref or "").replace("\\", "/").strip()
    parts = [part for part in ref.split("/") if part]
    parsed = {"scoreRef": ref, "runId": "", "caseId": "", "variantId": "", "replicateId": ""}
    try:
        runs_index = parts.index("runs")
        parsed["runId"] = parts[runs_index + 1]
    except (ValueError, IndexError):
        pass
    try:
        cases_index = parts.index("cases")
        parsed["caseId"] = parts[cases_index + 1]
        parsed["variantId"] = parts[cases_index + 2]
        parsed["replicateId"] = parts[cases_index + 3]
    except (ValueError, IndexError):
        pass
    return parsed


def score_value(section: Dict[str, Any], field: str) -> Optional[float]:
    scores = section.get("scores") if isinstance(section.get("scores"), dict) else {}
    value = scores.get(field)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def section_text(section: Any) -> str:
    if not isinstance(section, dict):
        return ""
    parts: List[str] = []
    for key in (
        "verdict",
        "strongestStrength",
        "strongestWeakness",
        "strongestControlStrength",
        "strongestControlWeakness",
        "rationale",
    ):
        if section.get(key):
            parts.append(str(section.get(key)))
    return "\n".join(parts)


def score_learning_text(score: Dict[str, Any]) -> str:
    parts = [
        section_text(score.get("quality")),
        section_text(score.get("answerHealth")),
        section_text(score.get("control")),
        section_text(score.get("comparison")),
    ]
    deterministic = score.get("deterministic") if isinstance(score.get("deterministic"), dict) else {}
    if not deterministic.get("passed", True):
        parts.append(json.dumps(deterministic.get("checks") or {}, ensure_ascii=True))
    return "\n".join(part for part in parts if part)


def classify_scenario(case: Dict[str, Any]) -> Dict[str, Any]:
    haystack = tokenize_text(
        " ".join(
            [
                str(case.get("caseId") or ""),
                str(case.get("title") or ""),
                str(case.get("objective") or ""),
                str(case.get("sessionContext") or ""),
                " ".join(str(item) for item in case.get("constraints", []) if item),
            ]
        )
    )
    for scenario_id, keywords, title, tags in SCENARIO_RULES:
        if any(keyword in haystack for keyword in keywords):
            return {"scenarioId": scenario_id, "scenarioTitle": title, "tags": list(tags)}
    return {"scenarioId": "msp-major-incident", "scenarioTitle": "MSP major incident", "tags": ["major-incident", "msp"]}


def metric_failure_classes(score: Dict[str, Any]) -> List[str]:
    classes: List[str] = []

    def add(class_id: str) -> None:
        if class_id not in classes:
            classes.append(class_id)

    quality = score.get("quality") if isinstance(score.get("quality"), dict) else {}
    health = score.get("answerHealth") if isinstance(score.get("answerHealth"), dict) else {}
    control = score.get("control") if isinstance(score.get("control"), dict) else {}

    if (score_value(quality, "objectionAbsorption") or 10) <= 7:
        add("lead-control-self-check")
    if (score_value(health, "efficiencyDiscipline") or 10) <= 6 or (score_value(health, "structuralClarity") or 10) <= 7:
        add("operator-efficiency")
    if (score_value(health, "evidenceHygiene") or 10) <= 7:
        add("evidence-preservation")
    if (score_value(quality, "tradeoffHandling") or 10) <= 7:
        add("continuity-gating")
    if (score_value(control, "selfCheckQuality") or 10) <= 6 or (score_value(control, "adversarialDiscipline") or 10) <= 6:
        add("lead-control-self-check")
    return classes


def matched_failure_classes(score: Dict[str, Any]) -> List[FailureClass]:
    text = tokenize_text(score_learning_text(score))
    matched_ids = set(metric_failure_classes(score))
    for failure in FAILURE_CLASSES:
        if any(keyword in text for keyword in failure.keywords):
            matched_ids.add(failure.class_id)
    by_id = {failure.class_id: failure for failure in FAILURE_CLASSES}
    return [by_id[class_id] for class_id in sorted(matched_ids) if class_id in by_id]


def extract_score_observation(score: Dict[str, Any], score_ref: str, failure: FailureClass) -> Dict[str, Any]:
    quality = score.get("quality") if isinstance(score.get("quality"), dict) else {}
    health = score.get("answerHealth") if isinstance(score.get("answerHealth"), dict) else {}
    control = score.get("control") if isinstance(score.get("control"), dict) else {}
    weakness = (
        str(quality.get("strongestWeakness") or "").strip()
        or str(health.get("strongestWeakness") or "").strip()
        or str(control.get("strongestControlWeakness") or "").strip()
    )
    rationale = (
        str(quality.get("rationale") or "").strip()
        or str(health.get("rationale") or "").strip()
        or str(control.get("rationale") or "").strip()
    )
    scores = {
        "quality": score_value(quality, "overallQuality"),
        "health": score_value(health, "overallHealth"),
        "control": score_value(control, "overallControl"),
    }
    deficits = [max(0.0, 8.0 - value) for value in scores.values() if value is not None]
    return {
        "scoreRef": score_ref,
        "variantId": str(score.get("variantId") or ""),
        "armId": str(score.get("armId") or ""),
        "weakness": compact(weakness, 280),
        "rationale": compact(rationale, 360),
        "scoreDeficit": round(sum(deficits), 2),
        "scores": {key: value for key, value in scores.items() if value is not None},
        "failureClass": failure.class_id,
    }


def run_cases_by_id(run: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    suite = run.get("inlineSuite") if isinstance(run.get("inlineSuite"), dict) else run.get("suite")
    cases = suite.get("cases") if isinstance(suite, dict) and isinstance(suite.get("cases"), list) else []
    return {str(case.get("caseId") or ""): case for case in cases if isinstance(case, dict) and str(case.get("caseId") or "").strip()}


def iter_run_score_files(root: Path, run_id: str) -> Iterable[Path]:
    run_dir = storage.project_paths(root).root / "data" / "evals" / "runs" / run_id
    cases_dir = run_dir / "cases"
    if not cases_dir.is_dir():
        return []
    return sorted(cases_dir.rglob("score.json"))


def load_json(path: Path) -> Dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def latest_eval_run_ids(root: Path, limit: int = 1) -> List[str]:
    runs_dir = storage.project_paths(root).root / "data" / "evals" / "runs"
    if not runs_dir.is_dir():
        return []
    candidates = [path for path in runs_dir.iterdir() if path.is_dir() and (path / "run.json").is_file()]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [path.name for path in candidates[: max(1, int(limit or 1))]]


def replay_interval_for_misses(miss_count: int) -> int:
    index = min(len(REPLAY_INTERVAL_DAYS) - 1, max(0, int(math.log2(max(1, miss_count)))))
    return REPLAY_INTERVAL_DAYS[index]


def learning_event_from_ref(root: Path, bank_id: str, record: Dict[str, Any], score_ref: str, *, now: Optional[str] = None) -> Dict[str, Any]:
    timestamp = now or utc_now()
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    scenario_id = str(metadata.get("learning.scenarioId") or "unknown").strip() or "unknown"
    failure_class = str(metadata.get("learning.failureClass") or "unknown").strip() or "unknown"
    record_id = str(record.get("id") or "").strip()
    parsed = parse_score_ref(score_ref)
    group_key = learning_group_key(scenario_id, failure_class)
    event_id = knowledgebase.stable_id("learn_evt", bank_id, record_id, parsed["scoreRef"])
    return {
        "id": event_id,
        "schemaVersion": LEARNING_EVENT_SCHEMA_VERSION,
        "bankId": knowledgebase.safe_bank_id(bank_id),
        "memoryId": record_id,
        "group": group_key,
        "scenarioId": scenario_id,
        "failureClass": failure_class,
        "scoreRef": parsed["scoreRef"],
        "runId": parsed["runId"],
        "caseId": parsed["caseId"],
        "variantId": parsed["variantId"],
        "replicateId": parsed["replicateId"],
        "source": "judge-score",
        "firstSeenAt": timestamp,
        "lastSeenAt": timestamp,
    }


def read_learning_events(root: Path | str, bank_id: str) -> tuple[List[Dict[str, Any]], List[str]]:
    path = learning_event_ledger_path(root, bank_id)
    events: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if not path.is_file():
        return events, warnings
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for offset, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                warnings.append(f"{path.name}:{offset} invalid JSONL event: {exc.msg}")
                continue
            if not isinstance(parsed, dict):
                continue
            event_id = str(parsed.get("id") or "").strip()
            score_ref = str(parsed.get("scoreRef") or "").strip()
            memory_id = str(parsed.get("memoryId") or "").strip()
            if event_id and score_ref and memory_id:
                events.append(parsed)
    return events, warnings[:20]


def write_learning_events(root: Path | str, bank_id: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    path = learning_event_ledger_path(root, bank_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing, warnings = read_learning_events(root, bank_id)
    by_id: Dict[str, Dict[str, Any]] = {str(event.get("id") or ""): event for event in existing if event.get("id")}
    inserted = 0
    updated = 0
    unchanged = 0
    for event in events:
        event_id = str(event.get("id") or "").strip()
        if not event_id:
            continue
        current = by_id.get(event_id)
        if current is None:
            by_id[event_id] = event
            inserted += 1
            continue
        merged = dict(current)
        changed_fields = False
        for key, value in event.items():
            if key in {"firstSeenAt", "lastSeenAt"} or value in (None, ""):
                continue
            if not merged.get(key):
                merged[key] = value
                changed_fields = True
        merged["firstSeenAt"] = current.get("firstSeenAt") or event.get("firstSeenAt") or utc_now()
        merged["lastSeenAt"] = event.get("lastSeenAt") if changed_fields else current.get("lastSeenAt") or event.get("lastSeenAt") or utc_now()
        if merged == current:
            unchanged += 1
        else:
            by_id[event_id] = merged
            updated += 1
    ordered = sorted(by_id.values(), key=lambda item: (str(item.get("group") or ""), str(item.get("scoreRef") or ""), str(item.get("id") or "")))
    path.write_text("\n".join(json.dumps(item, ensure_ascii=True, sort_keys=True) for item in ordered) + ("\n" if ordered else ""), encoding="utf-8")
    return {"inserted": inserted, "updated": updated, "unchanged": unchanged, "count": len(ordered), "path": str(path), "warnings": warnings}


def event_refs_by_memory(events: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    refs: Dict[str, List[str]] = defaultdict(list)
    for event in events:
        memory_id = str(event.get("memoryId") or "").strip()
        score_ref = str(event.get("scoreRef") or "").strip()
        if memory_id and score_ref and score_ref not in refs[memory_id]:
            refs[memory_id].append(score_ref)
    return refs


def event_runs_by_memory(events: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    runs: Dict[str, List[str]] = defaultdict(list)
    for event in events:
        memory_id = str(event.get("memoryId") or "").strip()
        run_id = str(event.get("runId") or "").strip()
        if memory_id and run_id and run_id not in runs[memory_id]:
            runs[memory_id].append(run_id)
    return runs


def score_deficit(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def update_learning_text(record: Dict[str, Any], *, miss_count: int, run_count: int, adaptive_weight: float, interval: int) -> str:
    sop = record.get("sop") if isinstance(record.get("sop"), dict) else {}
    use_case = str(sop.get("useCase") or record.get("title") or "MSP major incident")
    scenario_title = use_case.split(":", 1)[0].strip() or "MSP major incident"
    summary = str(sop.get("summary") or "").strip()
    if not summary:
        summary = compact(record.get("text"), 240)
    return (
        f"Judge-learned MSP SOP delta for {scenario_title}: {summary} "
        f"This is a failure-class memory, not an answer key. It was reinforced by {miss_count} judge observation(s) "
        f"across {run_count} run(s). Adaptive replay weight {adaptive_weight}; next replay interval {interval} day(s)."
    )


def compact_learning_packet(
    root: Path,
    bank_id: str,
    record: Dict[str, Any],
    score_refs: List[str],
    *,
    score_deficit_total: Optional[float] = None,
    touch: bool = True,
) -> Dict[str, Any]:
    metadata = dict(record.get("metadata") if isinstance(record.get("metadata"), dict) else {})
    metadata.pop("learning.pendingScoreRefs", None)
    all_refs = unique_items(score_refs)
    exemplars = exemplar_refs(all_refs)
    source_runs = unique_items(
        [
            *split_csv(metadata.get("learning.sourceRuns")),
            *[parse_score_ref(ref).get("runId") for ref in all_refs],
        ]
    )
    miss_count = len(all_refs)
    total_deficit = round(score_deficit_total if score_deficit_total is not None else score_deficit(metadata.get("learning.scoreDeficit")), 2)
    adaptive_weight = round(min(10.0, miss_count + total_deficit), 2)
    interval = replay_interval_for_misses(miss_count)
    next_replay = (
        (datetime.now(timezone.utc) + timedelta(days=interval)).replace(microsecond=0).isoformat()
        if touch or not metadata.get("learning.nextReplayAfter")
        else str(metadata.get("learning.nextReplayAfter"))
    )
    last_seen = utc_now() if touch or not metadata.get("learning.lastSeenAt") else str(metadata.get("learning.lastSeenAt"))
    ledger_path = relative_to_root(root, learning_event_ledger_path(root, bank_id))
    metadata.update(
        {
            "learning.sourceRuns": ",".join(source_runs[:12]),
            "learning.sourceRunCount": len(source_runs),
            "learning.scoreRefs": ",".join(exemplars),
            "learning.exemplarScoreRefs": ",".join(exemplars),
            "learning.scoreRefMode": "exemplar",
            "learning.scoreRefCount": miss_count,
            "learning.eventCount": miss_count,
            "learning.eventLedger": ledger_path,
            "learning.eventLedgerSchemaVersion": LEARNING_EVENT_SCHEMA_VERSION,
            "learning.missCount": miss_count,
            "learning.scoreDeficit": total_deficit,
            "learning.adaptiveWeight": adaptive_weight,
            "learning.replayIntervalDays": interval,
            "learning.nextReplayAfter": next_replay,
            "learning.lastSeenAt": last_seen,
        }
    )
    compacted = dict(record)
    compacted["metadata"] = metadata
    compacted["sourceId"] = ",".join(source_runs[:6]) or str(record.get("sourceId") or "")
    sop = dict(record.get("sop") if isinstance(record.get("sop"), dict) else {})
    if sop:
        sop["sourceRefs"] = exemplars
        compacted["sop"] = sop
    compacted["text"] = update_learning_text(
        compacted,
        miss_count=miss_count,
        run_count=len(source_runs),
        adaptive_weight=adaptive_weight,
        interval=interval,
    )
    return knowledgebase.normalize_record(compacted) or compacted


def build_learning_record(
    *,
    root: Path,
    bank_id: str,
    run_ids: List[str],
    case: Dict[str, Any],
    scenario: Dict[str, Any],
    failure: FailureClass,
    observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    now = utc_now()
    miss_count = len(observations)
    total_deficit = round(sum(float(item.get("scoreDeficit") or 0.0) for item in observations), 2)
    adaptive_weight = round(min(10.0, miss_count + total_deficit), 2)
    interval = replay_interval_for_misses(miss_count)
    due_after = (datetime.now(timezone.utc) + timedelta(days=interval)).replace(microsecond=0).isoformat()
    scenario_id = str(scenario.get("scenarioId") or "msp-major-incident")
    scenario_title = str(scenario.get("scenarioTitle") or "MSP major incident")
    record_id = knowledgebase.stable_id("mem_learn", bank_id, scenario_id, failure.class_id)
    source_refs = unique_items([item["scoreRef"] for item in observations if item.get("scoreRef")])
    exemplars = exemplar_refs(source_refs)
    ledger_path = relative_to_root(root, learning_event_ledger_path(root, bank_id))
    weakness_lines = [
        f"- {compact(item.get('variantId'), 80)}: {compact(item.get('weakness') or item.get('rationale'), 220)}"
        for item in observations[:5]
        if item.get("weakness") or item.get("rationale")
    ]
    text = (
        f"Judge-learned MSP SOP delta for {scenario_title}: {failure.summary} "
        f"This is a failure-class memory, not an answer key. It was reinforced by {miss_count} judge observation(s) "
        f"across {len(run_ids)} run(s). Adaptive replay weight {adaptive_weight}; next replay interval {interval} day(s)."
    )
    context = (
        f"Case family: {scenario_title}. Source case: {case.get('caseId') or 'unknown'}. "
        "Observed judge pressure:\n" + ("\n".join(weakness_lines) if weakness_lines else "No compact weakness text captured.")
    )
    tags = [
        "msp",
        "sop",
        "learned",
        "judge-learning",
        "failure-class",
        scenario_id,
        failure.class_id,
        *[str(tag) for tag in scenario.get("tags", [])],
    ]
    record = {
        "id": record_id,
        "bankId": bank_id,
        "title": f"Learned: {failure.title} ({scenario_title})",
        "type": "runbook",
        "source": "judge-learning",
        "sourceId": ",".join(run_ids[:6]),
        "text": text,
        "context": context,
        "tags": tags,
        "entities": ["MSP", scenario_title, failure.title],
        "metadata": {
            "learning.schemaVersion": SCHEMA_VERSION,
            "learning.kind": "judge-score-failure-class",
            "learning.failureClass": failure.class_id,
            "learning.scenarioId": scenario_id,
            "learning.sourceRuns": ",".join(run_ids[:12]),
            "learning.sourceRunCount": len(run_ids),
            "learning.pendingScoreRefs": ",".join(source_refs[:80]),
            "learning.scoreRefs": ",".join(exemplars),
            "learning.exemplarScoreRefs": ",".join(exemplars),
            "learning.scoreRefMode": "exemplar",
            "learning.scoreRefCount": len(source_refs),
            "learning.eventCount": len(source_refs),
            "learning.eventLedger": ledger_path,
            "learning.eventLedgerSchemaVersion": LEARNING_EVENT_SCHEMA_VERSION,
            "learning.missCount": miss_count,
            "learning.scoreDeficit": total_deficit,
            "learning.adaptiveWeight": adaptive_weight,
            "learning.replayIntervalDays": interval,
            "learning.nextReplayAfter": due_after,
            "learning.lastSeenAt": now,
        },
        "sop": {
            "schemaVersion": "msp-learned-sop/v1",
            "useCase": f"{scenario_title}: {failure.title}",
            "summary": failure.summary,
            "eventTypes": list(failure.event_types),
            "triggers": list(failure.triggers),
            "firstActions": list(failure.first_actions),
            "evidence": list(failure.evidence),
            "decisionGates": list(failure.decision_gates),
            "communications": [],
            "escalation": list(failure.escalation),
            "agentChecklist": list(failure.agent_checklist),
            "avoid": list(failure.avoid),
            "handoff": ["If this packet fires during an eval, use it as a missing-check nudge, not as a memorized final answer."],
            "sourceRefs": exemplars,
            "fallback": "If learned memory is unavailable, fall back to the base MSP SOP and current runtime logs.",
        },
        "createdAt": now,
    }
    return knowledgebase.normalize_record(record) or record


def merge_learning_record(
    root: Path,
    bank_id: str,
    existing: Dict[str, Any],
    incoming: Dict[str, Any],
    *,
    existing_event_refs: Optional[List[str]] = None,
) -> tuple[Dict[str, Any], List[str]]:
    merged = dict(existing)
    existing_meta = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
    incoming_meta = incoming.get("metadata") if isinstance(incoming.get("metadata"), dict) else {}
    existing_refs = unique_items(
        [
            *(existing_event_refs or []),
            *split_csv(existing_meta.get("learning.scoreRefs")),
            *split_csv(existing_meta.get("learning.exemplarScoreRefs")),
        ]
    )
    incoming_refs = unique_items([*split_csv(incoming_meta.get("learning.pendingScoreRefs")), *split_csv(incoming_meta.get("learning.scoreRefs"))])
    combined_refs = existing_refs + [ref for ref in incoming_refs if ref not in existing_refs]
    if len(combined_refs) == len(existing_refs):
        compacted = compact_learning_packet(root, bank_id, existing, combined_refs, touch=False)
        return compacted, combined_refs

    source_runs = split_csv(existing_meta.get("learning.sourceRuns")) + [
        run_id for run_id in split_csv(incoming_meta.get("learning.sourceRuns")) if run_id not in split_csv(existing_meta.get("learning.sourceRuns"))
    ]
    miss_count = len(combined_refs)
    try:
        existing_deficit = float(existing_meta.get("learning.scoreDeficit") or 0.0)
    except (TypeError, ValueError):
        existing_deficit = 0.0
    try:
        incoming_deficit = float(incoming_meta.get("learning.scoreDeficit") or 0.0)
    except (TypeError, ValueError):
        incoming_deficit = 0.0
    score_deficit = round(existing_deficit + incoming_deficit, 2)
    adaptive_weight = round(min(10.0, miss_count + score_deficit), 2)
    interval = replay_interval_for_misses(miss_count)
    next_replay = (datetime.now(timezone.utc) + timedelta(days=interval)).replace(microsecond=0).isoformat()

    merged_meta = dict(existing_meta)
    merged_meta.update(
        {
            "learning.sourceRuns": ",".join(source_runs[:12]),
            "learning.sourceRunCount": len(source_runs),
            "learning.missCount": miss_count,
            "learning.scoreDeficit": score_deficit,
            "learning.adaptiveWeight": adaptive_weight,
            "learning.replayIntervalDays": interval,
            "learning.nextReplayAfter": next_replay,
            "learning.lastSeenAt": utc_now(),
        }
    )
    merged["metadata"] = merged_meta
    merged["createdAt"] = str(incoming.get("createdAt") or existing.get("createdAt") or utc_now())
    compacted = compact_learning_packet(root, bank_id, merged, combined_refs, score_deficit_total=score_deficit)
    return compacted, combined_refs


def upsert_records(root: Path, bank_id: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    path = knowledgebase.bank_records_path(root, bank_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_events, event_warnings = read_learning_events(root, bank_id)
    refs_by_memory = event_refs_by_memory(existing_events)
    existing: List[Dict[str, Any]] = []
    if path.is_file():
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                existing.append(parsed)
    by_id = {str(item.get("id") or ""): index for index, item in enumerate(existing)}
    inserted = 0
    updated = 0
    unchanged = 0
    ledger_events: List[Dict[str, Any]] = []
    for record in records:
        record_id = str(record.get("id") or "")
        if record_id and record_id in by_id:
            index = by_id[record_id]
            merged, refs = merge_learning_record(
                root,
                bank_id,
                existing[index],
                record,
                existing_event_refs=refs_by_memory.get(record_id, []),
            )
            if merged == existing[index]:
                unchanged += 1
            else:
                existing[index] = merged
                updated += 1
            ledger_events.extend(learning_event_from_ref(root, bank_id, merged, ref) for ref in refs)
            continue
        incoming_meta = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        refs = unique_items([*split_csv(incoming_meta.get("learning.pendingScoreRefs")), *split_csv(incoming_meta.get("learning.scoreRefs"))])
        compacted = compact_learning_packet(root, bank_id, record, refs)
        existing.append(compacted)
        if record_id:
            by_id[record_id] = len(existing) - 1
        ledger_events.extend(learning_event_from_ref(root, bank_id, compacted, ref) for ref in refs)
        inserted += 1
    path.write_text("\n".join(json.dumps(item, ensure_ascii=True, sort_keys=True) for item in existing if item) + ("\n" if existing else ""), encoding="utf-8")
    ledger_result = write_learning_events(root, bank_id, ledger_events) if ledger_events else {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "count": len(existing_events),
        "path": str(learning_event_ledger_path(root, bank_id)),
        "warnings": event_warnings,
    }
    return {"inserted": inserted, "updated": updated, "unchanged": unchanged, "path": str(path), "eventLedger": ledger_result}


def compact_learning_bank(root: Path | str, bank_id: str = DEFAULT_LEARNING_BANK_ID, *, dry_run: bool = False) -> Dict[str, Any]:
    paths = storage.project_paths(Path(root))
    normalized_bank = knowledgebase.safe_bank_id(bank_id)
    record_path = knowledgebase.bank_records_path(paths.root, normalized_bank)
    records: List[Dict[str, Any]] = []
    if record_path.is_file():
        for raw in record_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                normalized = knowledgebase.normalize_record(parsed)
                if normalized:
                    records.append(normalized)
    existing_events, event_warnings = read_learning_events(paths.root, normalized_bank)
    refs_by_memory = event_refs_by_memory(existing_events)
    compacted_records: List[Dict[str, Any]] = []
    ledger_events: List[Dict[str, Any]] = []
    changed = 0
    learned_count = 0
    for record in records:
        if "judge-learning" not in record.get("tags", []):
            compacted_records.append(record)
            continue
        learned_count += 1
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        sop = record.get("sop") if isinstance(record.get("sop"), dict) else {}
        refs = unique_items(
            [
                *refs_by_memory.get(str(record.get("id") or ""), []),
                *split_csv(metadata.get("learning.scoreRefs")),
                *split_csv(metadata.get("learning.exemplarScoreRefs")),
                *split_csv(sop.get("sourceRefs")),
            ]
        )
        compacted = compact_learning_packet(paths.root, normalized_bank, record, refs, touch=False)
        compacted_records.append(compacted)
        if compacted != record:
            changed += 1
        ledger_events.extend(learning_event_from_ref(paths.root, normalized_bank, compacted, ref) for ref in refs)
    ledger_result = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "count": len(existing_events),
        "path": str(learning_event_ledger_path(paths.root, normalized_bank)),
        "warnings": event_warnings,
    }
    if not dry_run:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(
            "\n".join(json.dumps(item, ensure_ascii=True, sort_keys=True) for item in compacted_records if item)
            + ("\n" if compacted_records else ""),
            encoding="utf-8",
        )
        ledger_result = write_learning_events(paths.root, normalized_bank, ledger_events)
    librarian = librarian_review(paths.root, normalized_bank, write=not dry_run)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "dryRun": bool(dry_run),
        "bankId": normalized_bank,
        "recordCount": len(records),
        "learnedRecordCount": learned_count,
        "changedRecordCount": changed,
        "eventLedger": ledger_result,
        "librarian": {
            "bankId": librarian.get("bankId"),
            "learnedRecordCount": librarian.get("learnedRecordCount"),
            "groupCount": librarian.get("groupCount"),
            "duplicateGroupCount": librarian.get("duplicateGroupCount"),
            "uniqueScoreRefCount": librarian.get("uniqueScoreRefCount"),
            "eventLedgerCount": (librarian.get("eventLedger") or {}).get("eventCount") if isinstance(librarian.get("eventLedger"), dict) else None,
            "storageDuplication": librarian.get("storageDuplication"),
            "path": librarian.get("path"),
        },
    }


def librarian_index_path(root: Path | str, bank_id: str) -> Path:
    return knowledgebase.bank_dir(root, bank_id) / "librarian_index.json"


def librarian_review(root: Path | str, bank_id: str = DEFAULT_LEARNING_BANK_ID, *, write: bool = True) -> Dict[str, Any]:
    paths = storage.project_paths(Path(root))
    normalized_bank = knowledgebase.safe_bank_id(bank_id)
    records, warnings = knowledgebase.load_persistent_records(paths.root, bank_id=normalized_bank)
    ledger_events, ledger_warnings = read_learning_events(paths.root, normalized_bank)
    warnings.extend(ledger_warnings)
    refs_by_memory = event_refs_by_memory(ledger_events)
    runs_by_memory = event_runs_by_memory(ledger_events)
    learned = [record for record in records if "judge-learning" in record.get("tags", [])]
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    source_refs: set[str] = set()
    score_ref_frequency: Counter[str] = Counter()
    over_weighted: List[Dict[str, Any]] = []
    reinforcement_groups: List[Dict[str, Any]] = []
    vector_candidates: List[Dict[str, Any]] = []
    for record in learned:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        scenario_id = str(metadata.get("learning.scenarioId") or "unknown").strip() or "unknown"
        failure_class = str(metadata.get("learning.failureClass") or "unknown").strip() or "unknown"
        group_key = learning_group_key(scenario_id, failure_class)
        groups[group_key].append(record)
        refs = unique_items(
            [
                *refs_by_memory.get(str(record.get("id") or ""), []),
                *split_csv(metadata.get("learning.scoreRefs")),
                *split_csv(metadata.get("learning.exemplarScoreRefs")),
            ]
        )
        source_runs = unique_items([*runs_by_memory.get(str(record.get("id") or ""), []), *split_csv(metadata.get("learning.sourceRuns"))])
        for ref in refs:
            source_refs.add(ref)
            score_ref_frequency[ref] += 1
        try:
            adaptive_weight = float(metadata.get("learning.adaptiveWeight") or 0.0)
        except (TypeError, ValueError):
            adaptive_weight = 0.0
        try:
            miss_count = int(float(metadata.get("learning.missCount") or 0))
        except (TypeError, ValueError):
            miss_count = 0
        if adaptive_weight >= 10.0:
            over_weighted.append(
                {
                    "id": record.get("id"),
                    "title": record.get("title"),
                    "group": group_key,
                    "adaptiveWeight": adaptive_weight,
                    "missCount": miss_count,
                }
            )
        if adaptive_weight >= 10.0 or len(source_runs) > 1 or miss_count >= 10:
            reinforcement_groups.append(
                {
                    "id": record.get("id"),
                    "group": group_key,
                    "title": record.get("title"),
                    "sourceRunCount": len(source_runs),
                    "scoreRefCount": len(refs),
                    "missCount": miss_count,
                    "adaptiveWeight": adaptive_weight,
                    "state": "saturated" if adaptive_weight >= 10.0 else "reinforced",
                }
            )
        vector_candidates.append(
            {
                "id": record.get("id"),
                "group": group_key,
                "title": record.get("title"),
                "tags": record.get("tags", []),
                "source": record.get("source"),
                "sourceId": record.get("sourceId"),
                "eventCount": len(refs),
                "chunkText": compact(" ".join([str(record.get("title") or ""), str(record.get("text") or ""), str(record.get("context") or "")]), 1200),
            }
        )
    duplicate_groups = [
        {
            "group": group,
            "count": len(items),
            "ids": [str(item.get("id") or "") for item in items],
            "titles": [str(item.get("title") or "") for item in items[:5]],
        }
        for group, items in sorted(groups.items())
        if len(items) > 1
    ]
    score_ref_slots = sum(score_ref_frequency.values())
    ref_reuse = [
        {"scoreRef": ref, "useCount": count}
        for ref, count in score_ref_frequency.most_common()
        if count > 1
    ]
    index = {
        "schemaVersion": f"{SCHEMA_VERSION}/librarian",
        "generatedAt": utc_now(),
        "bankId": normalized_bank,
        "recordCount": len(records),
        "learnedRecordCount": len(learned),
        "groupCount": len(groups),
        "duplicateGroupCount": len(duplicate_groups),
        "uniqueScoreRefCount": len(source_refs),
        "overWeightedCount": len(over_weighted),
        "reinforcementGroupCount": len(reinforcement_groups),
        "eventLedger": {
            "path": str(learning_event_ledger_path(paths.root, normalized_bank)),
            "eventCount": len(ledger_events),
            "schemaVersion": LEARNING_EVENT_SCHEMA_VERSION,
            "authoritativeForScoreRefs": True,
        },
        "storageDuplication": {
            "recordDuplicateGroupCount": len(duplicate_groups),
            "scoreRefSlots": score_ref_slots,
            "uniqueScoreRefCount": len(source_refs),
            "scoreRefReuseSlots": max(0, score_ref_slots - len(source_refs)),
            "scoreRefReuseGroupCount": len(ref_reuse),
            "saturatedGroupCount": len(over_weighted),
            "recommendation": (
                "Keep one learned memory per scenario/failure group. Move raw score-ref history into a compact event ledger "
                "when scoreRefReuseSlots or saturatedGroupCount rises, and keep only exemplar refs on the memory packet."
            ),
        },
        "warnings": warnings,
        "policy": {
            "identity": "Learned memories are keyed by bank + scenario family + failure class, not by exact question wording.",
            "dedupe": "Repeated score refs are ignored. New score refs update the same memory group instead of creating answer-key duplicates.",
            "vectorization": "The vectorCandidates list is an optional middle index. JSONL memory remains authoritative.",
            "reinforcement": "Once a memory group is saturated, new matching score refs should reinforce counters or event history rather than expand the agent-facing packet.",
        },
        "smartDedupePlan": [
            "Use scenarioId + failureClass as the semantic identity for learned MSP runbook memories.",
            "Hash the normalized SOP summary, triggers, firstActions, decisionGates, and avoid list to detect same-lesson reinforcement.",
            "Store repeated score evidence in a per-bank learning event ledger, then keep only top exemplar refs and aggregate counters in memory_units.jsonl.",
            "Treat saturated memories as retrieval priorities with decay/replay metadata, not as text that should keep growing.",
            "Vectorize compact chunks from vectorCandidates only as an optional middle index; never make vectors the authoritative record.",
        ],
        "groups": [
            {
                "group": group,
                "recordCount": len(items),
                "ids": [str(item.get("id") or "") for item in items],
                "titles": [str(item.get("title") or "") for item in items[:3]],
                "scoreRefCount": sum(len(split_csv((item.get("metadata") or {}).get("learning.scoreRefs"))) for item in items),
                "eventCount": sum(
                    len(
                        unique_items(
                            [
                                *refs_by_memory.get(str(item.get("id") or ""), []),
                                *split_csv((item.get("metadata") or {}).get("learning.scoreRefs")),
                                *split_csv((item.get("metadata") or {}).get("learning.exemplarScoreRefs")),
                            ]
                        )
                    )
                    for item in items
                ),
                "sourceRunCount": len(
                    {
                        run_id
                        for item in items
                        for run_id in unique_items(
                            [
                                *runs_by_memory.get(str(item.get("id") or ""), []),
                                *split_csv((item.get("metadata") or {}).get("learning.sourceRuns")),
                            ]
                        )
                    }
                ),
            }
            for group, items in sorted(groups.items())
        ],
        "duplicateGroups": duplicate_groups,
        "reinforcementGroups": sorted(reinforcement_groups, key=lambda item: (str(item.get("state")), str(item.get("group"))))[:120],
        "scoreRefReuse": ref_reuse[:120],
        "overWeighted": over_weighted[:80],
        "vectorCandidates": vector_candidates[:500],
    }
    if write:
        path = librarian_index_path(paths.root, normalized_bank)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(index, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        index["path"] = str(path)
    return index


def learn_from_eval_runs(
    root: Path | str,
    *,
    run_ids: Optional[List[str]] = None,
    latest: int = 1,
    bank_id: str = DEFAULT_LEARNING_BANK_ID,
    dry_run: bool = False,
) -> Dict[str, Any]:
    paths = storage.project_paths(Path(root))
    selected_run_ids = [str(run_id).strip() for run_id in (run_ids or []) if str(run_id).strip()]
    if not selected_run_ids:
        selected_run_ids = latest_eval_run_ids(paths.root, latest)

    grouped: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    score_files_seen = 0
    score_files_learned = 0
    warnings: List[str] = []

    for run_id in selected_run_ids:
        run_dir = paths.root / "data" / "evals" / "runs" / run_id
        run = load_json(run_dir / "run.json")
        if not run:
            warnings.append(f"Missing or unreadable run metadata: {run_id}")
            continue
        cases = run_cases_by_id(run)
        for score_path in iter_run_score_files(paths.root, run_id):
            score_files_seen += 1
            score = load_json(score_path)
            if not score or score.get("error"):
                continue
            failures = matched_failure_classes(score)
            if not failures:
                continue
            case_id = str(score.get("caseId") or score_path.parts[-4] if len(score_path.parts) >= 4 else "")
            case = cases.get(case_id) or {"caseId": case_id, "objective": "", "constraints": [], "sessionContext": ""}
            scenario = classify_scenario(case)
            score_ref = str(score_path.relative_to(paths.root)).replace("\\", "/")
            for failure in failures:
                key = (str(scenario.get("scenarioId") or "msp-major-incident"), failure.class_id, str(case.get("caseId") or ""))
                if key not in grouped:
                    grouped[key] = {
                        "case": case,
                        "scenario": scenario,
                        "failure": failure,
                        "runIds": [],
                        "observations": [],
                    }
                if run_id not in grouped[key]["runIds"]:
                    grouped[key]["runIds"].append(run_id)
                grouped[key]["observations"].append(extract_score_observation(score, score_ref, failure))
                score_files_learned += 1

    records = [
        build_learning_record(
            root=paths.root,
            bank_id=knowledgebase.safe_bank_id(bank_id),
            run_ids=entry["runIds"],
            case=entry["case"],
            scenario=entry["scenario"],
            failure=entry["failure"],
            observations=entry["observations"],
        )
        for entry in grouped.values()
        if entry["observations"]
    ]
    records.sort(key=lambda item: (str((item.get("metadata") or {}).get("learning.scenarioId") or ""), str((item.get("metadata") or {}).get("learning.failureClass") or "")))

    write_result = {"inserted": 0, "updated": 0, "unchanged": 0, "path": str(knowledgebase.bank_records_path(paths.root, bank_id))}
    if not dry_run:
        write_result = upsert_records(paths.root, knowledgebase.safe_bank_id(bank_id), records)
    librarian = librarian_review(paths.root, bank_id, write=not dry_run)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "dryRun": bool(dry_run),
        "bankId": knowledgebase.safe_bank_id(bank_id),
        "runIds": selected_run_ids,
        "scoreFilesSeen": score_files_seen,
        "scoreFilesLearned": score_files_learned,
        "learnedRecordCount": len(records),
        "write": write_result,
        "librarian": {
            "bankId": librarian.get("bankId"),
            "learnedRecordCount": librarian.get("learnedRecordCount"),
            "groupCount": librarian.get("groupCount"),
            "duplicateGroupCount": librarian.get("duplicateGroupCount"),
            "uniqueScoreRefCount": librarian.get("uniqueScoreRefCount"),
            "overWeightedCount": librarian.get("overWeightedCount"),
            "reinforcementGroupCount": librarian.get("reinforcementGroupCount"),
            "eventLedger": librarian.get("eventLedger"),
            "storageDuplication": librarian.get("storageDuplication"),
            "path": librarian.get("path"),
        },
        "warnings": warnings,
        "records": [
            {
                "id": record.get("id"),
                "title": record.get("title"),
                "tags": record.get("tags"),
                "metadata": record.get("metadata"),
            }
            for record in records
        ],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Burn judge scores into compact learned SOP memory packets.")
    parser.add_argument("--root", default=".", help="Project root. Defaults to current directory.")
    parser.add_argument("--run-id", action="append", default=[], help="Eval run id to learn from. May be repeated.")
    parser.add_argument("--latest", type=int, default=1, help="Use the N latest eval runs when --run-id is omitted.")
    parser.add_argument("--bank-id", default=DEFAULT_LEARNING_BANK_ID, help="Knowledgebase bank to write to.")
    parser.add_argument("--dry-run", action="store_true", help="Compute learning records without writing them.")
    parser.add_argument("--librarian-only", action="store_true", help="Only rebuild the librarian index for a bank.")
    parser.add_argument("--compact-ledger", action="store_true", help="Compact learned memory score refs into the per-bank event ledger.")
    args = parser.parse_args(argv)
    if args.compact_ledger:
        result = compact_learning_bank(Path(args.root), args.bank_id, dry_run=args.dry_run)
    elif args.librarian_only:
        result = librarian_review(Path(args.root), args.bank_id, write=not args.dry_run)
    else:
        result = learn_from_eval_runs(
            Path(args.root),
            run_ids=args.run_id,
            latest=args.latest,
            bank_id=args.bank_id,
            dry_run=args.dry_run,
        )
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
