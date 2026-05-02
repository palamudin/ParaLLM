# 2026-05-02 OpenAI 5.4 Rub Test: Backup/Identity

This was a focused repeat test after the basis sweep showed that backup and identity cases were where Direct most often beat Para.

The run intentionally reused the current baseline/adaptive MSP memory path and judge-learning writeback.

## Run

| Field | Value |
| --- | --- |
| Run id | `rub-g54-bi-151642` |
| Provider/model | `openai` / `gpt-5.4` |
| Judge | `openai` / `gpt-5.4` |
| Suite shape | backup-console + identity OAuth hard cases |
| Arms | `direct-gpt54-open`, `para-gpt54-critical-double--loops-1` |
| Requested replicates | `3` per arm/case |
| Completed useful replicates | backup `6/6`; identity `0/6` |
| Identity failure cause | OpenAI quota exhausted: HTTP `429` / `insufficient_quota` |
| Tokens / estimated cost | `172,173` / `$1.480645` |
| Judge learning | `43` score events learned; event ledger `586 -> 637` |

## Backup Case Result

| Arm | Replicate scores | Quality mean | Actionability mean | Health mean | Control mean |
| --- | --- | ---: | ---: | ---: | ---: |
| `direct-gpt54-open` | `9`, `9`, `9` | `9.00` | `9.67` | `9.67` | `n/a` |
| `para-gpt54-critical-double--loops-1` | `9`, `5`, `6` | `6.67` | `8.00` | `8.33` | `8.33` |

## Repeated Judge Weakness

The same weakness repeated across the Para failures:

- Replicate 1: stops short of explicit per-customer ownership/handling for all affected tenants.
- Replicate 2: does not establish explicit per-customer incident ownership/evidence handling for all affected tenants.
- Replicate 3: weak objection absorption, with the same tenant-ownership issue visible in the surrounding score packet.

Direct was stable and repeatedly received only minor notes: make named tenant ownership, legal/compliance thresholds, and tenant-specific artifacts even more explicit.

## Read

This is no longer just scoring variance.

The system has the right baseline memory, but Para's final synthesis can still lose mandatory baseline obligations that workers or memory already surfaced. In this case, the final answer did not consistently carry explicit named per-tenant ownership and evidence handling through to the public response.

## Decision

Stop broad scoring until the next reasoning upgrade is implemented.

The next upgrade should be cross-round contradiction memory plus final merge gates:

- persist unresolved worker objections and held-out concerns as contradiction memories
- replay them into commander review and summarizer as "must resolve or explicitly reject"
- add a final gate that fails the synthesis if named tenant ownership, evidence sequencing, control-plane distrust, continuity gates, tenant-safe comms, or vendor/legal escalation are missing
- rerun this exact backup rub test after the gate lands

