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
