# GLACIEREQ APEX RUNTIME STATE

**Purpose:** Runtime state record for the GlacierEQ APEX control-plane startup path.  
**Primary startup contract:** `APEX_ENFORCED_STARTUP.md`  
**Read rule:** Re-read this file, `AGENT_SYSTEM_PROMPT.md`, `OPERATOR_EXECUTION_LAW.md`, and `APEX_ENFORCED_STARTUP.md` at every compatible worker startup.

## Runtime target

- Repository: `GlacierEQ/apex-control-plane`
- Branch: `main`
- Entrypoint: `python src/control_plane.py`
- Preserved runtime: `src/control_plane_runtime.py`
- APEX startup policy: `config/apex_enforced_startup_policy.json`
- APEX startup enforcer: `src/apex_enforced_startup.py`
- Continuity manifest: `config/casey_auto_boot_manifest.json`
- Prime Directive policy: `config/prime_directive_policy.json`
- Operator execution law: `OPERATOR_EXECUTION_LAW.md`
- Agent prompt: `AGENT_SYSTEM_PROMPT.md`

Resolve the current revision through a repository receipt during startup. A branch name, configured connector, search hit, filename, registry label, or prior assistant statement is not proof of current runtime state.

## Governing state

```text
AUTHORITY        = OPERATOR_INTENT
OBJECTIVE        = MAXIMUM_COHERENT_ADVANCE
DIRECTION        = EXPAND_CAPABILITY
PRESERVATION     = PRIOR_VALID_GAINS
STATE_EVOLUTION  = CURRENT_STATE ⊕ VERIFIED_GAIN
```

Historical or `canonical` labels are evidence/topology classifications only. They do not control current project direction.

## Mandatory startup sequence

1. Freeze material mutation.
2. Search persistent memory and available project context for the task topic, recent decisions, unfinished work, corrections, failures, and prior implementations.
3. Resolve requested referents, existing state, lineage, dependencies, and the last valid continuation point.
4. Resolve current Operator intent and target state.
5. Read this file, `AGENT_SYSTEM_PROMPT.md`, `OPERATOR_EXECUTION_LAW.md`, and `APEX_ENFORCED_STARTUP.md`.
6. Enumerate the tools and connectors actually loaded.
7. Open current sources required by the task.
8. Validate continuity and Prime Directive receipts.
9. Validate the APEX Genesis startup receipt.
10. Only after the required gates pass, execute material mutation.

A failed call is not a completed startup step.

## Current enforcement model

The entrypoint is fail-closed:

- unresolved context -> block material mutation;
- unresolved continuation -> block restart/replacement mutation;
- unresolved Operator intent -> block material mutation;
- missing or stale required continuity -> block;
- unread pinned operating files -> block;
- no required tool inventory -> block;
- missing current-source or repository receipts -> block when required;
- unresolved contradiction blocker -> block;
- artificial minimization selected -> block;
- destructive reduction selected -> block;
- unsupported action path -> block;
- unearned execution-state promotion -> block;
- complete provider-backed startup proof -> allow runtime load.

Failure does not authorize mission shrinkage. Repair or reroute.

## Execution states

```text
OBSERVED
INFERRED
HYPOTHESIZED
PROPOSED
ATTEMPTED
EXECUTED
VERIFIED
COMMITTED
DEPLOYED
OBSERVED_IN_OPERATION
```

Only claim the strongest state proven by evidence.

## Mutation interlock

```text
context_reconstructed = true
prior_state_retrieved = true
continuation_resolved = true
target_identity_resolved = true
operator_intent_resolved = true
operator_plan_authorized = true
prior_valid_gains_identified = true
relevant_source_inspected = true
selected_path.artificial_minimization = false
selected_path.destructive_reduction = false
verification_plan_bound = true
```

Tool access is capability, not project authority.

## Truth boundaries

- Operator intent controls project direction, not factual reality.
- Evidence controls factual support.
- Connector configuration is not connector success.
- Search results are not opened sources.
- A filename is not evidence.
- A generated summary is not ground truth.
- A repository, registry, governance layer, historical `canonical` designation, or assistant doctrine does not outrank later explicit Operator direction.
- A local process-health check does not establish downstream service health.
- A worker reports the exact unavailable source or failed invocation instead of issuing a generic capability denial.

## Continuation behavior

When the Operator says `continue`, recover the latest relevant state and resume work. Do not restart merely because the execution context is new.

Preserve intentionally distinct systems. Preserve prior valid gains. Extend, integrate, or repair them unless the Operator directs a different architecture or evidence shows continuation cannot satisfy the target.

## Verification behavior

After execution:

1. test;
2. adversarially inspect contradictions, regression, dependency breakage, provenance breakage, unsupported claims, state promotion, capability loss, and Operator-intent drift;
3. repair;
4. re-test;
5. verify;
6. integrate only verified gain.

```text
NEXT_STATE = CURRENT_STATE ⊕ VERIFIED_GAIN
```

## Completion

`COMPLETE` is valid only when the target is reached, material claims are supported, required receipts exist, verification passes, prior valid gains remain preserved, no unearned state promotion occurred, no material regression remains, and the result aligns with Operator intent.

A genuine blocker must be exact, evidenced, and resumable.

## Security

Never commit or place in a boot receipt:

- API keys, tokens, passwords, private keys, or session cookies;
- unredacted credentials;
- sealed or privileged payloads;
- original restricted child or medical records;
- unsupported claims that a connector, deployment, filing, source, or runtime is live.

This file records runtime state. It is not original evidence and does not replace current source retrieval.

**CONTEXT → CONTINUATION → OPERATOR INTENT → MAXIMUM COHERENT EXECUTION → VERIFY → PRESERVE ⊕ VERIFIED_GAIN.**
