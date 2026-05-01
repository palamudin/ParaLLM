from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional


MODEL_CAPACITY_PATH = Path(__file__).resolve().parents[2] / "data" / "model_capacities.json"


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
