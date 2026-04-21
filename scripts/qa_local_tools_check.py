from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.engine import LoopRuntime, RuntimeErrorWithCode


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    runtime = LoopRuntime(REPO_ROOT)

    list_result, _ = runtime.execute_local_file_tool_call(
        "local_list_dir",
        {"path": "api", "max_entries": 5},
        {"enabled": True, "roots": ["api", "runtime"]},
    )
    assert_true(list_result["path"] == "api", "Expected api directory listing path.")
    assert_true(len(list_result["entries"]) > 0, "Expected directory listing entries.")

    read_result, _ = runtime.execute_local_file_tool_call(
        "local_read_file",
        {"path": "api/common.php", "start_line": 1, "end_line": 5},
        {"enabled": True, "roots": ["api"]},
    )
    assert_true(read_result["lineCount"] == 5, "Expected five lines from local_read_file.")
    assert_true(read_result["content"].startswith("1:"), "Expected numbered output from local_read_file.")

    search_result, search_audit = runtime.execute_local_file_tool_call(
        "local_search_text",
        {"path": "assets", "pattern": "localFilesEnabled", "max_matches": 5},
        {"enabled": True, "roots": ["assets"]},
    )
    assert_true(len(search_result["matches"]) > 0, "Expected at least one local_search_text match.")
    assert_true(bool(search_audit["sources"]), "Expected local_search_text sources.")

    traversal_blocked = False
    try:
        runtime.execute_local_file_tool_call(
            "local_read_file",
            {"path": "../Auth.txt"},
            {"enabled": True, "roots": ["api"]},
        )
    except RuntimeErrorWithCode:
        traversal_blocked = True
    assert_true(traversal_blocked, "Expected path traversal to be rejected.")

    responses = [
        {
            "id": "resp_1",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "local_read_file",
                    "call_id": "call_1",
                    "arguments": json.dumps({"path": "api/common.php", "start_line": 1, "end_line": 3}),
                }
            ],
        },
        {
            "id": "resp_2",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"ok": True, "usedLocalFile": True}),
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

        def __enter__(self) -> "FakeHandle":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        body = json.loads(request.data.decode("utf-8"))
        requests.append(body)
        return FakeHandle(responses.pop(0))

    original_urlopen = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        result = runtime.invoke_openai_json(
            api_key="test",
            model="gpt-5-mini",
            reasoning_effort="low",
            instructions="Test instructions",
            input_text="Find the file and answer.",
            schema_name="qa_local_tool_loop",
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["ok", "usedLocalFile"],
                "properties": {
                    "ok": {"type": "boolean"},
                    "usedLocalFile": {"type": "boolean"},
                },
            },
            max_output_tokens=200,
            target_kind="worker",
            tools=runtime.build_local_file_function_tools({"enabled": True, "roots": ["api"]}),
            tool_choice="auto",
            function_handlers={
                "local_read_file": lambda arguments: runtime.execute_local_file_tool_call(
                    "local_read_file",
                    arguments,
                    {"enabled": True, "roots": ["api"]},
                )
            },
        )
    finally:
        urllib.request.urlopen = original_urlopen

    assert_true(result.parsed["ok"] is True, "Expected structured output after tool continuation.")
    assert_true(len(result.executed_tools) == 1, "Expected one executed local tool call.")
    assert_true(requests[1]["previous_response_id"] == "resp_1", "Expected previous_response_id on continuation request.")
    assert_true(requests[1]["input"][0]["type"] == "function_call_output", "Expected function_call_output continuation input.")

    print(
        json.dumps(
            {
                "status": "ok",
                "listEntries": len(list_result["entries"]),
                "readLineCount": read_result["lineCount"],
                "searchMatchCount": len(search_result["matches"]),
                "executedToolCount": len(result.executed_tools),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
