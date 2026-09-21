create extension if not exists pgcrypto;

create table if not exists public.oa_agent_genomes_v1 (
  logical_agent_id text primary key,
  runtime_agent_id uuid null,
  parent_logical_agent_id text null references public.oa_agent_genomes_v1(logical_agent_id) on delete restrict,
  domain_key text not null,
  display_name text not null,
  purpose text,
  lifecycle text not null check (lifecycle in ('SEED','HATCHED','PROBATION','ACTIVE','DEGRADED','BLOCKED','QUARANTINED','SUSPENDED','UPGRADING','RETIRED','ARCHIVED')),
  current_version text not null,
  continuity_priority smallint not null default 1 check (continuity_priority = 1),
  operator_root text not null default 'OPERATOR',
  authority_source text not null default 'OPERATOR',
  jurisdiction jsonb not null default '{}'::jsonb,
  scope_boundaries jsonb not null default '{}'::jsonb,
  continuity_contract jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.oa_agent_genome_versions_v1 (
  genome_version_id uuid primary key default gen_random_uuid(),
  logical_agent_id text not null references public.oa_agent_genomes_v1(logical_agent_id) on delete restrict,
  version text not null,
  genome jsonb not null,
  genome_sha256 text not null check (genome_sha256 ~ '^[0-9a-f]{64}$'),
  previous_version_id uuid null references public.oa_agent_genome_versions_v1(genome_version_id) on delete restrict,
  activation_status text not null default 'ACTIVE' check (activation_status in ('CANDIDATE','ACTIVE','SUPERSEDED','QUARANTINED','RETIRED')),
  created_by text not null,
  created_source_class text not null check (created_source_class in ('OPERATOR','AGENT','SYSTEM','EVIDENCE','MIGRATION')),
  created_at timestamptz not null default now(),
  activated_at timestamptz,
  unique (logical_agent_id, version),
  check (
    jsonb_typeof(genome) = 'object'
    and genome ->> 'schema' = 'glaciereq.operator-agent-genome.v1'
    and jsonb_typeof(genome -> 'chromosomes') = 'object'
    and (genome -> 'chromosomes') ?& array[
      'continuity','authority','identity_lineage','mission','cognition',
      'knowledge_memory','capability','execution','evidence_provenance',
      'verification','integrity_security','administration_observability'
    ]
  )
);

create table if not exists public.oa_agent_delegations_v1 (
  delegation_id uuid primary key default gen_random_uuid(),
  logical_agent_id text not null references public.oa_agent_genomes_v1(logical_agent_id) on delete restrict,
  authority_source text not null default 'OPERATOR',
  mission_ref text,
  scope jsonb not null default '{}'::jsonb,
  capability_constraints jsonb not null default '{}'::jsonb,
  valid_from timestamptz not null default now(),
  valid_until timestamptz,
  revoked_at timestamptz,
  status text not null default 'ACTIVE' check (status in ('ACTIVE','EXPIRED','REVOKED','SUPERSEDED')),
  grant_sha256 text not null check (grant_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now()
);

create table if not exists public.oa_administration_events_v1 (
  admin_event_id uuid primary key default gen_random_uuid(),
  logical_agent_id text not null references public.oa_agent_genomes_v1(logical_agent_id) on delete restrict,
  event_type text not null,
  source_continuity_event_id uuid null,
  parent_admin_event_id uuid null references public.oa_administration_events_v1(admin_event_id) on delete restrict,
  payload jsonb not null default '{}'::jsonb,
  payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  created_by text not null,
  created_source_class text not null check (created_source_class in ('OPERATOR','AGENT','SYSTEM','EVIDENCE','MIGRATION')),
  created_at timestamptz not null default now()
);

create table if not exists public.oa_continuity_heads_v1 (
  continuity_head_id uuid primary key default gen_random_uuid(),
  logical_agent_id text not null references public.oa_agent_genomes_v1(logical_agent_id) on delete restrict,
  sequence bigint not null check (sequence > 0),
  previous_head_id uuid null references public.oa_continuity_heads_v1(continuity_head_id) on delete restrict,
  genome_version_id uuid not null references public.oa_agent_genome_versions_v1(genome_version_id) on delete restrict,
  source_continuity_event_id uuid null,
  state jsonb not null,
  state_sha256 text not null check (state_sha256 ~ '^[0-9a-f]{64}$'),
  recovery_instructions jsonb not null default '{}'::jsonb,
  verified boolean not null default false,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  unique (logical_agent_id, sequence),
  check ((verified = true and verified_at is not null) or (verified = false and verified_at is null))
);


-- Optional estate dependencies are bound when present. The migration remains
-- installable in a fresh control plane where legacy runtime/continuity tables
-- have not yet been created.
do $$
begin
  if to_regclass('public.agents') is not null
     and not exists (
       select 1 from pg_constraint
       where conname = 'oa_agent_genomes_runtime_agent_fk'
         and conrelid = 'public.oa_agent_genomes_v1'::regclass
     ) then
    alter table public.oa_agent_genomes_v1
      add constraint oa_agent_genomes_runtime_agent_fk
      foreign key (runtime_agent_id) references public.agents(id) on delete set null;
  end if;

  if to_regclass('public.continuity_events_v1') is not null then
    if not exists (
      select 1 from pg_constraint
      where conname = 'oa_admin_events_source_continuity_event_fk'
        and conrelid = 'public.oa_administration_events_v1'::regclass
    ) then
      alter table public.oa_administration_events_v1
        add constraint oa_admin_events_source_continuity_event_fk
        foreign key (source_continuity_event_id)
        references public.continuity_events_v1(event_id) on delete restrict;
    end if;

    if not exists (
      select 1 from pg_constraint
      where conname = 'oa_continuity_heads_source_continuity_event_fk'
        and conrelid = 'public.oa_continuity_heads_v1'::regclass
    ) then
      alter table public.oa_continuity_heads_v1
        add constraint oa_continuity_heads_source_continuity_event_fk
        foreign key (source_continuity_event_id)
        references public.continuity_events_v1(event_id) on delete restrict;
    end if;
  end if;
end;
$$;

create unique index if not exists oa_agent_genomes_runtime_agent_idx
  on public.oa_agent_genomes_v1(runtime_agent_id)
  where runtime_agent_id is not null;

create index if not exists oa_agent_genome_versions_agent_created_idx
  on public.oa_agent_genome_versions_v1(logical_agent_id, created_at desc);

create index if not exists oa_agent_delegations_agent_status_idx
  on public.oa_agent_delegations_v1(logical_agent_id, status);

create index if not exists oa_admin_events_agent_created_idx
  on public.oa_administration_events_v1(logical_agent_id, created_at desc);

create index if not exists oa_continuity_heads_agent_sequence_idx
  on public.oa_continuity_heads_v1(logical_agent_id, sequence desc);


create or replace function public.oa_source_class_v1(p_identity text)
returns text
language sql
immutable
set search_path = pg_catalog, public
as $$
  select case
    when p_identity = 'OPERATOR' then 'OPERATOR'
    when p_identity like 'agent:%' then 'AGENT'
    when p_identity like 'evidence:%' then 'EVIDENCE'
    when p_identity like 'migration:%' then 'MIGRATION'
    else 'SYSTEM'
  end;
$$;

create or replace function public.oa_validate_content_hash_v1()
returns trigger
language plpgsql
set search_path = pg_catalog, public, extensions
as $$
declare
  v_expected text;
begin
  if tg_table_name = 'oa_agent_genome_versions_v1' then
    v_expected := encode(digest(jsonb_strip_nulls(new.genome)::text, 'sha256'), 'hex');
    if new.genome_sha256 <> v_expected then
      raise exception 'genome_sha256 does not match genome payload';
    end if;
  elsif tg_table_name = 'oa_administration_events_v1' then
    v_expected := encode(digest(jsonb_strip_nulls(new.payload)::text, 'sha256'), 'hex');
    if new.payload_sha256 <> v_expected then
      raise exception 'payload_sha256 does not match event payload';
    end if;
  elsif tg_table_name = 'oa_continuity_heads_v1' then
    v_expected := encode(digest(jsonb_strip_nulls(new.state)::text, 'sha256'), 'hex');
    if new.state_sha256 <> v_expected then
      raise exception 'state_sha256 does not match continuity state';
    end if;
  end if;
  return new;
end;
$$;

create or replace function public.oa_reject_history_mutation_v1()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  raise exception '% is append-only; write a new record instead', tg_table_name;
end;
$$;

drop trigger if exists oa_genome_versions_append_only_v1 on public.oa_agent_genome_versions_v1;
create trigger oa_genome_versions_append_only_v1
before update or delete on public.oa_agent_genome_versions_v1
for each row execute function public.oa_reject_history_mutation_v1();

drop trigger if exists oa_genome_versions_hash_check_v1 on public.oa_agent_genome_versions_v1;
create trigger oa_genome_versions_hash_check_v1
before insert on public.oa_agent_genome_versions_v1
for each row execute function public.oa_validate_content_hash_v1();

drop trigger if exists oa_admin_events_hash_check_v1 on public.oa_administration_events_v1;
create trigger oa_admin_events_hash_check_v1
before insert on public.oa_administration_events_v1
for each row execute function public.oa_validate_content_hash_v1();

drop trigger if exists oa_continuity_heads_hash_check_v1 on public.oa_continuity_heads_v1;
create trigger oa_continuity_heads_hash_check_v1
before insert on public.oa_continuity_heads_v1
for each row execute function public.oa_validate_content_hash_v1();

drop trigger if exists oa_admin_events_append_only_v1 on public.oa_administration_events_v1;
create trigger oa_admin_events_append_only_v1
before update or delete on public.oa_administration_events_v1
for each row execute function public.oa_reject_history_mutation_v1();

drop trigger if exists oa_continuity_heads_append_only_v1 on public.oa_continuity_heads_v1;
create trigger oa_continuity_heads_append_only_v1
before update or delete on public.oa_continuity_heads_v1
for each row execute function public.oa_reject_history_mutation_v1();

create or replace function public.oa_hatch_agent_v1(
  p_logical_agent_id text,
  p_domain_key text,
  p_display_name text,
  p_purpose text,
  p_parent_logical_agent_id text,
  p_runtime_agent_id uuid,
  p_version text,
  p_genome jsonb,
  p_created_by text
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog, public, extensions
as $$
declare
  v_version_id uuid;
  v_event_id uuid;
  v_genome_hash text;
  v_event_payload jsonb;
  v_state jsonb;
  v_state_hash text;
  v_source_class text;
  v_request_role text;
begin
  v_request_role := coalesce(current_setting('request.jwt.claim.role', true), session_user);
  if session_user not in ('postgres','supabase_admin','service_role')
     and v_request_role <> 'service_role' then
    raise exception 'oa_hatch_agent_v1 requires service_role or migration owner';
  end if;

  if p_created_by is null or btrim(p_created_by) = '' then
    raise exception 'created_by identity is required';
  end if;
  v_source_class := public.oa_source_class_v1(p_created_by);
  if p_logical_agent_id is null or btrim(p_logical_agent_id) = '' then
    raise exception 'logical_agent_id is required';
  end if;

  if p_genome ->> 'schema' <> 'glaciereq.operator-agent-genome.v1' then
    raise exception 'invalid operator agent genome schema';
  end if;

  if jsonb_typeof(p_genome -> 'chromosomes') <> 'object'
     or not ((p_genome -> 'chromosomes') ?& array[
       'continuity','authority','identity_lineage','mission','cognition',
       'knowledge_memory','capability','execution','evidence_provenance',
       'verification','integrity_security','administration_observability'
     ]) then
    raise exception 'all 12 chromosomes are required';
  end if;

  v_genome_hash := encode(digest(jsonb_strip_nulls(p_genome)::text, 'sha256'), 'hex');

  insert into public.oa_agent_genomes_v1 (
    logical_agent_id, runtime_agent_id, parent_logical_agent_id, domain_key,
    display_name, purpose, lifecycle, current_version, continuity_priority,
    operator_root, authority_source, jurisdiction, scope_boundaries, continuity_contract
  ) values (
    p_logical_agent_id, p_runtime_agent_id, p_parent_logical_agent_id, p_domain_key,
    p_display_name, p_purpose, 'HATCHED', p_version, 1,
    'OPERATOR', 'OPERATOR', '{}'::jsonb, '{}'::jsonb,
    jsonb_build_object(
      'priority', 1,
      'recover_before_recreate', true,
      'continue_before_reconstructing', true,
      'provider_independent', true,
      'model_independent', true,
      'tool_independent', true
    )
  );

  insert into public.oa_agent_genome_versions_v1 (
    logical_agent_id, version, genome, genome_sha256, activation_status, created_by, created_source_class, activated_at
  ) values (
    p_logical_agent_id, p_version, p_genome, v_genome_hash, 'ACTIVE', p_created_by, v_source_class, now()
  )
  returning genome_version_id into v_version_id;

  v_event_payload := jsonb_build_object(
    'logical_agent_id', p_logical_agent_id,
    'version', p_version,
    'genome_sha256', v_genome_hash,
    'runtime_agent_id', p_runtime_agent_id,
    'event', 'HATCHED'
  );

  insert into public.oa_administration_events_v1 (
    logical_agent_id, event_type, payload, payload_sha256, created_by, created_source_class
  ) values (
    p_logical_agent_id,
    'AGENT_HATCHED',
    v_event_payload,
    encode(digest(jsonb_strip_nulls(v_event_payload)::text, 'sha256'), 'hex'),
    p_created_by,
    v_source_class
  )
  returning admin_event_id into v_event_id;

  v_state := jsonb_build_object(
    'logical_agent_id', p_logical_agent_id,
    'lifecycle', 'HATCHED',
    'genome_version', p_version,
    'genome_version_id', v_version_id,
    'runtime_agent_id', p_runtime_agent_id,
    'continuity_priority', 1,
    'administration_event_id', v_event_id
  );
  v_state_hash := encode(digest(jsonb_strip_nulls(v_state)::text, 'sha256'), 'hex');

  insert into public.oa_continuity_heads_v1 (
    logical_agent_id, sequence, genome_version_id, state, state_sha256,
    recovery_instructions, verified, verified_at
  ) values (
    p_logical_agent_id, 1, v_version_id, v_state, v_state_hash,
    jsonb_build_object(
      'law', 'RECOVER BEFORE RECREATING; CONTINUE BEFORE RECONSTRUCTING; COMPOUND BEFORE REPLACING',
      'load_genome_version_id', v_version_id,
      'resume_from_verified_state', true
    ),
    true, now()
  );

  return v_version_id;
end;
$$;

create or replace view public.oa_current_continuity_heads_v1
with (security_invoker = true)
as
select distinct on (h.logical_agent_id)
  h.continuity_head_id,
  h.logical_agent_id,
  h.sequence,
  h.previous_head_id,
  h.genome_version_id,
  h.source_continuity_event_id,
  h.state,
  h.state_sha256,
  h.recovery_instructions,
  h.verified,
  h.verified_at,
  h.created_at
from public.oa_continuity_heads_v1 h
where h.verified = true
order by h.logical_agent_id, h.sequence desc, h.created_at desc;

alter table public.oa_agent_genomes_v1 enable row level security;
alter table public.oa_agent_genome_versions_v1 enable row level security;
alter table public.oa_agent_delegations_v1 enable row level security;
alter table public.oa_administration_events_v1 enable row level security;
alter table public.oa_continuity_heads_v1 enable row level security;

revoke all on public.oa_agent_genomes_v1 from anon, authenticated;
revoke all on public.oa_agent_genome_versions_v1 from anon, authenticated;
revoke all on public.oa_agent_delegations_v1 from anon, authenticated;
revoke all on public.oa_administration_events_v1 from anon, authenticated;
revoke all on public.oa_continuity_heads_v1 from anon, authenticated;
revoke all on public.oa_current_continuity_heads_v1 from anon, authenticated;
revoke all on function public.oa_hatch_agent_v1(text,text,text,text,text,uuid,text,jsonb,text) from public, anon, authenticated;
revoke all on function public.oa_reject_history_mutation_v1() from public, anon, authenticated;
revoke all on function public.oa_validate_content_hash_v1() from public, anon, authenticated;
revoke all on function public.oa_source_class_v1(text) from public, anon, authenticated;

grant all on public.oa_agent_genomes_v1 to service_role;
grant all on public.oa_agent_genome_versions_v1 to service_role;
grant all on public.oa_agent_delegations_v1 to service_role;
grant all on public.oa_administration_events_v1 to service_role;
grant all on public.oa_continuity_heads_v1 to service_role;
grant select on public.oa_current_continuity_heads_v1 to service_role;
grant execute on function public.oa_hatch_agent_v1(text,text,text,text,text,uuid,text,jsonb,text) to service_role;

do $$
declare
  v_root_genome jsonb;
  a record;
  v_agent_genome jsonb;
  v_logical_id text;
begin
  if not exists (select 1 from public.oa_agent_genomes_v1 where logical_agent_id = 'OA.OPERATOR') then
    v_root_genome := jsonb_build_object(
      'schema','glaciereq.operator-agent-genome.v1',
      'chromosomes', jsonb_build_object(
        'continuity', jsonb_build_object('priority',1,'invariant','continuity_is_position_1'),
        'authority', jsonb_build_object('authority_holder','OPERATOR','root',true),
        'identity_lineage', jsonb_build_object('logical_agent_id','OA.OPERATOR','parent',null),
        'mission', jsonb_build_object('purpose','Root Operator administrative authority'),
        'cognition', jsonb_build_object('recover_before_recreate',true,'continue_before_reconstructing',true,'compound_before_replacing',true),
        'knowledge_memory', jsonb_build_object('provenance_required',true),
        'capability', jsonb_build_object('root_capability_grant',false),
        'execution', jsonb_build_object('blocked_route_changes_route_not_objective',true),
        'evidence_provenance', jsonb_build_object('provider_native_receipts_required',true),
        'verification', jsonb_build_object('readback_required',true),
        'integrity_security', jsonb_build_object('hash_algorithm','sha256','least_privilege',true),
        'administration_observability', jsonb_build_object('audit_required',true,'append_only_history',true)
      )
    );
    perform public.oa_hatch_agent_v1(
      'OA.OPERATOR','root','Operator','Root mission authority',null,null,'1.0.0',v_root_genome,'migration:operator_administration_genome_v1'
    );
  end if;

  if to_regclass('public.agents') is not null then
    for a in execute
      'select id, name, display_name, category, description, status from public.agents'
    loop
      v_logical_id := 'OA.RUNTIME.'
        || upper(regexp_replace(a.name, '[^a-zA-Z0-9]+', '_', 'g'))
        || '_'
        || upper(replace(a.id::text, '-', ''));

      if not exists (
        select 1 from public.oa_agent_genomes_v1
        where runtime_agent_id = a.id
      ) then
        v_agent_genome := jsonb_build_object(
          'schema','glaciereq.operator-agent-genome.v1',
          'chromosomes', jsonb_build_object(
            'continuity', jsonb_build_object('priority',1,'resumable',true,'source','legacy_runtime_import'),
            'authority', jsonb_build_object('authority_holder','OPERATOR','delegated',true),
            'identity_lineage', jsonb_build_object('logical_agent_id',v_logical_id,'parent','OA.OPERATOR','runtime_agent_id',a.id),
            'mission', jsonb_build_object('purpose',coalesce(a.description,a.display_name),'category',a.category),
            'cognition', jsonb_build_object('recover_before_recreate',true,'continue_before_reconstructing',true,'compound_before_replacing',true),
            'knowledge_memory', jsonb_build_object('provenance_required',true),
            'capability', jsonb_build_object('runtime_binding',a.id,'runtime_name',a.name),
            'execution', jsonb_build_object('blocked_route_changes_route_not_objective',true),
            'evidence_provenance', jsonb_build_object('provider_native_receipts_required',true),
            'verification', jsonb_build_object('readback_required',true),
            'integrity_security', jsonb_build_object('hash_algorithm','sha256','least_privilege',true),
            'administration_observability', jsonb_build_object('audit_required',true,'legacy_status',a.status)
          )
        );
        perform public.oa_hatch_agent_v1(
          v_logical_id,
          coalesce(nullif(a.category,''),'runtime'),
          a.display_name,
          a.description,
          'OA.OPERATOR',
          a.id,
          'legacy-1',
          v_agent_genome,
          'migration:operator_administration_genome_v1'
        );
      end if;
    end loop;
  end if;
end;
$$;

comment on table public.oa_agent_genomes_v1 is
  'Operator Administration logical agent identities. Continuity is priority 1; runtime executors are replaceable bindings.';
comment on table public.oa_agent_genome_versions_v1 is
  'Versioned 12-chromosome Operator Administration genomes with SHA-256 content identity.';
comment on table public.oa_administration_events_v1 is
  'Append-only administrative event ledger for agent lifecycle and genetic changes.';
comment on table public.oa_continuity_heads_v1 is
  'Append-only resumable state heads. New executors recover from the latest verified head.';
