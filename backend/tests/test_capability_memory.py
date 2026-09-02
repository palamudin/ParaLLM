from __future__ import annotations

import unittest

from backend.app import capability_memory
from deployment.dev import build as native_build


class CapabilityMemoryTests(unittest.TestCase):
    def test_contract_is_machine_readable_and_has_unique_tools(self) -> None:
        contract = capability_memory.load_contract()
        tools = capability_memory.installed_tool_names()

        self.assertEqual(contract["schemaVersion"], capability_memory.SCHEMA_VERSION)
        self.assertEqual(len(tools), len(set(tools)))
        self.assertIn("web_search", tools)
        self.assertIn("local_read_file", tools)
        self.assertIn("db_read", tools)
        self.assertIn("agent_board_post", tools)
        self.assertIn("web_research", capability_memory.runtime_tool_names("python"))
        self.assertIn("source_grade", capability_memory.runtime_tool_names("native"))
        self.assertNotIn("github_read_file", capability_memory.runtime_tool_names("native"))

    def test_new_model_receives_procedural_memory_and_exact_callable_projection(self) -> None:
        block = capability_memory.render_lane_memory(
            target_kind="worker",
            provider="ollama",
            model="brand-new-local-model",
            offered_tools=("web_search", "web_open", "local_read_file"),
            callable_tools=("web_search", "web_open"),
        )

        self.assertIn("PARALLM SYSTEM CAPABILITY MEMORY", block)
        self.assertIn("callable now: web_search, web_open", block)
        self.assertIn("offered by Para but unavailable on this model route: local_read_file", block)

    def test_non_tool_lane_knows_the_body_without_receiving_an_actuator(self) -> None:
        block = capability_memory.render_lane_memory(
            target_kind="summarizer",
            provider="openai",
            model="fresh-model",
        )

        self.assertIn("Owned web research", block)
        self.assertIn("callable now: none", block)
        self.assertIn("no direct tool actuator", block)

    def test_direct_baseline_remains_unmodified(self) -> None:
        instructions = "Answer directly."

        self.assertEqual(
            capability_memory.attach_to_instructions(
                instructions,
                target_kind="direct_baseline",
                provider="openai",
                model="gpt-test",
                offered_tools=("web_search",),
                callable_tools=("web_search",),
            ),
            instructions,
        )

    def test_memory_record_is_protected_runtime_truth(self) -> None:
        record = capability_memory.memory_record()

        self.assertEqual(record["kind"], "procedural_capability")
        self.assertEqual(record["scope"], "system/runtime")
        self.assertEqual(record["authority"], "runtime-contract")
        self.assertEqual(record["confidence"], 1.0)
        self.assertEqual(len(record["contractSha256"]), 64)
        self.assertEqual(len(record["contentSha256"]), 64)

    def test_native_generated_memory_matches_python_memory_byte_for_byte(self) -> None:
        generated = native_build.generate_tool_capability_memory()
        record = capability_memory.memory_record()

        self.assertEqual(generated["contractSha256"], record["contractSha256"])
        self.assertEqual(generated["contentSha256"], record["contentSha256"])
        self.assertEqual(
            generated["nativeTools"],
            len(capability_memory.runtime_tool_names("native")),
        )
        self.assertEqual(
            generated["pythonTools"],
            len(capability_memory.runtime_tool_names("python")),
        )


if __name__ == "__main__":
    unittest.main()
