# Agent subprocess timeout reconciliation — 2026-11-21

Base: GlacierEQ/apex-control-plane engineering/agent-scheduler-inspection-failclosed-20261121 at f5659af.

## Real consumer change
The --run-next-local / --drain-local CLI now bounds local subprocess execution (120 seconds by default, optional GLACIEREQ_LOCAL_COMMAND_TIMEOUT from 0 to 3600 seconds). A timeout records a durable execution receipt with inspection_failed, outcome_verified=false and cleanup_unresolved=true; the scheduler's existing negative-evidence gate transitions the claimed item to RECONCILING rather than authorizing blind replay. No external work is claimed.

## Evidence
Python 3.13 focused original CLI tests: 15 passed. New adversarial timeout/restart test: 1 passed. Full changed-worktree suite: 1,097 passed, 29 skipped, 8 subtests passed; exit 0. Test uses an actual sleeping subprocess and verifies persisted receipt, restart state and no immediate re-execution. No deployment or host-level automatic invocation was established.

## Remaining / continuation
Inspect actual subprocess durable receipt integration and ensure process-group cleanup and output bounding for noisy children; a timeout does not establish descendant termination. Next: recover this branch head, inspect CLI adapter and inspector, add genuine process-to-inspector-to-scheduler integration tests, then read back remote commit. No merge or deployment.

## 2026-11-21 bounded subprocess capture and process-group reap
On the actual `--run-next-local` / `--drain-local` worker adapter, replaced unbounded `subprocess.run(capture_output=True)` with disk-backed stdout/stderr, per-stream 65,536-byte persisted capture with explicit truncation flags, and a new-session subprocess group on POSIX. Timeout now attempts SIGKILL against the process group and bounded direct-child wait; uncertain descendant effects remain explicitly `cleanup_unresolved=true` and enter durable RECONCILING, even when the direct child was reaped. No automatic retry of ambiguous effects. The change does not attest external effects, and temporary output files may still grow on disk during a running command; future hardening should enforce a disk quota and independently inspect descendant termination.

Changed-head Python 3.13 focused CLI: 17 passed. Full repository suite: 1,098 passed, 29 skipped, 8 subtests passed, exit 0. Adversarial test executes a real process writing 200 KB to both streams and verifies the persisted receipt is bounded and marked truncated. Continuation: integrate standalone inspector's actual subprocess receipt into the scheduler and verify descendant cleanup plus output drain semantics; do not infer host deployment from these tests.

## 2026-11-21 — local subprocess disk quota gate

Recovered branch at 75faee8. Real local execution previously used unbounded disk-backed temporary output despite 64 KiB persisted receipt caps. Added POSIX RLIMIT_FSIZE 1 MiB per stream to actual subprocess launch, and fail-closed exit status 125 when either output file reaches quota even if the child reports zero. Receipt includes disk_limit_bytes_per_stream and output_quota_exhausted. This avoids silently accepting a partial write as success (observed during adversarial test: Python os.write of 2 MB returned after writing only 1 MB, and process exited 0). Windows remains without a disk quota; receipt records null limit. Focused CLI suite: 18 passed. Full suite outcome recorded separately after execution. Next: independently prove descendant cleanup and integrate standalone receipt inspector into worker adapter; preserve fail-closed reconciliation.

Full changed-head suite (Python 3.13): 1099 passed, 29 skipped, 8 subtests passed, exit 0 (4.58s), before evidence-only note commit.

## 2026-11-21 streaming artifact readback

Replaced whole-file `handle.read()` during local `--verify-file` attestation with 1 MiB chunked SHA-256 and byte counting, retaining pre/post opened-descriptor metadata comparison. This prevents artifact size from directly determining the Python verifier's peak memory consumption while preserving digest/size semantics and fail-closed mutation checks. A real CLI test writes and independently verifies a 512 KiB artifact and reopens the durable receipt after reconstruction. Exact changed worktree Python 3.13: 19 focused CLI tests passed; full suite 1100 passed, 29 skipped, 8 subtests passed. An initial 20 MiB artifact test exposed an existing RLIMIT_FSIZE behavior: the child output quota also caps files written by the child, not only stdout/stderr. This remains a separate unresolved functional restriction; do not represent the 1 MiB limit as output-only. Next: separate output quota enforcement from arbitrary child artifact writes, without allowing stdout/stderr spool growth; independently verify process-tree cleanup and connect standalone inspector.

## 2026-11-21 — parent-owned strict output quota, artifact writes unblocked

Recovered provider head `6bc0e5daaef010fa8eb372b7611faae58f5c1cbe` and repaired the RLIMIT_FSIZE coupling discovered in the preceding run. The actual `--run-next-local`/`--drain-local` POSIX adapter now consumes stdout/stderr through parent-owned selectors, counts each stream against its own 1 MiB ceiling, retains at most 64 KiB of each stream in memory, and kills the isolated subprocess group on quota exhaustion or timeout. No child file-size resource limit is applied, so legitimate large artifact writes are no longer blocked by output-capture policy. A 20 MB real subprocess artifact was created and its verified execution receipt recovered; the 2 MB stdout quota adversary still fails closed. Windows retains its previous temporary-file fallback without a strict quota claim. Output overrun is discarded by the parent rather than persisted. Process-group descendant termination remains unproven independently, and the standalone receipt inspector is not integrated.

Changed-head Python 3.13: 20 focused CLI tests passed, full repository suite 1,101 passed, 29 skipped, 8 subtests passed, exit 0; `git diff --check` clean. Continuation: independently test surviving descendants and timeout cleanup, then wire the standalone inspector into the actual worker receipt path. No merge/deployment authorized.
