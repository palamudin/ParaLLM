AI Loop Prototype for XAMPP / Windows
=====================================

What this is
------------
A local prototype scaffold for:
- Chat-first commander input where `Send` creates a task and kicks off the configured loop automatically
- Dynamic worker lanes that start with Proponent / Sceptic and can expand with more adversarial viewpoints
- Summarizer / canonical memory
- JSON persistence and event logging
- Autonomous multi-round execution
- Cross-process locking between PHP and the resident Python runtime
- Detached background loop execution through PHP
- Stale-job recovery for interrupted background runs
- Recent job and artifact history in the UI
- Per-position model selection
- Low / Mid / High / Ultra runtime profiles for opinionated cost-vs-depth presets
- Per-worker directive and temperature controls
- Session token / spend tracking with budget limits
- Optional grounded worker research with web-search controls
- Summarizer evidence vetting over worker research
- Dedicated Eval workspace with isolated per-run workspaces, suites, arms, and score artifacts
- Masked API key management through the UI
- Persistent commander draft state plus session reset / carry-forward archive support
- Resident Python runtime service so worker/summarizer logic stays warm between dispatches

Folder target
-------------
Copy the whole ai-loop-xampp folder into:
C:\xampp\htdocs\

Then browse to:
http://localhost/ai-loop-xampp/

Requirements
------------
- XAMPP / Apache / PHP enabled
- Python 3 available locally
- PHP process launching functions available locally
- Node is optional and only used for local JavaScript syntax checks if present

If process launching is disabled in php.ini
------------------------------------------
Check php.ini for disable_functions.
If functions like `shell_exec` or `popen` are listed there, remove them and restart Apache.

Main flow
---------
1. Open Home and type the prompt you want the lanes to investigate.
2. Optionally tweak Settings first:
   API key lives in `Settings / Integrations`.
   Runtime profiles, fine tuning, budgets, loop rounds, and research policy live in `Settings / Fine Tuning`.
   Home now also exposes the same runtime profiles in a compact `Quick profile` card so users can steer spend from the front dash.
3. Review the worker rail on Home:
   it starts with `Proponent` and `Sceptic`
   use `+ Add` to grow the adversarial roster
   use the per-worker controls to choose directive, temperature, and model
4. Press `Send`.
5. The app creates a task from the staged roster and automatically queues the configured loop.
6. Read the final Agent reply in Home. Use `Review` when you want the summarizer position trace, evidence lines, and saved artifacts.
7. Use `Debug` for manual controls such as `Run Round`, `Run Auto Loop`, `Summarize`, `Refresh`, `Reset Session`, `Cancel Loop`, or `Reset State`, and for reviewing/editing carry-forward `Session Context`.
8. Use `Review` for memory, jobs, artifacts, and side-by-side output inspection.
9. Use `Eval` when you want isolated benchmark runs, per-arm scoring, and side-by-side eval-artifact review without touching the live task workspace.

Main files
----------
- index.html               UI
- assets/app.js            frontend logic
- api/*.php                broker endpoints
- scripts/loop_runner.php  background loop runner
- scripts/qa_check.py      reusable lint + reversible mock smoke harness
- scripts/qa_live_check.py live-mode QA smoke with tight budgets and source allow-lists
- scripts/qa_eval_check.py isolated eval smoke for the sibling Eval subsystem
- scripts/quality_benchmark.py blind quality benchmark for direct-vs-steered answer comparison
- runtime/eval_runner.py   isolated eval batch runner
- runtime/*.py             resident Python runtime service and engine
- data/state.json          canonical state
- data/evals/              isolated eval suites, arms, runs, and artifacts
- data/sessions/*.json    archived session resets with carry-forward summaries
- data/events.jsonl        append-only event log
- data/outputs/*.json      dedicated saved worker/summarizer outputs for inspection
- data/jobs/*.json         background job metadata

QA workflow
-----------
Run the local verification harness from the repo root:

`python scripts/qa_check.py`

Run the live verification harness when you want a real model smoke:

`python scripts/qa_live_check.py`

Run the quality benchmark when you want to measure whether steered output actually beats a direct answer on the same prompt:

`python scripts/quality_benchmark.py`

Run the isolated eval smoke when you want to validate suites, arms, run manifests, and isolated eval artifacts:

`python scripts/qa_eval_check.py`

What it does:
- compiles the Python runtime files
- lints every PHP endpoint and runner script
- syntax-checks `assets/app.js` with Node if Node is installed
- checks that the local HTTP app is reachable
- runs a reversible mock smoke through `start_task.php`, `run_target.php` for `A`, `B`, and `summarizer`, and validates the saved adjudicated summary shape

What the live harness adds:
- skips cleanly if no API key is stored locally
- refreshes the resident Python runtime before the smoke unless told not to
- runs a reversible live `A/B/summarizer` smoke through the PHP endpoints
- caps the task budget and requested output tokens
- constrains worker web research to an allow-list of OpenAI-owned domains
- verifies the worker artifacts stayed on the live path and that their consulted/cited URLs stayed inside the allow-list

What the benchmark adds:
- generates a direct baseline answer with the same family of answer constraints
- runs a live steered multi-lane answer on the same case
- sends both public answers to a blind judge so the scorer does not know which one was steered
- scores decisiveness, tradeoff handling, objection absorption, actionability, single-voice quality, and overall quality
- separately scores whether the lead thread stayed in control of adversarial pressure instead of behaving like a funnel
- can sweep multiple loop depths in one run so extra rounds can be compared on both answer quality and lead-thread control
- fails fast by default if the supposed steered run silently falls back to mock output
- supports repeat trials per case and saves aggregate score deltas under `data/benchmarks/`

By default the QA script refreshes the resident Python runtime before the smoke so stale loaded code does not mask backend changes.
Useful flags:
- `--skip-smoke`
- `--skip-http`
- `--no-restart-runtime`
- `--base-url http://127.0.0.1/loop`

Useful live-smoke flags:
- `--skip-prechecks`
- `--no-restart-runtime`
- `--max-cost-usd 0.08`
- `--max-total-tokens 40000`
- `--allowed-domains openai.com,platform.openai.com,help.openai.com`

Useful benchmark flags:
- `--case sensitive-feature-launch`
- `--case core`
- `--repeats 3`
- `--loop-rounds 2`
- `--loop-sweep 1,2,3`
- `--keep-artifacts`
- `--allow-mock-fallback`

Current behavior
----------------
Workers support two modes:
- `mock`: local scaffolded reasoning output
- `live`: real model calls through the OpenAI Responses API

PHP now dispatches worker and summarizer targets through a resident Python service on `127.0.0.1:8765`.
That service keeps the runtime warm between calls and writes the same state, checkpoint, output, and step-log artifacts as before.
On Windows, detached background launches now use `cmd /c start` instead of a PowerShell shim, so the runtime no longer depends on `.ps1` worker scripts.
For live structured outputs, the Python runtime now treats very low `maxOutputTokens` values as a requested cap, not a trap:
- workers start with a safe floor of `900`
- summarizer starts with a safe floor of `1400`
- one retry is allowed at a higher cap if the Responses API returns `incomplete: max_output_tokens`
- requested and effective caps are both logged in `steps.jsonl` and saved output artifacts

When worker research is enabled, worker lanes can use the Responses API `web_search` tool, keep their own research queries and consulted source URLs, and leave evidence ledgers for the summarizer to vet.
When summarizer vetting is enabled, the summarizer scores the worker claims by support strength instead of only merging prose.
The loop preserves contradictions, step logs, and per-round checkpoint files.
Each worker and summarizer run also writes a dedicated output artifact so you can inspect returned content and response metadata without diffing canonical state.
The Artifact Review section can load those saved artifacts side by side and show both raw response text and normalized output.
Fresh artifacts now normalize and dedupe source URLs more aggressively so malformed non-URL strings do not pollute research-source lists.
The commander form is now draft-backed, so refresh polling no longer overwrites in-progress edits.
The stored draft now also carries the worker roster plus loop rounds and delay, so a page refresh does not wipe the staged lanes.
Settings now expose opinionated `Low`, `Mid`, `High`, and `Ultra` runtime profiles so users can snap models, reasoning effort, auto-loop depth, and budget ceilings into tested templates before fine-tuning manually.
Home now mirrors those profiles with a compact runtime card, a header profile pill, and a `Sync Active` action so the front dash stays usable without a trip into Settings.
Home chat polling now preserves scroll position instead of snapping back to the bottom on every refresh.
The Home thread is intentionally simplified: it shows the prompt and the summarizer's response in a more standard agent-chat style, while the internal adjudication trace now lives in `Review`.
The summarizer now treats the visible answer as a lead thought that privately absorbs adversarial pressure, instead of outputting a recap or consensus blend.
Review now also shows a control audit for the lead thread: its first-pass draft, the control question applied to adversarial pressure, which objections were accepted or rejected, what concerns were held out, and the final self-check before the answer was shown.
Eval now runs as a sibling subsystem instead of reusing the interactive singleton workspace. Suites live under `data/evals/suites`, arms live under `data/evals/arms`, runs materialize under `data/evals/runs/<runId>`, and each replicate gets its own isolated workspace root so hidden gold labels and score artifacts never leak into normal task state.
The Home worker rail can now add the next adversarial lane from a selectable template such as `Security`, `Economist`, or `User Advocate`.
Review now exposes recent job operations, round-history compare actions, session archive replay/export controls, and visible requested-vs-effective output-token cap metadata.
`Reset Session` writes an archive file under `data/sessions`, clears the active task, and preloads a short carry-forward summary into the `Session Context` field for the next task.
The backend also uses a shared lock so PHP and the resident Python runtime do not trample the same state file.
`Run Auto Loop` now returns quickly and a detached background runner continues the work while the UI polls state.
If a queued or running background job goes stale, polling endpoints will mark it as recovered, move it to `interrupted`, and expose it for `Resume` or `Retry` from Review.
History polling is read-mostly and stays available even if a recovery check has to be deferred briefly because the loop lock is busy.
The top bar shows the current masked API key, session tokens, web-search-call count, and estimated spend so you can control live testing costs without exposing the full secret in the browser.

Live verification note
----------------------
On April 18, 2026, the prototype was smoke-tested live with:
- grounded worker search restricted to OpenAI-owned domains
- summarizer evidence vetting enabled
- `gpt-5-mini` for workers and summarizer

On April 19, 2026, a widened live `A/B/C` run also completed successfully with:
- three live worker lanes plus a live summarizer
- grounded worker research and saved output artifacts in `data/outputs`
- a total estimated spend that stayed below the configured session cap

On April 19, 2026, the resident Python runtime was also verified with:
- a mock `A/B/summarizer` pass through the manual runtime endpoint, returning `backend: python`
- a live `A/B/summarizer` pass through the Python runtime, which matched the prior behavior by falling back to mock when the Responses API returned `incomplete: max_output_tokens`
- a later live `A/B/summarizer` pass with `maxOutputTokens=500`, which still completed live because the runtime lifted the effective caps and retried where needed
- a final release-validation pass through the send-style task + background-loop flow, where both a mock smoke and a live smoke completed end to end with a saved summary artifact
- a PowerShell-removal pass where manual dispatch and background launches still completed with the Python runtime as the only worker backend
- after intentionally killing the resident Python service, both manual dispatch and a 1-round live background loop successfully relaunched it

That run confirmed:
- worker `web_search` usage is captured in usage totals and per-target buckets
- worker checkpoints persist research queries, source URLs, and evidence ledgers
- summarizer checkpoints persist evidence verdicts and preserved conflicts
- summarizer outputs now persist a front-channel answer plus review-trace line references
- output-token recovery metadata is preserved in step logs and output artifacts
- the default chat path of `start_task` plus `start_loop` still works after the Home/Debug split and thread-renderer cleanup
- worker dispatch no longer depends on legacy PowerShell scripts or fallback paths

On April 19, 2026, `python scripts/qa_check.py` also passed locally after forcing a resident-runtime refresh, which confirmed:
- PHP, Python, and frontend syntax checks all passed in the current tree
- the reversible mock smoke returned `frontAnswer`, `summarizerOpinion`, `reviewTrace`, and `lineCatalog`
- the saved summary output artifact preserved the same adjudicated fields
- draft lane-template spawning carried a requested `Security` lane into the next started task
- current-session export, archive export, and archive replay all completed through the real PHP endpoints
- bounded queueing, queued-job cancellation, retry, and resume all completed through the real job-management endpoints

On April 19, 2026, `python scripts/qa_live_check.py` also passed locally with the default OpenAI-domain allow-list, which confirmed:
- the reversible live smoke stayed under the configured `$0.0800` estimated-spend cap at approximately `$0.031216`
- total live usage for that smoke was `29,471` tokens and `2` web-search calls
- worker and summary artifacts stayed on the live path
- worker research/citation URLs stayed within the OpenAI-owned allow-list

Pricing policy note
-------------------
As of April 19, 2026, OpenAI-owned pricing pages still conflicted about web-search content-token billing. This workspace now resolves that ambiguity with a conservative product policy: treat web-search-related model tokens as chargeable and keep the web-search tool-call component separately priced at `$10.00 / 1k calls`.

That means displayed spend should be read as a conservative operational estimate under the chargeable-search assumption, not as an attempt to guess the cheapest possible interpretation.

Next sensible step
------------------
Pressure-test the new lead-answer architecture on harder live prompts and tune how aggressively adversarial objections can narrow, redirect, or overturn the final answer before it starts sounding hesitant.
