"""Validation for the APEX direct authenticated connector runtime contract.

The repository already contains an authenticated-session provider bridge catalog.  The
direct runtime installed in ``supabase-backend-ops`` is a different transport and
therefore a different permission domain.  This module makes that distinction
machine-checkable so capabilities are never unioned across transports by accident.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "config" / "apex_connector_contract_registry.json"
DEFAULT_BRIDGE_CATALOG_PATH = REPO_ROOT / "config" / "apex_connector_catalog.json"
DEFAULT_DIRECT_RUNTIME_PATH = REPO_ROOT / "config" / "apex_direct_connector_runtime.json"


class DirectConnectorRuntimeContractError(ValueError):
    """Raised when connector transport contracts cannot be reconciled safely."""


@dataclass(frozen=True, slots=True)
class DirectRuntimeSummary:
    runtime_id: str
    version: int
    authority_project_id: str
    route_count: int
    pipeline_count: int
    verified_receipt_count: int
    transport: str


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DirectConnectorRuntimeContractError(f"contract file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DirectConnectorRuntimeContractError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise DirectConnectorRuntimeContractError(f"contract must be a JSON object: {path}")
    return payload


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise DirectConnectorRuntimeContractError(f"{field_name} is required")
    return text


def _positive_int(value: Any, field_name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise DirectConnectorRuntimeContractError(f"{field_name} must be an integer") from exc
    if number < 1:
        raise DirectConnectorRuntimeContractError(f"{field_name} must be positive")
    return number


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _target_digest(target: Any) -> str:
    if not isinstance(target, Mapping) or not target:
        raise DirectConnectorRuntimeContractError("pipeline step target must be a non-empty object")
    return sha256(_canonical_json(target).encode("utf-8")).hexdigest()


def _require_boolean(mapping: Mapping[str, Any], key: str, expected: bool) -> None:
    if mapping.get(key) is not expected:
        raise DirectConnectorRuntimeContractError(f"{key} must be {expected}")


def load_contract_registry(path: Path | None = None) -> Mapping[str, Any]:
    registry = _read_json(path or DEFAULT_REGISTRY_PATH)
    if registry.get("schema_version") != 1:
        raise DirectConnectorRuntimeContractError("unsupported connector contract registry schema")
    _required_text(registry.get("registry_id"), "registry_id")
    _positive_int(registry.get("version"), "registry version")

    contracts = registry.get("contracts")
    resolution = registry.get("resolution")
    if not isinstance(contracts, Mapping):
        raise DirectConnectorRuntimeContractError("registry contracts must be an object")
    if not isinstance(resolution, Mapping):
        raise DirectConnectorRuntimeContractError("registry resolution must be an object")

    required_contracts = {
        "authenticated_session_provider_bridge": "config/apex_connector_catalog.json",
        "authenticated_chatgpt_direct_runtime": "config/apex_direct_connector_runtime.json",
    }
    for contract_name, expected_path in required_contracts.items():
        contract = contracts.get(contract_name)
        if not isinstance(contract, Mapping):
            raise DirectConnectorRuntimeContractError(f"missing registry contract: {contract_name}")
        if contract.get("path") != expected_path:
            raise DirectConnectorRuntimeContractError(
                f"registry path mismatch for {contract_name}: expected {expected_path}"
            )
        _required_text(contract.get("transport"), f"{contract_name}.transport")
        _required_text(contract.get("authority"), f"{contract_name}.authority")
        _positive_int(contract.get("source_version"), f"{contract_name}.source_version")

    _require_boolean(resolution, "permission_union_allowed", False)
    _require_boolean(resolution, "transport_must_be_selected_before_capability_resolution", True)
    _require_boolean(resolution, "bridge_catalog_cannot_disable_a_verified_direct_runtime_route", True)
    _require_boolean(resolution, "direct_runtime_cannot_enable_a_bridge_host_mapping", True)
    _require_boolean(resolution, "writes_require_transport_local_approval_and_terminal_readback", True)
    _require_boolean(resolution, "ambiguous_external_outcome_can_never_promote_to_verified", True)
    return registry


def load_direct_runtime_contract(path: Path | None = None) -> Mapping[str, Any]:
    contract = _read_json(path or DEFAULT_DIRECT_RUNTIME_PATH)
    if contract.get("schema_version") != 1:
        raise DirectConnectorRuntimeContractError("unsupported direct runtime schema")
    _required_text(contract.get("runtime_id"), "runtime_id")
    _positive_int(contract.get("version"), "runtime version")

    authority = contract.get("authority")
    transport = contract.get("transport")
    security = contract.get("security")
    routes = contract.get("routes")
    pipelines = contract.get("pipelines")
    receipts = contract.get("verified_receipts")
    boundaries = contract.get("known_boundaries")

    if not isinstance(authority, Mapping):
        raise DirectConnectorRuntimeContractError("authority must be an object")
    if authority.get("system") != "supabase-backend-ops":
        raise DirectConnectorRuntimeContractError("direct runtime authority must be supabase-backend-ops")
    _required_text(authority.get("project_id"), "authority.project_id")
    for field_name in (
        "route_policy_table",
        "route_runtime_table",
        "pipeline_definition_table",
        "pipeline_run_table",
        "pipeline_stage_table",
    ):
        _required_text(authority.get(field_name), f"authority.{field_name}")

    if not isinstance(transport, Mapping):
        raise DirectConnectorRuntimeContractError("transport must be an object")
    if transport.get("name") != "authenticated_chatgpt_connectors":
        raise DirectConnectorRuntimeContractError("unexpected direct runtime transport")
    _require_boolean(transport, "credential_material_in_repository", False)
    _require_boolean(transport, "scheduled_execution", False)
    _require_boolean(transport, "persistent_worker_claimed", False)

    if not isinstance(security, Mapping):
        raise DirectConnectorRuntimeContractError("security must be an object")
    for security_flag in (
        "route_policy_v3_is_binding",
        "writes_require_bound_operator_approval",
        "writes_cannot_self_certify",
        "writes_require_same_connector_same_target_terminal_readback",
        "ambiguous_external_outcome_can_never_promote_to_verified",
        "successful_stages_require_request_hash",
        "successful_stages_require_result_hash",
        "successful_stages_require_invocation_reference",
        "successful_stages_require_source_references",
        "service_role_execution_allowed",
    ):
        _require_boolean(security, security_flag, True)
    _require_boolean(security, "anon_execution_allowed", False)
    _require_boolean(security, "authenticated_execution_allowed", False)

    if not isinstance(routes, Mapping) or not routes:
        raise DirectConnectorRuntimeContractError("routes must be a non-empty object")
    validated_routes: dict[str, Mapping[str, Any]] = {}
    for route_key, raw_route in routes.items():
        route_name = _required_text(route_key, "route key")
        if not isinstance(raw_route, Mapping):
            raise DirectConnectorRuntimeContractError(f"route must be an object: {route_name}")
        connector_key = _required_text(raw_route.get("connector_key"), f"{route_name}.connector_key")
        mutation_class = raw_route.get("mutation_class")
        if mutation_class not in {"read", "write"}:
            raise DirectConnectorRuntimeContractError(
                f"{route_name}.mutation_class must be read or write"
            )
        _required_text(raw_route.get("tool_name"), f"{route_name}.tool_name")
        _required_text(raw_route.get("capability"), f"{route_name}.capability")
        _required_text(raw_route.get("policy_version"), f"{route_name}.policy_version")
        approval_required = raw_route.get("approval_required")
        if not isinstance(approval_required, bool):
            raise DirectConnectorRuntimeContractError(
                f"{route_name}.approval_required must be boolean"
            )
        if mutation_class == "write" and approval_required is not True:
            raise DirectConnectorRuntimeContractError(
                f"write route must require approval: {route_name} ({connector_key})"
            )
        validated_routes[route_name] = dict(raw_route)

    if not isinstance(pipelines, Mapping) or not pipelines:
        raise DirectConnectorRuntimeContractError("pipelines must be a non-empty object")
    pipeline_step_counts: dict[str, int] = {}
    pipeline_hashes: dict[str, str] = {}
    for pipeline_key, raw_pipeline in pipelines.items():
        name = _required_text(pipeline_key, "pipeline key")
        if not isinstance(raw_pipeline, Mapping):
            raise DirectConnectorRuntimeContractError(f"pipeline must be an object: {name}")
        _positive_int(raw_pipeline.get("version"), f"{name}.version")
        definition_hash = raw_pipeline.get("definition_hash")
        if not _is_sha256(definition_hash):
            raise DirectConnectorRuntimeContractError(f"{name}.definition_hash must be sha256")
        raw_steps = raw_pipeline.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise DirectConnectorRuntimeContractError(f"{name}.steps must be non-empty")

        steps: dict[str, Mapping[str, Any]] = {}
        for raw_step in raw_steps:
            if not isinstance(raw_step, Mapping):
                raise DirectConnectorRuntimeContractError(f"{name} step must be an object")
            step_id = _required_text(raw_step.get("step_id"), f"{name}.step_id")
            if step_id in steps:
                raise DirectConnectorRuntimeContractError(f"duplicate step_id in {name}: {step_id}")
            route_key = _required_text(raw_step.get("route_key"), f"{name}.{step_id}.route_key")
            if route_key not in validated_routes:
                raise DirectConnectorRuntimeContractError(
                    f"unknown route in {name}.{step_id}: {route_key}"
                )
            _target_digest(raw_step.get("target"))
            dependencies = raw_step.get("depends_on")
            if not isinstance(dependencies, list) or any(
                not isinstance(item, str) or not item.strip() for item in dependencies
            ):
                raise DirectConnectorRuntimeContractError(
                    f"{name}.{step_id}.depends_on must be an array of step ids"
                )
            steps[step_id] = dict(raw_step)

        for step_id, step in steps.items():
            for dependency in step["depends_on"]:
                if dependency not in steps:
                    raise DirectConnectorRuntimeContractError(
                        f"unknown dependency in {name}.{step_id}: {dependency}"
                    )
            route = validated_routes[step["route_key"]]
            if route["mutation_class"] != "write":
                continue
            readback_step_id = _required_text(
                step.get("readback_step_id"), f"{name}.{step_id}.readback_step_id"
            )
            readback = steps.get(readback_step_id)
            if readback is None:
                raise DirectConnectorRuntimeContractError(
                    f"unknown readback step in {name}.{step_id}: {readback_step_id}"
                )
            readback_route = validated_routes[readback["route_key"]]
            if readback_route["mutation_class"] != "read":
                raise DirectConnectorRuntimeContractError(
                    f"readback route must be read-only: {name}.{readback_step_id}"
                )
            if readback_route["connector_key"] != route["connector_key"]:
                raise DirectConnectorRuntimeContractError(
                    f"write/readback connector mismatch: {name}.{step_id}"
                )
            if _target_digest(readback["target"]) != _target_digest(step["target"]):
                raise DirectConnectorRuntimeContractError(
                    f"write/readback target mismatch: {name}.{step_id}"
                )
            if step_id not in readback["depends_on"]:
                raise DirectConnectorRuntimeContractError(
                    f"readback must depend on its write: {name}.{step_id}"
                )

        pipeline_step_counts[name] = len(steps)
        pipeline_hashes[name] = str(definition_hash)

    if not isinstance(receipts, list) or not receipts:
        raise DirectConnectorRuntimeContractError("verified_receipts must be a non-empty array")
    seen_runs: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            raise DirectConnectorRuntimeContractError("verified receipt must be an object")
        pipeline_key = _required_text(receipt.get("pipeline_key"), "receipt.pipeline_key")
        if pipeline_key not in pipelines:
            raise DirectConnectorRuntimeContractError(
                f"receipt references unknown pipeline: {pipeline_key}"
            )
        run_id = _required_text(receipt.get("run_id"), "receipt.run_id")
        if run_id in seen_runs:
            raise DirectConnectorRuntimeContractError(f"duplicate verified run: {run_id}")
        seen_runs.add(run_id)
        _required_text(receipt.get("correlation_id"), "receipt.correlation_id")
        if receipt.get("status") != "verified":
            raise DirectConnectorRuntimeContractError(f"receipt is not verified: {run_id}")
        if receipt.get("pipeline_hash") != pipeline_hashes[pipeline_key]:
            raise DirectConnectorRuntimeContractError(f"pipeline hash mismatch: {run_id}")
        if int(receipt.get("stage_count", -1)) != pipeline_step_counts[pipeline_key]:
            raise DirectConnectorRuntimeContractError(f"stage count mismatch: {run_id}")
        if int(receipt.get("bad_terminal", -1)) != 0:
            raise DirectConnectorRuntimeContractError(f"verified run has bad terminal state: {run_id}")
        _required_text(receipt.get("completed_at"), "receipt.completed_at")

    if not isinstance(boundaries, Mapping):
        raise DirectConnectorRuntimeContractError("known_boundaries must be an object")
    _require_boolean(boundaries, "github_branch_protection_bypassed", False)
    for undeployed_boundary in (
        "cloudflare_queue_consumer_deployed",
        "smithery_scoped_executor_deployed",
        "automatic_supabase_to_notion_publisher_deployed",
    ):
        _require_boolean(boundaries, undeployed_boundary, False)

    return contract


def reconcile_connector_contracts(
    *,
    registry_path: Path | None = None,
    bridge_catalog_path: Path | None = None,
    direct_runtime_path: Path | None = None,
) -> DirectRuntimeSummary:
    """Validate transport separation and return the source-backed runtime summary."""
    registry = load_contract_registry(registry_path)
    bridge_catalog = _read_json(bridge_catalog_path or DEFAULT_BRIDGE_CATALOG_PATH)
    direct_runtime = load_direct_runtime_contract(direct_runtime_path)

    bridge_contract = registry["contracts"]["authenticated_session_provider_bridge"]
    direct_contract = registry["contracts"]["authenticated_chatgpt_direct_runtime"]
    if int(bridge_catalog.get("version", -1)) != int(bridge_contract["source_version"]):
        raise DirectConnectorRuntimeContractError("bridge catalog version does not match registry")
    if int(direct_runtime.get("version", -1)) != int(direct_contract["source_version"]):
        raise DirectConnectorRuntimeContractError("direct runtime version does not match registry")
    if bridge_contract["transport"] == direct_contract["transport"]:
        raise DirectConnectorRuntimeContractError("bridge and direct runtime transports must be distinct")

    # Critical non-union proof: the repository bridge intentionally keeps Notion
    # page.update inactive while the direct authenticated transport has a verified,
    # approval/readback-gated Notion projection route.  One transport does not grant
    # capability to the other.
    notion_bridge = bridge_catalog.get("connectors", {}).get("notion", {})
    notion_page_update = notion_bridge.get("write_operations", {}).get("page.update", {})
    if notion_page_update.get("enabled") is not False:
        raise DirectConnectorRuntimeContractError(
            "bridge Notion page.update must remain inactive until its host mapping is validated"
        )
    notion_direct_route = direct_runtime["routes"].get(
        "notion:notion-update-page:control_projection_write:v1"
    )
    if not isinstance(notion_direct_route, Mapping):
        raise DirectConnectorRuntimeContractError("verified direct Notion projection route is missing")
    if notion_direct_route.get("mutation_class") != "write":
        raise DirectConnectorRuntimeContractError("direct Notion projection route must be a write")
    if notion_direct_route.get("approval_required") is not True:
        raise DirectConnectorRuntimeContractError("direct Notion projection write must require approval")

    return DirectRuntimeSummary(
        runtime_id=str(direct_runtime["runtime_id"]),
        version=int(direct_runtime["version"]),
        authority_project_id=str(direct_runtime["authority"]["project_id"]),
        route_count=len(direct_runtime["routes"]),
        pipeline_count=len(direct_runtime["pipelines"]),
        verified_receipt_count=len(direct_runtime["verified_receipts"]),
        transport=str(direct_runtime["transport"]["name"]),
    )
