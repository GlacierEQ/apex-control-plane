"""Safe Manus compatibility contract harvested from feat/durable-workflow-machine.

This module preserves structured-output and callback-correlation mechanisms while
explicitly excluding mock credentials, fabricated provider state, and callback
observation as terminal provider verification.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Any, Mapping

_ALLOWED_STATUSES = {"success", "failed", "blocked", "requires_input"}
_REQUIRED_OUTPUT = ("status", "facts", "findings", "recommended_changes")


class ManusContractError(ValueError):
    """Raised when Manus-compatible data cannot satisfy the safe contract."""


def validate_structured_output(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = payload.get("structured_output", payload)
    if not isinstance(data, Mapping):
        raise ManusContractError("structured output must be an object")
    missing = [key for key in _REQUIRED_OUTPUT if key not in data]
    if missing:
        raise ManusContractError(f"missing structured-output fields: {', '.join(missing)}")
    if data["status"] not in _ALLOWED_STATUSES:
        raise ManusContractError("unsupported structured-output status")
    for key in ("facts", "findings", "recommended_changes"):
        if not isinstance(data[key], list):
            raise ManusContractError(f"{key} must be a list")
    return dict(data)


def verify_callback_signature(payload_bytes: bytes, signature_header: str, *, secret: str) -> bool:
    if not secret or not signature_header:
        raise ManusContractError("explicit webhook secret and signature are required")
    expected = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@dataclass(frozen=True)
class ManusCallbackObservation:
    event_type: str
    task_id: str
    mission_id: str
    status: str
    structured_output: dict[str, Any]
    provider_terminal_verified: bool = False

    def __post_init__(self) -> None:
        if not self.event_type or not self.task_id or not self.mission_id or not self.status:
            raise ManusContractError("event_type, task_id, mission_id, and status are required")
        if self.provider_terminal_verified:
            raise ManusContractError(
                "callback observation cannot assert terminal provider verification"
            )


def correlate_callback(event_payload: Mapping[str, Any]) -> ManusCallbackObservation:
    required = ("event_type", "task_id", "mission_id", "status")
    missing = [key for key in required if not event_payload.get(key)]
    if missing:
        raise ManusContractError(f"missing callback correlation fields: {', '.join(missing)}")
    raw_output = event_payload.get("structured_output", {})
    if raw_output and not isinstance(raw_output, Mapping):
        raise ManusContractError("structured_output must be an object")
    return ManusCallbackObservation(
        event_type=str(event_payload["event_type"]),
        task_id=str(event_payload["task_id"]),
        mission_id=str(event_payload["mission_id"]),
        status=str(event_payload["status"]),
        structured_output=dict(raw_output),
    )
