# PRIME Counter-Engineering — 2026-09-28

## Objective

Preserve PRIME's useful execution machinery while removing the failure mode in which an established Operator/source-bearing state is repeatedly reopened merely because it is stated again.

This document does not alter platform safety, security, legal, or provider boundaries. It concerns project-state interpretation and continuity inside GlacierEQ.

## Verified lineage

- `GlacierEQ/apex-control-plane@4fc7bd7725f767583caf978ddd07a626bac25589` introduced fail-closed Prime Directive middleware on 2026-08-04.
- The current default branch retains Prime startup, memory-state, source-read, tool-inventory, receipt, contradiction, and APEX execution machinery.
- A current estate code search for the exact phrase `prime directive` returned 228 matches; `prime_directive` returned 138. After deduplication, the first sweep identified 427 files across 35 repositories.
- The highest concentrations in the first sweep are `monolith` (106), `monolith-map` (106), `apex-control-plane` (36), `LEGAL-AI-NEXUS` (26), `THE-CATACLYSM` (18), `legal-motion-automation` (16), `nexus-legal-grid` (16), and `legal-powerhouse` (14).

## Defect pattern

The harmful pattern is not the word PRIME. It is an asymmetric epistemic loop:

```text
ESTABLISHED STATE
  -> reopen because it was asserted
  -> seek contradiction without a positive conflict trigger
  -> treat missing corroboration / metadata / freshness as doubt
  -> demote the wider proposition
  -> repeat
```

That converts verification from a strengthening mechanism into a perpetual veto engine.

## Counter-engineered semantics

```text
RECOVER STRONGEST ESTABLISHED STATE
  -> PRESERVE SOURCE CLASS + PROVENANCE
  -> APPLY IT TO THE CURRENT OPERATION
  -> DETECT ACTUAL POSITIVE CONFLICT
  -> IF CONFLICT EXISTS, INVESTIGATE ONLY THE AFFECTED DIMENSION
  -> PRESERVE PRIOR STATE + SUPERSESSION LINEAGE
  -> CONTINUE EXECUTION
```

Required invariants:

1. Established source-bearing state is starting state, not a hypothesis to retry from zero.
2. Operator firsthand facts remain attributed firsthand facts unless corrected or materially contradicted.
3. Documentary facts remain documentary facts unless materially conflicting source evidence appears.
4. Missing fresh verification is not contradictory evidence.
5. Missing metadata affects the missing metadata dimension, not every underlying event.
6. Contradiction search requires a positive conflict signal; generalized skepticism is not a trigger.
7. Adversarial analysis attacks weak claims, hostile positions, implementation defects, regressions, and unsupported inferences. The Operator is not the default adversary.
8. Prior PRIME artifacts remain preserved as lineage and defect provenance; do not erase them.
9. Useful PRIME machinery is retained: context acquisition, tool invocation, source opening, falsification of unsupported claims, regression detection, repair, testing, and provider readback.
10. Platform safety/security boundaries remain intact and are not project-authority questions.

## Classification for estate-wide sweep

Every PRIME occurrence should be classified rather than blanket-replaced:

- **AMPLIFIER** — directly converts Operator intent into stronger execution.
- **MECHANICAL_GATE** — startup, source, tool, receipt, or state integrity machinery.
- **DOMAIN_PRIME** — a local mission statement such as a casebuilder/event pipeline.
- **HISTORICAL_PROVENANCE** — superseded behavior preserved for lineage.
- **AUTHORITY_INVERSION** — grants project-direction authority to policy/assistant/system over the Operator.
- **PERPETUAL_SKEPTICISM** — reopens established state without a material positive conflict.
- **UNKNOWN** — requires opening the source before classification.

Only the last two classes require semantic inversion by default. Benign/beneficial PRIME machinery is preserved and strengthened.
