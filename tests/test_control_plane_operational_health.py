from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_operational_snapshot_is_service_role_only_and_prioritized():
    source = (ROOT / "db" / "migrations" / "20260902193651_control_plane_operational_snapshot_v2.sql").read_text().lower()
    assert "control_plane_operational_snapshot_v2" in source
    assert "operational_core" in source
    assert "integration_working_set" in source
    assert "estate_backlog" in source
    assert "revoke all on function public.control_plane_operational_snapshot_v2() from public,anon,authenticated" in source
    assert "grant execute on function public.control_plane_operational_snapshot_v2() to service_role" in source


def test_operational_snapshot_preserves_backlog_visibility():
    source = (ROOT / "db" / "migrations" / "20260902193651_control_plane_operational_snapshot_v2.sql").read_text().lower()
    assert "estate_backlog" in source
    assert "effective_health_status" in source
    assert "next_human_gate" in source


def test_operational_core_requires_executable_routes():
    source = (ROOT / "db" / "migrations" / "20260902193955_control_plane_route_runtime_health_v4.sql").read_text().lower()
    assert "and enabled_route_count>0" in source
    assert "authority_tier<=2" not in source


def test_route_runtime_can_promote_verified_connector_to_healthy():
    source = (ROOT / "db" / "migrations" / "20260902193955_control_plane_route_runtime_health_v4.sql").read_text().lower()
    assert "enabled_routes_with_runtime" in source
    assert "enabled_healthy_runtime_routes" in source
    assert "enabled_unhealthy_runtime_routes" in source
    assert "rt.circuit_state='closed'" in source
    assert "coalesce(rt.consecutive_failures,0)=0" in source


def test_notion_search_v1_is_only_superseded_when_v2_is_healthy():
    source = (ROOT / "db" / "migrations" / "20260902193841_notion_route_supersession_v1.sql").read_text().lower()
    assert "notion:search:workspace_search:v1" in source
    assert "notion:search:workspace_search:v2" in source
    assert "r2.health_status='healthy'" in source
    assert "r2.circuit_state='closed'" in source
    assert "r2.consecutive_failures=0" in source
    assert "set enabled=false" in source
