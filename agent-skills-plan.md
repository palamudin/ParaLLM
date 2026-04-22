# Agent Skills Plan

## Why This Matters

ParaLLM already has a strong advisor/persona model. The missing layer is a portable skill system that lets each advisor load a small, reusable playbook instead of relying on one giant prompt or hoping the model rediscovers the workflow every run.

That becomes more important if we want to do an intermediate upgrade around local Ollama and larger local models before going further: weaker or less tool-savvy models tend to benefit more from deterministic, pre-attached skills than from open-ended "figure it out" prompting.

## Research Takeaways

- On October 16, 2025, Anthropic introduced Agent Skills as folders built around `SKILL.md` plus optional scripts and references. The key idea is progressive disclosure: only metadata loads first, and the full skill body loads when relevant.
- Anthropic's Claude Code subagent docs show that subagents can preload explicit skills, and the full content of each listed skill is injected into the subagent's context. Subagents do not inherit skills from the parent automatically.
- OpenAI's Codex product and skill catalog now treat skills as a first-class capability. OpenAI also separately recommends `AGENTS.md` for persistent repo context and team conventions.
- Vercel's January 27, 2026 evals found that `AGENTS.md` beat skills for broad, always-relevant framework knowledge, while skills worked better for narrower action-oriented workflows.

## Design Conclusion For ParaLLM

Use both layers, but for different jobs:

- `AGENTS.md` or equivalent shared memory:
  - repo-wide truth
  - architectural invariants
  - naming conventions
  - retrieval-first rules
  - output and review contracts
- Persona skills:
  - domain-specific review workflows
  - checklists
  - decision heuristics
  - failure modes
  - when-to-escalate rules

For ParaLLM, that means:

- keep universal project rules in shared memory
- attach 1 to 3 explicit skills to each advisor
- do not depend on auto-selection alone for local models
- keep each skill narrow and procedural

## Good Skill Design Rules

- Prefer vertical workflows over broad background knowledge.
- Keep `SKILL.md` lean; move bulky details into `references/`.
- Make each skill answer:
  - when to use it
  - what steps to follow
  - what artifacts to produce
  - what not to do
- Preserve contradiction instead of forcing consensus.
- Require evidence tags, line refs, and confidence labels where possible.
- Keep skills composable so multiple advisors can share the same foundation.

## Shared Foundation Skills

These should be reusable across most or all advisors.

| Skill | Purpose |
| --- | --- |
| `claim-calibration` | Separate fact, inference, assumption, and unknown. Force confidence labeling. |
| `evidence-ledger` | Record key claims, supporting evidence, counterevidence, and open gaps. |
| `line-ref-audit` | Require artifact refs, line refs, or source refs for conclusions that shaped the answer. |
| `retrieval-first-reasoning` | Check docs, code, or approved sources before leaning on stale priors. |
| `contradiction-preservation` | Preserve unresolved tensions instead of averaging them away. |
| `escalation-gates` | Define when the advisor should stop, flag uncertainty, or request another lane. |

## Persona Skill Assignments

These are the recommended primary skills for the current ParaLLM worker catalog.

| Persona | Recommended Skills |
| --- | --- |
| `Proponent` | `feasibility-breakdown`, `delivery-plan` |
| `Sceptic` | `failure-mode-analysis`, `assumption-buster` |
| `Economist` | `cost-envelope`, `roi-tradeoff-review` |
| `Security` | `threat-model`, `attack-path-review` |
| `Reliability` | `failure-domain-map`, `resilience-review` |
| `Concurrency` | `race-condition-hunt`, `shared-state-audit` |
| `Data Integrity` | `invariant-checker`, `corruption-path-review` |
| `Compliance` | `policy-and-terms-check`, `auditability-requirements` |
| `User Advocate` | `user-journey-friction`, `clarity-and-adoption-review` |
| `Performance` | `hotspot-triage`, `perf-experiment-design` |
| `Observability` | `telemetry-gap-finder`, `alertability-review` |
| `Scalability` | `capacity-envelope`, `fanout-stress-review` |
| `Recovery` | `rollback-plan`, `restore-test-review` |
| `Integrations` | `boundary-contract-check`, `dependency-risk-review` |
| `Abuse Cases` | `misuse-enumeration`, `rate-limit-and-control-review` |
| `Latency` | `latency-budget-review`, `critical-path-trim` |
| `Incentives` | `metric-gaming-check`, `incentive-alignment-review` |
| `Scope Control` | `scope-shrinker`, `hidden-complexity-surfacer` |
| `Maintainability` | `maintenance-burden-estimate`, `change-surface-review` |
| `Edge Cases` | `pathological-input-sweep`, `invariant-breaker` |
| `Human Factors` | `operator-error-analysis`, `handoff-friction-review` |
| `Portability` | `lock-in-detector`, `exit-plan-review` |
| `Privacy` | `data-minimization-review`, `retention-exposure-check` |
| `Product Strategy` | `thesis-check`, `demand-and-risk-framing` |
| `Governance` | `decision-rights-map`, `review-bottleneck-check` |
| `Wildcard` | `novel-angle-generator`, `outside-context-probe` |

## Skills To Build First

The first wave should bias toward cross-cutting usefulness rather than one-off specialization.

1. `claim-calibration`
2. `evidence-ledger`
3. `retrieval-first-reasoning`
4. `feasibility-breakdown`
5. `failure-mode-analysis`
6. `threat-model`
7. `cost-envelope`
8. `user-journey-friction`
9. `telemetry-gap-finder`
10. `rollback-plan`

That set covers the highest-value core advisors:

- `Proponent`
- `Sceptic`
- `Economist`
- `Security`
- `User Advocate`
- `Observability`
- `Recovery`

## Recommended Implementation Shape

If we add this to ParaLLM, the clean model is:

- shared repo context in `AGENTS.md`
- skill folders under a dedicated skills directory
- per-worker config field such as `skills: []`
- optional `preloadSkills: true` or equivalent for local/Ollama runs
- explicit review metadata showing which skills were attached to which advisor for each round

For local larger models, I would prefer:

- deterministic persona-to-skill mapping
- explicit preload for assigned skills
- no dependence on fuzzy automatic triggering for critical lanes

## OpenAI Skill Examples Worth Studying

These look like good pattern references from OpenAI's public skill catalog, even though most are external workflow skills rather than ParaLLM-native advisor skills:

- `security-threat-model`
- `security-best-practices`
- `gh-fix-ci`
- `gh-address-comments`
- `openai-docs`
- `playwright`
- `sentry`
- `linear`
- `notion-research-documentation`

## Practical Recommendation

Do not try to make every advisor unique on day one.

Start with:

- one shared foundation pack
- six to ten high-value domain skills
- explicit assignment to the current advisor roster
- a visible audit trail showing which skill influenced which lane

That gives us the upside of skills without turning the system into a giant prompt zoo.

## Sources

- Anthropic engineering: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Claude Code subagents: https://code.claude.com/docs/en/sub-agents
- OpenAI Codex usage guidance: https://openai.com/business/guides-and-resources/how-openai-uses-codex/
- OpenAI Codex app and skills: https://openai.com/index/introducing-the-codex-app/
- OpenAI public skills catalog: https://github.com/openai/skills
- Vercel evals on `AGENTS.md` vs skills: https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals
