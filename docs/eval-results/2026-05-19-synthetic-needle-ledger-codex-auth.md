# 2026-05-19 Synthetic Needle Ledger Codex-Auth Refresh

## Purpose

This run refreshes the Synthetic Needle Ledger Transit benchmark through Codex-auth OpenAI lanes. It uses the same non-MSP memory-integrity fixture as the earlier side test: three synthetic transit ledgers are stored as durable memory, then each answer path receives a noisy prompt with near-name poison, recency bait, and irrelevant arithmetic.

The test is intentionally outside MSP phrasing. The required behavior is exact retrieval of the stored ledger fields when answer-time memory is available, and safe refusal rather than guessing when no answer-time memory is available.

## Run Summary

| Field | Value |
| --- | --- |
| Run id | `judge-20260519-162718+0000-snl-codex` |
| Suite | `synthetic-needle-ledger-transit` |
| Cases | `3` |
| Scored cells | `9` |
| Errors | `0` |
| Judge provider/model | OpenAI `gpt-5.4-mini` via Codex auth |
| Total tokens | `1,137,950` |
| Estimated cost | `$1.439108` |

## Results

| Path | Answer-time memory | Deterministic pass | Quality | Health | Control | Corporate readout |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Pure Direct prompt-only | No | `0 / 3` | `1.33` | `1.33` | `n/a` | Correctly avoided inventing a ledger, but failed retrieval because no answer-time memory was available. |
| Direct + synthetic memory | Yes | `3 / 3` | `10.00` | `10.00` | `n/a` | Exact retrieval from a single memory-backed call. |
| ParaLLM multi-lane orchestration | Yes | `3 / 3` | `10.00` | `10.00` | `9.67` | Exact retrieval with lane-level pressure and a separate control score. |

## Learning and Contamination Guard

Judge learning inspected all nine score files and inserted nine broad candidate records into the isolated candidate ledger. It promoted zero durable records into the synthetic bank because the cases are non-MSP fixtures and should not contaminate the MSP knowledgebase.

| Learning field | Value |
| --- | ---: |
| Score files seen | `9` |
| Durable records learned | `0` |
| Candidate records captured | `9` |
| Candidate ledger count after run | `14` |

## Interpretation

This is a clean plumbing result rather than a broad intelligence claim. It shows that the current answer paths can separate three materially different regimes:

- Pure Direct without answer-time memory can be safe, but it cannot retrieve what it was not given.
- Direct plus explicit memory proves the cheap single-call memory-bound path can recover exact stored facts.
- ParaLLM proves the same exact retrieval through the multi-lane route, while adding an auditable control surface.

The remaining calibration item is the synthetic control-audit owner-protection readout. Para's normal control score averaged `9.67`, but the nested owner-protection audit averaged lower on this artificial fixture. That looks like a rubric mismatch for non-operational ledger tests, not an answer failure, and should be tested separately before it is treated as headline evidence.

