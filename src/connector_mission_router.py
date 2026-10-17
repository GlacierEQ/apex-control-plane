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

    # Populated only from a verified recovery receipt, never inferred from intent.
    source_ref: str = ""


@dataclass(frozen=True)
class ContinuationRecord:
    """Source-bound state passed to the host's durable continuation store.

    A record object does not persist itself; the host must save and read it
    back from its own authoritative durable store.
    """
    mission_id: str
    source_ref: str
    cursor: str
    correction_ids: tuple[str, ...]
    provider: str
    action: str
    operation_key: str
    native_result: object


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
    *,
    persist_continuation: Callable[[ContinuationRecord], object] | None = None,
    verify_continuation: Callable[[object], bool] | None = None,
) -> object:
    """Recover -> reserve -> execute -> provider readback -> durable handoff.

    Both persistence functions MUST be backed by the owning durable system.
    Provider readback alone never certifies the next chat/worker can resume.
    Reserve MUST be a durable atomic insert-if-absent. A failure at *any*
    subsequent stage retains the reservation and requires reconciliation.
    The returned native result is never by itself proof of human outcome.
    """
    admit(mission, capability)
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise AdmissionDenied("missing stable operation identity")
    if any(":" in value for value in (mission.expected_mission_id, capability.provider, capability.action, operation_id)):
        raise AdmissionDenied("ambiguous idempotency identity segment")
    if not all(callable(fn) for fn in (reserve, execute, readback)):
        raise AdmissionDenied("durable reservation, execution and independent provider readback callbacks required")
    # The host must supply the handoff store before any external effect occurs.
    if not callable(persist_continuation) or not callable(verify_continuation):
        raise AdmissionDenied("durable continuation persistence and independent readback required")
    key = f"{mission.expected_mission_id}:{capability.provider}:{capability.action}:{operation_id}"
    if reserve(key) is not True:
        raise AdmissionDenied("operation already reserved; reconcile provider state before retry")
    result = execute()
    if readback(result) is not True:
        raise AdmissionDenied("provider effect not independently verified; reservation retained")
    record = ContinuationRecord(
        mission_id=mission.expected_mission_id,
        source_ref=mission.source_ref,
        cursor=mission.cursor,
        correction_ids=mission.correction_ids,
        provider=capability.provider,
        action=capability.action,
        operation_key=key,
        native_result=result,
    )
    try:
        checkpoint = persist_continuation(record)
        if checkpoint is None or verify_continuation(checkpoint) is not True:
            raise AdmissionDenied("continuation not independently verified; reservation retained")
    except AdmissionDenied:
        raise
    except Exception as exc:
        raise AdmissionDenied("continuation persistence/readback failed; reservation retained") from exc
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
    persist_continuation: Callable[[ContinuationRecord], object] | None = None,
    verify_continuation: Callable[[object], bool] | None = None,
    fact_keys: Sequence[str] = (),
    apply_context: Callable[[Any], Any] | None = None,
    mission_scope: dict | None = None,
    execution_evidence: dict | None = None,
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
            source_ref=receipt.source_ref,
        )
        if mission_scope is not None or execution_evidence is not None:
            if mission_scope is None or execution_evidence is None:
                raise AdmissionDenied("mission fidelity requires both intent and execution evidence")
            from .mission_fidelity_admission import assess_mission_fidelity, FidelityViolation
            try:
                fidelity = assess_mission_fidelity(mission_scope, execution_evidence)
            except FidelityViolation as exc:
                raise AdmissionDenied("mission fidelity rejected: " + str(exc)) from exc
            if fidelity["status"] != "COMPLETE":
                raise AdmissionDenied("mission fidelity incomplete: " + ", ".join(fidelity["remaining_lanes"]))
            if fidelity["mission_id"] != expected_mission_id or fidelity["cursor"] != receipt.cursor:
                raise AdmissionDenied("mission fidelity does not match recovered context")
            if not set(receipt.recovery.corrections).issubset(set(fidelity["applied_correction_ids"])):
                raise AdmissionDenied("recovered corrections not applied in mission fidelity evidence")
        return dispatch_once(
            admission, capability, operation_id, reserve, execute, readback,
            persist_continuation=persist_continuation,
            verify_continuation=verify_continuation,
        )

    return execute_with_recovered_context(
        journal=journal,
        chat_session_id=chat_session_id,
        kernel=kernel,
        expected_mission_id=expected_mission_id,
        execute=effect_after_application,
        fact_keys=fact_keys,
        apply_context=apply_context,
    )
