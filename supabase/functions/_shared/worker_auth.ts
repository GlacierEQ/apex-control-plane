export type EnvReader = (name: string) => string | undefined;

export type WorkerAuthOptions = {
  allowedOrigins?: Iterable<string>;
  env?: EnvReader;
};

export type WorkerAuthDecision =
  | {
      ok: true;
      status: 200;
      origin: string;
      credentialMode: "worker_secret" | "service_role";
    }
  | {
      ok: false;
      status: 401 | 403;
      error:
        | "worker_auth_required"
        | "worker_auth_forbidden_role"
        | "worker_auth_forbidden";
      reason: string;
    };

export const DEFAULT_ALLOWED_WORKER_ORIGINS: ReadonlySet<string> = new Set([
  "apex-scheduler",
  "apex-github-batch-worker",
  "apex-github-webhook-wake",
  "apex-github-webhook-worker",
  "apex-github-router",
  "apex-direct-github-mcp",
  "apex-control-plane",
  "apex-direct-mcp-fabric",
  "ignition_command",
]);

const DEFAULT_AUTH_HEADERS: Record<string, string> = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store, max-age=0",
  "x-content-type-options": "nosniff",
};

const SHA256_K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function rotr(value: number, bits: number): number {
  return (value >>> bits) | (value << (32 - bits));
}

function sha256Bytes(input: Uint8Array): Uint8Array {
  let h0 = 0x6a09e667;
  let h1 = 0xbb67ae85;
  let h2 = 0x3c6ef372;
  let h3 = 0xa54ff53a;
  let h4 = 0x510e527f;
  let h5 = 0x9b05688c;
  let h6 = 0x1f83d9ab;
  let h7 = 0x5be0cd19;

  const bitLenHi = Math.floor((input.length * 8) / 0x100000000);
  const bitLenLo = (input.length * 8) >>> 0;
  const paddedLength = Math.ceil((input.length + 9) / 64) * 64;
  const padded = new Uint8Array(paddedLength);
  padded.set(input);
  padded[input.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(paddedLength - 8, bitLenHi, false);
  view.setUint32(paddedLength - 4, bitLenLo, false);

  const w = new Uint32Array(64);
  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let i = 0; i < 16; i += 1) {
      w[i] = view.getUint32(offset + i * 4, false);
    }
    for (let i = 16; i < 64; i += 1) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }

    let a = h0;
    let b = h1;
    let c = h2;
    let d = h3;
    let e = h4;
    let f = h5;
    let g = h6;
    let h = h7;

    for (let i = 0; i < 64; i += 1) {
      const s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + ch + SHA256_K[i] + w[i]) >>> 0;
      const s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) >>> 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
    h5 = (h5 + f) >>> 0;
    h6 = (h6 + g) >>> 0;
    h7 = (h7 + h) >>> 0;
  }

  const out = new Uint8Array(32);
  const outView = new DataView(out.buffer);
  outView.setUint32(0, h0, false);
  outView.setUint32(4, h1, false);
  outView.setUint32(8, h2, false);
  outView.setUint32(12, h3, false);
  outView.setUint32(16, h4, false);
  outView.setUint32(20, h5, false);
  outView.setUint32(24, h6, false);
  outView.setUint32(28, h7, false);
  return out;
}

export function defaultEnvReader(name: string): string | undefined {
  const g = globalThis as {
    Deno?: { env?: { get?: (key: string) => string | undefined } };
    process?: { env?: Record<string, string | undefined> };
  };
  if (typeof g.Deno?.env?.get === "function") {
    return g.Deno.env.get(name);
  }
  return g.process?.env?.[name];
}

export function constantTimeEqual(left: string, right: string): boolean {
  const encoder = new TextEncoder();
  const leftBytes = encoder.encode(left);
  const rightBytes = encoder.encode(right);
  const leftDigest = sha256Bytes(leftBytes);
  const rightDigest = sha256Bytes(rightBytes);
  let diff = leftBytes.length ^ rightBytes.length;
  for (let i = 0; i < 32; i += 1) {
    diff |= leftDigest[i] ^ rightDigest[i];
  }
  return diff === 0;
}

function constantTimeMatchesAny(candidate: string, secrets: readonly string[]): boolean {
  if (!candidate || secrets.length === 0) return false;
  let matched = 0;
  for (const secret of secrets) {
    if (constantTimeEqual(candidate, secret)) {
      matched |= 1;
    }
  }
  return matched === 1;
}

export function runtimeServiceKeys(env: EnvReader = defaultEnvReader): string[] {
  const keys: string[] = [];
  const modern = env("SUPABASE_SECRET_KEYS");
  if (modern) {
    try {
      const parsed = JSON.parse(modern);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        for (const value of Object.values(parsed as Record<string, unknown>)) {
          if (typeof value === "string" && value.trim()) {
            keys.push(value.trim());
          }
        }
      }
    } catch {
      // Ignore malformed secret dictionary and fall back to SUPABASE_SERVICE_ROLE_KEY.
    }
  }
  const legacy = env("SUPABASE_SERVICE_ROLE_KEY")?.trim();
  if (legacy) keys.push(legacy);
  return [...new Set(keys)];
}

function decodeJwtRole(token: string): string | null {
  const parts = token.split(".");
  if (parts.length !== 3 || !parts[1]) return null;
  try {
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padLen = (4 - (normalized.length % 4)) % 4;
    const binary = atob(normalized + "=".repeat(padLen));
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    const decoded = JSON.parse(new TextDecoder().decode(bytes));
    if (decoded && typeof decoded === "object" && !Array.isArray(decoded)) {
      const role = (decoded as Record<string, unknown>).role;
      return typeof role === "string" ? role : null;
    }
  } catch {
    return null;
  }
  return null;
}

function isAnonymousCredential(token: string, anonKey: string): boolean {
  if (!token) return false;
  if (anonKey && constantTimeEqual(token, anonKey)) return true;
  if (token.startsWith("sb_publishable_")) return true;
  const role = decodeJwtRole(token);
  return role === "anon" || role === "anon_key";
}

export function authorizePrivilegedWorkerRequest(
  req: Request,
  options: WorkerAuthOptions = {},
): WorkerAuthDecision {
  const env = options.env ?? defaultEnvReader;
  const allowedOrigins = options.allowedOrigins
    ? new Set(options.allowedOrigins)
    : DEFAULT_ALLOWED_WORKER_ORIGINS;

  const workerAuth = req.headers.get("x-apex-worker-auth")?.trim() || "";
  const rawAuthorization = req.headers.get("authorization")?.trim() || "";
  const bearer = /^Bearer\s+/i.test(rawAuthorization)
    ? rawAuthorization.replace(/^Bearer\s+/i, "").trim()
    : "";
  const apiKey = req.headers.get("apikey")?.trim() || "";
  const origin =
    req.headers.get("x-glaciereq-worker-origin")?.trim() ||
    req.headers.get("x-glaciereq-origin")?.trim() ||
    "";

  if (!workerAuth && !bearer && !apiKey) {
    return {
      ok: false,
      status: 401,
      error: "worker_auth_required",
      reason: "missing_worker_credentials",
    };
  }

  const anonKey = env("SUPABASE_ANON_KEY")?.trim() || "";
  for (const candidate of [apiKey, bearer, workerAuth]) {
    if (candidate && isAnonymousCredential(candidate, anonKey)) {
      return {
        ok: false,
        status: 403,
        error: "worker_auth_forbidden_role",
        reason: "anonymous_or_publishable_credential_rejected",
      };
    }
  }

  for (const candidate of [bearer, apiKey]) {
    if (candidate && decodeJwtRole(candidate) === "authenticated") {
      return {
        ok: false,
        status: 403,
        error: "worker_auth_forbidden",
        reason: "authenticated_user_jwt_rejected",
      };
    }
  }

  const configuredWorkerSecret = env("APEX_INTERNAL_WORKER_SECRET")?.trim() || "";
  const serviceKeys = runtimeServiceKeys(env);

  let credentialMode: "worker_secret" | "service_role" | null = null;
  if (workerAuth) {
    if (configuredWorkerSecret && constantTimeEqual(workerAuth, configuredWorkerSecret)) {
      credentialMode = "worker_secret";
    }
  } else if (
    bearer &&
    apiKey &&
    constantTimeMatchesAny(apiKey, serviceKeys) &&
    constantTimeMatchesAny(bearer, serviceKeys)
  ) {
    credentialMode = "service_role";
  }

  if (!credentialMode) {
    return {
      ok: false,
      status: 403,
      error: "worker_auth_forbidden",
      reason: "invalid_worker_credentials",
    };
  }

  if (!origin || !allowedOrigins.has(origin)) {
    return {
      ok: false,
      status: 403,
      error: "worker_auth_forbidden",
      reason: origin ? "worker_origin_not_allowed" : "worker_origin_required",
    };
  }

  return {
    ok: true,
    status: 200,
    origin,
    credentialMode,
  };
}

export function requirePrivilegedWorkerAuth(
  req: Request,
  options: WorkerAuthOptions & { headers?: Record<string, string> } = {},
): Response | null {
  const decision = authorizePrivilegedWorkerRequest(req, options);
  if (decision.ok) return null;
  return new Response(
    JSON.stringify({
      ok: false,
      error: decision.error,
      reason: decision.reason,
    }),
    {
      status: decision.status,
      headers: {
        ...DEFAULT_AUTH_HEADERS,
        ...(options.headers || {}),
      },
    },
  );
}

export function buildInternalWorkerHeaders(
  origin: string,
  extraHeaders: Record<string, string> = {},
  env: EnvReader = defaultEnvReader,
): Record<string, string> {
  const headers: Record<string, string> = {
    "x-glaciereq-worker-origin": origin,
    "x-glaciereq-origin": origin,
  };
  const serviceKeys = runtimeServiceKeys(env);
  if (serviceKeys.length > 0) {
    headers.authorization = `Bearer ${serviceKeys[0]}`;
    headers.apikey = serviceKeys[0];
  }
  const workerSecret = env("APEX_INTERNAL_WORKER_SECRET")?.trim() || "";
  if (workerSecret) {
    headers["x-apex-worker-auth"] = workerSecret;
  }
  return {
    ...headers,
    ...extraHeaders,
  };
}
