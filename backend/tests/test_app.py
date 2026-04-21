from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.app.main import create_app


class AppRouteTests(unittest.TestCase):
    def test_expected_routes_are_registered(self) -> None:
        app = create_app()
        paths = {route.path for route in app.routes}

        self.assertIn("/", paths)
        self.assertIn("/index.html", paths)
        self.assertIn("/health", paths)
        self.assertIn("/v1/system/topology", paths)
        self.assertIn("/v1/system/infrastructure", paths)
        self.assertIn("/v1/auth/status", paths)
        self.assertIn("/v1/auth/keys", paths)
        self.assertIn("/v1/state", paths)
        self.assertIn("/v1/state/reset", paths)
        self.assertIn("/v1/history", paths)
        self.assertIn("/v1/events", paths)
        self.assertIn("/v1/steps", paths)
        self.assertIn("/v1/artifacts/{name}", paths)
        self.assertIn("/v1/artifact", paths)
        self.assertIn("/v1/evals/history", paths)
        self.assertIn("/v1/evals/runs", paths)
        self.assertIn("/v1/evals/artifact", paths)
        self.assertIn("/v1/evals/artifacts/{run_id}/{artifact_id}", paths)
        self.assertIn("/v1/draft", paths)
        self.assertIn("/v1/tasks", paths)
        self.assertIn("/v1/session/reset", paths)
        self.assertIn("/v1/session/replay", paths)
        self.assertIn("/v1/session/export", paths)
        self.assertIn("/v1/runtime/apply", paths)
        self.assertIn("/v1/workers/update", paths)
        self.assertIn("/v1/workers/add", paths)
        self.assertIn("/v1/positions/model", paths)
        self.assertIn("/v1/loops", paths)
        self.assertIn("/v1/loops/cancel", paths)
        self.assertIn("/v1/jobs/manage", paths)
        self.assertIn("/v1/targets/background", paths)
        self.assertIn("/v1/rounds", paths)
        self.assertIn("/v1/targets/run", paths)

    def test_root_serves_python_shell_defaults(self) -> None:
        client = TestClient(create_app())
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("assets/app.js", response.text)
        self.assertIn("assets/vendor/jquery/jquery-3.7.1.min.js", response.text)
        self.assertIn('id="headerApiMode"', response.text)

    def test_topology_endpoint_reports_local_single_node_defaults(self) -> None:
        client = TestClient(create_app())
        response = client.get("/v1/system/topology")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["profile"], "local-single-node")
        self.assertEqual(payload["queueBackend"], "local_subprocess")
        self.assertEqual(payload["metadataBackend"], "json_files")
        self.assertEqual(payload["artifactBackend"], "filesystem")
        self.assertEqual(payload["secretBackend"], "local_file")
        self.assertEqual(payload["runtimeExecutionBackend"], "embedded_engine_subprocess")

    def test_infrastructure_endpoint_reports_local_defaults_ready(self) -> None:
        client = TestClient(create_app())
        response = client.get("/v1/system/infrastructure")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["profile"], "local-single-node")
        self.assertIn("backends", payload)
        self.assertEqual(payload["backends"]["queue"]["backend"], "local_subprocess")
        self.assertEqual(payload["backends"]["metadata"]["backend"], "json_files")
        self.assertEqual(payload["backends"]["artifacts"]["backend"], "filesystem")


if __name__ == "__main__":
    unittest.main()
