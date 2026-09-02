from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit


TRANSPORT_OPENAI_RESPONSES = "openai_responses"
TRANSPORT_CODEX_RESPONSES = "codex_responses"
TRANSPORT_XAI_RESPONSES = "xai_responses"
TRANSPORT_OPENAI_CHAT = "openai_compatible_chat"
TRANSPORT_ANTHROPIC_MESSAGES = "anthropic_messages"
TRANSPORT_OLLAMA_JSON = "ollama_json"

MODEL_SOURCE_OPENAI_API = "openai_api"
MODEL_SOURCE_CODEX_AUTH = "codex_auth"

AUTH_ROUTE_API_KEY = "api_key"
AUTH_ROUTE_SUBSCRIPTION = "subscription"
AUTH_ROUTE_CODEX_CURRENT_USER = "codex_current_user"

REASONING_EFFORTS: Tuple[str, ...] = ("none", "low", "medium", "high", "xhigh")
CONTRACT_PATH = Path(__file__).resolve().parents[1] / "contracts" / "provider-models.v1.json"


@dataclass(frozen=True)
class ModelCapabilities:
    allows_custom_models: bool = False
    prefers_compact_context: bool = False
    supports_server_input_autocompress: bool = False
    supports_reasoning_effort: bool = False
    supports_web_search: bool = False
    supported_reasoning_efforts: Tuple[str, ...] = REASONING_EFFORTS
    minimum_reasoning_effort: str = "none"
    reasoning_wire_format: str = "none"
    supports_structured_output: bool = True
    structured_output_mode: str = "prompted_json"
    supports_client_tools: bool = True
    supports_instructions_on_continuation: bool = True
    strip_leading_think_blocks: bool = False
    accepted_include_values: Tuple[str, ...] = ()
    verified_by: str = "provider_matrix"


@dataclass(frozen=True)
class LaneProcessRequest:
    provider: str
    api_key: str
    model: str
    reasoning_effort: str
    instructions: str
    input_text: str
    schema_name: str
    schema: Dict[str, Any]
    max_output_tokens: int = 0
    target_kind: str = "generic"
    tools: Optional[list[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    include: Optional[list[str]] = None
    function_handlers: Optional[Dict[str, Any]] = None
    auth_assignments: Optional[list[Dict[str, Any]]] = None
    provider_settings: Optional[Dict[str, Any]] = None
    task_id: Optional[str] = None
    auth_route: str = ""


@dataclass(frozen=True)
class ResolvedLaneProcess:
    provider: str
    model: str
    auth_route: str
    transport: str
    endpoint: str
    reasoning_effort: str
    capabilities: ModelCapabilities
    tools_enabled: bool
    include: Tuple[str, ...]

    @property
    def model_source(self) -> str:
        """Legacy state/UI projection; runtime routing uses auth_route."""
        return model_source_for_auth_route(self.auth_route)


def _load_contract() -> Dict[str, Any]:
    try:
        payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Provider/model contract could not be loaded: {CONTRACT_PATH}: {error}") from error
    if payload.get("schemaVersion") != "parallm.provider-models.v1":
        raise RuntimeError(f"Unsupported provider/model contract: {payload.get('schemaVersion')!r}")
    providers = payload.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise RuntimeError("Provider/model contract has no provider declarations.")
    for default_key in ("defaultProvider", "defaultJudgeProvider"):
        default_provider = str(payload.get(default_key) or "").strip()
        if default_provider not in providers:
            raise RuntimeError(
                f"Provider/model contract {default_key} references undeclared provider {default_provider!r}."
            )
    for provider, definition in providers.items():
        if not isinstance(definition, Mapping):
            raise RuntimeError(f"Provider {provider!r} must be an object.")
        declared_models = definition.get("models")
        if not isinstance(declared_models, list) or not declared_models:
            raise RuntimeError(f"Provider {provider!r} has no model declarations.")
        models_by_id = {
            str(model.get("id") or "").strip(): model
            for model in declared_models
            if isinstance(model, Mapping) and str(model.get("id") or "").strip()
        }
        if len(models_by_id) != len(declared_models):
            raise RuntimeError(f"Provider {provider!r} has an empty or duplicate model id.")
        for default_key in ("defaultModel", "defaultJudgeModel"):
            default_model = str(definition.get(default_key) or "").strip()
            if default_model and default_model not in models_by_id:
                raise RuntimeError(
                    f"Provider {provider!r} {default_key} references undeclared model {default_model!r}."
                )
        transports = definition.get("transportByAuthRoute")
        for route_key in ("defaultAuthRoute", "defaultJudgeAuthRoute"):
            default_auth_route = str(
                definition.get(route_key)
                or definition.get("defaultAuthRoute")
                or AUTH_ROUTE_API_KEY
            ).strip()
            if not isinstance(transports, Mapping) or default_auth_route not in transports:
                raise RuntimeError(
                    f"Provider {provider!r} {route_key} {default_auth_route!r} has no transport."
                )
        route_defaults = definition.get("defaultModelByAuthRoute")
        if isinstance(route_defaults, Mapping):
            for route, default_model in route_defaults.items():
                model_id = str(default_model or "").strip()
                model_routes = set(models_by_id.get(model_id, {}).get("authRoutes") or [])
                if not isinstance(transports, Mapping) or route not in transports:
                    raise RuntimeError(f"Provider {provider!r} default route {route!r} has no transport.")
                if model_id not in models_by_id or route not in model_routes:
                    raise RuntimeError(
                        f"Provider {provider!r} route {route!r} default {model_id!r} is not declared for that route."
                    )
        profiles = definition.get("qualityProfiles")
        if isinstance(profiles, Mapping):
            for profile, profile_models in profiles.items():
                if not isinstance(profile_models, Mapping):
                    raise RuntimeError(f"Provider {provider!r} quality profile {profile!r} must be an object.")
                for lane in ("workerModel", "summarizerModel"):
                    model_id = str(profile_models.get(lane) or "").strip()
                    if model_id not in models_by_id:
                        raise RuntimeError(
                            f"Provider {provider!r} quality profile {profile!r} {lane} references "
                            f"undeclared model {model_id!r}."
                        )
    return payload


_CONTRACT: Dict[str, Any] = _load_contract()
_PROVIDER_DEFINITIONS: Mapping[str, Dict[str, Any]] = _CONTRACT["providers"]


def _capability_values(value: Any) -> Dict[str, Any]:
    values = dict(value) if isinstance(value, Mapping) else {}
    for field in ("supported_reasoning_efforts", "accepted_include_values"):
        if isinstance(values.get(field), list):
            values[field] = tuple(str(item) for item in values[field])
    return values


def _provider_models(provider: str) -> list[Dict[str, Any]]:
    definition = _PROVIDER_DEFINITIONS.get(provider)
    models = definition.get("models") if isinstance(definition, Mapping) else None
    return [dict(model) for model in models if isinstance(model, Mapping)] if isinstance(models, list) else []


_PROVIDER_TRANSPORTS: Mapping[str, str] = {
    provider: str((definition.get("transportByAuthRoute") or {}).get(AUTH_ROUTE_API_KEY) or "")
    for provider, definition in _PROVIDER_DEFINITIONS.items()
}

_PROVIDER_CAPABILITIES: Mapping[str, ModelCapabilities] = {
    provider: ModelCapabilities(**_capability_values(definition.get("capabilities")))
    for provider, definition in _PROVIDER_DEFINITIONS.items()
}

_MODEL_CAPABILITY_OVERRIDES: Mapping[Tuple[str, str], Dict[str, Any]] = {
    (provider, str(model.get("id") or "")): _capability_values(model.get("capabilityOverrides"))
    for provider in _PROVIDER_DEFINITIONS
    for model in _provider_models(provider)
    if isinstance(model.get("capabilityOverrides"), Mapping)
}


def _normalized_provider(value: Any) -> str:
    fallback = str(_CONTRACT.get("defaultProvider") or "").strip().lower()
    return str(value or fallback).strip().lower() or fallback


def _normalized_model(value: Any) -> str:
    return str(value or "").strip()


def normalize_auth_route(value: Any) -> str:
    normalized = str(value or AUTH_ROUTE_API_KEY).strip().lower()
    if normalized == AUTH_ROUTE_SUBSCRIPTION:
        return AUTH_ROUTE_SUBSCRIPTION
    if normalized in {
        AUTH_ROUTE_CODEX_CURRENT_USER,
        MODEL_SOURCE_CODEX_AUTH,
        "codex",
        "codex_cli",
        "chatgpt",
        "chatgpt_auth",
    }:
        return AUTH_ROUTE_CODEX_CURRENT_USER
    return AUTH_ROUTE_API_KEY


def model_source_for_auth_route(value: Any) -> str:
    return (
        MODEL_SOURCE_CODEX_AUTH
        if normalize_auth_route(value) in {AUTH_ROUTE_SUBSCRIPTION, AUTH_ROUTE_CODEX_CURRENT_USER}
        else MODEL_SOURCE_OPENAI_API
    )


def provider_definitions() -> Dict[str, Dict[str, Any]]:
    return {
        provider: dict(definition)
        for provider, definition in _PROVIDER_DEFINITIONS.items()
    }


def default_provider_id(*, judge: bool = False) -> str:
    key = "defaultJudgeProvider" if judge else "defaultProvider"
    return str(_CONTRACT.get(key) or "").strip()


def provider_auth_routes(provider: Any) -> Tuple[str, ...]:
    definition = _PROVIDER_DEFINITIONS.get(_normalized_provider(provider), {})
    transports = definition.get("transportByAuthRoute") if isinstance(definition, Mapping) else {}
    return tuple(
        normalize_auth_route(route)
        for route in (transports.keys() if isinstance(transports, Mapping) else [])
    )


def provider_supports_auth_route(provider: Any, auth_route: Any) -> bool:
    return normalize_auth_route(auth_route) in provider_auth_routes(provider)


def provider_default_auth_route(provider: Any, *, judge: bool = False) -> str:
    definition = _PROVIDER_DEFINITIONS.get(_normalized_provider(provider), {})
    key = "defaultJudgeAuthRoute" if judge else "defaultAuthRoute"
    declared = str(
        definition.get(key)
        or definition.get("defaultAuthRoute")
        or AUTH_ROUTE_API_KEY
    ).strip()
    normalized = normalize_auth_route(declared)
    if normalized in provider_auth_routes(provider):
        return normalized
    routes = provider_auth_routes(provider)
    return routes[0] if routes else AUTH_ROUTE_API_KEY


def provider_catalog() -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    for provider, definition in _PROVIDER_DEFINITIONS.items():
        endpoints = dict(definition.get("endpointByAuthRoute") or {})
        catalog[provider] = {
            "label": str(definition.get("label") or provider),
            "shortLabel": str(definition.get("shortLabel") or definition.get("label") or provider),
            "displayOrder": int(definition.get("displayOrder") or 0),
            "status": str(definition.get("status") or "primary"),
            "credentialRequired": bool(definition.get("credentialRequired", True)),
            "defaultAuthRoute": provider_default_auth_route(provider),
            "defaultJudgeAuthRoute": provider_default_auth_route(provider, judge=True),
            "defaultModel": str(definition.get("defaultModel") or ""),
            "defaultJudgeModel": str(definition.get("defaultJudgeModel") or definition.get("defaultModel") or ""),
            "defaultModelByAuthRoute": dict(definition.get("defaultModelByAuthRoute") or {}),
            "qualityProfiles": {
                str(profile): dict(models)
                for profile, models in (definition.get("qualityProfiles") or {}).items()
                if isinstance(models, Mapping)
            },
            "capabilities": dict(_PROVIDER_CAPABILITIES[provider].__dict__),
            "defaultEndpoint": str(endpoints.get(AUTH_ROUTE_API_KEY) or next(iter(endpoints.values()), "")),
            "defaultApiKeyEnvironment": str(definition.get("defaultApiKeyEnvironment") or ""),
            "defaultApiKeyFileEnvironment": str(definition.get("defaultApiKeyFileEnvironment") or ""),
            "defaultModelEnvironment": str(definition.get("defaultModelEnvironment") or ""),
            "defaultJudgeModelEnvironment": str(definition.get("defaultJudgeModelEnvironment") or ""),
            "transportByAuthRoute": dict(definition.get("transportByAuthRoute") or {}),
            "endpointByAuthRoute": endpoints,
            "endpointEnvironmentByAuthRoute": dict(definition.get("endpointEnvironmentByAuthRoute") or {}),
        }
    return catalog


def provider_model_catalog(provider: Any) -> Dict[str, Dict[str, Any]]:
    normalized_provider = _normalized_provider(provider)
    catalog: Dict[str, Dict[str, Any]] = {}
    for model in _provider_models(normalized_provider):
        model_id = str(model.get("id") or "").strip()
        if not model_id:
            continue
        metadata: Dict[str, Any] = {
            "label": str(model.get("label") or model_id),
            "authRoutes": [normalize_auth_route(route) for route in model.get("authRoutes", [])],
            "liveValidation": bool(model.get("liveValidation", False)),
        }
        if isinstance(model.get("pricing"), Mapping):
            metadata.update(dict(model["pricing"]))
        catalog[model_id] = metadata
    return catalog


def provider_capabilities(provider: Any) -> ModelCapabilities:
    return _PROVIDER_CAPABILITIES.get(_normalized_provider(provider), ModelCapabilities())


def provider_model_aliases() -> Dict[str, Dict[str, str]]:
    return {
        provider: {
            str(alias): str(canonical)
            for alias, canonical in (definition.get("aliases") or {}).items()
        }
        for provider, definition in _PROVIDER_DEFINITIONS.items()
        if isinstance(definition.get("aliases"), Mapping)
    }


def provider_default_models(*, judge: bool = False) -> Dict[str, str]:
    key = "defaultJudgeModel" if judge else "defaultModel"
    return {
        provider: str(definition.get(key) or definition.get("defaultModel") or "")
        for provider, definition in _PROVIDER_DEFINITIONS.items()
    }


def provider_default_model(provider: Any, *, auth_route: Any = None, judge: bool = False) -> str:
    normalized_provider = _normalized_provider(provider)
    definition = _PROVIDER_DEFINITIONS.get(normalized_provider, {})
    if not isinstance(definition, Mapping):
        return ""
    environment_key = "defaultJudgeModelEnvironment" if judge else "defaultModelEnvironment"
    environment_name = str(definition.get(environment_key) or "").strip()
    if judge and not environment_name:
        environment_name = str(definition.get("defaultModelEnvironment") or "").strip()
    environment_model = str(os.getenv(environment_name) or "").strip() if environment_name else ""
    if environment_model:
        return environment_model
    if not judge:
        route_defaults = definition.get("defaultModelByAuthRoute")
        normalized_auth_route = normalize_auth_route(auth_route)
        if isinstance(route_defaults, Mapping):
            route_default = str(route_defaults.get(normalized_auth_route) or "").strip()
            if route_default:
                return route_default
    key = "defaultJudgeModel" if judge else "defaultModel"
    return str(definition.get(key) or definition.get("defaultModel") or "").strip()


def model_definition(provider: Any, model: Any) -> Optional[Dict[str, Any]]:
    normalized_provider = _normalized_provider(provider)
    normalized_model = _normalized_model(model).lower()
    aliases = provider_model_aliases().get(normalized_provider, {})
    canonical = next(
        (value for alias, value in aliases.items() if alias.lower() == normalized_model),
        _normalized_model(model),
    )
    for current in _provider_models(normalized_provider):
        if str(current.get("id") or "").lower() == canonical.lower():
            return current
    return None


def model_supports_auth_route(provider: Any, model: Any, auth_route: Any) -> bool:
    normalized_provider = _normalized_provider(provider)
    normalized_route = normalize_auth_route(auth_route)
    if not provider_supports_auth_route(normalized_provider, normalized_route):
        return False
    definition = model_definition(normalized_provider, model)
    if not isinstance(definition, Mapping):
        return provider_capabilities(normalized_provider).allows_custom_models
    routes = {
        normalize_auth_route(route)
        for route in (definition.get("authRoutes") or [])
    }
    return not routes or normalized_route in routes


def resolve_auth_route(
    provider: Any,
    auth_route: Any = None,
    *,
    model: Any = None,
    judge: bool = False,
) -> str:
    normalized_provider = _normalized_provider(provider) or default_provider_id(judge=judge)
    explicit = auth_route is not None and str(auth_route).strip() != ""
    candidate = (
        normalize_auth_route(auth_route)
        if explicit
        else provider_default_auth_route(normalized_provider, judge=judge)
    )
    if not provider_supports_auth_route(normalized_provider, candidate):
        candidate = provider_default_auth_route(normalized_provider, judge=judge)
        explicit = False
    if explicit or not str(model or "").strip() or model_supports_auth_route(normalized_provider, model, candidate):
        return candidate
    definition = model_definition(normalized_provider, model)
    if not isinstance(definition, Mapping):
        return candidate
    model_routes = {
        normalize_auth_route(route)
        for route in (definition.get("authRoutes") or [])
    }
    return next(
        (route for route in provider_auth_routes(normalized_provider) if route in model_routes),
        candidate,
    )


def normalize_reasoning_effort(value: Any) -> str:
    normalized = str(value or "low").strip().lower() or "low"
    return normalized if normalized in REASONING_EFFORTS else "low"


def model_capabilities(provider: Any, model: Any) -> ModelCapabilities:
    normalized_provider = _normalized_provider(provider)
    normalized_model = _normalized_model(model)
    base = _PROVIDER_CAPABILITIES.get(normalized_provider, ModelCapabilities())
    values = dict(base.__dict__)

    values.update(_MODEL_CAPABILITY_OVERRIDES.get((normalized_provider, normalized_model), {}))
    return ModelCapabilities(**values)


def effective_reasoning_effort(capabilities: ModelCapabilities, requested: Any) -> str:
    normalized = normalize_reasoning_effort(requested)
    if not capabilities.supports_reasoning_effort:
        return "none"
    allowed = capabilities.supported_reasoning_efforts or REASONING_EFFORTS
    if normalized not in allowed:
        requested_rank = REASONING_EFFORTS.index(normalized)
        ranked_allowed = sorted(
            (value for value in allowed if value in REASONING_EFFORTS),
            key=REASONING_EFFORTS.index,
        )
        lower_or_equal = [
            value for value in ranked_allowed
            if REASONING_EFFORTS.index(value) <= requested_rank
        ]
        normalized = lower_or_equal[-1] if lower_or_equal else ranked_allowed[0]
    minimum = normalize_reasoning_effort(capabilities.minimum_reasoning_effort)
    if minimum in REASONING_EFFORTS and normalized in REASONING_EFFORTS:
        if REASONING_EFFORTS.index(normalized) < REASONING_EFFORTS.index(minimum):
            normalized = minimum
    return normalized


def merge_endpoint_override(canonical_endpoint: Any, override_endpoint: Any) -> str:
    """Apply a base/full URL override while retaining the contract endpoint path."""
    canonical = str(canonical_endpoint or "").strip().rstrip("/")
    override = str(override_endpoint or "").strip().rstrip("/")
    if not override:
        return canonical
    if not canonical:
        return override

    canonical_parts = urlsplit(canonical)
    override_parts = urlsplit(override)
    if not override_parts.scheme or not override_parts.netloc:
        return override

    canonical_segments = [segment for segment in canonical_parts.path.split("/") if segment]
    override_segments = [segment for segment in override_parts.path.split("/") if segment]
    overlap = 0
    maximum_overlap = min(len(canonical_segments), len(override_segments))
    for count in range(maximum_overlap, 0, -1):
        if override_segments[-count:] == canonical_segments[:count]:
            overlap = count
            break
    merged_segments = override_segments + canonical_segments[overlap:]
    merged_path = "/" + "/".join(merged_segments) if merged_segments else ""
    return urlunsplit(
        (
            override_parts.scheme,
            override_parts.netloc,
            merged_path,
            override_parts.query,
            override_parts.fragment,
        )
    )


def _route_endpoint(
    provider_definition: Mapping[str, Any],
    auth_route: str,
    settings: Mapping[str, Any],
    route_override: Optional[Mapping[str, Any]] = None,
) -> str:
    override_definition = route_override if isinstance(route_override, Mapping) else {}
    endpoints = provider_definition.get("endpointByAuthRoute")
    canonical = str(
        override_definition.get("endpoint")
        or ((endpoints or {}).get(auth_route) if isinstance(endpoints, Mapping) else "")
        or ""
    ).strip()

    explicit_endpoint = str(settings.get("endpoint") or "").strip()
    if explicit_endpoint:
        return explicit_endpoint

    setting_name = str(override_definition.get("endpointSetting") or "").strip()
    if not setting_name:
        setting_names = provider_definition.get("endpointSettingByAuthRoute")
        if isinstance(setting_names, Mapping):
            setting_name = str(setting_names.get(auth_route) or "").strip()
    configured_endpoint = str(settings.get(setting_name) or "").strip() if setting_name else ""
    if not configured_endpoint:
        provider_instance = settings.get("providerInstance")
        if isinstance(provider_instance, Mapping):
            configured_endpoint = str(provider_instance.get("baseUrl") or provider_instance.get("endpoint") or "").strip()

    environment_name = str(override_definition.get("endpointEnvironment") or "").strip()
    if not environment_name:
        environment_names = provider_definition.get("endpointEnvironmentByAuthRoute")
        if isinstance(environment_names, Mapping):
            environment_name = str(environment_names.get(auth_route) or "").strip()
    environment_endpoint = str(os.getenv(environment_name) or "").strip() if environment_name else ""
    return merge_endpoint_override(canonical, configured_endpoint or environment_endpoint)


def resolve_lane_process(
    provider: Any,
    model: Any,
    reasoning_effort: Any,
    provider_settings: Optional[Mapping[str, Any]] = None,
    tools_requested: bool = False,
    include: Optional[list[str]] = None,
    auth_route: Any = None,
) -> ResolvedLaneProcess:
    normalized_provider = _normalized_provider(provider) or default_provider_id()
    normalized_model = _normalized_model(model)
    settings = provider_settings if isinstance(provider_settings, Mapping) else {}
    requested_auth_route = auth_route
    if requested_auth_route is None or str(requested_auth_route).strip() == "":
        requested_auth_route = settings.get(
            "authRoute",
            settings.get("authMode", settings.get("authSource", settings.get("modelSource"))),
        )
    if (
        requested_auth_route is not None
        and str(requested_auth_route).strip() != ""
        and not provider_supports_auth_route(normalized_provider, requested_auth_route)
    ):
        raise ValueError(
            f"Provider {normalized_provider!r} does not support auth route "
            f"{normalize_auth_route(requested_auth_route)!r}."
        )
    normalized_auth_route = resolve_auth_route(
        normalized_provider,
        requested_auth_route,
        model=normalized_model,
    )
    provider_definition = _PROVIDER_DEFINITIONS.get(normalized_provider, {})
    if not normalized_model:
        normalized_model = provider_default_model(
            normalized_provider,
            auth_route=normalized_auth_route,
        )
    transport_by_auth = provider_definition.get("transportByAuthRoute") if isinstance(provider_definition, Mapping) else {}
    if normalized_auth_route not in (transport_by_auth or {}):
        raise ValueError(
            f"Provider {normalized_provider!r} does not support auth route {normalized_auth_route!r}."
        )
    declared_model = model_definition(normalized_provider, normalized_model)
    provider_capability = provider_capabilities(normalized_provider)
    if not isinstance(declared_model, Mapping) and not provider_capability.allows_custom_models:
        raise ValueError(
            f"Provider {normalized_provider!r} does not allow undeclared model {normalized_model!r}."
        )
    if isinstance(declared_model, Mapping) and str(declared_model.get("id") or "").strip():
        normalized_model = str(declared_model["id"]).strip()
    declared_auth_routes = {
        normalize_auth_route(route)
        for route in (declared_model.get("authRoutes") or [])
    } if isinstance(declared_model, Mapping) else set()
    if declared_auth_routes and normalized_auth_route not in declared_auth_routes:
        raise ValueError(
            f"Model {normalized_provider}/{normalized_model} does not support auth route {normalized_auth_route!r}."
        )
    transport = str(
        (transport_by_auth or {}).get(normalized_auth_route)
        or _PROVIDER_TRANSPORTS.get(normalized_provider, "")
    )
    route_override: Optional[Mapping[str, Any]] = None
    selector = provider_definition.get("transportSelector") if isinstance(provider_definition, Mapping) else None
    if isinstance(selector, Mapping):
        setting_name = str(selector.get("setting") or "").strip()
        environment_name = str(selector.get("environment") or "").strip()
        selector_value = str(
            (settings.get(setting_name) if setting_name else "")
            or (os.getenv(environment_name) if environment_name else "")
            or ""
        ).strip().lower()
        selector_routes = selector.get("routes")
        candidate = selector_routes.get(selector_value) if isinstance(selector_routes, Mapping) else None
        if isinstance(candidate, Mapping):
            route_override = candidate
            transport = str(candidate.get("transport") or transport)

    endpoint = _route_endpoint(
        provider_definition if isinstance(provider_definition, Mapping) else {},
        normalized_auth_route,
        settings,
        route_override,
    )

    capabilities = model_capabilities(normalized_provider, normalized_model)
    accepted_include = tuple(
        item
        for item in (str(value or "").strip() for value in (include or []))
        if item and item in capabilities.accepted_include_values
    )
    return ResolvedLaneProcess(
        provider=normalized_provider,
        model=normalized_model,
        auth_route=normalized_auth_route,
        transport=transport,
        endpoint=endpoint,
        reasoning_effort=effective_reasoning_effort(capabilities, reasoning_effort),
        capabilities=capabilities,
        tools_enabled=bool(tools_requested and capabilities.supports_client_tools),
        include=accepted_include,
    )


def capability_manifest() -> Dict[str, Any]:
    return {
        "schemaVersion": "parallm.provider-torso-capabilities.v1",
        "contract": str(CONTRACT_PATH),
        "contractSchemaVersion": str(_CONTRACT.get("schemaVersion") or ""),
        "authRoutes": list(_CONTRACT.get("authRoutes") or []),
        "transports": {
            provider: dict(definition.get("transportByAuthRoute") or {})
            for provider, definition in _PROVIDER_DEFINITIONS.items()
        },
        "endpoints": {
            provider: dict(definition.get("endpointByAuthRoute") or {})
            for provider, definition in _PROVIDER_DEFINITIONS.items()
        },
        "providerDefaults": {
            provider: dict(capabilities.__dict__)
            for provider, capabilities in _PROVIDER_CAPABILITIES.items()
        },
        "modelOverrides": {
            f"{provider}/{model}": dict(overrides)
            for (provider, model), overrides in _MODEL_CAPABILITY_OVERRIDES.items()
        },
    }


def model_catalog_manifest(*, validation_only: bool = False) -> Dict[str, Any]:
    models: list[Dict[str, Any]] = []
    for provider, definition in _PROVIDER_DEFINITIONS.items():
        for model in _provider_models(provider):
            if validation_only and not bool(model.get("liveValidation", False)):
                continue
            model_id = str(model.get("id") or "").strip()
            if not model_id:
                continue
            capabilities = model_capabilities(provider, model_id)
            auth_routes = [normalize_auth_route(route) for route in model.get("authRoutes", [])]
            models.append(
                {
                    "provider": provider,
                    "id": model_id,
                    "label": str(model.get("label") or model_id),
                    "shortLabel": str(model.get("shortLabel") or model.get("label") or model_id),
                    "authRoutes": auth_routes,
                    "authModes": auth_routes,
                    "liveValidation": bool(model.get("liveValidation", False)),
                    "pricing": dict(model.get("pricing") or {}) if isinstance(model.get("pricing"), Mapping) else {},
                    "capabilities": dict(capabilities.__dict__),
                }
            )
    return {
        "schemaVersion": "parallm.provider-model-catalog.v1",
        "source": str(CONTRACT_PATH),
        "sourceSchemaVersion": str(_CONTRACT.get("schemaVersion") or ""),
        "defaultProvider": default_provider_id(),
        "defaultJudgeProvider": default_provider_id(judge=True),
        "providers": provider_catalog(),
        "models": models,
    }
