# Agent crash-boundary reconciliation — 2026-11-22 HST

Owning source: `src/continuous_control_plane.py`, `ContinuousControlPlane.claim_next`. Recovered prior branch `engineering/agent-replay-concurrency-20261121`, receipt-batch envelope head `b0177a6a5382678f847dddb961523705bc7f2b1f`, and prior test boundary.

Defect: after a local worker persisted its receipt batch but crashed before transitioning the work state, the expired local lease was requeued automatically. A second worker could execute the same work again despite durable evidence of the first attempt. This is distinct from the existing external-action lease reconciliation path.

Changed executable consumer: `claim_next` now checks recovered durable receipts while holding the ledger transaction. Expired leased work with receipts enters `RECONCILING`, including local-only work; receipt-free expired local work remains retriable. No new permissions or automatic provider calls.

Source commit: `d6def3d867869619639d220c3d46b840067386a3`. Adversarial regression commit: `cf6e05a739a07d4b5bc57c9ae966f59436447656`. Tests model receipt fsync followed by restart before state transition, require no executor invocation and durable reconciliation, plus receipt-free local lease retry.

Verification boundary: GitHub accepted both writes. Connected Mac runner request was pending without usable command output; Python 3.13 tests are NOT confirmed on this changed head. Do not claim runtime verification, merge, or deployment.

Next exact transition: run `python3 -m pytest -q tests/test_continuous_control_plane.py` then `python3 -m pytest -q` against this branch; independently fetch source/test/notes and compare head. Inspect whether a failed execution with durable receipt should be auto-reconciled beyond the lease-expiration path. Preserve distinct Omni, structured-memory, legal and continuity workstreams.
