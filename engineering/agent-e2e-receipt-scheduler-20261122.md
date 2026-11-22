# APEX end-to-end subprocess inspection and durable scheduler integration — 2026-11-22 HST

## Owning implementation and recovery

- Repository: `GlacierEQ/apex-control-plane`
- Isolated branch: `engineering/agent-end-to-end-receipt-scheduler-20261122`
- Base source: `52814aca5751c7607c9b234130266eadf002312e` (crash-safe receipt batch / expired-lease reconciliation)
- Consumers: `src/control_plane.py` (`--run-next-local`, `--drain-local`), `src/inspect_execution_receipt.py`, and `src/continuous_control_plane.py`.
- No changes to Omni_Engine, structured memory, legal, continuity, production, or scheduled task configurations.

## Actual new capability

The operator-supplied local subprocess CLI now accepts `--inspect-execution-receipt FILE` alongside optional `--verify-file FILE`, in either order, before `-- PROGRAM`. It compares the independent durable receipt file's source identity before/after the real child invocation, invokes the real read-only inspector, and attaches that diagnostic result to the actual worker execution receipt.

- An inspected subprocess receipt is **diagnostic, not attestation**. Even a zero-exit child plus a fresh artifact cannot convert `outcome_evidence=unattested_receipt` into scheduler completion.
- Missing/stale/malformed receipt evidence is classified `inspection_failed`, stored as an execution receipt, and enters durable `RECONCILING` without blind replay. A fresh valid receipt is `inspected_unverified` and also reconciles.
- Existing local artifact-only verification behavior remains compatible when independent inspection is not requested; this is not an automatic host-wide activation claim.
- A bounded direct-child timeout (default 120 seconds; finite per-process env override `GLACIEREQ_LOCAL_COMMAND_TIMEOUT`) prevents routine hangs. Captured process output is stored in temporary files and read back at most 64 KiB per stream. Output above 1 MiB per stream is classified as failure after child execution. It is **not a strict real-time disk quota**.
- Multi-megabyte artifact hashing streams 1 MiB chunks, preserving same-run identity metadata checks.

## Executed verification

- RED: 3 real subprocess→inspector→scheduler tests failed before wiring (CLI rejected the option), followed by 2 deadline/output tests failing on the original unbounded subprocess path.
- GREEN: all 6 new real subprocess/adversarial tests passed.
- Existing inspector, scheduler, and CLI tests together with new bridge: 81 passed at initial focused checkpoint.
- **Full exact changed-tree Python 3.13 suite**: `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.13 -m pytest -q -p no:cacheprovider` → **1161 passed, 29 skipped, 8 subtests passed, 35.50 seconds, exit 0**.
- `git diff --check`: no reported errors. Real native Mac execution, not mocked provider delivery.

## Boundaries and continuation

The inspector cannot independently attest the human objective; complete descendant containment and Windows execution are not proven. Temporary output files can grow until execution terminates; 1 MiB enforcement here is post-run failure detection, not a strict disk cap. The separate stronger POSIX stream enforcement remains on its existing branch and was not overwritten. No PR merge or production deployment.

Next: reconcile nonregressing strict POSIX output quota and verified descendant cleanup from the separate tested branch without losing this inspector bridge; test cross-process lease/crash recovery, full Python 3.13 suite, and provider readback on exact final commit. In production, approval-controlled installation and native host activation require separate proof.

## Follow-on worker-receipt shape hardening (same isolated branch)

After the inspector bridge passed its first full suite, a new adversarial worker-callback test reproduced a real `AttributeError` when `ExecutionReceipt.details` was `None` or another non-mapping. A second failing test reproduced an unhashable receipt-kind crash during completion after receipt persistence.

`src/continuous_control_plane.py::execute_next_local` now checks runtime types of status, details, receipt UUID, receipt kind, source system and provider receipt identity before any receipt append. Nested detail values must also be strict JSON-serializable. Malformed or unserializable worker receipts enter durable `RECONCILING`; no receipt from that invalid callback is appended and no automatic replay is authorized.

RED: 2 focused adversarial tests failed on the pre-fix implementation. GREEN: 60 focused scheduler/bridge tests passed. Full exact changed-tree Python 3.13 verification: `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.13 -m pytest -q -p no:cacheprovider` → **1163 passed, 29 skipped, 8 subtests passed, 40.05 seconds, exit 0**. Previous clean 1161-pass result remains tied to the earlier revision only.

Remaining boundaries: real host adoption, strict live disk quota, Windows process-tree containment, escaped-session descendants, and independent human-outcome attestation are not proven. Keep all other scheduled worker configurations and unrelated repositories untouched. Next executable cursor: independently read back the final pushed head, then reconcile strict POSIX stream limits and verified descendant cleanup from the older tested branch in another isolated change without weakening the durable inspection/reconciliation path.
