#!/usr/bin/env python3
"""Fail-closed validator for the static GlacierEQ execution-route policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "config" / "estate_execution_routes.json"

REQUIRED_ROUTES = {
    "compute_fabric",
    "buildkite_verified_execution",
    "public_action_face",
    "connector_worker_fabric",
    "private_github_actions_exception",
    "none",
}

REQUIRED_ROUTING_LAWS = {
    "selection_is_not_authority",
    "routing_is_not_sovereignty",
    "no_verified_delta_no_success",
    "do_not_disable_current_route_until_target_route_is_proven",
    "do_not_auto_admit_repositories_to_public_action_face",
    "do_not_promote_unverified_compute_backends",
    "destructive_provider_mutation_requires_explicit_operator_authorization",
    "private_github_actions_is_not_the_estate_scheduler",
    "failure_reporting_must_not_depend_on_the_same_failed_execution_substrate",
    "preserve_provider_native_identity_and_receipts",
}


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_policy(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if data.get("status") != "active":
        errors.append("policy status must be active")

    routes = data.get("route_definitions")
    if not isinstance(routes, dict):
        return errors + ["route_definitions must be an object"]

    missing_routes = sorted(REQUIRED_ROUTES - set(routes))
    if missing_routes:
        errors.append(f"missing route definitions: {missing_routes}")

    laws = data.get("routing_laws")
    if not isinstance(laws, list):
        errors.append("routing_laws must be a list")
        laws = []
    missing_laws = sorted(REQUIRED_ROUTING_LAWS - set(laws))
    if missing_laws:
        errors.append(f"missing routing laws: {missing_laws}")

    public_face = routes.get("public_action_face", {})
    if public_face.get("catalog_admission") != "explicit_only":
        errors.append("public_action_face must require explicit_only catalog admission")

    compute = routes.get("compute_fabric", {})
    if compute.get("requires_backend_promotion") is not True:
        errors.append("compute_fabric must require backend promotion")

    connector = routes.get("connector_worker_fabric", {})
    if connector.get("destructive_requires_operator_approval") is not True:
        errors.append("connector_worker_fabric destructive mutation must require operator approval")

    private_actions = routes.get("private_github_actions_exception", {})
    if private_actions.get("default_allowed") is not False:
        errors.append("private GitHub Actions exception route must default deny")
    if private_actions.get("requires_exception_reason") is not True:
        errors.append("private GitHub Actions exception route must require a reason")
    if private_actions.get("requires_expiry_or_review") is not True:
        errors.append("private GitHub Actions exception route must require expiry or review")

    for route_name, route in routes.items():
        if not isinstance(route, dict):
            errors.append(f"route {route_name} must be an object")
            continue
        if not isinstance(route.get("purpose"), str) or not route["purpose"].strip():
            errors.append(f"route {route_name} must declare a purpose")

    dynamic = data.get("dynamic_workload_state")
    if not isinstance(dynamic, dict) or dynamic.get("embedded_in_static_policy") is not False:
        errors.append("time-varying workload state must not be embedded in static route policy")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()
    errors = validate_policy(load_policy(args.policy))
    if errors:
        print("ESTATE_EXECUTION_ROUTING: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("ESTATE_EXECUTION_ROUTING: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
