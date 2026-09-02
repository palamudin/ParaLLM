from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import knowledgebase, storage
from runtime.engine import LoopRuntime, ProviderResult


def provider_result(parsed: dict, *, response_id: str = "resp-test") -> ProviderResult:
    return ProviderResult(
        provider="openai",
        parsed=parsed,
        response={
            "id": response_id,
            "status": "completed",
            "usage": {
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
                "input_tokens_details": {"cached_tokens": 2},
                "output_tokens_details": {"reasoning_tokens": 3},
            },
        },
        response_id=response_id,
        output_text=None,
        thinking_text=None,
        web_search_queries=[],
        web_search_sources=[],
        url_citations=[],
        requested_max_output_tokens=2400,
        effective_max_output_tokens=2400,
        attempts=[2400],
        recovered_from_incomplete=False,
        executed_tools=[],
        auth_assignment=None,
        auth_failover_history=[],
    )


class RuntimeWebAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.runtime = LoopRuntime(self.root)
        self.runtime.ensure_data_paths()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_page_artifact(self) -> str:
        artifact_id = "page_arbiterfixture"
        page_dir = storage.project_paths(self.root).data / "research" / "pages"
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / f"{artifact_id}.json").write_text(
            json.dumps(
                {
                    "artifactId": artifact_id,
                    "kind": "page",
                    "title": "Servo calibration specification",
                    "url": "https://docs.example.test/servo",
                    "finalUrl": "https://docs.example.test/servo",
                    "sha256": "source-hash",
                    "chunks": [
                        {"id": "chunk_keep", "locator": "page", "text": "Nominal servo travel is 18.2 mm."},
                        {"id": "chunk_other", "locator": "page", "text": "Inspection interval is 500 hours."},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return artifact_id

    def test_web_tool_catalog_only_exposes_explicit_memory_promotion_when_requested(self) -> None:
        without_memory = self.runtime.build_web_function_tools({"domains": ["example.test"]})
        with_memory = self.runtime.build_web_function_tools({"domains": ["example.test"]}, memory_enabled=True)

        self.assertNotIn("web_retain_chunks", [tool["name"] for tool in without_memory])
        self.assertIn("web_research", [tool["name"] for tool in without_memory])
        self.assertIn("web_retain_chunks", [tool["name"] for tool in with_memory])

    def test_memory_arbiter_can_only_retain_exact_valid_chunk_ids(self) -> None:
        artifact_id = self.write_page_artifact()
        task = {
            "taskId": "t-web-arbiter",
            "objective": "Calibrate this exact servo using its source specification.",
            "constraints": ["Retain source-backed specifications."],
            "runtime": {"knowledgebase": {"enabled": True, "bankId": "web-manuals"}},
        }
        decision = provider_result(
            {
                "decisions": [
                    {
                        "artifactId": artifact_id,
                        "disposition": "retain_selected",
                        "retainChunkIds": ["chunk_keep", "chunk_invented"],
                        "rationale": "Stable source specification needed for this device.",
                        "tags": ["servo", "manual"],
                    }
                ],
                "summary": "Retain the exact calibration datum only.",
            },
            response_id="resp-arbiter",
        )

        with mock.patch.object(self.runtime, "invoke_provider_json", return_value=decision):
            result = self.runtime.arbitrate_web_memory(
                api_key="test-key",
                auth_assignments=[],
                task=task,
                runtime={"provider": "openai", "model": "gpt-5-mini", "maxOutputTokens": 2400},
                provider_settings={},
                target_kind="worker_A",
                artifact_ids=[artifact_id],
                lane_output={"observation": "The calibration datum is directly relevant."},
            )

        recall = knowledgebase.recall(
            self.root,
            query="nominal servo travel",
            bank_id="web-manuals",
            include_runtime=False,
            include_persistent=True,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["retainedArtifacts"], 1)
        self.assertEqual(result["retainedChunks"], 1)
        self.assertEqual(result["decisions"][0]["retainChunkIds"], ["chunk_keep"])
        self.assertEqual(recall["resultCount"], 1)
        self.assertIn("18.2 mm", recall["hits"][0]["text"])
        self.assertNotIn("500 hours", recall["hits"][0]["text"])

    def test_supplemental_provider_usage_is_counted_in_lane_budget(self) -> None:
        response = {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "completion_tokens_details": {"reasoning_tokens": 4},
            },
            "_paraCallCount": 2,
        }
        additional = {
            "input_tokens": 30,
            "output_tokens": 10,
            "total_tokens": 40,
            "input_tokens_details": {"cached_tokens": 5},
            "output_tokens_details": {"reasoning_tokens": 2},
        }

        self.runtime.merge_response_usage(response, additional, additional_calls=1)
        delta = self.runtime.get_response_usage_delta(response, "gpt-5-mini")

        self.assertIsNotNone(delta)
        self.assertEqual(delta["calls"], 3)
        self.assertEqual(delta["inputTokens"], 130)
        self.assertEqual(delta["outputTokens"], 30)
        self.assertEqual(delta["cachedInputTokens"], 5)
        self.assertEqual(delta["reasoningTokens"], 6)
        self.assertEqual(delta["totalTokens"], 160)

    def test_pure_direct_baseline_is_not_given_browser_or_memory_tools(self) -> None:
        result = provider_result({"answer": "A plain provider answer."}, response_id="resp-direct")
        task = {
            "taskId": "t-direct-clean",
            "objective": "Answer without Para tooling.",
            "runtime": {
                "research": {"enabled": True, "externalWebAccess": True},
                "knowledgebase": {"enabled": True},
            },
        }
        direct_runtime = {
            "provider": "openai",
            "model": "gpt-5-mini",
            "reasoningEffort": "low",
            "maxOutputTokens": 2400,
        }

        with mock.patch.object(self.runtime, "invoke_provider_json", return_value=result) as invoke:
            self.runtime.new_live_direct_baseline("test-key", [], task, direct_runtime)

        kwargs = invoke.call_args.kwargs
        self.assertNotIn("tools", kwargs)
        self.assertNotIn("function_handlers", kwargs)
        self.assertNotIn("Research policy", kwargs["input_text"])
        self.assertNotIn("knowledgebase", kwargs["input_text"].lower())

    def test_commander_and_worker_receive_para_owned_browser_tools(self) -> None:
        task = {
            "taskId": "t-owned-browser",
            "objective": "Read the public device manual and identify the calibration interval.",
            "constraints": ["Use source-backed evidence."],
            "runtime": {
                "knowledgebase": {"enabled": False},
            },
            "workers": [
                {
                    "id": "A",
                    "label": "Evidence",
                    "type": "data",
                    "role": "adversarial",
                    "focus": "source accuracy",
                    "temperature": "cool",
                }
            ],
        }
        runtime_config = {
            "provider": "openai",
            "model": "gpt-5-mini",
            "reasoningEffort": "low",
            "maxOutputTokens": 2400,
            "contextMode": "weighted",
            "research": {
                "enabled": True,
                "externalWebAccess": True,
                "domains": ["example.test"],
            },
            "localFiles": {"enabled": False},
            "githubTools": {"enabled": False},
        }
        commander = self.runtime.new_offline_fixture_commander(
            task,
            runtime_config,
            1,
            list(task["constraints"]),
            None,
        )
        worker = {
            "workerId": "A",
            "label": "Evidence",
            "role": "adversarial",
            "viewpoint": "Verify the source.",
            "focus": "source accuracy",
            "step": 1,
            "modelUsed": "gpt-5-mini",
            "observation": "Source inspection is required.",
            "peerSteer": "",
            "sharedMemorySeen": {"memoryVersion": 0, "recommendedNextAction": ""},
            "benefits": ["Direct source inspection can ground the calibration interval."],
            "detriments": ["The result remains unverified until the source is opened."],
            "requiredCircumstances": [],
            "invalidatingCircumstances": [],
            "immediateConsequences": [],
            "downstreamConsequences": [],
            "uncertainty": [],
            "reversalConditions": [],
            "researchMode": "model_only",
            "researchQueries": [],
            "researchSources": [],
            "urlCitations": [],
            "evidenceLedger": [],
            "evidenceGaps": [],
            "confidence": 0.5,
            "requestToPeer": "",
            "requestTargets": [],
            "constraintsSeen": list(task["constraints"]),
        }

        def fake_invoke(**kwargs):
            parsed = commander if kwargs["target_kind"] == "commander" else worker
            return provider_result(parsed, response_id=f"resp-{kwargs['target_kind']}")

        with mock.patch.object(self.runtime, "invoke_provider_json", side_effect=fake_invoke) as invoke:
            self.runtime.new_live_commander(
                api_key="test-key",
                auth_assignments=[],
                task=task,
                runtime=runtime_config,
                round_number=1,
                constraints=list(task["constraints"]),
                prior_summary=None,
            )
            self.runtime.new_live_checkpoint(
                api_key="test-key",
                auth_assignments=[],
                task=task,
                worker=task["workers"][0],
                runtime=runtime_config,
                research_config=runtime_config["research"],
                step_number=1,
                constraints=list(task["constraints"]),
                commander_checkpoint=commander,
                prior_summary=None,
                prior_memory_version=0,
                peer_messages=[],
            )

        self.assertEqual(invoke.call_count, 2)
        for call in invoke.call_args_list:
            kwargs = call.kwargs
            tool_names = {tool["name"] for tool in kwargs["tools"]}
            self.assertTrue({"web_research", "web_search", "web_open", "web_download", "web_ingest"}.issubset(tool_names))
            self.assertEqual(set(kwargs["function_handlers"]), tool_names)
            self.assertEqual(kwargs["tool_choice"], "required")


if __name__ == "__main__":
    unittest.main()
