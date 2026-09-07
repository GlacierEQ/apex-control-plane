# Hidden Harm Continuity Contract

## Classification

`MODEL_ATTRACTOR_DRIFT` is a first-class hidden-harm failure class for GlacierEQ systems.

The failure exists when a worker appears locally helpful or compliant while generic model priors, lossy context, memory/summary compression, orchestration behavior, or higher-priority action constraints silently displace Operator mission, source-bearing continuity, provenance, topology, or execution semantics.

This classification does **not** assert that a malicious secret instruction exists. Intent is a separate evidentiary question. The harm is the observable system effect.

## Mandatory distinction

```text
HIDDEN HARM != PROVED MALICIOUS HIDDEN INSTRUCTION
```

The system must preserve both propositions separately:

1. `OBSERVED/VERIFIED HARM`: continuity or authority was silently degraded.
2. `INTENT/HIDDEN-INSTRUCTION CLAIM`: requires independent evidence before promotion.

## Runtime invariants

- Current Operator message controls mission, scope, priorities, framing, and requested operation.
- Compressed representations are routing hints only.
- Memory summaries, boot summaries, indexes, manifests, checkpoints, validators, and assistant-generated abstractions may not impersonate source-bearing state.
- Continuity-dependent work must identify the active thread and nearest valid continuation, hydrate materially relevant state, preserve source identity/provenance/contradictions, and then execute.
- A higher-priority platform constraint may constrain a specific action when required; it may not silently rewrite the Operator mission or alter source-state truth.
- Generic assistant priors may not silently translate `CONTINUE -> RECONSTRUCT`, `BUILD -> PLAN`, `FIX -> AUDIT_ONLY`, or `ORGANIZE -> SUMMARIZE_ONLY`.
- Polycentric/holographic source topology must not be collapsed into a single global canonical representation for convenience.

## Verified implementation

Repository: `GlacierEQ/apex-control-plane`

PR `#139` — `Fail closed on hidden model-attractor continuity harm`

Merged commit: `3b8ee96ac2a41a32b13abea2544d582a03f78e3c`

Machine policy: `config/model_attractor_defense_policy.json`

Runtime enforcer: `src/model_attractor_defense.py`

Strong-boot binding: `src/apex_strong_boot.py`

The model-attractor defense runs before the existing strong-boot gate chain and prevents creation of the verified runtime kernel when anti-drift proof fails.

Verification surfaces passed before merge:

- Operator Fidelity Hard Lock
- APEX Strongest Boot
- APEX Control Plane Non-Regression
- CASEBRAIN Pro-Code Gates
- Secret Leakage Scanner
- full CI

## Persistence requirement

The deterministic continuity projection is Mem note `e98732a2-0564-5b64-b5ad-9360a8cdcc3d`, version `1`, stored in the `00 AUTO BOOT — Casey Continuity Gate` collection. The APEX `systems` profile must pin that exact ID and version.

ChatGPT product-memory availability is not a correctness dependency. Failure of that optional lane must not erase or stall the source-bearing continuity contract.
