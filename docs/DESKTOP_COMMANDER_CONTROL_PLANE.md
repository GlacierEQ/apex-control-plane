# Glacier Desktop Commander — Supabase Local-Agent Plane

Glacier Desktop Commander remains a **local stdio MCP server**. Backend Ops does not turn the desktop into an inbound HTTP service.

The connection is an outbound local-agent bridge:

```text
UDC local process
  -> local Ed25519 identity
  -> signed outbound request
  -> apex-desktop-commander-bridge
  -> approved device/root policy
  -> durable local-agent queue
  -> append-only receipts
```

## Source and validation

Private source repository: `GlacierEQ/UDC`.

Merged bridge source: `07ca4b4bd50d9ec6c368a2579c3032c1648798cf`.

The exact pre-merge source SHA `8bbf1c7751ec0ebbdcc4f98d6fc48f3adb00c048` was validated through the existing **public Action Face**. The private UDC repository contains no executable GitHub Actions workflow.

Validation action: `udc-supabase-bridge-ci`.

Public Action Face run: `33686159662`.

Immutable private result: `GlacierEQ/llm-runner-teams/results/udc-bridge-ci-20260902-2142.json`.

The validated workload completed:

- `npm ci` — exit 0.
- TypeScript `tsc --noEmit` — exit 0.
- `npm run test` — exit 0.
- bridge-policy tests — passed.
- `npm run build` — exit 0.

The public runner used OIDC → Keymaster → one-repository read token, exact-SHA checkout, `persist-credentials:false`, immutable private result publication, and token revocation.

UDC was added narrowly to the existing Keymaster bootstrap repository allowlist. Admission receipt: `79d49324-645e-401d-9137-95fb481ca38f`. No wildcard repository admission was added.

## Backend runtime

Live Edge function: `apex-desktop-commander-bridge` v3.

Live SHA-256: `a79a9200fce9d74469b058cce24d3b9588ff182fd44109e86be54184632c2fc6`.

Live migrations mirrored here exactly:

- `20260902202019_desktop_commander_local_agent_plane_v1.sql`
- `20260902202236_desktop_commander_operation_policy_v2.sql`\n- `20260902214312_github_oidc_udc_workload_allowlist_v1.sql`\n- `20260902221859_desktop_commander_registry_runtime_ready_v3.sql`
- `20260902223005_desktop_commander_bridge_v3_registry_v6.sql`
- `20260902222903_desktop_commander_heartbeat_monotonic_v5.sql`
- `20260902222552_desktop_commander_runtime_hardening_v4.sql`

The local-agent data plane is service-role-only with RLS and contains device identities, jobs, append-only receipts, nonce replay records, and an explicit remote-operation policy.

## Device trust

Enrollment uses the Vault-held bootstrap credential `desktop_commander_enrollment_token_v1`.

The desktop generates an Ed25519 keypair locally. The private key remains on the desktop. Backend Ops stores only the public key and hashes/metadata needed to identify and authorize the device.

Post-enrollment calls are signed over timestamp, nonce, HTTP method, path, and body hash. The bridge enforces a bounded timestamp window and stores used nonces to reject replay.

A device cannot claim jobs until it is approved with at least one backend-approved root.

## Remote execution boundary

Remote queue operations are intentionally narrower than local UDC:

- `read_file`
- `read_multiple_files`
- `list_directory`
- `search_files`
- `get_file_info`
- `write_file`
- `edit_block`
- `run_profile`

Edits require `expected_before_sha`.

`run_profile` is limited to `git_status`, `git_diff`, `test`, `build`, `lint`, and `typecheck`.

The remote queue does not expose arbitrary shell commands, system-power actions, service management, registry mutation, process termination, scheduled-task control, or ownership changes.

## Current state

Source/runtime: **verified**.

Physical device: **not yet enrolled**.

Worker state: **source/runtime verified / physical device unbound**.

Selection: **disabled**.

The connector must not be called online until the physical UDC process enrolls, requested roots are approved, a signed heartbeat is observed, and one read-only claimed job completes with a receipt.


## Registry separation

Backend Ops models source/runtime readiness and execution-plane readiness separately:

- `desktop_commander.glacier` is `source_runtime_ready`, connected/authenticated, but non-selectable until a physical device proves the final runtime boundary.
- `github.actions.public_runner` is a separate healthy execution-plane connector carrying the exact-SHA/OIDC/Keymaster/immutable-result proof for private workload validation.

This prevents a GitHub source-control or Actions-runner problem from being misclassified as a Desktop Commander device problem.


## Runtime hardening v4–v6

The original migration history remains intact. Corrective migrations harden the live runtime without rewriting prior ledger entries.

- Re-enrollment with a changed public key or host fingerprint resets the device to `pending`, clears approved roots, and requires approval again.
- Enqueue is atomic under concurrent idempotency-key reuse. Same key + same payload replays the original job; same key + different payload fails closed.
- Expired claimed jobs are reclaimed while attempts remain; exhausted expired leases are terminalized with an append-only failure receipt.
- Terminal results require the device to remain approved and to still own a live lease.
- Result payload size is enforced from the operation policy's `max_result_bytes`.
- Heartbeat persistence and its append-only receipt are committed transactionally by `record_desktop_commander_heartbeat_v1`.
- Claim receipts are written transactionally inside the claim RPC rather than best-effort in Edge.
- Bridge v3 distinguishes a duplicate nonce (`nonce_replay_rejected`) from a nonce-store failure (`nonce_persistence_failed`).
- Heartbeats merge runtime metadata rather than replacing source provenance.
- An approved heartbeat proves presence, not execution. Selection remains disabled until a completed **read-only claimed job** records the final proof.
- After that read-only proof, subsequent heartbeats preserve the verified selection state; they cannot silently demote it.

Physical execution remains unverified in the current live state. No device has yet crossed the final read-only execution gate.
