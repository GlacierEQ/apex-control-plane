import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
const PROTOCOL_VERSION = "2025-06-18";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

type Json = Record<string, unknown>;
type RpcId = string | number | null;
type PluginKey = "github" | "notion" | "memory" | "runtime";
const PLUGINS: Record<PluginKey, { key: string; server: string; endpoint: string; prefix: string }> = {
  github: { key: "github.direct_mcp", server: "apex-direct-github-mcp", endpoint: `${SUPABASE_URL}/functions/v1/apex-direct-github-mcp`, prefix: "github_" },
  notion: { key: "notion.direct_mcp", server: "apex-direct-notion-mcp", endpoint: `${SUPABASE_URL}/functions/v1/apex-direct-notion-mcp`, prefix: "notion_" },
  memory: { key: "memory.direct_mcp", server: "apex-direct-memory-mcp", endpoint: `${SUPABASE_URL}/functions/v1/apex-direct-memory-mcp`, prefix: "memory_" },
  runtime: { key: "connector.runtime_mcp", server: "apex-connector-tool-gateway", endpoint: `${SUPABASE_URL}/functions/v1/apex-connector-tool-gateway`, prefix: "connector_" }
};

function isServiceRoleRequest(req: Request): boolean { return req.headers.get("authorization") === `Bearer ${SERVICE_ROLE}`; }
function response(body: unknown, status = 200): Response {
  return new Response(body === null ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "x-content-type-options": "nosniff", "mcp-protocol-version": PROTOCOL_VERSION } });
}
function ok(id: RpcId, result: unknown) { return { jsonrpc: "2.0", id, result }; }
function err(id: RpcId, code: number, message: string, data?: unknown) { return { jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) } }; }
async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function childRpc(plugin: PluginKey, payload: Json): Promise<Json> {
  const res = await fetch(PLUGINS[plugin].endpoint, {
    method: "POST",
    headers: { authorization: `Bearer ${SERVICE_ROLE}`, apikey: SERVICE_ROLE, "content-type": "application/json", "x-glaciereq-origin": "apex-direct-mcp-fabric" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(60_000)
  });
  const raw = await res.text();
  let data: unknown = raw;
  try { data = raw ? JSON.parse(raw) : {}; } catch { data = raw; }
  if (!res.ok) {
    const bodyHash = await sha256Hex(raw);
    const requestId = res.headers.get("x-request-id") || undefined;
    throw new Error(`child_${plugin}_http_${res.status}:body_sha256=${bodyHash}${requestId ? `:request_id=${requestId}` : ""}`);
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error(`child_${plugin}_invalid_rpc`);
  return data as Json;
}

async function childTools(plugin: PluginKey): Promise<Json[]> {
  const reply = await childRpc(plugin, { jsonrpc: "2.0", id: `fabric-list-${plugin}`, method: "tools/list", params: {} });
  const result = reply.result && typeof reply.result === "object" && !Array.isArray(reply.result) ? reply.result as Json : {};
  return Array.isArray(result.tools) ? result.tools.filter((tool) => tool && typeof tool === "object") as Json[] : [];
}
function pluginForTool(name: string): PluginKey | null {
  for (const [key, plugin] of Object.entries(PLUGINS) as [PluginKey, (typeof PLUGINS)[PluginKey]][]) if (name.startsWith(plugin.prefix)) return key;
  return null;
}
async function pluginSnapshot() {
  return Promise.all((Object.keys(PLUGINS) as PluginKey[]).map(async (key) => {
    try {
      const tools = await childTools(key);
      return { key: PLUGINS[key].key, server: PLUGINS[key].server, status: "active", tool_count: tools.length, tools: tools.map((tool) => tool.name).filter((name) => typeof name === "string") };
    } catch (e) {
      return { key: PLUGINS[key].key, server: PLUGINS[key].server, status: "degraded", tool_count: 0, error: e instanceof Error ? e.message : String(e) };
    }
  }));
}
async function resilientToolList(): Promise<Json[]> {
  const sets = await Promise.all((Object.keys(PLUGINS) as PluginKey[]).map(async (key) => {
    try { return await childTools(key); } catch { return []; }
  }));
  return sets.flat();
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return response({ ok: false, error: "method_not_allowed" }, 405);
  if (!isServiceRoleRequest(req)) return response(err(null, -32001, "service_role_required"), 403);
  let rpc: Json;
  try { const value = await req.json(); if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(); rpc = value as Json; }
  catch { return response(err(null, -32700, "Parse error"), 400); }
  const id = (rpc.id ?? null) as RpcId;
  const method = typeof rpc.method === "string" ? rpc.method : "";
  const params = rpc.params && typeof rpc.params === "object" && !Array.isArray(rpc.params) ? rpc.params as Json : {};
  if (rpc.jsonrpc !== "2.0") return response(err(id, -32600, "Invalid Request"), 400);
  if (method === "initialize") return response(ok(id, { protocolVersion: PROTOCOL_VERSION, capabilities: { tools: { listChanged: true } }, serverInfo: { name: "glaciereq-direct-mcp-fabric", version: "3.1.0" }, instructions: "GlacierEQ-owned direct MCP plugin fabric. Child MCP servers remain authoritative and independent; one degraded plugin does not suppress healthy peer tools. Smithery is excluded from direct connector execution." }));
  if (method === "notifications/initialized") return new Response(null, { status: 204 });
  if (method === "ping") return response(ok(id, {}));
  if (method === "tools/list") {
    const tools = await resilientToolList();
    tools.push({ name: "apex_plugins_list", description: "List GlacierEQ-owned direct MCP plugins and their live child tool surfaces.", inputSchema: { type: "object", properties: {}, additionalProperties: false }, annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true } });
    return response(ok(id, { tools }));
  }
  if (method === "tools/call") {
    const name = typeof params.name === "string" ? params.name : "";
    if (name === "apex_plugins_list") {
      const plugins = await pluginSnapshot();
      const structuredContent = { plugins, plugin_count: plugins.length, provider_tool_count: plugins.reduce((sum, plugin) => sum + Number(plugin.tool_count || 0), 0), smithery_required: false, transport: "mcp_streamable_http", protocol_version: PROTOCOL_VERSION };
      return response(ok(id, { content: [{ type: "text", text: JSON.stringify(structuredContent) }], structuredContent, isError: false }));
    }
    const plugin = pluginForTool(name);
    if (!plugin) return response(err(id, -32602, "Unknown tool", { name }), 400);
    const args = params.arguments && typeof params.arguments === "object" && !Array.isArray(params.arguments) ? params.arguments as Json : {};
    try { return response(await childRpc(plugin, { jsonrpc: "2.0", id, method: "tools/call", params: { name, arguments: args } })); }
    catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      return response(ok(id, { content: [{ type: "text", text: message }], structuredContent: { ok: false, error: message, tool: name, plugin: PLUGINS[plugin].key }, isError: true }));
    }
  }
  return response(err(id, -32601, "Method not found", { method }), 404);
});
