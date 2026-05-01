from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional


def normalize_provider_name(provider: Any) -> str:
    return str(provider or "").strip().lower()


def empty_provider_result(provider: Any, reason: str = "") -> Dict[str, str]:
    return {
        "provider": normalize_provider_name(provider) or "unknown",
        "answer": "",
        "stance": "",
        "confidenceNote": reason.strip(),
        "sourceField": "",
    }


def provider_result(provider: Any, answer: Any, stance: Any = "", confidence_note: Any = "", source_field: str = "") -> Dict[str, str]:
    return {
        "provider": normalize_provider_name(provider) or "unknown",
        "answer": clean_text(answer),
        "stance": clean_text(stance),
        "confidenceNote": clean_text(confidence_note),
        "sourceField": str(source_field or "").strip(),
    }


def parse_embedded_json_value(value: Any) -> Any:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidates: List[str] = [raw]
    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    for block in fenced_blocks:
        cleaned = str(block or "").strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
    first_object = raw.find("{")
    last_object = raw.rfind("}")
    if 0 <= first_object < last_object:
        extracted = raw[first_object:last_object + 1].strip()
        if extracted and extracted not in candidates:
            candidates.append(extracted)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            repaired = repair_truncated_json(candidate)
            if repaired and repaired != candidate:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    continue
    return None


def repair_truncated_json(candidate: Any) -> Optional[str]:
    raw = str(candidate or "")
    if not raw:
        return None
    stack: List[str] = []
    in_string = False
    escaped = False
    for char in raw:
        if escaped:
            escaped = False
            continue
        if in_string:
            if char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            stack.append(char)
            continue
        if char in "}]":
            if not stack:
                return None
            opener = stack.pop()
            if (opener, char) not in {("{", "}"), ("[", "]")}:
                return None
    if in_string or not stack:
        return None
    closers: List[str] = []
    while stack:
        opener = stack.pop()
        closers.append("}" if opener == "{" else "]")
    return raw + "".join(closers)


def safe_provider_payload(input_value: Any) -> Any:
    if input_value is None:
        return None
    if isinstance(input_value, (dict, list)):
        return input_value
    if isinstance(input_value, str):
        decoded = parse_embedded_json_value(input_value)
        if decoded is not None:
            return decoded
        trimmed = input_value.strip()
        if trimmed:
            return {"response": trimmed}
        return None
    return {"response": str(input_value)}


def get_by_path(obj: Any, path: str) -> Any:
    if obj is None or not path:
        return None
    current = obj
    for part in str(path).split("."):
        if current is None:
            return None
        if re.fullmatch(r"\d+", part):
            if not isinstance(current, list):
                return None
            index = int(part)
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def humanize_key(value: Any) -> str:
    return (
        str(value or "")
        .replace("_", " ")
        .strip()
        .title()
    )


def value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        lines = []
        for item in value:
            item_text = value_to_text(item).strip()
            if item_text:
                lines.append(item_text)
        return "\n".join(lines)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            item_text = value_to_text(item).strip()
            if item_text:
                parts.append(f"{humanize_key(key)}: {item_text}")
        return " | ".join(parts)
    return str(value)


def clean_text(value: Any) -> str:
    return (
        value_to_text(value)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n\n\n", "\n\n")
        .strip()
    )


def compact_join(parts: Iterable[Any], separator: str = " | ") -> str:
    rendered = [clean_text(part) for part in parts]
    return separator.join([part for part in rendered if part]).strip()


def array_to_bullets(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    lines = []
    for item in value:
        item_text = clean_text(item)
        if item_text:
            lines.append(f"- {item_text}")
    return "\n".join(lines)


def array_to_sentence(value: Any, label: str) -> str:
    if not isinstance(value, list):
        return ""
    items = [clean_text(item) for item in value if clean_text(item)]
    if not items:
        return ""
    return f"{label}: {'; '.join(items)}"


def indent_text(value: Any, prefix: str = "  ") -> str:
    text = clean_text(value)
    if not text:
        return ""
    return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())


def render_key_values(obj: Any, keys: Iterable[str]) -> str:
    if not isinstance(obj, dict):
        return ""
    lines = []
    for key in keys:
        rendered = clean_text(obj.get(key))
        if rendered:
            lines.append(f"{humanize_key(key)}: {rendered}")
    return "\n".join(lines)


def render_sections(sections: Iterable[tuple[str, Any]]) -> str:
    blocks: List[str] = []
    for title, body in sections:
        rendered = clean_text(body)
        if rendered:
            blocks.append(f"## {title}\n{rendered}")
    return "\n\n".join(blocks).strip()


def render_timed_actions(actions: Any) -> str:
    if not isinstance(actions, list):
        return ""
    lines = []
    for action in actions:
        if not isinstance(action, dict):
            text = clean_text(action)
            if text:
                lines.append(f"- {text}")
            continue
        lines.append(
            "- " + compact_join(
                [
                    f"[{clean_text(action.get('time'))}]" if clean_text(action.get("time")) else "",
                    action.get("action"),
                    f"— {clean_text(action.get('rationale'))}" if clean_text(action.get("rationale")) else "",
                ],
                " ",
            ).strip()
        )
    return "\n".join([line for line in lines if line.strip("- ").strip()])


def render_decision_gates(gates: Any) -> str:
    if not isinstance(gates, list):
        return ""
    lines = []
    for gate in gates:
        if not isinstance(gate, dict):
            text = clean_text(gate)
            if text:
                lines.append(f"- {text}")
            continue
        lines.append(
            "- " + compact_join(
                [
                    f"Gate: {clean_text(gate.get('gate'))}" if clean_text(gate.get("gate")) else "",
                    f"Trigger: {clean_text(gate.get('trigger'))}" if clean_text(gate.get("trigger")) else "",
                    f"Action: {clean_text(gate.get('action'))}" if clean_text(gate.get("action")) else "",
                    f"Owner: {clean_text(gate.get('owner'))}" if clean_text(gate.get("owner")) else "",
                ]
            )
        )
    return "\n".join([line for line in lines if line.strip("- ").strip()])


def render_role_reasons(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    lines = []
    for item in items:
        if not isinstance(item, dict):
            text = clean_text(item)
            if text:
                lines.append(f"- {text}")
            continue
        lines.append(
            "- " + compact_join(
                [
                    f"Role: {clean_text(item.get('role'))}" if clean_text(item.get("role")) else "",
                    f"Reason: {clean_text(item.get('reason'))}" if clean_text(item.get("reason")) else "",
                ]
            )
        )
    return "\n".join([line for line in lines if line.strip("- ").strip()])


def render_risk_triage(risk_triage: Any) -> str:
    if not isinstance(risk_triage, dict):
        return ""
    sections: List[str] = []
    for level in ("critical", "high", "medium", "low"):
        value = risk_triage.get(level)
        if value is None:
            continue
        rendered = array_to_bullets(value) if isinstance(value, list) else clean_text(value)
        if rendered:
            sections.append(f"{level.upper()}:\n{rendered}")
    return "\n\n".join(sections).strip()


def render_anthropic_phases(phases: Any) -> str:
    if not isinstance(phases, list):
        return ""
    blocks: List[str] = []
    for phase in phases:
        if not isinstance(phase, dict):
            text = clean_text(phase)
            if text:
                blocks.append(text)
            continue
        header = compact_join(
            [
                f"Phase {clean_text(phase.get('phase'))}" if clean_text(phase.get("phase")) else "",
                phase.get("name"),
                f"({clean_text(phase.get('window'))})" if clean_text(phase.get("window")) else "",
                f"Goal: {clean_text(phase.get('goal'))}" if clean_text(phase.get("goal")) else "",
            ],
            " ",
        )
        step_lines: List[str] = []
        for step in phase.get("steps", []) if isinstance(phase.get("steps"), list) else []:
            if not isinstance(step, dict):
                text = clean_text(step)
                if text:
                    step_lines.append(f"- {text}")
                continue
            step_lines.append(
                "- " + compact_join(
                    [
                        f"{clean_text(step.get('step'))}." if clean_text(step.get("step")) else "",
                        step.get("action"),
                        f"— {clean_text(step.get('detail'))}" if clean_text(step.get("detail")) else "",
                        f"(Evidence: {clean_text(step.get('evidence_preservation'))})" if clean_text(step.get("evidence_preservation")) else "",
                        f"(Reasoning: {clean_text(step.get('reasoning'))})" if clean_text(step.get("reasoning")) else "",
                    ],
                    " ",
                ).strip()
            )
        blocks.append(compact_join([header, "\n".join(step_lines)], "\n"))
    return "\n\n".join([block for block in blocks if block]).strip()


def flatten_object(obj: Any, prefix: str = "", out: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if out is None:
        out = {}
    if obj is None:
        return out
    if not isinstance(obj, (dict, list)):
        out[prefix or "value"] = obj
        return out
    if isinstance(obj, list):
        for index, item in enumerate(obj):
            next_prefix = f"{prefix}.{index}" if prefix else str(index)
            flatten_object(item, next_prefix, out)
        return out
    for key, value in obj.items():
        next_prefix = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, (dict, list)):
            flatten_object(value, next_prefix, out)
        else:
            out[next_prefix] = value
    return out


def pick_first_text(obj: Any, paths: Iterable[str]) -> str:
    for path in paths:
        text = clean_text(get_by_path(obj, path))
        if text:
            return text
    return ""


def find_first_path(obj: Any, paths: Iterable[str]) -> str:
    for path in paths:
        if clean_text(get_by_path(obj, path)):
            return path
    return ""


def looks_like_nested_incident_only(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(
        payload.get("incident")
        or payload.get("phases")
        or payload.get("decision_gates_summary")
        or payload.get("t_plus_60_checkpoint")
    )


def looks_like_minimax_plan(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(
        payload.get("immediateActions")
        or payload.get("initialAssessment")
        or payload.get("riskTriage")
        or payload.get("nextStepsAfterFirstHour")
        or payload.get("communicationsPlan")
    )


def looks_like_minimax_flat_plan(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(
        payload.get("immediate_actions_0_to_15_minutes")
        or payload.get("first_hour_objectives")
        or payload.get("control_plane_trust_status")
    )


def extract_likely_answer(payload: Any) -> str:
    flattened = flatten_object(payload)
    preferred_suffixes = [
        "answer",
        "answerDraft",
        "summary",
        "initialAssessment",
        "response",
        "output",
        "completion",
        "content",
        "text",
    ]
    for suffix in preferred_suffixes:
        for path, value in flattened.items():
            if str(path).lower().endswith(suffix.lower()):
                text = clean_text(value)
                if text:
                    return text
    longest = ""
    for value in flattened.values():
        if isinstance(value, str) and len(value) > len(longest):
            longest = value
    return clean_text(longest)


def render_nested_plan_value(value: Any) -> str:
    if isinstance(value, list):
        return array_to_bullets(value)
    if isinstance(value, dict):
        lines: List[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                nested = render_nested_plan_value(item)
                if nested:
                    lines.append(f"- {humanize_key(key)}:\n{indent_text(nested)}")
                continue
            rendered = clean_text(item)
            if rendered:
                lines.append(f"- {humanize_key(key)}: {rendered}")
        return "\n".join(lines)
    return clean_text(value)


def render_plan_action_group(group: Any) -> str:
    if not isinstance(group, dict):
        return clean_text(group)
    blocks: List[str] = []
    for key, value in group.items():
        if not isinstance(value, dict):
            rendered = render_nested_plan_value(value)
            if rendered:
                blocks.append(f"### {humanize_key(key)}\n{rendered}")
            continue
        lines: List[str] = []
        preferred_keys = [
            "action",
            "rationale",
            "blocking_dependencies",
            "risk",
            "evidence_action",
            "decision_gate",
            "who_to_wake",
            "what_to_tell_them",
            "time_constraint",
            "acceptance_needed_from",
            "documentation",
            "triggered_status",
            "who",
            "when",
            "reason",
        ]
        used_keys = set()
        for item_key in preferred_keys:
            rendered = clean_text(value.get(item_key))
            if rendered:
                lines.append(f"- {humanize_key(item_key)}: {rendered}")
                used_keys.add(item_key)
        for item_key, item_value in value.items():
            if item_key in used_keys:
                continue
            rendered = render_nested_plan_value(item_value)
            if rendered:
                lines.append(f"- {humanize_key(item_key)}:\n{indent_text(rendered)}")
        blocks.append(f"### {humanize_key(key)}\n" + "\n".join(lines).strip())
    return "\n\n".join(block for block in blocks if block.strip()).strip()


def render_minimax_flat_plan(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    immediate = get_by_path(payload, "immediate_actions_0_to_15_minutes")
    short_term = get_by_path(immediate, "short_term_actions_15_to_30_minutes") if isinstance(immediate, dict) else None
    medium_term = get_by_path(short_term, "medium_term_actions_30_to_60_minutes") if isinstance(short_term, dict) else None
    risk_acceptances = get_by_path(medium_term, "risk_acceptances_needed") if isinstance(medium_term, dict) else None
    summary_lines = [
        compact_join(
            [
                clean_text(get_by_path(payload, "classification")),
                f"ID: {clean_text(get_by_path(payload, 'incident_id'))}" if clean_text(get_by_path(payload, "incident_id")) else "",
                f"Discovered: {clean_text(get_by_path(payload, 'discovered_utc'))}" if clean_text(get_by_path(payload, "discovered_utc")) else "",
            ]
        ),
        compact_join(
            [
                f"Severity: {clean_text(get_by_path(payload, 'severity'))}" if clean_text(get_by_path(payload, "severity")) else "",
                f"Status: {clean_text(get_by_path(payload, 'current_status'))}" if clean_text(get_by_path(payload, "current_status")) else "",
                f"Affected tenants: {clean_text(get_by_path(payload, 'affected_tenants'))}" if clean_text(get_by_path(payload, "affected_tenants")) else "",
            ]
        ),
        f"Confidence level: {clean_text(get_by_path(payload, 'confidence_level'))}" if clean_text(get_by_path(payload, "confidence_level")) else "",
        f"Control-plane trust: {clean_text(get_by_path(payload, 'control_plane_trust_status'))}" if clean_text(get_by_path(payload, "control_plane_trust_status")) else "",
    ]
    immediate_group = dict(immediate) if isinstance(immediate, dict) else {}
    if isinstance(immediate_group.get("short_term_actions_15_to_30_minutes"), dict):
        immediate_group.pop("short_term_actions_15_to_30_minutes", None)
    short_group = dict(short_term) if isinstance(short_term, dict) else {}
    if isinstance(short_group.get("medium_term_actions_30_to_60_minutes"), dict):
        short_group.pop("medium_term_actions_30_to_60_minutes", None)
    sections = [
        ("Summary", "\n".join(line for line in summary_lines if line.strip())),
        ("First hour objectives", array_to_bullets(get_by_path(payload, "first_hour_objectives"))),
        ("Immediate actions (0-15 minutes)", render_plan_action_group(immediate_group)),
        ("Short-term actions (15-30 minutes)", render_plan_action_group(short_group)),
        ("Medium-term actions (30-60 minutes)", render_plan_action_group(medium_term)),
        ("Risk acceptances needed", render_plan_action_group(risk_acceptances)),
        ("Post-first-hour immediate priorities", array_to_bullets(get_by_path(risk_acceptances, "post_first_hour_immediate_priorities")) if isinstance(risk_acceptances, dict) else ""),
        ("Compliance considerations", render_nested_plan_value(get_by_path(risk_acceptances, "compliance_considerations")) if isinstance(risk_acceptances, dict) else ""),
    ]
    return render_sections(sections)


def normalize_openai(provider: Any, payload: Any) -> Dict[str, str]:
    answer = pick_first_text(
        payload,
        [
            "answer",
            "output_text",
            "message.content",
            "choices.0.message.content",
            "choices.0.text",
            "response.answer",
            "data.answer",
        ],
    ) or extract_likely_answer(payload)
    embedded_payload = parse_embedded_json_value(answer)
    if isinstance(embedded_payload, dict):
        answer = pick_first_text(
            embedded_payload,
            [
                "answer",
                "output_text",
                "message.content",
                "choices.0.message.content",
                "choices.0.text",
                "response.answer",
                "data.answer",
            ],
        ) or answer
    return provider_result(
        provider,
        answer,
        stance=pick_first_text(payload, ["stance", "response.stance", "data.stance"])
        or (pick_first_text(embedded_payload, ["stance", "response.stance", "data.stance"]) if isinstance(embedded_payload, dict) else ""),
        confidence_note=pick_first_text(payload, ["confidenceNote", "confidence_note", "response.confidenceNote"])
        or (
            pick_first_text(embedded_payload, ["confidenceNote", "confidence_note", "response.confidenceNote"])
            if isinstance(embedded_payload, dict)
            else ""
        ),
        source_field=find_first_path(
            payload,
            [
                "answer",
                "output_text",
                "message.content",
                "choices.0.message.content",
                "choices.0.text",
            ],
        ),
    )


def normalize_xai(provider: Any, payload: Any) -> Dict[str, str]:
    answer = pick_first_text(
        payload,
        [
            "answer",
            "message.content",
            "choices.0.message.content",
            "choices.0.text",
            "response.answer",
            "data.answer",
        ],
    ) or extract_likely_answer(payload)
    return provider_result(
        provider,
        answer,
        stance=pick_first_text(payload, ["stance", "response.stance", "data.stance"]),
        confidence_note=pick_first_text(payload, ["confidenceNote", "confidence_note", "response.confidenceNote"]),
        source_field=find_first_path(
            payload,
            [
                "answer",
                "message.content",
                "choices.0.message.content",
                "choices.0.text",
            ],
        ),
    )


def normalize_ollama(provider: Any, payload: Any) -> Dict[str, str]:
    direct = pick_first_text(payload, ["answer", "answerDraft", "response", "message.content", "output"])
    if direct:
        return provider_result(
            provider,
            direct,
            stance=pick_first_text(payload, ["stance", "leadDirection"]),
            confidence_note=compact_join(
                [
                    pick_first_text(payload, ["suggestedLaneReason"]),
                    array_to_sentence(get_by_path(payload, "uncertainty"), "Uncertainty"),
                ],
                " ",
            ),
            source_field=find_first_path(payload, ["answer", "answerDraft", "response", "message.content", "output"]),
        )
    rendered = render_sections(
        [
            ("Lead direction", pick_first_text(payload, ["leadDirection"])),
            ("Why this direction", pick_first_text(payload, ["whyThisDirection", "suggestedLaneReason"])),
            ("Suggested lane types", array_to_bullets(get_by_path(payload, "suggestedLaneTypes"))),
            ("Keep course if", array_to_bullets(get_by_path(payload, "keepCourseIf"))),
            ("Change course if", array_to_bullets(get_by_path(payload, "changeCourseIf"))),
            ("Pressure points", array_to_bullets(get_by_path(payload, "pressurePoints"))),
            ("Questions for workers", array_to_bullets(get_by_path(payload, "questionsForWorkers"))),
        ]
    )
    return provider_result(
        provider,
        rendered or extract_likely_answer(payload),
        stance=pick_first_text(payload, ["stance", "leadDirection"]),
        confidence_note=array_to_sentence(get_by_path(payload, "uncertainty"), "Uncertainty"),
        source_field="ollama.rendered",
    )


def normalize_anthropic(provider: Any, payload: Any) -> Dict[str, str]:
    direct = pick_first_text(payload, ["answer", "content.0.text", "message.content", "completion", "response"])
    if direct and not looks_like_nested_incident_only(payload):
        return provider_result(
            provider,
            direct,
            stance=pick_first_text(payload, ["stance", "incident.severity"]),
            confidence_note=pick_first_text(payload, ["confidenceNote", "confidence_note"]),
            source_field=find_first_path(payload, ["answer", "content.0.text", "message.content", "completion", "response"]),
        )
    incident = get_by_path(payload, "incident") if isinstance(get_by_path(payload, "incident"), dict) else {}
    wake = incident.get("wake_senior_lead") if isinstance(incident.get("wake_senior_lead"), dict) else {}
    checkpoint = get_by_path(payload, "t_plus_60_checkpoint") if isinstance(get_by_path(payload, "t_plus_60_checkpoint"), dict) else {}
    incident_summary = render_sections(
        [
            (
                "Incident",
                compact_join(
                    [
                        incident.get("title"),
                        f"ID: {clean_text(incident.get('id'))}" if clean_text(incident.get("id")) else "",
                        f"Severity: {clean_text(incident.get('severity'))}" if clean_text(incident.get("severity")) else "",
                        f"Declared: {clean_text(incident.get('declared_at'))}" if clean_text(incident.get("declared_at")) else "",
                    ]
                ),
            ),
            ("Threat hypothesis", incident.get("threat_hypothesis")),
            ("Senior lead decision", render_key_values(wake, ["decision", "action", "justification"])),
        ]
    )
    rendered = render_sections(
        [
            ("Summary", incident_summary),
            ("Phases", render_anthropic_phases(get_by_path(payload, "phases"))),
            ("Decision gates", render_decision_gates(get_by_path(payload, "decision_gates_summary"))),
            ("Do not do", array_to_bullets(get_by_path(payload, "do_not_do"))),
            (
                "T+60 checkpoint",
                render_sections(
                    [
                        ("Expected state at T+60", checkpoint.get("expected_state")),
                        ("If payload unknown at 60 min", checkpoint.get("if_payload_unknown_at_60_min")),
                        ("Next phase", checkpoint.get("next_phase")),
                    ]
                ),
            ),
        ]
    )
    return provider_result(
        provider,
        rendered or extract_likely_answer(payload),
        stance=compact_join(
            [
                f"Severity: {clean_text(incident.get('severity'))}" if clean_text(incident.get("severity")) else "",
                f"Senior lead: {clean_text(wake.get('decision'))}" if clean_text(wake.get("decision")) else "",
            ]
        ),
        confidence_note="Rendered from Anthropic incident-response structure.",
        source_field="anthropic.rendered",
    )


def normalize_minimax(provider: Any, payload: Any) -> Dict[str, str]:
    answer_draft = pick_first_text(payload, ["answerDraft"])
    if answer_draft:
        return provider_result(
            provider,
            answer_draft,
            stance=pick_first_text(payload, ["stance", "leadDirection", "incident.severity", "incident.status"]),
            confidence_note=pick_first_text(payload, ["confidenceNote", "confidence_note", "notes", "uncertainty"]),
            source_field="answerDraft",
        )
    if looks_like_minimax_flat_plan(payload):
        rendered = render_minimax_flat_plan(payload)
        return provider_result(
            provider,
            rendered or extract_likely_answer(payload),
            stance=compact_join(
                [
                    f"Severity: {clean_text(get_by_path(payload, 'severity'))}" if clean_text(get_by_path(payload, "severity")) else "",
                    f"Status: {clean_text(get_by_path(payload, 'current_status'))}" if clean_text(get_by_path(payload, "current_status")) else "",
                    f"Control-plane trust: {clean_text(get_by_path(payload, 'control_plane_trust_status'))}" if clean_text(get_by_path(payload, "control_plane_trust_status")) else "",
                ]
            ),
            confidence_note=clean_text(get_by_path(payload, "confidence_level")) or "Rendered from MiniMax incident-response structure.",
            source_field="minimax.rendered_flat_plan",
        )
    direct = pick_first_text(payload, ["answer", "response", "message.content", "choices.0.message.content", "output"])
    if direct and not looks_like_minimax_plan(payload):
        return provider_result(
            provider,
            direct,
            stance=pick_first_text(payload, ["stance", "incident.severity", "incident.status"]),
            confidence_note=pick_first_text(payload, ["confidenceNote", "confidence_note", "notes"]),
            source_field=find_first_path(payload, ["answer", "response", "message.content", "choices.0.message.content", "output"]),
        )
    incident = get_by_path(payload, "incident") if isinstance(get_by_path(payload, "incident"), dict) else {}
    risk_mitigation = get_by_path(payload, "riskMitigation") if isinstance(get_by_path(payload, "riskMitigation"), dict) else {}
    incident_summary = render_sections(
        [
            (
                "Incident",
                compact_join(
                    [
                        incident.get("title"),
                        f"ID: {clean_text(incident.get('id'))}" if clean_text(incident.get("id")) else "",
                        f"Severity: {clean_text(incident.get('severity'))}" if clean_text(incident.get("severity")) else "",
                        f"Status: {clean_text(incident.get('status'))}" if clean_text(incident.get("status")) else "",
                        f"Detected: {clean_text(incident.get('detectedAt'))}" if clean_text(incident.get("detectedAt")) else "",
                        f"Goal: {clean_text(incident.get('durationGoal'))}" if clean_text(incident.get("durationGoal")) else "",
                    ]
                ),
            ),
            ("Initial assessment", get_by_path(payload, "initialAssessment")),
            ("Risk mitigation", render_key_values(risk_mitigation, ["balance", "contingency"])),
        ]
    )
    rendered = render_sections(
        [
            ("Summary", incident_summary),
            ("Immediate actions", render_timed_actions(get_by_path(payload, "immediateActions"))),
            ("Decision gates", render_decision_gates(get_by_path(payload, "decisionGates"))),
            ("Escalations", render_role_reasons(get_by_path(payload, "escalations"))),
            ("Risk triage", render_risk_triage(get_by_path(payload, "riskTriage"))),
            ("Evidence preservation", array_to_bullets(get_by_path(payload, "evidencePreservation"))),
            ("Compliance considerations", array_to_bullets(get_by_path(payload, "complianceConsiderations"))),
            ("Next steps after first hour", array_to_bullets(get_by_path(payload, "nextStepsAfterFirstHour"))),
            ("Notes", get_by_path(payload, "notes")),
        ]
    )
    return provider_result(
        provider,
        rendered or extract_likely_answer(payload),
        stance=compact_join(
            [
                f"Severity: {clean_text(incident.get('severity'))}" if clean_text(incident.get("severity")) else "",
                f"Status: {clean_text(incident.get('status'))}" if clean_text(incident.get("status")) else "",
            ]
        ),
        confidence_note="Rendered from MiniMax incident-response structure.",
        source_field="minimax.rendered",
    )


def normalize_generic(provider: Any, payload: Any) -> Dict[str, str]:
    answer = pick_first_text(
        payload,
        [
            "answer",
            "answerDraft",
            "summary",
            "initialAssessment",
            "response",
            "output",
            "message.content",
            "choices.0.message.content",
            "content.0.text",
            "completion",
        ],
    ) or extract_likely_answer(payload)
    return provider_result(
        provider,
        answer,
        stance=pick_first_text(payload, ["stance", "leadDirection", "incident.severity", "incident.status"]),
        confidence_note=pick_first_text(payload, ["confidenceNote", "confidence_note", "notes"]),
        source_field=find_first_path(
            payload,
            [
                "answer",
                "answerDraft",
                "summary",
                "initialAssessment",
                "response",
                "output",
                "message.content",
                "choices.0.message.content",
                "content.0.text",
                "completion",
            ],
        ) or "generic.heuristic",
    )


def normalize_provider_response(provider: Any, input_value: Any) -> Dict[str, str]:
    payload = safe_provider_payload(input_value)
    normalized_provider = normalize_provider_name(provider)
    if payload is None:
        return empty_provider_result(provider, "Empty or invalid payload.")
    if normalized_provider in {"openai", "oai", "deepseek"}:
        return normalize_openai(provider, payload)
    if normalized_provider in {"xai", "grok"}:
        return normalize_xai(provider, payload)
    if normalized_provider == "ollama":
        return normalize_ollama(provider, payload)
    if normalized_provider in {"anthropic", "claude"}:
        return normalize_anthropic(provider, payload)
    if normalized_provider == "minimax":
        return normalize_minimax(provider, payload)
    return normalize_generic(provider, payload)


def extract_normalized_provider_answer(provider: Any, input_value: Any) -> str:
    normalized = normalize_provider_response(provider, input_value)
    return clean_text(normalized.get("answer")) or ""
