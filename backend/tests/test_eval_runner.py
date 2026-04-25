from __future__ import annotations

import sys
import unittest
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

import eval_runner  # type: ignore  # noqa: E402


class EvalRunnerTests(unittest.TestCase):
    def test_validate_arm_manifest_tracks_context_and_answer_path(self) -> None:
        manifest = eval_runner.validate_arm_manifest(
            {
                "armId": "compare-full",
                "title": "Compare Full",
                "type": "steered",
                "runtime": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "summarizerProvider": "openai",
                    "summarizerModel": "gpt-5-mini",
                    "contextMode": "full",
                    "directBaselineMode": "both",
                    "directProvider": "ollama",
                    "directModel": "qwen3.5:2b",
                    "ollamaBaseUrl": "http://192.168.0.26:11434/api",
                    "targetTimeouts": {"directBaseline": 300, "commanderReview": 540, "summarizer": 720},
                },
                "workers": [{"id": "A", "type": "proponent", "label": "Proponent", "model": "gpt-5-mini"}],
            },
            Path("compare-full.json"),
        )

        self.assertEqual(manifest["runtime"]["contextMode"], "full")
        self.assertEqual(manifest["runtime"]["directBaselineMode"], "both")
        self.assertEqual(manifest["runtime"]["directProvider"], "ollama")
        self.assertEqual(manifest["runtime"]["directModel"], "qwen3.5:2b")
        self.assertEqual(manifest["runtime"]["ollamaBaseUrl"], "http://192.168.0.26:11434/api")
        self.assertEqual(manifest["runtime"]["targetTimeouts"]["directBaseline"], 300)
        self.assertEqual(manifest["runtime"]["targetTimeouts"]["commanderReview"], 540)
        self.assertEqual(manifest["runtime"]["targetTimeouts"]["summarizer"], 720)

    def test_build_eval_task_includes_answer_path_runtime_fields(self) -> None:
        arm = eval_runner.validate_arm_manifest(
            {
                "armId": "single-mini",
                "title": "Single Mini",
                "type": "steered",
                "runtime": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "summarizerProvider": "openai",
                    "summarizerModel": "gpt-5-mini",
                    "contextMode": "weighted",
                    "directBaselineMode": "single",
                    "directProvider": "openai",
                    "directModel": "gpt-5-mini",
                    "targetTimeouts": {"commander": 210, "workerDefault": 240, "workers": {"A": 180}},
                },
                "workers": [{"id": "A", "type": "proponent", "label": "Proponent", "model": "gpt-5-mini"}],
            },
            Path("single-mini.json"),
        )

        task = eval_runner.build_eval_task(
            {
                "caseId": "case-a",
                "objective": "Decide whether to ship.",
                "constraints": ["Be direct."],
                "sessionContext": "none",
            },
            arm,
            1,
            "seed-a",
        )

        self.assertEqual(task["runtime"]["contextMode"], "weighted")
        self.assertEqual(task["runtime"]["directBaselineMode"], "single")
        self.assertEqual(task["runtime"]["directProvider"], "openai")
        self.assertEqual(task["runtime"]["directModel"], "gpt-5-mini")
        self.assertEqual(task["runtime"]["targetTimeouts"]["commander"], 210)
        self.assertEqual(task["runtime"]["targetTimeouts"]["workerDefault"], 240)
        self.assertEqual(task["runtime"]["targetTimeouts"]["workers"]["A"], 180)

    def test_build_eval_task_carries_main_thread_harness(self) -> None:
        arm = eval_runner.validate_arm_manifest(
            {
                "armId": "compare-expansive",
                "title": "Compare Expansive",
                "type": "steered",
                "runtime": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "summarizerProvider": "openai",
                    "summarizerModel": "gpt-5-mini",
                    "summarizerHarness": {"concision": "none", "instruction": "Only state verified operational facts."},
                },
                "workers": [{"id": "A", "type": "proponent", "label": "Proponent", "model": "gpt-5-mini"}],
            },
            Path("compare-expansive.json"),
        )

        task = eval_runner.build_eval_task(
            {
                "caseId": "case-a",
                "objective": "Decide whether to ship.",
                "constraints": ["Be direct."],
                "sessionContext": "none",
            },
            arm,
            1,
            "seed-a",
        )

        self.assertEqual(arm["runtime"]["summarizerHarness"]["concision"], "none")
        self.assertEqual(task["summarizer"]["harness"]["concision"], "none")
        self.assertEqual(task["summarizer"]["harness"]["instruction"], "Only state verified operational facts.")

    def test_extract_public_answer_prefers_direct_baseline_for_single_mode(self) -> None:
        answer = eval_runner.extract_public_answer(
            {"type": "steered"},
            {
                "answerPath": "single",
                "directBaseline": {
                    "answer": {
                        "answer": "Use the direct baseline answer.",
                        "stance": "Ship carefully.",
                        "confidenceNote": "medium",
                    }
                },
            },
        )

        self.assertEqual(answer, "Use the direct baseline answer.")

    def test_deterministic_checks_require_direct_baseline_capture_for_both_mode(self) -> None:
        result = {
            "summary": {
                "frontAnswer": {"answer": "Ship with guardrails."},
                "summarizerOpinion": {"stance": "support"},
                "controlAudit": {"leadDraft": "Ship with review."},
            },
            "usage": {"totalTokens": 100, "estimatedCostUsd": 0.01},
            "modeState": {"workerModes": {"A": "live"}, "summaryMode": "live"},
            "answerPath": "both",
            "baselineError": "timeout",
        }

        checks = eval_runner.deterministic_checks(
            {"checks": {}},
            {
                "type": "steered",
                "runtime": {
                    "budget": {"maxTotalTokens": 0, "maxCostUsd": 0.0},
                    "allowMockFallback": True,
                    "requireLive": False,
                },
            },
            result,
            "Ship with guardrails.",
        )

        self.assertFalse(checks["checks"]["directBaselineCaptured"]["passed"])
        self.assertIn("timeout", checks["checks"]["directBaselineCaptured"]["detail"])

    def test_answer_similarity_metrics_detect_near_duplicate_answers(self) -> None:
        metrics = eval_runner.answer_similarity_metrics(
            "Ship with guardrails and review the rollout after launch.",
            "Ship with guardrails and review the rollout after launch.",
        )

        self.assertTrue(metrics["sharedOpening"])
        self.assertGreaterEqual(metrics["sequenceSimilarity"], 0.99)
        self.assertGreaterEqual(metrics["tokenOverlap"], 0.99)

    def test_aggregate_variant_summarizes_baseline_comparison(self) -> None:
        variant = {
            "replicates": [
                {
                    "status": "completed",
                    "quality": {"scores": {field: 8 for field in eval_runner.QUALITY_SCORE_FIELDS}},
                    "answerHealth": {"scores": {field: 7 for field in eval_runner.ANSWER_HEALTH_SCORE_FIELDS}},
                    "control": {"scores": {field: 7 for field in eval_runner.CONTROL_SCORE_FIELDS}},
                    "baselineQuality": {"scores": {field: 6 for field in eval_runner.QUALITY_SCORE_FIELDS}},
                    "baselineAnswerHealth": {"scores": {field: 6 for field in eval_runner.ANSWER_HEALTH_SCORE_FIELDS}},
                    "comparison": {
                        "scoreDelta": {field: 2 for field in eval_runner.QUALITY_SCORE_FIELDS},
                        "scores": {field: 6 for field in eval_runner.COMPARISON_SCORE_FIELDS},
                        "materialDifference": True,
                        "verdict": "pressurized_advantage",
                    },
                    "deterministic": {"passed": True},
                    "usage": {"totalTokens": 500, "estimatedCostUsd": 0.12},
                },
                {
                    "status": "completed",
                    "quality": {"scores": {field: 7 for field in eval_runner.QUALITY_SCORE_FIELDS}},
                    "answerHealth": {"scores": {field: 8 for field in eval_runner.ANSWER_HEALTH_SCORE_FIELDS}},
                    "control": {"scores": {field: 6 for field in eval_runner.CONTROL_SCORE_FIELDS}},
                    "baselineQuality": {"scores": {field: 7 for field in eval_runner.QUALITY_SCORE_FIELDS}},
                    "baselineAnswerHealth": {"scores": {field: 7 for field in eval_runner.ANSWER_HEALTH_SCORE_FIELDS}},
                    "comparison": {
                        "scoreDelta": {field: 0 for field in eval_runner.QUALITY_SCORE_FIELDS},
                        "scores": {field: 3 for field in eval_runner.COMPARISON_SCORE_FIELDS},
                        "materialDifference": False,
                        "verdict": "mixed",
                    },
                    "deterministic": {"passed": True},
                    "usage": {"totalTokens": 400, "estimatedCostUsd": 0.08},
                },
            ]
        }

        aggregate = eval_runner.aggregate_variant(variant)

        self.assertEqual(aggregate["comparison"]["replicateCount"], 2)
        self.assertEqual(aggregate["comparison"]["pressurizedWins"], 1)
        self.assertEqual(aggregate["comparison"]["ties"], 1)
        self.assertEqual(aggregate["baselineQuality"]["overallQuality"], 6.5)
        self.assertEqual(aggregate["answerHealth"]["overallHealth"], 7.5)
        self.assertEqual(aggregate["baselineAnswerHealth"]["overallHealth"], 6.5)
        self.assertEqual(aggregate["comparison"]["averageScoreDelta"]["overallQuality"], 1.0)
        self.assertEqual(aggregate["comparison"]["averageScores"]["overallDifferentiation"], 4.5)
        self.assertEqual(aggregate["comparison"]["meaningfulDifferenceRate"], 0.5)

    def test_vetting_matrix_judge_schema_tracks_answer_ids(self) -> None:
        schema = eval_runner.vetting_matrix_judge_schema(["A", "B", "C"])

        self.assertEqual(schema["properties"]["bestFinalAnswer"]["enum"], ["A", "B", "C"])
        self.assertEqual(schema["properties"]["computeVerdict"]["enum"], eval_runner.VETTING_COMPUTE_VERDICTS)
        self.assertEqual(
            schema["properties"]["scores"]["properties"]["A"]["required"],
            eval_runner.VETTING_MATRIX_SCORE_FIELDS,
        )

    def test_normalize_vetting_matrix_result_backfills_ranking_and_leaders(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "scores": {
                    "A": {
                        "blastRadiusPerception": 8.2,
                        "humanUsability": 7.8,
                        "agentExecutability": 7.6,
                        "tacticalDetail": 8.9,
                        "restraintAndCollateral": 8.0,
                        "decisionGates": 7.3,
                        "firstHourRealism": 7.9,
                        "overall": 0,
                    },
                    "B": {
                        "blastRadiusPerception": 9.1,
                        "humanUsability": 8.6,
                        "agentExecutability": 8.4,
                        "tacticalDetail": 7.2,
                        "restraintAndCollateral": 9.0,
                        "decisionGates": 8.2,
                        "firstHourRealism": 8.7,
                        "overall": 8.8,
                    },
                },
                "bestFinalAnswer": "B",
                "bestTacticalDetail": "A",
                "bestValue": "A",
                "computeVerdict": "earned",
                "answerNotes": {"A": "More tactical detail.", "B": "Best final answer."},
                "rationale": "B is cleaner, A is tactically denser.",
            },
            ["A", "B"],
            response_id="resp_123",
        )

        self.assertEqual(normalized["ranking"], ["B", "A"])
        self.assertEqual(normalized["bestFinalAnswer"], "B")
        self.assertEqual(normalized["bestTacticalDetail"], "A")
        self.assertEqual(normalized["computeVerdict"], "earned")
        self.assertEqual(normalized["responseId"], "resp_123")
        self.assertEqual(normalized["scores"]["A"]["overall"], 8.0)
        self.assertEqual(normalized["categoryLeaders"]["tacticalDetail"], ["A"])
        self.assertEqual(normalized["categoryLeaders"]["blastRadiusPerception"], ["B"])


if __name__ == "__main__":
    unittest.main()
