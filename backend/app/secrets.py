from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from .config import deployment_topology


def normalize_auth_key_pool(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else str(value or "").splitlines()
    keys: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        key = str(entry or "").strip()
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def env_secret_keys() -> list[str]:
    raw = str(os.getenv("LOOP_OPENAI_API_KEYS") or os.getenv("OPENAI_API_KEYS") or "").strip()
    if not raw:
        return []
    return normalize_auth_key_pool(raw.replace(",", "\n"))


def _external_secret_request(url: str, token: str = "", timeout: float = 5.0) -> str:
    headers = {"Accept": "application/json, text/plain;q=0.9, */*;q=0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _parse_external_secret_payload(text: str) -> list[str]:
    body = str(text or "").strip()
    if not body:
        return []
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return normalize_auth_key_pool(body)
    if isinstance(parsed, list):
        return normalize_auth_key_pool(parsed)
    if isinstance(parsed, dict):
        candidates = [
            parsed.get("keys"),
            parsed.get("apiKeys"),
            ((parsed.get("data") or {}) if isinstance(parsed.get("data"), dict) else {}).get("keys"),
            ((parsed.get("data") or {}) if isinstance(parsed.get("data"), dict) else {}).get("apiKeys"),
        ]
        for candidate in candidates:
            if candidate is not None:
                return normalize_auth_key_pool(candidate)
    return []


def external_secret_keys(root: Optional[Path] = None, timeout: float = 5.0) -> list[str]:
    topology = deployment_topology(root)
    url = str(os.getenv("LOOP_SECRET_PROVIDER_URL") or topology.secret_provider_url or "").strip()
    if not url:
        return []
    token = str(os.getenv("LOOP_SECRET_PROVIDER_TOKEN") or "").strip()
    try:
        payload = _external_secret_request(url, token=token, timeout=timeout)
    except urllib.error.HTTPError:
        return []
    except Exception:
        return []
    return _parse_external_secret_payload(payload)
