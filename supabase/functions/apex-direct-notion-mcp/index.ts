import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
const NOTION_VERSION = "2026-03-11";
const PROTOCOL_VERSION = "2025-06-18";
const SERVER_NAME = "glaciereq-direct-notion";
const SERVER_VERSION = "1.1.0";
const API = "https://api.notion.com/v1";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, { auth: { persistSession: false, autoRefreshToken: false } });
type Json = Record<string, unknown>;
type RpcId = string | number | null;
type Tool = { name: string; description: string; inputSchema: Json };

const TOOLS: Tool[] = [
  { name: "notion_search", description: "Search the Operator's directly connected Notion workspace without Smithery.", inputSchema: { type: "object", properties: { query: { type: "string", minLength: 1, maxLength: 500 }, limit: { type: "integer", minimum: 1, maximum: 100 } }, required: ["query"], additionalProperties: false } },
  { name: "notion_page_get", description: "Read one Notion page by page ID through the direct Notion API.", inputSchema: { type: "object", properties: { page_id: { type: "string", minLength: 16, maxLength: 64 } }, required: ["page_id"], additionalProperties: false } },
  { name: "notion_block_children", description: "Read child blocks for a Notion page or block, preserving provider IDs and pagination.", inputSchema: { type: "object", properties: { block_id: { type: "string", minLength: 16, maxLength: 64 }, page_size: { type: "integer", minimum: 1, maximum: 100 }, start_cursor: { type: "string" } }, required: ["block_id"], additionalProperties: false } }
];

function isServiceRoleRequest(req: Request): boolean {
  return req.headers.get("authorization") === `Bearer ${SERVICE_ROLE}`;
}
function response(body: unknown, status = 200): Response {
  return new Response(body === null ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "x-content-type-options": "nosniff", "mcp-protocol-version": PROTOCOL_VERSION } });
}
function result(id: RpcId, value: unknown) { return { jsonrpc: "2.0", id, result: value }; }
function error(id: RpcId, code: number, message: string, data?: unknown) { return { jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) } }; }
function boundedInteger(value: unknown, fallback: number, min: number, max: number, field: string): number {
  if (value == null) return fallback;
  if (typeof value !== "number" || !Number.isInteger(value) || value < min || value > max) throw new Error(`${field}_must_be_integer_${min}_${max}`);
  return value;
}
async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function notionToken(): Promise<string> {
  const { data, error: rpcError } = await admin.rpc("get_apex_notion_token");
  if (rpcError || typeof data !== "string" || !data) throw new Error("notion_not_connected");
  return data;
}

async function notion(path: string, init: RequestInit = {}): Promise<Json> {
  const token = await notionToken();
  const res = await fetch(API + path, {
    ...init,
    signal: init.signal || AbortSignal.timeout(20_000),
    headers: { authorization: `Bearer ${token}`, "notion-version": NOTION_VERSION, "content-type": "application/json", ...(init.headers || {}) }
  });
  const raw = await res.text();
  let data: unknown = raw;
  try { data = raw ? JSON.parse(raw) : {}; } catch { data = raw; }
  if (!res.ok) {
    const bodyHash = await sha256Hex(raw);
    const requestId = res.headers.get("x-request-id") || undefined;
    throw new Error(`notion_http_${res.status}:body_sha256=${bodyHash}${requestId ? `:request_id=${requestId}` : ""}`);
  }
  return (data && typeof data === "object" && !Array.isArray(data) ? data : { data }) as Json;
}

function richTextPlain(value: unknown): string {
  if (!Array.isArray(value)) return "";
  return value.map((x: any) => x?.plain_text || x?.text?.content || "").join("").trim();
}
function titleOf(item: any): string {
  const topLevel = richTextPlain(item?.title);
  if (topLevel) return topLevel;
  const properties = item?.properties || {};
  for (const value of Object.values<any>(properties)) {
    if (value?.type === "title") {
      const title = richTextPlain(value?.title);
      if (title) return title;
    }
  }
  return "Untitled";
}

async function callTool(name: string, args: Json): Promise<Json> {
  if (name === "notion_search") {
    const query = typeof args.query === "string" ? args.query.trim() : "";
    if (!query) throw new Error("query_required");
    const limit = boundedInteger(args.limit, 20, 1, 100, "limit");
    const payload = await notion("/search", { method: "POST", body: JSON.stringify({ query, page_size: limit, sort: { direction: "descending", timestamp: "last_edited_time" } }) });
    const rows = Array.isArray((payload as any).results) ? (payload as any).results : [];
    return { ok: true, provider: "notion", direct_api: true, query, result_count: rows.length, results: rows.slice(0, limit).map((item: any) => ({ id: item?.id, object: item?.object, url: item?.url, last_edited_time: item?.last_edited_time, title: titleOf(item) })) };
  }
  if (name === "notion_page_get") {
    const pageId = typeof args.page_id === "string" ? args.page_id.trim() : "";
    if (!pageId) throw new Error("page_id_required");
    const page = await notion(`/pages/${encodeURIComponent(pageId)}`);
    return { ok: true, provider: "notion", direct_api: true, page };
  }
  if (name === "notion_block_children") {
    const blockId = typeof args.block_id === "string" ? args.block_id.trim() : "";
    if (!blockId) throw new Error("block_id_required");
    const pageSize = boundedInteger(args.page_size, 100, 1, 100, "page_size");
    const search = new URLSearchParams({ page_size: String(pageSize) });
    if (typeof args.start_cursor === "string" && args.start_cursor) search.set("start_cursor", args.start_cursor);
    const payload = await notion(`/blocks/${encodeURIComponent(blockId)}/children?${search.toString()}`);
    return { ok: true, provider: "notion", direct_api: true, block_id: blockId, ...payload };
  }
  throw new Error("unknown_tool");
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return response({ ok: false, error: "method_not_allowed" }, 405);
  if (!isServiceRoleRequest(req)) return response(error(null, -32001, "service_role_required"), 403);
  let rpc: Json;
  try { const value = await req.json(); if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(); rpc = value as Json; }
  catch { return response(error(null, -32700, "Parse error"), 400); }
  const id = (rpc.id ?? null) as RpcId;
  const method = typeof rpc.method === "string" ? rpc.method : "";
  const params = rpc.params && typeof rpc.params === "object" && !Array.isArray(rpc.params) ? rpc.params as Json : {};
  if (rpc.jsonrpc !== "2.0") return response(error(id, -32600, "Invalid Request"), 400);
  if (method === "initialize") return response(result(id, { protocolVersion: PROTOCOL_VERSION, capabilities: { tools: { listChanged: false } }, serverInfo: { name: SERVER_NAME, version: SERVER_VERSION }, instructions: "GlacierEQ-owned direct Notion MCP. Provider calls use the service-role-only Supabase Vault token RPC directly; no Smithery quota or broker hop." }));
  if (method === "notifications/initialized") return new Response(null, { status: 204 });
  if (method === "ping") return response(result(id, {}));
  if (method === "tools/list") return response(result(id, { tools: TOOLS.map((tool) => ({ ...tool, annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true } })) }));
  if (method === "tools/call") {
    const name = typeof params.name === "string" ? params.name : "";
    const args = params.arguments && typeof params.arguments === "object" && !Array.isArray(params.arguments) ? params.arguments as Json : {};
    try { const value = await callTool(name, args); return response(result(id, { content: [{ type: "text", text: JSON.stringify(value) }], structuredContent: value, isError: false })); }
    catch (e) { const message = e instanceof Error ? e.message : String(e); return response(result(id, { content: [{ type: "text", text: message }], structuredContent: { ok: false, error: message, tool: name }, isError: true })); }
  }
  return response(error(id, -32601, "Method not found", { method }), 404);
});
