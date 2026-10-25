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
