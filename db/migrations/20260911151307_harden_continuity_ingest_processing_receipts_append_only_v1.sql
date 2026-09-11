-- Preserve only the ingest-receipt substrate this hardening actually needs.
-- If an older runtime already created it, these guards are no-ops. On a clean replay,
-- the surviving migration can establish the ledger without depending on a deleted branch.

alter table public.continuity_ingest_queue_v1
  add column if not exists processing_owner text,
  add column if not exists lease_expires_at timestamptz,
  add column if not exists attempt_count integer not null default 0,
  add column if not exists last_attempt_at timestamptz;

create table if not exists public.continuity_ingest_processing_receipts_v1 (
  receipt_id uuid primary key default gen_random_uuid(),
  ingest_id uuid not null references public.continuity_ingest_queue_v1(ingest_id) on delete restrict,
  worker_id text not null,
  from_state text not null,
  to_state text not null,
  payload_hash text not null,
  outcome text not null check (outcome in ('claimed','normalized','processed','error','lease_released')),
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- Existing runtimes may have created the FK with ON DELETE CASCADE. Preserve the
-- receipt ledger by upgrading that relationship in place.
alter table public.continuity_ingest_processing_receipts_v1
  drop constraint if exists continuity_ingest_processing_receipts_v1_ingest_id_fkey;
alter table public.continuity_ingest_processing_receipts_v1
  add constraint continuity_ingest_processing_receipts_v1_ingest_id_fkey
  foreign key (ingest_id) references public.continuity_ingest_queue_v1(ingest_id) on delete restrict;

alter table public.continuity_ingest_processing_receipts_v1 enable row level security;
create index if not exists continuity_ingest_processing_receipts_v1_ingest_idx
  on public.continuity_ingest_processing_receipts_v1 (ingest_id, created_at desc);

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
