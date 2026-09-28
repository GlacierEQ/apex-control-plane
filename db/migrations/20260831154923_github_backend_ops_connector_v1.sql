-- GitHub Backend Ops connector v1
-- Mirrors the live supabase-backend-ops schema installed 2026-08-31.
-- GitHub remains source/schema authority; this migration is rebuildable and idempotent.

create table if not exists public.github_connector_receipts_v1 (
  receipt_id uuid primary key default gen_random_uuid(),
  request_id text not null,
  correlation_id uuid not null default gen_random_uuid(),
  connector_key text not null default 'github.backend_ops',
  operation text not null,
  repository text,
  target_ref text,
  mutation_class text not null check (mutation_class in ('read','write','trigger','admin')),
  outcome text not null check (outcome in ('succeeded','failed','rejected')),
  request_hash text not null,
  response_hash text,
  github_request_id text,
  readback_verified boolean not null default false,
  before_sha text,
  after_sha text,
  duration_ms integer check (duration_ms is null or duration_ms >= 0),
  actor text,
  result_summary jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists github_connector_receipts_v1_successful_write_request_uq
  on public.github_connector_receipts_v1(request_id)
  where mutation_class = 'write' and outcome = 'succeeded';

create index if not exists github_connector_receipts_v1_repo_created_idx
  on public.github_connector_receipts_v1(repository, created_at desc);

create index if not exists github_connector_receipts_v1_operation_created_idx
  on public.github_connector_receipts_v1(operation, created_at desc);

create table if not exists public.github_webhook_deliveries_v1 (
  delivery_id text primary key,
  event_type text not null,
  action text,
  repository text,
  sender_login text,
  payload_sha256 text not null,
  signature_verified boolean not null,
  processing_status text not null default 'received'
    check (processing_status in ('received','accepted','ignored','processed','failed')),
  metadata jsonb not null default '{}'::jsonb,
  received_at timestamptz not null default now(),
  processed_at timestamptz
);

create index if not exists github_webhook_deliveries_v1_repo_received_idx
  on public.github_webhook_deliveries_v1(repository, received_at desc);

create index if not exists github_webhook_deliveries_v1_event_received_idx
  on public.github_webhook_deliveries_v1(event_type, received_at desc);

create table if not exists public.github_connector_config_v1 (
  connector_key text primary key,
  owner_login text not null,
  mode text not null default 'pr_first' check (mode in ('pr_first')),
  allow_default_branch_writes boolean not null default false,
  destructive_actions_allowed boolean not null default false,
  webhook_secret_ref text,
  bootstrap_ref text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.github_connector_receipts_v1 enable row level security;
alter table public.github_webhook_deliveries_v1 enable row level security;
alter table public.github_connector_config_v1 enable row level security;

revoke all on public.github_connector_receipts_v1 from public, anon, authenticated;
revoke all on public.github_webhook_deliveries_v1 from public, anon, authenticated;
revoke all on public.github_connector_config_v1 from public, anon, authenticated;

grant select, insert on public.github_connector_receipts_v1 to service_role;
grant select, insert, update on public.github_webhook_deliveries_v1 to service_role;
grant select, insert, update on public.github_connector_config_v1 to service_role;

create or replace function public.github_connector_receipts_v1_block_mutation()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  raise exception 'github_connector_receipts_v1 is append-only';
end;
$$;

revoke all on function public.github_connector_receipts_v1_block_mutation() from public, anon, authenticated;
grant execute on function public.github_connector_receipts_v1_block_mutation() to service_role;

drop trigger if exists github_connector_receipts_v1_immutable on public.github_connector_receipts_v1;
create trigger github_connector_receipts_v1_immutable
before update or delete on public.github_connector_receipts_v1
for each row execute function public.github_connector_receipts_v1_block_mutation();

comment on table public.github_connector_receipts_v1 is
  'Append-only GitHub backend-ops execution receipts. No GitHub credential or raw secret may be persisted.';
comment on table public.github_webhook_deliveries_v1 is
  'Deduplicated GitHub webhook delivery metadata and payload hashes; raw credentials are never stored.';
comment on table public.github_connector_config_v1 is
  'Backend-ops GitHub gateway configuration. Default-branch writes and destructive actions are hard-disabled.';
