from pathlib import Path
import sys

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from continuous_impact_selection import (  # noqa: E402
    ContinuousImpactSelector,
    ImpactCandidate,
    ImpactSelectionViolation,
)


def _candidate(
    candidate_id: str,
    operation: str,
    expected_delta: str,
    *,
    operation_class: str = "repair_runtime_selection",
    **features: float,
) -> ImpactCandidate:
    return ImpactCandidate(
        candidate_id=candidate_id,
        operation=operation,
        operation_class=operation_class,
        expected_delta=expected_delta,
        features=features,
        evidence_refs=(f"test:{candidate_id}",),
    )


def test_live_runtime_repair_beats_another_rule_copy() -> None:
    selector = ContinuousImpactSelector()
    candidates = (
        _candidate(
            "rule-copy",
            "add another impact rule beside existing prompts",
            "another passive instruction exists",
            mission_advancement=0.15,
            state_change_value=0.10,
            success_impact=0.15,
            execution_proximity=0.10,
            prior_gain_preservation=0.80,
            reversibility=0.95,
            already_done_risk=1.0,
            meta_substitution_risk=0.95,
            rule_accretion_risk=1.0,
            rediscovery_risk=0.90,
        ),
        _candidate(
            "wire-ranker",
            "wire adaptive impact ranking into the live action-selection path",
            "candidate actions are compared by impact before execution",
            mission_advancement=1.0,
            state_change_value=0.95,
            success_impact=0.95,
            execution_proximity=0.90,
            prior_gain_preservation=1.0,
            reversibility=0.80,
            failure_risk=0.20,
            meta_substitution_risk=0.05,
            rule_accretion_risk=0.05,
            rediscovery_risk=0.05,
        ),
    )

    decision = selector.select(
        task_id="selection-defect",
        mission="make impact evaluation causally control the next operation",
        operation_class="repair_runtime_selection",
        state_version="git:main@before",
        candidates=candidates,
    )

    assert decision.selected_candidate_id == "wire-ranker"
    assert decision.ranked_candidate_ids[0] == "wire-ranker"
    assert decision.decision_sha256
    frame = selector.execution_frame(decision)
    assert frame["role"] == "system"
    assert "wire adaptive impact ranking" in frame["content"]
    assert "Re-evaluate after any material state change" in frame["content"]


def test_reweight_after_material_state_change_can_change_next_action() -> None:
    selector = ContinuousImpactSelector()
    first = (
        _candidate(
            "inspect-host",
            "trace the live model host integration boundary",
            "the actual inference caller is identified",
            mission_advancement=0.95,
            state_change_value=0.70,
            execution_proximity=0.75,
            success_impact=0.85,
            already_done_risk=0.0,
        ),
        _candidate(
            "patch-host",
            "patch the model host now",
            "the model host enforces impact selection",
            mission_advancement=0.70,
            state_change_value=0.95,
            execution_proximity=0.90,
            success_impact=0.95,
            failure_risk=0.85,
            unsupported_claim_risk=0.75,
        ),
    )
    first_decision = selector.select(
        task_id="dynamic",
        mission="repair the live selection path",
        operation_class="repair_runtime_selection",
        state_version="state:unknown-host",
        candidates=first,
    )
    assert first_decision.selected_candidate_id == "inspect-host"

    second = (
        _candidate(
            "inspect-host",
            "trace the live model host integration boundary",
            "the actual inference caller is identified again",
            mission_advancement=0.15,
            state_change_value=0.05,
            execution_proximity=0.10,
            success_impact=0.10,
            already_done_risk=1.0,
            rediscovery_risk=1.0,
        ),
        _candidate(
            "patch-host",
            "patch the verified model host with impact-bound generation",
            "every generated action passes impact selection before execution",
            mission_advancement=1.0,
            state_change_value=1.0,
            execution_proximity=1.0,
            success_impact=1.0,
            prior_gain_preservation=1.0,
            failure_risk=0.15,
            unsupported_claim_risk=0.05,
        ),
    )
    second_decision = selector.select(
        task_id="dynamic",
        mission="repair the live selection path",
        operation_class="repair_runtime_selection",
        state_version="state:verified-host",
        candidates=second,
    )
    assert second_decision.selected_candidate_id == "patch-host"
    assert second_decision.state_version != first_decision.state_version
    assert second_decision.decision_sha256 != first_decision.decision_sha256
    assert len(selector.history()) == 2


def test_operation_class_rewrite_is_rejected_before_scoring() -> None:
    selector = ContinuousImpactSelector()
    candidates = (
        _candidate(
            "meta",
            "write a new governance architecture",
            "a new architecture document exists",
            operation_class="design_governance",
            mission_advancement=1.0,
            state_change_value=1.0,
        ),
        _candidate(
            "repair",
            "repair the runtime selection path",
            "selection behavior changes",
            mission_advancement=0.8,
            state_change_value=0.8,
        ),
    )
    decision = selector.select(
        task_id="op-class",
        mission="repair runtime selection",
        operation_class="repair_runtime_selection",
        state_version="state:1",
        candidates=candidates,
    )
    assert decision.selected_candidate_id == "repair"
    assert decision.rejected_candidate_ids == ("meta",)


def test_all_operation_class_rewrites_fail_closed() -> None:
    selector = ContinuousImpactSelector()
    candidates = (
        _candidate(
            "wrong",
            "summarize the defect",
            "summary exists",
            operation_class="summarize",
            mission_advancement=1.0,
        ),
    )
    try:
        selector.select(
            task_id="fail",
            mission="repair runtime selection",
            operation_class="repair_runtime_selection",
            state_version="state:1",
            candidates=candidates,
        )
    except ImpactSelectionViolation as exc:
        assert "no candidate preserves" in str(exc)
    else:
        raise AssertionError("operation-class rewrite must fail closed")


def test_operator_correction_changes_persisted_selection_in_new_worker(tmp_path) -> None:
    """Real feedback must alter the next selector even after re-instantiation."""
    state_path = tmp_path / "shared-learning.json"
    choices = (
        _candidate(
            "summarize-again", "repeat a summary instead of executing",
            "no external state changes", mission_advancement=0.2,
            state_change_value=0.1, correction_risk=1.0,
        ),
    )
    first = ContinuousImpactSelector(model_state_path=state_path)
    original = first.select(
        task_id="operator-learning", mission="make durable learning control decisions",
        operation_class="repair_runtime_selection",
        state_version="feedback:before", candidates=choices,
    )
    first.record_operator_correction(
        decision=original, candidates=choices,
        reason="Operator rejected repetitive summaries instead of execution",
    )
    assert state_path.exists()
    fresh = ContinuousImpactSelector(model_state_path=state_path)
    after = fresh.select(
        task_id="operator-learning", mission="make durable learning control decisions",
        operation_class="repair_runtime_selection",
        state_version="feedback:after", candidates=choices,
    )
    assert after.selected_candidate_id == original.selected_candidate_id
    assert after.score < original.score
    assert after.decision_sha256 != original.decision_sha256


def test_default_runtime_selector_uses_configured_shared_learning_state(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "worker-state.json"
    monkeypatch.setenv("GLACIEREQ_APEX_LEARNING_STATE_PATH", str(path))
    worker_a = ContinuousImpactSelector()
    assert worker_a.engine.model_state_path == path
    original = worker_a.engine.ranker.score(
        worker_a._to_adaptive(_candidate(
            "repeat", "repeat prior failure", "no improvement",
            correction_risk=1.0, mission_advancement=0.2,
        ))
    ).score
    worker_a.engine.record_operator_correction(
        task_id="configured-learning",
        candidate=worker_a._to_adaptive(_candidate(
            "repeat", "repeat prior failure", "no improvement",
            correction_risk=1.0, mission_advancement=0.2,
        )),
        reason="recover and apply prior feedback",
    )
    worker_b = ContinuousImpactSelector()
    assert worker_b.engine.model_state_path == path
    updated = worker_b.engine.ranker.score(
        worker_b._to_adaptive(_candidate(
            "repeat", "repeat prior failure", "no improvement",
            correction_risk=1.0, mission_advancement=0.2,
        ))
    ).score
    assert updated < original


# Forward progress regressions: the selector already controls action choice.
# These tests keep repeat suppression and authority INSIDE that existing path.

def _guarded(
    candidate_id: str,
    *, method: str = "original", source: str = "source:version1",
    authorized: bool = True, external: bool = False,
    external_authorized: bool = False, already_completed: bool = False,
    value: float = 0.9,
) -> ImpactCandidate:
    return ImpactCandidate(
        candidate_id=candidate_id,
        operation=f"advance {candidate_id}",
        operation_class="repair_runtime_selection",
        expected_delta=f"verified target-state improvement for {candidate_id}",
        features={"mission_advancement": value, "state_change_value": value},
        metadata={
            "source_state_ref": source,
            "method_id": method,
            "authorized": authorized,
            "external_effect": external,
            "external_effect_authorized": external_authorized,
            "already_completed": already_completed,
        },
    )


def _attempt(candidate_id: str, *, method: str = "original",
             source: str = "source:version1", stage: str = "BLOCKED"):
    from hashlib import sha256
    from continuous_impact_selection import ImpactAttempt
    return ImpactAttempt(
        mission_sha256=sha256(b"continue mission").hexdigest(),
        candidate_id=candidate_id,
        method_id=method,
        source_state_ref=source,
        stage=stage,
        provider_ref="provider-error:previous-blocker",
    )


def _choose(candidates, attempts=()):
    selector = ContinuousImpactSelector()
    return selector.select(
        task_id="forward-continuation",
        mission="continue mission",
        operation_class="repair_runtime_selection",
        state_version="context:v31",
        candidates=candidates,
        prior_attempts=attempts,
        require_authenticated_frontier=True,
    )


def test_forward_guard_reroutes_blocked_write_in_same_mission():
    decision = _choose(
        (_guarded("blocked-write", value=1.0), _guarded("new-impactful-work", value=0.9)),
        (_attempt("blocked-write"),),
    )
    assert decision.selected_candidate_id == "new-impactful-work"
    assert decision.rejection_reasons["blocked-write"].startswith("unchanged")


def test_forward_guard_does_not_repeat_completed_or_no_delta_acquisition():
    decision = _choose(
        (_guarded("completed-task", already_completed=True),
         _guarded("old-analysis"), _guarded("current-benefit")),
        (_attempt("old-analysis", stage="NO_DELTA"),),
    )
    assert decision.selected_candidate_id == "current-benefit"
    assert "completed-task" in decision.rejected_candidate_ids
    assert "old-analysis" in decision.rejected_candidate_ids


def test_forward_guard_reopens_changed_method_or_new_state_not_blind_retry():
    for new_action in (
        _guarded("provider-write", method="new-route"),
        _guarded("provider-write", source="source:version2"),
    ):
        decision = _choose((new_action,), (_attempt("provider-write"),))
        assert decision.selected_candidate_id == "provider-write"


def test_forward_guard_external_effect_requires_distinct_authorization():
    decision = _choose((
        _guarded("send-external", external=True, value=1.0),
        _guarded("internal-remedy", value=0.5),
    ))
    assert decision.selected_candidate_id == "internal-remedy"
    assert "authorization" in decision.rejection_reasons["send-external"]
    assert _choose((
        _guarded("send-external", external=True, external_authorized=True),
    )).selected_candidate_id == "send-external"


def test_forward_guard_cannot_silently_use_candidates_without_current_proof():
    try:
        _choose((_candidate("summary", "summarize again", "summary exists"),))
    except ImpactSelectionViolation as exc:
        assert "no fresh authorized" in str(exc)
    else:
        raise AssertionError("missing recovered source/authority was accepted")


def test_forward_guard_wrong_mission_receipt_is_not_reused():
    from dataclasses import replace
    wrong = replace(_attempt("blocked-write"), mission_sha256="0" * 64)
    try:
        _choose((_guarded("blocked-write"),), (wrong,))
    except ImpactSelectionViolation as exc:
        assert "mission" in str(exc)
    else:
        raise AssertionError("cross-mission receipt was accepted")


def test_forward_guard_all_blocked_does_not_claim_task_completion():
    try:
        _choose((_guarded("blocked-write"),), (_attempt("blocked-write"),))
    except ImpactSelectionViolation as exc:
        assert "no fresh authorized" in str(exc)
        assert "mission" in str(exc)
    else:
        raise AssertionError("an unchanged blocker was selected")


def test_verified_outcomes_require_native_readback_not_artifact_claims():
    from continuous_impact_selection import ImpactAttempt
    from hashlib import sha256
    from dataclasses import replace
    basic = _attempt("done")
    invalid = replace(
        basic,
        stage="HUMAN_OUTCOME",
        source_class="assistant",
        provider_ref="assistant:report",
        readback_ref="assistant:verification",
        after_state_ref="source:version2",
    )
    try:
        invalid.verify_claim()
    except ImpactSelectionViolation as exc:
        assert "native" in str(exc)
    else:
        raise AssertionError("assistant progress promotion was accepted")
    valid = replace(
        basic,
        stage="HUMAN_OUTCOME",
        source_class="source_native",
        provider_ref="provider:authoritative-event",
        readback_ref="provider:independent-readback",
        after_state_ref="source:version2",
    )
    valid.verify_claim()
