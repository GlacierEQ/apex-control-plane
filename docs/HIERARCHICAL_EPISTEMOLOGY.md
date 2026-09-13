# Hierarchical Epistemology — APEX Control Kernel v1

## Purpose

This is a small control kernel for strongest useful agent operation. It does not
pretend that more agents, more context, or more prose automatically produce
better cognition. It selects the cheapest strategy that can satisfy the proof
floor, then escalates only when ambiguity, consequence, or contradiction makes
that escalation worthwhile.

## Hierarchy

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

The hierarchy prevents a lower layer from silently rewriting a higher layer:

- a tool result cannot redefine the mission;
- a repository policy cannot override current Operator direction;
- a worker opinion cannot become a fact without provenance;
- a generated artifact cannot become verified execution;
- a successful run cannot erase a contradiction;
- a failure can change routing, but not authorize scope loss.

## Strategy selector

- **ReAct**: clear, short, tool-centered work.
- **Plan-and-Execute**: long-horizon work with replanning.
- **Reflection**: quality-sensitive work with a concrete critic rubric.
- **Tree-of-Thoughts**: multiple high-cost candidate paths.
- **Reflexion**: repeated attempts where persisted failure memory can improve routing.
- **Debate**: contested or evidence-weighted work with differentiated roles.

The simpler strategy wins until observable failure justifies escalation.

## Budget lanes

- **Cold**: one worker, one round, minimal retrieval.
- **Warm**: three workers, two rounds, bounded retrieval.
- **Hot**: five differentiated workers, two rounds, verification required.

Fan-out stops when verification is achieved, the budget is exhausted, or two
workers add no unique signal without an unresolved conflict. Conflicts remain
visible and route to investigation rather than being averaged away.

## Self-correction

A correction records:

```text
failure
→ failed assumption
→ objective-function change
→ preserve known-good state
→ bounded reroute
→ verify
→ learn
```

Self-healing is deliberately bounded. The kernel can isolate, retry, reroute,
and escalate. It cannot silently mutate project scope, promote its own output,
or invent authority. Boringly explicit code is how future-proof systems stay
alive.

## Progress law

```text
forward_progress = (target_state_changed OR evidence_added) AND NOT artifact_only
```

A new report, plan, page, or log is not progress unless it moves the target state
or adds source-bearing evidence.

## Integration

The implementation is stdlib-only and provider-neutral:

```text
src/hierarchical_epistemology.py
config/hierarchical_epistemology_policy.json
tests/test_hierarchical_epistemology.py
```

The next integration step is to bind the packet and ledger into the existing
APEX strong-boot/runtime path without changing the established five-gate
compatibility contract.

Easter egg: the duck is a sentinel. It watches receipts. It never signs them.
