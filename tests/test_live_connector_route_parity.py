from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALL_E = ROOT / "db/migrations/20260903093425_register_call_e_continuity_connector_v1_1.sql"
RESOLVER = ROOT / "db/migrations/20260912123530_add_connector_capability_route_resolver_v1.sql"


def test_call_e_registration_keeps_external_execution_fail_closed() -> None:
    source = CALL_E.read_text().lower()
    assert "'call_e'" in source
    assert "'voice_run_readback'" in source
    assert "'voice_plan'" in source
    assert "'voice_external_action'" in source
    assert "explicit_user_call_intent_required" in source
    assert "no_external_call_by_planning_alone" in source
    assert "ready_plan_required" in source
    assert "confirm_token_required" in source
    assert "terminal_readback_required" in source
    assert "idempotent_plan_id_required" in source
    assert "'voice_plan', 'write', 'v1',\n  99, false, true, false" in source
    assert "'voice_external_action', 'write', 'v1',\n  100, false, true, false" in source


def test_capability_resolver_uses_live_route_state_without_transferring_authority() -> None:
    source = RESOLVER.read_text().lower()
    assert "resolve_connector_capability_routes_v1" in source
    assert "connector_execution_route_eligibility_v3" in source
    assert "connector_route_policy_v3" in source
    assert "connector_route_runtime_v3" in source
    assert "connector_registry_v2" in source
    assert "connector_capability_matrix_v2" in source
    assert "capability_mesh_edges_v1" in source
    assert "verified_capability_level" in source
    assert "mesh_evidence_count" in source
    assert "circuit_state = 'closed'" in source
    assert "revoke all on function public.resolve_connector_capability_routes_v1(text,text,integer) from public, anon, authenticated" in source
    assert "grant execute on function public.resolve_connector_capability_routes_v1(text,text,integer) to service_role" in source
    assert "without transferring source authority" in source
