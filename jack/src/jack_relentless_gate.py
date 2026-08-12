"""Fail-closed Jack the Ripper relentless-execution contract evaluator."""
from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Mapping

CONTRACT_ID = "JTR-RELENTLESS-EXECUTION-v1"
CONTRACT_VERSION = "1.0.0"


class Status(str, Enum):
    RECOVERING = "RECOVERING"
    EXECUTING = "EXECUTING"
    BLOCKED = "BLOCKED"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class GateState:
    authority_valid: bool = False
    safety_boundary_clear: bool = False
    continuity_loaded: bool = False
    resources_invoked: bool = False
    existing_work_checked: bool = False
    canonical_owner_resolved: bool = False
    objective_preserved: bool = False
    required_sources_opened: bool = False
    contradictions_preserved: bool = False
    highest_value_delta_selected: bool = False
    material_action_executed: bool = False
    verification_passed: bool = False
    defects_repaired_or_exactly_blocked: bool = False
    persistence_written: bool = False
    readback_verified: bool = False
    next_state_resumable: bool = False


PRE_FLIGHT = [
    "authority_valid",
    "safety_boundary_clear",
    "continuity_loaded",
    "resources_invoked",
    "existing_work_checked",
    "canonical_owner_resolved",
    "objective_preserved",
    "required_sources_opened",
]
COMPLETION = list(GateState.__dataclass_fields__)
RESUME = [
    "continuity_loaded",
    "canonical_owner_resolved",
    "persistence_written",
    "readback_verified",
    "next_state_resumable",
]


def _all(g: GateState, names: list[str]) -> bool:
    return all(bool(getattr(g, name)) for name in names)


def execution_ready(g: GateState) -> bool:
    return _all(g, PRE_FLIGHT)


def completion_ready(g: GateState) -> bool:
    return _all(g, COMPLETION)


def resume_ready(g: GateState) -> bool:
    return _all(g, RESUME)


def missing(g: GateState, names: list[str] = COMPLETION) -> list[str]:
    return [name for name in names if not bool(getattr(g, name))]


def evaluate(g: GateState, *, exact_blockers: list[str] | None = None) -> Status:
    blockers = [str(value).strip() for value in (exact_blockers or []) if str(value).strip()]
    if blockers:
        return Status.BLOCKED
    if completion_ready(g):
        return Status.COMPLETE
    if not execution_ready(g):
        return Status.RECOVERING
    return Status.EXECUTING


def from_mapping(data: Mapping[str, object]) -> GateState:
    allowed = {f.name for f in fields(GateState)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown Jack gate(s): {sorted(unknown)}")
    values: dict[str, bool] = {}
    for name in allowed:
        value = data.get(name, False)
        if type(value) is not bool:
            raise ValueError(f"Jack gate {name!r} must be a bool")
        values[name] = value
    return GateState(**values)


def _receipt_list(receipt: Mapping[str, object], name: str) -> list[object]:
    value = receipt.get(name)
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _nonempty_string(receipt: Mapping[str, object], name: str) -> str:
    value = receipt.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def validate_receipt(receipt: Mapping[str, object]) -> None:
    """Reject structurally incomplete or logically false execution receipts."""
    if receipt.get("contract_id") != CONTRACT_ID:
        raise ValueError("wrong or missing contract_id")
    if receipt.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("wrong or missing contract_version")

    for name in ("task", "objective", "canonical_owner", "next_material_action"):
        _nonempty_string(receipt, name)

    raw_gates = receipt.get("gates")
    if not isinstance(raw_gates, Mapping):
        raise ValueError("receipt.gates must be a fixed gate mapping")
    allowed = set(GateState.__dataclass_fields__)
    if set(raw_gates) != allowed:
        missing_names = sorted(allowed - set(raw_gates))
        unknown_names = sorted(set(raw_gates) - allowed)
        raise ValueError(
            f"receipt.gates must contain exactly 16 gates; missing={missing_names}, unknown={unknown_names}"
        )

    gates = from_mapping(raw_gates)
    try:
        status = Status(str(receipt.get("status", "")))
    except ValueError as exc:
        raise ValueError("invalid receipt status") from exc

    blockers = _receipt_list(receipt, "exact_blockers")
    normalized_blockers = [str(v).strip() for v in blockers if str(v).strip()]
    resolved_blockers = receipt.get("resolved_blockers", [])
    if not isinstance(resolved_blockers, list):
        raise ValueError("resolved_blockers must be a list when present")

    sources = _receipt_list(receipt, "sources_opened")
    actions = _receipt_list(receipt, "actions_executed")
    verification = _receipt_list(receipt, "verification")
    persistence = _receipt_list(receipt, "persistence_receipts")
    readback = _receipt_list(receipt, "readback_receipts")

    if (gates.resources_invoked or gates.required_sources_opened) and not any(
        isinstance(row, Mapping) and row.get("opened") is True for row in sources
    ):
        raise ValueError("resource/source gates require at least one opened source receipt")

    if gates.material_action_executed and not any(
        isinstance(row, Mapping) and row.get("executed") is True for row in actions
    ):
        raise ValueError("material_action_executed requires an executed action receipt")

    if gates.verification_passed and not any(
        isinstance(row, Mapping)
        and row.get("passed") is True
        and isinstance(row.get("receipt_ref"), str)
        and bool(row.get("receipt_ref", "").strip())
        for row in verification
    ):
        raise ValueError("verification_passed requires a passed verification receipt")

    if gates.persistence_written and not any(isinstance(v, str) and v.strip() for v in persistence):
        raise ValueError("persistence_written requires persistence_receipts")

    if gates.readback_verified and not any(isinstance(v, str) and v.strip() for v in readback):
        raise ValueError("readback_verified requires readback_receipts")

    expected = evaluate(gates, exact_blockers=normalized_blockers)
    if status is not expected:
        raise ValueError(f"receipt status {status.value} contradicts gate state; expected {expected.value}")
    if status is Status.COMPLETE and not completion_ready(gates):
        raise ValueError("COMPLETE requires every completion gate")
    if status is Status.EXECUTING and not execution_ready(gates):
        raise ValueError("EXECUTING requires every preflight gate")
    if status is Status.BLOCKED and not normalized_blockers:
        raise ValueError("BLOCKED requires at least one exact blocker")


def assert_completion(g: GateState) -> None:
    gaps = missing(g)
    if gaps:
        raise RuntimeError("Jack completion claim blocked; missing gates: " + ", ".join(gaps))
