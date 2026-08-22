create extension if not exists pgcrypto;
create schema if not exists forensic;

revoke all on schema forensic from public;
grant usage on schema forensic to postgres, service_role;

create table if not exists forensic.matters (
  matter_id text primary key,
  title text not null,
  owner text,
  authority_state text not null default 'observed_only' check (authority_state in ('observed_only','approved_collection','legal_hold','closed')),
  authority_reference text,
  jurisdiction text,
  retention_status text not null default 'active' check (retention_status in ('active','hold','closed','disposed')),
  privilege_rules jsonb not null default '{}'::jsonb,
  approved_scope jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists forensic.evidence_items (
  evidence_id text primary key,
  matter_id text not null references forensic.matters(matter_id) on delete restrict,
  source_provider text not null,
  source_file_id text not null,
  source_revision text,
  source_path_ns text not null,
  source_path_display text,
  original_filename text not null,
  media_type text,
  byte_size bigint check (byte_size is null or byte_size >= 0),
  sha256 text check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$'),
  hash_status text not null default 'not_acquired' check (hash_status in ('not_acquired','pending','verified','mismatch','unavailable')),
  plane text not null default 'source' check (plane in ('source','evidence','working','case')),
  client_modified timestamptz,
  server_modified timestamptz,
  observed_at timestamptz not null default now(),
  access_class text not null default 'restricted',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create unique index if not exists evidence_source_identity_uq on forensic.evidence_items(source_provider, source_file_id);
create index if not exists evidence_matter_idx on forensic.evidence_items(matter_id);
create index if not exists evidence_sha_idx on forensic.evidence_items(sha256) where sha256 is not null;

create table if not exists forensic.acquisitions (
  acquisition_id text primary key,
  evidence_id text not null references forensic.evidence_items(evidence_id) on delete restrict,
  method text not null,
  collector text not null,
  source_revision text,
  source_hash text check (source_hash is null or source_hash ~ '^[0-9a-f]{64}$'),
  destination_hash text check (destination_hash is null or destination_hash ~ '^[0-9a-f]{64}$'),
  byte_size bigint check (byte_size is null or byte_size >= 0),
  tool_name text not null,
  tool_version text not null,
  manifest_id text,
  transfer_verified boolean not null default false,
  started_at timestamptz,
  completed_at timestamptz,
  exception_notes text,
  created_at timestamptz not null default now()
);

create table if not exists forensic.processing_jobs (
  job_id text primary key,
  matter_id text not null references forensic.matters(matter_id) on delete restrict,
  evidence_id text references forensic.evidence_items(evidence_id) on delete restrict,
  job_type text not null,
  idempotency_key text not null unique,
  status text not null default 'queued' check (status in ('queued','running','succeeded','failed','quarantined','cancelled')),
  recipe_hash text check (recipe_hash is null or recipe_hash ~ '^[0-9a-f]{64}$'),
  attempts integer not null default 0 check (attempts >= 0),
  error_code text,
  error_detail text,
  queued_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  receipt jsonb not null default '{}'::jsonb
);

create table if not exists forensic.derivatives (
  derivative_id text primary key,
  evidence_id text not null references forensic.evidence_items(evidence_id) on delete restrict,
  transformation_type text not null,
  recipe jsonb not null,
  recipe_hash text not null check (recipe_hash ~ '^[0-9a-f]{64}$'),
  input_sha256 text not null check (input_sha256 ~ '^[0-9a-f]{64}$'),
  output_sha256 text not null check (output_sha256 ~ '^[0-9a-f]{64}$'),
  tool_name text not null,
  tool_version text not null,
  job_id text references forensic.processing_jobs(job_id) on delete restrict,
  reviewer text,
  review_status text not null default 'lead' check (review_status in ('lead','reviewed','accepted','rejected')),
  intended_use text,
  visible_label text not null default 'DERIVATIVE FOR REVIEW',
  created_at timestamptz not null default now()
);
create index if not exists derivatives_parent_idx on forensic.derivatives(evidence_id);

create table if not exists forensic.custody_events (
  event_seq bigserial primary key,
  event_id uuid not null default gen_random_uuid() unique,
  evidence_id text not null references forensic.evidence_items(evidence_id) on delete restrict,
  event_time timestamptz not null default clock_timestamp(),
  actor text not null,
  actor_role text not null,
  action text not null,
  purpose text,
  source_location text,
  target_location text,
  before_sha256 text check (before_sha256 is null or before_sha256 ~ '^[0-9a-f]{64}$'),
  after_sha256 text check (after_sha256 is null or after_sha256 ~ '^[0-9a-f]{64}$'),
  job_id text references forensic.processing_jobs(job_id) on delete restrict,
  metadata jsonb not null default '{}'::jsonb,
  previous_event_hash text check (previous_event_hash is null or previous_event_hash ~ '^[0-9a-f]{64}$'),
  event_hash text not null check (event_hash ~ '^[0-9a-f]{64}$'),
  signature text,
  signature_status text not null default 'unsigned' check (signature_status in ('unsigned','signed','verified','invalid'))
);
create index if not exists custody_evidence_seq_idx on forensic.custody_events(evidence_id, event_seq);

create table if not exists forensic.findings (
  finding_id text primary key,
  matter_id text not null references forensic.matters(matter_id) on delete restrict,
  finding_type text not null,
  proposition text not null,
  method text,
  confidence_category text not null default 'lead' check (confidence_category in ('lead','low','medium','high','confirmed')),
  review_status text not null default 'lead' check (review_status in ('lead','reviewed','accepted','rejected')),
  reviewer text,
  corroboration_state text not null default 'single_source' check (corroboration_state in ('single_source','corroborated','contradicted','unknown')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  reviewed_at timestamptz
);

create table if not exists forensic.source_anchors (
  anchor_id uuid primary key default gen_random_uuid(),
  finding_id text not null references forensic.findings(finding_id) on delete cascade,
  evidence_id text not null references forensic.evidence_items(evidence_id) on delete restrict,
  anchor_type text not null check (anchor_type in ('page','paragraph','timecode','audio_offset','image_region','byte_offset','whole_item')),
  locator jsonb not null,
  quoted_text text,
  created_at timestamptz not null default now()
);
create index if not exists source_anchor_finding_idx on forensic.source_anchors(finding_id);
create index if not exists source_anchor_evidence_idx on forensic.source_anchors(evidence_id);

create table if not exists forensic.duplicate_families (
  duplicate_family_id text primary key,
  matter_id text not null references forensic.matters(matter_id) on delete restrict,
  duplicate_type text not null check (duplicate_type in ('exact_sha256','near_candidate')),
  basis jsonb not null,
  review_status text not null default 'lead' check (review_status in ('lead','reviewed','accepted','rejected')),
  created_at timestamptz not null default now()
);

create table if not exists forensic.duplicate_family_members (
  duplicate_family_id text not null references forensic.duplicate_families(duplicate_family_id) on delete cascade,
  evidence_id text not null references forensic.evidence_items(evidence_id) on delete restrict,
  source_location_retained boolean not null default true,
  primary key (duplicate_family_id, evidence_id)
);

create table if not exists forensic.review_decisions (
  decision_id uuid primary key default gen_random_uuid(),
  matter_id text not null references forensic.matters(matter_id) on delete restrict,
  object_type text not null,
  object_id text not null,
  reviewer text not null,
  decision text not null check (decision in ('accept','reject','needs_more','escalate')),
  rationale text,
  decided_at timestamptz not null default now()
);

create table if not exists forensic.production_items (
  production_item_id text primary key,
  matter_id text not null references forensic.matters(matter_id) on delete restrict,
  evidence_id text not null references forensic.evidence_items(evidence_id) on delete restrict,
  derivative_id text references forensic.derivatives(derivative_id) on delete restrict,
  production_hash text not null check (production_hash ~ '^[0-9a-f]{64}$'),
  approval_state text not null default 'candidate' check (approval_state in ('candidate','approved','released','withdrawn')),
  approved_by text,
  recipient text,
  released_at timestamptz,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists forensic.integrity_checks (
  integrity_check_id uuid primary key default gen_random_uuid(),
  matter_id text not null references forensic.matters(matter_id) on delete restrict,
  evidence_id text references forensic.evidence_items(evidence_id) on delete restrict,
  check_type text not null,
  expected_hash text check (expected_hash is null or expected_hash ~ '^[0-9a-f]{64}$'),
  observed_hash text check (observed_hash is null or observed_hash ~ '^[0-9a-f]{64}$'),
  status text not null check (status in ('pass','fail','not_run','blocked')),
  tool_name text,
  tool_version text,
  checked_at timestamptz not null default now(),
  detail jsonb not null default '{}'::jsonb
);

create table if not exists forensic.pilot_runs (
  pilot_run_id text primary key,
  matter_id text not null references forensic.matters(matter_id) on delete restrict,
  source_provider text not null,
  source_scope text not null,
  observation_count integer not null check (observation_count >= 0),
  manifest_sha256 text check (manifest_sha256 is null or manifest_sha256 ~ '^[0-9a-f]{64}$'),
  status text not null check (status in ('observed','manifested','acquired','failed')),
  read_only boolean not null default true,
  receipt jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create or replace function forensic.reject_mutation() returns trigger language plpgsql as $$
begin
  raise exception 'forensic append-only record cannot be %', tg_op;
end;
$$;

drop trigger if exists custody_events_no_update on forensic.custody_events;
create trigger custody_events_no_update before update on forensic.custody_events for each row execute function forensic.reject_mutation();
drop trigger if exists custody_events_no_delete on forensic.custody_events;
create trigger custody_events_no_delete before delete on forensic.custody_events for each row execute function forensic.reject_mutation();

create or replace function forensic.prepare_custody_event() returns trigger language plpgsql as $$
declare
  prev_hash text;
  payload jsonb;
begin
  perform pg_advisory_xact_lock(hashtextextended(new.evidence_id, 0));
  select ce.event_hash into prev_hash from forensic.custody_events ce where ce.evidence_id = new.evidence_id order by ce.event_seq desc limit 1;
  new.previous_event_hash := prev_hash;
  if new.event_time is null then new.event_time := clock_timestamp(); end if;
  payload := jsonb_build_object('event_id', new.event_id, 'evidence_id', new.evidence_id, 'event_time', new.event_time, 'actor', new.actor, 'actor_role', new.actor_role, 'action', new.action, 'purpose', new.purpose, 'source_location', new.source_location, 'target_location', new.target_location, 'before_sha256', new.before_sha256, 'after_sha256', new.after_sha256, 'job_id', new.job_id, 'metadata', new.metadata);
  new.event_hash := encode(digest(convert_to(coalesce(prev_hash,'') || payload::text, 'UTF8'), 'sha256'), 'hex');
  return new;
end;
$$;

drop trigger if exists custody_events_hash_chain on forensic.custody_events;
create trigger custody_events_hash_chain before insert on forensic.custody_events for each row execute function forensic.prepare_custody_event();

comment on schema forensic is 'APEX forensic-integrity evidence operating system: source observations, acquisitions, derivatives, custody, findings, production, and integrity checks.';
comment on table forensic.evidence_items is 'Source identity is provider ID; SHA-256 remains null until byte-preserving acquisition occurs.';
comment on table forensic.custody_events is 'Append-only, per-evidence hash-chained custody ledger. Corrections must be appended as new events.';

alter table forensic.matters enable row level security;
alter table forensic.evidence_items enable row level security;
alter table forensic.acquisitions enable row level security;
alter table forensic.derivatives enable row level security;
alter table forensic.processing_jobs enable row level security;
alter table forensic.custody_events enable row level security;
alter table forensic.findings enable row level security;
alter table forensic.source_anchors enable row level security;
alter table forensic.duplicate_families enable row level security;
alter table forensic.duplicate_family_members enable row level security;
alter table forensic.review_decisions enable row level security;
alter table forensic.production_items enable row level security;
alter table forensic.integrity_checks enable row level security;
alter table forensic.pilot_runs enable row level security;
