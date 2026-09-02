from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from backend.app import tool_database
from runtime.engine import LoopRuntime, RuntimeErrorWithCode


class ToolDatabaseTests(unittest.TestCase):
    def test_create_read_update_and_list_with_revision_guard(self) -> None:
        with tempfile.TemporaryDirectory(prefix="parallm-tool-db-") as directory:
            root = Path(directory)
            created = tool_database.write_record(
                root,
                "workspace",
                "vehicle/paint",
                "blue",
                actor="worker_A",
            )
            self.assertEqual(created["revision"], 1)
            self.assertEqual(created["value"], "blue")
            self.assertEqual(len(created["contentSha256"]), 64)

            loaded = tool_database.read_record(root, "workspace", "vehicle/paint")
            self.assertEqual(loaded["value"], "blue")
            self.assertEqual(loaded["createdBy"], "worker_A")

            updated = tool_database.update_record(
                root,
                "workspace",
                "vehicle/paint",
                "green",
                expected_revision=1,
                actor="commander",
            )
            self.assertEqual(updated["revision"], 2)
            self.assertEqual(updated["value"], "green")
            self.assertEqual(updated["updatedBy"], "commander")

            listed = tool_database.list_records(root, "workspace", prefix="vehicle/", limit=5)
            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["records"][0]["key"], "vehicle/paint")
            self.assertEqual(listed["records"][0]["preview"], "green")

            with self.assertRaises(tool_database.ToolDatabaseError) as conflict:
                tool_database.update_record(
                    root,
                    "workspace",
                    "vehicle/paint",
                    "red",
                    expected_revision=1,
                )
            self.assertEqual(conflict.exception.status_code, 409)
            self.assertEqual(
                tool_database.read_record(root, "workspace", "vehicle/paint")["value"],
                "green",
            )

            health = tool_database.status(root)
            self.assertTrue(health["available"])
            self.assertEqual(health["records"], 1)

    def test_create_rejects_overwrite_and_identifiers_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="parallm-tool-db-") as directory:
            root = Path(directory)
            tool_database.write_record(root, "workspace", "one", "first")
            with self.assertRaises(tool_database.ToolDatabaseError) as duplicate:
                tool_database.write_record(root, "workspace", "one", "second")
            self.assertEqual(duplicate.exception.status_code, 409)

            with self.assertRaises(tool_database.ToolDatabaseError):
                tool_database.read_record(root, "../outside", "one")
            with self.assertRaises(tool_database.ToolDatabaseError):
                tool_database.read_record(root, "workspace", "missing")

    def test_runtime_exposes_bounded_database_tools(self) -> None:
        with tempfile.TemporaryDirectory(prefix="parallm-tool-db-") as directory:
            runtime = LoopRuntime(Path(directory))
            config = {"enabled": True, "namespaces": ["workspace"]}
            names = [entry["name"] for entry in runtime.build_database_function_tools(config)]
            self.assertEqual(names, ["db_write", "db_read", "db_update", "db_list"])

            created, create_audit = runtime.execute_database_tool_call(
                "db_write",
                {"namespace": "workspace", "key": "qa/value", "value": "one"},
                config,
            )
            self.assertEqual(created["revision"], 1)
            self.assertEqual(create_audit["sources"], ["db://workspace/qa/value"])

            loaded, _ = runtime.execute_database_tool_call(
                "db_read",
                {"namespace": "workspace", "key": "qa/value"},
                config,
            )
            self.assertEqual(loaded["value"], "one")

            updated, _ = runtime.execute_database_tool_call(
                "db_update",
                {
                    "namespace": "workspace",
                    "key": "qa/value",
                    "value": "two",
                    "expected_revision": 1,
                },
                config,
            )
            self.assertEqual(updated["revision"], 2)

            listed, _ = runtime.execute_database_tool_call(
                "db_list",
                {"namespace": "workspace", "prefix": "qa/"},
                config,
            )
            self.assertEqual(listed["count"], 1)

            with self.assertRaises(RuntimeErrorWithCode) as denied:
                runtime.execute_database_tool_call(
                    "db_read",
                    {"namespace": "other", "key": "qa/value"},
                    config,
                )
            self.assertEqual(denied.exception.status_code, 403)

    def test_openai_tool_loop_can_write_database_record(self) -> None:
        with tempfile.TemporaryDirectory(prefix="parallm-tool-db-") as directory:
            runtime = LoopRuntime(Path(directory))
            config = {"enabled": True, "namespaces": ["workspace"]}
            responses = [
                {
                    "id": "resp_db_1",
                    "status": "completed",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "db_write",
                            "call_id": "call_db_1",
                            "arguments": json.dumps(
                                {"namespace": "workspace", "key": "qa/provider", "value": "persisted"}
                            ),
                        }
                    ],
                },
                {
                    "id": "resp_db_2",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps({"ok": True, "stored": True}),
                                }
                            ],
                        }
                    ],
                },
            ]
            requests = []

            class FakeHandle:
                def __init__(self, payload: dict) -> None:
                    self.payload = payload

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, traceback) -> bool:
                    return False

                def read(self) -> bytes:
                    return json.dumps(self.payload).encode("utf-8")

            def fake_urlopen(request, timeout=0):
                requests.append(json.loads(request.data.decode("utf-8")))
                return FakeHandle(responses.pop(0))

            original_urlopen = urllib.request.urlopen
            urllib.request.urlopen = fake_urlopen
            try:
                result = runtime.invoke_openai_json(
                    api_key="test",
                    model="gpt-5-mini",
                    reasoning_effort="low",
                    instructions="Store the requested record.",
                    input_text="Persist the QA value.",
                    schema_name="qa_database_tool_loop",
                    schema={
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["ok", "stored"],
                        "properties": {
                            "ok": {"type": "boolean"},
                            "stored": {"type": "boolean"},
                        },
                    },
                    max_output_tokens=200,
                    target_kind="worker",
                    tools=runtime.build_database_function_tools(config),
                    tool_choice="auto",
                    function_handlers={
                        "db_write": lambda arguments: runtime.execute_database_tool_call(
                            "db_write", arguments, config
                        )
                    },
                )
            finally:
                urllib.request.urlopen = original_urlopen

            self.assertTrue(result.parsed["stored"])
            self.assertEqual(len(result.executed_tools), 1)
            self.assertEqual(requests[1]["previous_response_id"], "resp_db_1")
            self.assertEqual(requests[1]["input"][0]["type"], "function_call_output")
            self.assertEqual(
                tool_database.read_record(Path(directory), "workspace", "qa/provider")["value"],
                "persisted",
            )


if __name__ == "__main__":
    unittest.main()
