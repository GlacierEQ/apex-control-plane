# Jack the Ripper — APEX Relentless Execution Binding

This package is the executable/machine-readable adversarial execution layer for APEX. It attacks false completion, continuity loss, objective dilution, under-recovery, and scope minimization while remaining subordinate to Casey Barton's project direction and concrete law/safety/permission boundaries.

## Binding surfaces

- `config/jack_relentless_contract.yaml` — APEX execution contract source.
- `config/jack_relentless_contract.compiled.json` — dependency-free compiled gate manifest.
- `glaciereq/jack/v1/jack_relentless_contract.proto` — typed receipt and fixed gate-vector wire contract.
- `odin/jack_relentless_gate.odin` — native fail-closed evaluator.
- `src/jack_relentless_gate.py` — Python runtime evaluator for `apex-control-plane`.
- `models/jack_relentless_gate.onnx` — deterministic readiness graph:
  - `execution_ready = AND(8 preflight gates, NOT(current_blocker_present))`
  - `completion_ready = AND(all 16 gates, NOT(current_blocker_present))`
  - `resume_ready = AND(5 persistence/continuity gates)`
- `models/jack_relentless_gate.onnx.b64` — GitHub-safe exact binary representation.
- `tools/materialize_jack_onnx.py` — recreates the ONNX binary and verifies SHA-256.
- `tests/test_jack_relentless_gate.py` — fail-closed APEX regression tests.

## APEX law

**Human project-direction authority:** Casey Barton  
**Execution law:** `MAXIMUM_COHERENT_ADVANCE`

The gate does not resolve a stored repository/document owner and then place that owner above the operator. It requires:

- operator authority loaded;
- exact objective preserved;
- strongest source and legitimate prior state checked;
- required sources opened;
- conflicts preserved instead of silently flattened;
- maximum coherent advance selected;
- material execution, verification, persistence, and readback.

A source conflict is evidence to reconcile against Casey's objective. It is not automatic authority to stop progress or redefine the target downward.

## Contract law

A zero on any required gate prevents the corresponding readiness output from becoming `1.0`. There is no weighted score and no partial-credit path to `COMPLETE`.

Status is fail-closed: `RECOVERING` until preflight is ready, `EXECUTING` only after all preflight gates pass, `BLOCKED` only with an exact blocker, and `COMPLETE` only after all 16 gates pass. Receipts use a fixed 16-field gate vector and are rejected when their status contradicts their gates. A current exact blocker takes precedence over completion.

The 16-gate shape remains compatible with the deterministic ONNX readiness topology, while gate meanings are now APEX-native: stored-owner resolution was replaced by operator-authority loading, prior-state recovery, and maximum-coherent-advance selection.

ONNX SHA-256: `5602367fb172d7457c9cc7dc57e87e6aa765e8bc53cfbe8662468c5ad91d338b`

## Operational interpretation

Jack attacks execution failure, arguments, contradictions, source gaps, artificial smallness, and broken workflows. It does not authorize violence, threats, unlawful access, unauthorized external actions, fabrication, or treating a repository/projection/model output as superior project-direction authority.
