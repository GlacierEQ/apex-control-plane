from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.direct_connector_runtime_contract import (
    DirectConnectorRuntimeContractError,
    load_contract_registry,
    load_direct_runtime_contract,
    validate_connector_transport_admission,
    validate_source_contracts,
)


def _rewrite(tmp_path: Path, source: Path, mutate) -> Path:
    payload = json.loads(source.read_text(encoding="utf-8"))
    mutate(payload)
    target = tmp_path / source.name
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_current_source_contracts_preserve_transport_isolation_without_blanket_approval() -> None:
    summary = validate_source_contracts()
    assert summary["permission_union_allowed"] is False
    assert summary["blanket_per_write_approval_required"] is False
    assert summary["verification_is_permission"] is False
    assert summary["terminal_readback_required"] is True


def test_registry_rejects_permission_union(tmp_path: Path) -> None:
    source = Path("config/apex_connector_contract_registry.json")
    target = _rewrite(tmp_path, source, lambda p: p["resolution"].__setitem__("permission_union_allowed", True))
    with pytest.raises(DirectConnectorRuntimeContractError):
        load_contract_registry(target)


def test_runtime_rejects_blanket_per_write_approval(tmp_path: Path) -> None:
    source = Path("config/apex_direct_connector_runtime.json")
    target = _rewrite(tmp_path, source, lambda p: p["authority_semantics"].__setitem__("blanket_per_write_approval_required", True))
    with pytest.raises(DirectConnectorRuntimeContractError):
        load_direct_runtime_contract(target)


def test_runtime_rejects_verification_as_permission(tmp_path: Path) -> None:
    source = Path("config/apex_direct_connector_runtime.json")
    target = _rewrite(tmp_path, source, lambda p: p["authority_semantics"].__setitem__("verification_is_permission", True))
    with pytest.raises(DirectConnectorRuntimeContractError):
        load_direct_runtime_contract(target)


def test_runtime_requires_terminal_readback_for_completion_claim(tmp_path: Path) -> None:
    source = Path("config/apex_direct_connector_runtime.json")
    target = _rewrite(tmp_path, source, lambda p: p["authority_semantics"].__setitem__("terminal_readback_required_for_write_completion_claim", False))
    with pytest.raises(DirectConnectorRuntimeContractError):
        load_direct_runtime_contract(target)


def test_transport_resolves_before_capability_and_reports_active_mission_authority() -> None:
    result = validate_connector_transport_admission("authenticated_chatgpt_connectors")
    assert result["contract"] == "authenticated_chatgpt_direct_runtime"
    assert result["permission_union_allowed"] is False
    assert result["authority_mode_for_routine_recoverable_write"] == "active_mission_authority"
    assert result["terminal_readback_required"] is True


GATEWAY_SOURCE = Path("supabase/functions/apex-connector-tool-gateway/index.ts")
FABRIC_SOURCE = Path("supabase/functions/apex-direct-mcp-fabric/index.ts")


def test_connector_runtime_requires_explicit_internal_auth_before_any_route_or_job_access() -> None:
    source = GATEWAY_SOURCE.read_text(encoding="utf-8")
    auth_index = source.index("authorizeInternalRuntimeRequest(req)")
    url_index = source.index("const url = new URL(req.url)")
    assert auth_index < url_index
    assert 'req.headers.get("apikey")' in source
    assert 'req.headers.get("x-glaciereq-origin")' in source
    assert '"apex-direct-mcp-fabric"' in source
    assert "SUPABASE_SECRET_KEYS" in source
    assert "SUPABASE_SERVICE_ROLE_KEY" in source


def test_connector_runtime_does_not_treat_platform_jwt_check_as_authorization() -> None:
    source = GATEWAY_SOURCE.read_text(encoding="utf-8")
    assert "authorizeInternalRuntimeRequest" in source
    assert "internal_runtime_unauthorized" in source
    assert "service_key_unavailable" in source


def test_direct_fabric_supplies_the_runtime_internal_auth_contract() -> None:
    source = FABRIC_SOURCE.read_text(encoding="utf-8")
    assert '"x-glaciereq-origin": "apex-direct-mcp-fabric"' in source
    assert "apikey:" in source
    assert "SUPABASE_SECRET_KEYS" in source
    assert "SUPABASE_SERVICE_ROLE_KEY" in source
