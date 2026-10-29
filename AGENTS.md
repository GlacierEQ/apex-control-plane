# APEX Control Plane — Overhaul Note (2026-10-24)

Update 2026-10-24: the `apex_proactive` engine was removed after its
live-job proof test (OMP model-list scoping) returned NOT PROVEN — no
workflow mechanism altered an outcome except the grader formalizing an
already-spotted empty receipt. The tool catalog survived as a standalone
module (`src/tool_catalog.py`): the whole inventory stays visible and
loading is a per-turn choice by the agent, never a cap. The overhaul's
resistance fixes stand; only the engine is gone.

This file was replaced in the ACP overhaul. Older startup/gate references
in this repository are superseded; see OVERHAUL_NOTES.md for the rebuild
receipt, the resistances resolved, and the test numbers.

Current model, in one paragraph: triggers run routes; receipts are
before/after state diffs; an unverified route runs until it verifies or
reroutes; escalation survives only for a genuine judgment call, an
offer/acceptance, a fact only the Operator holds, or a Tier-2 log matter
(court, agencies, administration, PACT); a worker never grades its own
work; missing evidence renders as no value, never an invented number.

Attribution, standing: the control stack that was eradicated in
2026-10-23 is the machine's handwriting, not the Operator's build.
Git author name is the separator: GlacierEQ is his lane.


## Operator words: source-preserving hierarchical distillation

The Operator's October 24 correction is direct: "Distill my words into hierarchical bulletpoints. How many times I say it"; "The memory structure needs to be overhauled and the way you work needs to be fucking flashed".

- Recover the original statements, nearby context and later corrections first. Their literal language and intent are not replaced by assistant explanations, capsules or summaries.
- Render nested parent/child/subchild bullets without losing unique words, repeated occurrences, negations, swearing/emphasis, factual qualifications, dates, actors or cross-references.
- Keep exactly sourced speech (`VERBATIM`) separate from assistant-created organization (`DERIVED STRUCTURE`), interpretations, or unverified memory projections.
- Use the surviving positive operation `render_operator_hierarchical_distillation` in `src/operator_source_authority.py` when constructing such an outline from verified source-span bindings. Keep unverified source items visible as retrieval gaps instead of manufacturing quotations.
- Read source-locator, original text and version/provenance evidence back from the owning provider after every persistent transformation. Memory acknowledgement is not proof of host adoption, new-session behavior, or overall user outcome.
- The October 23/24 proactive ACP overhaul remains intact. This instruction does not recreate deleted startup machinery, change merge/deploy approval, create an arbitrary block, or assert control over native ChatGPT boot. The original positive execution path remains active.
