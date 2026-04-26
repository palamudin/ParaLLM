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
SAFE_SECRET_BACKENDS = {"env", "docker_secret", "external"}
AUTH_BACKEND_MODES = {"local", "env", "db"}
AUTH_LOCAL_FILE_PREFIXES: dict[str, str] = {
    "openai": "openai",
    "anthropic": "ant",
    "xai": "xai",
    "minimax": "min",
}
AUTH_LOCAL_FILE_PREFIX_ALIASES: dict[str, str] = {
    "openai": "openai",
    "oai": "openai",
    "anthropic": "anthropic",
    "ant": "anthropic",
    "claude": "anthropic",
    "xai": "xai",
    "grok": "xai",
    "minimax": "minimax",
    "min": "minimax",
    "mini": "minimax",
}


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


def auth_backend_mode_label(mode: Any) -> str:
    normalized = normalize_auth_backend_mode(mode)
    if normalized == "local":
        return "Local"
    if normalized == "db":
        return "DB"
    return "Env"


def auth_key_env_vars(provider: Any) -> list[str]:
    normalized = normalize_auth_key_provider(provider)
    catalog = AUTH_KEY_PROVIDER_CATALOG.get(normalized) or {}
    return [str(name) for name in catalog.get("envVars", []) if str(name).strip()]


def normalize_auth_backend_mode(value: Any, fallback: str = "env") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in AUTH_BACKEND_MODES:
        return candidate
    if candidate == "safe":
        candidate = str(fallback or "env").strip().lower()
        return candidate if candidate in AUTH_BACKEND_MODES else "env"
    normalized_fallback = str(fallback or "env").strip().lower()
    if normalized_fallback == "safe":
        normalized_fallback = "env"
    return normalized_fallback if normalized_fallback in AUTH_BACKEND_MODES else "env"


def auth_backend_category_from_backend(backend: Any) -> str:
    normalized = str(backend or "").strip().lower()
    if normalized == "local_file":
        return "local"
    if normalized == "external":
        return "db"
    if normalized in {"env", "docker_secret"}:
        return "env"
    return "env"


def auth_backend_override_path(root: Optional[Path] = None) -> Path:
    topology = deployment_topology(root)
    return topology.data_root / "auth_provider_backends.json"


def default_auth_backend_mode(root: Optional[Path] = None) -> str:
    topology = deployment_topology(root)
    current_backend = str(topology.secret_backend or "").strip().lower()
    if current_backend == "local_file":
        return "local"
    if current_backend in {"env", "docker_secret", "external"}:
        return auth_backend_category_from_backend(current_backend)
    return auth_backend_category_from_backend(preferred_safe_secret_backend(root))


def read_auth_backend_mode_overrides(root: Optional[Path] = None) -> dict[str, str]:
    path = auth_backend_override_path(root)
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    overrides: dict[str, str] = {}
    for provider in auth_key_provider_ids():
        if parsed.get(provider) is None:
            continue
        overrides[provider] = normalize_auth_backend_mode(parsed.get(provider), default_auth_backend_mode(root))
    return overrides


def write_auth_backend_mode_override(root: Optional[Path], provider: Any, mode: Any) -> dict[str, str]:
    normalized_provider = normalize_auth_key_provider(provider)
    path = auth_backend_override_path(root)
    overrides = read_auth_backend_mode_overrides(root)
    default_mode = default_auth_backend_mode(root)
    normalized_mode = normalize_auth_backend_mode(mode, default_mode)
    if normalized_mode == default_mode:
        overrides.pop(normalized_provider, None)
    else:
        overrides[normalized_provider] = normalized_mode
    path.parent.mkdir(parents=True, exist_ok=True)
    if overrides:
        path.write_text(json.dumps(overrides, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()
    return read_auth_backend_mode_overrides(root)


def auth_backend_mode_for_provider(root: Optional[Path], provider: Any) -> str:
    normalized_provider = normalize_auth_key_provider(provider)
    overrides = read_auth_backend_mode_overrides(root)
    return normalize_auth_backend_mode(overrides.get(normalized_provider), default_auth_backend_mode(root))


def preferred_safe_secret_backend(root: Optional[Path] = None) -> str:
    topology = deployment_topology(root)
    current_backend = str(topology.secret_backend or "").strip().lower()
    if current_backend in SAFE_SECRET_BACKENDS:
        return current_backend
    if topology.profile in {"hosted-single-node", "hosted-distributed"}:
        if topology.secret_provider_url:
            return "external"
        return "docker_secret"
    if topology.secret_provider_url:
        return "external"
    return "env"


def preferred_env_secret_backend(root: Optional[Path] = None) -> str:
    topology = deployment_topology(root)
    current_backend = str(topology.secret_backend or "").strip().lower()
    if current_backend in {"env", "docker_secret"}:
        return current_backend
    if topology.profile in {"hosted-single-node", "hosted-distributed"}:
        return "docker_secret"
    return "env"


def resolve_provider_secret_backend(root: Optional[Path], provider: Any) -> dict[str, str]:
    mode = auth_backend_mode_for_provider(root, provider)
    if mode == "local":
        backend = "local_file"
    elif mode == "db":
        backend = "external"
    else:
        backend = preferred_env_secret_backend(root)
    return {
        "provider": normalize_auth_key_provider(provider),
        "mode": mode,
        "backend": backend,
    }


def auth_local_file_prefix(provider: Any) -> str:
    normalized = normalize_auth_key_provider(provider)
    return str(AUTH_LOCAL_FILE_PREFIXES.get(normalized) or normalized)


def _normalize_local_auth_prefix(prefix: Any) -> Optional[str]:
    candidate = str(prefix or "").strip().lower()
    if not candidate:
        return None
    normalized = AUTH_LOCAL_FILE_PREFIX_ALIASES.get(candidate)
    if normalized:
        return normalized
    if candidate in AUTH_KEY_PROVIDER_CATALOG:
        return candidate
    return None


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


def _parse_local_auth_line(raw_line: str) -> dict[str, Any]:
    raw = str(raw_line or "").rstrip("\r\n")
    stripped = raw.strip()
    if not stripped:
        return {"kind": "blank", "raw": raw}
    if stripped.startswith("#") or stripped.startswith(";"):
        return {"kind": "comment", "raw": raw}
    prefix, separator, remainder = stripped.partition(":")
    if separator:
        provider = _normalize_local_auth_prefix(prefix)
        if provider:
            return {
                "kind": "provider_key",
                "provider": provider,
                "key": remainder.strip(),
                "raw": raw,
            }
        return {"kind": "other", "raw": raw}
    return {
        "kind": "legacy_openai_key",
        "provider": DEFAULT_AUTH_KEY_PROVIDER,
        "key": stripped,
        "raw": raw,
    }


def _shared_local_auth_groups(base_path: Path) -> tuple[dict[str, list[str]], dict[str, bool]]:
    groups = {provider: [] for provider in auth_key_provider_ids()}
    present = {provider: False for provider in auth_key_provider_ids()}
    if not base_path.is_file():
        return groups, present
    for raw_line in base_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parsed = _parse_local_auth_line(raw_line)
        provider = parsed.get("provider")
        key = str(parsed.get("key") or "").strip()
        if provider in groups and key:
            groups[str(provider)].append(key)
            present[str(provider)] = True
    for provider in auth_key_provider_ids():
        groups[provider] = normalize_auth_key_pool(groups.get(provider, []))
    return groups, present


def read_local_auth_file_groups(base_path: Path) -> dict[str, list[str]]:
    groups, present = _shared_local_auth_groups(base_path)
    for provider in auth_key_provider_ids():
        if present.get(provider):
            continue
        provider_path = auth_key_file_path(base_path, provider)
        if provider_path != base_path and provider_path.is_file():
            groups[provider] = normalize_auth_key_pool(provider_path.read_text(encoding="utf-8", errors="replace"))
    return groups


def read_local_auth_keys(base_path: Path, provider: Any = DEFAULT_AUTH_KEY_PROVIDER) -> list[str]:
    normalized = normalize_auth_key_provider(provider)
    return list(read_local_auth_file_groups(base_path).get(normalized, []))


def write_local_auth_keys(base_path: Path, provider: Any, keys: Any) -> None:
    normalized = normalize_auth_key_provider(provider)
    canonical_prefix = auth_local_file_prefix(normalized)
    shared_path = Path(base_path).resolve()
    existing_lines = shared_path.read_text(encoding="utf-8", errors="replace").splitlines() if shared_path.is_file() else []
    kept_lines: list[str] = []
    for raw_line in existing_lines:
        parsed = _parse_local_auth_line(raw_line)
        parsed_provider = parsed.get("provider")
        if parsed.get("kind") == "provider_key" and parsed_provider == normalized:
            continue
        if normalized == DEFAULT_AUTH_KEY_PROVIDER and parsed.get("kind") == "legacy_openai_key":
            continue
        kept_lines.append(raw_line.rstrip("\r\n"))
    for key in normalize_auth_key_pool(keys):
        kept_lines.append(f"{canonical_prefix}:{key}")
    payload = "\n".join(kept_lines)
    if payload:
        payload += "\n"
    shared_path.parent.mkdir(parents=True, exist_ok=True)
    shared_path.write_text(payload, encoding="utf-8")
    legacy_path = auth_key_file_path(shared_path, normalized)
    if legacy_path != shared_path and legacy_path.exists():
        legacy_path.unlink()


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
