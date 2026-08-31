
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const CONNECTOR_KEY = "github.backend_ops";
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store, max-age=0",
  "x-content-type-options": "nosniff",
};

function reply(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: HEADERS });
}

function obj(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

async function sha256Hex(raw: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", raw);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(value: string): Uint8Array {
  if (!/^[0-9a-f]{64}$/i.test(value)) return new Uint8Array();
  const out = new Uint8Array(32);
  for (let i = 0; i < 32; i++) out[i] = parseInt(value.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function timingSafeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length || a.length === 0) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

async function hmacSha256(secret: string, raw: Uint8Array): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, raw));
}

async function webhookSecret(deliveryId: string): Promise<{secret: string; owner: string}> {
  const { data: config, error: configError } = await admin
    .from("github_connector_config_v1")
    .select("owner_login,webhook_secret_ref")
    .eq("connector_key", CONNECTOR_KEY)
    .maybeSingle();

  if (configError || !config) throw new Error("connector_config_unavailable");
  if (typeof config.webhook_secret_ref !== "string" || !config.webhook_secret_ref) {
    throw new Error("webhook_secret_not_bound");
  }

  const { data, error } = await admin.rpc("resolve_apex_keymaster_secret_for_broker", {
    p_secret_ref: config.webhook_secret_ref,
    p_provider: "github",
    p_request_id: ("webhook-" + deliveryId).slice(0, 256),
    p_actor: "github-webhook",
    p_operation: "verify_webhook_hmac",
  });

  if (error || typeof data?.secret !== "string" || !data.secret) {
    throw new Error("webhook_secret_resolution_failed");
  }
  return { secret: data.secret, owner: String(config.owner_login || "GlacierEQ") };
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return reply(405, { ok: false, error: "method_not_allowed" });

  const deliveryId = (req.headers.get("x-github-delivery") || "").trim();
  const eventType = (req.headers.get("x-github-event") || "").trim();
  const signature = (req.headers.get("x-hub-signature-256") || "").trim();

  if (!/^[0-9a-f-]{16,128}$/i.test(deliveryId)) {
    return reply(400, { ok: false, error: "invalid_delivery_id" });
  }
  if (!eventType || eventType.length > 128) {
    return reply(400, { ok: false, error: "invalid_event_type" });
  }
  if (!signature.startsWith("sha256=")) {
    return reply(401, { ok: false, error: "signature_missing" });
  }

  const declared = Number(req.headers.get("content-length") || 0);
  if (declared > MAX_BODY_BYTES) return reply(413, { ok: false, error: "payload_too_large" });

  const rawBuffer = new Uint8Array(await req.arrayBuffer());
  if (rawBuffer.byteLength > MAX_BODY_BYTES) {
    return reply(413, { ok: false, error: "payload_too_large" });
  }

  const payloadHash = await sha256Hex(rawBuffer);

  const { data: existing } = await admin
    .from("github_webhook_deliveries_v1")
    .select("delivery_id,processing_status,received_at")
    .eq("delivery_id", deliveryId)
    .maybeSingle();

  if (existing) {
    return reply(202, {
      ok: true,
      duplicate: true,
      delivery_id: existing.delivery_id,
      processing_status: existing.processing_status,
      received_at: existing.received_at,
    });
  }

  let secret = "";
  let owner = "";
  try {
    const resolved = await webhookSecret(deliveryId);
    secret = resolved.secret;
    owner = resolved.owner;

    const expected = await hmacSha256(secret, rawBuffer);
    secret = "";
    const supplied = hexToBytes(signature.slice(7));
    if (!timingSafeEqual(expected, supplied)) {
      return reply(401, { ok: false, error: "signature_invalid" });
    }
  } catch (error) {
    secret = "";
    const code = error instanceof Error ? error.message : "webhook_verification_unavailable";
    const status = code === "webhook_secret_not_bound" ? 503 : 500;
    return reply(status, { ok: false, error: code });
  } finally {
    secret = "";
  }

  let payload: unknown;
  try {
    payload = JSON.parse(new TextDecoder().decode(rawBuffer));
  } catch {
    return reply(400, { ok: false, error: "invalid_json" });
  }

  const body = obj(payload);
  const repository = obj(body.repository);
  const sender = obj(body.sender);
  const fullName = typeof repository.full_name === "string" ? repository.full_name : "";
  const action = typeof body.action === "string" ? body.action.slice(0, 128) : null;
  const senderLogin = typeof sender.login === "string" ? sender.login.slice(0, 256) : null;

  if (fullName && !fullName.startsWith(owner + "/")) {
    return reply(403, { ok: false, error: "repository_owner_rejected" });
  }

  const safeMetadata: Record<string, unknown> = {
    hook_id: body.hook_id || null,
    installation_id: obj(body.installation).id || null,
    repository_id: repository.id || null,
    repository_private: repository.private ?? null,
    ref: typeof body.ref === "string" ? body.ref.slice(0, 512) : null,
    before: typeof body.before === "string" ? body.before.slice(0, 128) : null,
    after: typeof body.after === "string" ? body.after.slice(0, 128) : null,
    pull_request_number: obj(body.pull_request).number || null,
    issue_number: obj(body.issue).number || null,
    workflow_run_id: obj(body.workflow_run).id || null,
    raw_payload_persisted: false,
  };

  const { error: insertError } = await admin.from("github_webhook_deliveries_v1").insert({
    delivery_id: deliveryId,
    event_type: eventType,
    action,
    repository: fullName || null,
    sender_login: senderLogin,
    payload_sha256: payloadHash,
    signature_verified: true,
    processing_status: "accepted",
    metadata: safeMetadata,
  });

  if (insertError) {
    return reply(500, { ok: false, error: "delivery_receipt_persistence_failed" });
  }

  await admin
    .from("connector_registry_v2")
    .update({ last_checked_at: new Date().toISOString(), updated_at: new Date().toISOString() })
    .eq("connector_key", CONNECTOR_KEY);

  return reply(202, {
    ok: true,
    delivery_id: deliveryId,
    event_type: eventType,
    action,
    repository: fullName || null,
    payload_sha256: payloadHash,
    signature_verified: true,
    raw_payload_persisted: false,
  });
});
