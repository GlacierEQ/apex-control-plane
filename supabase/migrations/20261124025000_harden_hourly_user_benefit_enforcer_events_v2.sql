-- Benefit Enforcer: close INSERT-completed and evidence-edit bypasses.
-- Existing scope, evidence requirements and context application guard preserved.
-- No additional automation, scheduler, queue, or evidence owner created.
--
-- Previously the guards fired only BEFORE UPDATE OF status and only on
-- a transition into completed. A completed INSERT or later alteration to
-- proof/status-related columns escaped their verification.
--
-- The same guards now execute on INSERT and relevant UPDATE columns,
-- and check EVERY completed state they encounter.

CREATE OR REPLACE FUNCTION private.enforce_hourly_user_benefit_completion_v1()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'public', 'private'
AS $function$
BEGIN
  IF NEW.scope_key = 'automation:6ae8e3c2dafc8191ab6a582f1a74c71a'
     AND NEW.status = 'completed'
  THEN
    IF COALESCE(NEW.item_count, 0) < 1
       OR COALESCE(NEW.completed_item_count, 0) < NEW.item_count
       OR COALESCE(NEW.result_summary ->> 'verification_state', '') <> 'VERIFIED_USER_BENEFIT'
       OR COALESCE(NEW.result_summary ->> 'before_state', '') <> 'failed'
       OR COALESCE(NEW.result_summary ->> 'after_state', '') <> 'restored'
       OR NULLIF(BTRIM(COALESCE(NEW.result_summary ->> 'provider_ref', '')), '') IS NULL
       OR NULLIF(BTRIM(COALESCE(NEW.result_summary ->> 'readback_ref', '')), '') IS NULL
       OR NULLIF(BTRIM(COALESCE(NEW.result_summary ->> 'subject_id', '')), '') IS NULL
    THEN
      RAISE EXCEPTION USING
        ERRCODE = 'check_violation',
        MESSAGE = 'hourly_user_benefit_completion_requires_native_restoration_readback';
    END IF;

    PERFORM 1
    FROM public.cognition_context_binding_current_v1 AS b
    WHERE b.case_id IS NULL
      AND b.subject_type = 'action'
      AND b.subject_id = NEW.result_summary ->> 'subject_id'
      AND b.mission = 'HOURLY_USER_BENEFIT_OVERHAUL'
      AND b.hydration_state = 'hydrated'
      AND b.packet_id IS NOT NULL
      AND b.context_fresh IS TRUE
      AND b.context_created_at >= NEW.created_at
      -- Hydrated/retrieved is not the same as applied by the consumer.
      AND b.recovery_debt->>'downstream_application_unverified' IS DISTINCT FROM 'true'
      AND jsonb_typeof(b.metadata->'context_application_receipt')='object'
      AND b.metadata->'context_application_receipt'->>'verification_state'='PROVIDER_READBACK'
      AND b.metadata->'context_application_receipt'->>'packet_id'=b.packet_id::text
      AND b.metadata->'context_application_receipt'->>'packet_snapshot_hash'=b.packet_snapshot_hash
      AND b.metadata->'context_application_receipt'->>'readback_ref'=NEW.result_summary->>'readback_ref'
      AND b.metadata->'context_application_receipt'->>'observed_effect'=NEW.result_summary->>'observed_effect'
      AND nullif(btrim(NEW.result_summary->>'observed_effect'),'') IS NOT NULL;

    IF NOT FOUND THEN
      RAISE EXCEPTION USING
        ERRCODE = 'check_violation',
        MESSAGE = 'hourly_user_benefit_completion_requires_verified_context_application_receipt';
    END IF;
  END IF;

  RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION private.enforce_hourly_user_benefit_invocation_completion_v1()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path TO pg_catalog, public, private
AS $function$
BEGIN
  IF NEW.scope_key = 'automation:6ae8e3c2dafc8191ab6a582f1a74c71a'
     AND NEW.status = 'completed'
  THEN
    PERFORM 1 FROM public.connector_work_bundles AS b
    WHERE b.id = NEW.bundle_id
      AND b.scope_key = NEW.scope_key
      AND b.status = 'completed'
      AND b.item_count > 0
      AND b.completed_item_count >= b.item_count
      AND b.result_summary = NEW.result
      AND b.result_summary ->> 'verification_state' = 'VERIFIED_USER_BENEFIT'
      AND b.result_summary ->> 'before_state' = 'failed'
      AND b.result_summary ->> 'after_state' = 'restored';

    IF NOT FOUND THEN
      RAISE EXCEPTION USING ERRCODE='check_violation',
      MESSAGE='hourly_user_benefit_invocation_requires_verified_completed_bundle';
    END IF;
  END IF;
  RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS trg_enforce_hourly_user_benefit_completion_v1
  ON public.connector_work_bundles;
CREATE TRIGGER trg_enforce_hourly_user_benefit_completion_v1
BEFORE INSERT OR UPDATE OF status, scope_key, item_count, completed_item_count,
  result_summary, created_at
ON public.connector_work_bundles
FOR EACH ROW
EXECUTE FUNCTION private.enforce_hourly_user_benefit_completion_v1();

DROP TRIGGER IF EXISTS trg_enforce_hourly_user_benefit_invocation_completion_v1
  ON public.everything_mcp_plugin_invocations;
CREATE TRIGGER trg_enforce_hourly_user_benefit_invocation_completion_v1
BEFORE INSERT OR UPDATE OF status, scope_key, bundle_id, result
ON public.everything_mcp_plugin_invocations
FOR EACH ROW
EXECUTE FUNCTION private.enforce_hourly_user_benefit_invocation_completion_v1();
