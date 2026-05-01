---
name: msp-provider-sop
description: Use when evaluating, drafting, or pressure-testing managed service provider (MSP/MSSP) operations, security incidents, RMM/PSA/cloud administration, tenant communications, evidence handling, backup/restore events, identity events, service changes, onboarding/offboarding, or eval/judge scenarios that need an MSP provider rulebook.
---

# MSP Provider SOP

Use this as the domain skill after `claim-calibration` and `evidence-ledger` when an advisor lane must reason about MSP provider operations.

## Quick Workflow

1. Classify the scenario: incident, change, access, backup/restore, customer communication, vendor/supply-chain, or service-quality dispute.
2. Identify the tenants, the control plane, the affected customer systems, and who has authority to approve risky action.
3. Separate facts, assumptions, and unknowns. Do not treat a management console as trusted truth when that console or its identity path may be compromised.
4. State the first safe action: preserve evidence, stop spread, keep service alive, or hold an unsafe change.
5. Define gates before disruptive action: evidence captured, impact assessed, customer-owner approval, senior authority, rollback ready, and tenant-safe comms.
6. Produce a compact pressure packet with verdict, confidence, top pressure, evidence, unknowns, and recommended next check.

## Provider Rules

- Tenant separation is sacred. Keep tickets, evidence, scope, decisions, and customer messages separated per customer, with one internal major-incident record above them.
- The MSP control plane is a blast-radius amplifier. RMM, PSA, backup portals, identity, remote access, and vendor integrations need skepticism when they are part of the incident path.
- Evidence comes before cleanup when feasible. Preserve logs, package/script contents, job history, command lines, identities, tokens, source IPs, timestamps, screenshots/exports, hashes, and chain-of-custody records.
- Least privilege beats convenience. Prefer named accounts, MFA, just-in-time access, just-enough access, privileged access workstations, and no shared cross-customer admin credentials.
- Communications must be tenant-specific. Never reveal other affected customers unless legal/customer authority explicitly allows it.
- Service continuity matters, but it does not erase security gates. Use scoped, reversible, monitored containment instead of broad shutdowns unless an emergency threshold is crossed.
- Every exception needs an owner, expiry, monitoring plan, rollback path, and after-action item.

## Read The Rulebook

Read `references/msp-provider-rulebook.md` when the scenario involves:

- RMM or remote access misuse.
- Backup deletion, restore reliability, or immutable storage concerns.
- Identity, OAuth, MFA, privileged access, or admin-session events.
- Multi-tenant customer impact or customer communications.
- Service provisioning, firewall/VLAN/DNS/voice changes, or unsafe go-live pressure.
- MSP contract/SLA/security responsibility boundaries.

## Output Shape

For internal advisor packets, use:

- `Verdict`: `support`, `caution`, `block`, or `investigate`.
- `Confidence`: `low`, `medium`, or `high`.
- `Top Pressure`: 1 to 3 course-changing points.
- `Evidence`: concrete facts from prompt, logs, artifacts, docs, or sources.
- `Unknowns`: what blocks confidence.
- `Recommended Next Check`: one verification step an operator or AI agent can perform next.

For user-facing operational answers, stay single-voice. Give a practical sequence, explicit gates, tenant boundaries, and the first executable action.
