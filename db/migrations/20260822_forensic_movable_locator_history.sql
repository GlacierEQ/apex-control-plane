create table if not exists forensic.evidence_locator_observations (
  observation_id uuid primary key default gen_random_uuid(),
  evidence_id text not null references forensic.evidence_items(evidence_id) on delete restrict,
  provider text not null,
  account_ref text,
  provider_file_id text,
  provider_revision text,
  locator text not null,
  display_locator text,
  filename text,
  byte_size bigint,
  sha256 text,
  hash_status text not null default 'not_verified'
    check (hash_status in ('verified','not_verified','pending','mismatch','unavailable')),
  observation_kind text not null default 'observed'
    check (observation_kind in ('observed','moved','renamed','copied','restored','missing','transfer_verified','transfer_pending')),
  observed_at timestamptz not null default now(),
  actor text,
  source_observation_id uuid references forensic.evidence_locator_observations(observation_id) on delete restrict,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$')
);

create index if not exists idx_forensic_locator_evidence_time
  on forensic.evidence_locator_observations(evidence_id, observed_at desc);
create index if not exists idx_forensic_locator_provider_id
  on forensic.evidence_locator_observations(provider, provider_file_id, observed_at desc);
create index if not exists idx_forensic_locator_sha256
  on forensic.evidence_locator_observations(sha256) where sha256 is not null;
create index if not exists idx_forensic_locator_locator
  on forensic.evidence_locator_observations(locator);

alter table forensic.evidence_locator_observations enable row level security;

drop trigger if exists evidence_locator_observations_no_update_delete
  on forensic.evidence_locator_observations;
create trigger evidence_locator_observations_no_update_delete
before update or delete on forensic.evidence_locator_observations
for each row execute function forensic.reject_mutation();

create or replace view forensic.evidence_current_locations
with (security_invoker=true) as
select distinct on (evidence_id, provider, coalesce(provider_file_id, ''))
  observation_id,
  evidence_id,
  provider,
  account_ref,
  provider_file_id,
  provider_revision,
  locator,
  display_locator,
  filename,
  byte_size,
  sha256,
  hash_status,
  observation_kind,
  observed_at,
  actor,
  metadata
from forensic.evidence_locator_observations
order by evidence_id, provider, coalesce(provider_file_id, ''), observed_at desc, created_at desc;

insert into forensic.evidence_locator_observations (
  evidence_id, provider, provider_file_id, provider_revision,
  locator, display_locator, filename, byte_size, sha256, hash_status,
  observation_kind, observed_at, actor, metadata
)
select
  e.evidence_id,
  e.source_provider,
  e.source_file_id,
  e.source_revision,
  e.source_path_ns,
  e.source_path_display,
  e.original_filename,
  e.byte_size,
  e.sha256,
  case
    when e.hash_status = 'verified' then 'verified'
    when e.hash_status = 'mismatch' then 'mismatch'
    when e.hash_status = 'not_acquired' then 'unavailable'
    else 'not_verified'
  end,
  'observed',
  e.observed_at,
  'forensic_movable_locator_history_backfill',
  jsonb_build_object(
    'migration_backfill', true,
    'meaning', 'first observed locator; path is not evidence identity'
  )
from forensic.evidence_items e
where not exists (
  select 1
  from forensic.evidence_locator_observations l
  where l.evidence_id = e.evidence_id
    and l.provider = e.source_provider
    and coalesce(l.provider_file_id, '') = coalesce(e.source_file_id, '')
    and l.locator = e.source_path_ns
);

comment on column forensic.evidence_items.source_path_ns is
  'First observed source locator. Not a stable evidence identity and not guaranteed to remain current.';
comment on column forensic.evidence_items.source_path_display is
  'First observed human-readable source locator. Current location is derived from forensic.evidence_locator_observations.';
comment on table forensic.evidence_locator_observations is
  'Append-only history of where an evidence item was observed. Storage location may change without changing Evidence ID.';
