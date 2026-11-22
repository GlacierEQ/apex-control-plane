# Cross-work receipt batch integrity — 2026-11-21

Owning source: `src/continuous_control_plane.py`, `record_receipt_batch`; consumer `execute_next_local`.

Recovered provider-native branch `engineering/agent-replay-concurrency-20261121` and earlier preflight commit `54df3bb13d80996c0ae6ffda6a7f21bcc02823d3`. The batch API accepted receipts for different work IDs, then checkpointed only the first receipt's mission. This could persist unrelated work evidence as one worker batch.

Correction: reject multi-work batches before any append, under the same durable transaction lock. Regression checks two distinct routed work items and confirms neither receipt survives a fresh ledger reload. Implementation `05eb79a759ea2a511839a8073668d7ca7d033f08`; regression `fbc9a7d9f7b30a3aa4b003d8338f6e9fda114182`.

Verification boundary: GitHub source update and independent readback only. Remote Mac runner offline (last seen 51 minutes prior at execution), so changed-head Python suite and live runtime verification not claimed. No merge or deployment.

Next executable cursor: restore Python 3.13 execution runner; run `python3 -m pytest -q tests/test_continuous_control_plane.py` then full `python3 -m pytest -q`; inject crash between multi-receipt appends and implement journaled batch commit/recovery if test demonstrates partial certification. Do not modify Omni, memory, legal cases, continuity or scheduled-task configurations.
