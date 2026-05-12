from __future__ import annotations

import io
import json
import tempfile
import urllib.error
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from backend.app import storage
from backend.app.secrets import write_auth_backend_mode_override
from runtime.engine import (
    LoopRuntime,
    OpenAIResult,
    RuntimeErrorWithCode,
    coerce_confidence_value,
    flatten_output_payload_text,
    looks_like_incomplete_structured_output,
    normalize_front_answer,
    parse_structured_output_text,
    provider_capability_profile,
    read_api_key_pool,
)


class _FakeHTTPResponse:
    def __init__(self, payload: dict, headers: dict | None = None, status: int = 200) -> None:
        self.payload = payload
        self.headers = headers or {}
        self.status = status

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class RuntimeAuthTests(unittest.TestCase):
    def test_provider_capability_profile_marks_minimax_deferred(self) -> None:
        profile = provider_capability_profile("minimax")
        self.assertEqual(profile["provider"], "minimax")
        self.assertEqual(profile["status"], "deferred")
        self.assertFalse(profile["primary"])

    def test_provider_capability_profile_marks_deepseek_primary(self) -> None:
        profile = provider_capability_profile("deepseek")
        self.assertEqual(profile["provider"], "deepseek")
        self.assertEqual(profile["status"], "primary")
        self.assertTrue(profile["primary"])

    def _stub_openai_result(self, parsed: dict, max_output_tokens: int = 400) -> OpenAIResult:
        attempts = [int(max_output_tokens)] if int(max_output_tokens) > 0 else []
        return OpenAIResult(
            provider="openai",
            parsed=parsed,
            response={"status": "completed", "usage": {}},
            response_id="resp-test",
            output_text=None,
            thinking_text=None,
            web_search_queries=[],
            web_search_sources=[],
            url_citations=[],
            requested_max_output_tokens=int(max_output_tokens),
            effective_max_output_tokens=int(max_output_tokens),
            attempts=attempts,
            recovered_from_incomplete=False,
            executed_tools=[],
            auth_assignment=None,
            auth_failover_history=[],
        )

    def test_invoke_provider_json_writes_successful_provider_call_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            runtime.ensure_data_paths()
            result = self._stub_openai_result({"answer": "ok"}, 120)
            result.output_text = "{\"answer\":\"ok\"}"
            result.auth_assignment = {"apiKey": "sk-test-secret-1234", "provider": "openai", "keySlot": 1}
            with mock.patch.object(runtime, "invoke_openai_json", return_value=result):
                actual = runtime.invoke_provider_json(
                    provider="openai",
                    api_key="sk-test-secret-1234",
                    model="gpt-test",
                    reasoning_effort="medium",
                    instructions="system prompt",
                    input_text="user prompt",
                    schema_name="front_answer",
                    schema={"type": "object"},
                    max_output_tokens=120,
                    target_kind="summarizer",
                    auth_assignments=[{"apiKey": "sk-test-secret-1234", "provider": "openai", "keySlot": 1}],
                    task_id="task-provider-ledger",
                )
            self.assertIs(actual, result)
            call_files = sorted((Path(tmpdir) / "data" / "provider_calls").glob("*.json"))
            self.assertEqual(len(call_files), 1)
            saved = json.loads(call_files[0].read_text(encoding="utf-8"))
            self.assertEqual(saved["artifactType"], "provider_call")
            self.assertEqual(saved["status"], "completed")
            self.assertEqual(saved["request"]["inputText"], "user prompt")
            self.assertEqual(saved["response"]["rawOutputText"], "{\"answer\":\"ok\"}")
            self.assertNotIn("sk-test-secret-1234", call_files[0].read_text(encoding="utf-8"))
            self.assertEqual(saved["auth"][0]["apiKey"]["last4"], "1234")

    def _build_summary_ready_fixture(self) -> tuple[dict, dict, dict, list[dict], dict, dict]:
        task = {
            "taskId": "task-1",
            "objective": "Contain the incident without overreacting.",
            "constraints": ["Keep user impact low.", "Document the decision path."],
            "sessionContext": "Operations needs an answer before business hours.",
            "workers": [
                {"id": "A", "label": "Proponent", "role": "utility", "focus": "execution", "model": "gpt-5.4"},
                {"id": "B", "label": "Sceptic", "role": "adversarial", "focus": "failure modes", "model": "gpt-5.4"},
            ],
            "summarizer": {"provider": "openai", "model": "gpt-5-mini"},
        }
        commander_checkpoint = {
            "taskId": "task-1",
            "round": 1,
            "stance": "Contain first.",
            "leadDirection": "Use the smallest responsible containment step first.",
            "answerDraft": "Use the smallest responsible containment step first.",
            "whyThisDirection": "It keeps service alive while reducing blast radius.",
            "questionsForWorkers": [],
            "pressurePoints": [],
            "keepCourseIf": [],
            "changeCourseIf": [],
            "uncertainty": [],
            "suggestedLaneTypes": [],
            "suggestedLaneReason": "",
            "constraintsSeen": ["Keep user impact low."],
        }
        commander_review_checkpoint = {
            "taskId": "task-1",
            "round": 1,
            "courseDecision": "maintain",
            "stance": "Contain first, but prepare isolation if spread is confirmed.",
            "leadDirection": "Use the smallest responsible containment step first.",
            "answerDraft": "Contain first, but prepare isolation if spread is confirmed.",
            "whyThisDirection": "It balances caution with operator speed.",
            "adoptedWorkerMoves": [],
            "rejectedWorkerMoves": [],
            "controlAudit": [],
            "evidenceVerdicts": [],
            "reviewTrace": [],
            "dynamicLaneDecision": {"shouldSpawn": False, "rejectedLaneTypes": []},
            "dynamicLaneResolution": {"spawned": False, "reason": "none"},
        }
        workers = task["workers"]
        worker_state = {
            "A": {
                "workerId": "A",
                "label": "Proponent",
                "role": "utility",
                "focus": "execution",
                "step": 1,
                "observation": "A reversible containment step is available.",
                "benefits": ["Keeps core systems up."],
                "detriments": ["Does not answer persistence immediately."],
                "invalidatingCircumstances": ["If spread is already org-wide."],
                "uncertainty": ["Unknown whether persistence is active."],
                "evidenceLedger": [],
                "evidenceGaps": [],
            },
            "B": {
                "workerId": "B",
                "label": "Sceptic",
                "role": "adversarial",
                "focus": "failure modes",
                "step": 1,
                "observation": "Waiting risks wider spread.",
                "benefits": ["Higher certainty if isolated now."],
                "detriments": ["Short-term user impact increases."],
                "invalidatingCircumstances": ["If containment takes too long to apply."],
                "uncertainty": ["Need EDR confirmation."],
                "evidenceLedger": [],
                "evidenceGaps": [],
            },
        }
        runtime_config = {
            "provider": "openai",
            "model": "gpt-5.4",
            "reasoningEffort": "low",
            "maxOutputTokens": 400,
            "executionMode": "live",
            "contextMode": "weighted",
            "localFiles": {"enabled": False},
            "githubTools": {"enabled": False},
            "requestTimeoutSeconds": 180,
        }
        return task, commander_checkpoint, commander_review_checkpoint, workers, worker_state, runtime_config

    def test_coerce_confidence_value_accepts_string_bands(self) -> None:
        self.assertEqual(coerce_confidence_value("high"), 0.85)
        self.assertEqual(coerce_confidence_value("medium"), 0.6)
        self.assertEqual(coerce_confidence_value("low"), 0.35)

    def test_read_api_key_pool_uses_env_backend_when_configured(self) -> None:
        missing_path = Path(tempfile.gettempdir()) / "parallm-missing-auth.txt"
        env = {
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_OPENAI_API_KEYS": "sk-one\nsk-two\nsk-one\n",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            keys = read_api_key_pool(missing_path)

        self.assertEqual(keys, ["sk-one", "sk-two"])

    def test_read_api_key_pool_reads_requested_provider_group_from_env(self) -> None:
        missing_path = Path(tempfile.gettempdir()) / "parallm-missing-auth.txt"
        env = {
            "LOOP_SECRET_BACKEND": "env",
            "LOOP_OPENAI_API_KEYS": "sk-openai\n",
            "LOOP_ANTHROPIC_API_KEYS": "sk-anthropic\nsk-anthropic\n",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            keys = read_api_key_pool(missing_path, "anthropic")

        self.assertEqual(keys, ["sk-anthropic"])

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

    def test_read_api_key_pool_reads_provider_specific_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = Path(tmpdir) / "Auth.txt"
            auth_path.write_text("sk-openai\n", encoding="utf-8")
            (Path(tmpdir) / "Auth.anthropic.txt").write_text("sk-anthropic\nsk-anthropic\n", encoding="utf-8")
            env = {
                "LOOP_SECRET_BACKEND": "local_file",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                keys = read_api_key_pool(auth_path, "anthropic")

        self.assertEqual(keys, ["sk-anthropic"])

    def test_read_api_key_pool_reads_prefixed_shared_auth_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = Path(tmpdir) / "Auth.txt"
            auth_path.write_text("openai:sk-openai\nant:sk-anthropic\n", encoding="utf-8")
            env = {
                "LOOP_SECRET_BACKEND": "local_file",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                keys = read_api_key_pool(auth_path, "anthropic")

        self.assertEqual(keys, ["sk-anthropic"])

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

    def test_budget_limits_ignore_token_caps(self) -> None:
        task = {
            "taskId": "task-1",
            "runtime": {
                "budget": {
                    "maxOutputTokens": 1200,
                    "maxTotalTokens": 900000,
                    "targets": {
                        "summarizer": {"maxOutputTokens": 9000},
                    },
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            limits = runtime.get_budget_limits(task, "summarizer")

        self.assertEqual(limits["maxOutputTokens"], 0)
        self.assertEqual(limits["maxTotalTokens"], 0)

    def test_zero_requested_output_tokens_leave_provider_uncapped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            attempts = runtime.build_output_token_attempts(0, "summarizer")

        self.assertEqual(attempts, [0])

    def test_explicit_provider_caps_use_model_capacity_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            attempts = runtime.build_output_token_attempts(
                0,
                "commander_review",
                provider="deepseek",
                model="deepseek-v4-flash",
                require_explicit_max=True,
            )

        self.assertEqual(attempts, [384_000])

    def test_target_timeout_modes_resolve_default_user_and_auto_profiles(self) -> None:
        manual = {
            "commander": 101,
            "workerDefault": 111,
            "workers": {"A": 77},
            "commanderReview": 222,
            "summarizer": 333,
            "answerNow": 144,
            "arbiter": 155,
        }
        auto_profile = {
            "status": "ready",
            "baseUrl": "http://192.168.0.26:11434",
            "models": {"qwen3.5:9b": {"wallSeconds": 42}},
            "targetTimeouts": {
                "commander": 260,
                "workerDefault": 275,
                "workers": {"A": 205},
                "commanderReview": 320,
                "summarizer": 420,
                "answerNow": 210,
                "arbiter": 180,
            },
        }
        task = {
            "runtime": {
                "provider": "ollama",
                "directProvider": "ollama",
                "targetTimeouts": manual,
                "timeoutMode": "user",
                "ollamaTimeoutProfile": auto_profile,
            },
            "summarizer": {"provider": "ollama"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            user_config = runtime.get_target_timeout_config(task, "A")
            task["runtime"]["timeoutMode"] = "default"
            default_config = runtime.get_target_timeout_config(task, "A")
            task["runtime"]["timeoutMode"] = "auto"
            auto_worker = runtime.get_target_timeout_config(task, "A")
            auto_summary = runtime.get_target_timeout_config(task, "summarizer")
            task["runtime"]["provider"] = "openai"
            task["summarizer"]["provider"] = "openai"
            auto_openai = runtime.get_target_timeout_config(task, "summarizer")
            task["runtime"]["provider"] = "ollama"
            task["summarizer"]["provider"] = "ollama"
            runtime_view = runtime.get_task_runtime(task)
            summarizer_view = runtime.get_task_runtime(task, budget_target="summarizer")

        self.assertEqual(user_config["workers"]["A"], 77)
        self.assertEqual(user_config["commander"], 101)
        self.assertEqual(default_config["commander"], 180)
        self.assertEqual(default_config["workers"], {})
        self.assertEqual(auto_worker["workers"]["A"], 205)
        self.assertEqual(auto_summary["summarizer"], 420)
        self.assertEqual(auto_openai["summarizer"], 240)
        self.assertEqual(runtime_view["timeoutMode"], "auto")
        self.assertEqual(runtime_view["ollamaTimeoutProfile"]["status"], "ready")
        self.assertEqual(runtime_view["requestTimeoutSeconds"], 275)
        self.assertEqual(summarizer_view["requestTimeoutSeconds"], 420)

    def test_select_provider_instance_prefers_distinct_arbiter_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "providers.txt").write_text(
                json.dumps(
                    {
                        "ollama": [
                            {
                                "label": "Ollama A",
                                "baseUrl": "http://192.168.0.26:11434",
                                "models": ["qwen3.5:9b"],
                                "enabled": True,
                            },
                            {
                                "label": "Ollama B",
                                "baseUrl": "http://192.168.0.30:11434",
                                "models": ["qwen3.5:9b"],
                                "enabled": True,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            runtime = LoopRuntime(tmpdir)
            runtime_config = {
                "ollamaBaseUrl": "http://192.168.0.26:11434",
                "providerRouting": {"ollama": {"selectionMode": "single", "judgeMode": "prefer_distinct"}},
            }

            summary_instance = runtime.select_provider_instance(
                {"taskId": "task-1"},
                runtime_config,
                "ollama",
                "qwen3.5:9b",
                "summarizer",
                1,
            )
            arbiter_instance = runtime.select_provider_instance(
                {"taskId": "task-1"},
                runtime_config,
                "ollama",
                "qwen3.5:9b",
                "arbiter",
                1,
            )

        self.assertEqual(summary_instance["baseUrl"], "http://192.168.0.26:11434")
        self.assertEqual(arbiter_instance["baseUrl"], "http://192.168.0.30:11434")

    def test_select_provider_instance_filters_to_matching_model_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "providers.txt").write_text(
                json.dumps(
                    {
                        "ollama": [
                            {
                                "label": "Fast host",
                                "baseUrl": "http://192.168.0.26:11434",
                                "models": ["qwen3.5:9b"],
                                "enabled": True,
                            },
                            {
                                "label": "Heavy host",
                                "baseUrl": "http://192.168.0.30:11434",
                                "models": ["qwen3.5:27b"],
                                "enabled": True,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            runtime = LoopRuntime(tmpdir)
            runtime_config = {
                "ollamaBaseUrl": "http://192.168.0.26:11434",
                "providerRouting": {"ollama": {"selectionMode": "mix", "judgeMode": "prefer_distinct"}},
            }
            filtered_instances = runtime.load_provider_instances("ollama", runtime_config, "qwen3.5:27b")

            instance = runtime.select_provider_instance(
                {"taskId": "task-2"},
                runtime_config,
                "ollama",
                "qwen3.5:27b",
                "summarizer",
                1,
            )

        self.assertEqual(len(filtered_instances), 1)
        self.assertEqual(filtered_instances[0]["baseUrl"], "http://192.168.0.30:11434")
        self.assertEqual(instance["baseUrl"], "http://192.168.0.30:11434")

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

    def test_read_api_key_pool_honors_local_override_over_safe_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = Path(tmpdir) / "Auth.txt"
            auth_path.write_text("openai:sk-local-only\n", encoding="utf-8")
            write_auth_backend_mode_override(Path(tmpdir), "openai", "local")
            env = {
                "LOOP_SECRET_BACKEND": "env",
                "LOOP_OPENAI_API_KEYS": "sk-env-only\n",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                keys = read_api_key_pool(auth_path, "openai")

        self.assertEqual(keys, ["sk-local-only"])

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

    def test_invoke_openai_json_captures_provider_trace_headers(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        response_payload = {
            "id": "resp-trace",
            "status": "completed",
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

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch(
                "urllib.request.urlopen",
                return_value=_FakeHTTPResponse(
                    response_payload,
                    headers={
                        "x-request-id": "req_trace_123",
                        "openai-processing-ms": "321",
                        "x-ratelimit-remaining-requests": "4999",
                        "x-ratelimit-remaining-tokens": "180000",
                    },
                ),
            ):
                result = runtime.invoke_openai_json(
                    api_key="sk-trace",
                    model="gpt-5-mini",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say ok.",
                    schema_name="trace_test",
                    schema=schema,
                    target_kind="commander",
                )

        self.assertEqual(result.parsed, {"answer": "ok"})
        self.assertIsNotNone(result.provider_trace)
        self.assertEqual(result.provider_trace["providerRequestId"], "req_trace_123")
        self.assertEqual(result.provider_trace["providerProcessingMs"], 321)
        self.assertEqual(result.provider_trace["rateLimitRequestsRemaining"], 4999)
        self.assertEqual(result.provider_trace["rateLimitTokensRemaining"], 180000)
        self.assertEqual(result.provider_trace["stage"], "completed")
        self.assertEqual(result.provider_trace["httpStatus"], 200)

    def test_invoke_openai_json_enables_server_input_autocompress(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        seen_bodies: list[dict] = []
        response_payload = {
            "id": "resp-autocompress",
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

        def fake_urlopen(request, timeout=0):
            seen_bodies.append(json.loads(request.data.decode("utf-8")))
            return _FakeHTTPResponse(response_payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = runtime.invoke_openai_json(
                    api_key="sk-live",
                    model="gpt-5.4",
                    reasoning_effort="high",
                    instructions="Return JSON only.",
                    input_text="Say ok.",
                    schema_name="autocompress_test",
                    schema=schema,
                    target_kind="summarizer",
                )

        self.assertEqual(result.parsed, {"answer": "ok"})
        self.assertEqual(seen_bodies[0]["truncation"], "auto")

    def test_invoke_openai_json_uses_configured_request_timeout(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        seen_timeouts: list[int] = []
        response_payload = {
            "id": "resp-timeout-check",
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

        def fake_urlopen(request, timeout=0):
            seen_timeouts.append(int(timeout))
            return _FakeHTTPResponse(response_payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                runtime.invoke_openai_json(
                    api_key="sk-live",
                    model="gpt-5-mini",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say ok.",
                    schema_name="timeout_test",
                    schema=schema,
                    target_kind="worker",
                    request_timeout_seconds=42,
                )

        self.assertEqual(seen_timeouts, [42])

    def test_prompt_text_locally_compacts_when_provider_lacks_server_autocompress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            original = "\n\n".join(
                [f"Section {index}:\n" + ("x" * 5000) for index in range(1, 7)]
            )
            compacted = runtime.maybe_compact_prompt_text(original, {"provider": "anthropic"}, "worker")
            soft_limit = runtime.prompt_compaction_char_limit("anthropic", "worker")

        self.assertIn("locally compacted", compacted)
        self.assertLess(len(compacted), len(original))
        self.assertLessEqual(len(compacted), soft_limit)

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
        seen_urls: list[str] = []

        def fake_urlopen(request, timeout=1800):
            seen_urls.append(str(request.full_url))
            return _FakeHTTPResponse(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
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
                    provider_settings={"ollamaBaseUrl": "http://192.168.0.26:11434/api"},
                )

        self.assertEqual(result.provider, "ollama")
        self.assertEqual(result.parsed, {"answer": "Local model reply"})
        self.assertEqual(result.thinking_text, "Reasoned locally.")
        self.assertEqual(result.response_id, "2026-04-21T12:34:56Z")
        self.assertEqual(seen_urls, ["http://192.168.0.26:11434/api/chat"])
        usage = runtime.get_response_usage_delta(result.response, "qwen3")
        self.assertEqual(usage["inputTokens"], 123)
        self.assertEqual(usage["outputTokens"], 45)
        self.assertEqual(usage["estimatedCostUsd"], 0.0)

    def test_invoke_provider_json_supports_xai_wrapper_flattening(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        payload = {
            "id": "resp-xai-1",
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": [{"type": "summary_text", "text": "hidden"}]},
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"answer": "Grok wrapper reply"}),
                        }
                    ],
                },
            ],
            "usage": {"input_tokens": 22, "output_tokens": 14, "total_tokens": 36},
        }
        seen_urls: list[str] = []

        def fake_urlopen(request, timeout=1800):
            seen_urls.append(str(request.full_url))
            return _FakeHTTPResponse(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = runtime.invoke_provider_json(
                    provider="xai",
                    api_key="xai-test-key",
                    model="grok-4.20",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say something useful.",
                    schema_name="xai_test",
                    schema=schema,
                    target_kind="worker",
                )

        self.assertEqual(result.provider, "xai")
        self.assertEqual(result.parsed, {"answer": "Grok wrapper reply"})
        self.assertEqual(result.output_text, json.dumps({"answer": "Grok wrapper reply"}))
        self.assertEqual(seen_urls, ["https://api.x.ai/v1/responses"])

    def test_invoke_provider_json_supports_anthropic_wrapper_flattening(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        payload = {
            "id": "msg-ant-1",
            "stop_reason": "end_turn",
            "content": [
                {"type": "thinking", "thinking": "internal only"},
                {"type": "text", "text": "```json\n" + json.dumps({"answer": "Claude wrapper reply"}) + "\n```"},
            ],
            "usage": {"input_tokens": 18, "output_tokens": 11},
        }
        seen_urls: list[str] = []

        def fake_urlopen(request, timeout=1800):
            seen_urls.append(str(request.full_url))
            return _FakeHTTPResponse(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = runtime.invoke_provider_json(
                    provider="anthropic",
                    api_key="anthropic-test-key",
                    model="claude-sonnet-4-20250514",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say something useful.",
                    schema_name="anthropic_test",
                    schema=schema,
                    target_kind="worker",
                )

        self.assertEqual(result.provider, "anthropic")
        self.assertEqual(result.parsed, {"answer": "Claude wrapper reply"})
        self.assertEqual(result.output_text, "```json\n" + json.dumps({"answer": "Claude wrapper reply"}) + "\n```")
        self.assertEqual(runtime.get_response_output_text(result.response), result.output_text)
        self.assertEqual(seen_urls, ["https://api.anthropic.com/v1/messages"])

    def test_invoke_provider_json_supports_minimax_openai_compat_wrapper_flattening(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        payload = {
            "id": "chatcmpl-min-1",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"answer": "MiniMax wrapper reply"}),
                        "name": "MiniMax AI",
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 16,
                "completion_tokens": 9,
                "total_tokens": 25,
                "completion_tokens_details": {"reasoning_tokens": 4},
            },
            "base_resp": {
                "status_code": 0,
                "status_msg": "",
            },
        }
        seen_urls: list[str] = []

        def fake_urlopen(request, timeout=1800):
            seen_urls.append(str(request.full_url))
            return _FakeHTTPResponse(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = runtime.invoke_provider_json(
                    provider="minimax",
                    api_key="minimax-test-key",
                    model="MiniMax-M2.7",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say something useful.",
                    schema_name="minimax_test",
                    schema=schema,
                    target_kind="worker",
                )

        self.assertEqual(result.provider, "minimax")
        self.assertEqual(result.parsed, {"answer": "MiniMax wrapper reply"})
        self.assertEqual(result.output_text, json.dumps({"answer": "MiniMax wrapper reply"}))
        self.assertEqual(seen_urls, ["https://api.minimax.io/v1/chat/completions"])
        usage = runtime.get_response_usage_delta(result.response, "MiniMax-M2.7")
        self.assertEqual(usage["inputTokens"], 16)
        self.assertEqual(usage["outputTokens"], 9)
        self.assertEqual(usage["reasoningTokens"], 4)

    def test_minimax_malformed_json_failure_is_persisted_for_review(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["verdict"],
            "properties": {
                "verdict": {"type": "string"},
            },
        }
        malformed_text = "0645260f38c63ca7db5abd54e3df163a\n\n<think>not json</think>\nfinal: no object"
        payload = {
            "id": "chatcmpl-min-bad-json",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": malformed_text,
                    },
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 7, "total_tokens": 16},
            "base_resp": {"status_code": 0, "status_msg": ""},
        }

        def fake_urlopen(request, timeout=1800):
            return _FakeHTTPResponse(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with self.assertRaises(RuntimeErrorWithCode) as context:
                    runtime.invoke_provider_json(
                        provider="minimax",
                        api_key="minimax-test-key",
                        model="MiniMax-M2.7",
                        reasoning_effort="low",
                        instructions="Return JSON only.",
                        input_text="Return malformed JSON.",
                        schema_name="minimax_bad_json",
                        schema=schema,
                        target_kind="commander_review",
                        task_id="t-test-minimax-failed-call",
                    )
            failed_artifact = getattr(context.exception, "failed_call_artifact", None)
            self.assertIsInstance(failed_artifact, dict)
            failed_files = sorted((Path(tmpdir) / "data" / "failed_calls").glob("*.json"))
            self.assertEqual(len(failed_files), 1)
            saved = json.loads(failed_files[0].read_text(encoding="utf-8"))

        self.assertEqual(saved["artifactType"], "failed_call")
        self.assertEqual(saved["provider"], "minimax")
        self.assertEqual(saved["failureKind"], "malformed_json")
        self.assertEqual(saved["taskId"], "t-test-minimax-failed-call")
        self.assertEqual(saved["rawOutputText"], malformed_text)
        self.assertEqual(saved["ingestion"]["rawLength"], len(malformed_text))

    def test_flattener_empty_output_is_persisted_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            flattened = runtime.flatten_output_for_artifact(
                {},
                "summary_output",
                provider="minimax",
                model="MiniMax-M2.7",
                task_id="t-test-flattener",
                target_kind="summarizer",
                schema_name="loop_summary_multi",
                raw_output_text="{}",
                response_id="resp-flat-empty",
            )
            failed_files = sorted((Path(tmpdir) / "data" / "failed_calls").glob("*.json"))
            self.assertEqual(flattened, "")
            self.assertEqual(len(failed_files), 1)
            saved = json.loads(failed_files[0].read_text(encoding="utf-8"))

        self.assertEqual(saved["artifactType"], "failed_call")
        self.assertEqual(saved["failureKind"], "flattener_empty")
        self.assertEqual(saved["provider"], "minimax")
        self.assertEqual(saved["targetNode"], "summarizer")
        self.assertFalse(saved["passedToNextNode"])

    def test_invoke_provider_json_supports_deepseek_openai_compat_wrapper_flattening(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        payload = {
            "id": "chatcmpl-deep-1",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"answer": "DeepSeek wrapper reply"}),
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 18,
                "completion_tokens": 11,
                "total_tokens": 29,
            },
        }
        seen_urls: list[str] = []
        seen_bodies: list[dict] = []

        def fake_urlopen(request, timeout=1800):
            seen_urls.append(str(request.full_url))
            seen_bodies.append(json.loads(request.data.decode("utf-8")))
            return _FakeHTTPResponse(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = runtime.invoke_provider_json(
                    provider="deepseek",
                    api_key="deepseek-test-key",
                    model="deepseek-v4-flash",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say something useful.",
                    schema_name="deepseek_test",
                    schema=schema,
                    target_kind="worker",
                )

        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.parsed, {"answer": "DeepSeek wrapper reply"})
        self.assertEqual(result.output_text, json.dumps({"answer": "DeepSeek wrapper reply"}))
        self.assertEqual(seen_urls, ["https://api.deepseek.com/chat/completions"])
        self.assertEqual(seen_bodies[0]["max_tokens"], 384_000)
        self.assertEqual(result.effective_max_output_tokens, 384_000)

    def test_deepseek_malformed_json_failure_is_persisted_for_review(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["verdict"],
            "properties": {
                "verdict": {"type": "string"},
            },
        }
        malformed_text = '{"verdict": "ship", "notes": ["missing close"'
        payload = {
            "id": "chatcmpl-deep-bad-json",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": malformed_text,
                    },
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 7, "total_tokens": 16},
        }

        def fake_urlopen(request, timeout=1800):
            return _FakeHTTPResponse(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with self.assertRaises(RuntimeErrorWithCode) as context:
                    runtime.invoke_provider_json(
                        provider="deepseek",
                        api_key="deepseek-test-key",
                        model="deepseek-v4-flash",
                        reasoning_effort="low",
                        instructions="Return JSON only.",
                        input_text="Return malformed JSON.",
                        schema_name="deepseek_bad_json",
                        schema=schema,
                        target_kind="commander_review",
                        task_id="t-test-failed-call",
                    )
            failed_artifact = getattr(context.exception, "failed_call_artifact", None)
            self.assertIsInstance(failed_artifact, dict)
            failed_files = sorted((Path(tmpdir) / "data" / "failed_calls").glob("*.json"))
            self.assertEqual(len(failed_files), 1)
            saved = json.loads(failed_files[0].read_text(encoding="utf-8"))

        self.assertEqual(saved["artifactType"], "failed_call")
        self.assertEqual(saved["failureKind"], "malformed_json")
        self.assertEqual(saved["taskId"], "t-test-failed-call")
        self.assertEqual(saved["rawOutputText"], malformed_text)
        self.assertEqual(saved["ingestion"]["rawLength"], len(malformed_text))

    def test_node_transfer_artifact_filename_stays_compact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            packet = runtime.write_node_transfer_artifact(
                task_id="te-test-transfer",
                source_node="deepseek:provider_ingress",
                target_nodes=["commander_review", "summarizer"],
                payload={"answer": "ok", "evidence": ["one", "two"]},
            )
            artifact_name = packet["artifact"]["name"]
            saved_path = Path(tmpdir) / "data" / "node_transfers" / artifact_name

            self.assertLessEqual(len(artifact_name), 52)
            self.assertTrue(artifact_name.startswith("nt_tetesttransf_"))
            self.assertTrue(saved_path.exists())
            self.assertEqual(packet["sourceNode"], "deepseek:provider_ingress")
            self.assertEqual(packet["targetNodes"], ["commander_review", "summarizer"])
            self.assertEqual(packet["routeLabel"]["source"], "deepseek-provider_ingress")

    def test_invoke_provider_json_supports_deepseek_anthropic_fallback_transport(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        payload = {
            "id": "msg-deep-1",
            "stop_reason": "end_turn",
            "content": [
                {"type": "text", "text": json.dumps({"answer": "DeepSeek wrapper reply"})},
            ],
            "usage": {"input_tokens": 14, "output_tokens": 8},
        }
        seen_urls: list[str] = []

        def fake_urlopen(request, timeout=1800):
            seen_urls.append(str(request.full_url))
            return _FakeHTTPResponse(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with (
                mock.patch("urllib.request.urlopen", side_effect=fake_urlopen),
                mock.patch.dict("os.environ", {"LOOP_DEEPSEEK_TRANSPORT": "anthropic"}, clear=False),
            ):
                result = runtime.invoke_provider_json(
                    provider="deepseek",
                    api_key="deepseek-test-key",
                    model="deepseek-v4-flash",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say something useful.",
                    schema_name="deepseek_test",
                    schema=schema,
                    target_kind="worker",
                )

        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.parsed, {"answer": "DeepSeek wrapper reply"})
        self.assertEqual(result.output_text, json.dumps({"answer": "DeepSeek wrapper reply"}))
        self.assertEqual(seen_urls, ["https://api.deepseek.com/anthropic/v1/messages"])

    def test_invoke_provider_json_supports_minimax_anthropic_fallback_transport(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        payload = {
            "id": "msg-min-1",
            "stop_reason": "end_turn",
            "content": [
                {"type": "text", "text": json.dumps({"answer": "MiniMax wrapper reply"})},
            ],
            "usage": {"input_tokens": 16, "output_tokens": 9},
        }
        seen_urls: list[str] = []

        def fake_urlopen(request, timeout=1800):
            seen_urls.append(str(request.full_url))
            return _FakeHTTPResponse(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with (
                mock.patch("urllib.request.urlopen", side_effect=fake_urlopen),
                mock.patch.dict("os.environ", {"LOOP_MINIMAX_TRANSPORT": "anthropic"}, clear=False),
            ):
                result = runtime.invoke_provider_json(
                    provider="minimax",
                    api_key="minimax-test-key",
                    model="MiniMax-M2.7",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say something useful.",
                    schema_name="minimax_test",
                    schema=schema,
                    target_kind="worker",
                )

        self.assertEqual(result.provider, "minimax")
        self.assertEqual(result.parsed, {"answer": "MiniMax wrapper reply"})
        self.assertEqual(result.output_text, json.dumps({"answer": "MiniMax wrapper reply"}))
        self.assertEqual(seen_urls, ["https://api.minimax.io/anthropic/v1/messages"])

    def test_invoke_provider_json_salvages_minimax_direct_answer_from_structured_plan_text(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer", "stance", "confidenceNote"],
            "properties": {
                "answer": {"type": "string"},
                "stance": {"type": "string"},
                "confidenceNote": {"type": "string"},
            },
        }
        sample_path = Path(__file__).resolve().parents[2] / "responses" / "minimax_response.json"
        sample_text = sample_path.read_text(encoding="utf-8")
        payload = {
            "id": "msg-min-salvage-1",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": sample_text,
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 16,
                "completion_tokens": 9,
                "total_tokens": 25,
            },
            "base_resp": {
                "status_code": 0,
                "status_msg": "",
            },
        }

        def fake_urlopen(request, timeout=1800):
            return _FakeHTTPResponse(payload)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with (
                mock.patch("urllib.request.urlopen", side_effect=fake_urlopen),
                mock.patch(
                    "runtime.engine.parse_structured_output_text",
                    side_effect=RuntimeErrorWithCode("forced parse failure", 500),
                ),
            ):
                result = runtime.invoke_provider_json(
                    provider="minimax",
                    api_key="minimax-test-key",
                    model="MiniMax-M2.7",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say something useful.",
                    schema_name="eval_direct_answer",
                    schema=schema,
                    target_kind="generic",
                )

        self.assertEqual(result.provider, "minimax")
        self.assertIn("## Immediate actions", result.parsed["answer"])
        self.assertIn("Severity:", result.parsed["stance"])
        self.assertIn("Rendered from MiniMax incident-response structure.", result.parsed["confidenceNote"])

    def test_flatten_output_payload_text_prefers_shared_provider_normalizer(self) -> None:
        payload = {
            "provider": "minimax",
            "rawOutputText": '{"incident_id":"INC-TEST","severity":"P1 - CRITICAL","current_status":"ACTIVE","control_plane_trust_status":"UNTRUSTED","first_hour_objectives":["Contain spread"],"immediate_actions_0_to_15_minutes":{"revoke_automation_package":{"action":"Suspend package","rationale":"Stop spread"},"short_term_actions_15_to_30_minutes":{"validate_package_revocation":{"action":"Confirm revoke"},"medium_term_actions_30_to_60_minutes":{"risk_acceptances_needed":{"overall_risk_posture":"Containment first"}}}}',
            "frontAnswer": {"answer": "stale front answer"},
        }
        flattened = flatten_output_payload_text(payload, "direct_baseline_output")
        self.assertIn("## Immediate actions (0-15 minutes)", flattened)
        self.assertIn("Suspend package", flattened)
        self.assertNotIn("stale front answer", flattened)

    def test_parse_structured_output_text_repairs_literal_newlines_inside_json_strings(self) -> None:
        payload = """{
  "answer": "Line one
Line two",
  "confidenceNote": "Safe to continue"
}"""
        parsed = parse_structured_output_text(payload)
        self.assertEqual(parsed["answer"], "Line one\nLine two")
        self.assertEqual(parsed["confidenceNote"], "Safe to continue")

    def test_parse_structured_output_text_strips_json_prefix_before_parse(self) -> None:
        parsed = parse_structured_output_text('json\\n{"answer":"ok"}')
        self.assertEqual(parsed, {"answer": "ok"})

    def test_parse_structured_output_text_extracts_minimax_thinking_preamble_json(self) -> None:
        payload = (
            "0645260f38c63ca7db5abd54e3df163a\n\n"
            "<think>I will reason in prose before the object.</think>\n"
            "{\"taskId\":\"te-c4176d\",\"round\":1,\"stance\":\"caution\"}"
        )
        parsed = parse_structured_output_text(payload)
        self.assertEqual(parsed["taskId"], "te-c4176d")
        self.assertEqual(parsed["stance"], "caution")

    def test_parse_structured_output_text_skips_minimax_schema_echo_before_payload(self) -> None:
        payload = (
            "<think>MiniMax displays its reasoning first.</think>\n\n"
            '{"type":"object","additionalProperties":false,"required":["taskId","round"],'
            '"properties":{"taskId":{"type":"string"},"round":{"type":"integer"}}}}\n\n'
            '{"taskId":"msp-rmm-powershell-incident-001","round":1,'
            '"frontAnswer":{"answer":"Request confirmation of package provenance and any known compromise disclosures.",'
            '"stance":"act","leadDirection":"contain","adversarialPressure":"none","confidenceNote":"medium"},'
            '"summarizerOpinion":{"stance":"act","because":"multi-tenant RMM risk",'
            '"uncertainty":"root cause still open","integrationMode":"gated"},'
            '"sourceWorkers":[]}'
        )
        parsed = parse_structured_output_text(payload)
        self.assertEqual(parsed["taskId"], "msp-rmm-powershell-incident-001")
        self.assertIn("package provenance", parsed["frontAnswer"]["answer"])
        self.assertEqual(parsed["summarizerOpinion"]["integrationMode"], "gated")

    def test_parse_structured_output_text_skips_minimax_direct_schema_payload_echo(self) -> None:
        payload = (
            "<think>MiniMax echoed the requested direct-answer shape first.</think>\n\n"
            '{"answer":{"type":"string"},"stance":{"type":"string"},"confidenceNote":{"type":"string"}}\n\n'
            '{"answer":"Run the first-hour incident bridge with per-customer ownership.",'
            '"stance":"contain safely","confidenceNote":"medium"}'
        )
        parsed = parse_structured_output_text(payload)
        self.assertEqual(parsed["answer"], "Run the first-hour incident bridge with per-customer ownership.")
        self.assertEqual(parsed["stance"], "contain safely")

    def test_parse_structured_output_text_prefers_real_payload_over_placeholder(self) -> None:
        payload = (
            "<think>MiniMax emitted a placeholder before final JSON.</think>\n"
            '{"answer":"...\\n...","stance":"...","confidenceNote":"..."}\n'
            '{"answer":"Run the first-hour incident bridge with per-customer ownership and evidence capture.",'
            '"stance":"contain safely","confidenceNote":"medium"}'
        )
        parsed = parse_structured_output_text(payload)
        self.assertIn("evidence capture", parsed["answer"])
        self.assertNotEqual(parsed["answer"], "...\n...")

    def test_parse_structured_output_text_prefers_full_judge_payload_over_nested_scores(self) -> None:
        payload = (
            '{"scores":{"decisiveness":8,"tradeoffHandling":8,"objectionAbsorption":7,'
            '"actionability":8,"singleVoice":9,"overallQuality":3},'
            '"verdict":"Structured but misses tenant ownership.",'
            '"strongestStrength":"Clear containment sequencing.",'
            '"strongestWeakness":"Per-customer incident ownership is missing.",'
            '"rationale":"The score is low because a hard MSP governance gate is absent."}'
        )
        parsed = parse_structured_output_text(payload)
        self.assertIn("scores", parsed)
        self.assertEqual(parsed["scores"]["overallQuality"], 3)
        self.assertIn("tenant ownership", parsed["verdict"])

    def test_parse_structured_output_text_rejects_truncated_judge_payload_instead_of_nested_scores(self) -> None:
        payload = (
            '{"scores":{"decisiveness":9,"tradeoffHandling":9,"objectionAbsorption":10,'
            '"actionability":9,"singleVoice":10,"overallQuality":9},'
            '"verdict":"Strong plan.",'
            '"strongestWeakness":'
        )
        with self.assertRaises(RuntimeErrorWithCode):
            parse_structured_output_text(payload)
        self.assertTrue(looks_like_incomplete_structured_output(payload))

    def test_normalize_front_answer_falls_back_to_answer_draft_when_front_answer_missing(self) -> None:
        normalized = normalize_front_answer(
            {},
            {
                "answerDraft": "Use per-customer incident ownership and preserve control-plane evidence first.",
                "vettingSummary": "Detailed fallback summary.",
            },
        )
        self.assertEqual(
            normalized["answer"],
            "Use per-customer incident ownership and preserve control-plane evidence first.",
        )
        self.assertIn("Use per-customer incident ownership", normalized["stance"])

    def test_get_task_runtime_carries_context_mode_and_ollama_endpoint(self) -> None:
        task = {
            "objective": "Validate remote Ollama runtime state.",
            "runtime": {
                "provider": "ollama",
                "model": "qwen3.5:2b",
                "contextMode": "full",
                "directBaselineMode": "both",
                "directProvider": "anthropic",
                "directModel": "claude-sonnet-4-20250514",
                "ollamaBaseUrl": "http://192.168.0.26:11434/api",
                "timeoutMode": "user",
                "targetTimeouts": {"commander": 95, "workerDefault": 115, "workers": {"A": 70}, "commanderReview": 210, "summarizer": 230},
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            runtime_config = runtime.get_task_runtime(task)
            direct_runtime = runtime.get_direct_baseline_runtime(task)
            task_projection = runtime.project_task_for_summary(task)

        self.assertEqual(runtime_config["provider"], "ollama")
        self.assertEqual(runtime_config["model"], "qwen3.5:2b")
        self.assertEqual(runtime_config["contextMode"], "full")
        self.assertEqual(runtime_config["directBaselineMode"], "both")
        self.assertEqual(runtime_config["directProvider"], "anthropic")
        self.assertEqual(runtime_config["directModel"], "claude-sonnet-4-20250514")
        self.assertEqual(direct_runtime["mode"], "both")
        self.assertEqual(direct_runtime["provider"], "anthropic")
        self.assertEqual(direct_runtime["model"], "claude-sonnet-4-20250514")
        self.assertEqual(runtime_config["ollamaBaseUrl"], "http://192.168.0.26:11434/api")
        self.assertEqual(runtime_config["targetTimeouts"]["commander"], 95)
        self.assertEqual(runtime_config["targetTimeouts"]["workerDefault"], 115)
        self.assertEqual(runtime_config["targetTimeouts"]["workers"]["A"], 70)
        self.assertEqual(runtime_config["requestTimeoutSeconds"], 115)
        self.assertEqual(direct_runtime["requestTimeoutSeconds"], 150)
        self.assertEqual(task_projection["runtime"]["contextMode"], "full")
        self.assertEqual(task_projection["runtime"]["directBaselineMode"], "both")
        self.assertEqual(task_projection["runtime"]["directProvider"], "anthropic")
        self.assertEqual(task_projection["runtime"]["directModel"], "claude-sonnet-4-20250514")
        self.assertEqual(task_projection["runtime"]["ollamaBaseUrl"], "http://192.168.0.26:11434/api")

    def test_runtime_uses_auth_root_for_provider_backend_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as repo_tmpdir:
            with tempfile.TemporaryDirectory() as workspace_tmpdir:
                repo_root = Path(repo_tmpdir)
                auth_path = repo_root / "Auth.txt"
                auth_path.write_text("openai:sk-local-only\n", encoding="utf-8")
                write_auth_backend_mode_override(repo_root, "openai", "local")
                env = {
                    "LOOP_SECRET_BACKEND": "env",
                    "LOOP_OPENAI_API_KEYS": "",
                    "OPENAI_API_KEYS": "",
                }
                with mock.patch.dict("os.environ", env, clear=False):
                    runtime = LoopRuntime(Path(workspace_tmpdir) / "workspace", auth_path=auth_path)
                    pool = runtime.load_api_key_pool_state("openai")

        self.assertEqual(pool["backend"], "local_file")
        self.assertEqual(pool["selectedMode"], "local")
        self.assertEqual(pool["keys"], ["sk-local-only"])

    def test_runtime_preserves_direct_baseline_in_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            baseline = {
                "taskId": "task-1",
                "mode": "live",
                "provider": "openai",
                "answer": {
                    "answer": "Direct baseline answer.",
                    "stance": "contain-first",
                    "confidenceNote": "high confidence",
                },
            }

            runtime.write_state({"activeTask": {"taskId": "task-1"}, "directBaseline": baseline})
            state = runtime.read_state()

        self.assertEqual(state["directBaseline"], baseline)

    def test_light_workers_mode_keeps_full_packet_on_main_thread(self) -> None:
        captured: dict[str, str] = {}
        task = {
            "taskId": "task-1",
            "objective": "Stabilize the rollout without hiding the risk.",
            "constraints": ["Keep production impact low.", "Document the decision path."],
            "sessionContext": "Customer is already nervous after a failed change window.",
            "workers": [
                {"id": "A", "label": "Proponent", "role": "utility", "focus": "execution", "model": "gpt-5.4"},
                {"id": "B", "label": "Sceptic", "role": "adversarial", "focus": "failure modes", "model": "gpt-5.4"},
            ],
        }
        runtime_config = {
            "provider": "openai",
            "model": "gpt-5.4",
            "reasoningEffort": "low",
            "maxOutputTokens": 400,
            "contextMode": "weighted",
            "localFiles": {"enabled": False},
            "githubTools": {"enabled": False},
        }
        constraints = list(task["constraints"])
        prior_summary = {
            "taskId": "task-1",
            "round": 1,
            "recommendedNextAction": "Use the safest reversible path first.",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)

            def fake_invoke_provider_json(**kwargs):
                captured["instructions"] = kwargs["instructions"]
                captured["input_text"] = kwargs["input_text"]
                parsed = runtime.new_offline_fixture_commander(task, runtime_config, 1, constraints, prior_summary)
                return self._stub_openai_result(parsed, kwargs.get("max_output_tokens", 400))

            with mock.patch.object(runtime, "invoke_provider_json", side_effect=fake_invoke_provider_json):
                runtime.new_live_commander(
                    api_key="sk-test",
                    auth_assignments=None,
                    task=task,
                    runtime=runtime_config,
                    round_number=1,
                    constraints=constraints,
                    prior_summary=prior_summary,
                )

        self.assertIn("Main-thread full context is active.", captured["instructions"])
        self.assertIn("Light Workers mode", captured["instructions"])
        self.assertIn("Task brief:", captured["input_text"])

    def test_commander_review_packet_drops_worker_lineup(self) -> None:
        captured: dict[str, str] = {}
        task = {
            "taskId": "task-1",
            "objective": "Contain risk without overreacting.",
            "constraints": ["Keep user impact low."],
            "sessionContext": "The customer wants an answer before business hours.",
            "workers": [
                {"id": "A", "label": "Proponent", "role": "utility", "focus": "execution", "model": "gpt-5.4"},
                {"id": "B", "label": "Sceptic", "role": "adversarial", "focus": "failure modes", "model": "gpt-5.4"},
            ],
        }
        runtime_config = {
            "provider": "openai",
            "model": "gpt-5.4",
            "reasoningEffort": "low",
            "maxOutputTokens": 400,
            "contextMode": "weighted",
            "localFiles": {"enabled": False},
            "githubTools": {"enabled": False},
        }
        workers = task["workers"]
        commander_checkpoint = {
            "taskId": "task-1",
            "round": 1,
            "stance": "Contain first.",
            "leadDirection": "Use the smallest responsible containment step first.",
            "answerDraft": "Use the smallest responsible containment step first.",
            "whyThisDirection": "It keeps service alive while reducing blast radius.",
            "questionsForWorkers": [],
            "pressurePoints": [],
            "keepCourseIf": [],
            "changeCourseIf": [],
            "uncertainty": [],
            "suggestedLaneTypes": [],
            "suggestedLaneReason": "",
            "constraintsSeen": ["Keep user impact low."],
        }
        prior_summary = {"taskId": "task-1", "round": 1, "recommendedNextAction": "Start with reversible containment."}
        worker_state = {
            "A": {
                "workerId": "A",
                "label": "Proponent",
                "role": "utility",
                "focus": "execution",
                "step": 1,
                "observation": "A narrow containment step keeps service usable.",
                "benefits": ["Low blast radius."],
                "detriments": ["May not stop all spread."],
                "invalidatingCircumstances": ["If lateral movement is already active."],
                "uncertainty": ["Scope of compromise is still incomplete."],
                "evidenceLedger": [{"claim": "Containment is reversible.", "supportLevel": "supported", "note": "Rollback path is known.", "sourceUrls": []}],
                "evidenceGaps": ["Need host-level confirmation."],
            },
            "B": {
                "workerId": "B",
                "label": "Sceptic",
                "role": "adversarial",
                "focus": "failure modes",
                "step": 1,
                "observation": "Waiting risks wider spread.",
                "benefits": ["Higher certainty if isolated now."],
                "detriments": ["Short-term user impact increases."],
                "invalidatingCircumstances": ["If containment takes too long to apply."],
                "uncertainty": ["Unknown whether persistence is active."],
                "evidenceLedger": [{"claim": "Delay increases exposure.", "supportLevel": "mixed", "note": "Depends on current foothold.", "sourceUrls": []}],
                "evidenceGaps": ["Need EDR confirmation."],
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            line_catalog = runtime.build_summary_line_catalog(worker_state, workers, max_items_per_worker=8)

            def fake_invoke_provider_json(**kwargs):
                captured["instructions"] = kwargs["instructions"]
                captured["input_text"] = kwargs["input_text"]
                parsed = runtime.new_offline_fixture_commander_review(task, commander_checkpoint, workers, worker_state)
                return self._stub_openai_result(parsed, kwargs.get("max_output_tokens", 400))

            with mock.patch.object(runtime, "invoke_provider_json", side_effect=fake_invoke_provider_json):
                runtime.new_live_commander_review(
                    api_key="sk-test",
                    auth_assignments=None,
                    task=task,
                    commander_checkpoint=commander_checkpoint,
                    prior_summary=prior_summary,
                    workers=workers,
                    worker_state=worker_state,
                    runtime=runtime_config,
                    line_catalog=line_catalog,
                )

        self.assertIn("Task brief:", captured["input_text"])
        self.assertNotIn("Worker lineup:", captured["input_text"])

    def test_commander_review_packet_uses_compact_binder_for_deepseek(self) -> None:
        captured: dict[str, Any] = {}
        task = {
            "taskId": "task-1",
            "objective": "Contain risk without overreacting.",
            "constraints": ["Keep user impact low."],
            "sessionContext": "The customer wants an answer before business hours.",
            "workers": [
                {"id": "A", "label": "Proponent", "role": "utility", "focus": "execution", "model": "deepseek-v4-flash"},
                {"id": "B", "label": "Sceptic", "role": "adversarial", "focus": "failure modes", "model": "deepseek-v4-flash"},
            ],
        }
        runtime_config = {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "reasoningEffort": "low",
            "maxOutputTokens": 400,
            "contextMode": "weighted",
            "localFiles": {"enabled": False},
            "githubTools": {"enabled": False},
        }
        workers = task["workers"]
        commander_checkpoint = {
            "taskId": "task-1",
            "round": 1,
            "stance": "Contain first.",
            "leadDirection": "Use the smallest responsible containment step first.",
            "answerDraft": "Use the smallest responsible containment step first.",
            "whyThisDirection": "It keeps service alive while reducing blast radius.",
            "questionsForWorkers": [],
            "pressurePoints": [],
            "keepCourseIf": [],
            "changeCourseIf": [],
            "uncertainty": [],
            "suggestedLaneTypes": [],
            "suggestedLaneReason": "",
            "constraintsSeen": ["Keep user impact low."],
        }
        prior_summary = {"taskId": "task-1", "round": 1, "recommendedNextAction": "Start with reversible containment."}
        worker_state = {
            "A": {
                "workerId": "A",
                "label": "Proponent",
                "role": "utility",
                "focus": "execution",
                "step": 1,
                "observation": "A narrow containment step keeps service usable.",
                "benefits": ["Low blast radius."],
                "detriments": ["May not stop all spread."],
                "invalidatingCircumstances": ["If lateral movement is already active."],
                "uncertainty": ["Scope of compromise is still incomplete."],
                "evidenceLedger": [{"claim": "Containment is reversible.", "supportLevel": "supported", "note": "Rollback path is known.", "sourceUrls": []}],
                "evidenceGaps": ["Need host-level confirmation."],
            },
            "B": {
                "workerId": "B",
                "label": "Sceptic",
                "role": "adversarial",
                "focus": "failure modes",
                "step": 1,
                "observation": "Waiting risks wider spread.",
                "benefits": ["Higher certainty if isolated now."],
                "detriments": ["Short-term user impact increases."],
                "invalidatingCircumstances": ["If containment takes too long to apply."],
                "uncertainty": ["Unknown whether persistence is active."],
                "evidenceLedger": [{"claim": "Delay increases exposure.", "supportLevel": "mixed", "note": "Depends on current foothold.", "sourceUrls": []}],
                "evidenceGaps": ["Need EDR confirmation."],
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            line_catalog = runtime.build_summary_line_catalog(worker_state, workers, max_items_per_worker=8)

            def fake_invoke_provider_json(**kwargs):
                captured["instructions"] = kwargs["instructions"]
                captured["input_text"] = kwargs["input_text"]
                captured["schema"] = kwargs["schema"]
                parsed = runtime.new_offline_fixture_commander_review(task, commander_checkpoint, workers, worker_state)
                return self._stub_openai_result(parsed, kwargs.get("max_output_tokens", 400))

            with mock.patch.object(runtime, "invoke_provider_json", side_effect=fake_invoke_provider_json):
                runtime.new_live_commander_review(
                    api_key="sk-test",
                    auth_assignments=None,
                    task=task,
                    commander_checkpoint=commander_checkpoint,
                    prior_summary=prior_summary,
                    workers=workers,
                    worker_state=worker_state,
                    runtime=runtime_config,
                    line_catalog=line_catalog,
                )

        self.assertNotIn("Task brief:", captured["input_text"])
        self.assertNotIn("Prior summary packet:", captured["input_text"])
        self.assertNotIn("Known adversarial lane types:", captured["input_text"])
        self.assertNotIn("Worker review line catalog:", captured["input_text"])
        self.assertIn("Worker checkpoint digests:", captured["input_text"])
        self.assertIn("answerDraft", captured["schema"]["required"])
        self.assertIn("requiredDecisionGates", captured["schema"]["required"])
        self.assertNotIn("controlAudit", captured["schema"]["required"])
        self.assertNotIn("dynamicLaneDecision", captured["schema"]["required"])
        self.assertIn("sourceWorkers", captured["schema"]["required"])

    def test_parse_structured_output_text_repairs_relaxed_object_keys_and_trailing_commas(self) -> None:
        payload = """DeepSeek reply

{
  taskId: "task-1",
  round: 1,
  leadDirection: "Contain first",
  answerDraft: "Do the least destructive safe step first",
  whyThisDirection: "It preserves service while reducing blast radius",
  claimsToStrengthen: ["Preserve evidence",],
  claimsToLimit: ["Do not trust the control plane blindly",],
  requiredDecisionGates: ["Confirm scope before broad isolation",],
  evidenceOrCommsRisks: ["Cross-tenant communication creates a second incident",],
  remainingUncertainty: ["Need vendor confirmation",],
}
"""
        parsed = parse_structured_output_text(payload)
        self.assertEqual(parsed["taskId"], "task-1")
        self.assertEqual(parsed["round"], 1)
        self.assertEqual(parsed["leadDirection"], "Contain first")
        self.assertEqual(parsed["claimsToStrengthen"], ["Preserve evidence"])

    def test_summarizer_packet_drops_worker_lineup_and_lane_catalog_list(self) -> None:
        captured: dict[str, str] = {}
        task = {
            "taskId": "task-1",
            "objective": "Contain risk without overreacting.",
            "constraints": ["Keep user impact low."],
            "sessionContext": "The customer wants an answer before business hours.",
            "workers": [
                {"id": "A", "label": "Proponent", "role": "utility", "focus": "execution", "model": "gpt-5.4"},
                {"id": "B", "label": "Sceptic", "role": "adversarial", "focus": "failure modes", "model": "gpt-5.4"},
            ],
        }
        runtime_config = {
            "provider": "openai",
            "model": "gpt-5.4",
            "reasoningEffort": "low",
            "maxOutputTokens": 400,
            "contextMode": "weighted",
            "localFiles": {"enabled": False},
            "githubTools": {"enabled": False},
        }
        workers = task["workers"]
        commander_checkpoint = {
            "taskId": "task-1",
            "round": 1,
            "stance": "Contain first.",
            "leadDirection": "Use the smallest responsible containment step first.",
            "answerDraft": "Use the smallest responsible containment step first.",
            "whyThisDirection": "It keeps service alive while reducing blast radius.",
            "questionsForWorkers": [],
            "pressurePoints": [],
            "keepCourseIf": [],
            "changeCourseIf": [],
            "uncertainty": [],
            "suggestedLaneTypes": [],
            "suggestedLaneReason": "",
            "constraintsSeen": ["Keep user impact low."],
        }
        commander_review_checkpoint = {
            "taskId": "task-1",
            "round": 1,
            "stance": "Contain first, but prepare isolation if spread is confirmed.",
            "leadDirection": "Use the smallest responsible containment step first.",
            "answerDraft": "Start with the smallest reversible containment step, then escalate if telemetry confirms spread.",
            "whyThisDirection": "It balances service continuity with containment speed.",
            "controlAudit": {
                "leadDraft": "Start with the smallest reversible containment step.",
                "integrationQuestion": "Does the pressure materially change correctness or just sharpen guardrails?",
                "courseDecision": "qualify",
                "courseDecisionReason": "Pressure tightened the guardrails but did not reverse the direction.",
                "contributionAssessments": [],
                "acceptedAdversarialPoints": ["Escalate quickly if spread is confirmed."],
                "rejectedAdversarialPoints": [],
                "heldOutConcerns": [],
                "selfCheck": "The revised draft still answers the user directly.",
            },
            "dynamicLaneDecision": {
                "shouldSpawn": False,
                "suggestedLaneTypes": [],
                "reason": "",
                "requiredPressure": "",
                "temperature": "",
                "instruction": "",
            },
            "remainingUncertainty": ["Need confirmation on host spread."],
            "sourceWorkers": ["A", "B"],
        }
        worker_state = {
            "A": {
                "workerId": "A",
                "label": "Proponent",
                "role": "utility",
                "focus": "execution",
                "step": 1,
                "observation": "A narrow containment step keeps service usable.",
                "benefits": ["Low blast radius."],
                "detriments": ["May not stop all spread."],
                "invalidatingCircumstances": ["If lateral movement is already active."],
                "uncertainty": ["Scope of compromise is still incomplete."],
                "evidenceLedger": [{"claim": "Containment is reversible.", "supportLevel": "supported", "note": "Rollback path is known.", "sourceUrls": []}],
                "evidenceGaps": ["Need host-level confirmation."],
            },
            "B": {
                "workerId": "B",
                "label": "Sceptic",
                "role": "adversarial",
                "focus": "failure modes",
                "step": 1,
                "observation": "Waiting risks wider spread.",
                "benefits": ["Higher certainty if isolated now."],
                "detriments": ["Short-term user impact increases."],
                "invalidatingCircumstances": ["If containment takes too long to apply."],
                "uncertainty": ["Unknown whether persistence is active."],
                "evidenceLedger": [{"claim": "Delay increases exposure.", "supportLevel": "mixed", "note": "Depends on current foothold.", "sourceUrls": []}],
                "evidenceGaps": ["Need EDR confirmation."],
            },
        }
        vetting_config = {"enabled": True}

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            line_catalog = runtime.build_summary_line_catalog(worker_state, workers, max_items_per_worker=10)

            def fake_invoke_provider_json(**kwargs):
                captured["instructions"] = kwargs["instructions"]
                captured["input_text"] = kwargs["input_text"]
                parsed = runtime.new_offline_fixture_summary(
                    task,
                    commander_checkpoint,
                    commander_review_checkpoint,
                    workers,
                    worker_state,
                    vetting_config,
                    line_catalog,
                )
                return self._stub_openai_result(parsed, kwargs.get("max_output_tokens", 400))

            with mock.patch.object(runtime, "invoke_provider_json", side_effect=fake_invoke_provider_json):
                runtime.new_live_summary(
                    api_key="sk-test",
                    auth_assignments=None,
                    task=task,
                    commander_checkpoint=commander_checkpoint,
                    commander_review_checkpoint=commander_review_checkpoint,
                    workers=workers,
                    worker_state=worker_state,
                    runtime=runtime_config,
                    vetting_config=vetting_config,
                    line_catalog=line_catalog,
                )

        self.assertIn("Rebound lead position from the internal pressure test:", captured["input_text"])
        self.assertIn("Supporting evidence packet for review-facing fields only:", captured["input_text"])
        self.assertNotIn("Worker lineup:", captured["input_text"])
        self.assertNotIn("Known adversarial lane types:", captured["input_text"])

    def test_summarizer_packet_uses_compact_binder_for_deepseek(self) -> None:
        captured: dict[str, Any] = {}
        task = {
            "taskId": "task-1",
            "objective": "Contain risk without overreacting.",
            "constraints": ["Keep user impact low."],
            "sessionContext": "The customer wants an answer before business hours.",
            "workers": [
                {"id": "A", "label": "Proponent", "role": "utility", "focus": "execution", "model": "deepseek-v4-flash"},
                {"id": "B", "label": "Sceptic", "role": "adversarial", "focus": "failure modes", "model": "deepseek-v4-flash"},
            ],
        }
        runtime_config = {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "reasoningEffort": "low",
            "maxOutputTokens": 400,
            "contextMode": "weighted",
            "localFiles": {"enabled": False},
            "githubTools": {"enabled": False},
        }
        workers = task["workers"]
        commander_checkpoint = {
            "taskId": "task-1",
            "round": 1,
            "stance": "Contain first.",
            "leadDirection": "Use the smallest responsible containment step first.",
            "answerDraft": "Use the smallest responsible containment step first.",
            "whyThisDirection": "It keeps service alive while reducing blast radius.",
            "questionsForWorkers": [],
            "pressurePoints": [],
            "keepCourseIf": [],
            "changeCourseIf": [],
            "uncertainty": [],
            "suggestedLaneTypes": [],
            "suggestedLaneReason": "",
            "constraintsSeen": ["Keep user impact low."],
        }
        commander_review_checkpoint = {
            "taskId": "task-1",
            "round": 1,
            "stance": "Contain first, but prepare isolation if spread is confirmed.",
            "leadDirection": "Use the smallest responsible containment step first.",
            "answerDraft": "Start with the smallest reversible containment step, then escalate if telemetry confirms spread.",
            "whyThisDirection": "It balances service continuity with containment speed.",
            "controlAudit": {
                "leadDraft": "Start with the smallest reversible containment step.",
                "integrationQuestion": "Does the pressure materially change correctness or just sharpen guardrails?",
                "courseDecision": "qualify",
                "courseDecisionReason": "Pressure tightened the guardrails but did not reverse the direction.",
                "contributionAssessments": [],
                "acceptedAdversarialPoints": ["Escalate quickly if spread is confirmed."],
                "rejectedAdversarialPoints": [],
                "heldOutConcerns": [],
                "selfCheck": "The revised draft still answers the user directly.",
            },
            "dynamicLaneDecision": {
                "shouldSpawn": False,
                "suggestedLaneTypes": [],
                "reason": "",
                "requiredPressure": "",
                "temperature": "",
                "instruction": "",
            },
            "remainingUncertainty": ["Need confirmation on host spread."],
            "sourceWorkers": ["A", "B"],
        }
        worker_state = {
            "A": {
                "workerId": "A",
                "label": "Proponent",
                "role": "utility",
                "focus": "execution",
                "step": 1,
                "observation": "A narrow containment step keeps service usable.",
                "benefits": ["Low blast radius."],
                "detriments": ["May not stop all spread."],
                "invalidatingCircumstances": ["If lateral movement is already active."],
                "uncertainty": ["Scope of compromise is still incomplete."],
                "evidenceLedger": [{"claim": "Containment is reversible.", "supportLevel": "supported", "note": "Rollback path is known.", "sourceUrls": []}],
                "evidenceGaps": ["Need host-level confirmation."],
            },
            "B": {
                "workerId": "B",
                "label": "Sceptic",
                "role": "adversarial",
                "focus": "failure modes",
                "step": 1,
                "observation": "Waiting risks wider spread.",
                "benefits": ["Higher certainty if isolated now."],
                "detriments": ["Short-term user impact increases."],
                "invalidatingCircumstances": ["If containment takes too long to apply."],
                "uncertainty": ["Unknown whether persistence is active."],
                "evidenceLedger": [{"claim": "Delay increases exposure.", "supportLevel": "mixed", "note": "Depends on current foothold.", "sourceUrls": []}],
                "evidenceGaps": ["Need EDR confirmation."],
            },
        }
        vetting_config = {"enabled": True}

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            line_catalog = runtime.build_summary_line_catalog(worker_state, workers, max_items_per_worker=10)

            def fake_invoke_provider_json(**kwargs):
                captured["instructions"] = kwargs["instructions"]
                captured["input_text"] = kwargs["input_text"]
                captured["schema"] = kwargs["schema"]
                parsed = runtime.new_offline_fixture_summary(
                    task,
                    commander_checkpoint,
                    commander_review_checkpoint,
                    workers,
                    worker_state,
                    vetting_config,
                    line_catalog,
                )
                return self._stub_openai_result(parsed, kwargs.get("max_output_tokens", 400))

            with mock.patch.object(runtime, "invoke_provider_json", side_effect=fake_invoke_provider_json):
                runtime.new_live_summary(
                    api_key="sk-test",
                    auth_assignments=None,
                    task=task,
                    commander_checkpoint=commander_checkpoint,
                    commander_review_checkpoint=commander_review_checkpoint,
                    workers=workers,
                    worker_state=worker_state,
                    runtime=runtime_config,
                    vetting_config=vetting_config,
                    line_catalog=line_catalog,
                )

        self.assertIn("Authoritative rebound lead binder:", captured["input_text"])
        self.assertNotIn("Supporting evidence packet for review-facing fields only:", captured["input_text"])
        self.assertNotIn("Worker checkpoint digests:", captured["input_text"])
        self.assertNotIn("Worker review line catalog:", captured["input_text"])
        self.assertNotIn("Lead draft before the final rewrite:", captured["input_text"])
        self.assertNotIn("Repo agent context:", captured["instructions"])
        self.assertIn("frontAnswer", captured["schema"]["required"])
        self.assertIn("summarizerOpinion", captured["schema"]["required"])
        self.assertNotIn("controlAudit", captured["schema"]["required"])
        self.assertNotIn("reviewTrace", captured["schema"]["required"])

    def test_review_binder_compacts_for_budgeted_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            binder, meta = runtime.compact_review_binder_for_model(
                {
                    "leadDirection": "L" * 1500,
                    "answerDraft": "A" * 12000,
                    "whyThisDirection": "W" * 2200,
                    "claimsToStrengthen": ["S" * 900 for _ in range(6)],
                    "claimsToLimit": ["L" * 900 for _ in range(6)],
                    "requiredDecisionGates": ["G" * 900 for _ in range(6)],
                    "evidenceOrCommsRisks": ["R" * 900 for _ in range(6)],
                    "discardedPressure": ["D" * 900 for _ in range(6)],
                    "remainingUncertainty": ["U" * 900 for _ in range(6)],
                },
                "deepseek",
                "deepseek-v4-flash",
            )

        self.assertTrue(meta["reviewBinderCompacted"])
        self.assertLessEqual(meta["reviewBinderEstimatedTokens"], meta["reviewBinderBudgetTokens"])
        self.assertLessEqual(len(binder["answerDraft"]), 700)
        self.assertLessEqual(len(binder["whyThisDirection"]), 240)

    def test_run_summarizer_retries_live_call_before_succeeding(self) -> None:
        task, commander_checkpoint, commander_review_checkpoint, workers, worker_state, runtime_config = self._build_summary_ready_fixture()

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            runtime.write_state(
                {
                    "activeTask": task,
                    "commander": commander_checkpoint,
                    "commanderReview": commander_review_checkpoint,
                    "workers": worker_state,
                }
            )
            line_catalog = runtime.build_summary_line_catalog(worker_state, workers, max_items_per_worker=10)
            summary_payload = runtime.new_offline_fixture_summary(
                task,
                commander_checkpoint,
                commander_review_checkpoint,
                workers,
                worker_state,
                {"enabled": False},
                line_catalog,
            )
            calls = {"count": 0}

            def fake_new_live_summary(*args, **kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeErrorWithCode("Model response JSON parse failed: bad json", 500)
                return (
                    summary_payload,
                    "resp-summary",
                    {"status": "completed", "usage": {}},
                    {
                        "requestedMaxOutputTokens": 400,
                        "effectiveMaxOutputTokens": 400,
                        "attempts": [400],
                        "recoveredFromIncomplete": False,
                        "inputText": "Objective:\nSynthetic summary input",
                        "fullPrompt": "Instructions:\nSynthetic summary prompt",
                    },
                )

            with (
                mock.patch.object(runtime, "get_task_runtime", return_value=runtime_config),
                mock.patch.object(runtime, "provider_live_api_key", return_value="sk-test"),
                mock.patch.object(runtime, "new_live_summary", side_effect=fake_new_live_summary),
            ):
                result = runtime.run_summarizer()

            self.assertEqual(result["target"], "summarizer")
            self.assertEqual(calls["count"], 2)
            state = runtime.read_state()
            self.assertEqual(state["summary"]["frontAnswer"]["answer"], summary_payload["frontAnswer"]["answer"])
            paths = storage.project_paths(Path(tmpdir))
            outputs = list(paths.outputs.glob("*summary_round001_output.json"))
            self.assertTrue(outputs)
            payload = json.loads(outputs[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["mode"], "live")
            self.assertEqual(payload["inputText"], "Objective:\nSynthetic summary input")
            self.assertEqual(payload["fullPrompt"], "Instructions:\nSynthetic summary prompt")
            steps_text = paths.steps.read_text(encoding="utf-8")
            self.assertIn("Live API call failed; retrying live call.", steps_text)
            self.assertNotIn("falling back to mock", steps_text)

    def test_run_summarizer_raises_after_retry_exhaustion_without_synthetic_output(self) -> None:
        task, commander_checkpoint, commander_review_checkpoint, _workers, worker_state, runtime_config = self._build_summary_ready_fixture()

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            runtime.write_state(
                {
                    "activeTask": task,
                    "commander": commander_checkpoint,
                    "commanderReview": commander_review_checkpoint,
                    "workers": worker_state,
                }
            )
            calls = {"count": 0}

            def fake_new_live_summary(*args, **kwargs):
                calls["count"] += 1
                raise RuntimeErrorWithCode("Model response JSON parse failed: still bad", 500)

            with (
                mock.patch.object(runtime, "get_task_runtime", return_value=runtime_config),
                mock.patch.object(runtime, "provider_live_api_key", return_value="sk-test"),
                mock.patch.object(runtime, "new_live_summary", side_effect=fake_new_live_summary),
            ):
                with self.assertRaises(RuntimeErrorWithCode) as ctx:
                    runtime.run_summarizer()

            self.assertIn("Live run failed for summarizer", str(ctx.exception))
            self.assertEqual(calls["count"], 2)
            state = runtime.read_state()
            self.assertIsNone(state["summary"])
            paths = storage.project_paths(Path(tmpdir))
            self.assertEqual(list(paths.outputs.glob("*summary_round001_output.json")), [])
            steps_text = paths.steps.read_text(encoding="utf-8")
            self.assertIn("Live API call failed after retries; no synthetic output was used.", steps_text)
            self.assertNotIn("synthetic output was used.", steps_text.replace("no synthetic output was used.", ""))

    def test_full_workers_mode_controls_worker_packet_scope(self) -> None:
        task = {
            "taskId": "task-1",
            "objective": "Contain risk without overreacting.",
            "constraints": ["Keep user impact low."],
            "sessionContext": "The customer wants an answer before business hours.",
            "workers": [
                {"id": "A", "label": "Proponent", "role": "utility", "focus": "execution", "model": "gpt-5-mini"},
                {"id": "B", "label": "Sceptic", "role": "adversarial", "focus": "failure modes", "model": "gpt-5-mini"},
            ],
        }
        worker = {"id": "A", "label": "Proponent", "role": "utility", "focus": "execution", "temperature": "balanced", "model": "gpt-5-mini"}
        research_config = {"enabled": False, "externalWebAccess": False, "domains": []}
        constraints = list(task["constraints"])
        prior_summary = {"taskId": "task-1", "round": 1, "recommendedNextAction": "Start with reversible containment."}
        commander_checkpoint = {
            "taskId": "task-1",
            "round": 1,
            "stance": "Contain first.",
            "leadDirection": "Use the smallest responsible containment step first.",
            "answerDraft": "Use the smallest responsible containment step first.",
            "whyThisDirection": "It keeps service alive while reducing blast radius.",
            "questionsForWorkers": [],
            "pressurePoints": [],
            "keepCourseIf": [],
            "changeCourseIf": [],
            "uncertainty": [],
            "suggestedLaneTypes": [],
            "suggestedLaneReason": "",
            "constraintsSeen": constraints,
        }
        observed_inputs: dict[str, dict[str, str]] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)

            def invoke_for_mode(mode: str) -> tuple[str, str]:
                runtime_config = {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "reasoningEffort": "low",
                    "maxOutputTokens": 400,
                    "contextMode": mode,
                    "localFiles": {"enabled": False},
                    "githubTools": {"enabled": False},
                }

                def fake_invoke_provider_json(**kwargs):
                    observed_inputs[mode] = {
                        "instructions": kwargs["instructions"],
                        "input_text": kwargs["input_text"],
                    }
                    parsed = runtime.new_offline_fixture_checkpoint(
                        task,
                        worker,
                        runtime_config,
                        research_config,
                        1,
                        constraints,
                        prior_summary,
                        0,
                        [],
                    )
                    return self._stub_openai_result(parsed, kwargs.get("max_output_tokens", 400))

                with mock.patch.object(runtime, "invoke_provider_json", side_effect=fake_invoke_provider_json):
                    runtime.new_live_checkpoint(
                        api_key="sk-test",
                        auth_assignments=None,
                        task=task,
                        worker=worker,
                        runtime=runtime_config,
                        research_config=research_config,
                        step_number=1,
                        constraints=constraints,
                        commander_checkpoint=commander_checkpoint,
                        prior_summary=prior_summary,
                        prior_memory_version=0,
                        peer_messages=[],
                    )
                return observed_inputs[mode]["instructions"], observed_inputs[mode]["input_text"]

            light_instructions, light_input = invoke_for_mode("weighted")
            full_instructions, full_input = invoke_for_mode("full")

        self.assertIn("Light Workers mode is active.", light_instructions)
        self.assertIn("Full Workers mode is active.", full_instructions)
        self.assertNotIn("Full commander packet:", light_input)
        self.assertNotIn("Task brief:", light_input)
        self.assertIn("Full commander packet:", full_input)
        self.assertIn("Task brief:", full_input)

    def test_direct_baseline_uses_main_thread_harness(self) -> None:
        captured: dict[str, str] = {}
        task = {
            "taskId": "task-1",
            "objective": "Stabilize the breach response before executives wake up.",
            "constraints": ["Be explicit about the first move."],
            "sessionContext": "The on-call lead is alone and needs a usable answer fast.",
            "summarizer": {
                "provider": "openai",
                "model": "gpt-5-mini",
                "harness": {"concision": "expansive", "instruction": "Use crisp sections for recommendation, reasoning, and next steps."},
            },
        }
        runtime_config = {
            "provider": "openai",
            "model": "gpt-5-mini",
            "reasoningEffort": "low",
            "maxOutputTokens": 400,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)

            def fake_invoke_provider_json(**kwargs):
                captured["instructions"] = kwargs["instructions"]
                parsed = runtime.new_offline_fixture_direct_baseline_answer(task)
                return self._stub_openai_result(parsed, kwargs.get("max_output_tokens", 400))

            with mock.patch.object(runtime, "invoke_provider_json", side_effect=fake_invoke_provider_json):
                runtime.new_live_direct_baseline(
                    api_key="sk-test",
                    auth_assignments=[],
                    task=task,
                    direct_runtime=runtime_config,
                )

        self.assertIn("Give a decisive but conditional recommendation.", captured["instructions"])
        self.assertIn("Prefer the most detailed factual response the evidence supports.", captured["instructions"])
        self.assertNotIn("up to 7 compact paragraphs is acceptable", captured["instructions"])

    def test_direct_baseline_can_run_with_no_harness(self) -> None:
        captured: dict[str, str] = {}
        task = {
            "taskId": "task-1",
            "objective": "Decide whether to isolate the host immediately.",
            "constraints": ["Do not overclaim."],
            "sessionContext": "none",
            "summarizer": {
                "provider": "openai",
                "model": "gpt-5-mini",
                "harness": {"concision": "none", "instruction": ""},
            },
        }
        runtime_config = {
            "provider": "openai",
            "model": "gpt-5-mini",
            "reasoningEffort": "low",
            "maxOutputTokens": 400,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)

            def fake_invoke_provider_json(**kwargs):
                captured["instructions"] = kwargs["instructions"]
                parsed = runtime.new_offline_fixture_direct_baseline_answer(task)
                return self._stub_openai_result(parsed, kwargs.get("max_output_tokens", 400))

            with mock.patch.object(runtime, "invoke_provider_json", side_effect=fake_invoke_provider_json):
                runtime.new_live_direct_baseline(
                    api_key="sk-test",
                    auth_assignments=[],
                    task=task,
                    direct_runtime=runtime_config,
                )

        self.assertNotIn("structured, methodical, factual operator response", captured["instructions"])
        self.assertNotIn("Keep answer to at most", captured["instructions"])

    def test_invoke_provider_json_supports_ollama_function_tools(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {
                "answer": {"type": "string"},
            },
        }
        request_bodies: list[dict] = []
        responses = [
            {
                "created_at": "2026-04-21T12:34:56Z",
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "get_temperature",
                                "arguments": {"city": "New York"},
                            },
                        }
                    ],
                },
            },
            {
                "created_at": "2026-04-21T12:34:57Z",
                "message": {
                    "content": json.dumps({"answer": "New York is 22C and sunny."}),
                },
            },
        ]

        def fake_urlopen(request, timeout=1800):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return _FakeHTTPResponse(responses.pop(0))

        tool_def = [
            {
                "type": "function",
                "name": "get_temperature",
                "description": "Get the temperature for a city.",
                "parameters": {
                    "type": "object",
                    "required": ["city"],
                    "properties": {
                        "city": {"type": "string"},
                    },
                },
            }
        ]
        handlers = {
            "get_temperature": lambda arguments: (
                {"city": arguments.get("city"), "temperature_c": 22},
                {
                    "summary": "Resolved local temperature.",
                    "path": ".",
                    "sources": [],
                },
            )
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = LoopRuntime(tmpdir)
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = runtime.invoke_provider_json(
                    provider="ollama",
                    api_key="",
                    model="qwen3",
                    reasoning_effort="low",
                    instructions="Return JSON only.",
                    input_text="Say something local.",
                    schema_name="ollama_tool_test",
                    schema=schema,
                    target_kind="worker",
                    tools=tool_def,
                    tool_choice="auto",
                    function_handlers=handlers,
                )

        self.assertEqual(result.provider, "ollama")
        self.assertEqual(result.parsed, {"answer": "New York is 22C and sunny."})
        self.assertEqual(len(result.executed_tools), 1)
        self.assertEqual(result.executed_tools[0]["name"], "get_temperature")
        self.assertEqual(result.executed_tools[0]["arguments"], {"city": "New York"})
        self.assertEqual(request_bodies[0]["tools"][0]["function"]["name"], "get_temperature")
        self.assertTrue(any(message.get("role") == "tool" for message in request_bodies[1]["messages"]))

    def test_invoke_provider_json_rejects_ollama_web_search_tool(self) -> None:
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
                    tools=[{"type": "web_search"}],
                )

        self.assertIn("provider_does_not_support", str(context.exception))
        self.assertIn("web_search", str(context.exception))


if __name__ == "__main__":
    unittest.main()
