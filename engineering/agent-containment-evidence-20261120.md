# Agent execution: explicit descendant containment uncertainty (2026-11-20)

Owner: GlacierEQ/apex-control-plane, src/control_plane.py, --exec-capability.

Recovered branch engineering/agent-cross-platform-kill-denial-20261120 at ed4d98d, preserving all earlier bounded reap, durable receipt, stdin delivery, group-signal fallback and output-drain behavior.

Executable change: record denied POSIX process-group signaling across launch-receipt failure, execution timeout, and descendant-held output-drain timeout. A final failure receipt now exposes group_signal_denied=true and descendant_containment_verified=false, rather than leaving the unresolved descendant containment invisible. Null means not established, NOT verified. This is diagnostic truthfulness, not a guarantee of descendant cleanup.

Focused Mac Python 3.13 tests: group signal denial and descendant pipe deadline, 2 passed in 2.64s. Full changed-head Mac Python 3.13 suite: 1127 passed, 29 skipped, 8 subtests passed in 50.22s; output /tmp/glaciereq-containment-full.log. Native Windows kill-denial and combined second-kill denial remain unverified. No merge or deployment.

Next: inspect full-suite output, correct any regression, independently read back pushed source, and add controlled descendant process cleanup verification under signal denial.
