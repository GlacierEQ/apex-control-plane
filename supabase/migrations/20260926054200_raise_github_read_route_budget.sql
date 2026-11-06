-- Keep the two high-frequency, read-only GitHub discovery routes from exhausting
-- the internal APEX daily RPC budget during normal estate scans.
--
-- GitHub provider limits remain authoritative; this only raises the internal
-- route budget floor. Write/destructive routes are unchanged.

do $$
declare
  v_updated integer;
begin
  update public.connector_route_runtime_v3
  set rpc_budget_limit = greatest(rpc_budget_limit, 4000),
      state_version = state_version + 1,
      updated_at = clock_timestamp()
  where route_key in (
    'github.backend_ops:repo.get:repository_read:v1',
    'github.backend_ops:branches.list:repository_branch_read:v1'
  );

  get diagnostics v_updated = row_count;

  if v_updated <> 2 then
    raise exception
      'expected 2 GitHub read route runtime rows, updated %',
      v_updated;
  end if;
end
$$;
