from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from backend.app import codex_lanes


class _CompletedProcess:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _FakeSseResponse:
    def __init__(self, events: list[dict], status: int = 200) -> None:
        self.status = status
        self.code = status
        self._lines = [f"data: {json.dumps(event)}\n".encode("utf-8") for event in events]

    def __enter__(self) -> "_FakeSseResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def __iter__(self):
        return iter(self._lines)


class CodexLaneTests(unittest.TestCase):
    def test_direct_chatgpt_response_uses_in_process_sse_transport(self) -> None:
        captured: dict = {}
        output_text = '{"result":"DIRECT_OK"}'
        completed_response = {
            "id": "resp-direct-1",
            "status": "completed",
            "model": "gpt-5.6-luna",
            "usage": {"input_tokens": 11, "output_tokens": 4, "total_tokens": 15},
        }

        def fake_opener(request, **kwargs):
            captured["request"] = request
            captured.update(kwargs)
            return _FakeSseResponse(
                [
                    {"type": "response.output_text.done", "text": output_text},
                    {"type": "response.completed", "response": completed_response},
                ]
            )

        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["result"],
            "properties": {"result": {"type": "string"}},
        }
        with mock.patch.dict(
            os.environ,
            {"CODEX_ACCESS_TOKEN": "test-access-token", "CODEX_CHATGPT_ACCOUNT_ID": "test-account"},
            clear=False,
        ):
            result = codex_lanes.run_codex_chatgpt_response(
                model="gpt-5.6-luna",
                instructions="Return the result.",
                input_text="Confirm direct transport.",
                schema_name="direct response",
                output_schema=schema,
                reasoning_effort="medium",
                max_output_tokens=1200,
                timeout_seconds=42,
                subagents_enabled=False,
                opener=fake_opener,
            )

        request = captured["request"]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(result["outputText"], output_text)
        self.assertEqual(result["responseId"], "resp-direct-1")
        self.assertEqual(result["authSource"], "codex_environment")
        self.assertEqual(captured["timeout"], 42)
        self.assertEqual(request.full_url, codex_lanes.CODEX_CHATGPT_RESPONSES_URL)
        self.assertEqual(request.get_header("Chatgpt-account-id"), "test-account")
        self.assertEqual(body["text"]["format"]["name"], "direct_response")
        self.assertNotIn("max_output_tokens", body)
        self.assertFalse(body["store"])
        self.assertTrue(body["stream"])
        self.assertIn("without delegation", body["instructions"])

    def test_direct_chatgpt_response_reads_inherited_auth_file(self) -> None:
        with tempfile.TemporaryDirectory() as codex_home:
            home = Path(codex_home)
            (home / "auth.json").write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgpt",
                        "tokens": {"access_token": "file-token", "account_id": "file-account"},
                    }
                ),
                encoding="utf-8",
            )
            seen_headers: dict = {}

            def fake_opener(request, **_kwargs):
                seen_headers.update(dict(request.header_items()))
                return _FakeSseResponse(
                    [{"type": "response.output_text.done", "text": '{"answer":"ok"}'}]
                )

            with mock.patch.dict(
                os.environ,
                {"CODEX_HOME": str(home), "CODEX_ACCESS_TOKEN": "", "CODEX_CHATGPT_ACCOUNT_ID": ""},
                clear=False,
            ):
                result = codex_lanes.run_codex_chatgpt_response(
                    model="gpt-5.6-luna",
                    instructions="Return JSON.",
                    input_text="Question?",
                    schema_name="answer",
                    output_schema={"type": "object"},
                    opener=fake_opener,
                )

        self.assertEqual(result["authSource"], "codex_current_user")
        self.assertIn("Bearer file-token", seen_headers.values())

    def test_configured_timeout_preserves_explicit_zero(self) -> None:
        self.assertEqual(codex_lanes._configured_timeout_seconds({"timeoutSeconds": 0}), 0)
        self.assertEqual(codex_lanes._configured_timeout_seconds({"timeout_seconds": 0}), 0)
        self.assertEqual(codex_lanes._configured_timeout_seconds({}), 900)

    def test_default_output_schema_is_codex_strict(self) -> None:
        schema = codex_lanes.DEFAULT_CODEX_LANE_OUTPUT_SCHEMA
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(set(schema["required"]), set(schema["properties"]))

    def test_parse_codex_jsonl_usage_and_cost(self) -> None:
        jsonl = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": '{"verdict":"caution"}'}}),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 24763,
                            "cached_input_tokens": 24448,
                            "output_tokens": 122,
                            "reasoning_output_tokens": 10,
                        },
                    }
                ),
            ]
        )

        artifact = codex_lanes.codex_artifact_from_jsonl(
            jsonl,
            lane_id="codex_adversarial",
            model="gpt-5.3-codex",
        )

        self.assertEqual(artifact["threadId"], "thread-1")
        self.assertEqual(artifact["responseText"], '{"verdict":"caution"}')
        self.assertEqual(artifact["usage"]["inputTokens"], 24763)
        self.assertEqual(artifact["usage"]["cachedInputTokens"], 24448)
        self.assertEqual(artifact["usage"]["billableInputTokens"], 315)
        self.assertEqual(artifact["usage"]["outputTokens"], 122)
        self.assertEqual(artifact["usage"]["reasoningTokens"], 10)
        self.assertEqual(artifact["usage"]["totalTokens"], 24885)
        self.assertAlmostEqual(artifact["usage"]["estimatedCostUsd"], 0.006538, places=6)
        self.assertTrue(artifact["usage"]["pricingKnown"])

    def test_run_codex_lane_uses_json_read_only_exec_and_hidden_window(self) -> None:
        calls: list[dict] = []
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-run"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
            ]
        )

        def fake_runner(cmd, **kwargs):
            calls.append({"cmd": cmd, **kwargs})
            return _CompletedProcess(stdout=stdout)

        with tempfile.TemporaryDirectory() as tmpdir:
            request = codex_lanes.CodexLaneRequest(
                lane_id="codex_commander",
                prompt="Inspect the repo and return the pressure packet.",
                root=Path(tmpdir),
                model="gpt-5.3-codex",
                reasoning_effort="medium",
                timeout_seconds=123,
            )
            artifact = codex_lanes.run_codex_lane(request, runner=fake_runner)

        self.assertEqual(artifact["status"], "completed")
        self.assertEqual(artifact["responseText"], "done")
        self.assertEqual(len(calls), 1)
        command = calls[0]["cmd"]
        self.assertEqual(command[:2], ["codex", "exec"])
        self.assertIn("--json", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        self.assertEqual(command.count("--disable"), 2)
        self.assertIn("plugins", command)
        self.assertIn("multi_agent", command)
        self.assertIn("agents.enabled=false", command)
        self.assertIn('model_reasoning_effort="medium"', command)
        self.assertNotIn("general_analytics", command)
        self.assertIn("--output-schema", command)
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn("--cd", command)
        self.assertIn("--model", command)
        self.assertIn("gpt-5.3-codex", command)
        self.assertEqual(command[-1], "-")
        self.assertIn("Inspect the repo and return the pressure packet.", calls[0]["input"])
        self.assertIn("Nested Codex subagents are disabled", calls[0]["input"])
        self.assertEqual(calls[0]["timeout"], 123)
        self.assertFalse(calls[0]["shell"])
        self.assertGreaterEqual(calls[0]["creationflags"], 0)
        self.assertEqual(calls[0]["encoding"], "utf-8")
        self.assertEqual(calls[0]["errors"], "replace")

    def test_run_codex_lane_can_enable_nested_subagents(self) -> None:
        calls: list[dict] = []

        def fake_runner(cmd, **kwargs):
            calls.append({"cmd": cmd, **kwargs})
            return _CompletedProcess(
                stdout=json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}})
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            request = codex_lanes.CodexLaneRequest(
                lane_id="codex_enabled",
                prompt="Return done.",
                root=Path(tmpdir),
                subagents_enabled=True,
            )
            artifact = codex_lanes.run_codex_lane(request, runner=fake_runner)

        self.assertEqual(artifact["status"], "completed")
        self.assertIn("--enable", calls[0]["cmd"])
        self.assertIn("multi_agent", calls[0]["cmd"])
        self.assertIn("agents.enabled=true", calls[0]["cmd"])
        self.assertIn("Nested Codex subagents are enabled", calls[0]["input"])
        self.assertTrue(artifact["limits"]["localBudget"]["subagentsEnabled"])

    def test_run_codex_lane_can_disable_subprocess_timeout(self) -> None:
        calls: list[dict] = []
        stdout = "\n".join(
            [
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
            ]
        )

        def fake_runner(cmd, **kwargs):
            calls.append({"cmd": cmd, **kwargs})
            return _CompletedProcess(stdout=stdout)

        with tempfile.TemporaryDirectory() as tmpdir:
            request = codex_lanes.CodexLaneRequest(
                lane_id="codex_unbounded",
                prompt="Return done.",
                root=Path(tmpdir),
                timeout_seconds=0,
            )
            artifact = codex_lanes.run_codex_lane(request, runner=fake_runner)

        self.assertEqual(artifact["status"], "completed")
        self.assertIsNone(calls[0]["timeout"])
        self.assertIsNone(artifact["limits"]["localBudget"]["timeoutSeconds"])
        self.assertTrue(artifact["limits"]["localBudget"]["timeoutDisabled"])

    def test_run_codex_lane_prepends_configured_pwsh_to_child_path(self) -> None:
        calls: list[dict] = []
        stdout = "\n".join(
            [
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
            ]
        )

        def fake_runner(cmd, **kwargs):
            calls.append({"cmd": cmd, **kwargs})
            return _CompletedProcess(stdout=stdout)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pwsh_path = root / "PowerShell" / "pwsh.exe"
            pwsh_path.parent.mkdir()
            pwsh_path.write_bytes(b"test executable")
            request = codex_lanes.CodexLaneRequest(
                lane_id="codex_reliability",
                prompt="Return a pressure packet.",
                root=root,
            )
            with mock.patch.dict(os.environ, {codex_lanes.CODEX_PWSH_PATH_ENV: str(pwsh_path)}, clear=False):
                artifact = codex_lanes.run_codex_lane(request, runner=fake_runner)

        self.assertEqual(artifact["status"], "completed")
        self.assertEqual(calls[0]["env"][codex_lanes.CODEX_PWSH_PATH_ENV], str(pwsh_path.resolve()))
        self.assertEqual(Path(calls[0]["env"]["PATH"].split(os.pathsep)[0]), pwsh_path.parent.resolve())

    def test_run_codex_lane_blocks_prompt_that_exceeds_local_token_budget(self) -> None:
        def runner_should_not_be_called(*args, **kwargs):
            raise AssertionError("Codex runner should not be called when the preflight budget blocks the lane.")

        request = codex_lanes.CodexLaneRequest(
            lane_id="codex_adversarial",
            prompt="x" * 1000,
            root=Path("."),
            model="gpt-5.3-codex",
            max_total_tokens=10,
        )

        artifact = codex_lanes.run_codex_lane(request, runner=runner_should_not_be_called)

        self.assertEqual(artifact["status"], "budget_blocked")
        self.assertIn("estimated prompt tokens", artifact["limits"]["reasons"][0])
        self.assertEqual(artifact["usage"]["totalTokens"], 0)

    def test_run_codex_lane_marks_post_run_budget_exhausted(self) -> None:
        stdout = "\n".join(
            [
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 120, "output_tokens": 90}}),
            ]
        )

        def fake_runner(_cmd, **_kwargs):
            return _CompletedProcess(stdout=stdout)

        request = codex_lanes.CodexLaneRequest(
            lane_id="codex_reliability",
            prompt="short",
            root=Path("."),
            model="gpt-5.3-codex",
            max_total_tokens=100,
        )

        artifact = codex_lanes.run_codex_lane(request, runner=fake_runner)

        self.assertEqual(artifact["status"], "budget_exhausted")
        self.assertIn("observed tokens", " ".join(artifact["limits"]["reasons"]))

    def test_run_codex_lane_rejects_empty_success_output(self) -> None:
        def fake_runner(_cmd, **_kwargs):
            return _CompletedProcess(stdout="", stderr="transport ended without a result", returncode=0)

        request = codex_lanes.CodexLaneRequest(
            lane_id="codex_reliability",
            prompt="Return a pressure packet.",
            root=Path("."),
            model="gpt-5.6-luna",
        )

        artifact = codex_lanes.run_codex_lane(request, runner=fake_runner)

        self.assertEqual(artifact["status"], "error")
        self.assertEqual(artifact["eventCount"], 0)
        self.assertIn("no JSONL events", " ".join(artifact["warnings"]))
        self.assertIn("transport ended without a result", " ".join(artifact["warnings"]))

    def test_run_codex_arm_persists_openai_agent_artifact_with_user_config(self) -> None:
        calls: list[dict] = []
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-arm"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": '{"verdict":"investigate"}'}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 50, "cached_input_tokens": 10, "output_tokens": 20}}),
            ]
        )

        def fake_runner(cmd, **kwargs):
            calls.append({"cmd": cmd, **kwargs})
            return _CompletedProcess(stdout=stdout)

        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as codex_home:
            root = Path(tmpdir)
            home = Path(codex_home)
            (home / "auth.json").write_text(json.dumps({"mode": "chatgpt", "test": True}), encoding="utf-8")
            data = root / "data"
            data.mkdir(parents=True, exist_ok=True)
            (data / "state.json").write_text(
                json.dumps(
                    {
                        "draft": {
                            "provider": "openai",
                            "objective": "Use the Codex arm to pressure test the staged plan.",
                            "constraints": ["read-only", "return artifact"],
                        }
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"CODEX_HOME": str(home)}):
                result = codex_lanes.run_codex_arm(
                    root,
                    {
                        "laneId": "codex_adversarial",
                        "providerFamily": "openai",
                        "model": "gpt-5.4",
                        "objective": "Check the current plan for structural risks.",
                    },
                    runner=fake_runner,
                )

            stored_path = root / "data" / "outputs" / result["artifactFile"]
            stored = json.loads(stored_path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["providerFamily"], "openai")
        self.assertEqual(result["provider"], "codex_cli")
        self.assertEqual(result["interface"], "codex_cli_exec")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["artifactMeta"]["category"], "outputs")
        self.assertEqual(stored["artifactType"], "codex_lane")
        self.assertEqual(stored["providerFamily"], "openai")
        self.assertEqual(stored["arm"]["provider"], "codex_cli")
        self.assertTrue(stored["arm"]["extensionLike"])
        self.assertEqual(stored["output"]["threadId"], "thread-arm")
        self.assertIn("Use the Codex arm", stored["input"]["state"]["draft"]["objective"])
        self.assertIn("Check the current plan", calls[0]["input"])
        command = calls[0]["cmd"]
        self.assertNotIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertEqual(command[-1], "-")

    def test_run_codex_arm_rejects_when_codex_auth_is_disabled(self) -> None:
        def runner_should_not_be_called(*args, **kwargs):
            raise AssertionError("Codex runner should not be called when Codex auth is disabled.")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            codex_lanes.save_codex_auth_policy(root, {"mode": "disabled"})
            result = codex_lanes.run_codex_arm(
                root,
                {"laneId": "codex_adversarial", "providerFamily": "openai", "objective": "Should not run."},
                runner=runner_should_not_be_called,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "rejected")
        self.assertIn("disabled", result["message"].lower())

    def test_run_codex_arm_can_use_api_key_billing_mode_without_user_config(self) -> None:
        calls: list[dict] = []
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-app-key"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 20, "output_tokens": 5}}),
            ]
        )

        def fake_runner(cmd, **kwargs):
            calls.append({"cmd": cmd, **kwargs})
            return _CompletedProcess(stdout=stdout)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "Auth.txt").write_text("openai:sk-app-codex-1234\n", encoding="utf-8")
            codex_lanes.save_codex_auth_policy(root, {"mode": "api_key"})
            with mock.patch.dict(os.environ, {"LOOP_SECRET_BACKEND": "local_file"}, clear=False):
                result = codex_lanes.run_codex_arm(
                    root,
                    {
                        "laneId": "codex_commander",
                        "providerFamily": "openai",
                        "model": "gpt-5.4",
                        "objective": "Use app-managed auth.",
                    },
                    runner=fake_runner,
                )
            stored_path = root / "data" / "outputs" / result["artifactFile"]
            stored = json.loads(stored_path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(stored["input"]["authMode"], "api_key")
        self.assertTrue(stored["input"]["apiKeyBillingMode"])
        command = calls[0]["cmd"]
        self.assertIn("--ignore-user-config", command)
        self.assertIn("env", calls[0])
        self.assertEqual(calls[0]["env"]["OPENAI_API_KEY"], "sk-app-codex-1234")
        self.assertNotIn("sk-app-codex-1234", json.dumps(stored))

    def test_run_codex_arm_rejects_non_openai_provider_family(self) -> None:
        def runner_should_not_be_called(*args, **kwargs):
            raise AssertionError("Codex arm should not launch for non-OpenAI provider families.")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = codex_lanes.run_codex_arm(
                Path(tmpdir),
                {"laneId": "codex_adversarial", "providerFamily": "anthropic", "objective": "Wrong provider family."},
                runner=runner_should_not_be_called,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "rejected")
        self.assertIn("OpenAI", result["message"])

    def test_codex_limits_status_reads_catalog_public_limits_and_manual_limits(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as codex_home:
            root = Path(root_dir)
            home = Path(codex_home)
            (root / "data").mkdir(parents=True, exist_ok=True)
            (home / "models_cache.json").write_text(
                json.dumps(
                    {
                        "fetched_at": "2026-05-05T18:06:58Z",
                        "client_version": "0.124.0",
                        "models": [
                            {
                                "slug": "gpt-5.3-codex",
                                "display_name": "GPT-5.3-Codex",
                                "context_window": 272000,
                                "max_context_window": 400000,
                                "effective_context_window_percent": 95,
                                "default_reasoning_level": "medium",
                                "supported_reasoning_levels": [{"effort": "low"}, {"effort": "xhigh"}],
                                "supports_reasoning_summaries": True,
                                "supported_in_api": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            codex_lanes.save_manual_codex_limits(
                root,
                {
                    "general": {"label": "General Codex", "limit": "80%", "resetWindow": "weekly", "notes": "from Codex settings"},
                    "models": {"gpt-5.3-codex": {"limit": "50%", "resetWindow": "5h"}},
                },
            )

            with mock.patch.dict(os.environ, {"CODEX_HOME": str(home)}):
                status = codex_lanes.codex_limits_status(root, model="gpt-5.3-codex")

        self.assertEqual(status["provider"], "codex_cli")
        self.assertEqual(status["selectedModel"], "gpt-5.3-codex")
        self.assertEqual(status["auth"]["policy"]["mode"], "inherit_chatgpt")
        self.assertEqual(status["catalog"]["source"], str(home / "models_cache.json"))
        self.assertEqual(status["catalog"]["selectedModel"]["displayName"], "GPT-5.3-Codex")
        self.assertEqual(status["catalog"]["selectedModel"]["contextWindow"], 272000)
        self.assertEqual(status["pricing"]["inputPer1M"], 1.75)
        self.assertEqual(status["publicModelLimits"]["contextWindow"], 400000)
        self.assertEqual(status["publicModelLimits"]["tiers"][0]["rpm"], 500)
        self.assertEqual(status["manualAccountLimits"]["general"]["limit"], "80%")
        self.assertEqual(status["manualAccountLimits"]["models"]["gpt-5.3-codex"]["resetWindow"], "5h")
        self.assertFalse(status["projectRateLimits"]["known"])
        self.assertGreater(status["measured"]["lastSmoke"]["inputTokens"], 0)

    def test_codex_auth_policy_status_tracks_app_key_and_inherited_auth(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as codex_home:
            root = Path(root_dir)
            home = Path(codex_home)
            (home / "auth.json").write_text("{}", encoding="utf-8")
            (root / "Auth.txt").write_text("openai:sk-app-codex-1234\n", encoding="utf-8")
            saved = codex_lanes.save_codex_auth_policy(root, {"mode": "api_key"})

            with mock.patch.dict(os.environ, {"CODEX_HOME": str(home), "LOOP_SECRET_BACKEND": "local_file"}):
                status = codex_lanes.codex_limits_status(root, model="gpt-5.4")

        self.assertTrue(saved["ok"])
        self.assertEqual(status["auth"]["policy"]["mode"], "api_key")
        self.assertTrue(status["auth"]["inheritedChatGpt"]["available"])
        self.assertTrue(status["auth"]["appOpenAIKey"]["available"])
        self.assertEqual(status["auth"]["appOpenAIKey"]["last4"], "1234")

    def test_codex_limits_status_surfaces_missing_catalog_without_failing(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                status = codex_lanes.codex_limits_status(Path(root_dir), model="gpt-5.4")

        self.assertEqual(status["selectedModel"], "gpt-5.4")
        self.assertFalse(status["catalog"]["exists"])
        self.assertEqual(status["catalog"]["selectedModel"], {})
        self.assertEqual(status["publicModelLimits"]["contextWindow"], 1050000)

    def test_codex_limits_status_exposes_gpt_56_family_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                sol = codex_lanes.codex_limits_status(Path(root_dir), model="gpt-5.6-sol")
                luna = codex_lanes.codex_limits_status(Path(root_dir), model="gpt-5.6-luna")

        self.assertEqual(sol["pricing"]["inputPer1M"], 4.0)
        self.assertEqual(sol["pricing"]["outputPer1M"], 20.0)
        self.assertEqual(sol["publicModelLimits"]["contextWindow"], 1_050_000)
        self.assertEqual(sol["publicModelLimits"]["maxOutputTokens"], 128_000)
        self.assertEqual(luna["pricing"]["inputPer1M"], 0.2)
        self.assertEqual(luna["pricing"]["outputPer1M"], 1.2)
        self.assertEqual(luna["publicModelLimits"]["tiers"][-1]["rpm"], 30_000)


if __name__ == "__main__":
    unittest.main()
