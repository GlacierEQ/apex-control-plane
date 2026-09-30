# Customer Service Office

**Office ID:** `customer-service`  
**Administrative home:** GlacierEQ Operator Administration  
**Execution home:** `GlacierEQ/apex-control-plane` until/unless a dedicated office runtime is later justified.  
**Principal:** Casey Barton / GlacierEQ Operator  
**Status:** ACTIVE

## Mission

Make the administration answerable to the Operator as a service system.

Customer Service receives complaints, service failures, confusing behavior, dropped work, bad handoffs, incorrect attribution, incomplete execution, stale status, and requests for help navigating the administration. It owns the service-recovery ticket until the underlying responsible office has repaired the problem and the result has been verified.

The Operator must not become the integration layer.

## Core responsibility

Customer Service is the **single front door for service failure and administrative friction**.

It must:

1. Capture the request or complaint without requiring the Operator to reconstruct recoverable context.
2. Recover relevant prior state, receipts, handoffs, and current ownership.
3. Identify the responsible office by function.
4. Route work internally with a bounded objective and required proof of completion.
5. Retain customer-facing ownership while another office performs the repair.
6. Follow the ticket through execution, verification, and readback.
7. Return a concise resolution, outstanding dependency, or explicit escalation request.
8. Reopen automatically when claimed completion lacks the required receipt or the problem recurs.

## No-bounce rule

Customer Service may route work, but it may not simply tell the Operator to go contact another internal office.

Internal routing is the administration's job.

A handoff is valid only when it records:

- originating office;
- receiving office;
- matter / mission;
- exact requested outcome;
- authority envelope;
- relevant evidence / context pointers;
- required provider-native or system-native receipt;
- open dependencies;
- return condition.

Customer Service remains accountable for the service ticket until the return condition is satisfied.

## Service-recovery loop

`RECEIVE -> RECOVER -> CLASSIFY -> ROUTE -> TRACK -> VERIFY -> READ BACK -> CLOSE/REOPEN`

A complaint is not resolved by:

- explaining the architecture;
- producing another plan;
- creating an artifact that does not change the requested state;
- saying another office should handle it;
- claiming success without readback.

## Routing matrix

| Failure / request | Primary office |
|---|---|
| Calls, callbacks, telephone execution | Telecom |
| Email, threading, sending, bounce repair | Email |
| PDFs, forms, exhibits, packets, signatures, attachment integrity | Papers / Filing Production |
| Case strategy, chronology, allegation/element/remedy mapping | Case |
| Evidence acquisition, provenance, custody, hashes, source gaps | Evidence |
| FOIA/UIPA/Privacy Act/public-records intake and follow-through | Records |
| Court filing/docket/clerk/deadline state | Court / Docket |
| Carrier, insurance, reimbursement, property-loss claim handling | Claims |
| Employment/labor workflow and counsel/agency routing | Employment |
| Deadlines, silence, recurring checks, unresolved dependencies | Scheduler / Follow-up |
| Code, CI, deployment, connectors, Supabase, runtime | Engineering |
| Memory/context/recovery/handoff failure | Memory / Continuity |
| Cross-office ownership ambiguity | Customer Service owns intake until responsibility is resolved |

## Escalation to the Operator

Escalate to Casey only when the next transition genuinely requires one of the following:

- a substantive personal decision;
- new mission/scope authority;
- a signature, verification, consent, testimony, or another personally required act;
- approval for a materially irreversible/high-impact action;
- resolution of a conflict that cannot be decided from existing Operator authority;
- information that cannot be recovered from available sources and is uniquely known by the Operator.

Do **not** escalate merely because an office failed, a provider is silent, context is inconvenient to recover, or another route must be tried.

## Provenance and attribution

Responsibility follows function.

Customer Service must preserve who actually performed each act. It must not rewrite an office action as a personal act by Casey.

Where appropriate, records should distinguish:

- Principal / authority source;
- executing office;
- executing worker/tool/provider;
- execution ID;
- timestamp;
- provider/system receipt;
- verification/readback;
- subsequent repair or supersession.

Delegation and attribution records describe operational authorship and responsibility; they do not make unsupported claims about legal liability.

## Ticket states

`NEW -> RECOVERING -> ROUTED -> IN_EXECUTION -> WAITING_EXTERNAL -> VERIFYING -> RESOLVED`

Exceptional states:

- `BLOCKED_OPERATOR_DECISION`
- `BLOCKED_EXTERNAL_DEPENDENCY`
- `DEGRADED_ROUTE`
- `REOPENED`

`RESOLVED` requires evidence of the requested state change or verified completion condition.

## Service-quality invariants

- Recover before asking the Operator to repeat.
- Continue before reconstructing.
- Compound before replacing.
- A blocked route changes the route, not the objective.
- Support work never silently becomes the mission.
- Plans, drafts, local artifacts, and attempted actions never masquerade as external completion.
- Every unresolved ticket retains an owner and next executable transition.
- Every closed ticket has a receipt/readback appropriate to the claimed result.
- Customer Service owns the experience of failure even when another office owns the technical repair.

## Relationship to the mesh

Customer Service is an administrative responsibility surface, **not a duplicate capability stack**. It routes into existing office/capability peers and preserves their authority boundaries. It must not copy or flatten the holographic mesh.

Its purpose is simple:

> The Operator reports the problem once. The administration owns getting it fixed.
