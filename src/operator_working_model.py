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
        "state_reuse",
        "scope_fidelity",
        "working_patterns",
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

    scope_fidelity = value.get("scope_fidelity")
    if not isinstance(scope_fidelity, Mapping):
        raise BootError("operator working model scope_fidelity must be an object")
    for field, expected in {
        "operator_asserted_scope_is_source_state": True,
        "scope_carries_across_execution_contexts": True,
        "assistant_may_not_narrow_scope_without_explicit_operator_authorization": True,
        "assistant_may_not_replace_systemic_with_local": True,
        "assistant_may_not_replace_longitudinal_with_current_thread": True,
        "assistant_may_not_introduce_partial_or_frequency_qualifiers_without_source_basis": True,
        "operator_scope_correction_propagates_forward": True,
    }.items():
        _require_flag(scope_fidelity, field, expected, prefix="operator_working_model.scope_fidelity")
    if not str(scope_fidelity.get("rule", "")).strip():
        raise BootError("operator_working_model.scope_fidelity.rule must be non-empty")
    examples = scope_fidelity.get("examples_of_forbidden_unbacked_narrowing")
    if not isinstance(examples, list) or not any(str(item).strip() for item in examples):
        raise BootError(
            "operator_working_model.scope_fidelity.examples_of_forbidden_unbacked_narrowing must be non-empty"
        )

    patterns = value.get("working_patterns")
    if not isinstance(patterns, Mapping) or not patterns:
        raise BootError("operator_working_model.working_patterns must be a non-empty object")

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
        raise BootError("operator_working_model.startup_receipt_requirements must be an object")
    for field in (
        "operator_model_loaded",
        "relevant_memory_consulted_when_available",
        "known_state_reused_before_rediscovery",
        "literal_operator_sources_preserved_separately_from_derived_interpretation",
        "working_method_applied_to_task_decomposition",
        "operator_asserted_scope_preserved",
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
    """Return the boot-safe projection without converting it into authority."""
    return {
        "name": model.get("name"),
        "schema_version": model.get("schema_version"),
        "authority_semantics": dict(model.get("authority_semantics", {})),
        "state_reuse": dict(model.get("state_reuse", {})),
        "scope_fidelity": dict(model.get("scope_fidelity", {})),
        "working_patterns": dict(model.get("working_patterns", {})),
        "literal_operator_anchors": list(model.get("literal_operator_anchors", [])),
        "failure_interrupt_vectors": dict(model.get("failure_interrupt_vectors", {})),
        "anti_patterns": list(model.get("anti_patterns", [])),
        "startup_receipt_requirements": dict(model.get("startup_receipt_requirements", {})),
    }
