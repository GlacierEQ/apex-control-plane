"""Regression tests for APEX mission continuation (no confidential case data)."""
from __future__ import annotations

from pathlib import Path
import sys
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mission_forward_progress import (
    ForwardAction, ForwardReceipt, ForwardLedger, choose_forward_action,
)


def action(action_id, *, method="original", state="state:v31",
           benefit=5, urgency=5, authorized=True, external=False,
           external_authorized=False, already_done=False):
    return ForwardAction(
        action_id=action_id, method_id=method, source_state_ref=state,
        expected_benefit=benefit, urgency=urgency, authorized=authorized,
        external_effect=external,
        external_effect_authorized=external_authorized,
        already_completed=already_done,
    )


def test_blocked_write_routes_to_fresh_high_benefit_action():
    old = ForwardReceipt(
        "provider-write", "original", "state:v31", "BLOCKED", "provider-error:blocked"
    )
    choice = choose_forward_action("mission:EXAMPLE", [
        action("provider-write", benefit=8),
        action("current-target-review", benefit=10),
    ], [old])
    assert choice.action_id == "current-target-review"
    assert choice.status == "EXECUTE"
    assert "provider-write" in choice.suppressed


def test_no_replay_of_unchanged_retrieval_or_completed_task():
    history = [ForwardReceipt(
        "already-audited-material", "original", "state:v31",
        "NO_DELTA", "source:existing",
    )]
    choice = choose_forward_action("mission:EXAMPLE", [
        action("already-audited-material"),
        action("completed-admin-step", already_done=True),
        action("unresolved-current-state"),
    ], history)
    assert choice.action_id == "unresolved-current-state"
    assert set(choice.suppressed) == {
        "already-audited-material", "completed-admin-step",
    }


def test_changed_method_or_source_state_allows_meaningful_retry():
    history = [ForwardReceipt(
        "write", "method-1", "state:v31", "BLOCKED", "provider-error:safety",
    )]
    assert choose_forward_action(
        "mission:EXAMPLE", [action("write", method="method-2")], history,
    ).action_id == "write"
    assert choose_forward_action(
        "mission:EXAMPLE", [action("write", state="state:v32")], history,
    ).action_id == "write"


def test_external_effect_requires_distinct_explicit_authorization():
    choice = choose_forward_action("mission:EXAMPLE", [
        action("external-send", external=True, benefit=10),
        action("internal-ready-work", benefit=2),
    ])
    assert choice.action_id == "internal-ready-work"
    assert "external-send" in choice.suppressed
    assert choose_forward_action("mission:EXAMPLE", [
        action("external-send", external=True, external_authorized=True),
    ]).action_id == "external-send"


def test_all_blocked_does_not_claim_mission_closure():
    h = [ForwardReceipt(
        "write", "original", "state:v31", "BLOCKED", "provider-error:safety",
    )]
    choice = choose_forward_action("mission:EXAMPLE", [
        action("write"), action("external-send", external=True),
    ], h)
    assert choice.status == "NO_AUTHORIZED_FRESH_ROUTE"
    assert choice.action_id is None
    assert choice.mission_complete is False


def test_priority_favors_consequential_work_over_repeat_analysis():
    choice = choose_forward_action("mission:EXAMPLE", [
        action("low-value", benefit=1, urgency=1),
        action("urgent-beneficial-task", benefit=9, urgency=10),
    ])
    assert choice.action_id == "urgent-beneficial-task"


def test_activity_cannot_impersonate_source_native_human_outcome():
    ledger = ForwardLedger(mission_id="mission:EXAMPLE")
    ledger.record(ForwardReceipt(
        "analysis", "original", "state:v31", "INTERMEDIATE", "box:file-2",
        readback_ref="box:readback-2",
    ))
    assert ledger.human_outcomes == 0
    assert ledger.mission_outcomes == 0
    with pytest.raises(ValueError):
        ledger.record(ForwardReceipt(
            "alleged-outcome", "original", "state:v31", "HUMAN_OUTCOME",
            "assistant:report", after_state_ref="state:v32",
            readback_ref="assistant:summary", source_class="assistant",
        ))
    ledger.record(ForwardReceipt(
        "external-verification", "original", "state:v31", "HUMAN_OUTCOME",
        "provider:verified-event", after_state_ref="state:v32",
        readback_ref="provider:independent-readback",
        source_class="source_native", outcome_scope="contact",
    ))
    assert ledger.human_outcomes == 1
    assert ledger.current_contact_state == "VERIFIED_CONTACT_EVENT"


def test_material_delta_needs_different_state_and_readback():
    ledger = ForwardLedger(mission_id="mission:EXAMPLE")
    with pytest.raises(ValueError):
        ledger.record(ForwardReceipt(
            "write", "original", "state:v31", "VERIFIED_MATERIAL_DELTA",
            "provider:receipt", after_state_ref="state:v31",
            readback_ref="provider:readback", source_class="source_native",
        ))
    with pytest.raises(ValueError):
        ledger.record(ForwardReceipt(
            "write", "original", "state:v31", "VERIFIED_MATERIAL_DELTA",
            "provider:receipt", after_state_ref="state:v32",
            source_class="source_native",
        ))


def test_durable_journal_restores_blocked_paths_and_mission_identity():
    ledger = ForwardLedger("mission:EXAMPLE")
    ledger.record(ForwardReceipt(
        "write", "original", "state:v31", "BLOCKED", "provider-error:safety",
    ))
    restored = ForwardLedger.from_snapshot(
        ledger.snapshot(), expected_mission_id="mission:EXAMPLE",
    )
    assert restored.choose([action("write"), action("alternate")]).action_id == "alternate"
    with pytest.raises(ValueError):
        ForwardLedger.from_snapshot(
            ledger.snapshot(), expected_mission_id="mission:OTHER",
        )


def test_bounded_negative_search_is_not_zero_events():
    ledger = ForwardLedger("mission:EXAMPLE")
    assert ledger.human_outcomes == 0
    assert ledger.current_contact_state == "NOT_CHECKED"
    ledger.record(ForwardReceipt(
        "contact-search", "original", "state:v31",
        "NO_DELTA", "provider:bounded-negative-search",
    ))
    assert ledger.current_contact_state == "NOT_CHECKED"


def test_unchanged_failed_route_cannot_count_as_progress():
    ledger = ForwardLedger("mission:EXAMPLE")
    ledger.record(ForwardReceipt(
        "write", "original", "state:v31", "BLOCKED", "provider-error:safety",
    ))
    choice = ledger.choose([action("write")])
    assert choice.action_id is None
    assert choice.mission_complete is False


def test_unverified_authority_and_bad_types_are_rejected():
    with pytest.raises(ValueError):
        action("bad", benefit=-1)
    with pytest.raises(ValueError):
        action("bad", authorized="yes")
    assert choose_forward_action("mission:EXAMPLE", [
        action("not-authorized", authorized=False),
    ]).status == "NO_AUTHORIZED_FRESH_ROUTE"


def test_exact_native_receipt_replay_is_idempotent():
    ledger = ForwardLedger("mission:EXAMPLE")
    receipt = ForwardReceipt(
        "write", "original", "state:v31", "BLOCKED", "provider-error:safety",
    )
    ledger.record(receipt)
    ledger.record(receipt)
    assert len(ledger.receipts) == 1
