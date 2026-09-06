"""Exact-approval contracts for authenticated APEX connector operations.

This module never loads credentials, executes a provider call, or stores provider input or
output in an audit receipt.  It validates an operator's immutable action scope, evaluates
mutation readiness, and turns host-side execution and readback observations into safe,
digest-only receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Mapping
from uuid import uuid4

from connector_receipts import (
    ConnectorCatalog,
    ConnectorReceiptError,
    canonical_json,
    canonical_sha256,
    validate_action_request,
)
from epistemic_risk_gate import (
    BlastRadius,
    CompletionEvidence,
    EpistemicState,
    ExecutionEvidence,
    Reversibility,
    evaluate_execution,
    validate_completion_claim,
)


class ApprovedOperationError(ValueError):
    """Raised when an exact provider-operation approval is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class ApprovedConnectorAction:
    """One catalogued provider operation bound to one exact operator approval."""

    action_request_id: str
    connector: str
    operation: str
    target: Mapping[str, Any]
    provider_input: Mapping[str, Any]
    consequence: str
    evidence_refs: tuple[str, ...]
    idempotency_key: str
    approved_by: str
    approved_at: datetime
    approval_reference: str
    approval_scope_sha256: str
    execution_evidence: ExecutionEvidence


@dataclass(frozen=True, slots=True)
class ProviderExecutionObservation:
    """Host-held material for one executed provider action or terminal readback."""

    source_refs: tuple[str, ...]
    material: str | bytes | None
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.source_refs:
            raise ApprovedOperationError(
                "provider execution observation requires a source reference"
            )
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ApprovedOperationError(
                "provider execution observation time must include a timezone"
            )


@dataclass(frozen=True, slots=True)
class ConnectorExecutionReceipt:
    """Validated digest-only evidence that one approved provider action was attempted."""

    execution_receipt_id: str
    action_request_id: str
    connector: str
    operation: str
    idempotency_key: str
    approval_scope_sha256: str
    result_state: str
    verification_passed: bool
    executed_at: datetime
    result_target: Mapping[str, Any]
    execution_content_sha256: str | None
    execution_source_refs: tuple[str, ...]
    readback_at: datetime | None
    readback_content_sha256: str | None
    readback_source_refs: tuple[str, ...]


def _text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ApprovedOperationError(f"{name} is required")
    return text


def _mapping(
    value: Any, name: str, *, required_values: bool = True
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ApprovedOperationError(f"{name} must be an object")
    output = dict(value)
    if required_values and not any(str(item).strip() for item in output.values()):
        raise ApprovedOperationError(f"{name} requires at least one value")
    return output


def _refs(value: Any, name: str, *, required: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ApprovedOperationError(f"{name} must be an array")
    refs = tuple(str(item).strip() for item in value if str(item).strip())
    if required and not refs:
        raise ApprovedOperationError(f"{name} requires at least one source reference")
    if len(set(refs)) != len(refs):
        raise ApprovedOperationError(f"{name} contains duplicates")
    return refs


def _parse_time(value: Any, name: str) -> datetime:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApprovedOperationError(f"{name} must be RFC3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ApprovedOperationError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _content_sha256(material: str | bytes | None) -> str | None:
    if material is None:
        return None
    raw = material.encode("utf-8") if isinstance(material, str) else material
    return sha256(raw).hexdigest()


def action_scope_payload(
    *,
    connector: str,
    operation: str,
    target: Mapping[str, Any],
    provider_input: Mapping[str, Any],
    consequence: str,
    evidence_refs: tuple[str, ...],
    idempotency_key: str,
) -> dict[str, Any]:
    """Return the immutable values to which an operator approval must bind."""
    return {
        "connector": connector,
        "operation": operation,
        "target": dict(target),
        "provider_input_sha256": canonical_sha256(provider_input),
        "consequence": consequence,
        "evidence_refs": sorted(evidence_refs),
        "idempotency_key": idempotency_key,
    }


def action_scope_sha256(**kwargs: Any) -> str:
    """Return the immutable exact-approval digest for one proposed provider action."""
    return canonical_sha256(action_scope_payload(**kwargs))


def _execution_evidence(value: Any) -> ExecutionEvidence:
    raw = _mapping(value, "execution_evidence")
    try:
        return ExecutionEvidence(
            operation=_text(raw.get("operation"), "execution_evidence.operation"),
            epistemic_state=EpistemicState(
                _text(raw.get("epistemic_state"), "execution_evidence.epistemic_state")
            ),
            blast_radius=BlastRadius(int(raw.get("blast_radius"))),
            reversibility=Reversibility(int(raw.get("reversibility"))),
            source_state_observed=raw.get("source_state_observed") is True,
            dependency_map_observed=raw.get("dependency_map_observed") is True,
            recovery_checkpoint_verified=raw.get("recovery_checkpoint_verified")
            is True,
            recovery_procedure_verified=raw.get("recovery_procedure_verified") is True,
            dry_run_verified=raw.get("dry_run_verified") is True,
            staged_execution=raw.get("staged_execution") is True,
            novel_operation=raw.get("novel_operation") is True,
            operator_explicit_irreversible_authorization=(
                raw.get("operator_explicit_irreversible_authorization") is True
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ApprovedOperationError(
            "execution_evidence contains an unsupported safety value"
        ) from exc


def validate_approved_action_request(
    payload: Mapping[str, Any],
    catalog: ConnectorCatalog,
    *,
    now: datetime | None = None,
) -> ApprovedConnectorAction:
    """Validate one active catalogued mutation with exact scope and readiness evidence."""
    try:
        base = validate_action_request(payload, catalog)
    except ConnectorReceiptError as exc:
        raise ApprovedOperationError(str(exc)) from exc

    write_rule = catalog.connectors[base.connector]["write_operations"][base.operation]
    if write_rule.get("idempotency_required") is not True:
        raise ApprovedOperationError(
            "catalogued provider operation lacks idempotency enforcement"
        )
    if write_rule.get("terminal_readback_required") is not True:
        raise ApprovedOperationError(
            "catalogued provider operation lacks terminal readback enforcement"
        )

    provider_input = _mapping(payload.get("provider_input"), "provider_input")
    idempotency_key = _text(payload.get("idempotency_key"), "idempotency_key")
    execution_evidence = _execution_evidence(payload.get("execution_evidence"))
    expected_scope = action_scope_sha256(
        connector=base.connector,
        operation=base.operation,
        target=base.target,
        provider_input=provider_input,
        consequence=base.consequence,
        evidence_refs=base.evidence_refs,
        idempotency_key=idempotency_key,
    )
    approval = _mapping(payload.get("approval"), "approval")
    supplied_scope = _text(
        approval.get("approval_scope_sha256"), "approval.approval_scope_sha256"
    )
    if not _is_sha256(supplied_scope):
        raise ApprovedOperationError(
            "approval.approval_scope_sha256 must be a lowercase SHA-256 digest"
        )
    if supplied_scope != expected_scope:
        raise ApprovedOperationError(
            "approval scope does not match the immutable action request"
        )

    current = now.astimezone(UTC) if now is not None else None
    if current is not None:
        age_seconds = (current - base.approved_at).total_seconds()
        if age_seconds < -300:
            raise ApprovedOperationError(
                "approval.approved_at is materially in the future"
            )
        if age_seconds > catalog.maximum_receipt_age_seconds:
            raise ApprovedOperationError(
                "approval is stale for the current connector policy"
            )

    readiness = evaluate_execution(execution_evidence)
    if not readiness.allowed:
        reasons = "; ".join(readiness.reasons) or readiness.decision.value
        raise ApprovedOperationError(
            f"provider operation is not ready for execution: {reasons}"
        )
    if execution_evidence.operation != f"{base.connector}.{base.operation}":
        raise ApprovedOperationError(
            "execution_evidence.operation must match the requested provider operation"
        )

    return ApprovedConnectorAction(
        action_request_id=base.action_request_id,
        connector=base.connector,
        operation=base.operation,
        target=base.target,
        provider_input=provider_input,
        consequence=base.consequence,
        evidence_refs=base.evidence_refs,
        idempotency_key=idempotency_key,
        approved_by=base.approved_by,
        approved_at=base.approved_at,
        approval_reference=base.approval_reference,
        approval_scope_sha256=supplied_scope,
        execution_evidence=execution_evidence,
    )


def action_audit_scope(action: ApprovedConnectorAction) -> dict[str, Any]:
    """Return only digest-safe action metadata for ledgers and logs."""
    return {
        "action_request_id": action.action_request_id,
        "connector": action.connector,
        "operation": action.operation,
        "target_sha256": canonical_sha256(action.target),
        "provider_input_sha256": canonical_sha256(action.provider_input),
        "consequence_sha256": sha256(action.consequence.encode("utf-8")).hexdigest(),
        "evidence_ref_count": len(action.evidence_refs),
        "idempotency_key": action.idempotency_key,
        "approval_reference": action.approval_reference,
        "approval_scope_sha256": action.approval_scope_sha256,
        "external_action_authorized": True,
    }


def build_execution_receipt(
    *,
    action: ApprovedConnectorAction,
    execution: ProviderExecutionObservation,
    result_target: Mapping[str, Any],
    readback: ProviderExecutionObservation | None,
    verification_passed: bool,
    result_state: str = "success",
    execution_receipt_id: str | None = None,
) -> dict[str, Any]:
    """Build a digest-only provider execution receipt after a host action and readback."""
    state = _text(result_state, "result_state")
    if state not in {"success", "failure"}:
        raise ApprovedOperationError("result_state must be success or failure")
    if not isinstance(verification_passed, bool):
        raise ApprovedOperationError("verification_passed must be boolean")
    if state == "success" and readback is None:
        raise ApprovedOperationError(
            "successful provider execution requires terminal readback"
        )
    if state == "success" and not verification_passed:
        raise ApprovedOperationError(
            "successful provider execution requires verified terminal readback"
        )
    target = _mapping(result_target, "result_target")
    executed_at = execution.observed_at.astimezone(UTC)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "execution_receipt_id": execution_receipt_id or str(uuid4()),
        "action_request_id": action.action_request_id,
        "connector": action.connector,
        "operation": action.operation,
        "idempotency_key": action.idempotency_key,
        "approval_scope_sha256": action.approval_scope_sha256,
        "result_state": state,
        "executed_at": executed_at.isoformat().replace("+00:00", "Z"),
        "result_target": dict(target),
        "execution_content_sha256": _content_sha256(execution.material),
        "execution_source_refs": list(execution.source_refs),
        "verification_passed": verification_passed,
        "external_action_authorized": True,
    }
    if readback is not None:
        observed = readback.observed_at.astimezone(UTC)
        payload.update(
            {
                "readback_at": observed.isoformat().replace("+00:00", "Z"),
                "readback_content_sha256": _content_sha256(readback.material),
                "readback_source_refs": list(readback.source_refs),
            }
        )
    else:
        payload.update(
            {
                "readback_at": None,
                "readback_content_sha256": None,
                "readback_source_refs": [],
            }
        )
    return payload


def validate_execution_receipt(
    payload: Mapping[str, Any],
    action: ApprovedConnectorAction,
) -> ConnectorExecutionReceipt:
    """Validate receipt scope and completion evidence without retaining provider material."""
    if not isinstance(payload, Mapping):
        raise ApprovedOperationError("execution receipt must be an object")
    if payload.get("schema_version") != 1:
        raise ApprovedOperationError("execution receipt schema_version is unsupported")
    if payload.get("external_action_authorized") is not True:
        raise ApprovedOperationError(
            "execution receipt must record an exact approved action"
        )
    for field, expected in (
        ("action_request_id", action.action_request_id),
        ("connector", action.connector),
        ("operation", action.operation),
        ("idempotency_key", action.idempotency_key),
        ("approval_scope_sha256", action.approval_scope_sha256),
    ):
        if _text(payload.get(field), f"execution receipt {field}") != expected:
            raise ApprovedOperationError(
                f"execution receipt {field} does not match the approved action"
            )

    state = _text(payload.get("result_state"), "execution receipt result_state")
    if state not in {"success", "failure"}:
        raise ApprovedOperationError(
            "execution receipt result_state must be success or failure"
        )
    executed_at = _parse_time(
        payload.get("executed_at"), "execution receipt executed_at"
    )
    result_target = _mapping(
        payload.get("result_target"), "execution receipt result_target"
    )
    execution_refs = _refs(
        payload.get("execution_source_refs"), "execution receipt execution_source_refs"
    )
    execution_digest = payload.get("execution_content_sha256")
    if execution_digest is not None and (
        not isinstance(execution_digest, str) or not _is_sha256(execution_digest)
    ):
        raise ApprovedOperationError(
            "execution receipt execution_content_sha256 is invalid"
        )

    readback_refs = _refs(
        payload.get("readback_source_refs"),
        "execution receipt readback_source_refs",
        required=state == "success",
    )
    readback_at_raw = payload.get("readback_at")
    readback_at = (
        None
        if readback_at_raw is None
        else _parse_time(readback_at_raw, "execution receipt readback_at")
    )
    readback_digest = payload.get("readback_content_sha256")
    if readback_digest is not None and (
        not isinstance(readback_digest, str) or not _is_sha256(readback_digest)
    ):
        raise ApprovedOperationError(
            "execution receipt readback_content_sha256 is invalid"
        )
    verification_passed = payload.get("verification_passed")
    if not isinstance(verification_passed, bool):
        raise ApprovedOperationError(
            "execution receipt verification_passed must be boolean"
        )
    if state == "success" and readback_at is None:
        raise ApprovedOperationError(
            "successful execution receipt requires readback_at"
        )
    if state == "success" and not verification_passed:
        raise ApprovedOperationError(
            "successful execution receipt requires verified terminal readback"
        )
    if readback_at is not None and readback_at < executed_at:
        raise ApprovedOperationError(
            "execution receipt readback precedes the provider action"
        )
    if state == "success":
        completion_errors = validate_completion_claim(
            evidence=CompletionEvidence(
                execution_receipt=True,
                terminal_readback=True,
                verification_passed=verification_passed,
                active_operations=0,
            )
        )
        if completion_errors:
            raise ApprovedOperationError("; ".join(completion_errors))

    return ConnectorExecutionReceipt(
        execution_receipt_id=_text(
            payload.get("execution_receipt_id"), "execution_receipt_id"
        ),
        action_request_id=action.action_request_id,
        connector=action.connector,
        operation=action.operation,
        idempotency_key=action.idempotency_key,
        approval_scope_sha256=action.approval_scope_sha256,
        result_state=state,
        verification_passed=verification_passed,
        executed_at=executed_at,
        result_target=result_target,
        execution_content_sha256=execution_digest,
        execution_source_refs=execution_refs,
        readback_at=readback_at,
        readback_content_sha256=readback_digest,
        readback_source_refs=readback_refs,
    )


def execution_receipt_audit_details(
    receipt: ConnectorExecutionReceipt,
    action: ApprovedConnectorAction,
) -> dict[str, Any]:
    """Return execution metadata without raw provider request or response material."""
    details = action_audit_scope(action)
    details.update(
        {
            "execution_receipt_id": receipt.execution_receipt_id,
            "result_state": receipt.result_state,
            "executed_at": receipt.executed_at.isoformat().replace("+00:00", "Z"),
            "result_target_sha256": canonical_sha256(receipt.result_target),
            "execution_content_sha256": receipt.execution_content_sha256,
            "execution_source_ref_count": len(receipt.execution_source_refs),
            "readback_at": (
                receipt.readback_at.isoformat().replace("+00:00", "Z")
                if receipt.readback_at is not None
                else None
            ),
            "readback_content_sha256": receipt.readback_content_sha256,
            "readback_source_ref_count": len(receipt.readback_source_refs),
            "verification_passed": receipt.verification_passed,
            "external_action_authorized": True,
        }
    )
    return details


def render_safe_execution_receipt(receipt: Mapping[str, Any]) -> str:
    """Serialize a validated receipt; the provider material is never accepted here."""
    return canonical_json(receipt) + "\n"
