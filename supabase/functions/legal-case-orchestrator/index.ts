import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

const json = (body: unknown, status = 200) =>
  Response.json(body, { status, headers: { "cache-control": "no-store" } });

async function resolveMatter(matterKey?: string, matterId?: string) {
  if (matterId) {
    const { data, error } = await supabase
      .from("continuity_matters_v1")
      .select("matter_id,matter_key,title,status,priority,metadata")
      .eq("matter_id", matterId)
      .maybeSingle();
    if (error) throw error;
    if (!data) throw new Error("matter not found");
    return data;
  }
  if (!matterKey) throw new Error("matter_key or matter_id is required");
  const { data: resolved, error: resolveError } = await supabase.rpc(
    "legal_control_resolve_matter_id_v1",
    { p_key: matterKey },
  );
  if (resolveError) throw resolveError;
  const { data, error } = await supabase
    .from("continuity_matters_v1")
    .select("matter_id,matter_key,title,status,priority,metadata")
    .eq("matter_id", resolved)
    .single();
  if (error) throw error;
  return data;
}

async function controlSnapshot(matterKey?: string, matterId?: string) {
  const matter = await resolveMatter(matterKey, matterId);
  const { data: control, error: controlError } = await supabase
    .from("legal_control_dashboard_v1")
    .select("*")
    .eq("matter_id", matter.matter_id)
    .maybeSingle();
  if (controlError) throw controlError;

  const [{ data: commitments, error: cErr }, { data: attention, error: aErr }, { data: journal, error: jErr }] =
    await Promise.all([
      supabase
        .from("continuity_commitments_v1")
        .select("commitment_id,commitment_type,title,due_at,due_precision,status,priority,owner,metadata")
        .eq("matter_id", matter.matter_id)
        .in("status", ["open", "in_progress", "waiting"])
        .order("priority", { ascending: false })
        .order("due_at", { ascending: true, nullsFirst: false }),
      supabase
        .from("continuity_attention_queue_v1")
        .select("*")
        .eq("matter_id", matter.matter_id)
        .order("priority", { ascending: false })
        .order("attention_at", { ascending: true }),
      supabase
        .from("legal_control_events_v1")
        .select("event_id,event_key,event_type,occurred_at,ingested_at,source_system,source_ref,provider_receipt,content_hash,created_by")
        .eq("matter_id", matter.matter_id)
        .order("ingested_at", { ascending: false })
        .limit(50),
    ]);
  if (cErr) throw cErr;
  if (aErr) throw aErr;
  if (jErr) throw jErr;

  return {
    matter,
    control,
    commitments: commitments ?? [],
    attention: attention ?? [],
    journal: journal ?? [],
  };
}

async function sha256Hex(value: string) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req: Request) => {
  try {
    const url = new URL(req.url);

    if (req.method === "GET") {
      const matterKey = url.searchParams.get("matter_key") ?? undefined;
      const matterId = url.searchParams.get("matter_id") ?? undefined;
      if (!matterKey && !matterId) {
        const { data, error } = await supabase
          .from("legal_control_dashboard_v1")
          .select("matter_id,matter_key,stable_alias,title,priority,execution_state,state_version,last_provider_ref,next_action,next_due_at,attention_count,journal_revision_count,open_deadletters,open_commitments,control_updated_at")
          .order("priority", { ascending: false })
          .limit(100);
        if (error) throw error;
        return json({ ok: true, service: "legal-case-orchestrator-v3", dashboard: data ?? [] });
      }
      return json({ ok: true, service: "legal-case-orchestrator-v3", ...(await controlSnapshot(matterKey, matterId)) });
    }

    if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });

    const body = await req.json();
    const operation = body.operation ?? "snapshot";
    const matter = await resolveMatter(body.matter_key, body.matter_id);

    if (operation === "snapshot") {
      return json({ ok: true, service: "legal-case-orchestrator-v3", ...(await controlSnapshot(matter.matter_key, matter.matter_id)) });
    }

    if (operation === "record_action") {
      const a = body.action ?? {};
      if (!a.provider_ref) return json({ ok: false, error: "provider_ref is required for record_action" }, 400);
      const { data, error } = await supabase.rpc("legal_record_external_action_v1", {
        p_matter_id: matter.matter_id,
        p_packet_id: a.packet_id,
        p_idempotency_key: a.idempotency_key,
        p_channel: a.channel,
        p_target: a.target,
        p_intended_action: a.intended_action,
        p_provider_ref: a.provider_ref,
        p_receipt_type: a.receipt_type,
        p_outcome: a.outcome,
        p_event_type: a.event_type,
        p_occurred_at: a.occurred_at,
        p_subject: a.subject ?? null,
        p_summary: a.summary ?? null,
        p_detail: {
          ...(a.detail ?? {}),
          source_system: a.source_system ?? a.channel,
          orchestrator: "legal-case-orchestrator-v3",
        },
      });
      if (error) throw error;
      return json({ ok: true, receipt: data, ...(await controlSnapshot(matter.matter_key, matter.matter_id)) });
    }

    if (operation === "record_event") {
      const e = body.event ?? {};
      if (!e.event_type || !e.occurred_at || !e.source_system || !e.source_ref) {
        return json({ ok: false, error: "event_type, occurred_at, source_system, source_ref are required" }, 400);
      }
      const { data, error } = await supabase
        .from("continuity_events_v1")
        .upsert({
          matter_id: matter.matter_id,
          event_type: e.event_type,
          occurred_at: e.occurred_at,
          source_system: e.source_system,
          source_ref: e.source_ref,
          subject: e.subject ?? null,
          summary: e.summary ?? null,
          delivery_status: e.delivery_status ?? null,
          metadata: {
            ...(e.metadata ?? {}),
            orchestrator: "legal-case-orchestrator-v3",
          },
        }, { onConflict: "source_ref" })
        .select("event_id")
        .single();
      if (error) throw error;
      return json({ ok: true, event_id: data.event_id, ...(await controlSnapshot(matter.matter_key, matter.matter_id)) });
    }

    if (operation === "transition") {
      const t = body.transition ?? {};
      if (!t.to_state || !t.transition_key) {
        return json({ ok: false, error: "to_state and transition_key are required" }, 400);
      }
      const { data, error } = await supabase.rpc("legal_execution_transition_v1", {
        p_matter_id: matter.matter_id,
        p_to_state: t.to_state,
        p_transition_key: t.transition_key,
        p_event_id: t.event_id ?? null,
        p_action_id: t.action_id ?? null,
        p_receipt_id: t.receipt_id ?? null,
        p_provider_ref: t.provider_ref ?? null,
        p_next_action: t.next_action ?? null,
        p_next_due_at: t.next_due_at ?? null,
        p_error: t.error ?? {},
        p_detail: { ...(t.detail ?? {}), orchestrator: "legal-case-orchestrator-v3" },
      });
      if (error) throw error;
      return json({ ok: true, state: data, ...(await controlSnapshot(matter.matter_key, matter.matter_id)) });
    }

    if (operation === "prepare_action") {
      const a = body.action ?? {};
      if (!a.idempotency_key || !a.channel || !a.target || !a.intended_action) {
        return json({ ok: false, error: "idempotency_key, channel, target, intended_action are required" }, 400);
      }
      if (!["email", "phone", "calendar", "other"].includes(a.channel)) {
        return json({ ok: false, error: "channel must be email, phone, calendar, or other" }, 400);
      }
      const context = {
        matter_id: matter.matter_id,
        matter_key: matter.matter_key,
        stable_alias: matter.metadata?.stable_alias ?? null,
        action: {
          channel: a.channel,
          target: a.target,
          intended_action: a.intended_action,
        },
        context: a.context ?? {},
        prepared_by: "legal-case-orchestrator-v3",
      };
      const snapshotHash = await sha256Hex(JSON.stringify(context));
      const expiresAt = a.expires_at ?? new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

      const { data: packet, error: pErr } = await supabase
        .from("continuity_context_packets_v1")
        .insert({
          matter_id: matter.matter_id,
          action_channel: a.channel,
          action_purpose: a.intended_action,
          context_json: context,
          snapshot_hash: snapshotHash,
          expires_at: expiresAt,
          created_by: "legal-case-orchestrator-v3",
        })
        .select("packet_id")
        .single();
      if (pErr) throw pErr;

      const { data: action, error: aErr } = await supabase
        .from("continuity_outbound_actions_v1")
        .upsert({
          idempotency_key: a.idempotency_key,
          packet_id: packet.packet_id,
          matter_id: matter.matter_id,
          channel: a.channel,
          target: a.target,
          intended_action: a.intended_action,
          status: "planned",
          requires_operator_approval: a.requires_operator_approval ?? true,
          not_before: a.not_before ?? null,
          source_commitment_id: a.source_commitment_id ?? null,
          execution_guard: {
            no_auto_send: true,
            provider_receipt_required: true,
            prepared_by: "legal-case-orchestrator-v3",
          },
          result_json: {},
          error_json: {},
        }, { onConflict: "idempotency_key" })
        .select("*")
        .single();
      if (aErr) throw aErr;

      return json({ ok: true, packet_id: packet.packet_id, action, ...(await controlSnapshot(matter.matter_key, matter.matter_id)) });
    }

    if (operation === "approve_action") {
      if (body.operator_approved !== true) {
        return json({ ok: false, error: "explicit operator_approved=true is required" }, 400);
      }
      const actionKey = body.action_id;
      const idempotencyKey = body.idempotency_key;
      if (!actionKey && !idempotencyKey) {
        return json({ ok: false, error: "action_id or idempotency_key is required" }, 400);
      }
      let q = supabase
        .from("continuity_outbound_actions_v1")
        .update({
          status: "approved",
          approved_at: new Date().toISOString(),
          approved_by: body.approved_by ?? "operator",
          execution_guard: { no_auto_send: true, approval_recorded_by: "legal-case-orchestrator-v3" },
        })
        .eq("matter_id", matter.matter_id);
      q = actionKey ? q.eq("action_id", actionKey) : q.eq("idempotency_key", idempotencyKey);
      const { data, error } = await q.select("*").single();
      if (error) throw error;
      return json({ ok: true, action: data, note: "Approval recorded. This orchestrator does not send or call.", ...(await controlSnapshot(matter.matter_key, matter.matter_id)) });
    }

    return json({ ok: false, error: "unsupported operation", operation }, 400);
  } catch (error) {
    return json({ ok: false, service: "legal-case-orchestrator-v3", error: error instanceof Error ? error.message : String(error) }, 500);
  }
});
