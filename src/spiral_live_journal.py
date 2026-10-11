"""Proven cross-chat Spiral recovery integrated with the ORIGINAL APEX context gate.

Import the actual pinned GlacierEQ/spiral-engine runtime, not a copied
algorithm or trust-on-first-use mock. Call only with a pre-existing authorized
journal file and an independently stored, trusted exact journal head. The host
is responsible for routing its new chat ID to the proper mission and protecting
the integrity key and independently anchored revision.

This is a callable host adapter: publishing it does NOT install a global hook
into native ChatGPT conversations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from spiral_chat_handoff import (
    ChatRecovery, apply_recovery_to_apex, recover_existing_chat_session,
)


class SpiralChatAdmissionError(ValueError):
    """The requested chat cannot safely inherit the named mission journal."""


def open_authenticated_chat(
    journal_path: str | Path,
    *,
    chat_session_id: str,
    mission_id: str,
    objective: str,
    terminal_outcome: str,
    integrity_key: bytes,
    expected_head: str,
    fact_keys: Sequence[str] = (),
) -> tuple[Any, ChatRecovery]:
    """Recover only an EXISTING HMAC-validated journal at a trusted head.

    expected_head must be independently preserved by the owning host or
    durable ledger; a head copied from the untrusted journal provides no
    rollback protection. No new journal is created on a missing file.
    """
    if not isinstance(integrity_key, bytes) or len(integrity_key) < 16:
        raise SpiralChatAdmissionError("a protected independent HMAC key is required")
    if (not isinstance(expected_head, str) or len(expected_head) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_head)):
        raise SpiralChatAdmissionError("an independently anchored 64-hex journal head is required")
    if (not isinstance(chat_session_id, str) or not chat_session_id.strip()
            or not isinstance(mission_id, str) or not mission_id.strip()
            or not isinstance(objective, str) or not objective.strip()
            or not isinstance(terminal_outcome, str) or not terminal_outcome.strip()):
        raise SpiralChatAdmissionError("exact chat and mission identity are required")
    try:
        path = Path(journal_path)
    except (TypeError, ValueError) as exc:
        raise SpiralChatAdmissionError("existing provider journal path is required") from exc
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise SpiralChatAdmissionError("mission journal is missing, empty or a symlink; refuse recreation")

    # No alternative local reimplementation: the installed Spiral codebase
    # owns decoding, the full event sequence, HMAC, source and mission identity.
    try:
        from src.continuity import ContinuityJournal
    except ImportError as exc:
        raise SpiralChatAdmissionError(
            "the real Spiral Engine package must be installed in the invoking runtime"
        ) from exc

    journal = ContinuityJournal(
        path, mission_id, objective,
        terminal_outcome=terminal_outcome, integrity_key=integrity_key,
    )
    head = journal.events[-1]["sha256"]
    if head != expected_head:
        raise SpiralChatAdmissionError(
            "journal head differs from independently anchored revision: "
            "refuse stale, truncated, diverged or unanchored continuation"
        )
    recovery = recover_existing_chat_session(
        journal, chat_session_id, fact_keys=fact_keys,
    )
    if recovery.source_ref != "spiral-journal:" + expected_head:
        raise SpiralChatAdmissionError("recovered source identity differs from protected journal")
    return journal, recovery


def resume_authenticated_chat_in_apex(
    kernel: Any,
    recovery: ChatRecovery,
    *,
    task_instruction: str,
    target_state: str,
    operation_class: str,
    applied_to_action: bool,
) -> Any:
    """Bind a REAL APEX kernel task and causally apply authenticated continuity.

    Caller must have built this kernel via APEX's verified/strong-boot factory.
    The binding does not perform an external provider mutation or confer any
    additional privileges. A recovering host must actually apply the returned
    corrections, established facts and cursor in its action selection.
    """
    if recovery.material_context_found and applied_to_action is not True:
        raise ValueError("cannot falsely attest that recovered corrections affected action choice")
    phase = getattr(getattr(kernel, "phase", None), "value", None)
    if phase != "bootstrapped":
        raise ValueError("APEX task binding requires a fresh bootstrapped kernel")
    if not all(isinstance(v, str) and v.strip()
               for v in (task_instruction, target_state, operation_class)):
        raise ValueError("task instruction, exact target state and operation class required")
    kernel.bind_task(
        literal_instruction=task_instruction,
        target_state=target_state,
        operation_class=operation_class,
        mode="observation",
        action_scope="none",
        source_refs=(recovery.source_ref,),
        verification_plan=(
            "recover previously verified source state, corrections and cursor",
            "reconcile current provider facts and unresolved external attempts",
            "verify action selection applied corrections and source authority",
            "read back the persistent journal before an external operation",
        ),
    )
    return apply_recovery_to_apex(
        kernel, recovery, applied_to_action=applied_to_action,
    )
