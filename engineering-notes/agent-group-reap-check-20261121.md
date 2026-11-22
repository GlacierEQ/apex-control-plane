# Agent subprocess group termination readback — 2026-11-21

Owning source: `src/control_plane.py`, `--exec-capability` real subprocess path. Recovered stronger branch `engineering/agent-descendant-cleanup-test-20261121` at `5657a49`, rather than older scheduler-only branches. Existing same-group survivor test and durable receipt behavior preserved.

Change: after sending SIGKILL to a surviving process group following direct-child exit, perform a bounded 500ms kernel process-group existence recheck. Only clear `descendant_group_unresolved` after `killpg(..., 0)` reports `ProcessLookupError`. Signal permission failures remain fail-closed. This prevents treating signal delivery as cleanup proof, while permitting verified absence to be distinguished from unresolved cleanup. Escaped sessions remain out of scope; no host-level attestation is claimed.

Acceptance: changed-head focused subprocess tests and full repository suite; GitHub readback; no merge/deploy. Continuation: integrate independent durable receipt inspection with scheduler receipt consumer, validate restart and escaped-session behavior. No other workstream modifications.
