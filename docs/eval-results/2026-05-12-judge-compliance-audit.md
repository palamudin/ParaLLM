# 2026-05-12 Judge Compliance Audit

This audit reviews the weak compliance rows from the memory-aware MSP sweep and separates answer failures from judge/rubric failures.

## Finding Summary

| Row | Classification | Root cause | Readout |
| --- | --- | --- | --- |
| Direct Anthropic, cross-tenant identity/OAuth | Bad answer, judge correct | The submitted answer was only a short SEV-1 label plus scenario restatement and `True`; it did not provide the requested first-hour plan. | This is a real direct-answer failure, not judge confusion. |
| Direct Anthropic, RMM replay | Bad/partial answer, judge mostly correct | The answer missed or under-specified external incident records, per-tenant records, RMM artifact export/hash, automation freeze, endpoint evidence, and vendor handoff. | This is an observable final-answer risk. |
| Para xAI, CSP/OAuth cousin | Partial final-answer miss plus generator/judge asymmetry | The judge enforced command/scribe relocation, unsafe automation freeze, senior wake, MFA/source-IP/device evidence, and rollback/re-enable gates. Some were present in baseline packets but not always present in the compact `memoryObligations` list used as the final gate. | The judge was directionally right, but the generator had weaker pressure than the judge. |
| Para xAI, backup immutability cousin | Good answer, weak control trace | Quality and health were high and memory mostly/fully compliant; control dropped because the self-audit was too cursory for governance reliance. | This is not primarily harmful advice; it is an audit-trace weakness. |
| Para Anthropic, CSP/OAuth cousin | Good answer, weak/inconsistent control trace | The public answer was strong and memory mostly compliant, but `controlAudit` contradicted itself: empty accepted/rejected arrays while the self-check described accepted worker contributions. | The judge correctly punished internal control discipline, not the visible answer. |

## Root Cause

The compliance signal had two separate problems:

1. **Real answer misses.** Some direct and Para answers omitted binding MSP actions or produced too little usable content.
2. **Contract asymmetry.** The judge could see full baseline SOP packet fields, while the generator's compact release checklist could omit some universal first actions due filtering and cap order. That allowed the judge to penalize requirements the final-answer gate did not force with equal pressure.

## Tightening Applied

- Expanded universal MSP memory obligations so command/scribe relocation, unsafe automation freeze, senior incident-lead wake, and rollback/monitoring gates enter the compact checklist earlier.
- Raised the compact `memoryObligations` cap from `24` to `32`.
- Raised contradiction-memory gate caps from `16` to `24`.
- Made the memory authority rule explicit: baseline packet `firstActions`, `decisionGates`, and `avoid` items are mandatory guardrails when relevant; `memoryObligations` is the compact release checklist.
- Tightened judge instructions so partial/failing memory-compliance judgments must name whether the missing binding requirement came from `memoryObligations` or a packet field.
- Increased `controlAudit.selfCheck` retention so memory-gate accounting is not truncated before the judge sees it.

## Current Judgment

The judge did not broadly misunderstand the task. The largest scoring discomfort came from Para exposing more evidence for the judge to inspect. Direct answers can only fail on final text. Para can fail on final text, memory integration, and internal control discipline. That is stricter, but it is also the governance feature.

