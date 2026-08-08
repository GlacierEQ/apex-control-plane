# Casey Continuity Auto-Boot

The APEX control plane has a deterministic, fail-closed startup gate for
ephemeral workers that cannot safely assume they remember prior chats, project
state, repository decisions, deadlines, tools, source state, or where current
work belongs.

The gate now combines three contracts:

1. **Notion-first continuity/integration proof** — the worker must search and
   fetch the canonical Notion continuity authorities, recover identity,
   expectations, capabilities, and current state, determine whether the task is
   already started, resolve one canonical owner, and map owner/consumer/
   dependency/overlap relationships before creating or executing new work.
2. **Continuity proof** — exact Mem notes and versions, current sources,
   repository receipts, lanes, deadlines, task context, and blocker state.
3. **Prime Directive proof** — an executed memory search, hash-verified
   `STATE.md` and `AGENT_SYSTEM_PROMPT.md`, and a structured inventory of tools
   actually loaded in the current worker.

The new preflight extends the existing auto-boot architecture. It does not
replace the Mem continuity gate or Prime Directive middleware.

## Canonical startup

```bash
python src/control_plane.py
```

`src/control_plane.py` calls `automatic_notion_continuity_preflight()` first,
then `automatic_prime_directive_boot()`, and only then loads
`src/control_plane_runtime.py`.

Strict mode is the default. A missing, stale, malformed, conflicting, or blocked
receipt causes exit status `78` before runtime load.

## Mandatory startup order

```text
Notion continuity search/fetch
  -> recover identity + expectations + capabilities + current state
  -> search whether the requested work already exists
  -> resolve one canonical owner
  -> discover consumers + dependencies + overlaps
  -> produce integration/link plan
  -> existing Mem continuity + source proof
  -> Prime Directive + tool + ground-truth proof
  -> runtime
```

The governing laws are in `config/notion_continuity_policy.json`:

- **NOTION BEFORE SPEECH.**
- **Before STARTING, determine whether it is already STARTED.**
- **Resume and extend the canonical owner before creating.**
- **Before MAKING, discover who needs, owns, consumes, depends on, or overlaps
  with it.**
- **Add and link before fragmenting.**
- **Unresolved canonical conflicts block creation.**
- **New roots are a last resort.**

## Canonical Notion wake set

The Notion preflight requires the existing canonical pages by exact ID and role;
it does not create another continuity hub:

- SuperNova Continuity Ledger — cross-session current state;
- NOVA-001 — identity, expectations, and capability architecture;
- SKILL 5 — Memory & Continuity Engineering — continuity method;
- Notion Workspace Connector — Notion governance and routing doctrine;
- H20 Holographic Continuity Index — rolling chat/project continuity index.

The policy stores identifiers, roles, and proof metadata only. It does not put
private page payloads into source control or boot receipts.

## Pre-start and integration receipt

A compatible worker proves the Notion-first stages in the same boot receipt.
The important shape is:

```json
{
  "notion_boot_analysis": {
    "search_tool": "Notion.search",
    "fetch_tool": "Notion.fetch",
    "status": "complete",
    "query": "current task plus continuity and active-build terms",
    "pages_loaded": [
      {
        "id": "<canonical-notion-page-id>",
        "role": "<canonical-role>",
        "source": "Notion.fetch:<canonical-notion-page-id>"
      }
    ],
    "identity_loaded": true,
    "expectations_loaded": true,
    "capabilities_loaded": true,
    "current_state_loaded": true,
    "canonical_conflicts": []
  },
  "existing_work_discovery": {
    "tool": "GitHub.search",
    "status": "found",
    "query": "current requested capability and likely canonical owner",
    "systems_searched": ["Notion", "GitHub"],
    "candidates": [
      {
        "system": "GitHub",
        "id": "owner/repository",
        "relationship": "canonical_owner"
      }
    ],
    "canonical_owner": {
      "system": "GitHub",
      "id": "owner/repository",
      "kind": "repository"
    },
    "canonical_conflicts": [],
    "decision": "extend"
  },
  "integration_map": {
    "status": "complete",
    "need_search_performed": true,
    "searched_relationships": ["owner", "consumer", "dependency", "overlap"],
    "owner": {
      "system": "GitHub",
      "id": "owner/repository",
      "kind": "repository"
    },
    "consumers": [],
    "dependencies": [],
    "related_nodes": [],
    "link_plan": ["extend the canonical owner through its existing interface"],
    "decision": "integrate",
    "create_new_root": false,
    "abandon_existing": false
  }
}
```

If existing work is found, `decision=extend` and `create_new_root=false` are
mandatory. If no direct owner is found but a consumer, dependency, or related
node exists, the work must still integrate there. Standalone creation is valid
only after the search proves no owner or relationship and records a specific
justification.

## Modes

### Strict

```bash
CASEY_AUTO_BOOT_MODE=strict python src/control_plane.py
```

### Request

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

Request mode emits the Notion continuity preflight plus the existing combined
boot request and continues only as degraded:

```text
GLACIEREQ_NOTION_CONTINUITY_GATE_STATUS=degraded
CASEY_BOOT_STATUS=degraded
GLACIEREQ_PRIME_DIRECTIVE_GATE_STATUS=degraded
```

It is for connector-bridge development and local inspection. It is not proof of
current awareness or continuity.

### Off

```bash
CASEY_AUTO_BOOT_MODE=off python src/control_plane.py
```

or:

```bash
CASEY_AUTO_BOOT_DISABLE=1 python src/control_plane.py
```

A disabled run cannot claim continuity, Notion preflight completion, or Prime
Directive completion.

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

The existing Mem continuity manifest remains
`config/casey_auto_boot_manifest.json`. The Notion-first extension is
`config/notion_continuity_policy.json`. Neither replaces the other.

## Ground truth

Every Prime Directive startup reads and verifies:

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

The existing continuity portion proves exact note versions, current sources,
repository revisions where required, current task/next action, lane/deadline
state where applicable, restricted-context state, and an empty blocker list.

The Prime Directive portion proves the executed memory search, loaded tool
inventory, and hash-bound ground-truth reads. An empty memory result is valid
only when the search actually ran and reports `status=empty` with `hit_count=0`.

## Base request and receipt validation

The original continuity request remains available:

```bash
python src/auto_boot.py \
  --profile legal_case \
  --task "continue the highest-value unfinished material action" \
  --emit-request
```

The canonical control-plane entrypoint adds the Notion continuity/integration
preflight in front of the existing combined Prime Directive validator. See
`docs/PRIME_DIRECTIVE_ENFORCER.md` for the pre-text middleware.

## Response middleware

`src/prime_directive_enforcer.py` blocks model text before startup completion.
The canonical entrypoint now runs the Notion preflight before reaching that
existing Prime Directive gate.

- Tool calls are allowed through.
- Any accompanying pre-gate prose is removed by compatible middleware.
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

`src/sitecustomize.py` now invokes the same Notion-first preflight before the
existing Prime Directive boot. The explicit `src/control_plane.py` wrapper
remains the canonical enforcement path.

## Security

No credentials, restricted source payloads, sealed records, or original child
or medical records belong in the repository, policy, or boot receipt.

The restricted-child profile requires explicit authorization and remains
excluded from portable projections. The Notion preflight records page IDs,
roles, search proof, ownership relationships, and link plans—not private page
content.

## Boundary

This implementation proves the startup contract in execution loops that import
it and in the APEX Python entrypoint.

It does not cause the ChatGPT application itself to execute repository code at
the start of every UI conversation. A compatible chat worker must still invoke
the connected Notion, memory, and source tools. The executable gate exists so
workers that integrate this control plane fail closed rather than pretending
that a cold start has continuity.
