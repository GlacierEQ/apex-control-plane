# Agent cleanup resolution — 2026-11-20

Owner: `GlacierEQ/apex-control-plane`, `src/control_plane.py`, `--exec-capability`.

Previous head: `f6ad15660a59c57543c7cbe7488dac6fb26d4e89`.

Change: expose `cleanup_unresolved` and `output_drains_unresolved` in the actual final execution receipt. The aggregate is fail-closed when the direct child remains unreaped, an output drain or stdin writer is still alive, or group signaling was denied. This prevents schedulers from mistaking a bounded cleanup attempt for verified resource release. It does not assert descendant containment.

Acceptance: denied-group real CLI reports unresolved cleanup even when direct child is reaped; normal completion does not spuriously report unresolved cleanup; full Python 3.13 suite passes. No merge or deployment.

Continuation: integrate with actual scheduler receipt consumption only after source-native consumer recovery, then add combined descendant-held-pipe/second-kill-denial adversarial scenarios and native Windows verification. Keep receipt semantics distinct from proof of full process-tree containment.

Verification: changed-head Python 3.13 full suite `1127 passed, 29 skipped, 8 subtests passed` (18.93s); focused capability-consumer and signal-denial suite `21 passed`; changed signal-denial regression `1 passed`. The full-suite run preceded the final assertion-only test edit, which was independently rerun; no executable source changed after the full-suite run.
