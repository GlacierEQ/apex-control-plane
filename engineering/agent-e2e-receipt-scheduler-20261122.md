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


## Exact-head native focused regression — 2026-11-22

Recovered branch 79a8ca6fdeca310d078d682cc9cb040408467073 from GitHub and fetched it into an isolated Mac worktree at ~/Documents/GlacierEQ-Agent-Linux-Validation-20261122. Ran /opt/homebrew/bin/python3.13 -m pytest -q -p no:cacheprovider tests/test_scheduler_inspector_bridge.py on that exact commit: **12 passed, 2 skipped, exit 0, 25.57 seconds**. This confirms the macOS subprocess/inspector/scheduler focused boundary, not Linux subreaper operation: Linux-only regressions were skipped. The existing Podman VM 'monk' was found stopped and its start remained in 'Currently starting' state; Linux integration and full suite on this new exact head remain unverified. No deployment or merge. Next: establish a working isolated Linux runtime, execute Linux detached-grandchild and fail-closed prctl-denial adversarial cases, run full changed-head suite, then repair actual failures and read back the source revision. Preserve other workstreams.


## Independent Linux kernel-boundary rehearsal — 2026-11-22 (isolated runtime)

Recovered exact GitHub branch bb258466881ef050ca4b63e00dc8dc3450263d04 and source blobs. Authorized Mac is offline; previous remote invocation 8fdd9587-5a67-4b9f-9a1b-892116ba0698 now returns not_found (not proof of execution). Ran a fresh Linux Python 3.13 real-process rehearsal in the isolated execution container, without accessing the private repository or running its scheduler. Linux prctl GET_CHILD_SUBREAPER returned 0 with prior value 0; SET_CHILD_SUBREAPER succeeded. This runtime lacks /proc/self/task/<pid>/children, confirming that the repository's fallback path is relevant. First direct-proc-only probe failed with FileNotFoundError; repaired the independent probe to enumerate immediate child PPIDs from /proc/<pid>/stat. A real parent spawned a setsid grandchild closing all stdio, then exited; the subreaper adopted one PID, SIGKILL plus waitpid reaped it, and after a 1.2-second delay the expected marker file was absent. This proves the kernel-level primitive and fallback PPID discovery in this isolated runtime, **not** exact-head repository integration or durable RECONCILING. No source defect was established by this rehearsal. Exact continuation: run repository test_linux_detached_grandchild_cannot_falsely_complete_durable_queue and test_linux_guard_unavailable_fails_closed_in_worker_source on a Linux checkout of bb25846; verify durable receipt and late-marker assertions, then full suite. No merge/deployment/automations/credentials changes.


## Nested Linux subreaper ownership isolation — 2026-11-22

Recovered owning branch 05b4e7e38b694f8d82d3fa369e209ea1b50e3f2e. Found a concrete nested-supervisor isolation defect: LinuxAdoptedDescendants.arm() accepted an already-active PR_GET_CHILD_SUBREAPER state and could later kill adopted children owned by an enclosing supervisor. The worker now refuses to arm when the previous state is nonzero; the existing Linux scheduler fail-closed path marks the execution unconfirmed instead of claiming containment. Added an isolated subprocess regression asserting that an existing subreaper remains enabled and is never hijacked. This protects nested agent execution boundaries without touching other workstreams. Linux changed-head runtime regression and full suite still require an accessible checkout/runner; do not claim them passed. Next: run the Linux nested-supervisor test and detached-grandchild durable scheduler test, then the full suite; repair demonstrated failures. No merge/deployment/automation/credential changes.


## Pre-launch containment gate — 2026-11-22

Recovered branch 469c76bc635a73aadd7a4d46b45ec2e45736b38c. Corrected a concrete safety defect: the Linux local worker previously launched subprocesses even when its subreaper guard refused ownership, then merely marked the receipt unconfirmed afterward. A detached worker could still produce side effects. The real POSIX scheduler path now raises before Popen on Linux when arm() fails, retaining the existing failure receipt and no-retry reconciliation behavior. macOS retains its previous path. Added a source regression assertion. Exact-head Linux end-to-end test, durable receipt validation, and full suite remain pending; do not claim runtime validation. Next: run a Linux CLI under an already-active subreaper, assert no worker marker is created and the persisted work is unconfirmed; run detached-grandchild regression and full suite. No merge/deployment/automation/credential changes.


## Linux nested-supervisor integration regression added — 2026-11-22

Extended the previous pre-launch containment fix with a real Linux CLI integration regression: run the queue worker under an inherited PR_SET_CHILD_SUBREAPER supervisor, supply a command that would write a marker, assert the command never launches, the marker remains absent, the queue survives restart in RECONCILING, and the receipt records guard inactive / cleanup unresolved / exit 127. This is committed test code, **not yet an executed test**; Linux exact-head run remains the next gate. Preserve parent 6e3ea10e52d81eff47094f424075330d274403d6 for rollback.


## Unreapable adopted-child reconciliation — 2026-11-22

Recovered branch 6e8f17396f4e118ac41052882fe305f5ed2cadfd and its actual guard/scheduler/test source. Found a false-cleanup classification in LinuxAdoptedDescendants.finish(): when procfs reported an adopted PID but waitpid raised ChildProcessError, the guard silently ignored loss of reaping ownership, potentially returning cleanup_unresolved=False. Changed the real guard to mark this uncertainty unresolved, which feeds the already-wired scheduler durable RECONCILING classification; added a targeted Linux regression injecting a lost waitpid ownership claim. Source change is bounded and preserves the prior pre-launch containment gate. Validation: independently run the guard regression and Linux scheduler tests against this new exact head; full checkout unavailable while Mac offline and isolated container GitHub DNS fails. Do not claim unexecuted integration or full-suite success. No merge, deployment, credentials, permissions, or automation edits.


## Independent Linux execution route discovery — 2026-11-22 (no validation claim)

Fresh provider-native readback confirms agent containment branch head 1180afddfbd873326375a114fd62c331d08c1dec, while APEX PR #380 remains open. Queried GitHub Actions for runs on engineering/agent-linux-detached-subprocess-containment-20261122: zero runs, so no changed-head CI proof exists. Investigated an alternative authorized Linux runner rather than retrying the offline Mac: the connected Sprites organization already contains an existing apexfs-ci-20261004 environment, but an actual exec attempt returned an account billing prerequisite (add credit card). Do not activate paid infrastructure without operator approval. Local Linux checkout attempt failed on github.com DNS resolution; this is an environment/access problem, not a demonstrated source defect. No Linux regression was executed in this invocation and no runtime code was changed. Next executable transition: use an already-authorized no-payment Linux execution host with access to exact GitHub head, run tests/test_scheduler_inspector_bridge.py and the complete suite, inspect durable RECONCILING receipts, then repair only demonstrated failures. Preserve other automation ownership and do not merge/deploy or modify schedules.


## Exact-head Ubuntu GitHub Actions full-suite verification — 2026-11-22 HST

Recovered provider branch d20fef7c8e32d54ef37179a6bb6592b51b3d92d5 and brought the authorized Mac back into the validation path. On macOS the focused scheduler/descendant tests completed 14 passed, 5 Linux-only skipped. The local Colima VM could not start because its image cache clonefile path was missing, and the Mac filesystem reported only ~231 MiB free; no disk cleanup or payment action was attempted. Instead invoked the repository existing CI workflow via gh workflow run ci.yml --ref engineering/agent-linux-detached-subprocess-containment-20261122. GitHub Actions Ubuntu run https://github.com/GlacierEQ/apex-control-plane/actions/runs/45124376032 independently reports SUCCESS on exact code SHA d20fef7c8e32d54ef37179a6bb6592b51b3d92d5: 1,145 passed, 29 skipped, 8 subtests passed in 19.00s; compile step succeeded. This is genuine Linux changed-head full-suite execution, not proof of deployed agent behavior. The previous runner-access blockage is resolved through existing workflow_dispatch; future Linux verification should use that route, not require Mac-hosted Linux. Next: inspect why 29 tests skipped and add targeted observable receipt/adversarial coverage only for actual gaps; use existing CI to validate code changes. Do not merge, deploy, alter schedules, credentials or other workstreams.


## CI verification gap closed in source — 2026-11-22 HST

The prior exact-head Ubuntu run 45124376032 passed 1,145 tests but its default pytest `-q` output did not reveal the reasons for 29 skips. Updated `.github/workflows/ci.yml` to use `pytest -q -ra` and require a second explicit Linux adversarial selection for detached-grandchild cleanup, nested-subreaper launch refusal, preexisting-subreaper ownership and unreapable-child reconciliation. The CI step now fails if any selected adversarial test fails; the full suite remains required. Source commit `e89a9de4ed686c2280d13d352da832e9272946f9`. This is a CI verification-path improvement, not a new deployed agent behavior. Next: execute workflow_dispatch on this exact head and independently inspect skip reasons and the focused adversarial selection; repair demonstrated failures. No schedule, production, permissions, merge or credential change.


## Linux subreaper restoration failure — 2026-11-23 HST

Source `src/posix_descendant_guard.py` now catches OSError/ValueError/AttributeError raised while restoring PR_SET_CHILD_SUBREAPER, marks cleanup unresolved, and always clears guard.enabled. This prevents a restoration exception from masking the scheduler's structured fail-closed cleanup outcome. Regression `test_linux_guard_restore_exception_is_unresolved_and_disarmed` added in `tests/test_scheduler_inspector_bridge.py`. Source commit d00567593e2769cff24641746454f06f5e6dafef; regression commit f037413ea8a6407603d2923c41696127523afb3c. Tests on the new head are not yet verified. Next: run Ubuntu CI against this branch and inspect the focused adversarial selection and full-suite skip reasons; verify durable scheduler reconciliation receipt on restoration failure. No deployment or merge.


## 2026-11-23 — branch-native Linux CI trigger repaired

- Recovered owning branch and `.github/workflows/ci.yml` via GitHub native readback. The workflow previously accepted manual dispatch, main/develop pushes, and main-targeting PRs; engineering branch pushes did not trigger its Linux tests.
- Updated only the CI push branch filter to include `engineering/agent-linux-detached-subprocess-containment-20261122` in commit `5fe47665926d8e9872cca64f38a3912c5af3d2f9`. Existing main/develop behavior, test steps, and privileges are unchanged. This is a branch-specific test trigger, not a scheduled automation change or production deployment.
- Acceptance: a subsequent branch push triggers Ubuntu CI, executes full pytest with skip reasons and four explicit Linux adversarial tests; inspect native workflow jobs/logs before claiming validation.
- Continuation: inspect GitHub Actions for this notes-update commit, read exact-head Linux results and skip reasons, repair failures in source; retain PRs unmerged and deployment unchanged.


## 2026-11-23 — subreaper restoration regression required in Linux CI

- Recovered native workflow and runtime regression source. The prior focused Linux CI selector omitted `test_linux_guard_restore_exception_is_unresolved_and_disarmed`, despite the runtime repair at d005675 and test at f037413.
- Updated `.github/workflows/ci.yml` in commit `3b0f664418b40b98c5f4dc22dae9d1e9e4fd3c8c` to require this fifth Linux adversarial test in addition to the existing four and full suite. This is verification wiring, not proof of test execution or production runtime behavior.
- Acceptance: provider-native Ubuntu job executes full suite plus five selected adversarial tests on exact branch head; inspect skip reasons and receipt outcome. Continuation: obtain GitHub Actions job and logs for latest head; fix any failing tests or actual scheduler defects without merging/deploying.


## 2026-11-23 — exact-head Ubuntu proof and adversarial test identity hardening

- Native GitHub commit status for `00e1be8476c461a1487ff4b03d7f2c6dd9d66727` reports success, linked to Actions run `45174281725`, job `137691390339`. Read the actual Ubuntu job logs: `1146 passed, 29 skipped, 8 subtests passed in 19.46s`; focused Linux selection `5 passed, 13 deselected in 1.87s`. Compile and commit status reporting passed. This establishes Linux CI execution of the restoration regression, not deployed/runtime-host invocation.
- Skip reasons reconciled: 15 ChatGPT context bridge and 13 Spiral live journal tests require a pinned real Spiral checkout; one tool-catalog test requires the estate skills directory. These 29 are unrelated to Linux guard failures; do not count them as tested.
- Found a false-confidence gap: `pytest -k` succeeds even when one of five expected test names is renamed or disappears, provided other tests still match. Replaced substring selection with five exact pytest node IDs in `.github/workflows/ci.yml` at commit `b0c779ec158773ff2417cb2a9ff871ac97c2d7ec`. A missing/renamed adversarial test now causes pytest collection error and fails CI rather than silently reducing coverage.
- Acceptance for the new head: GitHub Actions Ubuntu compile, full suite, and five exact node IDs all pass; inspect job logs and native status. Preserve all existing permissions and branch triggers. Continuation: inspect the automatically triggered CI for this notes commit; if green, prioritize actual scheduler durable-receipt behavior and integration gaps, not additional CI-only patches. No merge, deployment, credential, permission, or scheduled-task changes.


## 2026-11-23 — exact-node Ubuntu CI independently confirmed

- GitHub-native combined status for `6f3abc817bd2aafcb8fd0a118c6d57d20fd2e75f`: success, Actions run `45187426275`, job `137736563883`. Read job steps and decoded logs directly: Ubuntu Python 3.12 full suite `1146 passed, 29 skipped, 8 subtests passed in 21.97s`; five **exact node ID** Linux adversarial regressions `5 passed in 1.96s`; compilation passed; GitHub status POST returned HTTP 201. This resolves the previous exact-node CI execution gap; no host adoption or deployment is inferred.
- The 29 skips still exclude pinned Spiral and estate-skills integration. The branch source `src/posix_descendant_guard.py` and `src/control_plane.py` was recovered; no additional runtime code defect was demonstrated by this CI run. Container git checkout failed on DNS resolution of github.com, so no independent exact-head local regression execution was possible. Do not count a source readback or green CI as a new deployed capability.
- Continuation cursor: inspect current owning scheduler receipt state and integration boundary, reproduce a real failure before changing runtime code, run changed-head tests on authorized runner, independently read back provider result. Preserve distinct Omni_Engine, structured memory, legal and continuity workstreams. No merge, deployment, permission, credential or automation configuration changes.
