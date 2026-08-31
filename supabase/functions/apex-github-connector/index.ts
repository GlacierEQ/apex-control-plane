
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";
import { importPKCS8, SignJWT } from "npm:jose@6";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const CONNECTOR_KEY = "github.backend_ops";
const GITHUB_API = "https://api.github.com";
const GITHUB_API_VERSION = "2022-11-28";
const MAX_BODY_BYTES = 3 * 1024 * 1024;
const MAX_CONTENT_BYTES = 2 * 1024 * 1024;
const MAX_TREE_ENTRIES = 5000;
const DEFAULT_TIMEOUT_MS = 20000;

type Json = Record<string, unknown>;
type Permission = "read" | "write";

class ConnectorError extends Error {
  status: number;
  code: string;
  details: Json;
  constructor(status: number, code: string, message?: string, details: Json = {}) {
    super(message || code);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const RESPONSE_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store, max-age=0",
  "pragma": "no-cache",
  "x-content-type-options": "nosniff",
  "referrer-policy": "no-referrer",
};

function respond(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: RESPONSE_HEADERS });
}

function obj(value: unknown): Json {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
}

function text(value: unknown, field: string, max = 512, required = true): string {
  if ((value === null || value === undefined || value === "") && !required) return "";
  if (typeof value !== "string") throw new ConnectorError(400, "invalid_" + field);
  const out = value.trim();
  if ((required && !out) || out.length > max) throw new ConnectorError(400, "invalid_" + field);
  return out;
}

function integer(value: unknown, field: string, min = 1, max = Number.MAX_SAFE_INTEGER): number {
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n < min || n > max) throw new ConnectorError(400, "invalid_" + field);
  return n;
}

function bool(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function stringArray(value: unknown, maxItems: number, maxLength = 128): string[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || value.length > maxItems) throw new ConnectorError(400, "invalid_string_array");
  const out = value.map((item) => text(item, "string_array_item", maxLength));
  return [...new Set(out)];
}

async function readJson(req: Request): Promise<Json> {
  const declared = Number(req.headers.get("content-length") || 0);
  if (declared > MAX_BODY_BYTES) throw new ConnectorError(413, "request_body_too_large");
  const raw = await req.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) {
    throw new ConnectorError(413, "request_body_too_large");
  }
  let parsed: unknown = {};
  try {
    parsed = JSON.parse(raw || "{}");
  } catch {
    throw new ConnectorError(400, "invalid_json");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new ConnectorError(400, "invalid_json_object");
  }
  return parsed as Json;
}

function stable(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(stable).join(",") + "]";
  const record = value as Json;
  return "{" + Object.keys(record).sort().map((key) => JSON.stringify(key) + ":" + stable(record[key])).join(",") + "}";
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function decodeJwtPayload(req: Request): Json {
  const auth = req.headers.get("authorization") || "";
  if (!auth.startsWith("Bearer ")) return {};
  const token = auth.slice(7).trim();
  const parts = token.split(".");
  if (parts.length !== 3) return {};
  try {
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(parts[1].length / 4) * 4, "=");
    return obj(JSON.parse(atob(normalized)));
  } catch {
    return {};
  }
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const clean = value.replace(/\s+/g, "");
  const binary = atob(clean);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

function encodePath(path: string): string {
  return path.split("/").map((part) => encodeURIComponent(part)).join("/");
}

function q(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? "?" + encoded : "";
}

function concatBytes(...arrays: Uint8Array[]): Uint8Array {
  const output = new Uint8Array(arrays.reduce((sum, a) => sum + a.length, 0));
  let offset = 0;
  for (const array of arrays) {
    output.set(array, offset);
    offset += array.length;
  }
  return output;
}

function derLength(length: number): Uint8Array {
  if (length < 0x80) return Uint8Array.of(length);
  const bytes: number[] = [];
  let value = length;
  while (value > 0) {
    bytes.unshift(value & 0xff);
    value = Math.floor(value / 256);
  }
  return Uint8Array.of(0x80 | bytes.length, ...bytes);
}

function normalizeRsaPrivateKey(pem: string): string {
  const normalized = pem.trim();
  if (normalized.includes("-----BEGIN PRIVATE KEY-----")) return normalized + "\n";
  if (!normalized.includes("-----BEGIN RSA PRIVATE KEY-----")) {
    throw new ConnectorError(500, "unsupported_github_private_key_format");
  }

  const raw = normalized
    .replace("-----BEGIN RSA PRIVATE KEY-----", "")
    .replace("-----END RSA PRIVATE KEY-----", "")
    .replace(/\s+/g, "");

  const pkcs1 = base64ToBytes(raw);
  const version = Uint8Array.of(0x02, 0x01, 0x00);
  const rsaAlgorithm = Uint8Array.of(
    0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48,
    0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01, 0x05, 0x00,
  );
  const octet = concatBytes(Uint8Array.of(0x04), derLength(pkcs1.length), pkcs1);
  const body = concatBytes(version, rsaAlgorithm, octet);
  const pkcs8 = concatBytes(Uint8Array.of(0x30), derLength(body.length), body);
  const encoded = bytesToBase64(pkcs8);
  const lines = encoded.match(/.{1,64}/g)?.join("\n") || "";
  return "-----BEGIN PRIVATE KEY-----\n" + lines + "\n-----END PRIVATE KEY-----\n";
}

async function createAppJwt(appId: number, privateKeyPem: string): Promise<string> {
  const key = await importPKCS8(normalizeRsaPrivateKey(privateKeyPem), "RS256");
  const now = Math.floor(Date.now() / 1000);
  return await new SignJWT({})
    .setProtectedHeader({ alg: "RS256" })
    .setIssuer(String(appId))
    .setIssuedAt(now - 30)
    .setExpirationTime(now + 540)
    .sign(key);
}

type GhResult = {
  data: unknown;
  status: number;
  requestId: string | null;
  etag: string | null;
  rateRemaining: number | null;
};

async function gh(path: string, token: string, init: RequestInit = {}): Promise<GhResult> {
  const response = await fetch(GITHUB_API + path, {
    ...init,
    signal: init.signal || AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
    headers: {
      "accept": "application/vnd.github+json",
      "authorization": "Bearer " + token,
      "x-github-api-version": GITHUB_API_VERSION,
      "content-type": "application/json",
      ...(init.headers || {}),
    },
  });

  const raw = await response.text();
  let data: unknown = null;
  if (raw) {
    try { data = JSON.parse(raw); } catch { data = { raw: raw.slice(0, 4096) }; }
  }

  const requestId = response.headers.get("x-github-request-id");
  const etag = response.headers.get("etag");
  const remainingRaw = response.headers.get("x-ratelimit-remaining");
  const rateRemaining = remainingRaw !== null && /^\d+$/.test(remainingRaw) ? Number(remainingRaw) : null;

  if (!response.ok) {
    const body = obj(data);
    throw new ConnectorError(
      response.status >= 500 ? 502 : response.status,
      "github_http_" + response.status,
      typeof body.message === "string" ? body.message : "GitHub request failed",
      {
        github_status: response.status,
        github_request_id: requestId,
        accepted_permissions: response.headers.get("x-accepted-github-permissions"),
        documentation_url: typeof body.documentation_url === "string" ? body.documentation_url : null,
      },
    );
  }

  return { data, status: response.status, requestId, etag, rateRemaining };
}

async function ghMaybe(path: string, token: string, init: RequestInit = {}): Promise<GhResult> {
  try {
    return await gh(path, token, init);
  } catch (error) {
    if (error instanceof ConnectorError && error.code === "github_http_404") {
      return { data: null, status: 404, requestId: error.details.github_request_id as string || null, etag: null, rateRemaining: null };
    }
    throw error;
  }
}

async function revokeInstallationToken(token: string): Promise<void> {
  if (!token) return;
  try {
    await fetch(GITHUB_API + "/installation/token", {
      method: "DELETE",
      signal: AbortSignal.timeout(10000),
      headers: {
        "accept": "application/vnd.github+json",
        "authorization": "Bearer " + token,
        "x-github-api-version": GITHUB_API_VERSION,
      },
    });
  } catch {
    // Best-effort revocation. Tokens are short-lived and never persisted.
  }
}

async function latestConfig(): Promise<Json> {
  const { data, error } = await admin
    .from("github_connector_config_v1")
    .select("*")
    .eq("connector_key", CONNECTOR_KEY)
    .maybeSingle();
  if (error) throw new ConnectorError(500, "github_connector_config_read_failed");
  return obj(data || {});
}

async function latestBootstrap(owner: string): Promise<Json> {
  const { data, error } = await admin
    .from("apex_github_bootstrap_sessions")
    .select("*")
    .eq("status", "completed")
    .eq("owner_login", owner)
    .order("installed_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error || !data) throw new ConnectorError(503, "github_app_not_bootstrapped");
  const session = obj(data);
  if (!session.app_private_key_ref || !session.app_id || !session.installation_id) {
    throw new ConnectorError(503, "github_app_identity_incomplete");
  }
  const detail = obj(session.verification_detail);
  if (detail.installation_scope !== "all") {
    throw new ConnectorError(503, "github_app_installation_scope_not_all");
  }
  return session;
}

async function resolvePrivateKey(session: Json, operation: string, requestId: string, actor: string): Promise<string> {
  const { data, error } = await admin.rpc("resolve_apex_keymaster_secret_for_broker", {
    p_secret_ref: session.app_private_key_ref,
    p_provider: "github",
    p_request_id: (requestId + "-key").slice(0, 256),
    p_actor: actor.slice(0, 256),
    p_operation: operation.slice(0, 256),
  });

  if (error || typeof data?.secret !== "string" || !data.secret) {
    throw new ConnectorError(503, "github_private_key_resolution_failed");
  }
  return data.secret;
}

async function mintToken(appJwt: string, installationId: number, body: Json): Promise<{token: string; expiresAt: string; permissions: Json}> {
  const result = await gh("/app/installations/" + installationId + "/access_tokens", appJwt, {
    method: "POST",
    body: JSON.stringify(body),
  });
  const payload = obj(result.data);
  if (typeof payload.token !== "string" || typeof payload.expires_at !== "string") {
    throw new ConnectorError(502, "github_installation_token_invalid");
  }
  return {
    token: payload.token,
    expiresAt: payload.expires_at,
    permissions: obj(payload.permissions),
  };
}

function permissionSatisfied(actual: unknown, requested: Permission): boolean {
  if (actual === "write") return true;
  return requested === "read" && actual === "read";
}

function permissionsFor(operation: string): Record<string, Permission> {
  if (["repo.get"].includes(operation)) return { metadata: "read" };
  if (["contents.get", "tree.list", "branches.list", "commits.list", "code.search"].includes(operation)) return { contents: "read" };
  if (["issues.list", "issue.get"].includes(operation)) return { issues: "read" };
  if (["pulls.list", "pull.get"].includes(operation)) return { pull_requests: "read" };
  if (["actions.runs"].includes(operation)) return { actions: "read" };

  if (["branch.create", "contents.put"].includes(operation)) return { contents: "write" };
  if (["issue.create", "issue.comment", "pull.comment"].includes(operation)) return { issues: "write" };
  if (["pull.create", "pull.review"].includes(operation)) return { pull_requests: "write" };
  if (["workflow.dispatch"].includes(operation)) return { actions: "write" };

  throw new ConnectorError(400, "unsupported_operation");
}

function isWrite(operation: string): boolean {
  return [
    "branch.create", "contents.put", "issue.create", "issue.comment",
    "pull.create", "pull.comment", "pull.review", "workflow.dispatch",
  ].includes(operation);
}

async function getRepositoryContext(
  repository: string,
  permissions: Record<string, Permission>,
  operation: string,
  requestId: string,
  actor: string,
): Promise<{token: string; repo: Json; session: Json; lastRequestId: string | null}> {
  const config = await latestConfig();
  const owner = typeof config.owner_login === "string" && config.owner_login ? config.owner_login : "GlacierEQ";

  const parts = repository.split("/");
  if (parts.length !== 2 || parts[0] !== owner || !/^[A-Za-z0-9_.-]+$/.test(parts[1])) {
    throw new ConnectorError(403, "repository_scope_rejected");
  }

  const session = await latestBootstrap(owner);
  let privateKey = "";
  let resolverToken = "";
  let workloadToken = "";
  let lastRequestId: string | null = null;

  try {
    privateKey = await resolvePrivateKey(session, operation, requestId, actor);
    let jwt = await createAppJwt(Number(session.app_id), privateKey);
    privateKey = "";

    const installationId = Number(session.installation_id);
    const installationResult = await gh("/app/installations/" + installationId, jwt);
    lastRequestId = installationResult.requestId;
    const installation = obj(installationResult.data);
    const account = obj(installation.account);

    if (
      Number(installation.id) !== installationId ||
      Number(installation.app_id) !== Number(session.app_id) ||
      String(account.login || "") !== owner ||
      installation.suspended_at
    ) {
      throw new ConnectorError(503, "github_installation_binding_rejected");
    }

    const repoInstallationResult = await gh("/repos/" + encodeURIComponent(owner) + "/" + encodeURIComponent(parts[1]) + "/installation", jwt);
    lastRequestId = repoInstallationResult.requestId;
    const repoInstallation = obj(repoInstallationResult.data);
    if (Number(repoInstallation.id) !== installationId) {
      throw new ConnectorError(403, "repository_not_in_live_installation");
    }

    const resolver = await mintToken(jwt, installationId, { permissions: { metadata: "read" } });
    resolverToken = resolver.token;

    const repoResult = await gh("/repos/" + encodeURIComponent(owner) + "/" + encodeURIComponent(parts[1]), resolverToken);
    lastRequestId = repoResult.requestId;
    const repo = obj(repoResult.data);
    if (String(repo.full_name || "") !== repository || !Number.isSafeInteger(Number(repo.id))) {
      throw new ConnectorError(502, "github_repository_identity_resolution_failed");
    }
    const repositoryId = Number(repo.id);

    await revokeInstallationToken(resolverToken);
    resolverToken = "";

    const minted = await mintToken(jwt, installationId, {
      repository_ids: [repositoryId],
      permissions,
    });
    jwt = "";
    workloadToken = minted.token;

    for (const [name, level] of Object.entries(permissions)) {
      if (name === "metadata") continue;
      if (!permissionSatisfied(minted.permissions[name], level)) {
        throw new ConnectorError(403, "github_permission_mismatch", "Requested GitHub App permission was not granted", {
          permission: name,
          requested: level,
          granted: minted.permissions[name] || null,
        });
      }
    }

    return { token: workloadToken, repo, session, lastRequestId };
  } catch (error) {
    await revokeInstallationToken(resolverToken);
    await revokeInstallationToken(workloadToken);
    throw error;
  } finally {
    privateKey = "";
  }
}

async function priorSuccessfulWrite(requestId: string): Promise<Json | null> {
  const { data, error } = await admin
    .from("github_connector_receipts_v1")
    .select("request_id,correlation_id,operation,repository,target_ref,outcome,readback_verified,before_sha,after_sha,result_summary,created_at")
    .eq("request_id", requestId)
    .eq("mutation_class", "write")
    .eq("outcome", "succeeded")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw new ConnectorError(500, "receipt_idempotency_lookup_failed");
  return data ? obj(data) : null;
}

async function persistReceipt(input: {
  requestId: string;
  correlationId: string;
  operation: string;
  repository: string | null;
  targetRef: string | null;
  mutationClass: "read" | "write" | "trigger" | "admin";
  outcome: "succeeded" | "failed" | "rejected";
  requestHash: string;
  responseHash?: string | null;
  githubRequestId?: string | null;
  readbackVerified?: boolean;
  beforeSha?: string | null;
  afterSha?: string | null;
  durationMs: number;
  actor: string;
  resultSummary?: Json;
  metadata?: Json;
}): Promise<void> {
  const { error } = await admin.from("github_connector_receipts_v1").insert({
    request_id: input.requestId,
    correlation_id: input.correlationId,
    connector_key: CONNECTOR_KEY,
    operation: input.operation,
    repository: input.repository,
    target_ref: input.targetRef,
    mutation_class: input.mutationClass,
    outcome: input.outcome,
    request_hash: input.requestHash,
    response_hash: input.responseHash || null,
    github_request_id: input.githubRequestId || null,
    readback_verified: input.readbackVerified || false,
    before_sha: input.beforeSha || null,
    after_sha: input.afterSha || null,
    duration_ms: input.durationMs,
    actor: input.actor,
    result_summary: input.resultSummary || {},
    metadata: input.metadata || {},
  });
  if (error) throw new ConnectorError(500, "receipt_persistence_failed", error.message);
}

function summarize(operation: string, result: Json): Json {
  if (operation === "contents.get") {
    return {
      path: result.path || null,
      sha: result.sha || null,
      size: result.size || null,
      type: result.type || null,
      directory_entries: Array.isArray(result.entries) ? result.entries.length : null,
    };
  }
  if (operation === "tree.list") {
    return {
      ref: result.ref || null,
      entries_returned: result.entries_returned || 0,
      truncated: result.truncated || false,
    };
  }
  if (operation === "code.search") {
    return { total_count: result.total_count || 0, items_returned: Array.isArray(result.items) ? result.items.length : 0 };
  }
  return result;
}

async function runHealth(requestId: string, actor: string): Promise<Json> {
  const config = await latestConfig();
  const owner = typeof config.owner_login === "string" && config.owner_login ? config.owner_login : "GlacierEQ";
  const session = await latestBootstrap(owner);

  let privateKey = "";
  let token = "";
  try {
    privateKey = await resolvePrivateKey(session, "health", requestId, actor);
    let jwt = await createAppJwt(Number(session.app_id), privateKey);
    privateKey = "";

    const installationId = Number(session.installation_id);
    const installationResult = await gh("/app/installations/" + installationId, jwt);
    const installation = obj(installationResult.data);
    const account = obj(installation.account);
    if (
      Number(installation.id) !== installationId ||
      Number(installation.app_id) !== Number(session.app_id) ||
      String(account.login || "") !== owner ||
      installation.suspended_at
    ) {
      throw new ConnectorError(503, "github_installation_binding_rejected");
    }

    const minted = await mintToken(jwt, installationId, { permissions: { metadata: "read" } });
    jwt = "";
    token = minted.token;

    const repoListResult = await gh("/installation/repositories?per_page=1", token);
    const repoList = obj(repoListResult.data);
    const totalCount = Number(repoList.total_count || 0);

    await admin
      .from("connector_registry_v2")
      .update({
        health_status: "healthy",
        lifecycle_state: "connected",
        authentication_state: "authenticated",
        last_checked_at: new Date().toISOString(),
        last_successful_probe_at: new Date().toISOString(),
        freshness_status: "fresh",
        updated_at: new Date().toISOString(),
      })
      .eq("connector_key", CONNECTOR_KEY);

    return {
      ok: true,
      connector_key: CONNECTOR_KEY,
      owner_login: owner,
      app_id: Number(session.app_id),
      installation_id: installationId,
      installation_scope: obj(session.verification_detail).installation_scope || null,
      repositories_accessible: totalCount,
      token_persisted: false,
      default_branch_writes_allowed: false,
      destructive_actions_allowed: false,
      mode: "pr_first",
      github_request_id: repoListResult.requestId,
      rate_remaining: repoListResult.rateRemaining,
    };
  } finally {
    privateKey = "";
    await revokeInstallationToken(token);
  }
}

async function executeOperation(operation: string, repository: string, args: Json, ctx: {
  requestId: string;
  actor: string;
}): Promise<{
  result: Json;
  githubRequestId: string | null;
  readbackVerified: boolean;
  beforeSha: string | null;
  afterSha: string | null;
  targetRef: string | null;
}> {
  const permissions = permissionsFor(operation);
  const repoCtx = await getRepositoryContext(repository, permissions, operation, ctx.requestId, ctx.actor);
  const token = repoCtx.token;
  const repo = repoCtx.repo;
  let githubRequestId = repoCtx.lastRequestId;
  let readbackVerified = false;
  let beforeSha: string | null = null;
  let afterSha: string | null = null;
  let targetRef: string | null = null;

  try {
    if (operation === "repo.get") {
      const result = {
        id: repo.id,
        full_name: repo.full_name,
        private: repo.private,
        archived: repo.archived,
        default_branch: repo.default_branch,
        visibility: repo.visibility,
        pushed_at: repo.pushed_at,
        updated_at: repo.updated_at,
        permissions: repo.permissions || null,
      };
      return { result, githubRequestId, readbackVerified, beforeSha, afterSha, targetRef };
    }

    if (operation === "contents.get") {
      const path = text(args.path, "path", 4096);
      const ref = text(args.ref, "ref", 256, false);
      targetRef = ref || String(repo.default_branch || "");
      const result = await gh(
        "/repos/" + repository + "/contents/" + encodePath(path) + q({ ref: targetRef }),
        token,
      );
      githubRequestId = result.requestId;

      if (Array.isArray(result.data)) {
        const entries = result.data.slice(0, 1000).map((item: unknown) => {
          const row = obj(item);
          return {
            name: row.name,
            path: row.path,
            sha: row.sha,
            type: row.type,
            size: row.size,
          };
        });
        return {
          result: { type: "dir", path, ref: targetRef, entries },
          githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
        };
      }

      const file = obj(result.data);
      let contentText: string | null = null;
      if (file.encoding === "base64" && typeof file.content === "string" && Number(file.size || 0) <= MAX_CONTENT_BYTES) {
        contentText = new TextDecoder().decode(base64ToBytes(file.content));
      }
      return {
        result: {
          type: file.type,
          name: file.name,
          path: file.path,
          sha: file.sha,
          size: file.size,
          ref: targetRef,
          content_text: contentText,
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "tree.list") {
      const ref = text(args.ref, "ref", 256, false) || String(repo.default_branch || "");
      targetRef = ref;
      const result = await gh("/repos/" + repository + "/git/trees/" + encodeURIComponent(ref) + "?recursive=1", token);
      githubRequestId = result.requestId;
      const payload = obj(result.data);
      const tree = Array.isArray(payload.tree) ? payload.tree : [];
      const entries = tree.slice(0, MAX_TREE_ENTRIES).map((item: unknown) => {
        const row = obj(item);
        return { path: row.path, mode: row.mode, type: row.type, sha: row.sha, size: row.size || null };
      });
      return {
        result: {
          ref,
          tree_sha: payload.sha || null,
          entries,
          entries_returned: entries.length,
          truncated: bool(payload.truncated) || tree.length > MAX_TREE_ENTRIES,
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "branches.list") {
      const perPage = args.per_page === undefined ? 100 : integer(args.per_page, "per_page", 1, 100);
      const result = await gh("/repos/" + repository + "/branches" + q({ per_page: perPage }), token);
      githubRequestId = result.requestId;
      const rows = Array.isArray(result.data) ? result.data : [];
      return {
        result: {
          branches: rows.map((item: unknown) => {
            const row = obj(item);
            return { name: row.name, protected: row.protected, commit: obj(row.commit).sha || null };
          }),
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "commits.list") {
      const ref = text(args.ref, "ref", 256, false);
      const path = text(args.path, "path", 4096, false);
      const perPage = args.per_page === undefined ? 50 : integer(args.per_page, "per_page", 1, 100);
      targetRef = ref || null;
      const result = await gh("/repos/" + repository + "/commits" + q({ sha: ref || undefined, path: path || undefined, per_page: perPage }), token);
      githubRequestId = result.requestId;
      const rows = Array.isArray(result.data) ? result.data : [];
      return {
        result: {
          commits: rows.map((item: unknown) => {
            const row = obj(item);
            const commit = obj(row.commit);
            const author = obj(commit.author);
            return {
              sha: row.sha,
              message: commit.message,
              authored_at: author.date || null,
              html_url: row.html_url || null,
            };
          }),
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "code.search") {
      const query = text(args.query, "query", 1024);
      const perPage = args.per_page === undefined ? 30 : integer(args.per_page, "per_page", 1, 100);
      const search = query + " repo:" + repository;
      const result = await gh("/search/code" + q({ q: search, per_page: perPage }), token);
      githubRequestId = result.requestId;
      const payload = obj(result.data);
      const items = Array.isArray(payload.items) ? payload.items : [];
      return {
        result: {
          total_count: payload.total_count || 0,
          incomplete_results: payload.incomplete_results || false,
          items: items.map((item: unknown) => {
            const row = obj(item);
            return { name: row.name, path: row.path, sha: row.sha, html_url: row.html_url || null };
          }),
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "issues.list") {
      const state = text(args.state, "state", 16, false) || "open";
      if (!["open", "closed", "all"].includes(state)) throw new ConnectorError(400, "invalid_state");
      const perPage = args.per_page === undefined ? 50 : integer(args.per_page, "per_page", 1, 100);
      const result = await gh("/repos/" + repository + "/issues" + q({ state, per_page: perPage }), token);
      githubRequestId = result.requestId;
      const rows = Array.isArray(result.data) ? result.data : [];
      return {
        result: {
          issues: rows.filter((item: unknown) => !obj(item).pull_request).map((item: unknown) => {
            const row = obj(item);
            return { number: row.number, title: row.title, state: row.state, html_url: row.html_url, updated_at: row.updated_at };
          }),
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "issue.get") {
      const number = integer(args.number, "number");
      const result = await gh("/repos/" + repository + "/issues/" + number, token);
      githubRequestId = result.requestId;
      const row = obj(result.data);
      return {
        result: {
          number: row.number, title: row.title, body: row.body, state: row.state,
          labels: row.labels || [], assignees: row.assignees || [], html_url: row.html_url, updated_at: row.updated_at,
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "pulls.list") {
      const state = text(args.state, "state", 16, false) || "open";
      if (!["open", "closed", "all"].includes(state)) throw new ConnectorError(400, "invalid_state");
      const perPage = args.per_page === undefined ? 50 : integer(args.per_page, "per_page", 1, 100);
      const result = await gh("/repos/" + repository + "/pulls" + q({ state, per_page: perPage }), token);
      githubRequestId = result.requestId;
      const rows = Array.isArray(result.data) ? result.data : [];
      return {
        result: {
          pulls: rows.map((item: unknown) => {
            const row = obj(item);
            return {
              number: row.number, title: row.title, state: row.state, draft: row.draft,
              head: obj(row.head).ref || null, base: obj(row.base).ref || null,
              mergeable_state: row.mergeable_state || null, html_url: row.html_url, updated_at: row.updated_at,
            };
          }),
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "pull.get") {
      const number = integer(args.number, "number");
      const result = await gh("/repos/" + repository + "/pulls/" + number, token);
      githubRequestId = result.requestId;
      const row = obj(result.data);
      return {
        result: {
          number: row.number, title: row.title, body: row.body, state: row.state, draft: row.draft,
          head: obj(row.head).ref || null, head_sha: obj(row.head).sha || null,
          base: obj(row.base).ref || null, base_sha: obj(row.base).sha || null,
          mergeable: row.mergeable ?? null, mergeable_state: row.mergeable_state || null,
          changed_files: row.changed_files || 0, additions: row.additions || 0, deletions: row.deletions || 0,
          html_url: row.html_url, updated_at: row.updated_at,
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "actions.runs") {
      const branch = text(args.branch, "branch", 256, false);
      const status = text(args.status, "status", 64, false);
      const perPage = args.per_page === undefined ? 30 : integer(args.per_page, "per_page", 1, 100);
      const result = await gh("/repos/" + repository + "/actions/runs" + q({ branch: branch || undefined, status: status || undefined, per_page: perPage }), token);
      githubRequestId = result.requestId;
      const payload = obj(result.data);
      const runs = Array.isArray(payload.workflow_runs) ? payload.workflow_runs : [];
      return {
        result: {
          total_count: payload.total_count || 0,
          runs: runs.map((item: unknown) => {
            const row = obj(item);
            return {
              id: row.id, name: row.name, event: row.event, status: row.status, conclusion: row.conclusion,
              head_branch: row.head_branch, head_sha: row.head_sha, html_url: row.html_url,
              created_at: row.created_at, updated_at: row.updated_at,
            };
          }),
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "branch.create") {
      const branch = text(args.branch, "branch", 256);
      const defaultBranch = String(repo.default_branch || "");
      const base = text(args.base_branch, "base_branch", 256, false) || defaultBranch;
      if (!branch || branch === defaultBranch) throw new ConnectorError(403, "default_branch_write_blocked");
      if (branch.startsWith("refs/") || branch.includes("..") || /[~^:?*[\\]]/.test(branch)) {
        throw new ConnectorError(400, "invalid_branch");
      }
      targetRef = branch;

      const baseResult = await gh("/repos/" + repository + "/git/ref/heads/" + encodeURIComponent(base), token);
      githubRequestId = baseResult.requestId;
      const baseSha = String(obj(obj(baseResult.data).object).sha || "");
      if (!baseSha) throw new ConnectorError(502, "base_branch_sha_missing");
      beforeSha = baseSha;

      const existing = await ghMaybe("/repos/" + repository + "/git/ref/heads/" + encodeURIComponent(branch), token);
      if (existing.status === 200) {
        githubRequestId = existing.requestId;
        const existingSha = String(obj(obj(existing.data).object).sha || "");
        afterSha = existingSha;
        readbackVerified = existingSha === baseSha;
        if (!readbackVerified) throw new ConnectorError(409, "branch_exists_with_different_sha", undefined, { existing_sha: existingSha, requested_base_sha: baseSha });
        return {
          result: { branch, base_branch: base, sha: existingSha, existed: true, readback_verified: true },
          githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
        };
      }

      const created = await gh("/repos/" + repository + "/git/refs", token, {
        method: "POST",
        body: JSON.stringify({ ref: "refs/heads/" + branch, sha: baseSha }),
      });
      githubRequestId = created.requestId;

      const verify = await gh("/repos/" + repository + "/git/ref/heads/" + encodeURIComponent(branch), token);
      githubRequestId = verify.requestId;
      const verifySha = String(obj(obj(verify.data).object).sha || "");
      afterSha = verifySha;
      readbackVerified = verifySha === baseSha;
      if (!readbackVerified) throw new ConnectorError(502, "branch_readback_mismatch");

      return {
        result: { branch, base_branch: base, sha: verifySha, existed: false, readback_verified: true },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "contents.put") {
      const path = text(args.path, "path", 4096);
      const branch = text(args.branch, "branch", 256);
      const message = text(args.message, "message", 512);
      const content = text(args.content, "content", MAX_CONTENT_BYTES, false);
      const bytes = new TextEncoder().encode(content);
      if (bytes.byteLength > MAX_CONTENT_BYTES) throw new ConnectorError(413, "content_too_large");

      const defaultBranch = String(repo.default_branch || "");
      if (branch === defaultBranch) throw new ConnectorError(403, "default_branch_write_blocked");
      targetRef = branch;

      const current = await ghMaybe("/repos/" + repository + "/contents/" + encodePath(path) + q({ ref: branch }), token);
      let currentSha = "";
      if (current.status === 200) {
        githubRequestId = current.requestId;
        const row = obj(current.data);
        if (row.type !== "file" || typeof row.sha !== "string") throw new ConnectorError(409, "target_path_not_file");
        currentSha = row.sha;
        beforeSha = currentSha;
      }

      const body: Json = {
        message,
        content: bytesToBase64(bytes),
        branch,
      };
      if (currentSha) body.sha = currentSha;

      const written = await gh("/repos/" + repository + "/contents/" + encodePath(path), token, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      githubRequestId = written.requestId;
      const writtenPayload = obj(written.data);
      const contentRow = obj(writtenPayload.content);
      afterSha = typeof contentRow.sha === "string" ? contentRow.sha : null;

      const verify = await gh("/repos/" + repository + "/contents/" + encodePath(path) + q({ ref: branch }), token);
      githubRequestId = verify.requestId;
      const verifyRow = obj(verify.data);
      if (verifyRow.encoding !== "base64" || typeof verifyRow.content !== "string") {
        throw new ConnectorError(502, "contents_readback_unavailable");
      }

      const desiredHash = await sha256Hex(content);
      const readbackText = new TextDecoder().decode(base64ToBytes(verifyRow.content));
      const readbackHash = await sha256Hex(readbackText);
      readbackVerified = desiredHash === readbackHash;
      afterSha = typeof verifyRow.sha === "string" ? verifyRow.sha : afterSha;
      if (!readbackVerified) throw new ConnectorError(502, "contents_readback_hash_mismatch");

      return {
        result: {
          path, branch, before_sha: beforeSha, after_sha: afterSha,
          commit_sha: obj(writtenPayload.commit).sha || null,
          content_sha256: desiredHash,
          readback_sha256: readbackHash,
          readback_verified: true,
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "issue.create") {
      const title = text(args.title, "title", 256);
      const body = text(args.body, "body", 65536, false);
      const labels = stringArray(args.labels, 20, 128);
      const assignees = stringArray(args.assignees, 10, 64);
      const payload: Json = { title };
      if (body) payload.body = body;
      if (labels.length) payload.labels = labels;
      if (assignees.length) payload.assignees = assignees;

      const created = await gh("/repos/" + repository + "/issues", token, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      githubRequestId = created.requestId;
      const row = obj(created.data);
      const number = Number(row.number);
      const verify = await gh("/repos/" + repository + "/issues/" + number, token);
      githubRequestId = verify.requestId;
      const verifyRow = obj(verify.data);
      readbackVerified = String(verifyRow.title || "") === title;
      if (!readbackVerified) throw new ConnectorError(502, "issue_readback_mismatch");
      targetRef = "issue:" + number;
      afterSha = typeof row.node_id === "string" ? row.node_id : null;
      return {
        result: { number, title: verifyRow.title, state: verifyRow.state, html_url: verifyRow.html_url, readback_verified: true },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "issue.comment" || operation === "pull.comment") {
      const number = integer(args.number, "number");
      const body = text(args.body, "body", 65536);
      const created = await gh("/repos/" + repository + "/issues/" + number + "/comments", token, {
        method: "POST",
        body: JSON.stringify({ body }),
      });
      githubRequestId = created.requestId;
      const row = obj(created.data);
      const commentId = Number(row.id);
      const verify = await gh("/repos/" + repository + "/issues/comments/" + commentId, token);
      githubRequestId = verify.requestId;
      const verifyRow = obj(verify.data);
      readbackVerified = String(verifyRow.body || "") === body;
      if (!readbackVerified) throw new ConnectorError(502, "comment_readback_mismatch");
      targetRef = (operation === "pull.comment" ? "pull:" : "issue:") + number + "#comment:" + commentId;
      return {
        result: { number, comment_id: commentId, html_url: verifyRow.html_url, readback_verified: true },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "pull.create") {
      const title = text(args.title, "title", 256);
      const head = text(args.head, "head", 256);
      const base = text(args.base, "base", 256, false) || String(repo.default_branch || "");
      const body = text(args.body, "body", 65536, false);
      if (head === base || head.includes(":")) throw new ConnectorError(400, "invalid_pull_head");
      const payload: Json = { title, head, base, draft: bool(args.draft) };
      if (body) payload.body = body;

      const created = await gh("/repos/" + repository + "/pulls", token, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      githubRequestId = created.requestId;
      const row = obj(created.data);
      const number = Number(row.number);

      const verify = await gh("/repos/" + repository + "/pulls/" + number, token);
      githubRequestId = verify.requestId;
      const verifyRow = obj(verify.data);
      readbackVerified =
        String(verifyRow.title || "") === title &&
        String(obj(verifyRow.head).ref || "") === head &&
        String(obj(verifyRow.base).ref || "") === base;
      if (!readbackVerified) throw new ConnectorError(502, "pull_readback_mismatch");
      targetRef = "pull:" + number;
      afterSha = typeof obj(verifyRow.head).sha === "string" ? String(obj(verifyRow.head).sha) : null;

      return {
        result: {
          number, title, head, base, draft: verifyRow.draft || false,
          html_url: verifyRow.html_url, head_sha: afterSha, readback_verified: true,
        },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "pull.review") {
      const number = integer(args.number, "number");
      const event = text(args.event, "event", 32).toUpperCase();
      if (!["COMMENT", "APPROVE", "REQUEST_CHANGES"].includes(event)) {
        throw new ConnectorError(400, "invalid_review_event");
      }
      const body = text(args.body, "body", 65536, event !== "APPROVE");
      const payload: Json = { event };
      if (body) payload.body = body;

      const created = await gh("/repos/" + repository + "/pulls/" + number + "/reviews", token, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      githubRequestId = created.requestId;
      const row = obj(created.data);
      const reviewId = Number(row.id);

      const verify = await gh("/repos/" + repository + "/pulls/" + number + "/reviews/" + reviewId, token);
      githubRequestId = verify.requestId;
      const verifyRow = obj(verify.data);
      readbackVerified = Number(verifyRow.id) === reviewId;
      if (!readbackVerified) throw new ConnectorError(502, "review_readback_mismatch");
      targetRef = "pull:" + number + "#review:" + reviewId;

      return {
        result: { number, review_id: reviewId, state: verifyRow.state, html_url: verifyRow.html_url, readback_verified: true },
        githubRequestId, readbackVerified, beforeSha, afterSha, targetRef,
      };
    }

    if (operation === "workflow.dispatch") {
      const workflowId = text(String(args.workflow_id ?? ""), "workflow_id", 256);
      const ref = text(args.ref, "ref", 256);
      const inputs = obj(args.inputs);
      if (Object.keys(inputs).length > 50) throw new ConnectorError(400, "too_many_workflow_inputs");
      targetRef = "workflow:" + workflowId + "@" + ref;

      const dispatched = await gh("/repos/" + repository + "/actions/workflows/" + encodeURIComponent(workflowId) + "/dispatches", token, {
        method: "POST",
        body: JSON.stringify({ ref, inputs }),
      });
      githubRequestId = dispatched.requestId;
      readbackVerified = dispatched.status === 204;

      return {
        result: {
          workflow_id: workflowId,
          ref,
          accepted: dispatched.status === 204,
          readback_verified: false,
          note: "GitHub accepted the dispatch; exact downstream workflow completion is intentionally not self-certified.",
        },
        githubRequestId, readbackVerified: false, beforeSha, afterSha, targetRef,
      };
    }

    throw new ConnectorError(400, "unsupported_operation");
  } finally {
    await revokeInstallationToken(token);
  }
}

Deno.serve(async (req: Request) => {
  const started = Date.now();
  const correlationId = crypto.randomUUID();
  if (req.method !== "POST") return respond(405, { ok: false, error: "method_not_allowed", correlation_id: correlationId });

  let input: Json = {};
  let requestId = "";
  let operation = "";
  let repository: string | null = null;
  let requestHash = "";
  let actor = "supabase-authenticated";
  let mutationClass: "read" | "write" | "trigger" | "admin" = "read";

  try {
    input = await readJson(req);
    operation = text(input.operation, "operation", 128);
    const jwt = decodeJwtPayload(req);
    const sub = typeof jwt.sub === "string" ? jwt.sub : "";
    const role = typeof jwt.role === "string" ? jwt.role : "";
    actor = sub ? "supabase:" + sub : (role ? "supabase-role:" + role : "supabase-authenticated");

    const requestedActor = text(input.actor, "actor", 256, false);
    const write = operation !== "health" && isWrite(operation);
    mutationClass = write ? "write" : operation === "health" ? "admin" : "read";

    requestId = text(input.request_id, "request_id", 256, !write);
    if (!requestId) requestId = crypto.randomUUID();
    if (write && requestId.length < 8) throw new ConnectorError(400, "request_id_required_for_write");

    repository = operation === "health" ? null : text(input.repository, "repository", 256);
    const args = obj(input.args);
    requestHash = await sha256Hex(stable({ operation, repository, args }));

    if (write) {
      const prior = await priorSuccessfulWrite(requestId);
      if (prior) {
        return respond(200, {
          ok: true,
          idempotent_replay: true,
          connector_key: CONNECTOR_KEY,
          request_id: requestId,
          correlation_id: prior.correlation_id,
          operation: prior.operation,
          repository: prior.repository,
          target_ref: prior.target_ref,
          readback_verified: prior.readback_verified,
          result: prior.result_summary,
          receipt_created_at: prior.created_at,
        });
      }
    }

    let result: Json;
    let githubRequestId: string | null = null;
    let readbackVerified = false;
    let beforeSha: string | null = null;
    let afterSha: string | null = null;
    let targetRef: string | null = null;

    if (operation === "health") {
      result = await runHealth(requestId, actor);
      githubRequestId = typeof result.github_request_id === "string" ? result.github_request_id : null;
      readbackVerified = true;
    } else {
      const execution = await executeOperation(operation, repository as string, obj(input.args), { requestId, actor });
      result = execution.result;
      githubRequestId = execution.githubRequestId;
      readbackVerified = execution.readbackVerified;
      beforeSha = execution.beforeSha;
      afterSha = execution.afterSha;
      targetRef = execution.targetRef;
    }

    const responseHash = await sha256Hex(stable(result));
    const summary = summarize(operation, result);
    try {
      await persistReceipt({
        requestId,
        correlationId,
        operation,
        repository,
        targetRef,
        mutationClass,
        outcome: "succeeded",
        requestHash,
        responseHash,
        githubRequestId,
        readbackVerified,
        beforeSha,
        afterSha,
        durationMs: Date.now() - started,
        actor,
        resultSummary: summary,
        metadata: {
          requested_actor: text(input.actor, "actor", 256, false) || null,
          token_persisted: false,
          default_branch_writes_allowed: false,
          destructive_actions_allowed: false,
          mode: "pr_first",
        },
      });
    } catch (receiptError) {
      const message = receiptError instanceof Error ? receiptError.message : "receipt_persistence_failed";
      return respond(502, {
        ok: false,
        error: "receipt_persistence_failed_after_github_success",
        ambiguous_external_outcome: mutationClass === "write",
        operation,
        repository,
        request_id: requestId,
        correlation_id: correlationId,
        result_summary: summary,
        detail: message,
      });
    }

    return respond(200, {
      ok: true,
      connector_key: CONNECTOR_KEY,
      request_id: requestId,
      correlation_id: correlationId,
      operation,
      repository,
      target_ref: targetRef,
      readback_verified: readbackVerified,
      github_request_id: githubRequestId,
      result,
    });
  } catch (error) {
    const connectorError = error instanceof ConnectorError
      ? error
      : new ConnectorError(500, "internal_connector_error", error instanceof Error ? error.message : "internal_connector_error");

    if (!requestHash) {
      try { requestHash = await sha256Hex(stable({ operation, repository, input })); } catch { requestHash = "unavailable"; }
    }

    if (requestId && operation) {
      try {
        await persistReceipt({
          requestId,
          correlationId,
          operation,
          repository,
          targetRef: null,
          mutationClass,
          outcome: connectorError.status === 400 || connectorError.status === 401 || connectorError.status === 403 ? "rejected" : "failed",
          requestHash,
          responseHash: null,
          githubRequestId: typeof connectorError.details.github_request_id === "string" ? connectorError.details.github_request_id : null,
          readbackVerified: false,
          durationMs: Date.now() - started,
          actor,
          resultSummary: { error: connectorError.code },
          metadata: { details: connectorError.details, token_persisted: false },
        });
      } catch {
        // Preserve the primary error; receipt failure is surfaced explicitly below.
      }
    }

    return respond(connectorError.status, {
      ok: false,
      connector_key: CONNECTOR_KEY,
      request_id: requestId || null,
      correlation_id: correlationId,
      operation: operation || null,
      repository,
      error: connectorError.code,
      message: connectorError.message,
      details: connectorError.details,
    });
  }
});
