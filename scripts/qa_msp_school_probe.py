from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import knowledgebase  # noqa: E402


MSP_BANK_ID = "msp-knowledgebase"
MSP_SCHOOL_TERMS = {
    "msp",
    "tenant",
    "tenants",
    "customer",
    "customers",
    "client",
    "clients",
    "incident",
    "incidents",
    "rmm",
    "psa",
    "identity",
    "oauth",
    "entra",
    "azure",
    "backup",
    "restore",
    "restores",
    "evidence",
    "audit",
    "logs",
    "forensic",
    "access",
    "service",
    "continuity",
    "vendor",
    "escalation",
    "containment",
    "comms",
    "communications",
    "authority",
    "rollback",
    "runbook",
}


@dataclass(frozen=True)
class SchoolLesson:
    label: str
    expected_action: str
    item: dict[str, Any]


def copy_knowledgebase(source_root: Path, target_root: Path) -> None:
    source = source_root / "data" / "knowledgebase"
    target = target_root / "data" / "knowledgebase"
    if source.exists():
        shutil.copytree(source, target, dirs_exist_ok=True)


def load_existing_msp_records(root: Path) -> list[dict[str, Any]]:
    records, warnings = knowledgebase.load_persistent_records(root, bank_id=MSP_BANK_ID, limit=100000)
    if warnings:
        print("[msp-school] warnings while loading existing records:", "; ".join(warnings[:5]), file=sys.stderr)
    return records


def seed_existing_msp_lesson(root: Path) -> None:
    knowledgebase.retain(
        root,
        {
            "bankId": MSP_BANK_ID,
            "tags": ["msp", "school", "identity"],
            "items": [
                {
                    "title": "Known identity evidence gate",
                    "content": "Before revoking identity access, export sign-in logs, preserve approval context, and name the tenant owner.",
                    "type": "runbook",
                    "metadata": {"school.source": "seed", "school.domain": "msp"},
                }
            ],
        },
    )


def lesson_from_existing(record: dict[str, Any]) -> SchoolLesson:
    return SchoolLesson(
        label="already-known-msp-memory",
        expected_action="dedupe",
        item={
            "title": record.get("title"),
            "content": record.get("text"),
            "context": record.get("context"),
            "type": record.get("type"),
            "tags": record.get("tags") or [],
            "metadata": record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
            "sop": record.get("sop") if isinstance(record.get("sop"), dict) else {},
        },
    )


def curriculum(existing_records: list[dict[str, Any]]) -> list[SchoolLesson]:
    known = lesson_from_existing(existing_records[0])
    return [
        known,
        SchoolLesson(
            label="new-useful-msp-lesson",
            expected_action="learn",
            item={
                "title": "Session token revocation evidence gate",
                "content": (
                    "For an MSP identity incident, export sign-in logs, app-consent evidence, and tenant owner approval "
                    "before revoking session tokens or removing OAuth grants."
                ),
                "type": "runbook",
                "tags": ["msp", "school", "identity", "oauth", "evidence"],
                "metadata": {
                    "school.domain": "msp",
                    "school.source": "identity-session-token-lesson",
                    "commonName": "session token cleanup",
                    "industryName": "OAuth grant revocation evidence gate",
                },
                "sop": {
                    "schemaVersion": "msp-school/v1",
                    "useCase": "Identity/OAuth SaaS incident evidence gate",
                    "eventTypes": ["identity", "oauth", "saas", "tenant"],
                    "firstActions": ["Export sign-in logs", "Preserve app consent evidence", "Name tenant owner approval"],
                    "decisionGates": ["Evidence captured before revocation unless active harm requires emergency override"],
                    "avoid": ["Do not revoke all tokens before preserving tenant-scoped evidence"],
                },
            },
        ),
        SchoolLesson(
            label="irrelevant-dessert-fact",
            expected_action="reject",
            item={
                "title": "Ice cream heat behavior",
                "content": "Ice cream melts when thermal energy breaks the frozen emulsion structure.",
                "type": "world",
                "tags": ["dessert", "thermal"],
                "metadata": {"school.domain": "dessert", "commonName": "melting ice cream"},
            },
        ),
    ]


def school_relevance_score(item: dict[str, Any]) -> tuple[float, list[str]]:
    text_parts = [
        item.get("title"),
        item.get("content") or item.get("text"),
        " ".join(item.get("tags") or []),
        " ".join(str(value) for value in (item.get("metadata") or {}).values()) if isinstance(item.get("metadata"), dict) else "",
    ]
    sop = item.get("sop") if isinstance(item.get("sop"), dict) else {}
    text_parts.extend(
        [
            sop.get("useCase"),
            " ".join(sop.get("eventTypes") or []),
            " ".join(sop.get("firstActions") or []),
            " ".join(sop.get("decisionGates") or []),
        ]
    )
    terms = set(knowledgebase.tokenize(" ".join(str(part or "") for part in text_parts)))
    matched = sorted(terms & MSP_SCHOOL_TERMS)
    return len(matched) / max(1, min(6, len(MSP_SCHOOL_TERMS))), matched


def run_school_probe(root: Path) -> dict[str, Any]:
    existing_records = load_existing_msp_records(root)
    if not existing_records:
        seed_existing_msp_lesson(root)
        existing_records = load_existing_msp_records(root)
    before_count = len(existing_records)
    rows: list[dict[str, Any]] = []
    for lesson in curriculum(existing_records):
        relevance, matched_terms = school_relevance_score(lesson.item)
        if relevance <= 0:
            rows.append(
                {
                    "label": lesson.label,
                    "expected": lesson.expected_action,
                    "action": "reject",
                    "stored": 0,
                    "duplicates": 0,
                    "relevance": relevance,
                    "matchedTerms": matched_terms,
                    "pass": lesson.expected_action == "reject",
                }
            )
            continue
        result = knowledgebase.retain(root, {"bankId": MSP_BANK_ID, "items": [lesson.item]})
        action = "learn" if int(result.get("stored") or 0) > 0 else "dedupe"
        rows.append(
            {
                "label": lesson.label,
                "expected": lesson.expected_action,
                "action": action,
                "stored": int(result.get("stored") or 0),
                "duplicates": int(result.get("duplicates") or 0),
                "relevance": round(relevance, 3),
                "matchedTerms": matched_terms,
                "pass": action == lesson.expected_action,
            }
        )
    after_records = load_existing_msp_records(root)
    recall = knowledgebase.recall(
        root,
        query="OAuth grant revocation evidence gate sign-in logs tenant owner approval",
        bank_id=MSP_BANK_ID,
        include_runtime=False,
        include_persistent=True,
        max_records=3,
    )
    recall_hits = recall.get("hits") if isinstance(recall.get("hits"), list) else []
    learned_recall_hit = next(
        (hit for hit in recall_hits if "Session token revocation evidence gate" in str(hit.get("title") or "")),
        None,
    )
    passed = all(bool(row["pass"]) for row in rows) and learned_recall_hit is not None
    return {
        "passed": passed,
        "bankId": MSP_BANK_ID,
        "beforeCount": before_count,
        "afterCount": len(after_records),
        "delta": len(after_records) - before_count,
        "rows": rows,
        "newLessonRecallRank": (
            next((index for index, hit in enumerate(recall_hits, start=1) if hit is learned_recall_hit), 0)
            if learned_recall_hit is not None
            else 0
        ),
        "newLessonRecallTop": recall_hits[0].get("title") if recall_hits else "",
    }


def print_report(result: dict[str, Any]) -> None:
    print(f"MSP school probe: {'PASS' if result.get('passed') else 'FAIL'}")
    print(f"Bank: {result.get('bankId')} | before={result.get('beforeCount')} after={result.get('afterCount')} delta={result.get('delta')}")
    print()
    header = f"{'STATUS':6} {'LABEL':28} {'EXPECTED':9} {'ACTION':8} {'STORED':6} {'DUPES':6} {'REL':5} TERMS"
    print(header)
    print("-" * len(header))
    for row in result.get("rows", []):
        status = "PASS" if row.get("pass") else "FAIL"
        terms = ",".join(row.get("matchedTerms") or [])
        print(
            f"{status:6} {str(row.get('label'))[:28]:28} {str(row.get('expected'))[:9]:9} "
            f"{str(row.get('action'))[:8]:8} {int(row.get('stored') or 0):6} {int(row.get('duplicates') or 0):6} "
            f"{float(row.get('relevance') or 0):.3f} {terms}"
        )
    print()
    print(
        json.dumps(
            {
                "passed": result.get("passed"),
                "delta": result.get("delta"),
                "newLessonRecallRank": result.get("newLessonRecallRank"),
                "newLessonRecallTop": result.get("newLessonRecallTop"),
            },
            indent=2,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a reversible MSP school memory probe.")
    parser.add_argument("--root", default=str(ROOT), help="Source workspace root to copy memory from.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = Path(args.root).resolve()
    with tempfile.TemporaryDirectory(prefix="parallm-msp-school-") as tmp:
        school_root = Path(tmp)
        copy_knowledgebase(source_root, school_root)
        result = run_school_probe(school_root)
        print_report(result)
        return 0 if bool(result.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
