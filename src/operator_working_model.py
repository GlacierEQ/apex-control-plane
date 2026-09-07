"""Load and validate the derived, non-sovereign Operator working model.

The working model exists to prevent repeated rediscovery of already-known Operator
state. It is a continuation aid, not a source of project-direction authority.
Current literal Operator direction always controls the current mission.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from auto_boot import BootError

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _require_flag(value: Mapping[str, Any], field: str, expected: bool, *, prefix: str) -> None:
    if value.get(field) is not expected:
        raise BootError(f"{prefix}.{field} must be {expected!r}")


def _require_nonempty_text(value: Mapping[str, Any], field: str, *, prefix: str) -> None:
    if not str(value.get(field, "")).strip():
        raise BootError(f"{prefix}.{field} must be non-empty")


def _require_nonempty_list(value: Mapping[str, Any], field: str, *, prefix: str) -> None:
    items = value.get(field)
    if not isinstance(items, list) or not any(str(item).strip() for item in items):
        raise BootError(f"{prefix}.{field} must be a non-empty array")


def load_operator_working_model(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Return a validated Operator working-model projection referenced by startup policy."""
    raw_path = str(policy.get("operator_working_model_path", "")).strip()
    if not raw_path:
        raise BootError("APEX startup policy must define operator_working_model_path")

    target = (_REPO_ROOT / raw_path).resolve()
    try:
        target.relative_to(_REPO_ROOT)
    except ValueError as exc:
        raise BootError("operator_working_model_path must stay inside the repository") from exc

    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BootError(f"operator working model not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise BootError(f"invalid operator working model: {exc}") from exc

    if not isinstance(value, dict):
        raise BootError("operator working model must be a JSON object")

    required = {
        "schema_version",
        "name",
        "authority_semantics",
        "operator_identity",
        "estate_model",
        "actual_work_pattern",
        "default_loop",
        "state_reuse",
        "working_patterns",
        "impact_first_judgment",
        "literal_operator_anchors",
        "failure_interrupt_vectors",
        "anti_patterns",
        "startup_receipt_requirements",
    }
    missing = sorted(required - value.keys())
    if missing:
        raise BootError("operator working model missing: " + ", ".join(missing))

    authority = value.get("authority_semantics")
    if not isinstance(authority, Mapping):
        raise BootError("operator working model authority_semantics must be an object")
    for field, expected in {
        "current_operator_message_controls_current_mission": True,
        "literal_operator_sources_outrank_assistant_derivations": True,
        "assistant_working_model_is_derived_and_non_sovereign": True,
        "memory_and_continuity_state_are_starting_state_not_project_authority": True,
        "historical_summaries_are_routing_hints_not_identity_or_current_state": True,
    }.items():
        _require_flag(authority, field, expected, prefix="operator_working_model.authority_semantics")

    identity = value.get("operator_identity")
    if not isinstance(identity, Mapping):
        raise BootError("operator working model operator_identity must be an object")
    for field in ("name", "role", "primary_model", "anti_reduction_rule", "builds"):
        _require_nonempty_text(identity, field, prefix="operator_working_model.operator_identity")
    _require_nonempty_list(
        identity,
        "diagnostic_discipline",
        prefix="operator_working_model.operator_identity",
    )

    estate = value.get("estate_model")
    if not isinstance(estate, Mapping):
        raise BootError("operator working model estate_model must be an object")
    for field in ("glaciereq", "design_thesis", "target", "organ_rule", "anti_monolith_rule"):
        _require_nonempty_text(estate, field, prefix="operator_working_model.estate_model")
    for field in ("principles", "recurring_organs"):
        _require_nonempty_list(estate, field, prefix="operator_working_model.estate_model")

    actual_work_pattern = value.get("actual_work_pattern")
    if not isinstance(actual_work_pattern, list) or not any(
        str(item).strip() for item in actual_work_pattern
    ):
        raise BootError("operator_working_model.actual_work_pattern must be a non-empty array")
    if not str(value.get("default_loop", "")).strip():
        raise BootError("operator_working_model.default_loop must be non-empty")

    state_reuse = value.get("state_reuse")
    if not isinstance(state_reuse, Mapping):
        raise BootError("operator working model state_reuse must be an object")
    _require_flag(
        state_reuse,
        "rediscovery_is_progress",
        False,
        prefix="operator_working_model.state_reuse",
    )
    if not str(state_reuse.get("rule", "")).strip():
        raise BootError("operator_working_model.state_reuse.rule must be non-empty")

    patterns = value.get("working_patterns")
    if not isinstance(patterns, Mapping) or not patterns:
        raise BootError("operator_working_model.working_patterns must be a non-empty object")

    impact = value.get("impact_first_judgment")
    if not isinstance(impact, Mapping):
        raise BootError("operator working model impact_first_judgment must be an object")
    _require_nonempty_text(impact, "rule", prefix="operator_working_model.impact_first_judgment")
    _require_nonempty_list(impact, "weigh", prefix="operator_working_model.impact_first_judgment")
    _require_flag(
        impact,
        "reweight_on_state_change",
        True,
        prefix="operator_working_model.impact_first_judgment",
    )
    _require_flag(
        impact,
        "frameworks_are_inputs_not_substitutes_for_judgment",
        True,
        prefix="operator_working_model.impact_first_judgment",
    )

    interrupts = value.get("failure_interrupt_vectors")
    if not isinstance(interrupts, Mapping):
        raise BootError("operator_working_model.failure_interrupt_vectors must be an object")
    phrases = interrupts.get("phrases")
    if not isinstance(phrases, list) or not any(str(item).strip() for item in phrases):
        raise BootError("operator_working_model.failure_interrupt_vectors.phrases must be non-empty")
    if not str(interrupts.get("contextual_semantics", "")).strip():
        raise BootError(
            "operator_working_model.failure_interrupt_vectors.contextual_semantics must be non-empty"
        )

    receipt_requirements = value.get("startup_receipt_requirements")
    if not isinstance(receipt_requirements, Mapping):
        raise BootError("operator working model startup_receipt_requirements must be an object")
    for field in (
        "operator_identity_loaded",
        "operator_estate_model_loaded",
        "operator_model_loaded",
        "relevant_memory_consulted_when_available",
        "known_state_reused_before_rediscovery",
        "literal_operator_sources_preserved_separately_from_derived_interpretation",
        "working_method_applied_to_task_decomposition",
        "continuation_point_resolved",
        "rediscovery_if_performed_has_material_justification",
    ):
        _require_flag(
            receipt_requirements,
            field,
            True,
            prefix="operator_working_model.startup_receipt_requirements",
        )

    return value


def public_operator_model_projection(model: Mapping[str, Any]) -> dict[str, Any]:
    """Return the complete boot-safe projection without converting it into authority."""
    return {
        "name": model.get("name"),
        "schema_version": model.get("schema_version"),
        "authority_semantics": dict(model.get("authority_semantics", {})),
        "operator_identity": dict(model.get("operator_identity", {})),
        "estate_model": dict(model.get("estate_model", {})),
        "actual_work_pattern": list(model.get("actual_work_pattern", [])),
        "default_loop": model.get("default_loop"),
        "state_reuse": dict(model.get("state_reuse", {})),
        "working_patterns": dict(model.get("working_patterns", {})),
        "impact_first_judgment": dict(model.get("impact_first_judgment", {})),
        "literal_operator_anchors": list(model.get("literal_operator_anchors", [])),
        "failure_interrupt_vectors": dict(model.get("failure_interrupt_vectors", {})),
        "anti_patterns": list(model.get("anti_patterns", [])),
        "startup_receipt_requirements": dict(model.get("startup_receipt_requirements", {})),
    }
