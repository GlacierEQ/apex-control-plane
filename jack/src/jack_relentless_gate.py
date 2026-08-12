"""Fail-closed Jack the Ripper relentless-execution contract evaluator."""
from __future__ import annotations
from dataclasses import dataclass, fields
from enum import Enum
from typing import Mapping

CONTRACT_ID = "JTR-RELENTLESS-EXECUTION-v1"
CONTRACT_VERSION = "1.0.0"

class Status(str, Enum):
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

PRE_FLIGHT = ['authority_valid', 'safety_boundary_clear', 'continuity_loaded', 'resources_invoked', 'existing_work_checked', 'canonical_owner_resolved', 'objective_preserved', 'required_sources_opened']
COMPLETION = ['authority_valid', 'safety_boundary_clear', 'continuity_loaded', 'resources_invoked', 'existing_work_checked', 'canonical_owner_resolved', 'objective_preserved', 'required_sources_opened', 'contradictions_preserved', 'highest_value_delta_selected', 'material_action_executed', 'verification_passed', 'defects_repaired_or_exactly_blocked', 'persistence_written', 'readback_verified', 'next_state_resumable']
RESUME = ['continuity_loaded', 'canonical_owner_resolved', 'persistence_written', 'readback_verified', 'next_state_resumable']

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
    if exact_blockers and not execution_ready(g):
        return Status.BLOCKED
    return Status.EXECUTING

def from_mapping(data: Mapping[str, object]) -> GateState:
    allowed = {f.name for f in fields(GateState)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown Jack gate(s): {sorted(unknown)}")
    return GateState(**{name: bool(data.get(name, False)) for name in allowed})

def assert_completion(g: GateState) -> None:
    gaps = missing(g)
    if gaps:
        raise RuntimeError("Jack completion claim blocked; missing gates: " + ", ".join(gaps))
