# APEX Direct Connector Runtime

## Purpose

APEX now has two authenticated connector transports that must not be confused or permission-unioned:

1. `authenticated_session_provider_bridge` is the repository-side host bridge described by `config/apex_connector_catalog.json`.
2. `authenticated_chatgpt_connectors` is the direct connector transport whose governed route and pipeline state lives in `supabase-backend-ops` and is source-projected by `config/apex_direct_connector_runtime.json`.

`config/apex_connector_contract_registry.json` is the reconciliation registry. A caller must select a transport before resolving capability.

## Why the split matters

The bridge catalog and the direct runtime can legitimately expose different mutation capabilities because they use different authenticated hosts and different execution mappings. For example, bridge-side Notion `page.update` remains inactive until that host mapping is validated, while the direct ChatGPT connector runtime has already executed an approval-gated Notion control projection followed by an independent terminal readback.

That is not a permission contradiction. It is a transport-scoped capability difference. Neither transport grants capability to the other.

## Direct runtime authority

Operational authority is `supabase-backend-ops` (`dyhprklicgewmrimecey`). Route identity comes from `public.connector_route_policy_v3`; runtime state comes from `public.connector_route_runtime_v3`.

The pipeline layer installed on 2026-08-22 adds:

- `public.connector_pipeline_definitions_v1`
- `public.connector_pipeline_runs_v1`
- `public.connector_pipeline_stage_runs_v1`
- `public.start_direct_connector_pipeline_run_v1(...)`
- `public.record_direct_connector_stage_v1(...)`
- `public.finalize_direct_connector_pipeline_run_v1(...)`

The runtime functions are service-role execution surfaces. `anon` and `authenticated` execution are denied.

## Promotion invariants

A direct pipeline is not complete merely because connector calls returned success.

- Route policy v3 is binding.
- Every write carries a bound operator approval reference.
- A write may become `succeeded`; it cannot self-certify as `verified`.
- Every write names a terminal readback stage.
- The readback must use the same connector and the same target object.
- The readback must depend on the write it verifies.
- Successful stages require request hash, result hash, invocation reference, and source references.
- `failed` or `ambiguous` external outcomes cannot promote to a verified pipeline.
- Finalization refuses incomplete write/readback pairs.

## Verified runs

### `apex.direct_control_plane_checkpoint` v1

Pipeline hash: `40691dea85db8d3ca0113d691973a9f0b82cf98ba642e76bea750a1f25fb9aaa`

Run: `b1764a8d-dddd-4c16-a2bc-7e75f9f24f98`

Correlation: `af0c31b1-ed45-4b41-a86e-c63e24b3304e`

Path:

`GitHub source read -> Supabase receipt write -> Supabase receipt readback -> Notion control-plane write -> Notion readback`

Final state: `verified`

Stage proof: 5 stages, 3 verified reads, 2 succeeded writes, 0 failed or ambiguous terminals.

### `apex.connector_mesh_health_sweep` v1

Pipeline hash: `d0a9b1d0e043501e29d56771ae29ecaa1e29ddc8a2a6b7168b636fe41fe0c8b5`

Run: `8998607d-e878-4366-b459-cc27426a0a82`

Correlation: `71948647-9112-4df8-8fc7-ff0b08cfc8f4`

Path:

`Supabase route-state read + GitHub source-contract read + Notion control-plane read`

Final state: `verified`

Stage proof: 3 verified reads, no writes, 0 failed or ambiguous terminals.

## GitHub branch protection boundary

A direct update to protected `main` was attempted while reconciling the runtime and GitHub rejected it because the repository requires four status checks:

- `Audit hardening quality`
- `Estate registry quality`
- `Operator fidelity hard stop`
- `Repository security / 📊 Status`

That protection was not weakened or bypassed. Source reconciliation therefore travels through the repository's required pull-request path.

## Known nonclaims

The direct connector runtime does not imply that the persistent Cloudflare Queue consumer, scoped Smithery executor, or automatic Supabase-to-Notion publisher is deployed. Those boundaries remain explicitly false in the source contract.

The source projection also does not replace Supabase operational truth. If the runtime state and this repository projection diverge, the discrepancy must be investigated and the source projection updated from newly observed evidence rather than silently guessing which side is current.

## Validation

`src/direct_connector_runtime_contract.py` validates the registry and runtime projection. The regression suite proves:

- permissions cannot be unioned across transports;
- the verified direct runtime loads with its two pipelines and five governed routes;
- bridge-side Notion mutation remains inactive while direct-runtime Notion projection authority remains separately represented;
- writes without terminal readback fail validation;
- cross-connector readback fails validation;
- same-connector/different-target readback fails validation;
- verified-run hash mismatch fails validation; and
- a registry that permits permission union fails validation.
