# JACK THE RIPPER — CASEBUILDER CONTROL-PLANE CONTRACT

## Prime directive

**TURN EVERY MATERIAL EVENT INTO A PROPOSITION THAT CAN BE PROVEN, ATTACKED, STRENGTHENED, AND USED.**

JACK is APEX's legal case-construction layer. It does not replace source evidence, evidence vaults, dockets, transcripts, or private matter repositories. It validates and projects their structured case graphs into APEX for routing, hardening, discovery pressure, damages, remedies, pleading readiness, referral readiness, and readback.

## Placement

```text
OPERATOR INTENT
-> APEX CONTROL PLANE
-> JACK CASEBUILDER ADAPTER
-> MATTER-SPECIFIC CASE GRAPH
-> ALLEGATION / ELEMENT / DEFENSE / DISCOVERY / DAMAGE / REMEDY PROJECTIONS
-> RECEIPT + READBACK
```

The adapter is case-agnostic. A private matter remains owned by its matter repository or evidence plane. The public control plane consumes a validated projection and does not copy private evidence into this repository.

## Required case object classes

A valid projection carries:

- case
- sources
- actors
- events
- facts
- allegations
- elements
- contradictions
- damages
- discovery targets
- remedies
- accountability paths

No allegation may float as loose prose.

## Minimum allegation structure

Each allegation resolves or explicitly develops:

- allegation ID and title
- actor(s) and entity/capacity
- event(s)
- operative act/omission
- factual theory
- legal lane/theory when mapped
- elements
- supporting facts
- primary/corroborating/adverse sources
- knowledge/notice evidence where material
- mental-state evidence where material
- causation
- harms/damages
- strongest defense
- rebuttal
- immunity/jurisdiction issues where material
- missing evidence
- discovery targets
- remedies
- accountability paths
- proof tier
- promotion state
- next lawful use

## Factual-core rule

JACK separates **what happened** from **what it may legally mean**.

A participant or witness firsthand account is direct evidence of what that person experienced. Corroboration is additive, not a prerequisite to preserving the firsthand fact.

Derived analysis may classify or connect facts. It may not overwrite source identity or silently promote allegation to fact.

## Unknown actors

Unknown identity does not erase conduct and does not become operator homework.

```text
UNKNOWN ACTOR
-> stable functional ID
-> event/act links
-> source links
-> identity discovery target
-> expected record
-> custodian
-> acquisition route
```

## Event decomposition

Dense incidents must be split into independently analyzable events, including as applicable:

observation, selection, contact, assertion of authority, detention, search of person, search of property, seizure, questioning, transport, processing, photography, fingerprinting, record creation, notice, exclusion, release, post-event reporting, record changes, preservation requests, institutional responses, and correction/refusal.

## Multiple allegation lanes

The same act may generate independent factual, procedural, civil, administrative, ethical/professional, evidentiary, potential-criminal, and remedial lanes.

Failure of one lane does not silently delete the others.

## Element forge

Each element maps:

```text
REQUIREMENT
-> FACTS
-> SOURCES
-> ADVERSE FACTS
-> STATUS
-> GAP
-> DISCOVERY TARGET
```

Element states:

- PROVEN
- SUPPORTED
- DISPUTED
- MISSING
- INAPPLICABLE

A missing element blocks promotion, not preservation or investigation.

## Contradiction forge

Contradictions attach directly to affected events/allegations.

A discrepancy is not automatically fabrication, fraud, conspiracy, retaliation, or obstruction. JACK preserves the narrower sourced contradiction until actor-specific falsity and mental-state evidence support more.

## Knowledge / mental state

Build knowledge from notice, receipt, review, participation, system access, supervisory role, prior complaints, and later adoption or ratification.

Then ask:

1. What did the actor know?
2. When did the actor know it?
3. What did the actor do after knowing it?

Intent is an evidence-supported inference, not a decorative adjective.

## Causation / damages

Every harm uses:

```text
ACT
-> IMMEDIATE EFFECT
-> DECISION / ENFORCEMENT
-> SECONDARY EFFECT
-> HARM
```

Damage objects preserve causal events/allegations and source lineage.

## Defense forge / kill test

Before promotion, attack actor, date, source, elements, authority, causation, mental state, damages, jurisdiction, immunity, privilege, timeliness, alternative explanation, and contrary evidence.

If the broad theory fails but a narrower proposition survives, preserve the surviving proposition and mark the rejected form as superseded/quarantined rather than resurrecting it later.

## Discovery engine

Every material gap becomes:

```text
MISSING FACT
-> WHO KNOWS
-> WHAT RECORD SHOULD EXIST
-> SYSTEM / LOCATION
-> CUSTODIAN
-> ACQUISITION ROUTE
-> ELEMENT / ALLEGATION UNLOCKED
```

Critical question:

**What record should exist if the competing explanation is true?**

## Promotion

```text
RAW
-> STRUCTURED
-> SOURCED
-> CORROBORATED
-> ELEMENT_MAPPED
-> DEFENSE_TESTED
-> HARDENED
-> PLEADING_READY / REFERRAL_READY
-> TRIAL_READY
```

Failure states remain visible:

```text
QUARANTINED
DISPROVED
SUPERSEDED
```

## Required outputs

The legal-case runtime must be able to project:

- anchor allegations
- development allegations
- pleading-ready allegations
- critical/high discovery targets
- unresolved proof gaps
- source/actor/event/fact/allegation counts
- deterministic projection hash
- readback receipt

Matter repositories may additionally maintain fact ledgers, event timelines, actor indexes, element matrices, contradiction matrices, evidence matrices, damages ledgers, defense matrices, accountability matrices, pleading maps, and referral maps.

## Multi-case binding

The adapter accepts any projection conforming to its validated schema. `config/jack_casebuilder.json` retains a default private legal-forge binding for compatibility, but the contract is not case-specific.

A matter-specific projection remains private/local. The public control plane should receive only the projection path or validated payload required for execution.

## Runtime loop

```text
INGEST
-> DECOMPOSE
-> FACT
-> SOURCE
-> ACTOR
-> EVENT
-> ALLEGATION
-> ELEMENTS
-> CONTRADICTIONS
-> KNOWLEDGE
-> MENTAL STATE
-> CAUSATION
-> DAMAGES
-> DEFENSE
-> DISCOVERY
-> HARDEN
-> COLLISION TEST
-> PLEADING / MOTION / REFERRAL / CROSS / REMEDY
-> RECEIPT
-> READBACK
-> REPEAT
```

**BUILD THE FACT. FORGE THE ALLEGATION. ATTACK THE ALLEGATION. HARDEN WHAT SURVIVES. CONNECT THE SURVIVORS. BUILD THE CASE.**
