import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");
const FABRIC = `${SUPABASE_URL}/functions/v1/apex-direct-mcp-fabric`;

const ALLOWED_COMMANDS = new Set(["bootstrap", "scan", "execute", "capabilities", "plugins", "sweep", "resurrect"]);
type Json = Record<string, unknown>;
type Command = "bootstrap" | "scan" | "execute" | "capabilities" | "plugins" | "sweep" | "resurrect";

interface IgnitionPayload {
  command: Command;
  tool?: string;
  arguments?: Json;
  request_id?: string;
}

interface DelegationContext {
  source: string;
  authorityScope: string;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

function isServiceRole(req: Request): boolean {
  return req.headers.get("authorization") === `Bearer ${SERVICE_ROLE}`;
}

function validatedHeader(req: Request, name: string): string | null {
  const value = req.headers.get(name);
  if (!value || value.length > 128 || !/^[A-Za-z0-9._:/-]+$/.test(value)) return null;
  return value;
}

function delegationContext(req: Request): DelegationContext | null {
  const source = validatedHeader(req, "x-glaciereq-source");
  const authorityScope = validatedHeader(req, "x-glaciereq-authority-scope");
  return source && authorityScope ? { source, authorityScope } : null;
}

function validateRpcEnvelope(parsed: unknown, requestId: string): Json {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("fabric_invalid_response");
  const envelope = parsed as Json;
  if (envelope.id !== requestId) throw new Error("fabric_response_id_mismatch");
  if ("error" in envelope) throw new Error("fabric_rpc_error");
  const result = envelope.result;
  if (result && typeof result === "object" && !Array.isArray(result) && (result as Json).isError === true) {
    throw new Error("fabric_tool_error");
  }
  return envelope;
}

async function fabricRpc(method: string, params: Json, requestId: string, ctx: DelegationContext): Promise<Json> {
  const res = await fetch(FABRIC, {
    method: "POST",
    headers: {
      authorization: `Bearer ${SERVICE_ROLE}`,
      apikey: SERVICE_ROLE,
      "content-type": "application/json",
      "x-glaciereq-origin": "ignition_command",
      "x-glaciereq-source": ctx.source,
      "x-glaciereq-authority-scope": ctx.authorityScope,
      "x-glaciereq-request-id": requestId,
    },
    body: JSON.stringify({ jsonrpc: "2.0", id: requestId, method, params }),
    signal: AbortSignal.timeout(60_000),
  });

  const raw = await res.text();
  if (!res.ok) throw new Error(`fabric_http_${res.status}`);
  let parsed: unknown;
  try {
    parsed = raw ? JSON.parse(raw) : {};
  } catch {
    throw new Error("fabric_invalid_json");
  }
  return validateRpcEnvelope(parsed, requestId);
}

async function listAllTools(requestId: string, ctx: DelegationContext): Promise<Json> {
  const tools: unknown[] = [];
  const seen = new Set<string>();
  let cursor: string | undefined;

  for (let page = 0; page < 100; page += 1) {
    const params: Json = cursor ? { cursor } : {};
    const envelope = await fabricRpc("tools/list", params, requestId, ctx);
    const result = envelope.result;
    if (!result || typeof result !== "object" || Array.isArray(result)) throw new Error("fabric_invalid_tools_result");
    const resultObj = result as Json;
    if (!Array.isArray(resultObj.tools)) throw new Error("fabric_invalid_tools_result");
    tools.push(...resultObj.tools);

    const next = resultObj.nextCursor;
    if (next === undefined || next === null || next === "") {
      return { jsonrpc: "2.0", id: requestId, result: { ...resultObj, tools, nextCursor: undefined } };
    }
    if (typeof next !== "string" || seen.has(next)) throw new Error("fabric_invalid_pagination");
    seen.add(next);
    cursor = next;
  }

  throw new Error("fabric_pagination_limit");
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({ ok: false, error: "method_not_allowed" }, 405);
  if (!isServiceRole(req)) return json({ ok: false, error: "service_role_required" }, 403);

  const ctx = delegationContext(req);
  if (!ctx) return json({ ok: false, error: "delegation_context_required" }, 400);

  let payload: IgnitionPayload;
  try {
    const candidate = await req.json();
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) throw new Error();
    const command = (candidate as Json).command;
    if (typeof command !== "string" || !ALLOWED_COMMANDS.has(command)) throw new Error();
    payload = candidate as IgnitionPayload;
  } catch {
    return json({ ok: false, error: "invalid_request" }, 400);
  }

  const suppliedRequestId = payload.request_id;
  if (suppliedRequestId !== undefined &&
      (typeof suppliedRequestId !== "string" || suppliedRequestId.length === 0 || suppliedRequestId.length > 128)) {
    return json({ ok: false, error: "invalid_request_id" }, 400);
  }
  const requestId = suppliedRequestId || crypto.randomUUID();

  try {
    if (payload.command === "bootstrap" || payload.command === "plugins") {
      const result = await fabricRpc("tools/call", { name: "apex_plugins_list", arguments: {} }, requestId, ctx);
      return json({ ok: true, command: payload.command, request_id: requestId, delegated: true, source: ctx.source, authority_scope: ctx.authorityScope, fabric: "apex-direct-mcp-fabric", result });
    }

    if (payload.command === "scan" || payload.command === "capabilities" || payload.command === "sweep") {
      const result = await listAllTools(requestId, ctx);
      return json({ ok: true, command: payload.command, request_id: requestId, delegated: true, source: ctx.source, authority_scope: ctx.authorityScope, fabric: "apex-direct-mcp-fabric", result });
    }

    if (payload.command === "execute") {
      if (typeof payload.tool !== "string" || payload.tool.length === 0 || payload.tool.length > 256) {
        return json({ ok: false, error: "tool_required", request_id: requestId }, 400);
      }
      if (payload.arguments !== undefined &&
          (!payload.arguments || typeof payload.arguments !== "object" || Array.isArray(payload.arguments))) {
        return json({ ok: false, error: "invalid_arguments", request_id: requestId }, 400);
      }
      const args = payload.arguments ?? {};
      const result = await fabricRpc("tools/call", { name: payload.tool, arguments: args }, requestId, ctx);
      return json({ ok: true, command: "execute", request_id: requestId, delegated: true, source: ctx.source, authority_scope: ctx.authorityScope, tool: payload.tool, fabric: "apex-direct-mcp-fabric", result });
    }

    if (payload.command === "resurrect") {
      return json({ ok: false, error: "unsupported_legacy_command", command: "resurrect", reason: "No real resurrection capability is bound. Fake status-only behavior was removed.", request_id: requestId }, 422);
    }

    return json({ ok: false, error: "unknown_command", request_id: requestId }, 400);
  } catch (error) {
    const message = error instanceof Error ? error.message : "delegation_failed";
    return json({ ok: false, error: "delegation_failed", detail: message, request_id: requestId }, 502);
  }
});
