from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app import memory_deposit


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class MemoryDepositTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def seed_score(self) -> Path:
        score_path = (
            self.root
            / "data"
            / "evals"
            / "runs"
            / "judge-memory-proposal"
            / "cases"
            / "lme-temporal"
            / "variant"
            / "replicate-001"
            / "score.json"
        )
        write_json(
            score_path,
            {
                "runId": "judge-memory-proposal",
                "caseId": "lme-temporal",
                "armId": "para-test",
                "variantId": "variant",
                "quality": {
                    "scores": {"overallQuality": 9},
                    "strongestWeakness": "Answer was right but evidence wording was thin.",
                    "rationale": "The candidate used retained memory.",
                    "memoryCompliance": "Compliant by meaning.",
                },
                "answerHealth": {
                    "scores": {"overallHealth": 9},
                    "strongestWeakness": "Could cite the memory source more clearly.",
                },
                "control": {
                    "scores": {"overallControl": 8},
                    "strongestControlWeakness": "Self-check was brief.",
                },
            },
        )
        return score_path

    def test_build_eval_candidate_routes_to_pending_context_review_without_proposal(self) -> None:
        score_path = self.seed_score()
        score = json.loads(score_path.read_text(encoding="utf-8"))
        case = {
            "caseId": "lme-temporal",
            "title": "LongMemEval temporal recall",
            "objective": "Answer from retained memory.",
            "sessionContext": "External memory QA benchmark.",
        }

        candidate = memory_deposit.build_eval_score_candidate(
            self.root,
            run_id="judge-memory-proposal",
            score_path=score_path,
            score=score,
            case=case,
            requested_bank_id="longmemeval-oracle-pilot-5",
        )

        self.assertEqual(candidate["schemaVersion"], memory_deposit.CANDIDATE_SCHEMA_VERSION)
        self.assertEqual(candidate["source"]["kind"], "eval-score")
        self.assertEqual(candidate["routing"]["status"], "pending_context_review")
        self.assertEqual(candidate["routing"]["destination"], "quarantine")
        self.assertEqual(candidate["routing"]["requestedBankId"], "longmemeval-oracle-pilot-5")
        self.assertIn("router_missing", candidate["arbiter"]["blockers"])
        self.assertIn("score.json", candidate["evidenceRefs"][0])

    def test_candidate_ledger_is_idempotent_for_same_score_ref(self) -> None:
        score_path = self.seed_score()
        score = json.loads(score_path.read_text(encoding="utf-8"))
        case = {"caseId": "lme-temporal", "objective": "Answer from retained memory."}
        candidate = memory_deposit.build_eval_score_candidate(
            self.root,
            run_id="judge-memory-proposal",
            score_path=score_path,
            score=score,
            case=case,
            requested_bank_id="longmemeval-oracle-pilot-5",
        )

        first = memory_deposit.write_candidate_ledger(self.root, [candidate])
        second = memory_deposit.write_candidate_ledger(self.root, [candidate])

        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["unchanged"], 1)
        records, warnings = memory_deposit.read_candidate_ledger(self.root)
        self.assertEqual(warnings, [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], candidate["id"])


if __name__ == "__main__":
    unittest.main()
