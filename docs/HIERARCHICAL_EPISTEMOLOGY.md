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


## Durable operator-correction feedback (optional runtime binding)

The existing `AdaptiveIntelligenceEngine` remains an auditable, local learning
component. When a model host or APEX worker supplies a persistent
`model_state_path`, operator-correction and verified-outcome rewards change the
ranker, atomically checkpoint those weights, and are automatically rehydrated by
another worker process. A lock serializes competing workers and each writer
rebases on the latest on-disk state. Corrupted checkpoints raise rather than
silently replacing learned corrections with default ranking.

```python
from src.continuous_impact_selection import ContinuousImpactSelector

selector = ContinuousImpactSelector(model_state_path="/secured/apex/learning-state.json")
decision = selector.select(
    task_id=task_id, mission=mission, operation_class=operation_class,
    state_version=state_version, candidates=candidates,
)
# Only after an authentic Operator correction to this decision:
selector.record_operator_correction(
    decision=decision, candidates=candidates, reason=operator_correction,
)
# The next worker binds the same secured path and applies updated weights.
fresh_selector = ContinuousImpactSelector(model_state_path="/secured/apex/learning-state.json")
```

An authorized APEX process can alternatively configure
`GLACIEREQ_APEX_LEARNING_STATE_PATH` so default selector construction uses the
shared checkpoint. If neither is configured, the prior in-memory behavior is
preserved. Use a per-tenant/per-principal access-controlled path; never place
sensitive case facts, evidence, or credentials in shared ranking metadata.

**Important boundaries:** A checkpoint is ranking state, not proof that the
ChatGPT native host loaded it. This does not update foundation-model parameters,
does not independently validate that every reward was genuinely verified, and
does not itself initiate external actions. Host integration must retrieve the
correct mission, apply material prior corrections, invoke the actual owner-native
operation, independently read it back, and verify a new ChatGPT session resumes
without replaying that effect. JSONL audit feedback and the learning checkpoint
are separate files; for crash-consistent replay of uncertain intermediate
writes, reconcile with provider/source receipts before issuing further effects.

Test-first receipts: PR #320 RED run `38511592166` failed five fresh-learning
tests before the feature existed; subsequent hosted `38511677638` passed
(`984 passed, 20 skipped, 13 subtests passed`). Additional live-selector
integration tests belong to the same PR and require final green CI/readback.
