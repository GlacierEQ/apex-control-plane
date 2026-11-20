# APEX timeout reaping bound — 2026-11-20

## Source recovery and defect
Recovered `engineering/agent-preserve-pending-integrated-20261120` at `69290ecb996daa894f2fea3116779f482bde0362` and owning `src/control_plane.py --exec-capability`. Receipt-write failure cleanup already bounded `child.wait`, but ordinary execution timeout still called `child.wait()` without a deadline after SIGKILL. A stuck child could therefore hang the executor indefinitely despite a requested timeout.

## Operational repair
Ordinary timeout cleanup now waits at most 1 second after process-group termination, then attempts child termination again and waits at most 300 ms. If unreaped, it continues fail-closed with timeout code 124; existing stdin integrity, receipt preservation, output-drain and group containment paths remain unchanged. No guarantee is made for uninterruptible kernel I/O or surviving descendants.

## Verification
- New adversarial POSIX CLI regression patches `Popen.wait` to reject any unbounded wait and launches a real sleeping child with a 200 ms timeout; exit 124, failed receipt, elapsed under 3 seconds.
- Focused native Python 3.13: 23 passed in 7.89 seconds.
- Full native Python 3.13 repository suite: 1126 passed, 29 skipped, 8 subtests passed in 19.25 seconds.
- `git diff --check` clean before commit. Native macOS tests, not production deployment or host integration proof.

## Continuation cursor
Reconcile group-signal denial and receipt-failure/descendant-held-pipe adversarial tests into the isolated integrated branch, repair demonstrated failures, rerun complete suite, independently read back provider source and notes. Do not merge, deploy, modify credentials/permissions or automation configuration.
