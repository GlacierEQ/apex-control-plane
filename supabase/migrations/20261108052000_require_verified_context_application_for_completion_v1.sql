-- Harden the original Hourly User-Benefit Overhaul completion owner.
-- Previously 'hydrated' + fresh packet was misnamed as 'applied' although
-- it did not establish any downstream consumer effect.
-- Require the existing action binding to carry a packet/hash-matched,
-- provider-readback context application receipt and observed effect.
-- This gates only the success label; it does not block independent work,
-- change schedulers, delete evidence or force completion.
-- The consumer must independently establish the receipt; a metadata claim
-- without real provider evidence is not proof of application.

CREATE OR REPLACE FUNCTION private.enforce_hourly_user_benefit_completion_v1()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'public', 'private'
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
$function$

