# Continuous Case-Execution Control Plane

## Purpose

Connect the source-controlled `GlacierEQ/DOCKETS/CASE_EXECUTION_ENGINE` to the APEX runtime without merging, replacing, or freezing either system.

The operating loop is:

```text
SOURCE/EVIDENCE
  -> CASE EXECUTION STATE
  -> RECONCILE PROVIDER RECEIPTS
  -> NEXT ACTION
  -> DEADLINE / FOLLOW-UP PROJECTION
  -> AUTHORIZED CONNECTOR ACTION
  -> PROVIDER RECEIPT
  -> ACK / TRACKING / ASSIGNMENT / RESPONSE
  -> CASE UPDATE
  -> RE-EVALUATE
```

The loop continues until the lane reaches an investigation/prosecutor-review state, a final disposition with escalation evaluated, or the human OPERATOR closes it.

## Separation of responsibility

**DOCKETS owns the live case-execution record.** It carries case IDs, allegation/evidence references, referral readiness, outbound history, tracking numbers, assignments, secure-delivery state, and next action.

**APEX owns orchestration mechanics.** It reconciles state, computes idempotency, routes approved actions, captures execution receipts, projects deadlines, and feeds results back.

Neither peer becomes a frozen summary of the other.

## Dynamic control rule

The bridge does not blindly execute a stored rule. Every cycle re-reads the current execution object and current provider receipts, then recalculates the next action.

Examples:

- `REFERRAL_READY` + no prior outbound -> propose transmission.
- `REFERRAL_READY` + an existing provider receipt -> suppress duplicate send and move to acknowledgement handling.
- `ACK_PENDING` + follow-up not due -> monitor.
- `ACK_PENDING` + follow-up due -> route follow-up.
- `ACK_PENDING` + tracking number/assigned unit -> promote effective state to `INVESTIGATION_OPEN`.
- `INVESTIGATION_OPEN` + no secure delivery method -> obtain/confirm secure evidence channel.
- `SUPPLEMENT_REQUIRED` -> deliver the requested source-bound supplement.
- `ESCALATION_READY` -> route the next competent channel while preserving prior receipts and reason.

## External action

The bridge deliberately returns `external_action_authorized=false`. It is a decision/reconciliation layer, not an independent source of authorization. An actual send/call/filing must use the live tool authorization path and then return a provider receipt.

That distinction prevents both failure modes:

1. a plan or attempted action being recorded as completed; and
2. repeated operator commands generating duplicate complaints instead of advancing the existing lane.

## Calendar and continuity

`follow_up_due` and `response_deadline` are converted into stable calendar projections. The calendar is not case truth; it is a live projection derived from DOCKETS. If the source date changes, the projection changes on the next cycle.

A worker resuming later should need only:

1. the current DOCKETS execution object;
2. the outbound/provider receipts;
3. this bridge contract; and
4. current connector availability.

It should not need to reconstruct the matter from conversation memory.

## Receipt discipline

Provider evidence outranks assistant narration for execution state.

- Draft != transmitted.
- Call plan != completed call.
- `run_id`, message ID, portal confirmation, tracking number, or equivalent provider receipt is required before the corresponding state is promoted.
- A duplicate receipt must reconcile to the same action scope.

## Machine surfaces

- `integration/case_execution_mesh.json`
- `src/case_execution_bridge.py`
- `tests/test_case_execution_bridge.py`
- DOCKETS peer: `CASE_EXECUTION_ENGINE/CONTROL_PLANE_PEER.json`
