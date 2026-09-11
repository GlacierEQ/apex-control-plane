# Federated Execution Permit

## Purpose

GlacierEQ has two independent freshness domains that protect external execution:

1. the primary/global control-plane awareness fabric, which binds an action to current source-bearing reality; and
2. Backend Ops communications continuity, which binds an outbound action to an active Operator-approved plan, a fresh context packet, duplicate/bounce guards, and execution-time preflight.

The federated execution permit is the short-lived compositional proof between those domains. It does not create mission authority and it does not accept caller assertions as awareness evidence.

## Sequence

```text
DOCKETS / current mission state
        |
        v
primary dynamic-awareness evaluation
        |
        +--> current global frontier hash/watermark
        +--> source-bound awareness receipt + watermark
        |
        v
checkpoint awareness evidence into Backend Ops peer projection
        |
        v
Backend Ops active plan + continuity_start_outbound_v1
        |
        +--> execution_guard.execution_ready = true
        +--> live active-plan gate authorized
        +--> fresh packet/preflight
        |
        v
continuity_issue_federated_execution_permit_v1
        |
        v
short-lived action-specific permit
        |
        v
provider adapter validates + atomically consumes permit
        |
        v
provider dispatch -> provider-native receipt
```

## Permit invariants

A permit can be issued only when:

- the continuity action is already in `executing` state;
- its Backend execution guard is ready;
- the action remains bound to a currently authorized action in an active Operator-approved case plan;
- its context packet still exists and has not expired;
- Backend Ops has a healthy recent checkpoint for the primary global frontier;
- the supplied global-frontier hash exactly matches that checkpoint;
- the primary-awareness receipt reference and source watermark exactly match the values checkpointed in the peer projection; and
- the awareness watermark is not older than the current global-frontier watermark.

A caller-supplied receipt string is not evidence. If the primary-awareness receipt has not been checkpointed, issuance fails closed.

Permits default to five minutes and cannot exceed ten minutes, but their expiration is also capped by the bound context packet expiration.

## Validation and single use

Validation rereads the current action, live plan gate, context packet, peer frontier, awareness evidence, and watermark. A same-hash frontier with a newer watermark invalidates older awareness evidence.

Provider adapters must validate and consume the permit immediately before provider mutation. Consumption is serialized on the permit row and succeeds only when that invocation actually records the unique `CONSUMED` receipt.

A consumed, revoked, expired, changed-packet, deauthorized-plan, stale-awareness, or stale-frontier permit cannot authorize dispatch.

## Staged rollout

The permit primitive exists before mandatory provider-adapter enforcement. Existing adapters are not allowed to claim the federated contract merely because the functions exist.

The current fail-closed boundary requires an explicit adapter binding **and** a trusted projection of the primary awareness receipt into Backend Ops. Until that projection exists, permit issuance intentionally refuses to mint dispatch authority.

Target adapter contract:

```text
current primary awareness
+ checkpointed awareness evidence
+ current Backend continuity/plan state
+ federated permit validate/consume
+ provider mutation
+ provider receipt
```
