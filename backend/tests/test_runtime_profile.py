from __future__ import annotations

import unittest

from scripts.profile_runtime_models import summarize_spans


class RuntimeProfileTests(unittest.TestCase):
    def test_para_owned_time_uses_outer_target_boundary(self) -> None:
        summary = summarize_spans(
            [
                {"component": "pipeline", "stage": "target.commander", "durationMs": 120.0, "coreMode": "dual"},
                {"component": "provider", "stage": "openai.call", "durationMs": 90.0, "coreMode": "dual"},
                {"component": "storage", "stage": "state.read", "durationMs": 4.0, "coreMode": "dual"},
                {"component": "memory", "stage": "knowledgebase.recall", "durationMs": 6.0, "coreMode": "dual"},
            ]
        )

        self.assertEqual(summary["pipelineTargetWallMs"], 120.0)
        self.assertEqual(summary["providerSpanMs"], 90.0)
        self.assertEqual(summary["paraOwnedTargetWallMs"], 30.0)
        self.assertEqual(summary["storageWorkMs"], 4.0)
        self.assertEqual(summary["memoryWorkMs"], 6.0)
        self.assertEqual(summary["sumOfNestedSpanMs"], 220.0)

    def test_unfinished_pipeline_is_not_invented_from_nested_work(self) -> None:
        summary = summarize_spans(
            [
                {"component": "storage", "stage": "state.write", "durationMs": 5.0, "coreMode": "python"},
            ]
        )

        self.assertEqual(summary["pipelineTargetWallMs"], 0.0)
        self.assertEqual(summary["paraOwnedTargetWallMs"], 0.0)


if __name__ == "__main__":
    unittest.main()
