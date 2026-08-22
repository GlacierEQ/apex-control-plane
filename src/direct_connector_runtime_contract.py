"""Validation for the APEX direct authenticated connector runtime contract.

The repository-side authenticated-session bridge and the direct ChatGPT connector
runtime are different transports and therefore different permission domains. This
module keeps those capabilities separate and validates the source projection of the
verified Supabase runtime.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "config" / "apex_connector_contract_registry.json"
DEFAULT_BRIDGE_CATALOG_PATH = REPO_ROOT / "config" / "apex_connector_catalog.json"
DEFAULT_DIRECT_RUNTIME_PATH = REPO_ROOT / "config" / "apex_direct_connector_runtime.json"

EXPECTED_BRIDGE_TRANSPORT = "authenticated_session_provider_bridge"
EXPECTED_DIRECT_TRANSPORT = "authenticated_chatgpt_connectors"
EXPECTED_AUTHORITY = {
    "system": "supabase-backend-ops",
    "project_id": "dyhprklicgewmrimecey",
    "route_policy_table": "public.connector_route_policy_v3",
    "route_runtime_table": "public.connector_route_runtime_v3",
    "pipeline_definition_table": "public.connector_pipeline_definitions_v1",
    "pipeline_run_table": "public.connector_pipeline_runs_v1",
    "pipeline_stage_table": "public.connector_pipeline_stage_runs_v1",
}
EXPECTED_GITHUB_MAIN_DIRECT_WRITE = "blocked_by_required_status_checks"


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


def _nonnegative_int(value: Any, field_name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise DirectConnectorRuntimeContractError(f"{field_name} must be an integer") from exc
    if number < 0:
        raise DirectConnectorRuntimeContractError(f"{field_name} must be nonnegative")
    return number


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _digest_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _target_digest(target: Any) -> str:
    if not isinstance(target, Mapping) or not target:
        raise DirectConnectorRuntimeContractError("pipeline step target must be a non-empty object")
    return _digest_text(_stable_json(target))


def _require_boolean(mapping: Mapping[str, Any], key: str, expected: bool) -> None:
    if mapping.get(key) is not expected:
        raise DirectConnectorRuntimeContractError(f"{key} must be {expected}")


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise DirectConnectorRuntimeContractError(f"{field_name} must be an array of text values")
    if len(value) != len(set(value)):
        raise DirectConnectorRuntimeContractError(f"{field_name} contains duplicates")
    return list(value)


def _assert_acyclic_pipeline(
    pipeline_name: str,
    steps: Mapping[str, Mapping[str, Any]],
) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise DirectConnectorRuntimeContractError(
                f"dependency cycle detected in {pipeline_name}: {step_id}"
            )
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in steps[step_id]["depends_on"]:
            visit(str(dependency))
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in steps:
        visit(step_id)


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

    expected_contracts = {
        "authenticated_session_provider_bridge": (
            "config/apex_connector_catalog.json",
            EXPECTED_BRIDGE_TRANSPORT,
        ),
        "authenticated_chatgpt_direct_runtime": (
            "config/apex_direct_connector_runtime.json",
            EXPECTED_DIRECT_TRANSPORT,
        ),
    }
    for contract_name, (expected_path, expected_transport) in expected_contracts.items():
        contract = contracts.get(contract_name)
        if not isinstance(contract, Mapping):
            raise DirectConnectorRuntimeContractError(f"missing registry contract: {contract_name}")
        if contract.get("path") != expected_path:
            raise DirectConnectorRuntimeContractError(
                f"registry path mismatch for {contract_name}: expected {expected_path}"
            )
        if contract.get("transport") != expected_transport:
            raise DirectConnectorRuntimeContractError(
                f"registry transport mismatch for {contract_name}: expected {expected_transport}"
            )
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
    for key, expected in EXPECTED_AUTHORITY.items():
        if authority.get(key) != expected:
            raise DirectConnectorRuntimeContractError(
                f"authority.{key} must match verified runtime identity {expected}"
            )

    if not isinstance(transport, Mapping):
        raise DirectConnectorRuntimeContractError("transport must be an object")
    if transport.get("name") != EXPECTED_DIRECT_TRANSPORT:
        raise DirectConnectorRuntimeContractError("unexpected direct runtime transport")
    _require_boolean(transport, "credential_material_in_repository", False)
    _require_boolean(transport, "scheduled_execution", False)
    _require_boolean(transport, "persistent_worker_claimed", False)

    if not isinstance(security, Mapping):
        raise DirectConnectorRuntimeContractError("security must be an object")
    for security_flag in (
        "route_policy_v3_is_binding",
        "writes_require_bound_OPERATOR_approval",
        "writes_cannot_self_certify",
        "writes_require_same_connector_same_target_terminal_readback",
        "ambiguous_external_outcome_can_never_promote_to_verified",
        "successful_stages_require_request_hash",
        "successful_stages_require_result_hash",
        "successful_stages_require_invocation_reference",
        "successful_stages_require_source_references",
        "definition_hash_binds_stored_behavior",
        "dependency_graph_must_be_acyclic",
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
    pipeline_versions: dict[str, int] = {}
    pipeline_hashes: dict[str, str] = {}
    pipeline_read_counts: dict[str, int] = {}
    pipeline_write_steps: dict[str, dict[str, Mapping[str, Any]]] = {}

    for pipeline_key, raw_pipeline in pipelines.items():
        name = _required_text(pipeline_key, "pipeline key")
        if not isinstance(raw_pipeline, Mapping):
            raise DirectConnectorRuntimeContractError(f"pipeline must be an object: {name}")
        version = _positive_int(raw_pipeline.get("version"), f"{name}.version")
        definition_hash = _required_text(raw_pipeline.get("definition_hash"), f"{name}.definition_hash")
        if not _is_sha256(definition_hash):
            raise DirectConnectorRuntimeContractError(f"{name}.definition_hash must be sha256")
        definition_text = _required_text(raw_pipeline.get("definition_text"), f"{name}.definition_text")
        if _digest_text(definition_text) != definition_hash:
            raise DirectConnectorRuntimeContractError(
                f"{name}.definition_hash does not match stored definition text"
            )
        try:
            stored_definition = json.loads(definition_text)
        except json.JSONDecodeError as exc:
            raise DirectConnectorRuntimeContractError(
                f"{name}.definition_text must contain valid JSON"
            ) from exc

        invariants = _string_list(raw_pipeline.get("invariants"), f"{name}.invariants")
        raw_steps = raw_pipeline.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise DirectConnectorRuntimeContractError(f"{name}.steps must be non-empty")
        expected_definition = {
            "schema_version": 1,
            "pipeline_key": name,
            "version": version,
            "transport": EXPECTED_DIRECT_TRANSPORT,
            "invariants": invariants,
            "steps": raw_steps,
        }
        if stored_definition != expected_definition:
            raise DirectConnectorRuntimeContractError(
                f"{name}.definition_text does not match projected pipeline behavior"
            )

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
            dependencies = _string_list(
                raw_step.get("depends_on"),
                f"{name}.{step_id}.depends_on",
            )
            steps[step_id] = {**dict(raw_step), "depends_on": dependencies}

        for step_id, step in steps.items():
            for dependency in step["depends_on"]:
                if dependency not in steps:
                    raise DirectConnectorRuntimeContractError(
                        f"unknown dependency in {name}.{step_id}: {dependency}"
                    )
        _assert_acyclic_pipeline(name, steps)

        write_steps: dict[str, Mapping[str, Any]] = {}
        read_count = 0
        for step_id, step in steps.items():
            route = validated_routes[str(step["route_key"])]
            if route["mutation_class"] == "read":
                read_count += 1
                continue
            write_steps[step_id] = {
                "connector_key": route["connector_key"],
                "target": step["target"],
            }
            readback_step_id = _required_text(
                step.get("readback_step_id"),
                f"{name}.{step_id}.readback_step_id",
            )
            readback = steps.get(readback_step_id)
            if readback is None:
                raise DirectConnectorRuntimeContractError(
                    f"unknown readback step in {name}.{step_id}: {readback_step_id}"
                )
            readback_route = validated_routes[str(readback["route_key"])]
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
        pipeline_versions[name] = version
        pipeline_hashes[name] = definition_hash
        pipeline_read_counts[name] = read_count
        pipeline_write_steps[name] = write_steps

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
        if _positive_int(receipt.get("pipeline_version"), "receipt.pipeline_version") != pipeline_versions[pipeline_key]:
            raise DirectConnectorRuntimeContractError(f"pipeline version mismatch: {run_id}")
        if receipt.get("pipeline_hash") != pipeline_hashes[pipeline_key]:
            raise DirectConnectorRuntimeContractError(f"pipeline hash mismatch: {run_id}")
        if _nonnegative_int(receipt.get("stage_count"), "receipt.stage_count") != pipeline_step_counts[pipeline_key]:
            raise DirectConnectorRuntimeContractError(f"stage count mismatch: {run_id}")
        expected_reads = pipeline_read_counts[pipeline_key]
        expected_writes = len(pipeline_write_steps[pipeline_key])
        if _nonnegative_int(receipt.get("verified_reads"), "receipt.verified_reads") != expected_reads:
            raise DirectConnectorRuntimeContractError(f"verified read count mismatch: {run_id}")
        if _nonnegative_int(receipt.get("succeeded_writes"), "receipt.succeeded_writes") != expected_writes:
            raise DirectConnectorRuntimeContractError(f"succeeded write count mismatch: {run_id}")
        if _nonnegative_int(receipt.get("bad_terminal"), "receipt.bad_terminal") != 0:
            raise DirectConnectorRuntimeContractError(f"verified run has bad terminal state: {run_id}")

        raw_approvals = receipt.get("write_approvals")
        if not isinstance(raw_approvals, list):
            raise DirectConnectorRuntimeContractError("receipt.write_approvals must be an array")
        expected_write_steps = pipeline_write_steps[pipeline_key]
        if len(raw_approvals) != expected_writes:
            raise DirectConnectorRuntimeContractError(f"write approval count mismatch: {run_id}")
        if expected_writes:
            if receipt.get("approval_source") != "OPERATOR":
                raise DirectConnectorRuntimeContractError(
                    f"verified mutating run must name OPERATOR as approval source: {run_id}"
                )
            approval_reference = _required_text(
                receipt.get("approval_reference"),
                "receipt.approval_reference",
            )
            approvals_by_step: dict[str, Mapping[str, Any]] = {}
            for raw_approval in raw_approvals:
                if not isinstance(raw_approval, Mapping):
                    raise DirectConnectorRuntimeContractError("write approval must be an object")
                step_id = _required_text(raw_approval.get("step_id"), "write approval step_id")
                if step_id in approvals_by_step:
                    raise DirectConnectorRuntimeContractError(
                        f"duplicate write approval for {pipeline_key}.{step_id}"
                    )
                approvals_by_step[step_id] = raw_approval
            if set(approvals_by_step) != set(expected_write_steps):
                raise DirectConnectorRuntimeContractError(f"write approval step mismatch: {run_id}")
            for step_id, expected_stage in expected_write_steps.items():
                approval = approvals_by_step[step_id]
                if approval.get("connector_key") != expected_stage["connector_key"]:
                    raise DirectConnectorRuntimeContractError(
                        f"write approval connector mismatch: {pipeline_key}.{step_id}"
                    )
                if approval.get("approval_source") != "OPERATOR":
                    raise DirectConnectorRuntimeContractError(
                        f"write approval source must be OPERATOR: {pipeline_key}.{step_id}"
                    )
                if approval.get("approval_reference") != approval_reference:
                    raise DirectConnectorRuntimeContractError(
                        f"write approval reference mismatch: {pipeline_key}.{step_id}"
                    )
                target_text = _required_text(
                    approval.get("target_text"),
                    f"{pipeline_key}.{step_id}.target_text",
                )
                target_hash = _required_text(
                    approval.get("target_hash"),
                    f"{pipeline_key}.{step_id}.target_hash",
                )
                if not _is_sha256(target_hash) or _digest_text(target_text) != target_hash:
                    raise DirectConnectorRuntimeContractError(
                        f"write approval target hash mismatch: {pipeline_key}.{step_id}"
                    )
                try:
                    approved_target = json.loads(target_text)
                except json.JSONDecodeError as exc:
                    raise DirectConnectorRuntimeContractError(
                        f"write approval target text is invalid JSON: {pipeline_key}.{step_id}"
                    ) from exc
                if approved_target != expected_stage["target"]:
                    raise DirectConnectorRuntimeContractError(
                        f"write approval target mismatch: {pipeline_key}.{step_id}"
                    )
        _required_text(receipt.get("completed_at"), "receipt.completed_at")

    if not isinstance(boundaries, Mapping):
        raise DirectConnectorRuntimeContractError("known_boundaries must be an object")
    if boundaries.get("github_main_direct_write") != EXPECTED_GITHUB_MAIN_DIRECT_WRITE:
        raise DirectConnectorRuntimeContractError(
            "github_main_direct_write must preserve the observed protected-main boundary"
        )
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

    contracts = registry["contracts"]
    bridge_contract = contracts["authenticated_session_provider_bridge"]
    direct_contract = contracts["authenticated_chatgpt_direct_runtime"]
    if int(bridge_catalog.get("version", -1)) != int(bridge_contract["source_version"]):
        raise DirectConnectorRuntimeContractError("bridge catalog version does not match registry")
    if int(direct_runtime.get("version", -1)) != int(direct_contract["source_version"]):
        raise DirectConnectorRuntimeContractError("direct runtime version does not match registry")
    if bridge_contract["transport"] != EXPECTED_BRIDGE_TRANSPORT:
        raise DirectConnectorRuntimeContractError("bridge transport identity mismatch")
    if direct_contract["transport"] != direct_runtime["transport"]["name"]:
        raise DirectConnectorRuntimeContractError("direct runtime transport identity mismatch")

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


def validate_connector_transport_admission(
    transport: str,
    *,
    registry_path: Path | None = None,
    bridge_catalog_path: Path | None = None,
    direct_runtime_path: Path | None = None,
) -> DirectRuntimeSummary:
    """Fail closed before a production connector admission or dispatch operation."""
    selected = _required_text(transport, "transport")
    if selected not in {EXPECTED_BRIDGE_TRANSPORT, EXPECTED_DIRECT_TRANSPORT}:
        raise DirectConnectorRuntimeContractError(f"unregistered connector transport: {selected}")
    return reconcile_connector_contracts(
        registry_path=registry_path,
        bridge_catalog_path=bridge_catalog_path,
        direct_runtime_path=direct_runtime_path,
    )
