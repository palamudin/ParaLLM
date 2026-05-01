from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.app import artifacts


class FakeObjectBody:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class FakeObjectStore:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}

    def head_bucket(self, Bucket: str) -> None:  # noqa: N803
        if Bucket not in self.buckets:
            raise RuntimeError("bucket not found")

    def create_bucket(self, Bucket: str) -> None:  # noqa: N803
        self.buckets.add(Bucket)

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str = "") -> None:  # noqa: N803
        self.buckets.add(Bucket)
        self.objects[(Bucket, Key)] = bytes(Body)

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:  # noqa: N803
        payload = self.objects[(Bucket, Key)]
        return {"Body": FakeObjectBody(payload)}

    def list_objects_v2(self, Bucket: str, Prefix: str = "", ContinuationToken: str | None = None) -> dict[str, object]:  # noqa: N803
        contents = []
        for (bucket, key), payload in sorted(self.objects.items(), key=lambda item: item[0][1]):
            if bucket != Bucket or not key.startswith(Prefix):
                continue
            contents.append(
                {
                    "Key": key,
                    "Size": len(payload),
                    "LastModified": datetime.now(timezone.utc),
                }
            )
        return {"Contents": contents, "IsTruncated": False}

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
        self.objects.pop((Bucket, Key), None)


class ArtifactWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_write_json_artifact_creates_category_path_in_fresh_workspace(self) -> None:
        payload = {"hello": "world"}

        meta = artifacts.write_json_artifact(self.root / "workspace", "checkpoints", "demo.json", payload)

        target = self.root / "workspace" / "data" / "checkpoints" / "demo.json"
        self.assertTrue(target.is_file())
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), payload)
        self.assertEqual(meta["category"], "checkpoints")
