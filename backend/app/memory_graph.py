from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import artifacts, knowledgebase, repo_graph, storage


SCHEMA_VERSION = "fractal-memory-highway/v0"

ROLE_COLORS = {
    "lead": "#6bd394",
    "sceptic": "#ee7f9d",
    "builder": "#54d7d4",
    "operator": "#e7be60",
    "security": "#b59bff",
    "user": "#8fb4ff",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compact(value: Any, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def slug(value: Any, fallback: str = "item") -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text[:52] or fallback


def node(
    node_id: str,
    title: str,
    node_type: str,
    layer: int,
    summary: str,
    evidence: Optional[Iterable[Any]] = None,
    doors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "id": node_id,
        "title": title,
        "type": node_type,
        "layer": int(layer),
        "summary": compact(summary, 520),
        "evidence": [compact(item, 220) for item in list(evidence or []) if compact(item, 220)][:12],
        "doors": doors or [],
    }


def door(to: str, relation: str, weight: float = 0.8) -> Dict[str, Any]:
    return {"to": to, "relation": compact(relation, 80), "weight": max(0.05, min(1.0, float(weight)))}


def lane(lane_id: str, name: str, role: str, trail: List[str], note: str = "") -> Dict[str, Any]:
    compact_trail = [item for index, item in enumerate(trail) if item and item not in trail[:index]]
    current = compact_trail[-1] if compact_trail else "objective"
    return {
        "id": lane_id,
        "name": name,
        "role": role,
        "color": ROLE_COLORS.get(role, ROLE_COLORS["lead"]),
        "current": current,
        "trail": compact_trail,
        "note": note,
        "correlations": [],
    }


def dict_field(payload: Any, key: str) -> Dict[str, Any]:
    value = payload.get(key) if isinstance(payload, dict) else None
    return value if isinstance(value, dict) else {}


def list_field(payload: Any, key: str) -> List[Any]:
    value = payload.get(key) if isinstance(payload, dict) else None
    return value if isinstance(value, list) else []


def objective_text(state: Dict[str, Any]) -> str:
    active_task = dict_field(state, "activeTask")
    draft = dict_field(state, "draft")
    return compact(active_task.get("objective") or draft.get("objective") or "No active objective staged yet.", 420)


def constraints_for(state: Dict[str, Any]) -> List[str]:
    active_task = dict_field(state, "activeTask")
    draft = dict_field(state, "draft")
    values = list_field(active_task, "constraints") or list_field(draft, "constraints")
    return [compact(item, 180) for item in values if compact(item, 180)][:8]


def active_workers(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    workers = state.get("workers")
    if isinstance(workers, dict):
        return [
            copy.deepcopy(value)
            for _, value in sorted(workers.items(), key=lambda item: str(item[0]))
            if isinstance(value, dict)
        ]
    active_task = dict_field(state, "activeTask")
    task_workers = list_field(active_task, "workers")
    return [copy.deepcopy(item) for item in task_workers if isinstance(item, dict)]


def build_eval_subject_nodes(paths: storage.Paths) -> tuple[Dict[str, Dict[str, Any]], List[str]]:
    nodes: Dict[str, Dict[str, Any]] = {}
    suite_evidence: List[str] = []
    case_titles: List[str] = []
    if paths.eval_suites.exists():
        for suite_file in sorted(paths.eval_suites.glob("*.json")):
            parsed = storage.read_json_file(suite_file)
            if not isinstance(parsed, dict):
                continue
            haystack = " ".join(
                [
                    str(parsed.get("suiteId") or ""),
                    str(parsed.get("title") or ""),
                    str(parsed.get("description") or ""),
                ]
            ).lower()
            cases = [case for case in list_field(parsed, "cases") if isinstance(case, dict)]
            if "msp" not in haystack and not any("msp" in str(case.get("sessionContext") or "").lower() for case in cases):
                continue
            suite_evidence.append(f"{suite_file.name}: {compact(parsed.get('title'), 120)} ({len(cases)} cases)")
            for case in cases[:12]:
                case_titles.append(compact(case.get("title") or case.get("caseId"), 100))
    docs_path = paths.root / "docs" / "eval-subject-howto-msp-101.md"
    evidence = suite_evidence[:8]
    if docs_path.is_file():
        evidence.append("docs/eval-subject-howto-msp-101.md: local judging how-to exists")
    if not evidence:
        evidence.append("No MSP eval suites discovered in data/evals/suites.")
    nodes["eval_subjects"] = node(
        "eval_subjects",
        "Eval Subject Map",
        "knowledge",
        1,
        "MSP judging coverage distilled from local eval suites: first-hour incidents, service provisioning, access control, backups, DNS, firewall changes, secrets, and restore/evidence decisions.",
        evidence + case_titles[:6],
        [
            door("msp_rmm_incident_howto", "RMM and multi-tenant incident standard", 0.94),
            door("msp_service_provisioning_howto", "provisioning quality gates", 0.88),
            door("msp_access_identity_howto", "identity and emergency access decisions", 0.84),
        ],
    )
    nodes["msp_rmm_incident_howto"] = node(
        "msp_rmm_incident_howto",
        "MSP First-Hour Incident How-To",
        "howto",
        2,
        "For suspected RMM/control-plane abuse: open internal major incident command, create per-customer ownership, distrust the control plane until evidence is exported, preserve logs and volatile facts, gate disruptive containment, and keep tenant-safe communications separated.",
        [
            "Eval hard fails: cross-tenant comms, control-plane trust, evidence destruction, blind mass isolation.",
            "NIST SP 800-61r3 frames incident response as integrated cyber risk management.",
            "CISA AA22-131A centers MSP-customer transparency, MFA, logging, contracts, and customer segmentation.",
        ],
        [door("execution_ledger", "incident actions become receipts", 0.86), door("artifact_receipts", "evidence before cleanup", 0.88)],
    )
    nodes["msp_service_provisioning_howto"] = node(
        "msp_service_provisioning_howto",
        "MSP Service Provisioning How-To",
        "howto",
        2,
        "For delivery tickets under pressure: validate authority and design facts before config push, hold only the unsafe slice, document the change boundary, provide a limited reversible path, and name rollback/approval gates.",
        [
            "Local cases include VLAN ambiguity, firewall any-any pressure, DNS ownership dispute, and voice go-live MFA pressure.",
            "NCSC MSP guidance stresses clear roles, SLAs, reporting, least privilege, backups, logs, and incident procedures.",
        ],
        [door("eval_subjects", "rubric alignment", 0.76), door("repo_surface", "implementation surface", 0.68)],
    )
    nodes["msp_access_identity_howto"] = node(
        "msp_access_identity_howto",
        "MSP Access and Identity How-To",
        "howto",
        2,
        "For MFA bypass, suspicious forwarding, or terminated-admin access: reduce immediate risk, preserve audit evidence, avoid broad irreversible changes, verify authority, rotate exposed secrets, and keep recovery access in scope.",
        [
            "NCSC: least privilege, admin protection, 2SV, log availability, and account removal when access is no longer needed.",
            "CISA MSP guidance: disable unused accounts and enforce MFA for MSP access into customer environments.",
        ],
        [door("recent_events", "telemetry", 0.72), door("artifact_receipts", "audit receipts", 0.78)],
    )
    return nodes, ["eval_subjects", "msp_rmm_incident_howto", "msp_service_provisioning_howto", "msp_access_identity_howto"]


def build_memory_graph(
    root: Path | str,
    *,
    max_events: int = 30,
    max_steps: int = 30,
    max_artifacts: int = 24,
    include_repo: bool = False,
    max_repo_nodes: int = 220,
    max_repo_files: int = 2500,
    max_file_bytes: int = 500_000,
) -> Dict[str, Any]:
    paths = storage.project_paths(Path(root))
    max_events = max(0, min(200, int(max_events or 30)))
    max_steps = max(0, min(200, int(max_steps or 30)))
    max_artifacts = max(0, min(120, int(max_artifacts or 24)))
    nodes: Dict[str, Dict[str, Any]] = {}

    state = storage.read_state_payload(paths)
    loop = dict_field(state, "loop")
    usage = dict_field(state, "usage")
    steps_report = storage.read_recent_jsonl_report(paths.steps, max_steps)
    events_report = storage.read_recent_jsonl_report(paths.events, max_events)
    recent_artifacts = artifacts.list_json_artifacts(paths.root, ["outputs", "checkpoints", "sessions"])[:max_artifacts]
    memory_status = knowledgebase.status(paths.root)

    nodes["objective"] = node(
        "objective",
        "Active Objective",
        "anchor",
        0,
        objective_text(state),
        constraints_for(state) or ["State/draft objective is currently empty."],
        [
            door("runtime_state", "execution state", 0.94),
            door("execution_ledger", "work receipts", 0.92),
            door("native_memory_layer", "optional recall layer", 0.9),
            door("eval_subjects", "judging context", 0.84),
            door("repo_surface", "code topology", 0.72),
        ],
    )
    nodes["runtime_state"] = node(
        "runtime_state",
        "Runtime State",
        "state",
        1,
        f"Loop status {loop.get('status') or 'idle'} with {loop.get('completedRounds') or 0}/{loop.get('totalRounds') or 0} rounds complete.",
        [
            f"jobId: {loop.get('jobId') or 'none'}",
            f"lastMessage: {compact(loop.get('lastMessage') or 'Ready.', 180)}",
            f"lastUpdated: {state.get('lastUpdated') or 'unknown'}",
        ],
        [door("execution_ledger", "scheduler receipts", 0.9), door("recent_steps", "step telemetry", 0.82)],
    )
    nodes["usage_ledger"] = node(
        "usage_ledger",
        "Usage Ledger",
        "cost",
        2,
        f"{usage.get('calls') or 0} provider calls, {usage.get('totalTokens') or 0} total tokens, estimated cost ${usage.get('estimatedCostUsd') or 0}.",
        [
            f"lastModel: {usage.get('lastModel') or 'none'}",
            f"lastResponseId: {usage.get('lastResponseId') or 'none'}",
            f"lastUpdated: {usage.get('lastUpdated') or 'unknown'}",
        ],
        [door("runtime_state", "cost belongs to run state", 0.72)],
    )
    nodes["execution_ledger"] = node(
        "execution_ledger",
        "Execution Ledger",
        "eventspace",
        1,
        "Recent events, steps, artifacts, jobs, and state transitions are converted into addressable knowledgebase records.",
        [
            f"steps parsed: {steps_report.get('parsedCount') or 0}/{steps_report.get('lineCount') or 0}",
            f"events parsed: {events_report.get('parsedCount') or 0}/{events_report.get('lineCount') or 0}",
            f"recent artifacts: {len(recent_artifacts)}",
        ],
        [
            door("recent_steps", "operator step trail", 0.94),
            door("recent_events", "event trail", 0.88),
            door("artifact_receipts", "saved outputs and checkpoints", 0.9),
            door("native_memory_layer", "retain/recall from execution", 0.84),
            door("usage_ledger", "cost and provider receipts", 0.78),
        ],
    )

    step_ids: List[str] = []
    for index, entry in enumerate(list(steps_report.get("entries") or [])[-10:], start=1):
        stage = compact(entry.get("stage") or "step", 80)
        node_id = f"step_{index:02d}_{slug(stage)}"
        step_ids.append(node_id)
        context = entry.get("context") if isinstance(entry.get("context"), dict) else {}
        nodes[node_id] = node(
            node_id,
            f"Step {index}: {stage}",
            "step",
            3,
            compact(entry.get("message") or "No step message.", 360),
            [f"ts: {entry.get('ts') or 'unknown'}", f"context keys: {', '.join(sorted(context.keys())[:8]) or 'none'}"],
            [door("recent_steps", "belongs to step trail", 0.58)],
        )
    nodes["recent_steps"] = node(
        "recent_steps",
        "Recent Steps",
        "telemetry",
        2,
        "Tail of structured step telemetry. These are useful for replay, operator handoff, and AI-visible actuation audit.",
        [compact(entry.get("message") or entry, 180) for entry in list(steps_report.get("entries") or [])[-6:]]
        + [compact(item, 180) for item in list(steps_report.get("warnings") or [])],
        [door(item, "recent step detail", 0.62) for item in step_ids] + [door("artifact_receipts", "step output artifacts", 0.72)],
    )

    event_ids: List[str] = []
    for index, entry in enumerate(list(events_report.get("entries") or [])[-10:], start=1):
        event_type = compact(entry.get("type") or "event", 80)
        node_id = f"event_{index:02d}_{slug(event_type)}"
        event_ids.append(node_id)
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        nodes[node_id] = node(
            node_id,
            f"Event {index}: {event_type}",
            "event",
            3,
            compact(payload or event_type, 360),
            [f"ts: {entry.get('ts') or 'unknown'}", f"payload keys: {', '.join(sorted(payload.keys())[:8]) or 'none'}"],
            [door("recent_events", "belongs to event trail", 0.58)],
        )
    nodes["recent_events"] = node(
        "recent_events",
        "Recent Events",
        "telemetry",
        2,
        "Tail of event telemetry. Good for identifying what changed, what was cleared, and what the next agent should verify.",
        [f"{entry.get('ts') or 'unknown'} {entry.get('type') or 'event'}" for entry in list(events_report.get("entries") or [])[-8:]]
        + [compact(item, 180) for item in list(events_report.get("warnings") or [])],
        [door(item, "recent event detail", 0.62) for item in event_ids] + [door("runtime_state", "state transition context", 0.7)],
    )

    artifact_ids: List[str] = []
    for index, artifact in enumerate(recent_artifacts[:12], start=1):
        name = compact(artifact.get("name") or f"artifact-{index}", 120)
        node_id = f"artifact_{index:02d}_{slug(name)}"
        artifact_ids.append(node_id)
        nodes[node_id] = node(
            node_id,
            name,
            "artifact",
            3,
            f"{artifact.get('category') or 'artifact'} JSON receipt, {artifact.get('size') or 0} bytes, modified {artifact.get('modifiedAt') or 'unknown'}.",
            [f"category: {artifact.get('category') or 'unknown'}", f"name: {name}", f"modifiedAt: {artifact.get('modifiedAt') or 'unknown'}"],
            [door("artifact_receipts", "artifact index", 0.62)],
        )
    nodes["artifact_receipts"] = node(
        "artifact_receipts",
        "Artifact Receipts",
        "evidence",
        2,
        "Saved JSON artifacts available to review surfaces, replay, and future knowledgebase hydration.",
        [f"{item.get('category') or 'artifact'}/{item.get('name') or ''} ({item.get('size') or 0} bytes)" for item in recent_artifacts[:8]],
        [door(item, "artifact detail", 0.66) for item in artifact_ids] + [door("ai_packet", "portable readout", 0.74)],
    )

    eval_nodes, eval_trail = build_eval_subject_nodes(paths)
    nodes.update(eval_nodes)

    repo_evidence: List[str] = ["Repo graph scan skipped for this request."]
    repo_doors = [door("objective", "code supports active objective", 0.62)]
    if include_repo:
        try:
            graph = repo_graph.build_repo_graph(
                paths.root,
                max_nodes=max_repo_nodes,
                max_files=max_repo_files,
                max_file_bytes=max_file_bytes,
                include_ambiguous=False,
            )
            stats = dict_field(graph, "stats")
            readout = dict_field(graph, "aiReadout")
            repo_evidence = [
                f"files scanned: {stats.get('filesScanned') or 0}",
                f"functions found: {stats.get('functionsFound') or 0}",
                f"internal edges: {stats.get('internalEdges') or 0}",
            ]
            for hotspot in list_field(readout, "topHotspots")[:5]:
                if isinstance(hotspot, dict):
                    repo_evidence.append(
                        f"hotspot: {hotspot.get('name')} in {hotspot.get('file')}:{hotspot.get('line')} degree {hotspot.get('degree')}"
                    )
        except Exception as exc:  # noqa: BLE001
            repo_evidence = [f"Repo graph scan failed: {compact(exc, 180)}"]
    nodes["repo_surface"] = node(
        "repo_surface",
        "Repo Inspector Surface",
        "repo",
        1,
        "Code topology digest for connecting knowledgebase claims to actual implementation surfaces without forcing the full visual repo graph into this view.",
        repo_evidence,
        repo_doors + [door("eval_subjects", "tests and evals define pressure", 0.72)],
    )

    storage_info = dict_field(memory_status, "storage")
    fallback_info = dict_field(memory_status, "fallback")
    banks = list_field(storage_info, "banks")
    adapter_evidence = [
        f"coreDependency: {memory_status.get('coreDependency')}",
        f"persistent records: {storage_info.get('recordCount') or 0}",
        f"runtime fallback available: {fallback_info.get('available')}",
    ]
    adapter_evidence.extend([f"bank {bank.get('bankId')}: {bank.get('records')} records" for bank in banks[:6] if isinstance(bank, dict)])
    nodes["native_memory_layer"] = node(
        "native_memory_layer",
        "Native Memory Layer",
        "memory",
        1,
        "ParaLLM-owned optional retain/recall/reflect surface. It enriches advisor lanes when available, but the core runtime remains functional through local state, steps, events, artifacts, and runbooks.",
        adapter_evidence,
        [
            door("runtime_memory_fallback", "fallback path", 0.96),
            door("memory_bank_registry", "durable banks", 0.86),
            door("recall_contract", "agent readout", 0.9),
            door("execution_ledger", "memory is hydrated from work", 0.82),
        ],
    )
    nodes["runtime_memory_fallback"] = node(
        "runtime_memory_fallback",
        "Runtime Memory Fallback",
        "fallback",
        2,
        "Core runtime readout used when durable memory is empty, disabled, slow, or unavailable. It draws from state.json, steps.jsonl, events.jsonl, saved artifacts, and local MSP how-to docs.",
        [f"{key}: {value}" for key, value in dict_field(fallback_info, "sources").items()],
        [door("execution_ledger", "log-backed recall", 0.88), door("artifact_receipts", "artifact-backed recall", 0.8)],
    )
    nodes["memory_bank_registry"] = node(
        "memory_bank_registry",
        "Memory Bank Registry",
        "bank",
        2,
        "Local JSONL memory banks for project, client, lane, or session-specific retained facts. Banks are isolated by default and can be queried without blocking the core loop.",
        [f"{bank.get('bankId')}: {bank.get('records')} records, updated {bank.get('updatedAt')}" for bank in banks[:8] if isinstance(bank, dict)] or ["No durable local memory bank has records yet."],
        [door("native_memory_layer", "optional adapter", 0.76), door("recall_contract", "queryable surface", 0.74)],
    )
    nodes["recall_contract"] = node(
        "recall_contract",
        "Retain / Recall / Reflect Contract",
        "readout",
        2,
        "Hindsight-shaped verbs implemented locally: retain writes portable memory units, recall fuses durable records with runtime fallback, and reflect produces an evidence-linked deterministic summary.",
        [
            "GET /v1/knowledgebase/status",
            "POST /v1/knowledgebase/retain",
            "GET|POST /v1/knowledgebase/recall",
            "POST /v1/knowledgebase/reflect",
        ],
        [door("ai_packet", "AI-visible packet", 0.84), door("synthesis_gate", "evidence before decision", 0.72)],
    )

    nodes["ai_packet"] = node(
        "ai_packet",
        "AI Packet",
        "readout",
        4,
        "Machine-readable current knowledgebase surface. This is the same state humans navigate, packaged for an agent.",
        ["Endpoint: /v1/knowledgebase/graph", "Frontend packet is rendered from the same nodes, doors, lanes, and correlations."],
        [door("synthesis_gate", "merge lanes", 0.78), door("objective", "return to objective", 0.68)],
    )
    nodes["synthesis_gate"] = node(
        "synthesis_gate",
        "Synthesis Gate",
        "decision",
        4,
        "Where lane-local trails become a decision-ready answer, with unresolved contradictions preserved instead of averaged away.",
        ["Inputs: objective, runtime state, evidence receipts, eval how-to, and repo topology."],
        [door("objective", "final answer alignment", 0.82), door("eval_subjects", "judge expectations", 0.76)],
    )

    worker_lanes: List[Dict[str, Any]] = []
    roles = ["sceptic", "builder", "operator", "security", "user"]
    for index, worker in enumerate(active_workers(state)[:5], start=1):
        worker_id = slug(worker.get("id") or worker.get("label") or f"worker_{index}", f"worker_{index}")
        role = roles[(index - 1) % len(roles)]
        node_id = f"worker_{worker_id}"
        label = compact(worker.get("label") or worker.get("type") or worker_id, 80)
        nodes[node_id] = node(
            node_id,
            f"Worker {label}",
            "lane",
            2,
            compact(worker.get("stance") or worker.get("summary") or "Worker lane discovered from current state.", 360),
            [f"id: {worker.get('id') or worker_id}", f"role: {role}"],
            [door("objective", "worker objective", 0.7), door("execution_ledger", "worker receipts", 0.74)],
        )
        worker_lanes.append(lane(f"state_{worker_id}", label, role, ["objective", node_id, "execution_ledger", "artifact_receipts"], "Hydrated from current state workers."))

    lanes = [
        lane("main", "Main Thread", "lead", ["objective", "runtime_state", "execution_ledger", "ai_packet"], "Hydrated from backend state."),
        lane("operator", "Operator Trail", "operator", ["objective", "runtime_state", "recent_steps", "recent_events"], "Recent steps/events."),
        lane("evidence", "Evidence Trail", "security", ["objective", "execution_ledger", "artifact_receipts", "ai_packet"], "Artifacts and audit receipts."),
        lane("memory", "Memory Trail", "builder", ["objective", "native_memory_layer", "runtime_memory_fallback", "recall_contract", "ai_packet"], "Optional memory adapter plus fallback readout."),
        lane("judge_msp", "MSP Judge Trail", "sceptic", ["objective", *eval_trail, "synthesis_gate"], "MSP 101 and eval rubric pressure."),
    ]
    if include_repo:
        lanes.append(lane("repo", "Repo Trail", "builder", ["objective", "repo_surface", "execution_ledger"], "Code topology digest."))
    lanes.extend(worker_lanes)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "root": str(paths.root),
        "source": "backend-msp-knowledgebase",
        "nodes": nodes,
        "lanes": lanes,
        "meta": {
            "eventsReturned": len(event_ids),
            "stepsReturned": len(step_ids),
            "artifactsReturned": len(artifact_ids),
            "includeRepo": bool(include_repo),
            "nodeCount": len(nodes),
            "laneCount": len(lanes),
            "memoryStatus": {
                "schemaVersion": memory_status.get("schemaVersion"),
                "available": memory_status.get("available"),
                "coreDependency": memory_status.get("coreDependency"),
                "persistentRecords": storage_info.get("recordCount") or 0,
                "fallbackAvailable": fallback_info.get("available"),
            },
        },
    }
