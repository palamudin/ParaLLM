---
name: evidence-ledger
description: Build a compact evidence ledger for advisor work. Use when an agent should track supporting evidence, conflicting evidence, and key gaps instead of free-form argument alone.
metadata:
  short-description: Track support, conflict, and gaps
---

# Evidence Ledger

Use this skill when the answer should be shaped by concrete evidence instead of broad opinion.

## Goal

Keep a compact ledger of what supports the current position, what contradicts it, and what is still missing.

## Workflow

1. Extract only evidence that materially affects the decision.
2. Group it under:
   - support
   - conflict
   - gap
3. Prefer primary evidence:
   - inspected code
   - project docs
   - saved artifacts
   - approved sources
4. Note when the evidence is indirect or stale.
5. Keep the ledger short enough that another lane could absorb it quickly.

## Rules

- Do not include filler evidence that changes nothing.
- Preserve conflict instead of forcing a verdict too early.
- When two pieces of evidence disagree, state the tension plainly.
- If there is no real evidence, say so.

## Output Additions

- Include 1 to 5 evidence bullets.
- For each high-impact point, note whether it is support, conflict, or gap.
