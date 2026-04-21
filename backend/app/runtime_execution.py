from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from runtime.engine import LoopRuntime, RuntimeErrorWithCode

from .config import deployment_topology


def run_target(runtime: LoopRuntime, target: str, task_id: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    execution_options = dict(options or {})
    topology = deployment_topology(runtime.root)
    if topology.runtime_execution_backend != "runtime_service":
        return runtime.run_target(target, task_id, execution_options)

    service_url = str(topology.runtime_service_url or "").strip()
    if not service_url:
        raise RuntimeErrorWithCode("Runtime execution backend is set to runtime_service, but LOOP_RUNTIME_SERVICE_URL is missing.", 500)

    body = json.dumps(
        {
            "target": target,
            "taskId": task_id,
            "options": execution_options,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        service_url.rstrip("/") + "/run-target",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout_seconds = max(60, int(execution_options.get("timeoutSeconds") or 1860))
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as handle:
            payload = json.loads(handle.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeErrorWithCode(f"Runtime service request failed: HTTP {error.code} | {detail}", 500) from error
    except Exception as error:
        raise RuntimeErrorWithCode(f"Runtime service request failed: {error}", 500) from error

    if not isinstance(payload, dict):
        raise RuntimeErrorWithCode("Runtime service returned a malformed payload.", 500)
    if not payload.get("ok"):
        raise RuntimeErrorWithCode(str(payload.get("message") or "Runtime service reported a failure."), 500)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeErrorWithCode("Runtime service did not return a result object.", 500)
    return result
