# Agent receipt batch preflight — 2026-11-21

Owning source: `src/continuous_control_plane.py`, `execute_next_local` and `record_receipt_batch`.

Defect: the scheduler previously persisted worker receipts one at a time. A later receipt with a reused UUID or provider identity could reject the execution after earlier fresh receipts had already entered the durable ledger, leaving partial certification evidence.

Correction: preflight the complete worker receipt batch under one ledger transaction lock, including historical UUIDs, within-batch UUIDs, work mission/correlation, and provider receipt identities. Only append after all identity checks pass. The consumer enters RECONCILING on rejected evidence, without persisting any preceding receipt in that batch.

Validation: Python 3.13 focused scheduler tests 46 passed; complete suite 1149 passed, 29 skipped, 8 subtests passed. Adversarial test supplies a fresh receipt followed by an already-recorded UUID, then checks fresh evidence is absent after durable restart.

Boundary: this is preflight atomicity against identity conflicts, not crash-atomic multi-record filesystem persistence. A crash between append operations still requires recovery/reconciliation; do not claim transactional disk rollback. No merge or deployment.

Next: add a crash-injection/restart reconciliation test for interrupted multi-receipt append and evaluate a journaled batch commit marker. Independently verify GitHub pushed head and keep separate Omni, memory, case, and continuity streams untouched.
