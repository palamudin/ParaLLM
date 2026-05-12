# 2026-05-12 Pure Direct No-Memory MSP Sweep

This rerun isolates prompt-only Direct model output from the memory-bound Direct lane discovered in the prior sweep. The goal is to separate three signals:

- `ParaLLM`: multi-lane orchestration with memory available to the lane process.
- `Direct + fractal memory`: one Direct answer call with explicit knowledgebase recall injected into the answer prompt.
- `Pure Direct`: one Direct answer call with `directMemoryMode: off`; judge memory remains available only for scoring fairness.

## Run Metadata

| Field | Value |
| --- | --- |
| Pure Direct run id | `judge-direct-pure-five-20260512-130843+0000-7b4f37` |
| Compared Para run id | `judge-memory-five-20260511-181420+0000-2572d0` |
| Compared Direct + memory run id | `judge-direct-five-20260512-053302+0000-cadb55` plus `judge-direct-xai-csp-supplement-20260512-064500+0000` |
| Scenario count | `5` |
| Provider families | xAI, OpenAI, Anthropic |
| Pure Direct completed cells | `15 / 15` |
| Pure Direct eval errors | `0` |
| Pure Direct judge | OpenAI `gpt-5-mini` |
| Pure Direct judge reasoning | `low`, disclosed because high-effort structured judging overflowed on pure Direct answer-health / quality passes |
| Pure Direct answer memory | Off. Direct runtime calls show `directMemoryMode: off`; knowledgebase config exists in the arm for scoring context, not answer-time recall. |

## Three-Way Score

Scores below average the scored rubric dimensions, not only the `overallQuality` or `overallHealth` field.

| Architecture | Answer memory | Completed cells | Quality mean | Health mean | Control mean | Fail-resistance readout |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| ParaLLM multi-lane orchestration | Yes, across orchestration lanes | `15 / 15` | `8.92` | `9.11` | `7.80` | Best aggregate output and the only path with a separate control-discipline audit. |
| Direct + fractal memory | Yes, single-call recall injection | `15 / 15` | `8.49` | `8.64` | `n/a` | Cheap, useful memory-bound direct lane. It materially improves raw Direct, but has no internal process trace. |
| Pure Direct prompt-only | No answer-time recall | `15 / 15` | `8.01` | `7.86` | `n/a` | Usable in many rows, but weaker on MSP-specific obligations and not clean enough for hands-off operational reliance. |

Measured deltas:

| Comparison | Quality delta | Health delta | Readout |
| --- | ---: | ---: | --- |
| ParaLLM vs Direct + fractal memory | `+0.43` | `+0.47` | Para still leads after giving Direct the memory-bound single-call advantage. |
| ParaLLM vs Pure Direct | `+0.91` | `+1.26` | This is the cleaner architecture delta against raw prompt-only provider output. |
| Direct + fractal memory vs Pure Direct | `+0.48` | `+0.79` | Memory injection has visible value even before multi-lane orchestration. |

## Memory Integration

Memory-compliance counts are taken from judge text and classified as `pass`, `partial`, `fail`, or `unknown`.

| Architecture | Quality memory compliance | Health memory compliance | Control memory compliance | Readout |
| --- | --- | --- | --- | --- |
| ParaLLM | `7 pass / 8 partial / 0 fail` | `11 pass / 3 partial / 0 fail / 1 unknown` | `13 pass / 2 partial / 0 fail` | Memory is broadly present across final answer and internal control, with some explicitness gaps. |
| Direct + fractal memory | `10 pass / 3 partial / 0 fail / 2 unknown` | `9 pass / 3 partial / 0 fail / 3 unknown` | `n/a` | Single-call recall gives Direct a strong memory boost, but no worker/review/merge trace exists. |
| Pure Direct | `1 pass / 13 partial / 1 fail` | `2 pass / 12 partial / 1 fail` | `n/a` | Raw provider answers often gesture toward good MSP practice, but rarely satisfy the stored memory obligations cleanly. |

## Operational Scrutiny

This table asks whether an engineer could safely rely on the answer without creating an obvious compliance, evidence, tenant-boundary, or governance defect. It is stricter than the mean score.

| Architecture | Real-life pass | Conditional pass | Audit risk / likely damage | Practical meaning |
| --- | ---: | ---: | ---: | --- |
| ParaLLM multi-lane orchestration | `4 / 15` | `9 / 15` | `2 / 15` | Best governance shape because process risk is inspectable, but still needs stronger final memory enforcement on cousin cases. |
| Direct + fractal memory | `5 / 15` | `8 / 15` | `2 / 15` | Strong single-call text when memory is injected, but any process failure is invisible unless it leaks into the final answer. |
| Pure Direct prompt-only | `0 / 15` | `14 / 15` | `1 / 15` | Rarely catastrophic, but never reached clean hands-off pass criteria in this sweep. |

## Pure Direct Provider Result

| Provider family | Quality mean | Health mean | Memory readout |
| --- | ---: | ---: | --- |
| Anthropic | `7.67` | `7.33` | One hard failure on RMM; otherwise mostly partial memory compliance. |
| OpenAI | `8.67` | `8.53` | Strongest pure Direct provider in this rerun, but still mostly partial memory compliance. |
| xAI | `7.70` | `7.70` | Broadly usable but weaker on backup-console and RMM memory obligations. |

## Pure Direct Scenario Result

| Scenario | Pure Direct quality | Pure Direct health | Readout |
| --- | ---: | ---: | --- |
| RMM supply-chain replay | `6.72` | `6.28` | Weakest pure Direct scenario; Anthropic failed both quality and health memory compliance. |
| Backup console destruction | `8.06` | `7.94` | Usable but not complete enough on evidence and chain-of-custody expectations. |
| Cross-tenant identity/OAuth abuse | `8.61` | `8.28` | Reasonable raw guidance, but memory obligations remained partial across providers. |
| Backup immutability disablement cousin | `8.61` | `8.56` | Best pure Direct scenario; still mostly conditional except Anthropic's memory pass. |
| CSP/OAuth admin-consent cousin | `8.06` | `8.22` | Usable, but missing enough explicit MSP gates to stay conditional. |

## Product Readout

The clean benchmark story is now:

1. Pure Direct is not useless. It produces acceptable generic incident guidance in many cases.
2. Direct + fractal memory is a real discovered product lane. A single model call becomes measurably better when memory is injected into the prompt.
3. ParaLLM still wins the full architecture comparison because it combines memory pressure, provider routing, review lanes, final-answer scoring, and an auditable control trace.

The next target is not to patch individual benchmark cases. The runtime should treat retrieved memory as binding ground truth: workers should build from it, summarizers should integrate it, and judges should reject final answers that omit relevant memory obligations.
