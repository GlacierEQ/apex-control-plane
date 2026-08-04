# Casey Continuity Auto-Boot

The APEX control plane has a deterministic, fail-closed startup gate for
ephemeral workers that cannot safely assume they remember prior chats, case
runs, repository decisions, deadlines, tools, or source state.

The gate now combines two contracts:

1. **Continuity proof** — exact Mem notes and versions, current sources,
   repository receipts, lanes, deadlines, task context, and blocker state.
2. **Prime Directive proof** — an executed memory search, hash-verified
   `STATE.md` and `AGENT_SYSTEM_PROMPT.md`, and a structured inventory of tools
   actually loaded in the current worker.

## Canonical startup

```bash
python src/control_plane.py
```

`src/control_plane.py` calls `automatic_prime_directive_boot()` before loading
`src/control_plane_runtime.py`.

Strict mode is the default. A missing, stale, malformed, or blocked receipt
causes exit status `78` before runtime load.

## Modes

### Strict

```bash
CASEY_AUTO_BOOT_MODE=strict python src/control_plane.py
```

### Request

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

Request mode emits the complete combined JSON request and continues only as:

```text
CASEY_BOOT_STATUS=degraded
GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS=degraded
```

It is for connector-bridge development and local inspection. It is not proof of
current awareness.

### Off

```bash
CASEY_AUTO_BOOT_MODE=off python src/control_plane.py
```

or:

```bash
CASEY_AUTO_BOOT_DISABLE=1 python src/control_plane.py
```

A disabled run cannot claim continuity or Prime Directive completion.

## Profiles

```bash
CASEY_BOOT_PROFILE=legal_case python src/control_plane.py
CASEY_BOOT_PROFILE=systems python src/control_plane.py
CASEY_BOOT_PROFILE=legal_case,restricted_child \
CASEY_RESTRICTED_CONTEXT_AUTHORIZED=1 \
python src/control_plane.py
```

Available profiles:

- `always`
- `legal_case`
- `restricted_child`
- `systems`
- `separate_matter`

The manifest is `config/casey_auto_boot_manifest.json`. The canonical Mem
collection is `e9990f2e-affe-55b2-a402-1de35aeb1b73`; its canonical manifest
note is `6925915b-33d6-5fc9-b499-4fbe78790413`.

## Ground truth

Every startup reads and verifies:

- `STATE.md`
- `AGENT_SYSTEM_PROMPT.md`

Their exact SHA-256 values are pinned in
`config/prime_directive_policy.json`. A mismatched file does not complete the
startup stage.

## Combined receipt

Supply one receipt as a file path:

```bash
CASEY_BOOT_RECEIPT_PATH=/secure/runtime/boot-receipt.json \
CASEY_BOOT_PROFILE=legal_case \
python src/control_plane.py
```

or as inline JSON:

```bash
CASEY_BOOT_RECEIPT_JSON="$(< /secure/runtime/boot-receipt.json)" \
CASEY_BOOT_PROFILE=legal_case \
python src/control_plane.py
```

The continuity portion proves:

- exact boot-manifest ID and version;
- exact Mem collection ID;
- all required note IDs and pinned versions;
- structured current-source rows;
- repository revision receipts for systems work;
- `case_lane` or `matter_lane` as required;
- current deadline state for legal work;
- boolean restricted-context state;
- current task and next material action;
- `boot_status=complete`;
- an empty blocker array.

The Prime Directive portion proves:

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
    "loaded_tools": ["personal_context.search", "GitHub.fetch_file"],
    "gaps": []
  }
}
```

An empty memory result is valid when the search actually ran and reports
`status=empty` with `hit_count=0`.

## Base request and receipt validation

The original continuity request remains available:

```bash
python src/auto_boot.py \
  --profile legal_case \
  --task "continue the highest-value unfinished 1FDV artifact" \
  --emit-request
```

The canonical control-plane entrypoint uses the combined Prime Directive
request and validator. See `docs/PRIME_DIRECTIVE_ENFORCER.md`.

## Response middleware

`src/prime_directive_enforcer.py` blocks model text before startup completion.

- Tool calls are allowed through.
- Any accompanying pre-gate prose is removed.
- A stage advances only after a successful tool result.
- Text-only pre-gate output is replaced by a hard-correction system message.
- Repeated bypass attempts produce a terminal startup block rather than an
  infinite loop.

## Optional site hook

For another Python entrypoint with `src` already on `PYTHONPATH`:

```bash
PYTHONPATH=src \
CASEY_AUTO_BOOT=1 \
CASEY_AUTO_BOOT_MODE=request \
python another_entrypoint.py
```

The explicit `src/control_plane.py` wrapper remains the canonical enforcement
path.

## Security

No credentials, restricted source payloads, sealed records, or original child
or medical records belong in the repository, policy, or boot receipt.

The restricted-child profile requires explicit authorization and remains
excluded from portable projections.

## Boundary

This implementation proves the startup contract in execution loops that import
it and in the APEX Python entrypoint.

It does not cause the ChatGPT application to execute repository code at the
start of every UI conversation. A compatible chat worker must still invoke the
connected memory and source tools; the middleware prevents that worker from
speaking before it does.
