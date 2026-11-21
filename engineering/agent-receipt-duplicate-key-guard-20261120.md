# APEX receipt ambiguity guard — 2026-11-20

Owning executable: `src/inspect_execution_receipt.py`, consumed through `control_plane.py --inspect-receipt PATH`. Recovered from `engineering/agent-consumer-cleanup-gate-20261120`, preserving its cleanup-evidence gate. Separate from Omni connectors, structured memory, case building, and continuity.

## Implemented

Strict JSON parsing now rejects duplicate object members (including nested duplicates), NaN, Infinity, and -Infinity. Python's default `json.load` silently accepts last-key-wins duplicate fields and nonstandard numeric constants, allowing conflicting receipt claims to be interpreted as a single unambiguous record. The inspector now fails closed with `inspection_failed`, exit 2, and `retry_authorized=false`. Valid JSON still flows through the existing cleanup and containment evidence checks. This does not grant retry authority or claim mission success.

## Native verification

GitHub commits: implementation `7c5d5d52d4d4d99dc78fa3fa13a46298e9c02d26`, real-CLI regressions `3626c6b95dab44b2f3efd840fe53ff348b69b804`. Isolated Mac worktree `~/Documents/GlacierEQ-Agent-Receipt-Guard-20261120` at `3626c6b`; Python 3.13 venv. `python3 -m compileall -q src/inspect_execution_receipt.py` passed. Focused CLI suite: **7 passed in 0.90s**. Full `PYTHONPATH=src ~/Documents/GlacierEQ-continuity-validation/venv/bin/python -m pytest -q tests --basetemp=/tmp/glaciereq-receipt-guard-full-20261120`: **1103 passed, 29 skipped, 8 subtests passed in 18.17s**. Tests cover duplicate status, nested duplicates, nonstandard constants, and valid receipts. Local Mac tests are not deployed host/scheduler proof.

## Continuation cursor

Read back this exact branch and reconcile with latest concurrent `apex-control-plane` branches. Find actual scheduler receipt consumer and enforce `inspection_failed` and unresolved cleanup as hard stops before success/retry transitions; test real receipt flow. Preserve descendant containment uncertainty; native Windows still unverified. Do not merge/deploy without authorization.
