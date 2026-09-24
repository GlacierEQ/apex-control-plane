# Operator Administration — Control-Plane Binding

Operator Administration is additive over the existing APEX continuity, capability-mesh, receipt, memory-federation, and execution-control surfaces. It does not replace them.

## Authority and ownership

- **Operator** — mission intent and ultimate authority.
- **GitHub** — declarative source, schemas, migrations, genomes, policies, tests.
- **Supabase backend ops** — materialized operational state.
- **Existing continuity/event/receipt surfaces** — execution and provider provenance.
- **Operator Administration genome layer** — persistent logical agent identity, lineage, versioned genetic contract, delegation, and resumable continuity heads.
- **Dashboards/UI** — projection only, never underlying truth.

## Position 1: Continuity

Every durable agent must remain reconstructable across executor, model, tool, provider, session, process, and machine changes. A logical agent is not its runtime process. The runtime-agent UUID is a replaceable binding.

## Added surfaces

- `oa_agent_genomes_v1`
- `oa_agent_genome_versions_v1`
- `oa_agent_delegations_v1`
- `oa_administration_events_v1`
- `oa_continuity_heads_v1`
- `oa_current_continuity_heads_v1`
- `oa_hatch_agent_v1(...)`

Existing rows in `public.agents` are imported as `OA.RUNTIME.*` logical agents without altering or deleting the original runtime registry.

## Genetic contract

Every genome contains all 12 chromosomes, in this architecture order:

1. continuity
2. authority
3. identity_lineage
4. mission
5. cognition
6. knowledge_memory
7. capability
8. execution
9. evidence_provenance
10. verification
11. integrity_security
12. administration_observability

Historical administrative events and continuity heads are append-only. Genome versions preserve old versions.

## Recovery law

A replacement executor loads logical identity, current genome, latest verified continuity head, APEX context/memory, authority/delegation, open commitments/dependencies, capability routing, provider receipts, and verification state, then continues without requiring the Operator to reconstruct prior work.
