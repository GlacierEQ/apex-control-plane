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
2. Consult relevant already-known memory, continuity, current-conversation, and project state before any rediscovery.
3. Reuse known valid state and identify the nearest valid continuation point. Search or re-open state only for a material delta: unavailable usable state, likely change, source-native verification, conflict resolution, or exact-artifact execution requirements.
4. Resolve requested referents, existing lineage, dependencies, unfinished work, and the unresolved material delta.
5. Resolve current Operator intent and target state.
6. Read this file, `AGENT_SYSTEM_PROMPT.md`, `OPERATOR_EXECUTION_LAW.md`, and `APEX_ENFORCED_STARTUP.md` as pinned source-native startup surfaces.
7. Enumerate the tools and connectors actually loaded.
8. Open current sources required by the task where freshness, exact bytes, conflict resolution, or mutation safety materially requires source-native state.
9. Validate continuity and Prime Directive receipts.
10. Validate the APEX Genesis startup receipt.
11. Only after the required gates pass, execute material mutation.

A failed call is not a completed startup step. Rediscovery of already-known relevant Operator/project state is not progress.

## Current enforcement model

The entrypoint is fail-closed:

- unresolved required material state -> block material mutation;
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
known_relevant_state_consulted = true
known_state_reused_where_usable = true
material_delta_hydrated = true
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

Tool access is capability, not project authority. A fresh search is not a prerequisite when relevant usable state is already present; a search or source re-open is justified when it resolves a material unknown, change, contradiction, exact-byte requirement, or source-native verification need.

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

When the Operator says `continue`, begin from the latest relevant known state, recover the nearest valid continuation, hydrate only the unresolved or materially changed delta, and resume work. Do not restart or rediscover merely because the execution context is new.

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

This file records runtime state. It is not original evidence and does not replace source-native verification when current/exact external state materially matters.

**KNOWN STATE → MATERIAL DELTA HYDRATION → CONTINUATION → OPERATOR INTENT → MAXIMUM COHERENT EXECUTION → VERIFY → PRESERVE ⊕ VERIFIED_GAIN.**
