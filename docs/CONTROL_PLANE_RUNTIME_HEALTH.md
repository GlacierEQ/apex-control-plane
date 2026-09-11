# Control Plane Runtime Health

Backend Ops exposes two service-role-only health surfaces.

`control_plane_health_snapshot_v1()` is the full-estate snapshot. It preserves every connector, including staging, advertised, legacy, and blocked projections.

`control_plane_operational_snapshot_v2()` is the execution-priority snapshot. It does not delete or hide estate state; it classifies it into:

- **operational_core** — connected + authenticated connectors with executable routes or top-tier authority.
- **integration_working_set** — connected/staging connectors still being integrated.
- **estate_backlog** — dormant, advertised, or blocked estate records.

This prevents historical connector backlog from dominating current runtime health while preserving it for remediation.

The operational snapshot also embeds focused GitHub Backend Ops runtime state and the two primary Supabase project connectors.

## Verified state

On 2026-09-02 the live snapshot reported:

- operational core: 7 connectors; 7 healthy; 0 degraded; 0 blocked; 0 unknown.
- operational-core attention: empty.
- integration working set: 125 connectors.
- estate backlog: 52 connectors.
- `notion` is healthy because all three enabled routes have healthy, closed runtime state with zero consecutive failures.
- `mem.primary` and `smithery` remain visible in the integration working set because they have no enabled execution routes; authority tier alone does not promote a connector into the operational core.
- `github.backend_ops`: healthy, zero backlog, one live Edge worker, zero stale online workers.
- `supabase.backend_ops` and `supabase.glaciereq`: healthy with refreshed route-runtime success state.

Historical failures remain evidence; they do not by themselves demote present health.


## Route-runtime semantics

Registry labels such as `verified` and `verified_authorization` are not enough on their own to claim execution health.

For a connected and authenticated connector whose registry state is not already `healthy`, the runtime projection may promote it to healthy only when it has enabled routes, every enabled route has runtime state, and every enabled route runtime is healthy with a closed circuit and zero consecutive failures.

An enabled route with an unhealthy/down state, an open/half-open circuit, or nonzero consecutive failures makes the connector degraded.

The older Notion route `notion:search:workspace_search:v1` is retained as evidence but disabled from selection after `notion:search:workspace_search:v2` was verified healthy. This removes duplicate route ambiguity without deleting history.
