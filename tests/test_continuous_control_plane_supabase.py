from datetime import UTC, datetime

import pytest

from continuous_control_plane_supabase import (
    BACKEND_PROJECT_REF,
    legal_event_plan,
    legal_snapshot_plan,
    prepare_outbound_plan,
    start_outbound_plan,
)
from source_bound_authorization import (
    AuthorizationScopeError,
    AuthorizationScopeKind,
    SourceBoundAuthorization,
)


def auth(kind=AuthorizationScopeKind.PLAN_BATCH, *, operations=None,
         allow_material_strategy_delta=False):
    return SourceBoundAuthorization(
        source_ref="operator://mission/42",
        kind=kind,
        connector="supabase",
        operations=frozenset(operations or {
            "legal_control_ingest_event_v1",
            "continuity_prepare_outbound_v1",
            "continuity_start_outbound_v1",
        }),
        target_constraints={"project_ref": BACKEND_PROJECT_REF},
        plan_ref="plan-42" if kind is AuthorizationScopeKind.PLAN_BATCH else None,
        allow_material_strategy_delta=allow_material_strategy_delta,
    )


def test_plan_batch_constituent_carries_authority_provenance_without_fresh_approval():
    envelope = auth()
    plan = prepare_outbound_plan(
        authorization=envelope, matter_key="MAT-1", target_entity_key=None,
        channel="email", target="provider@example.test", action_purpose="follow-up",
        idempotency_key="idem-1",
    )
    assert plan.authority_source_ref == envelope.source_ref
    assert plan.authority_envelope_sha256 == envelope.envelope_sha256
    assert "approval_required" not in plan.__dataclass_fields__
    assert "operator_approved" not in plan.args


def test_explicit_action_and_action_class_are_valid_authority_shapes():
    for kind in (AuthorizationScopeKind.EXPLICIT_ACTION, AuthorizationScopeKind.ACTION_CLASS):
        envelope = auth(kind, operations={"continuity_start_outbound_v1"})
        plan = start_outbound_plan(
            authorization=envelope, action_id="A-1", provider_ref=None, detail={"x": 1}
        )
        assert plan.authority_envelope_sha256 == envelope.envelope_sha256


def test_out_of_envelope_rpc_is_rejected():
    envelope = auth(operations={"continuity_prepare_outbound_v1"})
    with pytest.raises(AuthorizationScopeError, match="operation is outside"):
        start_outbound_plan(
            authorization=envelope, action_id="A-1", provider_ref=None, detail={}
        )


def test_material_strategy_delta_requires_envelope_authority():
    now = datetime.now(UTC)
    with pytest.raises(AuthorizationScopeError, match="material strategy delta"):
        legal_event_plan(
            authorization=auth(), matter_key="MAT-1", event_key="E-1",
            event_type="transition", occurred_at=now, source_system="provider",
            payload={}, desired_state="ESCALATED", material_strategy_delta=True,
        )
    permitted = legal_event_plan(
        authorization=auth(allow_material_strategy_delta=True), matter_key="MAT-1",
        event_key="E-2", event_type="transition", occurred_at=now,
        source_system="provider", payload={}, desired_state="ESCALATED",
        material_strategy_delta=True,
    )
    assert permitted.authority_source_ref == "operator://mission/42"


def test_idempotency_key_survives_planning_unchanged():
    plan = prepare_outbound_plan(
        authorization=auth(), matter_key="MAT-1", target_entity_key="entity-1",
        channel="email", target="provider@example.test", action_purpose="follow-up",
        idempotency_key="stable-idem-key",
    )
    assert plan.args["p_idempotency_key"] == "stable-idem-key"


def test_snapshot_is_read_only_and_does_not_require_authority_envelope():
    plan = legal_snapshot_plan(matter_key="MAT-1")
    assert plan.mutation is False
    assert plan.authority_source_ref is None
    assert plan.authority_envelope_sha256 is None
