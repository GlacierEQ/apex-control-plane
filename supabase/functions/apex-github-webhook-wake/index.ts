import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const WORKER_URL = SUPABASE_URL + "/functions/v1/apex-github-webhook-worker";
const HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store, max-age=0",
  "x-content-type-options": "nosniff",
};

function reply(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: HEADERS });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return reply(405, { ok: false, error: "method_not_allowed" });

  const supplied = req.headers.get("x-apex-worker-secret") || "";
  if (!supplied || supplied.length > 256) return reply(401, { ok: false, error: "worker_wake_auth_required" });

  const { data: valid, error: validationError } = await admin.rpc("validate_github_worker_wake_secret_v1", {
    p_secret: supplied,
  });
  if (validationError) return reply(503, { ok: false, error: "worker_wake_auth_unavailable" });
  if (valid !== true) return reply(401, { ok: false, error: "worker_wake_auth_invalid" });

  let limit = 25;
  try {
    const raw = await req.text();
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && Number.isSafeInteger(Number(parsed.limit))) {
        limit = Math.max(1, Math.min(25, Number(parsed.limit)));
      }
    }
  } catch {
    return reply(400, { ok: false, error: "invalid_json" });
  }

  let response: Response;
  try {
    response = await fetch(WORKER_URL, {
      method: "POST",
      signal: AbortSignal.timeout(60000),
      headers: {
        authorization: `Bearer ${SERVICE_ROLE}`,
        apikey: SERVICE_ROLE,
        "content-type": "application/json",
        accept: "application/json",
        "user-agent": "APEX-GitHub-Webhook-Wake/1.0",
      },
      body: JSON.stringify({ limit }),
    });
  } catch (error) {
    return reply(503, {
      ok: false,
      error: "worker_transport_failure",
      message: error instanceof Error ? error.message : "transport_failure",
    });
  }

  const raw = await response.text();
  let body: unknown = raw;
  try { body = JSON.parse(raw); } catch { body = { raw: raw.slice(0, 4096) }; }

  return reply(response.ok ? 200 : 502, {
    ok: response.ok,
    worker_status: response.status,
    worker: body,
  });
});