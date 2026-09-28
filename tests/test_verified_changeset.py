from src.verified_changeset import (
    VerifiedOperation,
    VerificationFailure,
    apply_with_verified_readback,
    verify_expected_state,
)


def test_expected_state_requires_provider_readback_equality():
    result = verify_expected_state({"sha": "new"}, {"sha": "old"})
    assert not result.verified
    assert result.discrepancies


def test_preflight_blocks_stale_provider_state_before_mutation():
    mutated = []
    op = VerifiedOperation("github", "repo", "update", {"sha": "base"}, {"sha": "new"})
    try:
        apply_with_verified_readback(
            [op],
            observe=lambda _: {"sha": "other"},
            apply=lambda _: mutated.append(True),
            readback=lambda _: {"sha": "new"},
        )
    except VerificationFailure:
        pass
    else:
        raise AssertionError("stale preflight must fail")
    assert mutated == []


def test_mismatch_compensates_applied_operations_in_reverse_order():
    applied = []
    compensated = []
    ops = [
        VerifiedOperation("github", "a", "update", {"sha": "0"}, {"sha": "1"}),
        VerifiedOperation("github", "b", "update", {"sha": "0"}, {"sha": "1"}),
    ]

    def apply(op):
        applied.append(op.resource)
        return f"receipt:{op.resource}"

    def readback(op):
        return {"sha": "1" if op.resource == "a" else "mismatch"}

    try:
        apply_with_verified_readback(
            ops,
            observe=lambda _: {"sha": "0"},
            apply=apply,
            readback=readback,
            compensate=lambda op: compensated.append(op.resource),
        )
    except VerificationFailure:
        pass
    else:
        raise AssertionError("readback mismatch must fail")

    assert applied == ["a", "b"]
    assert compensated == ["b", "a"]


def test_success_returns_provider_receipts_and_verified_results():
    op = VerifiedOperation("github", "repo", "update", {"sha": "0"}, {"sha": "1"})
    receipts, results = apply_with_verified_readback(
        [op],
        observe=lambda _: {"sha": "0"},
        apply=lambda _: "provider:123",
        readback=lambda _: {"sha": "1"},
    )
    assert receipts == ("provider:123",)
    assert len(results) == 1 and results[0].verified
