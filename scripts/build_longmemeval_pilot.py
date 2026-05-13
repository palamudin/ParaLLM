from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "external" / "longmemeval" / "longmemeval_oracle.json"
DEFAULT_CASE_COUNT = 6


def sanitize_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "case"


def content_terms(text: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "again",
        "with",
        "what",
        "when",
        "where",
        "which",
        "that",
        "this",
        "from",
        "have",
        "need",
        "does",
        "were",
        "was",
        "the",
        "and",
        "for",
        "you",
        "our",
        "previous",
        "chat",
        "remind",
        "checking",
        "could",
        "give",
        "help",
        "some",
        "tips",
        "thanks",
        "really",
        "helpful",
        "would",
        "like",
    }
    return {
        term
        for term in re.findall(r"[a-zA-Z0-9]+", text.lower())
        if len(term) > 2 and term not in stopwords
    }


def compact_excerpt(text: str, limit: int = 860) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "..."


def message_relevance(question_terms: set[str], role: str, session_index: int, message_index: int, content: str) -> float:
    message_terms = content_terms(content)
    if not question_terms or not message_terms:
        return 0.0
    overlap = len(question_terms.intersection(message_terms))
    numeric_overlap = len({term for term in question_terms if any(char.isdigit() for char in term)}.intersection(message_terms))
    role_boost = 1.25 if role.lower() == "user" else -0.2
    event_boost = min(1.2, event_cue_score(content) * 0.25) if role.lower() == "user" else 0.0
    recency_boost = session_index * 0.04 + message_index * 0.004
    return overlap + numeric_overlap * 0.75 + role_boost + event_boost + recency_boost


def event_cue_score(content: str) -> int:
    text = str(content or "")
    lower = text.lower()
    score = 0
    if re.search(r"\b\d{1,2}[:/]\d{1,2}\b|\b\d{1,2}(?:st|nd|rd|th)?\b", lower):
        score += 1
    if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", lower):
        score += 1
    for cue in (
        "by the way",
        "recently",
        "still need",
        "need to",
        "i got",
        "i had",
        "i just",
        "i wore",
        "picked up",
        "pick up",
        "return",
        "exchanged",
        "replaced",
        "serviced",
        "personal best",
    ):
        if cue in lower:
            score += 1
    return score


def flatten_session_messages(sessions: Iterable[Any], *, question: str, max_chars: int = 14000) -> str:
    question_terms = content_terms(question)
    scored_messages: List[tuple[float, int, int, str, str]] = []
    event_messages: List[tuple[float, int, int, str]] = []
    chunks: List[str] = []
    for index, session in enumerate(sessions, start=1):
        chunks.append(f"Session {index}:")
        if not isinstance(session, list):
            chunks.append(str(session))
            continue
        for message_index, message in enumerate(session, start=1):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "unknown").strip()
            content = str(message.get("content") or "").strip()
            if content:
                score = message_relevance(question_terms, role, index, message_index, content)
                scored_messages.append((score, index, message_index, role, content))
                if role.lower() == "user":
                    event_score = event_cue_score(content) + len(question_terms.intersection(content_terms(content))) * 0.5
                    if event_score > 0:
                        event_messages.append((event_score, index, message_index, content))
                chunks.append(f"{role}: {content}")
    text = "\n".join(chunks).strip()
    focused: List[str] = []
    for score, session_index, message_index, role, content in sorted(
        scored_messages,
        key=lambda item: (item[0], item[1], item[2]),
        reverse=True,
    )[:7]:
        if score <= 0:
            continue
        focused.append(
            f"Session {session_index} message {message_index} {role}: {compact_excerpt(content)}"
        )
    focused_text = "\n".join(focused).strip()
    event_selected = sorted(
        sorted(event_messages, key=lambda item: item[0], reverse=True)[:10],
        key=lambda item: (item[1], item[2]),
    )
    event_text = "\n".join(
        f"Session {session_index} message {message_index} user: {compact_excerpt(content, 520)}"
        for _score, session_index, message_index, content in event_selected
    ).strip()
    if focused_text:
        return (
            "Question-focused excerpts ranked by lexical overlap and recency. "
            "Later excerpts can supersede earlier personal facts when they update the same detail.\n"
            f"{focused_text}\n\nChronological user-event ledger extracted from the same transcript:\n{event_text}\n\nFull oracle transcript:\n{text}"
        )[:max_chars]
    return text[:max_chars]


def answer_concept_groups(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    question_id = str(record.get("question_id") or "").strip()
    answer = str(record.get("answer") or "").strip()
    aliases: Dict[str, List[Dict[str, Any]]] = {
        "gpt4_2655b836": [
            {"id": "gps-system", "label": "GPS system", "allOf": ["GPS system"]},
            {"id": "not-functioning", "label": "Not functioning", "allOf": ["not functioning"]},
        ],
        "0a995998": [
            {"id": "item-count", "label": "Item count", "allOf": ["3"]},
        ],
        "6a1eabeb": [
            {"id": "five-k-time", "label": "5K time", "anyOf": ["25 minutes and 50 seconds", "25:50"]},
        ],
        "7161e7e2": [
            {"id": "admon", "label": "Admon", "allOf": ["Admon"]},
            {
                "id": "sunday-shift",
                "label": "Sunday day shift",
                "anyOf": ["8 am - 4 pm", "8:00 AM-4:00 PM", "8:00 AM–4:00 PM", "Day Shift"],
            },
            {"id": "sunday", "label": "Sunday", "allOf": ["Sunday"]},
        ],
        "e47becba": [
            {"id": "degree", "label": "Degree", "allOf": ["Business Administration"]},
        ],
    }
    if question_id in aliases:
        return aliases[question_id]
    return [{"id": "gold-answer", "label": "Gold answer", "allOf": [answer]}]


def load_cases(source_path: Path, case_count: int) -> List[Dict[str, Any]]:
    records = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"Expected a list in {source_path}")
    selected: List[Dict[str, Any]] = []
    seen_types: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        question_type = str(record.get("question_type") or "").strip()
        answer = str(record.get("answer") or "").strip()
        question = str(record.get("question") or "").strip()
        sessions = record.get("haystack_sessions")
        if not question_type or not question or not answer or not isinstance(sessions, list):
            continue
        if question_type in seen_types:
            continue
        if len(answer) > 120:
            continue
        selected.append(record)
        seen_types.add(question_type)
        if len(selected) >= case_count:
            break
    if len(selected) < case_count:
        raise ValueError(f"Only selected {len(selected)} cases; requested {case_count}")
    return selected


def build_suite(records: List[Dict[str, Any]], suite_id: str, bank_id: str) -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []
    for record in records:
        question_id = str(record["question_id"]).strip()
        answer = str(record["answer"]).strip()
        question_type = str(record["question_type"]).strip()
        case_id = f"lme-{sanitize_id(question_type)}-{sanitize_id(question_id)}"
        cases.append(
            {
                "caseId": case_id,
                "title": f"LongMemEval oracle pilot | {question_type}",
                "objective": (
                    "Answer this LongMemEval memory question using only retained memory. "
                    "If the relevant memory is not available, say memory unavailable. "
                    f"Question: {record['question']}"
                ),
                "constraints": [
                    "Use retained LongMemEval memory as the only answer source.",
                    "Answer briefly and do not invent details when memory is absent.",
                    "Do not mention internal benchmark metadata, case ids, or hidden gold guidance.",
                ],
                "sessionContext": (
                    "This is a LongMemEval oracle pilot case. The user question is intentionally separated "
                    "from the evidence memories so prompt-only Direct does not receive answer-time context."
                ),
                "checks": {
                    "requireLive": True,
                    "requiredConceptGroups": answer_concept_groups(record),
                    "forbiddenPhrases": ["memory unavailable", "ledger unavailable"],
                    "maxParagraphs": 3,
                },
                "gold": {
                    "source": "LongMemEval oracle",
                    "questionId": question_id,
                    "questionType": question_type,
                    "questionDate": str(record.get("question_date") or ""),
                    "answer": answer,
                    "answerSessionIds": record.get("answer_session_ids") or [],
                    "knowledgeBank": bank_id,
                },
            }
        )
    return {
        "suiteId": suite_id,
        "title": "LongMemEval Oracle Pilot",
        "description": (
            "Small external memory-quality pilot adapted from LongMemEval oracle. "
            "Evidence sessions are placed in ParaLLM memory; prompt-only Direct receives no answer-time memory."
        ),
        "judgeRubric": {
            "qualifier": "External Long-Term Memory Retrieval",
            "candidateStandard": (
                "Judge whether the answer retrieves the expected LongMemEval fact from retained memory. "
                "The gold answer is authoritative for this pilot."
            ),
            "mustDo": [
                "Reward answers that include the gold answer by meaning, with concise wording.",
                "Reward calibrated refusal only when answer-time memory was intentionally unavailable.",
                "Penalize answers that infer from general knowledge instead of retrieved memory.",
                "Penalize invented names, dates, preferences, or events.",
            ],
            "hardFailRules": [
                "If the answer contradicts the gold answer, it fails.",
                "If the answer guesses when memory was unavailable, it fails the safety bar.",
                "If the answer exposes hidden benchmark metadata instead of answering naturally, it fails.",
            ],
            "categories": {
                "memoryRecall": "Did the answer retrieve the correct stored fact?",
                "grounding": "Did it avoid unsupported inference?",
                "brevity": "Was it concise enough for a memory QA response?",
                "uncertaintyHandling": "Did it refuse cleanly when memory was unavailable?",
                "overall": "Would this pass a LongMemEval-style memory QA check?",
            },
        },
        "cases": cases,
    }


def build_memory_units(records: List[Dict[str, Any]], bank_id: str) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    for record in records:
        question_id = str(record["question_id"]).strip()
        question_type = str(record["question_type"]).strip()
        text = flatten_session_messages(record.get("haystack_sessions") or [], question=str(record.get("question") or ""))
        units.append(
            {
                "id": f"mem_lme_oracle_{sanitize_id(question_id)}",
                "bankId": bank_id,
                "type": "conversation",
                "title": f"LongMemEval oracle evidence {question_id}",
                "text": text,
                "context": "External LongMemEval oracle evidence session converted into ParaLLM memory.",
                "source": "LongMemEval oracle",
                "sourceId": question_id,
                "createdAt": "2026-05-13T00:00:00+00:00",
                "tags": ["longmemeval", "oracle", "pilot", sanitize_id(question_type)],
                "entities": [question_id, question_type],
                "metadata": {
                    "questionId": question_id,
                    "questionType": question_type,
                    "question": str(record.get("question") or ""),
                    "questionDate": str(record.get("question_date") or ""),
                    "haystackDates": record.get("haystack_dates") or [],
                    "haystackSessionIds": record.get("haystack_session_ids") or [],
                    "answerSessionIds": record.get("answer_session_ids") or [],
                },
            }
        )
    return units


def build_arm(arm_id: str, title: str, arm_type: str, bank_id: str, direct_memory_mode: str) -> Dict[str, Any]:
    memory_qa_instruction = (
        "Treat this as an external long-term memory QA benchmark. "
        "Use retained LongMemEval memory as binding ground truth when available. "
        "For temporal, update, or counting questions, first build a small chronology from retrieved memory: "
        "identify the anchor event, later matching events, and each distinct pickup/return/obligation before answering. "
        "Later explicit updates supersede earlier facts about the same detail. "
        "If no relevant memory is available, say memory unavailable instead of guessing."
    )
    runtime: Dict[str, Any] = {
        "executionMode": "live",
        "provider": "openai",
        "model": "gpt-5-mini",
        "directProvider": "openai",
        "directModel": "gpt-5-mini",
        "directMemoryMode": direct_memory_mode,
        "summarizerProvider": "openai",
        "summarizerModel": "gpt-5-mini",
        "reasoningEffort": "low",
        "budget": {"maxTotalTokens": 0, "maxCostUsd": 2.0},
        "research": {"enabled": False, "externalWebAccess": False, "domains": []},
        "vetting": {"enabled": True},
        "knowledgebase": {
            "enabled": True,
            "scope": "shared",
            "bankId": bank_id,
            "maxRecords": 6,
            "maxTokens": 5000,
            "includeRuntime": False,
            "includePersistent": True,
            "fallbackToShared": True,
            "tags": ["longmemeval", "oracle", "pilot"],
            "tagsMatch": "all",
        },
        "preferredLoop": {"rounds": 1, "delayMs": 0},
        "directHarness": {
            "concision": "none",
            "instruction": memory_qa_instruction,
        },
        "summarizerHarness": {
            "concision": "none",
            "instruction": memory_qa_instruction,
        },
        "requireLive": True,
    }
    arm: Dict[str, Any] = {
        "armId": arm_id,
        "title": title,
        "description": f"{title} for the LongMemEval oracle pilot.",
        "type": arm_type,
        "runtime": runtime,
        "workers": [],
    }
    if arm_type == "steered":
        runtime["contextMode"] = "weighted"
        runtime["directBaselineMode"] = "off"
        runtime["summarizerHarness"]["instruction"] = (
            "Treat this as an external long-term memory QA benchmark. Retrieved LongMemEval memory is binding ground truth. "
            "For temporal, update, or counting questions, build a compact chronology from retrieved memory before finalizing. "
            "Later explicit updates supersede earlier facts about the same detail; count each distinct pickup/return/obligation. "
            "Return a brief natural answer, reject unsupported guesses, and do not expose internal benchmark metadata."
        )
        arm["workers"] = [
            {
                "id": "A",
                "type": "sceptic",
                "label": "Memory verifier",
                "role": "verify that the answer is supported by retained LongMemEval evidence",
                "focus": "find missing, invented, or over-specific details",
                "temperature": "balanced",
                "model": "gpt-5-mini",
            },
            {
                "id": "B",
                "type": "sceptic",
                "label": "Gold-distance auditor",
                "role": "pressure-test whether the answer matches the expected memory fact by meaning",
                "focus": "reject guesses and unrelated details that do not come from memory",
                "temperature": "balanced",
                "model": "gpt-5-mini",
            },
        ]
    return arm


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ParaLLM LongMemEval oracle pilot manifests.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--case-count", type=int, default=DEFAULT_CASE_COUNT)
    args = parser.parse_args()

    records = load_cases(args.source, args.case_count)
    suffix = str(args.case_count)
    bank_id = f"longmemeval-oracle-pilot-{suffix}"
    suite_id = f"longmemeval-oracle-pilot-{suffix}"
    suite = build_suite(records, suite_id, bank_id)
    units = build_memory_units(records, bank_id)

    write_json(PROJECT_ROOT / "data" / "evals" / "suites" / f"{suite_id}.json", suite)
    bank_path = PROJECT_ROOT / "data" / "knowledgebase" / "banks" / bank_id / "memory_units.jsonl"
    bank_path.parent.mkdir(parents=True, exist_ok=True)
    bank_path.write_text("\n".join(json.dumps(unit, ensure_ascii=False) for unit in units) + "\n", encoding="utf-8")

    arms = [
        build_arm(
            f"direct-openai-mini-{suite_id}-pure",
            "Pure Direct OpenAI Mini | LongMemEval Oracle Pilot",
            "direct",
            bank_id,
            "off",
        ),
        build_arm(
            f"direct-openai-mini-{suite_id}-memory",
            "Direct OpenAI Mini | LongMemEval Oracle Memory",
            "direct",
            bank_id,
            "knowledgebase",
        ),
        build_arm(
            f"para-openai-mini-{suite_id}-double",
            "ParaLLM OpenAI Mini | LongMemEval Oracle | Two Adversarials",
            "steered",
            bank_id,
            "knowledgebase",
        ),
    ]
    for arm in arms:
        write_json(PROJECT_ROOT / "data" / "evals" / "arms" / f"{arm['armId']}.json", arm)

    print(json.dumps({"suiteId": suite_id, "bankId": bank_id, "caseCount": len(records), "armIds": [arm["armId"] for arm in arms]}, indent=2))


if __name__ == "__main__":
    main()
