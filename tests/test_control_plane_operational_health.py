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
