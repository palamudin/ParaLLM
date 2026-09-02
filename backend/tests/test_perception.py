from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.app import perception
from backend.app.main import create_app
from runtime.engine import RuntimeErrorWithCode


def sample_event(event_id: str = "pad8pro-dev:boot:000001") -> dict:
    return {
        "schemaVersion": "percsi.perception-event.v1",
        "eventId": event_id,
        "observedAt": "2026-08-28T02:30:00+02:00",
        "sequence": 1,
        "monotonicNanos": 123456789,
        "source": {
            "deviceId": "xiaomi-pad-8-pro-dev-01",
            "channel": "system",
            "component": "percsi-body-bridge",
            "authority": "device_observation",
        },
        "scope": {
            "deploymentId": "local-development",
            "subjectType": "device",
            "subjectId": "xiaomi-pad-8-pro-dev-01",
        },
        "observation": {
            "kind": "body.heartbeat",
            "summary": "The PERCSI body bridge is visible and its event queue is operational.",
            "attributes": {"batteryPct": 81, "network": "wifi"},
        },
        "quality": {
            "confidence": 1.0,
            "novelty": 0.1,
            "urgency": 0.0,
            "clockUncertaintyMs": 25,
        },
        "relation": {"kind": "heartbeat", "references": []},
        "constraints": {
            "privacy": "device_only",
            "execution": "observe_only",
            "captureConsent": "not_required",
        },
        "evidence": {},
    }


class PerceptionContractTests(unittest.TestCase):
    def test_normalize_event_preserves_observation_and_removes_action_authority(self) -> None:
        event = perception.normalize_event(sample_event(), received_at="2026-08-28T00:30:01Z")

        self.assertEqual(event["observedAt"], "2026-08-28T00:30:00.000Z")
        self.assertEqual(event["receivedAt"], "2026-08-28T00:30:01.000Z")
        self.assertEqual(event["executionAuthority"], "none")
        self.assertEqual(event["observation"]["attributes"]["batteryPct"], 81)
        self.assertEqual(len(event["eventHash"]), 64)

    def test_normalize_event_requires_time_with_timezone(self) -> None:
        payload = sample_event()
        payload["observedAt"] = "2026-08-28T00:30:00"

        with self.assertRaises(RuntimeErrorWithCode) as caught:
            perception.normalize_event(payload)

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("timezone", str(caught.exception))

    def test_normalize_event_rejects_execution_request(self) -> None:
        payload = sample_event()
        payload["constraints"]["execution"] = "execute"

        with self.assertRaises(RuntimeErrorWithCode) as caught:
            perception.normalize_event(payload)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertIn("observe_only", str(caught.exception))

    def test_normalize_event_rejects_contract_drift(self) -> None:
        payload = sample_event()
        payload["silentAction"] = "reboot"

        with self.assertRaises(RuntimeErrorWithCode) as caught:
            perception.normalize_event(payload)

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("unsupported fields", str(caught.exception))

    def test_ingest_is_disabled_without_explicit_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(perception.PERCEPTION_INGEST_TOKEN_ENV, None)
            with self.assertRaises(RuntimeErrorWithCode) as caught:
                perception.ingest(Path(tmpdir), sample_event(), "Bearer body-token")

        self.assertEqual(caught.exception.status_code, 503)

    def test_ingest_is_idempotent_and_rejects_event_id_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(
            os.environ,
            {perception.PERCEPTION_INGEST_TOKEN_ENV: "body-token"},
            clear=False,
        ):
            root = Path(tmpdir)
            first = perception.ingest(root, sample_event(), "Bearer body-token")
            duplicate = perception.ingest(root, sample_event(), "Bearer body-token")
            changed = sample_event()
            changed["observation"]["summary"] = "Conflicting content under the same event id."

            with self.assertRaises(RuntimeErrorWithCode) as caught:
                perception.ingest(root, changed, "Bearer body-token")

            listed = perception.list_events(root)

        self.assertTrue(first["accepted"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(listed["count"], 1)


class PerceptionRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "assets").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_status_is_available_but_ingest_requires_configuration(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(perception.PERCEPTION_INGEST_TOKEN_ENV, None)
            client = TestClient(create_app(self.root))
            status_response = client.get("/v1/perception/status")
            ingest_response = client.post("/v1/perception/events", json=sample_event())

        self.assertEqual(status_response.status_code, 200)
        self.assertFalse(status_response.json()["ingestEnabled"])
        self.assertEqual(ingest_response.status_code, 503)

    def test_authenticated_event_round_trip(self) -> None:
        with mock.patch.dict(
            os.environ,
            {perception.PERCEPTION_INGEST_TOKEN_ENV: "body-token"},
            clear=False,
        ):
            client = TestClient(create_app(self.root))
            headers = {"Authorization": "Bearer body-token"}
            ingest_response = client.post("/v1/perception/events", headers=headers, json=sample_event())
            list_response = client.get("/v1/perception/events", headers=headers)

        self.assertEqual(ingest_response.status_code, 202)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["events"][0]["eventId"], "pad8pro-dev:boot:000001")
        self.assertEqual(list_response.json()["executionAuthority"], "none")
