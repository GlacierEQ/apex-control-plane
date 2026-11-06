-- Deployed to Supabase kjebemdgvjvuutzvhbtp under migration
-- enforce_hourly_user_benefit_completion_v1 on 2026-11-06 UTC.
-- This is the GitHub source mirror of the native production guard, not a
-- ChatGPT scheduler hook. Preserve every other automation and case owner.
-- Reapplying is safe: the function is replaced, trigger created only if absent.

CREATE OR REPLACE FUNCTION private.enforce_hourly_user_benefit_completion_v1()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path TO pg_catalog, public, private
AS $function$
BEGIN
  IF NEW.scope_key = 'automation:6ae8e3c2dafc8191ab6a582f1a74c71a'
     AND NEW.status = 'completed'
     AND OLD.status IS DISTINCT FROM 'completed'
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
      AND b.context_created_at >= NEW.created_at;

    IF NOT FOUND THEN
      RAISE EXCEPTION USING
        ERRCODE = 'check_violation',
        MESSAGE = 'hourly_user_benefit_completion_requires_fresh_applied_context';
    END IF;
  END IF;

  RETURN NEW;
END;
$function$;

DO $block$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_trigger AS t
    WHERE t.tgrelid = 'public.connector_work_bundles'::pg_catalog.regclass
      AND t.tgname = 'trg_enforce_hourly_user_benefit_completion_v1'
      AND NOT t.tgisinternal
  ) THEN
    CREATE TRIGGER trg_enforce_hourly_user_benefit_completion_v1
    BEFORE UPDATE OF status ON public.connector_work_bundles
    FOR EACH ROW
    EXECUTE FUNCTION private.enforce_hourly_user_benefit_completion_v1();
  END IF;
END;
$block$;

-- Acceptance already exercised against the real queued APEX bundle:
-- bundle e5ff8e01-be12-4ab6-a88a-049d2ba1d258
-- invocation c985fd4f-fb3c-4473-a65a-eb18f600c623
-- attempted premature 'completed' UPDATE was rejected with SQLSTATE 23514.
-- Native readback kept both invocation and bundle queued (1 unfinished item).
-- This does NOT prove ChatGPT's native scheduler calls this APEX path.
