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

        def fake_live_summary(api_key, task_arg, commander_arg, workers_arg, worker_state_arg, runtime_arg, vetting_arg, line_catalog_arg, partial_mode=False, pending_workers=None):
            summary = runtime.new_mock_summary(task_arg, commander_arg, workers_arg, worker_state_arg, vetting_arg, line_catalog_arg)
            summary["dynamicLaneDecision"] = {
                "shouldSpawn": True,
                "suggestedLaneTypes": ["security"],
                "reason": "The current round still lacks a dedicated hostile-actor lane.",
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
                                "text": json.dumps(summary, ensure_ascii=False),
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
            return summary, "resp_dynamic", response, call_meta

        runtime.new_live_summary = fake_live_summary  # type: ignore[method-assign]

        result = runtime.run_summarizer()
        assert_true(result["exitCode"] == 0, "Expected summarizer run to complete.")

        final_state = runtime.read_state()
        active_task = final_state.get("activeTask") if isinstance(final_state.get("activeTask"), dict) else {}
        active_workers = task_workers(active_task)
        worker_ids = [worker["id"] for worker in active_workers]
        worker_types = {worker["id"]: worker.get("type") for worker in active_workers}
        summary = final_state.get("summary") if isinstance(final_state.get("summary"), dict) else {}

        assert_true("C" in worker_ids, "Expected dynamic spin-up to add worker C.")
        assert_true(worker_types.get("C") == "security", "Expected worker C to use the security lane type.")
        assert_true(final_state.get("workers", {}).get("C") is None, "Expected new worker state slot to be initialized to null.")
        assert_true(bool(summary.get("dynamicLaneDecision", {}).get("shouldSpawn")), "Expected persisted summary lane decision.")

        steps_text = Path(temp_dir, "data", "steps.jsonl").read_text(encoding="utf-8")
        assert_true('"stage": "dynamic_lane"' in steps_text, "Expected dynamic lane audit step.")

        print(
            json.dumps(
                {
                    "status": "ok",
                    "workerIds": worker_ids,
                    "spawnedType": worker_types.get("C"),
                    "memoryVersion": final_state.get("memoryVersion"),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
