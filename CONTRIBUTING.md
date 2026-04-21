# Contributing

Thanks for helping on ParaLLM.

This project is still a fast-moving prototype, so the goal is not process for its own sake. The goal is to keep changes testable, inspectable, and honest about tradeoffs.

## Ground Rules

- Keep the user-facing answer clean and single-voice.
- Keep internal pressure visible in review artifacts.
- Do not silently erase contradictions.
- Prefer measurable improvements over architectural ornament.
- Do not commit secrets, local runtime artifacts, or benchmark leftovers.

## Before You Change Runtime Behavior

If your change affects orchestration, prompting, merge logic, output caps, evals, or pricing assumptions:

1. say what changed
2. say why it should improve quality, control, reliability, or cost-awareness
3. run the relevant checks
4. note any regressions or unresolved risks

## Recommended Checks

```bash
python scripts/qa_check.py
python scripts/qa_live_check.py
python scripts/qa_eval_check.py
python scripts/quality_benchmark.py
```

Use the lighter pass when appropriate:

```bash
python scripts/qa_check.py --skip-smoke --no-restart-runtime
```

## PR Expectations

A good change usually includes:

- a short problem statement
- the architectural intent
- what files/modules were touched
- how you verified it
- any remaining caveats

## Docs

If behavior changes, update the docs with it:

- `README.md` for repo-facing behavior
- `project.md` for architecture/product notes

## Security / Local Data

- `Auth.txt` is local-only
- `data/` is volatile
- output artifacts may contain sensitive prompt material

If a change touches secrets, auth handling, or artifact retention, call that out explicitly.
