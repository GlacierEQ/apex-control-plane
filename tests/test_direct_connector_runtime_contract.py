from __future__ import annotations

import json
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from direct_connector_runtime_contract import (
    DirectConnectorRuntimeContractError,
    load_contract_registry,
    load_direct_runtime_contract,
    reconcile_connector_contracts,
    validate_connector_transport_admission,
)


REGISTRY_PATH = ROOT / "config" / "apex_connector_contract_registry.json"
DIRECT_RUNTIME_PATH = ROOT / "config" / "apex_direct_connector_runtime.json"
BRIDGE_CATALOG_PATH = ROOT / "config" / "apex_connector_catalog.json"


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _resign_pipeline(payload: dict, pipeline_key: str) -> None:
    pipeline = payload["pipelines"][pipeline_key]
    definition = json.loads(pipeline["definition_text"])
    definition["invariants"] = pipeline["invariants"]
    definition["steps"] = pipeline["steps"]
    definition_text = json.dumps(definition, sort_keys=True, separators=(",", ":"))
    definition_hash = sha256(definition_text.encode("utf-8")).hexdigest()
    pipeline["definition_text"] = definition_text
    pipeline["definition_hash"] = definition_hash
    for receipt in payload["verified_receipts"]:
        if receipt["pipeline_key"] == pipeline_key:
            receipt["pipeline_hash"] = definition_hash


def test_contract_registry_forbids_permission_union():
    registry = load_contract_registry(REGISTRY_PATH)

    assert registry["resolution"]["permission_union_allowed"] is False
    assert registry["resolution"]["transport_must_be_selected_before_capability_resolution"] is True
    assert registry["contracts"]["authenticated_session_provider_bridge"]["transport"] == (
        "authenticated_session_provider_bridge"
    )
    assert registry["contracts"]["authenticated_chatgpt_direct_runtime"]["transport"] == (
        "authenticated_chatgpt_connectors"
    )


def test_verified_direct_runtime_contract_loads():
    contract = load_direct_runtime_contract(DIRECT_RUNTIME_PATH)

    assert contract["runtime_id"] == "apex-direct-connector-runtime"
    assert contract["authority"]["project_id"] == "dyhprklicgewmrimecey"
    assert contract["transport"]["name"] == "authenticated_chatgpt_connectors"
    assert contract["security"]["writes_require_bound_OPERATOR_approval"] is True
    assert contract["security"]["definition_hash_binds_stored_behavior"] is True
    assert contract["security"]["dependency_graph_must_be_acyclic"] is True
    assert len(contract["routes"]) == 5
    assert len(contract["pipelines"]) == 2
    assert len(contract["verified_receipts"]) == 2


def test_reconciliation_preserves_transport_specific_notion_authority():
    bridge = json.loads(BRIDGE_CATALOG_PATH.read_text(encoding="utf-8"))
    direct = load_direct_runtime_contract(DIRECT_RUNTIME_PATH)

    assert bridge["connectors"]["notion"]["write_operations"]["page.update"]["enabled"] is False
    assert direct["routes"]["notion:notion-update-page:control_projection_write:v1"] == {
        "connector_key": "notion",
        "tool_name": "notion-update-page",
        "capability": "control_projection_write",
        "mutation_class": "write",
        "policy_version": "v1",
        "approval_required": True,
    }

    summary = reconcile_connector_contracts()
    assert summary.transport == "authenticated_chatgpt_connectors"
    assert summary.route_count == 5
    assert summary.pipeline_count == 2
    assert summary.verified_receipt_count == 2


def test_production_transport_admission_validates_registered_contracts():
    summary = validate_connector_transport_admission("authenticated_session_provider_bridge")
    assert summary.authority_project_id == "dyhprklicgewmrimecey"

    with pytest.raises(DirectConnectorRuntimeContractError, match="unregistered connector transport"):
        validate_connector_transport_admission("invented_transport")


def test_projected_behavior_tamper_with_stale_definition_is_rejected(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    pipeline = payload["pipelines"]["apex.direct_control_plane_checkpoint"]
    pipeline["steps"][0]["target"]["path"] = "config/TAMPERED.json"
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="projected pipeline behavior"):
        load_direct_runtime_contract(path)


def test_stored_definition_text_tamper_with_stale_hash_is_rejected(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    pipeline = payload["pipelines"]["apex.direct_control_plane_checkpoint"]
    pipeline["definition_text"] = pipeline["definition_text"].replace(
        "config/apex_connector_catalog.json",
        "config/TAMPERED.json",
        1,
    )
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="does not match stored definition"):
        load_direct_runtime_contract(path)


def test_write_without_terminal_readback_is_rejected(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    pipeline_key = "apex.direct_control_plane_checkpoint"
    del payload["pipelines"][pipeline_key]["steps"][1]["readback_step_id"]
    _resign_pipeline(payload, pipeline_key)
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="readback_step_id"):
        load_direct_runtime_contract(path)


def test_cross_connector_readback_is_rejected(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    pipeline_key = "apex.direct_control_plane_checkpoint"
    readback = payload["pipelines"][pipeline_key]["steps"][2]
    readback["route_key"] = "notion:fetch:workspace_page_read:v1"
    _resign_pipeline(payload, pipeline_key)
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="connector mismatch"):
        load_direct_runtime_contract(path)


def test_same_connector_different_target_readback_is_rejected(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    pipeline_key = "apex.direct_control_plane_checkpoint"
    readback = payload["pipelines"][pipeline_key]["steps"][2]
    readback["target"]["receipt_key"] = "different-object"
    _resign_pipeline(payload, pipeline_key)
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="target mismatch"):
        load_direct_runtime_contract(path)


def test_dependency_cycle_is_rejected_even_when_hash_is_consistent(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    pipeline_key = "apex.connector_mesh_health_sweep"
    steps = payload["pipelines"][pipeline_key]["steps"]
    steps[0]["depends_on"] = [steps[1]["step_id"]]
    steps[1]["depends_on"] = [steps[0]["step_id"]]
    _resign_pipeline(payload, pipeline_key)
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="dependency cycle"):
        load_direct_runtime_contract(path)


def test_verified_receipt_pipeline_version_must_match(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    payload["verified_receipts"][0]["pipeline_version"] = 99
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="pipeline version mismatch"):
        load_direct_runtime_contract(path)


def test_verified_receipt_outcome_counts_must_match_pipeline(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    payload["verified_receipts"][0]["verified_reads"] = 999
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="verified read count mismatch"):
        load_direct_runtime_contract(path)


def test_verified_write_requires_operator_approval_evidence(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    payload["verified_receipts"][0]["approval_source"] = "AGENT"
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="must name OPERATOR"):
        load_direct_runtime_contract(path)


def test_verified_write_approval_target_is_hash_bound(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    approval = payload["verified_receipts"][0]["write_approvals"][0]
    approval["target_text"] = approval["target_text"].replace(
        "public.connector_upgrade_changelog_v2",
        "public.other_table",
    )
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="target hash mismatch"):
        load_direct_runtime_contract(path)


def test_verified_receipt_hash_mismatch_is_rejected(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    payload["verified_receipts"][0]["pipeline_hash"] = "0" * 64
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="pipeline hash mismatch"):
        load_direct_runtime_contract(path)


def test_authority_project_identity_cannot_drift(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    payload["authority"]["project_id"] = "attacker-controlled-project"
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="authority.project_id"):
        load_direct_runtime_contract(path)


def test_registry_rejects_transport_identity_drift(tmp_path):
    payload = deepcopy(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))
    payload["contracts"]["authenticated_session_provider_bridge"]["transport"] = "other_bridge"
    path = _write_json(tmp_path / "registry.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="registry transport mismatch"):
        load_contract_registry(path)


def test_registry_rejects_permission_union(tmp_path):
    payload = deepcopy(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))
    payload["resolution"]["permission_union_allowed"] = True
    path = _write_json(tmp_path / "registry.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="permission_union_allowed"):
        load_contract_registry(path)


def test_protected_main_boundary_cannot_be_rewritten(tmp_path):
    payload = deepcopy(json.loads(DIRECT_RUNTIME_PATH.read_text(encoding="utf-8")))
    payload["known_boundaries"]["github_main_direct_write"] = "allowed"
    path = _write_json(tmp_path / "runtime.json", payload)

    with pytest.raises(DirectConnectorRuntimeContractError, match="protected-main boundary"):
        load_direct_runtime_contract(path)
