# Hierarchical Epistemology — APEX Control Kernel v1.1

## Purpose

This kernel preserves typed epistemic state, receipt-bound execution truth, strategy selection, contradiction visibility, progress semantics, and correction memory without turning heuristics into global execution ceilings.

The hierarchy remains:

```text
MISSION
  ↓
AUTHORITY
  ↓
CLAIM
  ↓
EVIDENCE
  ↓
STRATEGY
  ↓
EXECUTION
  ↓
VERIFICATION
  ↓
LEARNING
```

A lower layer cannot silently rewrite a higher layer. Tool output cannot redefine the mission; generated artifacts cannot become executed or verified without provider/path receipts; successful runs do not erase contradictions; failure may change routing but does not authorize scope loss.

## Claim-state truth

Material execution state is explicitly typed:

```text
UNKNOWN / OBSERVED / INFERRED / HYPOTHESIZED / PROPOSED
→ ATTEMPTED
→ EXECUTED
→ VERIFIED
→ COMMITTED
→ DEPLOYED
→ OBSERVED_IN_OPERATION
```

Transitions across execution states require the corresponding receipt. Action narration is never a receipt.

## Strategy selection

The kernel can select ReAct, Plan-and-Execute, Reflection, Tree-of-Thoughts, Reflexion, or Debate based on the task. Strategy choice is guidance, not authority over the Operator's mission.

Resource depth is `adaptive_evidence_driven`. There are no fixed global worker ceilings, retrieval ceilings, or hard-stop rules. Low marginal signal causes rerouting; unresolved conflicts remain visible and route to investigation; verification of one target does not imply the whole mission is complete.

## Progress law

```text
forward_progress = (target_state_changed OR evidence_added) AND NOT artifact_only
```

Reports and plans are useful only insofar as they change target state or add source-bearing evidence.

## Holographic mesh rule

The estate grows through merge, transcription, and compounding.

- `latest` is a routing cursor, not replacement authority.
- Older nodes remain active while they retain unique source, mechanism, contradiction, provenance, dependency, receipt, or authority-domain state.
- Partial overlap receives explicit relationship semantics instead of global supersession.
- Retirement requires unique-contribution recovery, merge/transcription of every still-valid contribution, provider readback, and verified `UNIQUE_CONTRIBUTION=0`.
- Lineage pointers survive retirement.

## Self-correction

A correction preserves:

```text
failure
→ failed assumption
→ objective-function change
→ known-good state
→ changed method/routing
→ verification
→ learning
```

Retry policy is adaptive. A failed method can be replaced; the mission and valid prior state are not silently discarded.

## Integration surface

```text
src/hierarchical_epistemology.py
config/hierarchical_epistemology_policy.json
tests/test_hierarchical_epistemology.py
```

The donor remains an explicit lineage node until these contributions are merged into the surviving execution graph and verified by readback.
