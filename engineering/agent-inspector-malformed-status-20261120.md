# APEX receipt inspector malformed-input repair — 2026-11-20

Owner: src/inspect_execution_receipt.py; consumer entry: src/control_plane.py --inspect-receipt.

Recovered from engineering/agent-receipt-duplicate-key-guard-20261120. The prior strict JSON parser rejected duplicate keys and nonfinite constants but could crash with TypeError on an untrusted JSON array/object in `status`, because the receipt consumer used set membership before type validation. Deeply nested JSON could also raise uncaught RecursionError.

Implemented strict status-type validation returning inspection_failed, retry_authorized=false, outcome_verified=false; caught parser recursion failures. Added five subprocess/real CLI regressions in tests/test_inspector_malformed_status.py (array, object, missing status, nested JSON, and valid pending control).

Provider evidence: GitHub branch engineering/agent-inspector-malformed-status-20261120; code commit 280fe59f6469ab63650ca83cbcba8ae656ec2101; test commit fc37cf0b2143df14ac86db6fa5792a2eedd45fc3. Mac clone independently read back fc37cf0b2143df14ac86db6fa5792a2eedd45fc3; five real CLI tests passed in 0.315s. First full-suite attempt used macOS default Python 3.15 without pytest and was an environment failure, not a code failure. Python 3.13 full repository suite subsequently passed: 1,108 passed, 29 skipped, 8 subtests passed in 21.91 seconds (Mac, isolated clone).

Continuation: inspect Python 3.13 full-suite output, repair any actual failures, verify GitHub final head, and recover owning scheduler consumer to enforce fail-closed inspection before success/retry transitions. No merge or deployment.
