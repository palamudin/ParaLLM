from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app import knowledgebase, storage, web_access


class WebAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_private_and_credential_bearing_urls_fail_closed(self) -> None:
        policy = web_access.BrowserPolicy()

        with self.assertRaisesRegex(web_access.WebAccessError, "Private, loopback"):
            web_access.assert_safe_url("http://127.0.0.1/private", policy)
        with self.assertRaisesRegex(web_access.WebAccessError, "Credential-bearing"):
            web_access.assert_safe_url("https://user:secret@example.com/manual", policy)

    def test_domain_allowlist_is_applied_before_navigation(self) -> None:
        policy = web_access.BrowserPolicy(allowed_domains=("example.com",))

        with self.assertRaisesRegex(web_access.WebAccessError, "outside the research allowlist"):
            web_access.assert_safe_url("https://example.net/manual", policy)

    def test_bing_result_redirect_is_unwrapped_before_navigation(self) -> None:
        wrapped = (
            "https://www.bing.com/ck/a?u="
            "a1aHR0cHM6Ly9kb2NzLnB5dGhvbi5vcmcvMy4xMi8"
        )

        self.assertEqual(web_access._unwrap_search_url(wrapped), "https://docs.python.org/3.12/")

    def test_exact_page_chunks_can_be_promoted_to_durable_memory(self) -> None:
        artifact_id = "page_sourcefixture"
        source_text = "Calibration datum: 17.25 mm."
        page_dir = storage.project_paths(self.root).data / "research" / "pages"
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / f"{artifact_id}.json").write_text(
            json.dumps(
                {
                    "artifactId": artifact_id,
                    "kind": "page",
                    "title": "Actuator calibration manual",
                    "url": "https://docs.example.test/actuator",
                    "finalUrl": "https://docs.example.test/actuator",
                    "sha256": "source-sha",
                    "chunks": [
                        {
                            "id": "chunk_exactdatum",
                            "ordinal": 1,
                            "locator": "page",
                            "text": source_text,
                            "sha256": "chunk-sha",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = web_access.retain_artifact_chunks(
            self.root,
            artifact_id=artifact_id,
            chunk_ids=["chunk_exactdatum", "chunk_not_present"],
            bank_id="manual-bank",
            rationale="Stable calibration reference for the current device.",
            tags=["manual", "calibration"],
        )
        recall = knowledgebase.recall(
            self.root,
            query="actuator calibration datum",
            bank_id="manual-bank",
            include_runtime=False,
            include_persistent=True,
        )

        self.assertEqual(result["acceptedChunkIds"], ["chunk_exactdatum"])
        self.assertTrue(result["sourceImmutable"])
        self.assertEqual(recall["resultCount"], 1)
        self.assertIn(source_text, recall["hits"][0]["text"])
        self.assertEqual(recall["hits"][0]["metadata"]["artifactId"], artifact_id)
        self.assertEqual(recall["hits"][0]["metadata"]["chunkId"], "chunk_exactdatum")

    def test_retain_rejects_unknown_or_empty_chunk_selection(self) -> None:
        artifact_id = "page_rejectfixture"
        page_dir = storage.project_paths(self.root).data / "research" / "pages"
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / f"{artifact_id}.json").write_text(
            json.dumps(
                {
                    "artifactId": artifact_id,
                    "kind": "page",
                    "url": "https://docs.example.test/reject",
                    "chunks": [{"id": "chunk_real", "locator": "page", "text": "Real source text."}],
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(web_access.WebAccessError, "No valid source chunk ids"):
            web_access.retain_artifact_chunks(
                self.root,
                artifact_id=artifact_id,
                chunk_ids=["chunk_invented"],
            )

    def test_retain_rejects_source_that_is_not_memory_eligible(self) -> None:
        artifact_id = "page_imageboardfixture"
        page_dir = storage.project_paths(self.root).data / "research" / "pages"
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / f"{artifact_id}.json").write_text(
            json.dumps(
                {
                    "artifactId": artifact_id,
                    "kind": "page",
                    "url": "https://boards.4chan.org/g/thread/123",
                    "chunks": [{"id": "chunk_claim", "locator": "page", "text": "Anonymous claim."}],
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(web_access.WebAccessError, "not eligible for durable memory"):
            web_access.retain_artifact_chunks(
                self.root,
                artifact_id=artifact_id,
                chunk_ids=["chunk_claim"],
            )


if __name__ == "__main__":
    unittest.main()
