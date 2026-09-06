create or replace view public.operator_runtime_context_current_v1 as
select
  profile_key,
  operator_name,
  principle,
  baseline_factors,
  shift_rules,
  source_routing,
  evaluation_loop,
  hard_constraint_note,
  ambient_invariant,
  interpretation_prelude,
  presence_surfaces,
  updated_at
from public.operator_decision_runtime_v1
where active = true
  and profile_key = 'casey_impact_weighted_v1';

create table if not exists public.operator_decision_events_v1 (
  id uuid primary key default gen_random_uuid(),
  profile_key text not null default 'casey_impact_weighted_v1',
  runtime_id text,
  thread_id text,
  task_ref text,
  event_type text not null check (event_type in (
    'evaluation','reweight','source_selection','action','outcome','checkpoint'
  )),
  context_hash text,
  weight_snapshot jsonb not null default '{}'::jsonb,
  changed_factors jsonb not null default '{}'::jsonb,
  source_route jsonb not null default '{}'::jsonb,
  impact_summary jsonb not null default '{}'::jsonb,
  receipt_refs jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.operator_decision_events_v1 enable row level security;

create index if not exists operator_decision_events_v1_runtime_idx
  on public.operator_decision_events_v1(runtime_id, created_at desc);

create index if not exists operator_decision_events_v1_thread_idx
  on public.operator_decision_events_v1(thread_id, created_at desc);

comment on table public.operator_decision_events_v1 is
'Append-only impact-weighted decision checkpoints/events. Stores structured reasoning factors and receipts, not hidden chain-of-thought or protected prompt text.';
