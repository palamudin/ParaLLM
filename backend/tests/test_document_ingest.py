from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.app import document_ingest, storage


class DocumentIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_download(self, name: str, payload: bytes, content_type: str) -> str:
        digest = hashlib.sha256(payload).hexdigest()
        artifact_id = "download_" + digest[:16]
        target = document_ingest.artifact_dir(self.root, artifact_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / name).write_bytes(payload)
        (target / "manifest.json").write_text(
            json.dumps(
                {
                    "artifactId": artifact_id,
                    "kind": "download",
                    "url": f"https://docs.example.test/{name}",
                    "finalUrl": f"https://docs.example.test/{name}",
                    "fileName": name,
                    "contentType": content_type,
                    "bytes": len(payload),
                    "sha256": digest,
                }
            ),
            encoding="utf-8",
        )
        return artifact_id

    def test_text_ingest_produces_stable_source_addressed_chunks(self) -> None:
        payload = (
            "Para service manual\n\n"
            "Before calibration, isolate the actuator and preserve the original profile.\n"
            "Record the serial number before replacing any component.\n"
        ).encode("utf-8")
        artifact_id = self.write_download("manual.txt", payload, "text/plain")

        first = document_ingest.ingest_artifact(self.root, artifact_id)
        second = document_ingest.ingest_artifact(self.root, artifact_id)

        self.assertEqual(first["sourceSha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(first["chunkCount"], 1)
        self.assertEqual(first["chunks"][0]["id"], second["chunks"][0]["id"])
        self.assertIn("isolate the actuator", first["chunks"][0]["text"])
        self.assertTrue((storage.project_paths(self.root).data / "research" / "downloads" / artifact_id / "extracted.json").is_file())

    def test_docx_ingest_extracts_paragraph_text_without_office_runtime(self) -> None:
        package = self.root / "manual.docx"
        document_xml = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Torque the fastener to 42 Nm.</w:t></w:r></w:p>
            <w:p><w:r><w:t>Recheck after the first heat cycle.</w:t></w:r></w:p>
          </w:body>
        </w:document>"""
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("word/document.xml", document_xml)
        artifact_id = self.write_download(
            "manual.docx",
            package.read_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        result = document_ingest.ingest_artifact(self.root, artifact_id)

        extracted = "\n".join(chunk["text"] for chunk in result["chunks"])
        self.assertIn("Torque the fastener to 42 Nm.", extracted)
        self.assertIn("Recheck after the first heat cycle.", extracted)

    def test_ingest_rejects_bytes_that_no_longer_match_manifest_hash(self) -> None:
        artifact_id = self.write_download("manual.txt", b"trusted source bytes", "text/plain")
        target, _manifest = document_ingest.resolve_downloaded_file(self.root, artifact_id)
        target.write_bytes(b"tampered bytes")

        with self.assertRaisesRegex(document_ingest.DocumentIngestError, "SHA-256 integrity"):
            document_ingest.ingest_artifact(self.root, artifact_id)


if __name__ == "__main__":
    unittest.main()
