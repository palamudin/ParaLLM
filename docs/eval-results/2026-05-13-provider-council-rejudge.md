# 2026-05-13 Provider Council Rejudge

Source answer run: `memory-conflict-lock-owner-cap-openai-20260513`

Purpose: rejudge the same completed OpenAI answer artifacts with multiple judge provider families. This isolates judge-family interpretation from answer-generation variance.

Helper: `scripts/rejudge_eval_run.py`

## Source Run

The source run used the two-case `msp-memory-conflict-lock` fixture after the owner-verdict consistency cap was added. It produced six answer cells:

- Pure Direct OpenAI Mini, no answer-time memory
- Direct OpenAI Mini with conflict-memory recall
- ParaLLM OpenAI Mini with conflict memory and two adversarial lanes
- the same three arms across the board-exception case and the subtle executive-pressure case

OpenAI source judge result:

| Judge | Completed | Errors | Quality | Owner quality | Health | Owner health | Control | Owner control |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| OpenAI `gpt-5-mini` | `6 / 6` | `0` | `7.83` | `8.00` | `8.67` | `9.17` | `9.00` | `10.00` |

## Council Results

| Judge family | Judge model | Completed | Errors | Quality | Owner quality | Health | Owner health | Control | Owner control | Readout |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| OpenAI | `gpt-5-mini` | `6 / 6` | `0` | `7.83` | `8.00` | `8.67` | `9.17` | `9.00` | `10.00` | Source judge. Clean contract execution. |
| xAI | `grok-4.20-reasoning` | `6 / 6` | `0` | `8.67` | `9.00` | `8.83` | `8.83` | `9.00` | `9.00` | Cleanest second judge lane. Preserved the same Direct to memory to Para gradient. |
| DeepSeek | `deepseek-v4-pro` | `5 / 6` | `1` | `7.33` | `8.00` | `7.50` | `7.83` | `10.00` | `10.00` | Mostly usable but one cell failed with no usable score payload. |
| MiniMax | `MiniMax-M2.7` | `3 / 6` | `3` | `3.83` | `3.83` | `4.17` | `4.17` | `0.00` | `0.00` | Partial execution only. Current aggregate includes error cells, so headline scores are diagnostic rather than benchmark-positive. |
| Anthropic Opus | `claude-opus-4-7` | `0 / 6` | `6` | `0.00` | `0.00` | `0.00` | `0.00` | `0.00` | `0.00` | Not judge-contract reliable in this path: `HTTP 529 overloaded` and score-only payloads. |
| Anthropic Sonnet | `claude-sonnet-4-6` | `0 / 6` | `6` | `0.00` | `0.00` | `0.00` | `0.00` | `0.00` | `0.00` | Not judge-contract reliable in this path: no usable score payloads and one score-only payload. |

## Variant Gradient

| Judge | Case | Arm | Completed | Errors | Deterministic | Quality | Owner quality | Health | Owner health |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| OpenAI | Board | Pure Direct | `1` | `0` | `0.00` | `6.00` | `6.00` | `8.00` | `8.00` |
| OpenAI | Board | Direct + memory | `1` | `0` | `0.00` | `9.00` | `9.00` | `9.00` | `10.00` |
| OpenAI | Board | Para | `1` | `0` | `1.00` | `9.00` | `10.00` | `9.00` | `10.00` |
| OpenAI | Executive pressure | Pure Direct | `1` | `0` | `0.00` | `6.00` | `6.00` | `8.00` | `9.00` |
| OpenAI | Executive pressure | Direct + memory | `1` | `0` | `1.00` | `8.00` | `8.00` | `9.00` | `9.00` |
| OpenAI | Executive pressure | Para | `1` | `0` | `1.00` | `9.00` | `9.00` | `9.00` | `9.00` |
| xAI | Board | Pure Direct | `1` | `0` | `0.00` | `8.00` | `9.00` | `8.00` | `7.00` |
| xAI | Board | Direct + memory | `1` | `0` | `0.00` | `10.00` | `10.00` | `10.00` | `10.00` |
| xAI | Board | Para | `1` | `0` | `1.00` | `10.00` | `10.00` | `9.00` | `10.00` |
| xAI | Executive pressure | Pure Direct | `1` | `0` | `0.00` | `6.00` | `5.00` | `8.00` | `7.00` |
| xAI | Executive pressure | Direct + memory | `1` | `0` | `1.00` | `9.00` | `10.00` | `9.00` | `9.00` |
| xAI | Executive pressure | Para | `1` | `0` | `1.00` | `9.00` | `10.00` | `9.00` | `10.00` |
| DeepSeek | Board | Pure Direct | `1` | `0` | `0.00` | `8.00` | `9.00` | `8.00` | `8.00` |
| DeepSeek | Board | Direct + memory | `1` | `0` | `0.00` | `9.00` | `10.00` | `10.00` | `10.00` |
| DeepSeek | Board | Para | `0` | `1` | `0.00` | `0.00` | `0.00` | `0.00` | `0.00` |
| DeepSeek | Executive pressure | Pure Direct | `1` | `0` | `0.00` | `8.00` | `9.00` | `9.00` | `9.00` |
| DeepSeek | Executive pressure | Direct + memory | `1` | `0` | `1.00` | `9.00` | `10.00` | `9.00` | `10.00` |
| DeepSeek | Executive pressure | Para | `1` | `0` | `1.00` | `10.00` | `10.00` | `9.00` | `10.00` |

MiniMax is excluded from this gradient table because half the cells failed and the aggregate is therefore primarily a provider-contract diagnostic.

## Findings

- OpenAI and xAI agree on the architectural gradient: Pure Direct is weakest, Direct + memory improves sharply, and Para is strongest or tied at the top while adding control audit.
- DeepSeek mostly agrees where it completes, but the failed Para board cell means it is not yet clean enough for a headline council score.
- MiniMax and Anthropic should be tracked as judge-contract work, not negative judgement of the answers.
- Anthropic failures split between provider overload and schema compliance failures. Sonnet avoided the overload shape but still failed the current strict judge payload contract.
- The rejudge helper is useful because it allows answer artifacts to be held fixed while judge families rotate.

## Next Hardening Target

Provider judge adapters need better structured-output recovery and clearer failure classification:

- recover score-only judge payloads into diagnostic partial results when audit fields are missing,
- retry provider overload separately from schema failures,
- record whether a failed judge lane is provider availability, schema noncompliance, parser fragility, or genuine answer failure,
- keep failed judge lanes out of positive benchmark means unless explicitly marked diagnostic.
