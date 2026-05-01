from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app import repo_graph


class RepoGraphTests(unittest.TestCase):
    def test_build_repo_graph_returns_ai_readout_and_scoped_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text(
                "\n".join(
                    [
                        "def entry():",
                        "    helper()",
                        "    print('done')",
                        "",
                        "def helper():",
                        "    return 1",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "ui.js").write_text(
                "\n".join(
                    [
                        "export function renderThing() {",
                        "  paintThing();",
                        "}",
                        "function paintThing() {",
                        "  return true;",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )

            payload = repo_graph.build_repo_graph(root)

        self.assertEqual(payload["schemaVersion"], "repo-function-graph/v1")
        self.assertEqual(payload["stats"]["filesScanned"], 2)
        self.assertGreaterEqual(payload["stats"]["functionsFound"], 4)
        self.assertTrue(payload["edges"])
        self.assertIn("aiReadout", payload)
        self.assertTrue(payload["aiReadout"]["topHotspots"])
        self.assertEqual(payload["aiReadout"]["claimCalibration"]["fact"].startswith("Nodes are detected"), True)


if __name__ == "__main__":
    unittest.main()
