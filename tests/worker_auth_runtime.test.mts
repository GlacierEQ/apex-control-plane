import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";
import { pathToFileURL } from "node:url";
import path from "node:path";

const REPO_ROOT = path.resolve(import.meta.dirname, "..");

function makeJwt(payload: Record<string, unknown>): string {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${header}.${body}.fakesignature`;
}

const SERVICE_KEY = "sb_secret_service_role_primary_test_key_0123456789";
const ROTATED_KEY = "sb_secret_service_role_rotated_test_key_9876543210";
const WORKER_SECRET = "apex_internal_worker_secret_test_value_abcdef012345";
const ANON_KEY = makeJwt({ role: "anon", iss: "supabase" });
const USER_JWT = makeJwt({ role: "authenticated", sub: "11111111-2222-3333-4444-555555555555" });

// Runtime mock state for Edge Function handler execution under Node
type RpcHandler = (fn: string, args: Record<string, unknown>) => Promise<{ data: unknown; error: { message: string } | null }>;
let activeEnv: Record<string, string> = {};
let rpcCalls: Array<{ fn: string; args: Record<string, unknown> }> = [];
let fromCalls: string[] = [];
let rpcImpl: RpcHandler = async () => ({ data: null, error: null });
let lastServedHandler: ((req: Request) => Promise<Response> | Response) | null = null;
let waitUntilPromises: Promise<unknown>[] = [];

class MockRateLimitError extends Error {
  retryAfterMs?: number;
}

(globalThis as Record<string, unknown>).Deno = {
  env: {
    get(key: string): string | undefined {
      return activeEnv[key];
    },
  },
  errors: {
    RateLimitError: MockRateLimitError,
  },
  serve(handler: (req: Request) => Promise<Response> | Response) {
    lastServedHandler = handler;
    return { finished: Promise.resolve() };
  },
};

(globalThis as Record<string, unknown>).EdgeRuntime = {
  waitUntil(promise: Promise<unknown>) {
    waitUntilPromises.push(promise);
  },
};

const VIRTUAL_SUPABASE_MODULE = `
export function createClient() {
  return {
    rpc(fn, args = {}) {
      globalThis.__apexTestRecordRpc(fn, args);
      const p = globalThis.__apexTestInvokeRpc(fn, args);
      return p;
    },
    from(table) {
      globalThis.__apexTestRecordFrom(table);
      const chain = {
        select() { return chain; },
        eq() { return chain; },
        in() { return Promise.resolve({ count: globalThis.__apexTestPendingCount ?? 0, data: [], error: null }); },
        single() { return Promise.resolve({ data: {}, error: null }); },
        maybeSingle() { return Promise.resolve({ data: null, error: null }); },
        insert() { return Promise.resolve({ data: null, error: null }); },
        upsert() { return Promise.resolve({ data: null, error: null }); },
        update() { return chain; },
        order() { return chain; },
        limit() { return chain; },
        not() { return chain; },
        gte() { return chain; },
        is() { return chain; },
      };
      return chain;
    },
  };
}
`;

(globalThis as Record<string, unknown>).__apexTestRecordRpc = (fn: string, args: Record<string, unknown>) => {
  rpcCalls.push({ fn, args });
};
(globalThis as Record<string, unknown>).__apexTestInvokeRpc = (fn: string, args: Record<string, unknown>) => rpcImpl(fn, args);
(globalThis as Record<string, unknown>).__apexTestRecordFrom = (table: string) => {
  fromCalls.push(table);
};
(globalThis as Record<string, unknown>).__apexTestPendingCount = 0;

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "jsr:@supabase/functions-js/edge-runtime.d.ts") {
      return { url: "data:text/javascript,export {};", shortCircuit: true };
    }
    if (
      specifier === "npm:@supabase/supabase-js@2" ||
      specifier === "jsr:@supabase/supabase-js@2" ||
      specifier === "https://esm.sh/@supabase/supabase-js@2"
    ) {
      return {
        url: `data:text/javascript,${encodeURIComponent(VIRTUAL_SUPABASE_MODULE)}`,
        shortCircuit: true,
      };
    }
    return nextResolve(specifier, context);
  },
});

async function loadWorkerModule(relPath: string, env: Record<string, string>) {
  activeEnv = { ...env };
  lastServedHandler = null;
  const fullPath = path.join(REPO_ROOT, relPath);
  const url = `${pathToFileURL(fullPath).href}?t=${Date.now()}_${Math.random()}`;
  await import(url);
  assert.ok(lastServedHandler, `Expected ${relPath} to register a Deno.serve handler`);
  return lastServedHandler!;
}

function unconsumedJsonRequest(url: string, headers: Record<string, string>) {
  const req = new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify({ limit: 5 }),
  });
  return { req, wasBodyRead: () => req.bodyUsed };
}

test("shared worker_auth enforces constant-time secrets, key rotation, origin allowlist, and role rejections", async () => {
  const authMod = await import("../supabase/functions/_shared/worker_auth.ts");
  const envMap: Record<string, string> = {
    SUPABASE_URL: "https://example.supabase.co",
    SUPABASE_SERVICE_ROLE_KEY: SERVICE_KEY,
    SUPABASE_SECRET_KEYS: JSON.stringify({ current: SERVICE_KEY, next: ROTATED_KEY }),
    SUPABASE_ANON_KEY: ANON_KEY,
    APEX_INTERNAL_WORKER_SECRET: WORKER_SECRET,
  };
  const getEnv = (k: string) => envMap[k];

  assert.equal(authMod.constantTimeEqual("alpha-secret", "alpha-secret"), true);
  assert.equal(authMod.constantTimeEqual("alpha-secret", "alpha-secrex"), false);
  assert.equal(authMod.constantTimeEqual("short", "longer-secret"), false);

  // 1. Missing credentials -> 401 worker_auth_required
  {
    const req = new Request("https://example.supabase.co/functions/v1/apex-github-batch-worker", { method: "POST" });
    const decision = authMod.authorizePrivilegedWorkerRequest(req, { env: getEnv });
    assert.equal(decision.ok, false);
    assert.equal(decision.status, 401);
    assert.equal(decision.error, "worker_auth_required");
  }

  // Missing credentials even with allowlisted origin -> 401 worker_auth_required
  {
    const req = new Request("https://example.supabase.co/functions/v1/apex-github-batch-worker", {
      method: "POST",
      headers: { "x-glaciereq-worker-origin": "apex-scheduler" },
    });
    const decision = authMod.authorizePrivilegedWorkerRequest(req, { env: getEnv });
    assert.equal(decision.ok, false);
    assert.equal(decision.status, 401);
    assert.equal(decision.error, "worker_auth_required");
  }

  // 2. Anonymous JWT / SUPABASE_ANON_KEY / sb_publishable_* -> 403 worker_auth_forbidden_role
  for (const headers of [
    { apikey: ANON_KEY, authorization: `Bearer ${ANON_KEY}`, "x-glaciereq-worker-origin": "apex-scheduler" },
    { apikey: "sb_publishable_live_12345", "x-glaciereq-worker-origin": "apex-scheduler" },
    { authorization: `Bearer ${makeJwt({ role: "anon" })}`, apikey: makeJwt({ role: "anon" }) },
  ]) {
    const req = new Request("https://example.supabase.co/functions/v1/apex-github-batch-worker", {
      method: "POST",
      headers,
    });
    const decision = authMod.authorizePrivilegedWorkerRequest(req, { env: getEnv });
    assert.equal(decision.ok, false);
    assert.equal(decision.status, 403);
    assert.equal(decision.error, "worker_auth_forbidden_role");
  }

  // 3. Ordinary authenticated user JWT -> 403 worker_auth_forbidden
  {
    const req = new Request("https://example.supabase.co/functions/v1/apex-github-batch-worker", {
      method: "POST",
      headers: {
        apikey: ANON_KEY,
        authorization: `Bearer ${USER_JWT}`,
        "x-glaciereq-worker-origin": "apex-control-plane",
      },
    });
    // Wait: if apikey is ANON_KEY and bearer is USER_JWT, let's check both pure USER_JWT and mixed!
    const pureUserReq = new Request("https://example.supabase.co/functions/v1/apex-github-batch-worker", {
      method: "POST",
      headers: {
        apikey: USER_JWT,
        authorization: `Bearer ${USER_JWT}`,
        "x-glaciereq-worker-origin": "apex-control-plane",
      },
    });
    const decision = authMod.authorizePrivilegedWorkerRequest(pureUserReq, { env: getEnv });
    assert.equal(decision.ok, false);
    assert.equal(decision.status, 403);
    assert.equal(decision.error, "worker_auth_forbidden");

    const mixedDecision = authMod.authorizePrivilegedWorkerRequest(req, { env: getEnv });
    assert.equal(mixedDecision.ok, false);
    assert.equal(mixedDecision.status, 403);
  }

  // 4. Wrong secret -> 403 worker_auth_forbidden
  for (const headers of [
    {
      apikey: "wrong-service-key",
      authorization: "Bearer wrong-service-key",
      "x-glaciereq-worker-origin": "apex-scheduler",
    },
    {
      "x-apex-worker-auth": "wrong-worker-secret",
      "x-glaciereq-worker-origin": "apex-scheduler",
    },
  ]) {
    const req = new Request("https://example.supabase.co/functions/v1/apex-github-batch-worker", {
      method: "POST",
      headers,
    });
    const decision = authMod.authorizePrivilegedWorkerRequest(req, { env: getEnv });
    assert.equal(decision.ok, false);
    assert.equal(decision.status, 403);
    assert.equal(decision.error, "worker_auth_forbidden");
  }

  // 5. Missing or unallowlisted internal origin header -> 403 worker_auth_forbidden
  for (const headers of [
    { apikey: SERVICE_KEY, authorization: `Bearer ${SERVICE_KEY}` },
    { "x-apex-worker-auth": WORKER_SECRET },
    {
      "x-apex-worker-auth": WORKER_SECRET,
      "x-glaciereq-worker-origin": "external-browser-client",
    },
  ]) {
    const req = new Request("https://example.supabase.co/functions/v1/apex-github-batch-worker", {
      method: "POST",
      headers,
    });
    const decision = authMod.authorizePrivilegedWorkerRequest(req, { env: getEnv });
    assert.equal(decision.ok, false);
    assert.equal(decision.status, 403);
    assert.equal(decision.error, "worker_auth_forbidden");
  }

  // 6. Valid scoped worker secret AND valid rotated service key with allowlisted origin -> ok: true
  for (const headers of [
    {
      "x-apex-worker-auth": WORKER_SECRET,
      "x-glaciereq-worker-origin": "apex-scheduler",
    },
    {
      apikey: ROTATED_KEY,
      authorization: `Bearer ${ROTATED_KEY}`,
      "x-glaciereq-origin": "apex-github-webhook-wake",
    },
  ]) {
    const req = new Request("https://example.supabase.co/functions/v1/apex-github-batch-worker", {
      method: "POST",
      headers,
    });
    const decision = authMod.authorizePrivilegedWorkerRequest(req, { env: getEnv });
    assert.equal(decision.ok, true);
  }
});

test("apex-github-batch-worker and apex-github-webhook-worker reject unauthorized callers BEFORE reading body or touching admin client", async () => {
  const baseEnv = {
    SUPABASE_URL: "https://example.supabase.co",
    SUPABASE_SERVICE_ROLE_KEY: SERVICE_KEY,
    SUPABASE_SECRET_KEYS: JSON.stringify({ primary: SERVICE_KEY, rotated: ROTATED_KEY }),
    SUPABASE_ANON_KEY: ANON_KEY,
    APEX_INTERNAL_WORKER_SECRET: WORKER_SECRET,
  };

  for (const workerPath of [
    "supabase/functions/apex-github-batch-worker/index.ts",
    "supabase/functions/apex-github-webhook-worker/index.ts",
  ]) {
    const handler = await loadWorkerModule(workerPath, baseEnv);

    const unauthorizedCases: Array<{
      name: string;
      headers: Record<string, string>;
      expectedStatus: number;
      expectedError: string;
    }> = [
      { name: "missing headers", headers: {}, expectedStatus: 401, expectedError: "worker_auth_required" },
      {
        name: "anon key",
        headers: {
          apikey: ANON_KEY,
          authorization: `Bearer ${ANON_KEY}`,
          "x-glaciereq-worker-origin": "apex-scheduler",
        },
        expectedStatus: 403,
        expectedError: "worker_auth_forbidden_role",
      },
      {
        name: "authenticated user jwt",
        headers: {
          apikey: USER_JWT,
          authorization: `Bearer ${USER_JWT}`,
          "x-glaciereq-worker-origin": "apex-scheduler",
        },
        expectedStatus: 403,
        expectedError: "worker_auth_forbidden",
      },
      {
        name: "wrong secret",
        headers: {
          "x-apex-worker-auth": "wrong-secret",
          "x-glaciereq-worker-origin": "apex-scheduler",
        },
        expectedStatus: 403,
        expectedError: "worker_auth_forbidden",
      },
      {
        name: "missing origin",
        headers: {
          apikey: SERVICE_KEY,
          authorization: `Bearer ${SERVICE_KEY}`,
        },
        expectedStatus: 403,
        expectedError: "worker_auth_forbidden",
      },
    ];

    for (const tc of unauthorizedCases) {
      rpcCalls = [];
      fromCalls = [];
      const { req, wasBodyRead } = unconsumedJsonRequest("https://example.supabase.co/functions/v1/worker", tc.headers);
      const res = await handler(req);
      assert.equal(res.status, tc.expectedStatus, `${workerPath} [${tc.name}] status`);
      const body = (await res.json()) as Record<string, unknown>;
      assert.equal(body.ok, false);
      assert.equal(body.error, tc.expectedError, `${workerPath} [${tc.name}] error`);
      assert.equal(wasBodyRead(), false, `${workerPath} [${tc.name}] must NOT read request body before auth`);
      assert.equal(rpcCalls.length, 0, `${workerPath} [${tc.name}] must NOT call admin.rpc before auth`);
      assert.equal(fromCalls.length, 0, `${workerPath} [${tc.name}] must NOT call admin.from before auth`);
    }
  }
});

test("valid internal worker dispatch succeeds across webhook-wake -> webhook-worker and batch-worker self-continuation", async () => {
  const baseEnv = {
    SUPABASE_URL: "https://example.supabase.co",
    SUPABASE_SERVICE_ROLE_KEY: SERVICE_KEY,
    SUPABASE_ANON_KEY: ANON_KEY,
    APEX_INTERNAL_WORKER_SECRET: WORKER_SECRET,
  };

  const webhookWorkerHandler = await loadWorkerModule(
    "supabase/functions/apex-github-webhook-worker/index.ts",
    baseEnv,
  );
  const webhookWakeHandler = await loadWorkerModule(
    "supabase/functions/apex-github-webhook-wake/index.ts",
    baseEnv,
  );
  const batchWorkerHandler = await loadWorkerModule(
    "supabase/functions/apex-github-batch-worker/index.ts",
    baseEnv,
  );

  // Route outbound fetch calls from wake -> webhook-worker and batch-worker -> batch-worker!
  const originalFetch = globalThis.fetch;
  const forwardedRequests: Array<{ url: string; headers: Headers }> = [];
  globalThis.fetch = async (input: string | URL | Request, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(input, init);
    forwardedRequests.push({ url: req.url, headers: new Headers(req.headers) });
    if (req.url.endsWith("/functions/v1/apex-github-webhook-worker")) {
      return await webhookWorkerHandler(req);
    }
    if (req.url.endsWith("/functions/v1/apex-github-batch-worker")) {
      // On self-continuation hop, clear pending count so recursion terminates after 1 hop
      (globalThis as Record<string, unknown>).__apexTestPendingCount = 0;
      return await batchWorkerHandler(req);
    }
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };

  try {
    // 1. Test webhook-wake -> webhook-worker end-to-end
    rpcCalls = [];
    rpcImpl = async (fn, args) => {
      if (fn === "validate_github_worker_wake_secret_v1") {
        return { data: args.p_secret === "valid-vault-wake-secret", error: null };
      }
      if (fn === "claim_github_webhook_events_v1") {
        return { data: [], error: null };
      }
      return { data: null, error: null };
    };

    const wakeRes = await webhookWakeHandler(
      new Request("https://example.supabase.co/functions/v1/apex-github-webhook-wake", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-apex-worker-secret": "valid-vault-wake-secret",
        },
        body: JSON.stringify({ limit: 7 }),
      }),
    );
    assert.equal(wakeRes.status, 200);
    const wakeBody = (await wakeRes.json()) as Record<string, unknown>;
    assert.equal(wakeBody.ok, true);
    assert.equal(wakeBody.worker_status, 200);
    assert.ok(
      forwardedRequests.some(
        (r) =>
          r.url.endsWith("/functions/v1/apex-github-webhook-worker") &&
          r.headers.get("x-glaciereq-worker-origin") === "apex-github-webhook-wake" &&
          r.headers.get("x-apex-worker-auth") === WORKER_SECRET,
      ),
      "webhook-wake must forward internal worker origin and scoped worker auth headers",
    );

    // 2. Test batch-worker valid execution + self-continuation headers
    forwardedRequests.length = 0;
    waitUntilPromises = [];
    (globalThis as Record<string, unknown>).__apexTestPendingCount = 2;
    rpcImpl = async (fn) => {
      if (fn === "acquire_github_batch_dispatch_lease_v2") {
        return { data: { acquired: true }, error: null };
      }
      if (fn === "claim_github_batch_items_v2") {
        return { data: [], error: null };
      }
      return { data: { ok: true }, error: null };
    };

    const batchRes = await batchWorkerHandler(
      new Request("https://example.supabase.co/functions/v1/apex-github-batch-worker", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-glaciereq-worker-origin": "apex-scheduler",
          "x-apex-worker-auth": WORKER_SECRET,
        },
        body: JSON.stringify({ limit: 16, max_cycles: 2 }),
      }),
    );
    assert.equal(batchRes.status, 200);
    const batchBody = (await batchRes.json()) as Record<string, unknown>;
    assert.equal(batchBody.ok, true);
    assert.equal(waitUntilPromises.length, 1, "Expected self-continuation waitUntil to be scheduled");
    await Promise.all(waitUntilPromises);

    assert.equal(forwardedRequests.length, 1);
    assert.equal(
      forwardedRequests[0].headers.get("x-glaciereq-worker-origin"),
      "apex-github-batch-worker",
    );
    assert.equal(forwardedRequests[0].headers.get("x-apex-worker-auth"), WORKER_SECRET);
  } finally {
    globalThis.fetch = originalFetch;
    (globalThis as Record<string, unknown>).__apexTestPendingCount = 0;
  }
});
