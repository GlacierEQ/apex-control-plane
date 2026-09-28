from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db" / "migrations" / "20260923154000_mission_context_packet_compiler_v1.sql"


def test_mission_context_compiler_contract_is_source_bearing_and_non_stopping():
    sql = MIGRATION.read_text()
    required = [
        "mission_context_packets_v1",
        "compile_mission_context_packet_v1",
        "'current_operator_state'",
        "'relevant_prior_decisions'",
        "'verified_sources'",
        "'open_tasks'",
        "'contradictions'",
        "'superseded_state'",
        "'repo_capabilities'",
        "'connector_health'",
        "'confidence'",
        "'resume_point'",
        "'degraded_lanes'",
        "'mission_stop',false",
        "DEGRADED_LANES_CHANGE_ROUTE_NOT_MISSION",
        "mission_context_packet_idempotency_conflict",
        "sha256",
    ]
    for token in required:
        assert token in sql, token


def test_context_compiler_does_not_promote_optional_lane_failure_to_permission_gate():
    sql = MIGRATION.read_text()
    assert "context_state in ('hydrated','degraded')" in sql
    assert "mission_stop',false" in sql
    assert "context missing -> mission blocked" not in sql.lower()
    assert "permission granted" not in sql.lower()
