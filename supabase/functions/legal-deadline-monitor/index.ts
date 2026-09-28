import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

Deno.serve(async (_req: Request) => {
  const started = Date.now();
  try {
    const now = new Date();
    const in24h = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    const in7d = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);

    const { data: commitments, error } = await supabase
      .from("continuity_commitments_v1")
      .select("commitment_id,matter_id,commitment_type,title,due_at,due_precision,status,priority,owner,evidence_required,metadata")
      .in("status", ["open","in_progress","waiting"])
      .not("due_at", "is", null)
      .order("due_at", { ascending: true });

    if (error) throw error;

    const rows = commitments ?? [];
    const overdue = rows.filter((x) => new Date(x.due_at) < now);
    const due24h = rows.filter((x) => {
      const d = new Date(x.due_at);
      return d >= now && d <= in24h;
    });
    const due7d = rows.filter((x) => {
      const d = new Date(x.due_at);
      return d > in24h && d <= in7d;
    });

    const status = overdue.length > 0 ? "critical" : due24h.length > 0 ? "warning" : "healthy";
    const details = {
      source: "legal-deadline-monitor-v2",
      checked_at: now.toISOString(),
      contract: "continuity_commitments_v1 is the deadline source of truth; this worker does not invent or infer legal limitation periods.",
      overdue,
      due_24h: due24h,
      due_7d: due7d,
      counts: {
        active_with_due_at: rows.length,
        overdue: overdue.length,
        due_24h: due24h.length,
        due_7d: due7d.length,
      },
    };

    await supabase.from("system_health").insert({
      service: "legal-deadline-monitor",
      status,
      latency_ms: Date.now() - started,
      details,
    });

    return Response.json({ ok: true, status, ...details });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await supabase.from("system_health").insert({
      service: "legal-deadline-monitor",
      status: "error",
      latency_ms: Date.now() - started,
      details: { source: "legal-deadline-monitor-v2", error: message, checked_at: new Date().toISOString() },
    });
    return Response.json({ ok: false, error: message }, { status: 500 });
  }
});
