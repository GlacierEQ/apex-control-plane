from __future__ import annotations

import hashlib

from operator_source_binding_contract import (
    SourceReadbackUnresolved,
    validate_source_span_binding_shape,
    verify_source_span_binding,
)


def _sha(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _binding() -> tuple[dict, bytes, str]:
    proposition = "Continue from source-bearing state, not a derivative summary."
    source = ("before\n" + proposition + "\nafter\n").encode()
    start = source.index(proposition.encode())
    end = start + len(proposition.encode())
    return (
        {
            "proposition_id": "operator:test:source-bound",
            "source_kind": "operator_message",
            "source_ref": "source:operator",
            "source_sha256": _sha(source),
            "span_start_byte": start,
            "span_end_byte": end,
            "span_sha256": _sha(source[start:end]),
            "temporal_context": "test-current",
            "contradiction_state": "active",
            "superseded_by": None,
            "verification_state": "source_resolved",
        },
        source,
        proposition,
    )


def test_shared_verifier_recomputes_source_and_span_bytes() -> None:
    binding, source, proposition = _binding()
    result = verify_source_span_binding(
        binding,
        resolver=lambda ref: source,
        prefix="binding",
        expected_text=proposition,
    )
    assert result.errors == ()
    assert result.span_text == proposition


def test_derivative_source_is_quarantined_before_readback() -> None:
    binding, source, _ = _binding()
    binding["source_kind"] = "assistant_summary"
    called = False

    def resolver(ref: str) -> bytes:
        nonlocal called
        called = True
        return source

    result = verify_source_span_binding(binding, resolver=resolver, prefix="binding")
    assert called is False
    assert any("derivative" in error for error in result.errors)


def test_retrieval_failure_stays_unresolved_not_absent() -> None:
    binding, _, _ = _binding()

    def resolver(ref: str) -> bytes:
        raise SourceReadbackUnresolved(
            "source readback unresolved: provider unavailable"
        )

    result = verify_source_span_binding(binding, resolver=resolver, prefix="binding")
    assert result.resolved is False
    assert any("source readback unresolved" in error for error in result.errors)


def test_supersession_lineage_blocks_active_frontier_use() -> None:
    binding, source, _ = _binding()
    binding["superseded_by"] = "operator:test:newer"
    result = verify_source_span_binding(
        binding,
        resolver=lambda ref: source,
        prefix="binding",
        require_unsuperseded=True,
    )
    assert any("superseded_by" in error for error in result.errors)


def test_malformed_digest_fails_before_claiming_byte_verification() -> None:
    binding, _, _ = _binding()
    binding["source_sha256"] = "sha256:not-real"
    errors = validate_source_span_binding_shape(binding, prefix="binding")
    assert "binding.source_sha256 must be sha256:<64 hex>" in errors
