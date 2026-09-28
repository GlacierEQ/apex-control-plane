import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
const MCP_PROTOCOL_VERSION = "2025-06-18";
if (!SUPABASE_URL || !SERVICE_ROLE_KEY) throw new Error("Supabase runtime credentials unavailable");

const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

type Json = Record<string, unknown>;
type RpcId = string | number | null;
type Route = {
  route_key: string;
  connector_key: string;
  tool_name: string;
  capability: string;
  mutation_class: string;
  policy_version: number;
  priority: number;
  enabled: boolean;
  approval_required: boolean;
  estimated_rpc_units: number | null;
  fallback_group: string | null;
  metadata: Json | null;
};

const json = (body: unknown, status = 200) => Response.json(body, {
  status,
  headers: {
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
    "mcp-protocol-version": MCP_PROTOCOL_VERSION,
  },
});

const text = (value: unknown, field: string, required = true): string | null => {
  if (value == null || value === "") {
    if (required) throw new Error(`${field} is required`);
    return null;
  }
  if (typeof value !== "string") throw new Error(`${field} must be a string`);
  return value;
};

const int = (value: unknown, field: string, min: number, max: number, fallback: number): number => {
  if (value == null) return fallback;
  if (!Number.isInteger(value) || Number(value) < min || Number(value) > max) {
    throw new Error(`${field} must be an integer between ${min} and ${max}`);
  }
  return Number(value);
};

function isDirectRoute(route: Route): boolean {
  const key = route.connector_key.toLowerCase();
  if (key.startsWith("smithery") || key.includes("smithery:")) return false;
  const metadata = route.metadata || {};
  if (metadata.fabric === "smithery" || metadata.transport === "smithery") return false;
  return true;
}

async function listRoutes(connectorKey?: string | null): Promise<Route[]> {
  let q = supabase
    .from("connector_route_policy_v3")
    .select("route_key,connector_key,tool_name,capability,mutation_class,policy_version,priority,enabled,approval_required,estimated_rpc_units,fallback_group,metadata")
    .eq("enabled", true)
    .order("connector_key")
    .order("priority")
    .order("route_key");
  if (connectorKey) q = q.eq("connector_key", connectorKey);
  const { data, error } = await q;
  if (error) throw error;
  return ((data ?? []) as Route[]).filter(isDirectRoute);
}

async function loadRoute(routeKey: string): Promise<Route | null> {
  const { data, error } = await supabase
    .from("connector_route_policy_v3")
    .select("route_key,connector_key,tool_name,capability,mutation_class,policy_version,priority,enabled,approval_required,estimated_rpc_units,fallback_group,metadata")
    .eq("route_key", routeKey)
    .eq("enabled", true)
    .maybeSingle();
  if (error) throw error;
  if (!data) return null;
  const route = data as Route;
  return isDirectRoute(route) ? route : null;
}

async function loadJob(jobId: string) {
  const { data, error } = await supabase
    .from("connector_execution_jobs_v3")
    .select("id,correlation_id,idempotency_key,connector_key,tool_name,capability,logical_scope,status,priority,approval_required,approved_at,approval_reference,attempt_count,max_attempts,run_after,payload_hash,result_hash,error,created_at,started_at,completed_at,updated_at,route_key,policy_version,estimated_rpc_units")
    .eq("id", jobId)
    .maybeSingle();
  if (error) throw error;
  return data ?? null;
}

async function jobStatus(jobId: string) {
  const job = await loadJob(jobId);
  if (!job) return json({ ok: false, error: "job_not_found" }, 404);
  return json({ ok: true, job });
}

async function enqueueRoute(route: Route, body: Json) {
  const args = body.arguments;
  if (args == null || typeof args !== "object" || Array.isArray(args)) {
    throw new Error("arguments must be a JSON object");
  }

  const { data, error } = await supabase.rpc("enqueue_connector_execution_job_v3", {
    p_connector_key: route.connector_key,
    p_tool_name: route.tool_name,
    p_capability: route.capability,
    p_arguments: args,
    p_logical_scope: text(body.logical_scope, "logical_scope", false),
    p_priority: int(body.priority, "priority", 0, 100, route.priority ?? 50),
    p_idempotency_key: text(body.idempotency_key, "idempotency_key", false),
    p_approval_required: route.mutation_class !== "read" || route.approval_required === true,
    p_notion_request_id: text(body.notion_request_id, "notion_request_id", false),
    p_linear_issue_id: text(body.linear_issue_id, "linear_issue_id", false),
  });
  if (error) throw error;
  return {
    ok: true,
    route: {
      route_key: route.route_key,
      connector_key: route.connector_key,
      tool_name: route.tool_name,
      capability: route.capability,
      mutation_class: route.mutation_class,
      approval_required: route.mutation_class !== "read" || route.approval_required === true,
      policy_version: route.policy_version,
    },
    enqueue: data,
  };
}

async function enqueueLegacy(body: Json) {
  const connectorKey = text(body.connector_key, "connector_key")!;
  const toolName = text(body.tool_name, "tool_name")!;
  const capability = text(body.capability, "capability")!;
  const { data: routes, error } = await supabase
    .from("connector_route_policy_v3")
    .select("route_key,connector_key,tool_name,capability,mutation_class,policy_version,priority,enabled,approval_required,estimated_rpc_units,fallback_group,metadata")
    .eq("connector_key", connectorKey)
    .eq("tool_name", toolName)
    .eq("capability", capability)
    .eq("enabled", true)
    .order("priority")
    .limit(1);
  if (error) throw error;
  const route = (routes?.[0] ?? null) as Route | null;
  if (!route || !isDirectRoute(route)) return json({ ok: false, error: "no_registered_direct_route" }, 404);
  const result = await enqueueRoute(route, body);
  return json(result, 202);
}

function routeToolName(routeKey: string): string {
  const safe = routeKey.toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  return `connector_${safe}`.slice(0, 120);
}

function routeToMcpTool(route: Route): Json {
  const readOnly = route.mutation_class === "read";
  return {
    name: routeToolName(route.route_key),
    description: `Direct governed connector route ${route.route_key}: ${route.connector_key} / ${route.tool_name} / ${route.capability}. ${readOnly ? "Read-only." : "Mutation; execution remains approval-gated when policy requires it."}`,
    inputSchema: {
      type: "object",
      properties: {
        arguments: { type: "object", description: "Provider tool arguments for this registered route." },
        logical_scope: { type: "string" },
        priority: { type: "integer", minimum: 0, maximum: 100 },
        idempotency_key: { type: "string" },
        notion_request_id: { type: "string" },
        linear_issue_id: { type: "string" },
      },
      required: ["arguments"],
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: readOnly,
      destructiveHint: false,
      idempotentHint: true,
    },
    _meta: {
      route_key: route.route_key,
      connector_key: route.connector_key,
      provider_tool: route.tool_name,
      capability: route.capability,
      mutation_class: route.mutation_class,
      approval_required: route.mutation_class !== "read" || route.approval_required === true,
      policy_version: route.policy_version,
    },
  };
}

async function mcpTools() {
  const routes = await listRoutes();
  return [
    ...routes.map(routeToMcpTool),
    {
      name: "connector_job_status",
      description: "Read durable execution status and receipt hashes for one connector execution job.",
      inputSchema: {
        type: "object",
        properties: { job_id: { type: "string", format: "uuid" } },
        required: ["job_id"],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
    },
  ];
}

async function handleMcp(rpc: Json) {
  const id = (rpc.id ?? null) as RpcId;
  const method = typeof rpc.method === "string" ? rpc.method : "";
  const params = rpc.params && typeof rpc.params === "object" && !Array.isArray(rpc.params) ? rpc.params as Json : {};
  const result = (value: unknown) => json({ jsonrpc: "2.0", id, result: value });
  const rpcError = (code: number, message: string, data?: unknown, status = 400) => json({ jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) } }, status);

  if (rpc.jsonrpc !== "2.0") return rpcError(-32600, "Invalid Request");
  if (method === "initialize") {
    return result({
      protocolVersion: MCP_PROTOCOL_VERSION,
      capabilities: { tools: { listChanged: true } },
      serverInfo: { name: "glaciereq-connector-runtime", version: "2.0.0" },
      instructions: "MCP-native GlacierEQ connector execution gateway. Enabled non-Smithery route policies become MCP tools automatically. Calls enqueue into the durable connector execution runtime; mutation approval, retries, idempotency, budgets, circuit state, and receipts remain authoritative downstream.",
    });
  }
  if (method === "notifications/initialized") return new Response(null, { status: 204 });
  if (method === "ping") return result({});
  if (method === "tools/list") return result({ tools: await mcpTools() });
  if (method === "tools/call") {
    const name = text(params.name, "params.name")!;
    const args = params.arguments && typeof params.arguments === "object" && !Array.isArray(params.arguments) ? params.arguments as Json : {};

    if (name === "connector_job_status") {
      const jobId = text(args.job_id, "job_id")!;
      const job = await loadJob(jobId);
      const payload = job ? { ok: true, job } : { ok: false, error: "job_not_found" };
      return result({ content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload, isError: !job });
    }

    const routes = await listRoutes();
    const route = routes.find((candidate) => routeToolName(candidate.route_key) === name) ?? null;
    if (!route) return rpcError(-32602, "Unknown direct connector tool", { name }, 404);
    const queued = await enqueueRoute(route, args);
    return result({ content: [{ type: "text", text: JSON.stringify(queued) }], structuredContent: queued, isError: false });
  }
  return rpcError(-32601, "Method not found", { method }, 404);
}

Deno.serve(async (req: Request) => {
  try {
    const url = new URL(req.url);
    if (req.method === "GET") {
      const operation = url.searchParams.get("operation") ?? "routes";
      if (operation === "routes") {
        return json({ ok: true, routes: await listRoutes(url.searchParams.get("connector_key")) });
      }
      if (operation === "status") {
        return await jobStatus(text(url.searchParams.get("job_id"), "job_id")!);
      }
      return json({ ok: false, error: "unsupported_operation" }, 400);
    }

    if (req.method !== "POST") return json({ ok: false, error: "method_not_allowed" }, 405);
    const body = await req.json() as Json;
    if (body.jsonrpc === "2.0") return await handleMcp(body);

    const operation = text(body.operation ?? "enqueue", "operation")!;
    if (operation === "enqueue") return await enqueueLegacy(body);
    if (operation === "status") return await jobStatus(text(body.job_id, "job_id")!);
    if (operation === "routes") return json({ ok: true, routes: await listRoutes(text(body.connector_key, "connector_key", false)) });
    return json({ ok: false, error: "unsupported_operation" }, 400);
  } catch (error) {
    return json({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }, 400);
  }
});
