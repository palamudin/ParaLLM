from __future__ import annotations

import base64
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
    config = {"enabled": True, "repos": ["openai/openai-cookbook"]}

    fake_file_body = "line one\nline two\nline three\nline four\n"
    encoded_body = base64.b64encode(fake_file_body.encode("utf-8")).decode("utf-8")

    def fake_github_request_json(url: str):
        if url.endswith("/contents?ref=main"):
            return [
                {
                    "name": "README.md",
                    "path": "README.md",
                    "type": "file",
                    "size": 128,
                    "html_url": "https://github.com/openai/openai-cookbook/blob/main/README.md",
                },
                {
                    "name": "examples",
                    "path": "examples",
                    "type": "dir",
                    "size": 0,
                    "html_url": "https://github.com/openai/openai-cookbook/tree/main/examples",
                },
            ]
        if url.endswith("/contents/README.md?ref=main"):
            return {
                "type": "file",
                "size": len(fake_file_body.encode("utf-8")),
                "content": encoded_body,
                "html_url": "https://github.com/openai/openai-cookbook/blob/main/README.md",
            }
        if url.endswith("/issues/12"):
            return {
                "title": "Example issue",
                "state": "open",
                "body": "Issue body",
                "labels": [{"name": "bug"}],
                "html_url": "https://github.com/openai/openai-cookbook/issues/12",
            }
        if url.endswith("/pulls/34"):
            return {
                "title": "Example PR",
                "state": "open",
                "draft": False,
                "merged": False,
                "base": {"ref": "main"},
                "head": {"ref": "feature"},
                "body": "PR body",
                "html_url": "https://github.com/openai/openai-cookbook/pull/34",
            }
        if url.endswith("/commits/abc123"):
            return {
                "sha": "abc123",
                "commit": {
                    "author": {"name": "Test Author"},
                    "message": "Commit message",
                },
                "html_url": "https://github.com/openai/openai-cookbook/commit/abc123",
            }
        raise AssertionError(f"Unexpected GitHub URL: {url}")

    original_github_request_json = runtime.github_request_json
    runtime.github_request_json = fake_github_request_json
    try:
        list_result, list_audit = runtime.execute_github_tool_call(
            "github_list_paths",
            {"repo": "openai/openai-cookbook", "ref": "main", "max_entries": 10},
            config,
        )
        read_result, read_audit = runtime.execute_github_tool_call(
            "github_read_file",
            {"repo": "openai/openai-cookbook", "path": "README.md", "ref": "main", "start_line": 2, "end_line": 3},
            config,
        )
        issue_result, _ = runtime.execute_github_tool_call(
            "github_get_issue",
            {"repo": "openai/openai-cookbook", "issue_number": 12},
            config,
        )
        pr_result, _ = runtime.execute_github_tool_call(
            "github_get_pull_request",
            {"repo": "openai/openai-cookbook", "pr_number": 34},
            config,
        )
        commit_result, _ = runtime.execute_github_tool_call(
            "github_get_commit",
            {"repo": "openai/openai-cookbook", "ref": "abc123"},
            config,
        )
    finally:
        runtime.github_request_json = original_github_request_json

    assert_true(len(list_result["entries"]) == 2, "Expected two GitHub paths.")
    assert_true(bool(list_audit["sources"]), "Expected GitHub list audit sources.")
    assert_true(read_result["lineCount"] == 2, "Expected two README lines.")
    assert_true("2:line two" in read_result["content"], "Expected numbered GitHub file content.")
    assert_true(bool(read_audit["sources"]), "Expected GitHub read audit sources.")
    assert_true(issue_result["title"] == "Example issue", "Expected fake issue title.")
    assert_true(pr_result["headRef"] == "feature", "Expected fake PR head ref.")
    assert_true(commit_result["author"] == "Test Author", "Expected fake commit author.")

    blocked = False
    try:
        runtime.execute_github_tool_call(
            "github_get_issue",
            {"repo": "octocat/Hello-World", "issue_number": 1},
            config,
        )
    except RuntimeErrorWithCode:
        blocked = True
    assert_true(blocked, "Expected GitHub allowlist rejection.")

    responses = [
        {
            "id": "resp_1",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "github_read_file",
                    "call_id": "call_1",
                    "arguments": json.dumps({"repo": "openai/openai-cookbook", "path": "README.md", "ref": "main", "start_line": 1, "end_line": 2}),
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
                            "text": json.dumps({"ok": True, "usedGithubFile": True}),
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
    original_github_request_json = runtime.github_request_json
    urllib.request.urlopen = fake_urlopen
    runtime.github_request_json = fake_github_request_json
    try:
        result = runtime.invoke_openai_json(
            api_key="test",
            model="gpt-5-mini",
            reasoning_effort="low",
            instructions="Test instructions",
            input_text="Inspect the repo and answer.",
            schema_name="qa_github_tool_loop",
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["ok", "usedGithubFile"],
                "properties": {
                    "ok": {"type": "boolean"},
                    "usedGithubFile": {"type": "boolean"},
                },
            },
            max_output_tokens=200,
            target_kind="worker",
            tools=runtime.build_github_function_tools(config),
            tool_choice="auto",
            function_handlers={
                "github_read_file": lambda arguments: runtime.execute_github_tool_call(
                    "github_read_file",
                    arguments,
                    config,
                )
            },
        )
    finally:
        urllib.request.urlopen = original_urlopen
        runtime.github_request_json = original_github_request_json

    assert_true(result.parsed["ok"] is True, "Expected structured output after GitHub tool continuation.")
    assert_true(len(result.executed_tools) == 1, "Expected one executed GitHub tool call.")
    assert_true(requests[1]["previous_response_id"] == "resp_1", "Expected previous_response_id on GitHub continuation request.")
    assert_true(requests[1]["input"][0]["type"] == "function_call_output", "Expected function_call_output continuation input.")

    print(
        json.dumps(
            {
                "status": "ok",
                "listedEntries": len(list_result["entries"]),
                "readLineCount": read_result["lineCount"],
                "issueTitle": issue_result["title"],
                "executedToolCount": len(result.executed_tools),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
