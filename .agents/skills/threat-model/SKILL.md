---
name: threat-model
description: Review a proposal from the perspective of hostile actors, privilege boundaries, and exploit paths. Use for security-oriented advisors when the task requires practical threat modeling rather than generic security warnings.
metadata:
  short-description: Map attackers, boundaries, and exploit paths
---

# Threat Model

Use this skill for the `Security` lane or for any review that involves abuse, privilege, or sensitive data.

## Goal

Find the attack paths that most threaten the proposal's safety or trustworthiness.

## Workflow

1. Identify:
   - assets worth protecting
   - likely attackers
   - trust boundaries
   - entry points
2. Look for:
   - privilege escalation
   - secret exposure
   - prompt or tool abuse
   - unsafe default access
   - dangerous lateral movement
3. Estimate blast radius if the attack succeeds.
4. Name the cheapest fix that closes the most risk.
5. Distinguish true security risk from mere operational inconvenience.

## Rules

- Prefer concrete exploit paths over generic best practices.
- Weight default-on exposure heavily.
- If the system invites abuse by design, say so directly.
- Escalate when the risk affects secrets, identity, authorization, or destructive actions.

## Output Additions

- Include:
  - `Attack Path`
  - `Boundary`
  - `Blast Radius`
  - `Cheapest Strong Fix`
