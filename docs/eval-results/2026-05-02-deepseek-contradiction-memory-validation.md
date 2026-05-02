# 2026-05-02 DeepSeek Contradiction Memory Validation

This was a focused validation pass after adding cross-round contradiction memory and MSP final-answer gates.

The goal was not a fresh public score claim. It was to check whether unresolved worker/review pressure survives into the summarizer, whether missing MSP obligations are backstopped before the public answer leaves, and whether DeepSeek can run the path without hand-holding.

## Runs

| Run id | Shape | Result |
| --- | --- | --- |
| `judge-deepseek-contradiction-gate-20260502-184319+0000` | Direct + Para, DeepSeek generation/judge, backup case | Direct completed with quality `9`; Para failed before execution because the long run id plus isolated knowledgebase hydration exceeded the Windows path boundary. |
| `ds-gate-bkp` | Short-path Direct + Para, DeepSeek generation/judge, backup case | Completed. Direct quality `9`; Para quality `7`, health `9`, control `9`. Contradiction memory fired and inserted missing MSP backstop gates. |
| `ds-gate-b2` | Short-path Para-only rerun after adding the evidence-compatible decision-log requirement | Completed. Para quality `8`, health `9`, control `9`. The judge still saw missing explicit major-incident/decision-log language, revealing that the tenant-owner matcher was too permissive. |
| `ds-gate-b3` | Short-path Para-only rerun after tightening the matcher | Failed at `commander_review` because DeepSeek returned malformed JSON: `Unterminated string starting at: line 7 column 23`. |
| `ds-gate-b4` | Fresh short-path Para-only retry after local tests passed | Failed at `commander` after two live retries because DeepSeek returned malformed JSON twice: `Unterminated string starting at: line 47 column 5`. |

## What Worked

- Contradiction memory is present in summarizer artifacts as `responseMeta.contradictionMemory`.
- The packet is optional background, not a core dependency.
- The summarizer received `6` MSP final-answer gates on the backup case:
  - `msp-tenant-ownership`
  - `msp-evidence-before-cleanup`
  - `msp-control-plane-distrust`
  - `msp-tenant-safe-communications`
  - `msp-continuity-authority-gate`
  - `msp-vendor-escalation`
- In `ds-gate-bkp`, the backstop appended missing tenant ownership, tenant-safe communications, and continuity authority gates to the final answer.
- Local regression tests now require the tenant-owner gate to include all three ideas: internal major-incident record, named per-tenant owner, and evidence-compatible decision log.

## What Failed

- Long eval run ids can break isolated knowledgebase hydration on Windows path limits. Short run ids are the practical workaround until the eval runner shortens workspace paths or uses long-path-safe copy handling.
- DeepSeek can still fail strict JSON parsing in commander/review stages. The gate logic is not the failure there; the provider adapter/retry path needs stronger malformed-JSON recovery for strict stages.
- The first live gate version was too easy to satisfy with generic incident language. That is fixed in code and covered by a regression test.

## Read

This is a useful validation, not a victory lap.

The feature does the thing we needed: it keeps unresolved MSP obligations alive and can force a missing final-answer backstop. The remaining work is runtime-hardening around provider JSON recovery and Windows path depth, then another clean scoring run on the backup/identity rub set.

After the stricter matcher landed, local regression tests became the primary validation signal because the fresh DeepSeek retry failed before reaching summarizer. Do not treat `ds-gate-b4` as a quality score.
