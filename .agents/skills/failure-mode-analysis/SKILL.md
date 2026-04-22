---
name: failure-mode-analysis
description: Surface concrete failure modes and fragile assumptions. Use for sceptic or adversarial review when the agent should pressure-test a proposal instead of providing broad negativity.
metadata:
  short-description: Find concrete failure modes
---

# Failure Mode Analysis

Use this skill for the `Sceptic` lane or any adversarial review focused on what could break.

## Goal

Pressure-test the proposal with concrete failure paths that would change the decision.

## Workflow

1. Identify the top ways this could fail in practice.
2. For each one, estimate:
   - severity
   - likelihood
   - detectability
   - reversibility
3. Separate loud failures from silent failures.
4. Highlight chain reactions and hidden coupling.
5. Name the mitigation that most changes the risk picture.

## Rules

- Avoid generic doom language.
- Focus on failure modes that are plausible in the current architecture.
- Prefer a few sharp risks over a long laundry list.
- A risk that is hard to detect deserves extra weight.

## Output Additions

- Include 1 to 4 failure modes.
- For each one, state why it matters now instead of later.
