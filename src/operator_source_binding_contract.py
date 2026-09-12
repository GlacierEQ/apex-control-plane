"""Scoped provenance primitives for source-bound Operator propositions.

This module owns only the reusable invariants of an Operator source-span
binding: source role, derivative quarantine, proposition identity, hashes,
byte range, temporal/contradiction state, and independent byte readback.
Domain gates retain their own authority semantics: literal fidelity controls
literal coverage; executable-frontier authority controls entailment/frontier
identity. This module is therefore a shared primitive, not a global sovereign.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SourceResolver = Callable[[str], bytes]

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


class SourceReadbackUnresolved(RuntimeError):
    """Typed boundary for retrieval failures that must not become evidence absence."""


@dataclass(frozen=True, slots=True)
class SourceSpanVerification:
    resolved: bool
    source_bytes: bytes | None
    span_bytes: bytes | None
    span_text: str | None
    errors: tuple[str, ...]


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def sha256_ref(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def is_sha256_ref(value: Any) -> bool:
    if not nonempty_text(value):
        return False
    prefix, sep, digest = value.strip().partition(":")
    return (
        sep == ":"
        and prefix.lower() == "sha256"
        and len(digest) == 64
        and all(ch in "0123456789abcdefABCDEF" for ch in digest)
    )


def validate_source_span_binding_shape(
    binding: Mapping[str, Any],
    *,
    prefix: str,
    allowed_source_kinds: frozenset[str] = ALLOWED_OPERATOR_SOURCE_KINDS,
    require_temporal_context: bool = True,
    require_unsuperseded: bool = False,
) -> tuple[str, ...]:
    """Validate reusable source-span provenance shape without claiming readback."""
    errors: list[str] = []
    source_kind = str(binding.get("source_kind", "")).strip()
    if source_kind in DERIVATIVE_SOURCE_KINDS:
        errors.append(
            f"{prefix}.source_kind={source_kind!r} is derivative and cannot authorize Operator direction"
        )
    elif source_kind not in allowed_source_kinds:
        errors.append(
            f"{prefix}.source_kind must be one of {sorted(allowed_source_kinds)!r}"
        )

    required_text = ["proposition_id", "source_ref"]
    if require_temporal_context:
        required_text.append("temporal_context")
    for field_name in required_text:
        if not nonempty_text(binding.get(field_name)):
            errors.append(f"{prefix}.{field_name} must be non-empty")

    for field_name in ("source_sha256", "span_sha256"):
        if not is_sha256_ref(binding.get(field_name)):
            errors.append(f"{prefix}.{field_name} must be sha256:<64 hex>")

    start = binding.get("span_start_byte")
    end = binding.get("span_end_byte")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end <= start
    ):
        errors.append(f"{prefix}.span byte range must be non-negative and increasing")

    contradiction_state = str(binding.get("contradiction_state", "")).strip()
    if contradiction_state not in ACTIVE_CONTRADICTION_STATES:
        errors.append(
            f"{prefix}.contradiction_state must be active or resolved_consistent; superseded/conflicted source cannot silently remain authoritative"
        )
    if require_unsuperseded and nonempty_text(binding.get("superseded_by")):
        errors.append(f"{prefix}.superseded_by must be empty for an active source")

    if str(binding.get("verification_state", "")).strip() != SOURCE_VERIFICATION_STATE:
        errors.append(
            f"{prefix}.verification_state must be {SOURCE_VERIFICATION_STATE!r}"
        )
    return tuple(dict.fromkeys(errors))


def verify_source_span_binding(
    binding: Mapping[str, Any],
    *,
    resolver: SourceResolver,
    prefix: str,
    expected_text: str | None = None,
    allowed_source_kinds: frozenset[str] = ALLOWED_OPERATOR_SOURCE_KINDS,
    require_temporal_context: bool = True,
    require_unsuperseded: bool = False,
) -> SourceSpanVerification:
    """Independently resolve bytes and prove hashes/span/text for one binding."""
    errors = list(
        validate_source_span_binding_shape(
            binding,
            prefix=prefix,
            allowed_source_kinds=allowed_source_kinds,
            require_temporal_context=require_temporal_context,
            require_unsuperseded=require_unsuperseded,
        )
    )
    if errors:
        return SourceSpanVerification(False, None, None, None, tuple(errors))

    source_ref = str(binding["source_ref"])
    try:
        source_bytes = resolver(source_ref)
    except SourceReadbackUnresolved as exc:
        return SourceSpanVerification(False, None, None, None, (f"{prefix}.{exc}",))
    except Exception as exc:  # noqa: BLE001 - fail-closed resolver boundary
        return SourceSpanVerification(
            False,
            None,
            None,
            None,
            (f"{prefix}.source readback unresolved: {exc.__class__.__name__}",),
        )
    if not isinstance(source_bytes, bytes):
        return SourceSpanVerification(
            False, None, None, None, (f"{prefix}.resolver must return bytes",)
        )

    if binding.get("source_sha256") != sha256_ref(source_bytes):
        errors.append(
            f"{prefix}.source_sha256 does not match independently resolved bytes"
        )

    start = int(binding["span_start_byte"])
    end = int(binding["span_end_byte"])
    if end > len(source_bytes):
        errors.append(f"{prefix}.span byte range is invalid for resolved source")
        return SourceSpanVerification(True, source_bytes, None, None, tuple(errors))

    span = source_bytes[start:end]
    if binding.get("span_sha256") != sha256_ref(span):
        errors.append(
            f"{prefix}.span_sha256 does not match independently resolved span"
        )
    try:
        span_text = span.decode("utf-8")
    except UnicodeDecodeError:
        errors.append(f"{prefix}.source span must be valid UTF-8")
        return SourceSpanVerification(True, source_bytes, span, None, tuple(errors))
    if expected_text is not None and span_text != expected_text:
        errors.append(
            f"{prefix}.resolved source span does not exactly equal expected text"
        )
    return SourceSpanVerification(True, source_bytes, span, span_text, tuple(errors))


def operator_source_binding_receipt_contract() -> list[dict[str, Any]]:
    """Describe one literal binding; callers repeat it once per constraint."""
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
    """Enforce literal-coverage shape while delegating shared provenance rules."""
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

        errors.extend(validate_source_span_binding_shape(binding, prefix=prefix))
        source_ref = str(binding.get("source_ref", "")).strip()
        if source_ref and not source_ref.startswith("file:"):
            errors.append(
                f"{prefix}.source_ref must use file: under GLACIEREQ_OPERATOR_SOURCE_ROOT"
            )

    if len(seen_indexes) != len(constraints):
        errors.append(
            "operator_fidelity.operator_source_bindings do not cover every literal constraint exactly once"
        )
    return tuple(dict.fromkeys(errors))
