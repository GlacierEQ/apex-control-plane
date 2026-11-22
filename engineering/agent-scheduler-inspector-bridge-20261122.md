# APEX real subprocess-to-inspector scheduler bridge — 2026-11-22 HST

## Owning state and preservation
Recovered `GlacierEQ/apex-control-plane` branch `engineering/agent-replay-concurrency-20261121` at `52814aca5751c7607c9b234130266eadf002312e`. Isolated worktree/branch `engineering/agent-end-to-end-receipt-scheduler-20261122`; no merges, deployments, credential or automation edits. Prior stronger scheduler retains atomic receipt-batch journal, cross-work and UUID replay guards, expired-lease reconciliation and inspector's fail-closed bounded-read checks.

## New real consumer capability
The actual `src/control_plane.py --run-next-local` and `--drain-local` CLI accepts optional `--inspect-execution-receipt PATH` alongside `--verify-file PATH`. A real operator-supplied subprocess may create a durable receipt. The local scheduler independently inspects it through `inspect_execution_receipt.inspect`, requires same-invocation filesystem freshness, persists the diagnostic with its actual exit code, and moves the work to `RECONCILING` rather than replay or false completion. Independent receipt inspection is diagnostic, **not outcome attestation**. A fresh artifact does not override an unverified or failed receipt inspection. No untrusted event content becomes an executable command.

## Executable regression
`tests/test_scheduler_inspector_bridge.py` uses real subprocesses and the persisted queue: (1) nested SHA-256-pinned capability execution with a real durable receipt and independent inspection, (2) malformed newly generated receipt, and (3) historical forged success receipt with a genuinely fresh output artifact. All three must produce nonzero CLI status, durable RECONCILING after restart, no replay, and no false verification. Red before implementation: 3 failed because CLI rejected inspector option. Green after implementation: 3 passed in 1.62 s. Existing focused suite and complete repository suite are separate gates; record their final changed-head outcomes rather than reusing earlier results.

## Next cursor
Validate full changed-head suite and subprocess timeout/output containment before claiming broad operational hardening. Specifically, this new bridge currently uses the existing `subprocess.run(capture_output=True)` local worker; do not treat it as bounded-output or process-tree-contained. Reconcile stronger divergent bounded-subprocess branch before attempting that integration. Then independently read back the pushed GitHub branch and verify live process exit/state and crash-injection behavior. Keep the other four workstreams untouched.

## Changed-head verification
After implementation, the real subprocess bridge regression passed 3/3; the focused scheduler/CLI/inspector regression command completed with exit 0. Full Python 3.13 repository suite executed against the exact changed source tree and returned **1158 passed, 29 skipped, 8 subtests passed in 36.95 s**, exit 0. Local implementation commit `8948cc91ee16715ef76a5488b64fe89ed84bb297`. These are local Mac tests, not proof of production deployment or host-level automatic invocation. The isolated branch is deliberately unmerged.
