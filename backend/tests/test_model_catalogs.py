from __future__ import annotations

import unittest

from runtime.engine import (
    default_model_for_provider,
    normalize_model_id,
    provider_model_catalog,
)


class ModelCatalogTest(unittest.TestCase):
    def test_current_low_tier_models_are_available(self) -> None:
        self.assertIn("claude-haiku-4-5-20251001", provider_model_catalog("anthropic"))
        self.assertIn("deepseek-v4-flash", provider_model_catalog("deepseek"))
        self.assertIn("Qwen3.8-27B:latest", provider_model_catalog("ollama"))

    def test_provider_defaults_are_selectable(self) -> None:
        for provider, catalog in (
            ("anthropic", provider_model_catalog("anthropic")),
            ("deepseek", provider_model_catalog("deepseek")),
        ):
            self.assertIn(default_model_for_provider(provider), catalog)

    def test_legacy_models_migrate_without_staying_selectable(self) -> None:
        self.assertNotIn("deepseek-chat", provider_model_catalog("deepseek"))
        self.assertNotIn("deepseek-reasoner", provider_model_catalog("deepseek"))
        self.assertEqual(normalize_model_id("deepseek-chat", provider="deepseek"), "deepseek-v4-flash")
        self.assertEqual(normalize_model_id("deepseek-reasoner", provider="deepseek"), "deepseek-v4-pro")
        self.assertEqual(
            normalize_model_id("claude-sonnet-4-20250514", provider="anthropic"),
            "claude-sonnet-4-6",
        )

    def test_catalog_ids_are_canonicalized_case_insensitively(self) -> None:
        self.assertEqual(normalize_model_id("GPT-5.6-LUNA", provider="openai"), "gpt-5.6-luna")


if __name__ == "__main__":
    unittest.main()
