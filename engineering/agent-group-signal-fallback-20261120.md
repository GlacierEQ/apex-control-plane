# Agent execution: denied group-signal fallback — 2026-11-20

Owner: GlacierEQ/apex-control-plane, `src/control_plane.py`, `--exec-capability`.

Recovered baseline: `engineering/agent-timeout-reap-bound-20261120`, commit `e10c2a1`, retaining launch-gate, bounded reaping, pending receipt and stdin-integrity corrections.

## Implemented
All three POSIX `os.killpg` cleanup sites now handle `PermissionError` by attempting direct-child `kill()` with missing/denied-child safeguards. Previously group-signal denial escaped cleanup and could prevent bounded wait and structured failure classification. This change does not claim to terminate descendants when group signaling is denied.

## Verification and limitations
- Real CLI adversarial injection `tests/test_control_plane_group_signal_denial.py`: group signal raises PermissionError; timed-out child receives direct termination; structured failure receipt, exit 124 and elapsed <3 seconds. 2 focused tests passed with existing timeout-reap regression.
- Existing capability consumer isolated rerun: 20 passed.
- Initial full Python 3.13 suite: 1125 passed, 29 skipped, 1 failed, 1 error, 8 subtests passed. The two failures were in capability consumer; isolated rerun passed 20/20. Full-suite rerun needed to distinguish environmental interference.
- Group-signal denial cannot guarantee containment of descendant processes. No merge or deployment.

## Exact continuation
Rerun full Python 3.13 suite against this branch without concurrent tests, inspect the capability consumer failures if repeated, then test denial on durable launch-receipt failure with a descendant holding inherited pipes. Keep other four workstreams untouched.
