# GlacierEQ Prime Directive Enforcer under APEX Genesis

This middleware prevents a compatible model execution loop from substituting prose for required startup state acquisition and proof. It is one enforcement layer inside the broader [`APEX_ENFORCED_STARTUP.md`](../APEX_ENFORCED_STARTUP.md) contract.

## Authority and scope

```text
PROJECT_DIRECTION_AUTHORITY = OPERATOR_INTENT
OBJECTIVE                   = MAXIMUM_COHERENT_ADVANCE
STATE_EVOLUTION             = CURRENT_STATE ⊕ VERIFIED_GAIN
```

The Prime Directive middleware does not create independent project authority. Its job is mechanical: prove the required memory-state, source, tool-inventory, and receipt stages before user-facing text. APEX Genesis additionally binds continuation, Operator intent, target state, path quality, contradiction state, and evidence-backed execution promotion.

The memory stage is **state acquisition**, not mandatory search. Relevant provenance-bearing state already available in the worker may be reused. Fresh search is valid only when rediscovery is materially justified.

## Enforcement chain

```text
model output
   │
   ├─ contains tool calls ───────────► strip unsupported pre-gate prose
   │                                     │
   │                                     └─ record successful results
   │
   └─ contains text only ────────────► reject with hard correction

relevant memory / continuity state consulted
        │
        ├─ usable known state exists ──► provenance-bearing reuse
        │
        └─ material delta requires retrieval
              └─► justified memory search / source re-open
        +
hash-verified pinned operating files
        +
structured loaded-tool inventory
        +
current task sources opened when materially required
        +
combined provider receipt validated
        │
        ▼
sealed Prime Directive proof
        │
        ▼
APEX Genesis + Operator-fidelity validation
        │
        ▼
continuation + Operator intent + target + path + verification bound
        │
        ▼
mission-outcome fidelity boundary
        │
        ▼
runtime execution permitted
```

**Rediscovery of already-known relevant Operator/project state is not progress.**

The APEX entrypoint runs the continuity preflight, Prime Directive proof, APEX Genesis gate, Operator-fidelity boundary, model-attractor defense, and strong-boot composition before trusted runtime execution:

```bash
python src/control_plane.py
```

Strict mode is the default. Missing or malformed required proof exits with code `78`.

## Files

- `APEX_ENFORCED_STARTUP.md` — primary startup/execution contract.
- `STATE.md` — APEX runtime-state contract and current repository startup surface.
- `AGENT_SYSTEM_PROMPT.md` — APEX Operator execution prompt.
- `OPERATOR_EXECUTION_LAW.md` — project-direction and execution law.
- `config/apex_enforced_startup_policy.json` — executable Genesis startup policy.
- `config/prime_directive_policy.json` — pinned file hashes, tool aliases, reuse/search receipt rules, and five-stage state-acquisition/proof rules.
- `src/apex_enforced_startup.py` — Genesis receipt and execution-state transition enforcement.
- `src/prime_directive_boot.py` — continuity + Prime Directive receipt validation.
- `src/prime_directive_enforcer.py` — provider-tolerant pre-text middleware.
- `src/control_plane.py` — fail-closed startup wrapper.

## Middleware integration

A host execution loop may satisfy the memory-state stage in either of two ways.

### Reuse known state

When materially relevant state is already available and usable, record a reuse proof without invoking a search tool. Reuse requires explicit structured `class:locator` provenance, a non-empty item count, and `known_state_available=true`:

```python
from prime_directive_enforcer import StartupGateEnforcer

enforcer = StartupGateEnforcer()
enforcer.record_memory_state_reuse(
    source="conversation-context:current-worker",
    item_count=3,
    known_state_available=True,
)
```

The reuse path is monotonic: later unrelated retrieval calls cannot silently downgrade the acquisition mode to `searched`.

### Perform materially justified rediscovery

When usable state is unavailable, may have changed, conflicts with another source-bearing state, or exact source-native verification is required, invoke an allowed search tool and record the successful result. **The search invocation itself** must carry a non-empty query and an allowed `material_rediscovery_justification`; a successful search result without that proof does not advance the memory-state stage. The provider receipt must preserve the same justification.

The broader execution loop validates the combined Prime Directive receipt and attaches the sealed validation before this middleware permits text. The APEX entrypoint then separately validates the Genesis startup receipt before runtime load.

```python
from auto_boot import load_manifest, normalize_profiles
from prime_directive_boot import validate_combined_receipt
from prime_directive_enforcer import StartupGateEnforcer, load_policy

enforcer = StartupGateEnforcer()
manifest = load_manifest()
policy = load_policy()
profiles = normalize_profiles(manifest, ["systems"])

if reusable_state_is_already_present():
    enforcer.record_memory_state_reuse(
        source="conversation-context:current-worker",
        item_count=reusable_state_count(),
        known_state_available=True,
    )

while True:
    raw = model.generate(messages=messages, tools=loaded_tools)
    checked = enforcer.intercept_llm_response(raw)

    if checked.get("type") in {"hard_correction", "startup_gate_terminal_block"}:
        messages.append(checked)
        if checked["type"] == "startup_gate_terminal_block":
            raise RuntimeError(checked["content"])
        continue

    if checked.get("tool_calls"):
        tool_results = execute_tool_calls(checked["tool_calls"])
        for item in tool_results:
            enforcer.record_tool_result(
                item["tool_name"],
                item["result"],
                arguments=item.get("arguments"),
                call_id=item.get("call_id"),
                success=item["success"],
            )
            messages.append(item["message"])

        if provider_receipt_is_ready():
            receipt = build_provider_receipt()
            validation = validate_combined_receipt(
                manifest,
                policy,
                receipt,
                profiles,
                restricted_authorized=False,
            )
            enforcer.attach_boot_validation(validation)
        continue

    deliver_to_user(checked)
```

A memory-search tool call must therefore look like this at invocation time:

```json
{
  "query": "task topic and user/project context",
  "material_rediscovery_justification": "state_not_available_in_usable_form"
}
```

A tool invocation alone does not advance a stage. The execution loop records a successful result. A hand-built object claiming `ok=true` cannot complete the gate; only a sealed validation object issued by the validator is accepted.

## Combined boot receipt

The provider-backed receipt includes continuity fields plus evidence for memory-state acquisition, pinned operating-file reads, tool inventory, and current-source access. The active repository bytes, policy-pinned SHA-256 values, and receipt values must agree.

### Reused state receipt

```json
{
  "memory_state": {
    "mode": "reused",
    "status": "complete",
    "source": "conversation-context:current-worker",
    "item_count": 3,
    "known_state_available": true,
    "material_rediscovery_justification": ""
  },
  "ground_truth_files_loaded": [
    {
      "path": "STATE.md",
      "sha256": "<pinned sha256>",
      "source": "GitHub.fetch_file:STATE.md"
    },
    {
      "path": "AGENT_SYSTEM_PROMPT.md",
      "sha256": "<pinned sha256>",
      "source": "GitHub.fetch_file:AGENT_SYSTEM_PROMPT.md"
    },
    {
      "path": "APEX_ENFORCED_STARTUP.md",
      "sha256": "<pinned sha256>",
      "source": "GitHub.fetch_file:APEX_ENFORCED_STARTUP.md"
    },
    {
      "path": "OPERATOR_EXECUTION_LAW.md",
      "sha256": "<pinned sha256>",
      "source": "GitHub.fetch_file:OPERATOR_EXECUTION_LAW.md"
    }
  ],
  "tool_inventory": {
    "tool": "api_tool.list_resources",
    "status": "complete",
    "loaded_tools": [
      "GitHub.fetch_file",
      "api_tool.list_resources"
    ],
    "gaps": []
  }
}
```

The reuse `source` is not free-form text: it must have both a source class and locator separated by `:`. An unstructured projection such as `"invented-projection"` cannot establish provenance.

### Searched state receipt

```json
{
  "memory_state": {
    "mode": "searched",
    "status": "complete",
    "source": "personal_context.search:task-topic",
    "item_count": 3,
    "known_state_available": false,
    "material_rediscovery_justification": "state_not_available_in_usable_form",
    "tool": "personal_context.search",
    "query": "task topic and user/project context"
  }
}
```

For searched state, the provenance source class must match the search tool. Null or non-string `source`, `query`, or justification fields are invalid rather than being string-coerced into apparent proof.

Legacy `memory_search` receipts remain accepted as compatibility input only when their legacy status is valid; invalid statuses are preserved through projection and rejected. New requests emit `memory_state` semantics.

## APEX Genesis extension

The same startup run also requires an `apex_startup` receipt proving, among other fields:

```json
{
  "authority": "operator_intent",
  "objective": "maximum_coherent_advance",
  "known_state_reused_before_rediscovery": true,
  "context_reconstructed": true,
  "prior_state_retrieved": true,
  "continuation_resolved": true,
  "operator_intent_resolved": true,
  "prior_valid_gains_preserved": true,
  "contradiction_status": "none",
  "state_model_bound": true,
  "selected_path": {
    "operator_alignment": true,
    "artificial_minimization": false,
    "destructive_reduction": false,
    "unsupported_action": false,
    "redundant_restart": false,
    "preserves_prior_valid_gain": true
  },
  "verification_plan": ["test", "adversarial test", "readback"]
}
```

`context_reconstructed` and `prior_state_retrieved` are compatibility receipt names. They mean the required context/prior-state obligations are satisfied; they do **not** authorize throwing away usable known state and rebuilding it.

An open contradiction blocker, artificial minimization, destructive reduction, unauthorized state promotion, or known-state rediscovery violation fails closed.

## Empty memory result

An empty search is valid only when a materially justified search actually ran and reports zero hits. `UNKNOWN != FALSE`; an empty result is not permission to invent nonexistence.

No empty-search phrase is emitted for the reuse path.

## Hard-correction behavior

Before the Prime Directive stage passes, unsupported text-only output is replaced with a correction that identifies missing stages. For the memory stage, that correction orders the worker to **consult relevant already-available state first**, record provenance-bearing reuse when usable, and search only when rediscovery is materially justified.

Pre-gate messages containing necessary tool calls are allowed while accompanying unsupported prose is removed.

After repeated bypass attempts, the middleware enters a terminal blocked state instead of laundering failure into completion.

## Audit and security

The enforcer records metadata such as event type, timestamp, normalized tool name, acquisition mode, and stage status. It does not log model content, prompts, tool arguments, credentials, or restricted source payloads.

## Mission-outcome boundary

Passing startup gates is not itself progress on the Operator mission. Mutation work remains behind the mission-outcome fidelity hard lock: assistant-authored artifacts, plans, reports, summaries, commits, or task updates cannot authorize persistence unless an underlying source-bearing mission-state transition or genuine route-exhausted external boundary is proved.

## Boundary

This code enforces the contract in execution loops that actually import or execute it. It does not make unrelated software obey a repository file merely because markdown describes the contract. A compatible worker must execute the gates and produce the receipts.
