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

The enforced startup contract is [`APEX_ENFORCED_STARTUP.md`](APEX_ENFORCED_STARTUP.md).

## Enforced startup

`python src/control_plane.py` is the explicit fail-closed wrapper. The composed startup/strong-boot path protects the preserved runtime in `src/control_plane_runtime.py` with these proof boundaries:

1. **Known-state / continuity preflight** — consult relevant already-known state, reuse provenance-bearing state where usable, resolve the nearest valid continuation, map owners/consumers/dependencies/overlaps where material, and preserve valid prior capability.
2. **Prime Directive memory-state proof** — satisfy memory acquisition either by provenance-bearing reuse or by a materially justified search; hash-bind pinned ground-truth reads; prove tool inventory, current-source requirements, and provider-backed receipt validation.
3. **APEX Genesis + Operator fidelity** — bind literal Operator intent and operation class, continuation, target state, prior valid gains, contradiction status, execution-state model, maximum coherent path, and verification plan.
4. **Model-attractor defense** — fail closed on `CONTINUE -> RECONSTRUCT`, known-state rediscovery, mission/support substitution, and related continuity drift.
5. **Mission-outcome fidelity** — mutation work cannot persist merely because the assistant produced a ledger, matrix, summary, report, plan, commit, task update, or other artifact; it must prove an underlying source-bearing mission-state transition or an evidenced genuine external boundary after materially available internal routes are exhausted.

Strict mode is the default. Without complete provider-backed proof, startup exits with status `78` rather than pretending context or execution state exists.

**Rediscovery of already-known relevant Operator/project state is not progress.**

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
python src/auto_boot.py --profile legal_case --task "continue" --emit-request
```

### Validate a provider receipt

```bash
python src/auto_boot.py --profile legal_case --verify-receipt /path/to/receipt.json
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

- [`APEX_ENFORCED_STARTUP.md`](APEX_ENFORCED_STARTUP.md)
- [`docs/CASEY_AUTO_BOOT.md`](docs/CASEY_AUTO_BOOT.md)
- [`docs/PRIME_DIRECTIVE_ENFORCER.md`](docs/PRIME_DIRECTIVE_ENFORCER.md)
- [`docs/APEX_CONNECTOR_BRIDGE.md`](docs/APEX_CONNECTOR_BRIDGE.md)
- [`config/apex_enforced_startup_policy.json`](config/apex_enforced_startup_policy.json)
- [`config/casey_auto_boot_manifest.json`](config/casey_auto_boot_manifest.json)
- [`config/notion_continuity_policy.json`](config/notion_continuity_policy.json)
- [`config/prime_directive_policy.json`](config/prime_directive_policy.json)
- [`config/outcome_fidelity_policy.json`](config/outcome_fidelity_policy.json)

## Native proof

Repository CI exercises startup, Operator fidelity, mission-outcome fidelity, registry, and audit-hardening surfaces on the exact source head for pull requests and pushes. A successful workflow is evidence only for the exact Git head it executed.

Core proof commands include:

```bash
python -m pytest -q tests/test_apex_enforced_startup.py
python -m pytest -q tests/test_notion_continuity_gate.py
python -m pytest -q tests/test_prime_directive_boot.py
python -m pytest -q tests/test_prime_directive_enforcer.py
python -m pytest -q tests/test_apex_strong_boot.py
python -m pytest -q tests/test_outcome_fidelity_runtime.py
python -m pytest -q tests/test_scan_repos.py
python -m pytest -q tests/test_audit_hardening.py
```

CI also runs static/style/security checks where configured.

## Local smoke test

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

The smoke test is synthetic and performs no network or external action. Request mode is not proof that connected sources were read.

## Federation and architecture references

- Project-direction authority: **Operator intent**
- APEX startup law: `APEX_ENFORCED_STARTUP.md`
- Operator execution law: `OPERATOR_EXECUTION_LAW.md`
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
| `src/apex_enforced_startup.py` | APEX Genesis startup + state-transition enforcement |
| `src/notion_continuity_gate.py` | Continuity and existing-work topology proof |
| `src/prime_directive_boot.py` | Reuse/search-aware provider-backed startup receipt validation |
| `src/prime_directive_enforcer.py` | Pre-gate response middleware with monotonic known-state reuse |
| `src/apex_strong_boot.py` | Strong-boot composition |
| `src/outcome_fidelity_runtime.py` | Mission-outcome postcondition hard lock |
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
python3 -m pytest -q tests/test_apex_enforced_startup.py
```

## Jack Casebuilder / Allegation Forge

The Jack legal case-construction subsystem is implemented in `src/jack_casebuilder.py` with its machine contract at `config/jack_casebuilder_contract.json` and architecture at `docs/JACK_CASEBUILDER_ALLEGATION_FORGE.md`. It adds stable case-graph objects, occurrence-first Doe actors, element mapping, proof-bound allegation promotion, pressure mapping, and SHA-256 state receipts without collapsing allegations into verified facts.

