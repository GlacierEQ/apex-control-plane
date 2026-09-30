"""Neutral parsing for optional startup receipt input.

This module carries no project-direction, startup-gate, or execution authority.
It only decodes an explicitly supplied JSON receipt from the environment so
callers can inspect whatever evidence the host provided.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from auto_boot import BootError


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootError(f"boot receipt not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BootError(f"invalid boot receipt JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BootError("boot receipt must be a JSON object")
    return value


def receipt_from_environment() -> dict[str, Any] | None:
    """Decode one optional receipt source without granting it authority."""
    inline = os.getenv("CASEY_BOOT_RECEIPT_JSON", "").strip()
    path_value = os.getenv("CASEY_BOOT_RECEIPT_PATH", "").strip()
    if inline and path_value:
        raise BootError(
            "set only one of CASEY_BOOT_RECEIPT_JSON or CASEY_BOOT_RECEIPT_PATH"
        )
    if inline:
        try:
            value = json.loads(inline)
        except json.JSONDecodeError as exc:
            raise BootError(f"CASEY_BOOT_RECEIPT_JSON is invalid: {exc}") from exc
        if not isinstance(value, dict):
            raise BootError("CASEY_BOOT_RECEIPT_JSON must contain an object")
        return value
    if path_value:
        return _read_json(Path(path_value).expanduser().resolve())
    return None
