"""Fail-closed admission wrapper for an existing ChatGPT/Spiral mission session.

Host integration must call this function before dispatching substantive work.
This does not claim to hook the native ChatGPT runtime by itself.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .spiral_chat_handoff import ChatRecovery

from .spiral_chat_handoff import recover_existing_chat_session, apply_recovery_to_apex
from .continuity_admission_guard import exclusive_kernel_admission


class ContextAdmissionDenied(RuntimeError):
    """No mission execution without validated, applied historical context."""


@dataclass(frozen=True)
class AdmissionReceipt:
    chat_session_id: str
    mission_id: str
    source_ref: str
    cursor: str
    recovery: ChatRecovery
    application_ref: str | None = None


@dataclass(frozen=True)
class ContextApplication:
    """Host-attested application, not independent downstream verification."""
    mission_id: str
    source_ref: str
    cursor: str
    corrections: tuple[str, ...]
    fact_keys: tuple[str, ...]
    effect_ref: str


def execute_with_recovered_context(
    *,
    journal: Any,
    chat_session_id: str,
    kernel: Any,
    expected_mission_id: str | None = None,
    execute: Callable[[AdmissionReceipt], Any],
    fact_keys: Sequence[str] = (),
    apply_context: Callable[[ChatRecovery], ContextApplication] | None = None,
) -> Any:
    """Recover -> apply -> admit -> execute; never call execute on failed admission.

    The host must provide an authenticated durable journal, a context_recovering
    APEX kernel, and a real session identifier. Missing or inconsistent state
    raises before the executor is invoked. This wrapper does not authorize
    external actions or silently create a replacement mission.
    Historical context requires an explicit source-matched host application
    callback before admission; mere retrieval cannot attest application.
    The host must independently select the expected mission ID from the
    current Operator request; an unrelated recovered journal cannot substitute.
    The callback's effect_ref is host testimony, not independently verified
    ChatGPT runtime enforcement or downstream provider readback.
    """
    if not callable(execute):
        raise TypeError("execute must be callable")
    with exclusive_kernel_admission(kernel):
        return _execute_under_exclusive_admission(
            journal=journal, chat_session_id=chat_session_id, kernel=kernel,
            expected_mission_id=expected_mission_id, execute=execute,
            fact_keys=fact_keys, apply_context=apply_context,
        )


def _execute_under_exclusive_admission(
    *, journal: Any, chat_session_id: str, kernel: Any,
    expected_mission_id: str | None, execute: Callable[[AdmissionReceipt], Any],
    fact_keys: Sequence[str],
    apply_context: Callable[[ChatRecovery], ContextApplication] | None,
) -> Any:
    try:
        recovery = recover_existing_chat_session(
            journal, chat_session_id, fact_keys=fact_keys
        )
        if recovery.material_context_found and expected_mission_id is None:
            raise ContextAdmissionDenied("existing mission requires explicit host mission identity")
        if expected_mission_id is not None:
            if (not isinstance(expected_mission_id, str) or not expected_mission_id.strip()
                    or expected_mission_id != recovery.mission_id):
                raise ContextAdmissionDenied("recovered journal is not the requested mission")
        if getattr(getattr(kernel, "phase", None), "value", None) != "context_recovering":
            raise ContextAdmissionDenied("APEX is not awaiting context recovery")
        application = None
        if recovery.material_context_found:
            if not callable(apply_context):
                raise ContextAdmissionDenied("historical context requires host application")
            application = apply_context(recovery)
            if not isinstance(application, ContextApplication):
                raise ContextAdmissionDenied("host application receipt is missing or invalid")
            if (application.mission_id != recovery.mission_id
                or application.source_ref != recovery.source_ref
                or application.cursor != recovery.cursor
                or application.corrections != recovery.corrections
                or Counter(application.fact_keys) != Counter(tuple(recovery.facts))
                or not isinstance(application.effect_ref, str)
                or not application.effect_ref.strip()):
                raise ContextAdmissionDenied("host application does not match recovered source")
        # Fresh missions remain admissible without invented historical context.
        apply_recovery_to_apex(
            kernel,
            recovery,
            applied_to_action=application is not None,
        )
        if getattr(getattr(kernel, "phase", None), "value", None) == "context_recovering":
            raise ContextAdmissionDenied("APEX remained in context recovery phase")
    except ContextAdmissionDenied:
        raise
    except Exception as exc:
        raise ContextAdmissionDenied("context admission failed") from exc
    receipt = AdmissionReceipt(
        chat_session_id=recovery.chat_session_id,
        mission_id=recovery.mission_id,
        source_ref=recovery.source_ref,
        cursor=recovery.cursor,
        recovery=recovery,
        application_ref=application.effect_ref if application else None,
    )
    return execute(receipt)
