"""Fail-closed startup entrypoint for an explicitly configured GLACIEREQ mission.

This is an owned-process startup integration, NOT a native ChatGPT host hook.
No mission is initialized or silently selected by this entrypoint.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping


def start_mission(
    *,
    store: Path,
    spiral_root: Path,
    mission_id: str,
    session_id: str,
    consumer: Callable[[Mapping[str, Any]], Any],
    bridge: Path | None = None,
    legacy_continue_cursor: str | None = None,
) -> Any:
    """Authenticate, admit and dispatch persisted context BEFORE consumer work.

    The consumer never runs if recovery, APEX admission or dispatch fails.
    Only the existing bridge may read mission secrets; subprocess arguments
    contain paths and explicit mission/session identifiers, not credentials.
    """
    if not mission_id.strip() or not session_id.strip():
        raise ValueError("explicit nonempty mission and session IDs required")
    if not callable(consumer):
        raise ValueError("consumer callback required")
    entry = bridge or Path(__file__).resolve().with_name("chatgpt_context_bridge.py")
    cmd = [
        sys.executable, str(entry), "--store", str(store),
        "--spiral-root", str(spiral_root), "--mission-id", mission_id,
        "dispatch", "--session-id", session_id,
    ]
    if legacy_continue_cursor is not None:
        if not isinstance(legacy_continue_cursor, str) or not legacy_continue_cursor.strip():
            raise ValueError("explicit nonempty legacy cursor required")
        cmd.extend(["--legacy-continue-cursor", legacy_continue_cursor])
    completed = subprocess.run(
        cmd, capture_output=True, text=True, check=False, timeout=60,
    )
    if completed.returncode:
        raise RuntimeError("authenticated startup recovery failed: " +
                           completed.stderr.strip()[:1000])
    try:
        receipt = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid startup recovery receipt") from exc
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "RECOVERED_ACTION_DISPATCHED"
        or receipt.get("mission_id") != mission_id
        or receipt.get("session_id") != session_id
        or receipt.get("downstream_action_executed") is not True
        or not isinstance(receipt.get("result"), dict)
        or not isinstance(receipt.get("head"), str)
        or len(receipt["head"]) != 64
        or any(ch not in "0123456789abcdef" for ch in receipt["head"])
        or not isinstance(receipt.get("cursor"), str)
        or not receipt["cursor"].strip()
        or receipt.get("action_name") != receipt["cursor"].split(":", 1)[0]
        or not isinstance(receipt.get("apex_runtime_id"), str)
        or not receipt["apex_runtime_id"].strip()
        or receipt.get("apex_phase") != "ready"
        or not isinstance(receipt.get("apex_receipt_kinds"), list)
        or "context_recovery" not in receipt["apex_receipt_kinds"]
        or receipt["result"].get("binding") != "spiral-journal:" + receipt["head"]
        or (receipt.get("action_name") not in ("continue", "inspect")
            and (legacy_continue_cursor is None
                 or receipt.get("cursor") != legacy_continue_cursor))
        or ((receipt["action_name"] == "continue"
             or (legacy_continue_cursor is not None
                 and receipt["cursor"] == legacy_continue_cursor))
            and receipt["result"].get("next_cursor") != receipt["cursor"])
        or (receipt["action_name"] == "inspect"
            and receipt["result"].get("key") != receipt["cursor"].partition(":")[2])
    ):
        raise RuntimeError("startup recovery receipt did not prove dispatch")
    return consumer(receipt)


def start_registered_mission(
    *,
    store: Path,
    spiral_root: Path,
    mission_id: str,
    session_id: str,
    handlers: Mapping[str, Callable[[Mapping[str, Any]], Any]],
    bridge: Path | None = None,
    legacy_continue_cursor: str | None = None,
) -> Any:
    """Run the *selected* authorized mission operation after verified startup.

    A persisted cursor chooses the handler; there is no default handler and no
    execution before the authenticated bridge receipt passes all startup gates.
    The entire recovery receipt is passed through, including corrections and
    provenance, so handlers can apply current instructions and source facts.
    """
    if not isinstance(handlers, Mapping) or not handlers:
        raise ValueError("explicit nonempty mission handler registry required")
    if any(not isinstance(name, str) or not name or not callable(handler)
           for name, handler in handlers.items()):
        raise ValueError("invalid mission handler registry")

    def dispatch_to_handler(receipt: Mapping[str, Any]) -> Any:
        action = receipt["action_name"]
        handler = handlers.get("continue" if legacy_continue_cursor is not None
                               and receipt["cursor"] == legacy_continue_cursor else action)
        if handler is None:
            raise ValueError("recovered action has no authorized mission handler")
        return handler(receipt)

    return start_mission(
        store=store, spiral_root=spiral_root, mission_id=mission_id,
        session_id=session_id, consumer=dispatch_to_handler, bridge=bridge,
        legacy_continue_cursor=legacy_continue_cursor,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Start a mission with mandatory authenticated recovery")
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--spiral-root", type=Path, required=True)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--legacy-continue-cursor", default=None,
                        help="Exact persisted legacy cursor; never inferred or rewritten")
    args = parser.parse_args()
    # The default consumer exposes the recovered action receipt to a caller.
    # Other host processes can import start_mission and supply their own consumer.
    start_mission(
        store=args.store, spiral_root=args.spiral_root,
        mission_id=args.mission_id, session_id=args.session_id,
        consumer=lambda receipt: print(json.dumps(receipt, sort_keys=True)),
        legacy_continue_cursor=args.legacy_continue_cursor,
    )


if __name__ == "__main__":
    main()
