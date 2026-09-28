import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const ROUTER_URL = SUPABASE_URL + "/functions/v1/apex-github-router";
const WORKER_VERSION = 1;
const RETRYABLE = new Set([429, 500, 502, 503, 504]);

type Json = Record<string, unknown>;
type EventRow = {
  event_id: string;
  delivery_id: string;
  event_type: string;
  action: string | null;
  repository: string | null;
  status: string;
  attempts: number;
  metadata: Json;
};

const HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store, max-age=0",
  "x-content-type-options": "nosniff",
};

function obj(value: unknown): Json {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
}

function integer(value: unknown, fallback: number, min: number, max: number): number {
  if (value === undefined || value === null) return fallback;
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n < min || n > max) throw new Error("invalid_integer");
  return n;
}

function branchFromRef(value: unknown): string | null {
  if (typeof value !== "string" || !value) return null;
  return value.startsWith("refs/heads/") ? value.slice("refs/heads/".length) : value;
}

function eventOperations(event: EventRow): Array<{operation: string; args: Json}> {
  const metadata = obj(event.metadata);
  const delivery = obj(metadata.delivery_metadata);
  const repo = event.repository;
  if (!repo) return [];

  const pullNumber = Number(delivery.pull_request_number || 0);
  const issueNumber = Number(delivery.issue_number || 0);
  const branch = branchFromRef(delivery.ref);
  const type = event.event_type;

  if (type === "ping") return [];
  if (type === "push") {
    const ops: Array<{operation: string; args: Json}> = [{ operation: "repo.get", args: {} }];
    ops.push({ operation: "actions.runs", args: branch ? { branch, per_page: 20 } : { per_page: 20 } });
    return ops;
  }
  if (["pull_request", "pull_request_review", "pull_request_review_comment"].includes(type)) {
    const ops: Array<{operation: string; args: Json}> = [{ operation: "repo.get", args: {} }];
    if (pullNumber > 0) ops.push({ operation: "pull.get", args: { number: pullNumber } });
    return ops;
  }
  if (["issues", "issue_comment"].includes(type)) {
    const ops: Array<{operation: string; args: Json}> = [{ operation: "repo.get", args: {} }];
    if (issueNumber > 0) ops.push({ operation: "issue.get", args: { number: issueNumber } });
    return ops;
  }
  if (["workflow_run", "workflow_job", "check_run", "check_suite"].includes(type)) {
    return [
      { operation: "repo.get", args: {} },
      { operation: "actions.runs", args: branch ? { branch, per_page: 20 } : { per_page: 20 } },
    ];
  }
  return [{ operation: "repo.get", args: {} }];
}

async function routerCall(event: EventRow, operation: string, args: Json): Promise<{ok: boolean; status: number; body: Json}> {
  const requestId = `webhook:${event.delivery_id}:${operation}`.slice(0, 256);
  let response: Response;
  try {
    response = await fetch(ROUTER_URL, {
      method: "POST",
      signal: AbortSignal.timeout(35000),
      headers: {
        authorization: `Bearer ${SERVICE_ROLE}`,
        apikey: SERVICE_ROLE,
        "content-type": "application/json",
        accept: "application/json",
        "user-agent": `APEX-GitHub-Webhook-Worker/${WORKER_VERSION}`,
      },
      body: JSON.stringify({
        operation,
        repository: event.repository,
        args,
        request_id: requestId,
        actor: "github-webhook-worker",
      }),
    });
  } catch (error) {
    return {
      ok: false,
      status: 503,
      body: { error: "router_transport_failure", message: error instanceof Error ? error.message : "transport_failure" },
    };
  }

  const raw = await response.text();
  let body: Json = {};
  try { body = obj(JSON.parse(raw || "{}")); } catch { body = { error: "invalid_router_response" }; }
  return { ok: response.ok, status: response.status, body };
}

async function recordResult(event: EventRow, operation: string, call: {ok: boolean; status: number; body: Json}): Promise<void> {
  const gateway = obj(call.body.gateway);
  const plan = obj(call.body.plan);
  const { error } = await admin.from("github_webhook_event_results_v1").insert({
    event_id: event.event_id,
    delivery_id: event.delivery_id,
    repository: event.repository,
    operation,
    response_status: call.status,
    outcome: call.ok ? "succeeded" : "failed",
    result_summary: {
      router_request_id: call.body.request_id || null,
      router_correlation_id: call.body.correlation_id || null,
      selected_connector: plan.selected_connector || null,
      selected_tool: plan.selected_tool || null,
      gateway_github_request_id: gateway.github_request_id || null,
      gateway_readback_verified: gateway.readback_verified === true,
      error: call.ok ? null : call.body.error || gateway.error || null,
    },
    metadata: { worker_version: WORKER_VERSION },
  });
  if (error) throw new Error("event_result_persistence_failed:" + error.message);
}

async function finishEvent(eventId: string, status: "completed" | "failed" | "ignored" | "pending", lastError: string | null, metadata: Json, retryAfter?: number): Promise<void> {
  const { error } = await admin.rpc("finish_github_webhook_event_v1", {
    p_event_id: eventId,
    p_status: status,
    p_last_error: lastError,
    p_metadata: metadata,
    p_retry_after_seconds: retryAfter ?? null,
  });
  if (error) throw new Error("finish_event_failed:" + error.message);
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return new Response(JSON.stringify({ ok: false, error: "method_not_allowed" }), { status: 405, headers: HEADERS });

  let payload: Json = {};
  try {
    const raw = await req.text();
    payload = raw ? obj(JSON.parse(raw)) : {};
  } catch {
    return new Response(JSON.stringify({ ok: false, error: "invalid_json" }), { status: 400, headers: HEADERS });
  }

  let limit: number;
  try { limit = integer(payload.limit, 10, 1, 25); } catch {
    return new Response(JSON.stringify({ ok: false, error: "invalid_limit" }), { status: 400, headers: HEADERS });
  }

  const { data, error } = await admin.rpc("claim_github_webhook_events_v1", { p_limit: limit });
  if (error) return new Response(JSON.stringify({ ok: false, error: "event_claim_failed", detail: error.message }), { status: 500, headers: HEADERS });

  const events = (data || []) as EventRow[];
  const report: Json[] = [];

  for (const event of events) {
    const operations = eventOperations(event);
    if (!event.repository || operations.length === 0) {
      await finishEvent(event.event_id, "ignored", null, { worker_version: WORKER_VERSION, reason: !event.repository ? "no_repository" : "no_refresh_needed" });
      report.push({ event_id: event.event_id, delivery_id: event.delivery_id, status: "ignored" });
      continue;
    }

    let failed: {status: number; error: string} | null = null;
    let succeeded = 0;
    for (const op of operations) {
      const call = await routerCall(event, op.operation, op.args);
      await recordResult(event, op.operation, call);
      if (call.ok) {
        succeeded += 1;
        continue;
      }
      failed = {
        status: call.status,
        error: String(call.body.error || obj(call.body.gateway).error || `http_${call.status}`),
      };
      break;
    }

    if (!failed) {
      await finishEvent(event.event_id, "completed", null, {
        worker_version: WORKER_VERSION,
        operations_succeeded: succeeded,
      });
      report.push({ event_id: event.event_id, delivery_id: event.delivery_id, repository: event.repository, status: "completed", operations_succeeded: succeeded });
      continue;
    }

    const mayRetry = RETRYABLE.has(failed.status) && Number(event.attempts || 0) < 3;
    if (mayRetry) {
      const retrySeconds = Math.min(600, 30 * Math.max(1, Number(event.attempts || 1)));
      await finishEvent(event.event_id, "pending", failed.error, {
        worker_version: WORKER_VERSION,
        retryable_status: failed.status,
      }, retrySeconds);
      report.push({ event_id: event.event_id, delivery_id: event.delivery_id, repository: event.repository, status: "pending", retry_after_seconds: retrySeconds, error: failed.error });
    } else {
      await finishEvent(event.event_id, "failed", failed.error, {
        worker_version: WORKER_VERSION,
        terminal_status: failed.status,
      });
      report.push({ event_id: event.event_id, delivery_id: event.delivery_id, repository: event.repository, status: "failed", error: failed.error });
    }
  }

  return new Response(JSON.stringify({
    ok: true,
    worker_version: WORKER_VERSION,
    claimed: events.length,
    results: report,
  }), { status: 200, headers: HEADERS });
});