# JACK THE RIPPER — CASEBUILDER / ALLEGATION FORGE

> **Prime directive:** TURN EVERY MATERIAL EVENT INTO A PROPOSITION THAT CAN BE PROVEN, ATTACKED, STRENGTHENED, AND USED.

CaseBuilder is Jack's case-construction layer. It operates downstream of source acquisition and upstream of litigation, administrative, disciplinary, discovery, damages, and referral outputs.

## Pipeline

```text
RAW MATERIAL
-> SOURCE OBJECTS
-> FACT PROPOSITIONS
-> EVENTS
-> ACTS
-> ACTORS / UNKNOWN ACTORS
-> ALLEGATION LANES
-> ELEMENT MAPS
-> PROOF STACKS
-> CONTRADICTIONS
-> KNOWLEDGE / MENTAL-STATE SUPPORT
-> CAUSATION
-> DAMAGES
-> BEST DEFENSE
-> REBUTTAL
-> PROOF GAPS
-> DISCOVERY TARGETS
-> REMEDIES
-> ACCOUNTABILITY PATHS
-> HARDENING
-> PLEADING / MOTION / DEMAND / REFERRAL / TRIAL OUTPUT
```

## Construction laws

1. Facts and legal meaning remain separate objects.
2. Unknown actors are modeled, not ignored; identity becomes discovery.
3. Every graph allegation links factual propositions and a duty or prohibition.
4. Every allegation maps required elements to proof, contrary proof, and gaps.
5. Contradictions attach to allegations and carry a resolution state.
6. Mental state is never inferred merely from contradiction or missing records.
7. Damages require event and source lineage.
8. Every core allegation must survive a best-defense pass.
9. Every unresolved material gap becomes an executable discovery, preservation, retrieval, or identity target.
10. P0/P1 unresolved discovery blocks trial-ready promotion.
11. Referral-ready requires a ready accountability path.
12. Orphan objects are surfaced instead of silently floating outside the case.
13. Pressure is emitted as a transparent multidimensional vector.
14. Public control-plane code must not contain private case evidence.
15. Promotion is fail-closed.

## Runtime surfaces

Stable allegation layer:
- `jack/src/casebuilder.py`
- `jack/config/casebuilder_contract.json`
- `legal/schemas/casebuilder_case.schema.json`
- `jack/tests/test_casebuilder.py`

Full typed graph extension:
- `jack/src/casegraph.py`
- `jack/config/casebuilder_graph_contract.json`
- `legal/schemas/casebuilder_graph.schema.json`
- `jack/tests/test_casegraph.py`

Machine routing:
- `machine/casebuilder.json`

## Promotion states

`RAW -> STRUCTURED -> SOURCED -> CORROBORATED -> ELEMENT_MAPPED -> DEFENSE_TESTED -> HARDENED -> PLEADING_READY -> REFERRAL_READY -> TRIAL_READY`

`QUARANTINED` and `DISPROVED` fail closed.

`PLEADING_READY` is produced only after the stable allegation gates survive. `REFERRAL_READY` additionally requires a ready accountability path. `TRIAL_READY` additionally requires satisfied elements, no allegation missing-evidence IDs, resolved P0/P1 discovery, and every linked contradiction to be `RESOLVED` or `IMPEACHMENT_READY`.

## Attack loop

```text
DRAFT
-> ATTACK FACTS
-> ATTACK SOURCE
-> ATTACK ELEMENTS
-> ATTACK CAUSATION
-> ATTACK MENTAL STATE
-> ATTACK DAMAGES
-> ATTACK PROCEDURE / AUTHORITY
-> BUILD BEST DEFENSE
-> REBUT
-> IDENTIFY GAP
-> CONVERT GAP TO TARGET
-> REWRITE
-> ATTACK AGAIN
```

Aggression is proof density and structural survivability.

## Machine outputs

The graph runtime emits:
- master fact ledger
- master event timeline
- actor index
- allegation ledger
- contradiction matrix
- damages ledger
- discovery matrix
- defense matrix
- accountability map
- promotion report
- pressure map
- orphan report

The case file therefore does not need to reconstruct its basic architecture for every pleading, motion, demand, referral, or hearing.
