"""Authenticated-session execution helpers for the APEX connector bridge.

This module holds no provider credentials and performs no network access by itself. A
session-specific dispatcher may execute a catalogued read through an authenticated
provider integration, then use these helpers to construct a receipt that APEX can
validate and admit to its audit ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Mapping
from uuid import uuid4

from connector_bridge_contract import build_read_request
from connector_receipts import (
    ConnectorCatalog,
    ConnectorReadReceipt,
    ConnectorReceiptError,
    canonical_json,
    validate_read_receipt,
)


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    """A read-only provider result kept in memory until its digest is recorded."""

    source_refs: tuple[str, ...]
    material: str | bytes | None
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.source_refs:
            raise ConnectorReceiptError("provider observation requires a source reference")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ConnectorReceiptError("provider observation time must include a timezone")


def content_sha256(material: str | bytes | None) -> str | None:
    """Return a digest without retaining the provider material in the receipt."""
    if material is None:
        return None
    payload = material.encode("utf-8") if isinstance(material, str) else material
    return sha256(payload).hexdigest()


def build_catalogued_read_request(
    *,
    connector: str,
    operation: str,
    profile: str,
    target: Mapping[str, Any],
    catalog: ConnectorCatalog,
    requested_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the exact non-authorizing request consumed by a session dispatcher."""
    return build_read_request(
        connector=connector,
        operation=operation,
        profile=profile,
        target=target,
        catalog=catalog,
        requested_at=requested_at,
    )


def build_read_receipt(
    *,
    request: Mapping[str, Any],
    observation: ProviderObservation,
    catalog: ConnectorCatalog,
    receipt_id: str | None = None,
) -> dict[str, Any]:
    """Build and validate a non-authorizing receipt from one provider observation."""
    required_request_fields = ("request_id", "connector", "operation", "profile", "target")
    missing = [field for field in required_request_fields if not request.get(field)]
    if missing:
        raise ConnectorReceiptError(f"read request missing field(s): {', '.join(missing)}")
    if request.get("external_action_authorized") is not False:
        raise ConnectorReceiptError("read request must remain non-authorizing")

    observed_at = observation.observed_at.astimezone(UTC)
    payload = {
        "schema_version": catalog.schema_version,
        "receipt_id": receipt_id or str(uuid4()),
        "request_id": str(request["request_id"]),
        "connector": str(request["connector"]),
        "operation": str(request["operation"]),
        "profile": str(request["profile"]),
        "target": dict(request["target"]),
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "content_sha256": content_sha256(observation.material),
        "source_refs": list(observation.source_refs),
        "result_state": "success",
        "external_action_authorized": False,
    }
    validate_read_receipt(payload, catalog, now=observed_at)
    return payload


def receipt_fingerprint(receipt: Mapping[str, Any]) -> str:
    """Provide a stable reference for evidence ledgers without provider content."""
    return sha256(canonical_json(receipt).encode("utf-8")).hexdigest()


def validate_built_receipt(
    receipt: Mapping[str, Any], catalog: ConnectorCatalog, *, now: datetime | None = None
) -> ConnectorReadReceipt:
    """Validate a bridge-produced receipt before runtime admission."""
    return validate_read_receipt(receipt, catalog, now=now)
