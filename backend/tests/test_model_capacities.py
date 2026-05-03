from __future__ import annotations

import unittest

from backend.app import model_capacities


class ModelCapacitiesTest(unittest.TestCase):
    def test_resolve_known_model_capacity(self) -> None:
        entry = model_capacities.resolve_model_capacity("deepseek", "deepseek-v4-flash")
        self.assertEqual(entry.get("contextWindowTokens"), 1_000_000)
        self.assertEqual(entry.get("maxOutputTokens"), 384_000)
        self.assertGreater(int(entry.get("recommendedReviewBinderBudgetTokens", 0) or 0), 0)

    def test_runtime_output_policy_is_centralized(self) -> None:
        self.assertEqual(model_capacities.max_output_tokens("deepseek", "deepseek-v4-flash"), 384_000)
        self.assertEqual(model_capacities.explicit_output_fallback_tokens("anthropic"), 8192)
        self.assertEqual(model_capacities.output_retry_policy("summarizer")["floor"], 2200)

    def test_inferred_budget_for_unknown_compact_model(self) -> None:
        budget = model_capacities.inferred_prompt_budget_tokens("openai", "mystery-mini", "review_binder")
        self.assertEqual(budget, 6000)


if __name__ == "__main__":
    unittest.main()
