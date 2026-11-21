# Agent scheduler receipt enforcement — 2026-11-20

Owner: APEX continuous control plane, distinct from Omni connectors, structured memory, legal case construction, and continuity.

## Recovered source

Main at 201be71; scheduler `ContinuousControlPlane.execute_next_local` accepted status='verified' even when receipt details explicitly asserted `outcome_verified=false`, `cleanup_unresolved=true`, `output_drains_unresolved=true`, `direct_child_reaped=false`, or inspector failure. Existing receipt inspector branches already emitted negative diagnostic evidence but were not consumed by this scheduler path.

## Implemented behavior

The real scheduler now persists the returned receipt and transitions to durable RECONCILING rather than COMPLETE, VERIFYING, RECEIVED, or WAITING when explicit negative execution evidence is present. No blind retry is authorized; independent eligible work remains runnable. Legacy successful verification receipts without negative evidence retain existing behavior. This is an opt-in evidence-field guard, not an attestation of positive success or a claim that an arbitrary executor callback is trusted.

## Continuation

Run `python3 -m pytest -q tests/test_scheduler_negative_execution_evidence.py tests/test_continuous_control_plane.py` and full suite on exact branch head; inspect exit codes. Independently fetch the branch's scheduler source and regression tests from GitHub. Then extend the actual worker adapter to attach inspected subprocess receipt evidence to scheduler `ExecutionReceipt.details`; test real subprocess -> inspector -> scheduler, including denied cleanup and corrupted receipt. Do not merge/deploy or alter scheduled automations without approval.
