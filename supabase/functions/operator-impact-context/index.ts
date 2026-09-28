import { createClient } from "npm:@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "GET" && req.method !== "POST") {
    return new Response(JSON.stringify({ error: "method_not_allowed" }), {
      status: 405,
      headers: { ...cors, "content-type": "application/json" },
    });
  }

  const url = Deno.env.get("SUPABASE_URL");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !serviceKey) {
    return new Response(JSON.stringify({ error: "supabase_runtime_not_configured" }), {
      status: 500,
      headers: { ...cors, "content-type": "application/json" },
    });
  }

  const supabase = createClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const requestUrl = new URL(req.url);
  let input: Record<string, unknown> = {};
  if (req.method === "POST") {
    try {
      const parsed = await req.json();
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) input = parsed;
    } catch {
      input = {};
    }
  }

  const caseId = String(input.case_id ?? requestUrl.searchParams.get("case_id") ?? "").trim() || null;
  const actionId = String(input.action_id ?? requestUrl.searchParams.get("action_id") ?? "").trim() || null;
  const executor = String(input.executor ?? requestUrl.searchParams.get("executor") ?? "unknown-executor").trim();

  const [profileResult, frontierResult, repoRuntimeResult, awarenessResult] = await Promise.all([
    supabase.from("operator_runtime_context_current_v1").select("*").maybeSingle(),
    supabase.from("control_plane_global_frontier_v2").select("*").maybeSingle(),
    supabase
      .from("application_repo_runtime_current_v1")
      .select("repo_name,observation_kind,full_name,default_branch,visibility,archived,branch_heads,source_project,source_projection_key,source_projection_version,projection_hash,source_refreshed_at,source_expires_at,is_fresh")
      .eq("is_fresh", true)
      .order("repo_name", { ascending: true })
      .order("observation_kind", { ascending: true })
      .limit(200),
    supabase.rpc("get_control_plane_action_awareness_v2", {
      p_case_id: caseId,
      p_action_id: actionId,
      p_limit: 50,
    }),
  ]);

  if (profileResult.error) {
    return new Response(JSON.stringify({ error: "profile_query_failed", detail: profileResult.error.message }), {
      status: 500,
      headers: { ...cors, "content-type": "application/json" },
    });
  }
  if (!profileResult.data) {
    return new Response(JSON.stringify({ error: "active_profile_not_found" }), {
      status: 404,
      headers: { ...cors, "content-type": "application/json" },
    });
  }
  if (frontierResult.error) {
    return new Response(JSON.stringify({ error: "continuity_frontier_query_failed", detail: frontierResult.error.message, continuity_ready: false }), {
      status: 500,
      headers: { ...cors, "content-type": "application/json" },
    });
  }
  if (!frontierResult.data) {
    return new Response(JSON.stringify({ error: "continuity_frontier_not_found", continuity_ready: false }), {
      status: 409,
      headers: { ...cors, "content-type": "application/json" },
    });
  }
  if (repoRuntimeResult.error) {
    return new Response(JSON.stringify({ error: "repo_runtime_state_query_failed", detail: repoRuntimeResult.error.message, continuity_ready: true, repo_runtime_ready: false }), {
      status: 500,
      headers: { ...cors, "content-type": "application/json" },
    });
  }
  if (awarenessResult.error) {
    return new Response(JSON.stringify({ error: "dynamic_awareness_query_failed", detail: awarenessResult.error.message, continuity_ready: true, awareness_ready: false }), {
      status: 500,
      headers: { ...cors, "content-type": "application/json" },
    });
  }

  const repoRuntime = repoRuntimeResult.data ?? [];
  const repoRuntimeByRepo = new Map<string, Record<string, unknown>>();
  for (const row of repoRuntime) {
    const existing = repoRuntimeByRepo.get(row.repo_name) ?? {
      repo_name: row.repo_name,
      full_name: row.full_name,
      qualified_source_peer: "supabase-backend-ops/github.backend_ops",
      observations: {},
    };
    const observations = existing.observations as Record<string, unknown>;
    observations[row.observation_kind] = {
      default_branch: row.default_branch,
      visibility: row.visibility,
      archived: row.archived,
      branch_heads: row.branch_heads,
      source_project: row.source_project,
      source_projection_key: row.source_projection_key,
      source_projection_version: row.source_projection_version,
      projection_hash: row.projection_hash,
      source_refreshed_at: row.source_refreshed_at,
      source_expires_at: row.source_expires_at,
      fresh: row.is_fresh,
    };
    repoRuntimeByRepo.set(row.repo_name, existing);
  }

  const awareness = awarenessResult.data ?? {
    observed_at: new Date().toISOString(),
    actions: [],
    actions_requiring_reevaluation: 0,
    actions_with_new_soft_context: 0,
    relevance_model: "explicit-link-target-global-gate-v2",
  };
  const reevaluationCount = Number(awareness.actions_requiring_reevaluation ?? 0);
  const softContextCount = Number(awareness.actions_with_new_soft_context ?? 0);

  return new Response(JSON.stringify({
    status: "ok",
    source: "supabase",
    continuity_ready: true,
    awareness_ready: true,
    profile: profileResult.data,
    frontier: frontierResult.data,
    awareness: {
      ...awareness,
      requested_case_id: caseId,
      requested_action_id: actionId,
      executor,
      must_re_evaluate_before_mutation: reevaluationCount > 0,
      newer_soft_context_present: softContextCount > 0,
      semantic_basis:
        "current relevant source-bearing state outranks cached action intent; unrelated context remains visible without blocking",
      hard_source_changes_block_dispatch: true,
      soft_context_blocks_dispatch: false,
    },
    repo_runtime: {
      authority: "qualified_projection_only",
      source_peer: "supabase-backend-ops/github.backend_ops",
      repository_authority_remains: "github",
      freshness_enforced: true,
      repository_count: repoRuntimeByRepo.size,
      observation_count: repoRuntime.length,
      repositories: Array.from(repoRuntimeByRepo.values()),
    },
    startup_contract: {
      first_action: "resume_from_frontier_before_replanning",
      do_not_restart_if_prior_state_exists: true,
      hydrate_material_delta_before_action: true,
      process_ready_actions_idempotently: true,
      capture_external_receipts_before_completion: true,
      recompute_on_new_communication_or_obligation: true,
      reevaluate_when_newer_relevant_source_state_exists: true,
      preserve_unrelated_new_context_without_false_blocking: true,
      stale_cached_intent_is_not_execution_authority: true,
      surface_connector_incidents: true,
      use_only_fresh_qualified_repo_runtime_state: true,
    },
    semantics: {
      authority: "operator_context_plus_continuous_control_plane",
      protected_instructions_overridden: false,
      dynamic_awareness_is_primary_runtime_context: true,
      relevance_model: awareness.relevance_model ?? "explicit-link-target-global-gate-v2",
      reweight_on_material_change: true,
      checkpoint_is_execution_state: true,
      repo_runtime_is_projection_not_repository_authority: true,
      action_rules_are_not_substitute_for_current_state: true,
      soft_context_is_visible_but_nonblocking: true,
      representation_duplicates_cannot_create_relevance: true,
    },
  }), {
    headers: {
      ...cors,
      "content-type": "application/json",
      "cache-control": "private, max-age=5",
    },
  });
});
