# Agent capability writer proof hardening — 2026-11-19

Owner: GlacierEQ/apex-control-plane `src/control_plane.py` `--exec-capability`.

## Recovered state

Recovered remote `engineering/agent-writer-liveness-receipt-20261119` commit `4ccda04148aabc73ab2361558b2c4acdbe8900f3` into an isolated Mac worktree; preserved other worktrees and other automation lanes. Prior source-only writer-liveness correction had no real changed-head tests. Existing stdin-delivery and cleanup regressions: 6 passed on the recovered source.

## Integrated correction

The final stdin delivery proof now rejects **any recorded writer error**, not just a mismatched byte count or a still-alive writer. The writer thread has a stable diagnostic name, permitting targeted liveness fault injection without modifying unrelated threads. Added real `--exec-capability` subprocess regression: force the writer-liveness probe to report unresolved even after all bytes are written; verify exit 74, incomplete delivery, explicit `InputWriterUnresolved`, and no mission completion. This regression exercises the actual receipt consumer, not just a helper.

## Verification and boundary

Focused stdin delivery tests: 3 passed, including new adversarial CLI case. Previously recovered cleanup suite: 6 passed. Full Python 3.13 suite pending completion and must be read back before declaring broad verification. This synthetic liveness fault is not proof of native non-POSIX thread cancellation or descendant containment. No merge/deployment/permission/credential/task change.

## Continuation cursor

Read back exact changed GitHub branch and commit, collect `/tmp/glaciereq-agent-suite-20261119.log` result from the Mac, repair any failure, reproduce intermittent post-receipt process hang with process/pipe tracing, and implement native non-POSIX containment only with real platform verification.

## 2026-11-19/20 independent full-suite recovery

Recovered the exact previously pending Mac log `/tmp/glaciereq-agent-suite-20261119.log` through the authenticated connected Mac (device `6787800d-2c79-47f2-8864-162a867dd4a1`). The file's final pytest summary is **1128 passed, 29 skipped, 8 subtests passed in 504.69s**. This closes the prior *missing result* uncertainty for that completed test invocation; it does not establish a fresh run on a later head, a fix for the intermittent post-receipt hang, or non-POSIX process-tree containment. Source blob at readback: `src/control_plane.py` `19f8fe0e98072f479697d70f5f6f96d10b21bdb2` on this branch. The Mac reports 9.2 GiB free on the data volume. A follow-up Mac git-status command remained unresponsive, so no new runtime modification is claimed.

**Next exact transition:** Recover the live Mac worktree HEAD/status and compare it to GitHub branch, then reproduce the intermittent post-receipt hang with a bounded CLI harness and inspect child/thread/pipe state. Implement only a reproduced repair, rerun focused regressions and the complete Python 3.13 suite, then independently read back the changed branch. No automated retry of uncertain external effects.

## 2026-11-19 bounded EOF-observation correction

Authenticated GitHub source recovery found the output-drain joins used only the original child execution deadline. Once a child exits near that deadline, a reader thread may not yet have observed EOF; joining with zero remaining budget can misclassify the invocation as a timeout despite successful child exit. On this existing branch, commit `d14a297b9263b8758e3375af04dac611278e45e2` changes the real `--exec-capability` consumer to grant at most 250 ms of *shared* post-exit EOF observation to both drain threads. It retains timeout handling for live children, descendant-held pipes, incomplete-output classification, process-group termination, and stdin-writer proof.

**Verification:** Authenticated GitHub readback confirms the changed source blob `0b0cabf3ca0611bfcd376bbe782b1208b794bc67`. An isolated local POSIX subprocess test ran 30 real child processes and confirmed EOF observation and reader completion; a separate bounded-join test passed (2 tests total). This is a focused behavior reproduction, not a full APEX integration test. The Mac's registered native runner is offline, so full changed-head Python 3.13 suite and intermittent-hang reproduction remain pending. Prior full-suite results remain historical only. No merge or deployment.

**Exact continuation:** When the native Mac runner returns, run real `--exec-capability` deadline-edge and descendant-held-pipe regressions against commit `d14a297b9263b8758e3375af04dac611278e45e2`, run complete Python 3.13 suite, inspect final receipts and thread/process state, then read back GitHub and update this same record. Do not treat a post-exit grace as proven repair of the intermittent hang until reproduced and measured.
