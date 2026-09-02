from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "tool-capabilities.v1.json"
SCHEMA_VERSION = "parallm.tool-capabilities.v1"
DIRECT_TARGETS = {"direct", "direct_baseline", "pure_direct"}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


@lru_cache(maxsize=1)
def load_contract() -> dict[str, Any]:
    try:
        payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Capability-memory contract could not be loaded: {CONTRACT_PATH}: {error}") from error
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise RuntimeError(f"Unsupported capability-memory contract: {payload.get('schemaVersion')!r}")
    memory = payload.get("memory")
    groups = payload.get("groups")
    inventories = payload.get("runtimeInventories")
    if (
        not isinstance(memory, Mapping)
        or not isinstance(groups, list)
        or not groups
        or not isinstance(inventories, Mapping)
        or not inventories
    ):
        raise RuntimeError(
            "Capability-memory contract requires memory metadata, runtime inventories, and tool groups."
        )
    seen_tools: set[str] = set()
    for group in groups:
        if not isinstance(group, Mapping) or not str(group.get("id") or "").strip():
            raise RuntimeError("Capability-memory contract contains an invalid tool group.")
        tools = _string_list(group.get("tools"))
        if not tools:
            raise RuntimeError(f"Capability group {group.get('id')!r} has no tools.")
        duplicates = seen_tools.intersection(tools)
        if duplicates:
            raise RuntimeError(f"Capability-memory contract repeats tools: {', '.join(sorted(duplicates))}")
        seen_tools.update(tools)
    for runtime, tools_value in inventories.items():
        tools = _string_list(tools_value)
        if not str(runtime).strip() or not tools:
            raise RuntimeError("Capability-memory contract contains an invalid runtime inventory.")
        unknown = set(tools).difference(seen_tools)
        if unknown:
            raise RuntimeError(
                f"Capability runtime {runtime!r} names undeclared tools: {', '.join(sorted(unknown))}"
            )
        if len(tools) != len(set(tools)):
            raise RuntimeError(f"Capability runtime {runtime!r} repeats tool names.")
    return dict(payload)


def contract_sha256() -> str:
    return hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()


def installed_tool_names() -> tuple[str, ...]:
    return tuple(
        tool
        for group in load_contract()["groups"]
        if isinstance(group, Mapping)
        for tool in _string_list(group.get("tools"))
    )


def runtime_tool_names(runtime: str) -> tuple[str, ...]:
    inventories = load_contract()["runtimeInventories"]
    name = str(runtime or "").strip().lower()
    if name not in inventories:
        raise KeyError(f"Unknown capability runtime: {runtime!r}")
    return tuple(_string_list(inventories[name]))


def tool_names_from_schemas(tools: Iterable[Mapping[str, Any]] | None) -> tuple[str, ...]:
    names: list[str] = []
    for tool in tools or ():
        if not isinstance(tool, Mapping):
            continue
        name = str(tool.get("name") or "").strip()
        if not name and isinstance(tool.get("function"), Mapping):
            name = str(tool["function"].get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def render_installed_memory() -> str:
    contract = load_contract()
    memory = contract["memory"]
    lines = [str(memory.get("title") or "PARALLM SYSTEM CAPABILITY MEMORY")]
    lines.extend(f"- {principle}" for principle in _string_list(memory.get("principles")))
    lines.append("Canonical capability procedures (runtime availability is projected per lane):")
    for group in contract["groups"]:
        tools = ", ".join(_string_list(group.get("tools")))
        lines.append(
            f"- {str(group.get('label') or group.get('id'))}: {str(group.get('procedure') or '').strip()} "
            f"Tools: {tools}."
        )
    return "\n".join(lines).strip()


def render_lane_memory(
    *,
    target_kind: str,
    provider: str,
    model: str,
    offered_tools: Sequence[str] = (),
    callable_tools: Sequence[str] = (),
) -> str:
    target = str(target_kind or "generic").strip().lower() or "generic"
    if target in DIRECT_TARGETS:
        return ""
    offered = tuple(dict.fromkeys(str(name).strip() for name in offered_tools if str(name).strip()))
    callable_now = tuple(dict.fromkeys(str(name).strip() for name in callable_tools if str(name).strip()))
    unavailable = tuple(name for name in offered if name not in callable_now)
    state_lines = [
        "Current lane capability projection:",
        f"- lane: {target}",
        f"- provider/model: {str(provider or 'unknown').strip()} / {str(model or 'unknown').strip()}",
        f"- callable now: {', '.join(callable_now) if callable_now else 'none'}",
    ]
    if unavailable:
        state_lines.append(
            "- offered by Para but unavailable on this model route: " + ", ".join(unavailable)
        )
    if not offered:
        state_lines.append("- this lane consumes supplied evidence and tool results but has no direct tool actuator")
    state_lines.append(
        "Invoke only names under callable now. If none are callable, do not emit a fabricated tool call or claim a result."
    )
    return render_installed_memory() + "\n" + "\n".join(state_lines)


def attach_to_instructions(
    instructions: str,
    *,
    target_kind: str,
    provider: str,
    model: str,
    offered_tools: Sequence[str] = (),
    callable_tools: Sequence[str] = (),
) -> str:
    block = render_lane_memory(
        target_kind=target_kind,
        provider=provider,
        model=model,
        offered_tools=offered_tools,
        callable_tools=callable_tools,
    )
    if not block:
        return str(instructions or "")
    return str(instructions or "").rstrip() + "\n\n" + block + "\n"


def memory_record() -> dict[str, Any]:
    contract = load_contract()
    metadata = contract["memory"]
    content = render_installed_memory()
    return {
        "id": str(metadata.get("id") or "parallm-system-capability-passport"),
        "kind": str(metadata.get("kind") or "procedural_capability"),
        "scope": str(metadata.get("scope") or "system/runtime"),
        "authority": str(metadata.get("authority") or "runtime-contract"),
        "confidence": float(metadata.get("confidence", 1.0)),
        "sourceId": str(metadata.get("sourceId") or "system:parallm-capability-passport"),
        "contractSha256": contract_sha256(),
        "contentSha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content": content,
    }
