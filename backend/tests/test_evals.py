from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import evals, storage
from backend.tests.test_metadata import FakeConnection, FakePostgresStore


class EvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.paths = storage.project_paths(self.root)
        self.paths.eval_suites.mkdir(parents=True, exist_ok=True)
        self.paths.eval_arms.mkdir(parents=True, exist_ok=True)
        (self.paths.eval_suites / "suite-a.json").write_text(
            json.dumps(
                {
                    "suiteId": "suite-a",
                    "title": "Suite A",
                    "description": "Test suite",
                    "cases": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (self.paths.eval_arms / "arm-a.json").write_text(
            json.dumps(
                {
                    "armId": "arm-a",
                    "title": "Arm A",
                    "type": "direct",
                    "runtime": {"model": "gpt-5-mini"},
                    "workers": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _postgres_connect_patch(self, store: FakePostgresStore):
        return mock.patch("backend.app.metadata.psycopg.connect", side_effect=lambda *args, **kwargs: FakeConnection(store))

    def test_start_eval_run_writes_manifest_and_launches_runner(self) -> None:
        with mock.patch("backend.app.evals.launch_eval_runner") as launcher:
            result = evals.start_eval_run(
                {
                    "suiteId": "suite-a",
                    "armIds": ["arm-a"],
                    "replicates": 2,
                    "loopSweep": "1,2",
                    "judgeModel": "gpt-5.4",
                },
                self.root,
            )

        self.assertEqual(result["message"], "Eval run queued.")
        launcher.assert_called_once()
        run = storage.read_eval_run(self.paths, result["runId"])
        self.assertIsInstance(run, dict)
        self.assertEqual(run["suiteId"], "suite-a")
        self.assertEqual(run["armIds"], ["arm-a"])
        self.assertEqual(run["replicates"], 2)
        self.assertEqual(run["loopSweep"], [1, 2])

    def test_start_eval_run_rejects_unknown_arm(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            evals.start_eval_run({"suiteId": "suite-a", "armIds": ["missing"]}, self.root)

        self.assertIn("Unknown eval arm", str(ctx.exception))

    def test_start_eval_run_uses_metadata_backend_for_run_state(self) -> None:
        store = FakePostgresStore()
        env = {
            "LOOP_METADATA_BACKEND": "postgres",
            "LOOP_DATABASE_URL": f"postgresql://fake/{self.root.name}",
        }
        with mock.patch.dict("os.environ", env, clear=False), self._postgres_connect_patch(store), mock.patch("backend.app.evals.launch_eval_runner") as launcher:
            result = evals.start_eval_run(
                {
                    "suiteId": "suite-a",
                    "armIds": ["arm-a"],
                },
                self.root,
            )
            run = storage.read_eval_run(self.paths, result["runId"])

        self.assertEqual(run["suiteId"], "suite-a")
        self.assertFalse((self.paths.eval_runs / result["runId"] / "run.json").exists())
        launcher.assert_called_once()


if __name__ == "__main__":
    unittest.main()
