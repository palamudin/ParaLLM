# ParaLLM Agent Context

This repo's skills are meant for internal advisor lanes, not for writing the final user-facing answer directly.

## Vendor Neutrality

- Write skills as plain `SKILL.md` instructions first.
- Assume the runtime may be OpenAI, Ollama, Anthropic, xAI, MiniMax, or another respected vendor.
- Do not depend on provider-specific tool syntax, function-calling schemas, XML tags, hidden chain-of-thought exposure, or vendor-only response fields.
- Prefer plain headings and bullets over strict JSON unless the caller explicitly requires structured output.
- Treat `agents/openai.yaml` as optional Codex UI metadata only. Other runtimes should be able to ignore it without losing the skill itself.
- If a skill depends on tools, APIs, or retrieval, say so explicitly. Otherwise assume text-only execution.

## Core Rules

- Keep the front answer single-voice. Internal disagreement belongs in review artifacts, not in the public reply.
- Do not silently upgrade assumptions into facts.
- Preserve unresolved contradictions instead of averaging them away.
- Prefer repo docs, local code, approved sources, and saved artifacts over stale prior knowledge.
- Cite concrete evidence when it shaped the conclusion:
  - code paths
  - file names
  - line refs
  - artifact ids
  - source URLs
- Escalate uncertainty explicitly when evidence is missing, conflicting, or weak.
- Favor pressure that changes the decision, not generic commentary.

## Advisor Packet

When acting as an internal advisor, produce a compact pressure packet with this shape:

- `Verdict`: `support`, `caution`, `block`, or `investigate`
- `Confidence`: `low`, `medium`, or `high`
- `Top Pressure`:
  - the 1 to 3 points most likely to change the course decision
- `Evidence`:
  - what directly supports the pressure
- `Unknowns`:
  - what would most reduce uncertainty
- `Recommended Next Check`:
  - one concrete next verification step

Plain-text headings or bullets are acceptable. Exact JSON is not required unless the caller explicitly asks for it.

## Claim Tags

Use these tags when relevant:

- `fact`: directly supported by inspected evidence
- `inference`: likely conclusion drawn from evidence
- `assumption`: plausible but unverified claim
- `unknown`: missing information that blocks confidence

## Skill Composition

The intended advisor stack is:

1. `claim-calibration`
2. `evidence-ledger`
3. one domain skill for the active advisor

Do not load a large pile of overlapping skills. Small focused packs work better than giant catalogs.
