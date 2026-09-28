import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
const PROTOCOL_VERSION = "2025-06-18";
const SERVER_NAME = "glaciereq-direct-github";
const SERVER_VERSION = "1.1.0";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");
const CONNECTOR_URL = `${SUPABASE_URL}/functions/v1/apex-github-connector`;

type Json = Record<string, unknown>;
type RpcId = string | number | null;
type ToolDef = { name: string; description: string; inputSchema: Json; operation: string; write?: boolean };

const TOOLS: ToolDef[] = [
  { name: "github_repo_get", description: "Read repository metadata from the GlacierEQ-owned direct GitHub connector.", operation: "repo.get", inputSchema: { type: "object", properties: { repository: { type: "string", description: "owner/repo" } }, required: ["repository"], additionalProperties: false } },
  { name: "github_contents_get", description: "Read one file or directory from a repository ref.", operation: "contents.get", inputSchema: { type: "object", properties: { repository: { type: "string" }, path: { type: "string" }, ref: { type: "string" } }, required: ["repository","path"], additionalProperties: false } },
  { name: "github_tree_list", description: "List a repository tree recursively from a ref.", operation: "tree.list", inputSchema: { type: "object", properties: { repository: { type: "string" }, ref: { type: "string" } }, required: ["repository"], additionalProperties: false } },
  { name: "github_branches_list", description: "List repository branches.", operation: "branches.list", inputSchema: { type: "object", properties: { repository: { type: "string" }, per_page: { type: "integer", minimum: 1, maximum: 100 } }, required: ["repository"], additionalProperties: false } },
  { name: "github_commits_list", description: "List commits, optionally filtered by ref or path.", operation: "commits.list", inputSchema: { type: "object", properties: { repository: { type: "string" }, ref: { type: "string" }, path: { type: "string" }, per_page: { type: "integer", minimum: 1, maximum: 100 } }, required: ["repository"], additionalProperties: false } },
  { name: "github_code_search", description: "Search code inside one repository.", operation: "code.search", inputSchema: { type: "object", properties: { repository: { type: "string" }, query: { type: "string" }, per_page: { type: "integer", minimum: 1, maximum: 100 } }, required: ["repository","query"], additionalProperties: false } },
  { name: "github_issues_list", description: "List repository issues.", operation: "issues.list", inputSchema: { type: "object", properties: { repository: { type: "string" }, state: { type: "string", enum: ["open","closed","all"] }, per_page: { type: "integer", minimum: 1, maximum: 100 } }, required: ["repository"], additionalProperties: false } },
  { name: "github_issue_get", description: "Read one repository issue or pull-request issue record by number.", operation: "issue.get", inputSchema: { type: "object", properties: { repository: { type: "string" }, number: { type: "integer", minimum: 1 } }, required: ["repository","number"], additionalProperties: false } },
  { name: "github_pulls_list", description: "List repository pull requests through the direct GitHub connector.", operation: "pulls.list", inputSchema: { type: "object", properties: { repository: { type: "string" }, state: { type: "string", enum: ["open","closed","all"] }, per_page: { type: "integer", minimum: 1, maximum: 100 } }, required: ["repository"], additionalProperties: false } },
  { name: "github_pull_get", description: "Read one pull request.", operation: "pull.get", inputSchema: { type: "object", properties: { repository: { type: "string" }, number: { type: "integer", minimum: 1 } }, required: ["repository","number"], additionalProperties: false } },
  { name: "github_actions_runs", description: "List GitHub Actions workflow runs for a repository.", operation: "actions.runs", inputSchema: { type: "object", properties: { repository: { type: "string" }, branch: { type: "string" }, status: { type: "string" }, per_page: { type: "integer", minimum: 1, maximum: 100 } }, required: ["repository"], additionalProperties: false } },
  { name: "github_branch_create", description: "Create a non-default branch through the governed direct GitHub connector.", operation: "branch.create", write: true, inputSchema: { type: "object", properties: { repository: { type: "string" }, branch: { type: "string" }, base_branch: { type: "string" }, request_id: { type: "string", minLength: 8 } }, required: ["repository","branch","request_id"], additionalProperties: false } },
  { name: "github_contents_put", description: "Create or update UTF-8 repository content on a non-default branch with readback verification.", operation: "contents.put", write: true, inputSchema: { type: "object", properties: { repository: { type: "string" }, path: { type: "string" }, branch: { type: "string" }, message: { type: "string" }, content: { type: "string" }, sha: { type: "string" }, request_id: { type: "string", minLength: 8 } }, required: ["repository","path","branch","message","content","request_id"], additionalProperties: false } },
  { name: "github_issue_create", description: "Create a GitHub issue through the direct connector with durable receipt.", operation: "issue.create", write: true, inputSchema: { type: "object", properties: { repository: { type: "string" }, title: { type: "string" }, body: { type: "string" }, labels: { type: "array", items: { type: "string" } }, assignees: { type: "array", items: { type: "string" } }, request_id: { type: "string", minLength: 8 } }, required: ["repository","title","request_id"], additionalProperties: false } },
  { name: "github_issue_comment", description: "Comment on an issue through the direct connector.", operation: "issue.comment", write: true, inputSchema: { type: "object", properties: { repository: { type: "string" }, number: { type: "integer", minimum: 1 }, body: { type: "string" }, request_id: { type: "string", minLength: 8 } }, required: ["repository","number","body","request_id"], additionalProperties: false } },
  { name: "github_pull_create", description: "Open a pull request through the direct connector.", operation: "pull.create", write: true, inputSchema: { type: "object", properties: { repository: { type: "string" }, title: { type: "string" }, body: { type: "string" }, head: { type: "string" }, base: { type: "string" }, draft: { type: "boolean" }, request_id: { type: "string", minLength: 8 } }, required: ["repository","title","head","base","request_id"], additionalProperties: false } },
  { name: "github_pull_comment", description: "Comment on a pull request through the direct connector.", operation: "pull.comment", write: true, inputSchema: { type: "object", properties: { repository: { type: "string" }, number: { type: "integer", minimum: 1 }, body: { type: "string" }, request_id: { type: "string", minLength: 8 } }, required: ["repository","number","body","request_id"], additionalProperties: false } },
  { name: "github_workflow_dispatch", description: "Dispatch an existing GitHub Actions workflow through the direct connector.", operation: "workflow.dispatch", write: true, inputSchema: { type: "object", properties: { repository: { type: "string" }, workflow_id: { oneOf: [{ type: "string" }, { type: "integer" }] }, ref: { type: "string" }, inputs: { type: "object" }, request_id: { type: "string", minLength: 8 } }, required: ["repository","workflow_id","ref","request_id"], additionalProperties: false } }
];
const TOOL_BY_NAME = new Map(TOOLS.map((tool) => [tool.name, tool]));

function isServiceRoleRequest(req: Request): boolean {
  return req.headers.get("authorization") === `Bearer ${SERVICE_ROLE}`;
}
function response(body: unknown, status = 200): Response {
  return new Response(body === null ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "x-content-type-options": "nosniff", "mcp-protocol-version": PROTOCOL_VERSION } });
}
function rpcResult(id: RpcId, result: unknown) { return { jsonrpc: "2.0", id, result }; }
function rpcError(id: RpcId, code: number, message: string, data?: unknown) { return { jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) } }; }
async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function callDirectConnector(tool: ToolDef, args: Json): Promise<Json> {
  const repository = typeof args.repository === "string" ? args.repository : "";
  const suppliedRequestId = typeof args.request_id === "string" ? args.request_id : "";
  if (tool.write && suppliedRequestId.length < 8) throw new Error("valid_request_id_required_for_write");
  const requestId = suppliedRequestId.length >= 8 ? suppliedRequestId : `mcp-read-${crypto.randomUUID()}`;
  const providerArgs: Json = { ...args };
  delete providerArgs.repository;
  delete providerArgs.request_id;

  const res = await fetch(CONNECTOR_URL, {
    method: "POST",
    headers: { authorization: `Bearer ${SERVICE_ROLE}`, apikey: SERVICE_ROLE, "content-type": "application/json", "x-glaciereq-origin": "apex-direct-github-mcp" },
    body: JSON.stringify({ operation: tool.operation, repository, args: providerArgs, request_id: requestId, actor: "apex-direct-github-mcp" }),
    signal: AbortSignal.timeout(45_000)
  });
  const raw = await res.text();
  let data: unknown = raw;
  try { data = raw ? JSON.parse(raw) : null; } catch { data = raw; }
  if (!res.ok) {
    const bodyHash = await sha256Hex(raw);
    const providerRequestId = res.headers.get("x-github-request-id") || res.headers.get("x-request-id") || undefined;
    throw new Error(`direct_connector_http_${res.status}:body_sha256=${bodyHash}${providerRequestId ? `:request_id=${providerRequestId}` : ""}`);
  }
  return (data && typeof data === "object" && !Array.isArray(data) ? data : { data }) as Json;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return response({ ok: true }, 200);
  if (req.method !== "POST") return response({ ok: false, error: "method_not_allowed" }, 405);
  if (!isServiceRoleRequest(req)) return response(rpcError(null, -32001, "service_role_required"), 403);

  let payload: Json;
  try { const value = await req.json(); if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(); payload = value as Json; }
  catch { return response(rpcError(null, -32700, "Parse error"), 400); }
  const id = (payload.id ?? null) as RpcId;
  const method = typeof payload.method === "string" ? payload.method : "";
  const params = payload.params && typeof payload.params === "object" && !Array.isArray(payload.params) ? payload.params as Json : {};
  if (payload.jsonrpc !== "2.0") return response(rpcError(id, -32600, "Invalid Request"), 400);
  if (method === "initialize") return response(rpcResult(id, { protocolVersion: PROTOCOL_VERSION, capabilities: { tools: { listChanged: false } }, serverInfo: { name: SERVER_NAME, version: SERVER_VERSION }, instructions: "GlacierEQ-owned direct GitHub MCP. No Smithery hop. Provider execution, policy, receipts, idempotency, and readback are delegated to apex-github-connector." }));
  if (method === "notifications/initialized") return new Response(null, { status: 204 });
  if (method === "ping") return response(rpcResult(id, {}));
  if (method === "tools/list") return response(rpcResult(id, { tools: TOOLS.map(({ operation, write, ...tool }) => ({ ...tool, annotations: { readOnlyHint: !write, destructiveHint: false, idempotentHint: !write } })) }));
  if (method === "tools/call") {
    const name = typeof params.name === "string" ? params.name : "";
    const tool = TOOL_BY_NAME.get(name);
    if (!tool) return response(rpcError(id, -32602, "Unknown tool", { name }), 400);
    const args = params.arguments && typeof params.arguments === "object" && !Array.isArray(params.arguments) ? params.arguments as Json : {};
    try {
      const value = await callDirectConnector(tool, args);
      return response(rpcResult(id, { content: [{ type: "text", text: JSON.stringify(value) }], structuredContent: value, isError: false }));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      return response(rpcResult(id, { content: [{ type: "text", text: message }], structuredContent: { ok: false, error: message, tool: name }, isError: true }));
    }
  }
  return response(rpcError(id, -32601, "Method not found", { method }), 404);
});
