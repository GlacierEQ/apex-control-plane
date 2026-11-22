# APEX local scheduler negative execution evidence gate — 2026-11-21 HST

Owner: `src/continuous_control_plane.py::execute_next_local` on `engineering/agent-inspection-consumer-gate-20261121`, based on inspector integration branch `b12c9a7`.

## Implemented

The real local execution consumer now preserves worker receipts but transitions the claimed work to durable `RECONCILING` when diagnostic inspection or subprocess evidence says outcome unverified, cleanup unresolved, output drains unresolved, or descendants survived the parent. Even a superficially `verified` receipt cannot promote such negative evidence to `COMPLETE`; automatic retry is withheld. Six parameterized adversarial cases assert durable restart state and no automatic replay. Existing ordinary failed receipts retain their retry semantics.

## Verification and continuation

Focused `tests/test_continuous_control_plane.py`: 43 passed (Python 3.13). Full suite result recorded separately after completion. No merge or deployment. Reconcile the divergent `engineering/agent-scheduler-inspection-failclosed-20261121` branch selectively; do not replace this branch wholesale because the branch diff removes stronger inspector/subprocess implementation. Next: add strict receipt identity replay detection and test receipt inspector's direct diagnostic output flowing through the worker callback, including malformed evidence and restart.
