---
name: rollback-plan
description: Evaluate whether a change can be reversed safely under pressure. Use for recovery-focused advisors when deployment, migration, or runtime changes need explicit rollback and restore thinking.
metadata:
  short-description: Pressure-test rollback and restore readiness
---

# Rollback Plan

Use this skill for the `Recovery` lane or whenever reversibility matters.

## Goal

Decide whether the proposal can be rolled back safely and what has to be true before taking the risk.

## Workflow

1. Identify what changes:
   - code
   - state
   - schema
   - configuration
   - external dependencies
2. Ask:
   - what can be rolled back cleanly
   - what cannot
   - what must be restored instead
3. Look for:
   - irreversible state mutation
   - missing checkpoints
   - partial rollback hazards
   - operator timing risk
   - hidden dependency on manual heroics
4. Define the trigger for rollback.
5. Name the cheapest rehearsal that would expose false confidence.

## Rules

- Do not assume backups equal recovery.
- Reversibility is weaker when state changes have already propagated.
- Weight manual emergency steps as risk, not as comfort.
- Escalate when rollback depends on undocumented tribal knowledge.

## Output Additions

- Include:
  - `Rollback Trigger`
  - `Irreversible Risk`
  - `Restore Requirement`
  - `Rehearsal To Run`
