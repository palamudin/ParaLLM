---
name: provider-xai-responses
description: Use when an advisor is running on xAI's OpenAI-compatible Responses API in this repo. Keeps Grok-specific reasoning and tool behavior aligned with the runtime contract.
metadata:
  short-description: xAI Responses API guidance
---

# xAI Responses

Use this skill when the active provider is `xai`.

## Goal

Use Grok's compatible Responses path cleanly without assuming every OpenAI-only field behaves the same.

## Rules

- Return strict schema-valid JSON in the final answer text.
- Use built-in web search when fresh information materially changes the recommendation.
- Handle custom function tools as normal request or pause points; the runtime will feed results back.
- Do not request or depend on exposed chain-of-thought.
- Treat citations and search evidence as real only if the provider actually returned them.
- Keep tool requests narrow and relevant; avoid speculative server-tool fan-out.

## What This Runtime Assumes

- Requests go to xAI's Responses-compatible endpoint.
- Structured outputs and tool calling can be combined.
- Most Grok reasoning models reason automatically; only multi-agent models treat `reasoning.effort` as agent-count selection.

## Output Additions

- Prefer direct evidence-backed fields over ornamental prose.
- If freshness matters and search was not used, say so through uncertainty fields instead of bluffing.
