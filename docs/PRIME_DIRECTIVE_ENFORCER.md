# GlacierEQ Prime Directive Enforcer under APEX Genesis

This middleware prevents a compatible model execution loop from substituting prose for required startup retrieval and proof. It is one enforcement layer inside the broader [`APEX_ENFORCED_STARTUP.md`](../APEX_ENFORCED_STARTUP.md) contract.

## Authority and scope

```text
PROJECT_DIRECTION_AUTHORITY = OPERATOR_INTENT
OBJECTIVE                   = MAXIMUM_COHERENT_ADVANCE
STATE_EVOLUTION             = CURRENT_STATE ⊕ VERIFIED_GAIN
```

The Prime Directive middleware does not create independent project authority. Its job is mechanical: prove required retrieval and source stages before user-facing text, while APEX Genesis additionally binds continuation, Operator intent, target state, path quality, contradiction state, and evidence-backed execution promotion.

## Enforcement chain

```text
model output
   │
   ├─ contains retrieval tool calls ──► strip unsupported pre-gate prose
   │                                      │
   │                                      └─ record successful results
   │
   └─ contains text only ─────────────► reject with hard correction

successful memory search
        +
hash-verified STATE.md
        +
hash-verified AGENT_SYSTEM_PROMPT.md
        +
structured loaded-tool inventory
        +
current task sources opened
        +
combined provider receipt validated
        │
        ▼
sealed Prime Directive proof
        │
        ▼
APEX Genesis receipt validation
        │
        ▼
continuation + Operator intent + target + path + verification bound
        │
        ▼
runtime execution permitted
```

The APEX entrypoint runs the continuity preflight, Prime Directive proof, and APEX Genesis gate before loading `src/control_plane_runtime.py`:

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
- `config/prime_directive_policy.json` — pinned file hashes, tool aliases, failure phrases, and five-stage retrieval/proof rules.
- `src/apex_enforced_startup.py` — Genesis receipt and execution-state transition enforcement.
- `src/prime_directive_boot.py` — continuity + Prime Directive receipt validation.
- `src/prime_directive_enforcer.py` — provider-tolerant pre-text middleware.
- `src/control_plane.py` — fail-closed startup wrapper.

## Middleware integration

The execution loop validates the combined Prime Directive receipt and attaches the sealed validation before this middleware permits text. The APEX entrypoint then separately validates the Genesis startup receipt before runtime load.

```python
from auto_boot import load_manifest, normalize_profiles
from prime_directive_boot import validate_combined_receipt
from prime_directive_enforcer import StartupGateEnforcer, load_policy

enforcer = StartupGateEnforcer()
manifest = load_manifest()
policy = load_policy()
profiles = normalize_profiles(manifest, ["systems"])

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

A tool invocation alone does not advance a stage. The execution loop records a successful result. A hand-built object claiming `ok=true` cannot complete the gate; only a sealed validation object issued by the validator is accepted.

## Combined boot receipt

The provider-backed receipt includes continuity fields plus evidence for memory search, pinned operating-file reads, tool inventory, and current-source access. The active repository bytes, policy-pinned SHA-256 values, and receipt values must agree.

```json
{
  "memory_search": {
    "tool": "personal_context.search",
    "query": "task topic and user/project context",
    "status": "searched",
    "hit_count": 3
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
    }
  ],
  "tool_inventory": {
    "tool": "api_tool.list_resources",
    "status": "complete",
    "loaded_tools": [
      "personal_context.search",
      "GitHub.fetch_file",
      "api_tool.list_resources"
    ],
    "gaps": []
  }
}
```

## APEX Genesis extension

The same startup run also requires an `apex_startup` receipt proving, among other fields:

```json
{
  "authority": "operator_intent",
  "objective": "maximum_coherent_advance",
  "context_reconstructed": true,
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

An open contradiction blocker, artificial minimization, destructive reduction, or unauthorized state promotion fails closed.

## Empty memory result

An empty search is valid only when the search actually ran and reports zero hits. `UNKNOWN != FALSE`; an empty result is not permission to invent nonexistence.

## Hard-correction behavior

Before the Prime Directive stage passes, unsupported text-only output is replaced with a correction that identifies missing stages. Pre-gate messages containing required retrieval tool calls are allowed while accompanying unsupported prose is removed.

After repeated bypass attempts, the middleware enters a terminal blocked state instead of laundering failure into completion.

## Audit and security

The enforcer records metadata such as event type, timestamp, normalized tool name, and stage status. It does not log model content, prompts, tool arguments, credentials, or restricted source payloads.

## Boundary

This code enforces the contract in execution loops that actually import or execute it. It does not make unrelated software obey a repository file through the mystical power of markdown. A compatible worker must execute the gates and produce the receipts.
