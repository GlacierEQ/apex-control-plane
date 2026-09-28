"""Evidence-gated escalation pressure for APEX action selection.

"Prosecution" is an execution mode, not a rhetorical intensity setting. The
system may increase pressure when ordinary routes are no longer changing the
mission state, but it may prefer a prosecution/accountability route only when a
real route is available and the supporting evidence clears an explicit floor.

The same primitive is useful outside legal work: route kinds such as escalation
and enforcement represent consequence-producing accountability paths. Nothing
in this module grants authority or asserts guilt.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class ProsecutionLevel(str, Enum):
    NORMAL = "normal"
    PRESSURE = "pressure"
    PROSECUTION = "prosecution"


@dataclass(frozen=True, slots=True)
class ProsecutionSignal:
    """Observed conditions that can justify increasing execution pressure."""

    consecutive_nonprogress: int = 0
    receipt_missing: bool = False
    deadline_breached: bool = False
    time_sensitive_harm: bool = False
    supported_accountability_route: bool = False
    evidence_strength: float = 0.0
    operator_escalation_directive: bool = False

    def __post_init__(self) -> None:
        if self.consecutive_nonprogress < 0:
            raise ValueError("consecutive_nonprogress cannot be negative")
        if not 0.0 <= float(self.evidence_strength) <= 1.0:
            raise ValueError("evidence_strength must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ProsecutionPressure:
    """Deterministic pressure assessment consumed by action ranking."""

    level: ProsecutionLevel
    score: float
    reasons: tuple[str, ...]
    accountability_route_supported: bool
    prosecution_eligible: bool
    evidence_strength: float

    @property
    def active(self) -> bool:
        return self.level is not ProsecutionLevel.NORMAL


PROSECUTION_EVIDENCE_FLOOR = 0.65

ROUTE_KINDS = frozenset(
    {
        "analysis",
        "remediation",
        "execution",
        "escalation",
        "enforcement",
        "prosecution",
    }
)


def assess_prosecution_pressure(signal: ProsecutionSignal) -> ProsecutionPressure:
    """Turn observed stagnation/accountability signals into bounded pressure."""

    evidence = float(signal.evidence_strength)
    reasons: list[str] = []
    score = 0.0

    if signal.consecutive_nonprogress:
        score += min(signal.consecutive_nonprogress, 4) * 0.18
        reasons.append(f"nonprogress:{signal.consecutive_nonprogress}")
    if signal.receipt_missing:
        score += 0.18
        reasons.append("receipt_missing")
    if signal.deadline_breached:
        score += 0.24
        reasons.append("deadline_breached")
    if signal.time_sensitive_harm:
        score += 0.20
        reasons.append("time_sensitive_harm")
    if signal.operator_escalation_directive:
        score += 0.30
        reasons.append("operator_escalation_directive")

    supported = bool(signal.supported_accountability_route)
    prosecution_eligible = supported and evidence >= PROSECUTION_EVIDENCE_FLOOR
    if supported:
        score += 0.10
        reasons.append("accountability_route_supported")
    if prosecution_eligible:
        score += 0.10
        reasons.append("evidence_floor_met")

    score = min(score, 1.0)

    prosecution_trigger = prosecution_eligible and (
        signal.operator_escalation_directive
        or signal.consecutive_nonprogress >= 2
        or (signal.deadline_breached and signal.receipt_missing)
        or (signal.time_sensitive_harm and signal.consecutive_nonprogress >= 1)
    )
    pressure_trigger = (
        signal.consecutive_nonprogress >= 1
        or signal.receipt_missing
        or signal.deadline_breached
        or signal.time_sensitive_harm
        or signal.operator_escalation_directive
    )

    if prosecution_trigger:
        level = ProsecutionLevel.PROSECUTION
    elif pressure_trigger:
        level = ProsecutionLevel.PRESSURE
    else:
        level = ProsecutionLevel.NORMAL

    return ProsecutionPressure(
        level=level,
        score=score,
        reasons=tuple(reasons),
        accountability_route_supported=supported,
        prosecution_eligible=prosecution_eligible,
        evidence_strength=evidence,
    )


def route_kind(metadata: Mapping[str, Any]) -> str:
    value = str(metadata.get("route_kind", "execution")).strip().lower()
    return value if value in ROUTE_KINDS else "execution"


def pressure_adjusted_features(
    features: Mapping[str, float],
    *,
    metadata: Mapping[str, Any],
    pressure: ProsecutionPressure,
) -> dict[str, float]:
    """Adjust ranking without converting unsupported accusations into evidence."""

    adjusted = {str(name): _clamp01(float(value)) for name, value in features.items()}
    kind = route_kind(metadata)

    # Prosecution is never self-authorizing. If the evidence/route gate is not
    # satisfied, the candidate carries a strong unsupported-claim/failure cost
    # even when the runtime is otherwise under pressure.
    if kind == "prosecution" and not pressure.prosecution_eligible:
        _raise(adjusted, "unsupported_claim_risk", 0.80)
        _raise(adjusted, "failure_risk", 0.55)

    if pressure.level is ProsecutionLevel.NORMAL:
        return adjusted

    if kind in {"analysis", "remediation"}:
        _raise(adjusted, "delay_cost", 0.20 + 0.35 * pressure.score)
        _raise(adjusted, "meta_substitution_risk", 0.15 + 0.35 * pressure.score)
        _raise(adjusted, "rediscovery_risk", 0.10 + 0.30 * pressure.score)

    if kind in {"execution", "escalation", "enforcement"} or (
        kind == "prosecution" and pressure.prosecution_eligible
    ):
        _raise(adjusted, "mission_advancement", 0.10 + 0.20 * pressure.score)
        _raise(adjusted, "state_change_value", 0.10 + 0.20 * pressure.score)
        _raise(adjusted, "execution_proximity", 0.12 + 0.25 * pressure.score)

    if pressure.level is ProsecutionLevel.PROSECUTION:
        if kind in {"enforcement", "prosecution"} and pressure.prosecution_eligible:
            _raise(adjusted, "mission_advancement", 0.25)
            _raise(adjusted, "state_change_value", 0.30)
            _raise(adjusted, "success_impact", 0.20)
            _raise(adjusted, "execution_proximity", 0.30)
            _raise(adjusted, "second_order_value", 0.15)
        elif kind == "prosecution":
            # The unsupported-route penalty was applied before pressure boosts.
            pass

    return adjusted


def _raise(features: dict[str, float], name: str, delta: float) -> None:
    features[name] = _clamp01(features.get(name, 0.0) + delta)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
