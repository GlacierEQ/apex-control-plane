"""
APEX CONTROL PLANE CONTRACTS: AGENT RESULT
Standard: Strict JSON Schema Extraction contract for Manus and reasoning workers.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentResult:
    task_id: str
    agent_id: str
    status: str = "success"  # "success", "failed", "blocked", "requires_input"
    facts: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    recommended_changes: List[Dict[str, Any]] = field(default_factory=list)
    executed_changes: List[Dict[str, Any]] = field(default_factory=list)
    verification: List[Dict[str, Any]] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    raw_output: Optional[str] = None
    completed_at_utc: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentResult:
        return cls(
            task_id=data.get("task_id", ""),
            agent_id=data.get("agent_id", "manus_worker"),
            status=data.get("status", "success"),
            facts=data.get("facts", []),
            sources=data.get("sources", []),
            findings=data.get("findings", []),
            artifacts=data.get("artifacts", []),
            recommended_changes=data.get("recommended_changes", []),
            executed_changes=data.get("executed_changes", []),
            verification=data.get("verification", []),
            unresolved=data.get("unresolved", []),
            raw_output=data.get("raw_output"),
            completed_at_utc=data.get("completed_at_utc", time.time()),
        )
