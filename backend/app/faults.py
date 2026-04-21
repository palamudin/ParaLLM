from __future__ import annotations

import os
import re
from typing import Iterable, Optional

from runtime.engine import RuntimeErrorWithCode


def configured_fault_points() -> set[str]:
    raw = str(os.getenv("LOOP_FAULT_POINTS") or "").strip()
    if not raw:
        return set()
    values = re.split(r"[\s,]+", raw)
    return {value.strip() for value in values if value.strip()}


def active_fault_point(*candidates: str) -> Optional[str]:
    configured = configured_fault_points()
    if not configured:
        return None
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if normalized and normalized in configured:
            return normalized
    return None


def maybe_raise_fault(*candidates: str, status_code: int = 500) -> None:
    triggered = active_fault_point(*candidates)
    if not triggered:
        return
    raise RuntimeErrorWithCode(f"Injected fault at {triggered}.", status_code)


def fault_metadata(*candidates: str) -> dict[str, object]:
    triggered = active_fault_point(*candidates)
    return {
        "configured": bool(configured_fault_points()),
        "triggered": bool(triggered),
        "point": triggered,
        "candidates": [str(candidate or "").strip() for candidate in candidates if str(candidate or "").strip()],
    }
