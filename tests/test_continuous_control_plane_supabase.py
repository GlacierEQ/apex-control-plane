from __future__ import annotations
from datetime import UTC, datetime
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from continuous_control_plane import ControlEvent
from continuous_control_plane_supabase import (
    BACKEND_PROJECT_REF,
    continuity_event_plan,
    legal_event_plan,
    prepare_outbound_plan,
    preflight_outbound_plan,
    start_outbound_plan,
    finish_outbound_plan,
    action_receipt_plan,
    legal_snapshot_plan,
)

NOW=datetime(2026,9,3,9,30,tzinfo=UTC)

def ev():
    return ControlEvent(
        event_type="gmail.reply.received",
        source_system="gmail",
        subject_id="case:1FDV-23-0001009",
        correlation_id="corr-1",
        occurred_at=NOW,
        payload={"message_id":"m1","thread_id":"t1"},
        provenance_refs=("gmail:m1",),
    )

def test_live_backend_contract_matches_observed_supabase_kernel():
    cfg=json.loads((ROOT/"config"/"continuous_control_plane_supabase.json").read_text())
    assert cfg["authoritative_project"]["project_ref"]==BACKEND_PROJECT_REF
    assert "legal_control_outbox_v1" in cfg["legal_tables"]
    assert cfg["rpcs"]["preflight_outbound"]=="continuity_preflight_outbound_v2"
    assert cfg["rpcs"]["legal_snapshot"]=="legal_execution_snapshot_v1"

def test_provider_event_plans_preserve_source_and_matter_identity():
    c=continuity_event_plan(ev(),account_key="glacier",external_id="m1",external_type="email",matter_key="case:1FDV-23-0001009")
    l=legal_event_plan(ev(),matter_key="case:1FDV-23-0001009",event_key="gmail:m1")
    assert c.rpc=="continuity_ingest_external_event_v1"
    assert c.args["p_external_id"]=="m1"
    assert l.rpc=="legal_control_ingest_event_v1"
    assert l.args["p_source_ref"]=="gmail:m1"
    assert l.approval_required is False

def test_state_change_request_is_explicitly_approval_bound():
    p=legal_event_plan(
        ev(),matter_key="case:1FDV-23-0001009",event_key="gmail:m1",
        desired_state="ACK_PENDING",operator_approved=False,
    )
    assert p.approval_required is True
    assert p.args["p_operator_approved"] is False

def test_outbound_transaction_has_preflight_execution_finish_and_receipt_phases():
    prep=prepare_outbound_plan(
        matter_key="case:1FDV-23-0001009",target_entity_key=None,
        channel="email",target="recipient@example.invalid",
        action_purpose="ack follow-up",idempotency_key="idem-1",
    )
    pre=preflight_outbound_plan(packet_id="00000000-0000-0000-0000-000000000001",channel="email",target="recipient@example.invalid")
    start=start_outbound_plan(action_id="00000000-0000-0000-0000-000000000002",provider_ref=None,detail={})
    finish=finish_outbound_plan(action_id="00000000-0000-0000-0000-000000000002",terminal_status="sent",provider_ref="gmail:m2")
    receipt=action_receipt_plan(
        action_id="00000000-0000-0000-0000-000000000002",
        matter_key="case:1FDV-23-0001009",packet_id=None,channel="email",
        receipt_type="provider_readback",outcome="sent",provider_ref="gmail:m2",detail={},
    )
    assert [prep.rpc,pre.rpc,start.rpc,finish.rpc,receipt.rpc]==[
        "continuity_prepare_outbound_v1",
        "continuity_preflight_outbound_v2",
        "continuity_start_outbound_v1",
        "continuity_finish_outbound_v1",
        "continuity_record_action_receipt_v1",
    ]
    assert start.approval_required is True
    assert finish.approval_required is False

def test_snapshot_is_read_only_and_non_authorizing():
    p=legal_snapshot_plan(matter_key="case:1FDV-23-0001009")
    assert p.mutation is False
    assert p.approval_required is False
