import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const forbiddenVerifierRefs = new Set([
  "frontier_receipt",
  "execution_receipt",
  "assistant_summary",
  "memory_projection",
  "manifest",
  "checkpoint",
]);

function json(status: number, body: Record<string, unknown>) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function stringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(nonEmptyString);
}

function sameSet(a: string[], b: string[]): boolean {
  if (new Set(a).size !== a.length || new Set(b).size !== b.length) return false;
  const left = [...a].sort();
  const right = [...b].sort();
  return left.length === right.length && left.every((v, i) => v === right[i]);
}

async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return "sha256:" + [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function allowedEvidenceUrl(raw: string): URL {
  const url = new URL(raw);
  if (url.protocol !== "https:") throw new Error("evidence_ref must use https");
  const allowed = new Set([
    "api.github.com",
    "raw.githubusercontent.com",
    "github.com",
  ]);
  if (!allowed.has(url.hostname)) {
    throw new Error("evidence_ref host is not an independently readable provider");
  }
  return url;
}

function observation(
  verificationComplete: boolean,
  status: string,
  errors: string[] = [],
  extra: Record<string, unknown> = {},
) {
  return json(200, {
    ok: true,
    status,
    verification_complete: verificationComplete,
    authority_effect: "none",
    execution_authorized_by_this_function: false,
    execution_blocked_by_this_function: false,
    errors,
    ...extra,
  });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json(405, { ok: false, status: "method_not_allowed" });

  let payload: Record<string, unknown>;
  try {
    payload = await req.json();
  } catch {
    return observation(false, "frontier_observation_unavailable", ["invalid_json"]);
  }

  const frontier = payload.frontier_authority;
  if (!frontier || typeof frontier !== "object" || Array.isArray(frontier)) {
    return observation(false, "frontier_observation_incomplete", [
      "frontier_authority observation was not supplied",
    ]);
  }
  const row = frontier as Record<string, unknown>;
  const frontierId = row.frontier_id;
  const operationClass = row.operation_class;
  const target = row.target;
  const frontierAction = row.frontier_action;
  const executionClaimIds = row.execution_claim_ids ?? [];
  const enumeration = row.dependency_enumeration;

  const errors: string[] = [];
  for (const [name, value] of Object.entries({ frontier_id: frontierId, operation_class: operationClass, target, frontier_action: frontierAction })) {
    if (!nonEmptyString(value)) errors.push(`${name} must be non-empty`);
  }
  if (!stringArray(executionClaimIds)) {
    errors.push("execution_claim_ids must be an array of non-empty strings");
  } else if (new Set(executionClaimIds).size !== executionClaimIds.length) {
    errors.push("execution_claim_ids must be unique");
  }
  if (!enumeration || typeof enumeration !== "object" || Array.isArray(enumeration)) {
    errors.push("dependency_enumeration must be an object");
  }
  if (errors.length) return observation(false, "frontier_observation_incomplete", errors);

  const enumRow = enumeration as Record<string, unknown>;
  const evidenceRef = enumRow.evidence_ref;
  const evidenceSha256 = enumRow.evidence_sha256;
  if (!nonEmptyString(evidenceRef) || !nonEmptyString(evidenceSha256)) {
    return observation(false, "frontier_observation_incomplete", [
      "dependency_enumeration requires evidence_ref and evidence_sha256",
    ]);
  }

  let evidenceBytes: Uint8Array;
  try {
    const url = allowedEvidenceUrl(evidenceRef);
    const response = await fetch(url, {
      redirect: "follow",
      headers: { accept: "application/json, text/plain;q=0.9" },
    });
    if (!response.ok) {
      return observation(false, "frontier_readback_unresolved", [
        `provider readback returned HTTP ${response.status}`,
      ]);
    }
    evidenceBytes = new Uint8Array(await response.arrayBuffer());
  } catch (error) {
    return observation(false, "frontier_readback_unresolved", [
      error instanceof Error ? error.message : "provider readback failed",
    ]);
  }

  const resolvedHash = await sha256(evidenceBytes);
  if (resolvedHash !== evidenceSha256) {
    return observation(false, "frontier_observation_mismatch", [
      "evidence_sha256 does not match independently resolved provider bytes",
    ], { resolved_evidence_sha256: resolvedHash });
  }

  let evidence: Record<string, unknown>;
  try {
    evidence = JSON.parse(new TextDecoder().decode(evidenceBytes));
  } catch {
    return observation(false, "frontier_observation_mismatch", [
      "resolved dependency enumeration evidence must be JSON",
    ], { resolved_evidence_sha256: resolvedHash });
  }

  const expected: Record<string, unknown> = {
    frontier_id: frontierId,
    verdict: "complete",
    operation_class: operationClass,
    target,
    frontier_action: frontierAction,
  };
  for (const [key, value] of Object.entries(expected)) {
    if (evidence[key] !== value) errors.push(`evidence.${key} does not match frontier`);
  }

  const requiredIds = evidence.required_execution_claim_ids;
  if (!stringArray(requiredIds)) {
    errors.push("evidence.required_execution_claim_ids must be an array of non-empty strings");
  } else if (!sameSet(requiredIds, executionClaimIds as string[])) {
    errors.push("declared execution_claim_ids are incomplete, duplicated, or substituted");
  }

  const verifierRef = evidence.verifier_ref;
  if (!nonEmptyString(verifierRef)) {
    errors.push("evidence.verifier_ref must be non-empty");
  } else if (forbiddenVerifierRefs.has(verifierRef)) {
    errors.push("evidence.verifier_ref cannot self-certify dependency completeness");
  }

  if (errors.length) {
    return observation(false, "frontier_observation_mismatch", errors, {
      frontier_id: frontierId,
      resolved_evidence_sha256: resolvedHash,
    });
  }

  return observation(true, "frontier_observed_complete", [], {
    frontier_id: frontierId,
    execution_claim_ids: executionClaimIds,
    provider_readback: true,
    resolved_evidence_sha256: resolvedHash,
  });
});
