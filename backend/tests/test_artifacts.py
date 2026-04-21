from __future__ import annotations

import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from backend.app import storage
from runtime.engine import LoopRuntime


class FakeObjectStore:
    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, tuple[bytes, datetime]]] = {}

    def head_bucket(self, Bucket: str) -> None:
        if Bucket not in self.buckets:
            raise RuntimeError("missing bucket")

    def create_bucket(self, Bucket: str) -> None:
        self.buckets.setdefault(Bucket, {})

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str | None = None) -> None:  # noqa: ARG002
        self.buckets.setdefault(Bucket, {})[Key] = (bytes(Body), datetime.now(timezone.utc))

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        body, _timestamp = self.buckets[Bucket][Key]
        return {"Body": io.BytesIO(body)}

    def list_objects_v2(self, Bucket: str, Prefix: str = "", ContinuationToken: str | None = None) -> dict[str, object]:  # noqa: ARG002
        contents = []
        for key, (body, modified) in sorted(self.buckets.get(Bucket, {}).items()):
            if not key.startswith(Prefix):
                continue
            contents.append({"Key": key, "Size": len(body), "LastModified": modified})
        return {"Contents": contents, "IsTruncated": False}


class ObjectStorageArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = FakeObjectStore()
        self.env = {
            "LOOP_ARTIFACT_BACKEND": "object_storage",
            "LOOP_OBJECT_STORE_URL": "http://object-store:9000",
            "LOOP_OBJECT_STORE_BUCKET": "parallm",
            "LOOP_OBJECT_STORE_ACCESS_KEY": "minioadmin",
            "LOOP_OBJECT_STORE_SECRET_KEY": "minioadmin",
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_output_artifact_roundtrip_through_object_storage(self) -> None:
        runtime = LoopRuntime(self.root)
        payload = {
            "taskId": "t-20260421-120000-deadbe",
            "artifactType": "summary_output",
            "target": "summarizer",
            "label": "Summarizer",
            "mode": "live",
            "model": "gpt-5-mini",
            "round": 1,
            "responseMeta": {"requestedMaxOutputTokens": 1200, "effectiveMaxOutputTokens": 2400},
        }
        history_name = "t-20260421-120000-deadbe_summary_round001_output.json"

        with mock.patch.dict("os.environ", self.env, clear=False), mock.patch("backend.app.artifacts._s3_client", return_value=self.store):
            runtime.write_output_artifact("t-20260421-120000-deadbe_summary_output.json", history_name, payload)
            artifact = storage.read_artifact(storage.project_paths(self.root), history_name)
            history = storage.build_history_payload(storage.project_paths(self.root))

        self.assertEqual(artifact["summary"]["taskId"], payload["taskId"])
        self.assertEqual(artifact["storage"], "outputs")
        self.assertTrue(any(item["name"] == history_name for item in history["artifacts"]))
        self.assertFalse((storage.project_paths(self.root).outputs / history_name).exists())

    def test_checkpoint_history_roundtrip_through_object_storage(self) -> None:
        runtime = LoopRuntime(self.root)
        task_id = "t-20260421-120000-cafe00"
        checkpoint = {
            "taskId": task_id,
            "artifactType": "worker_step",
            "workerId": "A",
            "modelUsed": "gpt-5-mini",
            "mode": "live",
            "step": 1,
        }

        with mock.patch.dict("os.environ", self.env, clear=False), mock.patch("backend.app.artifacts._s3_client", return_value=self.store):
            runtime.write_worker_checkpoint_files(task_id, "A", 1, checkpoint)
            history = storage.build_history_payload(storage.project_paths(self.root))

        names = {item["name"] for item in history["artifacts"]}
        self.assertIn(f"{task_id}_A_step001.json", names)


if __name__ == "__main__":
    unittest.main()
