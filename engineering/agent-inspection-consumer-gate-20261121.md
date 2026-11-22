# APEX local scheduler negative execution evidence gate — 2026-11-21 HST

Owner: `src/continuous_control_plane.py::execute_next_local` on `engineering/agent-inspection-consumer-gate-20261121`, based on inspector integration branch `b12c9a7`.

## Implemented

The real local execution consumer now preserves worker receipts but transitions the claimed work to durable `RECONCILING` when diagnostic inspection or subprocess evidence says outcome unverified, cleanup unresolved, output drains unresolved, or descendants survived the parent. Even a superficially `verified` receipt cannot promote such negative evidence to `COMPLETE`; automatic retry is withheld. Six parameterized adversarial cases assert durable restart state and no automatic replay. Existing ordinary failed receipts retain their retry semantics.

## Verification and continuation

Focused `tests/test_continuous_control_plane.py`: 43 passed (Python 3.13). Full suite result recorded separately after completion. No merge or deployment. Reconcile the divergent `engineering/agent-scheduler-inspection-failclosed-20261121` branch selectively; do not replace this branch wholesale because the branch diff removes stronger inspector/subprocess implementation. Next: add strict receipt identity replay detection and test receipt inspector's direct diagnostic output flowing through the worker callback, including malformed evidence and restart.

## Exact changed-head full-suite verification

Python 3.13 `python3.13 -m pytest -q`: **1146 passed, 29 skipped, 8 subtests passed in 53.05 seconds**, exit 0. Focused 43 passed. This proves local tests, not deployed provider execution.


## 2026-11-21 HST — durable receipt replay hardening
Recovered diverged `engineering/agent-receipt-id-replay-20261121` (17 commits ahead / 116 behind this stronger branch). Selectively implemented replay protection here without replacing the stronger branch. `record_receipt` now rejects existing UUIDs inside its durable store transaction; the real `execute_next_local` consumer reconciles UUID collisions, in-batch duplicate IDs, and historical provider receipt substitution. Added restart and ledger-collision regression tests. Source commits: 18798d71, 4cdf6287, 098a8860. Provider-native GitHub readback required. The Mac execution host was offline (last seen 19 minutes before this run), so Python 3.13 focused/full-suite results are NOT established for this changed head. Next: restore runner, run focused and full pytest, inspect any existing tests depending on idempotent repeated record_receipt, and test concurrent independent ledger writers. Do not merge or deploy without approval.
