# Relevance-Aware Dynamic Awareness V2

## Purpose

Dynamic awareness exists to prevent stale cached action intent from outranking materially newer source-bearing reality. V2 keeps that protection while removing a hidden-harm failure mode in V1: unrelated state inside the same case or null-case/global namespace could invalidate parallel work simply because it was newer.

The V2 principle is:

> Current **relevant** source-bearing state outranks cached action intent. Unrelated new context remains visible without blocking.

This is rule compression, not another case-specific behavioral layer.

## Why V1 needed refinement

V1 used case identity as the primary source boundary. That was intentionally conservative, but two effects emerged in live operation:

1. `case_id IS NULL` internal connector alerts could see unrelated global events as newer state.
2. A new communication, obligation, or event in one case lane could stale every parallel action in the same case, even when the new source concerned another recipient, obligation, or execution path.

A representation duplicate could also change semantics. For example, a source-native communication mirrored into `control_plane_events` could carry descriptive text naming another target. The mirror then appeared independently relevant even though the source communication itself was not directed to that target.

## Relevance graph

`control_plane_action_source_relevance_v2` classifies source observations as `HARD` or `SOFT` for each action.

### HARD

A source may block dispatch when it is linked by a typed relationship such as:

- explicit `action_id` or `action_key`;
- action source event or source obligation;
- provider message or thread identity;
- action target system or target reference;
- exact connector incident identity for internal connector alerts; or
- an explicit `global_execution_gate` declaration.

### SOFT

Same-case source material that lacks one of those relationships remains available to the evaluator as context, but it does not silently invalidate the action.

This allows an investigator response, records correspondence, collaboration request, or unrelated obligation to remain visible while preserving valid parallel work.

## Projection deduplication

Source-native records outrank their derived projections for relevance classification.

When a communication is already represented in `control_plane_communications`, its mirrored event is excluded from independent relevance classification. Action-outbox and obligation projection events are treated the same way unless they are the exact action source event.

This prevents representation duplication from manufacturing semantic relevance.

## Awareness states

`control_plane_action_awareness_v2` exposes:

- `REEVALUATE_CURRENT_REALITY` when newer HARD state exists for an executable/in-flight action;
- `CURRENT_BUT_ACTION_NOT_VALID` after an evaluator invalidates the action;
- `CURRENT_WITH_NEW_SOFT_CONTEXT` when only newer SOFT context exists; and
- `CURRENT_WITH_OBSERVED_STATE` when the action is current.

It separately exposes `dispatch_reevaluation_required` and `newer_soft_context_exists`, so callers do not have to infer blocking semantics from timestamps.

## Automated reconciliation boundary

`reconcile_control_plane_internal_awareness_v2()` automatically evaluates only structurally decidable internal connector-alert actions against their exact `apex_connector_incidents` row.

- open incident: the alert remains structurally valid;
- resolved incident: the alert is invalidated and cancelled with an awareness receipt and event.

The automatic path records `no_substantive_domain_judgment=true`.

It does **not** decide whether a legal referral, filing, escalation, investigative theory, evidence request, settlement posture, or other substantive domain action remains strategically valid. Those actions still require semantic evaluation from current evidence and Operator authority.

## Continuous execution

The `control-plane-awareness-reconcile-v2` pg_cron job runs once per minute. It clears structurally decidable internal stale state while leaving substantive actions untouched.

The dispatch path now consumes V2 directly:

- `claim_control_plane_actions_v1` uses `dispatch_reevaluation_required`;
- `control_plane_begin_authorized_attempt` uses the V2 awareness view;
- `execution-awareness-gate` consumes the V2 view; and
- `operator-impact-context` consumes `get_control_plane_action_awareness_v2`.

`READY` work may be claimed automatically only when it does not require Operator approval. Approval-required work still requires an authorization basis.

## Compatibility

`record_control_plane_action_awareness_v1` remains the publication interface so existing evaluator callers do not break, but its watermark is now computed from V2 HARD relevance.

`execution-awareness-gate` also retains the legacy `EVALUATE_CURRENT_REALITY` semantic token as an alias while exposing the more precise `EVALUATE_CURRENT_RELEVANT_REALITY` state.

## Operational effect

The control plane can now react continuously without either extreme:

- **too permissive:** executing stale work after a materially relevant source change; or
- **too conservative:** freezing independent work because something unrelated changed somewhere in the same case or global namespace.

The result is a continuous plane that preserves context breadth while making blocking semantics relationship-aware, source-bound, and auditable.
