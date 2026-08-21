# Casey Continuity Auto-Boot + APEX Genesis

The APEX control plane uses a deterministic startup path for workers that cannot safely assume they remember prior chats, project state, repository decisions, tools, sources, deadlines, failures, or where current work belongs.

The startup path is governed by [`APEX_ENFORCED_STARTUP.md`](../APEX_ENFORCED_STARTUP.md).

## Enforcement stack

`python src/control_plane.py` proves four compatible contracts before loading `src/control_plane_runtime.py`:

1. **Notion-first continuity / integration proof** — recover identity, expectations, capabilities, current state, existing work, owners, consumers, dependencies, and overlaps.
2. **Continuity proof** — exact memory notes/versions where configured, current sources, repository receipts, lanes, deadlines, task context, and blocker state.
3. **Prime Directive proof** — executed memory search, hash-verified operating files, structured tool inventory, current-source proof, and provider-backed receipt validation.
4. **APEX Genesis proof** — Operator intent, continuation, target state, preserved prior gains, contradiction status, execution-state model, strongest coherent path, and verification plan.

These contracts compose. None grants a repository, page, registry, or historical governance label project-direction authority over current Operator intent.

## Mandatory startup order

```text
CONTEXT RETRIEVAL
  -> EXISTING-STATE / CONTINUATION DISCOVERY
  -> OPERATOR INTENT BINDING
  -> TARGET STATE
  -> EVIDENCE-BOUND STATE MODEL
  -> STRONGEST COHERENT PATH
  -> EXECUTION
  -> TEST
  -> ADVERSARIAL TEST
  -> REPAIR
  -> VERIFY
  -> CURRENT_STATE ⊕ VERIFIED_GAIN
```

Continuity preflight must protect source state and prevent false state promotion. It must not become a universal stop switch. When a missing or conflicting continuity fact affects one lane, independent executable lanes continue while that dependency is reconciled.

## APEX topology and continuity fields

Current receipt and policy fields use APEX terminology:

- `apex_owner`
- `apex_owner_topology_resolved`
- `apex_conflicts`
- `apex_notion_pages`

These are topology and source-state fields. They do **not**:

- override explicit current Operator direction;
- authorize destructive consolidation;
- convert historical governance into present project authority;
- justify capability reduction;
- prevent an Operator-authorized new root when prior valid capability is preserved.

When existing work is found, continuation plus non-destructive integration is the default. Relationship discovery can therefore drive mission-aligned integration and hardening instead of terminating at an observational map.

A topology conflict must be recorded and reconciled. It does not nullify unrelated verified state or block independent work that does not depend on the conflict.

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

A proof gap blocks unsupported promotion. It does not erase a lower-state allegation, source, lead, or independent theory.

## APEX receipt extension

A compatible provider receipt includes an `apex_startup` object:

```json
{
  "apex_startup": {
    "authority": "operator_intent",
    "objective": "maximum_coherent_advance",
    "context_reconstructed": true,
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

A contradiction that actually blocks the requested mutation remains a real blocker for that dependent lane. Contradictions that do not affect an independent lane remain recorded while work continues.

## Notion continuity receipt

The continuity preflight requires the configured Notion wake set and proof that the worker searched for existing work across multiple systems.

For existing work, the normal relationship decision is `integrate_non_destructively`. A separate root requires `decision=operator_override` plus a structured override record containing `authorized=true` and a non-empty reason.

Inspection may expand into mission-aligned hardening without renewed confirmation when the expansion remains within the Operator's requested objective and does not dispose of Operator-owned assets. Asset value ranking, merger, retirement, deletion, subordination, or other disposition still requires explicit Operator direction.

## Strict mode

```bash
CASEY_AUTO_BOOT_MODE=strict python src/control_plane.py
```

Missing or malformed proof may prevent the dependent runtime path from loading. The gate records the exact dependency rather than converting a local continuity defect into a claim that all unrelated work is impossible.

## Request mode

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

Request mode emits or exposes required startup contracts and may continue as degraded. It is useful for connector-bridge development and local inspection. It is not proof of continuity, current-source retrieval, or runtime readiness.

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

```bash
CASEY_BOOT_PROFILE=legal_case python src/control_plane.py
CASEY_BOOT_PROFILE=systems python src/control_plane.py
CASEY_BOOT_PROFILE=legal_case,restricted_child \
CASEY_RESTRICTED_CONTEXT_AUTHORIZED=1 \
python src/control_plane.py
```

Configured profiles remain in `config/casey_auto_boot_manifest.json`.

## Ground-truth operating files

Prime Directive startup continues to hash-verify its pinned operating files. A mismatched active file does not satisfy the stage.

APEX adds its own policy and protocol:

- `APEX_ENFORCED_STARTUP.md`
- `config/apex_enforced_startup_policy.json`
- `src/apex_enforced_startup.py`

## Response middleware

`src/prime_directive_enforcer.py` blocks unsupported model text before its startup gate completes. APEX adds a runtime-start boundary that rejects unsupported state promotion, artificial minimization, destructive reduction, and genuinely blocking unresolved contradictions without turning those checks into an excuse to suppress independent executable work.

## Optional site hook

When `src` is already on `PYTHONPATH`, `src/sitecustomize.py` can enforce the same sequence for another entrypoint when `CASEY_AUTO_BOOT=1`.

## Security

No credentials, restricted source payloads, sealed records, or original child/medical records belong in repository policies or boot receipts.

Tool availability is capability, not authorization. Filing, sending, deleting, publishing, deploying, or other external mutation remains bound to Operator authorization and the relevant execution receipt.

## Boundary

This repository enforces startup for execution paths that actually import or execute these gates. It does not cause unrelated software to run repository code merely because a markdown file says so. Machines remain tragically literal.
