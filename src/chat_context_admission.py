"""Fail-closed admission wrapper for an existing ChatGPT/Spiral mission session.

Host integration must call this function before dispatching substantive work.
This does not claim to hook the native ChatGPT runtime by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .spiral_chat_handoff import recover_existing_chat_session, apply_recovery_to_apex


class ContextAdmissionDenied(RuntimeError):
    """No mission execution without validated, applied historical context."""


@dataclass(frozen=True)
class AdmissionReceipt:
    chat_session_id: str
    mission_id: str
    source_ref: str
    cursor: str


def execute_with_recovered_context(
    *,
    journal: Any,
    chat_session_id: str,
    kernel: Any,
    execute: Callable[[AdmissionReceipt], Any],
    fact_keys: Sequence[str] = (),
) -> Any:
    """Recover -> apply -> admit -> execute; never call execute on failed admission.

    The host must provide an authenticated durable journal, a context_recovering
    APEX kernel, and a real session identifier. Missing or inconsistent state
    raises before the executor is invoked. This wrapper does not authorize
    external actions or silently create a replacement mission.
    """
    if not callable(execute):
        raise TypeError("execute must be callable")
    try:
        recovery = recover_existing_chat_session(
            journal, chat_session_id, fact_keys=fact_keys
        )
        if not recovery.material_context_found:
            raise ContextAdmissionDenied("no material prior context to apply")
        apply_recovery_to_apex(kernel, recovery, applied_to_action=True)
        if getattr(getattr(kernel, "phase", None), "value", None) == "context_recovering":
            raise ContextAdmissionDenied("APEX remained in context recovery phase")
    except Exception as exc:
        raise ContextAdmissionDenied("context admission failed") from exc
    receipt = AdmissionReceipt(
        chat_session_id=recovery.chat_session_id,
        mission_id=recovery.mission_id,
        source_ref=recovery.source_ref,
        cursor=recovery.cursor,
    )
    return execute(receipt)
