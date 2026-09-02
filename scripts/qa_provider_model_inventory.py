from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUTH_FILE = ROOT / "Auth.txt"
PROVIDERS_FILE = ROOT / "providers.txt"
DEFAULT_AUDIT = ROOT / "data" / "qa" / "provider-model-inventory-latest.json"

HOSTED_ROUTES: dict[str, dict[str, Any]] = {
    "openai": {
        "url": "https://api.openai.com/v1/models",
        "prefixes": ("openai",),
        "environment": "OPENAI_API_KEY",
        "auth": "bearer",
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/models?limit=1000",
        "prefixes": ("anthropic", "ant", "claude"),
        "environment": "ANTHROPIC_API_KEY",
        "auth": "anthropic",
    },
    "deepseek": {
        "url": "https://api.deepseek.com/models",
        "prefixes": ("deepseek",),
        "environment": "DEEPSEEK_API_KEY",
        "auth": "bearer",
    },
    "xai": {
        "url": "https://api.x.ai/v1/models",
        "prefixes": ("xai", "grok"),
        "environment": "XAI_API_KEY",
        "auth": "bearer",
    },
    "minimax": {
        "url": "https://api.minimax.io/v1/models",
        "prefixes": ("minimax", "min"),
        "environment": "MINIMAX_API_KEY",
        "auth": "bearer",
    },
    "kimi": {
        "url": "https://api.kimi.com/coding/v1/models",
        "prefixes": ("kimi", "moonshot"),
        "environment": "KIMI_API_KEY",
        "auth": "bearer",
    },
}


def read_local_keys() -> dict[str, list[str]]:
    keys: dict[str, list[str]] = {}
    if not AUTH_FILE.is_file():
        return keys
    for raw_line in AUTH_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")) or ":" not in line:
            continue
        prefix, value = line.split(":", 1)
        normalized = prefix.strip().lower()
        secret = value.strip()
        if normalized and secret:
            keys.setdefault(normalized, []).append(secret)
    return keys


def route_key(route: dict[str, Any], local_keys: dict[str, list[str]]) -> str:
    environment = str(route.get("environment") or "")
    if environment and os.getenv(environment):
        return str(os.environ[environment]).strip()
    for prefix in route.get("prefixes", ()):
        values = local_keys.get(str(prefix).lower()) or []
        if values:
            return values[0]
    return ""


def request_json(url: str, headers: dict[str, str], timeout: int) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json", **headers})
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def extract_model_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    entries = payload.get("data")
    if not isinstance(entries, list):
        entries = payload.get("models")
    if not isinstance(entries, list):
        return []
    values: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        value = str(entry.get("id") or entry.get("model") or entry.get("name") or "").strip()
        if value and value not in values:
            values.append(value)
    return sorted(values, key=str.casefold)


def hosted_inventory(provider: str, route: dict[str, Any], local_keys: dict[str, list[str]], timeout: int) -> dict[str, Any]:
    key = route_key(route, local_keys)
    if not key:
        return {"provider": provider, "status": "missing_credentials", "models": []}
    headers: dict[str, str]
    if route.get("auth") == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    else:
        headers = {"Authorization": f"Bearer {key}"}
    try:
        payload = request_json(str(route["url"]), headers, timeout)
        models = extract_model_ids(payload)
        return {
            "provider": provider,
            "status": "available" if models else "empty_catalog",
            "endpoint": route["url"],
            "modelCount": len(models),
            "models": models,
        }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:600]
        return {
            "provider": provider,
            "status": "http_error",
            "endpoint": route["url"],
            "httpStatus": exc.code,
            "error": body,
            "models": [],
        }
    except Exception as exc:
        return {
            "provider": provider,
            "status": "error",
            "endpoint": route["url"],
            "error": str(exc),
            "models": [],
        }


def ollama_inventory(timeout: int) -> list[dict[str, Any]]:
    if not PROVIDERS_FILE.is_file():
        return []
    try:
        catalog = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    instances = catalog.get("ollama") if isinstance(catalog, dict) else []
    results: list[dict[str, Any]] = []
    for instance in instances if isinstance(instances, list) else []:
        if not isinstance(instance, dict) or not bool(instance.get("enabled", True)):
            continue
        base_url = str(instance.get("baseUrl") or "").rstrip("/")
        result = {
            "provider": "ollama",
            "instanceId": str(instance.get("id") or base_url),
            "label": str(instance.get("label") or base_url),
            "baseUrl": base_url,
            "models": [],
        }
        try:
            models = extract_model_ids(request_json(base_url + "/api/tags", {}, timeout))
            result.update(status="available" if models else "empty_catalog", modelCount=len(models), models=models)
        except Exception as exc:
            result.update(status="error", error=str(exc))
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory models visible to every configured ParaLLM provider account.")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()

    local_keys = read_local_keys()
    hosted = [hosted_inventory(provider, route, local_keys, args.timeout) for provider, route in HOSTED_ROUTES.items()]
    report = {
        "schemaVersion": "parallm.provider-model-inventory.v1",
        "capturedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hosted": hosted,
        "ollama": ollama_inventory(args.timeout),
    }
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for entry in hosted + report["ollama"]:
        label = entry.get("provider")
        if entry.get("instanceId"):
            label += "/" + str(entry["instanceId"])
        print(f"{label}: {entry.get('status')} ({len(entry.get('models') or [])} models)")
        for model in entry.get("models") or []:
            print(f"  {model}")
    return 0 if all(entry.get("status") == "available" for entry in hosted) else 1


if __name__ == "__main__":
    raise SystemExit(main())
