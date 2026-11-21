# Agent receipt status guard — 2026-11-20 HST

Owner: GlacierEQ/apex-control-plane, src/inspect_execution_receipt.py, the real `--inspect-receipt` CLI consumer.

Recovered from existing `engineering/agent-receipt-numeric-strict-20261120` branch rather than rebuilding older receipt guards. The consumer already bounds reads, detects concurrent mutation, rejects ambiguous JSON and prevents untrusted outcome attestation.

Change: reject string status values not emitted by the current executor (`launched_unverified`, `pending_unverified`, `process_succeeded_unverified`, `failed`) with `inspection_failed`, exit 2 and `retry_authorized=false`. This prevents a forged or future-unknown status from being treated as a valid inspected receipt. The consumer still never grants success or retry.

Acceptance criteria: unknown states fail closed, emitted completed state remains unverified, prior inspector tests remain green. Added CLI regression tests. Provider commit readback is required; full-suite and Mac-runtime results must not be claimed until observed.

Continuation cursor: execute `/opt/homebrew/bin/python3.13 -m pytest -q tests/test_receipt_status_allowlist.py tests/test_execution_receipt_inspection.py` on exact changed branch; then full repository suite. Recover scheduler receipt-consumption path before wiring any decision transition. Do not merge/deploy or alter scheduled tasks without permission.
