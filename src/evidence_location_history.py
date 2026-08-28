from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LocationContinuityError(ValueError):
    """Raised when two observations cannot safely be treated as one evidence item."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class LocatorObservation:
    evidence_id: str
    provider: str
    locator: str
    observed_at: str
    provider_file_id: str | None = None
    provider_revision: str | None = None
    display_locator: str | None = None
    filename: str | None = None
    byte_size: int | None = None
    sha256: str | None = None
    account_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id is required")
        if not self.provider.strip():
            raise ValueError("provider is required")
        if not self.locator.strip():
            raise ValueError("locator is required")
        if self.byte_size is not None and self.byte_size < 0:
            raise ValueError("byte_size cannot be negative")
        if self.sha256 is not None and not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("sha256 must be a lowercase 64-character hex digest")

    @property
    def basename(self) -> str:
        if self.filename:
            return self.filename
        return PurePosixPath(self.locator.replace("\\", "/")).name

    @property
    def provider_identity(self) -> str | None:
        if not self.provider_file_id:
            return None
        return f"{self.provider}:{self.provider_file_id}"

    @property
    def content_identity(self) -> str | None:
        if not self.sha256:
            return None
        return f"sha256:{self.sha256}"

    def fingerprint(self) -> str:
        payload = asdict(self)
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def transfer_verification_status(
    before_sha256: str | None,
    after_sha256: str | None,
) -> str:
    """Return verified, mismatch, or pending without inventing missing hashes."""
    if before_sha256 is None or after_sha256 is None:
        return "pending"
    if before_sha256 == after_sha256:
        return "verified"
    return "mismatch"


def continuity_match(previous: LocatorObservation, current: LocatorObservation) -> str:
    """Describe the strength of the evidence-identity link between observations."""
    if previous.evidence_id != current.evidence_id:
        if previous.sha256 and current.sha256 and previous.sha256 == current.sha256:
            return "verified_content_duplicate"
        return "different_evidence_id"

    hash_status = transfer_verification_status(previous.sha256, current.sha256)
    if hash_status == "mismatch":
        return "content_conflict"
    if hash_status == "verified":
        return "verified_content_continuity"
    if (
        previous.provider_identity
        and current.provider_identity
        and previous.provider_identity == current.provider_identity
    ):
        return "strong_provider_continuity"
    if previous.byte_size is not None and previous.byte_size == current.byte_size:
        return "possible_continuity"
    return "unresolved_continuity"


def classify_transition(
    previous: LocatorObservation, current: LocatorObservation
) -> str:
    """Classify a locator change without making path stability an integrity requirement."""
    if previous.evidence_id != current.evidence_id:
        raise LocationContinuityError("transition requires the same Evidence ID")

    hash_status = transfer_verification_status(previous.sha256, current.sha256)
    if hash_status == "mismatch":
        raise LocationContinuityError(
            "content hashes differ; do not silently continue the same evidence lineage"
        )

    if previous.provider != current.provider:
        return "transfer_verified" if hash_status == "verified" else "transfer_pending"

    if (
        previous.provider_file_id
        and current.provider_file_id
        and previous.provider_file_id != current.provider_file_id
    ):
        return "copied" if hash_status == "verified" else "transfer_pending"

    if previous.locator != current.locator:
        if previous.basename != current.basename:
            return "renamed"
        return "moved"

    return "observed"


def build_locator_transition(
    previous: LocatorObservation,
    current: LocatorObservation,
) -> dict[str, Any]:
    """Build an append-only custody/location transition receipt."""
    kind = classify_transition(previous, current)
    verification = transfer_verification_status(previous.sha256, current.sha256)
    return {
        "evidence_id": current.evidence_id,
        "observation_kind": kind,
        "source": {
            "provider": previous.provider,
            "provider_file_id": previous.provider_file_id,
            "provider_revision": previous.provider_revision,
            "locator": previous.locator,
            "display_locator": previous.display_locator,
            "filename": previous.basename,
            "sha256": previous.sha256,
        },
        "target": {
            "provider": current.provider,
            "provider_file_id": current.provider_file_id,
            "provider_revision": current.provider_revision,
            "locator": current.locator,
            "display_locator": current.display_locator,
            "filename": current.basename,
            "sha256": current.sha256,
        },
        "verification": verification,
        "continuity": continuity_match(previous, current),
        "observed_at": current.observed_at,
        "observation_fingerprint": current.fingerprint(),
    }
