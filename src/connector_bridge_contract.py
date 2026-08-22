"""Non-network request contracts for the APEX authenticated connector bridge."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

from connector_receipts import ConnectorCatalog, ConnectorReceiptError


def build_read_request(
    *,
    connector: str,
    operation: str,
    profile: str,
    target: Mapping[str, Any],
    catalog: ConnectorCatalog,
    requested_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a non-authorizing request for a catalogued external read operation."""
    if connector not in catalog.connectors:
        raise ConnectorReceiptError(f"connector is not catalogued: {connector}")
    if profile not in catalog.profiles or connector not in catalog.profiles[profile]:
        raise ConnectorReceiptError(f"connector {connector} is not active in profile {profile}")
    if operation not in catalog.connectors[connector]["read_operations"]:
        raise ConnectorReceiptError(f"read operation is not allowed: {connector}.{operation}")
    if not isinstance(target, Mapping) or not any(str(value).strip() for value in target.values()):
        raise ConnectorReceiptError("target requires a provider object reference")

    moment = (requested_at or datetime.now(UTC)).astimezone(UTC)
    return {
        "schema_version": catalog.schema_version,
        "request_id": str(uuid4()),
        "connector": connector,
        "operation": operation,
        "profile": profile,
        "target": dict(target),
        "requested_at": moment.isoformat().replace("+00:00", "Z"),
        "external_action_authorized": False,
    }


def build_action_proposal(
    *,
    connector: str,
    operation: str,
    target: Mapping[str, Any],
    consequence: str,
    evidence_refs: list[str],
    catalog: ConnectorCatalog,
) -> dict[str, Any]:
    """Describe a possible write without treating the proposal as an authorization."""
    if connector not in catalog.connectors:
        raise ConnectorReceiptError(f"connector is not catalogued: {connector}")
    if operation not in catalog.connectors[connector]["write_operations"]:
        raise ConnectorReceiptError(f"write operation is not catalogued: {connector}.{operation}")
    if not isinstance(target, Mapping) or not any(str(value).strip() for value in target.values()):
        raise ConnectorReceiptError("target requires a provider object reference")
    if not str(consequence).strip():
        raise ConnectorReceiptError("consequence is required")
    refs = [str(value).strip() for value in evidence_refs if str(value).strip()]
    if not refs:
        raise ConnectorReceiptError("evidence_refs requires at least one receipt reference")

    rule = catalog.connectors[connector]["write_operations"][operation]
    return {
        "schema_version": catalog.schema_version,
        "proposal_id": str(uuid4()),
        "connector": connector,
        "operation": operation,
        "target": dict(target),
        "consequence": str(consequence).strip(),
        "evidence_refs": refs,
        "operation_active": rule["enabled"],
        "approval_required": rule["approval_required"],
        "external_action_authorized": False,
    }
