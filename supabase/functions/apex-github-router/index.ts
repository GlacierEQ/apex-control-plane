import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const CONNECTOR_KEY = "github.backend_ops";
const GATEWAY_URL = SUPABASE_URL + "/functions/v1/apex-github-connector";
const ROUTER_VERSION = 2;
const MAX_BODY_BYTES = 3 * 1024 * 1024;
const DEFAULT_LEASE_TTL_SECONDS = 90;
const CIRCUIT_THRESHOLD = 3;
const CIRCUIT_OPEN_SECONDS = 60;
const RETRYABLE_STATUS = new Set([429, 502, 503, 504]);
const READ_RETRY_DELAYS_MS = [0, 200, 600];

const HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store, max-age=0",
  "pragma": "no-cache",
  "x-content-type-options": "nosniff",
  "referrer-policy": "no-referrer",
};

type Json = Record<string, unknown>;
type RouteRow = {
  route_key: string;
  connector_key: string;
  tool_name: string;
  capability: string;
  mutation_class: string;
  priority: number;
  enabled: boolean;
  approval_required: boolean;
  metadata: Json;
};

type GatewayResult = {
  ok: boolean;
  status: number;
  body: Json;
  attempts: number;
  latencyMs: number;
};

class RouterError extends Error {
  status: number;
  code: string;
  details: Json;
  constructor(status: number, code: string, message?: string, details: Json = {}) {
    super(message || code);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function respond(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: HEADERS });
}

function obj(value: unknown): Json {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
}

function stringValue(value: unknown, field: string, max = 512, required = true): string {
  if ((value === undefined || value === null || value === "") && !required) return "";
  if (typeof value !== "string") throw new RouterError(400, "invalid_" + field);
  const out = value.trim();
  if ((required && !out) || out.length > max) throw new RouterError(400, "invalid_" + field);
  return out;
}

function integerValue(value: unknown, field: string, min: number, max: number): number {
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n < min || n > max) throw new RouterError(400, "invalid_" + field);
  return n;
}

function stable(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(stable).join(",") + "]";
  const record = value as Json;
  return "{" + Object.keys(record).sort().map((key) => JSON.stringify(key) + ":" + stable(record[key])).join(",") + "}";
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function sleep(ms: number): Promise<void> {
  if (ms <= 0) return;
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function readJson(req: Request): Promise<Json> {
  const declared = Number(req.headers.get("content-length") || 0);
  if (declared > MAX_BODY_BYTES) throw new RouterError(413, "request_body_too_large");
  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) throw new RouterError(413, "request_body_too_large");
  try {
    const parsed = JSON.parse(raw || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("not_object");
    return parsed as Json;
  } catch {
    throw new RouterError(400, "invalid_json");
  }
}

function summarizeArgs(operation: string, args: Json): Json {
  if (operation === "contents.put" || operation === "contents.get") {
    return { path: args.path || null, branch: args.branch || args.ref || null };
  }
  if (operation === "branch.create") return { branch: args.branch || null, base_branch: args.base_branch || null };
  if (["issue.get", "issue.comment", "pull.get", "pull.comment", "pull.review"].includes(operation)) {
    return { number: args.number || null };
  }
  if (operation === "workflow.dispatch") return { workflow_id: args.workflow_id || null, ref: args.ref || null };
  return {};
}

function leaseKey(operation: string, repository: string, args: Json): string {
  if (operation === "contents.put") {
    return `github:${repository}:branch:${String(args.branch || "")}:path:${String(args.path || "")}`;
  }
  if (operation === "branch.create") return `github:${repository}:branch:${String(args.branch || "")}`;
  if (operation === "issue.comment") return `github:${repository}:issue:${String(args.number || "")}`;
  if (operation === "pull.comment") return `github:${repository}:pull:${String(args.number || "")}`;
  if (operation === "workflow.dispatch") return `github:${repository}:workflow:${String(args.workflow_id || "")}:ref:${String(args.ref || "")}`;
  return `github:${repository}:operation:${operation}`;
}

const nativeFallback: Record<string, {tool: string; capability: string}> = {
  "pulls.list": { tool: "search_prs", capability: "pull_requests_full_read" },
  "pull.get": { tool: "get_pr_info", capability: "pull_requests_full_read" },
  "pull.create": { tool: "create_pull_request", capability: "pull_requests_write" },
  "pull.review": { tool: "add_review_to_pr", capability: "pull_requests_review" },
};

async function loadRoutes(): Promise<RouteRow[]> {
  const { data, error } = await admin
    .from("connector_route_policy_v3")
    .select("route_key,connector_key,tool_name,capability,mutation_class,priority,enabled,approval_required,metadata")
    .eq("fallback_group", "github")
    .order("priority", { ascending: true });
  if (error) throw new RouterError(500, "route_policy_read_failed", error.message);
  return (data || []).map((row: any) => ({ ...row, metadata: obj(row.metadata) })) as RouteRow[];
}

function planRoute(operation: string, routes: RouteRow[], fullFidelity: boolean): Json {
  const backend = routes.find((r) => r.connector_key === CONNECTOR_KEY && r.tool_name === operation);
  const fallback = nativeFallback[operation];

  if (fullFidelity && fallback) {
    const native = routes.find((r) => r.connector_key === "github.native" && r.tool_name === fallback.tool && r.enabled);
    if (native) {
      return {
        executable_here: false,
        fallback_required: true,
        selected_connector: "github.native",
        selected_tool: fallback.tool,
        capability: fallback.capability,
        route_key: native.route_key,
        reason: "full_fidelity_requested",
      };
    }
  }

  if (backend?.enabled) {
    return {
      executable_here: true,
      fallback_required: false,
      selected_connector: backend.connector_key,
      selected_tool: backend.tool_name,
      capability: backend.capability,
      mutation_class: backend.mutation_class,
      approval_required: backend.approval_required,
      route_key: backend.route_key,
      route_metadata: backend.metadata,
    };
  }

  if (fallback) {
    const native = routes.find((r) => r.connector_key === "github.native" && r.tool_name === fallback.tool && r.enabled);
    return {
      executable_here: false,
      fallback_required: true,
      selected_connector: native?.connector_key || "github.native",
      selected_tool: fallback.tool,
      capability: fallback.capability,
      route_key: native?.route_key || null,
      reason: backend ? "backend_route_disabled" : "backend_route_unavailable",
      backend_route: backend?.route_key || null,
    };
  }

  return {
    executable_here: false,
    fallback_required: false,
    selected_connector: null,
    selected_tool: null,
    route_key: null,
    reason: "no_route",
  };
}

async function getCircuit(operation: string): Promise<Json> {
  const key = `${CONNECTOR_KEY}:${operation}`;
  const { data, error } = await admin.from("github_connector_circuit_v2").select("*").eq("circuit_key", key).maybeSingle();
  if (error) throw new RouterError(500, "circuit_read_failed", error.message);
  return obj(data || { circuit_key: key, consecutive_failures: 0 });
}

async function recordCircuit(operation: string, success: boolean, status: number, errorCode?: string): Promise<void> {
  const key = `${CONNECTOR_KEY}:${operation}`;
  const current = await getCircuit(operation);
  const failures = success ? 0 : Number(current.consecutive_failures || 0) + 1;
  const now = new Date();
  const openedUntil = !success && failures >= CIRCUIT_THRESHOLD
    ? new Date(now.getTime() + CIRCUIT_OPEN_SECONDS * 1000).toISOString()
    : success ? null : current.opened_until || null;

  const { error } = await admin.from("github_connector_circuit_v2").upsert({
    circuit_key: key,
    consecutive_failures: failures,
    opened_until: openedUntil,
    last_status: status,
    last_error: success ? null : errorCode || `http_${status}`,
    last_success_at: success ? now.toISOString() : current.last_success_at || null,
    last_failure_at: success ? current.last_failure_at || null : now.toISOString(),
    metadata: obj(current.metadata),
    updated_at: now.toISOString(),
  });
  if (error) throw new RouterError(500, "circuit_write_failed", error.message);
}

async function acquireLease(key: string, requestId: string, actor: string, ttl: number, metadata: Json): Promise<Json> {
  const { data, error } = await admin.rpc("acquire_github_connector_lease_v2", {
    p_lease_key: key,
    p_request_id: requestId,
    p_actor: actor,
    p_ttl_seconds: ttl,
    p_metadata: metadata,
  });
  if (error) throw new RouterError(500, "lease_acquire_failed", error.message);
  return obj(data);
}

async function releaseLease(key: string, requestId: string, state: "completed" | "released" | "failed", metadata: Json): Promise<void> {
  const { error } = await admin.rpc("release_github_connector_lease_v2", {
    p_lease_key: key,
    p_request_id: requestId,
    p_state: state,
    p_metadata: metadata,
  });
  if (error) throw new RouterError(500, "lease_release_failed", error.message);
}

async function gatewayCall(operation: string, repository: string | null, args: Json, requestId: string, actor: string, retryReads: boolean): Promise<GatewayResult> {
  const started = Date.now();
  const delays = retryReads ? READ_RETRY_DELAYS_MS : [0];
  let lastStatus = 500;
  let lastBody: Json = {};

  for (let i = 0; i < delays.length; i++) {
    await sleep(delays[i]);
    let response: Response;
    try {
      response = await fetch(GATEWAY_URL, {
        method: "POST",
        signal: AbortSignal.timeout(30000),
        headers: {
          authorization: `Bearer ${SERVICE_ROLE}`,
          apikey: SERVICE_ROLE,
          "content-type": "application/json",
          accept: "application/json",
          "user-agent": `APEX-GitHub-Router/${ROUTER_VERSION}`,
        },
        body: JSON.stringify({ operation, repository, args, request_id: requestId, actor }),
      });
    } catch (error) {
      lastStatus = 503;
      lastBody = { error: "gateway_transport_failure", message: error instanceof Error ? error.message : "transport_failure" };
      if (!retryReads || i === delays.length - 1) break;
      continue;
    }

    const raw = await response.text();
    try { lastBody = obj(JSON.parse(raw || "{}")); } catch { lastBody = { error: "invalid_gateway_response", raw: raw.slice(0, 2048) }; }
    lastStatus = response.status;

    if (response.ok || !retryReads || !RETRYABLE_STATUS.has(response.status) || i === delays.length - 1) {
      return { ok: response.ok, status: response.status, body: lastBody, attempts: i + 1, latencyMs: Date.now() - started };
    }
  }

  return { ok: false, status: lastStatus, body: lastBody, attempts: delays.length, latencyMs: Date.now() - started };
}

async function persistDecision(input: {
  requestId: string;
  correlationId: string;
  operation: string;
  repository: string | null;
  plan: Json;
  outcome: "executed" | "fallback" | "rejected" | "failed" | "planned";
  status: number | null;
  attempts: number;
  leaseKey: string | null;
  expectedBeforeSha: string | null;
  observedBeforeSha: string | null;
  latencyMs: number;
  metadata: Json;
}): Promise<void> {
  const { error } = await admin.from("github_connector_route_decisions_v2").insert({
    request_id: input.requestId,
    correlation_id: input.correlationId,
    operation: input.operation,
    repository: input.repository,
    route_key: input.plan.route_key || null,
    selected_connector: input.plan.selected_connector || null,
    selected_tool: input.plan.selected_tool || null,
    outcome: input.outcome,
    response_status: input.status,
    attempts: input.attempts,
    lease_key: input.leaseKey,
    expected_before_sha: input.expectedBeforeSha,
    observed_before_sha: input.observedBeforeSha,
    latency_ms: input.latencyMs,
    metadata: input.metadata,
  });
  if (error) throw new RouterError(500, "route_decision_persistence_failed", error.message);
}

Deno.serve(async (req: Request) => {
  const started = Date.now();
  const correlationId = crypto.randomUUID();
  let input: Json = {};
  let requestId = "";
  let operation = "";
  let repository: string | null = null;
  let plan: Json = {};
  let activeLeaseKey: string | null = null;
  let expectedBeforeSha: string | null = null;
  let observedBeforeSha: string | null = null;
  let attempts = 0;
  let leaseTerminal: "completed" | "released" | "failed" = "released";

  try {
    if (req.method !== "POST") throw new RouterError(405, "method_not_allowed");
    input = await readJson(req);
    operation = stringValue(input.operation, "operation", 128);
    requestId = stringValue(input.request_id, "request_id", 256, false) || crypto.randomUUID();
    const actor = stringValue(input.actor, "actor", 256, false) || "router-authenticated";
    const args = obj(input.args);
    const fullFidelity = input.full_fidelity === true;
    const routes = await loadRoutes();

    if (operation === "route.plan") {
      const requested = stringValue(args.requested_operation, "requested_operation", 128);
      plan = planRoute(requested, routes, fullFidelity || args.full_fidelity === true);
      const requestHash = await sha256Hex(stable({ requested, full_fidelity: fullFidelity || args.full_fidelity === true }));
      await persistDecision({
        requestId, correlationId, operation: requested, repository: null, plan, outcome: "planned", status: 200,
        attempts: 0, leaseKey: null, expectedBeforeSha: null, observedBeforeSha: null,
        latencyMs: Date.now() - started, metadata: { request_hash: requestHash, router_version: ROUTER_VERSION },
      });
      return respond(200, { ok: true, router_version: ROUTER_VERSION, request_id: requestId, correlation_id: correlationId, plan });
    }

    repository = stringValue(input.repository, "repository", 256);
    if (!/^GlacierEQ\/[A-Za-z0-9_.-]+$/.test(repository)) throw new RouterError(403, "repository_scope_rejected");
    plan = planRoute(operation, routes, fullFidelity);
    const requestHash = await sha256Hex(stable({ operation, repository, args, full_fidelity: fullFidelity }));

    if (plan.fallback_required === true) {
      await persistDecision({
        requestId, correlationId, operation, repository, plan, outcome: "fallback", status: 409,
        attempts: 0, leaseKey: null, expectedBeforeSha: null, observedBeforeSha: null,
        latencyMs: Date.now() - started,
        metadata: { request_hash: requestHash, router_version: ROUTER_VERSION, args_summary: summarizeArgs(operation, args) },
      });
      return respond(409, {
        ok: false,
        error: "fallback_required",
        router_version: ROUTER_VERSION,
        request_id: requestId,
        correlation_id: correlationId,
        plan,
      });
    }

    if (plan.executable_here !== true) throw new RouterError(404, "no_executable_route", undefined, { plan });

    const mutationClass = String(plan.mutation_class || "read");
    const isWrite = mutationClass === "write";
    if (isWrite && requestId.length < 8) throw new RouterError(400, "request_id_required_for_write");

    const circuit = await getCircuit(operation);
    if (typeof circuit.opened_until === "string" && new Date(circuit.opened_until).getTime() > Date.now()) {
      throw new RouterError(503, "circuit_open", undefined, {
        opened_until: circuit.opened_until,
        consecutive_failures: circuit.consecutive_failures || 0,
        fallback: nativeFallback[operation] || null,
      });
    }

    if (isWrite) {
      activeLeaseKey = leaseKey(operation, repository, args);
      const ttl = input.lease_ttl_seconds === undefined
        ? DEFAULT_LEASE_TTL_SECONDS
        : integerValue(input.lease_ttl_seconds, "lease_ttl_seconds", 10, 600);
      const lease = await acquireLease(activeLeaseKey, requestId, actor, ttl, {
        operation,
        repository,
        args_summary: summarizeArgs(operation, args),
        router_version: ROUTER_VERSION,
      });
      if (lease.acquired !== true) {
        await persistDecision({
          requestId, correlationId, operation, repository, plan, outcome: "rejected", status: 409,
          attempts: 0, leaseKey: activeLeaseKey, expectedBeforeSha: null, observedBeforeSha: null,
          latencyMs: Date.now() - started,
          metadata: { request_hash: requestHash, lease, router_version: ROUTER_VERSION },
        });
        activeLeaseKey = null;
        return respond(409, { ok: false, error: "resource_lease_busy", request_id: requestId, correlation_id: correlationId, lease });
      }
    }

    if (operation === "contents.put") {
      if (!Object.prototype.hasOwnProperty.call(input, "expected_before_sha")) {
        leaseTerminal = "failed";
        throw new RouterError(428, "write_precondition_required", "contents.put requires expected_before_sha (string for update, null for create)");
      }
      expectedBeforeSha = input.expected_before_sha === null ? null : stringValue(input.expected_before_sha, "expected_before_sha", 128);
      const preflightId = `${requestId}:preflight`.slice(0, 256);
      const preflight = await gatewayCall("contents.get", repository, { path: args.path, ref: args.branch }, preflightId, actor, true);
      attempts += preflight.attempts;
      if (preflight.ok) {
        observedBeforeSha = typeof obj(preflight.body.result).sha === "string" ? String(obj(preflight.body.result).sha) : null;
      } else if (preflight.status === 404) {
        observedBeforeSha = null;
      } else {
        leaseTerminal = "failed";
        await recordCircuit("contents.get", false, preflight.status, String(preflight.body.error || "preflight_failed"));
        throw new RouterError(preflight.status, "preflight_read_failed", undefined, { gateway: preflight.body });
      }

      if (observedBeforeSha !== expectedBeforeSha) {
        leaseTerminal = "failed";
        await persistDecision({
          requestId, correlationId, operation, repository, plan, outcome: "rejected", status: 409,
          attempts, leaseKey: activeLeaseKey, expectedBeforeSha, observedBeforeSha,
          latencyMs: Date.now() - started,
          metadata: { request_hash: requestHash, router_version: ROUTER_VERSION, reason: "stale_write_precondition" },
        });
        await releaseLease(activeLeaseKey!, requestId, "failed", { reason: "stale_write_precondition" });
        activeLeaseKey = null;
        return respond(409, {
          ok: false,
          error: "stale_write_precondition",
          request_id: requestId,
          correlation_id: correlationId,
          expected_before_sha: expectedBeforeSha,
          observed_before_sha: observedBeforeSha,
        });
      }
      await recordCircuit("contents.get", true, 200);
    }

    const execution = await gatewayCall(operation, repository, args, requestId, actor, !isWrite);
    attempts += execution.attempts;
    const gatewayError = typeof execution.body.error === "string" ? execution.body.error : undefined;
    await recordCircuit(operation, execution.ok, execution.status, gatewayError);

    if (!execution.ok) {
      leaseTerminal = "failed";
      await persistDecision({
        requestId, correlationId, operation, repository, plan, outcome: "failed", status: execution.status,
        attempts, leaseKey: activeLeaseKey, expectedBeforeSha, observedBeforeSha,
        latencyMs: Date.now() - started,
        metadata: {
          request_hash: requestHash,
          router_version: ROUTER_VERSION,
          args_summary: summarizeArgs(operation, args),
          gateway_error: gatewayError || null,
          gateway_correlation_id: execution.body.correlation_id || null,
        },
      });
      if (activeLeaseKey) {
        await releaseLease(activeLeaseKey, requestId, "failed", { gateway_status: execution.status, gateway_error: gatewayError || null });
        activeLeaseKey = null;
      }
      return respond(execution.status, {
        ok: false,
        router_version: ROUTER_VERSION,
        request_id: requestId,
        correlation_id: correlationId,
        plan,
        gateway: execution.body,
        attempts,
      });
    }

    leaseTerminal = "completed";
    try {
      await persistDecision({
        requestId, correlationId, operation, repository, plan, outcome: "executed", status: execution.status,
        attempts, leaseKey: activeLeaseKey, expectedBeforeSha, observedBeforeSha,
        latencyMs: Date.now() - started,
        metadata: {
          request_hash: requestHash,
          router_version: ROUTER_VERSION,
          args_summary: summarizeArgs(operation, args),
          gateway_correlation_id: execution.body.correlation_id || null,
          gateway_readback_verified: execution.body.readback_verified === true,
        },
      });
    } catch (receiptError) {
      if (activeLeaseKey) {
        await releaseLease(activeLeaseKey, requestId, "completed", { route_receipt_persistence_failed: true });
        activeLeaseKey = null;
      }
      return respond(502, {
        ok: false,
        error: "router_receipt_persistence_failed_after_gateway_success",
        external_outcome_verified_by_gateway: true,
        request_id: requestId,
        correlation_id: correlationId,
        gateway: execution.body,
        detail: receiptError instanceof Error ? receiptError.message : "route_receipt_failure",
      });
    }

    if (activeLeaseKey) {
      await releaseLease(activeLeaseKey, requestId, "completed", {
        gateway_correlation_id: execution.body.correlation_id || null,
        gateway_readback_verified: execution.body.readback_verified === true,
      });
      activeLeaseKey = null;
    }

    return respond(200, {
      ok: true,
      router_version: ROUTER_VERSION,
      request_id: requestId,
      correlation_id: correlationId,
      plan,
      attempts,
      expected_before_sha: expectedBeforeSha,
      observed_before_sha: observedBeforeSha,
      gateway: execution.body,
    });
  } catch (error) {
    const routerError = error instanceof RouterError
      ? error
      : new RouterError(500, "internal_router_error", error instanceof Error ? error.message : "internal_router_error");

    if (activeLeaseKey) {
      try { await releaseLease(activeLeaseKey, requestId, leaseTerminal, { router_error: routerError.code }); } catch { /* preserve primary error */ }
      activeLeaseKey = null;
    }

    if (requestId && operation && Object.keys(plan).length) {
      try {
        await persistDecision({
          requestId, correlationId, operation, repository, plan,
          outcome: routerError.status >= 500 ? "failed" : "rejected",
          status: routerError.status, attempts, leaseKey: null,
          expectedBeforeSha, observedBeforeSha, latencyMs: Date.now() - started,
          metadata: { router_version: ROUTER_VERSION, error: routerError.code, details: routerError.details },
        });
      } catch { /* preserve primary error */ }
    }

    return respond(routerError.status, {
      ok: false,
      router_version: ROUTER_VERSION,
      request_id: requestId || null,
      correlation_id: correlationId,
      operation: operation || null,
      repository,
      error: routerError.code,
      message: routerError.message,
      details: routerError.details,
    });
  }
});