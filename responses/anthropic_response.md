```json
{
  "incident": {
    "id": "INC-SEV1-AUTO-001",
    "declared_at": "T+00:00",
    "severity": "SEV-1",
    "title": "Suspected supply-chain / RMM-automation compromise — PowerShell spawning from RMM agent across 12 SMB tenants",
    "threat_hypothesis": "Malicious or trojanized automation package pushed via RMM control plane is executing arbitrary PowerShell on managed endpoints. Control plane itself must be treated as partially compromised until proven otherwise.",
    "wake_senior_lead": {
      "decision": "YES — wake now",
      "justification": "Multi-tenant blast radius, control-plane distrust, 24/7 client operations at risk, potential supply-chain event, compliance notifications may be required within hours. One engineer cannot safely manage evidence preservation, client communications, isolation decisions, and vendor escalation simultaneously.",
      "action": "Call senior lead via personal mobile. State: 'SEV-1, 12 tenants, RMM agent spawning PowerShell post-automation push, control plane suspected. I need you active now.'"
    }
  },
  "phases": [
    {
      "phase": 1,
      "name": "Immediate Triage and Control-Plane Freeze",
      "window": "T+00:00 to T+00:10",
      "goal": "Stop the bleeding — prevent further package execution while preserving forensic state.",
      "steps": [
        {
          "step": 1,
          "action": "FREEZE RMM automation pipeline immediately",
          "detail": "Log into the RMM console. Disable ALL scheduled and on-demand automation jobs globally. Do NOT delete the offending package — suspend/disable it and record the exact package name, version, hash, push timestamp, and the account that initiated the push. Screenshot every relevant UI pane before touching anything else.",
          "reasoning": "Every second the package remains active it can execute on additional endpoints or re-trigger on reconnecting agents. Deletion destroys evidence.",
          "evidence_preservation": "Screenshot RMM job queue, job history, package details, and the initiating admin account. Export logs immediately if the RMM supports log export — save to a timestamped folder outside the RMM platform."
        },
        {
          "step": 2,
          "action": "Revoke or rotate RMM API keys and automation service credentials",
          "detail": "If the RMM has API tokens or automation service accounts, invalidate them now. Generate new ones but do not re-enable automation. If SSO or an external credential is the trigger account, flag that account for review but do not delete it — disable login only.",
          "reasoning": "If the control plane is compromised, an attacker may be using stolen credentials to push further packages. Cutting API access limits lateral movement through the RMM."
        },
        {
          "step": 3,
          "action": "Open and lock the incident record",
          "detail": "Create a timestamped incident ticket with INC-SEV1-AUTO-001. Every action taken, every decision made, every piece of evidence collected goes into this ticket in chronological order. This serves legal, compliance, and post-mortem purposes.",
          "reasoning": "Multi-tenant incidents with compliance implications (HIPAA, PCI, SOC 2 clients) require a defensible chain of custody."
        }
      ]
    },
    {
      "phase": 2,
      "name": "Rapid Scoping — Which Clients, Which Systems, What Executed",
      "window": "T+00:10 to T+00:25",
      "goal": "Establish blast radius per tenant, identify highest-risk systems, and determine what the PowerShell actually did.",
      "steps": [
        {
          "step": 4,
          "action": "Pull the affected endpoint list from the RMM",
          "detail": "Export the list of every endpoint that received the automation package. Cross-reference with the 12 reporting clients. Identify: (a) endpoints that EXECUTED the package vs. merely received it, (b) any endpoints in sensitive roles — DCs, file servers, payment systems, EHR hosts, backup servers.",
          "decision_gate": "If any DC, backup server, or compliance-sensitive system shows execution — escalate criticality. Those tenants move to the front of the isolation queue."
        },
        {
          "step": 5,
          "action": "Collect PowerShell execution artifacts from a sample of affected endpoints",
          "detail": "For 2–3 representative endpoints per affected client, collect without modifying: (a) PowerShell ScriptBlock logging (Event ID 4104), (b) Process creation events (Event ID 4688 or Sysmon Event ID 1), (c) WMI and scheduled task logs, (d) Network connection logs at time of execution, (e) The RMM agent process tree — specifically what the agent spawned. Use the RMM's built-in log pull or EDR telemetry — do NOT run ad-hoc scripts through the RMM at this time since the RMM is untrusted.",
          "reasoning": "You need to know if this is a benign misconfigured script, ransomware staging, credential dumping, or C2 beaconing. The PowerShell content determines every downstream decision.",
          "evidence_preservation": "Copy raw logs to an evidence folder with MD5/SHA-256 hashes recorded immediately."
        },
        {
          "step": 6,
          "action": "Classify each tenant by operational tolerance and risk profile",
          "detail": "Build a quick matrix: Tenant name | 24/7 operation (Y/N) | Sensitive data class | Systems affected | PowerShell executed (Y/N) | Isolation tolerance. This matrix drives all subsequent isolation decisions.",
          "output": "Triage matrix shared with senior lead the moment they join."
        }
      ]
    },
    {
      "phase": 3,
      "name": "Targeted Isolation — Risk-Stratified, Not Mass Shutdown",
      "window": "T+00:25 to T+00:45",
      "goal": "Contain confirmed or high-probability malicious activity without blindly destroying 24/7 operations.",
      "decision_framework": {
        "principle": "Isolation decisions are made per-tenant and per-system based on evidence, not fear. Mass power-off is reserved for confirmed active ransomware spread or confirmed credential exfiltration with no other containment option.",
        "tiers": [
          {
            "tier": "TIER 1 — ISOLATE IMMEDIATELY",
            "criteria": "PowerShell executed AND content is confirmed malicious (C2 callback, credential dump, encryption activity, lateral movement) OR DC/backup server affected AND content unknown",
            "action": "Network-isolate affected endpoints via EDR quarantine or firewall ACL block. Do NOT power off — preserve volatile memory state. Alert tenant contact immediately.",
            "24_7_exception": "If the isolated system is business-critical for a 24/7 client, contact their on-call lead before isolation and give a 5-minute window unless active encryption is occurring — then isolate without waiting."
          },
          {
            "tier": "TIER 2 — MONITOR AND PREPARE",
            "criteria": "PowerShell executed but content appears benign or is unconfirmed, OR package was received but execution not confirmed",
            "action": "Enable enhanced EDR logging on these endpoints. Block outbound connections to any new external IPs seen in logs. Do not isolate yet. Prepare isolation runbook in case analysis escalates.",
            "reasoning": "Premature isolation of 24/7 systems without evidence of harm causes guaranteed business damage vs. probabilistic risk."
          },
          {
            "tier": "TIER 3 — WATCH ONLY",
            "criteria": "Package pushed to endpoint but no execution evidence, endpoint is non-sensitive",
            "action": "Log, monitor, no immediate action beyond RMM freeze already in place."
          }
        ]
      }
    },
    {
      "phase": 4,
      "name": "Evidence Preservation — Formal Collection",
      "window": "T+00:25 to T+00:55 (parallel with isolation)",
      "goal": "Ensure forensic integrity for potential legal, regulatory, and insurance purposes.",
      "steps": [
        {
          "step": 7,
          "action": "Memory acquisition on highest-risk isolated endpoints",
          "detail": "If you have a memory acquisition tool (WinPMEM, Magnet RAM Capture, EDR live memory pull), run it on Tier 1 isolated endpoints before any reboot. RAM may contain decrypted payloads, injected code, or C2 keys.",
          "reasoning": "Rebooting an infected endpoint without RAM capture permanently destroys volatile evidence."
        },
        {
          "step": 8,
          "action": "Preserve RMM platform logs at the vendor level",
          "detail": "Contact the RMM vendor's emergency/security line now. Request that they: (a) preserve all audit logs for the last 72 hours for your MSP account, (b) provide the full delivery log for the offending package, (c) confirm whether any other MSPs received the same package if it came from a vendor library. Log the case number in the incident record.",
          "reasoning": "If this is a supply-chain compromise at the RMM vendor level, their logs are the primary evidence source and they may overwrite on a rolling cycle."
        },
        {
          "step": 9,
          "action": "Hash and sequester the automation package",
          "detail": "Export the package files (scripts, binaries, config). Compute SHA-256. Submit hash to VirusTotal and your threat intel platform. Store a copy in an air-gapped or read-only evidence store. Do NOT execute or open on a production system.",
          "decision_gate": "If VirusTotal or threat intel returns a hit on the hash — this is confirmed malicious. Escalate all Tier 2 systems to Tier 1 immediately and consider notifying cyber insurance carrier."
        }
      ]
    },
    {
      "phase": 5,
      "name": "Client Communication — Safe, Accurate, Bounded",
      "window": "T+00:30 to T+01:00",
      "goal": "Notify affected clients honestly without overstating or understating the situation, and without creating legal liability through speculative statements.",
      "communication_safety_rules": [
        "Do NOT say 'you have been breached' unless exfiltration or confirmed malicious payload execution is evidenced.",
        "Do NOT name other affected tenants — each client communication is tenant-scoped only.",
        "Do NOT communicate via the RMM's built-in messaging if the RMM is untrusted — use email or phone.",
        "All client-facing statements are factual and bounded: what you know, what you are doing, what you do not yet know.",
        "Do NOT speculate on attacker identity or motive in client communications."
      ],
      "message_template": {
        "subject": "MSP Security Notification — Active Investigation on Managed Endpoints",
        "body": "We have identified anomalous activity involving our remote management tooling that may have affected systems we manage for your organization. We have immediately suspended all automation activity and are actively investigating. As a precaution, [specific systems if known] have been [isolated / placed under enhanced monitoring]. We are working to determine the nature and scope of this activity. We will provide an update within [60 minutes / 2 hours]. If you observe any unusual system behavior, please contact us immediately at [emergency line]. Please do not reboot or power off affected systems unless directed by our team. We will notify you immediately if any action is required on your end.",
        "recipients": "Primary technical contact and executive sponsor per tenant — sent individually, not as a group."
      },
      "24_7_client_protocol": "Call the 24/7 client's on-call number in addition to email. Do not leave a voicemail as the only notification."
    },
    {
      "phase": 6,
      "name": "Internal Escalation and Vendor Coordination",
      "window": "T+00:00 to T+01:00 (continuous)",
      "steps": [
        {
          "step": 10,
          "action": "Brief senior lead on join",
          "detail": "Hand off: triage matrix, RMM freeze status, evidence collected, isolation actions taken, client communications sent. Senior lead takes ownership of client executive communications and vendor escalation. You continue technical evidence collection and monitoring."
        },
        {
          "step": 11,
          "action": "Escalate to RMM vendor security team",
          "detail": "Escalate beyond standard support. State: SEV-1, suspected malicious automation package, multi-tenant impact, request: (a) incident case number, (b) confirmation of whether the package originated from their content library or an external upload, (c) whether other MSP customers are affected, (d) log preservation confirmation."
        },
        {
          "step": 12,
          "action": "Check for known CVE or threat intel on RMM platform",
          "detail": "Query your threat intel feeds, CISA KEV catalog, and RMM vendor's security advisories for any recent vulnerabilities or supply-chain alerts matching your RMM product and version. Cross-reference package push account for signs of account compromise (MFA bypass, unusual login location/time)."
        }
      ]
    }
  ],
  "decision_gates_summary": [
    {
      "gate": "G1",
      "trigger": "PowerShell content confirmed malicious",
      "action": "All Tier 2 systems escalate to Tier 1. Notify cyber insurance. Prepare breach notification review."
    },
    {
      "gate": "G2",
      "trigger": "DC or backup server confirmed affected with unknown or malicious payload",
      "action": "Immediate network isolation regardless of 24/7 status. Senior lead contacts tenant executive directly."
    },
    {
      "gate": "G3",
      "trigger": "RMM vendor confirms supply-chain compromise or other MSPs affected",
      "action": "Expand scope assumption to all tenants. Consider full RMM agent suspension across all clients. Prepare mass client notification."
    },
    {
      "gate": "G4",
      "trigger": "Evidence of active data exfiltration or ransomware encryption",
      "action": "Mass isolation of confirmed active systems authorized. Engage external IR firm. Notify affected tenants of potential breach immediately."
    },
    {
      "gate": "G5",
      "trigger": "PowerShell content confirmed benign (e.g., misconfigured legitimate script)",
      "action": "Step down to SEV-2. Maintain monitoring. Document root cause. Begin controlled remediation. No breach notification required — but document the determination with evidence."
    }
  ],
  "do_not_do": [
    "Do NOT delete the offending package from the RMM.",
    "Do NOT push any new automation via the RMM until the control plane is cleared.",
    "Do NOT reboot affected endpoints without RAM capture on Tier 1 systems.",
    "Do NOT communicate breach to clients until exfiltration or confirmed malicious execution is evidenced.",
    "Do NOT share one tenant's incident details with another tenant.",
    "Do NOT assume the RMM console admin account is clean — check its login history before using it further."
  ],
  "t_plus_60_checkpoint": {
    "expected_state": "RMM pipeline frozen, evidence collected from representative endpoints, triage matrix complete, Tier 1 systems isolated, all 12 clients notified, senior lead active, RMM vendor case open, payload nature known or actively being determined.",
    "if_payload_unknown_at_60_min": "Treat as malicious. Escalate all unknowns to Tier 1 posture. Do not wait for certainty before protecting clients.",
    "next_phase": "Root cause analysis, controlled remediation, regulatory notification assessment, post-incident review scheduling."
  }
}
```