"""Mission-level fidelity admission: structured scope, correction and cursor proof.

This validates host-supplied evidence; it cannot independently attest to
the truth of a provider receipt or install itself in the ChatGPT host.
"""
from __future__ import annotations

class FidelityViolation(ValueError):
    pass

def _strings(value, field):
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise FidelityViolation(f"invalid {field}")
    if len(set(value)) != len(value):
        raise FidelityViolation(f"duplicate {field}")
    return list(value)

def assess_mission_fidelity(intent: dict, execution: dict) -> dict:
    """Reject false completion, expose remaining scope, and require applied corrections."""
    if not isinstance(intent, dict) or not isinstance(execution, dict):
        raise FidelityViolation("intent and execution must be structured records")
    mission_id = intent.get("mission_id")
    if not isinstance(mission_id, str) or not mission_id.strip() or execution.get("mission_id") != mission_id:
        raise FidelityViolation("mission identity mismatch")
    cursor = intent.get("cursor")
    if not isinstance(cursor, str) or not cursor.strip() or execution.get("cursor") != cursor:
        raise FidelityViolation("continuation cursor mismatch")
    required = _strings(intent.get("required_lanes"), "required lanes")
    if not required:
        raise FidelityViolation("empty required coverage")
    corrections = _strings(intent.get("correction_ids"), "required corrections")
    applied = _strings(execution.get("applied_correction_ids"), "applied corrections")
    missing_corrections = [c for c in corrections if c not in applied]
    if missing_corrections:
        raise FidelityViolation("unapplied correction: " + ", ".join(missing_corrections))
    completed = _strings(execution.get("completed_lanes"), "completed lanes")
    if any(lane not in required for lane in completed):
        raise FidelityViolation("unrecognized completed coverage")
    refs = _strings(execution.get("evidence_refs"), "evidence references")
    if completed and not refs:
        raise FidelityViolation("completed work requires evidence references")
    remaining = [lane for lane in required if lane not in completed]
    claim = execution.get("claimed_complete")
    if not isinstance(claim, bool):
        raise FidelityViolation("claimed_complete must be boolean")
    if claim and remaining:
        raise FidelityViolation("incomplete mission coverage: " + ", ".join(remaining))
    if claim and not refs:
        raise FidelityViolation("completion requires evidence")
    return {"mission_id": mission_id, "status": "COMPLETE" if claim and not remaining else "PARTIAL", "completed_lanes": completed, "remaining_lanes": remaining, "applied_correction_ids": applied, "cursor": cursor}
