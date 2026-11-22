# Agent receipt batch crash boundary — 2026-11-21 HST

Owning module: `src/continuous_control_plane.py`, `JsonlControlStore` and `ContinuousControlPlane.record_receipt_batch`. Recovered predecessor `60b1538342941f3cc4410aea7b0b66e77d20d34c` and branch `engineering/agent-replay-concurrency-20261121`.

Operational correction: worker receipt batches now persist in **one fsynced JSONL envelope**, not one separately committed receipt line per item. Recovery expands only complete envelopes; a torn final envelope is discarded as a unit by the existing final-line recovery rule. Legacy single-receipt journal records remain readable. Duplicate receipt UUIDs across envelopes fail closed. The existing scheduler consumer still invokes the same batch API.

Source commit: `92b7f9b9ab1af1ebf66f9f206af61641b5789ac6`; adversarial regressions: `ce282ff37c2387c17dbb8bb853ac1033026fc7ae`. Coverage: one-envelope roundtrip, torn last envelope, duplicate identity across envelopes.

Verification boundary: GitHub writes succeeded. Connected Mac runner accepted process request but returned no shell output; changed-head Python tests are **not yet verified**. The envelope eliminates prefix-of-batch certification on crash but does not make work-state/checkpoint and receipt journal one atomic transaction. No merge, deployment or automation modification.

Next exact transition: run `python3 -m pytest -q tests/test_continuous_control_plane.py` and full `python3 -m pytest -q` against `engineering/agent-replay-concurrency-20261121`; inject a crash after receipt fsync and before work-state transition, verify restart enters reconciliation rather than re-execution; repair any discovered consumer ambiguity. Independently read back provider files and branch head.
