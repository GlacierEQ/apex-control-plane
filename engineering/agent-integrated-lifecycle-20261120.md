# APEX agent lifecycle integration — 2026-11-20

## Owning implementation and provenance
- Repository: GlacierEQ/apex-control-plane; executable consumer: src/control_plane.py --exec-capability.
- Isolated integration branch based on 57bc57661602abd87e9e68b043db69d7658b37c0 (durable launch receipt bounded child reaping, gate FD cleanup, bounded drain).
- Reconciled stdin-delivery fail-closed behavior from f9f5592 and writer-liveness cancellation behavior from cb0f156; included actual stdin-delivery regression from a865b78. Cherry-pick conflict in OSError handler was manually resolved to preserve timeout cleanup evidence and input-delivery failure classification. No other owning workstreams touched.

## Practical behavior
- Zero-exit child with incomplete pinned stdin delivery cannot produce a success-classified receipt; exits with failure code 74.
- A stdin writer surviving bounded cancellation prevents success classification.
- Earlier durable launch receipt failure cleanup remains bounded, with gated child and FD cleanup protections retained.

## Changed-head verification
- macOS Apple Silicon /opt/homebrew/bin/python3.13; full repository pytest: 1124 passed, 29 skipped, 8 subtests passed in 15.39s.
- Focused capability/CLI/receipt suite: 36 passed; direct stdin-integrity and receipt-reap regressions: 3 passed.
- Python compileall succeeded; git diff --check clean.
- This is local native runtime verification, not production deployment or proof of automatic ChatGPT host invocation.

## Exact continuation cursor
- Independently read back GitHub integration branch and notes after push.
- Next: compare remaining writer branch changes (group signal denial, pending receipt preservation, timeout containment evidence) with this integrated candidate, bring over only nonregressing behavior, add adversarial combined receipt-failure/descendant-held-pipe test, run changed-head suite again.
- No merge, deployment, credentials, permissions, automation edits, external messages, or changes to Omni_Engine, memory, legal case or continuity workstreams.
