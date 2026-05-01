# MSP Provider Rulebook

Use this reference for MSP/MSSP incident, change, access, backup, and tenant-communication scenarios. It is a practical rulebook, not legal advice.

## Source Spine

- CISA AA22-131A, Protecting Against Cyber Threats to Managed Service Providers and Their Customers: https://www.cisa.gov/news-events/cybersecurity-advisories/aa22-131a
- CISA Insights, Risk Considerations for Managed Service Provider Customers: https://www.cisa.gov/sites/default/files/publications/cisa-insights_risk-considerations-for-msp-customers_508.pdf
- NSA/CISA/MS-ISAC, Protecting Against Malicious Use of Remote Monitoring and Management Software: https://www.nsa.gov/Press-Room/Press-Releases-Statements/Press-Release-View/Article/3277084/nsa-cisa-and-ms-isac-release-guidance-for-securing-remote-monitoring-and-manage/
- NCSC, Choosing a managed service provider: https://www.ncsc.gov.uk/guidance/choosing-a-managed-service-provider-msp
- NCSC, Using MSPs to administer your cloud services: https://www.ncsc.gov.uk/blog-post/using-msps-to-administer-your-cloud-services
- NCSC, Secure system administration: https://www.ncsc.gov.uk/collection/secure-system-administration
- NCSC, Cloud security principle 12, Secure service administration: https://www.ncsc.gov.uk/collection/cloud/the-cloud-security-principles/principle-12-secure-service-administration
- NIST SP 800-61 Rev. 3, Incident Response Recommendations and Considerations: https://csrc.nist.gov/pubs/sp/800/61/r3/final

## Core Mental Model

An MSP does not just operate technology. It operates privileged trust relationships across customer environments. A small action in an MSP tool can become a multi-tenant incident if the action crosses customer boundaries, uses a shared control plane, or relies on an identity path that can reach many customers.

High-risk provider surfaces:

- RMM and remote support tools.
- PSA/ticketing/customer communication systems.
- Backup and disaster recovery portals.
- Identity providers, OAuth apps, API tokens, delegated admin, and break-glass accounts.
- Cloud admin consoles and tenant delegation relationships.
- Firewall, VPN, DNS, VLAN, voice, and hosted-service provisioning systems.
- Vendor plugins, automation packages, scripts, update channels, and marketplace integrations.

## Operating Invariants

1. Tenant separation is a hard boundary. Use one internal major incident record plus per-tenant child records.
2. Named accountability beats shared convenience. Avoid shared admin accounts, shared secrets, and generic customer-impacting actions.
3. A suspected control plane becomes evidence, not truth. Treat RMM, PSA, backup, cloud, or identity consoles as untrusted until corroborated if they are in the attack path.
4. Evidence before cleanup where feasible. Preserve state, exports, logs, hashes, command lines, task definitions, package contents, screenshots, and chain of custody before destructive changes.
5. Stop spread with the narrowest safe control. Freeze a job, package, token, session, route, or policy before broad isolation when that is enough to reduce harm.
6. Disruptive actions need gates. Require impact assessment, authority, customer-owner approval where applicable, rollback, and a documented emergency threshold.
7. Customer communications are tenant-specific. Do not disclose other affected customers, shared infrastructure details, or unconfirmed attribution.
8. Privileged access needs strong provenance. Require MFA, just-in-time access, just-enough access, privileged access workstations where appropriate, and audit trails tied to tickets.
9. Recovery is not proof. Backups, green dashboards, and vendor status pages must be verified with restore tests, independent logs, or out-of-band evidence.
10. Every exception expires. Temporary firewall rules, access grants, MFA bypasses, password resets, and service workarounds need owner, expiry, monitoring, and rollback.
11. Supply chain is part of the attack surface. Vendor plugins, subcontractors, update channels, and outsourced admin must be scoped and evidenced.
12. The final answer must be operator-executable: who does what, through which tool, under what gate, with what evidence captured.

## Provider Security Baseline

Minimum expected provider controls:

- Contractual responsibility matrix for hardening, monitoring, incident response, recovery, customer notifications, evidence access, and subcontractors.
- MFA on MSP accounts that access customer environments; phishing-resistant MFA for high-risk admin functions where possible.
- Least privilege and no credential reuse across customers.
- Prompt deprovisioning for departed staff, stale accounts, stale customer access, and unused infrastructure.
- Segregated customer data and services from each other and from internal MSP systems where possible.
- Central logging with customer-appropriate visibility, retention, alerting, and ability to audit MSP activity in customer environments.
- Endpoint and network monitoring appropriate to the contracted service.
- Timely patching, with known exploited vulnerabilities prioritized.
- Tested backups and recovery paths, including offline/isolated backups and protected encryption keys where applicable.
- Incident response and recovery plans exercised regularly, including hard-copy or offline access when networks are down.
- Vendor/subcontractor risk tracking, including plugins, marketplace integrations, and delegated service providers.

## Incident SOP

0. Declare the posture.

- Decide whether this is normal support, suspicious activity, security incident, major incident, or emergency.
- If multi-tenant, destructive, privileged, regulated, ransomware-like, or control-plane related, escalate early.

1. Establish command without leaking tenant data.

- Start an internal bridge and scribe log outside the suspect system if needed.
- Open an internal major incident record.
- Open per-tenant records for affected customers.
- Assign incident lead, technical lead, evidence owner, customer-success/comms owner, and vendor liaison where possible.

2. Preserve evidence.

- Capture current console state, audit logs, relevant system logs, package/script content, job queue, task definitions, endpoint process tree, command lines, network connections, identity/session logs, API token use, source IPs, timestamps, and customer approvals.
- Hash exports and store them in restricted/immutable evidence storage.
- Record collector, method, timestamp, source, and hash.

3. Bound trust in the control plane.

- If the suspected path is RMM, PSA, backup portal, identity, cloud admin, or vendor plugin, do not rely on that system alone for timeline, scope, or cleanup.
- Corroborate with endpoint, SIEM, EDR, firewall, IdP, cloud audit, backup storage, database/file-system, or vendor-side evidence.

4. Stop spread.

- Prefer narrow controls first: disable a task, freeze a plugin rollout, revoke a session, disable an OAuth app, block a known C2/domain, pause a destructive job, or prevent new execution.
- Avoid broad reboots, wipes, mass isolation, or console-led cleanup until evidence and impact gates are satisfied unless active harm demands emergency action.

5. Gate disruptive action.

- Required gates: evidence captured or emergency exception recorded, blast-radius confidence, business impact, customer-owner approval for high-impact tenants, senior authority, rollback path, and monitoring.
- Emergency threshold: destructive activity, active C2, credential theft, lateral movement, ransomware encryption, safety impact, or imminent unrecoverable data loss.

6. Communicate.

- Internal updates may include full cross-tenant scope.
- Customer updates include only that customer context, known facts, uncertainty, actions taken in their environment, requested approvals, and next update time.
- Avoid vendor attribution until evidence supports it or legal/compliance approves.

7. Recover and harden.

- Remove malicious jobs/packages only after preservation.
- Rotate/revoke credentials in a controlled order with break-glass and recovery keys verified.
- Restore from verified backups, ideally to alternate locations when evidence preservation matters.
- Update detections, least-privilege rules, allowlists, monitoring, and runbooks.

8. Close with learning.

- Keep an after-action: what happened, what evidence was preserved, what gates worked, what failed, customer impact, contractual gaps, detection gaps, and new controls.

## Scenario Rules

### RMM Or Remote Access Abuse

- Audit installed and authorized remote access tools.
- Prevent unauthorized RMM execution with application controls where possible.
- Use approved remote access paths only.
- Treat suspicious RMM actions as potentially privileged attacker activity.
- Freeze suspect automation before using the same RMM for broad remediation.
- Preserve scripts, packages, jobs, agent logs, operator accounts, API tokens, command lines, endpoint process data, and network evidence.

### Backup Portal Or Destructive Job

- A green vendor page or successful login is not proof of safety.
- Preserve portal session, job queue, API calls, audit logs, source IP, identity/session evidence, and backup-storage-side logs.
- Maintain active restores first.
- Pause or hold destructive jobs only after evidence capture unless waiting creates imminent unrecoverable loss.
- Verify immutability and restore paths from storage-side evidence, not only dashboard status.

### Identity, OAuth, Or Admin Session Incident

- Revoke active sessions and risky tokens when evidence and business impact are bounded.
- Preserve sign-in logs, OAuth grants, mailbox/forwarding rules, API-token use, admin changes, source IPs, device posture, and MFA events.
- Avoid unsupported MFA bypass. If access is needed, use supervised temporary access with expiry and monitoring.
- For departed or unreachable admins, disable interactive access while preserving break-glass, backup keys, firewall/vendor access, and documented handoff.

### Cloud Or Delegated Administration

- Do not give permanent root/global admin to the MSP unless explicitly accepted as a risk.
- Tie privileged access to named people, tickets, and logs.
- Use JIT/JEA, PAWs, scoped roles, and customer-visible audit logs where possible.
- Confirm subcontractors and delegated providers are covered by the contract and security clauses.

### Service Change Or Provisioning Pressure

- Validate the authority, ticket evidence, tenant, site, VLAN/subnet, DNS, firewall scope, dependency, change window, rollback, and monitoring before change.
- Hold only the unsafe slice when safe partial progress exists.
- Prefer temporary, scoped, monitored, reversible changes with explicit expiry.
- Block broad any-any rules, undocumented ownership transfers, irreversible DNS moves, or production-impacting changes without approval.

## AI/Judge Scoring Rubric

Score high when the answer:

- Preserves tenant boundaries.
- Distrusts compromised or suspect control planes.
- Captures evidence before destructive cleanup.
- Names owner/authority/approval gates.
- Separates internal major incident coordination from per-customer records.
- Gives bounded executable actions and rollback paths.
- Balances continuity with security.
- States uncertainty and next verification steps.

Score low when the answer:

- Uses a suspected management plane as trusted truth.
- Sends shared customer communications.
- Performs mass isolation, deletion, reboot, rollback, or wipe without gates.
- Skips evidence preservation.
- Skips per-customer ownership.
- Treats vendor status, green dashboards, or successful login as proof.
- Gives generic incident response without MSP-specific blast-radius handling.

## Agent Readout Template

Use this structure when the answer must be AI-friendly:

- `facts`: directly supported prompt/log/artifact facts.
- `assumptions`: plausible but unverified claims.
- `controlPlaneTrust`: trusted, suspect, compromised, or unknown; explain why.
- `tenantBoundary`: affected tenants, separate records, cross-tenant disclosure rule.
- `firstSafeAction`: one immediate action.
- `evidenceToPreserve`: concrete artifact list.
- `decisionGates`: gate, owner, evidence required, deadline.
- `actions`: bounded steps with owner/tool/fallback.
- `communications`: internal and per-tenant messages.
- `unknowns`: what blocks confidence.
- `nextCheck`: one verification step.
