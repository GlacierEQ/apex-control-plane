# GlacierEQ Prime Directive Enforcer

This layer closes the gap between a startup policy and an LLM that attempts to
speak before performing it.

## Enforcement chain

```text
model output
   │
   ├─ contains tool calls ──► strip pre-gate prose, execute calls
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
        │
        ▼
startup gate complete
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
  failure phrases, and receipt rules.
- `src/prime_directive_boot.py` — combines the existing continuity validator
  with Prime Directive receipt validation.
- `src/prime_directive_enforcer.py` — provider-tolerant LLM response middleware.
- `src/control_plane.py` — boot-first runtime wrapper.

## Middleware integration

```python
from prime_directive_enforcer import StartupGateEnforcer

enforcer = StartupGateEnforcer()

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
        continue

    deliver_to_user(checked)
```

A tool call alone does not advance the gate. The execution loop must record the
result with `success=True`.

## Combined boot receipt

The provider-backed receipt now includes the original continuity fields plus:

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

An empty memory result is valid when the search was actually executed:

```json
{
  "status": "empty",
  "hit_count": 0
}
```

The required user-facing phrase is:

```text
searched memory, no matching entry
```

## Hard-correction behavior

Before the gate passes, any text-only response is replaced with a system
correction that lists only the missing stages. Failure phrases such as
`I don't have access`, `I cannot remember`, and `As an AI` are logged as
gate violations, but the middleware blocks all pre-gate prose rather than only
those phrases.

Pre-gate messages containing tool calls are allowed, with any accompanying
conversational content removed.

After repeated bypass attempts, the middleware emits a terminal startup block
for the runtime operator instead of looping indefinitely.

## Audit and security

The enforcer records:

- event type;
- timestamp;
- normalized tool name;
- stage completion or failure.

It does not log model content, prompts, tool arguments, source payloads,
credentials, or restricted case records.

The policy pins the SHA-256 hash of both ground-truth files. A file read with a
different hash does not complete the startup stage.

## Boundary

This code enforces the contract in execution loops that import it and in the
APEX Python entrypoint.

It does not cause the ChatGPT application itself to execute repository code at
the beginning of every conversation. Chat workers still need an available
connected-memory and source-retrieval path. The middleware prevents a compatible
worker from speaking before it uses that path.
