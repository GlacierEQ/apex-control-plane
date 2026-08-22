#!/usr/bin/env python3
"""Admit host-side exact-approved provider execution observations into APEX.

The manifest points to local action-result and terminal-readback files created by a direct
authenticated host operation. This command reads those files only to calculate SHA-256
digests. It never invokes a provider, loads credentials, schedules a write, or copies
provider material to the JSONL receipt ledger.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from approved_operation_bridge import (
    ProviderExecutionObservation,
    build_execution_receipt,
    render_safe_execution_receipt,
    validate_approved_action_request,
)
from connector_receipts import ConnectorReceiptError, load_connector_catalog
from control_plane_runtime import CaseBrainOrchestrator, Producer, to_jsonable


class ExecutionAdmissionInputError(ValueError):
    """Raised for malformed local execution-observation input."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExecutionAdmissionInputError(f"{name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ExecutionAdmissionInputError(f"{name} is required")
    return text


def _parse_time(value: Any, name: str) -> datetime:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionAdmissionInputError(f"{name} must be RFC3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionAdmissionInputError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _refs(value: Any, name: str, *, required: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ExecutionAdmissionInputError(f"{name} must be an array")
    refs = tuple(str(item).strip() for item in value if str(item).strip())
    if required and not refs:
        raise ExecutionAdmissionInputError(f"{name} requires unique non-empty values")
    if len(set(refs)) != len(refs):
        raise ExecutionAdmissionInputError(f"{name} contains duplicates")
    return refs


def _read_material(value: Any, name: str, *, required: bool) -> bytes | None:
    if value is None and not required:
        return None
    path = Path(_text(value, name))
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise ExecutionAdmissionInputError(f"{name} file not found: {path}") from exc


def load_json(path: Path, name: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExecutionAdmissionInputError(f"{name} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ExecutionAdmissionInputError(f"{name} is not valid JSON: {exc}") from exc
    return _mapping(payload, name)


def admit_execution_manifest(
    *,
    action_request_path: Path,
    execution_manifest_path: Path,
    receipt_ledger_path: Path,
    commit_sha: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate and admit one host-completed exact-approved provider operation."""
    catalog = load_connector_catalog(ROOT / "config" / "apex_connector_catalog.json")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    action_request = load_json(action_request_path, "action request")
    action = validate_approved_action_request(action_request, catalog, now=current)
    manifest = load_json(execution_manifest_path, "execution manifest")
    result_state = _text(manifest.get("result_state"), "execution manifest result_state")
    if result_state not in {"success", "failure"}:
        raise ExecutionAdmissionInputError("execution manifest result_state must be success or failure")
    verification_passed = manifest.get("verification_passed")
    if not isinstance(verification_passed, bool):
        raise ExecutionAdmissionInputError("execution manifest verification_passed must be boolean")

    execution = ProviderExecutionObservation(
        source_refs=_refs(manifest.get("execution_source_refs"), "execution_source_refs"),
        material=_read_material(manifest.get("execution_observation_path"), "execution_observation_path", required=True),
        observed_at=_parse_time(manifest.get("executed_at"), "executed_at"),
    )
    readback: ProviderExecutionObservation | None = None
    if result_state == "success":
        readback = ProviderExecutionObservation(
            source_refs=_refs(manifest.get("readback_source_refs"), "readback_source_refs"),
            material=_read_material(manifest.get("readback_observation_path"), "readback_observation_path", required=True),
            observed_at=_parse_time(manifest.get("readback_at"), "readback_at"),
        )

    receipt = build_execution_receipt(
        action=action,
        execution=execution,
        result_target=_mapping(manifest.get("result_target"), "result_target"),
        readback=readback,
        verification_passed=verification_passed,
        result_state=result_state,
    )
    runtime = CaseBrainOrchestrator(
        producer=Producer(
            repo="GlacierEQ/apex-control-plane",
            commit_sha=commit_sha,
            component="authenticated-session-approved-operation-bridge",
        )
    )
    accepted = runtime.admit_connector_execution_receipt(
        action_request,
        receipt,
        catalog,
        now=current,
    )
    receipt_ledger_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_ledger_path.write_text(render_safe_execution_receipt(receipt), encoding="utf-8")
    return {
        "status": "accepted",
        "accepted": accepted,
        "audit_receipts": [to_jsonable(item) for item in runtime.receipts],
        "external_action_authorized": True,
        "repository_provider_execution": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-request", type=Path, required=True)
    parser.add_argument("--execution-manifest", type=Path, required=True)
    parser.add_argument("--receipt-ledger", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    arguments = parser.parse_args()
    try:
        result = admit_execution_manifest(
            action_request_path=arguments.action_request,
            execution_manifest_path=arguments.execution_manifest,
            receipt_ledger_path=arguments.receipt_ledger,
            commit_sha=arguments.commit_sha,
        )
    except (ExecutionAdmissionInputError, ConnectorReceiptError, ValueError) as exc:
        print(f"execution receipt admission refused: {exc}", file=sys.stderr)
        return 78
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
