# Jack the Ripper — Relentless Execution Binding

This package is an executable/machine-readable extension of the existing GlacierEQ continuity and Jack architecture.

## Binding surfaces

- `config/jack_relentless_contract.yaml` — canonical human/machine policy.
- `config/jack_relentless_contract.compiled.json` — dependency-free compiled gate manifest.
- `proto/glaciereq/jack/v1/jack_relentless_contract.proto` — package-aligned typed receipt and fixed gate-vector wire contract.
- `odin/jack_relentless_gate.odin` — native fail-closed evaluator.
- `src/jack_relentless_gate.py` — Python runtime evaluator for `apex-control-plane`.
- `models/jack_relentless_gate.onnx` — deterministic ONNX graph:
  - `execution_ready = Min(8 preflight gates + current_blocker_clear)`
  - `completion_ready = Min(all 16 gates + current_blocker_clear)`
  - `resume_ready = Min(5 persistence/continuity gates)`
- `models/jack_relentless_gate.onnx.b64` — GitHub-safe exact binary representation.
- `tools/materialize_jack_onnx.py` — recreates the ONNX binary and verifies SHA-256.
- `tests/test_jack_relentless_gate.py` — fail-closed regression tests.

## Contract law

A zero on any required gate prevents the corresponding readiness output from becoming `1.0`.
There is no weighted score and no partial-credit path to `COMPLETE`.

Status is fail-closed: `RECOVERING` until preflight is ready, `EXECUTING` only after all preflight gates pass, `BLOCKED` only with an exact blocker, and `COMPLETE` only after all 16 gates pass. Receipts use a fixed 16-field gate vector and are rejected when their status contradicts their gates. A current exact blocker takes precedence over completion.

ONNX SHA-256: `a30920efe9e9cf930d90ce120511ef9b30547dbaaf624bc3fe1628aade1e1618`

## Operational interpretation

Jack attacks execution failure, arguments, contradictions, source gaps, and broken workflows.
The contract does not authorize violence, threats, unlawful access, unauthorized external actions, or fabrication.
