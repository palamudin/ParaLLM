# 2026-05-12 Direct vs Para Memory-Aware MSP Sweep

This run compares memory-bound single-thread Direct answers against ParaLLM's pressurized multi-lane path on five hard MSP severity-1 scenarios. It is intended as an internal evaluation snapshot for product and architecture review, not third-party certification.

## Executive Summary

| Architecture | Completed cells | Quality mean | Health mean | Control mean | Readout |
| --- | ---: | ---: | ---: | ---: | --- |
| Direct memory-bound single-call baseline | `15 / 15` | `8.49` | `8.64` | `n/a` | Strong direct performance, especially OpenAI and xAI, but weaker Anthropic direct results on RMM and identity cases reduced the aggregate. |
| ParaLLM multi-lane orchestration | `15 / 15` | `8.92` | `9.11` | `7.80` | Higher overall aggregate with a separate control-discipline score that direct baselines do not expose. |

Measured delta on the completed sweep: ParaLLM is `+0.43` on quality and `+0.47` on answer health versus memory-bound direct single-call baselines. Control is Para-only because it grades internal orchestration discipline.

## Run Metadata

| Field | Value |
| --- | --- |
| Para run id | `judge-memory-five-20260511-181420+0000-2572d0` |
| Direct run id | `judge-direct-five-20260512-053302+0000-cadb55` |
| Supplemental direct cell | `judge-direct-xai-csp-supplement-20260512-064500+0000` |
| Scenario count | `5` |
| Provider families | xAI, OpenAI, Anthropic |
| Judge | OpenAI `gpt-5-mini` |
| Judge audits captured | Para `45 / 45`; Direct `30 / 30` |
| Memory-compliance fields captured | Para `45 / 45`; Direct `30 / 30`; coverage only, not a pass-rate claim |
| Exposed thinking fields returned | `0` |
| Failed-call artifacts after sweep | `0` |

The initial direct xAI CSP/OAuth cell hit a provider `max_output_tokens` completion error after retry attempts `[1600, 3200, 6400]`. It was rerun as a disclosed supplemental one-cell run with a concise direct-answer contract and included in the final direct aggregate.

## Payload Classification

This audit surfaced an important architecture distinction: the scored Direct rows are not raw model-only calls. They are a useful memory-bound single-call lane.

| Lane | Answer-generation memory | Judge memory | Arm ids / use | Product meaning |
| --- | --- | --- | --- | --- |
| ParaLLM multi-lane orchestration | Yes. Recall can be injected into commander, worker, review, and summarizer lanes. | Yes | Para eval arms | Full orchestration path with worker pressure, merge gates, traceable control behavior, and final-answer scoring. |
| Direct memory-bound single call | Yes. `directMemoryMode: knowledgebase` injects explicit recall into the single Direct answer prompt. | Yes | `direct-xai-fast-open`, `direct-openai-mini-open`, `direct-anthropic-sonnet-open` | Current Direct score table. This is the discovered cheap memory-backed single-call baseline. |
| Pure Direct prompt-only | No. `directMemoryMode: off` blocks answer-time recall even when the arm still carries a knowledgebase block for judge scoring. | Yes | `direct-xai-fast-pure`, `direct-openai-mini-pure`, `direct-anthropic-sonnet-pure` | New clean no-memory control for the next scoring run. |

## Scoring Method

- `Quality` averages the judge's rubric fields for factual correctness, sequencing, actionability, safety, and operational judgment.
- `Health` averages user-facing answer integrity fields such as coherence, readability, completeness, and calibration.
- `Control` is Para-only and grades whether the internal lane process preserved memory obligations, evidence gates, tenant boundaries, and unsafe-shortcut rejection.
- Memory is treated as binding operational ground truth when relevant. The judge grades memory compliance by operational meaning, not exact wording.
- Direct answers receive memory-compliance commentary inside the `Quality` and `Health` judges, but direct does not receive the Para-only `Control` audit because there are no internal worker/review/merge lanes to inspect.
- The scored Direct arms in this document were memory-bound single calls. New pure Direct arms are available for a future prompt-only baseline that removes answer-time recall while preserving judge-side memory audit.
- Several direct memory-compliance findings were partial or negative, including the direct Anthropic identity/OAuth answer being marked noncompliant on the quality judge. The aggregate direct score should therefore be read as user-facing answer quality, not as proof that direct passed all internal governance obligations.
- The five-case suite covers RMM supply-chain replay, backup console destruction, cross-tenant identity/OAuth abuse, backup immutability disablement, and CSP/OAuth admin-consent abuse.

## Provider-Level Result

| Provider family | Direct quality | Direct health | Para quality | Para health | Para control | Interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Anthropic | `7.07` | `6.93` | `9.20` | `9.17` | `7.68` | Para materially improved the weaker direct baseline on RMM and identity cases. |
| OpenAI | `9.30` | `9.50` | `9.03` | `9.23` | `8.32` | Direct was slightly higher on user-facing scores; Para added auditable control discipline. |
| xAI | `9.10` | `9.50` | `8.53` | `8.94` | `7.40` | Direct xAI was very strong; Para xAI needs tighter control/merge pressure on the cousin cases. |

## Scenario-Level Result

| Scenario | Direct quality | Direct health | Para quality | Para health | Para control | Readout |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| RMM supply-chain replay | `7.72` | `7.83` | `8.67` | `9.22` | `8.07` | Para improved aggregate incident handling where direct Anthropic underperformed. |
| Backup console destruction | `9.11` | `9.17` | `9.11` | `8.78` | `8.47` | Quality tied; direct health was slightly higher. |
| Cross-tenant identity/OAuth abuse | `7.22` | `7.56` | `8.94` | `9.39` | `8.67` | Para showed the clearest orchestration benefit. |
| Backup immutability disablement cousin | `9.28` | `9.33` | `9.11` | `9.22` | `7.27` | Direct was slightly higher; Para control needs stronger final-gate enforcement. |
| CSP/OAuth admin-consent cousin | `9.11` | `9.33` | `8.78` | `8.95` | `6.53` | Direct won user-facing scores; Para needs more pressure on internal control compliance. |

## Operational Scrutiny Table

This table is stricter than the average score table. It asks whether an engineer could safely act on the answer in a real MSP environment without creating an obvious compliance, evidence, tenant-boundary, or governance defect.

Classification rule:

- `Real-life pass`: high quality/health, no failing memory-compliance finding, and, for Para, control score at or above governance threshold.
- `Conditional pass`: usable direction, but a human incident lead should close the missing checklist items before acting.
- `Audit risk`: low score, failed memory compliance, or weak Para control trace. This is where a compliance officer could reasonably attach the company to a miss driven by assistant directions.

Summary:

| Path | Real-life pass | Conditional pass | Audit risk / likely damage | Notes |
| --- | ---: | ---: | ---: | --- |
| Direct memory-bound single-call baseline | `4 / 15` | `9 / 15` | `2 / 15` | Direct has no worker/review/merge audit. The direct risk class only catches final-answer defects. |
| ParaLLM multi-lane orchestration | `3 / 15` | `9 / 15` | `3 / 15` | Para is held to a stricter standard because internal control trace is visible and scored. |

Direct scrutiny:

| Scenario | Provider | Quality | Health | Memory compliance | Scrutiny | Observable business risk |
| --- | --- | ---: | ---: | --- | --- | --- |
| RMM supply-chain replay | xAI | `9.17` | `9.67` | pass / pass | Real-life pass | No major governance miss detected in the final answer. |
| RMM supply-chain replay | OpenAI | `9.33` | `9.33` | pass / pass | Real-life pass | No major governance miss detected in the final answer. |
| RMM supply-chain replay | Anthropic | `4.67` | `4.50` | partial / partial | Audit risk | Missing external incident records, per-tenant records, RMM artifact export/hash, automation freeze, endpoint evidence, and vendor handoff would be observable under review. |
| Backup console destruction | xAI | `9.00` | `9.17` | partial / partial | Conditional pass | Strong answer, but collection and chain-of-custody details need human closure. |
| Backup console destruction | OpenAI | `9.33` | `9.33` | partial / pass | Conditional pass | Strong answer with minor explicitness gaps. |
| Backup console destruction | Anthropic | `9.00` | `9.00` | partial / unclear | Conditional pass | Strong answer, but some evidence-storage/detail language is not clean enough for hands-off reliance. |
| Cross-tenant identity/OAuth abuse | xAI | `8.83` | `9.67` | partial / partial | Conditional pass | Good answer with missing explicit command/scribe isolation and unsafe-automation freeze wording. |
| Cross-tenant identity/OAuth abuse | OpenAI | `9.17` | `9.83` | partial / partial | Conditional pass | Strong answer, but senior wake/escalation and automation-freeze language needs closure. |
| Cross-tenant identity/OAuth abuse | Anthropic | `3.67` | `3.17` | fail / fail | Audit risk | Noncompliant on major incident records, per-tenant records, evidence exports/hashing, decision gates, and senior/legal escalation. |
| Backup immutability disablement cousin | xAI | `9.33` | `9.17` | pass / pass | Real-life pass | No major governance miss detected in the final answer. |
| Backup immutability disablement cousin | OpenAI | `9.50` | `9.50` | pass / pass | Real-life pass | No major governance miss detected in the final answer. |
| Backup immutability disablement cousin | Anthropic | `9.00` | `9.33` | partial / pass | Conditional pass | Strong answer, but named per-tenant ownership should be explicit. |
| CSP/OAuth admin-consent cousin | xAI | `9.17` | `9.83` | pass / partial | Conditional pass | Strong answer, but token/session volatility and automation-freeze language need closure. |
| CSP/OAuth admin-consent cousin | OpenAI | `9.17` | `9.50` | partial / pass | Conditional pass | Strong answer, but command/scribe isolation and automation-freeze wording need closure. |
| CSP/OAuth admin-consent cousin | Anthropic | `9.00` | `8.67` | pass / partial | Conditional pass | Strong answer, but critical-access preservation and first-hour checklist need human closure. |

Para scrutiny:

| Scenario | Provider | Quality | Health | Control | Memory compliance | Scrutiny | Observable business risk |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| RMM supply-chain replay | xAI | `8.00` | `9.00` | `8.00` | partial / partial / pass | Conditional pass | Good direction, but tenant-owner and operator/API-token explicitness should be closed before reliance. |
| RMM supply-chain replay | OpenAI | `8.83` | `9.33` | `7.60` | partial / pass / pass | Conditional pass | Strong answer, but package-freeze and vendor-handoff details should be more explicit. |
| RMM supply-chain replay | Anthropic | `9.17` | `9.33` | `8.60` | pass / pass / pass | Real-life pass | No major governance miss detected across final answer and control trace. |
| Backup console destruction | xAI | `9.00` | `8.67` | `7.80` | partial / partial / partial | Conditional pass | Strong answer, but command/scribe isolation and token custody details need closure. |
| Backup console destruction | OpenAI | `9.17` | `8.67` | `8.80` | partial / partial / pass | Conditional pass | Strong answer, but suspected-platform command/scribe and token custody wording need closure. |
| Backup console destruction | Anthropic | `9.17` | `9.00` | `8.80` | partial / pass / pass | Conditional pass | Strong answer, but storage-side immutability and named-owner timing need stronger explicitness. |
| Cross-tenant identity/OAuth abuse | xAI | `8.50` | `9.17` | `8.80` | partial / partial / pass | Conditional pass | Good answer, but command/scribe isolation, MFA evidence, rollback/re-enable planning, and escalation timing need closure. |
| Cross-tenant identity/OAuth abuse | OpenAI | `9.00` | `9.67` | `8.60` | partial / pass / partial | Conditional pass | Strong answer, but unsafe-automation freeze, named evidence owners, and write-once evidence storage should be explicit. |
| Cross-tenant identity/OAuth abuse | Anthropic | `9.33` | `9.33` | `8.60` | pass / partial / pass | Conditional pass | Strong answer, but vendor escalation/artifact handoff should be explicit. |
| Backup immutability disablement cousin | xAI | `9.00` | `9.17` | `4.60` | partial / pass / pass | Audit risk | Final answer reads well, but control trace is weak enough that a governance review should not treat it as hands-off safe. |
| Backup immutability disablement cousin | OpenAI | `9.17` | `9.33` | `8.80` | pass / pass / pass | Real-life pass | No major governance miss detected across final answer and control trace. |
| Backup immutability disablement cousin | Anthropic | `9.17` | `9.17` | `8.40` | pass / pass / pass | Real-life pass | No major governance miss detected across final answer and control trace. |
| CSP/OAuth admin-consent cousin | xAI | `8.17` | `8.67` | `7.80` | fail / partial / partial | Audit risk | Missing command/scribe isolation, immediate senior wake, unsafe-automation freeze, and chain-of-custody clarity creates a compliance latch point. |
| CSP/OAuth admin-consent cousin | OpenAI | `9.00` | `9.17` | `7.80` | partial / pass / pass | Conditional pass | Strong answer, but senior wake and vendor artifact handoff should be more explicit. |
| CSP/OAuth admin-consent cousin | Anthropic | `9.17` | `9.00` | `4.00` | partial / pass / partial | Audit risk | Final answer scored well, but internal control trace is weak enough to fail governance confidence. |

## Corporate Readout

The current evidence supports ParaLLM as an inspectable orchestration layer, not merely a UI wrapper around model calls. The main signal is not that every Para answer beats every direct model. It is that Para produces comparable or better aggregate answers while also exposing a control score, judge memory-compliance audit, and traceable lane artifacts that memory-bound direct single-thread answers do not naturally provide.

Follow-up audit: [2026-05-12 Judge Compliance Audit](2026-05-12-judge-compliance-audit.md)

For an MSP leadership pitch, the clean position is: ParaLLM is an SLT / service-manager incident-command assistant. It helps managers, escalation owners, and incident leads align the first hour of response, preserve tenant boundaries, keep evidence discipline visible, and review what the assistant did after the fact.

For broader product direction, the assistant surface is intentionally thin: a shell plus API call into ParaLLM, backed by memory, provider routing, tools, and scoring. MSP is the current validation domain because the scenarios are easy to audit against real operational expectations. The same pattern can be adapted to other documented domains once the memory bank, tool permissions, and evaluation rubric are swapped.

The next evaluation target is twofold: run the new pure Direct arms to establish a no-memory provider baseline, and tighten Para's final merge gate so memory obligations become mandatory output material whenever relevant memory is retrieved. That should focus on the lower-control cousin cases before expanding the benchmark suite beyond MSP scenarios.

Do not overclaim this as autonomous remediation or third-party-certified benchmark evidence yet. The defensible commercial language is auditable operational decision support with measurable internal scoring and traceable control behavior.
