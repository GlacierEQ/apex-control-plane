from __future__ import annotations

import pytest

from src.operator_source_authority import (
    OperatorSourceAuthorityError,
    enforce_verbatim_response_fidelity,
)


def test_verbatim_request_rejects_missing_recovered_source() -> None:
    with pytest.raises(OperatorSourceAuthorityError, match="recovered Operator source"):
        enforce_verbatim_response_fidelity(
            requested_verbatim=True,
            recovered_operator_source=None,
            emitted_operator_quote="DEFAULT IS MAXIMUM COHERENT PROGRESS.",
        )


def test_verbatim_request_rejects_paraphrase() -> None:
    source = "DEFAULT IS MAXIMUM COHERENT PROGRESS.\nBlocked route changes route, not objective."
    with pytest.raises(OperatorSourceAuthorityError, match="exact source span"):
        enforce_verbatim_response_fidelity(
            requested_verbatim=True,
            recovered_operator_source=source,
            emitted_operator_quote="Default to maximum useful progress.",
        )


def test_verbatim_request_accepts_exact_source_span() -> None:
    source = "DEFAULT IS MAXIMUM COHERENT PROGRESS.\nBlocked route changes route, not objective."
    enforce_verbatim_response_fidelity(
        requested_verbatim=True,
        recovered_operator_source=source,
        emitted_operator_quote="DEFAULT IS MAXIMUM COHERENT PROGRESS.",
    )


def test_non_verbatim_request_does_not_require_exact_quote() -> None:
    enforce_verbatim_response_fidelity(
        requested_verbatim=False,
        recovered_operator_source=None,
        emitted_operator_quote=None,
    )
