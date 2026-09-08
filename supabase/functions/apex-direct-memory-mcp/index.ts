import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
const PROTOCOL_VERSION = "2025-06-18";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");
const DISPATCHER_URL = `${SUPABASE_URL}/functions/v1/memory-federation-dispatcher`;

type Json = Record<string, unknown>;
type RpcId = string | number | null;
type ToolDef = { name: string; description: string; action: "health" | "preview" | "dispatch"; write: boolean; inputSchema: Json };

const TOOLS: ToolDef[] = [
  { name: "memory_federation_health", description: "Read the live GlacierEQ memory-federation backend state and adapter configuration without exposing secrets.", action: "health", write: false, inputSchema: { type: "object", properties: {}, additionalProperties: false } },
  { name: "memory_federation_preview", description: "Preview one durable memory-federation sync event, including provenance-bound memory/backend policy and whether the direct adapter is configured. Performs no provider call.", action: "preview", write: false, inputSchema: { type: "object", properties: { event_id: { type: "integer", minimum: 1 } }, required: ["event_id"], additionalProperties: false } },
  { name: "memory_federation_dispatch", description: "Execute one claimable memory-federation event through the existing direct provider adapter. Preserves namespace/sensitivity policy, duplicate suppression, leases, provider receipts, error classification, and durable bindings.", action: "dispatch", write: true, inputSchema: { type: "object", properties: { event_id: { type: "integer", minimum: 1 } }, required: ["event_id"], additionalProperties: false } }
];
const BY_NAME = new Map(TOOLS.map((tool) => [tool.name, tool]));

function isServiceRoleRequest(req: Request): boolean { return req.headers.get("authorization") === `Bearer ${SERVICE_ROLE}`; }
function response(body: unknown, status = 200) {
  return new Response(body === null ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "x-content-type-options": "nosniff", "mcp-protocol-version": PROTOCOL_VERSION } });
}
function ok(id: RpcId, result: unknown) { return { jsonrpc: "2.0", id, result }; }
function err(id: RpcId, code: number, message: string, data?: unknown) { return { jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) } }; }
async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function invokeDispatcher(tool: ToolDef, args: Json): Promise<Json> {
  const body: Json = { action: tool.action };
  if (tool.action !== "health") {
    const eventId = Number(args.event_id);
    if (!Number.isSafeInteger(eventId) || eventId <= 0) throw new Error("valid_event_id_required");
    body.event_id = eventId;
  }
  const res = await fetch(DISPATCHER_URL, {
    method: "POST",
    headers: { authorization: `Bearer ${SERVICE_ROLE}`, apikey: SERVICE_ROLE, "content-type": "application/json", "x-glaciereq-origin": "apex-direct-memory-mcp" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(60_000)
  });
  const raw = await res.text();
  let data: unknown = raw;
  try { data = raw ? JSON.parse(raw) : {}; } catch { data = raw; }
  if (!res.ok) {
    const bodyHash = await sha256Hex(raw);
    const requestId = res.headers.get("x-request-id") || undefined;
    throw new Error(`memory_dispatcher_http_${res.status}:body_sha256=${bodyHash}${requestId ? `:request_id=${requestId}` : ""}`);
  }
  return (data && typeof data === "object" && !Array.isArray(data) ? data : { data }) as Json;
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
  if (method === "initialize") return response(ok(id, { protocolVersion: PROTOCOL_VERSION, capabilities: { tools: { listChanged: false } }, serverInfo: { name: "glaciereq-direct-memory", version: "1.1.0" }, instructions: "GlacierEQ-owned direct Memory MCP over the durable memory-federation dispatcher. No Smithery dependency. Provider-specific policy, leases, duplicate suppression, receipts, bindings, and error classification remain authoritative in the dispatcher." }));
  if (method === "notifications/initialized") return new Response(null, { status: 204 });
  if (method === "ping") return response(ok(id, {}));
  if (method === "tools/list") return response(ok(id, { tools: TOOLS.map(({ action, write, ...tool }) => ({ ...tool, annotations: { readOnlyHint: !write, destructiveHint: false, idempotentHint: !write } })) }));
  if (method === "tools/call") {
    const name = typeof params.name === "string" ? params.name : "";
    const tool = BY_NAME.get(name);
    if (!tool) return response(err(id, -32602, "Unknown tool", { name }), 400);
    const args = params.arguments && typeof params.arguments === "object" && !Array.isArray(params.arguments) ? params.arguments as Json : {};
    try { const value = await invokeDispatcher(tool, args); return response(ok(id, { content: [{ type: "text", text: JSON.stringify(value) }], structuredContent: value, isError: false })); }
    catch (e) { const message = e instanceof Error ? e.message : String(e); return response(ok(id, { content: [{ type: "text", text: message }], structuredContent: { ok: false, error: message, tool: name }, isError: true })); }
  }
  return response(err(id, -32601, "Method not found", { method }), 404);
});
