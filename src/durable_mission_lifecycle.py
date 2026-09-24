"""Compatibility harvest from feat/durable-workflow-machine.

Donor provenance:
- contracts/mission.py
- contracts/context_pack.py
- workflows/master_run.py

Preserved mechanism: explicit durable mission lifecycle and source-versioned context
snapshotting. Deliberately excluded: RootTruth/single-owner authority, context
freezing as a permission gate, and any implication that a lifecycle state outranks
current Operator authority or provider-native truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class MissionStage(str, Enum):
    RECEIVED = "RECEIVED"
    CONTEXT_HYDRATING = "CONTEXT_HYDRATING"
    CONTEXT_READY = "CONTEXT_READY"
    EXECUTING = "EXECUTING"
    RECONCILING = "RECONCILING"
    CHANGESET_READY = "CHANGESET_READY"
    PREFLIGHT = "PREFLIGHT"
    MUTATING = "MUTATING"
    READBACK = "READBACK"
    VERIFYING = "VERIFYING"
    RECEIPTING = "RECEIPTING"
    COMPLETE = "COMPLETE"
    WAITING_INPUT = "WAITING_INPUT"
    RETRYING = "RETRYING"
    COMPENSATING = "COMPENSATING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


LEGAL_TRANSITIONS: dict[MissionStage, frozenset[MissionStage]] = {
    MissionStage.RECEIVED: frozenset({MissionStage.CONTEXT_HYDRATING, MissionStage.BLOCKED, MissionStage.FAILED}),
    MissionStage.CONTEXT_HYDRATING: frozenset({MissionStage.CONTEXT_READY, MissionStage.WAITING_INPUT, MissionStage.FAILED}),
    MissionStage.CONTEXT_READY: frozenset({MissionStage.EXECUTING, MissionStage.CONTEXT_HYDRATING, MissionStage.FAILED}),
    MissionStage.EXECUTING: frozenset({MissionStage.RECONCILING, MissionStage.RETRYING, MissionStage.FAILED}),
    MissionStage.RECONCILING: frozenset({MissionStage.CHANGESET_READY, MissionStage.FAILED}),
    MissionStage.CHANGESET_READY: frozenset({MissionStage.PREFLIGHT, MissionStage.FAILED}),
    MissionStage.PREFLIGHT: frozenset({MissionStage.MUTATING, MissionStage.BLOCKED, MissionStage.FAILED}),
    MissionStage.MUTATING: frozenset({MissionStage.READBACK, MissionStage.COMPENSATING, MissionStage.FAILED}),
    MissionStage.READBACK: frozenset({MissionStage.VERIFYING, MissionStage.FAILED}),
    MissionStage.VERIFYING: frozenset({MissionStage.RECEIPTING, MissionStage.COMPENSATING, MissionStage.FAILED}),
    MissionStage.RECEIPTING: frozenset({MissionStage.COMPLETE, MissionStage.FAILED}),
    MissionStage.COMPLETE: frozenset(),
    MissionStage.WAITING_INPUT: frozenset({MissionStage.CONTEXT_HYDRATING, MissionStage.FAILED}),
    MissionStage.RETRYING: frozenset({MissionStage.CONTEXT_HYDRATING, MissionStage.EXECUTING, MissionStage.FAILED}),
    MissionStage.COMPENSATING: frozenset({MissionStage.FAILED, MissionStage.RETRYING}),
    MissionStage.BLOCKED: frozenset({MissionStage.RETRYING, MissionStage.WAITING_INPUT, MissionStage.FAILED}),
    MissionStage.FAILED: frozenset({MissionStage.RETRYING}),
}


@dataclass(frozen=True)
class ContextSnapshot:
    """Evidence snapshot, never a replacement authority source."""

    mission_id: str
    source_versions: Mapping[str, str]
    verified_state: tuple[Mapping[str, Any], ...] = ()
    unverified_claims: tuple[Mapping[str, Any], ...] = ()
    degraded_lanes: tuple[str, ...] = ()

    @property
    def mission_stop(self) -> bool:
        """A degraded retrieval lane changes route, not mission."""
        return False

    def version_of(self, source: str) -> str | None:
        return self.source_versions.get(source)


@dataclass
class DurableMissionLifecycle:
    mission_id: str
    stage: MissionStage = MissionStage.RECEIVED
    transitions: list[dict[str, str]] = field(default_factory=list)
    context: ContextSnapshot | None = None

    def transition(self, target: MissionStage, *, reason: str) -> None:
        if target not in LEGAL_TRANSITIONS[self.stage]:
            raise ValueError(f"illegal mission transition {self.stage.value} -> {target.value}")
        previous = self.stage
        self.stage = target
        self.transitions.append({"from": previous.value, "to": target.value, "reason": reason})

    def bind_context(self, snapshot: ContextSnapshot) -> None:
        if self.stage is not MissionStage.CONTEXT_HYDRATING:
            raise ValueError("context may be bound only while hydrating")
        if snapshot.mission_id != self.mission_id:
            raise ValueError("context mission_id mismatch")
        if not snapshot.source_versions:
            raise ValueError("source-bearing context requires source_versions")
        self.context = snapshot
        self.transition(MissionStage.CONTEXT_READY, reason="source-bearing context applied")

    def require_source_version(self, source: str, observed_version: str) -> None:
        """Detect stale hydrated context without turning freshness into authority."""
        if self.context is None:
            raise ValueError("context not bound")
        expected = self.context.version_of(source)
        if expected is None:
            raise ValueError(f"source version not recorded: {source}")
        if expected != observed_version:
            raise ValueError(f"stale source version for {source}: {expected} != {observed_version}")

    def mark_complete(self, *, readback_verified: bool, receipt_recorded: bool) -> None:
        """Completion requires verified reality plus receipt, never write success alone."""
        if self.stage is not MissionStage.RECEIPTING:
            raise ValueError("mission may complete only from RECEIPTING")
        if not readback_verified or not receipt_recorded:
            raise ValueError("completion requires verified readback and recorded receipt")
        self.transition(MissionStage.COMPLETE, reason="verified readback and receipt recorded")
