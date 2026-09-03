"""APEX adapter for Casebuilder4000 continuous legal-case health.

This module projects operational health only. It must never promote or demote the
truth class of a fact, allegation, authority, or evidence item.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPECTED_BINDING_SCHEMA = "apex.legal-case-control-plane.v1"
EXPECTED_CASEBUILDER_HEALTH_SCHEMA = "casebuilder4000.control-plane-health.v1"


class LegalCaseControlPlaneError(ValueError):
    pass


def load_binding(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_binding(payload)
    return payload


def validate_binding(binding: dict[str, Any]) -> None:
    errors: list[str] = []
    if binding.get("schema") != EXPECTED_BINDING_SCHEMA:
        errors.append(
            f"schema={binding.get('schema')!r}"
        )

    source = binding.get("source_of_case_truth", {})
    if source.get("repository") != "GlacierEQ/Casebuilder4000":
        errors.append("Casebuilder4000 source-of-case-truth binding missing")
    if source.get("lifecycle_does_not_promote_truth_class") is not True:
        errors.append("truth-class non-promotion invariant missing")

    registry = binding.get("estate_registry", {})
    if registry.get("preserves_matter_identity") is not True:
        errors.append("matter identity preservation invariant missing")

    host = binding.get("host_execution", {})
    if host.get("repository") != "GlacierEQ/computer-user":
        errors.append("computer-user host execution binding missing")

    runtime = binding.get("local_casebuilder_runtime", {})
    if runtime.get("health_schema") != EXPECTED_CASEBUILDER_HEALTH_SCHEMA:
        errors.append("Casebuilder health schema binding missing")
    if runtime.get("store") != "control_plane.sqlite3":
        errors.append("durable Casebuilder control store binding missing")

    anti_collapse = set(binding.get("anti_collapse", []))
    required_anti_collapse = {
        "APEX does not become case truth authority",
        "host execution does not become case truth authority",
        "case overlap creates links, not silent merges",
    }
    missing = required_anti_collapse - anti_collapse
    if missing:
        errors.append(
            "anti-collapse invariants missing: "
            + ", ".join(sorted(missing))
        )

    envelope = set(
        binding.get("event_bridge", {}).get(
            "required_envelope",
            [],
        )
    )
    required_envelope = {
        "case_id",
        "event_type",
        "source",
        "correlation_id",
        "idempotency_key",
        "payload",
    }
    missing_envelope = required_envelope - envelope
    if missing_envelope:
        errors.append(
            "event envelope fields missing: "
            + ", ".join(sorted(missing_envelope))
        )

    if errors:
        raise LegalCaseControlPlaneError("; ".join(errors))


def normalize_casebuilder_health(
    snapshot: dict[str, Any],
    *,
    revision_chain_valid: bool | None = None,
    evidence_chain_valid: bool | None = None,
    build_verified: bool | None = None,
    truth_acceptance: str = "unknown",
) -> dict[str, Any]:
    """Normalize Casebuilder local health into APEX operational health."""
    if snapshot.get("schema") != EXPECTED_CASEBUILDER_HEALTH_SCHEMA:
        raise LegalCaseControlPlaneError(
            "unexpected Casebuilder health schema: "
            f"{snapshot.get('schema')!r}"
        )

    blocked_reasons: list[str] = []
    degraded_reasons: list[str] = []

    if revision_chain_valid is False:
        blocked_reasons.append("case_revision_chain_invalid")
    if evidence_chain_valid is False:
        blocked_reasons.append("evidence_manifest_chain_invalid")
    if build_verified is False:
        blocked_reasons.append("build_receipt_invalid")
    if truth_acceptance == "rejected":
        blocked_reasons.append("truth_provenance_acceptance_rejected")

    work = snapshot.get("work", {})
    failed = int(work.get("failed") or 0)
    blocked = int(work.get("blocked") or 0)
    backlog = int(work.get("backlog") or 0)
    inflight = int(work.get("inflight") or 0)
    deliveries = snapshot.get("deliveries", {})
    delivery_failed = int(deliveries.get("failed") or 0)
    workers = snapshot.get("workers", [])
    live_workers = [
        worker
        for worker in workers
        if not worker.get("stale")
        and worker.get("status") in {"online", "ready", "running"}
    ]
    stale_workers = [
        worker
        for worker in workers
        if worker.get("stale")
    ]

    if blocked:
        blocked_reasons.append("blocked_work")
    if failed:
        degraded_reasons.append("terminal_failed_work")
    if delivery_failed:
        degraded_reasons.append("external_delivery_failed")
    if stale_workers:
        degraded_reasons.append("stale_worker")
    if backlog and not live_workers:
        degraded_reasons.append("backlog_without_live_worker")
    if inflight and not live_workers:
        degraded_reasons.append("inflight_without_live_worker")
    if snapshot.get("status") == "degraded":
        degraded_reasons.append("casebuilder_local_degraded")

    if blocked_reasons:
        status = "blocked"
    elif degraded_reasons:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "schema": "apex.legal-case-runtime-health.v1",
        "status": status,
        "source_status": snapshot.get("status"),
        "observed_at": snapshot.get("observed_at"),
        "casebuilder": {
            "events": snapshot.get("events", {}),
            "work": work,
            "deliveries": deliveries,
            "workers": workers,
            "latest_checkpoint": snapshot.get("latest_checkpoint"),
        },
        "integrity": {
            "revision_chain_valid": revision_chain_valid,
            "evidence_chain_valid": evidence_chain_valid,
            "build_verified": build_verified,
            "truth_acceptance": truth_acceptance,
        },
        "blocked_reasons": sorted(set(blocked_reasons)),
        "degraded_reasons": sorted(set(degraded_reasons)),
        "truth_class_mutated": False,
    }
