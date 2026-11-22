# APEX descendant evidence inspection — 2026-11-21

Owner: `src/inspect_execution_receipt.py` and real `--exec-capability` receipt producer in `src/control_plane.py`. Recovered branch `engineering/agent-cleanup-verified-20261121` at `72f1251`; earlier source revision `5657a49` and its descendant test were preserved.

Full-suite baseline: 1136 passed, 29 skipped, 8 subtests, one failure: the test assumed `cleanup_unresolved=True` even when bounded process-group recheck proved the descendant gone. That assumption conflated detected late descendant execution (always fails with exit 74) with remaining cleanup uncertainty (may be false after successful cleanup).

Changed consumer: the independent read-only receipt inspector now exposes `descendant_detected_after_exit=True` and `cleanup_status=descendant_detected_cleanup_completed` when a failed receipt shows a late descendant but successful subsequent cleanup. It continues to refuse `outcome_verified` and retry authorization. Corrected the adversarial subprocess test to assert the durable detection flag independently from unresolved cleanup, and repaired existing inspector test import isolation (source module in `src/`, not installed package). Added a receipt-inspection regression for cleaned-up late descendants.

Acceptance: Python 3.13 full changed-head suite: 1138 passed, 29 skipped, 8 subtests passed in 18.61s; `git diff --check` clean. Local real-subprocess test and read-only inspector test included. No end-to-end scheduler adapter wiring or host-level invocation claimed.

Continuation: wire this inspector's fail-closed diagnostics into the scheduler's actual receipt-consumption path with a durable artifact reference, preserving its non-attestation semantics; test restart, malformed receipt, and escaped-session cases. Do not merge or deploy without specific approval.
