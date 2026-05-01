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


if __name__ == "__main__":
    unittest.main()
