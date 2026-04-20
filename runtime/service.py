from __future__ import annotations

import argparse
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from engine import LoopRuntime, RuntimeErrorWithCode


STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_handler(runtime: LoopRuntime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LoopRuntime/1.0"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "service": "python-runtime",
                        "startedAt": STARTED_AT,
                        "pid": os.getpid(),
                    },
                )
                return
            self.send_json(404, {"message": "Not found."})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/run-target":
                stop_heartbeat = None
                heartbeat_thread = None
                try:
                    payload = self.read_json_body()
                    target = str(payload.get("target", "")).strip()
                    task_id = payload.get("taskId")
                    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
                    if not target:
                        raise RuntimeErrorWithCode("Target is required.", 400)
                    dispatch_job_id = str(options.get("dispatchJobId") or "").strip()
                    if dispatch_job_id:
                        heartbeat_message = str(
                            options.get("dispatchHeartbeatMessage")
                            or f"Waiting on {target} response..."
                        ).strip()
                        stop_heartbeat = threading.Event()

                        def keepalive() -> None:
                            while not stop_heartbeat.wait(10.0):
                                try:
                                    runtime.heartbeat_dispatch_job(dispatch_job_id, heartbeat_message)
                                except Exception:
                                    return

                        heartbeat_thread = threading.Thread(
                            target=keepalive,
                            name=f"dispatch-heartbeat-{dispatch_job_id}",
                            daemon=True,
                        )
                        heartbeat_thread.start()
                    result = runtime.run_target(target, str(task_id).strip() if task_id else None, options)
                    self.send_json(200, {"ok": True, "result": result})
                except RuntimeErrorWithCode as error:
                    self.send_json(error.status_code, {"message": str(error)})
                except Exception as error:
                    self.send_json(500, {"message": str(error)})
                finally:
                    if stop_heartbeat is not None:
                        stop_heartbeat.set()
                    if heartbeat_thread is not None:
                        heartbeat_thread.join(timeout=1.0)
                return
            self.send_json(404, {"message": "Not found."})

        def log_message(self, format: str, *args: Any) -> None:
            return

        def read_json_body(self) -> Dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
            if not raw.strip():
                return {}
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as error:
                raise RuntimeErrorWithCode(f"Invalid JSON body: {error}", 400)
            if not isinstance(payload, dict):
                raise RuntimeErrorWithCode("Request body must be a JSON object.", 400)
            return payload

        def send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resident Python runtime for the loop prototype.")
    parser.add_argument("--root", required=True, help="Absolute project root path.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    runtime = LoopRuntime(root)
    runtime.ensure_data_paths()
    server = ThreadingHTTPServer((args.host, args.port), build_handler(runtime))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
