# APEX integrated launch-receipt uncertainty preservation — 2026-11-20

Owning source: `src/control_plane.py --exec-capability`, derived from tested integrated lifecycle head `10e650c`. Existing writer-liveness, input-integrity, bounded reaping, drain, and gate cleanup preserved.

## Operational correction
If the durable `launched_unverified` receipt replacement fails after initial `pending_unverified` creation, the executor now retains the original pending receipt rather than attempting a second final replacement. A one-shot injected `os.replace` failure (where a subsequent replacement would succeed) proves the fail-closed behavior: gated command never runs; exit 2; initial pending receipt remains. This closes an uncertainty-evidence overwrite path, not just a persistent filesystem failure case.

## Acceptance and proof
- One-shot and persistent launch-receipt failure CLI regressions: 2 passed.
- Native macOS Python 3.13 full repository suite: 1125 passed, 29 skipped, 8 subtests passed in 14.63 seconds; exit 0.
- `git diff --check` clean.
- Local native runtime proof only, not deployment or ChatGPT host integration proof.

## Exact continuation
Reconcile remaining group-signal denial and descendant-held-pipe evidence tests with this integrated branch, preserving stronger protections. Test adversarial receipt-failure with surviving pipe holder and denied killpg, then full suite and provider readback. No merge, deployment, permissions, credentials, external messages, or automation edits authorized.
