# GlacierEQ Prime Directive Enforcer

This layer closes the gap between a startup policy and an LLM that attempts to
speak before performing it.

## Enforcement chain

```text
model output
   │
   ├─ contains tool calls ──► strip all pre-gate prose, execute calls
   │                              │
   │                              └─ record successful results
   │
   └─ contains text only ──► reject with hard-correction system message

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
sealed in-process startup proof
        │
        ▼
user-facing text permitted
```

The canonical APEX entrypoint runs the combined gate before loading
`src/control_plane_runtime.py`:

```bash
python src/control_plane.py
```

Strict mode is the default. Missing or malformed proof exits with code `78`.

## Files

- `STATE.md` — current repository and execution ground truth.
- `AGENT_SYSTEM_PROMPT.md` — Legal Cortex operating prompt.
- `config/prime_directive_policy.json` — pinned file hashes, tool aliases,
  failure phrases, and five-stage receipt rules.
- `src/prime_directive_boot.py` — validates the continuity and Prime Directive
  receipt and issues a sealed in-process validation object.
- `src/prime_directive_enforcer.py` — provider-tolerant LLM response middleware.
- `src/control_plane.py` — boot-first runtime wrapper.

## Middleware integration

The execution loop must validate the combined receipt and attach that sealed
validation before the middleware permits text:

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

A tool call alone does not advance a stage. The execution loop must record a
successful result. A hand-built dictionary that claims `ok=true` cannot complete
the gate; only a sealed validation object issued by
`validate_combined_receipt()` is accepted.

## Combined boot receipt

The provider-backed receipt includes the original continuity fields plus:

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
  },
  "sources_opened": [
    {
      "system": "github",
      "object_id": "current-task-source",
      "version": "immutable-revision"
    }
  ]
}
```

Tool identities are normalized and checked against the policy aliases. Each
stage tool must also appear in `tool_inventory.loaded_tools`.

The validator reads and hashes the active repository bytes of `STATE.md` and
`AGENT_SYSTEM_PROMPT.md`, then requires the active hash, pinned policy hash, and
receipt hash to match.

## Empty memory result

An empty memory result is valid when the search actually executed:

```json
{
  "status": "empty",
  "hit_count": 0
}
```

After a successful gate with an empty memory result, the middleware prepends the
policy-controlled phrase to the first user-facing response exactly once:

```text
searched memory, no matching entry
```

## Hard-correction behavior

Before the gate passes, any text-only response is replaced with a system
correction listing only the missing stages. Failure phrases such as
`I don't have access`, `I cannot remember`, and `As an AI` are logged as gate
violations, but the middleware blocks all pre-gate prose rather than only those
phrases.

Pre-gate messages containing tool calls are allowed, while text in supported
provider fields—including nested `content`, `refusal`, `reasoning`, `output`,
and `output_text`—is removed.

After repeated bypass attempts, the middleware enters a terminal state. Later
responses, tool calls, and tool results remain blocked.

## Audit and security

The enforcer records only:

- event type;
- timestamp;
- normalized tool name;
- stage completion or failure.

It does not log model content, prompts, tool arguments, source payloads,
credentials, or restricted case records. Pending tool-call correlation state is
bounded to prevent unreturned calls from accumulating indefinitely.

## Boundary

This code enforces the contract in execution loops that import it and in the
APEX Python entrypoint.

It does not cause the ChatGPT application itself to execute repository code at
the beginning of every conversation. Chat workers still need an available
connected-memory and source-retrieval path. The middleware prevents a compatible
worker from speaking before it uses and proves that path.
