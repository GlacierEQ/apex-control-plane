-- Lock the ingest-processing receipt ledger to append-only evidence semantics.
-- Workflow mutation occurs through SECURITY DEFINER functions; callers do not need
-- direct INSERT/UPDATE/DELETE/TRUNCATE authority on the receipt table itself.

revoke all on table public.continuity_ingest_processing_receipts_v1 from service_role;
grant select on table public.continuity_ingest_processing_receipts_v1 to service_role;

create or replace function public.continuity_ingest_processing_receipts_append_only_v1()
returns trigger
language plpgsql
set search_path='public','pg_temp'
as $$
begin
  raise exception 'continuity_ingest_processing_receipts_v1 is append-only';
end;
$$;

drop trigger if exists continuity_ingest_processing_receipts_append_only
  on public.continuity_ingest_processing_receipts_v1;
create trigger continuity_ingest_processing_receipts_append_only
before update or delete on public.continuity_ingest_processing_receipts_v1
for each row execute function public.continuity_ingest_processing_receipts_append_only_v1();

drop policy if exists continuity_ingest_processing_receipts_client_deny_v1
  on public.continuity_ingest_processing_receipts_v1;
create policy continuity_ingest_processing_receipts_client_deny_v1
on public.continuity_ingest_processing_receipts_v1
for all
to anon, authenticated
using (false)
with check (false);
