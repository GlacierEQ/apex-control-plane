"""Remove artificial execution vetoes while keeping outcome and external-effect truth."""
from hashlib import sha256
from src.continuous_impact_selection import (
    ContinuousImpactSelector, ImpactCandidate, ImpactAttempt,
)


def candidate(name, metadata=None, score=0.9):
    return ImpactCandidate(
        candidate_id=name,
        operation="continue authorized internal work: " + name,
        operation_class="CASE_EXECUTION",
        expected_delta="new source-backed work " + name,
        features={"mission_advancement": score, "state_change_value": score},
        evidence_refs=("case:current",), metadata=metadata or {},
    )


def choose(candidates, *, attempts=(), authenticated=False):
    return ContinuousImpactSelector().select(
        task_id="CHERRY:all-lanes",
        mission="advance the existing CHERRY mission",
        operation_class="CASE_EXECUTION",
        state_version="case:v11",
        candidates=candidates,
        prior_attempts=attempts,
        require_authenticated_frontier=authenticated,
    )


def test_one_failed_action_cannot_globally_block_independent_internal_action():
    blocked = ImpactAttempt(
        mission_sha256=sha256(b"advance the existing CHERRY mission").hexdigest(),
        candidate_id="blocked-claim", method_id="old-method",
        source_state_ref="case:old", stage="BLOCKED",
        provider_ref="provider-error:timeout",
    )
    decision = choose((
        candidate("blocked-claim", {"source_state_ref": "case:old", "method_id": "old-method",
                                     "authorized": True, "external_effect": False,
                                     "already_completed": False}),
        candidate("independent-private-work"),
    ), attempts=(blocked,))
    assert decision.selected_candidate_id == "independent-private-work"
    assert "blocked-claim" in decision.rejected_candidate_ids


def test_internal_action_is_not_gated_by_irrelevant_external_permission_field():
    decision = choose((candidate("private-evidence-preservation", {
        "source_state_ref": "case:evidence-1",
        "method_id": "preserve-native",
        "authorized": True,
        "external_effect": False,
        "already_completed": False,
    }),), authenticated=True)
    assert decision.selected_candidate_id == "private-evidence-preservation"


def test_unapproved_external_effect_is_still_not_selected():
    decision = choose((
        candidate("external-send", {
            "source_state_ref": "case:email-draft",
            "method_id": "send",
            "authorized": True,
            "external_effect": True,
            "already_completed": False,
        }, score=1.0),
        candidate("internal-prepare", {
            "source_state_ref": "case:email-draft",
            "method_id": "prepare",
            "authorized": True,
            "external_effect": False,
            "already_completed": False,
        }, score=0.5),
    ), authenticated=True)
    assert decision.selected_candidate_id == "internal-prepare"
    assert "external-send" in decision.rejected_candidate_ids
