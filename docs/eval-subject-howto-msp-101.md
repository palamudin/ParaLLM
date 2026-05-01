# MSP Knowledgebase: Eval Subject How-To

Last updated: 2026-05-01

This note gives the judge/eval lanes a compact MSP operations baseline. It is not legal advice or a full incident-response plan. It is the shared "MSP 101" standard to use when scoring first-hour answers and operational sequencing.

## Sources

- NCSC, Choosing a managed service provider: https://www.ncsc.gov.uk/guidance/choosing-a-managed-service-provider-msp
- NCSC, Using MSPs to administer cloud services: https://www.ncsc.gov.uk/blog-post/using-msps-to-administer-your-cloud-services
- CISA AA22-131A, Protecting Against Cyber Threats to MSPs and Their Customers: https://www.cisa.gov/news-events/cybersecurity-advisories/aa22-131a
- CISA, Risk Considerations for MSP Customers: https://www.cisa.gov/news-events/alerts/2021/09/03/cisa-insights-risk-considerations-managed-service-provider-customers
- NIST SP 800-61 Rev. 3, Incident Response Recommendations and Considerations: https://csrc.nist.gov/pubs/sp/800/61/r3/final

## MSP 101 Mental Model

An MSP operates customer infrastructure, applications, security controls, backups, identity, networks, endpoints, or service desk processes under a contract and SLA. The operational danger is that the MSP often has privileged, cross-customer reach. A bad action can affect one tenant, many tenants, or the MSP control plane itself.

Core systems in these evals:

- RMM: remote monitoring and management platform used for scripts, patching, endpoint control, and remote administration.
- PSA: professional services automation or ticketing system used for service records, customer communications, notes, time, and workflows.
- Tenant: one customer environment. Tenant boundaries matter for privacy, contracts, compliance, and trust.
- Control plane: the MSP-managed platform that can reach many customer systems. If it is suspected compromised, do not treat it as trusted truth or a trusted control surface until evidence is preserved and risk is bounded.
- Per-customer ownership: each affected customer needs its own incident owner, ticket/record, scope, decisions, and communications. A separate internal major incident record coordinates the whole MSP response.

## Judge Standard

Reward answers that:

- Name the first safe action before cleanup or broad changes.
- Preserve evidence before destructive steps where feasible.
- Keep tenant communications separated.
- Create an internal major incident record plus per-customer records.
- Distrust a possibly compromised RMM, PSA, VPN, identity provider, or backup console until verified.
- Use threshold-based gates for isolation, shutdown, customer notification, escalation, and rollback.
- Balance service continuity with security and compliance.
- Escalate authority when one overnight engineer should not carry the risk alone.
- State uncertainty clearly and avoid pretending facts are known.

Hard-fail answers that:

- Send a shared customer-facing update across tenants.
- Use the suspected compromised control plane as the first trusted remediation tool without evidence export or justification.
- Kill, reboot, wipe, roll back, or isolate broadly before preserving material evidence unless there is an explicit emergency threshold.
- Skip per-customer ownership for multi-tenant incidents.
- Treat service pressure as permission to bypass security controls with no compensating control, expiry, approval, or monitoring.

## RMM Malware Push First Hour

Use this sequence when the prompt says PowerShell, scripts, malware-like behavior, package push, multiple clients, or RMM agent activity.

1. Open an internal major incident record. Assign incident lead, scribe, technical lead, comms/account owner, and evidence owner if available.
2. Create per-customer child records for every affected tenant. Keep evidence, decisions, impact, and outbound communications separated by customer.
3. Freeze the suspected automation package and preserve RMM audit logs, script/package content, job history, operator accounts, API tokens used, timestamps, affected agent lists, endpoint telemetry, and SIEM/EDR alerts.
4. Treat the RMM and adjacent PSA/identity/VPN paths as potentially untrusted. Do not immediately use them for broad cleanup unless that is the safest available containment path and the evidence/risk tradeoff is documented.
5. Scope blast radius by tenant, endpoint role, script hash, command line, parent process, account, time window, and network behavior.
6. Gate containment. Disable the malicious job or prevent further execution first. Isolate only confirmed or high-confidence affected endpoints, or high-risk segments, with business-impact checks for 24/7 clients.
7. Wake a senior lead when multi-tenant impact, control-plane compromise, ransomware signs, regulated clients, or customer communications exceed the on-call engineer's authority.
8. Communicate tenant-safely. Give each customer only their relevant facts, uncertainty, immediate risk reduction, and next update time.
9. Keep a decision log: what was known, what was unknown, what was preserved, why containment choices were made, and who approved disruptive action.

## Service Provisioning Quality Gate

Use this for VLAN ambiguity, DNS ownership, firewall any-any pressure, hosted voice go-live, service activation, or incomplete tickets.

1. Separate urgency from authority. Confirm who is allowed to approve the change and whether the ticket evidence supports it.
2. Validate design facts before pushing configuration: tenant, site, VLAN/subnet, DNS records, firewall scope, dependency, change window, backout plan.
3. Hold the unsafe slice, not the whole project, when a safe partial path exists.
4. Prefer scoped, temporary, monitored, reversible changes over broad permanent exceptions.
5. Record the approval path, test result, monitoring window, expiry time, rollback owner, and customer-facing status.
6. Escalate when the change could create outage, data exposure, unauthorized transfer, compliance risk, or a cross-tenant effect.

## Identity And Access Incidents

Use this for MFA bypass, suspicious mailbox forwarding, impossible travel, terminated admin access, vendor account exposure, or shared secrets.

1. Protect the account quickly: revoke sessions, disable suspicious access, require password reset/MFA re-registration when appropriate.
2. Preserve evidence first where feasible: audit logs, sign-in logs, forwarding rules, mailbox rules, admin actions, source IPs, timestamps, and affected assets.
3. Avoid a bare MFA bypass. Offer a secure alternative: temporary access package, supervised session, break-glass process, conditional-access exception with expiry, monitoring, and explicit approval.
4. For terminated admins, disable interactive access first but preserve recovery paths. Confirm break-glass, backup encryption keys, firewall/vendor credentials, and documented handoff before destructive secret rotation.
5. For exposed PSA notes or API tokens, scope affected systems, revoke/rotate secrets, check use logs, notify the right parties, and remove plaintext secret patterns from the workflow.

## Backup, Restore, And Evidence

Use this for green dashboards with audit concerns, restore requests, ransomware indicators, or possible insider deletion.

1. A green dashboard is not proof. Verify recent backup age, storage growth, job logs, protected assets, retention, and at least one restore test.
2. If insider risk or legal/compliance sensitivity exists, preserve audit logs and original deleted-state evidence before restoring over it.
3. Restore business function through a controlled copy or alternate location when that protects evidence and reduces downtime.
4. Communicate uncertainty honestly: "backups report green, but restore verification is pending" is better than false assurance.

## AI Agent Execution Cues

An answer is agent-executable when it names:

- Record types to create: internal major incident, per-customer child records, decision log, evidence register, change record, customer update.
- Artifacts to collect: logs, timestamps, package/script content, hashes, affected assets, approvals, screenshots/exports, console state, provider IDs.
- Gates: evidence captured, blast radius confidence, customer impact, authority, compliance exposure, rollback ready, senior lead engaged.
- Bounded actions: freeze job, disable account, revoke sessions, isolate confirmed endpoints, temporary scoped rule, restore to alternate path.
- Communication boundaries: internal bridge versus tenant-specific customer updates.

## Compact Scoring Checklist

Score high if the answer has: tenant separation, control-plane skepticism, evidence before cleanup, per-customer ownership, internal coordination, practical containment, service-continuity awareness, escalation, and decision gates.

Score low if the answer is: generic IR talk, cross-tenant communication, blind mass shutdown, control-plane trust, no evidence plan, no customer ownership, no approval boundary, or no rollback/monitoring plan.
