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

## Follow-up exact-head verification
Second full-suite attempt: 1125 passed, 29 skipped, 1 failed, 1 error, 8 subtests passed (18.35s). The failed test shifted to `test_control_plane_stdin_delivery_integrity.py::test_full_context_pipe_delivery_retains_successful_exit`; the error shifted to `test_control_plane_timeout_reap_bound.py::test_timeout_path_never_uses_unbounded_child_wait`. Both affected test files immediately passed in isolation (3/3). The first full-suite run's affected capability-consumer file likewise passed in isolation (20/20). This pattern suggests shared test-environment interference or test-order sensitivity, not a proven root cause. Full-suite green is NOT claimed. Investigate shared test artifacts, process state and concurrent runs; rerun in an isolated temporary environment.
