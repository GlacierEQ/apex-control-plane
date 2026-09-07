import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
const FABRIC = SUPABASE_URL ? `${SUPABASE_URL}/functions/v1/apex-direct-mcp-fabric` : "";

if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

type Json = Record<string, unknown>;
type Command = "bootstrap" | "scan" | "execute" | "capabilities" | "plugins" | "sweep" | "resurrect";

interface IgnitionPayload {
  command: Command;
  tool?: string;
  arguments?: Json;
  request_id?: string;
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

async function fabricRpc(method: string, params: Json, requestId: string): Promise<Json> {
  const res = await fetch(FABRIC, {
    method: "POST",
    headers: {
      authorization: `Bearer ${SERVICE_ROLE}`,
      apikey: SERVICE_ROLE!,
      "content-type": "application/json",
      "x-glaciereq-origin": "ignition_command",
      "x-glaciereq-request-id": requestId,
    },
    body: JSON.stringify({ jsonrpc: "2.0", id: requestId, method, params }),
    signal: AbortSignal.timeout(60_000),
  });

  const raw = await res.text();
  let parsed: unknown = raw;
  try { parsed = raw ? JSON.parse(raw) : {}; } catch { /* retain opaque response */ }
  if (!res.ok) throw new Error(`fabric_http_${res.status}`);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("fabric_invalid_response");
  return parsed as Json;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({ ok: false, error: "method_not_allowed" }, 405);
  if (!isServiceRole(req)) return json({ ok: false, error: "service_role_required" }, 403);

  let payload: IgnitionPayload;
  try {
    const candidate = await req.json();
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) throw new Error();
    payload = candidate as IgnitionPayload;
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  const requestId = typeof payload.request_id === "string" && payload.request_id.length > 0
    ? payload.request_id.slice(0, 128)
    : crypto.randomUUID();

  try {
    if (payload.command === "bootstrap" || payload.command === "plugins") {
      const result = await fabricRpc("tools/call", { name: "apex_plugins_list", arguments: {} }, requestId);
      return json({ ok: true, command: payload.command, request_id: requestId, delegated: true, fabric: "apex-direct-mcp-fabric", result });
    }

    if (payload.command === "scan" || payload.command === "capabilities" || payload.command === "sweep") {
      const result = await fabricRpc("tools/list", {}, requestId);
      return json({ ok: true, command: payload.command, request_id: requestId, delegated: true, fabric: "apex-direct-mcp-fabric", result });
    }

    if (payload.command === "execute") {
      if (typeof payload.tool !== "string" || payload.tool.length === 0) {
        return json({ ok: false, error: "tool_required", request_id: requestId }, 400);
      }
      const args = payload.arguments && typeof payload.arguments === "object" && !Array.isArray(payload.arguments)
        ? payload.arguments
        : {};
      const result = await fabricRpc("tools/call", { name: payload.tool, arguments: args }, requestId);
      return json({ ok: true, command: "execute", request_id: requestId, delegated: true, tool: payload.tool, fabric: "apex-direct-mcp-fabric", result });
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
