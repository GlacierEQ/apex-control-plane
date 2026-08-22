"""APEX connector bridge receipt contracts.

This module validates data returned by an authenticated external bridge. It does not
store credentials, invoke provider APIs, or authorize an external action by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


RECEIPT_SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = REPO_ROOT / "config" / "apex_connector_catalog.json"


class ConnectorReceiptError(ValueError):
    """Raised when a bridge receipt or action request cannot be verified."""


@dataclass(frozen=True, slots=True)
class ConnectorCatalog:
    schema_version: int
    catalog_id: str
    version: int
    profiles: Mapping[str, tuple[str, ...]]
    connectors: Mapping[str, Mapping[str, Any]]
    maximum_receipt_age_seconds: int


@dataclass(frozen=True, slots=True)
class ConnectorReadReceipt:
    receipt_id: str
    request_id: str
    connector: str
    operation: str
    profile: str
    target: Mapping[str, Any]
    observed_at: datetime
    content_sha256: str | None
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConnectorActionRequest:
    action_request_id: str
    connector: str
    operation: str
    target: Mapping[str, Any]
    consequence: str
    evidence_refs: tuple[str, ...]
    approved_by: str
    approved_at: datetime
    approval_reference: str


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConnectorReceiptError(f"connector catalog not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConnectorReceiptError(f"invalid connector catalog JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ConnectorReceiptError("connector catalog must be an object")
    return value


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ConnectorReceiptError(f"{field_name} is required")
    return text


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    text = _required_text(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConnectorReceiptError(f"{field_name} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConnectorReceiptError(f"{field_name} must include a timezone")
    return parsed.astimezone(UTC)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _validate_target(value: Any, field_name: str = "target") -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConnectorReceiptError(f"{field_name} must be an object")
    if not any(str(item).strip() for item in value.values()):
        raise ConnectorReceiptError(f"{field_name} requires a provider object reference")
    return dict(value)


def _string_list(value: Any, field_name: str, *, required: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConnectorReceiptError(f"{field_name} must be an array")
    output = tuple(str(item).strip() for item in value if str(item).strip())
    if required and not output:
        raise ConnectorReceiptError(f"{field_name} requires at least one value")
    if len(set(output)) != len(output):
        raise ConnectorReceiptError(f"{field_name} contains duplicates")
    return output


def load_connector_catalog(path: Path | None = None) -> ConnectorCatalog:
    payload = _read_json(path or DEFAULT_CATALOG_PATH)
    try:
        schema_version = int(payload.get("schema_version"))
        version = int(payload.get("version"))
    except (TypeError, ValueError) as exc:
        raise ConnectorReceiptError("catalog schema_version and version must be integers") from exc
    if schema_version != RECEIPT_SCHEMA_VERSION:
        raise ConnectorReceiptError("unsupported connector catalog schema_version")
    if version < 1:
        raise ConnectorReceiptError("catalog version must be positive")

    raw_profiles = payload.get("profiles")
    raw_connectors = payload.get("connectors")
    security = payload.get("security")
    if not isinstance(raw_profiles, Mapping):
        raise ConnectorReceiptError("catalog profiles must be an object")
    if not isinstance(raw_connectors, Mapping) or not raw_connectors:
        raise ConnectorReceiptError("catalog connectors must be a non-empty object")
    if not isinstance(security, Mapping):
        raise ConnectorReceiptError("catalog security must be an object")

    try:
        maximum_age = int(security.get("maximum_receipt_age_seconds"))
    except (TypeError, ValueError) as exc:
        raise ConnectorReceiptError("maximum_receipt_age_seconds must be an integer") from exc
    if maximum_age < 1:
        raise ConnectorReceiptError("maximum_receipt_age_seconds must be positive")
    if security.get("credentials_in_source") is not False:
        raise ConnectorReceiptError("catalog must prohibit credentials in source")
    if security.get("bridge_receipt_required") is not True:
        raise ConnectorReceiptError("catalog must require bridge receipts")
    if security.get("external_write_requires_exact_approval") is not True:
        raise ConnectorReceiptError("catalog must require exact approval for external writes")

    connectors: dict[str, Mapping[str, Any]] = {}
    for raw_name, raw_definition in raw_connectors.items():
        name = _required_text(raw_name, "connector name")
        if not isinstance(raw_definition, Mapping):
            raise ConnectorReceiptError(f"connector {name} definition must be an object")
        _required_text(raw_definition.get("data_class"), f"connector {name}.data_class")
        read_operations = _string_list(
            raw_definition.get("read_operations"),
            f"connector {name}.read_operations",
            required=False,
        )
        write_operations = raw_definition.get("write_operations")
        if not isinstance(write_operations, Mapping):
            raise ConnectorReceiptError(f"connector {name}.write_operations must be an object")
        checked_writes: dict[str, Mapping[str, Any]] = {}
        for raw_operation, raw_rule in write_operations.items():
            operation = _required_text(raw_operation, f"connector {name} write operation")
            if not isinstance(raw_rule, Mapping):
                raise ConnectorReceiptError(f"connector {name}.{operation} must be an object")
            if not isinstance(raw_rule.get("enabled"), bool):
                raise ConnectorReceiptError(f"connector {name}.{operation}.enabled must be boolean")
            if raw_rule.get("approval_required") is not True:
                raise ConnectorReceiptError(
                    f"connector {name}.{operation} must require exact approval"
                )
            if raw_rule.get("idempotency_required") is not True:
                raise ConnectorReceiptError(
                    f"connector {name}.{operation} must require idempotency"
                )
            if raw_rule.get("terminal_readback_required") is not True:
                raise ConnectorReceiptError(
                    f"connector {name}.{operation} must require terminal readback"
                )
            checked_writes[operation] = dict(raw_rule)
        connectors[name] = {
            "data_class": str(raw_definition["data_class"]),
            "read_operations": read_operations,
            "write_operations": checked_writes,
        }

    profiles: dict[str, tuple[str, ...]] = {}
    for raw_profile, raw_members in raw_profiles.items():
        profile = _required_text(raw_profile, "profile name")
        members = _string_list(raw_members, f"profile {profile}")
        unknown = sorted(set(members).difference(connectors))
        if unknown:
            raise ConnectorReceiptError(
                f"profile {profile} names unknown connector(s): {', '.join(unknown)}"
            )
        profiles[profile] = members

    return ConnectorCatalog(
        schema_version=schema_version,
        catalog_id=_required_text(payload.get("catalog_id"), "catalog_id"),
        version=version,
        profiles=profiles,
        connectors=connectors,
        maximum_receipt_age_seconds=maximum_age,
    )


def _connector_definition(catalog: ConnectorCatalog, connector: str) -> Mapping[str, Any]:
    try:
        return catalog.connectors[connector]
    except KeyError as exc:
        raise ConnectorReceiptError(f"connector is not catalogued: {connector}") from exc


def validate_read_receipt(
    payload: Mapping[str, Any],
    catalog: ConnectorCatalog,
    *,
    now: datetime | None = None,
) -> ConnectorReadReceipt:
    if not isinstance(payload, Mapping):
        raise ConnectorReceiptError("read receipt must be an object")
    if payload.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise ConnectorReceiptError("read receipt schema_version is unsupported")
    if payload.get("result_state") != "success":
        raise ConnectorReceiptError("read receipt result_state must be success")
    if payload.get("external_action_authorized") is not False:
        raise ConnectorReceiptError("read receipt must be non-authorizing")

    connector = _required_text(payload.get("connector"), "connector")
    operation = _required_text(payload.get("operation"), "operation")
    profile = _required_text(payload.get("profile"), "profile")
    definition = _connector_definition(catalog, connector)
    if operation not in definition["read_operations"]:
        raise ConnectorReceiptError(f"read operation is not allowed: {connector}.{operation}")
    if profile not in catalog.profiles or connector not in catalog.profiles[profile]:
        raise ConnectorReceiptError(f"connector {connector} is not active in profile {profile}")

    observed_at = _parse_timestamp(payload.get("observed_at"), "observed_at")
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ConnectorReceiptError("now must include a timezone")
    age_seconds = (current.astimezone(UTC) - observed_at).total_seconds()
    if age_seconds < -300:
        raise ConnectorReceiptError("read receipt observed_at is materially in the future")
    if age_seconds > catalog.maximum_receipt_age_seconds:
        raise ConnectorReceiptError("read receipt is stale")

    digest_value = payload.get("content_sha256")
    content_sha256: str | None
    if digest_value is None:
        content_sha256 = None
    else:
        content_sha256 = _required_text(digest_value, "content_sha256")
        if not _is_sha256(content_sha256):
            raise ConnectorReceiptError("content_sha256 must be a 64-character lowercase hex digest")

    return ConnectorReadReceipt(
        receipt_id=_required_text(payload.get("receipt_id"), "receipt_id"),
        request_id=_required_text(payload.get("request_id"), "request_id"),
        connector=connector,
        operation=operation,
        profile=profile,
        target=_validate_target(payload.get("target")),
        observed_at=observed_at,
        content_sha256=content_sha256,
        source_refs=_string_list(payload.get("source_refs"), "source_refs"),
    )


def validate_action_request(
    payload: Mapping[str, Any],
    catalog: ConnectorCatalog,
) -> ConnectorActionRequest:
    if not isinstance(payload, Mapping):
        raise ConnectorReceiptError("action request must be an object")
    if payload.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise ConnectorReceiptError("action request schema_version is unsupported")

    connector = _required_text(payload.get("connector"), "connector")
    operation = _required_text(payload.get("operation"), "operation")
    definition = _connector_definition(catalog, connector)
    write_rule = definition["write_operations"].get(operation)
    if write_rule is None:
        raise ConnectorReceiptError(f"write operation is not catalogued: {connector}.{operation}")
    if write_rule.get("enabled") is not True:
        raise ConnectorReceiptError(f"write operation is inactive: {connector}.{operation}")
    if write_rule.get("approval_required") is not True:
        raise ConnectorReceiptError(f"write operation lacks exact approval rule: {connector}.{operation}")

    approval = payload.get("approval")
    if not isinstance(approval, Mapping):
        raise ConnectorReceiptError("action request approval must be an object")

    return ConnectorActionRequest(
        action_request_id=_required_text(payload.get("action_request_id"), "action_request_id"),
        connector=connector,
        operation=operation,
        target=_validate_target(payload.get("target")),
        consequence=_required_text(payload.get("consequence"), "consequence"),
        evidence_refs=_string_list(payload.get("evidence_refs"), "evidence_refs"),
        approved_by=_required_text(approval.get("approved_by"), "approval.approved_by"),
        approved_at=_parse_timestamp(approval.get("approved_at"), "approval.approved_at"),
        approval_reference=_required_text(
            approval.get("approval_reference"), "approval.approval_reference"
        ),
    )


def receipt_audit_details(receipt: ConnectorReadReceipt) -> dict[str, Any]:
    """Return safe metadata for APEX audit records without raw provider content."""
    return {
        "receipt_id": receipt.receipt_id,
        "request_id": receipt.request_id,
        "connector": receipt.connector,
        "operation": receipt.operation,
        "profile": receipt.profile,
        "observed_at": receipt.observed_at.isoformat().replace("+00:00", "Z"),
        "target_sha256": canonical_sha256(receipt.target),
        "content_sha256": receipt.content_sha256,
        "source_ref_count": len(receipt.source_refs),
        "external_action_authorized": False,
    }
