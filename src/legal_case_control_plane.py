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
EXPECTED_CASE_POLICY_SCHEMA = "apex.jack-casebuilder-case-policy.v1"

CASE_POLICY_FILENAMES = {
    "1FDV-23-0001009": "jack_casebuilder_1fdv_policy.json",
}


class LegalCaseControlPlaneError(ValueError):
    pass


def load_binding(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_binding(payload)
    return payload


def load_case_policy(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_case_policy(payload)
    return payload


def load_case_policy_for_case(
    config_dir: str | Path,
    case_id: str,
) -> dict[str, Any]:
    """Resolve and validate the runtime policy for one registered legal matter."""
    filename = CASE_POLICY_FILENAMES.get(case_id)
    if filename is None:
        raise LegalCaseControlPlaneError(
            f"no Jack Casebuilder runtime policy registered for {case_id!r}"
        )
    policy = load_case_policy(Path(config_dir) / filename)
    if policy.get("case_id") != case_id:
        raise LegalCaseControlPlaneError(
            f"case policy identity mismatch: requested {case_id!r}, "
            f"loaded {policy.get('case_id')!r}"
        )
    return policy


def validate_case_policy(policy: dict[str, Any]) -> None:
    errors: list[str] = []
    if policy.get("schema") != EXPECTED_CASE_POLICY_SCHEMA:
        errors.append(f"schema={policy.get('schema')!r}")
    if policy.get("status") != "ACTIVE":
        errors.append("case policy must be ACTIVE")
    if policy.get("case_id") != "1FDV-23-0001009":
        errors.append("1FDV case identity binding missing")
    if policy.get("engine") != "JACK_THE_RIPPER_CASEBUILDER":
        errors.append("Jack Casebuilder engine binding missing")

    authority = policy.get("authority", {})
    if authority.get("case_state_repository") != "GlacierEQ/apex-legal-case":
        errors.append("apex-legal-case authority binding missing")
    if authority.get("lifecycle_does_not_promote_truth_class") is not True:
        errors.append("case-policy truth-class non-promotion invariant missing")
    if authority.get("external_fact_rule") != (
        "authenticated native / official records control external fact"
    ):
        errors.append("native/official external-fact authority rule missing")

    controls = policy.get("runtime_controls", {})
    required_true_controls = {
        "preserve_lossless_detail",
        "event_date_law_required",
        "adverse_evidence_required_before_promotion",
        "gap_becomes_evidence_acquisition_target",
        "unknown_actor_becomes_discovery_target",
        "filing_state_requires_external_receipt",
        "substantial_run_requires_write_and_readback",
        "preserve_contradictions_and_supersession",
    }
    for control in sorted(required_true_controls):
        if controls.get(control) is not True:
            errors.append(f"required runtime control missing: {control}")
    if controls.get("reconstruct_from_scratch") is not False:
        errors.append("continuity invariant must prohibit reconstruction from scratch")

    projections = policy.get("projection_targets", {})
    for peer in ("github", "supabase", "notion", "dropbox"):
        if peer not in projections:
            errors.append(f"required projection peer missing: {peer}")
    airtable = projections.get("airtable", {})
    if airtable.get("status") != "BLOCKED_429_MONTHLY_API_LIMIT":
        errors.append("Airtable degradation state not preserved")
    if airtable.get("failure_is_nonfatal_to_independent_peers") is not True:
        errors.append("peer isolation invariant missing for Airtable degradation")

    quarantine = {
        row.get("id"): row
        for row in policy.get("quarantine", [])
        if isinstance(row, dict)
    }
    for quarantine_id in ("JACK-Q-001", "JACK-Q-002"):
        row = quarantine.get(quarantine_id)
        if not row or row.get("state") != "QUARANTINED":
            errors.append(f"required quarantine missing: {quarantine_id}")

    peer_mesh = policy.get("peer_mesh", {})
    if peer_mesh.get("master_controller") is not False:
        errors.append("peer mesh must not appoint a master controller")
    if peer_mesh.get("case_truth_authority_remains_with_case_state") is not True:
        errors.append("case truth authority boundary missing")
    if peer_mesh.get("cross_peer_mutations_preserve_provenance") is not True:
        errors.append("cross-peer provenance invariant missing")
    if peer_mesh.get("failed_peer_blocks_only_dependent_work") is not True:
        errors.append("peer failure isolation invariant missing")
    if peer_mesh.get("provider_native_receipt_controls_external_execution_claim") is not True:
        errors.append("provider receipt execution-claim invariant missing")

    if errors:
        raise LegalCaseControlPlaneError("; ".join(errors))


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
