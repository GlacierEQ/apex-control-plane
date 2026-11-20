# Agent receipt-failure bounded reaping — 2026-11-20

## Source and ownership
- Owner: `GlacierEQ/apex-control-plane`, `src/control_plane.py`, real `--exec-capability` consumer path.
- Base: `65c4ac2` on `engineering/agent-receipt-failure-bounded-drain-20261120` (including gate FD cleanup and bounded drain on receipt failure).
- Scope: distinct agent subprocess lifecycle reliability; no changes to Omni_Engine, structured memory, legal cases, continuity, or automations.

## Operational correction
- On durable launched-receipt write failure, SIGKILL and `child.wait()` previously had an unbounded wait, despite bounded stdout/stderr joins. An uninterruptibly stuck child could indefinitely hold the parent in failure cleanup.
- Reaping now has a one-second bound, a second kill attempt, and a 300 ms final bound. Existing process-group termination, gated execution, incomplete-output and writer protections remain unchanged.
- Real CLI fault injection uses `sitecustomize` to reject the launched receipt atomic replacement. It verifies the command never runs, the pending-unverified receipt remains, and the CLI returns promptly.

## Verification
- Python 3.13 changed-head focused consumer/drain suite: 21 passed.
- Python 3.13 real CLI injected launched-receipt failure: 1 passed.
- Python 3.13 changed-head full suite including new test: 1122 passed, 29 skipped, 8 subtests passed.
- `compileall` and `git diff --check` passed.
- No production deployment, merge, credential, permission or automation changes.

## Continuation cursor
- Independently read back branch and source through GitHub after push.
- Next: investigate pathological child reaping under actual uninterruptible kernel I/O (not reproducible with ordinary subprocess), and reconcile writer-liveness/drain branches in an isolated integration candidate before merging with explicit approval.
- No claim that a synthetic fault-injection test establishes production host-level reliability.
