import { createClient } from "npm:@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: cors });
  }
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

  const { data, error } = await supabase
    .from("operator_runtime_context_current_v1")
    .select("*")
    .maybeSingle();

  if (error) {
    return new Response(JSON.stringify({ error: "profile_query_failed", detail: error.message }), {
      status: 500,
      headers: { ...cors, "content-type": "application/json" },
    });
  }
  if (!data) {
    return new Response(JSON.stringify({ error: "active_profile_not_found" }), {
      status: 404,
      headers: { ...cors, "content-type": "application/json" },
    });
  }

  return new Response(JSON.stringify({
    status: "ok",
    source: "supabase",
    profile: data,
    semantics: {
      authority: "operator_context_projection",
      protected_instructions_overridden: false,
      reweight_on_material_change: true,
    },
  }), {
    headers: {
      ...cors,
      "content-type": "application/json",
      "cache-control": "private, max-age=30",
    },
  });
});
