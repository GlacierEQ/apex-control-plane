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
    if completion_ready(g):
        return Status.COMPLETE
    if not execution_ready(g):
        return Status.BLOCKED if exact_blockers else Status.RECOVERING
    return Status.EXECUTING


def from_mapping(data: Mapping[str, object]) -> GateState:
    allowed = {f.name for f in fields(GateState)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown Jack gate(s): {sorted(unknown)}")
    return GateState(**{name: bool(data.get(name, False)) for name in allowed})


def validate_receipt(receipt: Mapping[str, object]) -> None:
    """Reject structurally incomplete or logically false execution receipts."""
    if receipt.get("contract_id") != CONTRACT_ID:
        raise ValueError("wrong or missing contract_id")
    if receipt.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("wrong or missing contract_version")

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

    gates = GateState(**{name: bool(raw_gates[name]) for name in allowed})
    try:
        status = Status(str(receipt.get("status", "")))
    except ValueError as exc:
        raise ValueError("invalid receipt status") from exc

    blockers = receipt.get("exact_blockers", [])
    if not isinstance(blockers, list):
        raise ValueError("exact_blockers must be a list")

    expected = evaluate(gates, exact_blockers=[str(v) for v in blockers if str(v).strip()])
    if status is not expected:
        raise ValueError(f"receipt status {status.value} contradicts gate state; expected {expected.value}")
    if status is Status.COMPLETE and not completion_ready(gates):
        raise ValueError("COMPLETE requires every completion gate")
    if status is Status.EXECUTING and not execution_ready(gates):
        raise ValueError("EXECUTING requires every preflight gate")
    if status is Status.BLOCKED and not blockers:
        raise ValueError("BLOCKED requires at least one exact blocker")


def assert_completion(g: GateState) -> None:
    gaps = missing(g)
    if gaps:
        raise RuntimeError("Jack completion claim blocked; missing gates: " + ", ".join(gaps))
