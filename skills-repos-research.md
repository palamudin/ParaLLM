# Skills Repos Research

Research date: April 22, 2026

## What I Looked For

- Repos that use `SKILL.md` as a real operating primitive, not just a prompt dump
- Evidence of orchestration, harnessing, packaging, or evaluation
- Cross-agent portability for Codex / Claude Code / Cursor / OpenCode / related runtimes
- Signs of community adoption or discussion, including X

## Shortlist: Best Repos To Study

### 0. `VoltAgent/awesome-agent-skills`

Link: https://github.com/VoltAgent/awesome-agent-skills

Why it matters:

- As of April 22, 2026, it has about 17.4k GitHub stars
- It is one of the largest curated cross-agent catalogs, with 1000+ skills from vendor teams and the community
- It is useful as a map of the ecosystem and a fast way to see which domains have serious adoption

What to study:

- category structure
- which vendors are publishing official skills
- how community curation distinguishes official/team skills from one-off hobby entries
- contribution standards that try to filter out low-signal additions

Evidence:

- The README describes it as a hand-picked collection of official and community skills, not an AI-generated dump.
- The contribution guidance explicitly says they are focusing on community-adopted skills, especially those published by development teams and proven in real-world usage.

What not to copy:

- the mega-catalog shape itself
- the idea that more skills is automatically better

Notes:

- Best used as a discovery index
- Not the thing we should mirror into ParaLLM

### 1. `openai/skills`

Link: https://github.com/openai/skills

Why it matters:

- Best Codex-native reference point
- Explicitly positions skills as instructions, scripts, and resources for repeatable tasks
- Has curated and experimental folders, plus installer support

What to study:

- skill structure
- how OpenAI separates system, curated, and experimental skills
- what belongs in a reusable skill versus repo-level context

Evidence:

- The repo says Codex uses skills to package capabilities for repeatable tasks.
- The repo exposes install paths for `.system`, curated, and experimental skills.

Notes:

- Great baseline for Codex compatibility
- Less interesting for multi-agent orchestration than some community repos

## 2. `anthropics/skills`

Link: https://github.com/anthropics/skills

Why it matters:

- Still the canonical public reference implementation for the broader Agent Skills ecosystem
- Strongest source of mature `SKILL.md` examples
- Includes both example skills and production-like document skills

What to study:

- progressive disclosure patterns
- examples vs production-grade skill complexity
- how partner/platform skills are documented

Evidence:

- The repo states skills are folders of instructions, scripts, and resources loaded dynamically for specialized tasks.
- It includes examples across design, technical, enterprise, and document workflows.

Notes:

- Best place to learn content design
- Not the best place to copy orchestration architecture directly

## 3. `cloudflare/skills`

Link: https://github.com/cloudflare/skills

Why it matters:

- Best vertical productized skills repo I found
- Combines contextual skills, slash commands, and MCP servers in one coherent package
- Strong example of how a platform company teaches agents a full ecosystem

What to study:

- the split between commands, skills, and MCP servers
- large platform coverage without one bloated generic skill
- contextual auto-load wording

Evidence:

- The repo ships commands, skills, and MCP server integrations together.
- Skills cover platform-wide guidance plus specific areas like `agents-sdk`, `durable-objects`, `sandbox-sdk`, and `wrangler`.

Notes:

- This is one of the closest matches for what a serious packaged agent capability looks like
- High-value reference for ParaLLM if we want advisor skills plus optional tool integrations

## 4. `mxyhi/ok-skills`

Link: https://github.com/mxyhi/ok-skills

Why it matters:

- Best practical cross-agent curated repo
- Focuses on immediate usefulness instead of just spec purity
- Includes both skills and `AGENTS.md` playbooks

What to study:

- small high-value skill packaging
- install-and-go repo layout under `.agents/skills`
- curation strategy across docs lookup, planning, browser, CI, design, and office workflows

Evidence:

- The repo currently bundles dozens of reusable skills and vendored packs.
- It explicitly targets Codex, Claude Code, Cursor, OpenClaw, and related SKILL.md-compatible tools.

Notes:

- Strong repo to borrow from selectively
- Better source of “what should we actually install first?” than giant catalogs

## 5. `gannonh/kata` and the archived `gannonh/kata-orchestrator`

Links:

- https://github.com/gannonh/kata
- https://github.com/gannonh/kata-orchestrator

Why it matters:

- Best orchestration-heavy open-source example in this survey
- Treats skills as part of a broader spec-driven harness instead of isolated add-ons
- Spans CLI, orchestrator, desktop, context system, and headless workflow execution

What to study:

- discuss / plan / execute / verify workflow
- fresh-context execution in subagents
- ticket-to-PR orchestration via Symphony
- skills as one layer inside a larger runtime

Evidence:

- `kata` describes a headless orchestrator that dispatches parallel agent sessions and manages a full PR lifecycle.
- `kata-orchestrator` was updated to become Agent Skills spec compliant and inlined skill resources into spawned subagent prompts.

Notes:

- Probably the single most relevant orchestration repo for ParaLLM
- Heavyweight; copy ideas, not the whole framework

## 6. `ynulihao/AgentSkillOS`

Link: https://github.com/ynulihao/AgentSkillOS

Why it matters:

- Best research-driven repo for retrieval and orchestration at ecosystem scale
- Focuses on finding and composing skills instead of hand-picking a tiny set
- Strong match for future ParaLLM ideas around dynamic skill routing

What to study:

- skill tree retrieval
- DAG-based skill orchestration
- human-in-the-loop workflow control
- benchmark framing

Evidence:

- The repo focuses on discovering, composing, and running skill pipelines end to end.
- It claims a curated skill pool, pluggable retrieval/orchestration modules, GUI control, and benchmark support.

Notes:

- Great architecture inspiration
- Probably too heavy for the first local-Ollama upgrade

## 7. `numman-ali/n-skills`

Link: https://github.com/numman-ali/n-skills

Why it matters:

- One of the stronger community attempts at a portable marketplace
- Includes an explicit `orchestration` skill and multi-agent workflow positioning
- Good example of packaging across multiple agents

What to study:

- repo taxonomy
- workflow-category skills
- how orchestration is presented as a reusable installable unit

Evidence:

- The repo positions `SKILL.md` as the universal skill format and `AGENTS.md` as the universal discovery file.
- The listed `orchestration` skill is described as multi-agent orchestration.

Notes:

- Promising, but I would treat it as a pattern source rather than a gold standard

## 8. `803/skills-supply`

Link: https://github.com/803/skills-supply

Why it matters:

- Not a skill library so much as skill infrastructure
- Best repo I found for package management and multi-agent syncing
- Useful if we eventually want a reproducible way to ship persona skills across Codex/Claude/OpenCode installs

What to study:

- `agents.toml`
- auto-discovery rules
- sync model across different agents

Evidence:

- It supports package manifests, skill auto-discovery, and syncing to enabled agents.
- It understands plugin packages, subdirectory packages, and single-skill packages.

Notes:

- More ops/distribution than skill content
- Worth studying after the first batch of ParaLLM skills exists

## 9. `troykelly/codex-skills`

Link: https://github.com/troykelly/codex-skills

Why it matters:

- Strong example of Codex-specific workflow hardening
- Uses hooks, MCP, helper scripts, and AGENTS.md alignment around an issue-driven workflow

What to study:

- hook runner approach for Codex
- issue-driven development as a skill pack
- AGENTS.md + skills + MCP as one enforced workflow

Evidence:

- The repo ports a large hook set into Codex via `codex-hook-runner`.
- It explicitly instructs projects to align `AGENTS.md` with the skill pack and treat skills as mandatory when relevant.

Notes:

- More workflow/governance than persona expertise
- Good source for harness enforcement patterns

## 10. `jdrhyne/agent-skills`

Link: https://github.com/jdrhyne/agent-skills

Why it matters:

- Good example of a mixed practical library with actual orchestration skills
- Includes compatibility thinking across OpenClaw, Claude Code, and Codex

What to study:

- `planner`
- `parallel-task`
- `task-orchestrator`
- trust and portability labeling

Evidence:

- The repo says 79% of skills work across all supported platforms.
- It includes `parallel-task` and `task-orchestrator` as explicit multi-agent coordination skills.

Notes:

- Smaller and more opinionated than giant catalogs
- Worth mining for concrete orchestration procedures

## Repos Worth Browsing, But With Caution

### `sickn33/antigravity-awesome-skills`

Link: https://github.com/sickn33/antigravity-awesome-skills

Why browse it:

- Huge searchable catalog
- bundles, workflows, installer, official/community sources

Caution:

- very large
- mixed licenses
- curation quality may vary
- better as a discovery index than as a repo to blindly import from

### `hesreallyhim/awesome-claude-code`

Link: https://github.com/hesreallyhim/awesome-claude-code

Why browse it:

- strong map of the broader ecosystem
- includes skills, hooks, slash commands, and orchestrators

Caution:

- list repo, not a vetted skill implementation repo

### `letta-ai/skills`

Link: https://github.com/letta-ai/skills

Why browse it:

- good example of living shared knowledge and peer-reviewed skills
- includes agent-development, benchmarks, fleet-management, and webapp-testing

Caution:

- more Letta-centric than Codex-centric

### `encoredev/skills`

Link: https://github.com/encoredev/skills

Why browse it:

- strong vertical example for backend development skills
- useful model for framework-specific persona packs

Caution:

- narrow domain

## X Signals

### Signal 1: skills are becoming infrastructure, not just prompts

X itself now publishes a live `skill.md` page for the X API and exposes discovery endpoints for agents:

- https://docs.x.com/tools/skill-md

That is a strong ecosystem signal: `skill.md` is moving from community convention toward platform-facing capability contracts.

### Signal 2: skill management is becoming its own product category

X posts from Tessl and other builders point in the same direction:

- skills are getting hard to manage as static copied markdown
- teams want registries, versioning, install/update flows, and evaluation

Relevant links:

- https://x.com/tessl_io/status/2016938081555804272
- https://x.com/aiwithjainam/status/2036744727131996518

### Signal 3: people are converging on content-design patterns

Several X threads now focus less on file format and more on what belongs inside `SKILL.md`, especially progressive disclosure and moving bulky detail into references:

- https://x.com/Pluvio9yte/status/2036134125804130312
- https://x.com/kkk_cun/status/2035926571299852412

### Signal 4: cross-agent portability is now a selling point

Launch posts increasingly advertise “works with Claude Code, Codex, Cursor, OpenCode, Gemini CLI” rather than one harness only:

- https://x.com/encoredotdev/status/2013241413161324582

## What Online Comments Around VoltAgent Suggest

### 1. Big catalogs are best for discovery, not for loading wholesale

An April 2026 roundup called VoltAgent one of the best large curated libraries, but still recommended installing one or two focused collections instead of everything at once.

Source:

- https://ai.joaoqueiros.com/blog/best-claude-skills-repositories-april-2026

### 2. Most people only keep a few skills in daily use

A Reddit post from April 2026 said many installed skills were eventually removed because they failed to trigger correctly, introduced delays, or reduced output quality. The author kept only a small number of focused vendor skills.

Source:

- https://www.reddit.com/r/aiagents/comments/1sntzml/i_tried_a_bunch_of_agent_skills_these_are_the/

### 3. Pointer-style browsing is safer than bulk import

An OpenClaw listing built around VoltAgent describes the right pattern as a pointer skill that teaches the agent how to search the catalog and fetch one target skill, explicitly avoiding wholesale import because of supply-chain risk.

Source:

- https://openclawlaunch.com/skills/awesome-agent-skills

### 4. VoltAgent is becoming a de facto ecosystem index

A recent Reddit visualization project used VoltAgent as the base dataset for mapping hundreds of skills by topic cluster and authoring team. That suggests the repo is becoming the default map of the ecosystem, even if it is not the best runtime dependency.

Source:

- https://www.reddit.com/r/AgentSkills/comments/1sqzu2t/i_mapped_907_agent_skills_into_a_3d_latent_space/

### 5. Even pro-skill writeups say to install from vendor repos

One April 2026 article explicitly said VoltAgent is great for discovery, but most entries are links rather than installable source-of-truth files, so you should browse there and install from original vendor repos instead.

Source:

- https://aiallthethings.com/articles/claude-code/official-skills-stripe-cloudflare-best-practices-one-file

## What Actually Seems To Work

Based on repo stars plus public commentary, the pattern that keeps showing up is:

- use mega-catalogs to discover proven vendors and domains
- do not load giant numbers of skills into one runtime
- prefer vendor-maintained skills over anonymous one-offs
- keep the always-on set very small
- use pointer/browser skills or retrieval when the catalog is large
- rewrite external patterns into one house style instead of inheriting dozens of incompatible voices

## What This Means For ParaLLM

The best models in the community right now are not “one giant skill repo” and not “one giant prompt.”

They are:

- a small shared context layer (`AGENTS.md`, repo memory, or equivalent)
- a curated pack of narrow, high-value skills
- optional harness/orchestration rules on top
- visible packaging and install paths
- some notion of validation, trust, or compatibility

## My Recommendation

For ParaLLM, I would borrow in this order:

1. Content design patterns from `anthropics/skills`
2. Codex-native packaging instincts from `openai/skills`
3. Productized platform structure from `cloudflare/skills`
4. Practical curation from `mxyhi/ok-skills`
5. Orchestration ideas from `gannonh/kata`, `AgentSkillOS`, and `jdrhyne/agent-skills`
6. Distribution ideas later from `skills-supply`

## Best Near-Term Fit For Your Current Plan

If the next move is “upgrade ParaLLM with persona skills before the bigger bigrig step,” the most relevant repos are:

- `VoltAgent/awesome-agent-skills` as the discovery map
- `openai/skills`
- `anthropics/skills`
- `cloudflare/skills`
- `mxyhi/ok-skills`
- `gannonh/kata`
- `jdrhyne/agent-skills`

That set is the best balance of:

- quality
- portability
- orchestration relevance
- practical reuse
- Codex compatibility

## Scratch-Build Conclusion

For ParaLLM, we should not import VoltAgent wholesale.

We should:

1. Use VoltAgent as a discovery layer for high-signal vendor and community patterns
2. Read the original upstream skills that look proven
3. Rewrite the useful parts into our own advisor skills from scratch
4. Keep the first ParaLLM skill pack small, opinionated, and internally consistent
