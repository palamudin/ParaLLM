from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import run_vetting_matrix  # type: ignore  # noqa: E402


class VettingRunnerTests(unittest.TestCase):
    def test_normalize_judge_system_defaults_to_council(self) -> None:
        self.assertEqual(run_vetting_matrix.normalize_judge_system(""), "council")
        self.assertEqual(run_vetting_matrix.normalize_judge_system("provider-owned"), "provider_owned")
        self.assertEqual(run_vetting_matrix.normalize_judge_system("provider owned"), "provider_owned")

    def test_provider_owned_validation_requires_matching_family_and_direct_baseline(self) -> None:
        answers = [
            {"answerId": "para-openai", "label": "Para", "role": "parallm", "provider": "openai"},
            {"answerId": "direct-openai", "label": "Direct", "role": "direct", "provider": "openai"},
        ]
        manifest = {"providerFamily": "openai"}

        result = run_vetting_matrix.validate_judge_manifest_mode(manifest, answers, "provider_owned", "openai")

        self.assertEqual(result["judgeSystem"], "provider_owned")
        self.assertEqual(result["providerFamily"], "openai")
        self.assertEqual(result["roleCounts"]["direct"], 1)
        self.assertEqual(result["roleCounts"]["parallm"], 1)

    def test_provider_owned_validation_rejects_mixed_provider_answers(self) -> None:
        answers = [
            {"answerId": "para-openai", "label": "Para", "role": "parallm", "provider": "openai"},
            {"answerId": "direct-xai", "label": "Direct", "role": "direct", "provider": "xai"},
        ]
        manifest = {"providerFamily": "openai"}

        with self.assertRaises(ValueError):
            run_vetting_matrix.validate_judge_manifest_mode(manifest, answers, "provider_owned", "openai")

    def test_extract_answer_text_prefers_meaningful_artifact_answer_over_fenced_wrapper(self) -> None:
        payload = {
            "rawOutputText": "```json\n{\"frontAnswer\":{\"answer\":\"Wrapped answer.\"},\"tail\":\"ignored\"}\n```",
            "flattenedOutputText": "Flattened answer.",
            "output": {
                "frontAnswer": {
                    "answer": "Meaningful final answer."
                }
            },
        }

        result = run_vetting_matrix.extract_answer_text(payload)

        self.assertEqual(result, "Meaningful final answer.")

    def test_extract_answer_text_parses_fenced_json_string(self) -> None:
        payload = "```json\n{\"frontAnswer\":{\"answer\":\"Structured answer.\"}}\n```"

        result = run_vetting_matrix.extract_answer_text(payload)

        self.assertEqual(result, "Structured answer.")


if __name__ == "__main__":
    unittest.main()
