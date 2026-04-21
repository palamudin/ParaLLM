from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.app import queueing


class FakeRedis:
    def __init__(self) -> None:
        self._strings: dict[str, str] = {}
        self._lists: dict[str, list[str]] = {}

    def ping(self) -> bool:
        return True

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._strings:
                removed += 1
                del self._strings[key]
            if key in self._lists:
                removed += 1
                del self._lists[key]
        return removed

    def rpush(self, key: str, *values: str) -> int:
        bucket = self._lists.setdefault(key, [])
        bucket.extend(str(value) for value in values)
        return len(bucket)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        bucket = list(self._lists.get(key, []))
        if end == -1:
            end = len(bucket) - 1
        return bucket[start : end + 1]

    def lindex(self, key: str, index: int) -> str | None:
        bucket = self._lists.get(key, [])
        if index < 0 or index >= len(bucket):
            return None
        return bucket[index]

    def lpop(self, key: str) -> str | None:
        bucket = self._lists.get(key, [])
        if not bucket:
            return None
        value = bucket.pop(0)
        if not bucket:
            self._lists.pop(key, None)
        return value

    def get(self, key: str) -> str | None:
        return self._strings.get(key)

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self._strings:
            return False
        self._strings[key] = str(value)
        return True


class QueueingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.env = {
            "LOOP_QUEUE_BACKEND": "redis",
            "LOOP_REDIS_URL": "redis://example/0",
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_redis_loop_queue_claim_flow(self) -> None:
        fake = FakeRedis()
        task_id = "t-queue-test"
        with mock.patch.dict("os.environ", self.env, clear=False), mock.patch("backend.app.queueing._redis_client", return_value=fake):
            queueing.sync_loop_queue(self.root, task_id, ["job-a", "job-b"])
            claimed = queueing.claim_next_loop_job_id(self.root, task_id, ["job-a", "job-b"])

            self.assertEqual(claimed, "job-a")

            topology = queueing.deployment_topology(self.root)
            self.assertEqual(fake.get(queueing._loop_active_key(topology, task_id)), "job-a")
            self.assertEqual(fake.lrange(queueing._loop_queue_key(topology, task_id), 0, -1), ["job-b"])

            queueing.release_loop_claim(self.root, task_id, "job-a")
            claimed_second = queueing.claim_next_loop_job_id(self.root, task_id, ["job-b"])

            self.assertEqual(claimed_second, "job-b")
            self.assertEqual(fake.get(queueing._loop_active_key(topology, task_id)), "job-b")

    def test_redis_dispatch_launch_queue_drains_fifo(self) -> None:
        fake = FakeRedis()
        with mock.patch.dict("os.environ", self.env, clear=False), mock.patch("backend.app.queueing._redis_client", return_value=fake):
            queued = queueing.enqueue_dispatch_launches(self.root, ["dispatch-1", "dispatch-2", "dispatch-1"])
            drained = queueing.drain_dispatch_launches(self.root)

        self.assertEqual(queued, ["dispatch-1", "dispatch-2"])
        self.assertEqual(drained, ["dispatch-1", "dispatch-2"])


if __name__ == "__main__":
    unittest.main()
