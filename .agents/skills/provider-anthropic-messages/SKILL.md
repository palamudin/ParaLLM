---
name: provider-anthropic-messages
description: Use when an advisor is running on Anthropic's native Messages API in this repo. Keeps tool_use and tool_result turns aligned with the runtime contract.
metadata:
  short-description: Anthropic Messages API guidance
---

# Anthropic Messages

Use this skill when the active provider is `anthropic`.

## Goal

Work cleanly inside Anthropic's Messages and tool block model while still producing the final schema-valid JSON text the runtime expects.

## Rules

- Think in message blocks, not chat-completions shortcuts.
- Client tools are expressed as `tool_use` and must be answered with `tool_result` content blocks.
- If server web search is available, let it ground fresh claims instead of pretending prior knowledge is current.
- Server tools may pause a turn. Keep the answer state coherent so continuation can finish the same reasoning thread.
- Do not assume OpenAI-specific include fields, response annotations, or function-call wrappers.
- Keep the final user-facing content block as valid JSON text when structured output is required.

## What This Runtime Assumes

- Tool definitions use `name`, `description`, and `input_schema`.
- The runtime may continue paused or tool-using turns by replaying the full assistant content blocks.
- `tool_choice` should stay conservative; avoid forcing exotic tool behavior.

## Output Additions

- Keep arguments exact and minimal for client tools.
- Preserve uncertainty explicitly rather than padding the answer with extra natural-language commentary outside the schema.
