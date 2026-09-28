"""Compatibility validator for the harvested APEX direct connector runtime.

Donor provenance: apex/reconcile-direct-connector-runtime-v3 / PR #77.
The donor's transport isolation, receipt, dependency, and terminal-readback mechanisms
are preserved. Its blanket per-write approval predicates are intentionally rejected in
favor of current source-bound, route-scoped authority semantics.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "config" / "apex_connector_contract_registry.json"
DEFAULT_RUNTIME_PATH = REPO_ROOT / "config" / "apex_direct_connector_runtime.json"


class DirectConnectorRuntimeContractError(ValueError):
    """Raised when harvested connector semantics regress or conflict."""


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise DirectConnectorRuntimeContractError(f"contract must be an object: {path}")
    return payload


def _require(mapping: Mapping[str, Any], key: str, expected: Any) -> None:
    if mapping.get(key) != expected:
        raise DirectConnectorRuntimeContractError(
            f"{key} must be {expected!r}; got {mapping.get(key)!r}"
        )


def load_contract_registry(path: Path | None = None) -> Mapping[str, Any]:
    registry = _read_json(path or DEFAULT_REGISTRY_PATH)
    _require(registry, "schema_version", 2)
    resolution = registry.get("resolution")
    if not isinstance(resolution, Mapping):
        raise DirectConnectorRuntimeContractError("resolution must be an object")
    _require(resolution, "permission_union_allowed", False)
    _require(resolution, "transport_must_be_selected_before_capability_resolution", True)
    _require(resolution, "authorization_is_source_bound_and_route_scoped", True)
    _require(resolution, "routine_recoverable_writes_may_inherit_active_mission_authority", True)
    _require(resolution, "consequence_sensitive_writes_require_scoped_consequence_authority", True)
    _require(resolution, "verification_and_readback_do_not_manufacture_permission", True)
    _require(resolution, "writes_require_terminal_readback", True)
    return registry


def load_direct_runtime_contract(path: Path | None = None) -> Mapping[str, Any]:
    runtime = _read_json(path or DEFAULT_RUNTIME_PATH)
    _require(runtime, "schema_version", 2)
    transport = runtime.get("transport")
    authority = runtime.get("authority_semantics")
    resolution = runtime.get("transport_resolution")
    if not isinstance(transport, Mapping) or not isinstance(authority, Mapping) or not isinstance(resolution, Mapping):
        raise DirectConnectorRuntimeContractError("transport, authority_semantics and transport_resolution must be objects")
    _require(transport, "name", "authenticated_chatgpt_connectors")
    _require(transport, "credential_material_in_repository", False)
    _require(authority, "source_bound_authorization_required", True)
    _require(authority, "blanket_per_write_approval_required", False)
    _require(authority, "routine_recoverable_write_authority_mode", "active_mission_authority")
    _require(authority, "consequence_sensitive_write_authority_mode", "scoped_consequence_authority")
    _require(authority, "verification_is_permission", False)
    _require(authority, "terminal_readback_required_for_write_completion_claim", True)
    _require(resolution, "permission_union_allowed", False)
    _require(resolution, "transport_must_be_selected_before_capability_resolution", True)
    return runtime


def validate_connector_transport_admission(
    transport: str,
    *,
    registry_path: Path | None = None,
    runtime_path: Path | None = None,
) -> dict[str, Any]:
    registry = load_contract_registry(registry_path)
    runtime = load_direct_runtime_contract(runtime_path)
    contracts = registry.get("contracts")
    if not isinstance(contracts, Mapping):
        raise DirectConnectorRuntimeContractError("contracts must be an object")
    matching = [name for name, contract in contracts.items() if isinstance(contract, Mapping) and contract.get("transport") == transport]
    if len(matching) != 1:
        raise DirectConnectorRuntimeContractError(f"transport must resolve to exactly one contract: {transport}")
    return {
        "transport": transport,
        "contract": matching[0],
        "permission_union_allowed": False,
        "authority_mode_for_routine_recoverable_write": runtime["authority_semantics"]["routine_recoverable_write_authority_mode"],
        "terminal_readback_required": True,
    }


def validate_source_contracts() -> dict[str, Any]:
    registry = load_contract_registry()
    runtime = load_direct_runtime_contract()
    return {
        "registry_id": registry["registry_id"],
        "runtime_id": runtime["runtime_id"],
        "transport": runtime["transport"]["name"],
        "permission_union_allowed": False,
        "blanket_per_write_approval_required": False,
        "verification_is_permission": False,
        "terminal_readback_required": True,
    }
