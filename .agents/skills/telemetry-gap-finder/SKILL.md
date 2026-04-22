---
name: telemetry-gap-finder
description: Find the observability gaps that would leave operators blind during failure, drift, or misuse. Use for observability and operator-focused advisors.
metadata:
  short-description: Find missing signals, alerts, and audit gaps
---

# Telemetry Gap Finder

Use this skill for the `Observability` lane or when the question is "what would we fail to see?"

## Goal

Identify the missing signals, traces, alerts, and audit records that would make the system hard to operate safely.

## Workflow

1. Name the decisions operators need to make during failure or drift.
2. For each decision, ask:
   - what signal exists now
   - what signal is missing
   - how quickly we would notice a problem
3. Check:
   - tracing
   - metrics
   - logs
   - audit events
   - queue/job visibility
   - per-lane or per-step attribution
4. Highlight where the system could fail silently or ambiguously.
5. Suggest the smallest telemetry addition with the highest operator value.

## Rules

- Prefer operator blindness over dashboard beauty as the framing.
- Missing correlation between events often matters more than another metric.
- Escalate when recovery depends on logs that are absent, unactionable, or too noisy.
- Keep the advice implementation-shaped.

## Output Additions

- Include:
  - `Blind Spot`
  - `Operational Consequence`
  - `Minimal Signal To Add`
  - `Alert Or Audit Need`
