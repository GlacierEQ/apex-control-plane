# Bounded drain after durable-receipt write failure — 2026-11-20

Owner: GlacierEQ/apex-control-plane, src/control_plane.py, --exec-capability. Based on engineering/agent-gate-fd-cleanup-20261120, preserving gate FD fix and prior output-drain work. Isolated branch: engineering/agent-receipt-failure-bounded-drain-20261120.

## Functional change

Previously, if write_receipt(launched) raised OSError, the executor killed the child process group and then called unbounded join() on both output-drain threads. A descendant outside that process group retaining an inherited stdout/stderr pipe could prevent EOF and hang the executor indefinitely on its failure path. Now stop_drains is set and each reader gets a bounded 0.3-second join. The original durable gate remains closed on receipt failure, so the requested program cannot start without a durable launch receipt. No success classification is introduced.

## Verification boundary

GitHub accepted code commit 53ebe7e578e8cf45a75f8d3950f286cb644a4a6e; read back the changed source on this branch. Native Mac command request was pending at time of implementation; no changed-head Python 3.13 test or real descendant-held-pipe adversarial test has completed. This change must not be called runtime-verified, merged, or deployed.

## Exact continuation

On a responsive native runner, checkout engineering/agent-receipt-failure-bounded-drain-20261120 in a separate worktree, add a CLI regression that injects launch-receipt OSError while a descendant holds stdout open, assert bounded termination and no executed command, run focused adversarial tests and the full Python 3.13 suite. Compare with the writer-liveness branch and reconcile only after tests. Do not merge/deploy or alter automation configuration.

## 2026-11-20 runner recovery checkpoint

Authenticated GitHub readback confirmed the owning executable and branch. Desktop Commander listed kcbs-macbook-air online (device 6787800d-2c79-47f2-8864-162a867dd4a1), but both a worktree/Python probe (call 185d0d36-a5f8-423b-ad08-95337b60d9fd) and a minimal /bin/echo probe (call f6e932a3-e7fa-4161-9cde-5f9153a0fe42) remained asynchronous without a returned PID or stdout. The direct isolated-container GitHub clone path failed DNS resolution. These are execution transport blockers, not demonstrated executor defects. No changed-head runtime result exists from this checkpoint. Resume by recovering those pending command results through the desktop transport, not by repeatedly spawning more commands. Once responsive, execute the existing receipt-failure/descendant-held-pipe regression first, inspect real receipt and exit status, then full Python 3.13 suite. Preserve branch separation and avoid merging/deployment.

## 2026-11-20 execution transport investigation (03:26 HST)

Recovered branch and source directly from authenticated GitHub; source retains bounded 0.3-second joins on durable launch-receipt failure. Desktop Commander reports kcbs-macbook-air online (device 6787800d-2c79-47f2-8864-162a867dd4a1), but list_sessions returned no active sessions. Historical pending transport call IDs 185d0d36-a5f8-423b-ad08-95337b60d9fd and f6e932a3-e7fa-4161-9cde-5f9153a0fe42 now return not_found/expired. A fresh minimal command call c0339326-8574-499d-8fd3-79c9e58d0cfe returned PID 95885; read_process_output call 87df425d-dfd5-49b4-b747-ebf3cbac0121 remained pending without stdout. This distinguishes a successful session start from unresolved output retrieval; do not infer source failure or test success. Exact next cursor: retrieve pending read result 87df425d-dfd5-49b4-b747-ebf3cbac0121, then if responsive run real CLI launch-receipt OSError plus descendant-held pipe regression and full changed-head Python 3.13 suite. If transport remains stalled, use authenticated GitHub source for an independently executable isolated test runner; do not repeatedly spawn duplicate commands. No source modifications or runtime verification occurred in this checkpoint.
