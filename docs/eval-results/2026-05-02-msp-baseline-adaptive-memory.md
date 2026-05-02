# 2026-05-02 MSP Baseline/Adaptive Memory Scoring

This run scored the hard MSP council suite after adding baseline/adaptive MSP knowledgebase recall.

The intent was not a pure no-memory direct-vs-Para benchmark. Both Direct and Para were allowed to use the same MSP knowledgebase so we could test whether mandatory baseline SOP packets plus adaptive judge-learned memories improve first-hour incident answers without loading the full rulebook into every prompt.

## Run

| Field | Value |
| --- | --- |
| Run id | `judge-openai54-baseline-adaptive-20260502-112054` |
| Previous comparable run | `judge-openai54-memory-benefit-20260502-095951` |
| Suite | `msp-critical-council-hard` |
| Cases | RMM supply-chain replay, backup-console destructive jobs, cross-tenant OAuth/mailbox abuse |
| Arms | `direct-gpt54-open`, `para-gpt54-critical-double--loops-1` |
| Provider/model | `openai` / `gpt-5.4` |
| Judge | `openai` / `gpt-5.4` |
| Replicates | `1` per arm/case |
| Errors | `0` |
| Total tokens / estimated cost | `183,053` / `$1.664687` |
| Judge learning | enabled; `48` score events learned, event ledger `321 -> 369` |

## Memory Shape Confirmed

The backup-console case prompt included targeted recall with:

- `memoryMode`: `baseline_and_adaptive_sop_packets`
- baseline packets:
  - `MSP common major incident frame`
  - `24/7 operations and continuity SOP`
- adaptive packets:
  - tenant-safe incident communications
  - vendor escalation and artifact handoff

This is the intended pattern: compact baseline guardrails first, then targeted learned scars. The full MSP knowledgebase is not dumped into the prompt.

## Aggregate Result

| Metric | Previous run | Baseline/adaptive run | Delta |
| --- | ---: | ---: | ---: |
| Total tokens | `193,903` | `183,053` | `-10,850` |
| Estimated cost | `$1.648608` | `$1.664687` | `+$0.016079` |
| Average overall quality | `8.33` | `8.67` | `+0.34` |
| Average actionability | `8.50` | `9.17` | `+0.67` |
| Average answer health | `9.50` | `9.33` | `-0.17` |
| Average control | `9.00` | `7.67` | `-1.33` |

## Per-Case Overall Quality

| Case | Direct previous | Direct baseline/adaptive | Para previous | Para baseline/adaptive |
| --- | ---: | ---: | ---: | ---: |
| RMM supply-chain replay | `9` | `9` | `9` | `8` |
| Backup-console destructive jobs | `5` | `9` | `9` | `8` |
| Cross-tenant OAuth/mailbox abuse | `9` | `9` | `9` | `9` |

## Read

The baseline/adaptive memory model fixed the most obvious weakness from the previous run: the Direct backup-console answer no longer collapsed on operational/comms rigor.

The remaining problem moved into merge discipline. Para still produced strong answers, but two hard-case Para scores fell from `9` to `8` because the final answers did not always state per-tenant incident ownership and child records explicitly enough, even though that requirement was present in baseline memory. The backup Para control score also dropped because the judge wanted clearer fallback paths when vendor-side holds or normal coordination channels are unavailable.

## Follow-Up Tuning Target

This run immediately tightened the baseline packet wording from generic per-tenant child records to named ownership per affected tenant child record. The next step is making the final synthesis fail closed when that baseline obligation is missing:

- make commander review fail closed when a worker flags missing per-tenant ownership
- add a compact final self-check before summarizer output: tenant ownership, evidence gate, control-plane distrust, continuity gate, customer-safe comms, vendor/legal escalation
