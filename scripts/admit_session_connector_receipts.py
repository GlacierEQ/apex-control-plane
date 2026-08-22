"""Admit authenticated-session read observations into the APEX audit ledger.

The input manifest names catalogued read requests and local observation files produced
by direct authenticated provider calls. Provider material is read only to calculate a
SHA-256 digest; it is never copied to the generated receipt ledger. This command
cannot invoke providers and cannot execute an external action.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authenticated_session_bridge import ProviderObservation, build_read_receipt
from connector_bridge_contract import build_read_request
from connector_receipts import ConnectorReceiptError, canonical_json, load_connector_catalog
from control_plane_runtime import CaseBrainOrchestrator, Producer, to_jsonable
from direct_connector_runtime_contract import validate_connector_transport_admission


class AdmissionInputError(ValueError):
    """Raised when a local observation manifest is unsafe or incomplete."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AdmissionInputError(f"{name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AdmissionInputError(f"{name} is required")
    return text


def _parse_time(value: Any) -> datetime:
    text = _text(value, "observed_at")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdmissionInputError("observed_at must be RFC3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AdmissionInputError("observed_at must include a timezone")
    return parsed.astimezone(UTC)


def load_manifest(path: Path) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AdmissionInputError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AdmissionInputError(f"manifest is not valid JSON: {exc}") from exc
    root = _mapping(payload, "manifest")
    entries = root.get("observations")
    if not isinstance(entries, list) or not entries:
        raise AdmissionInputError("manifest.observations requires at least one entry")
    return [_mapping(entry, "observation entry") for entry in entries]


def _read_material(path_value: Any) -> bytes:
    path = Path(_text(path_value, "observation_path"))
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise AdmissionInputError(f"observation file not found: {path}") from exc


def _source_refs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AdmissionInputError("source_refs must be an array")
    refs = tuple(str(item).strip() for item in value if str(item).strip())
    if not refs or len(set(refs)) != len(refs):
        raise AdmissionInputError("source_refs requires unique non-empty values")
    return refs


def admit_manifest(
    *,
    manifest_path: Path,
    receipt_ledger_path: Path,
    commit_sha: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build and admit safe read receipts from a local authenticated-observation manifest."""
    validate_connector_transport_admission("authenticated_session_provider_bridge")
    catalog = load_connector_catalog(ROOT / "config" / "apex_connector_catalog.json")
    runtime = CaseBrainOrchestrator(
        producer=Producer(
            repo="GlacierEQ/apex-control-plane",
            commit_sha=commit_sha,
            component="authenticated-session-connector-bridge",
        )
    )
    current = (now or datetime.now(UTC)).astimezone(UTC)
    receipts: list[Mapping[str, Any]] = []
    accepted: list[Mapping[str, Any]] = []

    for index, entry in enumerate(load_manifest(manifest_path), start=1):
        connector = _text(entry.get("connector"), f"observations[{index}].connector")
        operation = _text(entry.get("operation"), f"observations[{index}].operation")
        profile = _text(entry.get("profile"), f"observations[{index}].profile")
        target = _mapping(entry.get("target"), f"observations[{index}].target")
        observed_at = _parse_time(entry.get("observed_at"))
        request = build_read_request(
            connector=connector,
            operation=operation,
            profile=profile,
            target=target,
            catalog=catalog,
            requested_at=observed_at,
        )
        material = _read_material(entry.get("observation_path"))
        receipt = build_read_receipt(
            request=request,
            observation=ProviderObservation(
                source_refs=_source_refs(entry.get("source_refs")),
                material=material,
                observed_at=observed_at,
            ),
            catalog=catalog,
        )
        outcome = runtime.admit_connector_read_receipt(receipt, catalog, now=current)
        receipts.append(receipt)
        accepted.append(outcome)

    receipt_ledger_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_ledger_path.write_text(
        "\n".join(canonical_json(receipt) for receipt in receipts) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "accepted",
        "receipt_count": len(receipts),
        "accepted": accepted,
        "audit_receipts": [to_jsonable(receipt) for receipt in runtime.receipts],
        "external_action_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt-ledger", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    arguments = parser.parse_args()
    try:
        result = admit_manifest(
            manifest_path=arguments.manifest,
            receipt_ledger_path=arguments.receipt_ledger,
            commit_sha=arguments.commit_sha,
        )
    except (AdmissionInputError, ConnectorReceiptError, ValueError) as exc:
        print(f"receipt admission refused: {exc}", file=sys.stderr)
        return 78
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
