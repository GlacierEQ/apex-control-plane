"""Execute a registered downstream action only after verified mission recovery.

Host integration supplies the authenticated ChatRecovery and an explicitly
authorized action registry. This module cannot install a native ChatGPT hook.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Any


@dataclass(frozen=True)
class ActionReceipt:
    mission_id: str
    source_ref: str
    cursor: str
    action_name: str
    result: Any


def execute_recovered_action(
    recovery: Any,
    *,
    expected_mission_id: str,
    expected_source_ref: str,
    registry: Mapping[str, Callable[[Any], Any]],
) -> ActionReceipt:
    """Route the persisted cursor to a real authorized callback, never a fallback.

    The caller must authenticate the journal through the original Spiral adapter
    before supplying recovery. A callback is the actual downstream operation;
    no arbitrary shell command, eval, or unregistered action is permitted.
    """
    if not expected_mission_id or recovery.mission_id != expected_mission_id:
        raise ValueError("mission identity mismatch")
    if (not isinstance(expected_source_ref, str)
            or not expected_source_ref.startswith("spiral-journal:")
            or len(expected_source_ref) != len("spiral-journal:") + 64
            or recovery.source_ref != expected_source_ref):
        raise ValueError("authenticated source head mismatch")
    if not isinstance(recovery.cursor, str) or not recovery.cursor.strip():
        raise ValueError("no persisted execution cursor")
    if not isinstance(registry, Mapping):
        raise ValueError("action registry required")
    action_name = recovery.cursor.split(":", 1)[0]
    action = registry.get(action_name)
    if not callable(action):
        raise ValueError("unregistered or unauthorized continuation action")
    if not isinstance(recovery.corrections, (tuple, list)):
        raise ValueError("recovered corrections unavailable")
    if not isinstance(recovery.facts, Mapping):
        raise ValueError("recovered facts unavailable")
    result = action(recovery)
    return ActionReceipt(
        mission_id=recovery.mission_id,
        source_ref=recovery.source_ref,
        cursor=recovery.cursor,
        action_name=action_name,
        result=result,
    )
