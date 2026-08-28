"""Fail-closed execution gate; planning never implies authorization."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionRequest:
    plan_id: str
    approved: bool
    stale: bool = False
    rollback_ready: bool = False


def authorize(request: ExecutionRequest) -> str:
    if request.stale or not request.approved or not request.rollback_ready:
        return "BLOCKED"
    return "AUTHORIZED"
