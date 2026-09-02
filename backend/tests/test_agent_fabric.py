import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agent_fabric import AgentFabric, PRIMARY_AGENT_ID, PROCEED_DIRECTIVE
from backend.app.main import create_app


class AgentFabricTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "assets").mkdir(parents=True)
        self.fabric = AgentFabric(self.root, spawn_processes=False)

    def tearDown(self) -> None:
        self.fabric.close()
        self._tmp.cleanup()

    def create_projects_and_agent(self) -> tuple[str, str, str]:
        alpha = self.fabric.create_project("Alpha")["projectId"]
        beta = self.fabric.create_project("Beta")["projectId"]
        agent = self.fabric.create_agent(
            "Project Worker",
            "Complete bounded project work.",
            "Read only the selected project packet.",
            start=False,
        )["agentId"]
        self.fabric.assign(alpha, agent)
        self.fabric.assign(beta, agent)
        return alpha, beta, agent

    def test_board_is_strictly_partitioned_by_project(self) -> None:
        alpha, beta, agent = self.create_projects_and_agent()
        alpha_post = self.fabric.post(alpha, "alpha-only", target_agent_id=agent)
        self.fabric.post(beta, "beta-only", target_agent_id=agent)

        alpha_board = self.fabric.board(alpha, agent_id=agent)
        beta_board = self.fabric.board(beta, agent_id=agent)

        self.assertEqual([item["content"] for item in alpha_board["items"]], ["alpha-only"])
        self.assertEqual([item["content"] for item in beta_board["items"]], ["beta-only"])
        with self.assertRaisesRegex(ValueError, "does not belong to this project"):
            self.fabric.post(
                beta,
                "cross-project-injection",
                source_agent_id=agent,
                thread_id=alpha_post["threadId"],
            )

    def test_read_cursor_is_project_and_agent_scoped(self) -> None:
        alpha, beta, agent = self.create_projects_and_agent()
        alpha_message = self.fabric.post(alpha, "alpha-unread", target_agent_id=agent)
        self.fabric.post(beta, "beta-unread", target_agent_id=agent)

        self.fabric.mark_read(alpha, agent, alpha_message["sequence"])

        self.assertEqual(self.fabric.board(alpha, agent_id=agent, unread_only=True)["items"], [])
        self.assertEqual(
            [item["content"] for item in self.fabric.board(beta, agent_id=agent, unread_only=True)["items"]],
            ["beta-unread"],
        )

    def test_job_requires_project_membership_and_creates_project_thread(self) -> None:
        alpha = self.fabric.create_project("Alpha")["projectId"]
        beta = self.fabric.create_project("Beta")["projectId"]
        agent = self.fabric.create_agent("Alpha Worker", "Work only in Alpha.", start=False)["agentId"]
        self.fabric.assign(alpha, agent)

        submitted = self.fabric.submit(alpha, agent, "Inspect Alpha evidence.")

        self.assertEqual(submitted["projectId"], alpha)
        self.assertEqual(
            [item["content"] for item in self.fabric.board(alpha, agent_id=agent)["items"]],
            ["Inspect Alpha evidence."],
        )
        with self.assertRaisesRegex(ValueError, "must belong to the selected project"):
            self.fabric.submit(beta, agent, "This must not cross into Beta.")

    def test_steward_nudges_stalled_work_and_holds_showstoppers(self) -> None:
        alpha = self.fabric.create_project("Alpha")["projectId"]
        beta = self.fabric.create_project("Beta")["projectId"]
        agent = self.fabric.create_agent("Steward Worker", "Report progress and blockers.", start=False)["agentId"]
        self.fabric.assign(alpha, agent)
        self.fabric.assign(beta, agent)
        submitted = self.fabric.submit(alpha, agent, "Complete the project check.")
        instance_id = self.fabric.start_agent(agent)["instanceId"]
        claimed = self.fabric.claim_next_job(agent, instance_id)
        self.assertEqual(claimed["job_id"], submitted["jobId"])
        stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self.fabric.connect() as db:
            db.execute(
                "UPDATE agent_job SET last_progress_at=?,activity_at=?,heartbeat_at=? WHERE job_id=?",
                (stale, stale, stale, submitted["jobId"]),
            )

        first = self.fabric.steward_once()

        self.assertEqual(first["nudged"], 1)
        directives = self.fabric.directives(agent, job_id=submitted["jobId"])["items"]
        self.assertEqual(directives[-1]["kind"], "continue")
        self.assertEqual(directives[-1]["content"], PROCEED_DIRECTIVE)
        self.assertEqual(self.fabric.board(beta, agent_id=agent)["items"], [])

        self.fabric.report(
            submitted["jobId"],
            "blocked",
            "A human authorization artifact is missing.",
            blocker_severity="showstopper",
            required_resolution="Attach signed authorization.",
        )
        second = self.fabric.steward_once()

        self.assertEqual(second["held"], 1)
        directives = self.fabric.directives(agent, job_id=submitted["jobId"])["items"]
        self.assertEqual(directives[-1]["kind"], "hold")
        self.assertIn("Attach signed authorization", directives[-1]["content"])
        alpha_messages = [item["content"] for item in self.fabric.board(alpha, agent_id=PRIMARY_AGENT_ID)["items"]]
        self.assertIn(PROCEED_DIRECTIVE, alpha_messages)
        self.assertTrue(any("Show-stopper reported" in item for item in alpha_messages))

    def test_steward_does_not_nudge_during_fresh_runtime_activity(self) -> None:
        alpha = self.fabric.create_project("Alpha")["projectId"]
        agent = self.fabric.create_agent("Active Worker", "Remain observable while a vendor call runs.", start=False)["agentId"]
        self.fabric.assign(alpha, agent)
        submitted = self.fabric.submit(alpha, agent, "Wait for the active provider response.")
        instance_id = self.fabric.start_agent(agent)["instanceId"]
        self.fabric.claim_next_job(agent, instance_id)
        stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        fresh = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self.fabric.connect() as db:
            db.execute(
                "UPDATE agent_job SET last_progress_at=?,activity_at=?,heartbeat_at=? WHERE job_id=?",
                (stale, stale, fresh, submitted["jobId"]),
            )

        result = self.fabric.steward_once()

        self.assertEqual(result["nudged"], 0)
        self.assertEqual(result["skippedActive"], 1)
        self.assertEqual(self.fabric.directives(agent, job_id=submitted["jobId"])["items"], [])

    def test_schema_is_sqlite_and_contains_no_text_agent_state(self) -> None:
        with closing(sqlite3.connect(self.fabric.database)) as db:
            schema = db.execute(
                "SELECT value FROM agent_fabric_meta WHERE key='schema_version'"
            ).fetchone()[0]
            tables = {
                row[0]
                for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }

        self.assertEqual(schema, "parallm.python-agent-fabric.v1")
        self.assertIn("agent_project", tables)
        self.assertIn("agent_board_message", tables)
        self.assertFalse((self.root / "data" / "agents.txt").exists())

    def test_real_worker_process_registers_heartbeat_and_stops(self) -> None:
        process_fabric = AgentFabric(self.root, database=self.root / "data" / "process-agents.sqlite3", spawn_processes=True)
        try:
            result = process_fabric.create_agent("Process Worker", "Prove the Python PID lifecycle.")
            deadline = time.monotonic() + 8.0
            instance = None
            while time.monotonic() < deadline:
                instance = process_fabric.agents(query="Process Worker")["items"][0]["instance"]
                if instance and instance["status"] == "idle":
                    break
                time.sleep(0.1)

            self.assertIsNotNone(instance)
            self.assertEqual(instance["status"], "idle")
            self.assertGreater(int(instance["processId"] or 0), 0)
            process_fabric.stop_agent(str(result["agentId"]))
            stopped = process_fabric.agents(query="Process Worker")["items"][0]["instance"]
            self.assertEqual(stopped["status"], "stopped")
        finally:
            process_fabric.close()


class AgentFabricRouteTests(unittest.TestCase):
    def test_http_start_route_uses_durable_agent_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "assets").mkdir(parents=True)
            app = create_app(root)
            received: list[str] = []

            def start_agent(agent_id: str) -> dict[str, object]:
                received.append(agent_id)
                return {"ok": True, "agentId": agent_id, "instanceId": "instance_test", "processId": 123}

            app.state.agent_fabric.start_agent = start_agent
            response = TestClient(app).post("/v1/agents/start", data={"agentId": "agent_test"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(received, ["agent_test"])
            self.assertEqual(response.json()["instanceId"], "instance_test")

    def test_http_project_boards_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "assets").mkdir(parents=True)
            client = TestClient(create_app(root))
            alpha = client.post("/v1/agents/projects", data={"name": "Alpha"}).json()["projectId"]
            beta = client.post("/v1/agents/projects", data={"name": "Beta"}).json()["projectId"]
            self.assertEqual(
                client.post(
                    "/v1/agents/board",
                    data={"projectId": alpha, "kind": "note", "severity": "info", "content": "alpha-only"},
                ).status_code,
                201,
            )
            self.assertEqual(
                client.post(
                    "/v1/agents/board",
                    data={"projectId": beta, "kind": "note", "severity": "info", "content": "beta-only"},
                ).status_code,
                201,
            )

            alpha_items = client.get("/v1/agents/board", params={"projectId": alpha}).json()["items"]
            beta_items = client.get("/v1/agents/board", params={"projectId": beta}).json()["items"]

            self.assertEqual([item["content"] for item in alpha_items], ["alpha-only"])
            self.assertEqual([item["content"] for item in beta_items], ["beta-only"])


if __name__ == "__main__":
    unittest.main()
