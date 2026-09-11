"""Shared structural contract for source-bound Operator literal fidelity.

Preflight uses this module to require a complete provenance shape before a
receipt can progress. The hard lock then independently resolves source bytes
and proves the declared hashes/spans against that external source root.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

ALLOWED_OPERATOR_SOURCE_KINDS = frozenset(
    {"operator_message", "operator_file", "operator_record"}
)
DERIVATIVE_SOURCE_KINDS = frozenset(
    {
        "assistant_summary",
        "checkpoint",
        "index",
        "manifest",
        "memory_summary",
        "profile",
        "working_model",
    }
)
ACTIVE_CONTRADICTION_STATES = frozenset({"active", "resolved_consistent"})
SOURCE_VERIFICATION_STATE = "source_resolved"


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256_ref(value: Any) -> bool:
    if not _nonempty_text(value):
        return False
    prefix, sep, digest = value.strip().partition(":")
    return (
        sep == ":"
        and prefix.lower() == "sha256"
        and len(digest) == 64
        and all(ch in "0123456789abcdefABCDEF" for ch in digest)
    )


def operator_source_binding_receipt_contract() -> list[dict[str, Any]]:
    """Describe one binding; callers repeat it once per literal constraint."""
    return [
        {
            "literal_index": "zero-based index into literal_constraints",
            "proposition_id": "stable proposition identity for this Operator source span",
            "source_kind": sorted(ALLOWED_OPERATOR_SOURCE_KINDS),
            "source_ref": "file:<path relative to GLACIEREQ_OPERATOR_SOURCE_ROOT>",
            "source_sha256": "sha256:<64 hex over independently resolved whole source>",
            "span_start_byte": "inclusive UTF-8 byte offset",
            "span_end_byte": "exclusive UTF-8 byte offset",
            "span_sha256": "sha256:<64 hex over exact source span>",
            "temporal_context": "source timestamp/message context/version identity",
            "contradiction_state": sorted(ACTIVE_CONTRADICTION_STATES),
            "verification_state": SOURCE_VERIFICATION_STATE,
        }
    ]


def validate_operator_source_binding_shape(
    row: Mapping[str, Any], constraints: Sequence[str]
) -> tuple[str, ...]:
    """Fail closed on provenance shape without pretending to verify source bytes."""
    errors: list[str] = []
    bindings = row.get("operator_source_bindings")
    if not isinstance(bindings, list):
        return (
            "operator_fidelity.operator_source_bindings must independently bind every literal constraint to source-bearing Operator bytes",
        )
    if len(bindings) != len(constraints):
        errors.append(
            "operator_fidelity.operator_source_bindings must contain exactly one binding per literal constraint"
        )

    seen_indexes: set[int] = set()
    for position, binding in enumerate(bindings):
        prefix = f"operator_fidelity.operator_source_bindings[{position}]"
        if not isinstance(binding, Mapping):
            errors.append(f"{prefix} must be an object")
            continue

        literal_index = binding.get("literal_index")
        if not isinstance(literal_index, int) or isinstance(literal_index, bool):
            errors.append(f"{prefix}.literal_index must be an integer")
            continue
        if literal_index < 0 or literal_index >= len(constraints):
            errors.append(f"{prefix}.literal_index is out of range")
            continue
        if literal_index in seen_indexes:
            errors.append(f"{prefix}.literal_index is duplicated")
            continue
        seen_indexes.add(literal_index)

        source_kind = str(binding.get("source_kind", "")).strip()
        if source_kind in DERIVATIVE_SOURCE_KINDS:
            errors.append(
                f"{prefix}.source_kind={source_kind!r} is derivative and cannot authorize verbatim Operator fidelity"
            )
        elif source_kind not in ALLOWED_OPERATOR_SOURCE_KINDS:
            errors.append(
                f"{prefix}.source_kind must be one of {sorted(ALLOWED_OPERATOR_SOURCE_KINDS)!r}"
            )

        for field_name in ("proposition_id", "source_ref", "temporal_context"):
            if not _nonempty_text(binding.get(field_name)):
                errors.append(f"{prefix}.{field_name} must be non-empty")

        source_ref = str(binding.get("source_ref", "")).strip()
        if source_ref and not source_ref.startswith("file:"):
            errors.append(
                f"{prefix}.source_ref must use file: under GLACIEREQ_OPERATOR_SOURCE_ROOT"
            )

        for field_name in ("source_sha256", "span_sha256"):
            if not _is_sha256_ref(binding.get(field_name)):
                errors.append(f"{prefix}.{field_name} must be sha256:<64 hex>")

        span_start = binding.get("span_start_byte")
        span_end = binding.get("span_end_byte")
        if (
            not isinstance(span_start, int)
            or isinstance(span_start, bool)
            or not isinstance(span_end, int)
            or isinstance(span_end, bool)
            or span_start < 0
            or span_end <= span_start
        ):
            errors.append(
                f"{prefix}.span byte range must be non-negative and increasing"
            )

        contradiction_state = str(binding.get("contradiction_state", "")).strip()
        if contradiction_state not in ACTIVE_CONTRADICTION_STATES:
            errors.append(
                f"{prefix}.contradiction_state must be active or resolved_consistent; superseded/conflicted source cannot silently remain authoritative"
            )

        if (
            str(binding.get("verification_state", "")).strip()
            != SOURCE_VERIFICATION_STATE
        ):
            errors.append(
                f"{prefix}.verification_state must be {SOURCE_VERIFICATION_STATE!r}"
            )

    if len(seen_indexes) != len(constraints):
        errors.append(
            "operator_fidelity.operator_source_bindings do not cover every literal constraint exactly once"
        )
    return tuple(dict.fromkeys(errors))
