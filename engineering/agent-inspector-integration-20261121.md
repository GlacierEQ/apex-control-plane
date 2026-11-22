# Agent inspector concurrent mutation guard — 2026-11-21 HST

Owning source: `src/inspect_execution_receipt.py`, based on `origin/engineering/agent-inspector-descendant-readback-20261121` (`5230b668`). This branch is isolated from the Omni_Engine, memory, legal, and continuity workstreams.

The existing bounded receipt read rejects >1 MiB growth, but a concurrent in-place writer could mutate an otherwise parseable receipt between initial fstat and JSON parse. The actual CLI inspector now compares pre/post descriptor identity, size, mtime_ns and ctime_ns and confirms bounded bytes equal the final size; mutation is classified `inspection_failed`, never replay-authorized. Adversarial regression modifies the receipt between the two descriptor observations. This is a fail-closed best-effort mutation check, not a cryptographic snapshot or proof against same-metadata rewrites.

Focused Python 3.13 inspector suite: 16 passed. Full suite result recorded separately after completion. Next: connect independent inspection to the scheduler's durable receipt-consumption boundary, reconciling the divergent scheduler failclosed branch before edits. Do not treat diagnostic inspection as attestation, and do not merge/deploy without approval.

Full Python 3.13 changed-tree suite: 1,140 passed, 29 skipped, 8 subtests passed in 16.38s (exit 0).
