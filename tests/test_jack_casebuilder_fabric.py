from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from continuous_impact_selection import ImpactCandidate
from jack_casebuilder_fabric import (
    JackFabricViolation,
    ProjectionEnvelope,
    build_fabric,
    select_case_action,
)


def peer(pid: str, role: str, observed: str, state: str) -> ProjectionEnvelope:
    return ProjectionEnvelope(
        projection_id=pid,
        case_id="CASE-DEMO",
        provider="test",
        locator=f"test://{pid}",
        role=role,
        revision="r1",
        observed_at=observed,
        payload={
            "allegations": [
                {
                    "allegation_id": "A-1",
                    "promotion_state": state,
                    "tier": 4,
                }
            ],
            "facts": [],
            "events": [],
            "discovery_targets": [{"discovery_target_id": "D-1"}],
            "remedies": [],
        },
    )


def test_peer_disagreement_is_preserved_not_overwritten() -> None:
    view = build_fabric(
        [
            peer("matter", "MATTER_GRAPH", "2026-09-11T18:00:00Z", "STRUCTURED"),
            peer("aggregate", "COMPATIBILITY_AGGREGATE", "2026-09-11T18:01:00Z", "QUARANTINED"),
        ],
        now=datetime(2026, 9, 11, 19, tzinfo=UTC),
    )
    assert view.allegation_ids == ("A-1",)
    conflicts = [row for row in view.conflicts if row.object_id == "A-1"]
    assert conflicts
    assert conflicts[0].values == {
        "aggregate": "QUARANTINED",
        "matter": "STRUCTURED",
    }


def test_stale_peer_remains_visible() -> None:
    view = build_fabric(
        [
            peer("vault", "EVIDENCE_VAULT", "2026-09-01T00:00:00Z", "STRUCTURED"),
            peer("matter", "MATTER_GRAPH", "2026-09-11T18:00:00Z", "STRUCTURED"),
        ],
        now=datetime(2026, 9, 11, 19, tzinfo=UTC),
        stale_after_seconds=3 * 24 * 60 * 60,
    )
    assert view.stale_projection_ids == ("vault",)
    assert set(view.projection_ids) == {"matter", "vault"}


def test_global_sovereignty_claim_is_rejected() -> None:
    projection = ProjectionEnvelope(
        projection_id="bad",
        case_id="CASE-DEMO",
        provider="test",
        locator="test://bad",
        role="MATTER_GRAPH",
        revision="r1",
        observed_at="2026-09-11T18:00:00Z",
        payload={},
        metadata={"globally_canonical": True},
    )
    try:
        build_fabric([projection], now=datetime(2026, 9, 11, 19, tzinfo=UTC))
    except JackFabricViolation as exc:
        assert "global canonicality" in str(exc)
    else:
        raise AssertionError("global canonicality must fail closed")


def test_case_action_uses_current_impact_selector() -> None:
    view = build_fabric(
        [peer("matter", "MATTER_GRAPH", "2026-09-11T18:00:00Z", "STRUCTURED")],
        now=datetime(2026, 9, 11, 19, tzinfo=UTC),
    )
    candidates = [
        ImpactCandidate(
            candidate_id="summary",
            operation="summarize case",
            operation_class="CASE_EXECUTION",
            expected_delta="no underlying case change",
            features={
                "mission_advancement": 0.1,
                "state_change_value": 0.0,
                "meta_substitution_risk": 1.0,
            },
        ),
        ImpactCandidate(
            candidate_id="bind-source",
            operation="bind source-backed evidence",
            operation_class="CASE_EXECUTION",
            expected_delta="case proposition gains source-bound support",
            features={
                "mission_advancement": 1.0,
                "state_change_value": 1.0,
                "prior_gain_preservation": 1.0,
                "execution_proximity": 1.0,
                "meta_substitution_risk": 0.0,
                "already_done_risk": 0.0,
            },
            evidence_refs=("source:test",),
        ),
        ImpactCandidate(
            candidate_id="wrong-operation",
            operation="rewrite governance",
            operation_class="GOVERNANCE",
            expected_delta="new policy",
            features={"mission_advancement": 1.0},
        ),
    ]
    decision = select_case_action(
        fabric=view,
        mission="advance the case with strongest current proof",
        state_version="case-head:test",
        candidates=candidates,
    )
    assert decision.selected_candidate_id == "bind-source"
    assert "wrong-operation" in decision.rejected_candidate_ids
