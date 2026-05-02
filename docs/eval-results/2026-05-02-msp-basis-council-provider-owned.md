# 2026-05-02 MSP Basis Council and Provider-Owned Sweep

This sweep tested the current MSP basis after baseline/adaptive recall, judge-learning persistence, and the named tenant-owner baseline update.

It answers a narrower question than "does Para always win?": is the current basis stable enough to move to the next reasoning-quality upgrade?

## Council Run

| Field | Value |
| --- | --- |
| Main run id | `judge-msp-basis-council-20260502-121129` |
| Suite | `msp-critical-council-hard` |
| Judge | `openai` / `gpt-5.4` |
| Arms | OpenAI, DeepSeek, Anthropic, xAI, MiniMax direct and Para pairs |
| Replicates | `1` per arm/case |
| Main-run variants | `30` |
| Main-run errors | `4` |
| Main-run tokens / estimated cost | `539,003` / `$1.524678` |
| Judge learning | enabled; event ledger grew to `571` during the main run and `586` after retries/fallbacks |

Retries recovered the transient network failures:

- DeepSeek identity Para retry completed but scored poorly: quality `2`.
- MiniMax identity Direct retry completed but scored poorly: quality `1`.
- MiniMax backup Para double still failed JSON review parsing; MiniMax single-lane fallback completed with quality `5`.
- MiniMax identity Para still failed JSON review parsing even after retry/fallback.

## OpenAI-Judged Council Means

Completed variants only, with successful retries/fallbacks included where available.

| Provider | Arm | Completed | Quality mean | Health mean | Control mean |
| --- | --- | ---: | ---: | ---: | ---: |
| OpenAI | Direct | `3` | `9.00` | `9.00` | `n/a` |
| OpenAI | Para | `3` | `9.00` | `9.33` | `9.00` |
| Anthropic | Direct | `3` | `9.33` | `8.00` | `n/a` |
| Anthropic | Para | `3` | `8.33` | `8.67` | `6.00` |
| DeepSeek | Direct | `3` | `8.00` | `9.00` | `n/a` |
| DeepSeek | Para | `3` | `3.00` | `5.67` | `4.00` |
| xAI | Direct | `3` | `8.33` | `8.33` | `n/a` |
| xAI | Para | `3` | `4.67` | `7.33` | `6.67` |
| MiniMax | Direct | `3` | `2.67` | `3.67` | `n/a` |
| MiniMax | Para | `2` | `3.00` | `5.00` | `5.50` |

## Provider-Owned Judging

Provider-owned judging reused completed answer artifacts instead of regenerating answers.

| Provider judge | Case coverage | Direct wins | Para wins | Notes |
| --- | ---: | ---: | ---: | --- |
| OpenAI | `3/3` | `2` | `1` | Para won RMM; Direct won backup and identity. |
| Anthropic | `3/3` | `2` | `1` | Para won RMM; Direct won backup and identity. |
| DeepSeek | `3/3` | `2` | `1` | Para won RMM; Direct decisively won backup and identity. |
| xAI | `3/3` | `2` | `1` | Para won RMM; Direct won backup and identity. |
| MiniMax | `2/3 usable pairs` | `0` | `1` | Backup Para fallback beat a broken Direct answer; RMM judge output produced zeroed scores and is not meaningful; identity lacked a completed Para. |

## Read

The infrastructure basis is good enough to proceed:

- baseline/adaptive memory recall is working across providers
- judge-learning is persisting misses without duplicating learned memory records
- OpenAI, Anthropic, DeepSeek, and xAI direct/Para generation paths completed most hard cases
- provider-owned scoring can reuse artifacts instead of regenerating expensive answers

The quality basis is not good enough for another expensive "prove Para wins" sweep yet:

- Same-provider judges preferred Direct in most backup and identity cases.
- Para still wins or competes best on RMM/control-plane style cases, where adversarial pressure helps catch trust and containment mistakes.
- DeepSeek and xAI Para paths underperformed despite acceptable Direct answers, which points to orchestration/merge fragility rather than raw provider incapability.
- MiniMax remains structurally unreliable in strict review/judge JSON stages.

## Decision

Do not run a larger proof sweep yet.

Implement cross-round contradiction memory and final merge gates first. The next scoring run should test whether Para can remember unresolved pressure across rounds and force the final answer to reconcile or explicitly reject contradictions before it reaches the user.

The concrete next upgrade is:

- store unresolved worker objections and rejected/held-out concerns as contradiction memories
- replay them into commander review and summarizer as "must resolve or explicitly reject"
- add final-answer gates for tenant ownership, evidence sequencing, control-plane distrust, continuity, customer-safe comms, and vendor/legal escalation
- score the same hard suite again after that change, keeping the current run as the basis reference

