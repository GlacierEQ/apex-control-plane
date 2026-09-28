from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/20260908_dynamic_awareness_dispatch_fence_v1.sql"
GATE = ROOT / "supabase/functions/execution-awareness-gate/index.ts"
IMPACT = ROOT / "supabase/functions/operator-impact-context/index.ts"
DOC = ROOT / "docs/DYNAMIC_AWARENESS_EXECUTION_BINDING.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dispatch_claim_requires_current_awareness() -> None:
    sql = _text(MIGRATION)
    claim = sql.split("create or replace function public.claim_control_plane_actions_v1", 1)[1]
    claim = claim.split("create or replace function public.control_plane_begin_authorized_attempt", 1)[0]
    assert "aw.newer_source_state_exists is false" in claim
    assert "coalesce(aw.execution_valid, true) is true" in claim


def test_explicit_attempt_refuses_stale_source_state_before_dispatch() -> None:
    sql = _text(MIGRATION)
    begin_attempt = sql.split(
        "create or replace function public.control_plane_begin_authorized_attempt", 1
    )[1]
    stale = begin_attempt.index("if v_aw.newer_source_state_exists then")
    dispatch = begin_attempt.index("status = 'DISPATCHING'")
    assert stale < dispatch
    assert "'dispatch_started', false" in begin_attempt[:dispatch]
    assert "'REEVALUATE_CURRENT_REALITY'" in begin_attempt[:dispatch]


def test_awareness_is_source_watermark_based_not_case_rule_based() -> None:
    sql = _text(MIGRATION)
    for source in (
        "control_plane_communications",
        "control_plane_events",
        "control_plane_obligations",
    ):
        assert source in sql
    assert "case_id = '" not in sql
    assert "recipient" not in sql.lower()


def test_awareness_evaluation_is_append_only_receipt_evidence() -> None:
    sql = _text(MIGRATION)
    assert "control_plane_action_awareness_receipts" in sql
    assert "DYNAMIC_AWARENESS_EVALUATION" in sql
    assert "source_watermark_at" in sql
    assert "execution_valid" in sql


def test_external_gate_is_preflight_not_executor() -> None:
    gate = _text(GATE)
    compact = "".join(gate.split())
    assert "mutation_capability:false" in compact
    assert '"EVALUATE_CURRENT_REALITY"' in gate
    assert '"EVALUATE_CURRENT_RELEVANT_REALITY"' in gate
    assert '"DO_NOT_EXECUTE_CURRENT_ACTION"' in gate
    assert '"CURRENT_ACTION_MAY_PROCEED"' in gate
    assert "record_control_plane_action_awareness_v1" in gate
    assert "control_plane_action_awareness_v2" in gate
    assert "send_email" not in gate


def test_operator_context_surfaces_material_delta() -> None:
    impact = _text(IMPACT)
    assert "get_control_plane_action_awareness_v2" in impact
    assert "must_re_evaluate_before_mutation" in impact
    assert "newer_soft_context_present" in impact
    assert "stale_cached_intent_is_not_execution_authority" in impact
    assert "action_rules_are_not_substitute_for_current_state" in impact
    assert "soft_context_blocks_dispatch: false" in impact


def test_documentation_preserves_rule_compression_intent() -> None:
    doc = _text(DOC)
    assert "This is not another behavioral rule layer." in doc
    assert "Current source-bearing state outranks cached action intent." in doc
    assert "No stale execution context may silently outrank materially newer source-bearing reality." in doc
