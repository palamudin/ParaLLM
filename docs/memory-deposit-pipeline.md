# Memory Deposit Pipeline

ParaLLM memory writes should not depend on brittle domain gates as the primary intelligence layer. The runtime now separates memory capture from memory promotion.

## Current Shape

Eval judge output can produce a memory candidate packet for every scored cell. Candidate packets are written to an isolated ledger:

- `data/knowledgebase/candidates/memory_candidates.jsonl`

This ledger is ignored by git because it is runtime evidence, not source truth.

Each candidate contains:

- source run, case, arm, variant, and score reference
- compact judge signals from quality, answer-health, control, comparison, and deterministic checks
- requested bank id
- routing status
- arbiter blockers
- evidence references

Without an autonomous routing proposal, candidates default to:

- `routing.status`: `pending_context_review`
- `routing.destination`: `quarantine`
- `arbiter.state`: `hold`
- `arbiter.promotion`: `disabled_until_context_review`

That means capture is broad, but durable promotion is blocked until the router/arbiter path approves it.

## Legacy Promotion

The existing judge-learning path still promotes MSP SOP lessons for eligible MSP cases. It is now guarded so non-MSP benchmarks, such as LongMemEval, can create candidate packets without polluting MSP or benchmark memory banks.

This keeps deterministic code as a rail:

- schema-valid packets only
- no direct durable write from generic judge text
- non-domain cases do not enter MSP SOP memory
- runtime candidate ledgers stay separate from durable memory banks

## Next Step

Add a context-router lane that reads candidate packets and returns a constrained proposal:

- destination: `session`, `user`, `domain`, `sop`, `eval`, `benchmark`, `artifact`, `quarantine`, or `reject`
- target bank id
- store class: `STS`, `LTS`, `eval`, `artifact`, `quarantine`, or `reject`
- confidence
- TTL when temporary
- evidence refs
- rationale
- conflict or supersession notes

After that, the memory arbiter can promote, merge, supersede, quarantine, or reject candidates without hard-coding every domain.
