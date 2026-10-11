"""Guard against destructive evidence-state projection and chain propagation.

The guard keeps historically established verification separate from current
readback and current operational authority. It also prevents derivative copies
from manufacturing corroboration or silently outranking their source lineage.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

VERIFIED_HISTORY = {"PROVIDER_VERIFIED", "SOURCE_VERIFIED", "VERIFIED"}
PRIMARY_SOURCE_CLASSES = {
    "NATIVE_OR_PROVIDER",
    "NATIVE_SOURCE",
    "PROVIDER_STATE",
    "AUTHORITATIVE_SOURCE",
}
DERIVATIVE_SOURCE_CLASSES = {
    "DERIVATIVE_SUMMARY",
    "ASSISTANT_DERIVATIVE",
    "MEMORY_PROJECTION",
    "INDEX",
    "CHECKPOINT",
}
UNRESOLVED_MARKERS = {"UNRESOLVED", "READBACK_UNRESOLVED", "PROVIDER_READBACK_UNRESOLVED"}


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _is_unresolved(value: Any) -> bool:
    normalized = str(value or "").strip().upper()
    return normalized in UNRESOLVED_MARKERS or normalized.endswith("_UNRESOLVED")


def validate_evidence_projection(
    prior: Mapping[str, Any],
    current: Mapping[str, Any],
) -> tuple[str, ...]:
    """Validate a derived/current projection against its stronger prior lineage."""

    errors: list[str] = []

    prior_id = str(prior.get("proposition_id", "")).strip()
    current_id = str(current.get("proposition_id", "")).strip()
    if prior_id and current_id and prior_id != current_id:
        errors.append("projection proposition_id differs from prior proposition")

    prior_truth = str(prior.get("historical_truth_state", "")).strip().upper()
    current_truth = str(current.get("historical_truth_state", "")).strip().upper()
    source_class = str(current.get("source_class", "")).strip().upper()

    if prior_truth in VERIFIED_HISTORY and current_truth not in VERIFIED_HISTORY:
        falsification_refs = _strings(current.get("falsification_refs"))
        falsification_source_class = str(
            current.get("falsification_source_class", "")
        ).strip().upper()
        if (
            not falsification_refs
            or falsification_source_class not in PRIMARY_SOURCE_CLASSES
        ):
            errors.append(
                "historical truth demotion requires affirmative falsification "
                "from a stronger source; omission, retrieval failure, or "
                "derivative uncertainty is insufficient"
            )

    if source_class in DERIVATIVE_SOURCE_CLASSES:
        parents = _strings(current.get("parent_lineage_ids"))
        if not parents:
            errors.append("derivative projection requires parent lineage")
        if current.get("superseded_by") and current_truth not in VERIFIED_HISTORY:
            errors.append(
                "derivative artifact cannot demote or supersede a stronger parent lineage"
            )

    prior_roots = set(_strings(prior.get("root_lineage_ids")))
    current_roots = set(_strings(current.get("root_lineage_ids")))
    if prior_roots and not prior_roots.issubset(current_roots):
        errors.append("projection dropped root lineage from prior evidence state")

    unresolved_dimensions = set(_strings(current.get("unresolved_dimensions")))
    readback_state = current.get("readback_state")
    authority_state = current.get("authority_state")
    if _is_unresolved(readback_state) and "current_readback" not in unresolved_dimensions:
        errors.append(
            "readback unresolved state requires unresolved_dimensions=current_readback"
        )
    if (
        _is_unresolved(authority_state)
        and "current_execution_authority" not in unresolved_dimensions
    ):
        errors.append(
            "authority unresolved state requires "
            "unresolved_dimensions=current_execution_authority"
        )

    return tuple(dict.fromkeys(errors))


def count_independent_lineages(records: Sequence[Mapping[str, Any]]) -> int:
    """Count root evidence lineages, not derivative copies.

    Multiple summaries, indexes, memories, or casebook projections that descend
    from one root source remain one evidentiary lineage.
    """

    roots: set[str] = set()
    for record in records:
        roots.update(_strings(record.get("root_lineage_ids")))
    return len(roots)
