create index if not exists github_batch_receipts_v2_item_id_idx
on public.github_batch_receipts_v2(item_id)
where item_id is not null;

comment on index public.github_batch_receipts_v2_item_id_idx is
  'Covers github_batch_receipts_v2.item_id foreign-key lookups and batch item evidence joins.';
