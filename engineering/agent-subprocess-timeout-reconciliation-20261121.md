# Agent subprocess timeout reconciliation — 2026-11-21

Base: GlacierEQ/apex-control-plane engineering/agent-scheduler-inspection-failclosed-20261121 at f5659af.

## Real consumer change
The --run-next-local / --drain-local CLI now bounds local subprocess execution (120 seconds by default, optional GLACIEREQ_LOCAL_COMMAND_TIMEOUT from 0 to 3600 seconds). A timeout records a durable execution receipt with inspection_failed, outcome_verified=false and cleanup_unresolved=true; the scheduler's existing negative-evidence gate transitions the claimed item to RECONCILING rather than authorizing blind replay. No external work is claimed.

## Evidence
Python 3.13 focused original CLI tests: 15 passed. New adversarial timeout/restart test: 1 passed. Full changed-worktree suite: 1,097 passed, 29 skipped, 8 subtests passed; exit 0. Test uses an actual sleeping subprocess and verifies persisted receipt, restart state and no immediate re-execution. No deployment or host-level automatic invocation was established.

## Remaining / continuation
Inspect actual subprocess durable receipt integration and ensure process-group cleanup and output bounding for noisy children; a timeout does not establish descendant termination. Next: recover this branch head, inspect CLI adapter and inspector, add genuine process-to-inspector-to-scheduler integration tests, then read back remote commit. No merge or deployment.
