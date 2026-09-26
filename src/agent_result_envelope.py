"""Fail-closed compatibility envelope for harvested agent results.

This module preserves useful donor result fields without allowing missing
identity or status to become provider truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

_ALLOWED_STATUSES = {"success", "failed", "blocked", "requires_input"}


@dataclass(frozen=True)
class AgentResultEnvelope:
    task_id: str
    agent_id: str
    status: str
    facts: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    recommended_changes: List[Dict[str, Any]] = field(default_factory=list)
    executed_changes: List[Dict[str, Any]] = field(default_factory=list)
    verification: List[Dict[str, Any]] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    raw_output: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("task_id", "agent_id", "status"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError("status is not an allowed explicit state")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResultEnvelope":
        if not isinstance(data, dict):
            raise TypeError("agent result must be an object")
        missing = [key for key in ("task_id", "agent_id", "status") if key not in data]
        if missing:
            raise ValueError("missing required fields: " + ", ".join(missing))
        return cls(
            task_id=data["task_id"],
            agent_id=data["agent_id"],
            status=data["status"],
            facts=data.get("facts", []),
            sources=data.get("sources", []),
            findings=data.get("findings", []),
            artifacts=data.get("artifacts", []),
            recommended_changes=data.get("recommended_changes", []),
            executed_changes=data.get("executed_changes", []),
            verification=data.get("verification", []),
            unresolved=data.get("unresolved", []),
            raw_output=data.get("raw_output"),
        )
