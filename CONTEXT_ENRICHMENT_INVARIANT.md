# Context Enrichment Invariant

## Controlling law

Context-first is an execution invariant and an enrichment transition. It is **not** a permission gate, promotion ladder, or sovereign authority.

For every substantial Operator-directed turn, action, run, bundle, or agent transition:

1. Attempt to recover materially relevant source-bearing context before discretionary action selection when retrieval is available.
2. Apply recovered context when material; retrieval that does not causally affect cognition is incomplete enrichment.
3. Bind the recovery attempt, packet, source references, and recovery debt to the work lineage.
4. Continue coherent execution even when retrieval is partial or unavailable.
5. Record missing or degraded context as durable recovery debt with `mission_stop=false`.
6. Retry or route to alternate context sources without converting the context subsystem into authority over the mission.
7. Preserve exact Operator source, provider-native receipts, contradictions, supersession, and provenance.
8. Treat semantic-memory providers as retrieval/index projections. They do not confer truth authority.
9. Allow context to be recovered in flight and applied to the next discretionary transition without rewinding already verified gain.
10. Only actual route-local constraints—provider rejection, missing credentials, destructive-operation authority requirements, or comparable concrete boundaries—may stop the affected route.

## State model

```text
hydrated
degraded
recovery_pending
not_applicable
```

These are enrichment states, not authorization states.

Forbidden reinterpretations include:

```text
context missing -> mission blocked
context packet -> permission granted
memory provider -> truth authority
context compiler -> Operator authority
recovery debt -> erase prior verified gain
```

## Estate propagation

The invariant must be inherited by:

- APEX runtime and boot
- Operator Administration and Agent Genomes
- continuity and cognition runtimes
- connector orchestration and Everything MCP runs
- action outboxes and execution-awareness surfaces
- memory and retrieval providers
- case, email, telecom, drafting, engineering, research, and other domain agents
- projections into Notion, Google Drive, OneDrive/SharePoint, and other Operator-facing knowledge surfaces

Projection copies are navigation and continuity aids. GitHub/Supabase provider-native contracts and source-bearing records remain authoritative according to their existing stewardship boundaries.

## Runtime receipt semantics

A successful context recovery emits `context_recovery`.

If work must continue before recovery completes, emit `context_recovery_debt` with at minimum:

```json
{
  "state": "recovery_pending",
  "mission_stop": false,
  "route_effect": "enrich_and_continue"
}
```

Either receipt satisfies the lifecycle requirement that context enrichment was accounted for. Only `context_recovery` claims actual recovery.

## Execution formula

```text
OPERATOR MISSION
    ↓
CONTEXT ATTEMPT
    ├─ hydrated ─────→ apply → continue
    └─ partial/fail ─→ record debt → alternate retrieval → continue
                                      ↓
                                  VERIFY / READBACK
```

Context increases coherence. It does not own the mission.
