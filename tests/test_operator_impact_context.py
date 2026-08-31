from operator_impact_context import OPERATOR_IMPACT_CONTEXT, load_operator_impact_context


def test_impact_context_loads_at_runtime_boundary():
    ctx = OPERATOR_IMPACT_CONTEXT
    assert ctx.profile_key == "casey_impact_weighted_v1"
    assert "Always evaluate everything relevant" in ctx.principle
    assert "failure_impact" in ctx.factors
    assert "overshoot_risk" in ctx.factors


def test_context_is_recomputable_from_local_projection():
    ctx = load_operator_impact_context()
    assert ctx.operator == "Casey Barton / GlacierEQ"
    assert ctx.source
