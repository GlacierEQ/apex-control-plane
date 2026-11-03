#!/usr/bin/env python3
"""Read-only, evidence-aware AWS Free Tier risk assessment.

Operates on a metadata-only snapshot. NEVER calls Cost Explorer, reads credential
values, changes resource configurations, creates budgets, or treats an EC2 tag
as proof of free-tier eligibility. Usage allowances are not dollar budgets.

Snapshot collection should use AWS read-only service metadata, with provenance.
A risk-free metadata snapshot is *not* proof of a zero-dollar AWS bill.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "glaciereq.aws-free-tier-guard.v1"
MIRROR_PREFIX = "/glaciereq/secure-mirror/"
SECRET_PREFIX = "glaciereq/"


def _entry(code: str, severity: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "detail": detail}


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [x for x in value if isinstance(x, dict)]


def _contains_credential_material(value: Any) -> bool:
    if isinstance(value, dict):
        if any(key in value for key in ("SecretString", "SecretBinary", "Plaintext")):
            return True
        if (value.get("Type") == "SecureString" and "Value" in value) or (value.get("type") == "SecureString" and "value" in value):
            return True
        return any(_contains_credential_material(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_credential_material(v) for v in value)
    return False


def _iam_guard_verified(receipt: Any) -> bool:
    if not isinstance(receipt, dict) or receipt.get("source") != "aws_iam_simulator":
        return False
    if not isinstance(receipt.get("principal"), str) or not receipt["principal"].strip():
        return False
    if not isinstance(receipt.get("observed_at"), str) or not receipt["observed_at"].strip():
        return False
    decisions = receipt.get("decisions")
    actions = ("ssm:GetParameter", "ssm:GetParameters", "ssm:GetParameterHistory", "ssm:GetParametersByPath")
    return isinstance(decisions, dict) and all(decisions.get(action) == "explicitDeny" for action in actions)


def assess(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Evaluate only documented metadata. No secret values appear in output."""
    if not isinstance(snapshot, dict):
        raise ValueError("Expected a dictionary snapshot")
    if _contains_credential_material(snapshot):
        raise ValueError("Credential material detected in input; supply metadata only")
    regions = snapshot.get("regions")
    findings: list[dict[str, str]] = []
    counts = {
        "billable_secret_count": 0,
        "secure_standard_mirror_count": 0,
        "unmirrored_secret_count": 0,
        "noncompliant_mirror_count": 0,
        "running_ec2_count": 0,
        "instance_public_ipv4_assignments": 0,
        "allocated_elastic_ips": 0,
        "other_namespace_secret_count": 0,
        "missing_region_count": 0,
        "ebs_gb": 0,
        "regions_observed": 0,
        "always_free_categories_reported": 0,
    }

    if not isinstance(regions, dict) or not regions:
        findings.append(_entry("NO_REGION_EVIDENCE", "ERROR", "No regional resource inventory; fail closed."))
        regions = {}
    else:
        counts["regions_observed"] = len(regions)

    for region, raw in sorted(regions.items()):
        if not isinstance(raw, dict):
            findings.append(_entry("INVALID_REGION_METADATA", "ERROR", f"Missing metadata for {region}."))
            continue
        active_secrets = [
            item for item in _records(raw.get("secrets"))
            if isinstance(item.get("name"), str) and not item.get("pending_deletion", False)
        ]
        sources = {
            s["name"][len(SECRET_PREFIX):] for s in active_secrets
            if s["name"].startswith(SECRET_PREFIX)
        }
        counts["other_namespace_secret_count"] += len(active_secrets) - len(sources)
        params = _records(raw.get("parameters"))
        mirrored: set[str] = set()
        for p in params:
            path = p.get("name")
            if not isinstance(path, str) or not path.startswith(MIRROR_PREFIX):
                continue
            suffix = path[len(MIRROR_PREFIX):]
            if p.get("type") == "SecureString" and p.get("tier") == "Standard":
                mirrored.add(suffix)
            else:
                counts["noncompliant_mirror_count"] += 1
        counts["billable_secret_count"] += len(active_secrets)
        counts["secure_standard_mirror_count"] += len(mirrored)
        counts["unmirrored_secret_count"] += len(sources - mirrored)
        for instance in _records(raw.get("instances")):
            if instance.get("state") == "running":
                counts["running_ec2_count"] += 1
            if instance.get("has_public_ip") is True:
                counts["instance_public_ipv4_assignments"] += 1
        counts["allocated_elastic_ips"] += len(_records(raw.get("addresses")))
        for volume in _records(raw.get("volumes")):
            size = volume.get("size_gb")
            if isinstance(size, (int, float)) and size >= 0:
                counts["ebs_gb"] += size

    expected_regions = snapshot.get("expected_regions")
    if isinstance(expected_regions, list):
        counts["missing_region_count"] = len(set(str(r) for r in expected_regions) - set(regions))
        if counts["missing_region_count"]:
            findings.append(_entry("REGIONAL_INVENTORY_INCOMPLETE", "ERROR", f"{counts['missing_region_count']} expected regions not inspected."))
    else:
        findings.append(_entry("REGIONAL_COVERAGE_UNVERIFIED", "WARN", "No expected region manifest; cannot establish full AWS regional coverage."))
    if counts["other_namespace_secret_count"]:
        findings.append(_entry("OUT_OF_SCOPE_BILLABLE_SECRETS", "ERROR", f"{counts['other_namespace_secret_count']} Secrets Manager entries are outside the configured migration namespace."))
    if counts["billable_secret_count"]:
        findings.append(_entry(
            "BILLABLE_SECRET_ORIGINALS", "ERROR",
            f"{counts['billable_secret_count']} active Secrets Manager records still incur potential storage charges. Copies do not stop source billing.",
        ))
    if counts["unmirrored_secret_count"]:
        findings.append(_entry(
            "SECRET_MIRROR_INCOMPLETE", "ERROR",
            f"{counts['unmirrored_secret_count']} sources have no same-region encrypted Standard mirror metadata.",
        ))
    if counts["secure_standard_mirror_count"] and not _iam_guard_verified(snapshot.get("mirror_access_guard")):
        findings.append(_entry(
            "MIRROR_IAM_UNVERIFIED", "WARN",
            "Standard SecureString type alone is not proof of restricted reads; supply a fresh IAM simulator receipt.",
        ))
    if counts["noncompliant_mirror_count"]:
        findings.append(_entry(
            "UNSAFE_SECRET_MIRROR", "ERROR",
            f"{counts['noncompliant_mirror_count']} mirror parameters are not Standard SecureStrings.",
        ))
    if counts["running_ec2_count"]:
        findings.append(_entry(
            "RUNNING_EC2_REVIEW_BILLING", "WARN",
            f"{counts['running_ec2_count']} EC2 instances running; tags do not prove free-tier eligibility.",
        ))
    if counts["instance_public_ipv4_assignments"] or counts["allocated_elastic_ips"]:
        findings.append(_entry(
            "PUBLIC_IPV4_REVIEW_BILLING", "WARN",
            f"{counts['instance_public_ipv4_assignments']} instance assignments and {counts['allocated_elastic_ips']} Elastic IP allocations need billing review; these can overlap.",
        ))
    if counts["ebs_gb"]:
        findings.append(_entry(
            "EBS_STORAGE_REMAINS", "WARN",
            f"{counts['ebs_gb']:g} GB attached or unattached EBS volumes require billing verification even with EC2 stopped.",
        ))

    plan = snapshot.get("plan")
    if not isinstance(plan, dict) or plan.get("type") is None:
        findings.append(_entry("ACCOUNT_PLAN_UNVERIFIED", "WARN", "Account plan and credit eligibility not established."))
    elif plan.get("type") == "PAID" and plan.get("remaining_credits_usd") == 0:
        findings.append(_entry("NO_FREE_PLAN_CREDITS", "INFO", "Paid account; no Free Plan credits. Always Free service allowances may still apply."))
    for entry in _records(snapshot.get("free_usage")):
        if entry.get("tier") != "Always Free":
            continue
        counts["always_free_categories_reported"] += 1
        used, limit = entry.get("used"), entry.get("limit")
        if isinstance(used, (int, float)) and isinstance(limit, (int, float)) and limit > 0 and used >= 0.9 * limit:
            findings.append(_entry(
                "ALWAYS_FREE_QUOTA_NEAR_LIMIT", "WARN",
                "At least one Always Free usage category is at or above 90% of its stated allowance.",
            ))
    if "free_usage" not in snapshot:
        findings.append(_entry("FREE_ALLOWANCES_UNVERIFIED", "WARN", "No live free-usage metadata supplied."))
    findings.append(_entry(
        "COST_STATUS_NOT_PROVEN_FROM_RESOURCE_METADATA", "INFO",
        "Resource metadata and usage quotas cannot certify a zero-dollar bill or exclude unobserved services.",
    ))
    return {
        "schema": SCHEMA,
        "policy": "usage_quotas_not_dollar_budget",
        "status": "ACTION_REQUIRED" if any(f["severity"] == "ERROR" for f in findings) else "REVIEW",
        "accepted_zero_recurring": False,
        "inventory": counts,
        "findings": findings,
        "safety": {
            "credential_values_read": False,
            "aws_mutations": False,
            "cost_explorer_requests": False,
            "billing_budget_enforced": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Assess a metadata-only AWS free-tier snapshot without AWS API calls")
    parser.add_argument("snapshot", type=Path, help="JSON metadata snapshot; do not include credentials")
    arguments = parser.parse_args()
    report = assess(json.loads(arguments.snapshot.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
