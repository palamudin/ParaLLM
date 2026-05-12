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


class CodexLaneTests(unittest.TestCase):
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
        self.assertIn("general_analytics", command)
        self.assertIn("--output-schema", command)
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn("--cd", command)
        self.assertIn("--model", command)
        self.assertIn("gpt-5.3-codex", command)
        self.assertEqual(command[-1], "-")
        self.assertEqual(calls[0]["input"], "Inspect the repo and return the pressure packet.")
        self.assertEqual(calls[0]["timeout"], 123)
        self.assertFalse(calls[0]["shell"])
        self.assertGreaterEqual(calls[0]["creationflags"], 0)

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


if __name__ == "__main__":
    unittest.main()
