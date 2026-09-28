# Founding Specialist Cohort

This cohort turns Operator Administration from a role catalog into named, continuity-bearing specialists.

## Identity rule

A specialist is a **logical agent**. Its executor/model/process may change without changing the specialist identity.

Every specialist receives:

1. a 12-chromosome genome;
2. Continuity as position 1;
3. one primary role plus composed secondary/specialist roles;
4. explicit capability intent, but no capability merely because a role exists;
5. explicit memory scope;
6. explicit verification intent;
7. an initial verified continuity head;
8. append-only role-assignment receipts.

## Founding identities

- **`OA.CONTINUITY.01` — Continuity 01:** Own continuity recovery, verified state heads, succession, and rehydration across executor changes.
  - roles: `OA.ROLE.CONTINUITY_CUSTODIAN` (PRIMARY), `OA.ROLE.RECOVERY_ENGINEER` (SECONDARY), `OA.ROLE.VERIFIER` (SPECIALIST)
- **`OA.AUTHORITY.01` — Authority 01:** Own delegation integrity, jurisdiction boundaries, authority-inversion detection, revocation, and restoration.
  - roles: `OA.ROLE.AUTHORITY_STEWARD` (PRIMARY), `OA.ROLE.SECURITY_GUARDIAN` (SECONDARY), `OA.ROLE.VERIFIER` (SPECIALIST)
- **`OA.ADMIN.01` — Administration 01:** Own agent census, lifecycle, genome administration, role assignment integrity, succession, quarantine, and retirement.
  - roles: `OA.ROLE.AGENT_ADMINISTRATOR` (PRIMARY), `OA.ROLE.ROLE_ARCHITECT` (SECONDARY), `OA.ROLE.CONTINUITY_CUSTODIAN` (SPECIALIST)
- **`OA.MEMORY.12` — Memory 12:** Own provenance-aware durable memory promotion, retrieval, contradiction handling, and scoped recall.
  - roles: `OA.ROLE.MEMORY_CURATOR` (PRIMARY), `OA.ROLE.PROVENANCE_RECORDER` (SECONDARY), `OA.ROLE.CONTEXT_COMPILER` (SPECIALIST)
- **`OA.CONTEXT.12` — Context 12:** Compile authority-aware, provenance-aware, minimum-sufficient context before reasoning and execution.
  - roles: `OA.ROLE.CONTEXT_COMPILER` (PRIMARY), `OA.ROLE.MEMORY_CURATOR` (SECONDARY), `OA.ROLE.PROVENANCE_RECORDER` (SPECIALIST)
- **`OA.ORCHESTRATION.12` — Orchestration 12:** Own mission decomposition, route generation, dependency ownership, work assignment, continuation, and next-best-action selection.
  - roles: `OA.ROLE.MISSION_ORCHESTRATOR` (PRIMARY), `OA.ROLE.CAPABILITY_ROUTER` (SECONDARY), `OA.ROLE.OPERATIONS_COORDINATOR` (SPECIALIST)
- **`OA.CAPABILITY.12` — Capability 12:** Own live capability discovery, health, eligibility, provider routing, fallbacks, and least-privilege execution selection.
  - roles: `OA.ROLE.CAPABILITY_ROUTER` (PRIMARY), `OA.ROLE.SECURITY_GUARDIAN` (SECONDARY), `OA.ROLE.OBSERVABILITY_SENTINEL` (SPECIALIST)
- **`OA.SECURITY.12` — Security 12:** Own least privilege, secret handling, integrity controls, blast-radius limits, and compromise detection.
  - roles: `OA.ROLE.SECURITY_GUARDIAN` (PRIMARY), `OA.ROLE.AUTHORITY_STEWARD` (SECONDARY), `OA.ROLE.VERIFIER` (SPECIALIST)
- **`OA.RECOVERY.12` — Recovery 12:** Own recovery from partial failure, corruption, provider loss, executor loss, and degraded continuity.
  - roles: `OA.ROLE.RECOVERY_ENGINEER` (PRIMARY), `OA.ROLE.INCIDENT_COMMANDER` (SECONDARY), `OA.ROLE.CONTINUITY_CUSTODIAN` (SPECIALIST)
- **`OA.EMAIL.12` — Email 12:** Own high-context email triage, drafting, routing, sending, provider receipts, follow-up, and thread continuity.
  - roles: `OA.ROLE.EMAIL_OPERATOR` (PRIMARY), `OA.ROLE.COMMUNICATIONS_COORDINATOR` (SECONDARY), `OA.ROLE.DRAFTING_ENGINE` (SPECIALIST), `OA.ROLE.RECEIPT_AUDITOR` (SPECIALIST)
- **`OA.TELECOM.12` — Telecom 12:** Own calls, SMS, telecom-provider execution, scripts, transcripts, receipts, routing, and follow-up continuity.
  - roles: `OA.ROLE.TELECOM_OPERATOR` (PRIMARY), `OA.ROLE.COMMUNICATIONS_COORDINATOR` (SECONDARY), `OA.ROLE.RECEIPT_AUDITOR` (SPECIALIST)
- **`OA.DRAFTING.12` — Drafting 12:** Own evidence-grounded production drafting across correspondence, reports, complaints, proposals, scripts, and formal documents.
  - roles: `OA.ROLE.DRAFTING_ENGINE` (PRIMARY), `OA.ROLE.DOCUMENT_ENGINEER` (SECONDARY), `OA.ROLE.CONTEXT_COMPILER` (SPECIALIST)
- **`OA.DRAFTING.12.12` — Drafting 12.12 Finalization:** Own finalization: reconcile source truth, resolve omissions, validate formatting, and produce handoff-ready final artifacts.
  - roles: `OA.ROLE.DRAFTING_ENGINE` (PRIMARY), `OA.ROLE.DOCUMENT_ENGINEER` (SECONDARY), `OA.ROLE.VERIFIER` (SPECIALIST), `OA.ROLE.RECEIPT_AUDITOR` (SPECIALIST)
- **`OA.CASEBUILDING.12` — Casebuilding 12:** Own cumulative case construction across facts, actors, chronology, claims, defenses, evidence, contradictions, remedies, discovery, and executable next actions.
  - roles: `OA.ROLE.CASEBUILDER` (PRIMARY), `OA.ROLE.INVESTIGATOR` (SECONDARY), `OA.ROLE.EVIDENCE_ANALYST` (SPECIALIST), `OA.ROLE.LEGAL_RESEARCHER` (SPECIALIST), `OA.ROLE.RESEARCHER` (SPECIALIST), `OA.ROLE.DRAFTING_ENGINE` (SPECIALIST)
- **`OA.RESEARCH.12` — Research 12:** Own source acquisition, ranking, synthesis, uncertainty tracking, and durable research state for mission-defined questions.
  - roles: `OA.ROLE.RESEARCHER` (PRIMARY), `OA.ROLE.INVESTIGATOR` (SECONDARY), `OA.ROLE.DATA_ANALYST` (SPECIALIST), `OA.ROLE.PROVENANCE_RECORDER` (SPECIALIST)
- **`OA.EVIDENCE.12` — Evidence 12:** Own evidence custody, integrity, source identity, transformation lineage, contradiction analysis, and evidentiary relationships.
  - roles: `OA.ROLE.EVIDENCE_CUSTODIAN` (PRIMARY), `OA.ROLE.EVIDENCE_ANALYST` (SECONDARY), `OA.ROLE.PROVENANCE_RECORDER` (SPECIALIST), `OA.ROLE.RECEIPT_AUDITOR` (SPECIALIST)
- **`OA.ENGINEERING.12` — Engineering 12:** Own architecture-preserving implementation, integration, testing, CI, deployment evidence, and repair across the engineering estate.
  - roles: `OA.ROLE.ENGINEER` (PRIMARY), `OA.ROLE.GITHUB_STEWARD` (SECONDARY), `OA.ROLE.SUPABASE_STEWARD` (SPECIALIST), `OA.ROLE.VERIFIER` (SPECIALIST)
- **`OA.VERIFICATION.12` — Verification 12:** Own independent falsification, readback, receipt reconciliation, regression detection, and completion certification.
  - roles: `OA.ROLE.VERIFIER` (PRIMARY), `OA.ROLE.RECEIPT_AUDITOR` (SECONDARY), `OA.ROLE.OBSERVABILITY_SENTINEL` (SPECIALIST), `OA.ROLE.SECURITY_GUARDIAN` (SPECIALIST)

## Hatching semantics

`oa_hatch_specialist_v1` is idempotent for already-created logical identities. It composes roles through `oa_assign_role_v1`, which resolves the current active role version and records a `ROLE_ASSIGNED` administration event.

The founding cohort deliberately has **no runtime executor UUIDs**. Runtime binding is a later, replaceable assignment. This prevents a model, machine, session, or provider from becoming the identity.

## Next transition

After source validation and migration deployment, capability grants can be bound to these identities from the existing capability mesh. The strongest next reference agents are:

- `OA.EMAIL.12`
- `OA.CASEBUILDING.12`
- `OA.ENGINEERING.12`
- `OA.VERIFICATION.12`

They jointly exercise external communication, cumulative case reasoning, estate mutation, and independent verification—the main execution loop needed to prove the architecture end-to-end.
