import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const db = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const headers = {
  "content-type": "application/json",
  "cache-control": "no-store",
};

function safeEqual(a: string, b: string) {
  const aa = new TextEncoder().encode(a);
  const bb = new TextEncoder().encode(b);
  if (aa.length !== bb.length) return false;
  let diff = 0;
  for (let i = 0; i < aa.length; i++) diff |= aa[i] ^ bb[i];
  return diff === 0;
}

async function authorized(req: Request) {
  const internal = req.headers.get("x-apex-cron-token") ?? "";
  if (internal) {
    const { data, error } = await db.rpc("verify_apex_internal_cron_token", {
      p_token: internal,
    });
    if (!error && data === true) return true;
  }

  const bearer = (req.headers.get("authorization") ?? "")
    .replace(/^Bearer\s+/i, "")
    .trim();
  return !!bearer && !!SERVICE_ROLE && safeEqual(bearer, SERVICE_ROLE);
}

async function resolveAction(body: Record<string, unknown>) {
  const actionId = String(body.action_id ?? "").trim();
  const actionKey = String(body.action_key ?? "").trim();
  if (!actionId && !actionKey) throw new Error("action_id or action_key required");

  let q = db
    .from("control_plane_action_outbox")
    .select(
      "id,case_id,action_key,status,action_type,target_system,target_ref,priority,requires_operator_approval,authorization_basis",
    );
  q = actionId ? q.eq("id", actionId) : q.eq("action_key", actionKey);
  const { data, error } = await q.single();
  if (error) throw new Error(`action_not_found:${error.message}`);
  return data;
}

async function awareness(actionId: string) {
  const { data, error } = await db
    .from("control_plane_action_awareness_v2")
    .select("*")
    .eq("action_id", actionId)
    .single();
  if (error) throw new Error(`awareness_query_failed:${error.message}`);
  return data;
}

Deno.serve(async (req) => {
  if (req.method === "GET") {
    return new Response(
      JSON.stringify({
        ok: true,
        service: "execution-awareness-gate",
        contract:
          "hydrate -> evaluate relevant impact -> publish awareness receipt when needed -> execute only from current relevant reality",
        awareness_model: "explicit-link-target-global-gate-v2",
        soft_context_blocks_dispatch: false,
        mutation_capability: false,
      }),
      { headers },
    );
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ ok: false, error: "method_not_allowed" }), {
      status: 405,
      headers,
    });
  }

  if (!(await authorized(req))) {
    return new Response(JSON.stringify({ ok: false, error: "unauthorized" }), {
      status: 401,
      headers,
    });
  }

  try {
    const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
    const executor = String(body.executor ?? "external-executor").trim();
    if (executor.length < 3) throw new Error("executor identity required");

    const action = await resolveAction(body);
    let current = await awareness(action.id);
    let receipt: unknown = null;

    if (body.publish_evaluation === true) {
      if (typeof body.execution_valid !== "boolean") {
        throw new Error(
          "execution_valid boolean required when publish_evaluation=true",
        );
      }
      const evaluation =
        body.evaluation &&
          typeof body.evaluation === "object" &&
          !Array.isArray(body.evaluation)
          ? body.evaluation
          : {};

      const { data, error } = await db.rpc(
        "record_control_plane_action_awareness_v1",
        {
          p_action_id: action.id,
          p_evaluator: executor,
          p_execution_valid: body.execution_valid,
          p_evaluation: evaluation,
        },
      );
      if (error) throw new Error(`awareness_receipt_failed:${error.message}`);
      receipt = data;
      current = await awareness(action.id);
    }

    const attemptable = ["READY", "APPROVED", "FAILED"].includes(
      String(action.status),
    );
    const currentReality = current.dispatch_reevaluation_required === false;
    const evaluationAllows = current.execution_valid !== false;
    const canExecute = attemptable && currentReality && evaluationAllows;

    return new Response(
      JSON.stringify({
        ok: true,
        executor,
        action,
        awareness: current,
        evaluation_receipt: receipt,
        can_execute: canExecute,
        next_semantic_step: current.dispatch_reevaluation_required
          ? "EVALUATE_CURRENT_RELEVANT_REALITY"
          : current.execution_valid === false
          ? "DO_NOT_EXECUTE_CURRENT_ACTION"
          : attemptable
          ? "CURRENT_ACTION_MAY_PROCEED"
          : "ACTION_NOT_IN_EXECUTABLE_STATE",
        newer_soft_context_exists: current.newer_soft_context_exists === true,
        principle:
          "current relevant source-bearing state outranks cached action intent; unrelated context remains visible without blocking",
        relevance_model:
          current.relevance_model ?? "explicit-link-target-global-gate-v2",
      }),
      { headers },
    );
  } catch (error) {
    return new Response(
      JSON.stringify({
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      }),
      { status: 400, headers },
    );
  }
});
