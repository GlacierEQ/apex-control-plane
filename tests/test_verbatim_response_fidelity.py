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


# Operator 2026-10-24: preserve all of his original words as hierarchical
# bullets. Single-span fidelity above must extend to an entire source-linked
# outline without omissions or assistant-authored replacement summaries.
def test_hierarchical_distillation_retains_exact_words_and_parent_child_links() -> None:
    from src.operator_source_authority import render_operator_hierarchical_distillation

    originals = {
        "file:source-1": "YOU DONT GET TO REPLACE MY WORDS WITH YOURS",
        "file:source-2": "Distill my words into hierarchical bulletpoints. How many times I say it",
        "file:source-3": "The memory structure needs to be overhauled and the way you work needs to be fucking flashed",
    }
    bindings = []
    for i, (ref, quote) in enumerate(originals.items(), 1):
        binding = _binding(quote.encode("utf-8"), quote)
        binding["source_ref"] = ref
        binding["proposition_id"] = f"statement-{i}"
        bindings.append(binding)
    parents = {"statement-1": None, "statement-2": "statement-1", "statement-3": "statement-2"}

    output = render_operator_hierarchical_distillation(
        source_bindings=bindings, parents=parents,
        source_resolver=lambda ref: originals[ref].encode("utf-8"),
    )
    assert [row["original_text"] for row in output["bullets"]] == list(originals.values())
    assert [row["depth"] for row in output["bullets"]] == [0, 1, 2]
    assert output["source_count"] == 3
    assert "  - VERBATIM" in output["markdown"]
    for quote in originals.values():
        assert output["markdown"].count(quote) == 1


def test_hierarchical_distillation_preserves_repetition_and_negation() -> None:
    from src.operator_source_authority import render_operator_hierarchical_distillation

    quote = "DO NOT SUMMARIZE. Do not remove the negative, the profanity, or the exception."
    binding_a = _binding(quote.encode(), quote)
    binding_a["proposition_id"] = "turn-a"
    binding_b = _binding(quote.encode(), quote)
    binding_b["proposition_id"] = "turn-b"
    output = render_operator_hierarchical_distillation(
        source_bindings=[binding_a, binding_b],
        parents={"turn-a": None, "turn-b": "turn-a"},
        source_resolver=lambda _: quote.encode(),
    )
    assert output["source_count"] == 2
    assert output["markdown"].count(quote) == 2
    assert output["bullets"][0]["original_text"] == output["bullets"][1]["original_text"]


def test_hierarchical_distillation_rejects_omitted_originals() -> None:
    from src.operator_source_authority import (
        OperatorSourceAuthorityError,
        render_operator_hierarchical_distillation,
    )
    quote = "don't summarize"
    binding = _binding(quote.encode(), quote)
    with pytest.raises(OperatorSourceAuthorityError, match="exactly cover"):
        render_operator_hierarchical_distillation(
            source_bindings=[binding], parents={},
            source_resolver=lambda _: quote.encode(),
        )


def test_hierarchical_distillation_rejects_corrupt_or_unretrievable_source() -> None:
    from src.operator_source_authority import (
        OperatorSourceAuthorityError,
        render_operator_hierarchical_distillation,
    )
    quote = "only these original words"
    binding = _binding(quote.encode(), quote)
    with pytest.raises(OperatorSourceAuthorityError, match="source verification"):
        render_operator_hierarchical_distillation(
            source_bindings=[binding], parents={"verbatim-test": None},
            source_resolver=lambda _: b"assistant made this up",
        )


def test_hierarchical_distillation_rejects_cycles_and_unknown_parents() -> None:
    from src.operator_source_authority import (
        OperatorSourceAuthorityError,
        render_operator_hierarchical_distillation,
    )
    quote = "my original words"
    one = _binding(quote.encode(), quote)
    one["proposition_id"] = "one"
    two = _binding(quote.encode(), quote)
    two["proposition_id"] = "two"
    kwargs = {
        "source_bindings": [one, two],
        "source_resolver": lambda _: quote.encode(),
    }
    with pytest.raises(OperatorSourceAuthorityError, match="cycle"):
        render_operator_hierarchical_distillation(
            **kwargs, parents={"one": "two", "two": "one"},
        )
    with pytest.raises(OperatorSourceAuthorityError, match="unknown parent"):
        render_operator_hierarchical_distillation(
            **kwargs, parents={"one": None, "two": "missing"},
        )


def test_hierarchical_distillation_cannot_claim_corpus_completeness_from_supplied_bindings() -> None:
    from src.operator_source_authority import render_operator_hierarchical_distillation

    quote = "First known original"
    binding = _binding(quote.encode(), quote)
    binding["proposition_id"] = "first"
    base = {
        "source_bindings": [binding],
        "parents": {"first": None},
        "source_resolver": lambda _: quote.encode(),
    }
    out = render_operator_hierarchical_distillation(**base)
    assert out["supplied_binding_coverage"] is True
    assert out["complete_source_coverage"] is False
    assert out["coverage_scope"] == "supplied_bindings_only"
    with pytest.raises(OperatorSourceAuthorityError, match="expected.*missing"):
        render_operator_hierarchical_distillation(
            **base, expected_proposition_ids=("first", "missing"),
        )
    full = render_operator_hierarchical_distillation(
        **base, expected_proposition_ids=("first",),
    )
    assert full["complete_source_coverage"] is True
    assert full["coverage_scope"] == "caller_inventory_match_not_independent_corpus_proof"


def test_hierarchical_distillation_preserves_superseded_words_without_promoting_as_active() -> None:
    from src.operator_source_authority import render_operator_hierarchical_distillation

    originals = {
        "file:old": "DO NOT SUMMARIZE.",
        "file:new": "YOU DISTILL MINE INTO HIERARCHICAL BULLETPOINTS.",
    }
    bindings = []
    for index, (ref, quote) in enumerate(originals.items()):
        row = _binding(quote.encode(), quote)
        row.update({
            "source_ref": ref,
            "proposition_id": "earlier" if index == 0 else "later",
            "temporal_context": f"2026-10-{22 + index}",
        })
        if index == 0:
            row["contradiction_state"] = "superseded"
            row["superseded_by"] = "later"
        bindings.append(row)

    out = render_operator_hierarchical_distillation(
        source_bindings=bindings,
        parents={"earlier": None, "later": "earlier"},
        source_resolver=lambda ref: originals[ref].encode(),
        expected_proposition_ids=("earlier", "later"),
    )
    assert [node["original_text"] for node in out["bullets"]] == list(originals.values())
    assert out["bullets"][0]["source_state"] == "superseded"
    assert out["bullets"][0]["direction_authority"] == "historical_quote_only"
    assert out["bullets"][0]["superseded_by"] == "later"
    assert out["bullets"][1]["source_state"] == "active"
    assert out["bullets"][1]["direction_authority"] == "source_quote_not_external_fact"
    assert out["complete_source_coverage"] is True
