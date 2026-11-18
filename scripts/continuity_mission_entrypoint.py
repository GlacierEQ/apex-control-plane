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
        or receipt.get("downstream_action_executed") is not True
        or not isinstance(receipt.get("result"), dict)
        or not isinstance(receipt.get("head"), str)
        or len(receipt["head"]) != 64
        or receipt.get("apex_phase") != "ready"
        or "context_recovery" not in receipt.get("apex_receipt_kinds", [])
        or receipt["result"].get("binding") != "spiral-journal:" + receipt["head"]
        or receipt.get("action_name") not in ("continue", "inspect")
    ):
        raise RuntimeError("startup recovery receipt did not prove dispatch")
    return consumer(receipt)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start a mission with mandatory authenticated recovery")
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--spiral-root", type=Path, required=True)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()
    # The default consumer exposes the recovered action receipt to a caller.
    # Other host processes can import start_mission and supply their own consumer.
    start_mission(
        store=args.store, spiral_root=args.spiral_root,
        mission_id=args.mission_id, session_id=args.session_id,
        consumer=lambda receipt: print(json.dumps(receipt, sort_keys=True)),
    )


if __name__ == "__main__":
    main()
