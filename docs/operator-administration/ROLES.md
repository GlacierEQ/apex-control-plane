# Operator Administration — Role System

A **role** is a persistent responsibility contract. It is not an agent, runtime process, model, prompt, or authority grant.

An **agent** can be reassigned while the role remains stable. A role can move to a successor without losing its open loops, evidence, commitments, or verified state.

## Role equation

```text
ROLE =
  CONTINUITY
+ PURPOSE
+ WIN CONDITION
+ AUTHORITY BOUNDARY
+ JURISDICTION
+ REASONING CONTRACT
+ EXECUTION CONTRACT
+ CAPABILITY REQUIREMENTS
+ MEMORY / CONTEXT CONTRACT
+ EVIDENCE / PROVENANCE
+ VERIFICATION
+ COMMUNICATION
+ ESCALATION
+ HANDOFF
+ OBSERVABILITY
+ SECURITY / RISK
+ LIFECYCLE
```

Continuity remains locus #1.

## Separation of concerns

- **Role:** what responsibility exists and what correct performance means.
- **Agent:** durable logical worker identity that may hold one or more roles.
- **Executor:** replaceable runtime/model/process currently instantiating an agent.
- **Delegation:** authority actually granted by the Operator.
- **Mission:** current desired outcome.
- **Capability grant:** concrete permission to invoke a tool/provider/resource.

No role automatically grants authority or capabilities.

## Assignment modes

- `PRIMARY` — default enduring responsibility of an agent.
- `SECONDARY` — additional durable responsibility.
- `SPECIALIST` — specialized competence composed into another mission.
- `MISSION_SCOPED` — assignment exists only for a mission.
- `TEMPORARY` — time-bounded assignment.

Every reassignment must preserve the role handoff packet: scope, mission state, open loops, evidence refs, provider-state refs, last verified event, and exact next action.

## Initial families

The registry seeds both:

1. **administrative/cognitive roles** such as Continuity Custodian, Authority Steward, Agent Administrator, Role Architect, Memory Curator, Context Compiler, Mission Orchestrator, Capability Router, Receipt Auditor, Verifier, Security Guardian, and Recovery Engineer;
2. **purpose/domain roles** such as Email Operator, Telecom Operator, Drafting Engine, Casebuilder, Researcher, Legal Researcher, Evidence Analyst, Document Engineer, Data Analyst, Engineer, GitHub Steward, Supabase Steward, File Custodian, Communications Coordinator, Investigator, Calendar Scheduler, and Operations Coordinator;
3. **existing infrastructure roles** mapped one-to-one from the current 19 runtime agents so the existing system gains explicit responsibility contracts without destructive replacement.

The next hatching layer can now instantiate identities such as `OA.EMAIL.12`, `OA.TELECOM.12`, or `OA.DRAFTING.12.12` and bind them to these versioned roles instead of encoding their responsibility only in prompt prose.
