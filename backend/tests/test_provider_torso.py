from __future__ import annotations

import unittest
from unittest import mock

from runtime.provider_torso import (
    AUTH_ROUTE_API_KEY,
    AUTH_ROUTE_CODEX_CURRENT_USER,
    MODEL_SOURCE_CODEX_AUTH,
    TRANSPORT_ANTHROPIC_MESSAGES,
    TRANSPORT_CODEX_RESPONSES,
    TRANSPORT_OPENAI_CHAT,
    TRANSPORT_XAI_RESPONSES,
    capability_manifest,
    default_provider_id,
    merge_endpoint_override,
    model_catalog_manifest,
    model_capabilities,
    model_supports_auth_route,
    provider_capabilities,
    provider_catalog,
    provider_default_auth_route,
    provider_default_model,
    provider_model_aliases,
    provider_supports_auth_route,
    resolve_lane_process,
)


class ProviderTorsoTests(unittest.TestCase):
    def test_openai_auth_source_changes_transport_not_lane_contract(self) -> None:
        api = resolve_lane_process(
            "openai",
            "gpt-5.4-mini",
            "high",
            auth_route=AUTH_ROUTE_API_KEY,
        )
        codex = resolve_lane_process(
            "openai",
            "gpt-5.4-mini",
            "high",
            {"modelSource": MODEL_SOURCE_CODEX_AUTH},
        )

        self.assertNotEqual(api.transport, codex.transport)
        self.assertEqual(codex.transport, TRANSPORT_CODEX_RESPONSES)
        self.assertEqual(codex.auth_route, AUTH_ROUTE_CODEX_CURRENT_USER)
        self.assertEqual(api.reasoning_effort, codex.reasoning_effort)
        self.assertEqual(api.endpoint, "https://api.openai.com/v1/responses")
        self.assertEqual(codex.endpoint, "https://chatgpt.com/backend-api/codex/responses")

    def test_gpt_54_pro_capabilities_are_data_driven(self) -> None:
        process = resolve_lane_process("openai", "gpt-5.4-pro", "low")

        self.assertEqual(process.reasoning_effort, "medium")
        self.assertFalse(process.capabilities.supports_structured_output)
        self.assertEqual(process.capabilities.structured_output_mode, "prompted_json")

    def test_wire_dialects_are_capabilities_not_provider_branches(self) -> None:
        deepseek = resolve_lane_process("deepseek", "deepseek-v4-flash", "high")
        minimax = resolve_lane_process("minimax", "MiniMax-M3", "high")
        kimi = resolve_lane_process("kimi", "k3", "none")
        grok = resolve_lane_process("xai", "grok-4.5", "xhigh")

        self.assertEqual(deepseek.capabilities.reasoning_wire_format, "direct")
        self.assertEqual(deepseek.capabilities.structured_output_mode, "json_object")
        self.assertTrue(minimax.capabilities.strip_leading_think_blocks)
        self.assertEqual(kimi.capabilities.reasoning_wire_format, "kimi")
        self.assertEqual(kimi.reasoning_effort, "low")
        self.assertEqual(grok.reasoning_effort, "high")

    def test_xai_continuation_and_multi_agent_tool_limits_are_explicit(self) -> None:
        regular = resolve_lane_process(
            "xai",
            "grok-4.20-0309-reasoning",
            "xhigh",
            tools_requested=True,
            include=["no_inline_citations", "reasoning.encrypted_content"],
        )
        multi_agent = resolve_lane_process(
            "xai",
            "grok-4.20-multi-agent-0309",
            "high",
            tools_requested=True,
        )

        self.assertEqual(regular.transport, TRANSPORT_XAI_RESPONSES)
        self.assertEqual(regular.reasoning_effort, "none")
        self.assertFalse(regular.capabilities.supports_instructions_on_continuation)
        self.assertEqual(regular.include, ("no_inline_citations",))
        self.assertTrue(regular.tools_enabled)
        self.assertFalse(multi_agent.tools_enabled)

    def test_compatible_and_fallback_protocols_are_resolved_from_variables(self) -> None:
        deepseek = resolve_lane_process("deepseek", "deepseek-v4-flash", "low")
        fallback = resolve_lane_process(
            "minimax",
            "MiniMax-M3",
            "low",
            {"minimaxTransport": "anthropic"},
        )

        self.assertEqual(deepseek.transport, TRANSPORT_OPENAI_CHAT)
        self.assertEqual(fallback.transport, TRANSPORT_ANTHROPIC_MESSAGES)
        self.assertEqual(deepseek.endpoint, "https://api.deepseek.com/chat/completions")
        self.assertEqual(fallback.endpoint, "https://api.minimax.io/anthropic/v1/messages")

    def test_endpoint_and_transport_overrides_are_contract_driven(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "LOOP_MINIMAX_TRANSPORT": "anthropic",
                "LOOP_MINIMAX_ANTHROPIC_BASE_URL": "http://127.0.0.1:9123/anthropic",
            },
            clear=False,
        ):
            process = resolve_lane_process("minimax", "MiniMax-M3", "low")

        self.assertEqual(process.transport, TRANSPORT_ANTHROPIC_MESSAGES)
        self.assertEqual(process.endpoint, "http://127.0.0.1:9123/anthropic/v1/messages")

    def test_endpoint_override_can_be_a_base_or_complete_endpoint(self) -> None:
        canonical = "https://api.kimi.com/coding/v1/chat/completions"

        self.assertEqual(
            merge_endpoint_override(canonical, "http://127.0.0.1:9000/coding/v1"),
            "http://127.0.0.1:9000/coding/v1/chat/completions",
        )
        self.assertEqual(
            merge_endpoint_override(canonical, "http://127.0.0.1:9000/coding/v1/chat/completions"),
            "http://127.0.0.1:9000/coding/v1/chat/completions",
        )

    def test_provider_catalog_projects_contract_endpoints_and_auth_defaults(self) -> None:
        catalog = provider_catalog()

        self.assertEqual(catalog["xai"]["defaultEndpoint"], "https://api.x.ai/v1/responses")
        self.assertEqual(catalog["kimi"]["defaultApiKeyEnvironment"], "KIMI_API_KEY")
        self.assertEqual(catalog["openai"]["defaultAuthRoute"], AUTH_ROUTE_CODEX_CURRENT_USER)
        self.assertEqual(catalog["openai"]["defaultJudgeAuthRoute"], AUTH_ROUTE_API_KEY)
        self.assertEqual(catalog["openai"]["defaultModelByAuthRoute"][AUTH_ROUTE_API_KEY], "gpt-5-mini")
        self.assertEqual(
            catalog["openai"]["defaultModelByAuthRoute"][AUTH_ROUTE_CODEX_CURRENT_USER],
            "gpt-5.6-sol",
        )

    def test_contract_defaults_resolve_to_declared_provider_routes(self) -> None:
        self.assertEqual(default_provider_id(), "openai")
        self.assertEqual(default_provider_id(judge=True), "openai")

        for provider in provider_catalog():
            with self.subTest(provider=provider, role="lane"):
                route = provider_default_auth_route(provider)
                self.assertTrue(provider_supports_auth_route(provider, route))
                model = provider_default_model(provider, auth_route=route)
                self.assertTrue(model_supports_auth_route(provider, model, route))
            with self.subTest(provider=provider, role="judge"):
                route = provider_default_auth_route(provider, judge=True)
                self.assertTrue(provider_supports_auth_route(provider, route))
                model = provider_default_model(provider, auth_route=route, judge=True)
                self.assertTrue(model_supports_auth_route(provider, model, route))

    def test_api_only_model_infers_compatible_route_when_route_is_unspecified(self) -> None:
        process = resolve_lane_process("openai", "gpt-5-mini", "high")

        self.assertEqual(process.auth_route, AUTH_ROUTE_API_KEY)
        self.assertEqual(process.transport, "openai_responses")

    def test_local_default_model_can_be_supplied_by_environment(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "LOOP_OLLAMA_DEFAULT_MODEL": "deployment-worker",
                "LOOP_OLLAMA_DEFAULT_JUDGE_MODEL": "deployment-judge",
            },
            clear=False,
        ):
            self.assertEqual(provider_default_model("ollama"), "deployment-worker")
            self.assertEqual(provider_default_model("ollama", judge=True), "deployment-judge")

    def test_local_qwen_default_is_selectable_through_the_shared_factory(self) -> None:
        catalog = provider_catalog()
        process = resolve_lane_process("ollama", "parallm-qwen3.8-27b:latest", "high")

        self.assertEqual(catalog["ollama"]["status"], "primary")
        self.assertFalse(catalog["ollama"]["credentialRequired"])
        self.assertEqual(catalog["ollama"]["defaultModel"], "parallm-qwen3.8-27b:latest")
        self.assertEqual(process.provider, "ollama")
        self.assertEqual(process.model, "parallm-qwen3.8-27b:latest")
        self.assertEqual(process.transport, "ollama_json")
        self.assertEqual(process.endpoint, "http://127.0.0.1:11434")
        self.assertTrue(process.capabilities.supports_client_tools)

        raw_process = resolve_lane_process("ollama", "Qwen3.8-27B:latest", "high", tools_requested=True)
        self.assertFalse(raw_process.capabilities.supports_client_tools)
        self.assertFalse(raw_process.tools_enabled)

    def test_empty_model_uses_auth_route_default_before_process_resolution(self) -> None:
        api = resolve_lane_process("openai", "", "high", auth_route=AUTH_ROUTE_API_KEY)
        codex = resolve_lane_process(
            "openai",
            "",
            "high",
            auth_route=AUTH_ROUTE_CODEX_CURRENT_USER,
        )

        self.assertEqual(api.model, "gpt-5-mini")
        self.assertEqual(codex.model, "gpt-5.6-sol")
        self.assertEqual(api.transport, "openai_responses")
        self.assertEqual(codex.transport, TRANSPORT_CODEX_RESPONSES)

    def test_quality_profiles_are_resolvable_factory_inputs(self) -> None:
        for provider, definition in provider_catalog().items():
            for profile, lanes in definition["qualityProfiles"].items():
                for lane, model in lanes.items():
                    with self.subTest(provider=provider, profile=profile, lane=lane, model=model):
                        process = resolve_lane_process(provider, model, "xhigh")
                        self.assertEqual(process.provider, provider)
                        self.assertEqual(process.model, model)

    def test_custom_model_policy_is_a_canonical_capability(self) -> None:
        custom = resolve_lane_process("ollama", "locally-built-model", "high")

        self.assertEqual(custom.model, "locally-built-model")
        self.assertTrue(provider_capabilities("ollama").allows_custom_models)
        with self.assertRaisesRegex(ValueError, "does not allow undeclared model"):
            resolve_lane_process("openai", "unlisted-openai-model", "high")

    def test_context_and_compression_traits_are_model_capabilities(self) -> None:
        self.assertTrue(model_capabilities("openai", "gpt-5-mini").prefers_compact_context)
        self.assertFalse(model_capabilities("openai", "gpt-5.4").prefers_compact_context)
        self.assertTrue(provider_capabilities("deepseek").prefers_compact_context)
        self.assertTrue(provider_capabilities("openai").supports_server_input_autocompress)
        self.assertFalse(provider_capabilities("anthropic").supports_server_input_autocompress)

    def test_model_alias_resolves_to_the_contract_model_id(self) -> None:
        process = resolve_lane_process("deepseek", "deepseek-chat", "high")

        self.assertEqual(process.model, "deepseek-v4-flash")

    def test_every_declared_model_and_auth_route_resolves_through_one_factory(self) -> None:
        manifest = model_catalog_manifest()

        for model in manifest["models"]:
            provider = model["provider"]
            model_id = model["id"]
            for auth_route in model["authRoutes"]:
                with self.subTest(provider=provider, model=model_id, auth_route=auth_route):
                    process = resolve_lane_process(
                        provider,
                        model_id,
                        "xhigh",
                        tools_requested=True,
                        auth_route=auth_route,
                    )
                    self.assertEqual(process.provider, provider)
                    self.assertEqual(process.model, model_id)
                    self.assertEqual(process.auth_route, auth_route)
                    self.assertTrue(process.transport)
                    self.assertTrue(process.endpoint)
                    self.assertIn(process.reasoning_effort, process.capabilities.supported_reasoning_efforts)
                    self.assertEqual(
                        process.tools_enabled,
                        process.capabilities.supports_client_tools,
                    )

    def test_every_alias_resolves_to_its_canonical_model(self) -> None:
        for provider, aliases in provider_model_aliases().items():
            for alias, canonical in aliases.items():
                with self.subTest(provider=provider, alias=alias):
                    process = resolve_lane_process(provider, alias, "high")
                    self.assertEqual(process.model, canonical)

    def test_invalid_provider_or_model_auth_route_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not support auth route"):
            resolve_lane_process(
                "anthropic",
                "claude-sonnet-5",
                "high",
                auth_route="codex_current_user",
            )
        with self.assertRaisesRegex(ValueError, "does not support auth route"):
            resolve_lane_process(
                "openai",
                "gpt-5.6-luna",
                "high",
                auth_route="api_key",
            )

    def test_manifest_is_machine_readable(self) -> None:
        manifest = capability_manifest()

        self.assertEqual(manifest["schemaVersion"], "parallm.provider-torso-capabilities.v1")
        self.assertIn(AUTH_ROUTE_CODEX_CURRENT_USER, manifest["authRoutes"])
        self.assertIn("openai", manifest["transports"])
        self.assertIn("xai/grok-4.20-multi-agent-0309", manifest["modelOverrides"])


if __name__ == "__main__":
    unittest.main()
