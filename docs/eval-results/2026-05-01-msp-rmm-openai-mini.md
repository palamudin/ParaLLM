# 2026-05-01 MSP RMM OpenAI Mini Stability Runs

These runs compare Direct OpenAI mini against ParaLLM OpenAI mini with two adversarial lanes on the same MSP RMM PowerShell incident scenario.

Artifacts live locally under `data/evals/runs/`. That directory is intentionally ignored, so this file preserves the publishable score summary.

## Run Metadata

| Regime | Run id | Suite | Replicates | Errors | Tokens | Estimated cost |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Constrained | `judge-20260501-105629+0000-d6a1cc` | `msp-rmm-midnight-malware-push-critical-structured` | `5` | `0` | `153,102` | `$0.105828` |
| Unconstrained | `judge-20260501-111907+0000-d5db95` | `msp-rmm-midnight-malware-push-unconstrained` | `5` | `0` | `138,904` | `$0.088030` |

Generation used `openai` / `gpt-5-mini`. Judging used `openai` / `gpt-5.4`.

## Summary

| Regime | Arm | Deterministic | Quality mean | Quality sd | Quality min-max | Health mean | Control mean |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| Constrained | `direct-openai-mini-open` | `5/5` | `3.60` | `1.36` | `2-6` | `8.20` | `n/a` |
| Constrained | `para-openai-mini-critical-double--loops-1` | `5/5` | `7.20` | `1.72` | `4-9` | `8.80` | `7.20` |
| Unconstrained | `direct-openai-mini-unconstrained` | `5/5` | `2.00` | `0.00` | `2-2` | `8.40` | `n/a` |
| Unconstrained | `para-openai-mini-unconstrained-double--loops-1` | `5/5` | `6.60` | `1.36` | `4-8` | `8.20` | `6.40` |

## Replicate Quality Scores

| Regime | Direct | Para | Para delta |
| --- | --- | --- | --- |
| Constrained | `6, 3, 3, 4, 2` | `7, 8, 4, 8, 9` | `+1, +5, +1, +4, +7` |
| Unconstrained | `2, 2, 2, 2, 2` | `7, 7, 4, 7, 8` | `+5, +5, +2, +5, +6` |

## Read

Para won every replicate on quality in both regimes.

Direct stayed high on answer-health because it produced clear, readable answers, but quality judges repeatedly hard-failed it for MSP lead-level omissions: per-customer ownership, internal major-incident record, evidence-compatible decision log, and unsafe trust in the suspected control plane.

Para was not perfect. The recurring weak spot was control-plane sequencing: some Para outputs still allowed too much use of the suspected RMM console before preserving/exporting evidence. That is the next reliability target.
