# Dynamic Awareness Execution Binding

## Purpose

This is not another behavioral rule layer.

It binds execution to **current source-bearing reality** so an old task, cached prompt, approved action, automation timer, or stale agent context cannot continue acting as if nothing has changed.

The compressed runtime principle is:

> **Current source-bearing state outranks cached action intent.**

The control plane should understand the materially relevant present state, understand what changed and its impact, identify the current frontier, and only then decide whether an existing action still advances the mission.

## Why this exists

GlacierEQ already has continuity, provenance, operator-context, case execution, communications, receipts, mission-frontier, connector, and recovery systems. The failure mode was not absence of those systems. It was that an execution surface could possess a previously valid action while failing to incorporate newer reality before dispatch.

That produces stale execution:

```text
old intent -> executor wakes up -> old action still says APPROVED -> executor acts
```

The corrected path is:

```text
objective / prior action
        |
        v
known valid state + live material delta
        |
        v
dynamic awareness
  what happened?
  what changed?
  what does it affect?
  what remains unresolved?
  is the old action still useful?
        |
        v
current frontier
        |
        +--> action remains valid -> execute -> provider receipt -> new reality
        |
        +--> action obsolete/satisfied -> do not execute
        |
        +--> reality changed -> re-evaluate before execution
```

No case-specific rule is required to derive those outcomes.

## Awareness watermark

`control_plane_action_awareness_v1` compares each action's awareness watermark with materially relevant source-bearing state in the same case/matter:

- communications;
- non-self control-plane events;
- obligations.

It exposes:

- `latest_source_state_at`;
- `awareness_watermark_at`;
- `newer_source_observations`;
- `newer_source_state_exists`;
- recent communications;
- the latest explicit dynamic-awareness evaluation, when one exists.

The semantic states are intentionally small:

- `CURRENT_WITH_OBSERVED_STATE`
- `REEVALUATE_CURRENT_REALITY`
- `CURRENT_BUT_ACTION_NOT_VALID`

They describe awareness state. They do not prescribe a case workflow.

## Evaluation receipts

`control_plane_action_awareness_receipts` is append-only evidence that an evaluator incorporated the source state through a specific watermark.

The receipt records:

- action identity;
- evaluator identity;
- source watermark;
- whether the current action remains executable after evaluation;
- the evaluator's structured reasoning/result payload;
- evaluation timestamp.

`record_control_plane_action_awareness_v1` also emits a normal control-plane receipt of type `DYNAMIC_AWARENESS_EVALUATION`.

The evaluator is responsible for understanding impact. The database does **not** replace that cognition with an expanding set of scenario rules.

## Structural dispatch fence

Dynamic awareness is enforced at the dispatch boundary rather than merely displayed in a dashboard.

### Batch/worker claim

`claim_control_plane_actions_v1` will not claim an otherwise approved action when:

- materially newer source state exists beyond its awareness watermark; or
- the latest awareness evaluation says the current action is no longer valid.

The action remains visible and recoverable. It is not silently deleted or rewritten.

### Explicit authorized attempt

`control_plane_begin_authorized_attempt` performs the same awareness check before beginning a specific action.

When reality has advanced it returns:

```json
{
  "dispatch_started": false,
  "awareness_state": "REEVALUATE_CURRENT_REALITY"
}
```

If an evaluator has incorporated current reality and concluded that the old action no longer advances the mission it returns:

```json
{
  "dispatch_started": false,
  "awareness_state": "CURRENT_BUT_ACTION_NOT_VALID"
}
```

Only a current, still-valid action crosses into `DISPATCHING`.

## Shared awareness surfaces

### `operator-impact-context`

This existing startup/context surface now includes action-level awareness in addition to operator context, the global frontier, and fresh repository-runtime projections.

Consumers can request a case or action and receive whether material source state has advanced beyond what the action currently knows.

### `execution-awareness-gate`

This is a narrow HTTP preflight surface for executors that live outside the database worker path.

Its contract is:

```text
HYDRATE CURRENT ACTION + SOURCE STATE
        |
        v
EVALUATE IMPACT
        |
        v
PUBLISH AWARENESS RECEIPT
        |
        v
EXECUTE ONLY IF CURRENT + VALID
        |
        v
PUBLISH PROVIDER RESULT
        |
        v
NEW REALITY
```

The gate itself does not send email, file documents, modify repositories, or perform another mission mutation. It exposes awareness and accepts the executor's evaluated validity result.

That makes it suitable for external actuators such as workflow engines, mail clients, agent runners, and connector workers without giving the awareness service a second execution role.

## Continuity spine

`control_plane_continuity_spine_v1` now projects active action awareness directly.

A consumer already hydrating the main continuity spine therefore does not need to discover a special email subsystem or know which external executor created an action. Stale-vs-current execution state is part of the same continuity model as operator context, global frontier, constellation, and epistemic state.

## External execution surfaces

Provider/application provenance may reveal multiple actuators using the same external identity. Those surfaces must not maintain independent, stale mission narratives.

The target topology is:

```text
                    SOURCE-BEARING REALITY
                             |
                             v
                   SHARED AWARENESS FABRIC
                             |
           +-----------------+-----------------+
           |                 |                 |
           v                 v                 v
      agent/runtime      workflow engine     mail client
           |                 |                 |
           +-----------------+-----------------+
                             |
                             v
                         ACTIONS
                             |
                             v
                       PROVIDER STATE
                             |
                             +------> new source-bearing reality
```

Registering an external surface does **not** prove it is already performing the preflight. Runtime binding state must distinguish:

- surface discovered;
- awareness endpoint available;
- external preflight configured;
- execution verified through receipts.

Do not promote those states without evidence.

## Relationship to communications continuity

`COMMUNICATIONS_CONTINUITY_CONTROL_PLANE.md` already defines bounded context packets, provider receipts, stale-packet blocking, idempotency, bounce handling, and provider reconciliation.

Dynamic awareness is broader than communication preflight. It answers a more fundamental question before any material execution:

> **Has the world materially changed since this action was last understood?**

Communications continuity remains the specialized transaction protocol for communication actions. Dynamic awareness is the shared reality-binding primitive across execution surfaces.

## Rule compression

The intended architecture is not:

```text
failure -> add rule -> edge case -> add exception -> add more rules
```

It is:

```text
observe -> understand -> evaluate impact -> act -> verify -> incorporate result
```

Hard invariants still belong where they are genuinely structural: authorization, security, provenance, irreversible-action boundaries, and integrity constraints.

Situational behavior should emerge from current awareness rather than an accumulated fossil record of prior failures.

## Verification standard

A dynamic-awareness implementation is not verified merely because a view exists.

Proof requires an actual stale action to reach a dispatch boundary and **not mutate into an execution attempt** until current reality is evaluated.

Conversely, once current state has been evaluated and the action remains valid, normal execution and provider-receipt semantics must remain intact.

The desired invariant is:

> **No stale execution context may silently outrank materially newer source-bearing reality.**
