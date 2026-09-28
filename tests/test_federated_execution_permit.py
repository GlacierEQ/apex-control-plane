from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "db" / "migrations" / "20260909150221_continuity_federated_execution_permit_v1.sql"
HARDENING = ROOT / "db" / "migrations" / "20260911151839_harden_federated_execution_permit_validation_v2.sql"


def sql(path: Path) -> str:
    return path.read_text()


def test_surviving_permit_migration_contains_required_harvested_substrate():
    source = sql(BASE)
    for marker in (
        "create table if not exists public.continuity_case_execution_plans_v1",
        "create table if not exists public.continuity_case_execution_plan_actions_v1",
        "add column if not exists execution_guard",
        "add column if not exists plan_action_id",
        "continuity_case_plan_gate_v1",
        "continuity_preflight_outbound_v3",
        "continuity_bind_outbound_to_plan_v1",
        "continuity_start_outbound_v1",
    ):
        assert marker in source
    assert "unique(action_id,packet_snapshot_hash,global_frontier_hash,primary_awareness_receipt_ref)" not in source


def test_permit_binds_both_execution_domains():
    source = sql(BASE) + "\n" + sql(HARDENING)
    assert "backend_execution_guard_not_ready" in source
    assert "active_plan_gate_not_authorized" in source
    assert "global_frontier_hash_mismatch" in source
    assert "primary_awareness_receipt_required" in source
    assert "primary_awareness_older_than_global_frontier_checkpoint" in source
    assert "continuity_case_plan_gate_v1(a.action_id)" in source


def test_primary_awareness_must_be_checkpointed_not_caller_asserted():
    source = sql(HARDENING)
    assert "primary_awareness_receipt_ref" in source
    assert "primary_awareness_source_watermark_at" in source
    assert "primary_awareness_receipt_not_checkpointed" in source
    assert "primary_awareness_receipt_mismatch" in source
    assert "primary_awareness_watermark_mismatch" in source
    assert "p.metadata->>'primary_awareness_receipt_ref'" in source
    assert "peer.metadata->>'primary_awareness_receipt_ref'" in source


def test_permit_lifetime_is_capped_by_context_packet():
    source = sql(HARDENING)
    assert "p_ttl_seconds integer default 300" in source
    assert "least(coalesce(p_ttl_seconds,300),600)" in source
    assert "least(cp.expires_at,now()+make_interval(secs=>v_ttl))" in source


def test_validation_rechecks_current_plan_packet_frontier_and_awareness():
    source = sql(HARDENING)
    assert "continuity_case_plan_gate_v1(a.action_id)" in source
    assert "context_packet_expired" in source
    assert "context_packet_snapshot_changed" in source
    assert "cp.snapshot_hash is distinct from pmt.packet_snapshot_hash" in source
    assert "where packet_id=pmt.packet_id" in source
    assert "for share" in source
    assert "pmt.primary_awareness_source_watermark_at < peer.last_watermark_at" in source


def test_expired_or_consumed_permit_identity_can_issue_new_generation():
    source = sql(BASE) + "\n" + sql(HARDENING)
    assert "pmt.expires_at>now()" in source
    assert "receipt_type in ('CONSUMED','REVOKED')" in source
    assert "insert into public.continuity_federated_execution_permits_v1" in source
    assert "unique(action_id,packet_snapshot_hash,global_frontier_hash,primary_awareness_receipt_ref)" not in source


def test_provider_dispatch_permit_is_atomically_single_use():
    source = sql(BASE) + "\n" + sql(HARDENING)
    assert "receipt_type in ('ISSUED','VALIDATED','CONSUMED'" in source
    assert "permit_consumed" in source
    assert "PROVIDER_DISPATCH_STARTED" in source
    assert "continuity_federated_execution_permit_receipts_v1 is append-only" in source
    assert "where permit_id=p_permit_id\n  for update" in source
    assert "returning receipt_id into v_receipt" in source
    assert "if v_receipt is null then" in source
    assert "'consumption_receipt_id',v_receipt" in source


def test_staged_binding_fails_closed_until_awareness_projection_exists():
    source = sql(HARDENING)
    assert "primary_awareness_receipt_not_checkpointed" in source
