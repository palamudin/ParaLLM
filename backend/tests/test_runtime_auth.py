from __future__ import annotations

import io
import json
import tempfile
import urllib.error
import unittest
from pathlib import Path
from unittest import mock

from backend.app.secrets import write_auth_backend_mode_override
from runtime.engine import LoopRuntime, OpenAIResult, RuntimeErrorWithCode, read_api_key_pool


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
                {"id": "A", "label": "Proponent", "role": "utility", "focus": "execution", "model": "gpt-5-mini"},
                {"id": "B", "label": "Sceptic", "role": "adversarial", "focus": "failure modes", "model": "gpt-5-mini"},
            ],
        }
        runtime_config = {
            "provider": "openai",
            "model": "gpt-5-mini",
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
                parsed = runtime.new_mock_commander(task, runtime_config, 1, constraints, prior_summary)
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
                {"id": "A", "label": "Proponent", "role": "utility", "focus": "execution", "model": "gpt-5-mini"},
                {"id": "B", "label": "Sceptic", "role": "adversarial", "focus": "failure modes", "model": "gpt-5-mini"},
            ],
        }
        runtime_config = {
            "provider": "openai",
            "model": "gpt-5-mini",
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
                parsed = runtime.new_mock_commander_review(task, commander_checkpoint, workers, worker_state)
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

    def test_summarizer_packet_drops_worker_lineup_and_lane_catalog_list(self) -> None:
        captured: dict[str, str] = {}
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
        runtime_config = {
            "provider": "openai",
            "model": "gpt-5-mini",
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
                parsed = runtime.new_mock_summary(
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

        self.assertIn("Task brief:", captured["input_text"])
        self.assertNotIn("Worker lineup:", captured["input_text"])
        self.assertNotIn("Known adversarial lane types:", captured["input_text"])

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
                    parsed = runtime.new_mock_checkpoint(
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
                parsed = runtime.new_mock_direct_baseline_answer(task)
                return self._stub_openai_result(parsed, kwargs.get("max_output_tokens", 400))

            with mock.patch.object(runtime, "invoke_provider_json", side_effect=fake_invoke_provider_json):
                runtime.new_live_direct_baseline(
                    api_key="sk-test",
                    auth_assignments=[],
                    task=task,
                    direct_runtime=runtime_config,
                )

        self.assertIn("structured, methodical, factual operator response", captured["instructions"])
        self.assertIn("Use crisp sections for recommendation, reasoning, and next steps.", captured["instructions"])
        self.assertIn("up to 7 compact paragraphs is acceptable", captured["instructions"])

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
                parsed = runtime.new_mock_direct_baseline_answer(task)
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
