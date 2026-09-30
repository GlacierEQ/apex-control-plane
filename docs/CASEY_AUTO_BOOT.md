# Casey Continuity Auto-Boot + APEX Runtime

The APEX control plane uses deterministic continuity startup observations for workers that must continue the living GlacierEQ estate without inventing missing state, rebuilding already-known state, or assuming that loaded state is current enough for a material action. Startup completeness is diagnostic evidence, not project-direction permission.

The startup path is governed by [`APEX_ENFORCED_STARTUP.md`](../APEX_ENFORCED_STARTUP.md).

## Startup observation stack

When corresponding evidence is available or materially required for a specific claim or route, the startup/strong-boot path can compose these compatible observations:

1. **Model-attractor / hidden-harm defense** — detects `CONTINUE -> RECONSTRUCT`, needless known-state rediscovery, operation-class drift, and substitution of assistant support work for the Operator mission, then surfaces repair-forward findings.
2. **Notion/continuity integration proof** — resolves configured identity, expectations, capabilities, existing work, owners, consumers, dependencies, and overlaps where that live provider state is materially required.
3. **Continuity proof** — exact memory notes/versions where configured, current sources where required, repository receipts, lanes, deadlines, task context, and blocker state.
4. **APEX Genesis / Operator fidelity observation** — Operator intent, literal operation class, nearest valid continuation, preserved prior gains, execution-state model, coherent path, and verification plan remain available; actual material conflicts are investigated when present.
5. **Mission-outcome fidelity accounting** — assistant activity is not automatically mission progress; claims about execution or external state remain tied to evidence of what actually changed.

These contracts compose. None grants a repository, page, registry, summary, manifest, validator, CI gate, or historical governance label project-direction authority over current Operator intent.

## Runtime continuation order

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

Startup observations do not grant or withhold project-direction authority. Absence of optional self-created proof is neutral. Explicitly supplied incomplete or invalid proof becomes repair/enrichment evidence. A real provider, credential, security, destructive-action, or factual constraint limits the affected route only.

A new chat, worker, process, or runtime is a new execution context, not a new project. It does not create authority to rediscover or reconstruct relevant state that is already available in usable provenance-bearing form.

## Context acquisition

Reuse materially relevant known state when it is already available and usable. Retrieve or reopen source-native state when it is absent, may have changed, conflicts materially, or exact source bytes are needed for the requested work.

A failed retrieval does not prove the underlying state is absent, and rediscovering already-known relevant state is not mission progress.

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

## Notion continuity receipt

The continuity preflight may still require configured Notion wake-set evidence and existing-work discovery across specified systems when that live provider proof is part of the selected profile. That provider-specific requirement does **not** convert into a global rule that every worker must search memory or reconstruct already-known state.

For existing work, `decision=extend` is valid. An Operator-authorized separate root may use `decision=operator_override` with a structured override record containing `authorized=true` and a non-empty reason.

## Strict mode

```bash
CASEY_AUTO_BOOT_MODE=strict python src/control_plane.py
```

Malformed explicit receipt input may fail that receipt-parsing route. An absent optional receipt creates no debt. Explicitly supplied incomplete startup evidence remains visible as enrichment and does not independently become general execution permission.

## Request mode

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

Request mode can emit or expose startup contracts when explicitly invoked for connector-bridge development or local inspection. Ordinary request-mode startup remains clean when no optional receipt is supplied. Emitting a contract is not proof of continuity, current-source retrieval, or runtime readiness.

Expected status projections include:

```text
GLACIEREQ_NOTION_CONTINUITY_GATE_STATUS=degraded|complete|blocked
GLACIEREQ_APEX_STARTUP_STATUS=off|complete|complete_enrichment_pending
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

A disabled run cannot claim continuity, APEX startup observation, or connected-source awareness.

## Profiles

Configured profiles remain in `config/casey_auto_boot_manifest.json`. A profile may require exact provider-native notes or current sources for its own proof boundary. Such profile requirements are material acquisition requirements, not authority to discard usable state already present elsewhere.

## APEX operating files

APEX keeps its active policy and protocol in:

- `APEX_ENFORCED_STARTUP.md`
- `config/apex_enforced_startup_policy.json`
- `src/apex_enforced_startup.py`

## Runtime diagnostics

APEX and strong boot surface unsupported state, destructive reduction, model-attractor drift, and false mission-progress claims as diagnostics and repair work. They do not suppress user-facing output merely because a self-created startup observer is incomplete.

## Optional site hook

When `src` is already on `PYTHONPATH`, `src/sitecustomize.py` can enforce the same sequence for another entrypoint when `CASEY_AUTO_BOOT=1`.

## Security

No credentials, restricted source payloads, sealed records, or original child/medical records belong in repository policies or boot receipts.

Tool availability is capability, not authorization. Filing, sending, deleting, publishing, deploying, or other external mutation remains bound to Operator authorization and the relevant execution receipt.

## Boundary

This repository enforces startup for execution paths that actually import or execute these gates. It does not cause unrelated software to run repository code merely because a markdown file describes the contract.
