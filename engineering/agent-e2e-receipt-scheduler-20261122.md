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

## Recovered strict POSIX execution and delegated-child containment — 2026-11-22 HST

Context: resumed existing branch at `fcac3a1713a7fd203fd1480fa860d3defc740355`. Recovered working POSIX streaming logic from divergent tested `origin/engineering/agent-subprocess-receipt-gate-20261121`, applied only to owning `src/control_plane.py` rather than overwriting later independent inspector or crash-safe scheduler work. Preserved the optional `--inspect-execution-receipt` route.

Actual changes: POSIX workers use a bounded selector/pipe capture (64 KiB retained each stream; 1 MiB live per-stream quota), an isolated child session, bounded deadline/cleanup, and process-group checks after the direct child exits. Surviving delegated same-session descendants force failure and `RECONCILING`, not `COMPLETE`. Group cleanup uses a bounded deadline. Unexpected post-launch subprocess errors are treated as uncertain, not automatically replayed. Existing Windows fallback remains non-strict and is not reported as verified containment.

RED: real subprocess and real persistent-queue adversarial tests proved (1) a parent could return successful output while its delegated child continued, and (2) the old path did not enforce live stream quotas. Both failed on the original `fcac3a1` source. GREEN: both tests passed after the source repair, including observed absent descendant marker after the delayed write interval.

**Exact changed-head macOS Python 3.13 suite:** `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.13 -m pytest -q -p no:cacheprovider` → **1165 passed, 29 skipped, 8 subtests passed, 35.46 seconds; exit 0**. `git diff --check` clean. Regression proof is local native subprocess+filesystem behavior; it is not production deployment proof.

Residual limits: detached processes that escape the original session are outside this bounded process-group guarantee. Windows descendant cleanup is not fully attested. Stream bytes are clipped counters at 1 MiB, not an exact total if a child emits beyond the quota. Independent receipt inspection is diagnostic and cannot verify an actual user objective; successful local artifact readback is a different scope. No automations, credentials, permissions, merges, or deployments touched.

Continuation: independently verify GitHub branch head and all changed blobs after push. The next operational step is host-controlled adoption/integration in the authorized runtime with provider-native readback; respect deployment approval. Improve escaped-session detection only with a separately proven, non-regressing mechanism.

## POSIX stream quota boundary correction — 2026-11-22

Recovered owning branch at 85fe906. In `execute_queued` the stream reader marked `quota_exhausted=True` at exactly the permitted 1,048,576 bytes (`counts[name] >= disk_limit`), rejecting a legitimate worker. Corrected overflow to require actual bytes beyond the limit (`len(data) > remaining`). Added a real subprocess and durable scheduler test that writes exactly 1 MiB, checks successful local execution remains `awaiting_receipts` rather than falsely claiming mission completion, and verifies persisted receipt counters. This affects only the local POSIX worker path, not provider attestation. Full changed-tree suite and provider readback to follow. Remaining independent boundaries: escaped-session descendants, Windows containment, human-objective attestation, and actual runtime adoption. No host deployment, automation configuration, credentials or permissions changed.

Final changed-tree validation: Python 3.13 native Mac `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.13 -m pytest -q -p no:cacheprovider`: **1166 passed, 29 skipped, 8 subtests passed, exit 0, 35.96s**. The new exact-boundary test passes; a no-attestation local process correctly remains `awaiting_receipts`, not `complete`. Next: commit/push and independently read back exact provider blob; no merge or deployment.


## Post-SIGKILL group liveness fail-closed correction — 2026-11-22

Recovered GitHub branch head 51104876764753cc76c75dd6e644ce9c74149de6 and live `src/control_plane.py` worker path. The killed branch previously called `child.wait()` and treated direct-child reaping as sufficient even if `killpg` was ineffective or descendants survived. Added a post-reap `killpg(pgid, 0)` check that marks cleanup uncertain if any group member remains or group inspection fails. This changes real worker receipt classification through existing `cleanup_unresolved` → durable `RECONCILING`, without permitting blind replay. Added a narrow source regression guard. The authorized Mac is offline, so this checkpoint is GitHub-source implementation and static verification only; **native changed-head adversarial subprocess tests and full suite are pending**, not claimed passed. This does not solve detached descendants outside the original group or Windows containment. No merge, deployment, credentials, scheduled tasks, or other workstreams touched. Next: run full native Python suite and adversarial group-liveness tests on the exact new commit, then independently read back source/notes and pursue detached-session containment separately.


## Detached Linux child reaping in real local scheduler — 2026-11-22

Recovered the newest previous source commit 8254520aeda2c050c48f5975bb49d597e49aa53c and preserved its post-SIGKILL process-group check. An independent Linux subprocess reproduction proved a setsid grandchild with closed inherited stdio could write a delayed marker after its successful direct parent exited; enabling the new subreaper terminated and reaped that child, suppressing the delayed marker. Wired the Linux-only per-CLI guard into the same --run-next-local/--drain-local worker with durable failure-classified execution receipts. Adopted child PIDs remain owned until waitpid prevents PID-reuse signaling. When /proc task children is missing, uses a read-only PPID scan of proc stat. New integration regression requires RECONCILING instead of false COMPLETE and checks the marker stays absent.

Source change is in isolated branch engineering/agent-linux-detached-subprocess-containment-20261122 so the concurrent scheduler worker branch is not overwritten. Isolated reproduction is real Linux subprocess testing, but full exact changed-branch GitHub CI and native deployment are pending verification. prctl/procfs unavailable disables the extra containment; no guarantee is asserted for macOS or Windows. Existing inspector, stream-quota, and group-cleanup behavior preserved. No scheduled task edits, merges, deployment, credential operations or unrelated workstreams.

Next: inspect CI for the exact new head; repair any test failures. Then separately prove non-Linux descendant containment and runtime adoption.


## Native macOS changed-head validation — 2026-11-22

The authorized Mac `kcbs-macbook-air` returned online. In an isolated checkout at `~/Documents/GlacierEQ-Agent-Containment-Validation/apex-control-plane`, Git detached HEAD was confirmed exactly `19d7958e4d6ef971ae8bfe8cba0297044c7a9d06`. Real native Python 3.13.18 subprocess/scheduler integration test `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.13 -m pytest -q -p no:cacheprovider tests/test_scheduler_inspector_bridge.py` completed **12 passed, 1 skipped, exit 0, 21.65 seconds**. The skipped test is Linux-only detached-grandchild adoption; macOS did not run that test. Full exact-head command `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.13 -m pytest -q -p no:cacheprovider && git diff --check` completed **1167 passed, 30 skipped, 8 subtests passed, exit 0, 124.98 seconds**. This verifies the current branch on macOS and no tracked diff errors, not the Linux subreaper's repository integration or production deployment. Next: execute the Linux-specific detached-grandchild regression in an isolated real Linux environment and verify the durable RECONCILING/late-marker boundary; repair any defect on a separate validated branch, preserve Mac regression results, and avoid touching unrelated workstreams. No merge, deployment, automation configuration, credentials, or permissions changed.


## Fail-closed Linux guard availability — 2026-11-22

Recovered owning branch 2db41caf1f644094dbb4865794b77dd54c12d7d1. Identified fail-open condition: on Linux, if prctl/procfs subreaper activation failed, a clean direct-child exit could still be marked verified despite unobservable detached descendants. Corrected the real scheduler worker path: Linux-only guard-unavailable execution now sets cleanup_unresolved and refuses exit-zero success (code 125), preserving durable reconciliation. macOS behavior remains unchanged. Added a source regression assertion; native Linux end-to-end integration and full changed-head suite remain pending. No merge, deployment, credential or automation changes.
