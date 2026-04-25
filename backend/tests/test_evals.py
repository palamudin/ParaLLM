from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import evals
from runtime.engine import RuntimeErrorWithCode


class EvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "data" / "evals" / "suites").mkdir(parents=True, exist_ok=True)
        (self.root / "data" / "evals" / "arms").mkdir(parents=True, exist_ok=True)
        (self.root / "data" / "evals" / "suites" / "suite-a.json").write_text(
            """
{
  "suiteId": "suite-a",
  "title": "Suite A",
  "description": "test",
  "judgeRubric": {},
  "cases": [
    {
      "caseId": "case-a",
      "title": "Case A",
      "objective": "Handle the incident.",
      "constraints": ["Be careful."]
    }
  ]
}
""".strip(),
            encoding="utf-8",
        )
        (self.root / "data" / "evals" / "arms" / "compare-mini-full.json").write_text(
            """
{
  "armId": "compare-mini-full",
  "title": "Compare Mini",
  "description": "test arm",
  "type": "steered",
  "runtime": {
    "executionMode": "live",
    "contextMode": "full",
    "directBaselineMode": "both",
    "provider": "openai",
    "model": "gpt-5-mini",
    "directProvider": "openai",
    "directModel": "gpt-5-mini",
    "summarizerProvider": "openai",
    "summarizerModel": "gpt-5-mini",
    "reasoningEffort": "medium",
    "budget": {"maxCostUsd": 10, "maxTotalTokens": 0, "maxOutputTokens": 0},
    "research": {"enabled": false, "externalWebAccess": true, "domains": []},
    "vetting": {"enabled": true},
    "preferredLoop": {"rounds": 1, "delayMs": 0}
  },
  "workers": [
    {"id": "A", "type": "proponent", "label": "Proponent", "role": "utility", "focus": "benefits", "temperature": "balanced", "model": "gpt-5-mini"}
  ]
}
""".strip(),
            encoding="utf-8",
        )
        (self.root / "data" / "evals" / "arms" / "direct-gpt54.json").write_text(
            """
{
  "armId": "direct-gpt54",
  "title": "Direct 5.4",
  "description": "direct arm",
  "type": "direct",
  "runtime": {
    "executionMode": "live",
    "provider": "openai",
    "model": "gpt-5.4",
    "directProvider": "openai",
    "directModel": "gpt-5.4",
    "summarizerProvider": "openai",
    "summarizerModel": "gpt-5.4",
    "reasoningEffort": "high",
    "budget": {"maxCostUsd": 10, "maxTotalTokens": 0, "maxOutputTokens": 0},
    "research": {"enabled": false, "externalWebAccess": true, "domains": []},
    "vetting": {"enabled": true},
    "preferredLoop": {"rounds": 1, "delayMs": 0}
  }
}
""".strip(),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_start_eval_run_redirects_to_front_eval_mode(self) -> None:
        with self.assertRaises(RuntimeErrorWithCode) as ctx:
            evals.start_eval_run({"suiteId": "suite-a", "armIds": ["arm-a"]}, self.root)

        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("Front mode to Eval", str(ctx.exception))

    def test_start_front_eval_run_builds_inline_run(self) -> None:
        payload = {
            "suiteId": "suite-a",
            "caseId": "case-a",
            "executionMode": "live",
            "provider": "openai",
            "model": "gpt-5-mini",
            "summarizerProvider": "openai",
            "summarizerModel": "gpt-5-mini",
            "directProvider": "openai",
            "directModel": "gpt-5-mini",
            "contextMode": "full",
            "reasoningEffort": "medium",
            "loopRounds": 1,
            "maxCostUsd": 4,
            "workers": [
                {"id": "A", "type": "proponent", "label": "Proponent", "role": "utility", "focus": "benefits", "temperature": "balanced", "model": "gpt-5-mini"}
            ],
        }
        with mock.patch.object(evals, "launch_eval_runner") as launch_runner:
            result = evals.start_front_eval_run(payload, self.root)

        self.assertEqual(result["run"]["canvas"], "eval")
        self.assertEqual(result["run"]["suiteId"], "suite-a--case-a")
        self.assertEqual(result["run"]["replicates"], 1)
        self.assertTrue((self.root / "data" / "evals" / "runs" / result["runId"] / "run.json").is_file())
        launch_runner.assert_called_once()

    def test_start_front_judge_run_builds_composite_suite(self) -> None:
        payload = {
            "suiteIds": ["suite-a"],
            "armIds": ["compare-mini-full", "direct-gpt54"],
            "judgeModel": "gpt-5.4",
            "replicates": 1,
            "loopSweep": [1],
        }
        with mock.patch.object(evals, "launch_eval_runner") as launch_runner:
            result = evals.start_front_judge_run(payload, self.root)

        self.assertEqual(result["run"]["canvas"], "judge")
        self.assertEqual(result["run"]["judgeModel"], "gpt-5.4")
        self.assertTrue((self.root / "data" / "evals" / "runs" / result["runId"] / "run.json").is_file())
        launch_runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
