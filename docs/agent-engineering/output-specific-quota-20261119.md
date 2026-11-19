# Agent capability execution — output-specific bounded capture

Base: db1399661d8291318d89a7d149fa2e063fb01b6f (PR #377 lineage).

The former POSIX RLIMIT_FSIZE quota applied to *every* file opened by the selected child, including its legitimate work artifacts. The real control-plane consumer now drains stdout/stderr through parent-owned pipes into separately capped 8 MiB temporary spools, discarding excess bytes while counting total bytes. Its JSON preview remains capped at 64 KiB. Child filesystem writes no longer inherit an artificial file-size limit. This also applies on non-POSIX hosts.

Validation: Python 3.13 focused consumer suite 18 passed; full suite 1116 passed, 29 skipped, 8 subtests passed; compileall and diff check passed. A real 12 MiB stdout producer exits successfully with counted/truncated output; a real 10 MiB child artifact write succeeds. No deployment or automatic host invocation implied.

Next cursor: inspect stdin backpressure and cancellation behavior under a large capability document with a non-reading child; add bounded stdin feeder/cancellation test if needed. Also force SIGKILL in the pre-exec gate window. Preserve receipt duplicate-prevention and no automatic replay.
