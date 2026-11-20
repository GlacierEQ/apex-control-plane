# Agent direct-child reaping evidence — 2026-11-20

Owning source: `src/control_plane.py` real `--exec-capability` consumer. Base: `engineering/agent-containment-evidence-20261120` at `5cf1276fe230317929d46450bd19070c4cd31fba`.

## Operational correction

The existing bounded termination/reaping path exposed process-group denial but did not distinguish a requested signal from an actually reaped direct child. The final structured JSON and durable final receipt now include `direct_child_reaped`: true only when `child.poll()` confirms a terminal return code; null when no delegated child was launched. A denied group signal may still leave descendants uncontained, independently represented by `descendant_containment_verified=false`.

## Acceptance and evidence

- Existing launch authorization and durable receipt gate unchanged.
- Final receipt reports observed direct-child reaping, not inferred reaping from kill requests.
- POSIX real-CLI denied-group-signal regression asserts direct child was reaped while descendant containment remains unverified.
- Focused test command: `python3.13 -m pytest -q tests/test_control_plane_group_signal_denial.py tests/test_control_plane_output_drain_deadline.py tests/test_control_plane_capability_consumer.py` — 22 passed.
- Full suite: see exact run log `/tmp/glaciereq-agent-run11-full.log` and follow-up verified result.

## Continuation cursor

Validate the combined second-kill-denial and descendant-held-pipe scenario under an isolated test root; distinguish direct-child reaping from descendant containment and test native Windows separately. Do not merge/deploy or change scheduled task configurations.
