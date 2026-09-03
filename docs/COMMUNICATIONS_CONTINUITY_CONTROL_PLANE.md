# Communications Continuity Control Plane

This layer makes email, phone, calendar, provider receipts, commitments, and case execution operate as one continuous state machine.

It is a **peer of the DOCKETS case-execution plane**, not a replacement for it.

## Authority and truth boundaries

- The human **OPERATOR** remains the source of project direction.
- `GlacierEQ/DOCKETS@master/CASE_EXECUTION_ENGINE` owns the source-controlled case-execution record.
- `GlacierEQ/apex-control-plane` owns orchestration and generic protocol/schema contracts.
- Supabase Backend Ops owns live continuity state, packets, cursors, commitments, and receipts.
- Provider-native messages, calls, calendar objects, tracking numbers, and acknowledgements are evidence of provider state.
- Calendar is a projection of commitments and deadlines. It is never an independent source of a legal deadline.
- A model statement that an action happened is never a substitute for a provider receipt.

Live case payloads, private addresses, allegation-bearing narratives, evidence bytes, and sensitive communication content do **not** belong in this public repository.

## Closed loop

```text
DOCKETS execution object
        |
        v
case_execution_bridge.ControlDecision
        |
        v
communications_continuity_bridge
        |
        v
canonical matter / alias / resolver
        |
        v
fresh context packet
        |
        v
preflight
  stale? duplicate? bounce? ambiguity?
        |
        v
explicitly authorized provider action
        |
        v
provider-native receipt
        |
        +--> continuity event + append-only receipt
        +--> follow-up/deadline commitment
        +--> calendar projection
        |
        v
DOCKETS receipt reconciliation
        |
        v
next ControlDecision
```

## Context packet

Before an outbound email, call, or calendar mutation, `continuity_build_context_packet_v1` captures a bounded snapshot of:

- canonical matter identity;
- target entity;
- source-typed facts;
- recent communications/events;
- unresolved delivery failures;
- open commitments and deadlines;
- the intended channel and purpose.

The packet is hashed and expires. If the matter changes after the packet is built, `continuity_preflight_outbound_v2` marks the packet stale and blocks execution.

## Matter identity

`continuity_matter_aliases_v1` maps stable external identities to one active matter.

`continuity_resolve_matter_v1` scores explicit routes and fails closed:

- a strong case/reference identifier may auto-bind;
- a weak name-only signal stays unresolved;
- two similarly strong case candidates stay unresolved;
- archived matters are never auto-bound.

Operational aliases/routes are private runtime data. The public repository contains only the resolver contract.

## Outbound transaction

All provider adapters use one transaction protocol:

1. `continuity_prepare_outbound_v1`
2. `continuity_start_outbound_v1`
3. provider execution
4. `continuity_finish_outbound_v1`

Prepare creates a fresh context packet, runs preflight, applies idempotency, and records an append-only preflight receipt.

Start records execution commencement.

Finish records the provider result, an append-only receipt, a timeline event, and optionally a follow-up commitment.

The control plane does **not** grant standing permission to send emails, place calls, file documents, or make other external mutations. Provider execution still requires the authorization rules of the owning execution lane.

## Preflight invariants

A normal outbound action is blocked when:

- its context packet expired;
- its matter changed after the packet snapshot;
- another equivalent action was recently created for the same target;
- the requested channel differs from the packet channel;
- the target has a recent unresolved bounce and the purpose is not delivery repair.

Delivery-repair flows may intentionally target an address associated with a known bounce because the bounce itself must be visible to the agent repairing it.

## Continuous ingestion

`continuity_ingest_and_resolve_v1` combines idempotent provider ingestion with matter resolution.

High-confidence events are bound to the active matter. Weak or ambiguous events enter the unresolved queue instead of being guessed into a case.

`continuity_attention_queue_v1` surfaces delivery failures, overdue commitments, unresolved ingestion, and calendar drift.

## DOCKETS composition

`case_execution_bridge.py` decides what the case lane needs next.

`communications_continuity_bridge.py` translates only external-action decisions into a continuity envelope. It does not create a second legal/case state machine and always leaves `authorization_required=True`.

Provider receipts are normalized and returned to DOCKETS reconciliation so execution state can advance only when provider/source evidence supports it.

## Calendar continuity

Every source-backed due date or follow-up should exist first as a continuity commitment. A calendar binding points that commitment at the provider event.

If the source date changes, update the binding/projected event. Do not create a parallel deadline whose provenance is only the calendar entry.

## Failure behavior

The plane is designed to prefer a visible unresolved state over a wrong confident state:

- ambiguous matter → unresolved;
- stale packet → blocked;
- duplicate action → blocked;
- known failed target → blocked except a delivery-repair purpose;
- provider attempt without receipt → not executed;
- missing acknowledgement → acknowledgement remains pending;
- calendar drift → attention queue;
- provider error → receipt + event + next-action re-evaluation.

That fail-closed behavior is what gives phone and email agents continuity across sessions instead of allowing each agent to improvise from partial context.
