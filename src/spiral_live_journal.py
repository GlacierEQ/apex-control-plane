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
import importlib.util
import os
import stat
import sys

try:
    import fcntl
except ImportError:  # fail closed if safe shared file locks unavailable
    fcntl = None

try:
    from .spiral_chat_handoff import (
        ChatRecovery, apply_recovery_to_apex, recover_existing_chat_session,
    )
except ImportError:  # existing PYTHONPATH=src legacy module import
    from spiral_chat_handoff import (
        ChatRecovery, apply_recovery_to_apex, recover_existing_chat_session,
    )


# Import through one canonical module name, including legacy top-level imports.
try:
    from src.continuity_admission_guard import exclusive_kernel_admission
except ModuleNotFoundError:  # legacy PYTHONPATH=src without repository root
    from continuity_admission_guard import exclusive_kernel_admission


class SpiralChatAdmissionError(ValueError):
    """The requested chat cannot safely inherit the named mission journal."""


def load_spiral_engine(spiral_source_root: str | Path) -> Any:
    """Load actual upstream Spiral in separate namespace, preserving both packages.

    APEX has its own package called src. Direct import of src.continuity
    would select the wrong repository. Require a trusted upstream checkout.
    """
    try:
        package_path = (Path(spiral_source_root) / "src" / "__init__.py").resolve(strict=True)
    except (TypeError, ValueError, OSError) as exc:
        raise SpiralChatAdmissionError("a trusted upstream Spiral checkout is required") from exc
    if not package_path.is_file():
        raise SpiralChatAdmissionError("upstream Spiral Python package is absent")
    name = "glaciereq_verified_spiral_upstream"
    existing = sys.modules.get(name)
    if existing is not None:
        if Path(existing.__file__).resolve() != package_path:
            raise SpiralChatAdmissionError("upstream Spiral package identity changed")
        return existing
    spec = importlib.util.spec_from_file_location(
        name, str(package_path),
        submodule_search_locations=[str(package_path.parent)],
    )
    if spec is None or spec.loader is None:
        raise SpiralChatAdmissionError("could not load the original Spiral package")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def open_authenticated_chat(
    journal_path: str | Path,
    *,
    spiral_source_root: str | Path,
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
    if (fcntl is None or not hasattr(os, "O_NOFOLLOW")):
        raise SpiralChatAdmissionError("safe journal locking and no-follow open not supported on host")
    if path.is_symlink():
        raise SpiralChatAdmissionError("symbolic-link journal rejected")
    # Open first with O_NOFOLLOW and hold a shared lock for the entire validated
    # read. Spiral's writer takes exclusive locks, so cooperative appends wait.
    # Recheck device/inode/mtime/length after loading to detect path swaps.
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        fcntl.flock(fd, fcntl.LOCK_SH)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size == 0:
            raise SpiralChatAdmissionError("existing journal is not a nonempty regular file")
        name_before = os.stat(path, follow_symlinks=False)
        if (name_before.st_dev, name_before.st_ino) != (before.st_dev, before.st_ino):
            raise SpiralChatAdmissionError("journal replaced during source admission")

        # The original Spiral implementation owns event-chain and HMAC validation.
        upstream = load_spiral_engine(spiral_source_root)
        journal = upstream.ContinuityJournal(
            path, mission_id, objective,
            terminal_outcome=terminal_outcome, integrity_key=integrity_key,
            require_existing=True,
        )
        events = journal.events
        if not events:
            raise SpiralChatAdmissionError("empty journal must never be recreated")
        after = os.stat(path, follow_symlinks=False)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise SpiralChatAdmissionError("journal changed during authenticated recovery")
        head = events[-1]["sha256"]
        if head != expected_head:
            raise SpiralChatAdmissionError(
                "journal head differs from independently anchored revision: "
                "refuse stale, truncated, diverged or unanchored continuation"
            )
        recovery = recover_existing_chat_session(
            journal, chat_session_id, fact_keys=fact_keys,
        )
        if recovery.source_ref != "spiral-journal:" + expected_head:
            raise SpiralChatAdmissionError("recovered source differs from protected journal")
        return journal, recovery
    except (FileNotFoundError, NotADirectoryError, PermissionError, IsADirectoryError) as exc:
        raise SpiralChatAdmissionError("pre-existing authorized journal is unavailable") from exc
    finally:
        if fd is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def resume_authenticated_chat_in_apex(
    kernel: Any,
    recovery: ChatRecovery,
    *,
    task_instruction: str,
    target_state: str,
    operation_class: str,
    applied_to_action: bool,
    expected_mission_id: str | None = None,
    mode: str = "observation",
    action_scope: str = "none",
    operator_authorization_ref: str | None = None,
    prior_state_ref: str | None = None,
) -> Any:
    """Bind a REAL APEX kernel task and causally apply authenticated continuity.

    Caller must have built this kernel via APEX's verified/strong-boot factory.
    The binding does not perform an external provider mutation or confer any
    additional privileges. The APEX kernel validates execution mode, action
    scope and scoped authority for consequence-sensitive operations. A recovering host must actually apply the returned
    corrections, established facts and cursor in its action selection.
    """
    with exclusive_kernel_admission(kernel):
        return _bind_recovery_under_exclusive_admission(
            kernel, recovery, task_instruction=task_instruction,
            target_state=target_state, operation_class=operation_class,
            applied_to_action=applied_to_action,
            expected_mission_id=expected_mission_id,
            mode=mode, action_scope=action_scope,
            operator_authorization_ref=operator_authorization_ref,
            prior_state_ref=prior_state_ref,
        )


def _bind_recovery_under_exclusive_admission(
    kernel: Any,
    recovery: ChatRecovery,
    *,
    task_instruction: str,
    target_state: str,
    operation_class: str,
    applied_to_action: bool,
    expected_mission_id: str | None,
    mode: str,
    action_scope: str,
    operator_authorization_ref: str | None,
    prior_state_ref: str | None,
) -> Any:
    if recovery.material_context_found and expected_mission_id is None:
        raise SpiralChatAdmissionError("existing mission requires explicit host mission identity")
    if expected_mission_id is not None and (
        not isinstance(expected_mission_id, str)
        or not expected_mission_id.strip()
        or expected_mission_id != recovery.mission_id
    ):
        raise SpiralChatAdmissionError("recovered journal is not the requested mission")
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
        mode=mode,
        action_scope=action_scope,
        operator_authorization_ref=operator_authorization_ref,
        prior_state_ref=prior_state_ref,
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
