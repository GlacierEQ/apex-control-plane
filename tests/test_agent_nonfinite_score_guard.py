"""Non-finite routing scores must never enter candidate ranking."""

from datetime import UTC, datetime

import pytest

from src.dynamic_execution_fabric import SubstrateObservation


@pytest.mark.parametrize("field", ["health_score", "cost_score", "latency_score"])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_observation_score_is_rejected(field, invalid):
    values = dict(
        name="provider", capabilities=frozenset({"execute"}), health="healthy",
        health_score=0.5, private_repo=False, exact_source=False,
        receipts=False, terminal_readback=False,
        observed_at=datetime(2026, 11, 17, tzinfo=UTC),
        cost_score=0.5, latency_score=0.5,
    )
    values[field] = invalid
    with pytest.raises(ValueError, match=f"{field} must be between 0 and 1"):
        SubstrateObservation(**values)
