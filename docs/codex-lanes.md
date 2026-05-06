# Codex Lanes

ParaLLM can use Codex as a specialist lane without making Codex the whole orchestration brain.

The first supported shape is a read-only OpenAI-family Codex agent arm around `codex exec --json`. Para owns the run contract, budget, merge gates, and artifact retention. Codex receives a bounded packet, returns a compact advisor artifact, and Para decides whether that artifact changes the public answer, the implementation plan, or the next verification step.

This is intentionally not just "use a Codex model as another worker model." The Para provider family remains OpenAI, while the arm provider is the local Codex automation surface. That gives Para a route for Codex-style repo-aware work without pretending the VS Code extension UI itself is a stable backend API.

## Lane Roles

- `codex_commander`: repo-aware planning and synthesis lane.
- `codex_adversarial`: read-only pressure lane for design, code, and operational weaknesses.
- `codex_reliability`: test, rollback, security, and production-readiness lane.
- `codex_builder`: future write-capable lane, only after isolated worktree ownership and merge locks are in place.

The initial adapter is intentionally read-only. Write-capable Codex lanes should use separate worktrees, explicit file ownership, patch artifacts, and merge review.

## Execution Contract

The low-level adapter can run Codex non-interactively:

```text
codex exec --json --ignore-user-config --ephemeral --disable plugins --disable general_analytics --sandbox read-only --cd <repo> --model <model> --output-schema <schema> -
```

The prompt is passed through stdin, not embedded into a shell command. The process is launched without `shell=True`, and Windows runs request `CREATE_NO_WINDOW` so the live UI does not spawn visible command windows. The adapter ignores user-level Codex config by default so automation lanes do not inherit UI plugins, personal MCP servers, or plugin sync failures.
The lane also disables Codex plugins and general analytics because plugin marketplace/cache calls are unrelated to a Para advisor lane and can fail before model execution.

The Para-facing arm route is `/v1/codex/lanes/run`. That route currently defaults to:

- `providerFamily`: `openai`
- `provider`: `codex_cli`
- `interface`: `codex_cli_exec`
- `sandbox`: `read-only`
- `useUserConfig`: `true`
- `disablePlugins`: `true`

So the first operator-triggered arm uses local Codex auth/config like the local Codex agent surface, but still keeps plugins disabled until there is an explicit MCP/plugin allowlist for Para lanes.

Each raw lane artifact includes:

- `laneId`
- `provider`: `codex_cli`
- `model`
- `status`
- `threadId`
- `responseText`
- `usage`
- `limits`
- `warnings`

The default structured-output schema is strict: every declared field is required and extra fields are rejected. Optional lane data should be represented as empty arrays or empty strings, not omitted keys.

The persisted Para artifact wraps that raw lane output with `artifactType: codex_lane`, `providerFamily`, `arm`, `input`, `output`, `usage`, `limits`, and `warnings`. It is written to `data/outputs` so Review/history tooling can consume it like other Para outputs.

## Usage And Cost

Codex JSONL exposes `turn.completed` events with token usage. The adapter normalizes these fields into the existing Para usage vocabulary:

- `inputTokens`
- `cachedInputTokens`
- `billableInputTokens`
- `outputTokens`
- `reasoningTokens`
- `totalTokens`
- `estimatedCostUsd`

Reasoning tokens are treated as part of output token burn. This matches OpenAI's Responses guidance: reasoning tokens are not visible as raw chain of thought, but they occupy context space and are billed as output tokens.

Pricing is a local estimate, not a billing source of truth. The current adapter carries a small Codex pricing snapshot for known Codex models so local budgets can trip quickly during experiments. Billing truth should come from provider usage exports or OpenAI organization usage APIs.

Current bare-metal smoke result, using `gpt-5.4` through the Para wrapper on this repo, completed with `21,649` input tokens, `2,432` cached input tokens, `91` output tokens, and a local estimated model cost of `$0.050015`. That is the practical floor to account for: even a tiny Codex lane can carry a large repo/context bootstrap, so Codex specialist lanes should be reserved for tasks where repo-aware pressure materially changes the decision.

## Limits

There are two different limit classes:

- Local Para budget limits: `maxTotalTokens`, `maxCostUsd`, timeout, and sandbox.
- Provider/account limits: RPM, TPM, daily limits, usage caps, and tier limits.

The CLI JSONL stream gives observed usage, but it does not expose authoritative account or project rate limits. For strict production accounting, direct API adapters should capture response headers and/or query the OpenAI project rate limit APIs. Until then, Codex lane artifacts mark provider limits as unknown.

The adapter has two budget gates:

- Preflight: estimate prompt tokens and block obviously oversized prompts before launching Codex.
- Post-run: mark the artifact `budget_exhausted` if observed usage crosses the local Para run contract.

Post-run enforcement cannot recover already-spent tokens. It exists so the operator and scheduler can stop follow-on lanes, not to pretend the spend never happened.

## Settings Plane

The replacement shell exposes Codex as `Settings -> Codex agent arm`.

The card separates evidence classes instead of blending them:

- `ChatGPT auth detected`: presence-only `CODEX_HOME/auth.json` check; token contents are not read.
- `Local catalog loaded`: values from Codex `models_cache.json`, including context and reasoning support.
- `Docs snapshot`: static public model caps and tier rows for known Codex/OpenAI models.
- `Manual account snapshot`: operator-entered general and model-specific quota values from Codex settings.
- `Measured smoke`: latest Para wrapper smoke usage and local estimated cost.

Account-level usage bars and project-specific RPM/TPM limits are not emitted by `codex exec --json`. The Settings card therefore includes a compact manual JSON editor that saves to `data/codex_limits.json` through `/v1/codex/limits/manual`. This is intentionally labeled manual until a direct organization/project usage API path can prove those values.

The Settings card also includes an operator-triggered read-only smoke button. It posts to `/v1/codex/lanes/run`, confirms token spend before launch, and reports the saved artifact filename. It is not automatic scheduler behavior yet.

## Source Notes

- OpenAI Codex non-interactive mode documents `codex exec --json`, JSONL event usage, `--output-schema`, and API-key auth for automation: https://developers.openai.com/codex/noninteractive
- OpenAI pricing lists Codex model token prices and tool costs: https://developers.openai.com/api/docs/pricing
- OpenAI reasoning guidance explains reasoning token accounting, `max_output_tokens`, and incomplete responses: https://developers.openai.com/api/docs/guides/reasoning
- OpenAI project rate limit APIs expose per-project model request and token limits: https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/projects/subresources/rate_limits

## Next Slice

Promote Codex commander/adversarial/reliability lane selection into the Run contract, with queue locks, lane labels, Settings-side limit warnings, artifact review shortcuts, and an explicit plugin/MCP allowlist before any write-capable builder lane exists.
