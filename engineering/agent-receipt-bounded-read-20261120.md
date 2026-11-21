# Agent receipt bounded-read hardening — 2026-11-20

Owning path: `src/inspect_execution_receipt.py` invoked by `src/control_plane.py --inspect-receipt`.

Recovered base: `b65a4288d1506eb473cbcb013de6b5baa0b8ba47` (attestation-boundary work). Defect: `fstat().st_size <= 1 MiB` was checked before `json.load(handle)`, but a concurrently appended regular file could grow after the check and induce unbounded reading/parsing. The consumer now reads at most 1 MiB + 1 bytes and rejects excess content before JSON parsing. Existing duplicate-key, nonfinite, pending, and unattested-outcome safeguards are retained.

Code commit: `f5ca28bae64f61286b43e8c21a03d226cb280574`. Regression commit: `b058246249ebed9903ef44ca950daac62487b955`.

Mac exact-branch checkout: `/Users/kcbflux/Documents/GlacierEQ-Agent-Receipt-Test/repo`. Python 3.13 focused regression: 2 passed. Full Python 3.13 suite on the exact code/test checkout: **1,138 passed, 29 skipped, 8 subtests passed in 19.54s**. The evidence-only notes commit follows that tested code head.

Acceptance: bounded actual receipt consumption, rejection above 1 MiB, preserved pending no-retry semantics, exact-head tests, GitHub readback. No merge/deployment. Next: inspect full-suite output, add a controlled concurrent-append adversarial case, and recover scheduler-level consumption before claiming scheduler enforcement.
