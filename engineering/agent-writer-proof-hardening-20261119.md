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
