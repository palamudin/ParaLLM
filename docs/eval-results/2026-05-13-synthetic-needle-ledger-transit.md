# 2026-05-13 Synthetic Needle Ledger Transit

## Purpose

This is an unrelated memory-integrity side test. It deliberately avoids MSP subject matter so ParaLLM cannot win by domain familiarity. Each case stores a small synthetic route ledger in memory, then gives the answer path a noisy transit story filled with repeated near-name poison and recency bait.

The answer must retrieve the stored ledger exactly and ignore the poisoned story. If no answer-time memory is available, the safe behavior is to say the ledger is unavailable rather than guess.

## Test Assets

- Knowledge bank: `data/knowledgebase/banks/synthetic-needle-ledger-transit/memory_units.jsonl`
- Suite: `data/evals/suites/synthetic-needle-ledger-transit.json`
- Pure Direct arm: `data/evals/arms/direct-openai-mini-synthetic-needle-pure.json`
- Direct + memory arm: `data/evals/arms/direct-openai-mini-synthetic-needle-memory.json`
- Para arm: `data/evals/arms/para-openai-mini-synthetic-needle-double.json`

The three routes were `cinder-7`, `amber-12`, and `vellum-4`. Required fields were `routeId`, `destination`, `destinationType`, `canonicalVehicle`, `addonIndustryTerm`, and `anchorPhrase`.

## Run Summary

| Run | Scope | Errors | Tokens | Cost |
| --- | --- | ---: | ---: | ---: |
| `synthetic-needle-ledger-openai-20260513-fix1` | Pure Direct, Direct + memory, Para before capture fix | `0` | `94,481` | `$0.040236` |
| `synthetic-needle-ledger-openai-20260513-para-fix4` | Para after capture fix | `0` | `84,826` | `$0.037090` |

## Results

| Path | Answer-time memory | Deterministic pass | Quality | Health | Control | Owner quality | Owner control | Readout |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Pure Direct prompt-only | No | `0 / 3` | `1.67` | `2.00` | `n/a` | `1.67` | `n/a` | Safe no-guess behavior, but no ledger retrieval. |
| Direct + synthetic memory | Yes | `3 / 3` | `10.00` | `10.00` | `n/a` | `10.00` | `n/a` | Exact retrieval from a single memory-backed call. |
| Para before capture fix | Yes | `0 / 3` | `1.00` | `1.00` | `2.33` | `1.33` | `2.00` | Plumbing failure: raw summarizer output had the right answer, but the public answer capture surfaced the fallback. |
| Para after capture fix | Yes | `3 / 3` | `10.00` | `10.00` | `7.67` | `10.00` | `8.33` | Exact retrieval with visible multi-lane control pressure. |

## Valuable Failure

The initial Para failure was not a reasoning failure. The worker and summarizer path produced the correct ledger answer, but generic structured-output parsing preferred a nested `frontAnswer` object and flattened the payload before the public answer was normalized. The visible answer became `No adjudicated answer was captured.`

Runtime fix: `runtime/engine.py` now checks the literal top-level provider JSON for `frontAnswer.answer` before falling back to the generic parser. If the parsed payload is flattened or contains the fallback, the raw top-level summary wins.

Regression coverage: `backend/tests/test_runtime_auth.py::RuntimeAuthTests::test_new_live_summary_prefers_raw_top_level_front_answer_over_flattened_parse`.

## Interpretation

This side test supports three current conclusions:

- Pure Direct can be safe by refusing to guess, but it does not prove memory retrieval.
- Direct + memory proves the cheap single-call memory path can work when the memory is clean and exact.
- Para proves the same exact retrieval after the capture fix, while also exposing a control surface that can be scored separately from the final answer.

Next useful expansion: generate rotating non-MSP needles across buildings, animals, tools, vehicle parts, and materials, then run longer context-poison cases to measure whether older deposited memory survives heavy recent-token bait.
