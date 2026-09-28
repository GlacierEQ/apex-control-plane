alter table public.continuity_ingest_queue_v1
  add column if not exists metadata jsonb not null default '{}'::jsonb;

comment on column public.continuity_ingest_queue_v1.metadata
  is 'Non-provider control metadata such as matter-resolution rationale. Provider payload remains unchanged in payload.';

create index if not exists continuity_ingest_matter_idx
  on public.continuity_ingest_queue_v1(matter_id,occurred_at desc)
  where matter_id is not null;

