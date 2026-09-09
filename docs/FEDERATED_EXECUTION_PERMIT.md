# Federated Execution Permit

## Purpose

GlacierEQ now has two independent freshness domains that protect external execution:

1. the primary/global control-plane awareness fabric, which binds an action to current source-bearing reality; and
2. Backend Ops communications continuity, which binds an outbound action to an active operator-approved plan, a fresh context packet, duplicate/bounce guards, and execution-time preflight.

Both guards are necessary. Neither one alone proves that the other was checked in the same provider attempt.

The federated execution permit is the compositional proof between them.

## Sequence

```text
DOCKETS / current mission state
        |
        v
primary dynamic-awareness evaluation
        |
        +--> current global frontier hash/watermark
        +--> awareness receipt reference
        |
        v
Backend Ops active plan + continuity_start_outbound_v1
        |
        +--> execution_guard.execution_ready = true
        +--> active plan gate authorized
        +--> fresh packet/preflight
        |
        v
continuity_issue_federated_execution_permit_v1
        |
        v
short-lived action-specific permit
        |
        v
provider adapter validates + consumes permit
        |
        v
provider dispatch
        |
        v
provider-native receipt -> continuity/DOCKETS/global reconciliation
```

## Permit invariants

A permit can be issued only when:

- the continuity action is already in `executing` state;
- its Backend execution guard is ready;
- the action remains bound to an authorized action in an active operator-approved case plan;
- its context packet still exists and has not expired;
- Backend Ops has a healthy recent checkpoint for the primary global frontier;
- the supplied global-frontier hash exactly matches that checkpoint;
- a primary dynamic-awareness receipt reference is supplied; and
- the primary awareness source watermark is not older than the checkpointed global frontier watermark.

Permits default to five minutes and cannot exceed ten minutes.

## Single-use dispatch

Provider adapters should validate and consume the permit immediately before the provider mutation. Consumption is recorded as append-only evidence with outcome `PROVIDER_DISPATCH_STARTED`.

A consumed, revoked, expired, mismatched, or stale-frontier permit cannot be reused.

## Staged rollout

The permit primitive is deployed before mandatory provider-adapter enforcement. This avoids silently breaking existing Gmail, phone, or Calendar execution surfaces while they are migrated.

Until an adapter is explicitly bound, it must not claim that it has satisfied the federated execution contract merely because the permit tables/functions exist.

Target adapter contract:

```text
current primary awareness
+ current Backend continuity/plan state
+ federated permit validate/consume
+ provider mutation
+ provider receipt
```

The permit does not grant mission authorization. It proves that two already-authoritative execution guards were current and mutually consistent immediately before provider dispatch.
