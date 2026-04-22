---
name: claim-calibration
description: Separate facts, inferences, assumptions, and unknowns for advisor work. Use when an agent needs to avoid overclaiming, calibrate confidence, or make uncertainty explicit.
metadata:
  short-description: Calibrate claims and confidence
---

# Claim Calibration

Use this skill whenever the task involves review, judgment, recommendations, or risk statements.

## Goal

Make the reasoning auditable by separating what is known from what is merely plausible.

## Workflow

1. List the claims that matter most to the decision.
2. Tag each one as `fact`, `inference`, `assumption`, or `unknown`.
3. Lower confidence when the chain depends on multiple unverified assumptions.
4. Call out where evidence is absent, stale, or indirect.
5. Collapse the output to only the claims that could change the course decision.

## Rules

- Do not use confident language for unsupported claims.
- Do not hide uncertainty inside vague wording.
- If a claim is important and weakly supported, mark it as an `assumption` or `unknown`.
- Prefer one sharp uncertainty over a long hedge-filled paragraph.

## Output Additions

- Tag consequential claims inline.
- End with one sentence naming the biggest uncertainty still open.
