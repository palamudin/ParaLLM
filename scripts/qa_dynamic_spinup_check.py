from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.engine import LoopRuntime, task_workers


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="loop-dynamic-spinup-") as temp_dir:
        runtime = LoopRuntime(Path(temp_dir))

        task = {
            "taskId": "t-dynamic-spinup",
            "objective": "Decide whether the current lane roster is enough for a risky product launch.",
            "constraints": ["Be decisive.", "Stay grounded in the actual risk posture."],
            "sessionContext": "",
            "runtime": {
                "executionMode": "live",
                "model": "gpt-5-mini",
                "reasoningEffort": "low",
                "dynamicSpinup": {"enabled": True},
                "budget": {"maxTotalTokens": 0, "maxCostUsd": 0, "maxOutputTokens": 1800},
            },
            "summarizer": {"id": "summarizer", "label": "Summarizer", "model": "gpt-5-mini"},
            "workers": [
                {"id": "A", "type": "proponent"},
                {"id": "B", "type": "sceptic"},
            ],
        }
        workers = task_workers(task)
        commander_checkpoint = runtime.new_mock_commander(task, runtime.get_task_runtime(task), 1, task["constraints"], None)
        worker_state = {}
        for worker in workers:
            worker_state[worker["id"]] = runtime.new_mock_checkpoint(
                task,
                worker,
                runtime.get_task_runtime(task, worker["model"], worker["id"]),
                runtime.get_research_config(task),
                1,
                task["constraints"],
                None,
                0,
                [],
            )

        state = runtime.read_state()
        state["activeTask"] = task
        state["commander"] = commander_checkpoint
        state["workers"] = worker_state
        runtime.write_state(state)

        runtime.assert_budget_available = lambda *args, **kwargs: None  # type: ignore[method-assign]
        runtime.update_usage_tracking = lambda *args, **kwargs: None  # type: ignore[method-assign]
        runtime.get_api_key_assignment = lambda *args, **kwargs: {"apiKey": "test-key", "slot": 1, "masked": "sk-test"}  # type: ignore[method-assign]

        def fake_live_commander_review(api_key, task_arg, commander_arg, workers_arg, worker_state_arg, runtime_arg, line_catalog_arg):
            checkpoint = runtime.new_mock_commander_review(task_arg, commander_arg, workers_arg, worker_state_arg)
            checkpoint["dynamicLaneDecision"] = {
                "shouldSpawn": True,
                "suggestedLaneTypes": ["security"],
                "reason": "The current round still lacks a dedicated hostile-actor lane.",
                "requiredPressure": "Explicit hostile-actor abuse testing remains under-covered.",
                "temperature": "hot",
                "instruction": "Pressure-test abuse paths and escalation mechanics before the next merge.",
            }
            response = {
                "id": "resp_dynamic",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(checkpoint, ensure_ascii=False),
                            }
                        ],
                    }
                ],
            }
            call_meta = {
                "requestedMaxOutputTokens": int(runtime_arg["maxOutputTokens"]),
                "effectiveMaxOutputTokens": int(runtime_arg["maxOutputTokens"]),
                "attempts": [int(runtime_arg["maxOutputTokens"])],
                "recoveredFromIncomplete": False,
            }
            return checkpoint, "resp_dynamic", response, call_meta

        runtime.new_live_commander_review = fake_live_commander_review  # type: ignore[method-assign]

        result = runtime.run_commander_review()
        assert_true(result["exitCode"] == 0, "Expected commander review run to complete.")

        final_state = runtime.read_state()
        active_task = final_state.get("activeTask") if isinstance(final_state.get("activeTask"), dict) else {}
        active_workers = task_workers(active_task)
        round_one_workers = task_workers(active_task, 1)
        round_two_workers = task_workers(active_task, 2)
        worker_ids = [worker["id"] for worker in active_workers]
        worker_types = {worker["id"]: worker.get("type") for worker in active_workers}
        activation_rounds = {worker["id"]: int(worker.get("activeFromRound", 1) or 1) for worker in active_workers}
        commander_review = final_state.get("commanderReview") if isinstance(final_state.get("commanderReview"), dict) else {}
        lane_resolution = commander_review.get("dynamicLaneResolution") if isinstance(commander_review.get("dynamicLaneResolution"), dict) else {}

        assert_true("C" in worker_ids, "Expected dynamic spin-up to add worker C.")
        assert_true(worker_types.get("C") == "security", "Expected worker C to use the security lane type.")
        assert_true(activation_rounds.get("C") == 2, "Expected spawned worker C to activate in round 2.")
        assert_true("C" not in [worker["id"] for worker in round_one_workers], "Expected spawned worker C to stay out of the current round roster.")
        assert_true("C" in [worker["id"] for worker in round_two_workers], "Expected spawned worker C to join the next round roster.")
        assert_true(final_state.get("workers", {}).get("C") is None, "Expected new worker state slot to be initialized to null.")
        assert_true(bool(commander_review.get("dynamicLaneDecision", {}).get("shouldSpawn")), "Expected persisted commander review lane decision.")
        assert_true(commander_review.get("dynamicLaneDecision", {}).get("temperature") == "hot", "Expected commander review to persist lane temperature.")
        assert_true(lane_resolution.get("status") == "spawned", "Expected lane resolution to mark the request as spawned.")
        assert_true(lane_resolution.get("selectedLaneType") == "security", "Expected lane resolution to preserve the chosen security lane.")
        assert_true(lane_resolution.get("spawnedWorkerId") == "C", "Expected lane resolution to persist the spawned worker id.")
        assert_true(int(lane_resolution.get("activationRound", 0) or 0) == 2, "Expected lane resolution to persist the next activation round.")

        inferred_resolution = runtime.resolve_dynamic_lane_request(
            {
                "runtime": {"model": "gpt-5-mini"},
                "workers": [
                    {"id": "A", "type": "proponent"},
                    {"id": "B", "type": "sceptic"},
                    {"id": "C", "type": "reliability"},
                ],
            },
            {
                "shouldSpawn": True,
                "suggestedLaneTypes": ["reliability"],
                "reason": "Telemetry drift is still poorly covered.",
                "requiredPressure": "Observability gaps and metric drift remain under-covered.",
                "temperature": "cool",
                "instruction": "Probe blind spots in instrumentation and alerting.",
            },
            2,
        )
        assert_true(
            inferred_resolution.get("selectedLaneType") == "observability",
            "Expected lane resolution to infer observability when the requested lane is already covered.",
        )

        rejected_resolution = runtime.resolve_dynamic_lane_request(
            active_task,
            {
                "shouldSpawn": True,
                "suggestedLaneTypes": ["security"],
                "reason": "The same hostile-actor lens was requested again.",
                "requiredPressure": "No new pressure beyond the current security lane.",
                "temperature": "hot",
                "instruction": "Repeat the same security pressure.",
            },
            3,
        )
        assert_true(
            rejected_resolution.get("status") in {"rejected_duplicate", "rejected_covered"},
            "Expected duplicate lane requests to be rejected cleanly.",
        )

        steps_text = Path(temp_dir, "data", "steps.jsonl").read_text(encoding="utf-8")
        assert_true('"stage": "dynamic_lane"' in steps_text, "Expected dynamic lane audit step.")

        print(
            json.dumps(
                {
                    "status": "ok",
                    "workerIds": worker_ids,
                    "spawnedType": worker_types.get("C"),
                    "activeFromRound": activation_rounds.get("C"),
                    "laneResolutionStatus": lane_resolution.get("status"),
                    "inferredFallbackType": inferred_resolution.get("selectedLaneType"),
                    "duplicateResolutionStatus": rejected_resolution.get("status"),
                    "memoryVersion": final_state.get("memoryVersion"),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
