from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db" / "migrations" / "20260909150221_continuity_federated_execution_permit_v1.sql"


def sql() -> str:
    return MIGRATION.read_text()


def test_permit_binds_both_execution_domains():
    source = sql()
    assert "backend_execution_guard_not_ready" in source
    assert "active_plan_gate_not_authorized" in source
    assert "global_frontier_hash_mismatch" in source
    assert "primary_awareness_receipt_required" in source
    assert "primary_awareness_older_than_global_frontier_checkpoint" in source


def test_permit_is_short_lived_and_action_specific():
    source = sql()
    assert "p_ttl_seconds integer default 300" in source
    assert "least(coalesce(p_ttl_seconds,300),600)" in source
    assert "permit_action_mismatch" in source
    assert "plan_action_changed" in source
    assert "packet_changed" in source
    assert "global_frontier_advanced_or_changed" in source


def test_provider_dispatch_permit_is_single_use():
    source = sql()
    assert "receipt_type in ('ISSUED','VALIDATED','CONSUMED'" in source
    assert "permit_consumed" in source
    assert "PROVIDER_DISPATCH_STARTED" in source
    assert "continuity_federated_execution_permit_receipts_v1 is append-only" in source


def test_staged_binding_does_not_silently_break_existing_adapters():
    source = sql()
    assert "'mode','staged_adapter_binding'" in source
    assert "'provider_adapter_enforcement','pending_explicit_adapter_binding'" in source
    assert "Provider adapters may claim globally current execution only" in source
