from __future__ import annotations

import io
import json
import tempfile
import urllib.error
import unittest
from pathlib import Path
from unittest import mock

from runtime.engine import LoopRuntime, RuntimeErrorWithCode, read_api_key_pool


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class RuntimeAuthTests(unittest.TestCase):
    def test_read_api_key_pool_uses_env_backend_when_configured(self) -> None:
        missing_path = Path(tempfile.gettempdir()) / "parallm-missing-auth.txt"
        env = {
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_OPENAI_API_KEYS": "sk-one\nsk-two\nsk-one\n",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            keys = read_api_key_pool(missing_path)

        self.assertEqual(keys, ["sk-one", "sk-two"])

    def test_read_api_key_pool_reads_mounted_secret_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "openai_api_keys"
            secret_path.write_text("sk-one\nsk-two\n", encoding="utf-8")
            env = {
                "LOOP_SECRET_BACKEND": "docker_secret",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                keys = read_api_key_pool(secret_path)

        self.assertEqual(keys, ["sk-one", "sk-two"])

    def test_read_api_key_pool_dedupes_local_file_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = Path(tmpdir) / "Auth.txt"
            auth_path.write_text("sk-one\n\nsk-two\nsk-one\n", encoding="utf-8")
            env = {
                "LOOP_SECRET_BACKEND": "local_file",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                keys = read_api_key_pool(auth_path)

        self.assertEqual(keys, ["sk-one", "sk-two"])

    def test_read_api_key_pool_honors_env_backend_without_falling_back_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = Path(tmpdir) / "Auth.txt"
            auth_path.write_text("sk-file-only\n", encoding="utf-8")
            env = {
                "LOOP_SECRET_BACKEND": "env",
                "LOOP_OPENAI_API_KEYS": "",
                "OPENAI_API_KEYS": "",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                keys = read_api_key_pool(auth_path)

        self.assertEqual(keys, [])

    def test_invoke_openai_json_rotates_to_next_key_after_auth_failure(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        response_payload = {
            "id": "resp-second-key",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"answer": "ok"}),
                        }
                    ],
                }
            ],
        }
        seen_auth_headers: list[str] = []

        def fake_urlopen(request, timeout=0):
            headers = {key.lower(): value for key, value in request.header_items()}
            seen_auth_headers.append(str(headers.get("authorization", "")))
            if len(seen_auth_headers) == 1:
                raise urllib.error.HTTPError(
                    request.full_url,
                    401,
                    "Unauthorized",
                    hdrs=None,
                    fp=io.BytesIO(b'{"error":{"message":"invalid_api_key"}}'),
                )
            return _FakeHTTPResponse(response_payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = runtime.invoke_openai_json(
                    api_key="sk-first",
                    model="gpt-5-mini",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say ok.",
                    schema_name="rotation_test",
                    schema=schema,
                    target_kind="worker",
                    auth_assignments=[
                        {
                            "apiKey": "sk-first",
                            "target": "worker_A",
                            "positionSlot": 1,
                            "keySlot": 1,
                            "poolSize": 2,
                            "rotationOffset": 0,
                            "reused": False,
                            "masked": "sk-...irst",
                            "last4": "irst",
                        },
                        {
                            "apiKey": "sk-second",
                            "target": "worker_A",
                            "positionSlot": 1,
                            "keySlot": 2,
                            "poolSize": 2,
                            "rotationOffset": 0,
                            "reused": False,
                            "masked": "sk-...cond",
                            "last4": "cond",
                        },
                    ],
                )

        self.assertEqual(result.parsed, {"answer": "ok"})
        self.assertEqual(result.auth_assignment["keySlot"], 2)
        self.assertEqual(len(result.auth_failover_history), 1)
        self.assertEqual(result.auth_failover_history[0]["failedKeySlot"], 1)
        self.assertEqual(result.auth_failover_history[0]["nextKeySlot"], 2)
        self.assertEqual(seen_auth_headers, ["Bearer sk-first", "Bearer sk-second"])

    def test_runtime_refuses_live_fallback_when_managed_secret_backend_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "LOOP_ROOT": tmpdir,
                "LOOP_SECRET_BACKEND": "env",
                "LOOP_OPENAI_API_KEYS": "",
                "OPENAI_API_KEYS": "",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                runtime = LoopRuntime(tmpdir)
                runtime.ensure_data_paths()
                with self.assertRaises(RuntimeErrorWithCode) as context:
                    runtime.raise_if_managed_secret_backend_unavailable(
                        "summarizer",
                        "t-test",
                        "gpt-5-mini",
                        "summarizer",
                    )

        self.assertIn("env secret backend", str(context.exception))
        self.assertIn("empty", str(context.exception))

    def test_invoke_provider_json_supports_ollama_native_chat(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        payload = {
            "created_at": "2026-04-21T12:34:56Z",
            "message": {
                "content": json.dumps({"answer": "Local model reply"}),
                "thinking": "Reasoned locally.",
            },
            "prompt_eval_count": 123,
            "eval_count": 45,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
                result = runtime.invoke_provider_json(
                    provider="ollama",
                    api_key="",
                    model="qwen3",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say something local.",
                    schema_name="ollama_test",
                    schema=schema,
                    max_output_tokens=600,
                    target_kind="worker",
                )

        self.assertEqual(result.provider, "ollama")
        self.assertEqual(result.parsed, {"answer": "Local model reply"})
        self.assertEqual(result.thinking_text, "Reasoned locally.")
        self.assertEqual(result.response_id, "2026-04-21T12:34:56Z")
        usage = runtime.get_response_usage_delta(result.response, "qwen3")
        self.assertEqual(usage["inputTokens"], 123)
        self.assertEqual(usage["outputTokens"], 45)
        self.assertEqual(usage["estimatedCostUsd"], 0.0)

    def test_invoke_provider_json_rejects_ollama_tools(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with self.assertRaises(RuntimeErrorWithCode) as context:
                runtime.invoke_provider_json(
                    provider="ollama",
                    api_key="",
                    model="qwen3",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say something local.",
                    schema_name="ollama_tool_test",
                    schema=schema,
                    target_kind="worker",
                    tools=[{"type": "function", "name": "local_read_file"}],
                )

        self.assertIn("provider_does_not_support", str(context.exception))


if __name__ == "__main__":
    unittest.main()
