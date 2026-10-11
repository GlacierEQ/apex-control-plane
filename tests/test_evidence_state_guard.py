from evidence_state_guard import (
    count_independent_lineages,
    validate_evidence_projection,
)


def _prior_verified():
    return {
        "proposition_id": "camaro:prado-call",
        "historical_truth_state": "PROVIDER_VERIFIED",
        "source_class": "NATIVE_OR_PROVIDER",
        "root_lineage_ids": ["root:prado-call-audio"],
    }


def test_readback_gap_cannot_demote_prior_verified_truth():
    errors = validate_evidence_projection(
        _prior_verified(),
        {
            "proposition_id": "camaro:prado-call",
            "historical_truth_state": "UNRESOLVED",
            "readback_state": "READBACK_UNRESOLVED",
            "source_class": "DERIVATIVE_SUMMARY",
            "root_lineage_ids": ["root:prado-call-audio"],
            "parent_lineage_ids": ["root:prado-call-audio"],
        },
    )
    assert any("historical truth demotion" in error for error in errors)


def test_preserved_truth_with_scoped_readback_gap_is_valid():
    errors = validate_evidence_projection(
        _prior_verified(),
        {
            "proposition_id": "camaro:prado-call",
            "historical_truth_state": "PROVIDER_VERIFIED",
            "readback_state": "READBACK_UNRESOLVED",
            "authority_state": "READBACK_UNRESOLVED",
            "unresolved_dimensions": ["current_readback", "current_execution_authority"],
            "source_class": "DERIVATIVE_SUMMARY",
            "root_lineage_ids": ["root:prado-call-audio"],
            "parent_lineage_ids": ["root:prado-call-audio"],
        },
    )
    assert errors == ()


def test_derivative_projection_requires_parent_lineage():
    errors = validate_evidence_projection(
        _prior_verified(),
        {
            "proposition_id": "camaro:prado-call",
            "historical_truth_state": "PROVIDER_VERIFIED",
            "source_class": "DERIVATIVE_SUMMARY",
            "root_lineage_ids": ["root:prado-call-audio"],
        },
    )
    assert any("parent lineage" in error for error in errors)


def test_unresolved_must_be_dimension_scoped():
    errors = validate_evidence_projection(
        _prior_verified(),
        {
            "proposition_id": "camaro:prado-call",
            "historical_truth_state": "PROVIDER_VERIFIED",
            "readback_state": "READBACK_UNRESOLVED",
            "source_class": "DERIVATIVE_SUMMARY",
            "root_lineage_ids": ["root:prado-call-audio"],
            "parent_lineage_ids": ["root:prado-call-audio"],
        },
    )
    assert any("unresolved_dimensions" in error for error in errors)


def test_newer_derivative_cannot_claim_supersession_without_affirmative_source():
    errors = validate_evidence_projection(
        _prior_verified(),
        {
            "proposition_id": "camaro:prado-call",
            "historical_truth_state": "SUPERSEDED",
            "source_class": "DERIVATIVE_SUMMARY",
            "root_lineage_ids": ["root:prado-call-audio"],
            "parent_lineage_ids": ["root:prado-call-audio"],
            "superseded_by": "summary:newer",
        },
    )
    assert any("historical truth demotion" in error for error in errors)
    assert any("derivative" in error for error in errors)


def test_shared_root_derivatives_count_as_one_independent_lineage():
    records = [
        {"root_lineage_ids": ["root:native-a"]},
        {"root_lineage_ids": ["root:native-a"]},
        {"root_lineage_ids": ["root:native-b"]},
    ]
    assert count_independent_lineages(records) == 2


def test_repetition_without_root_lineage_does_not_manufacture_independence():
    records = [
        {"source_class": "DERIVATIVE_SUMMARY", "parent_lineage_ids": ["summary:1"]},
        {"source_class": "DERIVATIVE_SUMMARY", "parent_lineage_ids": ["summary:2"]},
    ]
    assert count_independent_lineages(records) == 0
