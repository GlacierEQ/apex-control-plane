import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const JSON_HEADERS = {
  "content-type": "application/json",
  "cache-control": "no-store, max-age=0",
  "x-content-type-options": "nosniff",
};
const PKCS8_BEGIN = "-----BEGIN " + "PRIVATE KEY-----";
const PKCS8_END = "-----END " + "PRIVATE KEY-----";

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

function b64ToBytes(value: string): Uint8Array {
  const bin = atob(value);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

function bytesToB64(value: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < value.length; i += 0x8000) {
    bin += String.fromCharCode(...value.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

function bytesToHex(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function pemToPkcs8(pem: string): ArrayBuffer {
  const normalized = pem.trim();
  if (!normalized.includes(PKCS8_BEGIN)) throw new Error("oci_private_key_not_pkcs8");
  const b64 = normalized
    .replace(PKCS8_BEGIN, "")
    .replace(PKCS8_END, "")
    .replace(/\s+/g, "");
  const bytes = b64ToBytes(b64);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

async function sha256(data: Uint8Array): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", data));
}

async function deriveAesKey(wrapSecret: string, context: string): Promise<CryptoKey> {
  const raw = new TextEncoder().encode(`${wrapSecret}|${context}`);
  const keyBytes = await sha256(raw);
  return await crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["decrypt"]);
}

async function ociGet(
  region: string,
  tenancy: string,
  user: string,
  fingerprint: string,
  privateKeyPem: string,
  pathAndQuery: string,
): Promise<{ status: number; ok: boolean; payload: unknown }> {
  const host = `identity.${region}.oci.oraclecloud.com`;
  const date = new Date().toUTCString();
  const signingString = `(request-target): get ${pathAndQuery}\nhost: ${host}\ndate: ${date}`;
  const key = await crypto.subtle.importKey(
    "pkcs8",
    pemToPkcs8(privateKeyPem),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = new Uint8Array(await crypto.subtle.sign(
    { name: "RSASSA-PKCS1-v1_5" },
    key,
    new TextEncoder().encode(signingString),
  ));
  const authorization = `Signature version="1",keyId="${tenancy}/${user}/${fingerprint}",algorithm="rsa-sha256",headers="(request-target) host date",signature="${bytesToB64(signature)}"`;
  const response = await fetch(`https://${host}${pathAndQuery}`, {
    method: "GET",
    headers: { date, authorization, accept: "application/json" },
    signal: AbortSignal.timeout(15_000),
  });
  const text = await response.text();
  let payload: unknown = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = { body_length: text.length }; }
  return { status: response.status, ok: response.ok, payload };
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json(405, { error: "method_not_allowed" });

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceRole) return json(500, { error: "service_configuration_missing" });

  let envelopeRef = "";
  try {
    const body = await req.json();
    envelopeRef = typeof body?.envelope_ref === "string" ? body.envelope_ref.trim() : "";
    if (!envelopeRef || envelopeRef.length > 256) throw new Error("invalid_envelope_ref");
  } catch {
    return json(400, { error: "invalid_request" });
  }

  const admin = createClient(supabaseUrl, serviceRole, { auth: { persistSession: false, autoRefreshToken: false } });
  let oracleSecretRef = "";

  try {
    const token = req.headers.get("x-apex-bootstrap-token")?.trim() || "";
    const claimed = token
      ? await admin.rpc("claim_apex_oci_bootstrap_envelope", { p_envelope_ref: envelopeRef, p_token: token })
      : await admin.rpc("claim_apex_oci_bootstrap_capability", { p_envelope_ref: envelopeRef });
    if (claimed.error || claimed.data?.ok !== true) {
      return json(401, { error: claimed.error?.message || claimed.data?.error || "bootstrap_claim_failed" });
    }

    const envelope = claimed.data as Record<string, unknown>;
    const context = String(envelope.context || "");
    const ivB64 = String(envelope.iv_b64 || "");
    const ciphertextB64 = String(envelope.ciphertext_b64 || "");
    const expectedHash = String(envelope.ciphertext_sha256 || "");
    const wrapSecretRef = String(envelope.wrap_secret_ref || "");
    if (context !== "apex-oci-bootstrap-v1" || !ivB64 || !ciphertextB64 || !wrapSecretRef) throw new Error("bootstrap_envelope_invalid");

    const ciphertext = b64ToBytes(ciphertextB64);
    const observedHash = bytesToHex(await crypto.subtle.digest("SHA-256", ciphertext));
    if (observedHash !== expectedHash) throw new Error("bootstrap_ciphertext_hash_mismatch");

    const resolved = await admin.rpc("resolve_apex_keymaster_secret_for_broker", {
      p_secret_ref: wrapSecretRef,
      p_provider: "github",
      p_request_id: `${envelopeRef}-wrap-resolve`.slice(0, 256),
      p_actor: "apex-oci-bootstrap-activate",
      p_operation: "derive_ephemeral_oci_bootstrap_encryption_key",
    });
    if (resolved.error || typeof resolved.data?.secret !== "string" || !resolved.data.secret) throw new Error(resolved.error?.message || "wrap_secret_resolution_failed");

    let wrapSecret = resolved.data.secret as string;
    const aesKey = await deriveAesKey(wrapSecret, context);
    wrapSecret = "";
    const plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: b64ToBytes(ivB64), additionalData: new TextEncoder().encode(context) },
      aesKey,
      ciphertext,
    );
    const config = JSON.parse(new TextDecoder().decode(plaintext));

    const tenancy = String(config.tenancy_ocid || "");
    const user = String(config.user_ocid || "");
    const region = String(config.region || "");
    const fingerprint = String(config.fingerprint || "");
    let privateKeyPem = String(config.private_key_pem || "");
    if (!tenancy.startsWith("ocid1.tenancy.") || !user.startsWith("ocid1.user.") || !region || !fingerprint || !privateKeyPem.includes("PRIVATE KEY")) throw new Error("oci_config_validation_failed");

    const stored = await admin.rpc("store_apex_keymaster_secret", {
      p_provider: "oracle",
      p_account_label: "glaciereq-primary",
      p_purpose: "oci_api_signing_bundle",
      p_scope: ["identity", "compute", "network", "container_instances", "instance_pools", "buildkite_agents"],
      p_secret: JSON.stringify({ tenancy_ocid: tenancy, user_ocid: user, region, fingerprint, private_key_pem: privateKeyPem }),
      p_rotation_due_at: null,
      p_request_id: `${envelopeRef}-store`.slice(0, 256),
      p_actor: "apex-oci-bootstrap-activate",
      p_verification_status: "unverified",
      p_verification_detail: { source: "ciphertext_bootstrap_v1", region },
    });
    if (stored.error || typeof stored.data?.secret_ref !== "string") throw new Error(stored.error?.message || "oci_keymaster_store_failed");
    oracleSecretRef = stored.data.secret_ref;

    const regionsProbe = await ociGet(region, tenancy, user, fingerprint, privateKeyPem, "/20160918/regions");
    const adsPath = `/20160918/availabilityDomains?compartmentId=${encodeURIComponent(tenancy)}`;
    const adProbe = regionsProbe.ok
      ? await ociGet(region, tenancy, user, fingerprint, privateKeyPem, adsPath)
      : { status: 0, ok: false, payload: null };
    privateKeyPem = "";

    const probe = {
      provider: "oracle_cloud",
      region,
      regions_http_status: regionsProbe.status,
      regions_ok: regionsProbe.ok,
      region_count: Array.isArray(regionsProbe.payload) ? regionsProbe.payload.length : null,
      availability_domains_http_status: adProbe.status,
      availability_domains_ok: adProbe.ok,
      availability_domain_count: Array.isArray(adProbe.payload) ? adProbe.payload.length : null,
      verified_at: new Date().toISOString(),
    };

    await admin.rpc("verify_apex_keymaster_secret", {
      p_secret_ref: oracleSecretRef,
      p_verification_status: regionsProbe.ok ? "verified" : "failed",
      p_verification_detail: probe,
      p_request_id: `${envelopeRef}-verify`.slice(0, 256),
      p_actor: "apex-oci-bootstrap-activate",
    });

    if (!regionsProbe.ok) {
      await admin.rpc("fail_apex_oci_bootstrap_envelope", {
        p_envelope_ref: envelopeRef,
        p_error_code: `oci_identity_http_${regionsProbe.status}`,
        p_provider_probe: probe,
      });
      return json(502, { ok: false, status: "credential_stored_probe_failed", probe, plaintext_returned: false });
    }

    const completed = await admin.rpc("complete_apex_oci_bootstrap_envelope", {
      p_envelope_ref: envelopeRef,
      p_oracle_secret_ref: oracleSecretRef,
      p_provider_probe: probe,
    });
    if (completed.error || completed.data?.ok !== true) throw new Error(completed.error?.message || "bootstrap_completion_failed");

    return json(200, {
      ok: true,
      status: "OCI_IDENTITY_VERIFIED",
      probe,
      ciphertext_retained: false,
      plaintext_returned: false,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "oci_bootstrap_failed";
    await admin.rpc("fail_apex_oci_bootstrap_envelope", {
      p_envelope_ref: envelopeRef,
      p_error_code: message.slice(0, 256),
      p_provider_probe: { failed_at: new Date().toISOString() },
    }).catch(() => {});
    return json(400, { ok: false, error: message.slice(0, 256), plaintext_returned: false });
  }
});