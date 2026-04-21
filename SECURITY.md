# Security Policy

## Scope

This repository is still prototype software, but we want the supply-chain and secret-handling posture to move toward hosted-product standards as early as possible.

## Reporting

If you find a vulnerability, do not open a public issue with exploit details.

Report it privately to the maintainers through the repository security advisory flow if enabled, or through a private maintainer contact channel.

## Current Security Baseline

- Runtime browser dependencies are vendored locally instead of pulled from public CDNs at page load.
- GitHub Actions workflow dependencies are pinned to full commit SHAs.
- Python deployment dependencies are pinned in `requirements-ci.txt`.
- Python CI/developer dependencies live in `requirements-dev.txt`.
- `pip-audit` is part of the repository supply-chain check.
- Dependabot is configured for GitHub Actions and pip manifests.
- Local and GitHub retrieval tools now block secret-shaped files by default and filter them from directory listings.

## Known Prototype Constraints

- Local fallback secrets can still exist in `Auth.txt` when `local_file` is explicitly selected.
- Local JSON/JSONL state is still the main persistence layer.

These are active roadmap items, not final design decisions.

## Local Secret Handling

- Never commit real API keys.
- Prefer `env`, `docker_secret`, or `external` backends over `local_file`.
- Treat `Auth.txt` as local-only developer fallback state, not the preferred path.
- When a live call hits an auth-style key failure, the runtime rotates to the next non-empty key in the pool before surfacing final failure.
- Managed backends are authoritative: empty or unreachable `env`, `docker_secret`, or `external` sources now stop live execution instead of silently falling through to another secret source or mock output.
- Rotate any key immediately if it appears in logs, artifacts, screenshots, or pushed commits.

## Update Policy

- Keep workflow actions pinned to full SHAs.
- Use Dependabot PRs to review GitHub Actions and pip updates.
- Run `python scripts/qa_supply_chain_check.py` before rollout-sensitive changes.
