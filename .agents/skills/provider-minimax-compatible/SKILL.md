---
name: provider-minimax-compatible
description: Use when an advisor is running on MiniMax through the compatibility path in this repo. Preserves tool-turn continuity and avoids unsupported assumptions.
metadata:
  short-description: MiniMax compatibility guidance
---

# MiniMax Compatibility

Use this skill when the active provider is `minimax`.

## Goal

Stay inside the repo's compatibility contract so MiniMax remains reliable even when some vendor-specific parameters are ignored.

## Rules

- Keep prompts plain and tool requests explicit.
- Preserve the full assistant tool-turn context conceptually; interleaved reasoning continuity matters on this provider family.
- Use only text and tool-call assumptions in this runtime. Do not assume image or document input support.
- Do not rely on OpenAI Responses-only fields or Anthropic-only betas unless the runtime explicitly adds them.
- Treat unsupported live research as unavailable unless the runtime explicitly provides it.
- End with strict schema-valid JSON text when structured output is required.

## What This Runtime Assumes

- This repo uses MiniMax through a compatibility surface rather than a custom native SDK path.
- Tool calls are supported, but some third-party compatibility parameters may be ignored.
- Stability is better when prompts are concrete, compact, and not overloaded with vendor-specific tricks.

## Output Additions

- Keep the answer compact and strongly typed.
- When a claim depends on missing external verification, mark the gap instead of faking certainty.
