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

    def test_build_repo_graph_respects_gitignore_and_generated_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text(
                "\n".join(
                    [
                        "tmp/",
                        "data/outputs/",
                        "data/evals/*",
                        "!data/evals/arms/",
                        "!data/evals/arms/*.json",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "backend").mkdir()
            (root / "backend" / "app.py").write_text(
                "def useful():\n    return 1\n",
                encoding="utf-8",
            )
            generated = root / "qa" / "edge-cdp-clean" / "Default" / "Extensions" / "x" / "1.0"
            generated.mkdir(parents=True)
            (generated / "service_worker_bin_prod.js").write_text(
                "function noisy(){ noisy(); }\n" * 20,
                encoding="utf-8",
            )
            tmp_dir = root / "tmp"
            tmp_dir.mkdir()
            (tmp_dir / "scratch.js").write_text("function scratch(){ return true; }\n", encoding="utf-8")
            output_dir = root / "data" / "outputs"
            output_dir.mkdir(parents=True)
            (output_dir / "artifact.py").write_text("def artifact():\n    return 1\n", encoding="utf-8")

            payload = repo_graph.build_repo_graph(root)

        files = {str(item["path"]) for item in payload["files"]}
        self.assertIn("backend/app.py", files)
        self.assertFalse(any(path.startswith("qa/") for path in files))
        self.assertFalse(any(path.startswith("tmp/") for path in files))
        self.assertFalse(any(path.startswith("data/outputs/") for path in files))
        self.assertGreaterEqual(payload["stats"]["gitIgnoreRulesLoaded"], 1)

    def test_resolve_scan_root_stays_inside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend").mkdir()

            self.assertEqual(repo_graph.resolve_scan_root(root, "backend"), (root / "backend").resolve())
            with self.assertRaises(ValueError):
                repo_graph.resolve_scan_root(root, "../outside")


if __name__ == "__main__":
    unittest.main()
