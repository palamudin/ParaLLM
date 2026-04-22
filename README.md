# ParaLLM

![Status](https://img.shields.io/badge/status-prototype-orange)
![Platform](https://img.shields.io/badge/platform-local%20%2B%20Docker-0ea5e9)
![UI](https://img.shields.io/badge/UI-Bootstrap%205-7952b3)
![Runtime](https://img.shields.io/badge/runtime-Python%20control%20plane-3776ab)
![Reasoning](https://img.shields.io/badge/reasoning-adversarial%20lane%20stack-22c55e)

Local-first adversarial reasoning workspace for testing whether structured disagreement can improve final answers.

Instead of asking one model for one pass, ParaLLM runs a lead thread plus adversarial lanes, preserves disagreement at checkpoints, and lets the final answer be shaped by pressure rather than narrated as a debate recap.

## Why This Exists

Most "multi-agent" demos are really just wrappers around extra API calls. This project is trying to answer a harder question:

> Can a lead answer become meaningfully more grounded, more calibrated, or more robust when it is pressured by structured adversarial viewpoints before it reaches the user?

The current prototype is built to make that test inspectable:

- a normal-looking front chat
- a review surface with internal traces, line refs, and artifacts
- an isolated eval workspace for blind direct-vs-steered comparisons
- explicit cost controls, loop controls, and runtime profiles

## What It Does

- Chat-first workflow where `Send` creates a task and starts the configured loop
- Commander-first runtime evolving toward: `commander -> workers -> commander review -> summarizer`
- Dynamic adversarial worker roster starting from `Proponent` and `Sceptic`
- Summarizer-guided dynamic adversarial lane spin-up for the next round when a missing viewpoint survives review
- Review-only control audit showing accepted, rejected, and held-out objections
- Isolated eval subsystem for side-by-side benchmark runs
- Read-only local file tools for commander and worker lanes with allow-root policy and audit logs
- Read-only GitHub repo tools for commander and worker lanes with owner/repo allowlist and audit logs
- Provider-grouped API key pools with deterministic per-position assignment per vendor
- Container-friendly secret backends via provider-isolated env keys or mounted secret files
- Initial multi-provider runtime slice:
  - OpenAI remains the full-featured path
  - Ollama now works as a native local structured-output path
  - workers and summarizer can be assigned different providers
- Reversible QA scripts for mock, live, and eval smoke tests

## Architecture

```mermaid
flowchart LR
    U[User Prompt] --> C[Commander Draft]
    C --> A[Worker A]
    C --> B[Worker B]
    C --> D[Worker N]
    A --> S[Summarizer / Lead Merge]
    B --> S
    D --> S
    S --> F[Front Answer]
    S --> R[Review Trace + Artifacts]
```

### Design Rules

- The user-facing answer should read like one assistant, not a debate transcript.
- All adversarial lanes should receive the same user objective.
- Session memory is background context, not authoritative truth.
- Contradictions should remain visible in review artifacts.
- Cost should be controlled, but not by starving the primary reasoning path of user context.

## Stack

| Layer | Tech |
| --- | --- |
| Control plane | Python ASGI backend |
| Runtime | Resident Python service |
| Self-host packaging | Docker Compose Python stack |
| Frontend | HTML, jQuery, local Bootstrap 5.3, custom CSS |
| Storage | Local JSON / JSONL artifacts |
| Model path | OpenAI Responses API + native Ollama `/api/chat` |
| QA | Python harnesses + JS syntax check |

## Project Layout

```text
.
|-- .agents/                advisor skill pack and persona-to-skill map
|-- AGENTS.md               shared advisor conventions for repo-aware agents
|-- backend/                Python-first control plane
|-- assets/                 frontend JS, CSS, vendored Bootstrap
|-- deploy/                 Docker Compose stack and container images
|-- runtime/                reasoning engine + eval runner
|-- scripts/                QA harnesses and benchmarks
|-- data/                   local state, checkpoints, outputs, jobs, evals
|-- index.html              app shell
|-- project.md              running architecture notes / product log
`-- README.md               repo front door
```

The advisor skill pack is written as vendor-neutral `SKILL.md` content. The `agents/openai.yaml` files are optional Codex metadata; other runtimes can ignore them and still use the skills.

Current skill layers:

- Shared advisor skills under `.agents/skills/`:
  - `claim-calibration`
  - `evidence-ledger`
  - `feasibility-breakdown`
  - `failure-mode-analysis`
  - `threat-model`
  - `cost-envelope`
  - `user-journey-friction`
  - `telemetry-gap-finder`
  - `rollback-plan`
- Provider/runtime skills for live vendor paths:
  - `provider-openai-responses`
  - `provider-anthropic-messages`
  - `provider-xai-responses`
  - `provider-minimax-compatible`
  - `provider-ollama-local-json`
- Persona-to-skill assignment lives in `.agents/persona-skill-map.json`, so advisor lanes can stay vendor-neutral at the core while still picking the right runtime guidance when the active model/provider changes.

## Current Feature Set

### Reasoning Surface

- Commander-first orchestration with explicit round alignment
- Dynamic worker lanes with named personas like `Security`, `Economist`, `User Advocate`, `Reliability`, and more
- Per-worker directive, model, temperature, and harness controls
- Summarizer/lead-thread control audit:
  - lead draft
  - integration question
  - accepted objections
  - rejected objections
  - held-out concerns
  - self-check

### UI

- Chat-first `Home`
- Compact runtime profile controls on the front dash
- Collapsible admin-style sidebar
- Review workspace for trace/artifact inspection
- Eval workspace for isolated benchmark runs
- Settings surface for key-pool and runtime management

### Runtime / Ops

- Detached background loop execution
- Shared lock discipline between the Python control plane and worker subprocesses
- Stale-job recovery
- Output artifact persistence for every worker and summary pass
- Read-only local workspace inspection via `local_list_dir`, `local_read_file`, and `local_search_text`
- Read-only GitHub inspection via `github_list_paths`, `github_read_file`, `github_get_issue`, `github_get_pull_request`, and `github_get_commit`
- Secret-shaped files are filtered from retrieval listings and blocked from direct local/GitHub reads by default
- Local/GitHub tool audit in step logs, worker checkpoints, and artifact metadata
- Summarizer-driven next-round lane requests with audited worker spawn events
- Budget, token, and estimated-spend tracking
- Requested-vs-effective output-token cap visibility

### Eval / QA

- Blind direct-vs-steered benchmark harness
- Control-quality grading for lead-thread discipline
- Isolated eval runner with per-replicate workspaces
- Reusable QA scripts for:
  - mock smoke
  - live smoke
  - isolated eval smoke
  - local file tool smoke
  - GitHub tool smoke
  - dynamic lane spin-up smoke

## Quick Start

### Requirements

- Python 3
- Node optional, only for JS syntax checks
- Docker optional for the self-host stack

### Install

Install dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Portable local bring-up:

```bash
python scripts/run_local_stack.py
```

Then open:

```text
http://127.0.0.1:8787/
```

### Python Control-Plane Scaffold

The repo now includes the active Python control plane under `backend/`.

It now covers:

- state/history/review reads
- auth status and key mutation
- draft save and task creation
- session reset / replay / export
- worker/runtime mutation
- eval launch
- loop/job control
- background target dispatch
- Python-served shell defaults at `/` and `/index.html`

The Python-served shell is now the primary local path.

Install and run it from the repo root:

```bash
python -m pip install -r requirements-dev.txt
python scripts/run_local_stack.py
```

Then check:

```text
http://127.0.0.1:8787/
```

Deployment/topology introspection now lives at:

```text
http://127.0.0.1:8787/v1/system/topology
```

Infrastructure readiness now lives at:

```text
http://127.0.0.1:8787/v1/system/infrastructure
```

### Initial Multi-Provider Slice

Milestone 5 is now started with a real first provider split:

- `openai`
  - full current path
  - structured Responses execution
  - web search and audited local/GitHub tools
  - key-pool rotation and managed-secret backends
- `ollama`
  - native `/api/chat` execution
  - structured JSON output path
  - local-model experimentation without OpenAI keys
  - local function-tool loop for file/GitHub tools
- `anthropic`, `xai`, `minimax`
  - provider-native live adapters are wired now
  - capability normalization depends on the provider path
- auth/settings groundwork
  - provider-grouped key storage now exists for `openai`, `anthropic`, `xai`, and `minimax`
  - provider pools stay isolated; one vendor's lanes never reuse another vendor's key group
  - runtime/provider routing now switches the live call path as well as the key lane group

Current honest limitation:

- Ollama is available as a live structured-output provider with local function tools, but it does **not** support hosted web-search research in this repo
- workers currently inherit the global runtime provider, while the summarizer/lead-thread provider can be set separately
- Anthropic, xAI, and MiniMax are live runtime paths now, but capability differences are normalized conservatively and will keep evolving as provider docs and model behavior change
- eval arms, result artifacts, and the blind benchmark now carry provider identity so mixed-provider experiments can be inspected honestly in Review instead of being inferred from model names alone
- Milestone 5 is not complete until more providers and richer capability normalization land

If you still want the optional compatibility runtime service in the same local session:

```bash
python scripts/run_local_stack.py --with-runtime-service
```

### Docker Self-Host Path

The repo now also includes a first containerized bring-up path under `deploy/`.

It packages the active Python stack:

- `backend`: Python ASGI shell + control plane on `:8787`

Bring it up with:

```bash
docker compose -f deploy/compose.yml up --build
```

Then open:

```text
http://127.0.0.1:8787/
```

For a hosted-dev dependency shape, the repo also includes:

```bash
docker compose -f deploy/compose.hosted-dev.yml up --build
```

Hosted-dev with a dedicated runtime container:

```bash
docker compose \
  -f deploy/compose.hosted-dev.yml \
  -f deploy/compose.hosted-dev.runtime-service.yml \
  up --build
```

Portable handoff bundle for a Docker-capable rig:

```bash
python scripts/package_hosted_bundle.py
```

That compose file declares:

- `postgres`
- `redis`
- `minio`

The deploy env contract lives in `.env.example`, and the portability smoke is:

```bash
python scripts/qa_portability_check.py
```

The hosted-dev proof smoke is:

```bash
python scripts/qa_hosted_dev_stack.py
```

It is intentionally non-fake: it fails immediately if Docker is missing, otherwise it boots the hosted-dev compose stack and verifies Redis, Postgres, MinIO, mounted secrets, background loops, and artifact persistence through the live API and backing services.

That topology contract now makes the current single-node shape explicit:

- queue backend
- metadata backend
- artifact backend
- secret backend
- runtime execution backend

The runtime execution backend is now selectable:

- `embedded_engine_subprocess` for the default Python-only local stack
- `runtime_service` when you intentionally want the backend to dispatch target execution over the separate runtime service boundary

The queue backend is now partially real too:

- `local_subprocess` keeps the existing JSON-and-subprocess scheduling path
- `redis` now owns background loop ordering and ready target-dispatch launch handoff

The metadata backend has also crossed the line from “declared” to “real”:

- `json_files` remains the local default
- `postgres` now owns shared control-plane state, job metadata, task snapshots, and eval run state across both the FastAPI backend and the runtime engine
- events, steps, and eval manifests still remain filesystem-backed for this phase

The artifact backend is now partially real too:

- `filesystem` remains the local default
- `object_storage` now owns runtime checkpoints, saved output artifacts, session archives, and export bundles, and Review/history reads the runtime artifacts back through the same adapter
- eval run manifests still remain filesystem-backed for this phase

The secret backend is now hosted-aware too:

- local development now defaults to `LOOP_SECRET_BACKEND=env`
- provide newline-delimited keys in `LOOP_OPENAI_API_KEYS`, `LOOP_ANTHROPIC_API_KEYS`, `LOOP_XAI_API_KEYS`, or `LOOP_MINIMAX_API_KEYS`
- or set `LOOP_SECRET_BACKEND=docker_secret`
- or set `LOOP_SECRET_BACKEND=external` with `LOOP_SECRET_PROVIDER_URL`
- and mount a newline-delimited key file at `LOOP_SECRET_FILE` such as `/run/secrets/openai_api_keys`
  - sibling files like `/run/secrets/anthropic_api_keys`, `/run/secrets/xai_api_keys`, and `/run/secrets/minimax_api_keys` are used for those provider groups
- `local_file` remains available only as an explicit transitional fallback
- managed backends are now authoritative: if `env`, `docker_secret`, or `external` is empty or unreachable, live execution fails visibly instead of silently drifting into another secret source

### First Run

1. Open `Settings / Integrations`
2. Prefer setting the provider env vars you actually plan to use before launch, especially `LOOP_OPENAI_API_KEYS` for the current full-featured live path
3. If you explicitly start with `LOOP_SECRET_BACKEND=local_file`, paste keys into the matching provider group cards in Settings
4. Pick a runtime profile in `Home` or `Settings`
5. Write a prompt in `Home`
6. Press `Send`
7. Inspect `Review` if you want the internal adjudication trace

## Local API Key Pool

ParaLLM still supports local key pools through the UI, but only when you explicitly run with `LOOP_SECRET_BACKEND=local_file`.

- One provider card per vendor group
- One key slot per input row inside that provider group
- `+ Key` adds another slot
- Pasting into a stored slot replaces it immediately
- Pasting into a new slot appends it to the matching local fallback file such as `Auth.txt`, `Auth.anthropic.txt`, `Auth.xai.txt`, or `Auth.minimax.txt`
- `Clear` wipes the local pool

Assignment behavior:

- default order is `commander -> workers in letter order -> summarizer`
- assignments only draw from the selected provider's pool; there is no cross-vendor API key bleed
- if there are fewer keys than positions, slots wrap
- when wrapping is required, the starting slot rotates across rounds so one key does not always take commander-first traffic
- if a live lane hits an auth-style key failure, the runtime now retries on the next non-empty key in pool order before giving up
- if the active backend is managed and exposes no usable keys, live lanes fail loudly instead of downgrading to mock behind your back

Only masked previews are shown in the UI. Raw keys stay in provider-specific env vars for `env`, provider-specific mounted files for `docker_secret`, grouped payloads for `external`, or local fallback files only when `local_file` is explicitly selected as a transitional path.

## Usage Flow

### Home

- Write the prompt
- Stage worker lanes
- Pick a cost/depth profile
- Send once and read a single front-channel answer

### Review

- Inspect line refs and evidence shaping
- Compare round artifacts side by side
- Resume / retry / replay where applicable

### Eval

- Run isolated benchmark suites without contaminating live task state
- Compare direct vs steered outputs
- Inspect quality and control scores per replicate

## QA Commands

From the repo root:

```bash
python scripts/qa_check.py
python scripts/qa_live_check.py
python scripts/qa_eval_check.py
python scripts/qa_local_tools_check.py
python scripts/qa_github_tools_check.py
python scripts/qa_dynamic_spinup_check.py
python scripts/qa_supply_chain_check.py
python scripts/qa_container_check.py
python scripts/qa_python_crossover_check.py
python scripts/quality_benchmark.py
python -m unittest backend.tests.test_storage backend.tests.test_control backend.tests.test_metadata backend.tests.test_queueing backend.tests.test_artifacts backend.tests.test_jobs backend.tests.test_dispatch backend.tests.test_settings backend.tests.test_sessions backend.tests.test_evals backend.tests.test_infrastructure backend.tests.test_runtime_auth backend.tests.test_runtime_execution backend.tests.test_app
```

CI baseline:

- Python version is declared in `.python-version`
- Node version is declared in `.nvmrc`
- Deployment Python dependencies are pinned in `requirements-ci.txt`
- CI/developer Python dependencies are installed from `requirements-dev.txt`
- GitHub Actions QA lives in `.github/workflows/ci.yml`
- Dependabot updates GitHub Actions and pip manifests through `.github/dependabot.yml`
- Runtime browser dependencies are local-only; jQuery is vendored under `assets/vendor/jquery`

Supply-chain checks:

```bash
python scripts/qa_supply_chain_check.py
```

Container packaging checks:

```bash
python scripts/qa_container_check.py
```

Security baseline:

- `SECURITY.md` documents reporting expectations and the current hardening posture
- `pip-audit` now runs as part of the repository supply-chain check
- workflow actions are pinned to full commit SHAs
- browser runtime dependencies are local-only instead of pulled from a public CDN

Useful flags:

```bash
python scripts/qa_check.py --skip-smoke --no-restart-runtime
python scripts/qa_live_check.py --max-cost-usd 0.08 --max-total-tokens 40000
python scripts/quality_benchmark.py --case core --repeats 3 --loop-sweep 1,2,3
```

Internal hardening:
- `LOOP_FAULT_POINTS` can inject targeted dispatch/loop failures for repeatable recovery tests, for example `dispatch.execute.before_runtime.commander` or `loop.execute.before_target.commander`.

## Benchmark Philosophy

The project is not trying to prove that "more agents" is automatically better.

It is trying to measure whether:

- contradiction detection improves
- uncertainty is preserved better
- tradeoff handling is stronger
- the final answer is better enough to justify the extra burn

If steered output does not beat a direct baseline often enough, the logs and eval traces should make that failure obvious.

## Roadmap

The local stability gate is now closed:

- the true separate path completed 5 clean live 2-round runs without hanging
- next-round spawned workers activated correctly in round 2
- the async dispatch path also passed after the same alignment fixes

The next phase is productization for an online-capable offering.

Next milestone track:

- `Dynamic Lane Polish`
  - make spawned personas more deliberate, less duplicate, and more legible in Review
- `Deployment Portability and Online Packaging`
  - keep the stack Python-first and define the first hosted deployment shape
  - harden the Docker/self-host path so local and hosted deployments share one control plane
- `Secrets, Security, and Controlled Retrieval`
  - move beyond plaintext-only local key handling toward safer storage and hosted retrieval
- `Prototype Hardening`
  - add stronger error handling, typing discipline, test coverage, and recovery verification
- `Multi-Provider Model Abstraction`
  - add Grok, Claude, Gemini, and local runtimes through Ollama or LiteLLM
- `Review Surface and Frontend Architecture`
  - improve review visualization and split the frontend into more maintainable modules
- `Cost Governance Without Betraying the Thesis`
  - keep burn visible and enforceable without starving adversarial lanes of full user context

## Known Tradeoffs

- This architecture can burn tokens fast by design.
- Full-context adversarial lanes are a feature, not a bug.
- Summarizer quality still depends heavily on harness tuning and output-cap recovery.
- The Docker path now packages the Python-served shell and control plane directly.
- The Python control plane owns auth-key mutation, draft/task writes, runtime/worker settings, session/export/replay mutations, eval launch, loop/job control, and target dispatch.
- The primary app path is `http://127.0.0.1:8787/` or the backend container on the same port.
- The repo and runtime now operate without the legacy web-server stack.
- The system is inspectable enough to teach us where it helps, but not yet mature enough to call "production."

## Safety / Local Data

- `Auth.txt`, `Auth.anthropic.txt`, `Auth.xai.txt`, and `Auth.minimax.txt` are local-only and must never be committed
- `data/` contains volatile runtime state and artifacts
- review artifacts may include sensitive prompt material
- displayed spend is an operational estimate, not invoice truth
- provider terms vary; pooling multiple LLM providers into adversarial or cross-provider orchestration can violate some providers' ToS or acceptable-use rules and may lead to suspension, rate limits, key revocation, or other sanctions
- this project cannot certify that multi-provider adversarial usage is compliant with any provider's terms, and operators are responsible for their own provider-review, legal/compliance sign-off, and deployment choices before wiring together multiple providers or user-supplied keys

## Repo Hygiene

Things already in place:

- volatile runtime outputs ignored in `.gitignore`
- isolated eval store under `data/evals/`
- local vendored frontend dependencies
- reusable verification scripts

## Contributing

This repo is still moving like a fast prototype, but good contributions are welcome if they preserve the core ideas:

- keep the front answer clean and single-voice
- keep internal pressure inspectable
- do not silently erase contradictions
- prefer measurable architecture changes over vibe-driven complexity

If you change runtime behavior, run the QA scripts and say what changed in reasoning quality, control quality, or cost.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the short repo workflow.

## Current Direction

The next serious tuning work is not more surface polish. It is:

- better commander/worker/summarizer merge discipline
- harder blind eval cases
- stronger failure handling when the live summarizer hits output limits
- GitHub/local-file tooling for cheaper structured review than raw paste + repeated context

## Status

This is a real prototype, not a finished product.

It already supports live runs, evals, review traces, runtime profiles, and adversarial lane shaping. The open question is not whether it works at all. The open question is where it is genuinely worth the extra reasoning pressure and spend.
