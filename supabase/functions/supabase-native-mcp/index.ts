import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("Supabase runtime unavailable");

const db = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false },
});

type Json = Record<string, unknown>;

const TOOLS = [
  {
    name: "project.health",
    description: "Return Supabase-native MCP control-plane health and catalog counts.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "memory.bulk_scoped",
    description: "Read a large source-grounded canonical L1 memory page for one exact scope. Retrieval is not application. Service-role only; no packet or semantic-provider writes.",
    inputSchema: {
      type: "object",
      properties: {
        scope: { type: "string", enum: ["general", "case", "checkpoint", "matter_index", "checkpoint_index"], default: "general" },
        case_id: { type: "string", maxLength: 200, default: "" },
        after_id: { type: "string", default: "" },
        max_records: { type: "integer", minimum: 1, maximum: 5000, default: 2048 },
        max_bytes: { type: "integer", minimum: 65536, maximum: 2000000, default: 1500000 },
        include_content: { type: "boolean", default: true },
        include_metadata: { type: "boolean", default: false },
      },
      additionalProperties: false,
    },
  },
  {
    name: "catalog.search",
    description: "Search the persisted MCP tool catalog by name, description, or feature group.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        limit: { type: "integer", minimum: 1, maximum: 100, default: 25 },
        includeMutating: { type: "boolean", default: false },
        connectorKey: { type: ["string", "null"] },
      },
      additionalProperties: false,
    },
  },
  {
    name: "catalog.get",
    description: "Fetch one active tool definition from the persisted MCP tool catalog.",
    inputSchema: {
      type: "object",
      required: ["toolName"],
      properties: { toolName: { type: "string", minLength: 1 } },
      additionalProperties: false,
    },
  },
  {
    name: "schema.list_tables",
    description: "List table/view metadata without returning table contents.",
    inputSchema: {
      type: "object",
      properties: {
        schemas: { type: "array", items: { type: "string" }, default: ["public"] },
        limit: { type: "integer", minimum: 1, maximum: 2000, default: 500 },
      },
      additionalProperties: false,
    },
  },
  {
    name: "schema.list_extensions",
    description: "List installed Postgres extensions and versions.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "schema.list_migrations",
    description: "List recent Supabase migration identifiers without returning migration SQL.",
    inputSchema: {
      type: "object",
      properties: { limit: { type: "integer", minimum: 1, maximum: 1000, default: 200 } },
      additionalProperties: false,
    },
  },
  {
    name: "connectors.list",
    description: "List registered Everything-MCP connectors. Service-role only.",
    inputSchema: {
      type: "object",
      properties: { limit: { type: "integer", minimum: 1, maximum: 500, default: 100 } },
      additionalProperties: false,
    },
  },
  {
    name: "connectors.get",
    description: "Get one Everything-MCP connector by connector key. Service-role only.",
    inputSchema: {
      type: "object",
      required: ["connectorKey"],
      properties: { connectorKey: { type: "string", minLength: 1 } },
      additionalProperties: false,
    },
  },
  {
    name: "runs.list",
    description: "List recent Everything-MCP execution receipts. Service-role only.",
    inputSchema: {
      type: "object",
      properties: {
        status: { type: ["string", "null"] },
        limit: { type: "integer", minimum: 1, maximum: 200, default: 50 },
      },
      additionalProperties: false,
    },
  },
  {
    name: "runs.get",
    description: "Get one Everything-MCP run and its step receipts. Service-role only.",
    inputSchema: {
      type: "object",
      required: ["runId"],
      properties: { runId: { type: "string", minLength: 1 } },
      additionalProperties: false,
    },
  },
  {
    name: "audit.recent",
    description: "List recent security-audit records for MCP/control-plane components. Service-role only.",
    inputSchema: {
      type: "object",
      properties: { limit: { type: "integer", minimum: 1, maximum: 200, default: 50 } },
      additionalProperties: false,
    },
  },
  {
    name: "storage.list_buckets",
    description: "List Supabase Storage buckets. Service-role only.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "storage.list_objects",
    description: "List objects in one Supabase Storage bucket. Service-role only.",
    inputSchema: {
      type: "object",
      required: ["bucket"],
      properties: {
        bucket: { type: "string", minLength: 1 },
        path: { type: "string", default: "" },
        limit: { type: "integer", minimum: 1, maximum: 1000, default: 100 },
        offset: { type: "integer", minimum: 0, default: 0 },
        search: { type: ["string", "null"] },
      },
      additionalProperties: false,
    },
  },
  {
    name: "storage.create_signed_url",
    description: "Create a short-lived signed read URL for one Storage object. Service-role only.",
    inputSchema: {
      type: "object",
      required: ["bucket", "path"],
      properties: {
        bucket: { type: "string", minLength: 1 },
        path: { type: "string", minLength: 1 },
        expiresIn: { type: "integer", minimum: 60, maximum: 3600, default: 300 },
      },
      additionalProperties: false,
    },
  },
] as const;

const SERVICE_ONLY = new Set([
  "memory.bulk_scoped",
  "connectors.list",
  "connectors.get",
  "runs.list",
  "runs.get",
  "audit.recent",
  "storage.list_buckets",
  "storage.list_objects",
  "storage.create_signed_url",
]);

function obj(value: unknown): Json {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function jwtPayload(token: string): Json {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("invalid_jwt");
  const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(parts[1].length / 4) * 4, "=");
  return obj(JSON.parse(atob(normalized)));
}

function roleFromRequest(req: Request): string {
  const auth = req.headers.get("authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return "unknown";
  const token = auth.slice(7).trim();
  if (token && token === SERVICE_ROLE) return "service_role";
  try { return str(jwtPayload(token).role) || "unknown"; }
  catch { return "unknown"; }
}

function rpcResult(id: unknown, result: unknown, status = 200): Response {
  return Response.json({ jsonrpc: "2.0", id: id ?? null, result }, {
    status,
    headers: { "cache-control": "no-store", "x-content-type-options": "nosniff" },
  });
}

function rpcError(id: unknown, code: number, message: string, data?: unknown, status = 400): Response {
  return Response.json({ jsonrpc: "2.0", id: id ?? null, error: { code, message, ...(data === undefined ? {} : { data }) } }, {
    status,
    headers: { "cache-control": "no-store", "x-content-type-options": "nosniff" },
  });
}

function toolResult(value: unknown) {
  return {
    content: [{ type: "text", text: JSON.stringify(value) }],
    structuredContent: value,
    isError: false,
  };
}

function asLimit(value: unknown, fallback: number, max: number) {
  const n = Number(value ?? fallback);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(Math.max(Math.trunc(n), 1), max);
}

async function health() {
  const [{ count: connectors }, { count: tools }, { count: running }] = await Promise.all([
    db.from("everything_mcp_connectors").select("*", { count: "exact", head: true }),
    db.from("everything_mcp_tools").select("*", { count: "exact", head: true }).eq("enabled", true),
    db.from("everything_mcp_runs").select("*", { count: "exact", head: true }).eq("status", "running"),
  ]);
  return {
    ok: true,
    server: "supabase-native-mcp",
    version: "1.0.0",
    project: new URL(SUPABASE_URL).hostname.split(".")[0],
    connectors: connectors ?? 0,
    activeTools: tools ?? 0,
    runningReceipts: running ?? 0,
    protocolVersion: "2024-11-05",
  };
}

async function callTool(name: string, args: Json, role: string): Promise<unknown> {
  if (SERVICE_ONLY.has(name) && role !== "service_role") {
    throw new Error("service_role_required");
  }

  switch (name) {
    case "project.health":
      return health();

    case "memory.bulk_scoped": {
      const scope = str(args.scope || "general");
      if (!["general", "case", "checkpoint", "matter_index", "checkpoint_index"].includes(scope)) {
        throw new Error("unsupported_memory_scope");
      }
      const caseId = str(args.case_id).trim();
      if (caseId.length > 200 || caseId.includes(String.fromCharCode(10)) || caseId.includes(String.fromCharCode(13))) throw new Error("invalid_case_id");
      if (scope === "case" || scope === "checkpoint") {
        if (!caseId || (scope === "checkpoint") !== caseId.startsWith("chk_")) {
          throw new Error("exact_scope_identity_required");
        }
      } else if (caseId) throw new Error("case_id_forbidden_for_general_or_index");
      const cursor = str(args.after_id).trim();
      if (cursor && !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(cursor)) {
        throw new Error("invalid_memory_cursor");
      }
      const maxRecords = Number(args.max_records ?? 2048);
      const maxBytes = Number(args.max_bytes ?? 1500000);
      if (!Number.isInteger(maxRecords) || maxRecords < 1 || maxRecords > 5000) throw new Error("invalid_max_records");
      if (!Number.isInteger(maxBytes) || maxBytes < 65536 || maxBytes > 2000000) throw new Error("invalid_max_bytes");
      if (args.include_content !== undefined && typeof args.include_content !== "boolean") throw new Error("invalid_include_content");
      if (args.include_metadata !== undefined && typeof args.include_metadata !== "boolean") throw new Error("invalid_include_metadata");
      const { data, error } = await db.rpc("memory_organized_batch_v1", {
        p_scope: scope,
        p_case_id: caseId || null,
        p_after_id: cursor || null,
        p_max_records: maxRecords,
        p_max_bytes: maxBytes,
        p_include_content: args.include_content !== false,
        p_include_metadata: args.include_metadata === true,
      });
      if (error) throw new Error("canonical_memory_rpc_failed: " + error.code);
      if (!data || !Array.isArray(data.items) || data.scope !== scope || data.case_id !== (caseId || null)) {
        throw new Error("canonical_memory_page_invalid");
      }
      const requiredScope = scope === "general" ? "general"
        : (scope === "case" || scope === "matter_index") ? "matter" : "checkpoint";
      const trusted = new Set(["casey", "operator", null]);
      const items = data.items.filter((item: unknown) => {
        if (!item || typeof item !== "object" || Array.isArray(item)) return false;
        const memory = item as Json;
        const itemCase = memory.case_id;
        const itemScope = itemCase === null ? "general"
          : typeof itemCase === "string" && itemCase.startsWith("chk_") ? "checkpoint" : "matter";
        return trusted.has(memory.user_id as string | null)
          && itemScope === requiredScope
          && ((scope !== "case" && scope !== "checkpoint") || itemCase === caseId)
          && ((scope !== "matter_index" && scope !== "checkpoint_index")
            || (!Object.hasOwn(memory, "content") && !Object.hasOwn(memory, "metadata")));
      });
      return {
        ok: true, route: "L1:supabase_native_bulk", application_status: "retrieved_not_applied",
        schema: data.schema, source: data.source, scope, case_id: caseId || null,
        items, count: items.length, backend_count: data.item_count,
        excluded_identity_or_scope: data.items.length - items.length,
        after_id: data.after_id, has_more: data.has_more,
        backend_page_sha256: data.page_sha256, backend_item_bytes: data.item_bytes,
      };
    }

    case "catalog.search": {
      const includeMutating = role === "service_role" && args.includeMutating === true;
      const { data, error } = await db.rpc("search_everything_mcp_tools", {
        p_query: str(args.query),
        p_limit: asLimit(args.limit, 25, 100),
        p_include_mutating: includeMutating,
        p_connector_key: str(args.connectorKey) || null,
      });
      if (error) throw error;
      return { count: data?.length ?? 0, tools: data ?? [] };
    }

    case "catalog.get": {
      const toolName = str(args.toolName).trim();
      if (!toolName) throw new Error("toolName_required");
      const { data, error } = await db
        .from("everything_mcp_tools")
        .select("tool_name,display_name,description,feature_group,operation_kind,risk_level,requires_confirmation,input_schema,output_schema,annotations,schema_hash,last_seen_at,enabled")
        .eq("tool_name", toolName)
        .eq("enabled", true)
        .maybeSingle();
      if (error) throw error;
      return data ?? { found: false, toolName };
    }

    case "schema.list_tables": {
      const requested = Array.isArray(args.schemas) ? args.schemas.filter((x) => typeof x === "string").slice(0, 20) : ["public"];
      const schemas = requested.length ? requested : ["public"];
      const { data, error } = await db.rpc("mcp_schema_inventory", {
        p_schemas: schemas,
        p_limit: asLimit(args.limit, 500, 2000),
      });
      if (error) throw error;
      return { count: data?.length ?? 0, tables: data ?? [] };
    }

    case "schema.list_extensions": {
      const { data, error } = await db.rpc("mcp_extension_inventory");
      if (error) throw error;
      return { count: data?.length ?? 0, extensions: data ?? [] };
    }

    case "schema.list_migrations": {
      const { data, error } = await db.rpc("mcp_migration_inventory", { p_limit: asLimit(args.limit, 200, 1000) });
      if (error) throw error;
      return { migrations: data ?? [] };
    }

    case "connectors.list": {
      const { data, error } = await db
        .from("everything_mcp_connectors")
        .select("connector_key,display_name,plane,role,read_enabled,write_enabled,default_mode,risk_level,status,capabilities,blocked_actions,updated_at")
        .order("connector_key")
        .limit(asLimit(args.limit, 100, 500));
      if (error) throw error;
      return { count: data?.length ?? 0, connectors: data ?? [] };
    }

    case "connectors.get": {
      const key = str(args.connectorKey).trim();
      if (!key) throw new Error("connectorKey_required");
      const { data, error } = await db
        .from("everything_mcp_connectors")
        .select("*")
        .eq("connector_key", key)
        .maybeSingle();
      if (error) throw error;
      return data ?? { found: false, connectorKey: key };
    }

    case "runs.list": {
      let query = db
        .from("everything_mcp_runs")
        .select("id,correlation_id,requested_by,intent,scope,safety_mode,status,priority,created_at,started_at,completed_at,domain_key,skill_key,route_key,idempotency_key,human_review_required")
        .order("created_at", { ascending: false })
        .limit(asLimit(args.limit, 50, 200));
      const status = str(args.status).trim();
      if (status) query = query.eq("status", status);
      const { data, error } = await query;
      if (error) throw error;
      return { count: data?.length ?? 0, runs: data ?? [] };
    }

    case "runs.get": {
      const runId = str(args.runId).trim();
      if (!runId) throw new Error("runId_required");
      const [{ data: run, error: runError }, { data: steps, error: stepsError }] = await Promise.all([
        db.from("everything_mcp_runs").select("*").eq("id", runId).maybeSingle(),
        db.from("everything_mcp_run_steps").select("*").eq("run_id", runId).order("step_index"),
      ]);
      if (runError) throw runError;
      if (stepsError) throw stepsError;
      return { run, steps: steps ?? [] };
    }

    case "audit.recent": {
      const { data, error } = await db
        .from("ops_security_audit")
        .select("id,event_type,severity,component,summary,details,source_ref,actor,created_at")
        .or("component.ilike.%mcp%,component.ilike.%connector%,component.ilike.%control%")
        .order("created_at", { ascending: false })
        .limit(asLimit(args.limit, 50, 200));
      if (error) throw error;
      return { count: data?.length ?? 0, events: data ?? [] };
    }

    case "storage.list_buckets": {
      const { data, error } = await db.storage.listBuckets();
      if (error) throw error;
      return { count: data?.length ?? 0, buckets: data ?? [] };
    }

    case "storage.list_objects": {
      const bucket = str(args.bucket).trim();
      if (!bucket) throw new Error("bucket_required");
      const { data, error } = await db.storage.from(bucket).list(str(args.path), {
        limit: asLimit(args.limit, 100, 1000),
        offset: Math.max(0, Math.trunc(Number(args.offset ?? 0) || 0)),
        search: str(args.search) || undefined,
        sortBy: { column: "name", order: "asc" },
      });
      if (error) throw error;
      return { bucket, count: data?.length ?? 0, objects: data ?? [] };
    }

    case "storage.create_signed_url": {
      const bucket = str(args.bucket).trim();
      const path = str(args.path).trim();
      if (!bucket || !path) throw new Error("bucket_and_path_required");
      const expiresIn = Math.min(Math.max(Math.trunc(Number(args.expiresIn ?? 300) || 300), 60), 3600);
      const { data, error } = await db.storage.from(bucket).createSignedUrl(path, expiresIn);
      if (error) throw error;
      return { bucket, path, expiresIn, signedUrl: data.signedUrl };
    }

    default:
      throw new Error("unknown_tool");
  }
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return new Response("MCP uses POST", { status: 405 });

  const role = roleFromRequest(req);
  if (role !== "authenticated" && role !== "service_role") {
    return rpcError(null, -32001, "Authenticated or service role required.", undefined, 403);
  }

  let body: Json;
  try {
    const raw = await req.text();
    if (new TextEncoder().encode(raw).length > 262_144) {
      return rpcError(null, -32600, "Request too large.", undefined, 413);
    }
    body = obj(JSON.parse(raw || "{}"));
  } catch {
    return rpcError(null, -32700, "Parse error.", undefined, 400);
  }

  const id = body.id;
  const method = str(body.method);

  if (method === "initialize") {
    return rpcResult(id, {
      protocolVersion: "2024-11-05",
      capabilities: { tools: { listChanged: false } },
      serverInfo: { name: "GlacierEQ Supabase Native MCP", version: "1.0.0" },
    });
  }

  if (method === "notifications/initialized") return new Response(null, { status: 202 });
  if (method === "ping") return rpcResult(id, { ok: true });

  if (method === "tools/list") {
    const tools = role === "service_role"
      ? TOOLS
      : TOOLS.filter((tool) => !SERVICE_ONLY.has(tool.name));
    return rpcResult(id, { tools });
  }

  if (method === "tools/call") {
    const params = obj(body.params);
    const name = str(params.name).trim();
    if (!name) return rpcError(id, -32602, "Tool name required.");
    if (!TOOLS.some((tool) => tool.name === name)) return rpcError(id, -32601, `Unknown tool '${name}'.`, undefined, 404);

    try {
      const started = Date.now();
      const result = await callTool(name, obj(params.arguments), role);
      await db.from("ops_security_audit").insert({
        event_type: "SUPABASE_NATIVE_MCP_TOOL_CALL",
        severity: "INFO",
        component: "supabase-native-mcp",
        summary: `Native MCP tool '${name}' completed`,
        details: { tool_name: name, role, latency_ms: Date.now() - started },
        source_ref: "edge-function:supabase-native-mcp:v1",
        actor: role,
      });
      return rpcResult(id, toolResult(result));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await db.from("ops_security_audit").insert({
        event_type: "SUPABASE_NATIVE_MCP_TOOL_FAILURE",
        severity: "WARN",
        component: "supabase-native-mcp",
        summary: message,
        details: { tool_name: name, role },
        source_ref: "edge-function:supabase-native-mcp:v1",
        actor: role,
      });
      return rpcError(id, -32000, message, undefined, 500);
    }
  }

  return rpcError(id, -32601, `Method '${method}' not found.`, undefined, 404);
});
