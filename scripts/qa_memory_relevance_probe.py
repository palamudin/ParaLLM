from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import knowledgebase  # noqa: E402


@dataclass(frozen=True)
class ProbeCase:
    query: str
    expected_bank: str
    label: str


def seed_probe_records(root: Path) -> None:
    payloads: list[dict[str, Any]] = [
        {
            "bankId": "dog-lab",
            "tags": ["domain:canine", "registry"],
            "items": [
                {
                    "title": "Short-legged scent hound breed profile",
                    "content": "A low, elongated hound profile with strong scent-tracking history and common back-care screening concerns.",
                    "type": "world",
                    "metadata": {
                        "commonName": "wiener dog",
                        "industryName": "Dachshund",
                        "registryGroup": "FCI Group 4 Dachshunds",
                        "aliases": ["sausage dog", "teckel"],
                    },
                },
                {
                    "title": "Herding dog registry profile",
                    "content": "A high-drive herding breed profile used in stock work and obedience trial contexts.",
                    "type": "world",
                    "metadata": {
                        "commonName": "collie",
                        "industryName": "Border Collie",
                        "registryGroup": "AKC Herding Group",
                        "aliases": ["stock dog", "sheepdog"],
                    },
                },
            ],
        },
        {
            "bankId": "cat-lab",
            "tags": ["domain:feline", "registry"],
            "items": [
                {
                    "title": "Random-bred household cat profile",
                    "content": "A non-pedigree companion cat profile commonly described by coat length rather than a formal breed registry.",
                    "type": "world",
                    "metadata": {
                        "commonName": "moggy",
                        "industryName": "Domestic Shorthair",
                        "registryGroup": "Household pet class",
                        "aliases": ["DSH", "house cat"],
                    },
                },
                {
                    "title": "Pointed longhair breed profile",
                    "content": "A large semi-longhair cat profile with colorpoint markings and blue eyes in registry language.",
                    "type": "world",
                    "metadata": {
                        "commonName": "floppy cat",
                        "industryName": "Ragdoll",
                        "registryGroup": "Pedigree longhair",
                        "aliases": ["colorpoint companion cat"],
                    },
                },
            ],
        },
        {
            "bankId": "building-envelope-lab",
            "tags": ["domain:architecture", "facade"],
            "items": [
                {
                    "title": "Non-load-bearing exterior envelope profile",
                    "content": "A facade assembly that hangs from the structural frame and manages air, water, thermal, and wind loads.",
                    "type": "world",
                    "metadata": {
                        "commonName": "glass tower skin",
                        "industryName": "unitized curtain wall",
                        "tradeName": "facade contractor package",
                        "aliases": ["curtainwall", "panelized facade"],
                    },
                }
            ],
        },
        {
            "bankId": "building-systems-lab",
            "tags": ["domain:construction", "services"],
            "items": [
                {
                    "title": "Mechanical plant coordination package",
                    "content": "A building services coordination package for heating, cooling, ventilation, electrical distribution, and plumbing trades.",
                    "type": "world",
                    "metadata": {
                        "commonName": "plant room services",
                        "industryName": "MEP package",
                        "tradeName": "building services package",
                        "aliases": ["mechanical electrical plumbing", "services coordination"],
                    },
                }
            ],
        },
        {
            "bankId": "aviation-lab",
            "tags": ["domain:aviation", "fleet"],
            "items": [
                {
                    "title": "Commercial transport category jet profile",
                    "content": "A short-to-medium range passenger jet profile tracked by airline fleet planners and airport stand allocation teams.",
                    "type": "world",
                    "metadata": {
                        "commonName": "737",
                        "industryName": "Boeing 737-800",
                        "aliases": ["B738", "narrowbody", "single aisle"],
                    },
                }
            ],
        },
        {
            "bankId": "weather-lab",
            "tags": ["domain:meteorology", "clouds"],
            "items": [
                {
                    "title": "Anvil storm cloud field marker",
                    "content": "A mature thunderstorm cloud marker with downwind ice-crystal spread near the tropopause.",
                    "type": "observation",
                    "metadata": {
                        "commonName": "thunderhead anvil",
                        "industryName": "cumulonimbus incus",
                        "aliases": ["Cb incus", "anvil cloud"],
                    },
                }
            ],
        },
        {
            "bankId": "msp-lab",
            "tags": ["domain:msp", "operations"],
            "items": [
                {
                    "title": "Remote management incident workflow",
                    "content": "A tenant-safe operational response packet for remote monitoring and management control-plane faults.",
                    "type": "runbook",
                    "metadata": {
                        "commonName": "RMM outage",
                        "industryName": "remote monitoring and management incident",
                        "aliases": ["RMM control plane", "tenant-safe remediation"],
                    },
                }
            ],
        },
        {
            "bankId": "distractor-lab",
            "tags": ["domain:general"],
            "items": [
                {
                    "title": "Generic mixed-domain note",
                    "content": "This note mentions pets, buildings, aircraft, clouds, and operations without using the specific registry, trade, code, or alias names.",
                    "type": "note",
                }
            ],
        },
    ]
    for payload in payloads:
        knowledgebase.retain(root, payload)


def probe_cases() -> list[ProbeCase]:
    return [
        ProbeCase("wiener dog", "dog-lab", "common animal name"),
        ProbeCase("teckel dachshund registry group", "dog-lab", "breed alias plus industry name"),
        ProbeCase("AKC herding sheepdog stock dog", "dog-lab", "registry group plus working alias"),
        ProbeCase("domestic shorthair household pet class", "cat-lab", "cat registry class"),
        ProbeCase("DSH house cat random bred", "cat-lab", "cat acronym alias"),
        ProbeCase("ragdoll colorpoint companion cat", "cat-lab", "near-domain cat breed"),
        ProbeCase("unitized curtain wall facade contractor", "building-envelope-lab", "building envelope trade name"),
        ProbeCase("curtainwall panelized facade", "building-envelope-lab", "architecture shorthand"),
        ProbeCase("mechanical electrical plumbing services coordination", "building-systems-lab", "building systems acronym expansion"),
        ProbeCase("B738 narrowbody single aisle", "aviation-lab", "aircraft IATA/industry shorthand"),
        ProbeCase("cumulonimbus incus anvil cloud", "weather-lab", "weather formal name"),
        ProbeCase("RMM control plane tenant-safe remediation", "msp-lab", "operations acronym alias"),
    ]


def run_probe(root: Path) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    all_passed = True
    for case in probe_cases():
        result = knowledgebase.recall(
            root,
            query=case.query,
            include_runtime=False,
            include_persistent=True,
            max_records=5,
        )
        hits = result.get("hits") if isinstance(result.get("hits"), list) else []
        top = hits[0] if hits else {}
        top_bank = str(top.get("bankId") or "")
        rank = next((index for index, hit in enumerate(hits, start=1) if str(hit.get("bankId") or "") == case.expected_bank), 0)
        passed = top_bank == case.expected_bank
        all_passed = all_passed and passed
        rows.append(
            {
                "label": case.label,
                "query": case.query,
                "expected": case.expected_bank,
                "top": top_bank or "-",
                "rank": rank or "-",
                "demand": (top.get("scoreParts") or {}).get("demand") if isinstance(top.get("scoreParts"), dict) else None,
                "score": top.get("score"),
                "status": "PASS" if passed else "FAIL",
            }
        )
    return rows, all_passed


def print_table(rows: list[dict[str, Any]]) -> None:
    columns = [
        ("status", 6),
        ("label", 36),
        ("query", 48),
        ("expected", 24),
        ("top", 24),
        ("rank", 5),
        ("demand", 8),
        ("score", 8),
    ]
    header = " ".join(name.upper().ljust(width) for name, width in columns)
    print(header)
    print("-" * len(header))
    for row in rows:
        parts = []
        for name, width in columns:
            value = row.get(name)
            if isinstance(value, float):
                text = f"{value:.3f}"
            else:
                text = str(value if value is not None else "-")
            parts.append(text[:width].ljust(width))
        print(" ".join(parts))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="parallm-memory-probe-") as tmp:
        root = Path(tmp)
        seed_probe_records(root)
        rows, all_passed = run_probe(root)
        print_table(rows)
        print()
        print(json.dumps({"passed": all_passed, "caseCount": len(rows)}, indent=2))
        return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
