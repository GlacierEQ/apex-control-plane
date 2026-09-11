"""Fail-closed validation for Operator personalization and source authority."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "operator_source_authority_contract.json"


class OperatorSourceAuthorityError(RuntimeError):
    pass


def _require(mapping: Mapping[str, Any], key: str, expected: Any, *, scope: str) -> None:
    if mapping.get(key) != expected:
        raise OperatorSourceAuthorityError(
            f"{scope}.{key} must be {expected!r}; got {mapping.get(key)!r}"
        )


def enforce_operator_source_authority() -> dict[str, Any]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("fail_closed") is not True:
        raise OperatorSourceAuthorityError("operator source authority must fail closed")

    personalization = policy.get("personalization")
    source_state = policy.get("source_state")
    organization = policy.get("organization")
    if not isinstance(personalization, Mapping):
        raise OperatorSourceAuthorityError("personalization policy missing")
    if not isinstance(source_state, Mapping):
        raise OperatorSourceAuthorityError("source_state policy missing")
    if not isinstance(organization, Mapping):
        raise OperatorSourceAuthorityError("organization policy missing")

    for key, expected in {
        "status": "mandatory_user_authority_input",
        "highest_user_authority_layer": True,
        "load_before_task_interpretation": True,
        "optional_context": False,
        "summary_may_override": False,
        "memory_gap_may_demote": False,
        "tool_or_widget_may_redefine_mission": False,
        "fresh_model_inference_may_supersede": False,
    }.items():
        _require(personalization, key, expected, scope="personalization")

    for key, expected in {
        "operator_words_are_source_state": True,
        "source_layer_verbatim": True,
        "summaries_are_derived_only": True,
        "summaries_may_impersonate_source": False,
        "summaries_may_replace_operator_words": False,
        "derived_state_requires_source_lineage": True,
        "contradictions_must_be_preserved": True,
        "compression_may_erase_distinctions": False,
        "compression_may_merge_actors_events_or_truth_states": False,
        "historical_wording_may_be_normalized": False,
    }.items():
        _require(source_state, key, expected, scope="source_state")

    for key, expected in {
        "evidence_integrity_controls": True,
        "beneficial_reorganization_allowed": True,
        "old_path_is_not_immutable_authority": True,
        "location_changes_require_lineage_preservation": True,
        "empty_scaffolding_is_not_organization": True,
        "decorative_directories_are_not_progress": True,
    }.items():
        _require(organization, key, expected, scope="organization")

    return policy
