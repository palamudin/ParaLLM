from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from backend.app.background import InProcessPool
from runtime.timing import timing_path


class InProcessBackgroundTests(unittest.TestCase):
    def test_pool_executes_without_a_host_process_and_records_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            completed = threading.Event()
            pool = InProcessPool("test", 1, queue_capacity=2)

            task_id = pool.submit("proof", root, completed.set)

            self.assertTrue(completed.wait(2.0))
            deadline = time.monotonic() + 2.0
            entry = None
            while time.monotonic() < deadline:
                entry = next((item for item in pool.snapshot()["recent"] if item["taskId"] == task_id), None)
                if entry and entry["status"] == "completed":
                    break
                time.sleep(0.01)

            self.assertIsNotNone(entry)
            self.assertEqual(entry["status"], "completed")
            records = [json.loads(line) for line in timing_path(root).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[-1]["schemaVersion"], "parallm.timing.v1")
            self.assertEqual(records[-1]["stage"], "test.execute")
            self.assertEqual(records[-1]["status"], "completed")
            self.assertGreaterEqual(records[-1]["durationNs"], 0)

    def test_pool_contains_task_failure_and_keeps_worker_alive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pool = InProcessPool("test-error", 1, queue_capacity=2)
            recovered = threading.Event()

            def fail() -> None:
                raise ValueError("expected")

            failed_id = pool.submit("failure", root, fail)
            pool.submit("recovery", root, recovered.set)
            self.assertTrue(recovered.wait(2.0))
            deadline = time.monotonic() + 2.0
            failed = None
            while time.monotonic() < deadline:
                failed = next((item for item in pool.snapshot()["recent"] if item["taskId"] == failed_id), None)
                if failed and failed["status"] == "error":
                    break
                time.sleep(0.01)

            self.assertEqual(failed["status"], "error")
            self.assertEqual(failed["errorType"], "ValueError")


if __name__ == "__main__":
    unittest.main()
