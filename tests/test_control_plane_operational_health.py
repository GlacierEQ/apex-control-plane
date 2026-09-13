from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "db/migrations/20260902193640_control_plane_operational_snapshot_v2.sql"
RUNTIME = ROOT / "db/migrations/20260902194020_control_plane_route_runtime_health_v4.sql"


def test_live_operational_snapshot_source_is_service_role_only_and_prioritized():
    source = SNAPSHOT.read_text().lower()
    assert "control_plane_operational_snapshot_v2" in source
    assert "operational_core" in source
    assert "integration_working_set" in source
    assert "estate_backlog" in source
    assert "revoke all on function public.control_plane_operational_snapshot_v2() from public,anon,authenticated" in source
    assert "grant execute on function public.control_plane_operational_snapshot_v2() to service_role" in source


def test_live_runtime_health_requires_executable_healthy_routes():
    source = RUNTIME.read_text().lower()
    assert "and enabled_route_count>0" in source
    assert "authority_tier<=2" not in source
    assert "enabled_routes_with_runtime" in source
    assert "enabled_healthy_runtime_routes" in source
    assert "enabled_unhealthy_runtime_routes" in source
    assert "rt.circuit_state='closed'" in source
    assert "coalesce(rt.consecutive_failures,0)=0" in source


def test_runtime_health_preserves_backlog_and_current_failure_evidence():
    source = RUNTIME.read_text().lower()
    assert "estate_backlog" in source
    assert "effective_health_status" in source
    assert "batch_failed_recent_15m" in source
    assert "webhook_failed_recent_15m" in source
    assert "stale_online_worker_count" in source
