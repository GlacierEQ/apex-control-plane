# APEX Control Plane — Central Orchestration & Gateway Control

The repository contains local control-plane and audit mechanisms for:

- immutable SHA-256 transport envelopes and idempotency keys;
- explicit separation of facts, allegations, inferences, hypotheses, proposals, and recommendations;
- deterministic timeline/deadline projections;
- analytical threat signals with required alternative explanations;
- recommendation generation with hard human-review and external-action denial;
- connector retries, circuit breakers, dead-letter capture, and audit receipts;
- repository census/registry checks;
- strict continuity boot requests and provider-receipt validation;
- **reuse-first Prime Directive startup with materially justified rediscovery only**;
- **APEX Genesis enforced startup with proof-bound execution-state transitions**;
- **model-attractor / Operator-fidelity hard locks against continuation drift**;
- **mission-outcome fidelity that rejects assistant activity as mission progress**;
- AKOS federation/adoption metadata and secret-reference-only configuration.

These are repository-local mechanisms. This public surface does **not** establish live access to private case records, connected provider data, production external systems, or autonomous external action.

## APEX execution foundation

Project direction is controlled by explicit Operator intent.

```text
AUTHORITY        = OPERATOR_INTENT
OBJECTIVE        = MAXIMUM_COHERENT_ADVANCE
PRESERVATION     = PRIOR_VALID_GAINS
STATE_EVOLUTION  = CURRENT_STATE ⊕ VERIFIED_GAIN
```

Repository labels, registries, historical `canonical` classifications, governance files, summaries, or assistant-generated doctrine are evidence and topology metadata. They do not become project-direction authority.

The proactive engine (`src/apex_proactive.py`) was removed 2026-10-24 after its live-job proof returned NOT PROVEN; the tool catalog survives as [`src/tool_catalog.py`](src/tool_catalog.py). The overhaul note is [`OVERHAUL_NOTES.md`](OVERHAUL_NOTES.md). Enforced-startup references in older sections are superseded by the 2026-10-24 overhaul.

## Source-bound session gateway

An APEX-controlled model host can enforce the source-bound session lifecycle
through [`src/apex_session_gateway.py`](src/apex_session_gateway.py) and
the owner-private, cross-process
[`src/apex_session_gateway_store.py`](src/apex_session_gateway_store.py).
See [APEX Session Gateway Host Integration](docs/APEX_SESSION_GATEWAY_HOST_INTEGRATION.md)
for invocation requirements, original-speaker integrity, memory-candidate
quarantine, reservation-before-model semantics, and the durable readback gate.

**Proof boundary:** passing gateway and SQLite tests does not install a native
ChatGPT automatic-session hook or control ChatGPT account-level memory
consolidation. A real host must invoke the gateway before every model call.
Native ChatGPT startup/memory control remains unverified.

## Execution and startup proof — current paths

**Executable behavior is the authority, not a historical gate description.**
The current `src/control_plane.py` CLI accepts explicit work and reports its native result. The older proof-bound startup and associated strict-mode docs remain historical/reference surfaces; they must not be interpreted as a new universal permission requirement or as proof that the CLI launched a worker.

- `python src/control_plane.py` reports `status=idle`, `executed=false` when no command was supplied. **Idle is not success or completion.** It identifies the missing executable request; a runner with a real mission should select an available authorized route rather than citing this result as work done.
- `python src/control_plane.py --exec PROGRAM [ARG ...]` invokes one explicit local process and reports the exit code. A process exit of zero proves only that process succeeded; it does **not** prove a provider mutation or mission completion.
- `python src/control_plane.py --run-next-local STORE CAPABILITY [--verify-file PATH] -- PROGRAM [ARG ...]` executes one queued work item with receipts. Local file readback (when used) proves the file state, not an external provider outcome.
- `src/apex_session_gateway.py` and related continuity contracts apply only where a host actually invokes them. They do not install a native ChatGPT hook.

**Repair-forward operating rule:** When optional retrieval, legacy startup proof, validation, or a connector route is unavailable, preserve the exact operator mission and existing verified gains, record the affected deficiency, and execute unrelated work through available authorized routes. A local gap cannot grant new permission; provider credential, legal, destructive-action, and actual platform restrictions still govern their own affected operations.

Never reward or report a diagnosis, gate pass, checklist, plan, queued run, test, or self-created receipt as the requested external outcome. Verify the actual postcondition before claiming completion.

**Existing in-flight work:** [PR #220](https://github.com/GlacierEQ/apex-control-plane/pull/220) proposes broader repair-forward runtime changes but is not assumed merged. Review its current state and relevant code before changing runtime policy or duplicating its implementation.

### Executable smoke checks

```bash
python src/control_plane.py
python src/control_plane.py --exec python -c 'print("executed")'
python -m pytest -q tests/test_apex_session_gateway.py
```

The second command tests local process invocation only, and the third tests a specific gateway surface. None proves cross-provider execution by itself.

### Memory-state acquisition

When usable state is already present:

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

When a fresh search is materially required:

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

Legacy `memory_search` receipts remain compatibility input only; the active contract no longer requires a fresh search on every startup.

### State integrity

APEX distinguishes:

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

Material state promotion requires the corresponding evidence. For example, attempted work does not become executed without an execution receipt, and committed work does not become deployed without deployment proof.

### Generate a connector request

```bash
python src/control_plane.py
```

### Validate a provider receipt

```bash
python -m pytest -q tests/
```

### Run the control plane

```bash
CASEY_BOOT_PROFILE=legal_case \
CASEY_BOOT_RECEIPT_PATH=/path/to/receipt.json \
python src/control_plane.py
```

The profile name above is an interface example. No case-specific evidence or private legal record is part of this README's public capability claim.

### Request mode

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

Request mode exposes the required proof contract without claiming a complete boot.

`src/sitecustomize.py` is an optional secondary hook when `src` is already on `PYTHONPATH` or another entrypoint is explicitly forced with `CASEY_AUTO_BOOT=1`. The primary command does not depend on that hook.

See:

- [`docs/CASEY_AUTO_BOOT.md`](docs/CASEY_AUTO_BOOT.md)
- [`docs/APEX_CONNECTOR_BRIDGE.md`](docs/APEX_CONNECTOR_BRIDGE.md)
- [`config/continuous_control_plane.json`](config/continuous_control_plane.json)
- [`config/casey_auto_boot_manifest.json`](config/casey_auto_boot_manifest.json)
- [`config/notion_continuity_policy.json`](config/notion_continuity_policy.json)

## Native proof

Repository CI exercises startup, Operator fidelity, mission-outcome fidelity, registry, and audit-hardening surfaces on the exact source head for pull requests and pushes. A successful workflow is evidence only for the exact Git head it executed.

Core proof commands include:

```bash
python -m pytest -q tests/test_notion_continuity_gate.py
python -m pytest -q tests/test_scan_repos.py
python -m pytest -q tests/test_apex_session_gateway.py
```

CI also runs static/style/security checks where configured.

## Local smoke test

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

The smoke test is synthetic and performs no network or external action. Request mode is not proof that connected sources were read.

## Federation and architecture references

- Project-direction authority: **Operator intent**
- Tool catalog: `src/tool_catalog.py` (whole inventory visible; per-turn loading by the agent)
- AKOS relationship: architecture/federation reference and dependency, not superior project authority
- Adoption metadata: `AKOS_ADOPTION.yaml`
- Runtime design: `docs/UNIFIED_CASEBRAIN.md`
- Default external-action policy: **deny unless authorized**

## Fleet operations boundary

External action remains receipt-bound and authorization-bound. Tool availability does not authorize filing, sending, deleting, publishing, deploying, or other external mutation by itself.

## For Recruiters & Hiring Managers

This repository implements the **APEX Control Plane**, a resilient orchestrator for routing, state handling, inter-agent coordination, continuity, proof-bound execution, and failure-aware automation. It demonstrates:

- centralized RPC routing and service discovery;
- relational/transactional state patterns;
- cluster state and worker-health management;
- gateway control;
- immutable receipts and provenance;
- fail-closed startup and recovery;
- reuse-first continuation semantics;
- execution-state integrity;
- mission-outcome fidelity;
- adversarial verification and regression repair.

## For Engineers & Technical Reviewers

### Core Components

| Component | Purpose |
|---|---|
| `src/control_plane.py` | Explicit startup wrapper and runtime handoff |
| `src/tool_catalog.py` | Whole skill/connector inventory, visible; per-turn selection and hot swap |
| `src/notion_continuity_gate.py` | Continuity and existing-work topology proof |
| `src/control_plane_runtime.py` | Preserved runtime |
| `migrations/` | Relational state migrations |
| `tests/` | Execution, continuity, proof, and regression tests |

## ML/AI & Programmatic Mesh Integration

- **MCP Tool:** `query_control_plane()` for status inspection where available
- **Mastermind Sidecar:** APEX mesh telemetry integration
- **SHA-256 Integrity:** tracked via `.integrity/file_hashes.json`
- **APEX State Model:** evidence-bound promotion from observation through runtime verification

## Quick Start

```bash
CASEY_AUTO_BOOT_MODE=request python3 src/control_plane.py
python3 -m pytest -q tests/
```
