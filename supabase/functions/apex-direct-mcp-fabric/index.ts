import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const PROTOCOL_VERSION = "2025-06-18";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

type Json = Record<string, unknown>;
type RpcId = string | number | null;
type PluginKey = "github" | "notion" | "memory";

const PLUGINS: Record<PluginKey, { key: string; server: string; endpoint: string; prefix: string }> = {
  github: {
    key: "github.direct_mcp",
    server: "apex-direct-github-mcp",
    endpoint: `${SUPABASE_URL}/functions/v1/apex-direct-github-mcp`,
    prefix: "github_",
  },
  notion: {
    key: "notion.direct_mcp",
    server: "apex-direct-notion-mcp",
    endpoint: `${SUPABASE_URL}/functions/v1/apex-direct-notion-mcp`,
    prefix: "notion_",
  },
  memory: {
    key: "memory.direct_mcp",
    server: "apex-direct-memory-mcp",
    endpoint: `${SUPABASE_URL}/functions/v1/apex-direct-memory-mcp`,
    prefix: "memory_",
  },
};

function decodeJwt(req: Request): Json {
  const auth = req.headers.get("authorization") || "";
  if (!auth.startsWith("Bearer ")) return {};
  const parts = auth.slice(7).trim().split(".");
  if (parts.length !== 3) return {};
  try {
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(parts[1].length / 4) * 4, "=");
    return JSON.parse(atob(normalized));
  } catch {
    return {};
  }
}

function response(body: unknown, status = 200): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      "mcp-protocol-version": PROTOCOL_VERSION,
    },
  });
}

function ok(id: RpcId, result: unknown) {
  return { jsonrpc: "2.0", id, result };
}

function err(id: RpcId, code: number, message: string, data?: unknown) {
  return { jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) } };
}

async function childRpc(plugin: PluginKey, payload: Json): Promise<Json> {
  const res = await fetch(PLUGINS[plugin].endpoint, {
    method: "POST",
    headers: {
      authorization: `Bearer ${SERVICE_ROLE}`,
      apikey: SERVICE_ROLE,
      "content-type": "application/json",
      "x-glaciereq-origin": "apex-direct-mcp-fabric",
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(60_000),
  });

  const raw = await res.text();
  let data: unknown = raw;
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    // Keep bounded raw error only.
  }

  if (!res.ok) {
    throw new Error(
      `child_${plugin}_http_${res.status}:${typeof data === "string" ? data.slice(0, 1000) : JSON.stringify(data).slice(0, 1000)}`,
    );
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error(`child_${plugin}_invalid_rpc`);
  return data as Json;
}

async function childTools(plugin: PluginKey): Promise<Json[]> {
  const reply = await childRpc(plugin, {
    jsonrpc: "2.0",
    id: `fabric-list-${plugin}`,
    method: "tools/list",
    params: {},
  });
  const result = reply.result && typeof reply.result === "object" && !Array.isArray(reply.result)
    ? reply.result as Json
    : {};
  return Array.isArray(result.tools) ? result.tools.filter((tool) => tool && typeof tool === "object") as Json[] : [];
}

function pluginForTool(name: string): PluginKey | null {
  for (const [key, plugin] of Object.entries(PLUGINS) as [PluginKey, (typeof PLUGINS)[PluginKey]][]) {
    if (name.startsWith(plugin.prefix)) return key;
  }
  return null;
}

async function pluginSnapshot() {
  return Promise.all(
    (Object.keys(PLUGINS) as PluginKey[]).map(async (key) => {
      try {
        const tools = await childTools(key);
        return {
          key: PLUGINS[key].key,
          server: PLUGINS[key].server,
          status: "active",
          tool_count: tools.length,
          tools: tools.map((tool) => tool.name).filter((name) => typeof name === "string"),
        };
      } catch (error) {
        return {
          key: PLUGINS[key].key,
          server: PLUGINS[key].server,
          status: "degraded",
          tool_count: 0,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }),
  );
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return response({ ok: false, error: "method_not_allowed" }, 405);

  const claims = decodeJwt(req);
  if (claims.role !== "service_role") return response(err(null, -32001, "service_role_required"), 403);

  let rpc: Json;
  try {
    const value = await req.json();
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error();
    rpc = value as Json;
  } catch {
    return response(err(null, -32700, "Parse error"), 400);
  }

  const id = (rpc.id ?? null) as RpcId;
  const method = typeof rpc.method === "string" ? rpc.method : "";
  const params = rpc.params && typeof rpc.params === "object" && !Array.isArray(rpc.params) ? rpc.params as Json : {};
  if (rpc.jsonrpc !== "2.0") return response(err(id, -32600, "Invalid Request"), 400);

  if (method === "initialize") {
    return response(ok(id, {
      protocolVersion: PROTOCOL_VERSION,
      capabilities: { tools: { listChanged: true } },
      serverInfo: { name: "glaciereq-direct-mcp-fabric", version: "2.0.0" },
      instructions: "GlacierEQ-owned direct MCP plugin fabric. Child MCP servers are authoritative for their own tool contracts. Current direct plugins: GitHub, Notion, Memory. Smithery is not required on these routes.",
    }));
  }

  if (method === "notifications/initialized") return new Response(null, { status: 204 });
  if (method === "ping") return response(ok(id, {}));

  if (method === "tools/list") {
    const childSets = await Promise.all((Object.keys(PLUGINS) as PluginKey[]).map(childTools));
    const tools = childSets.flat();
    tools.push({
      name: "apex_plugins_list",
      description: "List GlacierEQ-owned direct MCP plugins and their live child tool surfaces.",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
    });
    return response(ok(id, { tools }));
  }

  if (method === "tools/call") {
    const name = typeof params.name === "string" ? params.name : "";
    if (name === "apex_plugins_list") {
      const plugins = await pluginSnapshot();
      const structuredContent = {
        plugins,
        plugin_count: plugins.length,
        provider_tool_count: plugins.reduce((sum, plugin) => sum + Number(plugin.tool_count || 0), 0),
        smithery_required: false,
        transport: "mcp_streamable_http",
        protocol_version: PROTOCOL_VERSION,
      };
      return response(ok(id, {
        content: [{ type: "text", text: JSON.stringify(structuredContent) }],
        structuredContent,
        isError: false,
      }));
    }

    const plugin = pluginForTool(name);
    if (!plugin) return response(err(id, -32602, "Unknown tool", { name }), 400);

    const args = params.arguments && typeof params.arguments === "object" && !Array.isArray(params.arguments)
      ? params.arguments as Json
      : {};
    try {
      return response(await childRpc(plugin, {
        jsonrpc: "2.0",
        id,
        method: "tools/call",
        params: { name, arguments: args },
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return response(ok(id, {
        content: [{ type: "text", text: message }],
        structuredContent: { ok: false, error: message, tool: name, plugin: PLUGINS[plugin].key },
        isError: true,
      }));
    }
  }

  return response(err(id, -32601, "Method not found", { method }), 404);
});
