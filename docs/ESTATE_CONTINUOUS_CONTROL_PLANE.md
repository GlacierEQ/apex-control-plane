# Estate Continuous Control Plane

## Mission

Maintain one continuous, source-bound operating state across the GlacierEQ estate so a new agent, CLI session, repository, or connector can recover the last verified frontier and continue without reconstructing everything from scratch.

This composes existing systems; it does not create a new sovereign layer.

## Functional constellation

- **Operator** — mission, priorities, firsthand knowledge, final project direction.
- **AKOS** — epistemology: how claims become known, disputed, corroborated, and verified.
- **apex-control-plane** — boot, continuity, evaluation, routing contract.
- **Monolith** — estate cartography and source orientation.
- **Aspen Grove** — memory, provenance, continuity, federation.
- **Tower of Babel** — technology placement, interoperability, proof.
- **Make-It-Heavy** — parallel perspectives and contradiction preservation.
- **Mega Skills** — Skill -> Combo -> Mega composition.
- **Genius-Mastery** — mastery, challenge, teaching, ascension.
- **Job App Helix** — evidence-bound application and exact-state proof.
- **Mastermind** — mission routing and receipt-backed coordination.
- **computer-user** — terminal execution and post-action readback.
- **Omni Engine** — ingestion, memory bridge, operator observability.
- **Supabase** — durable shared state and frontier.

## Durable spine

Project: `supabase-glaciereq` (`kjebemdgvjvuutzvhbtp`).

Existing state:
- `operator_runtime_context_current_v1`
- `operator_runtime_presence_v1`
- `operator_decision_runtime_v1`
- `control_plane_global_frontier_v1`
- `control_plane_events`
- `control_plane_receipts`
- `control_plane_action_outbox`
- `control_plane_obligations`

Epistemic / constellation bridge:
- `control_plane_constellation_v1`
- `control_plane_epistemic_state_v1`
- `control_plane_continuity_spine_v1`

The shared view is a boot/read surface. It combines Operator context, global frontier, constellation, and epistemic state without replacing the owning systems.

## Continuous loop

```text
BOOT
 -> READ OPERATOR CONTEXT
 -> READ LAST VERIFIED FRONTIER
 -> READ CONSTELLATION / RELEVANT OWNERS
 -> READ EPISTEMIC STATE / OPEN CONTRADICTIONS
 -> ACQUIRE LIVE SOURCE STATE
 -> EVALUATE IMPACT
 -> SELECT STRONGEST COHERENT FRONTIER
 -> ROUTE THROUGH OWNING SYSTEM
 -> EXECUTE
 -> READ BACK
 -> WRITE EVENT + RECEIPT
 -> UPDATE EPISTEMIC STATE
 -> UPDATE FRONTIER
 -> FAN OUT MEMORY / MAP PROJECTIONS
 -> RECOMPUTE
 -> CONTINUE
```

## AKOS shape

Every material claim flows through:

```text
L1 PERCEIVE
 -> L2 PROVENANCE
 -> L3 CLASSIFY
 -> L4 MODEL
 -> L5 FALSIFY
 -> L6 VERIFY
 -> LEARN / REENTER
```

Shared truth-state vocabulary:
`unknown`, `hypothesized`, `inferred`, `observed`, `corroborated`, `disputed`, `contradicted`, `verified`.

Verification authority is epistemic. It labels what reality supports; it does not redefine the Operator's mission.

## Write discipline

Every meaningful cycle should preserve enough state that the next worker can continue:
1. current objective and frontier;
2. source-bound propositions that changed;
3. contradictions that remain live;
4. execution event;
5. provider/readback receipt when execution occurred;
6. next probe or next executable action;
7. owning system and dependency references.

Store identities, claims, state, pointers, receipts, and frontier. Do not duplicate entire source systems into the control plane.

## Anti-entropy

- Memory is revalidated against live sources when factual freshness matters.
- Monolith points to owning repos instead of becoming them.
- Provider health is telemetry, not sovereignty.
- A search miss is not deletion proof.
- Duplicate names are not duplicate identity.
- Symlinks, mounts, registries, generators, and aliases are resolved before mutation.
- Conflicting receipts remain conflicts until source authority or readback resolves them.
- New evidence can reopen a claim at a new scope or time.

## Destructive boundary

```text
IDENTIFY -> TRACE -> RESOLVE INDIRECTION -> MAP DEPENDENTS
 -> CALCULATE BLAST RADIUS -> VERIFY RECOVERY
 -> EVALUATE NEAR/LONG-TERM IMPACT
 -> DISCUSS WITH OPERATOR WHEN MATERIAL
 -> EXECUTE ONLY WITH UNDERSTANDING
```

## Specialized lanes

Specialized continuous planes remain peers. `docs/CASE_EXECUTION_CONTINUOUS_CONTROL_PLANE.md` is the case-execution lane. It feeds the estate spine through events, receipts, obligations, actions, and frontier state; it is not replaced by this contract.

## Success condition

A compatible worker can recover who controls the mission, what the objective is, what is known/disputed/unknown, what was last executed and verified, which system owns the next action, and the strongest current frontier without relying on conversational memory alone.
