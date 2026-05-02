from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app import knowledgebase
from runtime.engine import LoopRuntime


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
        self.assertIn('"coreDependency": false', rendered)

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


if __name__ == "__main__":
    unittest.main()
