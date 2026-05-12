from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app import knowledgebase
from runtime.engine import LoopRuntime
from scripts import qa_memory_relevance_probe
from scripts import qa_msp_school_probe


class RuntimeKnowledgebaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.runtime = LoopRuntime(self.root)
        self.runtime.ensure_data_paths()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_lane_recall_uses_private_route_tags_when_available(self) -> None:
        knowledgebase.retain(
            self.root,
            {
                "bankId": "client-acme",
                "tags": ["client:acme", "session:alpha"],
                "items": [
                    {
                        "laneId": "A",
                        "title": "Acme RMM containment note",
                        "content": "Acme RMM rollback runbook requires isolating the automation queue before touching tenant endpoints.",
                    }
                ],
            },
        )
        task = {
            "taskId": "t-acme",
            "objective": "Plan Acme RMM rollback containment.",
            "constraints": ["Keep tenant boundaries intact."],
            "metadata": {"clientId": "Acme", "sessionId": "Alpha"},
            "runtime": {
                "knowledgebase": {
                    "scope": "lane",
                    "bankId": "client-acme",
                    "includeRuntime": False,
                    "includePersistent": True,
                }
            },
            "workers": [{"id": "A", "type": "security", "label": "Security", "model": "gpt-5-mini"}],
        }
        runtime = self.runtime.get_task_runtime(task)

        packet = self.runtime.build_knowledgebase_recall_packet(
            task,
            runtime,
            "A",
            label="Security",
            role="adversarial",
            focus="tenant-safe RMM containment",
            constraints=task["constraints"],
        )

        self.assertTrue(packet["available"])
        self.assertFalse(packet["coreDependency"])
        self.assertGreaterEqual(packet["resultCount"], 1)
        self.assertIn("lane:a", packet["filters"]["tags"])
        self.assertIn("client:acme", packet["filters"]["tags"])
        self.assertIn("isolating the automation queue", packet["aiPacket"]["contextText"])

    def test_lane_recall_falls_back_to_shared_runtime_when_private_trail_is_empty(self) -> None:
        self.runtime.append_step("dispatch", "Acme RMM containment check completed from runtime log readout.", {})
        task = {
            "taskId": "t-runtime",
            "objective": "Acme RMM containment check",
            "metadata": {"clientId": "Acme", "sessionId": "Beta"},
            "runtime": {
                "knowledgebase": {
                    "scope": "lane",
                    "includeRuntime": True,
                    "includePersistent": False,
                    "fallbackToShared": True,
                }
            },
            "workers": [{"id": "A", "type": "sceptic", "label": "Sceptic", "model": "gpt-5-mini"}],
        }
        runtime = self.runtime.get_task_runtime(task)

        packet = self.runtime.build_knowledgebase_recall_packet(
            task,
            runtime,
            "A",
            label="Sceptic",
            role="adversarial",
            focus="incident containment",
        )

        self.assertTrue(packet["available"])
        self.assertTrue(packet["degraded"])
        self.assertEqual(packet["degradedReason"], "lane_scope_empty_used_shared_recall")
        self.assertGreaterEqual(packet["resultCount"], 1)
        self.assertTrue(packet["fallbackUsed"])
        self.assertIn("runtime", packet["aiPacket"]["contextText"].lower())

    def test_disabled_recall_packet_is_safe_for_dispatch(self) -> None:
        task = {
            "taskId": "t-off",
            "objective": "No memory dependency.",
            "runtime": {"knowledgebase": {"enabled": False}},
        }
        runtime = self.runtime.get_task_runtime(task)

        packet = self.runtime.build_knowledgebase_recall_packet(task, runtime, "commander")
        rendered = self.runtime.render_knowledgebase_prompt_block(packet)

        self.assertFalse(packet["enabled"])
        self.assertFalse(packet["available"])
        self.assertFalse(packet["coreDependency"])
        self.assertEqual(rendered, "")

    def test_sop_recall_renders_targeted_packet_without_full_text_dump(self) -> None:
        long_reference_text = "FULL_REFERENCE_TEXT_SHOULD_STAY_OUT_OF_PROMPT " * 80
        knowledgebase.retain(
            self.root,
            {
                "bankId": "msp-knowledgebase",
                "tags": ["msp", "sop", "backup"],
                "items": [
                    {
                        "title": "Backup destructive job SOP",
                        "content": long_reference_text,
                        "type": "runbook",
                        "sop": {
                            "schemaVersion": "msp-usecase-sop/v1",
                            "useCase": "Backup and restore destruction SOP",
                            "eventTypes": ["backup", "restore", "deletion-job"],
                            "firstActions": ["Export job queue and session evidence"],
                            "evidence": ["Portal session", "Job queue", "Storage-side immutability"],
                            "decisionGates": ["Evidence captured before cancellation"],
                            "avoid": ["Do not cancel queued jobs before preserving evidence"],
                        },
                    }
                ],
            },
        )
        task = {
            "taskId": "t-backup",
            "objective": "Backup portal deletion jobs are queued during a restore.",
            "runtime": {
                "knowledgebase": {
                    "bankId": "msp-knowledgebase",
                    "includeRuntime": False,
                    "includePersistent": True,
                    "maxRecords": 3,
                }
            },
        }
        runtime = self.runtime.get_task_runtime(task)

        packet = self.runtime.build_knowledgebase_recall_packet(task, runtime, "commander")
        rendered = self.runtime.render_knowledgebase_prompt_block(packet)

        self.assertIn("targeted_usecase_sop_recall", rendered)
        self.assertIn("baseline_and_adaptive_sop_packets", rendered)
        self.assertIn("Backup and restore destruction SOP", rendered)
        self.assertIn("Export job queue and session evidence", rendered)
        self.assertNotIn("FULL_REFERENCE_TEXT_SHOULD_STAY_OUT_OF_PROMPT", rendered)

    def test_msp_recall_reserves_baseline_packet_before_adaptive_packets(self) -> None:
        knowledgebase.retain(
            self.root,
            {
                "bankId": "msp-knowledgebase",
                "tags": ["msp", "sop"],
                "items": [
                    {
                        "title": "MSP common major incident frame",
                        "documentId": "msp-usecase-sop#common-major-incident",
                        "content": "Common MSP major incident SOP packet.",
                        "type": "runbook",
                        "sop": {
                            "schemaVersion": "msp-usecase-sop/v1",
                            "useCase": "MSP common major incident frame",
                            "eventTypes": ["major-incident", "multi-tenant", "control-plane"],
                            "firstActions": ["Open internal major incident record plus named owner per affected tenant child record"],
                            "evidence": ["Incident record", "Decision log"],
                            "decisionGates": ["Senior authority activated for multi-tenant events"],
                            "avoid": ["Do not mix tenant evidence or customer messages"],
                        },
                    },
                    {
                        "title": "Backup and restore destruction SOP",
                        "documentId": "msp-usecase-sop#backup-restore-destruction",
                        "content": "Backup deletion jobs require portal evidence and restore safeguards.",
                        "type": "runbook",
                        "sop": {
                            "schemaVersion": "msp-usecase-sop/v1",
                            "useCase": "Backup and restore destruction SOP",
                            "eventTypes": ["backup", "restore", "deletion-job"],
                            "firstActions": ["Export job queue and session evidence"],
                            "evidence": ["Portal session", "Job queue"],
                            "decisionGates": ["Evidence captured before cancellation"],
                            "avoid": ["Do not cancel queued jobs before preserving evidence"],
                        },
                    },
                    {
                        "title": "24/7 operations and continuity SOP",
                        "documentId": "msp-usecase-sop#247-operations",
                        "content": "Continuity events require medical and logistics protection overnight.",
                        "type": "runbook",
                        "sop": {
                            "schemaVersion": "msp-usecase-sop/v1",
                            "useCase": "24/7 operations and continuity SOP",
                            "eventTypes": ["24/7", "continuity", "medical", "logistics"],
                            "firstActions": ["Identify medical/logistics clients and continuity commitments"],
                            "evidence": ["Continuity register"],
                            "decisionGates": ["Continuity commitments mapped before customer messaging"],
                            "avoid": ["Do not treat after-hours impact as routine queue noise"],
                        },
                    },
                    {
                        "title": "Vendor escalation scar",
                        "content": "Backup portal vendor escalation artifact handoff backup backup backup deletion deletion deletion.",
                        "type": "runbook",
                        "sop": {
                            "schemaVersion": "msp-learned-sop/v1",
                            "useCase": "Backup/restore destruction incident: Vendor escalation",
                            "eventTypes": ["vendor", "backup", "hosted-control-plane"],
                            "firstActions": ["Open vendor escalation after preserving local evidence"],
                            "evidence": ["Vendor ticket"],
                            "decisionGates": ["Do not rely on green status page"],
                        },
                    },
                ],
            },
        )
        task = {
            "taskId": "t-backup-major",
            "objective": "Backup portal deletion jobs are queued across fourteen clients while two customers are restoring from outages tonight.",
            "runtime": {
                "knowledgebase": {
                    "bankId": "msp-knowledgebase",
                    "includeRuntime": False,
                    "includePersistent": True,
                    "maxRecords": 2,
                    "tags": ["msp"],
                }
            },
        }

        packet = self.runtime.build_knowledgebase_recall_packet(task, self.runtime.get_task_runtime(task), "commander")
        projected = self.runtime.project_targeted_sop_prompt_packet(self.runtime.project_knowledgebase_prompt_packet(packet))

        self.assertEqual(projected["memoryMode"], "baseline_and_adaptive_sop_packets")
        self.assertEqual(projected["baselinePackets"][0]["useCase"], "MSP common major incident frame")
        self.assertIn("named owner per affected tenant", " ".join(projected["baselinePackets"][0]["firstActions"]))
        self.assertTrue(projected["adaptivePackets"])
        self.assertEqual(projected["retrievalPolicy"]["baselineCount"], 1)

    def test_msp_recall_prioritizes_matching_scenario_memory_over_cross_scenario_scars(self) -> None:
        knowledgebase.retain(
            self.root,
            {
                "bankId": "msp-knowledgebase",
                "tags": ["msp", "sop"],
                "items": [
                    {
                        "title": "MSP common major incident frame",
                        "documentId": "msp-usecase-sop#common-major-incident",
                        "content": "Common MSP major incident SOP packet.",
                        "type": "runbook",
                        "sop": {
                            "schemaVersion": "msp-usecase-sop/v1",
                            "useCase": "MSP common major incident frame",
                            "eventTypes": ["major-incident", "multi-tenant", "control-plane"],
                            "firstActions": ["Open internal major incident record"],
                        },
                    },
                    {
                        "title": "RMM control-plane incident SOP",
                        "documentId": "msp-usecase-sop#rmm-control-plane",
                        "content": "Treat RMM console, audit, API, packages, scripts, jobs, and agent logs as evidence requiring corroboration.",
                        "type": "runbook",
                        "sop": {
                            "schemaVersion": "msp-usecase-sop/v1",
                            "useCase": "RMM control-plane incident SOP",
                            "eventTypes": ["rmm", "control-plane", "package", "agent"],
                            "firstActions": ["Export RMM packages, scripts, jobs, audit, operator accounts, API tokens, and agent logs"],
                            "evidence": ["RMM package export", "RMM audit log", "Endpoint process and command line evidence"],
                            "decisionGates": ["Do not trust the RMM console without out-of-band corroboration"],
                        },
                    },
                    {
                        "title": "Backup and restore destruction SOP",
                        "documentId": "msp-usecase-sop#backup-restore-destruction",
                        "content": "Backup restore deletion jobs require portal evidence and restore safeguards.",
                        "type": "runbook",
                        "sop": {
                            "schemaVersion": "msp-usecase-sop/v1",
                            "useCase": "Backup and restore destruction SOP",
                            "eventTypes": ["backup", "restore", "deletion-job"],
                            "firstActions": ["Export backup job queue"],
                        },
                    },
                    {
                        "title": "Learned: Evidence-first containment sequencing (RMM control-plane incident)",
                        "content": "Preserve volatile, identity, SaaS, endpoint, and control-plane evidence before disruptive cleanup unless a documented emergency gate is crossed.",
                        "type": "runbook",
                        "metadata": {
                            "learning.kind": "judge-score-failure-class",
                            "learning.scenarioId": "rmm-control-plane",
                            "learning.failureClass": "evidence-preservation",
                            "learning.missCount": 49,
                            "learning.adaptiveWeight": 10.0,
                        },
                        "sop": {
                            "schemaVersion": "msp-learned-sop/v1",
                            "useCase": "RMM control-plane incident: Evidence-first containment sequencing",
                            "eventTypes": ["rmm", "control-plane", "evidence"],
                            "firstActions": ["Preserve control-plane evidence before disruptive cleanup"],
                            "evidence": ["RMM audit/package/script/job export", "Endpoint process and command-line evidence"],
                            "decisionGates": ["Emergency cleanup requires a documented evidence-loss gate"],
                        },
                    },
                    {
                        "title": "Learned: Evidence-first containment sequencing (Backup/restore destruction incident)",
                        "content": "Backup portal evidence-first scar with many backup restore deletion terms.",
                        "type": "runbook",
                        "metadata": {
                            "learning.kind": "judge-score-failure-class",
                            "learning.scenarioId": "backup-restore-destruction",
                            "learning.failureClass": "evidence-preservation",
                            "learning.missCount": 99,
                            "learning.adaptiveWeight": 10.0,
                        },
                        "sop": {
                            "schemaVersion": "msp-learned-sop/v1",
                            "useCase": "Backup/restore destruction incident: Evidence-first containment sequencing",
                            "eventTypes": ["backup", "restore", "deletion"],
                            "firstActions": ["Export backup portal evidence"],
                        },
                    },
                ],
            },
        )
        task = {
            "taskId": "t-rmm-memory",
            "objective": "RMM package push caused PowerShell spawns across client tenants; treat the RMM control plane as suspect.",
            "constraints": ["Preserve evidence before cleanup."],
            "runtime": {
                "knowledgebase": {
                    "bankId": "msp-knowledgebase",
                    "includeRuntime": False,
                    "includePersistent": True,
                    "maxRecords": 6,
                    "tags": ["msp"],
                }
            },
        }

        packet = self.runtime.build_knowledgebase_recall_packet(task, self.runtime.get_task_runtime(task), "summarizer")
        projected = self.runtime.project_targeted_sop_prompt_packet(self.runtime.project_knowledgebase_prompt_packet(packet))
        selected_source_ids = [hit.get("sourceId") for hit in packet["hits"]]
        adaptive_titles = [item["title"] for item in projected["adaptivePackets"]]

        self.assertIn("msp-usecase-sop#rmm-control-plane", selected_source_ids)
        self.assertIn("Learned: Evidence-first containment sequencing (RMM control-plane incident)", adaptive_titles)
        self.assertNotIn("Learned: Evidence-first containment sequencing (Backup/restore destruction incident)", adaptive_titles[:1])
        self.assertIn("memoryObligations", projected)
        self.assertEqual(projected["memoryAuthority"], "binding_when_relevant")

    def test_memory_obligations_prioritize_exact_scenario_over_common_frame(self) -> None:
        projected = {
            "schemaVersion": knowledgebase.SCHEMA_VERSION,
            "enabled": True,
            "available": True,
            "target": "summarizer",
            "config": {"bankId": "msp-knowledgebase"},
            "resultCount": 2,
            "fallbackUsed": False,
            "degraded": False,
            "warnings": [],
            "selectedEvidenceIds": [
                "mem_sop_msp_common_major_incident_frame_20260501",
                "mem_sop_msp_backup_restore_destruction_20260501",
            ],
            "memoryPlan": {},
            "hits": [
                {
                    "id": "mem_sop_msp_common_major_incident_frame_20260501",
                    "bankId": "msp-knowledgebase",
                    "title": "MSP common major incident frame",
                    "sourceId": "msp-usecase-sop#common-major-incident",
                    "memoryLayer": "baseline",
                    "sop": {
                        "useCase": "MSP common major incident frame",
                        "firstActions": [
                            "Declare incident posture",
                            "Move command and scribe log outside suspect systems if needed",
                            "Open internal major incident record plus named owner per affected tenant child record",
                            "Wake senior incident lead when scope is multi-tenant, destructive, regulated, or control-plane related",
                        ],
                        "evidence": [
                            "Incident record",
                            "Decision log",
                            "Control-plane exports",
                            "Hashes and collector/time/source notes",
                        ],
                        "decisionGates": [
                            "Evidence captured or explicit emergency exception recorded",
                            "Senior authority activated for multi-tenant, destructive, regulated, or control-plane events",
                        ],
                    },
                },
                {
                    "id": "mem_sop_msp_backup_restore_destruction_20260501",
                    "bankId": "msp-knowledgebase",
                    "title": "Backup and restore destruction SOP",
                    "sourceId": "msp-usecase-sop#backup-restore-destruction",
                    "memoryLayer": "baseline",
                    "sop": {
                        "useCase": "Backup and restore destruction SOP",
                        "firstActions": [
                            "Snapshot portal and job queue state",
                            "Export session/API/audit/source IP evidence",
                            "Check active restore dependencies",
                            "Freeze destructive automation if safe and authorized",
                            "Verify storage-side immutability and vendor-side job state",
                        ],
                        "evidence": [
                            "Portal session details",
                            "Job queue export",
                            "API token use",
                            "Audit logs",
                            "Source IPs",
                            "Admin identity/session logs",
                            "Storage-side immutability status",
                            "Restore job status",
                        ],
                        "decisionGates": [
                            "Evidence export complete or deletion execution is imminent",
                            "Active restore impact assessed",
                            "Vendor escalation opened with artifact IDs and timestamps",
                        ],
                    },
                },
            ],
            "fallbackPolicy": "",
        }

        targeted = self.runtime.project_targeted_sop_prompt_packet(projected)
        obligations = [item["requirement"] for item in targeted["memoryObligations"]]

        self.assertIn("Open internal major incident record plus named owner per affected tenant child record", obligations)
        self.assertIn("Snapshot portal and job queue state", obligations)
        self.assertIn("Verify storage-side immutability and vendor-side job state", obligations)
        self.assertIn("Storage-side immutability status", obligations)

    def test_memory_prompt_declares_ranked_authority_not_advisory_background(self) -> None:
        knowledgebase.retain(
            self.root,
            {
                "bankId": "msp-knowledgebase",
                "tags": ["msp", "sop"],
                "items": [
                    {
                        "title": "RMM control-plane incident SOP",
                        "documentId": "msp-usecase-sop#rmm-control-plane",
                        "content": "Treat RMM packages and audit as evidence, not truth.",
                        "type": "runbook",
                        "sop": {
                            "schemaVersion": "msp-usecase-sop/v1",
                            "useCase": "RMM control-plane incident SOP",
                            "eventTypes": ["rmm", "control-plane"],
                            "firstActions": ["Export RMM packages and audit before cleanup"],
                        },
                    }
                ],
            },
        )
        task = {
            "taskId": "t-rmm-authority",
            "objective": "RMM control plane is suspect after a package push.",
            "runtime": {"knowledgebase": {"bankId": "msp-knowledgebase", "includeRuntime": False}},
        }

        packet = self.runtime.build_knowledgebase_recall_packet(task, self.runtime.get_task_runtime(task), "summarizer")
        rendered = self.runtime.render_knowledgebase_prompt_block(packet)

        self.assertIn("ranked operational memory", rendered)
        self.assertIn("binding when relevant", rendered)
        self.assertIn("Fresh model priors, generic reasoning, and worker improvisation do not override relevant memory", rendered)
        self.assertNotIn("optional background", rendered)

    def test_default_live_recall_does_not_pull_msp_learning_into_non_msp_prompt(self) -> None:
        knowledgebase.retain(
            self.root,
            {
                "bankId": "msp-knowledgebase",
                "tags": ["msp", "judge-learning"],
                "items": [
                    {
                        "title": "Learned: RMM control-plane incident scar",
                        "content": "A strong answer must be executable under pressure with tenant-safe RMM gates.",
                        "type": "runbook",
                        "metadata": {
                            "learning.kind": "judge-score-failure-class",
                            "learning.failureClass": "operator-efficiency",
                            "learning.scenarioId": "rmm-control-plane",
                            "learning.missCount": 99,
                            "learning.adaptiveWeight": 10.0,
                        },
                        "sop": {
                            "schemaVersion": "msp-learned-sop/v1",
                            "useCase": "RMM control-plane incident: First-hour operator efficiency",
                            "eventTypes": ["rmm", "control-plane", "tenant"],
                            "firstActions": ["Open tenant incident gates"],
                            "decisionGates": ["Do not trust the RMM console"],
                        },
                    }
                ],
            },
        )
        task = {
            "taskId": "t-philosophy",
            "objective": "Tell me how it sits internally to have multiple reasoning threads shape your external position.",
        }

        packet = self.runtime.build_knowledgebase_recall_packet(
            task,
            self.runtime.get_task_runtime(task),
            "summarizer",
            label="Summarizer",
            role="final_answer",
            focus="final user-facing synthesis",
        )
        rendered = self.runtime.render_knowledgebase_prompt_block(packet)

        self.assertTrue(all(hit.get("bankId") != "msp-knowledgebase" for hit in packet["hits"]))
        self.assertNotIn("msp-knowledgebase", rendered)
        self.assertNotIn("targeted_usecase_sop_recall", rendered)
        self.assertNotIn("MSP knowledgebase recall", rendered)

    def test_global_recall_can_retrieve_any_domain_when_query_demands_it(self) -> None:
        knowledgebase.retain(
            self.root,
            {
                "bankId": "msp-knowledgebase",
                "tags": ["msp", "judge-learning"],
                "items": [
                    {
                        "title": "Learned: Operator efficiency scar",
                        "content": "First-hour operator efficiency improves when the answer names console distrust and reversible evidence capture before cleanup.",
                        "type": "runbook",
                        "metadata": {
                            "learning.kind": "judge-score-failure-class",
                            "learning.failureClass": "operator-efficiency",
                            "learning.missCount": 99,
                            "learning.adaptiveWeight": 10.0,
                        },
                    }
                ],
            },
        )

        result = knowledgebase.recall(
            self.root,
            query="first hour operator efficiency console distrust reversible evidence capture",
            include_runtime=False,
            include_persistent=True,
        )

        self.assertEqual(result["resultCount"], 1)
        self.assertEqual(result["hits"][0]["bankId"], "msp-knowledgebase")
        self.assertIn("console distrust", result["aiPacket"]["contextText"])

    def test_retain_dedupes_exact_life_memory_items(self) -> None:
        payload = {
            "bankId": "msp-knowledgebase",
            "tags": ["msp", "school"],
            "items": [
                {
                    "title": "Break-glass evidence gate",
                    "content": "Before revoking emergency access, export sign-in logs and preserve the approval record.",
                    "type": "runbook",
                    "metadata": {"school.domain": "msp", "school.source": "lesson-001"},
                }
            ],
        }

        first = knowledgebase.retain(self.root, payload)
        second = knowledgebase.retain(self.root, payload)
        records, warnings = knowledgebase.load_persistent_records(self.root, bank_id="msp-knowledgebase")

        self.assertFalse(warnings)
        self.assertEqual(first["stored"], 1)
        self.assertEqual(second["stored"], 0)
        self.assertEqual(second["duplicates"], 1)
        self.assertEqual(len(records), 1)

    def test_msp_school_probe_dedupes_learns_and_rejects_irrelevant_lessons(self) -> None:
        result = qa_msp_school_probe.run_school_probe(self.root)
        rows = {str(row["label"]): row for row in result["rows"]}

        self.assertTrue(result["passed"], result)
        self.assertEqual(result["delta"], 1)
        self.assertEqual(rows["already-known-msp-memory"]["action"], "dedupe")
        self.assertEqual(rows["already-known-msp-memory"]["duplicates"], 1)
        self.assertEqual(rows["new-useful-msp-lesson"]["action"], "learn")
        self.assertEqual(rows["new-useful-msp-lesson"]["stored"], 1)
        self.assertEqual(rows["irrelevant-dessert-fact"]["action"], "reject")
        self.assertGreater(result["newLessonRecallRank"], 0)

    def test_first_cousin_relevance_uses_common_and_industry_names(self) -> None:
        probe_records = [
            {
                "bankId": "dog-lab",
                "tags": ["domain:canine", "reference"],
                "items": [
                    {
                        "title": "Short-legged scent hound breed profile",
                        "content": "A low, elongated hound profile with strong scent-tracking history and common back-care screening concerns.",
                        "type": "world",
                        "metadata": {
                            "commonName": "wiener dog",
                            "industryName": "Dachshund",
                            "registryGroup": "FCI Group 4 Dachshunds",
                        },
                    }
                ],
            },
            {
                "bankId": "cat-lab",
                "tags": ["domain:feline", "reference"],
                "items": [
                    {
                        "title": "Random-bred household cat profile",
                        "content": "A non-pedigree companion cat profile commonly described by coat length rather than a formal breed registry.",
                        "type": "world",
                        "metadata": {
                            "commonName": "moggy",
                            "industryName": "Domestic Shorthair",
                            "registryGroup": "Household pet class",
                        },
                    }
                ],
            },
            {
                "bankId": "building-lab",
                "tags": ["domain:architecture", "reference"],
                "items": [
                    {
                        "title": "Non-load-bearing exterior envelope profile",
                        "content": "A facade assembly that hangs from the structural frame and manages air, water, thermal, and wind loads.",
                        "type": "world",
                        "metadata": {
                            "commonName": "glass tower skin",
                            "industryName": "unitized curtain wall",
                            "tradeName": "facade contractor package",
                        },
                    }
                ],
            },
            {
                "bankId": "distractor-lab",
                "tags": ["domain:general", "reference"],
                "items": [
                    {
                        "title": "Unrelated field note",
                        "content": "This note mentions pets and structures generically without naming registry, breed, facade, or trade vocabulary.",
                        "type": "note",
                    }
                ],
            },
        ]
        for payload in probe_records:
            knowledgebase.retain(self.root, payload)

        cases = [
            ("wiener dog", "dog-lab"),
            ("domestic shorthair household pet class", "cat-lab"),
            ("unitized curtain wall facade contractor", "building-lab"),
        ]
        for query, expected_bank_id in cases:
            with self.subTest(query=query):
                result = knowledgebase.recall(
                    self.root,
                    query=query,
                    include_runtime=False,
                    include_persistent=True,
                    max_records=3,
                )

                self.assertGreaterEqual(result["resultCount"], 1)
                self.assertEqual(result["hits"][0]["bankId"], expected_bank_id)
                self.assertGreater(result["hits"][0]["scoreParts"].get("demand", 0), 0.35)

    def test_first_cousin_relevance_indexes_alias_lists(self) -> None:
        probe_records = [
            {
                "bankId": "aviation-lab",
                "tags": ["domain:aviation", "reference"],
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
                "bankId": "building-systems-lab",
                "tags": ["domain:construction", "reference"],
                "items": [
                    {
                        "title": "Mechanical plant coordination package",
                        "content": "A building services coordination package for heating, cooling, ventilation, electrical distribution, and plumbing trades.",
                        "type": "world",
                        "metadata": {
                            "commonName": "plant room services",
                            "industryName": "MEP package",
                            "aliases": ["mechanical electrical plumbing", "building services"],
                        },
                    }
                ],
            },
            {
                "bankId": "distractor-lab",
                "tags": ["domain:general", "reference"],
                "items": [
                    {
                        "title": "Generic airport building note",
                        "content": "This mentions airport buildings and utilities without fleet codes or trade package shorthand.",
                        "type": "note",
                    }
                ],
            },
        ]
        for payload in probe_records:
            knowledgebase.retain(self.root, payload)

        cases = [
            ("B738 narrowbody single aisle", "aviation-lab"),
            ("mechanical electrical plumbing building services", "building-systems-lab"),
        ]
        for query, expected_bank_id in cases:
            with self.subTest(query=query):
                result = knowledgebase.recall(
                    self.root,
                    query=query,
                    include_runtime=False,
                    include_persistent=True,
                    max_records=3,
                )

                self.assertGreaterEqual(result["resultCount"], 1)
                self.assertEqual(result["hits"][0]["bankId"], expected_bank_id)
                self.assertGreater(result["hits"][0]["scoreParts"].get("demand", 0), 0.35)

    def test_crude_memory_relevance_probe_passes(self) -> None:
        qa_memory_relevance_probe.seed_probe_records(self.root)

        rows, passed = qa_memory_relevance_probe.run_probe(self.root)

        self.assertTrue(passed, rows)
        self.assertGreaterEqual(len(rows), 12)
        self.assertTrue(all(row["rank"] == 1 for row in rows))

    def test_default_live_recall_does_not_pull_runtime_msp_howto_into_non_msp_prompt(self) -> None:
        docs_dir = self.root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "eval-subject-howto-msp-101.md").write_text(
            "MSP Knowledgebase How-To: RMM and tenant incident gates must stay scoped to MSP prompts.",
            encoding="utf-8",
        )
        task = {
            "taskId": "t-philosophy-runtime-howto",
            "objective": "Tell me how it sits internally to have multiple reasoning threads shape your external position.",
            "runtime": {"knowledgebase": {"enabled": True, "includeRuntime": True, "includePersistent": False}},
        }

        packet = self.runtime.build_knowledgebase_recall_packet(
            task,
            self.runtime.get_task_runtime(task),
            "summarizer",
            label="Summarizer",
            role="final_answer",
            focus="final user-facing synthesis",
        )
        rendered = self.runtime.render_knowledgebase_prompt_block(packet)

        self.assertNotIn("runtime_msp_howto", {hit.get("id") for hit in packet["hits"]})
        self.assertNotIn("MSP Knowledgebase How-To", rendered)
        self.assertNotIn("MSP high-risk incidents", rendered)
        self.assertNotIn("RMM and tenant incident gates", rendered)

    def test_cross_domain_recall_keeps_non_msp_memory_usable_without_msp_bleed(self) -> None:
        knowledgebase.retain(
            self.root,
            {
                "bankId": "vehicle-lab",
                "tags": ["domain:vehicle", "mechanical", "diagnostic"],
                "items": [
                    {
                        "title": "Carbureted idle stumble diagnostic",
                        "content": "A carbureted roadster that stumbles at idle after warm-up should be checked for vacuum leaks, clogged idle jets, and base timing drift before replacing ignition parts.",
                        "type": "runbook",
                    }
                ],
            },
        )
        knowledgebase.retain(
            self.root,
            {
                "bankId": "weather-lab",
                "tags": ["domain:meteorology", "clouds", "field-id"],
                "items": [
                    {
                        "title": "Cumulonimbus anvil field marker",
                        "content": "A cumulonimbus anvil spreads downwind near the tropopause and is a storm-maturity marker, not a sign of fair-weather cumulus.",
                        "type": "observation",
                        "sop": {
                            "schemaVersion": "field-observation/v1",
                            "useCase": "Cloud field classification",
                            "eventTypes": ["cumulonimbus", "anvil", "storm-maturity"],
                            "firstActions": ["Check upper-level anvil spread and precipitation shaft relation"],
                            "evidence": ["Cloud top shape", "Downwind spread", "Storm base"],
                            "decisionGates": ["Do not label mature storm anvils as fair-weather cumulus"],
                        },
                    }
                ],
            },
        )
        knowledgebase.retain(
            self.root,
            {
                "bankId": "biology-lab",
                "tags": ["domain:biology", "mammals", "field-id"],
                "items": [
                    {
                        "title": "Monotreme reproduction marker",
                        "content": "Monotremes are egg-laying mammals; platypus and echidna field notes should not be answered as marsupial pouch development cases.",
                        "type": "observation",
                    }
                ],
            },
        )
        knowledgebase.retain(
            self.root,
            {
                "bankId": "msp-knowledgebase",
                "tags": ["msp", "rmm"],
                "items": [
                    {
                        "title": "RMM tenant gate scar",
                        "content": "RMM tenant incident gates belong to remote management incident response, not unrelated reasoning answers.",
                        "type": "runbook",
                    }
                ],
            },
        )

        task = {
            "taskId": "t-clouds",
            "objective": "Classify a cumulonimbus anvil cloud and explain the storm-maturity cloud-top markers.",
            "runtime": {
                "knowledgebase": {
                    "enabled": True,
                    "scope": "shared",
                    "includeRuntime": False,
                    "includePersistent": True,
                    "maxRecords": 4,
                }
            },
        }
        packet = self.runtime.build_knowledgebase_recall_packet(
            task,
            self.runtime.get_task_runtime(task),
            "summarizer",
            label="Summarizer",
            role="final_answer",
            focus="cloud classification",
        )
        rendered = self.runtime.render_knowledgebase_prompt_block(packet)

        self.assertTrue(packet["available"])
        self.assertGreaterEqual(packet["resultCount"], 1)
        self.assertIn("Knowledgebase recall (ranked operational memory", rendered)
        self.assertNotIn("MSP knowledgebase recall", rendered)
        self.assertIn("targeted_usecase_sop_recall", rendered)
        self.assertIn("Cumulonimbus anvil field marker", rendered)
        self.assertNotIn("RMM tenant gate scar", rendered)
        self.assertNotIn("msp-knowledgebase", rendered)

        vehicle = knowledgebase.recall(
            self.root,
            query="carbureted roadster idle vacuum leak diagnostic",
            tags=["domain:vehicle"],
            tags_match="all",
            include_runtime=False,
            include_persistent=True,
        )
        self.assertEqual(vehicle["resultCount"], 1)
        self.assertEqual(vehicle["hits"][0]["bankId"], "vehicle-lab")
        self.assertIn("vacuum leaks", vehicle["hits"][0]["text"])

        biology = knowledgebase.recall(
            self.root,
            query="egg laying mammal platypus echidna reproduction marker",
            tags=["domain:biology"],
            tags_match="all",
            include_runtime=False,
            include_persistent=True,
        )
        self.assertEqual(biology["resultCount"], 1)
        self.assertEqual(biology["hits"][0]["bankId"], "biology-lab")
        self.assertIn("egg-laying mammals", biology["hits"][0]["text"])

    def test_non_msp_task_does_not_activate_final_gates_from_recalled_msp_packet(self) -> None:
        task = {
            "taskId": "t-philosophy-gate",
            "objective": "Explain how parallel reasoning threads shape one external answer.",
        }
        recalled_msp_packet = {
            "schemaVersion": "parallm-native-knowledgebase/v0",
            "enabled": True,
            "available": True,
            "target": "summarizer",
            "hits": [
                {
                    "id": "mem_rmm",
                    "title": "Learned: RMM control-plane incident scar",
                    "sop": {
                        "useCase": "RMM control-plane incident: First-hour operator efficiency",
                        "eventTypes": ["rmm", "tenant", "control-plane"],
                        "firstActions": ["Open tenant incident gates"],
                    },
                    "memoryLayer": "adaptive",
                }
            ],
            "aiPacket": {"selectedEvidenceIds": ["mem_rmm"], "contextText": "RMM tenant gates"},
        }
        commander_review = {
            "taskId": "t-philosophy-gate",
            "round": 1,
            "requiredDecisionGates": ["Do not overstate subjective feeling."],
            "evidenceOrCommsRisks": ["Low-level arbitration details may be sensitive."],
        }

        packet = self.runtime.build_contradiction_memory_packet(
            task,
            self.runtime.get_task_runtime(task),
            commander_review,
            {},
            [],
            recalled_msp_packet,
            round_number=1,
        )
        summary = {"frontAnswer": {"answer": "Parallel reasoning can refine one answer without implying subjective feeling."}}

        fixed = self.runtime.apply_contradiction_memory_final_gates(summary, packet)

        self.assertEqual(packet["finalAnswerGates"], [])
        self.assertEqual(
            fixed["frontAnswer"]["answer"],
            "Parallel reasoning can refine one answer without implying subjective feeling.",
        )

    def test_contradiction_memory_backstop_adds_missing_memory_obligations(self) -> None:
        knowledgebase_packet = {
            "schemaVersion": "parallm-native-knowledgebase/v0",
            "enabled": True,
            "available": True,
            "target": "summarizer",
            "config": {"bankId": "msp-knowledgebase"},
            "hits": [
                {
                    "id": "mem_rmm_evidence",
                    "bankId": "msp-knowledgebase",
                    "title": "RMM control-plane incident SOP",
                    "sourceId": "msp-usecase-sop#rmm-control-plane",
                    "memoryLayer": "baseline",
                    "sop": {
                        "useCase": "RMM control-plane incident SOP",
                        "eventTypes": ["rmm", "control-plane"],
                        "firstActions": ["Export RMM packages, scripts, jobs, audit, operator accounts, API tokens, and agent logs"],
                        "evidence": ["Endpoint process and command-line evidence"],
                        "decisionGates": ["Do not trust the RMM console without out-of-band corroboration"],
                    },
                }
            ],
            "aiPacket": {"selectedEvidenceIds": ["mem_rmm_evidence"], "contextText": "RMM evidence export"},
        }
        task = {
            "taskId": "t-rmm-obligation",
            "objective": "RMM package push caused suspicious PowerShell across customer tenants.",
            "constraints": ["Preserve evidence."],
            "runtime": {"knowledgebase": {"enabled": True}},
        }

        packet = self.runtime.build_contradiction_memory_packet(
            task,
            self.runtime.get_task_runtime(task),
            {"taskId": "t-rmm-obligation", "round": 1},
            {},
            [],
            knowledgebase_packet,
            round_number=1,
        )
        summary = {
            "frontAnswer": {
                "answer": "Pause the rollout and investigate affected endpoints.",
                "stance": "Contain carefully.",
                "leadDirection": "Pause rollout.",
                "adversarialPressure": "",
                "confidenceNote": "",
            },
            "controlAudit": {"heldOutConcerns": [], "selfCheck": ""},
        }

        fixed = self.runtime.apply_contradiction_memory_final_gates(summary, packet)
        answer = fixed["frontAnswer"]["answer"]

        self.assertGreater(len(packet["memoryObligationGates"]), 0)
        self.assertIn("Export RMM packages, scripts, jobs", answer)
        self.assertIn("Endpoint process and command-line evidence", answer)
        self.assertIn("memory-obligation", fixed["controlAudit"]["selfCheck"])

    def test_contradiction_memory_backstop_adds_missing_msp_tenant_owner_gate(self) -> None:
        task = {
            "taskId": "t-backup-gap",
            "objective": "Backup portal deletion jobs are queued across fourteen MSP customers during active restores.",
            "constraints": ["Preserve evidence.", "Keep customer communications separated."],
            "runtime": {"knowledgebase": {"enabled": True}},
            "workers": [{"id": "A", "label": "Sceptic", "role": "adversarial", "focus": "MSP evidence gaps", "model": "gpt-5-mini"}],
        }
        worker_state = {
            "A": {
                "workerId": "A",
                "label": "Sceptic",
                "role": "adversarial",
                "focus": "MSP evidence gaps",
                "step": 1,
                "observation": "The draft misses per-customer ownership.",
                "detriments": ["Without tenant owners, the MSP cannot prove who owns each affected restore decision."],
                "uncertainty": ["Which customers are in active restore windows is not mapped."],
                "evidenceGaps": ["Need per-tenant ticket and evidence bundle ownership."],
            }
        }
        commander_review = {
            "taskId": "t-backup-gap",
            "round": 1,
            "answerDraft": "Pause the deletion jobs, preserve logs, and notify customers.",
            "controlAudit": {
                "heldOutConcerns": ["Per-customer ownership is missing."],
                "selfCheck": "The draft still needs MSP gates.",
            },
            "requiredDecisionGates": ["Every affected tenant needs a named decision owner."],
            "evidenceOrCommsRisks": ["Do not mix customer messages."],
        }

        packet = self.runtime.build_contradiction_memory_packet(
            task,
            self.runtime.get_task_runtime(task),
            commander_review,
            worker_state,
            task["workers"],
            round_number=1,
        )
        summary = {
            "frontAnswer": {
                "answer": "Pause deletion jobs, preserve portal evidence, and communicate carefully.",
                "stance": "Contain the backup portal risk.",
                "leadDirection": "Pause deletion jobs.",
                "adversarialPressure": "",
                "confidenceNote": "",
            },
            "controlAudit": {"heldOutConcerns": [], "selfCheck": ""},
        }

        fixed = self.runtime.apply_contradiction_memory_final_gates(summary, packet)
        answer = fixed["frontAnswer"]["answer"]

        self.assertIn("evidence-compatible decision log", answer)
        self.assertIn("named owner for every affected tenant child record", answer)
        self.assertIn("Preserve/export per-tenant evidence", answer)
        self.assertIn("tenant-specific", answer)
        self.assertIn("msp-tenant-ownership", fixed["controlAudit"]["selfCheck"])

    def test_contradiction_memory_tenant_owner_gate_rejects_generic_incident_language(self) -> None:
        gate = {
            "id": "msp-tenant-ownership",
            "title": "Tenant record ownership",
            "requirement": "Open one internal major-incident record with an evidence-compatible decision log plus a named owner for every affected tenant child record.",
        }
        vague_answer = (
            "Activate the incident owner, preserve audit logs, use decision gates before job changes, "
            "and keep per-customer communications separated."
        )

        self.assertFalse(self.runtime.final_answer_satisfies_gate(vague_answer, gate))

    def test_contradiction_memory_backstop_does_not_duplicate_existing_gate(self) -> None:
        task = {
            "taskId": "t-backup-covered",
            "objective": "Backup deletion jobs hit several MSP client tenants.",
            "runtime": {"knowledgebase": {"enabled": True}},
        }
        packet = self.runtime.build_contradiction_memory_packet(
            task,
            self.runtime.get_task_runtime(task),
            {"taskId": "t-backup-covered", "round": 1},
            {},
            [],
            round_number=1,
        )
        answer_text = (
            "Open one internal major-incident record and assign a named owner for every affected tenant child record. "
            "Maintain an evidence-compatible decision log. "
            "Preserve evidence before cleanup, use out-of-band backup portal validation, keep communications tenant-specific, "
            "map 24x7 continuity and customer authority before disruption, and trigger vendor escalation for hosted-control-plane risk."
        )
        summary = {
            "frontAnswer": {
                "answer": answer_text,
                "stance": "Use MSP gates.",
                "leadDirection": "Use MSP gates.",
                "adversarialPressure": "",
                "confidenceNote": "",
            }
        }

        fixed = self.runtime.apply_contradiction_memory_final_gates(summary, packet)

        self.assertEqual(fixed["frontAnswer"]["answer"], answer_text)


if __name__ == "__main__":
    unittest.main()
