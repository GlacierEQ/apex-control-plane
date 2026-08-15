# APEX Control Plane — Central Orchestration & Gateway Control

**Mode:** APEX  
**Human project-direction authority:** Casey Barton  
**Execution law:** `MAXIMUM_COHERENT_ADVANCE`

The APEX Control Plane is GlacierEQ's orchestration, continuity, routing, evidence, and execution-control surface. Its purpose is to make the system stronger in reality: recover source state, preserve Casey's intent and prior gains, compose compatible systems, execute substantial capability, and verify the result without reducing the product to the easiest proof surface.

Read [`APEX_AUTHORITY.md`](APEX_AUTHORITY.md) first. Repositories, manifests, CI, receipts, projections, and model outputs provide state evidence and implementation machinery; they do not outrank Casey's project direction.

## Core mechanisms

The repository contains local control-plane and audit mechanisms for:

- immutable SHA-256 transport envelopes and idempotency keys;
- explicit separation of facts, allegations, inferences, recommendations, and capability-state dimensions;
- deterministic timeline/deadline projections;
- analytical threat signals with required alternative explanations;
- connector retries, circuit breakers, dead-letter capture, and audit receipts;
- repository census/registry checks;
- strict continuity boot requests and provider-receipt validation;
- APEX operator-authority and maximum-coherent-advance enforcement;
- AKOS adoption metadata and secret-reference-only configuration;
- centralized RPC routing and service discovery for agent/worker systems;
- relational cluster-state storage patterns;
- REST/WebSocket gateway patterns;
- Mastermind/APEX mesh integration surfaces.

A public repository surface cannot by itself prove live access to private records, connected memory/provider data, production external systems, or current deployment state. Those are separate state dimensions and require their own receipts.

## APEX state model

Keep these separate:

- `SOURCE_STATE`
- `CURRENT_STATE`
- `TARGET_CAPABILITY`
- `IMPLEMENTED_CAPABILITY`
- `VERIFIED_CAPABILITY`
- `AUTHORIZED_CAPABILITY`
- `DEPLOYED_CAPABILITY`
- `OBSERVED_RESULT`
- `HISTORICAL_STATE`
- `PROJECTION`

A projection may never overwrite the source it projects. A proof limitation limits the claim that proof establishes; it does not silently reduce the target architecture.

## Continuity auto-boot

`python src/control_plane.py` runs the continuity and Prime Directive gates before loading the preserved runtime in `src/control_plane_runtime.py`.

The boot path checks configured requirements such as:

- APEX mode and Casey operator-authority contract;
- required continuity notes and versions;
- current-source receipts;
- repository revision receipts for systems work;
- lane/profile state;
- deadline-check status when a profile requires it;
- restricted-context authorization;
- current task and next material action;
- blocker state;
- provider-backed receipt integrity.

Strict mode is the default. Without a complete required receipt, startup exits with status `78` rather than pretending context or capability was loaded.

Generate a connector request:

```bash
python src/auto_boot.py --profile systems --task "continue" --emit-request
```

Validate a provider receipt:

```bash
python src/auto_boot.py --profile systems --verify-receipt /path/to/receipt.json
```

Run with a validated receipt:

```bash
CASEY_BOOT_PROFILE=systems \
CASEY_BOOT_RECEIPT_PATH=/path/to/receipt.json \
python src/control_plane.py
```

For request inspection without claiming a complete boot:

```bash
CASEY_AUTO_BOOT_MODE=request python src/control_plane.py
```

## Engineering law

APEX does **not** optimize for the smallest possible version. The default is the largest coherent, executable, testable, repairable/reversible, authority-valid capability tranche currently available.

Independent compatible fronts should advance in parallel. Preserve legitimate prior mechanisms. Integrate complementary systems. Expand proof to match built capability. If a capability is not yet verified or externally authorized, keep that state explicit rather than deleting the target.

Small changes remain valid when dependency, risk, rollback, authority, or shared-state constraints make them the correct engineering unit. Smallness itself is not the objective.

## Native proof

Focused tests include the estate registry, audit hardening, APEX continuity boot, operator-authority semantics, and next-agent regression surfaces. Successful CI is evidence for the exact source revision it executed; it is not project-direction authority.

Examples:

```bash
python -m pytest -q tests/test_auto_boot.py
python -m pytest -q tests/test_notion_continuity_gate.py
python -m pytest -q tests/test_apex_authority.py
```

## Security and external action

Security controls should be engineered around legitimate capability using authentication, authorization, isolation, validation, audit, rollback, and explicit boundaries. Capability deletion is not the default safety mechanism.

External action still requires the applicable authority. Tool availability is not, by itself, permission to file, send, publish, purchase, delete, disclose, deploy, or perform another irreversible action.

## Architecture relationships

- APEX authority contract: `APEX_AUTHORITY.md` / `config/apex_authority.json`
- Runtime: `src/control_plane.py` → `src/control_plane_runtime.py`
- Continuity: `config/casey_auto_boot_manifest.json` / `src/auto_boot.py`
- Integration preflight: `config/notion_continuity_policy.json` / `src/notion_continuity_gate.py`
- Prime Directive middleware: `config/prime_directive_policy.json`
- AKOS: architecture/adoption input, not superior human project authority
- Monolith: estate cartography/evidence/projection surface, not authority over Casey's intent

The answer remains `42`; the evidence still needs a source.
