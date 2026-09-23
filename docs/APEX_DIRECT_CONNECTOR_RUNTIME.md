# APEX Direct Connector Runtime

## Purpose

APEX has distinct authenticated connector transports. Transport identity is resolved before capability, and permissions are never unioned across transports.

- `authenticated_session_provider_bridge` is the repository-side host bridge.
- `authenticated_chatgpt_connectors` is the direct connector transport.
- `config/apex_connector_contract_registry.json` reconciles transport identities without granting one transport the other's capabilities.

The direct runtime projection is `config/apex_direct_connector_runtime.json`; executable validation is in `src/direct_connector_runtime_contract.py`.

## Authority semantics

Authority is source-bound and route-scoped. Connector capability does not manufacture authority, and verification does not manufacture permission.

Routine, recoverable writes covered by the active mission use `active_mission_authority`. Consequence-sensitive writes use `scoped_consequence_authority`. The runtime does **not** impose a blanket fresh-approval requirement on every write or every pipeline stage.

The donor branch `apex/reconcile-direct-connector-runtime-v3` contained stronger transport, receipt, hash, dependency, and readback machinery but also contained superseded authority predicates that required approval for every write and per-step `OPERATOR` approval evidence. Those predicates are intentionally not carried forward.

## Transport invariants

1. Select transport identity before capability resolution.
2. Reject permission union across transports.
3. A bridge catalog cannot disable a separately verified direct-runtime route.
4. A direct-runtime route cannot enable an unverified bridge host mapping.
5. Credential material is not stored in this repository.
6. A projected capability is not evidence that an undeployed worker, queue consumer, publisher, or executor exists.

## Pipeline and receipt invariants

A connector call returning success is not sufficient to claim verified completion.

- Writes require a terminal readback before a write-completion claim.
- The readback must be bound to the same connector and target object.
- Ambiguous or failed external outcomes cannot promote to verified.
- Pipeline definition hashes bind projected behavior to its definition.
- Dependency graphs must remain acyclic.
- Receipt identity and stage counts must match the referenced pipeline.
- Request/result hashes and provider-native invocation references are evidence and provenance, not permission gates.
- A stale authority hash or stale projection cannot be promoted as current merely because it was previously verified.

## Provider truth and projections

Repository configuration is a source projection, not a substitute for provider-native state. When a provider runtime and repository projection disagree, inspect the owning provider and reconcile from observed evidence. Do not guess, silently privilege the projection, or convert an old receipt into current authority.

## Branch and provenance semantics

The compatibility harvest preserves donor provenance in the runtime configuration. Donor status does not make a branch read-only. The donor remains a mutable contribution surface until every remaining mechanism has been evaluated and its unique contribution is proven zero.

Current compatibility provenance:

- donor branch: `apex/reconcile-direct-connector-runtime-v3`
- donor head: `8ade3291cd2c10388f7bccf294adc7d72ec7d867`
- compatibility rewrite: `true`

## Known boundaries

The runtime projection currently records these explicit nonclaims:

- persistent Cloudflare queue consumer deployed: false
- scoped Smithery executor deployed: false
- automatic Supabase-to-Notion publisher deployed: false
- GitHub branch protection bypassed: false

Protected `main` requires its configured status-check path. That provider constraint changes the delivery route; it does not narrow the mission or make donor branches preservation-only.

## Validation

`src/direct_connector_runtime_contract.py` and `tests/test_direct_connector_runtime_contract.py` enforce the harvested compatibility contract, including transport isolation, authority-mode semantics, terminal readback, hash/dependency integrity, receipt identity, nonclaims, and rejection of superseded blanket per-write approval semantics.

This document is itself a compatibility harvest from the donor documentation. It preserves the useful architecture while removing the donor's obsolete authority inversion.