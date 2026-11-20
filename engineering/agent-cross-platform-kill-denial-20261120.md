# Agent execution: non-POSIX kill-denial cleanup (2026-11-20)

Owner: `GlacierEQ/apex-control-plane`, executable `src/control_plane.py`, `--exec-capability`.

## Recovered baseline and defect
Recovered branch `engineering/agent-denied-reap-retry-20261120` at `857f799`, with integrated launch-gate, receipt preservation, bounded reaping, stdin integrity, drain deadlines, and POSIX group-signal-denial fallback. The initial direct `child.kill()` on non-POSIX launch-receipt failure and execution timeout remained unguarded. A denied signal or process-exit race could escape the bounded reap and structured failure cleanup, unlike the POSIX and second-attempt paths.

## Changed executable
Both non-POSIX first-attempt kills now tolerate `ProcessLookupError` and `PermissionError`, allowing the already-bounded wait/retry and failure classification to continue. No authorization, launch gate, receipt, or success criteria were weakened. This is cross-platform failure handling, not a claim of Windows runtime verification.

## Verification and exact continuation
Python 3.13 Mac POSIX focused real-CLI tests: 4 passed (group denial, receipt failure variants, descendant output drain). Full changed-head Python 3.13 suite: **1127 passed, 29 skipped, 8 subtests passed in 38.89 seconds**, isolated `--basetemp=/tmp/glaciereq-agent-run11-full`; native output `/tmp/glaciereq-agent-run11-full.log`. Non-POSIX denied-kill injection on Windows remains required. Continue with combined second-kill denial and descendant-held-pipe adversarial tests, then native Windows boundary testing. No merge, deployment, credential/permission, external-message, Linear creation or automation changes.
