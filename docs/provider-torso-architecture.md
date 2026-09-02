# ParaLLM Provider Torso Architecture

Status: implemented and parity-verified

Decision date: 2026-09-01

## Decision

ParaLLM has one provider/model process factory. A lane supplies variables; it does
not select or instantiate a bespoke provider arm.

```text
lane request
  provider + model + auth route + reasoning + tools + endpoint settings
      |
      v
canonical provider/model contract
  deployment defaults + role defaults + route defaults
      |
      v
resolved lane process
  canonical model + transport + endpoint + effective reasoning + capabilities
      |
      v
wire-protocol codec
      |
      v
vendor call
```

The source of truth is
[`contracts/provider-models.v1.json`](../contracts/provider-models.v1.json).
It owns:

- provider identity, defaults, credential environment names, and aliases;
- default worker and judge providers plus each provider's normal and judge auth
  routes;
- model identity, labels, auth routes, live-validation status, and pricing;
- transport and endpoint selection per auth route;
- model capability overrides and accepted reasoning levels;
- data-driven alternate protocol routes where a provider exposes more than one
  compatible API.

Worker, summarizer, direct-baseline, and judge selections all enter this same
contract. Each role contributes only variables: provider, model, auth route,
reasoning effort, tool request, and optional endpoint settings. No runtime may
maintain a second handwritten provider, model, endpoint, auth, or capability
list.

## Browser Projection

Both browser shells load `/v1/models` before hydrating staged run state. The
active shell is [`assets/replacement-shell.js`](../assets/replacement-shell.js);
the retained legacy shell is [`assets/app.js`](../assets/app.js). They derive
from that response:

- visible provider buttons and provider selectors;
- worker and summarizer model options;
- distinct API-key and current-user Codex choices for shared OpenAI model IDs;
- transport metadata, display order, labels, and abbreviated control labels.
- deployment-default and judge-default provider fallbacks.

The HTML contains only loading placeholders. It does not contain a fallback
provider/model inventory. Codex account-limit discovery is telemetry only and is
not permitted to mutate the runtime catalog.

## Python Runtime

[`runtime/provider_torso.py`](../runtime/provider_torso.py) resolves a
`ResolvedLaneProcess` from the lane variables. The result is immutable and
contains the complete execution decision:

- provider;
- canonical model;
- auth route;
- transport;
- endpoint;
- effective reasoning effort;
- model capabilities;
- allowed tool and response-include behavior.

The normal dispatcher in [`runtime/engine.py`](../runtime/engine.py) resolves this
descriptor once. It then passes the same descriptor to a protocol codec. Codecs
exist only where wire formats genuinely differ:

- OpenAI Responses and current-user Codex Responses;
- xAI Responses;
- OpenAI-compatible Chat Completions;
- Anthropic Messages;
- local Ollama JSON.

A codec is not a provider arm. It serializes one declared protocol and parses its
response. Provider choice, model choice, endpoint choice, reasoning constraints,
and tool eligibility have already been decided by the torso.

## Native Runtime

[`deployment/dev/build.py`](../deployment/dev/build.py) compiles the same JSON
contract into two generated C headers:

- `para_provider_catalog_generated.h` supplies models, aliases, capabilities,
  auth masks, routes, transports, and endpoints;
- `para_auth_catalog_generated.h` supplies provider labels, default models, and
  credential environment names;
- `para_provider_defaults_generated.h` supplies normal and judge provider,
  auth-route, model, and credential defaults for fresh native state and CLI
  probes.

The native executable therefore exposes the same contract through `/v1/models`
and `/v1/auth` without embedding parallel handwritten catalogs. Its single
`para_lane_profile_resolve` factory receives the same provider, model, auth,
reasoning, and tool variables before selecting a wire codec. Ollama remains a
declared Python/local transport and is omitted from native until native declares
and implements that protocol; the omission is explicit rather than a fallback.

## Extension Rules

### Add a model

Add one model row to the canonical contract. Rebuild native and run parity. No
Python or C routing branch is permitted.

### Add a provider using an existing protocol

Add the provider, auth route, endpoint, model rows, and capability defaults to the
canonical contract. The existing codec receives the resolved process. No new arm
is permitted.

### Add a genuinely new protocol

Add one protocol codec, map the provider route to it in the canonical contract,
and keep all provider/model policy outside the codec. Both runtimes must expose
the same normalized result contract before the route is accepted.

### Add an endpoint override

Declare its setting or environment name in the contract. Base URL overrides are
merged with the canonical endpoint path by the resolver. Provider-specific URL
helpers are not permitted in the orchestration engine.

## Release Invariants

1. Every declared model resolves through the same factory for every permitted
   auth route.
2. Undeclared provider/auth and model/auth combinations fail before transport.
3. Aliases resolve to canonical model IDs before dispatch and persistence.
4. Reasoning is clamped by declared model capability, never guessed in a codec.
5. Python's exposed catalog equals the canonical contract.
6. Native's exposed catalog equals the native-applicable subset of the same
   contract.
7. Native auth defaults and credential names equal the contract.
8. The native build manifest hashes the exact contract and both generated
   catalogs plus the generated deployment-default header.
9. There is no silent provider, model, endpoint, protocol, or auth fallback.
10. Browser provider/model controls are generated from `/v1/models`; account
    telemetry cannot create runtime options.
11. Fresh Python and native state derive normal and judge defaults from the
    contract; command-line probes do not embed provider or model literals.

The executable parity gate is
[`scripts/qa_provider_contract_parity.py`](../scripts/qa_provider_contract_parity.py).

## Verification Evidence

The 2026-09-01 parity run reported:

- 56/56 canonical models exposed by Python;
- 52/52 native-applicable models exposed by native;
- six native provider/auth definitions;
- zero model, auth, label, capability, default, schema, or build-hash mismatches;
- 140 focused torso/catalog/control/dispatch/eval tests passed;
- all 502 backend tests passed;
- 33 native-core, torso, and model-catalog tests passed;
- all 48 native concurrent state operations and all durability, evidence,
  integrity, and restart invariants passed.

Native build `51897c675402e82a` also initialized a clean database with the
contract-derived normal route (`openai`, `codex_current_user`, `gpt-5.6-sol`)
while exposing the distinct judge default (`openai`, `api_key`, `gpt-5.4`).

Post-refactor live runs completed all four orchestration stages on both Python and
native for OpenAI, DeepSeek, xAI, and MiniMax. Anthropic reached the correct API
and returned its account-credit rejection; Kimi reached the correct API and
returned its five-hour quota rejection. Those are external account states, not
router substitutions or malformed internal responses.
