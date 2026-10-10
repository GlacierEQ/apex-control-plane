"""Bind existing Spiral mission continuity to the APEX context-recovery gate.

A host must open a REAL, validated Spiral ContinuityJournal from its authorized
durable store first. This bridge never creates a mission or authorizes an
external action. A ChatGPT skill cannot invoke this Python in an arbitrary
native-app chat without a host integration or connected tool.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ChatRecovery:
    chat_session_id: str
    mission_id: str
    objective: str
    terminal_outcome: str
    source_ref: str
    cursor: str
    corrections: tuple[str, ...]
    facts: Mapping[str, Mapping[str, Any]]
    material_context_found: bool


def recover_existing_chat_session(
    journal: Any,
    chat_session_id: str,
    *,
    fact_keys: Sequence[str] = (),
) -> ChatRecovery:
    """Pin existing, validated mission-state history to a new chat session.

    Source integrity must already be authenticated by constructing the
    ContinuityJournal from the actual provider-backed journal bytes/key.
    Returning a recovery object does not create a fresh mission or fake proof.
    """
    if journal is None or not isinstance(chat_session_id, str) or not chat_session_id.strip():
        raise ValueError("existing journal and nonempty chat session ID required")
    for field in ("mission_id", "objective", "terminal_outcome", "events", "cursor", "corrections", "fact"):
        if not hasattr(journal, field):
            raise ValueError(f"existing Spiral journal missing required field: {field}")
    if not isinstance(journal.mission_id, str) or not journal.mission_id.strip():
        raise ValueError("existing mission identity must be nonempty")
    if not isinstance(journal.cursor, str):
        raise ValueError("existing continuation cursor must be a string")
    # An empty cursor is meaningful for a genuinely new, not-yet-checkpointed
    # mission. Do not invent a checkpoint merely to satisfy a schema.
    events = journal.events
    if not isinstance(events, (tuple, list)) or not events:
        raise ValueError("no verifiable stored mission history")
    first, last = events[0], events[-1]
    if not isinstance(first, dict) or first.get("kind") != "mission":
        raise ValueError("first recorded event is not a mission")
    if first.get("data", {}).get("mission_id") != journal.mission_id:
        raise ValueError("journal mission identity mismatch")
    head = last.get("sha256") if isinstance(last, dict) else None
    if not isinstance(head, str) or len(head) != 64 or any(ch not in "0123456789abcdef" for ch in head):
        raise ValueError("missing validated Spiral revision hash")
    if not journal.objective or not journal.terminal_outcome:
        raise ValueError("incomplete source mission definition")

    facts: dict[str, Mapping[str, Any]] = {}
    for key in fact_keys:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("requested fact key cannot be empty")
        source_fact = journal.fact(key)
        if source_fact is not None:
            if (not isinstance(source_fact, dict)
                    or not isinstance(source_fact.get("source"), str)
                    or not source_fact["source"].strip()):
                raise ValueError(f"unsourced fact cannot be admitted: {key}")
            facts[key] = deepcopy(source_fact)
    return ChatRecovery(
        chat_session_id=chat_session_id,
        mission_id=journal.mission_id,
        objective=journal.objective,
        terminal_outcome=journal.terminal_outcome,
        source_ref="spiral-journal:" + head,
        cursor=journal.cursor,
        corrections=tuple(journal.corrections),
        facts=facts,
        material_context_found=len(events) > 1,
    )


def apply_recovery_to_apex(
    kernel: Any,
    recovery: ChatRecovery,
    *,
    applied_to_action: bool,
) -> Any:
    """Use EXISTING APEX gate for proof-bound context before begin()/execute().

    Caller must causally apply recovered corrections and cursor to its work.
    This proof-bound entrypoint never substitutes for provider authorization.
    """
    if getattr(getattr(kernel, "phase", None), "value", None) != "context_recovering":
        raise ValueError("APEX must be waiting for context recovery before execution")
    if recovery.material_context_found and applied_to_action is not True:
        raise ValueError("cannot continue mission without applying material recovered state")
    material = bool(recovery.material_context_found)
    return kernel.record_context_recovery(
        f"chat-session-recovery:{recovery.chat_session_id}",
        recovered_refs=(recovery.source_ref,),
        details={
            "chat_session_id": recovery.chat_session_id,
            "mission_id": recovery.mission_id,
            "objective": recovery.objective,
            "terminal_outcome": recovery.terminal_outcome,
            "resume_cursor": recovery.cursor,
            "corrections": recovery.corrections,
            "source_fact_keys": tuple(recovery.facts),
            "prior_corrections_checked": True,
            "material_context_found": material,
            "material_context_applied": material and applied_to_action is True,
            "applied_context_refs": (recovery.source_ref,) if material else (),
        },
    )
