from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from runtime.provider_torso import (
    AUTH_ROUTE_CODEX_CURRENT_USER,
    REASONING_EFFORTS,
    provider_catalog,
    provider_default_model,
    provider_model_catalog,
)

from . import artifacts, storage


CODEX_PROVIDER_ID = "codex_cli"
CODEX_ARM_INTERFACE = "codex_cli_exec"
CODEX_ARM_PROVIDER_FAMILY = "openai"
CODEX_ARM_LANES = {"codex_commander", "codex_adversarial", "codex_reliability"}
CODEX_AUTH_MODE_INHERIT = "inherit_chatgpt"
CODEX_AUTH_MODE_ISOLATED_CHATGPT = "isolated_chatgpt"
CODEX_AUTH_MODE_API_KEY = "api_key"
CODEX_AUTH_MODE_DISABLED = "disabled"
CODEX_PWSH_PATH_ENV = "LOOP_CODEX_PWSH_PATH"
_OPENAI_PROVIDER_CONTRACT = provider_catalog()[CODEX_ARM_PROVIDER_FAMILY]
CODEX_DEFAULT_MODEL = provider_default_model(
    CODEX_ARM_PROVIDER_FAMILY,
    auth_route=AUTH_ROUTE_CODEX_CURRENT_USER,
)
CODEX_CHATGPT_RESPONSES_URL = str(
    _OPENAI_PROVIDER_CONTRACT["endpointByAuthRoute"][AUTH_ROUTE_CODEX_CURRENT_USER]
)
CODEX_CHATGPT_RESPONSE_LIMIT_BYTES = 64 * 1024 * 1024
CODEX_REASONING_EFFORTS = set(REASONING_EFFORTS)
CODEX_AUTH_MODES = {
    CODEX_AUTH_MODE_INHERIT,
    CODEX_AUTH_MODE_ISOLATED_CHATGPT,
    CODEX_AUTH_MODE_API_KEY,
    CODEX_AUTH_MODE_DISABLED,
}


# Public account/rate-limit telemetry is intentionally separate from the runtime
# catalog. It describes observed service limits; it never creates routing options.
PUBLIC_CODEX_MODEL_LIMITS: Dict[str, Dict[str, Any]] = {
    "gpt-5.6-sol": {
        "source": "OpenAI model docs",
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.6-sol",
        "contextWindow": 1_050_000,
        "maxOutputTokens": 128_000,
        "rateLimitClass": "Long Context",
        "tiers": [
            {"tier": "Tier 1", "rpm": 500, "tpm": 500_000, "batchQueueLimit": 1_500_000},
            {"tier": "Tier 2", "rpm": 5_000, "tpm": 1_000_000, "batchQueueLimit": 3_000_000},
            {"tier": "Tier 3", "rpm": 5_000, "tpm": 2_000_000, "batchQueueLimit": 100_000_000},
            {"tier": "Tier 4", "rpm": 10_000, "tpm": 4_000_000, "batchQueueLimit": 200_000_000},
            {"tier": "Tier 5", "rpm": 15_000, "tpm": 40_000_000, "batchQueueLimit": 15_000_000_000},
        ],
    },
    "gpt-5.6-terra": {
        "source": "OpenAI model docs",
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.6-terra",
        "contextWindow": 1_050_000,
        "maxOutputTokens": 128_000,
        "rateLimitClass": "Long Context",
        "tiers": [
            {"tier": "Tier 1", "rpm": 500, "tpm": 500_000, "batchQueueLimit": 1_500_000},
            {"tier": "Tier 2", "rpm": 5_000, "tpm": 1_000_000, "batchQueueLimit": 3_000_000},
            {"tier": "Tier 3", "rpm": 5_000, "tpm": 2_000_000, "batchQueueLimit": 100_000_000},
            {"tier": "Tier 4", "rpm": 10_000, "tpm": 4_000_000, "batchQueueLimit": 200_000_000},
            {"tier": "Tier 5", "rpm": 15_000, "tpm": 40_000_000, "batchQueueLimit": 15_000_000_000},
        ],
    },
    "gpt-5.6-luna": {
        "source": "OpenAI model docs",
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.6-luna",
        "contextWindow": 1_050_000,
        "maxOutputTokens": 128_000,
        "rateLimitClass": "Long Context",
        "tiers": [
            {"tier": "Tier 1", "rpm": 500, "tpm": 500_000, "batchQueueLimit": 5_000_000},
            {"tier": "Tier 2", "rpm": 5_000, "tpm": 2_000_000, "batchQueueLimit": 20_000_000},
            {"tier": "Tier 3", "rpm": 5_000, "tpm": 4_000_000, "batchQueueLimit": 40_000_000},
            {"tier": "Tier 4", "rpm": 10_000, "tpm": 10_000_000, "batchQueueLimit": 1_000_000_000},
            {"tier": "Tier 5", "rpm": 30_000, "tpm": 180_000_000, "batchQueueLimit": 15_000_000_000},
        ],
    },
    "gpt-5.4": {
        "source": "OpenAI model docs",
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.4",
        "contextWindow": 1_050_000,
        "maxOutputTokens": 128_000,
        "rateLimitClass": "Long Context",
        "tiers": [
            {"tier": "Tier 1", "rpm": 500, "tpm": 500_000, "batchQueueLimit": 1_500_000},
            {"tier": "Tier 2", "rpm": 5_000, "tpm": 1_000_000, "batchQueueLimit": 3_000_000},
            {"tier": "Tier 3", "rpm": 5_000, "tpm": 2_000_000, "batchQueueLimit": 100_000_000},
            {"tier": "Tier 4", "rpm": 10_000, "tpm": 4_000_000, "batchQueueLimit": 200_000_000},
            {"tier": "Tier 5", "rpm": 15_000, "tpm": 40_000_000, "batchQueueLimit": 15_000_000_000},
        ],
    },
    "gpt-5.3-codex": {
        "source": "OpenAI model docs",
        "sourceUrl": "https://developers.openai.com/api/docs/models/gpt-5.3-codex",
        "contextWindow": 400_000,
        "maxOutputTokens": 128_000,
        "rateLimitClass": "Codex",
        "tiers": [
            {"tier": "Tier 1", "rpm": 500, "tpm": 500_000, "batchQueueLimit": 1_500_000},
            {"tier": "Tier 2", "rpm": 5_000, "tpm": 1_000_000, "batchQueueLimit": 3_000_000},
            {"tier": "Tier 3", "rpm": 5_000, "tpm": 2_000_000, "batchQueueLimit": 100_000_000},
            {"tier": "Tier 4", "rpm": 10_000, "tpm": 4_000_000, "batchQueueLimit": 200_000_000},
            {"tier": "Tier 5", "rpm": 15_000, "tpm": 40_000_000, "batchQueueLimit": 15_000_000_000},
        ],
    },
}


LAST_MEASURED_CODEX_SMOKE: Dict[str, Any] = {
    "source": "Para wrapper bare-metal smoke",
    "measuredAt": "2026-05-05T18:00:12Z",
    "model": "gpt-5.4",
    "inputTokens": 21649,
    "cachedInputTokens": 2432,
    "billableInputTokens": 19217,
    "outputTokens": 91,
    "totalTokens": 21740,
    "estimatedCostUsd": 0.050015,
}


CODEX_MODEL_PRICING_USD_PER_1M: Dict[str, Dict[str, float]] = {
    model_id.lower(): {
        "input": float(metadata.get("inputPer1M") or 0.0),
        "cachedInput": float(metadata.get("cachedInputPer1M") or 0.0),
        "output": float(metadata.get("outputPer1M") or 0.0),
    }
    for model_id, metadata in provider_model_catalog(CODEX_ARM_PROVIDER_FAMILY).items()
    if any(
        float(metadata.get(field) or 0.0) > 0.0
        for field in ("inputPer1M", "cachedInputPer1M", "outputPer1M")
    )
}


DEFAULT_CODEX_LANE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "confidence": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "recommendedNextCheck": {"type": "string"},
        "filesTouched": {"type": "array", "items": {"type": "string"}},
        "commandsRun": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": [
        "verdict",
        "confidence",
        "findings",
        "evidence",
        "unknowns",
        "recommendedNextCheck",
        "filesTouched",
        "commandsRun",
        "summary",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class CodexLaneRequest:
    lane_id: str
    prompt: str
    root: Path
    model: str = CODEX_DEFAULT_MODEL
    reasoning_effort: str = ""
    subagents_enabled: bool = False
    sandbox: str = "read-only"
    timeout_seconds: int = 900
    max_total_tokens: int = 0
    max_cost_usd: float = 0.0
    output_schema: Optional[Dict[str, Any]] = None
    ignore_user_config: bool = True
    auth_mode: str = CODEX_AUTH_MODE_INHERIT
    env_overrides: Optional[Dict[str, str]] = None
    ephemeral: bool = True
    disable_plugins: bool = True
    disable_general_analytics: bool = True


class CodexChatGptTransportError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = int(status_code or 502)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def estimate_text_tokens(text: Any) -> int:
    raw = str(text or "")
    if not raw:
        return 0
    return max(1, int(math.ceil(len(raw) / 4)))


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _configured_timeout_seconds(payload: Dict[str, Any], default: int = 900) -> int:
    for key in ("timeoutSeconds", "timeout_seconds"):
        if key in payload and payload.get(key) is not None:
            return _as_int(payload.get(key))
    return max(0, int(default or 0))


def _as_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _as_bool(value: Any, fallback: bool) -> bool:
    if value is None or value == "":
        return bool(fallback)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_codex_reasoning_effort(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in CODEX_REASONING_EFFORTS else ""


def effective_codex_prompt(request: CodexLaneRequest) -> str:
    if request.subagents_enabled:
        contract = (
            "Nested Codex subagents are enabled for this provider call. You may delegate only when it "
            "materially improves the requested lane, while preserving the required output contract."
        )
    else:
        contract = (
            "Nested Codex subagents are disabled for this provider call. Do not delegate, spawn, or hand "
            "work to subagents; complete this provider lane yourself."
        )
    prompt = str(request.prompt or "").strip()
    return (prompt + "\n\nProvider subagent contract:\n" + contract).strip()


def _pricing_for_model(model: str) -> Optional[Dict[str, float]]:
    normalized = str(model or "").strip().lower()
    return CODEX_MODEL_PRICING_USD_PER_1M.get(normalized)


def _usage_cost_usd(model: str, input_tokens: int, cached_input_tokens: int, output_tokens: int) -> tuple[float, bool]:
    pricing = _pricing_for_model(model)
    if pricing is None:
        return 0.0, False
    billable_input_tokens = max(0, input_tokens - cached_input_tokens)
    cost = (
        (billable_input_tokens * pricing["input"])
        + (cached_input_tokens * pricing["cachedInput"])
        + (output_tokens * pricing["output"])
    ) / 1_000_000.0
    return round(cost, 6), True


def default_codex_usage_bucket(model: str = "") -> Dict[str, Any]:
    return {
        "calls": 0,
        "webSearchCalls": 0,
        "inputTokens": 0,
        "cachedInputTokens": 0,
        "billableInputTokens": 0,
        "outputTokens": 0,
        "reasoningTokens": 0,
        "totalTokens": 0,
        "modelCostUsd": 0.0,
        "toolCostUsd": 0.0,
        "estimatedCostUsd": 0.0,
        "pricingKnown": bool(_pricing_for_model(model)),
        "lastModel": str(model or "").strip() or None,
        "lastResponseId": None,
        "lastUpdated": None,
    }


def _usage_from_event_usage(raw_usage: Any) -> Dict[str, int]:
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = _as_int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
    cached_input_tokens = _as_int(
        usage.get(
            "cached_input_tokens",
            ((usage.get("input_tokens_details") or {}) if isinstance(usage.get("input_tokens_details"), dict) else {}).get("cached_tokens", 0),
        )
    )
    output_tokens = _as_int(usage.get("output_tokens", usage.get("completion_tokens", 0)))
    reasoning_tokens = _as_int(
        usage.get(
            "reasoning_output_tokens",
            ((usage.get("output_tokens_details") or {}) if isinstance(usage.get("output_tokens_details"), dict) else {}).get("reasoning_tokens", 0),
        )
    )
    total_tokens = _as_int(usage.get("total_tokens", input_tokens + output_tokens))
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    return {
        "inputTokens": input_tokens,
        "cachedInputTokens": min(cached_input_tokens, input_tokens),
        "outputTokens": output_tokens,
        "reasoningTokens": reasoning_tokens,
        "totalTokens": total_tokens,
    }


def parse_codex_jsonl_events(jsonl: str) -> tuple[List[Dict[str, Any]], List[str]]:
    events: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for line_number, line in enumerate(str(jsonl or "").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            warnings.append(f"codex jsonl line {line_number} was malformed and ignored.")
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
        else:
            warnings.append(f"codex jsonl line {line_number} was not an object and was ignored.")
    return events, warnings[:20]


def codex_usage_from_events(events: Iterable[Dict[str, Any]], model: str) -> Dict[str, Any]:
    usage = default_codex_usage_bucket(model)
    calls = 0
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "turn.completed":
            continue
        calls += 1
        delta = _usage_from_event_usage(event.get("usage"))
        usage["inputTokens"] += delta["inputTokens"]
        usage["cachedInputTokens"] += delta["cachedInputTokens"]
        usage["outputTokens"] += delta["outputTokens"]
        usage["reasoningTokens"] += delta["reasoningTokens"]
        usage["totalTokens"] += delta["totalTokens"]
    usage["calls"] = calls
    usage["billableInputTokens"] = max(0, int(usage["inputTokens"]) - int(usage["cachedInputTokens"]))
    model_cost, pricing_known = _usage_cost_usd(
        model,
        int(usage["inputTokens"]),
        int(usage["cachedInputTokens"]),
        int(usage["outputTokens"]),
    )
    usage["modelCostUsd"] = model_cost
    usage["estimatedCostUsd"] = model_cost
    usage["pricingKnown"] = pricing_known
    usage["lastUpdated"] = utc_now() if calls else None
    return usage


def _thread_id_from_events(events: Iterable[Dict[str, Any]]) -> Optional[str]:
    for event in events:
        if event.get("type") == "thread.started":
            thread_id = str(event.get("thread_id") or "").strip()
            if thread_id:
                return thread_id
    return None


def _last_agent_message(events: Iterable[Dict[str, Any]]) -> str:
    last_text = ""
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if item.get("type") != "agent_message":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            last_text = text
    return last_text


def default_codex_limits(request: CodexLaneRequest) -> Dict[str, Any]:
    timeout_seconds = int(request.timeout_seconds or 0)
    return {
        "localBudget": {
            "maxTotalTokens": max(0, int(request.max_total_tokens or 0)),
            "maxCostUsd": max(0.0, float(request.max_cost_usd or 0.0)),
            "timeoutSeconds": timeout_seconds if timeout_seconds > 0 else None,
            "timeoutDisabled": timeout_seconds <= 0,
            "sandbox": request.sandbox,
            "reasoningEffort": normalize_codex_reasoning_effort(request.reasoning_effort) or None,
            "subagentsEnabled": bool(request.subagents_enabled),
        },
        "providerRateLimits": {
            "known": False,
            "source": "codex exec JSONL",
            "note": "Codex CLI JSONL exposes turn usage, but not authoritative account/project RPM or TPM limits.",
        },
        "estimatedPromptTokens": estimate_text_tokens(effective_codex_prompt(request)),
        "reasons": [],
    }


def codex_home_path() -> Path:
    configured = str(os.getenv("CODEX_HOME") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex"


def manual_codex_limits_path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root is not None else Path.cwd()
    return base / "data" / "codex_limits.json"


def codex_auth_policy_path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root is not None else Path.cwd()
    return base / "data" / "codex_auth_policy.json"


def app_codex_home_path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root is not None else Path.cwd()
    return base / "data" / "codex_home"


def _codex_chatgpt_auth_material(
    root: Optional[Path] = None,
    auth_mode: str = CODEX_AUTH_MODE_INHERIT,
) -> Dict[str, str]:
    access_token = str(os.getenv("CODEX_ACCESS_TOKEN") or "").strip()
    account_id = str(os.getenv("CODEX_CHATGPT_ACCOUNT_ID") or "").strip()
    if access_token or account_id:
        if not access_token or not account_id:
            raise CodexChatGptTransportError(
                "Codex ChatGPT environment authentication requires both CODEX_ACCESS_TOKEN and CODEX_CHATGPT_ACCOUNT_ID.",
                401,
            )
        return {
            "accessToken": access_token,
            "accountId": account_id,
            "source": "codex_environment",
        }

    normalized_mode = normalize_codex_auth_mode(auth_mode)
    if normalized_mode == CODEX_AUTH_MODE_INHERIT:
        auth_path = codex_home_path() / "auth.json"
        source = "codex_current_user"
    elif normalized_mode == CODEX_AUTH_MODE_ISOLATED_CHATGPT:
        auth_path = app_codex_home_path(root) / "auth.json"
        source = "codex_isolated_user"
    else:
        raise CodexChatGptTransportError(
            "The direct ChatGPT Responses transport requires inherited or isolated ChatGPT authentication.",
            401,
        )

    try:
        if auth_path.stat().st_size > 4 * 1024 * 1024:
            raise CodexChatGptTransportError("The Codex authentication file is unexpectedly large.", 401)
        auth_payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except CodexChatGptTransportError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise CodexChatGptTransportError(
            "No readable current-user Codex ChatGPT authentication was found on this device.",
            401,
        ) from exc

    tokens = auth_payload.get("tokens") if isinstance(auth_payload.get("tokens"), dict) else {}
    stored_mode = str(auth_payload.get("auth_mode") or "").strip().lower()
    access_token = str(tokens.get("access_token") or "").strip()
    account_id = str(tokens.get("account_id") or "").strip()
    if stored_mode and stored_mode != "chatgpt":
        raise CodexChatGptTransportError("The current Codex session is not authenticated through ChatGPT.", 401)
    if not access_token or not account_id:
        raise CodexChatGptTransportError(
            "The current Codex session does not contain a usable ChatGPT access token and account id.",
            401,
        )
    return {
        "accessToken": access_token,
        "accountId": account_id,
        "source": source,
    }


def _codex_response_output_text(response: Any) -> str:
    current = response if isinstance(response, dict) else {}
    parts: List[str] = []
    for item in current.get("output", []):
        if not isinstance(item, dict) or str(item.get("type") or "") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict) or str(content.get("type") or "") != "output_text":
                continue
            text = str(content.get("text") or "")
            if text:
                parts.append(text)
    return "".join(parts).strip()


def run_codex_chatgpt_response(
    *,
    model: str,
    instructions: str,
    input_text: str,
    schema_name: str,
    output_schema: Dict[str, Any],
    reasoning_effort: str = "low",
    max_output_tokens: int = 0,
    timeout_seconds: Optional[float] = 900,
    root: Optional[Path] = None,
    auth_mode: str = CODEX_AUTH_MODE_INHERIT,
    subagents_enabled: bool = False,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Dict[str, Any]:
    auth = _codex_chatgpt_auth_material(root, auth_mode)
    normalized_schema_name = "_".join(
        part for part in str(schema_name or "parallm_output").strip().replace("-", "_").split() if part
    )
    normalized_schema_name = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in normalized_schema_name
    )[:64] or "parallm_output"
    effort = normalize_codex_reasoning_effort(reasoning_effort) or "low"
    subagent_contract = (
        "Nested model subagents are enabled for this call. Delegate only when it materially improves the requested output."
        if subagents_enabled
        else "Nested model subagents are disabled for this call. Complete the requested output without delegation."
    )
    effective_instructions = (str(instructions or "").strip() + "\n\n" + subagent_contract).strip()
    body: Dict[str, Any] = {
        "model": str(model or CODEX_DEFAULT_MODEL).strip() or CODEX_DEFAULT_MODEL,
        "instructions": effective_instructions,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": str(input_text or "")}],
            }
        ],
        "reasoning": {"effort": effort},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": normalized_schema_name,
                "strict": True,
                "schema": output_schema,
            },
        },
        "store": False,
        "stream": True,
    }
    request = urllib.request.Request(
        CODEX_CHATGPT_RESPONSES_URL,
        data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {auth['accessToken']}",
            "ChatGPT-Account-ID": auth["accountId"],
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "OpenAI-Beta": "responses=v1",
            "originator": "parallm_python",
        },
        method="POST",
    )

    output_done: List[str] = []
    output_deltas: List[str] = []
    final_response: Dict[str, Any] = {}
    response_error = ""
    received_bytes = 0
    http_status = 0
    try:
        with opener(request, timeout=timeout_seconds) as handle:
            http_status = int(getattr(handle, "status", 0) or getattr(handle, "code", 0) or 200)
            for raw_line in handle:
                encoded_line = raw_line if isinstance(raw_line, bytes) else str(raw_line).encode("utf-8", errors="replace")
                received_bytes += len(encoded_line)
                if received_bytes > CODEX_CHATGPT_RESPONSE_LIMIT_BYTES:
                    raise CodexChatGptTransportError("Codex ChatGPT response exceeded the 64 MiB transport limit.", 502)
                line = encoded_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload_text = line[5:].strip()
                if not payload_text or payload_text == "[DONE]":
                    continue
                try:
                    event = json.loads(payload_text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("type") or "")
                if event_type == "response.output_text.done":
                    output_done.append(str(event.get("text") or ""))
                elif event_type == "response.output_text.delta":
                    output_deltas.append(str(event.get("delta") or ""))
                elif event_type == "response.completed" and isinstance(event.get("response"), dict):
                    final_response = dict(event["response"])
                elif event_type == "response.failed":
                    failed_response = event.get("response") if isinstance(event.get("response"), dict) else {}
                    final_response = dict(failed_response)
                    failure = failed_response.get("error") if isinstance(failed_response.get("error"), dict) else {}
                    response_error = str(failure.get("message") or event.get("message") or "Codex ChatGPT response failed.")
                elif event_type == "error":
                    response_error = str(event.get("message") or event.get("error") or "Codex ChatGPT transport returned an error event.")
    except CodexChatGptTransportError:
        raise
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(8192).decode("utf-8", errors="replace").strip()
        except OSError:
            detail = ""
        raise CodexChatGptTransportError(
            f"Codex ChatGPT HTTP {int(exc.code or 502)}: {detail or exc.reason}",
            int(exc.code or 502),
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise CodexChatGptTransportError("Codex ChatGPT response timed out.", 504) from exc
    except urllib.error.URLError as exc:
        raise CodexChatGptTransportError(f"Codex ChatGPT connection failed: {exc.reason}", 502) from exc
    except OSError as exc:
        raise CodexChatGptTransportError(f"Codex ChatGPT transport failed: {exc}", 502) from exc

    if response_error:
        raise CodexChatGptTransportError(response_error, 502)
    output_text = "".join(output_done).strip() if output_done else "".join(output_deltas).strip()
    if not output_text:
        output_text = _codex_response_output_text(final_response)
    if not output_text:
        raise CodexChatGptTransportError("Codex ChatGPT response did not include output text.", 502)
    response_status = str(final_response.get("status") or "completed").strip().lower()
    if response_status not in {"completed", ""}:
        incomplete = final_response.get("incomplete_details") if isinstance(final_response.get("incomplete_details"), dict) else {}
        reason = str(incomplete.get("reason") or response_status)
        raise CodexChatGptTransportError(f"Codex ChatGPT response was {response_status}: {reason}", 502)
    final_response.setdefault("status", "completed")
    final_response.setdefault("model", body["model"])
    final_response["_paraTransport"] = "chatgpt_responses"
    return {
        "status": "completed",
        "response": final_response,
        "responseId": str(final_response.get("id") or ""),
        "outputText": output_text,
        "httpStatus": http_status,
        "receivedBytes": received_bytes,
        "authSource": auth["source"],
        "endpoint": CODEX_CHATGPT_RESPONSES_URL,
        "reasoningEffort": effort,
        "subagentsEnabled": bool(subagents_enabled),
    }


def normalize_codex_auth_mode(value: Any, fallback: str = CODEX_AUTH_MODE_INHERIT) -> str:
    candidate = str(value or "").strip().lower().replace("-", "_")
    if candidate in {"inherit", "chatgpt", "chatgpt_auth", "codex", "codex_auth", "user_config"}:
        return CODEX_AUTH_MODE_INHERIT
    if candidate in {"isolated", "isolated_codex", "app_chatgpt", "app_codex", "app_managed"}:
        return CODEX_AUTH_MODE_ISOLATED_CHATGPT
    if candidate in {"app", "app_key", "openai_key", "api_key", "para_key", "platform_api_key"}:
        return CODEX_AUTH_MODE_API_KEY
    if candidate in {"off", "none", "blocked"}:
        return CODEX_AUTH_MODE_DISABLED
    normalized_fallback = str(fallback or CODEX_AUTH_MODE_INHERIT).strip().lower().replace("-", "_")
    if candidate in CODEX_AUTH_MODES:
        return candidate
    return normalized_fallback if normalized_fallback in CODEX_AUTH_MODES else CODEX_AUTH_MODE_INHERIT


def _normalize_manual_codex_limits(payload: Any) -> Dict[str, Any]:
    current = payload if isinstance(payload, dict) else {}
    general = current.get("general") if isinstance(current.get("general"), dict) else {}
    raw_models = current.get("models") if isinstance(current.get("models"), dict) else {}
    models: Dict[str, Dict[str, str]] = {}
    for model, value in raw_models.items():
        model_id = str(model or "").strip().lower()
        if not model_id:
            continue
        config = value if isinstance(value, dict) else {"limit": value}
        models[model_id] = {
            "limit": str(config.get("limit") or "").strip(),
            "resetWindow": str(config.get("resetWindow") or config.get("reset_window") or "").strip(),
            "notes": str(config.get("notes") or "").strip(),
        }
    return {
        "general": {
            "label": str(general.get("label") or "Codex account").strip(),
            "limit": str(general.get("limit") or "").strip(),
            "resetWindow": str(general.get("resetWindow") or general.get("reset_window") or "").strip(),
            "notes": str(general.get("notes") or "").strip(),
        },
        "models": models,
        "updatedAt": str(current.get("updatedAt") or current.get("updated_at") or "").strip(),
    }


def read_manual_codex_limits(root: Optional[Path] = None) -> Dict[str, Any]:
    path = manual_codex_limits_path(root)
    if not path.is_file():
        return _normalize_manual_codex_limits({})
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _normalize_manual_codex_limits({})
    return _normalize_manual_codex_limits(parsed)


def save_manual_codex_limits(root: Optional[Path], payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_manual_codex_limits({**(payload or {}), "updatedAt": utc_now()})
    path = manual_codex_limits_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "message": "Codex manual limits saved.",
        "path": str(path),
        "manualAccountLimits": normalized,
    }


def read_codex_auth_policy(root: Optional[Path] = None) -> Dict[str, Any]:
    path = codex_auth_policy_path(root)
    if not path.is_file():
        return {"mode": CODEX_AUTH_MODE_INHERIT, "updatedAt": ""}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"mode": CODEX_AUTH_MODE_INHERIT, "updatedAt": ""}
    current = parsed if isinstance(parsed, dict) else {}
    return {
        "mode": normalize_codex_auth_mode(current.get("mode")),
        "updatedAt": str(current.get("updatedAt") or current.get("updated_at") or "").strip(),
    }


def _app_openai_key_status(root: Optional[Path] = None) -> Dict[str, Any]:
    from . import control

    pool = control.auth_key_pool_state(root, "openai")
    keys = pool.get("keys") if isinstance(pool.get("keys"), list) else []
    first = str(keys[0] if keys else "")
    last4 = first[-4:] if len(first) >= 4 else first
    return {
        "available": len(keys) > 0,
        "keyCount": len(keys),
        "last4": last4,
        "backend": str(pool.get("backend") or ""),
        "selectedMode": str(pool.get("selectedMode") or ""),
        "selectedModeLabel": str(pool.get("selectedModeLabel") or ""),
        "source": str(pool.get("localFilePath") or "Para OpenAI provider key pool"),
        "note": "Presence-only key-pool check; raw keys are not exposed.",
    }


def _first_app_openai_key(root: Optional[Path] = None) -> str:
    from . import control

    keys = control.read_auth_key_pool(root, "openai")
    return str(keys[0] if keys else "").strip()


def codex_auth_status(root: Optional[Path] = None) -> Dict[str, Any]:
    policy = read_codex_auth_policy(root)
    policy_mode = normalize_codex_auth_mode(policy.get("mode"))
    inherited_auth_path = codex_home_path() / "auth.json"
    inherited_available = inherited_auth_path.is_file()
    isolated_home = app_codex_home_path(root)
    isolated_auth_path = isolated_home / "auth.json"
    isolated_available = isolated_auth_path.is_file()
    app_key = _app_openai_key_status(root)

    if policy_mode == CODEX_AUTH_MODE_DISABLED:
        effective_known = False
        effective_mode = "disabled"
        effective_source = ""
        note = "Codex launches are blocked by Para settings."
    elif policy_mode == CODEX_AUTH_MODE_ISOLATED_CHATGPT:
        effective_known = isolated_available
        effective_mode = CODEX_AUTH_MODE_ISOLATED_CHATGPT if isolated_available else "missing_isolated_chatgpt_auth"
        effective_source = str(isolated_auth_path)
        note = "Codex will use Para's isolated Codex home. Sign in there with ChatGPT to spend Codex plan credits."
    elif policy_mode == CODEX_AUTH_MODE_API_KEY:
        effective_known = bool(app_key.get("available"))
        effective_mode = CODEX_AUTH_MODE_API_KEY if effective_known else "missing_openai_api_key"
        effective_source = str(app_key.get("source") or "Para OpenAI provider key pool")
        note = "Codex will use Para's OpenAI API key pool. This is API/platform billing, not Codex plan credits."
    else:
        effective_known = inherited_available
        effective_mode = "chatgpt" if inherited_available else "unknown"
        effective_source = str(inherited_auth_path)
        note = "Codex will inherit the local Codex/ChatGPT authentication relationship. Token contents are not read or exposed."

    return {
        "known": effective_known,
        "mode": effective_mode,
        "source": effective_source,
        "note": note,
        "policy": {
            "mode": policy_mode,
            "updatedAt": str(policy.get("updatedAt") or ""),
            "path": str(codex_auth_policy_path(root)),
        },
        "modes": [
            {
                "value": CODEX_AUTH_MODE_INHERIT,
                "label": "Inherit ChatGPT auth",
                "summary": "Use the existing local Codex/ChatGPT login from the Codex home directory.",
            },
            {
                "value": CODEX_AUTH_MODE_ISOLATED_CHATGPT,
                "label": "Para ChatGPT sign-in",
                "summary": "Use a Para-owned Codex home that can be signed into ChatGPT separately from the user profile.",
            },
            {
                "value": CODEX_AUTH_MODE_API_KEY,
                "label": "API key billing mode",
                "summary": "Use Para's OpenAI API key pool. This does not spend Codex plan credits.",
            },
            {
                "value": CODEX_AUTH_MODE_DISABLED,
                "label": "Disable Codex arm",
                "summary": "Prevent Codex launches until this policy is changed.",
            },
        ],
        "inheritedChatGpt": {
            "available": inherited_available,
            "mode": "chatgpt" if inherited_available else "unknown",
            "source": str(inherited_auth_path),
            "note": "Presence-only check; token contents are not read or exposed.",
        },
        "isolatedChatGpt": {
            "available": isolated_available,
            "mode": "chatgpt" if isolated_available else "unknown",
            "home": str(isolated_home),
            "source": str(isolated_auth_path),
            "note": "Para-owned Codex home for an app-managed ChatGPT sign-in path.",
        },
        "appOpenAIKey": app_key,
    }


def save_codex_auth_policy(root: Optional[Path], payload: Dict[str, Any]) -> Dict[str, Any]:
    mode = normalize_codex_auth_mode((payload or {}).get("mode"))
    policy = {"mode": mode, "updatedAt": utc_now()}
    path = codex_auth_policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "message": "Codex auth policy saved.",
        "path": str(path),
        "auth": codex_auth_status(root),
    }


def _read_codex_models_cache(home: Optional[Path] = None) -> tuple[Dict[str, Any], Path, List[str]]:
    codex_home = Path(home) if home is not None else codex_home_path()
    cache_path = codex_home / "models_cache.json"
    warnings: List[str] = []
    if not cache_path.is_file():
        return {}, cache_path, warnings
    try:
        parsed = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"Codex model cache could not be read: {exc}")
        return {}, cache_path, warnings
    return parsed if isinstance(parsed, dict) else {}, cache_path, warnings


def _normalize_codex_model_catalog_entry(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    slug = str(entry.get("slug") or "").strip()
    if not slug:
        return None
    reasoning_levels = []
    for item in entry.get("supported_reasoning_levels") if isinstance(entry.get("supported_reasoning_levels"), list) else []:
        if isinstance(item, dict) and str(item.get("effort") or "").strip():
            reasoning_levels.append(str(item.get("effort") or "").strip())
    return {
        "model": slug,
        "displayName": str(entry.get("display_name") or slug).strip(),
        "description": str(entry.get("description") or "").strip(),
        "contextWindow": _as_int(entry.get("context_window")),
        "maxContextWindow": _as_int(entry.get("max_context_window")),
        "effectiveContextWindowPercent": _as_int(entry.get("effective_context_window_percent")),
        "defaultReasoningLevel": str(entry.get("default_reasoning_level") or "").strip(),
        "supportedReasoningLevels": reasoning_levels,
        "supportsReasoningSummaries": bool(entry.get("supports_reasoning_summaries")),
        "supportedInApi": bool(entry.get("supported_in_api")),
        "visibility": str(entry.get("visibility") or "").strip(),
        "upgrade": entry.get("upgrade") if isinstance(entry.get("upgrade"), dict) else None,
    }


def _codex_catalog_status(selected_model: str) -> Dict[str, Any]:
    parsed, cache_path, warnings = _read_codex_models_cache()
    raw_models = parsed.get("models") if isinstance(parsed.get("models"), list) else []
    models = [model for model in (_normalize_codex_model_catalog_entry(entry) for entry in raw_models) if model]
    selected = next((model for model in models if model["model"].lower() == selected_model.lower()), None)
    return {
        "source": str(cache_path),
        "exists": cache_path.is_file(),
        "fetchedAt": str(parsed.get("fetched_at") or "").strip(),
        "clientVersion": str(parsed.get("client_version") or "").strip(),
        "modelCount": len(models),
        "selectedModel": selected or {},
        "models": models[:80],
        "warnings": warnings,
    }


def _codex_pricing_status(model: str) -> Dict[str, Any]:
    pricing = _pricing_for_model(model)
    return {
        "known": pricing is not None,
        "model": model,
        "inputPer1M": float((pricing or {}).get("input") or 0.0),
        "cachedInputPer1M": float((pricing or {}).get("cachedInput") or 0.0),
        "outputPer1M": float((pricing or {}).get("output") or 0.0),
        "source": "local Para pricing snapshot",
    }


def codex_limits_status(root: Optional[Path] = None, model: str = "") -> Dict[str, Any]:
    selected_model = str(model or "").strip().lower() or CODEX_DEFAULT_MODEL
    manual_limits = read_manual_codex_limits(root)
    return {
        "provider": CODEX_PROVIDER_ID,
        "selectedModel": selected_model,
        "auth": codex_auth_status(root),
        "catalog": _codex_catalog_status(selected_model),
        "pricing": _codex_pricing_status(selected_model),
        "publicModelLimits": PUBLIC_CODEX_MODEL_LIMITS.get(
            selected_model,
            {
                "source": "not in local public limit snapshot",
                "sourceUrl": "https://developers.openai.com/api/docs/models/compare",
                "tiers": [],
            },
        ),
        "projectRateLimits": {
            "known": False,
            "source": "OpenAI Admin project rate-limit API",
            "sourceUrl": "https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/projects/subresources/rate_limits",
            "note": "Requires organization/project API credentials; not available from Codex CLI JSONL.",
        },
        "manualAccountLimits": manual_limits,
        "measured": {
            "lastSmoke": dict(LAST_MEASURED_CODEX_SMOKE),
            "note": "Measured smoke is a local Para planning floor, not a provider bill.",
        },
        "updatedAt": utc_now(),
    }


def _clean_codex_lane_id(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch == "_")
    if cleaned in CODEX_ARM_LANES:
        return cleaned
    if cleaned in {"commander", "adversarial", "reliability"}:
        return f"codex_{cleaned}"
    return "codex_adversarial"


def _codex_arm_state_packet(state: Dict[str, Any]) -> Dict[str, Any]:
    draft = state.get("draft") if isinstance(state.get("draft"), dict) else {}
    active_task = state.get("activeTask") if isinstance(state.get("activeTask"), dict) else {}
    active_task_packet = {
        key: active_task.get(key)
        for key in ("taskId", "objective", "provider", "model", "summarizerProvider", "summarizerModel", "constraints")
        if active_task.get(key) not in (None, "", [])
    }
    return {
        "draft": draft,
        "activeTask": active_task_packet or None,
        "loop": state.get("loop") if isinstance(state.get("loop"), dict) else {},
        "executionHealth": state.get("executionHealth") if isinstance(state.get("executionHealth"), dict) else {},
        "contractWarnings": state.get("contractWarnings") if isinstance(state.get("contractWarnings"), list) else [],
    }


def _compact_json(value: Any, max_chars: int = 28000) -> str:
    try:
        text = json.dumps(value, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        text = json.dumps({"unserializable": str(value)[:1000]}, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...<truncated>"


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            text = "\n".join(str(item).strip() for item in value if str(item).strip())
            if text.strip():
                return text.strip()
    return ""


def build_codex_arm_prompt(lane_id: str, objective: str, state_packet: Dict[str, Any]) -> str:
    lane_guidance = {
        "codex_commander": "Synthesize the repo-aware plan and identify the next decision that would change execution.",
        "codex_adversarial": "Pressure-test assumptions, fragile internals, provider wiring, and operator-facing failure modes.",
        "codex_reliability": "Focus on tests, rollback, security, observability, and production-readiness gaps.",
    }
    return "\n\n".join(
        [
            "ParaLLM Codex arm packet",
            "Provider family: OpenAI",
            "Agent interface: local Codex CLI non-interactive (`codex exec --json`). This is the automation surface for a Codex-style IDE agent arm, not a raw model-only worker call.",
            f"Lane id: {lane_id}",
            f"Lane role: {lane_guidance.get(lane_id, lane_guidance['codex_adversarial'])}",
            "Execution boundary: read-only. Do not edit files, do not run destructive commands, and do not request secrets.",
            "Return the strict structured pressure packet requested by the output schema.",
            "Operator objective:\n" + (objective or "Inspect the staged Para state and return the highest-value pressure packet."),
            "Current Para state packet:\n```json\n" + _compact_json(state_packet) + "\n```",
        ]
    ).strip()


def _codex_arm_rejected(message: str, *, lane_id: str = "codex_adversarial") -> Dict[str, Any]:
    return {
        "ok": False,
        "providerFamily": CODEX_ARM_PROVIDER_FAMILY,
        "provider": CODEX_PROVIDER_ID,
        "interface": CODEX_ARM_INTERFACE,
        "laneId": lane_id,
        "status": "rejected",
        "message": message,
        "artifactFile": None,
        "artifactMeta": None,
        "laneArtifact": None,
    }


def run_codex_arm(root: Optional[Path], payload: Dict[str, Any], *, runner: Runner = subprocess.run) -> Dict[str, Any]:
    current = payload if isinstance(payload, dict) else {}
    lane_id = _clean_codex_lane_id(current.get("laneId") or current.get("lane_id"))
    provider_family = str(current.get("providerFamily") or current.get("provider_family") or CODEX_ARM_PROVIDER_FAMILY).strip().lower()
    if provider_family not in {"openai", "oai"}:
        return _codex_arm_rejected("Codex arm is available only when the OpenAI provider family is selected.", lane_id=lane_id)

    paths = storage.project_paths(root)
    state = storage.read_state_payload(paths)
    state_packet = _codex_arm_state_packet(state)
    draft = state_packet.get("draft") if isinstance(state_packet.get("draft"), dict) else {}
    objective = _first_text(
        current.get("objective"),
        current.get("prompt"),
        draft.get("objective") if isinstance(draft, dict) else "",
        ((state_packet.get("activeTask") or {}) if isinstance(state_packet.get("activeTask"), dict) else {}).get("objective"),
    )
    model = str(
        current.get("model")
        or current.get("codexModel")
        or current.get("codex_model")
        or CODEX_DEFAULT_MODEL
    ).strip() or CODEX_DEFAULT_MODEL
    reasoning_effort = normalize_codex_reasoning_effort(
        current.get("reasoningEffort")
        or current.get("reasoning_effort")
        or (draft.get("reasoningEffort") if isinstance(draft, dict) else "")
    )
    subagents_enabled = _as_bool(
        current.get("codexSubagentsEnabled", current.get("subagentsEnabled")),
        _as_bool(draft.get("codexSubagentsEnabled"), False) if isinstance(draft, dict) else False,
    )
    auth_mode = normalize_codex_auth_mode(current.get("authMode") or current.get("auth_mode"), read_codex_auth_policy(paths.root)["mode"])
    auth_status = codex_auth_status(paths.root)
    env_overrides: Dict[str, str] = {}
    ignore_user_config = not _as_bool(current.get("useUserConfig", current.get("use_user_config")), auth_mode == CODEX_AUTH_MODE_INHERIT)
    if auth_mode == CODEX_AUTH_MODE_DISABLED:
        return _codex_arm_rejected("Codex auth is disabled in Para settings.", lane_id=lane_id)
    if auth_mode == CODEX_AUTH_MODE_INHERIT and not bool(auth_status.get("inheritedChatGpt", {}).get("available")):
        return _codex_arm_rejected("Codex ChatGPT auth is not available. Sign in with Codex/ChatGPT or change the Codex auth mode.", lane_id=lane_id)
    if auth_mode == CODEX_AUTH_MODE_ISOLATED_CHATGPT:
        isolated = auth_status.get("isolatedChatGpt") if isinstance(auth_status.get("isolatedChatGpt"), dict) else {}
        if not bool(isolated.get("available")):
            return _codex_arm_rejected("Para Codex ChatGPT auth is not available. Sign into the isolated Para Codex home first.", lane_id=lane_id)
        env_overrides["CODEX_HOME"] = str(app_codex_home_path(paths.root))
        ignore_user_config = True
    if auth_mode == CODEX_AUTH_MODE_API_KEY:
        api_key = _first_app_openai_key(paths.root)
        if not api_key:
            return _codex_arm_rejected("OpenAI API key billing mode needs a Para OpenAI API key.", lane_id=lane_id)
        env_overrides["OPENAI_API_KEY"] = api_key
        ignore_user_config = True

    request = CodexLaneRequest(
        lane_id=lane_id,
        prompt=build_codex_arm_prompt(lane_id, objective, state_packet),
        root=paths.root,
        model=model,
        reasoning_effort=reasoning_effort,
        subagents_enabled=subagents_enabled,
        sandbox=str(current.get("sandbox") or "read-only").strip() or "read-only",
        timeout_seconds=_configured_timeout_seconds(current),
        max_total_tokens=_as_int(current.get("maxTotalTokens") or current.get("max_total_tokens")),
        max_cost_usd=_as_float(current.get("maxCostUsd") or current.get("max_cost_usd")),
        ignore_user_config=ignore_user_config,
        auth_mode=auth_mode,
        env_overrides=env_overrides or None,
        ephemeral=_as_bool(current.get("ephemeral"), True),
        disable_plugins=_as_bool(current.get("disablePlugins", current.get("disable_plugins")), True),
        disable_general_analytics=_as_bool(
            current.get("disableGeneralAnalytics", current.get("disable_general_analytics")),
            True,
        ),
    )
    lane_artifact = run_codex_lane(request, runner=runner)
    created_at = utc_now()
    stored_payload = {
        "artifactType": "codex_lane",
        "createdAt": created_at,
        "providerFamily": CODEX_ARM_PROVIDER_FAMILY,
        "provider": CODEX_PROVIDER_ID,
        "interface": CODEX_ARM_INTERFACE,
        "model": request.model,
        "laneId": lane_id,
        "arm": {
            "providerFamily": CODEX_ARM_PROVIDER_FAMILY,
            "provider": CODEX_PROVIDER_ID,
            "interface": CODEX_ARM_INTERFACE,
            "extensionLike": True,
            "authMode": auth_mode,
            "notes": "Uses local Codex CLI non-interactive automation as an agent arm. ChatGPT auth spends Codex plan credits; API-key mode spends OpenAI platform credits.",
        },
        "input": {
            "objective": objective,
            "prompt": request.prompt,
            "state": state_packet,
            "sandbox": request.sandbox,
            "authMode": auth_mode,
            "useUserConfig": not request.ignore_user_config,
            "appManagedCodexHome": auth_mode == CODEX_AUTH_MODE_ISOLATED_CHATGPT,
            "apiKeyBillingMode": auth_mode == CODEX_AUTH_MODE_API_KEY,
            "pluginsDisabled": request.disable_plugins,
            "reasoningEffort": request.reasoning_effort or None,
            "subagentsEnabled": request.subagents_enabled,
        },
        "output": lane_artifact,
        "responseText": lane_artifact.get("responseText"),
        "usage": lane_artifact.get("usage"),
        "limits": lane_artifact.get("limits"),
        "warnings": lane_artifact.get("warnings") if isinstance(lane_artifact.get("warnings"), list) else [],
    }
    safe_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_name = f"codex_{lane_id}_{safe_stamp}.json"
    artifact_meta = artifacts.write_json_artifact(paths.root, "outputs", artifact_name, stored_payload)
    lane_status = str(lane_artifact.get("status") or "unknown")
    return {
        "ok": lane_status in {"completed", "budget_exhausted"},
        "providerFamily": CODEX_ARM_PROVIDER_FAMILY,
        "provider": CODEX_PROVIDER_ID,
        "interface": CODEX_ARM_INTERFACE,
        "laneId": lane_id,
        "model": request.model,
        "status": lane_status,
        "artifactFile": artifact_meta["name"],
        "artifactMeta": artifact_meta,
        "laneArtifact": lane_artifact,
        "message": f"Codex arm {lane_id} wrote {artifact_meta['name']}.",
    }


def _budget_reasons(request: CodexLaneRequest, usage: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    max_total_tokens = max(0, int(request.max_total_tokens or 0))
    if max_total_tokens and int(usage.get("totalTokens") or 0) > max_total_tokens:
        reasons.append(f"observed tokens {int(usage.get('totalTokens') or 0)}/{max_total_tokens}")
    max_cost_usd = max(0.0, float(request.max_cost_usd or 0.0))
    if max_cost_usd and float(usage.get("estimatedCostUsd") or 0.0) > max_cost_usd:
        reasons.append(f"observed estimated cost ${float(usage.get('estimatedCostUsd') or 0.0):.6f}/${max_cost_usd:.6f}")
    return reasons


def _preflight_budget_block(request: CodexLaneRequest) -> Optional[Dict[str, Any]]:
    limits = default_codex_limits(request)
    prompt_tokens = int(limits["estimatedPromptTokens"])
    max_total_tokens = max(0, int(request.max_total_tokens or 0))
    reasons: List[str] = []
    if max_total_tokens and prompt_tokens > max_total_tokens:
        reasons.append(f"estimated prompt tokens {prompt_tokens}/{max_total_tokens}")
    max_cost_usd = max(0.0, float(request.max_cost_usd or 0.0))
    pricing = _pricing_for_model(request.model)
    if max_cost_usd and pricing is not None:
        estimated_input_cost = round((prompt_tokens * pricing["input"]) / 1_000_000.0, 6)
        if estimated_input_cost > max_cost_usd:
            reasons.append(f"estimated prompt input cost ${estimated_input_cost:.6f}/${max_cost_usd:.6f}")
    if not reasons:
        return None
    limits["reasons"] = reasons
    return {
        "laneId": request.lane_id,
        "provider": CODEX_PROVIDER_ID,
        "model": request.model,
        "status": "budget_blocked",
        "exitCode": None,
        "threadId": None,
        "responseText": "",
        "usage": default_codex_usage_bucket(request.model),
        "limits": limits,
        "warnings": [],
    }


def codex_artifact_from_jsonl(
    jsonl: str,
    *,
    lane_id: str,
    model: str,
    exit_code: int = 0,
    stderr: str = "",
    request: Optional[CodexLaneRequest] = None,
) -> Dict[str, Any]:
    events, warnings = parse_codex_jsonl_events(jsonl)
    usage = codex_usage_from_events(events, model)
    response_text = _last_agent_message(events)
    status = "completed" if int(exit_code or 0) == 0 else "error"
    limits = default_codex_limits(
        request
        if request is not None
        else CodexLaneRequest(lane_id=lane_id, prompt="", root=Path("."), model=model)
    )
    if status == "completed" and not events:
        status = "error"
        warnings.append("Codex exited successfully but emitted no JSONL events.")
    elif status == "completed" and not response_text:
        status = "error"
        warnings.append("Codex emitted events but no completed agent response.")
    if request is not None and status == "completed":
        reasons = _budget_reasons(request, usage)
        if reasons:
            status = "budget_exhausted"
            limits["reasons"] = reasons
    if status == "error" and stderr:
        warnings.append(str(stderr).strip()[:1000])
    return {
        "laneId": lane_id,
        "provider": CODEX_PROVIDER_ID,
        "model": model,
        "status": status,
        "exitCode": int(exit_code or 0),
        "threadId": _thread_id_from_events(events),
        "responseText": response_text,
        "usage": usage,
        "limits": limits,
        "eventCount": len(events),
        "warnings": warnings[:20],
    }


def _write_schema_file(directory: Path, schema: Dict[str, Any]) -> Path:
    schema_path = directory / "codex_lane_output.schema.json"
    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    return schema_path


def build_codex_exec_command(request: CodexLaneRequest, schema_path: Path) -> List[str]:
    command = [
        "codex",
        "exec",
        "--json",
    ]
    if request.ignore_user_config:
        command.append("--ignore-user-config")
    if request.ephemeral:
        command.append("--ephemeral")
    if request.disable_plugins:
        command.extend(["--disable", "plugins"])
    reasoning_effort = normalize_codex_reasoning_effort(request.reasoning_effort)
    if reasoning_effort:
        command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    command.extend(["-c", f"agents.enabled={'true' if request.subagents_enabled else 'false'}"])
    command.extend(["--enable" if request.subagents_enabled else "--disable", "multi_agent"])
    command.extend(
        [
            "--sandbox",
            str(request.sandbox or "read-only"),
            "--cd",
            str(Path(request.root).resolve()),
            "--model",
            str(request.model or CODEX_DEFAULT_MODEL),
            "--output-schema",
            str(schema_path),
            "-",
        ]
    )
    return command


Runner = Callable[..., Any]


def _codex_subprocess_environment(request: CodexLaneRequest) -> Optional[Dict[str, str]]:
    overrides = {
        str(key): str(value)
        for key, value in (request.env_overrides or {}).items()
        if str(key).strip()
    }
    configured_pwsh = str(overrides.get(CODEX_PWSH_PATH_ENV) or os.getenv(CODEX_PWSH_PATH_ENV) or "").strip()
    if not overrides and not configured_pwsh:
        return None

    run_env = dict(os.environ)
    run_env.update(overrides)
    if configured_pwsh:
        pwsh_path = Path(os.path.expandvars(configured_pwsh)).expanduser()
        try:
            pwsh_path = pwsh_path.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError(f"{CODEX_PWSH_PATH_ENV} does not point to an accessible executable: {configured_pwsh}") from exc
        if not pwsh_path.is_file():
            raise RuntimeError(f"{CODEX_PWSH_PATH_ENV} does not point to a file: {pwsh_path}")
        existing_path = str(run_env.get("PATH") or "")
        run_env["PATH"] = str(pwsh_path.parent) + (os.pathsep + existing_path if existing_path else "")
        run_env[CODEX_PWSH_PATH_ENV] = str(pwsh_path)
    return run_env


def run_codex_lane(request: CodexLaneRequest, *, runner: Runner = subprocess.run) -> Dict[str, Any]:
    blocked = _preflight_budget_block(request)
    if blocked is not None:
        return blocked

    schema = request.output_schema if isinstance(request.output_schema, dict) else DEFAULT_CODEX_LANE_OUTPUT_SCHEMA
    with tempfile.TemporaryDirectory(prefix="parallm-codex-lane-") as tmpdir:
        schema_path = _write_schema_file(Path(tmpdir), schema)
        command = build_codex_exec_command(request, schema_path)
        run_env = _codex_subprocess_environment(request)
        timeout_seconds = int(request.timeout_seconds or 0)
        completed = runner(
            command,
            input=effective_codex_prompt(request),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds if timeout_seconds > 0 else None,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            **({"env": run_env} if run_env is not None else {}),
        )
    return codex_artifact_from_jsonl(
        str(getattr(completed, "stdout", "") or ""),
        lane_id=request.lane_id,
        model=request.model,
        exit_code=int(getattr(completed, "returncode", 1) or 0),
        stderr=str(getattr(completed, "stderr", "") or ""),
        request=request,
    )
