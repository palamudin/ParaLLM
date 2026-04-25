from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import runtime_execution
from runtime.engine import LoopRuntime


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class RuntimeExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.runtime = LoopRuntime(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_embedded_runtime_calls_loopruntime_directly(self) -> None:
        with mock.patch.dict("os.environ", {"LOOP_RUNTIME_EXECUTION_BACKEND": "embedded_engine_subprocess"}, clear=False):
            with mock.patch.object(LoopRuntime, "run_target", return_value={"output": "ok", "exitCode": 0}) as run_target:
                result = runtime_execution.run_target(self.runtime, "A", "task-1", {})

        self.assertEqual(result["output"], "ok")
        run_target.assert_called_once_with("A", "task-1", {})

    def test_arbiter_target_uses_local_arbiter_runner(self) -> None:
        with mock.patch("backend.app.arbiter.run_current_task_arbiter", return_value={"output": "scored", "exitCode": 0}) as run_arbiter:
            result = runtime_execution.run_target(self.runtime, "arbiter", "task-9", {"force": True})

        self.assertEqual(result["output"], "scored")
        run_arbiter.assert_called_once_with(self.runtime, "task-9", {"force": True})

    def test_runtime_service_backend_calls_http_service(self) -> None:
        env = {
            "LOOP_RUNTIME_EXECUTION_BACKEND": "runtime_service",
            "LOOP_RUNTIME_SERVICE_URL": "http://127.0.0.1:8765",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            with mock.patch("urllib.request.urlopen", return_value=_FakeResponse({"ok": True, "result": {"output": "service", "exitCode": 0}})) as urlopen:
                result = runtime_execution.run_target(self.runtime, "summarizer", "task-2", {"partialSummary": True})

        self.assertEqual(result["output"], "service")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8765/run-target")


if __name__ == "__main__":
    unittest.main()
