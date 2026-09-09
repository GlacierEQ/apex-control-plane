#!/usr/bin/env python3
"""Fail-closed validator for GlacierEQ estate execution routing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "config" / "estate_execution_routes.json"
ALLOWED_ROUTES = {
    "buildkite_verified_execution",
    "public_action_face",
    "connector_worker_fabric",
    "private_github_actions_exception",
    "none",
}
ALLOWED_MIGRATION_STATES = {
    "route_selected_unmigrated",
    "canary_ready",
    "dual_run_verification",
    "target_verified",
    "source_disabled",
    "complete",
}
REQUIRED_ROUTING_LAWS = {
    "no_verified_delta_no_success",
    "do_not_disable_current_route_until_target_route_is_proven",
    "do_not_auto_admit_repositories_to_public_action_face",
    "destructive_provider_mutation_requires_explicit_operator_authorization",
    "private_github_actions_is_not_the_estate_scheduler",
    "failure_reporting_must_not_depend_on_the_same_failed_execution_substrate",
}


def load_registry(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_registry(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    routes = data.get("route_definitions")
    if not isinstance(routes, dict):
        return ["route_definitions must be an object"]

    missing_routes = ALLOWED_ROUTES - set(routes)
    if missing_routes:
        errors.append(f"missing route definitions: {sorted(missing_routes)}")

    laws = set(data.get("routing_laws") or [])
    missing_laws = REQUIRED_ROUTING_LAWS - laws
    if missing_laws:
        errors.append(f"missing routing laws: {sorted(missing_laws)}")

    workloads = data.get("initial_reconciliation")
    if not isinstance(workloads, list) or not workloads:
        errors.append("initial_reconciliation must contain at least one workload")
        return errors

    ids: set[str] = set()
    for index, workload in enumerate(workloads):
        prefix = f"initial_reconciliation[{index}]"
        if not isinstance(workload, dict):
            errors.append(f"{prefix} must be an object")
            continue

        workload_id = workload.get("workload_id")
        if not isinstance(workload_id, str) or not workload_id.strip():
            errors.append(f"{prefix}.workload_id must be a non-empty string")
        elif workload_id in ids:
            errors.append(f"duplicate workload_id: {workload_id}")
        else:
            ids.add(workload_id)

        current_route = workload.get("current_route")
        target_route = workload.get("target_route")
        for field, route in (("current_route", current_route), ("target_route", target_route)):
            if route not in ALLOWED_ROUTES:
                errors.append(f"{prefix}.{field} has unknown route: {route!r}")

        state = workload.get("migration_state")
        if state not in ALLOWED_MIGRATION_STATES:
            errors.append(f"{prefix}.migration_state has unknown state: {state!r}")

        verification = workload.get("terminal_verification")
        if not isinstance(verification, list) or not verification:
            errors.append(f"{prefix}.terminal_verification must be non-empty")
        elif not any(item in {"readback", "provider_readback"} for item in verification):
            errors.append(f"{prefix} must require terminal readback")

        destructive = workload.get("destructive")
        approval = workload.get("operator_approval_required")
        if destructive is True:
            if approval is not True:
                errors.append(f"{prefix} destructive workload must require operator approval")
            required = {"operator_authorization_reference", "mutation_receipt", "provider_readback"}
            missing = required - set(verification or [])
            if missing:
                errors.append(
                    f"{prefix} destructive workload missing verification: {sorted(missing)}"
                )

        if target_route == "public_action_face":
            if workload.get("catalog_admission") != "explicit":
                errors.append(
                    f"{prefix} public_action_face target requires catalog_admission='explicit'"
                )

        if target_route == "private_github_actions_exception":
            if not workload.get("exception_reason"):
                errors.append(
                    f"{prefix} private GitHub Actions target requires exception_reason"
                )
            if not workload.get("exception_review_at"):
                errors.append(
                    f"{prefix} private GitHub Actions target requires exception_review_at"
                )

        if state in {"source_disabled", "complete"}:
            if workload.get("target_route_verified") is not True:
                errors.append(
                    f"{prefix} cannot disable source/complete before target_route_verified=true"
                )

        if state == "complete" and workload.get("verified_delta") in (None, "", False):
            errors.append(f"{prefix} complete requires verified_delta")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Path to estate execution route registry JSON",
    )
    args = parser.parse_args()
    data = load_registry(args.registry)
    errors = validate_registry(data)
    if errors:
        print("ESTATE_EXECUTION_ROUTING: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("ESTATE_EXECUTION_ROUTING: PASS")
    print(f"workloads={len(data['initial_reconciliation'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
