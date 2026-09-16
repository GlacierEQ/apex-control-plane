# Casey Continuity Auto-Boot + APEX Genesis

The APEX control plane uses a deterministic, repair-forward startup path for workers that continue the living GlacierEQ estate without inventing missing state, rebuilding already-known state, or pretending that loaded state is current enough for a material claim.

The startup path is governed by [`APEX_ENFORCED_STARTUP.md`](../APEX_ENFORCED_STARTUP.md).

## Execution doctrine

Startup evidence is strict about truth, but truth checks are not global permission authorities.

```text
CAPABILITY
  -> EXECUTE KNOWN PERMITTED FRONTIERS
  -> HARDEN / TEST / VERIFY
  -> RECORD UPLIFT FINDINGS
  -> REPAIR / REROUTE THE AFFECTED FRONTIER
  -> PRESERVE VERIFIED GAIN
  -> COMPLETE
  -> RECEIPT / READBACK
```

Missing, stale, malformed, conflicting, or incomplete recoverable startup evidence becomes a durable `uplift_required` finding. It does not revoke unrelated mission authority or terminate unaffected executable frontiers.

Concrete provider, credential, hardware, legal, destructive-action, irreversible-action, and unrecoverable runtime-integrity constraints remain binding on the route that actually carries them.

## Startup observation stack

The strong-boot path composes multiple evidence observers. Each observer contributes diagnostics, provenance, and repair work; no observer acquires blanket authority to decide whether unrelated capability may exist.

1. **Model-attractor / hidden-harm defense** — detects `CONTINUE -> RECONSTRUCT`, known-state rediscovery, operation-class drift, and substitution of assistant support work for the Operator mission.
2. **Notion/continuity observation** — resolves configured identity, expectations, capabilities, existing work, owners, consumers, dependencies, and overlaps where live provider state is materially required.
3. **Continuity evidence** — checks configured memory notes/versions, current sources, repository receipts, lanes, deadlines, task context, and unresolved contradictions.
4. **Prime Directive evidence** — confirms relevant memory/continuity state was consulted; provenance-bearing known state was reused when usable, or a fresh search was performed only when materially justified; pinned operating files are hash-verified; structured tool inventory and source proof are recorded.
5. **APEX Genesis / Operator fidelity** — checks Operator intent, literal operation class, nearest valid continuation, preserved prior gains, contradiction state, execution-state model, strongest coherent path, and verification plan.
6. **Mission-outcome fidelity classifier** — distinguishes actual mission-state transitions from intermediate artifacts. Verified intermediate work may persist and become the launch point for the next material frontier; it must not be mislabeled as mission completion.

These contracts compose. None grants a repository, page, registry, summary, manifest, validator, CI check, or historical governance label project-direction authority over current Operator intent.

## Startup order

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
  -> REPAIR / REROUTE
  -> VERIFY MISSION OUTCOME
  -> CURRENT_STATE ⊕ VERIFIED_GAIN
  -> CONTINUE WHILE MISSION REMAINS OPEN
```

Startup findings strengthen execution. They do not manufacture a global precondition saying all proof must be complete before ordinary capability may run.

A new chat, worker, process, or runtime is a new execution context, not a new project. It does not create authority to rediscover or reconstruct relevant state that is already available in usable provenance-bearing form.

## Memory-state acquisition

Prime Directive memory acquisition has two valid paths.

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

A failed promotion check does not erase the underlying verified lower state. The worker repairs the missing evidence or affected execution path and continues from the strongest state actually proved.

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

An open contradiction remains visible and must be repaired or scoped. It does not silently become a global runtime veto unless the contradiction eliminates every executable frontier or corresponds to a concrete route-specific constraint.

## Notion continuity evidence

The continuity observer may require configured Notion wake-set evidence and existing-work discovery across specified systems when that live provider proof is part of the selected profile. That provider-specific requirement does **not** convert into a global rule that every worker must search memory or reconstruct already-known state.

For existing work, mapping and continuation preserve existing capability. An Operator-authorized separate root may use an explicit structured override while preserving the existing system.

## Strict mode

```bash
CASEY_AUTO_BOOT_MODE=strict python src/control_plane.py
```

Strict mode means evidence requirements remain strict: missing or conflicting proof is recorded exactly and surfaced as uplift work. Recoverable evidence gaps do not terminate the runtime or globally set external-action authority to false. Known executable frontiers continue while the affected evidence/route is repaired.

## Request mode

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

Request mode exposes startup contracts and diagnostic/uplift state for connector-bridge development and inspection. It is not proof of continuity, current-source retrieval, or completion. It also does not manufacture global permission authority.

Current uplift-oriented status projections include `complete`, `degraded` where retained for compatibility, and `uplift_required`. Historical `blocked`, `continuation_required`, `*_GATE_STATUS`, and hard-lock names may remain in compatibility schemas or provider-required check identities until migrated; those labels are non-authorizing and must not be used to infer a global execution veto.

## Off mode

```bash
CASEY_AUTO_BOOT_MODE=off python src/control_plane.py
```

or:

```bash
CASEY_AUTO_BOOT_DISABLE=1 python src/control_plane.py
```

A disabled observer cannot claim that its own evidence stage completed. Disabling an observer also does not grant or revoke unrelated route authority.

## Profiles

Configured profiles remain in `config/casey_auto_boot_manifest.json`. A profile may require exact provider-native notes or current sources for its own evidence boundary. Such requirements are material acquisition requirements, not authority to discard usable state already present elsewhere or stop unrelated capability.

## Ground-truth operating files

Prime Directive startup hash-verifies pinned operating files against active bytes. A mismatch is an evidence defect that must be surfaced and repaired; the mismatch does not manufacture authority over unrelated execution paths.

Current Prime Directive pins are defined in `config/prime_directive_policy.json`; the policy's memory stage is `memory_state`, not mandatory `memory_search`.

APEX adds its own policy and protocol:

- `APEX_ENFORCED_STARTUP.md`
- `config/apex_enforced_startup_policy.json`
- `src/apex_enforced_startup.py`

## Response and runtime middleware

Response/runtime middleware may prevent false state promotion, destructive scope expansion, source-authority substitution, or actions that actually require a provider/credential/legal/destructive boundary. It must not convert missing support evidence into blanket permission authority over ordinary capability.

APEX and StrongBoot therefore use unsupported state, minimization, destructive reduction, model-attractor drift, and false mission-progress findings as repair signals unless a concrete route-specific constraint is present.

## Optional site hook

When `src` is already on `PYTHONPATH`, `src/sitecustomize.py` can establish the same StrongBoot session for another entrypoint when `CASEY_AUTO_BOOT=1`. Recoverable observer findings are attached to that session rather than used as process-kill votes.

## Security and real-world consequences

No credentials, restricted source payloads, sealed records, or original child/medical records belong in repository policies or boot receipts.

Tool availability is capability, not proof of authorization for a consequential external act. Filing, sending, deleting, publishing, deploying, credential use, irreversible changes, and other externally consequential mutations remain bound to the actual Operator/provider/legal constraint applicable to that route.

That route-local rule must not be generalized into “ordinary capability must earn permission before it can execute.”

## Legacy archive boundary

Files under `legacy/` preserve historical source-bearing behavior for forensic comparison and regression archaeology. They are not current runtime doctrine and must not be imported or executed as authority for the active control plane unless an explicit migration operation says otherwise.

## Boundary

This repository governs execution paths that actually import or execute its active runtime code. Markdown, archived legacy files, historical check names, and compatibility fields do not themselves confer runtime authority.
