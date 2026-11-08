-- Live fail-closed repair for GlacierEQ APEX connector completion.
-- Original historical provider records are left untouched.
-- Former complete_connector_bundle auto-promoted queued items without provider calls.
-- Require item-level and bundle-level readback claims; this rejects empty/queued work.
-- For read_only work, record zero mutations. The originating provider evidence
-- is still independently subject to validation by its actual execution host.
-- Rollback: restore the prior function definition from provider migration history.
CREATE OR REPLACE FUNCTION public.complete_connector_bundle(p_bundle_id uuid, p_worker_name text, p_result_summary jsonb, p_receipt jsonb, p_verification_state text DEFAULT 'READ_BACK'::text, p_raw_provider_call_count integer DEFAULT 0, p_provider_phase_count integer DEFAULT 0, p_bytes_in bigint DEFAULT 0, p_bytes_out bigint DEFAULT 0, p_base_ref text DEFAULT NULL::text, p_final_ref text DEFAULT NULL::text, p_cursor jsonb DEFAULT NULL::jsonb, p_watermark text DEFAULT NULL::text)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_catalog', 'pg_temp'
AS $function$
declare v_connector text;v_scope text;v_items integer;v_budget integer;v_started timestamptz;v_safety_mode text;v_total_items integer;v_evidenced_items integer;
begin
  select connector_key,scope_key,item_count,provider_phase_budget,started_at,safety_mode into v_connector,v_scope,v_items,v_budget,v_started,v_safety_mode
    from public.connector_work_bundles where id=p_bundle_id and lease_owner=p_worker_name and status in ('leased','running');
  if not found then return false; end if;
  if p_provider_phase_count>v_budget then raise exception 'provider phase count % exceeds bundle budget %',p_provider_phase_count,v_budget; end if;
  -- A provider invocation cannot complete unexecuted items. Do not forge item receipts.
  select count(*)::integer,
    count(*) filter (where status='completed'
      and jsonb_typeof(result)='object'
      and nullif(btrim(result->>'provider_ref'),'') is not null
      and nullif(btrim(result->>'readback_ref'),'') is not null
      and coalesce(error,'{}'::jsonb)='{}'::jsonb)::integer
    into v_total_items,v_evidenced_items
    from public.connector_bundle_items where bundle_id=p_bundle_id;
  if v_items < 1 or v_total_items <> v_items or v_evidenced_items <> v_items then
    raise exception using errcode='check_violation',
      message='bundle_completion_requires_item_provider_evidence';
  end if;
  if p_raw_provider_call_count < 1 or p_provider_phase_count < 1
      or jsonb_typeof(p_receipt) <> 'object'
      or nullif(btrim(p_receipt->>'provider_ref'),'') is null
      or nullif(btrim(p_receipt->>'readback_ref'),'') is null
      or coalesce(p_receipt->>'provider_ref','') <> coalesce(p_result_summary->>'provider_ref','')
      or coalesce(p_receipt->>'readback_ref','') <> coalesce(p_result_summary->>'readback_ref','') then
    raise exception using errcode='check_violation',
      message='bundle_completion_requires_native_provider_readback_receipt';
  end if;
  update public.connector_work_bundles set status='completed',completed_item_count=v_items,result_summary=coalesce(p_result_summary,'{}'::jsonb),
    bytes_in=p_bytes_in,bytes_out=p_bytes_out,source_ref=coalesce(source_ref,p_base_ref),target_ref=p_final_ref,
    lease_owner=null,lease_expires_at=null,completed_at=now(),updated_at=now() where id=p_bundle_id;
  insert into public.connector_provider_sessions(bundle_id,connector_key,worker_name,acquisition_started_at,acquisition_completed_at,mutation_started_at,mutation_completed_at,readback_completed_at,raw_provider_call_count,logical_provider_phase_count,records_hydrated,records_mutated,bytes_hydrated,bytes_published,base_ref,final_ref,status,metadata,completed_at)
  values(p_bundle_id,v_connector,p_worker_name,v_started,case when p_provider_phase_count>=1 then now() else null end,
    case when p_provider_phase_count>=2 then v_started else null end,case when p_provider_phase_count>=2 then now() else null end,
    case when p_verification_state in ('READ_BACK','ACTIVE_VERIFIED','PROVIDER_READBACK') then now() else null end,
    p_raw_provider_call_count,p_provider_phase_count,v_items,case when v_safety_mode='read_only' then 0 else v_items end,p_bytes_in,p_bytes_out,p_base_ref,p_final_ref,'completed',
    jsonb_build_object('verification_state',p_verification_state,'receipt',coalesce(p_receipt,'{}'::jsonb)),now());
  insert into public.connector_consolidated_receipts(bundle_id,connector_key,verification_state,provider_phase_count,raw_provider_call_count,item_count,bytes_in,bytes_out,base_ref,final_ref,receipt)
  values(p_bundle_id,v_connector,p_verification_state,p_provider_phase_count,p_raw_provider_call_count,v_items,p_bytes_in,p_bytes_out,p_base_ref,p_final_ref,coalesce(p_receipt,'{}'::jsonb))
  on conflict(bundle_id,receipt_type) do update set verification_state=excluded.verification_state,provider_phase_count=excluded.provider_phase_count,
    raw_provider_call_count=excluded.raw_provider_call_count,item_count=excluded.item_count,bytes_in=excluded.bytes_in,bytes_out=excluded.bytes_out,
    base_ref=excluded.base_ref,final_ref=excluded.final_ref,receipt=excluded.receipt,created_at=now();
  if p_cursor is not null then
    insert into public.connector_high_volume_cursors(connector_key,scope_key,cursor,watermark,observed_at)
      values(v_connector,v_scope,p_cursor,p_watermark,now())
    on conflict(connector_key,scope_key) do update set cursor=excluded.cursor,watermark=excluded.watermark,observed_at=excluded.observed_at;
  end if;
  return true;
end $function$

