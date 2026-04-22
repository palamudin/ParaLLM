# TODO

## BYOK Deployment Plan
Source: `t-20260421-182136-0060cd`
Updated from final summarizer output at `data/outputs/t-20260421-182136-0060cd_summary_round001_output.json`

### Go/No-Go Gates
- [ ] Confirm which providers explicitly allow delegated end-user-key orchestration.
- [ ] Define a strict provider and model allowlist for v1 instead of allowing arbitrary upstreams.
- [ ] Turn provider delegated-use / ToS review into a formal compliance gate before beta.
- [ ] Decide whether the hosted product promise can support the minimum logging and abuse-response retention required for safety.
- [ ] Write a go/no-go checklist that can stop launch if provider terms are unclear or unsupported.
- [ ] Treat open beta as out of scope until the invite-only path proves manageable under hostile use.

### Secrets And Key Isolation
- [ ] Split the hosted architecture into app tier, key broker, and execution workers.
- [ ] Ensure plaintext keys never live in the main app tier, logs, traces, analytics, admin tools, tickets, or support tooling.
- [ ] Store only ciphertext plus provider metadata outside the broker; use opaque key handles everywhere else.
- [ ] Decrypt only inside short-lived sandboxed workers over mTLS.
- [ ] Zero secrets after use and verify the wipe path under failure conditions.
- [ ] Add audit events for key create, key use, key revoke, and key rotation without storing plaintext.

### Abuse And Safety Controls
- [ ] Ship per-tenant spend caps, quotas, concurrency limits, and request-size caps on day 1.
- [ ] Add model allowlists and tool/network allowlists; ban arbitrary outbound tools in v1.
- [ ] Require verified accounts and manual approval for the first beta cohort.
- [ ] Add IP/device throttles, anomaly scoring, suspension controls, and an operator kill switch.
- [ ] Build redaction into logs, traces, exports, and support views by default.
- [ ] Default-deny new tenants until verification and risk checks pass.
- [ ] Fail closed on any policy or risk check, not just auth failures.
- [ ] Keep metadata retention minimal by default and document any abuse-response exceptions explicitly.
- [ ] Assume malicious use arrives immediately and test the platform under that assumption.

### Reliability And Failure Behavior
- [ ] Validate BYOK credentials at onboarding and re-check them safely when possible.
- [ ] Fail closed on expiry, revocation, quota exhaustion, or provider auth errors.
- [ ] Surface tenant-specific key and provider failures clearly instead of collapsing into generic runtime errors.
- [ ] Separate provider outages from bad-key failures in UX, logs, and alerts.
- [ ] Retry only safe and idempotent calls after provider or transport failures.
- [ ] Isolate noisy tenants so bad keys or abuse spikes do not poison other tenants.
- [ ] Keep support unable to view secrets while still allowing session disable, revoke, and forced re-entry flows.
- [ ] Train support to never request, paste, or handle raw customer keys.
- [ ] Alert on key-broker failures, worker-sandbox violations, and abuse events as first-class incidents.
- [ ] Design explicitly for provider drift and user-visible instability caused by revoked or broken customer keys.

### Rollout Plan
- [ ] Start with internal dogfood.
- [ ] Keep the first external step invite-only with low caps and no external actions.
- [ ] Expand to a handful of vetted design partners only after the invite-only path is stable.
- [ ] Require manual abuse review throughout beta.
- [ ] Run incident drills before wider launch.
- [ ] Block wider launch until plaintext-key leakage paths are proven shut, abuse volume is manageable, provider allowlist decisions are settled, and key-failure rates are acceptable.
- [ ] Stop launch immediately if any shared service or staff workflow can access raw keys.

### Additional Follow-Up From Lane Pressure
- [ ] Add a dedicated compliance / provider-ToS adversarial lane for BYOK planning prompts.
- [ ] Treat delegated-use and provider operating commitments as hard invalidators, not just soft caveats.
- [ ] Make it explicit in product/docs that BYOK shifts billing exposure more than platform liability.
- [ ] Preserve the stable finding that BYOK is only viable as a narrow orchestration product, not a broad open-ended platform surface.
