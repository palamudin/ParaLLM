from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.provider_torso import model_catalog_manifest  # noqa: E402


DEFAULT_REPORT = ROOT / "data" / "qa" / "provider-contract-parity-latest.json"
DEPLOYMENT_MANIFEST = ROOT / "deployment" / "manifest.json"
CONTRACT = ROOT / "contracts" / "provider-models.v1.json"
API_KEY_NATIVE_MODES = {"app_api_key", "api_key_env", "api_key_file"}


def fetch_json(url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object from {url}.")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_native_auth_modes(auth_routes: list[Any]) -> list[str]:
    modes: set[str] = set()
    for route in auth_routes:
        normalized = str(route or "").strip()
        if normalized == "api_key":
            modes.update(API_KEY_NATIVE_MODES)
        elif normalized:
            modes.add(normalized)
    return sorted(modes)


def canonical_model(entry: dict[str, Any], *, native: bool) -> dict[str, Any]:
    capabilities = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
    if native:
        auth_modes = sorted(str(value) for value in entry.get("authModes") or [])
        normalized_capabilities = {
            "reasoningEffort": bool(capabilities.get("reasoningEffort")),
            "clientTools": bool(capabilities.get("clientTools")),
            "structuredOutput": bool(capabilities.get("structuredOutput")),
            "minimumReasoningEffort": str(capabilities.get("minimumReasoningEffort") or "none"),
        }
    else:
        auth_modes = expected_native_auth_modes(list(entry.get("authRoutes") or entry.get("authModes") or []))
        normalized_capabilities = {
            "reasoningEffort": bool(capabilities.get("supports_reasoning_effort")),
            "clientTools": bool(capabilities.get("supports_client_tools")),
            "structuredOutput": bool(capabilities.get("supports_structured_output")),
            "minimumReasoningEffort": str(capabilities.get("minimum_reasoning_effort") or "none"),
        }
    return {
        "provider": str(entry.get("provider") or ""),
        "id": str(entry.get("id") or ""),
        "label": str(entry.get("label") or ""),
        "authModes": auth_modes,
        "capabilities": normalized_capabilities,
    }


def indexed_models(payload: dict[str, Any], *, native: bool) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in payload.get("models") or []:
        if not isinstance(raw, dict):
            continue
        normalized = canonical_model(raw, native=native)
        key = f"{normalized['provider']}/{normalized['id']}"
        result[key] = normalized
    return result


def compare_maps(
    expected: dict[str, dict[str, Any]],
    actual: dict[str, dict[str, Any]],
    scope: str,
    mismatches: list[dict[str, Any]],
) -> None:
    for key in sorted(expected.keys() - actual.keys()):
        mismatches.append({"scope": scope, "key": key, "issue": "missing", "expected": expected[key]})
    for key in sorted(actual.keys() - expected.keys()):
        mismatches.append({"scope": scope, "key": key, "issue": "unexpected", "actual": actual[key]})
    for key in sorted(expected.keys() & actual.keys()):
        if expected[key] != actual[key]:
            mismatches.append(
                {
                    "scope": scope,
                    "key": key,
                    "issue": "different",
                    "expected": expected[key],
                    "actual": actual[key],
                }
            )


def canonical_provider(entry: dict[str, Any], provider_id: str) -> dict[str, Any]:
    auth_routes = list((entry.get("transportByAuthRoute") or {}).keys())
    route_defaults = entry.get("defaultModelByAuthRoute") if isinstance(entry.get("defaultModelByAuthRoute"), dict) else {}
    effective_route_defaults = {
        route: str(route_defaults.get(route) or entry.get("defaultModel") or "")
        for route in auth_routes
    }
    return {
        "id": provider_id,
        "label": str(entry.get("label") or provider_id),
        "defaultAuthRoute": str(entry.get("defaultAuthRoute") or "api_key"),
        "defaultJudgeAuthRoute": str(entry.get("defaultJudgeAuthRoute") or entry.get("defaultAuthRoute") or "api_key"),
        "defaultModel": str(entry.get("defaultModel") or ""),
        "defaultJudgeModel": str(entry.get("defaultJudgeModel") or entry.get("defaultModel") or ""),
        "defaultModelByAuthRoute": effective_route_defaults,
        "defaultApiKeyEnvironment": str(entry.get("defaultApiKeyEnvironment") or ""),
        "defaultApiKeyFileEnvironment": str(entry.get("defaultApiKeyFileEnvironment") or ""),
        "authModes": expected_native_auth_modes(auth_routes),
    }


def native_provider(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry.get("id") or ""),
        "label": str(entry.get("label") or ""),
        "defaultAuthRoute": str(entry.get("defaultAuthRoute") or ""),
        "defaultJudgeAuthRoute": str(entry.get("defaultJudgeAuthRoute") or ""),
        "defaultModel": str(entry.get("defaultModel") or ""),
        "defaultJudgeModel": str(entry.get("defaultJudgeModel") or ""),
        "defaultModelByAuthRoute": {
            str(route): str(model)
            for route, model in (entry.get("defaultModelByAuthRoute") or {}).items()
        },
        "defaultApiKeyEnvironment": str(entry.get("defaultApiKeyEnvironment") or ""),
        "defaultApiKeyFileEnvironment": str(entry.get("defaultApiKeyFileEnvironment") or ""),
        "authModes": sorted(str(value) for value in entry.get("authModes") or []),
    }


def verify_build_manifest(mismatches: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = json.loads(DEPLOYMENT_MANIFEST.read_text(encoding="utf-8"))
    catalog = manifest.get("providerModelCatalog") or {}
    expected_hash = sha256_file(CONTRACT)
    recorded_hash = str(catalog.get("contractSha256") or "")
    if recorded_hash != expected_hash:
        mismatches.append(
            {
                "scope": "native_build_manifest",
                "key": "contractSha256",
                "issue": "different",
                "expected": expected_hash,
                "actual": recorded_hash,
            }
        )
    for field in ("generatedHeader", "generatedAuthHeader", "generatedDefaultsHeader"):
        relative = Path(str(catalog.get(field) or ""))
        path = ROOT / relative
        hash_field = field + "Sha256"
        actual_hash = sha256_file(path) if path.is_file() else ""
        recorded_header_hash = str(catalog.get(hash_field) or "")
        if actual_hash != recorded_header_hash:
            mismatches.append(
                {
                    "scope": "native_build_manifest",
                    "key": hash_field,
                    "issue": "different",
                    "expected": actual_hash,
                    "actual": recorded_header_hash,
                }
            )
    return {
        "buildId": str(manifest.get("buildId") or ""),
        "contractSha256": expected_hash,
        "recordedContractSha256": recorded_hash,
        "artifact": (manifest.get("artifact") or {}).get("path"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Python and native provider catalogs against one contract.")
    parser.add_argument("--python-base-url", default="http://127.0.0.1:8815")
    parser.add_argument("--native-base-url", default="http://127.0.0.1:18878")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    canonical = model_catalog_manifest()
    python_catalog = fetch_json(args.python_base_url.rstrip("/") + "/v1/models", args.timeout)
    native_catalog = fetch_json(args.native_base_url.rstrip("/") + "/v1/models", args.timeout)
    native_auth = fetch_json(args.native_base_url.rstrip("/") + "/v1/auth", args.timeout)
    mismatches: list[dict[str, Any]] = []

    canonical_python_models = indexed_models(canonical, native=False)
    exposed_python_models = indexed_models(python_catalog, native=False)
    compare_maps(canonical_python_models, exposed_python_models, "python_model_catalog", mismatches)

    native_provider_ids = {
        str(entry.get("id") or "")
        for entry in native_auth.get("providers") or []
        if isinstance(entry, dict) and str(entry.get("id") or "")
    }
    expected_native_models = {
        key: value
        for key, value in canonical_python_models.items()
        if value["provider"] in native_provider_ids
    }
    exposed_native_models = indexed_models(native_catalog, native=True)
    compare_maps(expected_native_models, exposed_native_models, "native_model_catalog", mismatches)

    canonical_providers = canonical.get("providers") if isinstance(canonical.get("providers"), dict) else {}
    expected_native_providers = {
        provider_id: canonical_provider(canonical_providers[provider_id], provider_id)
        for provider_id in sorted(native_provider_ids)
        if provider_id in canonical_providers
    }
    exposed_native_providers = {
        str(entry.get("id") or ""): native_provider(entry)
        for entry in native_auth.get("providers") or []
        if isinstance(entry, dict) and str(entry.get("id") or "")
    }
    compare_maps(expected_native_providers, exposed_native_providers, "native_auth_catalog", mismatches)

    expected_schema = str(canonical.get("sourceSchemaVersion") or "")
    for scope, payload in (("python", python_catalog), ("native", native_catalog)):
        actual_schema = str(payload.get("sourceSchemaVersion") or "")
        if actual_schema != expected_schema:
            mismatches.append(
                {
                    "scope": f"{scope}_catalog",
                    "key": "sourceSchemaVersion",
                    "issue": "different",
                    "expected": expected_schema,
                    "actual": actual_schema,
                }
            )

    expected_default_provider = str(canonical.get("defaultProvider") or "")
    expected_default_judge_provider = str(canonical.get("defaultJudgeProvider") or expected_default_provider)
    for scope, payload in (("python", python_catalog), ("native", native_catalog)):
        for key, expected in (
            ("defaultProvider", expected_default_provider),
            ("defaultJudgeProvider", expected_default_judge_provider),
        ):
            actual = str(payload.get(key) or "")
            if actual != expected:
                mismatches.append(
                    {
                        "scope": f"{scope}_catalog",
                        "key": key,
                        "issue": "different",
                        "expected": expected,
                        "actual": actual,
                    }
                )

    build = verify_build_manifest(mismatches)
    report = {
        "schemaVersion": "parallm.provider-contract-parity.v1",
        "capturedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "passed": not mismatches,
        "contract": str(CONTRACT),
        "contractSchemaVersion": expected_schema,
        "pythonBaseUrl": args.python_base_url,
        "nativeBaseUrl": args.native_base_url,
        "counts": {
            "contractModels": len(canonical_python_models),
            "pythonModels": len(exposed_python_models),
            "nativeModelsExpected": len(expected_native_models),
            "nativeModelsExposed": len(exposed_native_models),
            "nativeProviders": len(exposed_native_providers),
            "mismatches": len(mismatches),
        },
        "nativeBuild": build,
        "mismatches": mismatches,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
