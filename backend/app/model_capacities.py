from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional


MODEL_CAPACITY_PATH = Path(__file__).resolve().parents[2] / "data" / "model_capacities.json"
RUNTIME_OUTPUT_POLICY_KEY = "_runtimeoutputpolicy"


def _normalize(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


@lru_cache(maxsize=1)
def load_model_capacity_catalog() -> Dict[str, Dict[str, Any]]:
    if not MODEL_CAPACITY_PATH.exists():
        return {}
    raw = json.loads(MODEL_CAPACITY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    catalog: Dict[str, Dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        catalog[_normalize(key)] = dict(value)
    return catalog


def resolve_model_capacity(provider: Optional[str], model: Optional[str]) -> Dict[str, Any]:
    provider_key = _normalize(provider)
    model_key = _normalize(model)
    if not provider_key or not model_key:
        return {}
    return dict(load_model_capacity_catalog().get(f"{provider_key}:{model_key}") or {})


def runtime_output_policy() -> Dict[str, Any]:
    policy = load_model_capacity_catalog().get(RUNTIME_OUTPUT_POLICY_KEY)
    return dict(policy) if isinstance(policy, dict) else {}


def max_output_tokens(provider: Optional[str], model: Optional[str]) -> int:
    capacity = resolve_model_capacity(provider, model)
    try:
        value = int(capacity.get("maxOutputTokens", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def explicit_output_fallback_tokens(provider: Optional[str] = None) -> int:
    policy = runtime_output_policy()
    provider_key = _normalize(provider)
    by_provider = policy.get("explicitMaxOutputTokensByProvider")
    if isinstance(by_provider, dict) and provider_key:
        try:
            provider_value = int(by_provider.get(provider_key, 0) or 0)
        except (TypeError, ValueError):
            provider_value = 0
        if provider_value > 0:
            return provider_value
    try:
        value = int(policy.get("unknownModelExplicitMaxOutputTokens", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def output_retry_policy(target_kind: Optional[str] = None) -> Dict[str, int]:
    policy = runtime_output_policy()
    defaults = policy.get("requestedOutputRetry")
    if not isinstance(defaults, dict):
        defaults = {}
    by_target = defaults.get("targets")
    target_config: Dict[str, Any] = {}
    if isinstance(by_target, dict):
        candidate = by_target.get(_normalize(target_kind))
        if isinstance(candidate, dict):
            target_config = candidate

    def positive_int(key: str, fallback: int) -> int:
        try:
            value = int(target_config.get(key, defaults.get(key, fallback)) or 0)
        except (TypeError, ValueError):
            value = 0
        return value if value > 0 else fallback

    return {
        "floor": positive_int("floor", 1600),
        "retryFloor": positive_int("retryFloor", 3200),
        "fallbackCeiling": positive_int("fallbackCeiling", 12000),
    }


def inferred_prompt_budget_tokens(provider: Optional[str], model: Optional[str], purpose: str) -> int:
    capacity = resolve_model_capacity(provider, model)
    if purpose == "review_binder":
        explicit = int(capacity.get("recommendedReviewBinderBudgetTokens", 0) or 0)
        if explicit > 0:
            return explicit
    else:
        explicit = int(capacity.get("recommendedSummaryPromptBudgetTokens", 0) or 0)
        if explicit > 0:
            return explicit

    context_window = int(capacity.get("contextWindowTokens", 0) or 0)
    model_text = _normalize(model)
    provider_text = _normalize(provider)
    compact_markers = ("mini", "nano", "flash", "highspeed")
    if any(marker in model_text for marker in compact_markers):
        return 6000 if purpose == "review_binder" else 12000
    if provider_text in {"minimax", "deepseek"}:
        return 8000 if purpose == "review_binder" else 16000
    if context_window >= 1_000_000:
        return 12000 if purpose == "review_binder" else 24000
    if context_window >= 400_000:
        return 8000 if purpose == "review_binder" else 16000
    if context_window >= 200_000:
        return 6000 if purpose == "review_binder" else 12000
    if context_window >= 128_000:
        return 5000 if purpose == "review_binder" else 10000
    return 4000 if purpose == "review_binder" else 8000
