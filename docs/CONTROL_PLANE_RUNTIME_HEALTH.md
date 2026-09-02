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

- operational core: 10 connectors; 7 healthy; 0 degraded; 0 blocked; 3 unknown.
- operational-core attention: `notion`, `mem.primary`, and `smithery`.
- integration working set: 122 connectors.
- estate backlog: 52 connectors.
- `github.backend_ops`: healthy, zero backlog, one live Edge worker, zero stale online workers.
- `supabase.backend_ops` and `supabase.glaciereq`: healthy with refreshed route-runtime success state.

Historical failures remain evidence; they do not by themselves demote present health.
