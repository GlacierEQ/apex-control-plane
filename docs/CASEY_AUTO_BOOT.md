# Casey Continuity Auto-Boot + APEX Genesis

The APEX control plane uses a deterministic, fail-closed startup path for workers that must continue the living GlacierEQ estate without inventing missing state, rebuilding already-known state, or assuming that loaded state is current enough for a material action.

The startup path is governed by [`APEX_ENFORCED_STARTUP.md`](../APEX_ENFORCED_STARTUP.md).

## Enforcement stack

The startup/strong-boot path composes multiple compatible proofs before material execution is trusted:

1. **Model-attractor / hidden-harm defense** — blocks `CONTINUE -> RECONSTRUCT`, known-state rediscovery, operation-class drift, and substitution of assistant support work for the Operator mission.
2. **Notion/continuity integration proof** — resolves configured identity, expectations, capabilities, existing work, owners, consumers, dependencies, and overlaps where that live provider state is materially required.
3. **Continuity proof** — exact memory notes/versions where configured, current sources where required, repository receipts, lanes, deadlines, task context, and blocker state.
4. **Prime Directive proof** — relevant memory/continuity state was consulted; provenance-bearing known state was reused when usable, or a fresh search was performed only with a material rediscovery justification; pinned operating files were hash-verified; structured tool inventory, current-source proof, and provider-backed receipt validation were established.
5. **APEX Genesis / Operator fidelity proof** — Operator intent, literal operation class, nearest valid continuation, preserved prior gains, contradiction status, execution-state model, strongest coherent path, and verification plan remain intact.
6. **Mission-outcome fidelity hard lock** — mutation work cannot persist merely because the assistant produced a ledger, matrix, summary, report, plan, commit, task update, or other durable artifact; it must prove an underlying source-bearing mission-state transition or an evidenced genuine external boundary after materially available internal routes are exhausted.

These contracts compose. None grants a repository, page, registry, summary, manifest, validator, CI gate, or historical governance label project-direction authority over current Operator intent.

## Mandatory startup order

```text
CURRENT OPERATOR MESSAGE
  -> CONSULT RELEVANT KNOWN STATE
  -> REUSE KNOWN VALID STATE WHERE USABLE
  -> ACTIVE THREAD / NEAREST VALID CONTINUATION
  -> HYDRATE ONLY MATERIAL UNKNOWN / CHANGED / CONFLICTING DELTA
  -> OPERATOR INTENT + TARGET
  -> EVIDENCE-BOUND STATE MODEL
  -> STRONGEST COHERENT PATH
  -> EXECUTION
  -> TEST
  -> ADVERSARIAL TEST
  -> REPAIR
  -> VERIFY MISSION OUTCOME
  -> CURRENT_STATE ⊕ VERIFIED_GAIN
```

Material mutation is blocked until the required startup proof is complete.

A new chat, worker, process, or runtime is a new execution context, not a new project. It does not create authority to rediscover or reconstruct relevant state that is already available in usable provenance-bearing form.

## Memory-state acquisition

Prime Directive memory acquisition has two valid paths:

### Reuse path

Use when materially relevant state is already available and usable.

```json
{
  "memory_state": {
    "mode": "reused",
    "status": "complete",
    "source": "conversation-context:current-worker",
    "item_count": 3,
    "known_state_available": true,
    "material_rediscovery_justification": ""
  }
}
```

No search tool call is required for this path. The source must be provenance-bearing and the state cannot be empty or invented.

### Search path

Use only when rediscovery is materially justified, for example because usable state is absent, state may have changed, exact source-native verification is required, available states conflict, or an exact artifact is needed for execution.

```json
{
  "memory_state": {
    "mode": "searched",
    "status": "complete",
    "source": "personal_context.search:task-topic",
    "item_count": 4,
    "known_state_available": false,
    "material_rediscovery_justification": "state_not_available_in_usable_form",
    "tool": "personal_context.search",
    "query": "task topic and user/project context"
  }
}
```

Legacy `memory_search` provider receipts remain accepted as a compatibility projection, but the runtime no longer emits mandatory-search semantics.

**Rediscovery of already-known relevant Operator/project state is not progress.**

## Continuity labels and historical `canonical` fields

Some receipt and policy fields retain names such as `canonical_owner`, `canonical_conflicts`, and `canonical_notion_pages` for schema compatibility. Under APEX these are topology/source labels only.

They do **not**:

- override explicit current Operator direction;
- authorize destructive consolidation;
- convert historical governance into present project authority;
- justify capability reduction;
- prevent an Operator-authorized new root when prior valid capability is preserved.

When existing work is found, continuation and integration are the default because restart without reason destroys lineage. An explicit Operator override may authorize a new root while preserving the existing system.

## APEX execution states

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

A worker may claim only the strongest state established by evidence.

Key promotion requirements:

- `ATTEMPTED -> EXECUTED`: execution receipt;
- `EXECUTED -> VERIFIED`: verification receipt;
- `VERIFIED -> COMMITTED`: commit receipt;
- `COMMITTED -> DEPLOYED`: deployment receipt;
- `DEPLOYED -> OBSERVED_IN_OPERATION`: runtime observation receipt.

## APEX receipt compatibility

The APEX startup receipt still contains compatibility fields such as `context_reconstructed` and `prior_state_retrieved`. Their valid meaning is **required context resolved and prior state accounted for**, not proof that a worker discarded usable state and rebuilt it.

The controlling continuation semantics are:

```text
known_state_reused_before_rediscovery = true
continuation_resolved = true
prior_valid_gains_preserved = true
```

A compatible provider receipt may therefore include:

```json
{
  "apex_startup": {
    "authority": "operator_intent",
    "objective": "maximum_coherent_advance",
    "known_state_reused_before_rediscovery": true,
    "context_reconstructed": true,
    "prior_state_retrieved": true,
    "continuation_resolved": true,
    "operator_intent_resolved": true,
    "operator_plan_authorized": true,
    "target_state": "non-empty target",
    "prior_valid_gains_preserved": true,
    "contradiction_status": "none",
    "state_model_bound": true,
    "mutation_intent": "authorized",
    "selected_path": {
      "id": "continue-and-extend",
      "operator_alignment": true,
      "artificial_minimization": false,
      "destructive_reduction": false,
      "unsupported_action": false,
      "redundant_restart": false,
      "preserves_prior_valid_gain": true
    },
    "verification_plan": [
      "run tests",
      "adversarially inspect state promotion and regression"
    ],
    "material_claims": []
  }
}
```

`contradiction_status=open_blocker` fails closed before runtime mutation.

## Notion continuity receipt

The continuity preflight may still require configured Notion wake-set evidence and existing-work discovery across specified systems when that live provider proof is part of the selected profile. That provider-specific requirement does **not** convert into a global rule that every worker must search memory or reconstruct already-known state.

For existing work, `decision=extend` is valid. An Operator-authorized separate root may use `decision=operator_override` with a structured override record containing `authorized=true` and a non-empty reason.

## Strict mode

```bash
CASEY_AUTO_BOOT_MODE=strict python src/control_plane.py
```

Missing, stale, malformed, conflicting, or incomplete required proof exits with status `78` before runtime load.

## Request mode

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

Request mode emits or exposes required startup contracts and may continue only as degraded. It is useful for connector-bridge development and local inspection. It is not proof of continuity, current-source retrieval, or runtime readiness.

Expected status projections include:

```text
GLACIEREQ_NOTION_CONTINUITY_GATE_STATUS=degraded|complete|blocked
GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS=degraded|complete|blocked
GLACIEREQ_APEX_STARTUP_STATUS=degraded|complete|blocked
CASEY_BOOT_STATUS=degraded|complete|blocked
```

## Off mode

```bash
CASEY_AUTO_BOOT_MODE=off python src/control_plane.py
```

or:

```bash
CASEY_AUTO_BOOT_DISABLE=1 python src/control_plane.py
```

A disabled run cannot claim continuity, Prime Directive completion, APEX startup completion, or connected-source awareness.

## Profiles

Configured profiles remain in `config/casey_auto_boot_manifest.json`. A profile may require exact provider-native notes or current sources for its own proof boundary. Such profile requirements are material acquisition requirements, not authority to discard usable state already present elsewhere.

## Ground-truth operating files

Prime Directive startup hash-verifies its pinned operating files against active bytes. A mismatched active file does not satisfy the stage.

Current Prime Directive pins are defined in `config/prime_directive_policy.json`; the policy's memory stage is `memory_state`, not mandatory `memory_search`.

APEX adds its own policy and protocol:

- `APEX_ENFORCED_STARTUP.md`
- `config/apex_enforced_startup_policy.json`
- `src/apex_enforced_startup.py`

## Response middleware

`src/prime_directive_enforcer.py` blocks unsupported model text before its startup gate completes. Its correction path orders workers to consult/reuse known state first and to search only when rediscovery is materially justified.

APEX and strong boot add runtime boundaries against unsupported state, minimization, destructive reduction, model-attractor drift, and false mission-progress claims.

## Optional site hook

When `src` is already on `PYTHONPATH`, `src/sitecustomize.py` can enforce the same sequence for another entrypoint when `CASEY_AUTO_BOOT=1`.

## Security

No credentials, restricted source payloads, sealed records, or original child/medical records belong in repository policies or boot receipts.

Tool availability is capability, not authorization. Filing, sending, deleting, publishing, deploying, or other external mutation remains bound to Operator authorization and the relevant execution receipt.

## Boundary

This repository enforces startup for execution paths that actually import or execute these gates. It does not cause unrelated software to run repository code merely because a markdown file describes the contract.
