---
name: provider-openai-responses
description: Use when an advisor is running on OpenAI's Responses API in this repo. Keeps tool use, web search, and strict JSON output aligned with the runtime contract.
metadata:
  short-description: OpenAI Responses API guidance
---

# OpenAI Responses

Use this skill when the active provider is `openai`.

## Goal

Exploit the repo's strongest live path without breaking schema or tool continuity.

## Rules

- Treat the response as strict structured output work: final text must match the requested JSON schema exactly.
- If repo tools are available, use them before making repository-specific claims.
- Keep tool requests concrete and minimal. Stable tool names and valid arguments matter more than flourish.
- Do not narrate tool plumbing in the final structured answer.
- Use web search only when it materially improves freshness or verification.
- Do not invent citations, URLs, or file evidence that was not actually surfaced during the run.

## What This Runtime Assumes

- `reasoning.effort` is available.
- Function tools and web search can both appear in the same run.
- The runtime will continue function calls for you using `function_call_output`.

## Output Additions

- Prefer concise, schema-valid strings over long explanatory prose.
- When evidence is weak, downgrade confidence inside the JSON fields rather than drifting out of schema.
