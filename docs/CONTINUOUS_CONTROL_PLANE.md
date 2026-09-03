# APEX Continuous Control Plane

APEX is the single orchestration authority. DOCKETS, Genius, Gmail, Calendar,
CALL-E, GitHub/Buildkite, memory systems, evidence systems, and other connectors
are domains connected through one durable mission/event/work/receipt backbone.

## Loop

OBSERVE -> EVENT -> CORRELATE -> HYDRATE -> COMPILE -> CLAIM/LEASE -> EXECUTE ->
RECEIPT -> READBACK -> VERIFY -> PERSIST VERIFIED DELTA -> WAIT/FOLLOW-UP ->
REAWAKEN -> CONTINUE.

A new session resumes the persisted frontier instead of reconstructing work from
scratch.

## Shared identity

Every cross-system operation carries a mission_id, correlation_id, event_id,
work_id, idempotency_key, provenance references, provider receipt identifiers,
and an approval_ref when external mutation is involved.

## Domain ownership

- **APEX** owns missions, events, work, routing, leases, health, receipts,
  checkpoints, retry policy, recovery, and connector coordination.
- **DOCKETS / CASE_EXECUTION_ENGINE** owns case facts, allegations, referral
  lanes, packet state, outbound ledgers, agency responses, and case completion.
- **Genius-Mastery / Genius family** owns capability graphs, progress, mastery
  frontier, synthesis, and domain verification.

APEX drives and observes domain state machines; it does not overwrite them.

## Communications

A Gmail send is not completion at API acceptance. The plane requires provider
receipt, message/thread readback, ledger reconciliation, and ACK monitoring.
Replies become events and re-enter the case.

CALL-E results emit run ID, destination, outcome, person/unit, tracking number,
supplement requests, recording/transcript references, and next follow-up.

Calendar is a wake/deadline projection surface, not the source of truth. Due
events rehydrate the mission from durable receipts and current domain state.

## CI

GitHub and Buildkite events are classified as domain/test failure,
checkout/bootstrap failure, runner/infrastructure failure, auth/connector
failure, superseded/canceled, or exact-head success. Infrastructure failure
routes to infrastructure repair and must not be misclassified as domain failure.

## Retry law

Read work may retry within policy. External-action work never blind-retries after
an uncertain attempt. Lease expiry or ambiguous provider state routes to
RECONCILING first, suppressing duplicate sends/calls/filings.

## Completion

Configured receipt kinds are mandatory. TRANSMITTED is progress, not completion.
Domain-specific terminal conditions remain authoritative.

## Persistence

- local append-only JSONL: `.apex/continuous-control-plane`
- shared multi-worker state: Supabase migration
  `20260903091500_continuous_control_plane_v1.sql`

No heartbeat, dispatch, API 200, send, or commit alone is completion.
