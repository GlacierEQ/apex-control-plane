# APEX gated-spawn descriptor cleanup — 2026-11-20

Owner: GlacierEQ/apex-control-plane `src/control_plane.py`, `--exec-capability` POSIX durable-launch gate. Source base: `c0a8f8386a14a1d1d9c63920387c0c4daabf9285` (`engineering/agent-output-drain-deadline-20261119`). Isolated branch `engineering/agent-gate-fd-cleanup-20261120`; no changes to other worktrees.

## Corrected behavior

When `subprocess.Popen` raises before returning a child, the previous `finally` closed only `gate_read`, leaking the parent-owned `gate_write` descriptor in long-lived invocations. The owning launch path now closes and clears `gate_write` on every `BaseException` from spawn while preserving `gate_read` cleanup and the normal successful gate release. This is an FD-resource cleanup, not a change to launch authorization or durable receipt semantics.

## Evidence

`python3.13 -m pytest -q tests/test_control_plane_gate_fd_cleanup.py --maxfail=1`: 1 passed. This fault-injects `Popen` failure in the real CLI path, verifies both actual POSIX gate FDs are closed, and observes the existing failure receipt/exit. `python3.13 -m pytest -q tests/test_control_plane_cli_execution.py tests/test_control_plane_output_drain_deadline.py --maxfail=1`: 16 passed. These are local native tests, not a production deployment or proof of the separate intermittent post-receipt hang.

## Exact continuation

Run broader changed-head Python 3.13 tests, inspect process lifecycle adversarial receipts, independently fetch pushed code and test from GitHub. Integrate only by an authorized non-destructive review path; do not merge or deploy without specific permission. Preserve parallel writer-liveness, drain, and continuity branches; reconcile before any eventual consolidation.

## Expanded exact-head verification

After code commit `857f718`, Python 3.13 native run across `test_control_plane_gate_fd_cleanup.py`, `test_control_plane_cli_execution.py`, `test_control_plane_output_drain_deadline.py`, `test_control_plane_prerelease_sigkill.py`, and `test_control_plane_capability_consumer.py` completed **38 passed in 25.00 seconds** (exit 0). GitHub independently read back the corrected launch path at blob `c03a3c7043e611623a2696f8e5dcbb0cbc3e6754`. Full repository suite not rerun on this head.
