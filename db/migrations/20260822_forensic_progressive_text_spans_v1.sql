-- Progressive, multi-resolution corpus annotations.
-- Source journal entries remain directly retrievable. These objects are derived
-- indexes that add addressable spans, tags, and embeddings without rewriting source.

create extension if not exists pg_trgm with schema extensions;
create extension if not exists vector with schema extensions;

create table if not exists forensic.annotation_tags (
  tag_id uuid primary key default gen_random_uuid(),
  tag_key text not null unique,
  display_label text not null,
  tag_type text not null check (
    tag_type in (
      'entity','actor','concept','event','argument','allegation','evidence',
      'legal','project','action','status','custom'
    )
  ),
  parent_tag_id uuid references forensic.annotation_tags(tag_id),
  aliases text[] not null default '{}',
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (tag_key = lower(tag_key)),
  check (length(btrim(tag_key)) > 0)
);

create table if not exists forensic.text_spans (
  span_id uuid primary key default gen_random_uuid(),
  journal_entry_id uuid not null references forensic.journal_index_entries(journal_entry_id),
  parent_span_id uuid references forensic.text_spans(span_id),
  span_level text not null check (
    span_level in ('chat','message','paragraph','sentence','phrase','token')
  ),
  ordinal integer,
  char_start integer check (char_start is null or char_start >= 0),
  char_end integer check (char_end is null or char_end >= 0),
  token_start integer check (token_start is null or token_start >= 0),
  token_end integer check (token_end is null or token_end >= 0),
  span_text text not null,
  span_sha256 text,
  source_anchor jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (char_start is null or char_end is null or char_end >= char_start),
  check (token_start is null or token_end is null or token_end >= token_start)
);

create table if not exists forensic.span_tag_assignments (
  assignment_id uuid primary key default gen_random_uuid(),
  span_id uuid not null references forensic.text_spans(span_id),
  tag_id uuid not null references forensic.annotation_tags(tag_id),
  relation text not null default 'topic',
  tag_source text not null check (
    tag_source in ('operator','manual','rule','model','import','derived')
  ),
  confidence numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists forensic.span_embeddings (
  embedding_id uuid primary key default gen_random_uuid(),
  span_id uuid not null references forensic.text_spans(span_id),
  embedding_model text not null,
  embedding extensions.vector not null,
  dimensions integer,
  embedding_sha256 text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (span_id, embedding_model)
);

create index if not exists annotation_tags_parent_idx
  on forensic.annotation_tags(parent_tag_id);
create index if not exists annotation_tags_type_idx
  on forensic.annotation_tags(tag_type);
create index if not exists annotation_tags_aliases_gin
  on forensic.annotation_tags using gin(aliases);
create index if not exists annotation_tags_key_trgm
  on forensic.annotation_tags using gin(tag_key extensions.gin_trgm_ops);
create index if not exists annotation_tags_label_trgm
  on forensic.annotation_tags using gin(display_label extensions.gin_trgm_ops);

create index if not exists text_spans_entry_idx
  on forensic.text_spans(journal_entry_id);
create index if not exists text_spans_parent_idx
  on forensic.text_spans(parent_span_id);
create index if not exists text_spans_level_idx
  on forensic.text_spans(span_level);
create index if not exists text_spans_fts
  on forensic.text_spans using gin(to_tsvector('english', span_text));
create index if not exists text_spans_text_trgm
  on forensic.text_spans using gin(span_text extensions.gin_trgm_ops);
create unique index if not exists text_spans_source_bounds_uidx
  on forensic.text_spans (
    journal_entry_id,
    span_level,
    coalesce(char_start, -1),
    coalesce(char_end, -1),
    coalesce(ordinal, -1)
  );

create index if not exists span_tag_assignments_span_idx
  on forensic.span_tag_assignments(span_id);
create index if not exists span_tag_assignments_tag_idx
  on forensic.span_tag_assignments(tag_id);
create index if not exists span_tag_assignments_relation_idx
  on forensic.span_tag_assignments(relation);
create index if not exists span_tag_assignments_source_idx
  on forensic.span_tag_assignments(tag_source);
create unique index if not exists span_tag_assignments_identity_uidx
  on forensic.span_tag_assignments(span_id, tag_id, relation, tag_source);

create index if not exists span_embeddings_span_idx
  on forensic.span_embeddings(span_id);
create index if not exists span_embeddings_model_idx
  on forensic.span_embeddings(embedding_model);

alter table forensic.annotation_tags enable row level security;
alter table forensic.text_spans enable row level security;
alter table forensic.span_tag_assignments enable row level security;
alter table forensic.span_embeddings enable row level security;

create or replace view forensic.annotated_span_catalog as
select
  s.span_id,
  s.journal_entry_id,
  s.parent_span_id,
  s.span_level,
  s.ordinal,
  s.char_start,
  s.char_end,
  s.token_start,
  s.token_end,
  s.span_text,
  s.span_sha256,
  s.source_anchor,
  s.metadata as span_metadata,
  e.speaker,
  e.recorded_at,
  e.provenance_class,
  e.operator_adoption_status,
  js.provider,
  js.provider_file_id,
  js.provider_revision,
  js.source_locator,
  js.source_title,
  coalesce(
    jsonb_agg(
      jsonb_build_object(
        'tag_key', t.tag_key,
        'display_label', t.display_label,
        'tag_type', t.tag_type,
        'relation', a.relation,
        'tag_source', a.tag_source,
        'confidence', a.confidence
      ) order by t.tag_key
    ) filter (where t.tag_id is not null),
    '[]'::jsonb
  ) as tags
from forensic.text_spans s
join forensic.journal_index_entries e
  on e.journal_entry_id = s.journal_entry_id
join forensic.journal_sources js
  on js.journal_source_id = e.journal_source_id
left join forensic.span_tag_assignments a
  on a.span_id = s.span_id
left join forensic.annotation_tags t
  on t.tag_id = a.tag_id
group by s.span_id, e.journal_entry_id, js.journal_source_id;

create or replace function forensic.search_annotated_spans(
  query_text text,
  requested_level text default null,
  result_limit integer default 100
)
returns table (
  span_id uuid,
  span_level text,
  span_text text,
  speaker text,
  recorded_at timestamptz,
  provider text,
  source_title text,
  source_locator text,
  tags jsonb,
  lexical_rank real
)
language sql
stable
set search_path = forensic, public, extensions
as $$
  select
    c.span_id,
    c.span_level,
    c.span_text,
    c.speaker,
    c.recorded_at,
    c.provider,
    c.source_title,
    c.source_locator,
    c.tags,
    greatest(
      ts_rank(
        to_tsvector('english', c.span_text),
        websearch_to_tsquery('english', query_text)
      ),
      extensions.similarity(c.span_text, query_text)
    )::real as lexical_rank
  from forensic.annotated_span_catalog c
  where (requested_level is null or c.span_level = requested_level)
    and (
      to_tsvector('english', c.span_text) @@ websearch_to_tsquery('english', query_text)
      or extensions.similarity(c.span_text, query_text) > 0.15
      or exists (
        select 1
        from jsonb_array_elements(c.tags) tag
        where tag->>'tag_key' ilike '%' || query_text || '%'
           or tag->>'display_label' ilike '%' || query_text || '%'
      )
    )
  order by lexical_rank desc, c.recorded_at nulls last
  limit greatest(1, least(result_limit, 1000));
$$;
