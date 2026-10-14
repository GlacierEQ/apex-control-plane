"""Mission-bound connector admission with idempotent effect reservation.

Tool discovery is not authentication. Source recovery is not context application.
This module enforces both boundaries before dispatching provider-native effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping


class AdmissionDenied(ValueError):
    """An execution prerequisite is missing or contradictory."""


@dataclass(frozen=True)
class ConnectorCapability:
    provider: str
    action: str
    discovered: bool
    authenticated: bool
    permitted: bool


@dataclass(frozen=True)
class MissionAdmission:
    expected_mission_id: str
    recovered_mission_id: str
    context_applied: bool
    cursor: str
    correction_ids: tuple[str, ...]


def admit(mission: MissionAdmission, capability: ConnectorCapability) -> None:
    if not isinstance(mission.expected_mission_id, str) or not mission.expected_mission_id.strip():
        raise AdmissionDenied("missing host-derived expected mission identity")
    if mission.recovered_mission_id != mission.expected_mission_id:
        raise AdmissionDenied("recovered context belongs to a different mission")
    if not mission.context_applied:
        raise AdmissionDenied("recovered context has not been applied")
    if not mission.cursor.strip():
        raise AdmissionDenied("missing durable continuation cursor")
    if not all((capability.provider.strip(), capability.action.strip())):
        raise AdmissionDenied("connector provider/action must be identified")
    if not capability.discovered:
        raise AdmissionDenied("connector action was not discovered")
    if not capability.authenticated:
        raise AdmissionDenied("connector authentication unverified")
    if not capability.permitted:
        raise AdmissionDenied("connector action not authorized")


def dispatch_once(
    mission: MissionAdmission,
    capability: ConnectorCapability,
    operation_id: str,
    reserve: Callable[[str], bool],
    execute: Callable[[], object],
    readback: Callable[[object], bool],
) -> object:
    """Reserve a durable key before a side effect; never replay uncertain outcomes.

    reserve MUST be an atomic durable insert-if-absent owned by the host.
    If execution or readback fails, keep the reservation for reconciliation.
    """
    admit(mission, capability)
    if not operation_id or not operation_id.strip():
        raise AdmissionDenied("missing stable operation identity")
    key = f"{mission.expected_mission_id}:{capability.provider}:{capability.action}:{operation_id}"
    if not reserve(key):
        raise AdmissionDenied("operation already reserved; reconcile provider state before retry")
    result = execute()
    if not readback(result):
        raise AdmissionDenied("provider effect not independently verified; reservation retained")
    return result
