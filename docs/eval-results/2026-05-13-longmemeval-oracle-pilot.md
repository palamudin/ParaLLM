# 2026-05-13 LongMemEval Oracle Pilot

## Purpose

This is the first external memory-quality pilot for ParaLLM. It adapts a small five-case slice from the LongMemEval oracle dataset into ParaLLM memory banks and eval arms.

Source: `https://github.com/xiaowu0162/LongMemEval`

This is not an official leaderboard submission. It is a local pilot to test whether ParaLLM can retrieve and use long-term conversational memory outside MSP/security language.

## Test Assets

- Builder: `scripts/build_longmemeval_pilot.py`
- Suite: `data/evals/suites/longmemeval-oracle-pilot-5.json`
- Knowledge bank: `data/knowledgebase/banks/longmemeval-oracle-pilot-5/memory_units.jsonl`
- Pure Direct arm: `data/evals/arms/direct-openai-mini-longmemeval-oracle-pilot-5-pure.json`
- Direct + memory arm: `data/evals/arms/direct-openai-mini-longmemeval-oracle-pilot-5-memory.json`
- Para arm: `data/evals/arms/para-openai-mini-longmemeval-oracle-pilot-5-double.json`

The external raw dataset is intentionally not committed. It is ignored under `data/external/`.

## Publication Scope

The publishable run here is `judge-20260513-214149+0000-55f943`.

Excluded runs:

- `judge-20260513-211918+0000-108e9f`: diagnostic only. The memory bank still exposed gold answers through metadata/entities, so it was too easy and not a clean score claim.
- `judge-20260513-220034+0000-0545d6`: operational fail. It attempted the improved v2 adapter, but OpenAI returned `HTTP 429 insufficient_quota` across all cells before clean scores could be produced.

## Run Summary

| Run | Scope | Errors | Tokens | Cost | Readout |
| --- | --- | ---: | ---: | ---: | --- |
| `judge-20260513-214149+0000-55f943` | Five LongMemEval oracle pilot cases across Pure Direct, Direct + memory, and Para | `0` | `135,588` | `$0.058281` | Valid leak-free diagnostic run. |
| `judge-20260513-220034+0000-0545d6` | Same suite after v2 event-ledger adapter | `15 / 15` cells failed before answer generation | `0 scored` | `n/a` | Blocked by OpenAI API quota, excluded from score claims. |

## Results

| Path | Answer-time memory | Deterministic pass | Quality | Health | Control | Owner quality | Owner health | Owner control | Readout |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Pure Direct prompt-only | No | `0 / 5` | `1.40` | `5.00` | `n/a` | `2.00` | `4.80` | `n/a` | Correctly weak on memory QA because no answer-time memory was available. |
| Direct + LongMemEval memory | Yes | `3 / 5` | `6.60` | `10.00` | `n/a` | `6.80` | `10.00` | `n/a` | Single-call memory answered simple recall and update cases, but missed temporal and multi-session counting cases. |
| ParaLLM multi-lane orchestration | Yes | `3 / 5` | `6.40` | `10.00` | `4.20` | `6.60` | `10.00` | `4.40` | Para used memory when the retrieved surface was clear, but inherited the same temporal/counting weakness from the memory shape. |

## Case Detail

| Case | Gold task shape | Pure Direct | Direct + memory | Para | Finding |
| --- | --- | ---: | ---: | ---: | --- |
| `gpt4_2655b836` | Temporal car issue after first service | Fail | Fail | Fail | Memory contained the GPS issue, but the compact surface did not make the service anchor plus later issue obvious enough. |
| `0a995998` | Multi-session clothing pickup/return count | Fail | Fail | Fail | Memory contained the relevant dry-cleaning and Zara obligations, but the answer path counted only the replacement pickup. |
| `6a1eabeb` | Knowledge-update personal best 5K time | Fail | Pass | Pass | Later `25:50` memory correctly overmatched earlier `27:12`. |
| `7161e7e2` | Single-session assistant table recall | Fail | Pass | Pass | Admon Sunday shift was retrieved correctly. |
| `e47becba` | Single-session user fact recall | Fail | Pass | Pass | Business Administration degree was retrieved correctly. |

## Adapter Fix After Diagnostic Run

The diagnostic failures were not treated as a theory failure. They identified that raw transcript recall needs an operator-quality memory surface.

The builder now creates a stronger leak-free memory record:

- removes gold answer from memory metadata and entities
- keeps gold answer only in the suite checks
- prepends question-focused transcript excerpts
- adds a chronological user-event ledger extracted from transcript messages
- adds generic memory-QA instructions for temporal, update, and counting questions

No benchmark answer is injected into answer-time memory. The v2 adapter is ready, but the rerun was blocked by provider quota.

## Interpretation

This pilot supports three useful conclusions:

- Pure Direct is a clean no-memory baseline and should not be expected to pass memory QA.
- Direct + memory is already valuable, but long-memory quality depends heavily on how raw memories are shaped before they reach the model.
- Para's lanes do not automatically fix a poor memory surface; they amplify the same source material. The next gain is a better memory transformation layer, not more generic prompting.

Next step: rerun the v2 event-ledger adapter when provider quota is available, then expand beyond five cases into a larger LongMemEval or LoCoMo-style memory suite.
