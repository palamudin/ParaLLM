# ParaLLM Promo Pack

Use this page when you need grounded copy for GitHub, demos, posts, or a landing page without drifting away from what the repo actually proves today.

## One-Liner

ParaLLM is a local-first adversarial reasoning workspace that pressures one lead answer with structured counter-arguments before it reaches the user.

## Short Pitch

Most "multi-agent" demos are just extra API calls wearing a costume. ParaLLM is trying to make the pressure visible, inspectable, and testable.

Instead of one model pass, ParaLLM runs a lead thread, adversarial lanes, review, and a final answer path with traces, evals, and benchmark scaffolding around the whole loop.

## Hero Copy

### Option A

One answer. Real pressure behind it.

ParaLLM is a chat-first workspace for testing whether structured disagreement makes final answers more grounded, more calibrated, and more operationally useful.

### Option B

Structured disagreement for better answers.

ParaLLM runs a lead thread plus adversarial lanes, keeps the review trace visible, and turns multi-step reasoning into something you can inspect instead of merely trust.

### Option C

Not just multi-agent theater.

ParaLLM lets you run a proven V1 reasoning pipeline, build a modular V2 topology in parallel, and compare pressured answers against direct baselines with blind vetting.

## GitHub Blurb

ParaLLM is a local-first adversarial reasoning workspace with a proven V1 pipeline, an emerging modular V2 engine, side-by-side evals, blind vetting, provider-aware scheduling, and live OpenAI/Ollama runtime support.

## What Is Real Today

- `V1` is a confirmed runnable pipeline: `commander -> workers -> commander review -> summarizer`
- `V2` is a live modular engine track with draggable blocks, editable links, node-level controls, runtime inspection, and scheduler/event visibility
- the front shell supports independent `Live`, `Eval`, and `Judge` canvases
- side-by-side eval runs can compare pressured answers against direct baselines
- the scheduler now understands provider-aware dispatch and key-capacity pressure
- V1 and V2 both benefit from session-level Ollama timeout optimization
- Ollama can be benchmarked live per session with `Default`, `User set`, and `Auto` timeout modes
- per-node V2 timeout control supports `Session` or explicit `Override`
- review, artifacts, and scheduler state are visible in the UI instead of being buried in logs

## Proof Points

- latest public blind external vetting snapshot in the repo shows:
  - `ParaLLM 5.4 full | full adversarials` at `9.5`, winning best final answer and best tactical detail
  - `Direct GPT-5.4` at `9.0`, winning best value
  - `ParaLLM 5.4 full | mini adversarials` at `9.0`, strong second and shippable
  - `ParaLLM 5.4 mini | mini adversarials` at `8.5`
- V1 and V2 both completed live hosted Ollama runs with `summaryMode = live` after the session timeout policy work was applied
- the repo includes reusable QA harnesses for mock, live, eval, local tool, GitHub tool, and crossover smoke

## Launch Post

Built a serious new slice of ParaLLM.

It now has:
- a proven V1 reasoning engine
- a modular V2 topology you can drag, link, and inspect
- independent Live / Eval / Judge canvases
- provider-aware scheduling
- blind answer vetting
- live Ollama benchmarking with session-driven timeout tuning

The point is not to make a debate transcript. The point is to test whether structured pressure produces a better final answer than a direct one-shot baseline, and to make that process visible enough to trust or reject.

## Short Social Variants

### Variant A

ParaLLM is no longer just a prototype shell. It now has a proven V1 pipeline, a draggable V2 modular topology, side-by-side evals, blind vetting, and live OpenAI/Ollama runtime support.

### Variant B

The fun part of ParaLLM now is that V1 stays trusted while V2 becomes programmable. You can edit topology, inspect scheduler state, benchmark Ollama live, and compare pressured answers against direct baselines.

### Variant C

Multi-agent only matters if the pressure is real and inspectable. ParaLLM now has traces, evals, scheduler visibility, modular topology controls, and a proven fallback engine underneath it.

## Demo Walkthrough

1. Start in `Live` and run the proven `V1` engine so the user sees a normal chat-first answer flow.
2. Switch to `V2` and open the topology panel to show draggable modules, `IN / OUT` links, node controls, and runtime inspection.
3. Trigger `Eval` to run pressured vs direct side by side.
4. Show `Judge` as the isolated scoring lane rather than mixing evaluation into the answer path.
5. If using Ollama, run the session benchmark and show `Default / User set / Auto` timeout modes.
6. Open Review or the node modal to show artifacts, scheduler events, and the work-item ledger.

## Talk Track

ParaLLM is built around a simple claim: if adversarial pressure is structured instead of noisy, the final answer can improve. The repo now has one confirmed engine for that claim, one modular engine track for the next generation, and enough observability to stop pretending the process is magic.

## Boundaries

Use this promo honestly:

- ParaLLM is still a fast-moving prototype
- V1 is the confirmed path
- V2 is already interactive and scheduler-aware, but it is still on the road to becoming a fully independent engine
- the benchmark direction is promising, but the sample size is still growing
