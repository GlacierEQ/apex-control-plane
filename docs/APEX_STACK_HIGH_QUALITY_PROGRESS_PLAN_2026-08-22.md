# APEX Stack High-Quality Progress Plan

**Source-state date:** 2026-08-22 HST  
**Planning base:** current `GlacierEQ/apex-control-plane` `main` after the strongest-boot and verified-runtime work  
**Purpose:** select the highest-leverage next work across AKOS, APEX, Aspen, ECHO, Monolith, Alpha, Omega, workers, integrations, Tower of Babel, Pro_Code, and pro-code without collapsing distinct capabilities or inventing repository hierarchy.

## 1. Architectural thesis

The stack should organize around one simple semantic boundary:

```text
REALITY / SOURCES / OBSERVATION
             ↓
            AKOS
   HOW KNOWLEDGE IS KNOWN
             ↓
       KNOWLEDGE STATE
             ↓
          OPERATOR
   HOW KNOWLEDGE IS USED
             ↓
     APEX EXECUTION INTENT
             ↓
CONTROL PLANE → OMEGA / WORKERS / TOOLS
             ↓
 EXECUTION / READBACK / RECEIPTS
             ↓
       NEW OBSERVATIONS
             ↓
            AKOS
```

`OPERATOR` is a singular proper-name designation, not a reusable job title.

The two non-collapse invariants are:

```text
AKOS KNOWLEDGE STATE != OPERATOR USE DIRECTION
OPERATOR USE DIRECTION != AKOS KNOWLEDGE STATE
```

AKOS may establish that a proposition is observed, inferred, hypothesized, contradicted, stale, unsupported, verified, or unknown. OPERATOR determines how that knowledge is used, prioritized, targeted, and applied. OPERATOR direction does not manufacture epistemic truth. AKOS knowledge does not choose the project objective or action by itself.

APEX is the composition and execution system that turns those two inputs into the smartest verified action.

## 2. Current stack finding

The estate already has substantial capability. The dominant weakness is not missing components. It is **semantic and interface fragmentation between strong components**.

### Current strong capabilities

| System | Strong current contribution | Main integration need |
|---|---|---|
| `apex-control-plane` | strongest boot, sealed process session, verified runtime kernel, observation/mutation lifecycles, provider bridges, receipts, readback | bind explicit knowledge/use objects into the current runtime |
| `AKOS` | evidence/state concepts, provenance, operational cognition, contradiction and verification mechanisms | make epistemic responsibility explicit and remove use-direction impersonation |
| `apex-alpha` | models, intelligence, memory, experimentation, invention | feed candidate knowledge/inference through AKOS epistemic contracts |
| `apex-omega` | gateways, workers, APIs, interfaces, execution | consume execution intent without becoming project-direction authority |
| `apex-boot-core` | capability discovery, resumability, circuit state, runtime receipts, fallback and replay concepts | compose its useful mechanisms behind the current strongest-boot interface rather than competing boot meanings |
| `aspen-grove-core` | continuity, memory, lineage, routing | become a provenance/context supply path into AKOS knowledge formation |
| `ECHO` | continuity, history, orchestration, deterministic identity, jobs, receipts | carry observations and execution continuity without becoming knowledge or use authority |
| `monolith` | estate map, structural classification, new epistemic methodology and distillation work | map and distill the estate without becoming the epistemic source or project-direction source |
| `the-tower-of-babel` | technology placement, interoperability, build/benchmark/proof contracts | return technology knowledge and proof into AKOS, execute placement under OPERATOR-directed objectives |
| `Pro_Code` | private engineering doctrine and human context | remain methodological input, explicitly adopted where useful |
| `pro-code` | executable local engineering workbench and proof surfaces | execute bounded engineering work through the shared envelopes |
| workers/integrations | provider reach, specialist execution, connector paths | preserve provenance and use-direction across every dispatch boundary |

### Current semantic split-brain

High-fanout surfaces still teach incompatible architectures. Examples include AKOS, Aspen Grove Core, ECHO, Pro_Code/pro-code references, Monolith foundation maps, and older AKOS/ECHO contracts that describe AKOS as governance or authority rather than the system for how knowledge is known.

That is dangerous because agents commonly ingest README, AGENTS, boot, memory, and routing surfaces before reaching the newer runtime semantics.

### Two executable defects that make the first priority concrete

1. Current `config/operator_fidelity_runtime_policy.json` still contains a hard-coded global `direction: "look_up"`. A durable policy must not impersonate the current OPERATOR use-direction.
2. Current `verified_runtime_entrypoint.py` creates a machine-authored `SMOKE_INSTRUCTION` and binds it to a runtime field whose contract describes it as the literal Operator instruction. A machine-generated diagnostic task is not OPERATOR speech.

The runtime kernel itself is strong. These are integration-boundary defects, not a reason to replace the kernel.

## 3. Selected priority

### P0: Bind AKOS knowledge and OPERATOR use into the current strongest runtime

This is the highest-leverage move because every downstream agent, worker, connector, legal system, engineering tool, and provider action eventually needs to know three different things:

1. **What is known?**
2. **What does OPERATOR want done with it?**
3. **What did execution actually do?**

Today those concepts exist across the estate, but they are not represented by one typed runtime boundary.

Do not begin with estate-wide README rewriting. Do not merge the old PR #59 into a much newer mainline. Extract its useful source-identity idea and implement the stronger epistemic/use model directly against current strongest-boot `main`.

## 4. P0 implementation: typed semantic spine

### 4.1 Add `KnowledgeEnvelope`

Create a small typed runtime object and JSON schema representing what AKOS knows about a proposition or state.

Minimum fields:

```text
knowledge_id
proposition
subject_refs[]
epistemic_state
source_refs[]
evidence_refs[]
contrary_evidence_refs[]
provenance_refs[]
inference_refs[]
contradiction_refs[]
confidence_or_support
observed_at
valid_from / valid_to when temporal
staleness_state
verification_state
revision
supersedes[]
```

Recommended epistemic states must distinguish at least:

```text
OBSERVED
SOURCE_STATEMENT
INFERRED
HYPOTHESIZED
UNKNOWN
CONTRADICTED
```

Domain systems may add richer states, but all state promotion must remain evidence-bound.

A `KnowledgeEnvelope` is **not an action request**.

### 4.2 Add `OperatorUseDirective`

Represent how the singular OPERATOR wants knowledge used.

Minimum fields:

```text
operator_designation = OPERATOR
use_directive_id
literal_direction_ref or literal text held privately
literal_direction_sha256
objective
application
priority
scope
constraints[]
knowledge_refs[]
consequence_scope
external_action_scope if applicable
authorization_ref if applicable
issued_at
supersedes[]
```

A use directive may select, prioritize, combine, or decline to use knowledge. It may not rewrite the referenced knowledge envelopes.

### 4.3 Add `ExecutionIntent`

Bind knowledge and use without collapsing them:

```text
execution_intent_id
knowledge_refs[]
operator_use_directive_ref
operation_class
mode = observation | mutation
action_scope = none | internal | external
target_state
verification_plan[]
recovery_refs[]
idempotency_ref when applicable
```

The execution intent is consumed by the verified runtime kernel and downstream execution surfaces.

### 4.4 Repair current source contamination

On current `main`:

- remove hard-coded global use-direction such as `direction: look_up` from policy as a substitute for current OPERATOR direction;
- keep reusable quality/verification constraints as framework mechanics, not OPERATOR words;
- stop representing machine-authored smoke/test instructions as literal OPERATOR speech;
- give diagnostic/system tasks an explicit `SYSTEM_DIAGNOSTIC` or equivalent source class;
- preserve SHA-256 fidelity for words actually attributed to OPERATOR;
- preserve runtime privacy so literal private instruction text is not leaked to audit surfaces.

### 4.5 Extend the runtime kernel without weakening it

Preserve the verified lifecycle already implemented:

```text
OBSERVATION:
BIND → OBSERVE → VERIFY → READBACK → COMPLETE

MUTATION:
BIND → EXECUTE → TEST → ADVERSARIAL TEST
→ VERIFY → PERSIST → READBACK → COMPLETE
```

Add these requirements:

- observation tasks may create new evidence/knowledge candidates without an action authorization;
- mutation tasks must bind an OPERATOR use directive appropriate to the mutation scope;
- verified execution results become new observations, not automatically new facts;
- any knowledge-state update from an execution result must pass through AKOS epistemic processing;
- OPERATOR direction cannot cause a failed verification to become verified;
- AKOS classification cannot silently choose a mutation or project objective.

### 4.6 P0 adversarial tests

Required tests before promotion:

1. machine diagnostic text cannot be attributed to OPERATOR;
2. retrieved AKOS/README/memory text cannot become OPERATOR words merely by retrieval;
3. OPERATOR use directive cannot change `HYPOTHESIZED` to `OBSERVED` or `VERIFIED`;
4. AKOS knowledge envelope cannot select an action without a use directive;
5. agent inference cannot impersonate AKOS observation or OPERATOR direction;
6. stale knowledge reference is surfaced before consequential use;
7. contradictory knowledge remains visible to execution planning;
8. mutation without a valid use directive fails before side effects;
9. observation without mutation authority remains executable;
10. literal OPERATOR wording digest detects mutation;
11. execution receipt cannot claim knowledge verification beyond the evidence in readback;
12. strong boot remains one process-owned session under concurrency;
13. existing runtime lifecycle and provider bridge tests remain green.

### P0 acceptance condition

One end-to-end test must prove:

```text
source observation
→ KnowledgeEnvelope
→ OPERATOR UseDirective references knowledge
→ ExecutionIntent
→ strongest boot
→ verified runtime
→ execution/observation
→ verification + readback
→ receipt
→ new observation returned for AKOS epistemic update
```

No component may collapse the two identities during the round trip.

## 5. P0B: land exact-run audit integrity in parallel

PR #70 is currently based on the newest strongest-boot mainline and addresses a separate high-value reliability defect. It should be reviewed as a parallel P0B track rather than mixed into the epistemic/use implementation.

Desired properties:

- one audit engine;
- one scheduler;
- exact `github.run_id` bindings;
- run log + queue + digest-bound proof;
- immediate readback;
- no newest/today fallback;
- connector reachability never becomes action authority;
- audit evidence remains evidence, not project direction;
- scheduled production observation required before claiming operational proof.

If PR #70 passes full repository checks and review, promote it before building new audit features. Preserve its exact-run proof semantics when later adding epistemic-drift detection.

## 6. P1: propagate one shared semantic boundary through high-fanout entrypoints

After P0 is executable, update the entrypoints agents actually read.

Order:

1. `AKOS/README.md`, `AKOS/AGENTS.md`, active AKOS manifest and active agent/runtime contracts;
2. `apex-control-plane/AGENTS.md`, startup docs, runtime docs;
3. `aspen-grove-core` README, machine node contracts, routing docs;
4. `ECHO` README, manifest, AKOS contract, operator/proof protocol;
5. `monolith` AGENTS, APEX foundation, AKOS foundation, machine initialization instructions;
6. `apex-alpha` and `apex-omega` agent/README surfaces;
7. `apex-boot-core` runtime relationship model;
8. `Pro_Code` and `pro-code` nervous-system references;
9. Tower of Babel integration/agent contracts;
10. workers and connector dispatch envelopes.

Use a concise shared boundary, not a new constitution:

```text
AKOS = how knowledge is known.
OPERATOR = how knowledge is used.
APEX = how the smartest verified action is composed and executed.
Execution results return as observations for AKOS to evaluate.
```

### P1 acceptance condition

An estate search over active high-fanout surfaces should find no unqualified claim that:

- AKOS owns project direction;
- AKOS is the OPERATOR;
- an agent/runtime/repository is another OPERATOR;
- OPERATOR use-direction itself changes factual or epistemic state;
- a receipt, audit, registry, memory, README, or policy is project-direction authority.

Historical evidence may retain old wording when clearly marked historical/non-current.

## 7. P2: build the AKOS knowledge plane

P0 creates the contract. P2 makes it powerful.

### Inputs

- source files and records;
- GitHub/repository observations;
- Aspen memory/context;
- connector read receipts;
- ECHO continuity events;
- Alpha model outputs;
- legal evidence packets;
- Tower build/benchmark/proof outputs;
- runtime readback receipts;
- user/OPERATOR firsthand assertions, distinctly typed as source statements unless independently verified.

### Processing

Build or compose:

- entity resolution;
- source identity/provenance;
- temporal validity and staleness;
- duplicate-source detection;
- contradiction graph;
- support/contrary-evidence relationships;
- inference lineage;
- confidence/support calibration;
- claim class and proof state;
- supersession/revision tracking;
- active knowledge queries;
- uncertainty and proof-gap queues.

### Output

AKOS should expose queryable `KnowledgeEnvelope` objects and graph relationships. It should be possible to ask:

```text
What do we know?
Why do we believe it?
What contradicts it?
How fresh is it?
What is inference rather than observation?
What would change the answer?
What is still unknown?
```

AKOS should not answer the separate question “What should OPERATOR do with this?” unless it is explicitly producing an advisory candidate labeled as agent inference/recommendation for OPERATOR consideration.

## 8. P3: compose Aspen, Monolith, and ECHO into the knowledge path

### Aspen Grove

Target role:

```text
cross-session context + memory + lineage + source continuity
→ provenance-bound input to AKOS
```

Repair stale “AKOS governance authority” and “canonical operational root” language where it creates actual semantic confusion. Preserve Aspen's routing/memory capability.

### Monolith

Target role:

```text
estate observation + structural fingerprinting + lineage map + distillation
→ structured observations and navigation for AKOS and agents
```

The new epistemic methodology and distillation protocol are useful donors, but require calibration before estate-wide adoption:

- verification depth should be claim-sensitive, not an absolute rule that every useful item requires runtime L2 behavior;
- file existence can be directly observed knowledge about existence, while behavioral claims require behavioral evidence;
- replace lineage language that machine-selects a single permanent “canonical” asset with revisable lineage/active-route descriptions unless the domain genuinely requires that technical term;
- Monolith remains a map/distillation system, not the owner of factual truth or project direction.

### ECHO

Target role:

```text
continuity + history + job orchestration + receipts
```

ECHO should preserve:

- deterministic identity;
- idempotent jobs;
- continuity;
- unresolved gaps;
- receipt generation;
- replay and recovery.

Repair “AKOS pillar/governs” semantics. ECHO carries movement and history. It does not decide what is known or how knowledge is used.

## 9. P4: wire the execution plane end to end

### Omega

Clarify Omega as the **executor/action strand**, not a competing project controller.

Preserve:

- gateways;
- workers;
- APIs;
- UI;
- provider/tool dispatch;
- operational orchestration.

Every Omega mutation should consume an `ExecutionIntent` that preserves both:

- AKOS knowledge references;
- OPERATOR use directive.

### Worker runtime

Every dispatch envelope should carry:

```text
execution_intent_id
operator_use_directive_ref
knowledge_refs[]
source/provenance refs where needed
operation class
allowed capability/tool boundary
idempotency identity
verification/readback contract
```

Worker output should be typed as execution result/observation, not automatic knowledge.

### Connector/provider path

Build on the already merged authenticated-session and exact-approved provider bridges:

```text
provider observation
→ digest/provenance receipt
→ AKOS ingestion

OPERATOR use directive
+ AKOS knowledge refs
→ exact execution intent
→ provider operation
→ terminal readback
→ receipt
→ AKOS observation
```

Expand provider mutations only after each provider mapping has executable tests, idempotency, exact target/consequence binding, and terminal readback.

## 10. P5: converge the boot/runtime mesh by interface, not destruction

There are multiple useful boot/runtime implementations:

- current `apex-control-plane` strongest boot;
- `apex-boot-core` capability discovery/resume/replay mechanisms;
- `APEX_BOOTUP` scripts/profiles;
- `apex-bootup-core` and related runtime surfaces.

Do not decide repository survival by name or age.

First build a capability matrix:

```text
capability
implementation
current entrypoint
current proof
callers
unique mechanism
interface compatibility
runtime duplication
failure/recovery behavior
```

Then define a common `BootCapability`/adapter boundary so the current strongest boot can compose proven donor mechanisms without creating multiple meanings of “boot complete.”

Priority donor candidates from `apex-boot-core` include:

- live capability states;
- TTL invalidation;
- circuit breakers;
- resumable run state;
- deterministic operation IDs;
- compensation pointers;
- resource admission;
- fallback contracts;
- replay attestation;
- drift refusal;
- health/SLO evaluation.

Acceptance: one externally visible boot meaning, multiple composable implementation capabilities.

## 11. P6: sharpen Alpha and Omega without flattening the double helix

### Alpha

Alpha should maximize:

- models;
- intelligence;
- memory mechanisms;
- experiments;
- invention;
- candidate inference;
- challenger generation.

Alpha outputs become candidate knowledge/inference that AKOS evaluates. Alpha is not demoted. Its intelligence becomes more usable because epistemic lineage is explicit.

### Omega

Omega should maximize:

- execution;
- gateways;
- interfaces;
- workers;
- APIs;
- operational feedback.

Omega receives use-directed execution intent. It does not infer project direction merely because it owns the action machinery.

### Helix composition

```text
ALPHA generates/learns
→ AKOS knows/qualifies
→ OPERATOR uses/directs
→ APEX composes
→ OMEGA executes
→ receipts/observations
→ AKOS updates
→ ALPHA learns
```

## 12. P7: make Monolith a live capability graph rather than a status oracle

Extend the estate map with current, evidence-backed dimensions:

```text
repo/component
function
interfaces
runtime vs projection vs reference
knowledge/use/execution/proof role
current source head
last verified head
verification depth by claim type
incoming dependencies
outgoing dependencies
live integration evidence
doc-only relationship
health receipt
known blocker
```

Important: capability mapping is observation. It does not imply ranking, merge, retirement, subordination, or disposition.

Generated maps should link to owning repositories and current receipts. Owning repos retain their implementation state.

## 13. P8: evidence-led audit and semantic drift detection

After PR #70 exact-run audit behavior is proven, extend the audit engine with checks that answer:

- Is a repository claiming live integration from a link only?
- Is connector reachability promoted into action capability?
- Is machine-generated text attributed to OPERATOR?
- Is OPERATOR use-direction being treated as factual verification?
- Is an AKOS knowledge object choosing project use without a directive?
- Are source/provenance refs stale or missing?
- Does a README claim behavior above current tested evidence?
- Do generated maps disagree with owning repository state?
- Did a test/receipt bind to the exact current source head?

Audit findings are observations/evidence. They do not become authority or automatic asset disposition.

## 14. P9: verification quality uplift

Apply quality work by failure surface, not aesthetics.

### Runtime

- concurrency/property tests for strongest boot;
- state-machine property tests for runtime lifecycle;
- replay/idempotency tests;
- stale directive/knowledge reference tests;
- blocker resume tests;
- failure injection between persistence and readback;
- audit privacy tests.

### Knowledge

- provenance mutation tests;
- contradiction tests;
- temporal staleness tests;
- entity-resolution hard negatives;
- duplicated-source non-corroboration tests;
- inference lineage tests;
- source withdrawal/supersession tests.

### Execution

- worker timeout/retry tests;
- provider partial-success tests;
- duplicate mutation suppression;
- terminal-readback mismatch tests;
- connector circuit-breaker/fallback tests;
- exact target/consequence verification.

### Polyglot/Tower

Use Tower proof classes to select languages only where evidence shows a boundary benefit. Polyglot count is never a quality target.

## 15. P10: domain proof missions

Do not declare the architecture successful because schemas compile. Prove it on real work classes.

Run at least these mission classes:

1. **Repository engineering mission**
   - observe current source;
   - AKOS knowledge envelope;
   - OPERATOR use directive;
   - patch;
   - tests/adversarial tests;
   - readback;
   - updated knowledge.

2. **Legal evidence mission**
   - ingest source;
   - distinguish source statement/fact/inference/allegation/theory;
   - preserve contradiction/proof gaps;
   - OPERATOR selects strategic use;
   - generate work product without changing evidence state.

3. **Connector read mission**
   - provider observation;
   - provenance receipt;
   - knowledge update;
   - no action authority inferred.

4. **Exact-approved external mutation mission**
   - knowledge references;
   - OPERATOR use directive;
   - exact target/consequence;
   - idempotent provider action;
   - terminal readback;
   - receipt;
   - AKOS update.

5. **Failure/recovery mission**
   - induced failure;
   - no false completion;
   - preserved recoverable state;
   - repair;
   - re-test;
   - verified readback.

## 16. Stale/open PR strategy

Open PRs are evidence-bearing work, not instructions to merge everything.

### PR #70

Current-base audit reengineering. Review and promote if checks and exact-run proof pass. High-value parallel track.

### PR #66

Secret-bound promotion-authority removal. Compare against current main and retain unique anti-lockout value. Promote only if still additive after newest runtime changes.

### PR #63

Older audit repair likely superseded by #70. Preserve unique findings/history, then close if #70 subsumes the implementation.

### PR #62

Old-base proof-aware operational mode conflicts with the newer strongest-boot architecture. Harvest any useful test or concept; do not merge the stale branch mechanically.

### PR #60

Contains valuable Jack/case-hardening work but old base. Extract unique case-preservation/runtime semantics into a current-main continuation rather than forcing the stale branch through.

### PR #59

Contains the predecessor source-identity work and the first explicit AKOS/OPERATOR epistemic-use contract. Reimplement its valuable semantics in P0 on current strongest-boot main. Once current-main proof exists, close #59 as superseded with a pointer to the replacement implementation.

### PR #57

Its stale-hash repair appears substantially superseded by merged connector bridge work. Verify unique diff before closure; do not merge redundant repair.

## 17. First execution tranche

The first build should stay focused enough to prove the architecture but broad enough to be real.

### Repository

`GlacierEQ/apex-control-plane`, current `main`.

### Expected files

Prefer a small explicit semantic module plus integration changes rather than adding dozens of policy booleans.

Candidate surfaces:

```text
NEW: src/epistemic_use_contract.py
NEW: config/epistemic_use_contract.schema.json or equivalent typed schema

MODIFY:
config/operator_fidelity_runtime_policy.json
src/operator_fidelity_preflight.py
src/operator_fidelity_lock.py
src/apex_strong_boot.py
src/apex_runtime_kernel.py
src/verified_runtime_entrypoint.py

TEST:
tests/test_epistemic_use_contract.py
tests/test_operator_fidelity_lock.py
tests/test_operator_fidelity_preflight.py
tests/test_apex_strong_boot.py
tests/test_apex_runtime_kernel.py
tests/test_verified_runtime_entrypoint.py
```

### First-tranche proof

Must produce:

- typed knowledge envelope;
- typed OPERATOR use directive;
- typed execution intent;
- system diagnostic source class;
- no hard-coded old OPERATOR direction in generic policy;
- no machine diagnostic text masquerading as OPERATOR words;
- end-to-end observation and mutation tests;
- existing strongest-boot and runtime suites still passing;
- exact source-head receipt/readback before promotion.

## 18. Quality gates for every tranche

A tranche is not complete because code was written.

Required where applicable:

```text
READ CURRENT SOURCE
→ MAP CALLERS / CONSUMERS
→ IMPLEMENT
→ UNIT TEST
→ ADVERSARIAL TEST
→ INTEGRATION TEST
→ FAILURE TEST
→ SOURCE READBACK
→ CI READBACK
→ RUNTIME / PRODUCER READBACK
→ RECORD VERIFIED GAIN
→ UPDATE DEPENDENT SEMANTICS
```

Claims use these boundaries:

- **implemented**: code exists;
- **tested**: relevant automated tests passed on exact source;
- **integrated**: consuming boundary exercised;
- **deployed/operational**: target environment observed;
- **verified**: expected terminal state read back;
- **observed in operation**: subsequent real use confirmed behavior.

Never promote one state into another by wording.

## 19. Things explicitly not to do

- do not create another giant constitutional layer;
- do not turn the epistemic/use distinction into hundreds of static policy flags;
- do not make AKOS weak in order to protect OPERATOR;
- do not make OPERATOR weak in order to protect truth-state discipline;
- do not let “proof” become permission to paralyze unrelated internal engineering;
- do not let “maximum” become maximum blast radius;
- do not treat repository similarity as duplication;
- do not auto-rank or dispose of OPERATOR-owned assets from inventory metadata;
- do not merge old PRs merely because they exist;
- do not erase useful historical evidence when superseding implementation;
- do not let Monolith, Aspen, ECHO, Tower, Alpha, Omega, a receipt, or a validator impersonate either AKOS knowledge-state responsibility or OPERATOR use-direction;
- do not count a README link as an exercised integration;
- do not call a reachable connector action-capable without the exact action proof.

## 20. High-quality target state

The stack is materially stronger when an agent can enter from any major surface and recover the same operating model without interpretive heroics:

```text
ASPEN / CONNECTORS / SOURCES / ECHO
             ↓ observations + continuity
            AKOS
       KNOWLEDGE GRAPH
             ↓ knowledge refs
          OPERATOR
        USE DIRECTIVE
             ↓
            APEX
   SMART ACTION COMPOSITION
             ↓
   ALPHA intelligence ↔ planning
             ↓
 OMEGA / WORKERS / TOWER / PRO-CODE
             ↓
     EXECUTION + PROOF
             ↓
    RECEIPTS + READBACK
             ↓
            AKOS
```

Success is not that every repository uses identical language. Success is that interfaces preserve the same meaning:

**AKOS determines how knowledge is known. OPERATOR determines how knowledge is used. APEX composes and executes the smartest action without allowing either side to impersonate the other.**
