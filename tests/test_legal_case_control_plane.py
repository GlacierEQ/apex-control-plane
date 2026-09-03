from __future__ import annotations

import json
from pathlib import Path

import pytest

from legal_case_control_plane import (
    LegalCaseControlPlaneError,
    load_binding,
    normalize_casebuilder_health,
)


def _healthy_snapshot() -> dict:
    return {
        "schema": "casebuilder4000.control-plane-health.v1",
        "observed_at": "2026-09-02T22:00:00-10:00",
        "status": "healthy",
        "events": {"count": 10, "latest_at": "2026-09-02T22:00:00-10:00"},
        "work": {
            "counts": {"succeeded": 10},
            "backlog": 0,
            "inflight": 0,
            "failed": 0,
        },
        "workers": [
            {
                "worker_id": "casebuilder-runtime",
                "worker_type": "casebuilder-continuous-runtime",
                "status": "online",
                "last_heartbeat_at": "2026-09-02T22:00:00-10:00",
                "stale": False,
                "current_work_id": None,
                "capabilities": ["VERIFY_CASE"],
            }
        ],
        "latest_checkpoint": {
            "case_id": "CASE-1",
            "stage": "case.build.completed",
        },
    }


def test_repository_binding_loads_and_preserves_authority_boundaries():
    root = Path(__file__).resolve().parents[1]
    binding = load_binding(
        root / "config" / "legal_case_control_plane.json"
    )
    assert (
        binding["source_of_case_truth"]["repository"]
        == "GlacierEQ/Casebuilder4000"
    )
    assert (
        binding["estate_registry"]["preserves_matter_identity"]
        is True
    )
    assert (
        "APEX does not become case truth authority"
        in binding["anti_collapse"]
    )


def test_healthy_casebuilder_projects_healthy_without_truth_mutation():
    result = normalize_casebuilder_health(
        _healthy_snapshot(),
        revision_chain_valid=True,
        evidence_chain_valid=True,
        build_verified=True,
        truth_acceptance="accepted",
    )
    assert result["status"] == "healthy"
    assert result["truth_class_mutated"] is False
    assert result["blocked_reasons"] == []


def test_integrity_failure_projects_blocked():
    result = normalize_casebuilder_health(
        _healthy_snapshot(),
        revision_chain_valid=False,
        evidence_chain_valid=True,
        build_verified=True,
        truth_acceptance="accepted",
    )
    assert result["status"] == "blocked"
    assert "case_revision_chain_invalid" in result["blocked_reasons"]


def test_historical_or_current_failed_work_degrades_not_truth_rewrites():
    snapshot = _healthy_snapshot()
    snapshot["status"] = "degraded"
    snapshot["work"]["failed"] = 2
    result = normalize_casebuilder_health(
        snapshot,
        revision_chain_valid=True,
        evidence_chain_valid=True,
        build_verified=True,
        truth_acceptance="accepted",
    )
    assert result["status"] == "degraded"
    assert "terminal_failed_work" in result["degraded_reasons"]
    assert result["truth_class_mutated"] is False


def test_backlog_without_live_worker_degrades():
    snapshot = _healthy_snapshot()
    snapshot["work"]["backlog"] = 3
    snapshot["workers"] = []
    result = normalize_casebuilder_health(snapshot)
    assert result["status"] == "degraded"
    assert "backlog_without_live_worker" in result["degraded_reasons"]


def test_wrong_health_schema_is_rejected():
    snapshot = _healthy_snapshot()
    snapshot["schema"] = "wrong"
    with pytest.raises(LegalCaseControlPlaneError):
        normalize_casebuilder_health(snapshot)


def test_binding_missing_truth_boundary_is_rejected(tmp_path):
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (
            root / "config" / "legal_case_control_plane.json"
        ).read_text(encoding="utf-8")
    )
    payload["source_of_case_truth"][
        "lifecycle_does_not_promote_truth_class"
    ] = False
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LegalCaseControlPlaneError):
        load_binding(path)


def test_supabase_mirror_contract_is_service_role_only_and_history_safe():
    root = Path(__file__).resolve().parents[1]
    binding = load_binding(
        root / "config" / "legal_case_control_plane.json"
    )
    mirror = binding["supabase_mirror"]
    migration = root / mirror["migration"]
    sql = migration.read_text(encoding="utf-8")

    assert "alter table public.legal_case_control_events_v1 enable row level security;" in sql
    assert "alter table public.legal_case_runtime_health_v1 enable row level security;" in sql
    assert "alter table public.legal_case_control_receipts_v1 enable row level security;" in sql

    assert (
        "revoke all on public.legal_case_control_events_v1 from public,anon,authenticated;"
        in sql
    )
    assert (
        "revoke all on public.legal_case_runtime_health_v1 from public,anon,authenticated;"
        in sql
    )
    assert (
        "revoke all on public.legal_case_control_receipts_v1 from public,anon,authenticated;"
        in sql
    )

    assert (
        "grant select,insert on public.legal_case_control_events_v1 to service_role;"
        in sql
    )
    assert (
        "grant select,insert,update on public.legal_case_runtime_health_v1 to service_role;"
        in sql
    )
    assert (
        "grant select,insert on public.legal_case_control_receipts_v1 to service_role;"
        in sql
    )

    assert "legal_case_control_events_v1_immutable" in sql
    assert "legal_case_control_receipts_v1_immutable" in sql
    assert "event_idempotent_replay" in sql
    assert "upsert_legal_case_runtime_health_v1" in sql
    assert "where public.legal_case_runtime_health_v1.observed_at <= excluded.observed_at;" in sql
    assert mirror["truth_class_mutation"] is False


def test_binding_names_real_mirror_rpcs_and_outbox():
    root = Path(__file__).resolve().parents[1]
    binding = load_binding(
        root / "config" / "legal_case_control_plane.json"
    )
    mirror = binding["supabase_mirror"]
    runtime = binding["local_casebuilder_runtime"]

    assert (
        mirror["event_ingest_rpc"]
        == "public.ingest_legal_case_control_event_v1(jsonb)"
    )
    assert (
        mirror["health_upsert_rpc"]
        == "public.upsert_legal_case_runtime_health_v1(text,jsonb)"
    )
    assert runtime["outbox_table"] == "control_deliveries"
    assert runtime["mirror_target"] == "apex.supabase"
