# OPERATOR ASSET SOVEREIGNTY

**Status:** Mandatory APEX project-direction boundary.

## Purpose

This contract removes any implied assistant, agent, model, automation, or governance authority to assign value, status, hierarchy, disposition, or strategic priority to Operator-owned project assets unless the Operator explicitly requests that specific evaluative act.

## Operator-owned assets

This applies to repositories, branches, files, databases, evidence stores, case lanes, connectors, agents, models, prompts, drafts, workflows, schemas, indexes, manifests, backups, historical snapshots, and other project artifacts.

## Scope semantics

The Operator's verb controls the allowed operation.

- `look`, `inspect`, `open`, `list`, `inventory`, `map`, `trace`, or equivalent observational instructions authorize observation and source-grounded description only.
- Observation does **not** authorize value ranking, strategic ranking, disposition ranking, ownership hierarchy, winner/loser labels, dead-weight labels, deprecation, retirement, archiving, deletion, merging, flattening, subordination, replacement, or priority reassignment.
- `compare` authorizes factual comparison of observed properties. It does not authorize disposition unless the Operator explicitly asks which asset should be preferred, retired, merged, replaced, or otherwise acted upon.
- `classify` defaults only to factual/source classes already required by the task, such as execution state, provenance, evidence type, file type, case relation, or explicitly requested taxonomy. It does not imply asset-worth classification.
- Similar names, overlapping capabilities, age, size, inactivity, branch shape, or apparent redundancy are observations, not authority to declare duplication or lower value.

## Asset-value and disposition authority

Only the Operator may authorize:

1. value ranking of Operator-owned assets;
2. strategic priority ranking among Operator-owned assets when not already supplied by the Operator;
3. designation of a repository or artifact as winner, loser, dead weight, obsolete, primary, subordinate, replacement, archive candidate, or equivalent evaluative status;
4. merge, flatten, rename, delete, archive, deprecate, retire, replace, redirect, or subordinate actions;
5. conversion of an observed relationship into a project hierarchy.

An assistant may surface factual differences and evidence-backed options when requested. A proposal never becomes project state without Operator direction.

## Inspection-only invariant

When the Operator asks to look, the worker must look.

```text
LOOK / INSPECT / MAP / INVENTORY
  -> RETRIEVE SOURCES
  -> OPEN SOURCES
  -> DESCRIBE OBSERVED STATE
  -> REPORT CONNECTIONS / DIFFERENCES / GAPS
  -> STOP AT THE REQUESTED BOUNDARY
```

The worker must not silently append:

```text
-> RANK ASSETS
-> CHOOSE WINNERS
-> LABEL DEAD WEIGHT
-> DESIGNATE PRIMARY / SUBORDINATE
-> RECOMMEND DISPOSITION
-> MUTATE
```

unless the Operator explicitly asked for that additional operation.

## Machine-enforced selected-path flags

Compatible APEX runtimes must fail closed unless the selected execution path preserves all of these invariants:

```text
unsolicited_operator_asset_value_ranking = false
unsolicited_operator_asset_disposition   = false
inspection_scope_expansion               = false
operator_owned_asset_identity_preserved  = true
```

## Correction receipt

The phrase `winners vs dead weight` applied without an Operator request for repo valuation is an example of forbidden authority leakage. It is not a valid inference from tool access, repo metadata, maximum-coherent-advance logic, path selection, or material-state classification.

**Tool access is capability. Observation is knowledge. Neither is authority.**
