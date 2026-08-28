from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Iterable

EVIDENCE_NAMESPACE = uuid.UUID("c5ae4e61-50b9-4b42-bd13-9e12b5c7b48a")
ACQUISITION_NAMESPACE = uuid.UUID("6404bc0d-d92a-4a7e-9c52-1f0db26d446e")
DERIVATIVE_NAMESPACE = uuid.UUID("4b39bde2-0995-43ce-85b8-82731a555bda")

PLANE_SOURCE = "source"
PLANE_EVIDENCE = "evidence"
PLANE_WORKING = "working"
PLANE_CASE = "case"
VALID_PLANES = {PLANE_SOURCE, PLANE_EVIDENCE, PLANE_WORKING, PLANE_CASE}

HASH_CHUNK_SIZE = 8 * 1024 * 1024


class IntegrityError(RuntimeError):
    """Raised when evidence-integrity invariants are violated."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_stream(stream: BinaryIO, chunk_size: int = HASH_CHUNK_SIZE) -> str:
    hasher = hashlib.sha256()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)
    return hasher.hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    with open(path, "rb") as fh:
        return sha256_stream(fh)


def stable_evidence_id(
    source_provider: str, source_file_id: str, source_revision: str | None = None
) -> str:
    del source_revision
    material = "\x1f".join([source_provider.strip().lower(), source_file_id.strip()])
    return f"EVD-{uuid.uuid5(EVIDENCE_NAMESPACE, material)}"


def stable_acquisition_id(evidence_id: str, sha256: str, method: str) -> str:
    material = "\x1f".join([evidence_id, sha256.lower(), method.strip().lower()])
    return f"ACQ-{uuid.uuid5(ACQUISITION_NAMESPACE, material)}"


def stable_derivative_id(
    evidence_id: str, transformation_type: str, recipe_hash_value: str, output_hash: str
) -> str:
    material = "\x1f".join(
        [
            evidence_id,
            transformation_type.strip().lower(),
            recipe_hash_value.lower(),
            output_hash.lower(),
        ]
    )
    return f"DRV-{uuid.uuid5(DERIVATIVE_NAMESPACE, material)}"


def recipe_hash(recipe: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(recipe).encode("utf-8"))


def custody_event_hash(previous_hash: str | None, payload: dict[str, Any]) -> str:
    envelope = {"previous_event_hash": previous_hash, "payload": payload}
    return sha256_bytes(canonical_json(envelope).encode("utf-8"))


@dataclass(frozen=True)
class SourceObservation:
    source_provider: str
    source_file_id: str
    source_revision: str | None
    source_path: str
    original_filename: str
    byte_size: int | None
    mime_type: str | None = None
    client_modified: str | None = None
    server_modified: str | None = None
    observed_at: str | None = None

    @property
    def evidence_id(self) -> str:
        return stable_evidence_id(
            self.source_provider, self.source_file_id, self.source_revision
        )

    def to_manifest_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["evidence_id"] = self.evidence_id
        record["plane"] = PLANE_SOURCE
        record["hash_status"] = "not_acquired"
        record["observed_at"] = self.observed_at or utc_now_iso()
        return record


@dataclass(frozen=True)
class AcquisitionReceipt:
    evidence_id: str
    acquisition_id: str
    method: str
    source_hash: str
    destination_hash: str
    byte_size: int
    tool_name: str
    tool_version: str
    acquired_at: str
    verified: bool

    @classmethod
    def from_paths(
        cls,
        *,
        evidence_id: str,
        source_path: str | os.PathLike[str],
        destination_path: str | os.PathLike[str],
        method: str,
        tool_name: str,
        tool_version: str,
    ) -> "AcquisitionReceipt":
        source = Path(source_path)
        destination = Path(destination_path)
        source_hash = sha256_file(source)
        destination_hash = sha256_file(destination)
        if source.stat().st_size != destination.stat().st_size:
            raise IntegrityError("acquisition byte-size mismatch")
        if source_hash != destination_hash:
            raise IntegrityError("acquisition SHA-256 mismatch")
        return cls(
            evidence_id=evidence_id,
            acquisition_id=stable_acquisition_id(evidence_id, source_hash, method),
            method=method,
            source_hash=source_hash,
            destination_hash=destination_hash,
            byte_size=source.stat().st_size,
            tool_name=tool_name,
            tool_version=tool_version,
            acquired_at=utc_now_iso(),
            verified=True,
        )


@dataclass(frozen=True)
class DerivativeReceipt:
    derivative_id: str
    evidence_id: str
    transformation_type: str
    recipe: dict[str, Any]
    recipe_hash: str
    input_sha256: str
    output_sha256: str
    tool_name: str
    tool_version: str
    created_at: str
    plane: str = PLANE_WORKING
    label: str = "DERIVATIVE FOR REVIEW"

    @classmethod
    def register(
        cls,
        *,
        evidence_id: str,
        transformation_type: str,
        recipe: dict[str, Any],
        input_path: str | os.PathLike[str],
        output_path: str | os.PathLike[str],
        tool_name: str,
        tool_version: str,
    ) -> "DerivativeReceipt":
        r_hash = recipe_hash(recipe)
        input_hash = sha256_file(input_path)
        output_hash = sha256_file(output_path)
        return cls(
            derivative_id=stable_derivative_id(
                evidence_id, transformation_type, r_hash, output_hash
            ),
            evidence_id=evidence_id,
            transformation_type=transformation_type,
            recipe=recipe,
            recipe_hash=r_hash,
            input_sha256=input_hash,
            output_sha256=output_hash,
            tool_name=tool_name,
            tool_version=tool_version,
            created_at=utc_now_iso(),
        )


def build_observation_manifest(
    observations: Iterable[SourceObservation],
    *,
    matter_id: str,
    scope: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    items = sorted(
        (obs.to_manifest_record() for obs in observations),
        key=lambda item: (
            item["source_provider"],
            item["source_file_id"],
            item["source_revision"] or "",
        ),
    )
    body = {
        "schema": "glaciereq.forensic.observation-manifest.v1",
        "matter_id": matter_id,
        "generated_at": generated_at or utc_now_iso(),
        "scope": scope,
        "items": items,
        "item_count": len(items),
    }
    body["manifest_sha256"] = sha256_bytes(canonical_json(body).encode("utf-8"))
    return body


def infer_mime_type(filename: str) -> str | None:
    return mimetypes.guess_type(filename)[0]


def verify_manifest(manifest: dict[str, Any]) -> bool:
    expected = manifest.get("manifest_sha256")
    if not isinstance(expected, str):
        return False
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    return sha256_bytes(canonical_json(unsigned).encode("utf-8")) == expected
