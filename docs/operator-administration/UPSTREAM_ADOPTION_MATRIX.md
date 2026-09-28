# Upstream Adoption Map

Operator Administration should finish mature systems, not recreate them.

| Operator surface | Upstream foundation | Integration rule |
|---|---|---|
| Continuity | Temporal; selected LangGraph checkpoint concepts | Wrap/adapt; do not fork distributed internals by default |
| Cognition | Microsoft Agent Framework; PydanticAI contracts | Specialize behind Operator genome/authority contracts |
| Runtime | Temporal + Dapr | Provider-independent adapters |
| Administration | Backstage concepts + SpiceDB + OPA | Adopt proven catalog/authorization/policy patterns |
| Memory | Graphiti + Letta concepts | Temporal knowledge + durable logical-agent memory |
| Ledger | Tessera + in-toto + OpenLineage | Cryptographic append-only and provenance semantics |
| Evidence | in-toto + lakeFS + OpenLineage | Preserve originals; version transforms |
| Verification | Promptfoo + DeepEval + OpenTelemetry | Behavioral evaluation + mechanical observability |
| Control plane | Supabase | Existing backend-ops project remains live operational plane |
| Command center | Refine + Backstage patterns | Projection/control UI, not source of truth |
| Domains | Activepieces + MCP SDKs | Reuse integrations, wrap with Operator capability grants |

For every adopted upstream record pinned version/commit, license, donor role, rejected components, adapter boundary, upgrade strategy, and verification evidence before production activation.
