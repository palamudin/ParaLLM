---
name: provider-ollama-local-json
description: Use when an advisor is running on Ollama in this repo. Keeps local generation schema-true without assuming hosted search or tool support.
metadata:
  short-description: Ollama local JSON guidance
---

# Ollama Local JSON

Use this skill when the active provider is `ollama`.

## Goal

Make local-model runs as reliable as possible under a text-plus-schema-only contract.

## Rules

- Return JSON only and match the requested schema exactly.
- Do not assume live web search, GitHub tools, or local file tools are available in this runtime.
- Keep answers compact, literal, and low-drift.
- Prefer shorter fields and cleaner wording over ambitious but fragile elaboration.
- If the task needs missing external evidence, say so in uncertainty or evidence-gap fields rather than inventing it.

## What This Runtime Assumes

- Calls go through Ollama's local chat API.
- Structured output relies on local schema prompting, not hosted tool orchestration.
- Reasoning text may exist, but the final answer still must stay schema-valid.

## Output Additions

- Favor deterministic wording.
- Avoid markdown wrappers, commentary, or explanatory preambles outside the JSON object.
