"""Mission-bound connector admission with idempotent effect reservation.

Tool discovery is not authentication. Source recovery is not context application.
This module enforces both boundaries before dispatching provider-native effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence


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
    if not isinstance(mission.recovered_mission_id, str) or mission.recovered_mission_id != mission.expected_mission_id:
        raise AdmissionDenied("recovered context belongs to a different mission")
    if mission.context_applied is not True:
        raise AdmissionDenied("recovered context has not been applied")
    if not isinstance(mission.cursor, str) or not mission.cursor.strip():
        raise AdmissionDenied("missing durable continuation cursor")
    if (not isinstance(capability.provider, str) or not capability.provider.strip()
            or not isinstance(capability.action, str) or not capability.action.strip()):
        raise AdmissionDenied("connector provider/action must be identified")
    if capability.discovered is not True:
        raise AdmissionDenied("connector action was not discovered")
    if capability.authenticated is not True:
        raise AdmissionDenied("connector authentication unverified")
    if capability.permitted is not True:
        raise AdmissionDenied("connector action not authorized")


def dispatch_once(
    mission: MissionAdmission,
    capability: ConnectorCapability,
    operation_id: str,
    reserve: Callable[[str], bool],
    execute: Callable[[], object],
    readback: Callable[[object], bool],
) -> object:
    """Reserve a durable key before an effect; do not replay uncertain outcomes.

    reserve MUST be an atomic durable insert-if-absent owned by the host.
    If execution or readback fails, keep the reservation for reconciliation.
    """
    admit(mission, capability)
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise AdmissionDenied("missing stable operation identity")
    # Reject ambiguous separators in the legacy key format; never alias two effects.
    if any(":" in value for value in (mission.expected_mission_id, capability.provider, capability.action, operation_id)):
        raise AdmissionDenied("ambiguous idempotency identity segment")
    if not all(callable(fn) for fn in (reserve, execute, readback)):
        raise AdmissionDenied("durable reservation, execution and independent readback callbacks required")
    key = f"{mission.expected_mission_id}:{capability.provider}:{capability.action}:{operation_id}"
    if reserve(key) is not True:
        raise AdmissionDenied("operation already reserved; reconcile provider state before retry")
    result = execute()
    if readback(result) is not True:
        raise AdmissionDenied("provider effect not independently verified; reservation retained")
    return result


def dispatch_recovered_once(
    *,
    journal: Any,
    chat_session_id: str,
    kernel: Any,
    expected_mission_id: str,
    capability: ConnectorCapability,
    operation_id: str,
    reserve: Callable[[str], bool],
    execute: Callable[[], object],
    readback: Callable[[object], bool],
    fact_keys: Sequence[str] = (),
    apply_context: Callable[[Any], Any] | None = None,
) -> object:
    """Pass the existing Spiral->APEX source-matched gate before a native effect.

    Do not synthesize context_applied from a flag. The host must supply an
    authenticated journal, a recovering APEX kernel, and a source-matched
    ContextApplication. A missing durable cursor blocks outbound effects.
    Reservation and provider readback still belong to the actual host.
    This does NOT intercept native ChatGPT sessions by itself.
    """
    if not isinstance(expected_mission_id, str) or not expected_mission_id.strip():
        raise AdmissionDenied("missing host-derived expected mission identity")
    from .chat_context_admission import execute_with_recovered_context

    def effect_after_application(receipt: Any) -> object:
        if receipt.mission_id != expected_mission_id:
            raise AdmissionDenied("recovered context belongs to a different mission")
        recovery = receipt.recovery
        if recovery.material_context_found and not receipt.application_ref:
            raise AdmissionDenied("historical context was not applied to this action")
        admission = MissionAdmission(
            expected_mission_id=expected_mission_id,
            recovered_mission_id=receipt.mission_id,
            context_applied=bool(receipt.application_ref) or not recovery.material_context_found,
            cursor=receipt.cursor,
            correction_ids=tuple(recovery.corrections),
        )
        return dispatch_once(admission, capability, operation_id, reserve, execute, readback)

    return execute_with_recovered_context(
        journal=journal,
        chat_session_id=chat_session_id,
        kernel=kernel,
        expected_mission_id=expected_mission_id,
        execute=effect_after_application,
        fact_keys=fact_keys,
        apply_context=apply_context,
    )
