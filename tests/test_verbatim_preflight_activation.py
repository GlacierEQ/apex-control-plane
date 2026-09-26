from __future__ import annotations

from operator_fidelity_preflight import (
    build_operator_fidelity_request,
    load_operator_fidelity_policy,
)


def test_verbatim_task_activates_exact_source_response_requirements() -> None:
    request = build_operator_fidelity_request(
        load_operator_fidelity_policy(),
        task="Recover my prior instructions VERBATIM.",
    )
    requirements = request["requirements"]
    assert requirements["verbatim_request_active"] is True
    assert requirements["verbatim_response_requires_recovered_source"] is True
    assert requirements["verbatim_response_forbids_paraphrase_substitution"] is True
    assert requirements["verbatim_response_quotes_must_be_exact_source_spans"] is True


def test_non_verbatim_task_does_not_invent_exact_quote_requirement() -> None:
    request = build_operator_fidelity_request(
        load_operator_fidelity_policy(),
        task="Continue the current implementation.",
    )
    requirements = request["requirements"]
    assert requirements["verbatim_request_active"] is False
    assert requirements["verbatim_response_requires_recovered_source"] is False
    assert requirements["verbatim_response_forbids_paraphrase_substitution"] is False
    assert requirements["verbatim_response_quotes_must_be_exact_source_spans"] is False
