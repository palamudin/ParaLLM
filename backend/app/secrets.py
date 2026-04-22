from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from .config import deployment_topology


AUTH_KEY_PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "envVars": ["LOOP_OPENAI_API_KEYS", "OPENAI_API_KEYS"],
        "dockerSecretName": "openai_api_keys",
        "localFileName": "Auth.txt",
    },
    "anthropic": {
        "label": "Anthropic",
        "envVars": ["LOOP_ANTHROPIC_API_KEYS", "ANTHROPIC_API_KEYS"],
        "dockerSecretName": "anthropic_api_keys",
        "localFileName": "Auth.anthropic.txt",
    },
    "xai": {
        "label": "xAI",
        "envVars": ["LOOP_XAI_API_KEYS", "XAI_API_KEYS"],
        "dockerSecretName": "xai_api_keys",
        "localFileName": "Auth.xai.txt",
    },
    "minimax": {
        "label": "MiniMax",
        "envVars": ["LOOP_MINIMAX_API_KEYS", "MINIMAX_API_KEYS"],
        "dockerSecretName": "minimax_api_keys",
        "localFileName": "Auth.minimax.txt",
    },
}
AUTH_KEY_PROVIDER_ORDER = list(AUTH_KEY_PROVIDER_CATALOG.keys())
DEFAULT_AUTH_KEY_PROVIDER = "openai"


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


def auth_key_provider_ids() -> list[str]:
    return list(AUTH_KEY_PROVIDER_ORDER)


def normalize_auth_key_provider(provider: Any, fallback: str = DEFAULT_AUTH_KEY_PROVIDER) -> str:
    candidate = str(provider or "").strip().lower()
    if candidate in AUTH_KEY_PROVIDER_CATALOG:
        return candidate
    normalized_fallback = str(fallback or DEFAULT_AUTH_KEY_PROVIDER).strip().lower()
    return normalized_fallback if normalized_fallback in AUTH_KEY_PROVIDER_CATALOG else DEFAULT_AUTH_KEY_PROVIDER


def auth_key_provider_label(provider: Any) -> str:
    normalized = normalize_auth_key_provider(provider)
    return str((AUTH_KEY_PROVIDER_CATALOG.get(normalized) or {}).get("label") or normalized.title())


def auth_key_env_vars(provider: Any) -> list[str]:
    normalized = normalize_auth_key_provider(provider)
    catalog = AUTH_KEY_PROVIDER_CATALOG.get(normalized) or {}
    return [str(name) for name in catalog.get("envVars", []) if str(name).strip()]


def auth_key_file_path(base_path: Path, provider: Any) -> Path:
    normalized = normalize_auth_key_provider(provider)
    if normalized == DEFAULT_AUTH_KEY_PROVIDER:
        return base_path

    catalog = AUTH_KEY_PROVIDER_CATALOG.get(normalized) or {}
    name = str(catalog.get("dockerSecretName") or "").strip()
    if name and base_path.name.lower().endswith("openai_api_keys"):
        return base_path.with_name(name)

    local_name = str(catalog.get("localFileName") or "").strip()
    if local_name and base_path.name.lower() == "auth.txt":
        return base_path.with_name(local_name)

    suffix = base_path.suffix
    stem = base_path.stem if suffix else base_path.name
    extension = suffix or ".txt"
    return base_path.with_name(f"{stem}.{normalized}{extension}")


def provider_env_secret_keys(provider: Any) -> list[str]:
    for env_name in auth_key_env_vars(provider):
        raw = str(os.getenv(env_name) or "").strip()
        if raw:
            return normalize_auth_key_pool(raw.replace(",", "\n"))
    return []


def env_secret_keys(provider: Any = DEFAULT_AUTH_KEY_PROVIDER) -> list[str]:
    return provider_env_secret_keys(provider)


def env_secret_status(provider: Any = DEFAULT_AUTH_KEY_PROVIDER) -> dict[str, Any]:
    normalized = normalize_auth_key_provider(provider)
    keys = provider_env_secret_keys(normalized)
    env_vars = auth_key_env_vars(normalized)
    env_detail = " or ".join(env_vars) if env_vars else "provider env vars"
    label = auth_key_provider_label(normalized)
    return {
        "backend": "env",
        "provider": normalized,
        "configured": True,
        "ready": len(keys) > 0,
        "keys": keys,
        "failureMode": None if keys else "empty",
        "detail": f"Using env-provided {label} API keys from {env_detail}." if keys else f"No environment {label} API keys are configured in {env_detail}.",
    }


def _external_secret_request(url: str, token: str = "", timeout: float = 5.0) -> str:
    headers = {"Accept": "application/json, text/plain;q=0.9, */*;q=0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _parse_external_secret_candidate(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        for key in ("keys", "apiKeys"):
            if value.get(key) is not None:
                return normalize_auth_key_pool(value.get(key))
    return normalize_auth_key_pool(value)


def _empty_external_groups() -> dict[str, list[str]]:
    return {provider: [] for provider in auth_key_provider_ids()}


def _parse_external_secret_payload_groups(text: str) -> dict[str, list[str]]:
    groups = _empty_external_groups()
    body = str(text or "").strip()
    if not body:
        return groups
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        groups[DEFAULT_AUTH_KEY_PROVIDER] = normalize_auth_key_pool(body)
        return groups
    if isinstance(parsed, list):
        groups[DEFAULT_AUTH_KEY_PROVIDER] = normalize_auth_key_pool(parsed)
        return groups
    if not isinstance(parsed, dict):
        return groups

    providers_node = parsed.get("providers")
    if isinstance(providers_node, dict):
        for provider in auth_key_provider_ids():
            groups[provider] = _parse_external_secret_candidate(providers_node.get(provider))
        return groups

    found_group = False
    for provider in auth_key_provider_ids():
        if parsed.get(provider) is not None:
            groups[provider] = _parse_external_secret_candidate(parsed.get(provider))
            found_group = True
    if found_group:
        return groups

    legacy_candidates = [
        parsed.get("keys"),
        parsed.get("apiKeys"),
        ((parsed.get("data") or {}) if isinstance(parsed.get("data"), dict) else {}).get("keys"),
        ((parsed.get("data") or {}) if isinstance(parsed.get("data"), dict) else {}).get("apiKeys"),
    ]
    for candidate in legacy_candidates:
        if candidate is not None:
            groups[DEFAULT_AUTH_KEY_PROVIDER] = normalize_auth_key_pool(candidate)
            return groups
    return groups


def external_secret_keys(root: Optional[Path] = None, timeout: float = 5.0, provider: Any = DEFAULT_AUTH_KEY_PROVIDER) -> list[str]:
    return external_secret_status(root=root, timeout=timeout, provider=provider)["keys"]


def external_secret_status(
    root: Optional[Path] = None,
    timeout: float = 5.0,
    provider: Any = DEFAULT_AUTH_KEY_PROVIDER,
) -> dict[str, Any]:
    normalized = normalize_auth_key_provider(provider)
    label = auth_key_provider_label(normalized)
    topology = deployment_topology(root)
    url = str(os.getenv("LOOP_SECRET_PROVIDER_URL") or topology.secret_provider_url or "").strip()
    if not url:
        return {
            "backend": "external",
            "provider": normalized,
            "configured": False,
            "ready": False,
            "keys": [],
            "failureMode": "misconfigured",
            "detail": "LOOP_SECRET_PROVIDER_URL is not configured.",
        }
    token = str(os.getenv("LOOP_SECRET_PROVIDER_TOKEN") or "").strip()
    try:
        payload = _external_secret_request(url, token=token, timeout=timeout)
    except urllib.error.HTTPError as error:
        return {
            "backend": "external",
            "provider": normalized,
            "configured": True,
            "ready": False,
            "keys": [],
            "failureMode": "unreachable",
            "detail": f"Secret provider returned HTTP {error.code}.",
        }
    except Exception as error:
        return {
            "backend": "external",
            "provider": normalized,
            "configured": True,
            "ready": False,
            "keys": [],
            "failureMode": "unreachable",
            "detail": str(error),
        }
    groups = _parse_external_secret_payload_groups(payload)
    keys = groups.get(normalized, [])
    return {
        "backend": "external",
        "provider": normalized,
        "configured": True,
        "ready": len(keys) > 0,
        "keys": keys,
        "failureMode": None if keys else "empty",
        "detail": f"reachable; {len(keys)} {label} keys exposed" if keys else f"Secret provider responded but returned no {label} keys.",
    }
