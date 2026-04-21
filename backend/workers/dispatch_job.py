from __future__ import annotations

import argparse
from pathlib import Path

from runtime.engine import RuntimeErrorWithCode

from backend.app import dispatch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a background ParaLLM target-dispatch job.")
    parser.add_argument("--root", required=True, help="Absolute project root path.")
    parser.add_argument("--job-id", required=True, help="Target dispatch job id to execute.")
    parser.add_argument("--auth-path", default=None, help="Optional auth file override.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    auth_path = Path(args.auth_path).resolve() if args.auth_path else None
    try:
        dispatch.execute_target_job_process(args.job_id, root=root, auth_path=auth_path)
        return 0
    except RuntimeErrorWithCode as exc:
        print(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
