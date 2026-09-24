import pytest

from src.durable_mission_lifecycle import ContextSnapshot, DurableMissionLifecycle, MissionStage


def hydrated() -> DurableMissionLifecycle:
    mission = DurableMissionLifecycle("m-1")
    mission.transition(MissionStage.CONTEXT_HYDRATING, reason="recover sources")
    mission.bind_context(ContextSnapshot(
        mission_id="m-1",
        source_versions={"github:GlacierEQ/apex-control-plane": "abc123"},
        verified_state=({"fact": "provider-read"},),
        degraded_lanes=("optional-memory-lane",),
    ))
    return mission


def test_context_is_source_versioned_and_degraded_lane_does_not_stop_mission():
    mission = hydrated()
    assert mission.stage is MissionStage.CONTEXT_READY
    assert mission.context is not None
    assert mission.context.mission_stop is False
    mission.require_source_version("github:GlacierEQ/apex-control-plane", "abc123")


def test_stale_source_version_is_detected_without_becoming_permission_semantics():
    mission = hydrated()
    with pytest.raises(ValueError, match="stale source version"):
        mission.require_source_version("github:GlacierEQ/apex-control-plane", "new-head")
    assert mission.stage is MissionStage.CONTEXT_READY


def test_context_can_be_rehydrated_before_execution():
    mission = hydrated()
    mission.transition(MissionStage.CONTEXT_HYDRATING, reason="provider advanced; recover delta")
    mission.bind_context(ContextSnapshot(
        mission_id="m-1",
        source_versions={"github:GlacierEQ/apex-control-plane": "new-head"},
    ))
    mission.require_source_version("github:GlacierEQ/apex-control-plane", "new-head")


def test_illegal_stage_skip_is_rejected():
    mission = DurableMissionLifecycle("m-1")
    with pytest.raises(ValueError, match="illegal mission transition"):
        mission.transition(MissionStage.MUTATING, reason="skip evidence")


def test_completion_requires_readback_and_receipt():
    mission = DurableMissionLifecycle("m-1", stage=MissionStage.RECEIPTING)
    with pytest.raises(ValueError, match="verified readback"):
        mission.mark_complete(readback_verified=False, receipt_recorded=True)
    with pytest.raises(ValueError, match="verified readback"):
        mission.mark_complete(readback_verified=True, receipt_recorded=False)
    mission.mark_complete(readback_verified=True, receipt_recorded=True)
    assert mission.stage is MissionStage.COMPLETE


def test_context_snapshot_is_evidence_not_authority_grant():
    snapshot = ContextSnapshot(
        mission_id="m-1",
        source_versions={"provider:x": "v1"},
        unverified_claims=({"claim": "candidate only"},),
    )
    assert not hasattr(snapshot, "approved")
    assert not hasattr(snapshot, "authority_grant")
