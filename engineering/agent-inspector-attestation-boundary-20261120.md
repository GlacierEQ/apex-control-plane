# Agent receipt attestation boundary — 2026-11-20

## Recovered owner state

Based on `engineering/agent-inspector-malformed-status-20261120` (commit `4a6b623`), preserving its duplicate-key, nonfinite, nesting and malformed-status protections. The real `src/control_plane.py` final execution receipt always emits `outcome_verified: false`, even when the subprocess exits zero (`process_succeeded_unverified`). The existing read-only inspector nevertheless allowed a caller-controlled receipt with `outcome_verified: true` and synthetic cleanup booleans to promote the inspected outcome to verified. This violated the executor's subprocess-exit-only evidence boundary.

## Change and acceptance criteria

The real `--inspect-receipt` consumer must never turn untrusted durable JSON fields into attested mission success. Preserve independent cleanup diagnostics, pending process-identity inspection, and no-retry behavior. Set `outcome_verified: false` for terminal receipts and expose `outcome_evidence: unattested_receipt`. Exercise zero-exit, failure, and invented terminal-status forged receipts through the real CLI, alongside prior inspector regressions.

## Verification and continuation

Focused CLI/inspector suite: 13 passed on Mac Python 3.13 with pytest `-o pythonpath=src`. Full repository suite executed separately using an isolated basetemp; final count should be read from the test run output, not inferred from this note. `git diff --check` clean. This branch is an isolated implementation, not a merge or deployment.

Next: recover the actual scheduler's receipt consumer and enforce `outcome_verified` and cleanup state at its transition boundary; validate with genuine execution receipts. Native Windows and descendant containment still require separate proof. No scheduled task configurations, credentials, permissions, merges or deployments changed.
