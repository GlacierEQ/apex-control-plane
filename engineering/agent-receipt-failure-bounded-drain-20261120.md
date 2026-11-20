# Bounded drain after durable-receipt write failure — 2026-11-20

Owner: GlacierEQ/apex-control-plane, src/control_plane.py, --exec-capability. Based on engineering/agent-gate-fd-cleanup-20261120, preserving gate FD fix and prior output-drain work. Isolated branch: engineering/agent-receipt-failure-bounded-drain-20261120.

## Functional change

Previously, if write_receipt(launched) raised OSError, the executor killed the child process group and then called unbounded join() on both output-drain threads. A descendant outside that process group retaining an inherited stdout/stderr pipe could prevent EOF and hang the executor indefinitely on its failure path. Now stop_drains is set and each reader gets a bounded 0.3-second join. The original durable gate remains closed on receipt failure, so the requested program cannot start without a durable launch receipt. No success classification is introduced.

## Verification boundary

GitHub accepted code commit 53ebe7e578e8cf45a75f8d3950f286cb644a4a6e; read back the changed source on this branch. Native Mac command request was pending at time of implementation; no changed-head Python 3.13 test or real descendant-held-pipe adversarial test has completed. This change must not be called runtime-verified, merged, or deployed.

## Exact continuation

On a responsive native runner, checkout engineering/agent-receipt-failure-bounded-drain-20261120 in a separate worktree, add a CLI regression that injects launch-receipt OSError while a descendant holds stdout open, assert bounded termination and no executed command, run focused adversarial tests and the full Python 3.13 suite. Compare with the writer-liveness branch and reconcile only after tests. Do not merge/deploy or alter automation configuration.
