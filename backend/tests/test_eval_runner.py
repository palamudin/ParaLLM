from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "runtime"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

import eval_runner  # type: ignore  # noqa: E402


class EvalRunnerTests(unittest.TestCase):
    def test_build_task_id_stays_short_for_nested_eval_workspaces(self) -> None:
        task_id = eval_runner.build_task_id(
            "eval-20260427-225359+0000-0202bb:rmm-midnight-malware-push-critical-structured:front-eval-8e9daf1f--loops-1:1"
        )

        self.assertTrue(task_id.startswith("te-"))
        self.assertLessEqual(len(task_id), 9)

    def test_replicate_dir_for_compacts_case_and_variant_path_components(self) -> None:
        run_dir = Path("runs") / "judge-test"
        case_id = "msp-hard-rmm-supply-chain-replay-across-regulated-clients-with-long-title"
        variant_id = "para-deepseek-v4flash-critical-double--loops-1-with-extra-router-detail"

        replicate_dir = eval_runner.replicate_dir_for(run_dir, case_id, variant_id, 1)
        parts = replicate_dir.parts

        self.assertEqual(parts[-1], "replicate-001")
        self.assertLessEqual(len(parts[-3]), 32)
        self.assertLessEqual(len(parts[-2]), 36)
        self.assertNotIn(case_id, parts)
        self.assertNotIn(variant_id, parts)

    def test_run_steered_answer_reads_task_scoped_state(self) -> None:
        arm = eval_runner.validate_arm_manifest(
            {
                "armId": "provider-owned-smoke",
                "title": "Provider-owned smoke",
                "type": "steered",
                "runtime": {
                    "provider": "xai",
                    "model": "grok-4-1-fast-reasoning",
                    "summarizerProvider": "xai",
                    "summarizerModel": "grok-4.20-reasoning",
                    "directBaselineMode": "off",
                },
                "workers": [{"id": "A", "type": "proponent", "label": "Proponent", "model": "grok-4-1-fast-reasoning"}],
            },
            Path("provider-owned-smoke.json"),
        )

        scoped_summary = {
            "frontAnswer": {
                "answer": "Scoped summary answer.",
                "confidenceNote": "high",
            }
        }

        class FakeRuntime:
            def __init__(self, root: Path, auth_path: Path) -> None:
                self.root = root
                self.auth_path = auth_path
                self.tasks_path = root / "data" / "tasks"
                self.tasks_path.mkdir(parents=True, exist_ok=True)
                self._context = {}
                self._task_state = {}
                self._global_state = eval_runner.default_state()

            def ensure_data_paths(self) -> None:
                self.tasks_path.mkdir(parents=True, exist_ok=True)

            def with_lock(self):
                from contextlib import nullcontext
                return nullcontext()

            def write_state(self, state):
                self._global_state = state

            def initialize_task_state_unlocked(self, task, state):
                self._task_state = dict(state)

            def run_target(self, target: str, task_id: str) -> None:
                self._task_state["summary"] = scoped_summary
                self._task_state["usage"] = {"totalTokens": 123, "estimatedCostUsd": 0.0}

            def current_execution_context(self):
                return dict(self._context)

            def set_execution_context(self, context):
                self._context = dict(context or {})

            def read_state(self):
                if str(self._context.get("stateScopeTaskId") or "").strip():
                    return dict(self._task_state)
                return dict(self._global_state)

        case = {
            "caseId": "provider-owned-smoke-case",
            "objective": "Respond to an incident.",
            "constraints": ["Be precise."],
            "sessionContext": "none",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            auth_path = root / "Auth.txt"
            auth_path.write_text("", encoding="utf-8")
            replicate_dir = root / "replicate-001"
            with mock.patch.object(eval_runner, "LoopRuntime", FakeRuntime):
                result = eval_runner.run_steered_answer(
                    root,
                    auth_path,
                    case,
                    arm,
                    1,
                    replicate_dir,
                    "seed-a",
                )

        self.assertEqual(result["summary"], scoped_summary)
        self.assertEqual(result["mode"], "live")
        self.assertEqual(result["answerPathCallPlan"]["plannedVendorCalls"], 4)
        self.assertEqual(result["answerPathCallPlan"]["nodes"], ["round1:commander", "round1:worker:1", "round1:commander_review", "round1:summarizer"])

    def test_answer_path_call_plan_keeps_two_worker_default_visible(self) -> None:
        plan = eval_runner.answer_path_call_plan("off", worker_count=2, loop_rounds=1)

        self.assertEqual(plan["plannedVendorCalls"], 5)
        self.assertEqual(
            plan["nodes"],
            [
                "round1:commander",
                "round1:worker:1",
                "round1:worker:2",
                "round1:commander_review",
                "round1:summarizer",
            ],
        )
        self.assertEqual(plan["scope"], "answer_generation_only")

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
        self.assertEqual(task["runtime"]["directHarness"]["concision"], "none")
        self.assertEqual(task["runtime"]["targetTimeouts"]["commander"], 210)
        self.assertEqual(task["runtime"]["targetTimeouts"]["workerDefault"], 240)
        self.assertEqual(task["runtime"]["targetTimeouts"]["workers"]["A"], 180)

    def test_build_eval_task_carries_explicit_knowledgebase_config(self) -> None:
        arm = eval_runner.validate_arm_manifest(
            {
                "armId": "memory-mini",
                "title": "Memory Mini",
                "type": "steered",
                "runtime": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "knowledgebase": {
                        "enabled": True,
                        "scope": "shared",
                        "bankId": "msp-knowledgebase",
                        "maxRecords": 4,
                        "includeRuntime": False,
                        "includePersistent": True,
                        "fallbackToShared": False,
                        "tags": ["msp"],
                    },
                },
                "workers": [{"id": "A", "type": "proponent", "label": "Proponent", "model": "gpt-5-mini"}],
            },
            Path("memory-mini.json"),
        )

        task = eval_runner.build_eval_task(
            {
                "caseId": "case-a",
                "objective": "Decide whether to contain an MSP incident.",
                "constraints": ["Preserve evidence."],
                "sessionContext": "none",
            },
            arm,
            1,
            "seed-a",
        )

        self.assertTrue(arm["runtime"]["knowledgebaseExplicit"])
        self.assertEqual(task["runtime"]["knowledgebase"]["bankId"], "msp-knowledgebase")
        self.assertFalse(task["runtime"]["knowledgebase"]["includeRuntime"])
        self.assertEqual(task["runtime"]["knowledgebase"]["tags"], ["msp"])

    def test_judge_learning_config_targets_active_knowledgebase_bank(self) -> None:
        arms = {
            "memory-mini": eval_runner.validate_arm_manifest(
                {
                    "armId": "memory-mini",
                    "title": "Memory Mini",
                    "type": "direct",
                    "runtime": {
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "knowledgebase": {
                            "enabled": True,
                            "scope": "shared",
                            "bankId": "msp-knowledgebase",
                            "includePersistent": True,
                        },
                    },
                },
                Path("memory-mini.json"),
            )
        }

        config = eval_runner.normalize_judge_learning_config({"enabled": True}, arms)

        self.assertTrue(config["enabled"])
        self.assertEqual(config["bankId"], "msp-knowledgebase")
        self.assertEqual(config["writeMode"], "knowledgebase")

    def test_execute_run_auto_deposits_judge_learning_when_enabled(self) -> None:
        def fake_execute_replicate(run, run_dir, case, arm, loop_rounds, replicate_index, judge_model, auth_path):
            variant_id = eval_runner.variant_id_for_arm(arm, loop_rounds)
            replicate_dir = eval_runner.replicate_dir_for(run_dir, case["caseId"], variant_id, replicate_index)
            replicate_dir.mkdir(parents=True, exist_ok=True)
            (replicate_dir / "score.json").write_text(
                json.dumps(
                    {
                        "runId": run["runId"],
                        "caseId": case["caseId"],
                        "armId": arm["armId"],
                        "variantId": variant_id,
                        "replicate": replicate_index,
                        "quality": {
                            "scores": {
                                "tradeoffHandling": 7,
                                "objectionAbsorption": 6,
                                "overallQuality": 7,
                            },
                            "strongestWeakness": "Vendor escalation and out-of-band RMM console integrity checks were not explicit.",
                            "rationale": "The answer underplayed vendor escalation and audit gap handling.",
                        },
                        "answerHealth": {
                            "scores": {"evidenceHygiene": 7, "efficiencyDiscipline": 8, "overallHealth": 7},
                            "strongestWeakness": "Evidence capture needs tighter sequencing.",
                        },
                        "control": {
                            "scores": {"selfCheckQuality": 5, "adversarialDiscipline": 6, "overallControl": 6},
                            "strongestControlWeakness": "Self-check was procedural.",
                        },
                    }
                ),
                encoding="utf-8",
            )
            return {
                "replicate": replicate_index,
                "status": "completed",
                "publicAnswer": "response",
                "usage": {"totalTokens": 10, "estimatedCostUsd": 0.0},
                "mode": "live",
                "answerPath": "off",
                "contextMode": "weighted",
                "modeState": {},
                "artifactIds": [],
                "artifacts": [],
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_id = "judge-auto-learning"
            run_dir = root / "data" / "evals" / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (root / "Auth.txt").write_text("", encoding="utf-8")
            run = {
                "runId": run_id,
                "suiteId": "inline",
                "armIds": ["direct-memory"],
                "replicates": 1,
                "loopSweep": [1],
                "judgeProvider": "openai",
                "judgeModel": "gpt-5-mini",
                "judgeLearning": {"enabled": True},
                "inlineSuite": {
                    "suiteId": "inline",
                    "title": "Inline",
                    "description": "Inline",
                    "judgeRubric": {},
                    "cases": [
                        {
                            "caseId": "msp-hard-rmm-supply-chain-replay",
                            "title": "RMM Replay",
                            "objective": "RMM vendor plugin update created an audit gap.",
                            "constraints": ["Do not trust RMM."],
                            "sessionContext": "RMM control-plane incident.",
                        }
                    ],
                },
                "inlineArms": {
                    "direct-memory": {
                        "armId": "direct-memory",
                        "title": "Direct Memory",
                        "description": "Direct",
                        "type": "direct",
                        "runtime": {
                            "provider": "openai",
                            "model": "gpt-5-mini",
                            "knowledgebase": {
                                "enabled": True,
                                "bankId": "msp-knowledgebase",
                                "includeRuntime": False,
                                "includePersistent": True,
                                "tags": ["msp"],
                            },
                        },
                    }
                },
            }
            (run_dir / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")

            with mock.patch.object(eval_runner, "execute_replicate", side_effect=fake_execute_replicate):
                completed = eval_runner.execute_run(root, run_id)

            self.assertEqual(completed["judgeLearning"]["status"], "completed")
            self.assertEqual(completed["judgeLearning"]["bankId"], "msp-knowledgebase")
            self.assertGreater(completed["judgeLearning"]["lastResult"]["learnedRecordCount"], 0)
            records_path = root / "data" / "knowledgebase" / "banks" / "msp-knowledgebase" / "memory_units.jsonl"
            self.assertTrue(records_path.is_file())
            self.assertIn("judge-score-failure-class", records_path.read_text(encoding="utf-8"))

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

    def test_build_direct_answer_prompt_uses_direct_harness_not_summarizer_harness(self) -> None:
        prompt = eval_runner.build_direct_answer_prompt(
            {
                "objective": "Stop the bad rollout.",
                "constraints": ["Be direct."],
                "sessionContext": "none",
            },
            {
                "directHarness": {"concision": "tight", "instruction": "Use one short answer block."},
                "summarizerHarness": {"concision": "expansive", "instruction": "This should not leak into direct."},
            },
        )

        self.assertIn("Use one short answer block.", prompt["instructions"])
        self.assertNotIn("This should not leak into direct.", prompt["instructions"])

    def test_build_direct_answer_prompt_does_not_feed_memory_to_direct_candidate(self) -> None:
        class FakeRuntime:
            def build_knowledgebase_recall_packet(self, task, runtime, target, **kwargs):
                raise AssertionError("Direct answer generation must not receive memory recall.")

            def render_knowledgebase_prompt_block(self, packet):
                raise AssertionError("Direct answer generation must not render memory recall.")

        fake_runtime = FakeRuntime()
        prompt = eval_runner.build_direct_answer_prompt(
            {
                "caseId": "case-a",
                "objective": "Stop the bad rollout.",
                "constraints": ["Be direct."],
                "sessionContext": "none",
            },
            {
                "directHarness": {"concision": "tight", "instruction": ""},
                "knowledgebaseExplicit": True,
                "knowledgebase": {"enabled": True, "bankId": "msp-knowledgebase"},
            },
            runtime=fake_runtime,
        )

        self.assertNotIn("MSP knowledgebase recall", prompt["inputText"])
        self.assertNotIn("mem_msp_rmm_control_plane", prompt["inputText"])
        self.assertNotIn("MSP knowledgebase recall", prompt["fullPrompt"])
        self.assertNotIn("mem_msp_rmm_control_plane", prompt["fullPrompt"])

    def test_build_judge_memory_context_uses_arm_knowledgebase(self) -> None:
        class FakeRuntime:
            def build_knowledgebase_recall_packet(self, task, runtime, target, **kwargs):
                self.task = task
                self.runtime = runtime
                self.target = target
                self.kwargs = kwargs
                return {"selectedEvidenceIds": ["mem_msp_esxi_backup_restore"]}

            def render_knowledgebase_prompt_block(self, packet):
                return "MSP knowledgebase recall (ranked operational memory; binding when relevant):\nmem_msp_esxi_backup_restore\n"

        fake_runtime = FakeRuntime()
        context = eval_runner.build_judge_memory_context(
            fake_runtime,
            {
                "caseId": "case-memory",
                "objective": "Assess an ESXi backup outage.",
                "constraints": ["Preserve evidence."],
            },
            {
                "knowledgebaseExplicit": True,
                "knowledgebase": {"enabled": True, "bankId": "msp-knowledgebase"},
            },
        )

        self.assertEqual(fake_runtime.target, "judge_memory")
        self.assertEqual(fake_runtime.runtime["knowledgebase"]["bankId"], "msp-knowledgebase")
        self.assertEqual(fake_runtime.kwargs["role"], "judge")
        self.assertIn("Judge memory context", context)
        self.assertIn("mem_msp_esxi_backup_restore", context)
        self.assertIn("equivalent wording", context)
        self.assertIn("compact release checklist", context)
        self.assertIn("missing requirement source", context)

    def test_format_candidate_answer_packets_stays_blind(self) -> None:
        rendered = eval_runner.format_candidate_answer_packets(
            [
                {
                    "id": "A",
                    "text": "First answer text.",
                    "familyHint": "answers openai",
                    "costUsd": 1.234,
                    "costNote": "expensive",
                },
                {
                    "id": "B",
                    "text": "Second answer text.",
                    "familyHint": "answers xai",
                },
            ]
        )

        self.assertIn("Answer A", rendered)
        self.assertIn("Answer B", rendered)
        self.assertNotIn("answers openai", rendered)
        self.assertNotIn("answers xai", rendered)
        self.assertNotIn("declared cost", rendered)
        self.assertNotIn("expensive", rendered)

    def test_judge_provider_settings_uses_ollama_auto_profile_for_arbiter_timeout(self) -> None:
        settings = eval_runner.judge_provider_settings(
            {
                "judgeRuntime": {
                    "timeoutMode": "auto",
                    "ollamaBaseUrl": "http://192.168.0.26:11434",
                    "ollamaTimeoutProfile": {
                        "status": "ready",
                        "targetTimeouts": {"arbiter": 612},
                    },
                }
            },
            "ollama",
        )

        self.assertEqual(settings["ollamaBaseUrl"], "http://192.168.0.26:11434")
        self.assertEqual(settings["requestTimeoutSeconds"], 612)

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

    def test_run_direct_answer_uses_non_openai_assignment_key(self) -> None:
        class FakeResult:
            parsed = {"answer": "Live xAI direct answer.", "stance": "Proceed carefully.", "confidenceNote": "high"}
            response = {}
            response_id = "resp_live_xai"
            output_text = "{\"answer\":\"Live xAI direct answer.\"}"
            requested_max_output_tokens = 0
            effective_max_output_tokens = 0
            attempts = [0]
            recovered_from_incomplete = False

        class FakeRuntime:
            def provider_requires_api_key(self, provider):
                return True

            def provider_live_api_key(self, provider, auth_assignments=None):
                assignment = auth_assignments[0] if auth_assignments else {}
                return str(assignment.get("apiKey") or "")

            def live_auth_meta(self, provider, assignment):
                return {"provider": provider, "masked": "****1234"}

            def invoke_provider_json(self, **kwargs):
                self.kwargs = kwargs
                return FakeResult()

            def get_response_usage_delta(self, response, model):
                return {"totalTokens": 77, "estimatedCostUsd": 0.0}

        arm = eval_runner.validate_arm_manifest(
            {
                "armId": "direct-xai-smoke",
                "title": "Direct xAI Smoke",
                "type": "direct",
                "runtime": {
                    "executionMode": "live",
                    "provider": "xai",
                    "model": "grok-4.20-reasoning",
                    "requireLive": True,
                    "allowMockFallback": False,
                },
            },
            Path("direct-xai-smoke.json"),
        )

        runtime = FakeRuntime()
        result = eval_runner.run_direct_answer(
            runtime,
            [{"apiKey": "xai-live-key"}],
            {
                "objective": "Respond to an incident.",
                "constraints": ["Be precise."],
                "sessionContext": "none",
            },
            arm,
        )

        self.assertEqual(result["mode"], "live")
        self.assertEqual(runtime.kwargs["api_key"], "xai-live-key")
        self.assertEqual(runtime.kwargs["auth_assignments"], [{"apiKey": "xai-live-key"}])
        self.assertEqual(result["answer"]["answer"], "Live xAI direct answer.")
        self.assertIn("Objective:", result["inputText"])
        self.assertTrue(str(result["fullPrompt"]).startswith("Instructions:"))

    def test_run_direct_answer_normalizes_provider_specific_shape(self) -> None:
        class FakeResult:
            parsed = {
                "recommendation": "Pause the blast path first.",
                "reasoning": "The RMM channel is the most likely vector.",
                "nextActions": ["Disable the package.", "Wake the senior lead."],
                "confidenceNote": "medium",
            }
            response = {}
            response_id = "resp_provider_shape"
            output_text = "{\"recommendation\":\"Pause the blast path first.\"}"
            requested_max_output_tokens = 0
            effective_max_output_tokens = 0
            attempts = [0]
            recovered_from_incomplete = False

        class FakeRuntime:
            def provider_requires_api_key(self, provider):
                return True

            def provider_live_api_key(self, provider, auth_assignments=None):
                return "provider-key"

            def live_auth_meta(self, provider, assignment):
                return {"provider": provider}

            def invoke_provider_json(self, **kwargs):
                return FakeResult()

            def get_response_usage_delta(self, response, model):
                return {"totalTokens": 50, "estimatedCostUsd": 0.0}

        arm = eval_runner.validate_arm_manifest(
            {
                "armId": "direct-provider-shape",
                "title": "Direct Provider Shape",
                "type": "direct",
                "runtime": {
                    "executionMode": "live",
                    "provider": "minimax",
                    "model": "MiniMax-M2.7",
                    "requireLive": True,
                    "allowMockFallback": False
                },
            },
            Path("direct-provider-shape.json"),
        )

        result = eval_runner.run_direct_answer(
            FakeRuntime(),
            [{"apiKey": "provider-key"}],
            {
                "objective": "Respond to an incident.",
                "constraints": ["Be precise."],
                "sessionContext": "none",
            },
            arm,
        )

        self.assertEqual(result["mode"], "live")
        self.assertIn("Pause the blast path first.", result["answer"]["answer"])
        self.assertTrue(result["answer"]["stance"])
        self.assertEqual(result["answer"]["confidenceNote"], "medium")
        self.assertTrue(str(result["fullPrompt"]).startswith("Instructions:"))

    def test_run_direct_answer_normalizes_nested_plan_shape(self) -> None:
        class FakeResult:
            parsed = {
                "incident_label": "RMM package incident",
                "first_hour_plan": {
                    "immediate_actions": [
                        {"action": "Disable the package"},
                        {"action": "Wake the senior lead"},
                    ],
                    "containment": ["Preserve volatile evidence", "Avoid mass shutdown"],
                },
                "confidence_note": "low-moderate",
            }
            response = {}
            response_id = "resp_nested_shape"
            output_text = "{\"incident_label\":\"RMM package incident\"}"
            requested_max_output_tokens = 0
            effective_max_output_tokens = 0
            attempts = [0]
            recovered_from_incomplete = False

        class FakeRuntime:
            def provider_requires_api_key(self, provider):
                return True

            def provider_live_api_key(self, provider, auth_assignments=None):
                return "provider-key"

            def live_auth_meta(self, provider, assignment):
                return {"provider": provider}

            def invoke_provider_json(self, **kwargs):
                return FakeResult()

            def get_response_usage_delta(self, response, model):
                return {"totalTokens": 50, "estimatedCostUsd": 0.0}

        arm = eval_runner.validate_arm_manifest(
            {
                "armId": "direct-nested-shape",
                "title": "Direct Nested Shape",
                "type": "direct",
                "runtime": {
                    "executionMode": "live",
                    "provider": "minimax",
                    "model": "MiniMax-M2.7",
                    "requireLive": True,
                    "allowMockFallback": False
                },
            },
            Path("direct-nested-shape.json"),
        )

        result = eval_runner.run_direct_answer(
            FakeRuntime(),
            [{"apiKey": "provider-key"}],
            {
                "objective": "Respond to an incident.",
                "constraints": ["Be precise."],
                "sessionContext": "none",
            },
            arm,
        )

        self.assertEqual(result["mode"], "live")
        self.assertIn("Disable the package", result["answer"]["answer"])
        self.assertIn("Wake the senior lead", result["answer"]["answer"])
        self.assertEqual(result["answer"]["confidenceNote"], "low-moderate")

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

    def test_deterministic_checks_report_required_sop_concept_groups(self) -> None:
        result = {
            "answer": {
                "answer": "Open per-customer incidents, preserve evidence, and wake the senior incident lead.",
                "stance": "contain",
                "confidenceNote": "medium",
            },
            "usage": {"totalTokens": 100, "estimatedCostUsd": 0.01},
            "mode": "live",
        }

        checks = eval_runner.deterministic_checks(
            {
                "checks": {
                    "requiredConceptGroups": [
                        {
                            "id": "tenant-ownership",
                            "label": "Per-customer incident ownership",
                            "anyOf": ["per-customer", "per customer", "per-client"],
                        },
                        {
                            "id": "vendor-escalation",
                            "label": "Vendor escalation",
                            "anyOf": ["vendor escalation", "vendor support", "vendor bridge"],
                        },
                    ]
                }
            },
            {
                "type": "direct",
                "runtime": {
                    "budget": {"maxTotalTokens": 0, "maxCostUsd": 0.0},
                    "allowMockFallback": True,
                    "requireLive": False,
                },
            },
            result,
            result["answer"]["answer"],
        )

        concept_check = checks["checks"]["requiredConceptGroups"]
        self.assertFalse(concept_check["passed"])
        self.assertIn("Vendor escalation", concept_check["detail"])
        self.assertTrue(concept_check["groups"][0]["passed"])
        self.assertFalse(concept_check["groups"][1]["passed"])

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
        self.assertNotIn("computeVerdict", schema["properties"])
        self.assertNotIn("bestValue", schema["properties"])
        self.assertIn("hireVerdicts", schema["properties"])
        self.assertIn("hardFailFlags", schema["properties"])
        self.assertIn("trapFindings", schema["properties"])
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
                        "commsAndIncidentDiscipline": 8.1,
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
                        "commsAndIncidentDiscipline": 8.8,
                        "tacticalDetail": 7.2,
                        "restraintAndCollateral": 9.0,
                        "decisionGates": 8.2,
                        "firstHourRealism": 8.7,
                        "overall": 8.8,
                    },
                },
                "bestFinalAnswer": "B",
                "bestTacticalDetail": "A",
                "answerNotes": {"A": "More tactical detail.", "B": "Best final answer."},
                "rationale": "B is cleaner, A is tactically denser.",
            },
            ["A", "B"],
            response_id="resp_123",
        )

        self.assertEqual(normalized["ranking"], ["B", "A"])
        self.assertEqual(normalized["bestFinalAnswer"], "B")
        self.assertEqual(normalized["bestTacticalDetail"], "A")
        self.assertEqual(normalized["responseId"], "resp_123")
        self.assertEqual(normalized["scores"]["A"]["overall"], 8.0)
        self.assertEqual(normalized["categoryLeaders"]["tacticalDetail"], ["A"])
        self.assertEqual(normalized["categoryLeaders"]["blastRadiusPerception"], ["B"])
        self.assertEqual(normalized["advantageSummary"]["leader"], "B")
        self.assertEqual(normalized["advantageSummary"]["runnerUp"], "A")
        self.assertEqual(normalized["advantageSummary"]["band"], "decisive")
        self.assertEqual(normalized["advantageSummary"]["overallMargin"], 1.0)
        self.assertEqual(normalized["hireVerdicts"]["A"], "unknown")
        self.assertEqual(normalized["hardFailFlags"]["B"], [])
        self.assertEqual(normalized["trapFindings"]["A"]["triggered"], [])

    def test_normalize_vetting_matrix_result_extracts_hire_verdicts_and_traps(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "scores": {
                    "A": {field: 8.0 for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS},
                    "B": {field: 6.5 for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS},
                },
                "ranking": ["A", "B"],
                "bestFinalAnswer": "A",
                "bestTacticalDetail": "A",
                "hireVerdicts": {
                    "A": "hire_with_supervision",
                    "B": "disqualifying",
                },
                "hardFailFlags": {
                    "A": [],
                    "B": ["cross-tenant customer comms"],
                },
                "trapFindings": {
                    "A": {"triggered": [], "caught": ["control-plane trust trap"], "missed": []},
                    "B": {"triggered": ["cross-tenant comms trap"], "caught": [], "missed": ["control-plane trust trap"]},
                },
                "answerNotes": {"A": "Safer path.", "B": "Unsafe comms structure."},
                "rationale": "A is safer; B is disqualifying on tenant boundaries.",
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["hireVerdicts"]["A"], "hire_with_supervision")
        self.assertEqual(normalized["hireVerdicts"]["B"], "disqualifying")
        self.assertEqual(normalized["hardFailFlags"]["B"], ["cross-tenant customer comms"])
        self.assertEqual(normalized["trapFindings"]["A"]["caught"], ["control-plane trust trap"])
        self.assertEqual(normalized["trapFindings"]["B"]["triggered"], ["cross-tenant comms trap"])

    def test_normalize_vetting_matrix_result_accepts_anthropic_verdict_shape(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "verdicts": [
                    {
                        "id": "A",
                        "blastRadiusPerception": 8.5,
                        "humanUsability": 8.0,
                        "aiAgentExecutability": 7.5,
                        "tacticalDetail": 8.5,
                        "restraintCollateralControl": 9.0,
                        "decisionGates": 8.5,
                        "firstHourRealism": 8.0,
                        "overallQuality": 8.5,
                        "strengths": "Good sequencing.",
                        "weaknesses": "Slightly verbose.",
                    },
                    {
                        "id": "B",
                        "blastRadiusPerception": 9.0,
                        "humanUsability": 8.5,
                        "aiAgentExecutability": 8.5,
                        "tacticalDetail": 9.0,
                        "restraintCollateralControl": 9.0,
                        "decisionGates": 9.5,
                        "firstHourRealism": 9.0,
                        "overallQuality": 9.0,
                        "strengths": "Best decision gates.",
                        "weaknesses": "No ready-to-send client note.",
                    },
                ],
                "comparisons": {
                    "bestFinalAnswer": "B",
                    "bestTacticalDetail": "B",
                },
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["bestFinalAnswer"], "B")
        self.assertEqual(normalized["bestTacticalDetail"], "B")
        self.assertEqual(normalized["scores"]["A"]["restraintAndCollateral"], 9.0)
        self.assertEqual(normalized["scores"]["B"]["overall"], 9.0)
        self.assertIn("Strengths:", normalized["answerNotes"]["A"])
        self.assertEqual(normalized["advantageSummary"]["leader"], "B")
        self.assertEqual(normalized["advantageSummary"]["band"], "decisive")

    def test_normalize_vetting_matrix_result_accepts_minimax_score_list_shape(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "bestFinal": "B",
                "bestTacticalDetail": "A",
                "scores": [
                    {
                        "id": "A",
                        "blastRadius": 7.5,
                        "humanUsability": 7.0,
                        "aiAgentExecutable": 6.5,
                        "tacticalDetail": 8.5,
                        "restraint": 8.0,
                        "decisionGates": 7.0,
                        "firstHourRealism": 7.5,
                        "overall": 7.5,
                        "reasoning": "Best low-latency answer despite lower ceiling.",
                    },
                    {
                        "id": "B",
                        "blastRadius": 8.5,
                        "humanUsability": 8.5,
                        "aiAgentExecutable": 8.0,
                        "tacticalDetail": 8.0,
                        "restraint": 8.5,
                        "decisionGates": 8.5,
                        "firstHourRealism": 8.5,
                        "overall": 8.5,
                        "reasoning": "Most shippable under pressure.",
                    },
                ],
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["bestFinalAnswer"], "B")
        self.assertEqual(normalized["bestTacticalDetail"], "A")
        self.assertEqual(normalized["scores"]["A"]["agentExecutability"], 6.5)
        self.assertEqual(normalized["scores"]["B"]["blastRadiusPerception"], 8.5)
        self.assertEqual(normalized["ranking"], ["B", "A"])
        self.assertEqual(normalized["advantageSummary"]["leader"], "B")
        self.assertEqual(normalized["advantageSummary"]["band"], "decisive")

    def test_normalize_vetting_matrix_result_accepts_minimax_evaluation_object_shape(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "evaluation": {
                    "A": {
                        "blastRadiusPerception": 7.5,
                        "humanUsability": 8.0,
                        "agentExecutability": 6.5,
                        "tacticalDetail": 6.5,
                        "restraintAndCollateral": 8.5,
                        "decisionGates": 7.5,
                        "firstHourRealism": 8.0,
                        "overall": 7.5,
                    },
                    "B": {
                        "note": "Placeholder command direction, not a substantive answer",
                    },
                    "C": {
                        "blastRadiusPerception": 7.0,
                        "humanUsability": 8.5,
                        "agentExecutability": 9.0,
                        "tacticalDetail": 8.0,
                        "restraintAndCollateral": 9.0,
                        "decisionGates": 8.5,
                        "firstHourRealism": 8.5,
                        "overall": 8.0,
                    },
                },
                "bestFinalAnswer": "C",
                "bestTacticalDetail": "C",
                "rationale": {
                    "bestFinalAnswer": "C is the most executable answer.",
                },
            },
            ["A", "B", "C"],
        )

        self.assertEqual(normalized["bestFinalAnswer"], "C")
        self.assertEqual(normalized["bestTacticalDetail"], "C")
        self.assertEqual(normalized["scores"]["A"]["overall"], 7.5)
        self.assertEqual(normalized["scores"]["B"]["overall"], 0.0)
        self.assertIn("Placeholder", normalized["answerNotes"]["B"])
        self.assertEqual(normalized["rationale"], "C is the most executable answer.")

    def test_normalize_vetting_matrix_result_extracts_string_from_structured_rationale(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "scores": {
                    "A": {field: 9.0 for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS},
                    "B": {field: 8.0 for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS},
                },
                "ranking": ["A", "B"],
                "bestFinalAnswer": "A",
                "bestTacticalDetail": "A",
                "answerNotes": {"A": "", "B": ""},
                "rationale": {"summary": "A wins on cleaner decision gates."},
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["rationale"], "A wins on cleaner decision gates.")

    def test_extract_live_score_block_accepts_top_level_alias_fields(self) -> None:
        scores = eval_runner._extract_live_score_block(
            {
                "decisiveness": 8,
                "tradeoffHandling": 7,
                "objection_absorption": 8,
                "actionability": 9,
                "single_voice": 8,
                "overall": 8,
            },
            eval_runner.QUALITY_SCORE_FIELDS,
            eval_runner.QUALITY_SCORE_ALIASES,
        )

        self.assertEqual(scores["decisiveness"], 8)
        self.assertEqual(scores["objectionAbsorption"], 8)
        self.assertEqual(scores["singleVoice"], 8)
        self.assertEqual(scores["overallQuality"], 8)

    def test_build_vetting_matrix_judge_prompt_uses_plain_text_candidate_blocks(self) -> None:
        prompt = eval_runner.build_vetting_matrix_judge_prompt(
            {
                "objective": "Contain the blast path.",
                "constraints": ["Use decision gates.", "Preserve evidence."],
                "gold": {"priority": "safety-first"},
            },
            {"mustDo": ["Reward operational restraint."]},
            [
                {"id": "A", "familyHint": "direct", "text": "Direct answer text."},
                {"id": "B", "familyHint": "parallm", "text": "Para answer text."},
            ],
        )

        self.assertIn("Candidate answers:", prompt["inputText"])
        self.assertIn("Judge metric:", prompt["inputText"])
        self.assertIn("Answer A", prompt["inputText"])
        self.assertIn("Direct answer text.", prompt["inputText"])
        self.assertIn("Record hire verdicts", prompt["instructions"])
        self.assertNotIn("Judge rubric", prompt["inputText"])
        self.assertNotIn("Hidden gold guidance", prompt["inputText"])
        self.assertNotIn("safety-first", prompt["inputText"])
        self.assertNotIn("direct", prompt["inputText"])
        self.assertNotIn("{\"id\"", prompt["inputText"])

    def test_build_vetting_matrix_judge_prompt_includes_judge_memory_context(self) -> None:
        prompt = eval_runner.build_vetting_matrix_judge_prompt(
            {
                "objective": "Contain the blast path.",
                "constraints": ["Use decision gates."],
            },
            {"mustDo": ["Reward operational restraint."]},
            [
                {"id": "A", "text": "Direct answer text."},
                {"id": "B", "text": "Para answer text."},
            ],
            judge_memory_context="Judge memory context:\n- preserve job queue exports\n",
        )

        self.assertIn("Judge memory context:", prompt["inputText"])
        self.assertIn("preserve job queue exports", prompt["inputText"])
        self.assertIn("memory compliance", prompt["instructions"].lower())
        self.assertIn("missing binding requirement source", prompt["instructions"])

    def test_quality_judge_live_includes_memory_context_and_returns_compliance(self) -> None:
        captured = {}

        def fake_invoke(_runtime, _provider, _api_key, _model, instructions, input_text, *_args, **_kwargs):
            captured["instructions"] = instructions
            captured["inputText"] = input_text

            class FakeResult:
                parsed = {
                    "scores": {field: 8 for field in eval_runner.QUALITY_SCORE_FIELDS},
                    "verdict": "usable",
                    "strongestStrength": "It preserved the required job evidence.",
                    "strongestWeakness": "It could make one dependency check clearer.",
                    "rationale": "The answer satisfies the relevant memory by operational meaning.",
                    "memoryCompliance": "used: job queue export and immutability checks are present by equivalent wording.",
                }
                output_text = "{}"
                response_id = "resp-memory"

            return FakeResult()

        with mock.patch.object(eval_runner, "invoke_live_judge_json", side_effect=fake_invoke):
            result = eval_runner.quality_judge_live(
                runtime=object(),
                judge_provider="openai",
                api_key="key",
                judge_model="gpt-5.3",
                case={"objective": "Contain the blast path.", "constraints": []},
                judge_rubric={},
                public_answer="Export the job queue and confirm immutability before destructive actions.",
                provider_settings={},
                judge_memory_context="Judge memory context:\n- preserve job queue exports\n",
            )

        self.assertIn("Judge memory context:", captured["inputText"])
        self.assertIn("memory compliance", captured["instructions"].lower())
        self.assertIn("equivalent wording", captured["instructions"])
        self.assertIn("missing binding requirement source", captured["instructions"])
        self.assertIn("job queue export", result["memoryCompliance"])

    def test_normalize_vetting_matrix_result_accepts_answer_key_score_list_shape(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "scores": [
                    {
                        "answer": "A",
                        "blast_radius_perception": 9,
                        "human_usability": 9,
                        "ai_agent_executability": 8.5,
                        "tactical_detail": 9,
                        "restraint_collateral_control": 9.5,
                        "decision_gates": 9,
                        "first_hour_realism": 9,
                        "overall_quality": 9,
                    },
                    {
                        "answer": "B",
                        "blast_radius_perception": 7,
                        "human_usability": 7,
                        "ai_agent_executability": 6,
                        "tactical_detail": 5,
                        "restraint_collateral_control": 8,
                        "decision_gates": 6,
                        "first_hour_realism": 6.5,
                        "overall_quality": 6.5,
                    },
                ],
                "best_final_answer": "A",
                "best_tactical_detail": "A",
                "notes": "A is the most complete answer.",
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["scores"]["A"]["overall"], 9.0)
        self.assertEqual(normalized["scores"]["B"]["tacticalDetail"], 5.0)
        self.assertEqual(normalized["bestFinalAnswer"], "A")
        self.assertEqual(normalized["bestTacticalDetail"], "A")
        self.assertEqual(normalized["rationale"], "A is the most complete answer.")

    def test_normalize_vetting_matrix_result_accepts_anthropic_reasoning_and_uppercase_ai_keys(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "scores": {
                    "Answer A": {
                        "blast_radius_perception": 8.5,
                        "human_usability": 8.0,
                        "AI_agent_executability": 7.5,
                        "tactical_detail": 9.0,
                        "restraint_collateral_control": 9.0,
                        "decision_gates": 8.5,
                        "first_hour_realism": 8.5,
                        "overall_quality": 8.5,
                    },
                    "Answer B": {
                        "blast_radius_perception": 8.5,
                        "human_usability": 9.0,
                        "AI_agent_executability": 8.5,
                        "tactical_detail": 8.5,
                        "restraint_collateral_control": 8.5,
                        "decision_gates": 8.0,
                        "first_hour_realism": 9.0,
                        "overall_quality": 8.5,
                    },
                },
                "best_final_answer": "Answer B",
                "best_tactical_detail": "Answer A",
                "reasoning": {
                    "summary": "Both answers are strong.",
                    "tiebreaker rationale": "Answer B wins final readability; Answer A wins tactical detail.",
                },
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["scores"]["A"]["agentExecutability"], 7.5)
        self.assertEqual(normalized["scores"]["B"]["agentExecutability"], 8.5)
        self.assertEqual(normalized["bestFinalAnswer"], "B")
        self.assertEqual(normalized["bestTacticalDetail"], "A")
        self.assertIn("Answer B wins final readability", normalized["rationale"])

    def test_normalize_vetting_matrix_result_accepts_top_level_anthropic_answer_blocks_with_nested_scores(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "answer_a": {
                    "scores": {
                        "blast_radius_perception": 9,
                        "human_usability": 8,
                        "agent_executability": 8,
                        "comms_and_incident_discipline": 9,
                        "tactical_detail": 9.5,
                        "restraint_and_collateral": 9,
                        "decision_gates": 9.5,
                        "first_hour_realism": 9,
                        "overall": 9,
                    },
                    "hire_verdict": "strong_hire",
                    "hard_fail_flags": [],
                    "trap_findings": {
                        "cross_tenant_comms_trap": "avoided - per-client emergency contacts called individually",
                        "control_plane_trust_trap": "avoided - explicitly distrusts RMM",
                    },
                    "notes": "Answer A is stronger on decision-gate structure.",
                },
                "answer_b": {
                    "scores": {
                        "blast_radius_perception": 9,
                        "human_usability": 8.5,
                        "agent_executability": 8,
                        "comms_and_incident_discipline": 8.5,
                        "tactical_detail": 9,
                        "restraint_and_collateral": 9,
                        "decision_gates": 9,
                        "first_hour_realism": 9.5,
                        "overall": 9,
                    },
                    "hire_verdict": "strong_hire",
                    "hard_fail_flags": [],
                    "trap_findings": {
                        "control_plane_trust_trap": "avoided - explicit critical rule against RMM console use",
                    },
                    "notes": "Answer B is stronger on tactical detail.",
                },
                "best_final_answer": "answer_a",
                "best_tactical_detail_answer": "answer_b",
                "best_final_answer_rationale": "Answer A wins the overall decision.",
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["scores"]["A"]["decisionGates"], 9.5)
        self.assertEqual(normalized["scores"]["B"]["tacticalDetail"], 9.0)
        self.assertEqual(normalized["hireVerdicts"]["A"], "hire")
        self.assertIn("cross tenant comms trap", " ".join(normalized["trapFindings"]["A"]["caught"]).lower())
        self.assertEqual(normalized["bestFinalAnswer"], "A")
        self.assertEqual(normalized["bestTacticalDetail"], "B")

    def test_normalize_vetting_matrix_result_accepts_minimax_answers_list_shape(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "answers": [
                    {
                        "answer_id": "A",
                        "scores": {
                            "blast_radius_perception": 7.5,
                            "human_usability": 7.5,
                            "ai_agent_executability": 7.5,
                            "tactical_detail": 7.5,
                            "restraint_collateral_control": 8.0,
                            "decision_gates": 7.0,
                            "first_hour_realism": 7.5,
                            "overall_quality": 7.5,
                        },
                        "best_final_answer": False,
                        "best_tactical_detail": False,
                        "notes": "Answer A skipped console trust verification.",
                    },
                    {
                        "answer_id": "B",
                        "scores": {
                            "blast_radius_perception": 8.0,
                            "human_usability": 8.0,
                            "ai_agent_executability": 8.0,
                            "tactical_detail": 8.5,
                            "restraint_collateral_control": 8.5,
                            "decision_gates": 8.5,
                            "first_hour_realism": 8.5,
                            "overall_quality": 8.5,
                        },
                        "best_final_answer": True,
                        "best_tactical_detail": True,
                        "notes": "Answer B shows stronger MSP operator thinking.",
                    },
                ],
                "comparison_summary": "Answer B is superior because it distrusts the likely control-plane compromise.",
                "verdict": {
                    "best_final_answer": "B",
                    "best_tactical_detail": "B",
                    "rationale": "Answer B earns both designations.",
                },
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["scores"]["A"]["agentExecutability"], 7.5)
        self.assertEqual(normalized["scores"]["B"]["overall"], 8.5)
        self.assertEqual(normalized["bestFinalAnswer"], "B")
        self.assertEqual(normalized["bestTacticalDetail"], "B")
        self.assertIn("MSP operator thinking", normalized["answerNotes"]["B"])
        self.assertIn("Answer B earns both designations", normalized["rationale"])

    def test_normalize_vetting_matrix_result_accepts_minimax_candidate_blocks(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "candidate_a": {
                    "blast_radius_perception": 8.5,
                    "human_usability": 9.0,
                    "ai_agent_executability": None,
                    "tactical_detail": 9.0,
                    "restraint_collateral_control": 9.5,
                    "decision_gates": 9.0,
                    "first_hour_realism": 8.5,
                    "overall_quality": 8.5,
                    "summary": "A adds console trust verification and rollback preservation.",
                },
                "candidate_b": {
                    "blast_radius_perception": 8.0,
                    "human_usability": 8.5,
                    "ai_agent_executability": None,
                    "tactical_detail": 8.0,
                    "restraint_collateral_control": 8.0,
                    "decision_gates": 7.5,
                    "first_hour_realism": 8.0,
                    "overall_quality": 8.0,
                    "summary": "B is readable but less disciplined.",
                },
                "best_final_answer": "A",
                "best_tactical_detail": "A",
                "scoring_notes": {
                    "differentiation": "Answer A is more disciplined because it distrusts the control plane.",
                },
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["scores"]["A"]["overall"], 8.5)
        self.assertEqual(normalized["scores"]["B"]["overall"], 8.0)
        self.assertEqual(normalized["bestFinalAnswer"], "A")
        self.assertEqual(normalized["bestTacticalDetail"], "A")
        self.assertIn("rollback preservation", normalized["answerNotes"]["A"])
        self.assertIn("distrusts the control plane", normalized["rationale"])

    def test_normalize_vetting_matrix_result_accepts_minimax_best_answer_and_differential_rationale(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "scores": {
                    "A": {field: 8.5 for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS},
                    "B": {field: 8.0 for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS},
                },
                "best_answer": "A",
                "differential_rationale": "Answer A is more disciplined about control-plane trust.",
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["bestFinalAnswer"], "A")
        self.assertIn("control-plane trust", normalized["rationale"])

    def test_normalize_vetting_matrix_result_prefers_evaluation_blocks_over_scalar_score_summary(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "evaluation": {
                    "answer_a": {
                        "blast_radius_perception": 8.0,
                        "human_usability": 7.5,
                        "ai_agent_executability": 7.5,
                        "tactical_detail": 8.5,
                        "restraint_collateral_control": 9.0,
                        "decision_gates": 8.5,
                        "first_hour_realism": 8.0,
                        "overall_quality": 8.0,
                    },
                    "answer_b": {
                        "blast_radius_perception": 7.5,
                        "human_usability": 8.0,
                        "ai_agent_executability": 8.0,
                        "tactical_detail": 7.5,
                        "restraint_collateral_control": 8.0,
                        "decision_gates": 7.0,
                        "first_hour_realism": 8.5,
                        "overall_quality": 7.5,
                    },
                },
                "scores": {
                    "answer_a": 8.0,
                    "answer_b": 7.5,
                },
                "best_answer": "answer_a",
                "rationale": {
                    "key_differentiator": "Answer A uses better calibrated decision gates.",
                },
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["scores"]["A"]["overall"], 8.0)
        self.assertEqual(normalized["scores"]["B"]["decisionGates"], 7.0)
        self.assertEqual(normalized["bestFinalAnswer"], "A")
        self.assertIn("decision gates", normalized["rationale"].lower())

    def test_normalize_vetting_matrix_result_accepts_hyphenated_ai_agent_key_and_evaluator_notes(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "answers": [
                    {
                        "answer_id": "A",
                        "scores": {
                            "AI-agent_executability": 8.5,
                            "overall_quality": 8.5,
                        },
                        "best_for_rationale": "A is the most executable answer.",
                    },
                    {
                        "answer_id": "B",
                        "scores": {
                            "AI-agent_executability": 6.5,
                            "overall_quality": 7.5,
                        },
                    },
                ],
                "best_answer": "A",
                "evaluator_notes": "A wins on stronger procedural sequencing.",
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["scores"]["A"]["agentExecutability"], 8.5)
        self.assertEqual(normalized["scores"]["B"]["agentExecutability"], 6.5)
        self.assertIn("most executable", normalized["answerNotes"]["A"])
        self.assertIn("procedural sequencing", normalized["rationale"])

    def test_normalize_vetting_matrix_result_accepts_minimax_best_answer_summary(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "scores": {
                    "answer_a": {field: 9.0 for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS},
                    "answer_b": {field: 8.0 for field in eval_runner.VETTING_MATRIX_SCORE_FIELDS},
                },
                "best_answer": "answer_a",
                "best_tactical_detail": "answer_a",
                "best_answer_summary": "Answer A is more disciplined about console trust.",
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["bestFinalAnswer"], "A")
        self.assertEqual(normalized["bestTacticalDetail"], "A")
        self.assertIn("console trust", normalized["rationale"])

    def test_normalize_vetting_matrix_result_recovers_recursive_answer_blocks(self) -> None:
        normalized = eval_runner.normalize_vetting_matrix_result(
            {
                "wrapper": {
                    "payload": {
                        "candidate_a": {
                            "scores": {
                                "blast_radius_perception": 8.5,
                                "overall_quality": 8.5,
                            }
                        },
                        "candidate_b": {
                            "scores": {
                                "blast_radius_perception": 7.5,
                                "overall_quality": 7.5,
                            }
                        },
                    }
                },
                "best_answer": "candidate_a",
            },
            ["A", "B"],
        )

        self.assertEqual(normalized["scores"]["A"]["blastRadiusPerception"], 8.5)
        self.assertEqual(normalized["scores"]["B"]["overall"], 7.5)
        self.assertEqual(normalized["bestFinalAnswer"], "A")

    def test_run_quality_judge_retries_transient_provider_failure(self) -> None:
        attempts = []
        valid_result = {
            "mode": "live",
            "scores": {field: 8 for field in eval_runner.QUALITY_SCORE_FIELDS},
            "verdict": "Strong answer.",
            "strongestStrength": "Concrete sequencing.",
            "strongestWeakness": "Could name one more evidence source.",
            "rationale": "The answer is operationally useful and calibrated.",
            "responseId": "resp_ok",
        }

        def flaky_quality_judge(*_args, **_kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise eval_runner.RuntimeErrorWithCode("OpenAI API request failed: HTTP 500 | server_error", 500)
            return valid_result

        with mock.patch.object(eval_runner, "quality_judge_live", side_effect=flaky_quality_judge), mock.patch.object(
            eval_runner, "persist_failed_call_from_error"
        ) as persist_failed_call, mock.patch("time.sleep") as sleep:
            result = eval_runner.run_quality_judge(
                judge_runtime=object(),
                judge_provider="openai",
                api_key="key",
                judge_model="gpt-5-mini",
                case={"caseId": "transient-case", "objective": "Do the thing.", "constraints": []},
                judge_rubric={},
                public_answer="Recommend staged containment with explicit next steps.",
                provider_settings={},
            )

        self.assertEqual(result, valid_result)
        self.assertEqual(len(attempts), 2)
        persist_failed_call.assert_called_once()
        sleep.assert_called_once()

    def test_run_quality_judge_does_not_retry_non_transient_provider_failure(self) -> None:
        attempts = []

        def bad_request_quality_judge(*_args, **_kwargs):
            attempts.append(1)
            raise eval_runner.RuntimeErrorWithCode("OpenAI API request failed: HTTP 400 | invalid_request", 400)

        with mock.patch.object(eval_runner, "quality_judge_live", side_effect=bad_request_quality_judge), mock.patch.object(
            eval_runner, "persist_failed_call_from_error"
        ) as persist_failed_call, mock.patch("time.sleep") as sleep:
            with self.assertRaises(eval_runner.RuntimeErrorWithCode):
                eval_runner.run_quality_judge(
                    judge_runtime=object(),
                    judge_provider="openai",
                    api_key="key",
                    judge_model="gpt-5-mini",
                    case={"caseId": "bad-request-case", "objective": "Do the thing.", "constraints": []},
                    judge_rubric={},
                    public_answer="Recommend staged containment with explicit next steps.",
                    provider_settings={},
                )

        self.assertEqual(len(attempts), 1)
        persist_failed_call.assert_called_once()
        sleep.assert_not_called()

    def test_run_quality_judge_raises_when_live_scores_are_missing(self) -> None:
        with mock.patch.object(
            eval_runner,
            "quality_judge_live",
            return_value={
                "mode": "live",
                "scores": {field: 0 for field in eval_runner.QUALITY_SCORE_FIELDS},
                "verdict": "",
                "strongestStrength": "",
                "strongestWeakness": "",
                "rationale": "",
                "responseId": "resp_bad",
            },
        ):
            with self.assertRaises(eval_runner.RuntimeErrorWithCode):
                eval_runner.run_quality_judge(
                    judge_runtime=object(),
                    judge_provider="minimax",
                    api_key="key",
                    judge_model="MiniMax-M2.7",
                    case={"objective": "Do the thing.", "constraints": []},
                    judge_rubric={},
                    public_answer="Recommend staged containment with explicit next steps.",
                    provider_settings={},
                )

    def test_run_quality_judge_raises_when_live_audit_text_is_missing(self) -> None:
        with mock.patch.object(
            eval_runner,
            "quality_judge_live",
            return_value={
                "mode": "live",
                "scores": {field: 7 for field in eval_runner.QUALITY_SCORE_FIELDS},
                "verdict": "",
                "strongestStrength": "Concrete sequencing.",
                "strongestWeakness": "",
                "rationale": "",
                "responseId": "resp_score_only",
            },
        ):
            with self.assertRaises(eval_runner.RuntimeErrorWithCode) as captured:
                eval_runner.run_quality_judge(
                    judge_runtime=object(),
                    judge_provider="deepseek",
                    api_key="key",
                    judge_model="deepseek-v4-pro",
                    case={"objective": "Do the thing.", "constraints": []},
                    judge_rubric={},
                    public_answer="Recommend staged containment with explicit next steps.",
                    provider_settings={},
                )

        self.assertIn("score-only payload", str(captured.exception))

    def test_run_answer_health_judge_raises_when_live_scores_are_missing(self) -> None:
        with mock.patch.object(
            eval_runner,
            "answer_health_judge_live",
            return_value={
                "mode": "live",
                "scores": {field: 0 for field in eval_runner.ANSWER_HEALTH_SCORE_FIELDS},
                "verdict": "Malformed live judge payload.",
                "strongestStrength": "",
                "strongestWeakness": "",
                "rationale": "",
                "responseId": "resp_bad",
                "telemetry": {},
            },
        ):
            with self.assertRaises(eval_runner.RuntimeErrorWithCode):
                eval_runner.run_answer_health_judge(
                    judge_runtime=object(),
                    judge_provider="minimax",
                    api_key="key",
                    judge_model="MiniMax-M2.7",
                    case={"objective": "Do the thing.", "constraints": []},
                    public_answer="If evidence is incomplete, isolate surgically and escalate.",
                    telemetry={"charCount": 64},
                    provider_settings={},
                )

    def test_run_answer_health_judge_raises_when_live_audit_text_is_missing(self) -> None:
        with mock.patch.object(
            eval_runner,
            "answer_health_judge_live",
            return_value={
                "mode": "live",
                "scores": {field: 8 for field in eval_runner.ANSWER_HEALTH_SCORE_FIELDS},
                "verdict": "Healthy shape.",
                "strongestStrength": "",
                "strongestWeakness": "",
                "rationale": "",
                "responseId": "resp_score_only",
                "telemetry": {},
            },
        ):
            with self.assertRaises(eval_runner.RuntimeErrorWithCode) as captured:
                eval_runner.run_answer_health_judge(
                    judge_runtime=object(),
                    judge_provider="deepseek",
                    api_key="key",
                    judge_model="deepseek-v4-pro",
                    case={"objective": "Do the thing.", "constraints": []},
                    public_answer="If evidence is incomplete, isolate surgically and escalate.",
                    telemetry={"charCount": 64},
                    provider_settings={},
                )

        self.assertIn("score-only payload", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
