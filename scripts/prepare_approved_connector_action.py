#!/usr/bin/env python3
"""Prepare one exact-approved APEX provider-operation plan.

This command validates a local action-request JSON document against the active catalog
and returns the one direct authenticated host operation plan. It does not call a provider,
load a credential, schedule work, or retain provider content.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from approved_operation_bridge import action_audit_scope, validate_approved_action_request
from approved_session_dispatch import build_approved_session_operation_plan
from connector_receipts import ConnectorReceiptError, load_connector_catalog
from direct_connector_runtime_contract import validate_connector_transport_admission


class ActionInputError(ValueError):
    """Raised for malformed local exact-approval action input."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ActionInputError(f"{name} must be an object")
    return value


def load_action_request(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ActionInputError(f"action request not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ActionInputError(f"action request is not valid JSON: {exc}") from exc
    return _mapping(payload, "action request")


def prepare_action_plan(
    *,
    action_request_path: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return an approved host plan and digest-only audit scope for one exact action."""
    validate_connector_transport_admission("authenticated_session_provider_bridge")
    catalog = load_connector_catalog(ROOT / "config" / "apex_connector_catalog.json")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    request = load_action_request(action_request_path)
    action = validate_approved_action_request(request, catalog, now=current)
    plan = build_approved_session_operation_plan(
        action_request=request,
        catalog=catalog,
        now=current,
    )
    return {
        "status": "approved_for_direct_host_execution",
        "plan": asdict(plan),
        "audit_scope": action_audit_scope(action),
        "external_action_authorized": True,
        "repository_provider_execution": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-request", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        result = prepare_action_plan(action_request_path=arguments.action_request)
    except (ActionInputError, ConnectorReceiptError, ValueError) as exc:
        print(f"approved action refused: {exc}", file=sys.stderr)
        return 78
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
