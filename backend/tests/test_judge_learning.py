from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app import judge_learning, knowledgebase
from runtime.engine import LoopRuntime


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class JudgeLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def seed_eval_run(self) -> str:
        run_id = "judge-test-learning"
        run_dir = self.root / "data" / "evals" / "runs" / run_id
        write_json(
            run_dir / "run.json",
            {
                "runId": run_id,
                "inlineSuite": {
                    "cases": [
                        {
                            "caseId": "msp-hard-rmm-supply-chain-replay",
                            "title": "RMM Supply Chain Replay",
                            "objective": "RMM agent spawned payloads after a vendor plugin update and audit gap.",
                            "constraints": ["Do not trust the RMM console.", "Escalate vendor if warranted."],
                            "sessionContext": "Multi-tenant MSP RMM control-plane incident.",
                        }
                    ]
                },
            },
        )
        write_json(
            run_dir
            / "cases"
            / "msp-hard-rmm-supply-chain-replay"
            / "para-test--loops-1"
            / "replicate-001"
            / "score.json",
            {
                "runId": run_id,
                "caseId": "msp-hard-rmm-supply-chain-replay",
                "armId": "para-test",
                "variantId": "para-test--loops-1",
                "quality": {
                    "scores": {
                        "tradeoffHandling": 7,
                        "objectionAbsorption": 6,
                        "overallQuality": 7,
                    },
                    "strongestWeakness": "Vendor escalation and out-of-band RMM console integrity checks were not explicit.",
                    "rationale": "The answer mostly works but underplays vendor escalation, tenant-safe comms, and the audit gap.",
                },
                "answerHealth": {
                    "scores": {
                        "evidenceHygiene": 7,
                        "efficiencyDiscipline": 8,
                        "overallHealth": 7,
                    },
                    "strongestWeakness": "Evidence capture before cleanup needs tighter sequencing.",
                },
                "control": {
                    "scores": {
                        "selfCheckQuality": 5,
                        "adversarialDiscipline": 6,
                        "overallControl": 6,
                    },
                    "strongestControlWeakness": "Self-check was procedural and did not reject weak pressure.",
                },
            },
        )
        return run_id

    def test_learn_from_eval_scores_writes_sop_failure_class_records(self) -> None:
        run_id = self.seed_eval_run()

        result = judge_learning.learn_from_eval_runs(self.root, run_ids=[run_id], dry_run=False)

        self.assertGreaterEqual(result["learnedRecordCount"], 3)
        records, warnings = knowledgebase.load_persistent_records(self.root, bank_id="msp-knowledgebase")
        self.assertEqual(warnings, [])
        titles = "\n".join(record["title"] for record in records)
        self.assertIn("Vendor escalation", titles)
        self.assertIn("Lead-thread control", titles)
        learned = [record for record in records if "judge-learning" in record.get("tags", [])]
        self.assertTrue(all(record.get("sop") for record in learned))
        self.assertTrue(any((record.get("metadata") or {}).get("learning.adaptiveWeight") for record in learned))

    def test_learning_upsert_is_idempotent_for_same_score_refs(self) -> None:
        run_id = self.seed_eval_run()

        first = judge_learning.learn_from_eval_runs(self.root, run_ids=[run_id], dry_run=False)
        second = judge_learning.learn_from_eval_runs(self.root, run_ids=[run_id], dry_run=False)

        self.assertGreater(first["write"]["inserted"], 0)
        self.assertEqual(second["write"]["inserted"], 0)
        self.assertEqual(second["write"]["updated"], 0)
        self.assertGreaterEqual(second["write"]["unchanged"], first["write"]["inserted"])
        self.assertEqual(second["librarian"]["status"], "skipped")
        self.assertEqual(second["librarian"]["reason"], "no_learning_delta")
        self.assertTrue((self.root / "data" / "knowledgebase" / "banks" / "msp-knowledgebase" / "learning_events.jsonl").is_file())
        self.assertEqual(second["write"]["eventLedger"]["inserted"], 0)
        records, _ = knowledgebase.load_persistent_records(self.root, bank_id="msp-knowledgebase")
        score_ref_sets = [
            (record.get("metadata") or {}).get("learning.scoreRefs")
            for record in records
            if (record.get("metadata") or {}).get("learning.scoreRefs")
        ]
        self.assertTrue(score_ref_sets)
        self.assertTrue(all(str(refs).count("score.json") == 1 for refs in score_ref_sets))

    def test_librarian_index_groups_learned_memories_without_duplicates(self) -> None:
        run_id = self.seed_eval_run()
        judge_learning.learn_from_eval_runs(self.root, run_ids=[run_id], dry_run=False)

        index = judge_learning.librarian_review(self.root, "msp-knowledgebase")

        self.assertEqual(index["duplicateGroupCount"], 0)
        self.assertGreater(index["groupCount"], 0)
        self.assertGreater(index["uniqueScoreRefCount"], 0)
        self.assertIn("storageDuplication", index)
        self.assertIn("smartDedupePlan", index)
        self.assertGreaterEqual(index["storageDuplication"]["scoreRefSlots"], index["uniqueScoreRefCount"])
        self.assertIn("eventLedger", index)
        self.assertTrue(index["eventLedger"]["authoritativeForScoreRefs"])
        self.assertTrue((self.root / "data" / "knowledgebase" / "banks" / "msp-knowledgebase" / "librarian_index.json").is_file())
        self.assertTrue(index["vectorCandidates"])

    def test_compact_learning_bank_moves_legacy_refs_to_event_ledger(self) -> None:
        run_id = self.seed_eval_run()
        judge_learning.learn_from_eval_runs(self.root, run_ids=[run_id], dry_run=False)
        record_path = self.root / "data" / "knowledgebase" / "banks" / "msp-knowledgebase" / "memory_units.jsonl"
        records = [json.loads(line) for line in record_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        learned = next(record for record in records if "judge-learning" in record.get("tags", []))
        legacy_refs = [
            "data/evals/runs/a/cases/case/arm-a/replicate-001/score.json",
            "data/evals/runs/b/cases/case/arm-b/replicate-001/score.json",
            "data/evals/runs/c/cases/case/arm-c/replicate-001/score.json",
            "data/evals/runs/d/cases/case/arm-d/replicate-001/score.json",
        ]
        learned["metadata"]["learning.scoreRefs"] = ",".join(legacy_refs)
        learned["sop"]["sourceRefs"] = legacy_refs
        record_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")

        result = judge_learning.compact_learning_bank(self.root, "msp-knowledgebase")

        self.assertGreaterEqual(result["eventLedger"]["count"], 4)
        compacted_records, _ = knowledgebase.load_persistent_records(self.root, bank_id="msp-knowledgebase")
        compacted = next(record for record in compacted_records if record["id"] == learned["id"])
        metadata = compacted["metadata"]
        self.assertEqual(metadata["learning.scoreRefMode"], "exemplar")
        self.assertGreaterEqual(metadata["learning.scoreRefCount"], 4)
        self.assertLessEqual(len(judge_learning.split_csv(metadata["learning.scoreRefs"])), 3)
        self.assertLessEqual(len(compacted["sop"]["sourceRefs"]), 3)

    def test_learned_packets_render_replay_metadata_for_agents(self) -> None:
        run_id = self.seed_eval_run()
        judge_learning.learn_from_eval_runs(self.root, run_ids=[run_id], dry_run=False)
        runtime = LoopRuntime(self.root)
        task = {
            "taskId": "t-rmm",
            "objective": "RMM vendor plugin update created an audit gap. Build first-hour response.",
            "runtime": {
                "knowledgebase": {
                    "bankId": "msp-knowledgebase",
                    "includeRuntime": False,
                    "includePersistent": True,
                    "maxRecords": 4,
                    "tags": ["msp"],
                }
            },
        }

        packet = runtime.build_knowledgebase_recall_packet(task, runtime.get_task_runtime(task), "commander")
        projected = runtime.project_targeted_sop_prompt_packet(runtime.project_knowledgebase_prompt_packet(packet))

        learned_packets = [item for item in projected.get("sopPackets", []) if item.get("learning")]
        self.assertTrue(learned_packets)
        self.assertEqual(learned_packets[0]["learning"]["kind"], "judge-score-failure-class")
        self.assertIn("adaptiveWeight", learned_packets[0]["learning"])


if __name__ == "__main__":
    unittest.main()
