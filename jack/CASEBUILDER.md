# JACK THE RIPPER — CASEBUILDER / ALLEGATION FORGE

> **Prime directive:** TURN EVERY MATERIAL EVENT INTO A PROPOSITION THAT CAN BE PROVEN, ATTACKED, STRENGTHENED, AND USED.

CaseBuilder is Jack's case-construction layer. It operates downstream of source acquisition and upstream of litigation, administrative, disciplinary, discovery, damages, and referral outputs.

## Pipeline

```text
RAW MATERIAL
-> SOURCE OBJECTS
-> EVENTS
-> ACTS
-> ACTORS / UNKNOWN ACTORS
-> FACT PROPOSITIONS
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
-> HARDENING
-> PLEADING / MOTION / DEMAND / REFERRAL OUTPUT
```

## Construction laws

1. Facts and legal meaning remain separate objects.
2. Unknown actors are modeled, not ignored; identity becomes discovery.
3. Every allegation maps every required element to proof, contrary proof, and gaps.
4. Contradictions attach to allegations.
5. Mental state is never inferred merely from contradiction or missing records.
6. Damages require causal lineage.
7. Every core allegation must survive a best-defense pass.
8. Every unresolved material gap becomes an executable discovery, preservation, retrieval, or identity target.
9. Public control-plane code must not contain private case evidence.
10. Promotion is fail-closed.

## Runtime surfaces

- `jack/src/casebuilder.py`
- `jack/config/casebuilder_contract.json`
- `legal/schemas/casebuilder_case.schema.json`
- `jack/tests/test_casebuilder.py`

## Promotion states

`RAW -> STRUCTURED -> SOURCED -> CORROBORATED -> ELEMENT_MAPPED -> DEFENSE_TESTED -> HARDENED -> PLEADING_READY -> REFERRAL_READY -> TRIAL_READY`

`QUARANTINED` and `DISPROVED` fail closed.

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
