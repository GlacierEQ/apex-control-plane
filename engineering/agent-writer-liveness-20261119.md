# Agent stdin writer liveness — 2026-11-19

Owner: GlacierEQ/apex-control-plane, src/control_plane.py, --exec-capability consumer.

## Recovered source and defect

Based on engineering/agent-stdin-delivery-integrity-20261119, blob f0cb57e7714c1bda06a881c58bb87c75fe033b7c. The existing cancellable stdin delivery thread uses a bounded join, but a surviving writer could still be classified as complete solely because the recorded byte count matched the document length. This is especially relevant to non-POSIX blocking writes; thread cancellation does not prove I/O completion.

## Implemented

After the bounded join, capture input_thread.is_alive(), add InputWriterUnresolved to the delivery errors, mark stdin_delivery_complete false when unresolved, and persist stdin_writer_unresolved in the final receipt. A zero-exit child with unresolved input delivery is classified as 74 instead of success. No permissions, runtime activation, merges, or deployments changed.

## Evidence and limits

GitHub independently read back src/control_plane.py at blob 72f39f0574381dc822f9e7daab610a8c5f09adf3, commit cb0f156796317229f5eebbd20da29853e62dd9cc. The Mac device 6787800d-2c79-47f2-8864-162a867dd4a1 was offline at the current invocation. This is source-verified, NOT changed-head runtime-tested or proven process containment. The prior intermittent post-receipt subprocess hang remains unresolved; this is a fail-closed evidence improvement, not a confirmed root-cause repair.

## Exact continuation cursor

1. Reconnect Mac or use a separately authorized executable checkout without overwriting any existing worktree.
2. Check out engineering/agent-writer-liveness-receipt-20261119 at cb0f156796317229f5eebbd20da29853e62dd9cc in an isolated worktree.
3. Add real CLI adversarial regression for an unresolved writer and ensure exit 74, stdin_writer_unresolved true, stdin_delivery_complete false; also test normal fully delivered input.
4. Reproduce intermittent post-receipt hang with process/pipe tracing and independently inspect process termination and receipt.
5. Run focused tests and full Python 3.13 suite on the exact changed head; repair defects, update this note, and preserve provider readback. Do not merge or deploy without specific authorization.
