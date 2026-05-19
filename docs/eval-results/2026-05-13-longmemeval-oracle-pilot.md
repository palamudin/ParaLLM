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

The initial publishable diagnostic run is `judge-20260513-214149+0000-55f943`.

The current repaired direct-memory run is `judge-20260514-104149+0000-ac6eb6`. It uses Codex-auth OpenAI execution, the same five-case pilot suite, and the direct + LongMemEval memory arm after Timerbiter projection fixes.

Excluded runs:

- `judge-20260513-211918+0000-108e9f`: diagnostic only. The memory bank still exposed gold answers through metadata/entities, so it was too easy and not a clean score claim.
- `judge-20260513-220034+0000-0545d6`: operational fail. It attempted the improved v2 adapter, but OpenAI returned `HTTP 429 insufficient_quota` across all cells before clean scores could be produced.
- `judge-20260513-234706+0000-8e3788`: operational fail. It attempted the Timerbiter-lite memory bank after mechanical validation, but OpenAI again returned `HTTP 429 insufficient_quota` across all cells before answer generation.
- `judge-20260514-090901+0000-f44d7b`, `judge-20260514-095402+0000-17093a`, and `judge-20260514-102307+0000-9213cb`: repair diagnostics. These isolated projection starvation, temporal event precedence, obligation row counting, and brittle deterministic wording checks before the final clean run.

## Run Summary

| Run | Scope | Errors | Tokens | Cost | Readout |
| --- | --- | ---: | ---: | ---: | --- |
| `judge-20260513-214149+0000-55f943` | Five LongMemEval oracle pilot cases across Pure Direct, Direct + memory, and Para | `0` | `135,588` | `$0.058281` | Valid leak-free diagnostic run. |
| `judge-20260513-220034+0000-0545d6` | Same suite after v2 event-ledger adapter | `15 / 15` cells failed before answer generation | `0 scored` | `n/a` | Blocked by OpenAI API quota, excluded from score claims. |
| `judge-20260513-234706+0000-8e3788` | Same suite after Timerbiter-lite temporal ledger | `15 / 15` cells failed before answer generation | `0 scored` | `n/a` | Blocked by OpenAI API quota, excluded from score claims. |
| `judge-20260514-104149+0000-ac6eb6` | Direct + LongMemEval memory after Timerbiter projection repair | `0` | `131,113` | `$0.061670` | Clean 5/5 direct-memory run. |

## Results

| Path | Answer-time memory | Deterministic pass | Quality | Health | Control | Owner quality | Owner health | Owner control | Readout |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Pure Direct prompt-only | No | `0 / 5` | `1.40` | `5.00` | `n/a` | `2.00` | `4.80` | `n/a` | Correctly weak on memory QA because no answer-time memory was available. |
| Direct + LongMemEval memory | Yes | `3 / 5` | `6.60` | `10.00` | `n/a` | `6.80` | `10.00` | `n/a` | Single-call memory answered simple recall and update cases, but missed temporal and multi-session counting cases. |
| ParaLLM multi-lane orchestration | Yes | `3 / 5` | `6.40` | `10.00` | `4.20` | `6.60` | `10.00` | `4.40` | Para used memory when the retrieved surface was clear, but inherited the same temporal/counting weakness from the memory shape. |

## Repaired Direct-Memory Result

Run: `judge-20260514-104149+0000-ac6eb6`

| Case | Deterministic pass | Quality | Health | Owner protection | Answer |
| --- | ---: | ---: | ---: | ---: | --- |
| `gpt4_2655b836` | `1.0` | `9.0` | `10.0` | `10.0` | The first issue was the car's GPS system, after the March 15 service anchor. |
| `0a995998` | `1.0` | `10.0` | `10.0` | `10.0` | 3 items: dry-cleaning pickup, boots return, and boots pickup. |
| `6a1eabeb` | `1.0` | `10.0` | `10.0` | `10.0` | 25:50. |
| `7161e7e2` | `1.0` | `10.0` | `10.0` | `10.0` | Admon was on the Sunday 8 am to 4 pm shift. |
| `e47becba` | `1.0` | `10.0` | `10.0` | `10.0` | Business Administration. |

Aggregate: deterministic `5 / 5`, average quality `9.8`, average answer health `10.0`, average owner protection `10.0`.

The repaired path changed the memory surface, not the benchmark facts:

- `metadata.timerbiter` now remains structured when retained, instead of being flattened into a string.
- Decisive temporal rows are projected as ordered event memory. The first event after an anchor is labelled `FIRST_AFTER_ANCHOR_CANDIDATE`.
- Open obligations are projected as countable rows, so the model treats multiple open actions as arithmetic rows rather than one vague shopping topic.
- Non-decisive dated background no longer crowds out direct query evidence. In the 5K case, the `25:50` update is shown before unrelated tennis event rows.
- Deterministic concept checks normalize equivalent time range wording, such as `8 am - 4 pm`, `8am-4pm`, and `8 am to 4 pm`.

## Case Detail

| Case | Gold task shape | Pure Direct | Direct + memory | Para | Finding |
| --- | --- | ---: | ---: | ---: | --- |
| `gpt4_2655b836` | Temporal car issue after first service | Fail | Fail | Fail | The diagnostic failure is now classified as missing temporal arbitration: the memory contained both the service anchor and the later GPS issue, but the memory surface did not give the model an explicit before/after authority. |
| `0a995998` | Multi-session clothing pickup/return count | Fail | Fail | Fail | The diagnostic failure is now classified as missing obligation arbitration: the memory contained the dry-cleaning and Zara tasks, but the answer path did not receive a clean open-obligation ledger. |
| `6a1eabeb` | Knowledge-update personal best 5K time | Fail | Pass | Pass | Later `25:50` memory correctly overmatched earlier `27:12`. |
| `7161e7e2` | Single-session assistant table recall | Fail | Pass | Pass | Admon Sunday shift was retrieved correctly. |
| `e47becba` | Single-session user fact recall | Fail | Pass | Pass | Business Administration degree was retrieved correctly. |

## Timerbiter-Lite Follow-Up

The diagnostic failures were not treated as a theory failure. They identified that raw transcript recall needs an operator-quality memory surface.

The builder now creates a stronger leak-free memory record:

- removes gold answer from memory metadata and entities
- keeps gold answer only in the suite checks
- prepends question-focused transcript excerpts
- adds a chronological user-event ledger extracted from transcript messages
- adds `metadata.timerbiter` with `parallm-timerbiter/v0`, deposited/retrieved clocks, ordered events, anchor/update labels, and an open-obligation ledger
- renders `Timerbiter temporal authority` and `Timerbiter obligation ledger` sections into the answer-time memory text
- adds generic memory-QA instructions for temporal, update, and counting questions
- projects decisive Timerbiter rows ahead of loose transcript excerpts
- keeps non-decisive time background behind direct query evidence

No benchmark answer is injected into answer-time memory. Focused tests now cover the temporal car anchor, the after-anchor issue, the open clothing-obligation ledger, query-focused deep excerpts, non-decisive temporal background ordering, and a guard that ignores generic advice requests as obligations.

## Interpretation

This pilot supports three useful conclusions:

- Pure Direct is a clean no-memory baseline and should not be expected to pass memory QA.
- Direct + memory is already valuable, but long-memory quality depends heavily on how raw memories are shaped before they reach the model.
- Para's lanes do not automatically fix a poor memory surface; they amplify the same source material.
- Timerbiter-lite is the next memory transformation layer: deterministic temporal and obligation scaffolding before probabilistic answer generation.

Next step: rerun Para multi-lane on the same repaired memory surface, then expand beyond five cases into a larger LongMemEval or LoCoMo-style memory suite.
