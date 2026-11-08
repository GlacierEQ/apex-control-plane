-- Live connector status view fix: completed means evidence-backed provider execution.
-- Historical connector_work_bundles and receipts remain unchanged, including
-- 4 old GitHub completed rows with zero raw provider calls.
-- Preserve the original column contract and all other CTEs.
-- Dependency: public.connector_bundle_items, public.connector_consolidated_receipts.
-- Rollback: restore the preceding pg_get_viewdef source in migration history.

CREATE OR REPLACE VIEW public.connector_mega_plane_status_v1 AS
 WITH latest_health AS (
         SELECT DISTINCT ON (apex_connector_health.connector) apex_connector_health.connector,
            apex_connector_health.status,
            apex_connector_health.error_msg,
            apex_connector_health.checked_at,
            apex_connector_health.latency_ms,
            apex_connector_health.consecutive_failures
           FROM apex_connector_health
          ORDER BY apex_connector_health.connector, apex_connector_health.checked_at DESC NULLS LAST
        ), latest_plugin_check AS (
         SELECT DISTINCT ON (p.connector_key) p.connector_key,
            c.status AS check_status,
            c.details AS check_details,
            c.observed_at
           FROM everything_mcp_plugin_checks c
             JOIN everything_mcp_plugins p ON p.plugin_key = c.plugin_key
          WHERE p.connector_key IS NOT NULL AND c.check_key ~~ 'provider_runtime_probe_%'::text
          ORDER BY p.connector_key, c.observed_at DESC
        ), bindings AS (
         SELECT lower(control_plane_connector_bindings.source_system) AS connector_key,
            count(*) FILTER (WHERE control_plane_connector_bindings.status = 'ACTIVE'::text) AS active_bindings
           FROM control_plane_connector_bindings
          GROUP BY (lower(control_plane_connector_bindings.source_system))
        ), verified_bundle_ids AS (
         SELECT b.id
           FROM public.connector_work_bundles b
           JOIN public.connector_consolidated_receipts r ON r.bundle_id=b.id
          WHERE b.status='completed'
            AND b.completed_at IS NOT NULL
            AND b.item_count > 0
            AND b.completed_item_count=b.item_count
            AND r.raw_provider_call_count > 0
            AND r.provider_phase_count > 0
            AND r.verification_state IN ('READ_BACK','ACTIVE_VERIFIED','PROVIDER_READBACK')
            AND nullif(btrim(b.result_summary->>'provider_ref'),'') IS NOT NULL
            AND nullif(btrim(b.result_summary->>'readback_ref'),'') IS NOT NULL
            AND b.result_summary->>'provider_ref'=r.receipt->>'provider_ref'
            AND b.result_summary->>'readback_ref'=r.receipt->>'readback_ref'
            AND (SELECT count(*) FROM public.connector_bundle_items i WHERE i.bundle_id=b.id)=b.item_count
            AND NOT EXISTS (
              SELECT 1 FROM public.connector_bundle_items i WHERE i.bundle_id=b.id
                AND (i.status IS DISTINCT FROM 'completed'
                  OR i.result IS NULL
                  OR nullif(btrim(i.result->>'provider_ref'),'') IS NULL
                  OR nullif(btrim(i.result->>'readback_ref'),'') IS NULL
                  OR coalesce(i.error,'{}'::jsonb)<>'{}'::jsonb)
            )
          GROUP BY b.id
        ), bundle_stats AS (
         SELECT connector_work_bundles.connector_key,
            count(*) AS bundles,
            count(*) FILTER (WHERE connector_work_bundles.status = ANY (ARRAY['queued'::text, 'leased'::text, 'running'::text])) AS open_bundles,
            count(*) FILTER (WHERE verified_bundle_ids.id IS NOT NULL) AS completed_bundles,
            COALESCE(sum(connector_work_bundles.item_count), 0::bigint) AS bundled_items,
            COALESCE(sum(CASE WHEN verified_bundle_ids.id IS NOT NULL THEN connector_work_bundles.completed_item_count ELSE 0 END), 0::bigint) AS completed_items
           FROM connector_work_bundles LEFT JOIN verified_bundle_ids ON verified_bundle_ids.id=connector_work_bundles.id
          GROUP BY connector_work_bundles.connector_key
        ), receipt_stats AS (
         SELECT connector_consolidated_receipts.connector_key,
            count(*) AS consolidated_receipts,
            COALESCE(sum(connector_consolidated_receipts.raw_provider_call_count), 0::bigint) AS raw_provider_calls,
            COALESCE(sum(connector_consolidated_receipts.item_count), 0::bigint) AS receipted_items,
            max(connector_consolidated_receipts.created_at) AS last_receipt_at
           FROM connector_consolidated_receipts
          GROUP BY connector_consolidated_receipts.connector_key
        ), plugin_receipt_stats AS (
         SELECT p.connector_key,
            count(*) FILTER (WHERE r.verification_state = 'VERIFIED'::text) AS verified_plugin_receipts,
            max(r.observed_at) FILTER (WHERE r.verification_state = 'VERIFIED'::text) AS last_plugin_receipt_at
           FROM everything_mcp_plugins p
             JOIN everything_mcp_plugin_receipts r ON r.plugin_key = p.plugin_key
          WHERE p.connector_key IS NOT NULL
          GROUP BY p.connector_key
        ), base AS (
         SELECT c.id,
            c.connector_key,
            c.display_name,
            c.plane,
            c.role,
            c.read_enabled,
            c.write_enabled,
            c.default_mode,
            c.risk_level,
            c.status,
            c.notes,
            c.capabilities,
            c.blocked_actions,
            c.created_at,
            c.updated_at,
            p.status AS profile_status,
            p.execution_class,
            p.acquisition_strategy,
            p.mutation_strategy,
            p.workspace_strategy,
            p.readback_strategy,
            p.consolidation_window_seconds,
            p.max_bundle_items,
            p.max_payload_bytes,
            p.provider_phase_budget,
            p.supports_snapshot,
            p.supports_delta,
            p.supports_batch_mutation,
            p.supports_local_workspace,
            p.requires_plan,
            p.requires_readback,
            COALESCE(b.active_bindings, 0::bigint) AS active_bindings,
            h.status AS raw_health_status,
            h.error_msg AS raw_health_error,
            h.checked_at AS raw_health_checked_at,
            h.latency_ms,
            h.consecutive_failures,
            pc.check_status,
            pc.check_details,
            pc.observed_at AS provider_check_at,
            COALESCE(bs.bundles, 0::bigint) AS bundles,
            COALESCE(bs.open_bundles, 0::bigint) AS open_bundles,
            COALESCE(bs.completed_bundles, 0::bigint) AS completed_bundles,
            COALESCE(bs.bundled_items, 0::bigint) AS bundled_items,
            COALESCE(bs.completed_items, 0::bigint) AS completed_items,
            COALESCE(rs.consolidated_receipts, 0::bigint) AS consolidated_receipts,
            COALESCE(rs.raw_provider_calls, 0::bigint) AS raw_provider_calls,
            COALESCE(rs.receipted_items, 0::bigint) AS receipted_items,
            rs.last_receipt_at,
            COALESCE(prs.verified_plugin_receipts, 0::bigint) AS verified_plugin_receipts,
            prs.last_plugin_receipt_at
           FROM everything_mcp_connectors c
             LEFT JOIN connector_execution_profiles p ON p.connector_key = c.connector_key
             LEFT JOIN latest_health h ON h.connector = c.connector_key
             LEFT JOIN latest_plugin_check pc ON pc.connector_key = c.connector_key
             LEFT JOIN bindings b ON b.connector_key = c.connector_key
             LEFT JOIN bundle_stats bs ON bs.connector_key = c.connector_key
             LEFT JOIN receipt_stats rs ON rs.connector_key = c.connector_key
             LEFT JOIN plugin_receipt_stats prs ON prs.connector_key = c.connector_key
        ), effective AS (
         SELECT b.id,
            b.connector_key,
            b.display_name,
            b.plane,
            b.role,
            b.read_enabled,
            b.write_enabled,
            b.default_mode,
            b.risk_level,
            b.status,
            b.notes,
            b.capabilities,
            b.blocked_actions,
            b.created_at,
            b.updated_at,
            b.profile_status,
            b.execution_class,
            b.acquisition_strategy,
            b.mutation_strategy,
            b.workspace_strategy,
            b.readback_strategy,
            b.consolidation_window_seconds,
            b.max_bundle_items,
            b.max_payload_bytes,
            b.provider_phase_budget,
            b.supports_snapshot,
            b.supports_delta,
            b.supports_batch_mutation,
            b.supports_local_workspace,
            b.requires_plan,
            b.requires_readback,
            b.active_bindings,
            b.raw_health_status,
            b.raw_health_error,
            b.raw_health_checked_at,
            b.latency_ms,
            b.consecutive_failures,
            b.check_status,
            b.check_details,
            b.provider_check_at,
            b.bundles,
            b.open_bundles,
            b.completed_bundles,
            b.bundled_items,
            b.completed_items,
            b.consolidated_receipts,
            b.raw_provider_calls,
            b.receipted_items,
            b.last_receipt_at,
            b.verified_plugin_receipts,
            b.last_plugin_receipt_at,
                CASE
                    WHEN b.provider_check_at IS NOT NULL AND (b.raw_health_checked_at IS NULL OR b.provider_check_at > b.raw_health_checked_at) AND b.check_status = 'PASS'::text THEN 'HEALTHY'::text
                    WHEN b.provider_check_at IS NOT NULL AND (b.raw_health_checked_at IS NULL OR b.provider_check_at > b.raw_health_checked_at) AND b.check_status = 'FAIL'::text THEN
                    CASE
                        WHEN COALESCE(b.check_details ->> 'classification'::text, ''::text) = 'connector_binding_degraded'::text THEN 'BINDING_FAILED'::text
                        ELSE 'PROVIDER_CHECK_FAILED'::text
                    END
                    ELSE b.raw_health_status
                END AS effective_health_status,
                CASE
                    WHEN b.provider_check_at IS NOT NULL AND (b.raw_health_checked_at IS NULL OR b.provider_check_at > b.raw_health_checked_at) THEN b.provider_check_at
                    ELSE b.raw_health_checked_at
                END AS effective_health_checked_at,
                CASE
                    WHEN b.provider_check_at IS NOT NULL AND (b.raw_health_checked_at IS NULL OR b.provider_check_at > b.raw_health_checked_at) THEN
                    CASE
                        WHEN b.check_status = 'FAIL'::text THEN COALESCE(b.check_details ->> 'evidence'::text, b.check_details::text)
                        ELSE NULL::text
                    END
                    ELSE b.raw_health_error
                END AS effective_health_error
           FROM base b
        )
 SELECT connector_key,
    display_name,
    plane,
    role,
    status AS catalog_status,
    read_enabled,
    write_enabled,
    default_mode,
    risk_level,
    profile_status,
    execution_class,
    acquisition_strategy,
    mutation_strategy,
    workspace_strategy,
    readback_strategy,
    consolidation_window_seconds,
    max_bundle_items,
    max_payload_bytes,
    provider_phase_budget,
    supports_snapshot,
    supports_delta,
    supports_batch_mutation,
    supports_local_workspace,
    requires_plan,
    requires_readback,
    active_bindings,
    effective_health_status AS health_status,
    effective_health_error AS health_error,
    effective_health_checked_at AS health_checked_at,
    latency_ms,
    consecutive_failures,
        CASE
            WHEN lower(status) = 'misbound_external_account'::text THEN 'BLOCKED_MISBOUND'::text
            WHEN lower(status) = 'account_required'::text THEN 'BLOCKED_ACCOUNT_REQUIRED'::text
            WHEN lower(status) = 'approval_or_login_required'::text THEN 'BLOCKED_USER_REAUTH'::text
            WHEN lower(status) = 'blocked_binding'::text THEN 'BLOCKED_BINDING'::text
            WHEN lower(status) = 'partial_scope'::text THEN 'ACTIVE_PARTIAL'::text
            WHEN lower(status) = 'partial_reauth'::text THEN 'ACTIVE_PARTIAL'::text
            WHEN lower(status) = 'healthy_scope_limited'::text THEN 'ACTIVE_SCOPE_LIMITED'::text
            WHEN lower(status) = 'healthy_limited_credits'::text THEN 'ACTIVE_CREDIT_LIMITED'::text
            WHEN lower(status) = 'connected_empty'::text THEN 'ACTIVE_EMPTY'::text
            WHEN effective_health_status = 'AUTH_FAILED'::text THEN 'BLOCKED_AUTH'::text
            WHEN profile_status = 'active'::text AND effective_health_status = 'HEALTHY'::text AND (consolidated_receipts > 0 OR verified_plugin_receipts > 0) THEN 'ACTIVE_VERIFIED'::text
            WHEN profile_status = 'active'::text AND effective_health_status = 'HEALTHY'::text AND read_enabled AND NOT write_enabled THEN 'ACTIVE_READ_ONLY'::text
            WHEN profile_status = 'active'::text AND effective_health_status = 'HEALTHY'::text THEN 'ACTIVE_UNVERIFIED'::text
            WHEN profile_status = 'active'::text AND (effective_health_status IS NULL OR effective_health_status = 'UNKNOWN'::text) THEN
            CASE
                WHEN read_enabled AND NOT write_enabled THEN 'ACTIVE_READ_ONLY'::text
                ELSE 'ACTIVE_UNVERIFIED'::text
            END
            WHEN profile_status = 'profiled'::text THEN 'PROFILED_NOT_PROMOTED'::text
            ELSE upper(COALESCE(profile_status, 'UNPROFILED'::text))
        END AS execution_state,
    bundles,
    open_bundles,
    completed_bundles,
    bundled_items,
    completed_items,
    consolidated_receipts,
    raw_provider_calls,
    receipted_items,
    GREATEST(last_receipt_at, last_plugin_receipt_at) AS last_receipt_at
   FROM effective e;
