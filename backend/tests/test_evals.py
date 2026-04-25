from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app import evals
from runtime.engine import RuntimeErrorWithCode


class EvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_start_eval_run_redirects_to_front_eval_mode(self) -> None:
        with self.assertRaises(RuntimeErrorWithCode) as ctx:
            evals.start_eval_run({"suiteId": "suite-a", "armIds": ["arm-a"]}, self.root)

        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("Front mode to Eval", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
