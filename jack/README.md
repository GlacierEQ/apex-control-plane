# Jack the Ripper — Relentless Execution Binding

This package is an executable/machine-readable extension of the existing GlacierEQ continuity and Jack architecture.

## Binding surfaces

- `config/jack_relentless_contract.yaml` — canonical human/machine policy.
- `config/jack_relentless_contract.compiled.json` — dependency-free compiled gate manifest.
- `glaciereq/jack/v1/jack_relentless_contract.proto` — package-aligned typed receipt and fixed gate-vector wire contract.
- `odin/jack_relentless_gate.odin` — native fail-closed evaluator.
- `src/jack_relentless_gate.py` — Python runtime evaluator for `apex-control-plane`.
- `models/jack_relentless_gate.onnx` — deterministic ONNX graph:
  - `execution_ready = AND(8 preflight gates, NOT(current_blocker_present))`
  - `completion_ready = AND(all 16 gates, NOT(current_blocker_present))`
  - `resume_ready = AND(5 persistence/continuity gates)`
- `models/jack_relentless_gate.onnx.b64` — GitHub-safe exact binary representation.
- `tools/materialize_jack_onnx.py` — recreates the ONNX binary and verifies SHA-256.
- `tests/test_jack_relentless_gate.py` — fail-closed regression tests.

## Contract law

A zero on any required gate prevents the corresponding readiness output from becoming `1.0`.
There is no weighted score and no partial-credit path to `COMPLETE`.

Status is fail-closed: `RECOVERING` until preflight is ready, `EXECUTING` only after all preflight gates pass, `BLOCKED` only with an exact blocker, and `COMPLETE` only after all 16 gates pass. Receipts use a fixed 16-field gate vector and are rejected when their status contradicts their gates. A current exact blocker takes precedence over completion.

ONNX SHA-256: `5602367fb172d7457c9cc7dc57e87e6aa765e8bc53cfbe8662468c5ad91d338b`

## Operational interpretation

Jack attacks execution failure, arguments, contradictions, source gaps, and broken workflows.
The contract does not authorize violence, threats, unlawful access, unauthorized external actions, or fabrication.


## Casebuilder / Allegation Forge plane

Jack now has a second executable plane for case construction. It does not replace
the relentless execution gate and it does not absorb the specialist systems.

Distributed topology:

- `GlacierEQ/Casebuilder4000` — evidence-driven forge engine.
- `GlacierEQ/apex-legal-case` — live case corpus and case-domain state.
- `GlacierEQ/computer-user` — source acquisition and connector execution plane.
- `GlacierEQ/legal-powerhouse` — downstream litigation artifact runtime.
- `GlacierEQ/apex-control-plane` — Jack orchestration and receipt verification.

`src/casebuilder_forge.py` binds this topology through
`casebuilder4000.build-receipt.v2`. A Casebuilder build can become a Jack
`VERIFIED` action only after exact artifact readback matches the receipt's
SHA-256 and byte-size manifest and the case-state object counts agree with the
receipt.

A packet, bootstrap, generated report, or structurally valid receipt is not an
executed build. A verified build is not a representation that the case itself
is complete.

The forge preserves these distinctions:

```text
SOURCE -> FACT -> EVENT -> ACTOR
       -> ALLEGATION -> ELEMENT
       -> CONTRADICTION -> KNOWLEDGE
       -> DAMAGE -> DEFENSE -> DISCOVERY
       -> ACCOUNTABILITY -> CROSS-EXAM
       -> PLEADING / MOTION / REFERRAL CONVERSION
```

Killed and quarantined allegations remain visible in audit state but cannot
silently re-enter pressure or promotion. Derived chat/history material cannot
self-promote into primary/native proof merely because it was routed through the
case graph.

The binding contract is
`config/casebuilder_forge_contract.json`; adversarial proof lives in
`tests/test_casebuilder_forge.py`.
