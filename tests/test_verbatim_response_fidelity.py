from __future__ import annotations

import pytest

from operator_source_binding_contract import sha256_ref
from src.operator_source_authority import (
    OperatorSourceAuthorityError,
    enforce_verbatim_response_fidelity,
)


def _binding(source: bytes, expected: str) -> dict:
    start = source.index(expected.encode("utf-8"))
    end = start + len(expected.encode("utf-8"))
    span = source[start:end]
    return {
        "proposition_id": "verbatim-test",
        "source_kind": "operator_message",
        "source_ref": "file:operator-history.txt",
        "source_sha256": sha256_ref(source),
        "span_start_byte": start,
        "span_end_byte": end,
        "span_sha256": sha256_ref(span),
        "temporal_context": "test",
        "contradiction_state": "active",
        "verification_state": "source_resolved",
    }


def test_verbatim_request_rejects_missing_source_binding() -> None:
    with pytest.raises(OperatorSourceAuthorityError, match="source binding"):
        enforce_verbatim_response_fidelity(
            requested_verbatim=True,
            source_binding=None,
            source_resolver=None,
            emitted_operator_quote="SECOND.",
        )


def test_verbatim_request_rejects_different_valid_passage() -> None:
    source = b"FIRST. SECOND."
    with pytest.raises(OperatorSourceAuthorityError, match="exact requested source span"):
        enforce_verbatim_response_fidelity(
            requested_verbatim=True,
            source_binding=_binding(source, "SECOND."),
            source_resolver=lambda ref: source,
            emitted_operator_quote="FIRST.",
        )


def test_verbatim_request_rejects_forged_source_hash() -> None:
    source = b"FIRST. SECOND."
    binding = _binding(source, "SECOND.")
    binding["source_sha256"] = "sha256:" + "0" * 64

    with pytest.raises(OperatorSourceAuthorityError, match="source verification failed"):
        enforce_verbatim_response_fidelity(
            requested_verbatim=True,
            source_binding=binding,
            source_resolver=lambda ref: source,
            emitted_operator_quote="SECOND.",
        )


def test_verbatim_request_accepts_exact_verified_source_span() -> None:
    source = b"FIRST. SECOND."
    enforce_verbatim_response_fidelity(
        requested_verbatim=True,
        source_binding=_binding(source, "SECOND."),
        source_resolver=lambda ref: source,
        emitted_operator_quote="SECOND.",
    )


def test_non_verbatim_request_does_not_require_source_binding() -> None:
    enforce_verbatim_response_fidelity(
        requested_verbatim=False,
        source_binding=None,
        source_resolver=None,
        emitted_operator_quote=None,
    )


def test_verbatim_request_rejects_whitespace_only_quote() -> None:
    source = b"FIRST. SECOND."
    with pytest.raises(OperatorSourceAuthorityError, match="non-empty exact Operator quote"):
        enforce_verbatim_response_fidelity(
            requested_verbatim=True,
            source_binding=_binding(source, "SECOND."),
            source_resolver=lambda ref: source,
            emitted_operator_quote="   \t",
        )
