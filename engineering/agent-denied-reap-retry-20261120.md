# Agent execution: denied reaping retry — 2026-11-20

Owner: GlacierEQ/apex-control-plane, `src/control_plane.py`, `--exec-capability`.

## Recovered baseline
`engineering/agent-group-signal-fallback-20261120`, preserving integrated lifecycle, pending launch receipt, bounded drains, stdin integrity, timeout reaping and group-signal-denial fallback. Original full suite intermittently failed in different tests; an isolated `--basetemp` rerun completed **1127 passed, 29 skipped, 8 subtests passed** in 17.56 seconds.

## Executable correction
Both bounded second-attempt `child.kill()` calls (launch receipt failure and execution deadline expiry) now tolerate `ProcessLookupError` and `PermissionError`, just as the first direct-child fallback does. Previously the retry could escape and interrupt structured failure cleanup if the OS denied signaling or the process vanished between wait and retry. The final bounded wait is still attempted. This is fail-closed cleanup, not proof of descendant containment.

## Verification and continuation
Focused signal-denial and timeout-reap tests: 2 passed. Full changed-head Python 3.13 suite in isolated `--basetemp`: **1127 passed, 29 skipped, 8 subtests passed in 16.95 seconds**. GitHub source readback confirmed the first guarded retry at blob `daf38f5dfee7cb39b02d5ed1133c01d440a42c98`. Next: adversarial second-kill denial and descendant-held-pipe integration regression, then reconcile any failures. No merge/deployment, credentials, permissions, other automation edits, or external messages.
