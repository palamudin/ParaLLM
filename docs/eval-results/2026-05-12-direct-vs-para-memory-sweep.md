# 2026-05-12 Direct vs Para Memory-Aware MSP Sweep

This run compares single-thread direct answers against ParaLLM's pressurized multi-lane path on five hard MSP severity-1 scenarios. It is intended as an internal evaluation snapshot for product and architecture review, not third-party certification.

## Executive Summary

| Architecture | Completed cells | Quality mean | Health mean | Control mean | Readout |
| --- | ---: | ---: | ---: | ---: | --- |
| Direct single-thread baseline | `15 / 15` | `8.49` | `8.64` | `n/a` | Strong direct performance, especially OpenAI and xAI, but weaker Anthropic direct results on RMM and identity cases reduced the aggregate. |
| ParaLLM multi-lane orchestration | `15 / 15` | `8.92` | `9.11` | `7.80` | Higher overall aggregate with a separate control-discipline score that direct baselines do not expose. |

Measured delta on the completed sweep: ParaLLM is `+0.43` on quality and `+0.47` on answer health versus direct single-thread baselines. Control is Para-only because it grades internal orchestration discipline.

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
| Memory-compliance fields captured | Para `45 / 45`; Direct `30 / 30` |
| Exposed thinking fields returned | `0` |
| Failed-call artifacts after sweep | `0` |

The initial direct xAI CSP/OAuth cell hit a provider `max_output_tokens` completion error after retry attempts `[1600, 3200, 6400]`. It was rerun as a disclosed supplemental one-cell run with a concise direct-answer contract and included in the final direct aggregate.

## Scoring Method

- `Quality` averages the judge's rubric fields for factual correctness, sequencing, actionability, safety, and operational judgment.
- `Health` averages user-facing answer integrity fields such as coherence, readability, completeness, and calibration.
- `Control` is Para-only and grades whether the internal lane process preserved memory obligations, evidence gates, tenant boundaries, and unsafe-shortcut rejection.
- Memory is treated as binding operational ground truth when relevant. The judge grades memory compliance by operational meaning, not exact wording.
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

## Corporate Readout

The current evidence supports ParaLLM as an inspectable orchestration layer, not merely a UI wrapper around model calls. The main signal is not that every Para answer beats every direct model. It is that Para produces comparable or better aggregate answers while also exposing a control score, judge memory-compliance audit, and traceable lane artifacts that direct single-thread answers do not naturally provide.

The next evaluation target is tightening Para's final merge gate so memory obligations become mandatory output material whenever relevant memory is retrieved. That should focus on the lower-control cousin cases before expanding the benchmark suite beyond MSP scenarios.

