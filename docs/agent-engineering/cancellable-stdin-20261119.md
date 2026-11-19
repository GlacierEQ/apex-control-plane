# Cancellable capability stdin delivery — 2026-11-19

Owner: APEX capability execution, src/control_plane.py; continuation of output-specific spool branch.

## Functional change
The real --exec-capability consumer no longer synchronously writes the entire pinned capability to a child that might never read stdin. A daemon delivery thread writes in bounded 64-KiB chunks; on POSIX it uses nonblocking descriptors and short select waits. The execution deadline begins before delivery and applies to subprocess waiting, including a nonreading child. The parent signals cancellation and joins the writer briefly after child exit or timeout. Existing bounded stdout/stderr spools, process-group timeout termination, durable receipt and pre-exec gate remain.

## Evidence
Python 3.13 on connected macOS: focused capability-consumer 20 passed (including 2 new real subprocess tests); full repository 1118 passed, 29 skipped, 8 subtests passed. New adversarial test uses a 2-MiB pinned capability with a 30-second nonreading child and a 1-second timeout; verifies exit_code 124 and outcome_verified false. Positive test sends 1 MiB and verifies SHA256 in child. Compilation and git diff --check passed.

## Remaining
Non-POSIX writes use a daemon writer and subprocess termination rather than POSIX nonblocking select; verify on a real Windows host. A forced SIGKILL exactly before gated child release remains untested. No production deployment, merge or host auto-invocation claim.

## Resume cursor
Check remote changed-head readback and CI; next implement deterministic pre-release SIGKILL adversarial test in the existing consumer/crash suite, then Windows-specific stdin cancellation verification. Preserve receipt fail-closed behavior.
