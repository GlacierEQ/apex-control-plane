# Silent descendant containment — 2026-11-21

Owning source: `src/control_plane.py` `--exec-capability` subprocess consumer. Base: `0698f499b1c185bdd063e5d9ddc9602d80d63eb3` (`engineering/agent-descendant-reap-proof-20261121`). This work is separate from Omni connectors, structured memory, legal cases and continuity.

## Defect and acceptance

The direct worker could exit 0 while a descendant remained in the same isolated POSIX process group with all inherited output descriptors closed. Pipe EOF and successful `child.wait()` then produced `process_succeeded_unverified` despite unfinished delegated execution. Acceptance: an actual silent descendant is detected after the direct child exits, a group termination is attempted, the result is failure-classified with explicit unresolved containment evidence, and the caller cannot mistake it for successful execution. A clean single process must retain the prior behavior.

## Changed consumer

After bounded output drains, the POSIX adapter probes the owned session's process group, flags remaining members as `descendant_group_unresolved`, attempts group SIGKILL and includes that condition in `cleanup_unresolved`. Exit zero is downgraded to 74 when containment is unresolved. This is a conservative fail-closed signal, **not** proof that every descendant has been reaped or that escaped/new-session descendants were contained. Windows is unchanged.

## Validation and continuation

A real subprocess regression spawns a 30-second descendant with stdout/stderr redirected to DEVNULL, exits its parent successfully, and verifies exit 74, failed receipt, and unresolved descendant-group evidence. Test cleanup sends SIGKILL as a fallback. Focused consumer suite: 21 passed. Full changed-head suite initiated; final result must be recorded only after observed completion. Continue by testing escaped-session descendants and integrating the independent receipt inspector with the scheduler receipt adapter; never treat subprocess exit alone as outcome attestation.

## Completed verification

Python 3.13 focused capability consumer suite: **21 passed**. Entire repository suite: **1,137 passed, 29 skipped, 8 subtests passed**, exit 0. `git diff --check` and Python compile succeeded. Implementation commit `30baa20d09dd6672b00d166e8df5c425fccef365` was pushed to `engineering/agent-descendant-cleanup-test-20261121` and independently fetched through GitHub with source, regression, and note paths confirmed. This is tested branch code, not a merge, deployment, or host-level automatic invocation. Next: investigate escaped-session descendants and wire durable independent inspection into scheduler receipt production, with real-process tests and fail-closed reconciliation.
