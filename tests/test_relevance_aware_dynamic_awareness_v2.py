from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "db/migrations/20260909_control_plane_relevance_aware_awareness_v2_1.sql"
DEDUP = ROOT / "db/migrations/20260909_control_plane_awareness_projection_dedup_v2_2.sql"
GATE = ROOT / "supabase/functions/execution-awareness-gate/index.ts"
IMPACT = ROOT / "supabase/functions/operator-impact-context/index.ts"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_v2_separates_hard_relevance_from_soft_context() -> None:
    sql = _text(BASE)
    assert "then 'HARD' else 'SOFT'" in sql
    assert "CASE_CONTEXT_ONLY" in sql
    assert "CURRENT_WITH_NEW_SOFT_CONTEXT" in sql
    assert "newer_soft_context_exists" in sql
    assert "dispatch_reevaluation_required" in sql
    assert "explicit-link-target-global-gate-v2" in sql


def test_hard_relevance_requires_typed_linkage_or_declared_gate() -> None:
    sql = _text(BASE)
    for marker in (
        "EXPLICIT_ACTION_LINK",
        "PROVIDER_MESSAGE_LINK",
        "PROVIDER_THREAD_LINK",
        "TARGET_MATCH",
        "ACTION_SOURCE_EVENT",
        "ACTION_SOURCE_OBLIGATION",
        "DECLARED_GLOBAL_EXECUTION_GATE",
        "EXPLICIT_INCIDENT_LINK",
        "CONNECTOR_IDENTITY_MATCH",
    ):
        assert marker in sql
    assert "global_execution_gate" in sql


def test_projection_events_cannot_manufacture_relevance() -> None:
    sql = _text(DEDUP)
    assert "not exists" in sql.lower()
    assert "control_plane_communications c2" in sql
    assert "control_plane_action_outbox" in sql
    assert "control_plane_obligations" in sql
    assert "projection text cannot manufacture new relevance" in sql


def test_claim_uses_v2_and_admits_only_nonapproval_ready_work() -> None:
    sql = _text(BASE)
    claim = sql.split(
        "create or replace function public.claim_control_plane_actions_v1", 1
    )[1]
    claim = claim.split(
        "create or replace function public.control_plane_begin_authorized_attempt", 1
    )[0]
    assert "control_plane_action_awareness_v2" in claim
    assert "a.status='READY' and not a.requires_operator_approval" in claim
    assert "aw.dispatch_reevaluation_required is false" in claim
    assert "coalesce(aw.execution_valid,true) is true" in claim


def test_explicit_attempt_uses_relevance_aware_fence() -> None:
    sql = _text(BASE)
    begin_attempt = sql.split(
        "create or replace function public.control_plane_begin_authorized_attempt", 1
    )[1]
    begin_attempt = begin_attempt.split(
        "create or replace function public.reconcile_control_plane_internal_awareness_v2", 1
    )[0]
    assert "control_plane_action_awareness_v2" in begin_attempt
    assert "if v_aw.dispatch_reevaluation_required then" in begin_attempt
    assert "newer_soft_context_exists" in begin_attempt
    assert "awareness_relevance_model" in begin_attempt


def test_internal_reconciler_is_structural_not_substantive() -> None:
    sql = _text(BASE)
    reconcile = sql.split(
        "create or replace function public.reconcile_control_plane_internal_awareness_v2", 1
    )[1]
    assert "a.action_type='OPERATOR_ALERT'" in reconcile
    assert "public.apex_connector_incidents" in reconcile
    assert "no_substantive_domain_judgment" in reconcile
    assert "STRUCTURAL_CONNECTOR_INCIDENT_STATE" in reconcile
    assert "CRIMINAL_REFERRAL" not in reconcile
    assert "LEGAL_REFERRAL" not in reconcile


def test_internal_awareness_reconciliation_is_continuous() -> None:
    sql = _text(BASE)
    assert "control-plane-awareness-reconcile-v2" in sql
    assert "'* * * * *'" in sql
    assert "reconcile_control_plane_internal_awareness_v2" in sql


def test_runtime_consumers_use_v2_contract() -> None:
    gate = _text(GATE)
    impact = _text(IMPACT)
    assert 'from("control_plane_action_awareness_v2")' in gate
    assert "dispatch_reevaluation_required" in gate
    assert "legacy_next_semantic_step" in gate
    assert "get_control_plane_action_awareness_v2" in impact
    assert "soft_context_blocks_dispatch: false" in impact
    assert "representation_duplicates_cannot_create_relevance: true" in impact


def test_relevance_model_has_no_case_specific_hardcoding() -> None:
    sql = _text(BASE) + "\n" + _text(DEDUP)
    for forbidden in (
        "NEX-JBPHH-2026-08-14",
        "1FDV-23-0001009",
        "CASE-CHR-003",
        "NCIS Hawaii",
        "FBI Honolulu",
    ):
        assert forbidden not in sql
