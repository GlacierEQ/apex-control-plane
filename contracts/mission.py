"""
APEX CONTROL PLANE CONTRACTS: MISSION
Standard: Formal Typed Mission Schema and Master Workflow State Machine.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class MissionStatus(str, enum.Enum):
    # Master Forward Lifecycle
    RECEIVED = "RECEIVED"
    CONTEXT_HYDRATING = "CONTEXT_HYDRATING"
    CONTEXT_LOCKED = "CONTEXT_LOCKED"
    MISSION_COMPILED = "MISSION_COMPILED"
    DISPATCHING = "DISPATCHING"
    EXECUTING = "EXECUTING"
    RESULTS_COLLECTING = "RESULTS_COLLECTING"
    RECONCILING = "RECONCILING"
    CHANGESET_READY = "CHANGESET_READY"
    PREFLIGHT = "PREFLIGHT"
    MUTATING = "MUTATING"
    READBACK = "READBACK"
    VERIFYING = "VERIFYING"
    COMMITTING_STATE = "COMMITTING_STATE"
    COMPLETE = "COMPLETE"

    # Controlled Side States
    WAITING_INPUT = "WAITING_INPUT"
    RETRYING = "RETRYING"
    COMPENSATING = "COMPENSATING"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


# The Master Invariant: Neither execution, mutation, nor HTTP 200 means completion.
# Only mutation + readback + (expected == observed) allows transition to COMPLETE.
TERMINAL_STATES = {MissionStatus.COMPLETE, MissionStatus.FAILED, MissionStatus.BLOCKED}


@dataclass
class SourceState:
    repositories: List[str] = field(default_factory=list)
    notion_pages: List[str] = field(default_factory=list)
    dropbox_paths: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)


@dataclass
class Mission:
    mission_id: str
    correlation_id: str
    objective: str
    project: str
    priority: str = "P0"  # P0, P1, P2
    source_state: SourceState = field(default_factory=SourceState)
    constraints: List[str] = field(default_factory=list)
    required_outputs: List[str] = field(default_factory=list)
    allowed_mutations: List[str] = field(default_factory=list)
    verification_requirements: List[str] = field(default_factory=list)
    status: MissionStatus = MissionStatus.RECEIVED
    created_at_utc: float = field(default_factory=time.time)
    updated_at_utc: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        objective: str,
        project: str,
        priority: str = "P0",
        repositories: Optional[List[str]] = None,
        notion_pages: Optional[List[str]] = None,
        dropbox_paths: Optional[List[str]] = None,
        evidence_refs: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        required_outputs: Optional[List[str]] = None,
        allowed_mutations: Optional[List[str]] = None,
        verification_requirements: Optional[List[str]] = None,
    ) -> Mission:
        m_id = f"msn_{uuid.uuid4().hex[:12]}"
        corr_id = f"run_{uuid.uuid4().hex[:12]}"
        return cls(
            mission_id=m_id,
            correlation_id=corr_id,
            objective=objective,
            project=project,
            priority=priority,
            source_state=SourceState(
                repositories=repositories or [],
                notion_pages=notion_pages or [],
                dropbox_paths=dropbox_paths or [],
                evidence_refs=evidence_refs or [],
            ),
            constraints=constraints or [],
            required_outputs=required_outputs or [],
            allowed_mutations=allowed_mutations or [],
            verification_requirements=verification_requirements or [],
            status=MissionStatus.RECEIVED,
        )

    def transition_to(self, new_status: MissionStatus, reason: Optional[str] = None) -> None:
        """Enforces legal state transitions."""
        if self.status in TERMINAL_STATES and new_status not in {MissionStatus.RETRYING, MissionStatus.COMPENSATING}:
            raise ValueError(f"Cannot transition from terminal state {self.status} to {new_status}")
        self.status = new_status
        self.updated_at_utc = time.time()
        if reason:
            self.metadata.setdefault("transition_log", []).append({
                "from": str(self.status),
                "to": str(new_status),
                "timestamp_utc": self.updated_at_utc,
                "reason": reason,
            })

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d
