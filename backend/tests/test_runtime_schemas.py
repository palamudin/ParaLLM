from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.engine import LoopRuntime


def assert_strict_schema_objects_require_all_properties(testcase: unittest.TestCase, schema: dict, path: str = "$") -> None:
    if not isinstance(schema, dict):
        return
    if schema.get("type") == "object" and schema.get("additionalProperties") is False:
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        testcase.assertEqual(
            set(properties.keys()),
            required,
            f"{path} must require every declared property for strict provider schemas",
        )
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            for property_name, property_schema in value.items():
                assert_strict_schema_objects_require_all_properties(testcase, property_schema, f"{path}.{property_name}")
        elif key == "items":
            assert_strict_schema_objects_require_all_properties(testcase, value, f"{path}[]")


class RuntimeSchemaTests(unittest.TestCase):
    def test_compact_commander_review_schema_requires_all_declared_properties(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(Path(tmpdir))
            schema = runtime.commander_review_schema_for_mode(compact=True)

        properties = set((schema.get("properties") or {}).keys())
        required = set(schema.get("required") or [])

        self.assertEqual(properties, required)

    def test_strict_runtime_schemas_require_declared_properties(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(Path(tmpdir))
            schemas = [
                runtime.commander_schema(),
                runtime.worker_schema(),
                runtime.commander_review_schema_for_mode(compact=False),
                runtime.commander_review_schema_for_mode(compact=True),
                runtime.summary_schema_for_mode(compact=False),
                runtime.summary_schema_for_mode(compact=True),
                runtime.direct_baseline_schema(),
            ]

        for schema in schemas:
            assert_strict_schema_objects_require_all_properties(self, schema)


if __name__ == "__main__":
    unittest.main()
