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

# Forward spine used by MasterWorkflowRunner. Illegal to skip or reverse these edges.
FORWARD_SPINE = (
    MissionStatus.RECEIVED,
    MissionStatus.CONTEXT_HYDRATING,
    MissionStatus.CONTEXT_LOCKED,
    MissionStatus.MISSION_COMPILED,
    MissionStatus.DISPATCHING,
    MissionStatus.EXECUTING,
    MissionStatus.RESULTS_COLLECTING,
    MissionStatus.RECONCILING,
    MissionStatus.CHANGESET_READY,
    MissionStatus.PREFLIGHT,
    MissionStatus.MUTATING,
    MissionStatus.READBACK,
    MissionStatus.VERIFYING,
    MissionStatus.COMMITTING_STATE,
    MissionStatus.COMPLETE,
)

LEGAL_TRANSITIONS: dict[MissionStatus, frozenset[MissionStatus]] = {
    MissionStatus.RECEIVED: frozenset(
        {MissionStatus.CONTEXT_HYDRATING, MissionStatus.FAILED, MissionStatus.BLOCKED}
    ),
    MissionStatus.CONTEXT_HYDRATING: frozenset(
        {MissionStatus.CONTEXT_LOCKED, MissionStatus.WAITING_INPUT, MissionStatus.FAILED}
    ),
    MissionStatus.CONTEXT_LOCKED: frozenset(
        {MissionStatus.MISSION_COMPILED, MissionStatus.FAILED}
    ),
    MissionStatus.MISSION_COMPILED: frozenset(
        {MissionStatus.DISPATCHING, MissionStatus.FAILED}
    ),
    MissionStatus.DISPATCHING: frozenset(
        {MissionStatus.EXECUTING, MissionStatus.BLOCKED, MissionStatus.FAILED}
    ),
    MissionStatus.EXECUTING: frozenset(
        {MissionStatus.RESULTS_COLLECTING, MissionStatus.RETRYING, MissionStatus.FAILED}
    ),
    MissionStatus.RESULTS_COLLECTING: frozenset(
        {MissionStatus.RECONCILING, MissionStatus.FAILED}
    ),
    MissionStatus.RECONCILING: frozenset(
        {MissionStatus.CHANGESET_READY, MissionStatus.FAILED}
    ),
    MissionStatus.CHANGESET_READY: frozenset(
        {MissionStatus.PREFLIGHT, MissionStatus.FAILED}
    ),
    MissionStatus.PREFLIGHT: frozenset(
        {MissionStatus.MUTATING, MissionStatus.BLOCKED, MissionStatus.FAILED}
    ),
    MissionStatus.MUTATING: frozenset(
        {MissionStatus.READBACK, MissionStatus.COMPENSATING, MissionStatus.FAILED}
    ),
    MissionStatus.READBACK: frozenset(
        {MissionStatus.VERIFYING, MissionStatus.FAILED}
    ),
    MissionStatus.VERIFYING: frozenset(
        {
            MissionStatus.COMMITTING_STATE,
            MissionStatus.COMPENSATING,
            MissionStatus.FAILED,
        }
    ),
    MissionStatus.COMMITTING_STATE: frozenset(
        {MissionStatus.COMPLETE, MissionStatus.PARTIAL, MissionStatus.FAILED}
    ),
    MissionStatus.COMPLETE: frozenset(
        {MissionStatus.RETRYING, MissionStatus.COMPENSATING}
    ),
    MissionStatus.FAILED: frozenset(
        {MissionStatus.RETRYING, MissionStatus.COMPENSATING}
    ),
    MissionStatus.BLOCKED: frozenset(
        {MissionStatus.RETRYING, MissionStatus.WAITING_INPUT, MissionStatus.FAILED}
    ),
    MissionStatus.PARTIAL: frozenset(
        {MissionStatus.RETRYING, MissionStatus.COMPENSATING, MissionStatus.COMPLETE}
    ),
    MissionStatus.RETRYING: frozenset(
        {
            MissionStatus.CONTEXT_HYDRATING,
            MissionStatus.DISPATCHING,
            MissionStatus.EXECUTING,
        }
    ),
    MissionStatus.COMPENSATING: frozenset(
        {MissionStatus.FAILED, MissionStatus.PARTIAL}
    ),
    MissionStatus.WAITING_INPUT: frozenset(
        {MissionStatus.CONTEXT_HYDRATING, MissionStatus.DISPATCHING, MissionStatus.FAILED}
    ),
}


def is_legal_transition(current: MissionStatus, new_status: MissionStatus) -> bool:
    """Return True iff the directed edge exists on the mission graph."""
    allowed = LEGAL_TRANSITIONS.get(current)
    if allowed is None:
        return False
    return new_status in allowed


def walk_forward_spine(mission: "Mission") -> "Mission":
    """Advance a mission along FORWARD_SPINE from its current node to COMPLETE."""
    return advance_to(mission, MissionStatus.COMPLETE)


def advance_to(mission: "Mission", target: MissionStatus) -> "Mission":
    """Walk FORWARD_SPINE from the current node to target. No skips."""
    if mission.status == target:
        return mission
    if mission.status not in FORWARD_SPINE or target not in FORWARD_SPINE:
        raise ValueError(
            f"advance_to only walks the forward spine, not {mission.status} -> {target}"
        )
    start = FORWARD_SPINE.index(mission.status)
    dest = FORWARD_SPINE.index(target)
    if dest <= start:
        raise ValueError(
            f"Cannot advance backwards along spine {mission.status} -> {target}"
        )
    for nxt in FORWARD_SPINE[start + 1 : dest + 1]:
        mission.transition_to(nxt, reason="advance-to")
    return mission


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
        """Enforces legal state transitions. Logs the previous status before mutation."""
        old_status = self.status
        if not is_legal_transition(old_status, new_status):
            raise ValueError(
                f"Cannot transition from terminal state {old_status} to {new_status}"
                if old_status in TERMINAL_STATES
                else f"Illegal mission transition {old_status} -> {new_status}"
            )
        self.status = new_status
        self.updated_at_utc = time.time()
        self.metadata.setdefault("transition_log", []).append({
            "from": str(old_status),
            "to": str(new_status),
            "timestamp_utc": self.updated_at_utc,
            "reason": reason,
        })

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d
