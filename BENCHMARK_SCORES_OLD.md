# Archived Benchmark Scores

This file preserves the pre-reset benchmark snapshot that was published before we proved some provider-owned runs were judged on fallback, placeholder, or otherwise incomplete payloads.

Status:
- archived on `2026-04-27`
- retained for research and historical context only
- not canonical for current README claims
- superseded by the live-only verification gate described in `README.md`

Why it was retired:
- some provider-owned judged runs were later shown, through the uncropped `Scores` surface, to include fallback or incomplete Para outputs
- that means the old published tables were useful as a milestone, but not strict enough for ongoing proof
- we now require complete live payloads from `direct` and final `summarizer` outputs before a score can be treated as publishable

Archived rollups:
- [summary_20260427_pre_verification_reset.json](data/benchmarks/vetting/_old/summary_20260427_pre_verification_reset.json)
- [latest_20260427_pre_verification_reset.json](data/benchmarks/vetting/_old/latest_20260427_pre_verification_reset.json)

Research note:
The archived runs still matter because they showed that the system could produce promising outcomes even before the scoring path was fully exposed and tightened. They should be read as historical signal, not current benchmark truth.
