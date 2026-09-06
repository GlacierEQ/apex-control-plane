# Legal Execution Continuous Control Plane

## Live runtime

**Hub:** Supabase project `supabase-backend-ops`  
**Matter:** `case:1FDV-23-0001009`

This is an event-driven execution layer over the existing continuity substrate. Source evidence remains in its native systems (DOCKETS, Gmail, calls, court systems, storage). Supabase stores normalized execution state, provider receipts, provenance, commitments, calendar bindings, attention, and immutable transitions.

### Shared substrate

- `continuity_matters_v1`
- `continuity_events_v1`
- `continuity_context_packets_v1`
- `continuity_outbound_actions_v1`
- `continuity_action_receipts_v1`
- `continuity_commitments_v1`
- `continuity_calendar_bindings_v1`
- `continuity_attention_queue_v1`
- `continuity_ingest_queue_v1`
- `continuity_sync_cursors_v1`

### Legal execution layer

- `legal_execution_state_v1` — authoritative current state
- `legal_execution_transitions_v1` — immutable transition log
- `legal_execution_control_v1` — single control projection
- `legal_control_transition_rules_v1` — legal state-transition rules
- `legal_execution_state_rank_v1` — state ordering/non-regression support
- `legal_control_deadletter_v1` — reducer failures / malformed events
- `legal_execution_transition_v1(...)`
- `legal_reduce_continuity_event_v1()`
- `legal_record_external_action_v1(...)`
- `legal_execution_snapshot_v1(matter_key)`

## Execution law

1. **Source before state.** No state promotion without a source/provider event.
2. **Send != delivery.** Provider send receipts create delivery-confirmation state, not acknowledgement.
3. **Bounce is actionable state.** Delivery failure routes to repair without erasing the failed attempt.
4. **No regression.** Later low-level events do not silently downgrade a materially more advanced state.
5. **Idempotency everywhere.** Sends, receipts, commitments, and transitions carry unique keys.
6. **Dead-letter failures.** Reducer errors are persisted instead of silently dropping events.
7. **Partial acknowledgements remain partial.** A receipt that does not establish substantive agency intake must not be promoted to full acknowledgement.
8. **Calendar is a projection.** `continuity_commitments_v1` is the deadline/follow-up source of truth.
9. **Provider identity is provenance.** Normalized channels are email/phone/calendar/other; Gmail, CALL_E, Google Calendar, etc. remain source-system metadata.
10. **No agent reconstructs current execution from memory.** Read `legal_execution_control_v1` first.

## External flow

```
Gmail / Calls / Calendar / GitHub / DOCKETS / storage / court systems
          |
          v
provider-native event + receipt
          |
          v
continuity substrate
          |
          v
legal reducer + transition rules
          |
          v
legal_execution_control_v1
          |
          +--> attention
          +--> commitments
          +--> calendar projection
          +--> evidence delivery
          +--> follow-up / escalation
          +--> immutable history
```

## Runtime workers

### legal-case-orchestrator v3

Continuity-native API for:
- snapshot
- record_action
- record_event
- transition

Deployed SHA-256: `d17ccde6ad7243a8ee920a9f795cfaaa27a60ff8ae1712ccef70e1a84139309b`

The obsolete v1 path that referenced missing `operation_ledger` / `processing_queue` tables has been replaced.

### legal-deadline-monitor v2

Reads active `continuity_commitments_v1` deadlines and reports overdue / 24-hour / 7-day pressure. It does **not** independently invent limitation periods.

Deployed SHA-256: `7c464d1deae6799c4956411e4afd617ee466774fd308bee4b730d7e72f96ef2b`

## Current referral execution example

The first CJD person-specific transmission produced a Gmail `550 5.1.1 User Unknown` bounce. That source event drove the matter into delivery repair. The source-bound referral was retransmitted to the published Criminal Justice Division mailbox and provider receipt `1a06690d88987c99` was atomically bound to the matter.

The state must remain source-driven: no acknowledgement, tracking number, investigation, or charging state may be asserted until an external source actually establishes it.

## Continuous watch

The hourly `1FDV Control Plane Watch` reads this state first, checks the exact referral provider references, ingests only genuinely new source events, reconciles commitments, and notifies only on material state change or required operator action.
